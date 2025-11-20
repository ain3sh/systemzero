#!/usr/bin/env node

import path from 'path';
import process from 'process';
import { fileURLToPath } from 'url';
import { CheckpointEngine } from './CheckpointEngine.js';
import { ConversationMetadata } from '../metadata/ConversationMetadata.js';
import { SessionParser } from '../parsers/SessionParser.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

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

function buildDescription(action, toolName = 'tool') {
  switch (action) {
    case 'session-start':
      return 'Session start';
    case 'stop':
      return 'Session end';
    case 'post-bash':
      return 'Auto: After bash command';
    case 'subagent-start':
      return `Subagent start: ${toolName}`;
    case 'subagent-stop':
      return `Subagent stop: ${toolName}`;
    case 'pre-tool-use':
    default:
      return `Auto: Before ${toolName}`;
  }
}

async function gatherConversation(agentHint, payload) {
  try {
    const parser = new SessionParser(agentHint || 'auto');
    const sessionFile = await parser.getCurrentSessionFile();
    if (!sessionFile) return null;
    const messages = await parser.parseSessionFile(sessionFile);
    if (!messages.length) return null;
    const latest = parser.getLatestUserMessage(messages);
    if (!latest) return null;
    const messageIndex = messages.findIndex(msg => msg.uuid === latest.uuid);
    return {
      agent: agentHint || parser.agent,
      sessionId: latest.sessionId || payload.session_id || null,
      sessionFile,
      messageUuid: latest.uuid,
      messageIndex,
      userPrompt: latest.content,
      timestamp: latest.timestamp
    };
  } catch (error) {
    return null;
  }
}

function structuralAction(action) {
  return ['session-start', 'stop', 'subagent-start', 'subagent-stop'].includes(action);
}

async function main() {
  const actionArg = process.argv[2] || 'pre-tool-use';
  const stdinData = await readStdin();
  let payload = {};
  if (stdinData) {
    try {
      payload = JSON.parse(stdinData);
    } catch (error) {
      payload = {};
    }
  }

  const action = payload.hook_event_name || actionArg;
  const projectRoot = payload.cwd ? path.resolve(payload.cwd) : process.cwd();
  const engine = new CheckpointEngine({ projectRoot });
  const metadataStore = new ConversationMetadata(projectRoot);

  const description = buildDescription(action, payload.tool_name || 'tool');
  const force = structuralAction(action) || payload.force === true;

  try {
    const result = await engine.createCheckpoint({ description, force });
    if (!result.success && result.noChanges) {
      return console.log(JSON.stringify({ success: true, noChanges: true, reason: result.message }));
    }
    if (!result.success) {
      console.log(JSON.stringify({ success: false, error: result.error || 'Failed to create checkpoint' }));
      process.exit(1);
    }

    const conversation = await gatherConversation(payload.agent_name, payload);
    let metadataStored = false;
    if (conversation) {
      await metadataStore.add(result.name, conversation);
      metadataStored = true;
    }

    console.log(JSON.stringify({
      success: true,
      checkpointName: result.name,
      metadataStored,
      description: result.description
    }));
  } catch (error) {
    console.log(JSON.stringify({ success: false, error: error.message || String(error) }));
    process.exit(1);
  }
}

main();
