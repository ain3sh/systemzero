import { RewindController } from '../core/RewindController.js';

/**
 * HookHandler - Intelligent hook processing logic
 * 
 * Moves all the decision-making logic from smart-checkpoint.sh into Node.js
 * for better performance, testing, and maintainability.
 * 
 * Responsibilities:
 * - Determine if a checkpoint should be created based on context
 * - Implement anti-spam/debounce logic
 * - Handle different hook events appropriately
 * - Provide structured output for hook systems
 */
export class HookHandler {
  constructor({ projectRoot = process.cwd() } = {}) {
    this.projectRoot = projectRoot;
    this.controller = new RewindController({ projectRoot });
    this.stateDir = this.getStateDir();
  }

  /**
   * Get state directory based on detected agent
   */
  getStateDir() {
    const agent = this.controller.contextManager.detectAgent();
    const homeDir = require('os').homedir();
    
    switch (agent) {
      case 'claude-code':
        return `${homeDir}/.claude-checkpoints`;
      case 'droid-cli':
        return `${homeDir}/.factory-checkpoints`;
      default:
        return `${homeDir}/.rewind-checkpoints`;
    }
  }

  /**
   * Main entry point for hook processing
   */
  async processHook(hookData) {
    try {
      const action = hookData.hook_event_name || hookData.action || 'pre-tool-use';
      const sessionId = hookData.session_id || 'unknown';
      
      // Determine if we should create a checkpoint
      const shouldCreate = await this.shouldCreateCheckpoint(action, sessionId, hookData);
      
      if (!shouldCreate.create) {
        return {
          success: true,
          skipped: true,
          reason: shouldCreate.reason,
          noChanges: shouldCreate.noChanges || false
        };
      }

      // Create the checkpoint
      const description = this.buildDescription(action, hookData);
      const checkpointResult = await this.controller.createCheckpoint({
        description,
        force: shouldCreate.force || false,
        hookPayload: hookData
      });

      // Update anti-spam timestamp if successful
      if (checkpointResult.success && shouldCreate.updateTimer) {
        await this.updateLastCheckpointTime(sessionId);
      }

      return {
        success: checkpointResult.success,
        checkpointName: checkpointResult.name,
        metadataStored: checkpointResult.metadataStored,
        description: checkpointResult.description,
        fileCount: checkpointResult.fileCount,
        noChanges: checkpointResult.noChanges || false,
        error: checkpointResult.error
      };
    } catch (error) {
      return {
        success: false,
        error: error.message || 'Hook processing failed'
      };
    }
  }

  /**
   * Determine if a checkpoint should be created
   */
  async shouldCreateCheckpoint(action, sessionId, hookData) {
    const config = await this.controller.checkpointStore.getConfig();
    
    // Structural actions (session start/end) bypass some checks
    const isStructural = ['session-start', 'stop', 'subagent-start', 'subagent-stop'].includes(action);
    
    if (isStructural) {
      return {
        create: true,
        force: true,
        updateTimer: false,
        reason: `Structural action: ${action}`
      };
    }

    // Check anti-spam if enabled
    if (config.antiSpam?.enabled) {
      const timeSinceLastCheckpoint = await this.getTimeSinceLastCheckpoint(sessionId);
      const minInterval = config.antiSpam.minIntervalSeconds || 30;
      
      if (timeSinceLastCheckpoint < minInterval) {
        return {
          create: false,
          reason: `Anti-spam: Only ${timeSinceLastCheckpoint}s since last checkpoint (need ${minInterval}s)`
        };
      }
    }

    // Check for actual file changes using fast scan
    const hasChanges = await this.controller.checkpointStore.hasChanges();
    if (!hasChanges) {
      return {
        create: false,
        noChanges: true,
        reason: 'No file changes detected'
      };
    }

    // Check significance thresholds if configured
    if (config.significance) {
      const significance = await this.checkSignificance(hookData, config.significance);
      if (!significance.isSignificant) {
        return {
          create: false,
          reason: `Below significance threshold: ${significance.reason}`
        };
      }
    }

    return {
      create: true,
      updateTimer: true,
      reason: 'Checkpoint criteria met'
    };
  }

