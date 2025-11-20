#!/usr/bin/env node

/**
 * Rewind CLI - System Zero Implementation
 * 
 * Enhanced CLI with interactive mode, conversation context support,
 * and atomic restore operations (code + context together).
 */

import path from 'path';
import readline from 'readline';
import { fileURLToPath } from 'url';
import process from 'process';
import { RewindController } from '../lib/core/RewindController.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import fs from 'fs/promises';
import os from 'os';

// Helper for relative time
function getRelativeTime(dateStr) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString();
}

// Helper to set configuration
async function setConfig(projectRoot, key, value) {
  const configPath = path.join(projectRoot, '.rewind', 'config.json');
  await fs.mkdir(path.dirname(configPath), { recursive: true });
  
  let config = {};
  try {
    const content = await fs.readFile(configPath, 'utf8');
    config = JSON.parse(content);
  } catch {
    // New config
  }

  // Support nested keys like "storage.mode"
  const parts = key.split('.');
  let current = config;
  for (let i = 0; i < parts.length - 1; i++) {
    current[parts[i]] = current[parts[i]] || {};
    current = current[parts[i]];
  }
  current[parts[parts.length - 1]] = value;

  await fs.writeFile(configPath, JSON.stringify(config, null, 2), 'utf8');
  return configPath;
}

class RewindCLI {
  constructor() {
    this.projectRoot = process.cwd();
    this.controller = new RewindController({ projectRoot: this.projectRoot });
  }

  /**
   * Parse command line arguments
   */
  parseArgs() {
    const args = process.argv.slice(2);
    const cmd = args[0];
    const options = {};
    const positional = [];

    for (let i = 1; i < args.length; i++) {
      const arg = args[i];
      if (arg.startsWith('--')) {
        if (arg.includes('=')) {
          const [key, value] = arg.slice(2).split('=', 2);
          options[key] = value;
        } else {
          const key = arg.slice(2);
          if (args[i + 1] && !args[i + 1].startsWith('--')) {
            options[key] = args[i + 1];
            i++;
          } else {
            options[key] = true;
          }
        }
      } else {
        positional.push(arg);
      }
    }

    return { cmd, options, positional };
  }

