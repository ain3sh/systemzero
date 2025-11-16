#!/usr/bin/env node

/**
 * ConversationTruncator - Safely truncate JSONL conversation files
 * 
 * Truncates conversation to specific message UUID, creating backups.
 * Used for conversation rewind functionality.
 * 
 * Safety features:
 * - Creates timestamped backup before truncation
 * - Validates JSON on each line
 * - Atomic write (write to temp, then rename)
 * - Dry-run mode for testing
 */

import fs from 'fs/promises';
import { createReadStream } from 'fs';
import { createInterface } from 'readline';
import path from 'path';

export class ConversationTruncator {
  constructor(sessionFile, options = {}) {
    this.sessionFile = path.resolve(sessionFile);
    this.dryRun = options.dryRun || false;
    this.verbose = options.verbose || false;
  }
  
  /**
   * Truncate conversation at specific message UUID
   * 
   * @param {string} messageUuid - Target message UUID
   * @returns {Object} - { success, linesKept, linesRemoved, backupFile }
   */
  async truncateAt(messageUuid) {
    // 1. Validate session file exists
    if (!await this.fileExists(this.sessionFile)) {
      throw new Error(`Session file not found: ${this.sessionFile}`);
    }
    
    // 2. Create backup
    const backupFile = await this.createBackup();
    this.log(`Created backup: ${backupFile}`);
    
    // 3. Read and truncate
    const { lines, targetFound } = await this.readUntilUuid(messageUuid);
    
    if (!targetFound) {
      throw new Error(`Message UUID not found: ${messageUuid}`);
    }
    
    // 4. Write truncated file (atomic)
    if (!this.dryRun) {
      await this.atomicWrite(lines);
      this.log(`Wrote ${lines.length} lines to ${this.sessionFile}`);
    } else {
      this.log(`[DRY RUN] Would write ${lines.length} lines`);
    }
    
    // 5. Return stats
    const originalLineCount = this.dryRun 
      ? await this.countLines(this.sessionFile)  // In dry-run, count original file
      : await this.countLines(backupFile);       // Otherwise count backup
    return {
      success: true,
      linesKept: lines.length,
      linesRemoved: originalLineCount - lines.length,
      backupFile,
      messageUuid
    };
  }
  
  /**
   * Read JSONL until we find the target UUID
   */
  async readUntilUuid(targetUuid) {
    const lines = [];
    let targetFound = false;
    
    const fileStream = createReadStream(this.sessionFile);
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
      } catch (e) {
        this.log(`WARNING: Skipping invalid JSON line: ${line.substring(0, 50)}...`);
        continue;
      }
      
      // Keep line
      lines.push(line);
      
      // Check if this is our target
      if (data.uuid === targetUuid) {
        targetFound = true;
        this.log(`Found target UUID at line ${lines.length}`);
        break;
      }
    }
    
    return { lines, targetFound };
  }
  
  /**
   * Create timestamped backup
   */
  async createBackup() {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const backupFile = `${this.sessionFile}.backup.${timestamp}`;
    
    if (!this.dryRun) {
      await fs.copyFile(this.sessionFile, backupFile);
    } else {
      this.log(`[DRY RUN] Would create backup: ${backupFile}`);
    }
    
    return backupFile;
  }
  
  /**
   * Atomic write - write to temp file, then rename
   */
  async atomicWrite(lines) {
    const tempFile = `${this.sessionFile}.tmp`;
    
    // Write to temp file
    const content = lines.join('\n') + '\n';
    await fs.writeFile(tempFile, content, 'utf8');
    
    // Atomic rename
    await fs.rename(tempFile, this.sessionFile);
  }
  
  /**
   * Count lines in file
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
  
  async fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }
  
  log(message) {
    if (this.verbose) {
      console.log(`[ConversationTruncator] ${message}`);
    }
  }
}

// CLI interface
if (import.meta.url === `file://${process.argv[1]}`) {
  const [,, sessionFile, messageUuid, ...flags] = process.argv;
  
  if (!sessionFile || !messageUuid) {
    console.log('Usage: ConversationTruncator.js <session-file> <message-uuid> [--dry-run] [--verbose]');
    console.log('');
    console.log('Truncates JSONL conversation file at specified message UUID.');
    console.log('Creates automatic backup before truncation.');
    console.log('');
    console.log('Options:');
    console.log('  --dry-run   Show what would happen without making changes');
    console.log('  --verbose   Show detailed progress');
    console.log('');
    console.log('Examples:');
    console.log('  ConversationTruncator.js ~/.claude/projects/xyz/session.jsonl msg-456');
    console.log('  ConversationTruncator.js session.jsonl msg-123 --dry-run --verbose');
    process.exit(1);
  }
  
  const options = {
    dryRun: flags.includes('--dry-run'),
    verbose: flags.includes('--verbose') || flags.includes('--dry-run')
  };
  
  const truncator = new ConversationTruncator(sessionFile, options);
  
  try {
    const result = await truncator.truncateAt(messageUuid);
    console.log('');
    console.log('✅ Truncation complete!');
    console.log(`   Lines kept: ${result.linesKept}`);
    console.log(`   Lines removed: ${result.linesRemoved}`);
    console.log(`   Backup: ${result.backupFile}`);
    console.log('');
    
    if (options.dryRun) {
      console.log('(Dry run - no changes made)');
    }
  } catch (error) {
    console.error('❌ Error:', error.message);
    process.exit(1);
  }
}