  /**
   * Check if changes meet significance thresholds
   */
  async checkSignificance(hookData, significanceConfig) {
    // This is a placeholder for more sophisticated significance detection
    // Could check things like:
    // - Number of files changed
    // - Size of changes
    // - Type of tool used
    // - Whitespace-only changes
    
    const minChangeSize = significanceConfig.minChangeSize || 50;
    const toolName = hookData.tool_name;
    
    // Some tools are always considered significant
    const significantTools = ['Write', 'Create', 'Edit', 'MultiEdit'];
    if (significantTools.includes(toolName)) {
      return {
        isSignificant: true,
        reason: `Significant tool: ${toolName}`
      };
    }
    
    // Bash commands need special handling
    if (toolName === 'Bash') {
      const command = hookData.tool_input?.command || '';
      const destructivePatterns = [
        /rm\s+/, /mv\s+/, /cp\s+/, /git\s+commit/, /git\s+push/, 
        /npm\s+install/, /pip\s+install/, /make/, /build/
      ];
      
      const isDestructive = destructivePatterns.some(pattern => pattern.test(command));
      if (isDestructive) {
        return {
          isSignificant: true,
          reason: `Potentially destructive command: ${command.slice(0, 50)}...`
        };
      }
    }
    
    // Default to significant - conservative approach
    return {
      isSignificant: true,
      reason: 'Default significance assumption'
    };
  }

  /**
   * Get time since last checkpoint for anti-spam
   */
  async getTimeSinceLastCheckpoint(sessionId) {
    try {
      const fs = await import('fs/promises');
      const path = await import('path');
      
      const lastCheckpointFile = path.join(this.stateDir, `${sessionId}.last`);
      const lastTime = parseInt(await fs.readFile(lastCheckpointFile, 'utf8'), 10);
      const currentTime = Math.floor(Date.now() / 1000);
      
      return currentTime - lastTime;
    } catch {
      // File doesn't exist or error reading - return large value to allow checkpoint
      return Number.MAX_SAFE_INTEGER;
    }
  }

  /**
   * Update last checkpoint timestamp for anti-spam
   */
  async updateLastCheckpointTime(sessionId) {
    try {
      const fs = await import('fs/promises');
      const path = await import('path');
      
      // Ensure state directory exists
      await fs.mkdir(this.stateDir, { recursive: true });
      
      const lastCheckpointFile = path.join(this.stateDir, `${sessionId}.last`);
      const currentTime = Math.floor(Date.now() / 1000);
      
      await fs.writeFile(lastCheckpointFile, String(currentTime), 'utf8');
    } catch (error) {
      // Non-fatal - just warn
      console.warn('[HookHandler] Failed to update checkpoint timestamp:', error.message);
    }
  }

  /**
   * Build descriptive checkpoint name based on hook context
   */
  buildDescription(action, hookData) {
    const toolName = hookData.tool_name || 'tool';
    
    switch (action) {
      case 'session-start':
        return 'Session start';
      case 'stop':
        return 'Session end';
      case 'post-bash':
        const command = hookData.tool_input?.command || 'command';
        const shortCommand = command.slice(0, 30);
        return `After: ${shortCommand}${command.length > 30 ? '...' : ''}`;
      case 'subagent-start':
        return `Subagent start: ${toolName}`;
      case 'subagent-stop':
        return `Subagent stop: ${toolName}`;
      case 'pre-tool-use':
      default:
        return `Before: ${toolName}`;
    }
  }

  /**
   * Process hook with structured output format
   * This is the main interface called by the hook entry point
   */
  static async processHookFromStdin(projectRoot = process.cwd()) {
    try {
      // Read hook input from stdin
      const stdinData = await readStdin();
      let hookData = {};
      
      if (stdinData.trim()) {
        try {
          hookData = JSON.parse(stdinData);
        } catch {
          // Invalid JSON - proceed with empty data
        }
      }

      const handler = new HookHandler({ projectRoot });
      const result = await handler.processHook(hookData);

      // Output result as JSON
      console.log(JSON.stringify(result, null, 2));
      
      // Exit with appropriate code
      process.exit(result.success ? 0 : 1);
      
    } catch (error) {
      console.error(JSON.stringify({
        success: false,
        error: error.message || 'Unknown error'
      }, null, 2));
      process.exit(1);
    }
  }
}

/**
 * Read from stdin (helper function)
 */
function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', chunk => {
      data += chunk;
    });
    process.stdin.on('error', reject);
    process.stdin.on('end', () => resolve(data.trim()));
  });
}

// CLI interface
if (import.meta.url === `file://${process.argv[1]}`) {
  const action = process.argv[2];
  
  switch (action) {
    case 'process':
      // Main hook processing interface
      HookHandler.processHookFromStdin();
      break;
      
    case 'test':
      // Test hook processing with sample data
      const sampleData = {
        hook_event_name: 'pre-tool-use',
        session_id: 'test-session',
        tool_name: 'Write',
        tool_input: {
          file_path: 'test.js',
          content: 'console.log("Hello");'
        }
      };
      
      const handler = new HookHandler();
      const result = await handler.processHook(sampleData);
      console.log(JSON.stringify(result, null, 2));
      break;
      
    default:
      console.log('Usage: HookHandler.js {process|test}');
      console.log('');
      console.log('  process  - Process hook data from stdin (main interface)');
      console.log('  test     - Run with sample data for testing');
      process.exit(1);
  }
}
