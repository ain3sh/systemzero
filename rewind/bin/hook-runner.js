#!/usr/bin/env node

/**
 * hook-runner.js - Entry point for hook system
 * 
 * This replaces the complex logic in smart-checkpoint.sh with a clean
 * Node.js entry point that uses the HookHandler class.
 * 
 * Called by hook scripts with action and JSON input via stdin.
 * Outputs structured JSON results.
 */

import path from 'path';
import { fileURLToPath } from 'url';
import { HookHandler } from '../lib/hooks/HookHandler.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  try {
    const action = process.argv[2] || 'pre-tool-use';
    
    // Detect project root from environment or current directory
    const projectRoot = process.env.CLAUDE_PROJECT_DIR || 
                       process.env.FACTORY_PROJECT_DIR || 
                       process.cwd();

    // Process hook using HookHandler
    await HookHandler.processHookFromStdin(projectRoot);
    
  } catch (error) {
    // Ensure we always output valid JSON
    const errorOutput = {
      success: false,
      error: error.message || 'Hook runner failed'
    };
    
    console.error(JSON.stringify(errorOutput, null, 2));
    process.exit(1);
  }
}

// Version check - ensure we're running a recent Node.js version
const nodeVersion = process.version.substring(1).split('.').map(Number);
if (nodeVersion[0] < 18) {
  console.error(JSON.stringify({
    success: false,
    error: `Node.js 18+ required, found ${process.version}`
  }, null, 2));
  process.exit(1);
}

main();
