import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { spawn } from 'child_process';
import { createHash } from 'crypto';
import { atomicWrite, ensureDir, fileExists, safeStatFile } from '../utils/fs-utils.js';
import { ConfigLoader } from './ConfigLoader.js';

/**
 * CheckpointStore - Enhanced file system snapshot manager
 * 
 * Improvements over CheckpointEngine:
 * - Fast scan optimization with persistent signatures
 * - Centralized configuration via ConfigLoader
 * - Better error handling and atomic operations
 * - Diff summaries for UI
 */
export class CheckpointStore {
  constructor({ projectRoot = process.cwd() } = {}) {
    this.projectRoot = path.resolve(projectRoot);
    this.configLoader = new ConfigLoader(projectRoot);
    this.initialized = false;
  }

  /**
   * Initialize storage paths based on configuration
   */
  async initialize() {
    if (this.initialized) return;

    // Use getStorageMode to resolve the correct mode (config > fallback)
    const storageMode = await this.configLoader.getStorageMode();
    
    if (storageMode === 'global') {
      const config = await this.configLoader.getConfig();
      // User-level storage: ~/.rewind/storage/<sanitized_project_path>
      const home = os.homedir();
      const globalRoot = config.storage?.path || path.join(home, '.rewind', 'storage');
      const projectHash = createHash('sha256').update(this.projectRoot).digest('hex').slice(0, 12);
      const projectName = path.basename(this.projectRoot).replace(/[^a-zA-Z0-9_-]/g, '_');
      
      this.baseDir = path.join(globalRoot, `${projectName}_${projectHash}`);
    } else {
      // Project-level storage: <project>/.rewind/code
      this.baseDir = path.join(this.projectRoot, '.rewind', 'code');
    }

    this.snapshotsDir = path.join(this.baseDir, 'snapshots');
    this.changelogFile = path.join(this.baseDir, 'changelog.json');
    this.headSignatureFile = path.join(this.baseDir, 'head_signature');
    
    // Ensure base directory exists (crucial for global mode)
    await ensureDir(this.baseDir);
    this.initialized = true;
  }

  async ensureDirs() {
    if (!this.initialized) await this.initialize();
    await ensureDir(this.snapshotsDir);
  }

  async getConfig() {
    return await this.configLoader.getConfig();
  }

  /**
   * Fast scan: Check if files changed since last checkpoint
   * Uses mtime + size comparison with cached signature
   */
  async hasChanges() {
    try {
      // Get current head signature if it exists
      let headSignature = null;
      if (await fileExists(this.headSignatureFile)) {
        headSignature = await fs.readFile(this.headSignatureFile, 'utf8');
      }

      // If no head signature, assume changes exist
      if (!headSignature) {
        return true;
      }

      // Quick scan: mtime + size only
      const files = await this.scanProject();
      const quickStats = await this.getQuickFileStats(files);
      const quickSignature = this.computeQuickSignature(quickStats);

      return quickSignature !== headSignature;
    } catch (error) {
      // On error, assume changes exist to be safe
      return true;
    }
  }

  /**
   * Get lightweight file stats (mtime + size only)
   */
  async getQuickFileStats(files) {
    const stats = [];
    for (const relPath of files) {
      const stat = await safeStatFile(path.join(this.projectRoot, relPath));
      if (stat) {
        stats.push({
          path: relPath,
          size: stat.size,
          mtimeMs: Math.floor(stat.mtimeMs) // Round to avoid precision issues
        });
      }
    }
    return stats;
  }

  /**
   * Compute quick signature from mtime + size
   */
  computeQuickSignature(quickStats) {
    const hash = createHash('sha256');
    for (const info of quickStats) {
      hash.update(info.path);
      hash.update(String(info.size));
      hash.update(String(info.mtimeMs));
    }
    return hash.digest('hex');
  }

  /**
   * Update the head signature after successful checkpoint
   */
  async updateHeadSignature() {
    try {
      const files = await this.scanProject();
      const quickStats = await this.getQuickFileStats(files);
      const signature = this.computeQuickSignature(quickStats);
      await atomicWrite(this.headSignatureFile, signature, 'utf8');
    } catch (error) {
      // Non-fatal error - checkpoint still succeeded
      console.warn('[CheckpointStore] Failed to update head signature:', error.message);
    }
  }

  /**
   * Scan project files using configuration
   */
  async scanProject() {
    const config = await this.getConfig();
    const gitignorePatterns = await this.configLoader.getGitignorePatterns();
    const shouldIgnore = this.buildIgnoreMatcher(config, gitignorePatterns);

    // Safety: refuse to scan home directory
    const home = os.homedir();
    if (this.projectRoot === home) {
      throw new Error(`Refusing to scan home directory as projectRoot: ${this.projectRoot}`);
    }

    const files = [];

    const walk = async (dir) => {
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

  /**
   * Build ignore matcher from configuration
   */
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
      
      // Always ignore .rewind directory and its contents
      if (normalized.startsWith('.rewind/') || normalized === '.rewind') {
        return true;
      }
      
      const ignored = ignoreRegexes.some(rx => rx.test(normalized));
      if (!ignored) return false;
      const forceIncluded = forceRegexes.some(rx => rx.test(normalized));
      return !forceIncluded;
    };
  }

