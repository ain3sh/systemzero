
import fs from 'fs/promises';
import path from 'path';
import os from 'os';
import { spawn } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const TEST_ROOT = path.join(__dirname, 'v3-suite-temp');
const MOCK_HOME = path.join(TEST_ROOT, 'home');
const PROJECT_ROOT = path.join(TEST_ROOT, 'project');

// Helper to run CLI commands
async function runCli(args, cwd = PROJECT_ROOT) {
  return new Promise((resolve, reject) => {
    // We run the CLI directly from the bin folder, but simulate it as if installed
    const cliPath = path.join(__dirname, '../bin/rewind.js');
    
    const child = spawn(process.execPath, [cliPath, ...args], {
      cwd,
      env: { 
        ...process.env, 
        HOME: MOCK_HOME
      },
      stdio: 'pipe' // Capture output
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', d => stdout += d.toString());
    child.stderr.on('data', d => stderr += d.toString());

    child.on('close', code => {
      if (code === 0) resolve(stdout);
      else reject(new Error(`CLI failed (${code}): ${stderr || stdout}`));
    });
  });
}

async function testV3Suite() {
  console.log('🚀 Starting System Zero v3 Integration Suite\n');

  try {
    // Cleanup & Setup
    await fs.rm(TEST_ROOT, { recursive: true, force: true });
    await fs.mkdir(MOCK_HOME, { recursive: true });
    await fs.mkdir(PROJECT_ROOT, { recursive: true });
    
    // Create dummy file
    await fs.writeFile(path.join(PROJECT_ROOT, 'test.txt'), 'v1');

    // ---------------------------------------------------
    // Test 1: Zero Config (Default Project Mode)
    // ---------------------------------------------------
    console.log('🧪 Test 1: Zero Config (Project Mode)');
    
    // Run 'save' without any setup
    const output1 = await runCli(['save', 'Initial Commit']);
    console.log('   Save output:', output1.trim().split('\n')[0]); // Just first line
    
    // Verify .rewind exists in project
    const hasLocalRewind = await fs.stat(path.join(PROJECT_ROOT, '.rewind'))
      .then(() => true).catch(() => false);
      
    if (!hasLocalRewind) throw new Error('Expected .rewind in project root');
    console.log('   ✅ Automatically created local .rewind directory');

    // ---------------------------------------------------
    // Test 2: Rewind Init (Global Mode)
    // ---------------------------------------------------
    console.log('\n🧪 Test 2: Rewind Init (Global Mode)');
    
    // Switch to global mode
    await runCli(['init', '--mode', 'global']);
    
    // Check config file
    const configPath = path.join(PROJECT_ROOT, '.rewind/config.json');
    const config = JSON.parse(await fs.readFile(configPath, 'utf8'));
    
    if (config.storage.mode !== 'global') throw new Error('Config not set to global');
    console.log('   ✅ Config updated to global mode');

    // Create new checkpoint
    await fs.writeFile(path.join(PROJECT_ROOT, 'test.txt'), 'v2');
    const output2 = await runCli(['save', 'Global Checkpoint']);
    console.log('   Save output:', output2.trim().split('\n')[0]);

    // Verify storage location (should be in MOCK_HOME/.rewind/storage)
    const globalStorage = path.join(MOCK_HOME, '.rewind/storage');
    const storageExists = await fs.stat(globalStorage).then(() => true).catch(() => false);
    
    if (!storageExists) throw new Error(`Expected global storage at ${globalStorage}`);
    
    const storageDirs = await fs.readdir(globalStorage);
    if (storageDirs.length === 0) throw new Error('Global storage directory is empty');
    
    console.log(`   ✅ Found global storage dir: ${storageDirs[0]}`);

    // ---------------------------------------------------
    // Test 3: Status Command
    // ---------------------------------------------------
    console.log('\n🧪 Test 3: Status Command');
    
    const statusOutput = await runCli(['status']);
    if (!statusOutput.includes('Storage: 🌍 GLOBAL')) {
      throw new Error('Status command did not report GLOBAL storage');
    }
    console.log('   ✅ Status reports GLOBAL storage');

    console.log('\n🎉 v3 Suite Passed Successfully!');

  } catch (error) {
    console.error('\n❌ Test Failed:', error.message);
    if (error.stack) console.error(error.stack);
    process.exit(1);
  } finally {
    // Cleanup
    await fs.rm(TEST_ROOT, { recursive: true, force: true });
  }
}

testV3Suite();
