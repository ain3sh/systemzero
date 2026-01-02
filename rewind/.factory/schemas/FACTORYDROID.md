### 1. The Core Data Models

We unify all log entry types into a single `TimelineNode` wrapper to allow generic traversal, while preserving strict typing for the payload data.

```typescript
type NodeId = string;

// The unified wrapper for any point in time
interface TimelineNode {
  id: NodeId;
  // If null, this is the Local Root (start of this specific session file)
  parentId: NodeId | null; 
  // Derived during parsing to enable "Redo" / Forward navigation
  childrenIds: NodeId[]; 
  
  // High-level type discriminator
  kind: 'session_start' | 'message' | 'state_update';
  
  // The specific content payload
  data: SessionStartPayload | MessagePayload | TodoPayload;
  
  timestamp: number; // Normalized epoch time
}

// Payload: Session Metadata
interface SessionStartPayload {
  title: string;
  cwd: string;
  // Preserved for context, even if the parent isn't in this file
  originalParentId: string | null; 
}

// Payload: Conversation Items
interface MessagePayload {
  role: 'user' | 'assistant';
  visibility?: 'llm_only' | 'both'; 
  // Granular content blocks
  content: Array<ContentBlock>; 
}

// Payload: Side-Effect State (Todo List)
interface TodoPayload {
  messageIndex: number; // The logic hook used to resolve parentId
  todos: Array<{
    id: string;
    content: string;
    status: 'pending' | 'in_progress' | 'completed';
    priority?: string;
  }>;
}

// Granular Content Block Definition
type ContentBlock = 
  | { type: 'text'; text: string }
  | { type: 'thinking'; signature: string; thinking: string }
  | { type: 'tool_use'; id: string; name: string; input: Record<string, any> }
  | { type: 'tool_result'; tool_use_id: string; content: string; is_error?: boolean };
```

### 2. The Graph Container Schema

This is the state object held by the application to manage the timeline.

```typescript
interface ConversationGraph {
  // O(1) lookup for any node
  nodes: Record<NodeId, TimelineNode>;
  
  // An ordered array of just the Message IDs. 
  // CRITICAL: This is required to resolve 'messageIndex' in Todo payloads.
  messageSequence: NodeId[];
  
  // The absolute start of this file's history
  rootId: NodeId;
  
  // The pointer to what the user is currently looking at
  headId: NodeId;
}
```

### 3. Parsing Logic (Ingestion)

This algorithm converts the linear JSONL stream into the Tree structure. It specifically solves the "Orphaned Todo State" issue identified during stress testing.

```javascript
function parseLogToGraph(logEntries) {
  const graph = {
    nodes: {},
    messageSequence: [],
    rootId: null,
    headId: null
  };

  // Pass 1: Node Creation & Indexing
  for (const entry of logEntries) {
    const nodeId = entry.id || `generated_${Date.now()}_${Math.random()}`; // Handle implicit IDs if any
    
    // Determine Parent Relationship
    let parentId = entry.parentId || entry.parent || null;

    // FIX: Handle 'todo_state' which lacks parentId but has messageIndex
    if (entry.type === 'todo_state' && typeof entry.messageIndex === 'number') {
      // It links to the message at that specific index in our sequence
      parentId = graph.messageSequence[entry.messageIndex];
    }

    // Determine Node Kind
    let kind = 'message';
    if (entry.type === 'session_start') kind = 'session_start';
    if (entry.type === 'todo_state') kind = 'state_update';

    const node = {
      id: nodeId,
      parentId: parentId, // Note: might point to non-existent ID if it's the root
      childrenIds: [],
      kind: kind,
      data: entry,
      timestamp: new Date(entry.timestamp || Date.now()).getTime()
    };

    // Store Node
    graph.nodes[nodeId] = node;

    // Update Sequence Trackers
    if (kind === 'message') {
      graph.messageSequence.push(nodeId);
    }
    
    if (kind === 'session_start') {
      graph.rootId = nodeId;
    }
    
    // Default head is the last processed node
    graph.headId = nodeId;
  }

  // Pass 2: Hydrate Children (The Tree Construction)
  // We iterate our own nodes map to ensure bidirectional linking
  Object.values(graph.nodes).forEach(node => {
    if (node.parentId && graph.nodes[node.parentId]) {
      graph.nodes[node.parentId].childrenIds.push(node.id);
    } else if (node.parentId && !graph.nodes[node.parentId]) {
      // Edge Case: The parent exists in a previous session file.
      // Treat this node as a local root if strict continuity isn't required.
      if (node.kind === 'session_start') graph.rootId = node.id;
    }
  });

  return graph;
}
```

### 4. Implementing "Rewind", "Undo Rewind", and "Branching"

Operations are performed by manipulating pointers and creating new nodes.