  /**
   * Interactive checkpoint selection
   */
  async selectCheckpoint(checkpoints) {
    if (checkpoints.length === 0) {
      console.log('No checkpoints available');
      return null;
    }

    console.log('\n📸 Available Checkpoints:\n');
    
    checkpoints.forEach((cp, idx) => {
      const date = new Date(cp.timestamp).toLocaleString();
      const context = cp.context?.userPrompt ? 
        `"${cp.context.userPrompt.slice(0, 50)}${cp.context.userPrompt.length > 50 ? '...' : ''}"` : 
        'No context';
      const contextIcon = cp.hasContext ? '💬' : '📄';
      
      console.log([
        `${String(idx + 1).padStart(2)}.`,
        contextIcon,
        cp.name,
        `[${date}]`,
        `${cp.fileCount} files,`,
        `${Math.round((cp.totalSize || 0) / 1024)}KB`
      ].join(' '));
      
      if (cp.context?.userPrompt) {
        console.log(`    ${context}`);
      }
      console.log();
    });

    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout
    });

    return new Promise((resolve) => {
      rl.question('Select checkpoint (number or name): ', (answer) => {
        rl.close();
        
        // Try to parse as number first
        const num = parseInt(answer, 10);
        if (!isNaN(num) && num >= 1 && num <= checkpoints.length) {
          resolve(checkpoints[num - 1]);
          return;
        }
        
        // Try to find by name
        const selected = checkpoints.find(cp => 
          cp.name === answer || cp.name.includes(answer)
        );
        
        resolve(selected || null);
      });
    });
  }

  /**
   * Format restore result for display
   */
  formatRestoreResult(result) {
    const lines = [];
    
    if (result.success) {
      lines.push(`✅ Restoration completed`);
      lines.push(`   Checkpoint: ${result.checkpointName}`);
      lines.push(`   Mode: ${result.mode}`);
      
      if (result.codeRestored) {
        lines.push('   ✅ Code restored');
      }
      
      if (result.contextRestored) {
        lines.push('   ✅ Context restored');
      }
      
      if (result.safetyBackup) {
        lines.push(`   🛡️  Safety backup: ${result.safetyBackup}`);
      }
      
      if (result.warning) {
        lines.push(`   ⚠️  ${result.warning}`);
      }
      
      if (result.contextDetails?.actionRequired) {
        lines.push('');
        lines.push(result.contextDetails.actionRequired);
      }
    } else {
      lines.push(`❌ Restoration failed: ${result.error}`);
      if (result.rolledBack) {
        lines.push('   🔄 Rolled back to safety point');
      }
    }
    
    return lines.join('\n');
  }

  /**
   * Main command dispatcher
   */
  async run() {
    const { cmd, options, positional } = this.parseArgs();

    try {
      // Initialize controller (loads config and sets up paths)
      await this.controller.init();

      switch (cmd) {
        case 'config': {
          const scope = options.global ? 'global' : 'local';
          const [key, value] = positional;
          
          // Determine target directory
          const targetRoot = options.global ? os.homedir() : this.projectRoot;
          
          if (!key) {
            // TODO: List config (not implemented yet)
            console.log('Usage: rewind config <key> <value> [--global]');
            break;
          }
          
          if (value === undefined) {
            console.log(`Error: Value required for ${key}`);
            break;
          }
          
          const configPath = await setConfig(targetRoot, key, value);
          console.log(`✅ Updated ${scope} config at ${configPath}`);
          console.log(`   ${key} = ${value}`);
          break;
        }

        case 'init': {
          const mode = options.mode || 'project';
          
          if (!['project', 'global'].includes(mode)) {
            console.error('Error: mode must be "project" or "global"');
            process.exit(1);
          }
          
          console.log(`Initializing rewind in ${mode} mode...`);
          
          const configPath = await setConfig(this.projectRoot, 'storage.mode', mode);
          console.log(`✅ Initialized ${mode} storage config at ${configPath}`);
          
          if (mode === 'global') {
            console.log('👉 Checkpoints will be stored in ~/.rewind/storage/');
          } else {
            console.log('👉 Checkpoints will be stored in .rewind/code/');
          }
          break;
        }

        case 'save':
        case 'create': {
          const name = options.name;
          const description = positional.join(' ') || options.description || '';
          const force = options.force || false;
          
          console.log('Creating checkpoint...');
          const result = await this.controller.createCheckpoint({
            name,
            description,
            force
          });

          if (!result.success) {
            if (result.noChanges) {
              console.log('⏭️  No changes detected - checkpoint skipped');
            } else {
              console.error(`❌ ${result.error || 'Failed to create checkpoint'}`);
              process.exit(1);
            }
          } else {
            const contextIcon = result.metadataStored ? '💬' : '📄';
            console.log(`✅ ${contextIcon} Created: ${result.name} (${result.fileCount} files)`);
            if (result.description) {
              console.log(`   Description: ${result.description}`);
            }
          }
          break;
        }

        case 'list':
        case 'ls': {
          const checkpoints = await this.controller.listCheckpoints();
          if (checkpoints.length === 0) {
            console.log('No checkpoints found');
            break;
          }

          console.log(`\n📸 ${checkpoints.length} Checkpoints:\n`);
          checkpoints.forEach((cp, idx) => {
            const timeStr = getRelativeTime(cp.timestamp);
            const contextIcon = cp.hasContext ? '💬' : '📄';
            
            console.log([
              `${String(idx + 1).padStart(2)}.`,
              contextIcon,
              cp.name,
              `[${timeStr}]`,
              `${cp.fileCount} files,`,
              `${Math.round((cp.totalSize || 0) / 1024)}KB`
            ].join(' '));
            
            if (cp.context?.userPrompt) {
              const prompt = cp.context.userPrompt.slice(0, 80);
              console.log(`    "${prompt}${cp.context.userPrompt.length > 80 ? '...' : ''}"`);
            }
            console.log();
          });
          break;
        }

        case 'restore': {
          let target = positional[0];
          const mode = options.mode || 'both';
          const dryRun = options['dry-run'] || false;
          const skipBackup = options['skip-backup'] || false;
          const interactive = options.interactive || !target;

          if (!['both', 'code', 'context'].includes(mode)) {
            console.error('Invalid mode. Use: both, code, or context');
            process.exit(1);
          }

          const checkpoints = await this.controller.listCheckpoints();
          
          if (interactive) {
            const selected = await this.selectCheckpoint(checkpoints);
            if (!selected) {
              console.log('No checkpoint selected');
              process.exit(0);
            }
            target = selected.name;
          }

          if (!target) {
            console.error('Usage: rewind restore <checkpoint-name> [--mode both|code|context]');
            process.exit(1);
          }

          console.log(`${dryRun ? '[DRY RUN] ' : ''}Restoring ${target} (${mode} mode)...`);
          
          const result = await this.controller.restore(target, mode, {
            dryRun,
            skipBackup
          });

          console.log('\n' + this.formatRestoreResult(result));
          
          if (!result.success) {
            process.exit(1);
          }
          break;
        }

        case 'undo': {
          const mode = options.mode || 'both';
          
          console.log(`Undoing last checkpoint (${mode} mode)...`);
          const result = await this.controller.undoLastCheckpoint(mode);
          
          console.log('\n' + this.formatRestoreResult(result));
          
          if (!result.success) {
            process.exit(1);
          }
          break;
        }

        case 'status': {
          const status = await this.controller.getStatus();
          const isGlobal = status.storageMode === 'global';
          const storageIcon = isGlobal ? '🌍' : '📁';
          
          console.log(`\n🔧 System Status:\n`);
          console.log(`Project: ${status.projectRoot}`);
          console.log(`Storage: ${storageIcon} ${status.storageMode.toUpperCase()} (${status.storagePath})`);
          console.log(`Agent: ${status.agent}`);
          console.log(`Tier: ${status.tier}`);
          console.log(`Checkpoints: ${status.checkpointCount} (${status.checkpointsWithContext} with context)`);
          console.log(`Max checkpoints: ${status.config.maxCheckpoints}`);
          console.log(`Max age: ${status.config.maxAgeDays} days`);
          console.log(`Anti-spam: ${status.config.antiSpam.enabled ? 'enabled' : 'disabled'}`);
          if (status.config.antiSpam.enabled) {
            console.log(`Anti-spam interval: ${status.config.antiSpam.minIntervalSeconds}s`);
          }
          break;
        }

        case 'validate': {
          const validation = await this.controller.validateSystem();
          
          console.log(`\n🔍 System Validation:\n`);
          console.log(`Status: ${validation.valid ? '✅ Valid' : '❌ Issues found'}`);
          console.log(`Agent: ${validation.stats.agent}`);
          console.log(`Checkpoints: ${validation.stats.checkpointCount}`);
          console.log(`Metadata entries: ${validation.stats.metadataCount}`);
          
          if (validation.issues.length > 0) {
            console.log('\nIssues:');
            validation.issues.forEach(issue => console.log(`  ❌ ${issue}`));
          }
          
          if (validation.stats.orphanedMetadata > 0) {
            console.log(`\nRun 'rewind cleanup' to remove ${validation.stats.orphanedMetadata} orphaned metadata entries`);
          }
          break;
        }

        case 'cleanup': {
          const result = await this.controller.cleanupMetadata();
          if (result.success) {
            console.log(`✅ Cleaned up ${result.cleanedCount} orphaned metadata entries`);
          } else {
            console.error(`❌ Cleanup failed: ${result.error}`);
            process.exit(1);
          }
          break;
        }

        case 'help':
        case '--help':
        case '-h':
        default: {
          console.log('Rewind - System Zero Implementation');
          console.log('');
          console.log('Usage: rewind <command> [options]');
          console.log('');
          console.log('Commands:');
          console.log('  init [--mode project|global]                    Initialize project config');
          console.log('  config <key> <value> [--global]                 Set configuration value');
          console.log('  save [description] [--name <name>] [--force]    Create checkpoint');
          console.log('  list                                             List all checkpoints');
          console.log('  restore [name] [--mode both|code|context]       Restore checkpoint');
          console.log('      --interactive                                Interactive selection');
          console.log('      --dry-run                                   Preview changes only');
          console.log('      --skip-backup                               Skip safety backup');
          console.log('  undo [--mode both|code|context]                Undo last checkpoint');
          console.log('  status                                          Show system status');
          console.log('  validate                                        Validate system integrity');
          console.log('  cleanup                                         Clean orphaned metadata');
          console.log('');
          console.log('Restore Modes:');
          console.log('  both      - Restore code and conversation context (default)');
          console.log('  code      - Restore files only');
          console.log('  context   - Restore conversation history only');
          console.log('');
          console.log('Examples:');
          console.log('  rewind save "Added user authentication"');
          console.log('  rewind restore --interactive');
          console.log('  rewind restore checkpoint_abc123 --mode code');
          console.log('  rewind undo --dry-run');
          
          if (cmd && cmd !== 'help' && cmd !== '--help' && cmd !== '-h') {
            process.exit(1);
          }
          break;
        }
      }
    } catch (error) {
      console.error(`❌ Error: ${error.message}`);
      if (options.debug) {
        console.error(error.stack);
      }
      process.exit(1);
    }
  }
}

// CLI entry point
async function main() {
  const cli = new RewindCLI();
  await cli.run();
}

main();
