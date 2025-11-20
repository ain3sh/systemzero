#!/usr/bin/env node

/**
 * Basic Integration Test for System Zero Rewind
 * 
 * Tests the core flow: create checkpoint -> modify files -> restore
 * This is a real test that exercises actual code paths.
 */

import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';
import { RewindController } from '../lib/core/RewindController.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

class IntegrationTest {
  constructor() {
    this.testDir = path.join(__dirname, 'test-workspace');
    this.controller = new RewindController({ projectRoot: this.testDir });
    this.cleanup = [];
  }

  async setup() {
    console.log('🔧 Setting up test workspace...');
    
    // Ensure clean slate
    await fs.rm(this.testDir, { recursive: true, force: true });

    // Create test directory
    await fs.mkdir(this.testDir, { recursive: true });
    this.cleanup.push(() => fs.rm(this.testDir, { recursive: true, force: true }));
    
    // Create initial test files
    await fs.writeFile(path.join(this.testDir, 'app.js'), 'console.log("Hello World");');
    await fs.writeFile(path.join(this.testDir, 'README.md'), '# Test Project\n\nThis is a test.');
    
    // Initialize controller
    await this.controller.init();
    
    console.log('✅ Test workspace created');
  }

  async testCreateCheckpoint() {
    console.log('\n📸 Testing checkpoint creation...');
    
    const result = await this.controller.createCheckpoint({
      description: 'Initial test checkpoint',
      force: true
    });

    if (!result.success) {
      throw new Error(`Checkpoint creation failed: ${result.error}`);
    }

    console.log(`✅ Created checkpoint: ${result.name} (${result.fileCount} files)`);
    return result.name;
  }

  async testModifyFiles() {
    console.log('\n✏️  Testing file modifications...');
    
    // Modify existing file
    await fs.writeFile(path.join(this.testDir, 'app.js'), 'console.log("Modified Hello World");');
    
    // Add new file
    await fs.writeFile(path.join(this.testDir, 'config.json'), '{"version": "1.0.0"}');
    
    console.log('✅ Files modified');
  }

  async testListCheckpoints() {
    console.log('\n📋 Testing checkpoint listing...');
    
    const checkpoints = await this.controller.listCheckpoints();
    
    if (checkpoints.length === 0) {
      throw new Error('No checkpoints found');
    }

    console.log(`✅ Found ${checkpoints.length} checkpoints`);
    checkpoints.forEach((cp, idx) => {
      const hasContext = cp.hasContext ? '💬' : '📄';
      console.log(`   ${idx + 1}. ${hasContext} ${cp.name} (${cp.fileCount} files)`);
    });

    return checkpoints;
  }

  async testRestore(checkpointName) {
    console.log(`\n🔄 Testing restore to: ${checkpointName}`);
    
    const result = await this.controller.restore(checkpointName, 'code', {
      skipBackup: true // Skip backup for test
    });

    if (!result.success) {
      throw new Error(`Restore failed: ${result.error}`);
    }

    console.log('✅ Restore completed');
    
    // Verify files were restored
    const appContent = await fs.readFile(path.join(this.testDir, 'app.js'), 'utf8');
    if (!appContent.includes('Hello World') || appContent.includes('Modified')) {
      throw new Error('File was not properly restored');
    }
    
    // Verify new file was removed
    try {
      await fs.access(path.join(this.testDir, 'config.json'));
      throw new Error('New file was not removed during restore');
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }

    console.log('✅ File state verified');
  }

  async testSystemStatus() {
    console.log('\n🔍 Testing system status...');
    
    const status = await this.controller.getStatus();
    
    console.log(`✅ System Status:`);
    console.log(`   Agent: ${status.agent}`);
    console.log(`   Checkpoints: ${status.checkpointCount}`);
    console.log(`   Tier: ${status.tier}`);
  }

  async testSystemValidation() {
    console.log('\n✅ Testing system validation...');
    
    const validation = await this.controller.validateSystem();
    
    if (!validation.valid) {
      console.warn(`⚠️  Validation issues found:`);
      validation.issues.forEach(issue => console.log(`   - ${issue}`));
    } else {
      console.log('✅ System validation passed');
    }
  }

  async runCleanup() {
    console.log('\n🧹 Cleaning up...');
    
    for (const cleanupFn of this.cleanup.reverse()) {
      try {
        await cleanupFn();
      } catch (error) {
        console.warn('Cleanup warning:', error.message);
      }
    }
    
    console.log('✅ Cleanup completed');
  }

  async run() {
    try {
      console.log('🚀 Starting System Zero Integration Test\n');
      
      await this.setup();
      const checkpointName = await this.testCreateCheckpoint();
      await this.testModifyFiles();
      const checkpoints = await this.testListCheckpoints();
      await this.testRestore(checkpointName);
      await this.testSystemStatus();
      await this.testSystemValidation();
      
      console.log('\n🎉 All tests passed! System Zero is working correctly.');
      
    } catch (error) {
      console.error(`\n❌ Test failed: ${error.message}`);
      if (process.env.DEBUG) {
        console.error(error.stack);
      }
      process.exit(1);
    } finally {
      await this.runCleanup();
    }
  }
}

// Run the test
if (import.meta.url === `file://${process.argv[1]}`) {
  const test = new IntegrationTest();
  test.run();
}
