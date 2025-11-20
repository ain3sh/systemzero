import fs from 'fs/promises';
import path from 'path';

/**
 * Utility functions for safe file system operations
 */

/**
 * Atomic write - write to temporary file then rename
 */
export async function atomicWrite(filePath, content, options = {}) {
  const tempPath = `${filePath}.tmp.${process.pid}.${Date.now()}`;
  
  try {
    await fs.writeFile(tempPath, content, options);
    await fs.rename(tempPath, filePath);
  } catch (error) {
    // Clean up temp file on failure
    try {
      await fs.unlink(tempPath);
    } catch {
      // Ignore cleanup errors
    }
    throw error;
  }
}

/**
 * Ensure directory exists, creating it if necessary
 */
export async function ensureDir(dirPath) {
  try {
    await fs.mkdir(dirPath, { recursive: true });
  } catch (error) {
    if (error.code !== 'EEXIST') {
      throw error;
    }
  }
}

/**
 * Check if file exists
 */
export async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Safe JSON parse with error handling
 */
export function safeJsonParse(content, fallback = {}) {
  try {
    return JSON.parse(content);
  } catch {
    return fallback;
  }
}

/**
 * Get file stats with error handling
 */
export async function safeStatFile(filePath) {
  try {
    return await fs.stat(filePath);
  } catch {
    return null;
  }
}
