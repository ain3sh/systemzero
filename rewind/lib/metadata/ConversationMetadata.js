#!/usr/bin/env node

/**
 * ConversationMetadata - Store conversation context for checkpoints
 * 
 * Extends ClaudePoint checkpoints with conversation metadata so we can
 * later truncate conversations to match code checkpoints.
 * 
 * Storage: .claudepoint/conversation_metadata.json
 * 
 * Format:
 * {
 *   "checkpoint_name_2025-11-16T12-00-00": {
 *     "agent": "claude-code",
 *     "sessionId": "abc-123",
 *     "sessionFile": "/home/user/.claude/projects/xyz/abc-123.jsonl",
 *     "messageUuid": "msg-456",
 *     "messageIndex": 42,
 *     "userPrompt": "Create a new feature",
 *     "timestamp": "2025-11-16T12:00:00Z"
 *   }
 * }
 */

import fs from 'fs/promises';
import path from 'path';

export class ConversationMetadata {
  constructor(projectRoot = process.cwd()) {
    this.projectRoot = path.resolve(projectRoot);
    this.claudepointDir = path.join(this.projectRoot, '.claudepoint');
    this.metadataFile = path.join(this.claudepointDir, 'conversation_metadata.json');
  }
  
  /**
   * Load existing metadata or return empty object
   */
  async load() {
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
   * Save metadata to file
   */
  async save(metadata) {
    // Ensure directory exists
    await fs.mkdir(this.claudepointDir, { recursive: true });
    
    // Write with pretty formatting for human readability
    await fs.writeFile(
      this.metadataFile,
      JSON.stringify(metadata, null, 2),
      'utf8'
    );
  }
  
  /**
   * Add conversation metadata for a checkpoint
   */
  async add(checkpointName, conversationData) {
    const metadata = await this.load();
    
    metadata[checkpointName] = {
      agent: conversationData.agent || 'unknown',
      sessionId: conversationData.sessionId || null,
      sessionFile: conversationData.sessionFile || null,
      messageUuid: conversationData.messageUuid || null,
      messageIndex: conversationData.messageIndex || null,
      userPrompt: conversationData.userPrompt || null,
      timestamp: conversationData.timestamp || new Date().toISOString()
    };
    
    await this.save(metadata);
    return metadata[checkpointName];
  }
  
  /**
   * Get conversation metadata for a checkpoint
   */
  async get(checkpointName) {
    const metadata = await this.load();
    return metadata[checkpointName] || null;
  }
  
  /**
   * List all checkpoints with conversation metadata
   */
  async list() {
    return await this.load();
  }
  
  /**
   * Remove metadata for a checkpoint (when checkpoint is deleted)
   */
  async remove(checkpointName) {
    const metadata = await this.load();
    
    if (metadata[checkpointName]) {
      delete metadata[checkpointName];
      await this.save(metadata);
      return true;
    }
    
    return false;
  }
  
  /**
   * Clean up metadata for checkpoints that no longer exist
   */
  async cleanup() {
    const metadata = await this.load();
    const snapshotsDir = path.join(this.claudepointDir, 'snapshots');
    
    try {
      const checkpoints = await fs.readdir(snapshotsDir);
      const checkpointNames = new Set(checkpoints);
      
      let cleaned = 0;
      for (const name of Object.keys(metadata)) {
        if (!checkpointNames.has(name)) {
          delete metadata[name];
          cleaned++;
        }
      }
      
      if (cleaned > 0) {
        await this.save(metadata);
      }
      
      return cleaned;
    } catch (error) {
      if (error.code === 'ENOENT') {
        // Snapshots directory doesn't exist, clear all metadata
        await this.save({});
        return Object.keys(metadata).length;
      }
      throw error;
    }
  }
}

// CLI usage
if (import.meta.url === `file://${process.argv[1]}`) {
  const metadata = new ConversationMetadata();
  
  const command = process.argv[2];
  
  switch (command) {
    case 'add':
      const checkpointName = process.argv[3];
      const data = JSON.parse(process.argv[4] || '{}');
      const result = await metadata.add(checkpointName, data);
      console.log('Added:', JSON.stringify(result, null, 2));
      break;
      
    case 'get':
      const name = process.argv[3];
      const meta = await metadata.get(name);
      console.log(meta ? JSON.stringify(meta, null, 2) : 'Not found');
      break;
      
    case 'list':
      const all = await metadata.list();
      console.log(JSON.stringify(all, null, 2));
      break;
      
    case 'remove':
      const cpName = process.argv[3];
      const removed = await metadata.remove(cpName);
      console.log(removed ? 'Removed' : 'Not found');
      break;
      
    case 'cleanup':
      const count = await metadata.cleanup();
      console.log(`Cleaned up ${count} orphaned metadata entries`);
      break;
      
    default:
      console.log('Usage: ConversationMetadata.js {add|get|list|remove|cleanup} [args]');
      console.log('');
      console.log('Examples:');
      console.log('  add <name> \'{"sessionId":"xyz","messageUuid":"msg-123"}\'');
      console.log('  get <name>');
      console.log('  list');
      console.log('  remove <name>');
      console.log('  cleanup');
      process.exit(1);
  }
}
