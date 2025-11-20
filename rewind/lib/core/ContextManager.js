import fs from 'fs/promises';
import { createReadStream } from 'fs';
import { createInterface } from 'readline';
import path from 'path';
import os from 'os';
import { atomicWrite, ensureDir, fileExists, safeStatFile } from '../utils/fs-utils.js';

/**
 * ContextManager - Unified conversation context management
 * 
 * Integrates ConversationMetadata and ConversationTruncator functionality
 * into a single cohesive service for managing agent conversation state.
 * 
 * Key responsibilities:
 * - Track conversation metadata linked to checkpoints
 * - Safely truncate JSONL conversation files
 * - Validate context consistency
 * - Support both Claude Code and Droid CLI
 */
export class ContextManager {
  constructor(projectRoot = process.cwd()) {
    this.projectRoot = path.resolve(projectRoot);
    this.initialized = false;
  }

  /**
   * Initialize storage paths based on configuration
   */
  async initialize(config = {}) {
    if (this.initialized) return;

    const storageMode = config.storage?.mode || 'project'; // 'project' or 'global'
    
    if (storageMode === 'global') {
      // User-level storage: ~/.rewind/storage/<sanitized_project_path>/conversation
      const home = os.homedir();
      const globalRoot = config.storage?.path || path.join(home, '.rewind', 'storage');
      // Import crypto dynamically if needed, or assume it's available in node
      // We'll replicate the hashing logic from CheckpointStore to be consistent
      const { createHash } = await import('crypto');
      const projectHash = createHash('sha256').update(this.projectRoot).digest('hex').slice(0, 12);
      const projectName = path.basename(this.projectRoot).replace(/[^a-zA-Z0-9_-]/g, '_');
      
      this.baseDir = path.join(globalRoot, `${projectName}_${projectHash}`, 'conversation');
    } else {
      // Project-level storage: <project>/.rewind/conversation
      this.baseDir = path.join(this.projectRoot, '.rewind', 'conversation');
    }

    this.metadataFile = path.join(this.baseDir, 'metadata.json');
    
    // Ensure base directory exists
    await ensureDir(this.baseDir);
    this.initialized = true;
  }

  async ensureDirs() {
    if (!this.initialized) {
      // Fallback default initialization if called directly without config
      await this.initialize(); 
    }
    await ensureDir(this.baseDir);
  }

  /**
   * Detect which agent is currently running
   */
  detectAgent() {
    // Check environment variables first
    if (process.env.CLAUDE_PROJECT_DIR) return 'claude-code';
    if (process.env.FACTORY_PROJECT_DIR) return 'droid-cli';

    // Check which directories exist
    const claudeDir = path.join(os.homedir(), '.claude', 'projects');
    const droidDir = path.join(os.homedir(), '.factory', 'sessions');
    
    try {
      if (fs.existsSync(claudeDir)) return 'claude-code';
      if (fs.existsSync(droidDir)) return 'droid-cli';
    } catch {
      // Fall through
    }
    
    return 'unknown';
  }

  /**
   * Get storage directory for current agent
   */
  getStorageDir(agent = null) {
    const detectedAgent = agent || this.detectAgent();
    
    switch (detectedAgent) {
      case 'claude-code':
        return path.join(os.homedir(), '.claude', 'projects');
      case 'droid-cli':
        return path.join(os.homedir(), '.factory', 'sessions');
      default:
        throw new Error(`Unknown agent: ${detectedAgent}`);
    }
  }

  /**
   * Find current session file for the agent
   */
  async getCurrentSessionFile(agent = null) {
    const detectedAgent = agent || this.detectAgent();
    const storageDir = this.getStorageDir(detectedAgent);
    
    if (!await fileExists(storageDir)) {
      return null;
    }

    try {
      // Find the most recent .jsonl file
      const entries = await fs.readdir(storageDir, { withFileTypes: true });
      const jsonlFiles = entries
        .filter(entry => entry.isFile() && entry.name.endsWith('.jsonl'))
        .map(entry => ({
          name: entry.name,
          path: path.join(storageDir, entry.name)
        }));

      if (jsonlFiles.length === 0) {
        return null;
      }

      // Sort by modification time, most recent first
      const filesWithStats = await Promise.all(
        jsonlFiles.map(async (file) => {
          const stat = await safeStatFile(file.path);
          return {
            ...file,
            mtime: stat ? stat.mtime : new Date(0)
          };
        })
      );

      filesWithStats.sort((a, b) => b.mtime - a.mtime);
      return filesWithStats[0].path;
    } catch (error) {
      return null;
    }
  }

