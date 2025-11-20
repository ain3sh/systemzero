#!/usr/bin/env node

// CheckpointEngine
// Lightweight, Rewind-native snapshot engine for project code
//
// Responsibilities:
// - Scan project files with configurable ignore patterns
// - Create full checkpoints as tarballs under .rewind/code/snapshots
// - Maintain a manifest and simple changelog
// - Restore a checkpoint (with an automatic emergency backup)

import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { spawn } from 'child_process';
import { createHash } from 'crypto';

const DEFAULT_CONFIG = {
  maxCheckpoints: 10,
  maxAgeDays: 30, // 0 = no age limit
  ignorePatterns: [
    '.git',
    '.rewind',
    '.claude',
    '.factory',
    'node_modules',
    '.env',
    '.env.*',
    '*.log',
    '.DS_Store',
    'Thumbs.db',
    '__pycache__',
    '*.pyc',
    '.vscode',
    '.idea',
    'dist',
    'build',
    'coverage',
    '.next',
    '.nuxt',
    '.cache',
    'tmp',
    'temp'
  ],
  additionalIgnores: [],
  forceInclude: [],
  nameTemplate: 'checkpoint_{timestamp}'
};

export class CheckpointEngine {
  constructor({ projectRoot = process.cwd() } = {}) {
    this.projectRoot = path.resolve(projectRoot);
    this.baseDir = path.join(this.projectRoot, '.rewind', 'code');
    this.snapshotsDir = path.join(this.baseDir, 'snapshots');
    this.configFile = path.join(this.baseDir, 'config.json');
    this.changelogFile = path.join(this.baseDir, 'changelog.json');
  }

  async ensureDirs() {
    await fs.mkdir(this.snapshotsDir, { recursive: true });
  }

  async loadConfig() {
    try {
      const raw = await fs.readFile(this.configFile, 'utf8');
      const config = JSON.parse(raw);
      const merged = { ...DEFAULT_CONFIG, ...config };
      return await this.applyProjectOverrides(merged);
    } catch (err) {
      if (err.code !== 'ENOENT') throw err;
      await this.saveConfig(DEFAULT_CONFIG);
      return await this.applyProjectOverrides({ ...DEFAULT_CONFIG });
    }
  }

  async saveConfig(config) {
    await fs.mkdir(this.baseDir, { recursive: true });
    const merged = { ...DEFAULT_CONFIG, ...config };
    await fs.writeFile(this.configFile, JSON.stringify(merged, null, 2), 'utf8');
  }

  async applyProjectOverrides(config) {
    const overrides = await this.loadProjectIgnoreOverrides();
    if (!overrides) return config;

    const updated = { ...config };
    if (Array.isArray(overrides.ignorePatterns) && overrides.ignorePatterns.length) {
      updated.ignorePatterns = overrides.ignorePatterns;
    }
    if (Array.isArray(overrides.additionalIgnores) && overrides.additionalIgnores.length) {
      updated.additionalIgnores = this.mergeUnique(updated.additionalIgnores, overrides.additionalIgnores);
    }
    if (Array.isArray(overrides.forceInclude) && overrides.forceInclude.length) {
      updated.forceInclude = this.mergeUnique(updated.forceInclude, overrides.forceInclude);
    }

    return updated;
  }

  async loadProjectIgnoreOverrides() {
    const candidates = [
      path.join(this.projectRoot, 'configs', 'rewind-checkpoint-ignore.json'),
      path.join(this.projectRoot, 'rewind-checkpoint-ignore.json')
    ];

    for (const candidate of candidates) {
      try {
        const raw = await fs.readFile(candidate, 'utf8');
        return JSON.parse(raw);
      } catch (err) {
        if (err.code === 'ENOENT') {
          continue;
        }
        throw err;
      }
    }
    return null;
  }

