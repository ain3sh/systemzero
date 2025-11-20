import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { fileExists, safeJsonParse } from '../utils/fs-utils.js';

/**
 * ConfigLoader - Centralized configuration management
 * 
 * Loads configuration from multiple sources in order of precedence:
 * 1. Project-specific overrides (rewind-checkpoint-ignore.json)
 * 2. Tier configuration files
 * 3. Default configuration
 */

const DEFAULT_CONFIG = {
  maxCheckpoints: 10,
  maxAgeDays: 30,
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
  nameTemplate: 'checkpoint_{timestamp}',
  antiSpam: {
    enabled: true,
    minIntervalSeconds: 30
  },
  significance: {
    minChangeSize: 50,
    ignoreWhitespaceOnly: true
  }
};

const TIER_CONFIGS = {
  minimal: {
    antiSpam: { enabled: true, minIntervalSeconds: 60 },
    significance: { minChangeSize: 100 }
  },
  balanced: {
    antiSpam: { enabled: true, minIntervalSeconds: 30 },
    significance: { minChangeSize: 50 }
  },
  aggressive: {
    antiSpam: { enabled: false, minIntervalSeconds: 0 },
    significance: { minChangeSize: 10 }
  }
};

export class ConfigLoader {
  constructor(projectRoot = process.cwd()) {
    this.projectRoot = path.resolve(projectRoot);
    this.tier = process.env.CHECKPOINT_TIER || 'balanced';
    this._configCache = null;
  }

  /**
   * Get the complete merged configuration
   */
  async getConfig() {
    if (this._configCache) {
      return this._configCache;
    }

    const config = { ...DEFAULT_CONFIG };
    
    // Apply tier-specific settings
    const tierConfig = TIER_CONFIGS[this.tier];
    if (tierConfig) {
      Object.assign(config, tierConfig);
    }

    // Load user-level global configuration (lowest priority overrides)
    const userConfig = await this.loadUserConfig();
    if (userConfig) {
      this.mergeConfig(config, userConfig);
    }

    // Load project overrides (highest priority)
    const projectOverrides = await this.loadProjectOverrides();
    if (projectOverrides) {
      this.mergeConfig(config, projectOverrides);
    }

    this._configCache = config;
    return config;
  }

  /**
   * Load user-level global configuration
   */
  async loadUserConfig() {
    const home = os.homedir();
    const candidates = [
      path.join(home, '.rewind', 'config.json'),
      path.join(home, '.config', 'rewind', 'config.json')
    ];

    for (const candidate of candidates) {
      if (await fileExists(candidate)) {
        try {
          const content = await fs.readFile(candidate, 'utf8');
          return safeJsonParse(content);
        } catch (error) {
          // Silently ignore user config errors or log debug
        }
      }
    }
    return null;
  }

  /**
   * Load project-specific override files
   */
  async loadProjectOverrides() {
    const candidates = [
      path.join(this.projectRoot, '.rewind', 'config.json'),
      path.join(this.projectRoot, 'rewind.json'), // Support cleaner root config
      path.join(this.projectRoot, 'rewind-checkpoint-ignore.json') // Legacy support
    ];

    for (const candidate of candidates) {
      if (await fileExists(candidate)) {
        try {
          const content = await fs.readFile(candidate, 'utf8');
          return safeJsonParse(content);
        } catch (error) {
          console.warn(`[ConfigLoader] Failed to load ${candidate}: ${error.message}`);
        }
      }
    }

    return null;
  }

  /**
   * Determine effective storage mode
   */
  async getStorageMode() {
    const config = await this.getConfig();
    
    // Explicit config wins
    if (config.storage?.mode) {
      return config.storage.mode;
    }
    
    // Fallback logic:
    // If we are in a "vendored" setup (rewind inside project), default to 'project'
    // Otherwise, default to what global config says, or 'project' as safe default
    return 'project';
  }

  /**
   * Merge configuration objects with array handling
   */
  mergeConfig(base, override) {
    for (const [key, value] of Object.entries(override)) {
      if (key === 'ignorePatterns' && Array.isArray(value)) {
        // Replace ignorePatterns completely if provided
        base.ignorePatterns = [...value];
      } else if (key === 'additionalIgnores' && Array.isArray(value)) {
        // Merge additionalIgnores
        base.additionalIgnores = this.mergeUnique(base.additionalIgnores, value);
      } else if (key === 'forceInclude' && Array.isArray(value)) {
        // Merge forceInclude
        base.forceInclude = this.mergeUnique(base.forceInclude, value);
      } else if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        // Recursively merge objects
        if (!base[key]) base[key] = {};
        this.mergeConfig(base[key], value);
      } else {
        // Direct assignment for primitives
        base[key] = value;
      }
    }
  }

  /**
   * Merge arrays removing duplicates
   */
  mergeUnique(base = [], additional = []) {
    const set = new Set([...base, ...additional]);
    return Array.from(set);
  }

  /**
   * Get .gitignore patterns
   */
  async getGitignorePatterns() {
    const gitignorePath = path.join(this.projectRoot, '.gitignore');
    
    if (!await fileExists(gitignorePath)) {
      return [];
    }

    try {
      const content = await fs.readFile(gitignorePath, 'utf8');
      return content
        .split(/\r?\n/)
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('#'));
    } catch {
      return [];
    }
  }

  /**
   * Clear config cache (useful for testing)
   */
  clearCache() {
    this._configCache = null;
  }

  /**
   * Get current tier
   */
  getTier() {
    return this.tier;
  }

  /**
   * Set tier (useful for testing)
   */
  setTier(tier) {
    if (!TIER_CONFIGS[tier]) {
      throw new Error(`Invalid tier: ${tier}. Must be one of: ${Object.keys(TIER_CONFIGS).join(', ')}`);
    }
    this.tier = tier;
    this.clearCache();
  }
}