  /**
   * Parse JSONL session file into messages
   */
  async parseSessionFile(sessionFile) {
    if (!await fileExists(sessionFile)) {
      return [];
    }

    const messages = [];
    const fileStream = createReadStream(sessionFile);
    const rl = createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });

    for await (const line of rl) {
      if (!line.trim()) continue;
      
      try {
        const data = JSON.parse(line);
        messages.push({
          uuid: data.uuid,
          type: data.type,
          content: data.content || data.text || '',
          timestamp: data.timestamp || data.created_at,
          sessionId: data.session_id || this.extractSessionId(sessionFile)
        });
      } catch {
        // Skip invalid JSON lines
      }
    }

    return messages;
  }

  /**
   * Extract session ID from file path
   */
  extractSessionId(sessionFile) {
    const basename = path.basename(sessionFile, '.jsonl');
    return basename;
  }

  /**
   * Get the latest user message from parsed messages
   */
  getLatestUserMessage(messages) {
    // Find the most recent user message
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      if (msg.type === 'human' || msg.type === 'user') {
        return msg;
      }
    }
    return null;
  }

  /**
   * Gather conversation context for a checkpoint
   */
  async gatherContext(payload = {}) {
    const agent = payload.agent_name || this.detectAgent();
    
    try {
      const sessionFile = await this.getCurrentSessionFile(agent);
      if (!sessionFile) return null;

      const messages = await this.parseSessionFile(sessionFile);
      if (!messages.length) return null;

      const latest = this.getLatestUserMessage(messages);
      if (!latest) return null;

      const messageIndex = messages.findIndex(msg => msg.uuid === latest.uuid);

      return {
        agent,
        sessionId: latest.sessionId || payload.session_id || null,
        sessionFile,
        messageUuid: latest.uuid,
        messageIndex,
        userPrompt: latest.content,
        timestamp: latest.timestamp || new Date().toISOString()
      };
    } catch (error) {
      return null;
    }
  }

  /**
   * Load conversation metadata
   */
  async loadMetadata() {
    if (!this.initialized) await this.initialize();
    try {
      const data = await fs.readFile(this.metadataFile, 'utf8');
      return JSON.parse(data);
    } catch (error) {
      if (error.code === 'ENOENT') {
        return {}; // File doesn't exist yet
      }
      throw error;
    }
  }

  /**
   * Save conversation metadata
   */
  async saveMetadata(metadata) {
    await this.ensureDirs(); // Calls initialize() if needed
    await atomicWrite(
      this.metadataFile,
      JSON.stringify(metadata, null, 2),
      'utf8'
    );
  }

  /**
   * Add conversation metadata for a checkpoint
   */
  async addCheckpointMetadata(checkpointName, contextData) {
    const metadata = await this.loadMetadata();
    
    metadata[checkpointName] = {
      agent: contextData.agent || 'unknown',
      sessionId: contextData.sessionId || null,
      sessionFile: contextData.sessionFile || null,
      messageUuid: contextData.messageUuid || null,
      messageIndex: contextData.messageIndex || null,
      userPrompt: contextData.userPrompt || null,
      timestamp: contextData.timestamp || new Date().toISOString()
    };
    
    await this.saveMetadata(metadata);
    return metadata[checkpointName];
  }

  /**
   * Get conversation metadata for a checkpoint
   */
  async getCheckpointMetadata(checkpointName) {
    const metadata = await this.loadMetadata();
    return metadata[checkpointName] || null;
  }

  /**
   * List all checkpoint metadata
   */
  async listMetadata() {
    return await this.loadMetadata();
  }

  /**
   * Remove metadata for a checkpoint
   */
  async removeCheckpointMetadata(checkpointName) {
    const metadata = await this.loadMetadata();
    
    if (metadata[checkpointName]) {
      delete metadata[checkpointName];
      await this.saveMetadata(metadata);
      return true;
    }
    
    return false;
  }

  /**
   * Truncate conversation at specific message UUID
   */
  async truncateConversation(sessionFile, messageUuid, options = {}) {
    const { dryRun = false, verbose = false } = options;
    
    // Validate session file exists
    if (!await fileExists(sessionFile)) {
      throw new Error(`Session file not found: ${sessionFile}`);
    }
    
    // Create backup
    const backupFile = await this.createBackup(sessionFile, dryRun);
    if (verbose) console.log(`Created backup: ${backupFile}`);
    
    // Read and truncate
    const { lines, targetFound } = await this.readUntilUuid(sessionFile, messageUuid);
    
    if (!targetFound) {
      throw new Error(`Message UUID not found: ${messageUuid}`);
    }
    
    // Write truncated file (atomic)
    if (!dryRun) {
      await this.atomicWriteLines(sessionFile, lines);
      if (verbose) console.log(`Wrote ${lines.length} lines to ${sessionFile}`);
    } else if (verbose) {
      console.log(`[DRY RUN] Would write ${lines.length} lines`);
    }
    
    // Return stats
    const originalLineCount = dryRun 
      ? await this.countLines(sessionFile)
      : await this.countLines(backupFile);
      
    return {
      success: true,
      linesKept: lines.length,
      linesRemoved: originalLineCount - lines.length,
      backupFile,
      messageUuid
    };
  }

  /**
   * Read JSONL until target UUID is found
   */
  async readUntilUuid(sessionFile, targetUuid) {
    const lines = [];
    let targetFound = false;
    
    const fileStream = createReadStream(sessionFile);
    const rl = createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });
    
    for await (const line of rl) {
      // Skip empty lines
      if (!line.trim()) continue;
      
      // Parse JSON
      let data;
      try {
        data = JSON.parse(line);
      } catch {
        // Keep malformed lines as-is but warn
        lines.push(line);
        continue;
      }
      
      // Keep line
      lines.push(line);
      
      // Check if this is our target
      if (data.uuid === targetUuid) {
        targetFound = true;
        break;
      }
    }
    
    return { lines, targetFound };
  }

  /**
   * Create timestamped backup of session file
   */
  async createBackup(sessionFile, dryRun = false) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupFile = `${sessionFile}.backup.${timestamp}`;
    
    if (!dryRun) {
      await fs.copyFile(sessionFile, backupFile);
    }
    
    return backupFile;
  }

  /**
   * Atomic write for JSONL lines
   */
  async atomicWriteLines(sessionFile, lines) {
    const content = lines.join('\n') + '\n';
    await atomicWrite(sessionFile, content, 'utf8');
  }

  /**
   * Count lines in a file
   */
  async countLines(filePath) {
    let count = 0;
    const fileStream = createReadStream(filePath);
    const rl = createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });
    
    for await (const line of rl) {
      if (line.trim()) count++;
    }
    
    return count;
  }

  /**
   * Validate context consistency - check if running session matches expected state
   */
  async validateContext(sessionId) {
    const agent = this.detectAgent();
    const sessionFile = await this.getCurrentSessionFile(agent);
    
    if (!sessionFile) {
      return { valid: false, reason: 'No active session found' };
    }

    const currentSessionId = this.extractSessionId(sessionFile);
    if (currentSessionId !== sessionId) {
      return { 
        valid: false, 
        reason: `Session ID mismatch: expected ${sessionId}, found ${currentSessionId}` 
      };
    }

    return { valid: true };
  }

  /**
   * Clean up metadata for checkpoints that no longer exist
   */
  async cleanupOrphanedMetadata(validCheckpointNames) {
    const metadata = await this.loadMetadata();
    const checkpointNames = new Set(validCheckpointNames);
    
    let cleaned = 0;
    for (const name of Object.keys(metadata)) {
      if (!checkpointNames.has(name)) {
        delete metadata[name];
        cleaned++;
      }
    }
    
    if (cleaned > 0) {
      await this.saveMetadata(metadata);
    }
    
    return cleaned;
  }

  /**
   * Restore conversation context to a checkpoint
   * Returns action instructions for the user since we can't force agent reload
   */
  async restoreContext(checkpointName) {
    const contextData = await this.getCheckpointMetadata(checkpointName);
    if (!contextData) {
      return { 
        success: false, 
        error: `No conversation metadata found for checkpoint: ${checkpointName}` 
      };
    }

    const { sessionFile, messageUuid } = contextData;
    if (!sessionFile || !messageUuid) {
      return { 
        success: false, 
        error: 'Incomplete conversation metadata - missing session file or message UUID' 
      };
    }

    if (!await fileExists(sessionFile)) {
      return { 
        success: false, 
        error: `Session file not found: ${sessionFile}` 
      };
    }

    try {
      const result = await this.truncateConversation(sessionFile, messageUuid);
      
      return {
        success: true,
        sessionFile,
        messageUuid,
        linesRemoved: result.linesRemoved,
        backupFile: result.backupFile,
        actionRequired: '🔄 Context restored. Please restart your agent or run /clear to apply changes.'
      };
    } catch (error) {
      return {
        success: false,
        error: error.message
      };
    }
  }
}
