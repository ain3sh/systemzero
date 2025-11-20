import path from 'path';
import process from 'process';
import { CheckpointStore } from './CheckpointStore.js';
import { ContextManager } from './ContextManager.js';

/**
 * RewindController - Core orchestrator for atomic state management
 * 
 * This is the main API surface for the rewind system. It coordinates
 * CheckpointStore (code snapshots) and ContextManager (conversation state)
 * to provide atomic operations where code and context move together.
 * 
 * Key principles:
 * - Atomic operations: Code and Context restore together or not at all
 * - Safety first: Create emergency backups before any destructive operation
 * - Fail fast: Validate inputs early and provide clear error messages
 * - Single responsibility: Only orchestrates, doesn't implement storage logic
 */
export class RewindController {
  constructor({ projectRoot = process.cwd() } = {}) {
    this.projectRoot = path.resolve(projectRoot);
    this.checkpointStore = new CheckpointStore({ projectRoot: this.projectRoot });
    this.contextManager = new ContextManager(this.projectRoot);
  }

  async init() {
    await this.checkpointStore.initialize();
    const config = await this.checkpointStore.getConfig();
    await this.contextManager.initialize(config);
  }

  /**
   * Create a checkpoint with conversation metadata
   */
  async createCheckpoint({ description = '', name, force = false, hookPayload = {} } = {}) {
    try {
      // Create code checkpoint
      const checkpointResult = await this.checkpointStore.createCheckpoint({
        description,
        name,
        force
      });

      if (!checkpointResult.success) {
        return checkpointResult; // Pass through no-changes or error
      }

      // Gather and store conversation context
      let metadataStored = false;
      try {
        const contextData = await this.contextManager.gatherContext(hookPayload);
        if (contextData) {
          await this.contextManager.addCheckpointMetadata(
            checkpointResult.name,
            contextData
          );
          metadataStored = true;
        }
      } catch (error) {
        // Context gathering is non-fatal - checkpoint still succeeded
        console.warn('[RewindController] Failed to gather context:', error.message);
      }

      return {
        success: true,
        name: checkpointResult.name,
        description: checkpointResult.description,
        fileCount: checkpointResult.fileCount,
        totalBytes: checkpointResult.totalBytes,
        metadataStored,
        checkpointResult
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to create checkpoint: ${error.message}`
      };
    }
  }

  /**
   * List checkpoints with enriched metadata
   */
  async listCheckpoints() {
    try {
      const checkpoints = await this.checkpointStore.listCheckpoints();
      const conversationMetadata = await this.contextManager.listMetadata();

      // Enrich checkpoints with conversation data
      return checkpoints.map(checkpoint => {
        const context = conversationMetadata[checkpoint.name];
        return {
          ...checkpoint,
          context: context || null,
          hasContext: !!context
        };
      });
    } catch (error) {
      throw new Error(`Failed to list checkpoints: ${error.message}`);
    }
  }

  /**
   * Get detailed checkpoint information including diff summaries
   */
  async getCheckpointDetails(checkpointName) {
    try {
      const checkpoints = await this.checkpointStore.listCheckpoints();
      const target = checkpoints.find(cp => 
        cp.name === checkpointName || cp.name.includes(checkpointName)
      );

      if (!target) {
        return { success: false, error: `Checkpoint not found: ${checkpointName}` };
      }

      // Get conversation metadata
      const context = await this.contextManager.getCheckpointMetadata(target.name);

      // Calculate diff from current state if possible
      let diffSummary = null;
      try {
        // Create a temporary checkpoint to compare against
        const tempResult = await this.checkpointStore.createCheckpoint({
          name: '_temp_diff',
          description: 'Temporary for diff calculation',
          force: true
        });

        if (tempResult.success) {
          const tempCheckpoints = await this.checkpointStore.listCheckpoints();
          const tempCheckpoint = tempCheckpoints.find(cp => cp.name === tempResult.name);
          
          if (tempCheckpoint) {
            diffSummary = await this.checkpointStore.getDiffSummary(target, tempCheckpoint);
          }

          // Clean up temp checkpoint
          await this.cleanupCheckpoint(tempResult.name);
        }
      } catch (error) {
        // Diff calculation is non-essential
        console.warn('[RewindController] Failed to calculate diff:', error.message);
      }

      return {
        success: true,
        checkpoint: target,
        context,
        diffSummary
      };
    } catch (error) {
      return {
        success: false,
        error: `Failed to get checkpoint details: ${error.message}`
      };
    }
  }

  /**
   * Restore checkpoint with mode selection
   * 
   * @param {string} checkpointName - Name or partial name of checkpoint
   * @param {string} mode - 'both', 'code', 'context'
   * @param {boolean} skipBackup - Skip emergency backup (dangerous!)
   */
  async restore(checkpointName, mode = 'both', options = {}) {
    const { skipBackup = false, dryRun = false } = options;

    // Validation
    if (!['both', 'code', 'context'].includes(mode)) {
      return {
        success: false,
        error: `Invalid mode: ${mode}. Must be 'both', 'code', or 'context'`
      };
    }

    try {
      // Find checkpoint
      const checkpoints = await this.checkpointStore.listCheckpoints();
      const target = checkpoints.find(cp => 
        cp.name === checkpointName || cp.name.includes(checkpointName)
      );

      if (!target) {
        return { 
          success: false, 
          error: `Checkpoint not found: ${checkpointName}` 
        };
      }

      const result = {
        success: false,
        checkpointName: target.name,
        mode,
        dryRun
      };

      // Create safety point (emergency backup) unless skipped
      let safetyPoint = null;
      if (!skipBackup && !dryRun) {
        try {
          const backupResult = await this.createCheckpoint({
            description: `Safety backup before restore to ${target.name}`,
            name: 'emergency_backup',
            force: true
          });
          safetyPoint = backupResult.success ? backupResult.name : null;
        } catch (error) {
          return {
            success: false,
            error: `Failed to create safety backup: ${error.message}`
          };
        }
      }

      // Execute restoration based on mode
      try {
        if (mode === 'code' || mode === 'both') {
          await this.restoreCode(target, dryRun);
          result.codeRestored = true;
        }

        if (mode === 'context' || mode === 'both') {
          const contextResult = await this.restoreContext(target.name, dryRun);
          result.contextRestored = contextResult.success;
          result.contextDetails = contextResult;
          
          if (!contextResult.success && mode === 'both') {
            // Context restore failed in 'both' mode - this is non-fatal but should be reported
            result.warning = `Code restored successfully but context restore failed: ${contextResult.error}`;
          }
        }

        result.success = true;
        result.safetyBackup = safetyPoint;
        result.message = this.buildSuccessMessage(mode, result);
        
        return result;

      } catch (error) {
        // Restoration failed - attempt rollback to safety point
        if (safetyPoint && !dryRun) {
          try {
            await this.restoreCode(
              checkpoints.find(cp => cp.name === safetyPoint),
              false
            );
            result.rolledBack = true;
            result.error = `Restore failed, rolled back to safety point: ${error.message}`;
          } catch (rollbackError) {
            result.error = `Restore failed AND rollback failed: ${error.message}. Rollback error: ${rollbackError.message}`;
          }
        } else {
          result.error = `Restore failed: ${error.message}`;
        }
        
        return result;
      }
    } catch (error) {
      return {
        success: false,
        error: `Restore operation failed: ${error.message}`
      };
    }
  }

  /**
   * Restore code portion of a checkpoint
   */
  async restoreCode(checkpoint, dryRun = false) {
    if (dryRun) {
      return; // No-op for dry run
    }

    const result = await this.checkpointStore.restoreCheckpoint({
      name: checkpoint.name
    });

    if (!result.success) {
      throw new Error(result.error || 'Code restoration failed');
    }
  }

  /**
   * Restore context portion of a checkpoint
   */
  async restoreContext(checkpointName, dryRun = false) {
    const contextResult = await this.contextManager.restoreContext(checkpointName);
    
    if (!contextResult.success) {
      return contextResult;
    }

    if (dryRun) {
      return {
        ...contextResult,
        dryRun: true,
        message: '[DRY RUN] Would truncate conversation and require agent restart'
      };
    }

    return contextResult;
  }

  /**
   * Build user-friendly success message
   */
  buildSuccessMessage(mode, result) {
    const messages = [];
    
    if (result.codeRestored) {
      messages.push('✅ Code restored');
    }
    
    if (result.contextRestored) {
      messages.push('✅ Context restored');
      if (result.contextDetails && result.contextDetails.actionRequired) {
        messages.push(result.contextDetails.actionRequired);
      }
    }

    if (result.safetyBackup) {
      messages.push(`🛡️ Safety backup: ${result.safetyBackup}`);
    }

    return messages.join('\n');
  }

  /**
   * Undo the last checkpoint (convenience method)
   */
  async undoLastCheckpoint(mode = 'both') {
    const checkpoints = await this.checkpointStore.listCheckpoints();
    if (!checkpoints.length) {
      return { success: false, error: 'No checkpoints to undo' };
    }
    
    return this.restore(checkpoints[0].name, mode);
  }

  /**
   * Clean up a specific checkpoint
   */
  async cleanupCheckpoint(checkpointName) {
    // This is a helper method - CheckpointStore doesn't expose individual deletion
    // We'd need to add this capability if needed
    console.warn('[RewindController] Individual checkpoint cleanup not implemented');
  }

  /**
   * Get system status
   */
  async getStatus() {
    try {
      const checkpoints = await this.listCheckpoints();
      const config = await this.checkpointStore.getConfig();
      const agent = this.contextManager.detectAgent();
      const isGlobal = this.checkpointStore.baseDir.includes('.rewind/storage');
      
      return {
        projectRoot: this.projectRoot,
        agent,
        storageMode: isGlobal ? 'global' : 'project',
        storagePath: this.checkpointStore.baseDir,
        checkpointCount: checkpoints.length,
        checkpointsWithContext: checkpoints.filter(cp => cp.hasContext).length,
        tier: this.checkpointStore.configLoader.getTier(),
        config: {
          maxCheckpoints: config.maxCheckpoints,
          maxAgeDays: config.maxAgeDays,
          antiSpam: config.antiSpam
        }
      };
    } catch (error) {
      throw new Error(`Failed to get status: ${error.message}`);
    }
  }

  /**
   * Cleanup orphaned metadata
   */
  async cleanupMetadata() {
    try {
      const checkpoints = await this.checkpointStore.listCheckpoints();
      const validNames = checkpoints.map(cp => cp.name);
      const cleaned = await this.contextManager.cleanupOrphanedMetadata(validNames);
      
      return {
        success: true,
        cleanedCount: cleaned
      };
    } catch (error) {
      return {
        success: false,
        error: `Metadata cleanup failed: ${error.message}`
      };
    }
  }

  /**
   * Validate system integrity
   */
  async validateSystem() {
    const issues = [];
    
    try {
      // Check if we can create/list checkpoints
      const checkpoints = await this.checkpointStore.listCheckpoints();
      
      // Check if context manager can detect agent
      const agent = this.contextManager.detectAgent();
      if (agent === 'unknown') {
        issues.push('Cannot detect current agent (Claude Code or Droid CLI)');
      }
      
      // Check for orphaned metadata
      const metadata = await this.contextManager.listMetadata();
      const checkpointNames = new Set(checkpoints.map(cp => cp.name));
      const orphaned = Object.keys(metadata).filter(name => !checkpointNames.has(name));
      
      if (orphaned.length > 0) {
        issues.push(`${orphaned.length} orphaned metadata entries found`);
      }
      
      return {
        valid: issues.length === 0,
        issues,
        stats: {
          checkpointCount: checkpoints.length,
          metadataCount: Object.keys(metadata).length,
          orphanedMetadata: orphaned.length,
          agent
        }
      };
    } catch (error) {
      return {
        valid: false,
        issues: [`System validation failed: ${error.message}`]
      };
    }
  }
}