  async readGitignorePatterns() {
    const gitignorePath = path.join(this.projectRoot, '.gitignore');
    try {
      const content = await fs.readFile(gitignorePath, 'utf8');
      return content
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('#'));
    } catch (err) {
      if (err.code === 'ENOENT') return [];
      throw err;
    }
  }

  patternToRegex(pattern) {
    // Treat directories ending with / as prefixes
    const p = pattern.replace(/\\/g, '/').replace(/\/\.$/, '');
    if (!p) return null;
    // Escape regex special chars except *
    const escaped = p.replace(/[-/\\^$+?.()|[\]{}]/g, '\\$&').replace(/\*/g, '.*');
    return new RegExp(`^${escaped}$`);
  }

  buildIgnoreMatcher(config, gitignorePatterns) {
    const ignorePatterns = [
      ...(config.ignorePatterns || []),
      ...(config.additionalIgnores || []),
      ...gitignorePatterns
    ];
    const forcePatterns = config.forceInclude || [];

    const ignoreRegexes = ignorePatterns
      .map(p => this.patternToRegex(p))
      .filter(Boolean);
    const forceRegexes = forcePatterns
      .map(p => this.patternToRegex(p))
      .filter(Boolean);

    return relPath => {
      const normalized = relPath.replace(/\\/g, '/');
      const ignored = ignoreRegexes.some(rx => rx.test(normalized));
      if (!ignored) return false;
      const forceIncluded = forceRegexes.some(rx => rx.test(normalized));
      return !forceIncluded;
    };
  }

  mergeUnique(base = [], extra = []) {
    const set = new Set(base || []);
    for (const value of extra || []) {
      if (value) {
        set.add(value);
      }
    }
    return Array.from(set);
  }

  async scanProject() {
    const config = await this.loadConfig();
    const gitignore = await this.readGitignorePatterns();
    const shouldIgnore = this.buildIgnoreMatcher(config, gitignore);

    // Safety guard: refuse to scan bare home directory
    const home = os.homedir();
    if (this.projectRoot === home) {
      throw new Error(`Refusing to scan home directory as projectRoot: ${this.projectRoot}`);
    }

    const files = [];

    const walk = async dir => {
      const entries = await fs.readdir(dir, { withFileTypes: true });
      for (const entry of entries) {
        const full = path.join(dir, entry.name);
        const rel = path.relative(this.projectRoot, full);
        if (!rel || rel.startsWith('..')) continue;

        if (entry.isDirectory()) {
          if (!shouldIgnore(rel + '/')) {
            await walk(full);
          }
        } else if (entry.isFile()) {
          if (!shouldIgnore(rel)) {
            files.push(rel);
          }
        }
      }
    };

    await walk(this.projectRoot);
    files.sort();
    return files;
  }

  async getFileStats(files) {
    const stats = [];
    for (const rel of files) {
      try {
        const stat = await fs.stat(path.join(this.projectRoot, rel));
        stats.push({ path: rel, size: stat.size, mtimeMs: stat.mtimeMs });
      } catch {
        stats.push({ path: rel, size: 0, mtimeMs: 0 });
      }
    }
    return stats;
  }

  computeSignature(fileStats) {
    const hash = createHash('sha256');
    for (const info of fileStats) {
      hash.update(info.path);
      hash.update(String(info.size));
      hash.update(String(info.mtimeMs));
    }
    return hash.digest('hex');
  }

  async createCheckpoint({ description = '', name, force = false } = {}) {
    await this.ensureDirs();
    const files = await this.scanProject();
    if (!files.length) {
      return { success: false, error: 'No files found to checkpoint', noChanges: true };
    }

    const fileStats = await this.getFileStats(files);
    const totalBytes = fileStats.reduce((sum, info) => sum + (info.size || 0), 0);
    const signature = this.computeSignature(fileStats);

    const latest = await this.getLatestCheckpoint();
    if (!force && latest && latest.signature === signature) {
      return { success: false, noChanges: true, message: 'No changes detected since last checkpoint' };
    }

    const effectiveName = this.generateCheckpointName({ name, description });
    const snapshotDir = path.join(this.snapshotsDir, effectiveName);
    await fs.mkdir(snapshotDir, { recursive: true });

    const manifest = {
      name: effectiveName,
      timestamp: new Date().toISOString(),
      description: description || 'Rewind checkpoint',
      files,
      fileCount: files.length,
      totalSize: totalBytes,
      signature,
      filesMetadata: fileStats
    };

    await fs.writeFile(
      path.join(snapshotDir, 'manifest.json'),
      JSON.stringify(manifest, null, 2),
      'utf8'
    );

    const tarPath = path.join(snapshotDir, 'files.tar.gz');
    await this.createTarball({ files, tarPath });

    await this.cleanupOldCheckpoints();
    await this.logChangelog({
      action: 'CREATE_CHECKPOINT',
      description: `Created checkpoint: ${effectiveName}`,
      details: manifest.description
    });

    return {
      success: true,
      name: effectiveName,
      description: manifest.description,
      fileCount: files.length,
      totalBytes
    };
  }

  generateCheckpointName({ name, description }) {
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    if (name && name.trim()) {
      const cleanName = name
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, '')
        .trim()
        .replace(/\s+/g, '_')
        .slice(0, 30) || 'checkpoint';
      return `${cleanName}_${ts}`;
    }
    if (description && description.trim()) {
      const clean = description
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, '')
        .trim()
        .replace(/\s+/g, '_')
        .slice(0, 30) || 'checkpoint';
      return `${clean}_${ts}`;
    }
    return `checkpoint_${ts}`;
  }

  createTarball({ files, tarPath }) {
    return new Promise((resolve, reject) => {
      const args = ['-czf', tarPath, '-C', this.projectRoot, ...files];
      const proc = spawn('tar', args, { stdio: ['ignore', 'ignore', 'pipe'] });

      let stderr = '';
      proc.stderr.on('data', chunk => {
        stderr += chunk.toString();
      });

      proc.on('close', code => {
        if (code === 0) return resolve();
        const msg = stderr || `tar exited with code ${code}`;
        reject(new Error(`Failed to create tarball: ${msg.trim()}`));
      });
    });
  }

  async listCheckpoints() {
    try {
      await this.ensureDirs();
      const entries = await fs.readdir(this.snapshotsDir, { withFileTypes: true });
      const manifests = [];
      for (const entry of entries) {
        if (!entry.isDirectory()) continue;
        const manifestPath = path.join(this.snapshotsDir, entry.name, 'manifest.json');
        try {
          const raw = await fs.readFile(manifestPath, 'utf8');
          const m = JSON.parse(raw);
          manifests.push(m);
        } catch {
          // Ignore bad manifests
        }
      }
      return manifests.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    } catch (err) {
      if (err.code === 'ENOENT') return [];
      throw err;
    }
  }

  async restoreCheckpoint({ name }) {
    await this.ensureDirs();
    const checkpoints = await this.listCheckpoints();
    if (!checkpoints.length) {
      return { success: false, error: 'No checkpoints available' };
    }

    const target = checkpoints.find(cp => cp.name === name) ||
      checkpoints.find(cp => cp.name.includes(name));

    if (!target) {
      return { success: false, error: `Checkpoint not found: ${name}` };
    }

    // Emergency backup before restore
    const backup = await this.createCheckpoint({ description: 'Auto-backup before restore', name: 'rewind_backup', force: true });
    const backupName = backup.success ? backup.name : null;

    await this.applyRestore(target);

    await this.logChangelog({
      action: 'RESTORE_CHECKPOINT',
      description: `Restored checkpoint: ${target.name}`,
      details: backupName ? `Emergency backup: ${backupName}` : 'Emergency backup unavailable'
    });

    return { success: true, restored: target.name, emergencyBackup: backupName };
  }

  async undoLastCheckpoint() {
    const checkpoints = await this.listCheckpoints();
    if (!checkpoints.length) {
      return { success: false, error: 'No checkpoints to undo' };
    }
    return this.restoreCheckpoint({ name: checkpoints[0].name });
  }

  async applyRestore(checkpoint) {
    const currentFiles = await this.scanProject();
    const currentSet = new Set(currentFiles);
    const snapshotSet = new Set(checkpoint.files || []);

    // Delete any file that exists now but not in the snapshot
    for (const file of currentSet) {
      if (!snapshotSet.has(file)) {
        try {
          await fs.unlink(path.join(this.projectRoot, file));
        } catch {
          // Ignore deletion failures
        }
      }
    }

    // Extract tarball
    const snapshotDir = path.join(this.snapshotsDir, checkpoint.name);
    const tarPath = path.join(snapshotDir, 'files.tar.gz');
    await this.extractTarball({ tarPath });
  }

  extractTarball({ tarPath }) {
    return new Promise((resolve, reject) => {
      const args = ['-xzf', tarPath, '-C', this.projectRoot];
      const proc = spawn('tar', args, { stdio: ['ignore', 'ignore', 'pipe'] });

      let stderr = '';
      proc.stderr.on('data', chunk => {
        stderr += chunk.toString();
      });

      proc.on('close', code => {
        if (code === 0) return resolve();
        const msg = stderr || `tar exited with code ${code}`;
        reject(new Error(`Failed to extract tarball: ${msg.trim()}`));
      });
    });
  }

  async cleanupOldCheckpoints() {
    const config = await this.loadConfig();
    const checkpoints = await this.listCheckpoints();
    const now = Date.now();

    const toDelete = [];

    if (config.maxAgeDays && config.maxAgeDays > 0) {
      const cutoff = now - config.maxAgeDays * 24 * 60 * 60 * 1000;
      for (const cp of checkpoints) {
        const ts = new Date(cp.timestamp).getTime();
        if (!Number.isNaN(ts) && ts < cutoff) {
          toDelete.push(cp);
        }
      }
    }

    const remaining = checkpoints.filter(cp => !toDelete.includes(cp));
    if (config.maxCheckpoints && remaining.length > config.maxCheckpoints) {
      const excess = remaining.slice(config.maxCheckpoints);
      toDelete.push(...excess);
    }

    // Delete uniquely
    const unique = Array.from(new Set(toDelete.map(cp => cp.name)));
    for (const name of unique) {
      const dir = path.join(this.snapshotsDir, name);
      try {
        await fs.rm(dir, { recursive: true, force: true });
      } catch {
        // Ignore cleanup failures
      }
    }
  }

  async logChangelog({ action, description, details }) {
    try {
      let entries = [];
      try {
        const raw = await fs.readFile(this.changelogFile, 'utf8');
        entries = JSON.parse(raw);
      } catch (err) {
        if (err.code !== 'ENOENT') throw err;
      }

      entries.unshift({
        timestamp: new Date().toISOString(),
        action,
        description,
        details
      });

      if (entries.length > 50) {
        entries = entries.slice(0, 50);
      }

      await fs.writeFile(this.changelogFile, JSON.stringify(entries, null, 2), 'utf8');
    } catch {
      // Changelog failures should not break main flow
    }
  }

  async getLatestCheckpoint() {
    const checkpoints = await this.listCheckpoints();
    return checkpoints.length ? checkpoints[0] : null;
  }
}

// Minimal CLI for debugging / manual use
if (import.meta.url === `file://${process.argv[1]}`) {
  const [, , cmd, ...rest] = process.argv;
  const engine = new CheckpointEngine({ projectRoot: process.cwd() });

  (async () => {
    try {
      switch (cmd) {
        case 'save': {
          const description = rest.join(' ');
          const result = await engine.createCheckpoint({ description });
          console.log(JSON.stringify(result, null, 2));
          break;
        }
        case 'list': {
          const cps = await engine.listCheckpoints();
          console.log(JSON.stringify(cps, null, 2));
          break;
        }
        case 'undo': {
          const result = await engine.undoLastCheckpoint();
          console.log(JSON.stringify(result, null, 2));
          break;
        }
        case 'restore': {
          const name = rest[0];
          if (!name) {
            console.error('Usage: CheckpointEngine.js restore <name>');
            process.exit(1);
          }
          const result = await engine.restoreCheckpoint({ name });
          console.log(JSON.stringify(result, null, 2));
          break;
        }
        default:
          console.log('Usage: CheckpointEngine.js <save|list|undo|restore> [args]');
          process.exit(1);
      }
    } catch (err) {
      console.error(err.message || String(err));
      process.exit(1);
    }
  })();
}