  patternToRegex(pattern) {
    const p = pattern.replace(/\\/g, '/').replace(/\/\.$/, '');
    if (!p) return null;
    const escaped = p.replace(/[-/\\^$+?.()|[\]{}]/g, '\\$&').replace(/\*/g, '.*');
    return new RegExp(`^${escaped}$`);
  }

  /**
   * Get detailed file stats for full signature computation
   */
  async getDetailedFileStats(files) {
    const stats = [];
    for (const relPath of files) {
      try {
        const stat = await fs.stat(path.join(this.projectRoot, relPath));
        stats.push({ 
          path: relPath, 
          size: stat.size, 
          mtimeMs: stat.mtimeMs 
        });
      } catch {
        stats.push({ 
          path: relPath, 
          size: 0, 
          mtimeMs: 0 
        });
      }
    }
    return stats;
  }

  computeDetailedSignature(fileStats) {
    const hash = createHash('sha256');
    for (const info of fileStats) {
      hash.update(info.path);
      hash.update(String(info.size));
      hash.update(String(info.mtimeMs));
    }
    return hash.digest('hex');
  }

  /**
   * Create checkpoint with optimization
   */
  async createCheckpoint({ description = '', name, force = false } = {}) {
    await this.ensureDirs();
    
    // Fast check first unless forced
    if (!force && !await this.hasChanges()) {
      return { 
        success: false, 
        noChanges: true, 
        message: 'No changes detected since last checkpoint' 
      };
    }

    const files = await this.scanProject();
    if (!files.length) {
      return { 
        success: false, 
        error: 'No files found to checkpoint', 
        noChanges: true 
      };
    }

    const fileStats = await this.getDetailedFileStats(files);
    const totalBytes = fileStats.reduce((sum, info) => sum + (info.size || 0), 0);
    const signature = this.computeDetailedSignature(fileStats);

    const config = await this.getConfig();
    const effectiveName = this.generateCheckpointName({ name, description, config });
    const snapshotDir = path.join(this.snapshotsDir, effectiveName);
    await ensureDir(snapshotDir);

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

    const tarPath = path.join(snapshotDir, 'files.tar.gz');
    
    // Create tarball first to catch any errors early
    try {
      await this.createTarball({ files, tarPath });
    } catch (error) {
      // Clean up the snapshot directory if tarball creation fails
      try {
        await fs.rm(snapshotDir, { recursive: true, force: true });
      } catch {
        // Ignore cleanup errors
      }
      throw new Error(`Failed to create checkpoint tarball: ${error.message}`);
    }

    // Only write manifest after successful tarball creation
    await atomicWrite(
      path.join(snapshotDir, 'manifest.json'),
      JSON.stringify(manifest, null, 2),
      'utf8'
    );

    await this.updateHeadSignature();
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
      totalBytes,
      signature
    };
  }

  generateCheckpointName({ name, description, config }) {
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

  /**
   * Get diff summary between two checkpoints
   */
  async getDiffSummary(checkpointA, checkpointB) {
    const filesA = new Set(checkpointA.files || []);
    const filesB = new Set(checkpointB.files || []);
    
    const added = [];
    const removed = [];
    const modified = [];

    // Files in B but not A = added
    for (const file of filesB) {
      if (!filesA.has(file)) {
        added.push(file);
      }
    }

    // Files in A but not B = removed
    for (const file of filesA) {
      if (!filesB.has(file)) {
        removed.push(file);
      }
    }

    // Files in both with different metadata = potentially modified
    const metadataA = new Map((checkpointA.filesMetadata || []).map(f => [f.path, f]));
    const metadataB = new Map((checkpointB.filesMetadata || []).map(f => [f.path, f]));

    for (const file of filesA) {
      if (filesB.has(file)) {
        const statA = metadataA.get(file);
        const statB = metadataB.get(file);
        if (statA && statB && 
            (statA.size !== statB.size || statA.mtimeMs !== statB.mtimeMs)) {
          modified.push(file);
        }
      }
    }

    return { added, removed, modified };
  }

  async restoreCheckpoint({ name }) {
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
    const backup = await this.createCheckpoint({ 
      description: 'Auto-backup before restore', 
      name: 'rewind_backup', 
      force: true 
    });
    const backupName = backup.success ? backup.name : null;

    await this.applyRestore(target);
    await this.updateHeadSignature();

    await this.logChangelog({
      action: 'RESTORE_CHECKPOINT',
      description: `Restored checkpoint: ${target.name}`,
      details: backupName ? `Emergency backup: ${backupName}` : 'Emergency backup unavailable'
    });

    return { 
      success: true, 
      restored: target.name, 
      emergencyBackup: backupName 
    };
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

    // Delete files that exist now but not in snapshot
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
    const config = await this.getConfig();
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

      await atomicWrite(this.changelogFile, JSON.stringify(entries, null, 2), 'utf8');
    } catch {
      // Changelog failures should not break main flow
    }
  }

  async getLatestCheckpoint() {
    const checkpoints = await this.listCheckpoints();
    return checkpoints.length ? checkpoints[0] : null;
  }
}