#### Rewind (Back)
User clicks "Rewind to here" on Message A.
1.  **Operation:** `graph.headId = MessageA.id`
2.  **View Render:** Traverse `parentId` from `headId` to `rootId` to build the linear chat view.
3.  **State Restore:** Search upwards from `headId` to find the nearest ancestor of kind `state_update` (Todo list). Apply that state.

#### Undo Rewind (Forward/Redo)
User clicks "Forward" from Message A.
1.  **Check:** Does `graph.nodes[MessageA.id].childrenIds` have entries?
2.  **Scenario Single Child:** `graph.headId = childrenIds[0]`
3.  **Scenario Multiple Children (Branching):** UI presents a "Version Selector" (e.g., "< 2 of 3 >"). User picks index `i`. `graph.headId = childrenIds[i]`.

#### Branching (Edit History)
User rewinds to Message A and submits a *new* prompt or modifies the tool output.
1.  **Context:** Current head is Message A.
2.  **Action:** Create new Node `Message B_prime`.
3.  **Linkage:** `Message B_prime.parentId = Message A.id`.
4.  **Tree Update:** `graph.nodes[Message A.id].childrenIds.push(Message B_prime.id)`.
5.  **Move Head:** `graph.headId = Message B_prime.id`.
    *   *Result:* Message A now has two children (original history `B` and new history `B_prime`). The "Undo Rewind" logic now triggers the "Multiple Children" scenario.

### 5. Detailed Multi-level Granularity Considerations

The logs group atomic actions (Thinking + Tool Call) into single messages. This creates a granularity mismatch for rewinding.

#### The Problem
A single message node (ID: `msg_1`) contains:
1.  Thinking: "I should delete the root directory."
2.  Tool Use: `rm -rf /`

User wants to: Keep the thinking, but prevent the tool use.

#### The Solution: Virtual Branching
Since we cannot point to a "half-node", we must branch at the *previous* node.

**Scenario:**
*   Node A (User: "Fix this")
*   Node B (Assistant: [Thinking], [Tool Use])

**User Action:** "Rewind to before Tool Use" (Edit the response).

**Execution Logic:**
1.  Identify Target: Node B.
2.  Identify Parent: Node A.
3.  **Clone & Modify:** Create Node C.
    *   Copy data from Node B.
    *   *Edit the content array:* Remove the `tool_use` block. Keep `thinking`.
4.  **Link:** Set Node C parent to Node A.
5.  **Set Head:** Set `headId` to Node C.

**Visual Result:**
```text
Node A
  |
  +-- Node B (Original: Thinking + Tool Call) [Inactive Branch]
  |
  +-- Node C (New Head: Thinking only) [Active Branch]
```
The Assistant is now in a state where it has "Thought" but not acted. The context window includes the thought. The next generated token/action will effectively be a retry of the tool use.

### 6. Final Example Data Structure

A visualized slice of the `ConversationGraph` after parsing and one branching action.

```javascript
{
  "rootId": "session_start_1",
  "headId": "msg_3_branch_2", // We are currently on a branched timeline
  "messageSequence": ["msg_1", "msg_2", "msg_3", "msg_3_branch_2"],
  "nodes": {
    "session_start_1": {
      "id": "session_start_1",
      "kind": "session_start",
      "childrenIds": ["msg_1"],
      "data": { "cwd": "/code" }
    },
    "msg_1": {
      "id": "msg_1",
      "kind": "message",
      "parentId": "session_start_1",
      "childrenIds": ["msg_2"],
      "data": { "role": "user", "content": [{"type": "text", "text": "Run tests"}] }
    },
    "msg_2": {
      "id": "msg_2",
      "kind": "message",
      "parentId": "msg_1",
      // NOTE: This node has TWO children. A divergence point.
      "childrenIds": ["msg_3", "msg_3_branch_2"], 
      "data": { "role": "assistant", "content": [{"type": "thinking", "text": "Running..."}] }
    },
    // The Original History (User rewound from here because tests failed)
    "msg_3": {
      "id": "msg_3",
      "kind": "message",
      "parentId": "msg_2",
      "childrenIds": [],
      "data": { "role": "assistant", "content": [{"type": "tool_use", "name": "run_tests"}] }
    },
    // The New History (User manually fixed the command)
    "msg_3_branch_2": {
      "id": "msg_3_branch_2",
      "kind": "message",
      "parentId": "msg_2",
      "childrenIds": [],
      "data": { "role": "assistant", "content": [{"type": "tool_use", "name": "run_tests_verbose"}] }
    },
    // Sidecar state attached to msg_2
    "todo_state_1": {
      "id": "todo_state_1",
      "kind": "state_update",
      "parentId": "msg_2", // Resolved via messageIndex: 1
      "childrenIds": [],
      "data": { "todos": [] }
    }
  }
}
```