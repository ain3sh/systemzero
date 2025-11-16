#!/usr/bin/env node

/**
 * SessionParser - Agent-agnostic JSONL session parser
 * 
 * Simplified from ccundo's ClaudeSessionParser - removes undo tracking,
 * focuses on reading sessions and finding message UUIDs.
 * 
 * Supports: Claude Code, Droid CLI
 */

import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { createReadStream } from 'fs';
import { createInterface } from 'readline';

export class SessionParser {
  constructor(agent = 'auto') {
    this.agent = agent;
    
    if (agent === 'auto') {
      this.agent = this.detectAgent();
    }
    
    // Set storage directory based on agent
    switch (this.agent) {
      case 'claude-code':
        this.storageDir = path.join(os.homedir(), '.claude', 'projects');
        break;
      case 'droid-cli':
        this.storageDir = path.join(os.homedir(), '.factory', 'sessions');
        break;
      default:
        throw new Error(`Unknown agent: ${this.agent}`);
    }
  }
  
  detectAgent() {
    const claudeDir = path.join(os.homedir(), '.claude', 'projects');
    const droidDir = path.join(os.homedir(), '.factory', 'sessions');
    
    // Check which directory exists
    try {
      if (fs.existsSync(claudeDir)) return 'claude-code';
      if (fs.existsSync(droidDir)) return 'droid-cli';
    } catch (e) {
      // Fall through
    }
    
    return 'claude-code'; // Default
  }
  
  async getCurrentProjectDir() {
    if (this.agent === 'droid-cli') {
      // Droid stores sessions flat in ~/.factory/sessions/
      return this.storageDir;
    }
    
    // Claude Code stores in project-specific directories
    const cwd = process.cwd();
    let safePath;
    
    // Claude uses different formats for different operating systems
    if (process.platform === 'win32') {
      // Windows: C:\Users\... → C--Users-...
      safePath = cwd.replace(/:[\\\/]/g, '--')
                     .replace(/[\\/]/g, '-')
                     .replace(/[\s_]/g, '-');
    } else {
      // Linux/macOS: /home/... → -home-...
      safePath = cwd.replace(/[\s\/_]/g, '-');
    }
    
    return path.join(this.storageDir, safePath);
  }
  
  async getCurrentSessionFile() {
    const projectDir = await this.getCurrentProjectDir();
    
    try {
      const files = await fs.readdir(projectDir);
      const sessionFiles = files.filter(f => f.endsWith('.jsonl'));
      
      if (sessionFiles.length === 0) return null;
      
      // Get the most recently modified session file
      const stats = await Promise.all(
        sessionFiles.map(async f => ({
          file: f,
          path: path.join(projectDir, f),
          mtime: (await fs.stat(path.join(projectDir, f))).mtime
        }))
      );
      
      stats.sort((a, b) => b.mtime - a.mtime);
      return stats[0].path;
    } catch (error) {
      if (error.code === 'ENOENT') return null;
      throw error;
    }
  }
  
  async parseSessionFile(sessionFile) {
    const messages = [];
    const fileStream = createReadStream(sessionFile);
    const rl = createInterface({
      input: fileStream,
      crlfDelay: Infinity
    });

    for await (const line of rl) {
      try {
        const entry = JSON.parse(line);
        
        // Store all messages (user and assistant)
        if (entry.type && entry.uuid && entry.timestamp) {
          messages.push({
            uuid: entry.uuid,
            type: entry.type,
            timestamp: entry.timestamp,
            content: this.extractContent(entry),
            sessionId: entry.sessionId || entry.session_id,
            parentUuid: entry.parentUuid || entry.parent_uuid
          });
        }
      } catch (e) {
        // Skip invalid JSON lines
      }
    }

    return messages;
  }
  
  extractContent(entry) {
    if (!entry.message) return '';
    
    if (typeof entry.message === 'string') {
      return entry.message;
    }
    
    if (entry.message.content) {
      if (typeof entry.message.content === 'string') {
        return entry.message.content;
      }
      
      // For array content (tool use, etc.), extract text parts
      if (Array.isArray(entry.message.content)) {
        return entry.message.content
          .filter(c => c.type === 'text')
          .map(c => c.text)
          .join('\n');
      }
    }
    
    return '';
  }
  
  /**
   * Find the message UUID closest to a given timestamp
   * Useful for linking checkpoints to conversation turns
   */
  findMessageByTimestamp(messages, targetTimestamp) {
    if (messages.length === 0) return null;
    
    const target = new Date(targetTimestamp).getTime();
    
    // Find message with closest timestamp (before or equal to target)
    let closest = messages[0];
    let closestDiff = Math.abs(new Date(closest.timestamp).getTime() - target);
    
    for (const msg of messages) {
      const msgTime = new Date(msg.timestamp).getTime();
      const diff = Math.abs(msgTime - target);
      
      // Only consider messages before the target time
      if (msgTime <= target && diff < closestDiff) {
        closest = msg;
        closestDiff = diff;
      }
    }
    
    return closest;
  }
  
  /**
   * Get the latest user message (useful for checkpoint descriptions)
   */
  getLatestUserMessage(messages) {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].type === 'user') {
        return messages[i];
      }
    }
    return null;
  }
}

// CLI usage
if (import.meta.url === `file://${process.argv[1]}`) {
  const parser = new SessionParser();
  
  const command = process.argv[2];
  
  switch (command) {
    case 'current-session':
      const sessionFile = await parser.getCurrentSessionFile();
      console.log(sessionFile || 'No session found');
      break;
      
    case 'parse':
      const file = process.argv[3];
      if (!file) {
        console.error('Usage: SessionParser.js parse <session-file>');
        process.exit(1);
      }
      const messages = await parser.parseSessionFile(file);
      console.log(JSON.stringify(messages, null, 2));
      break;
      
    case 'latest-user':
      const sessionPath = await parser.getCurrentSessionFile();
      if (!sessionPath) {
        console.error('No session found');
        process.exit(1);
      }
      const msgs = await parser.parseSessionFile(sessionPath);
      const latest = parser.getLatestUserMessage(msgs);
      console.log(JSON.stringify(latest, null, 2));
      break;
      
    default:
      console.log('Usage: SessionParser.js {current-session|parse <file>|latest-user}');
      process.exit(1);
  }
}
