### 1. The Core Data Models

We utilize a strict typing system to differentiate between "Human" inputs, "System" inputs (tool outputs), and "AI" actions.

```python
from typing import Dict, List, Optional, Any, Literal
from dataclasses import dataclass, field

# Enum to distinguish semantic intent from raw JSON roles
NodeType = Literal[
    "human_prompt",       # Active user input (role: user)
    "context_injection",  # Local commands/System outputs (role: user, but starts with tags like <local-command-stdout>)
    "assistant_thought",  # Model thinking blocks (role: assistant)
    "assistant_action",   # Model tool calls or text response (role: assistant)
    "tool_execution",     # Result of a tool use (role: user, content type: tool_result)
    "termination",        # Session end/exit events
]

@dataclass
class FileVersion:
    """Represents a specific version of a file at a point in time."""
    backup_file_name: str  # The hashed filename in the backup directory
    version_id: int
    timestamp: str

@dataclass
class ConversationNode:
    # --- Identity & Topology ---
    uuid: str
    parent_uuid: Optional[str]
    children: List[str] = field(default_factory=list)
    timestamp: str
    
    # --- Classification ---
    node_type: NodeType
    
    # --- Content Payload ---
    # The actual chat message, tool input, or tool output list
    content: List[Dict[str, Any]]
    
    # --- State Snapshots (The Sidecar Data) ---
    # Data merged from 'file-history-snapshot' entries.
    # Key: Real file path (e.g., "hooks/pre_compact.py")
    # Value: The backup metadata required to restore it.
    file_system_state: Dict[str, FileVersion] = field(default_factory=dict)
    
    # --- Ephemeral State ---
    # Queue operations or context derived from non-node log lines
    # that occurred immediately after this node.
    system_events: List[Dict[str, Any]] = field(default_factory=list)
```

---

### 2. The Graph Container Schema

This container manages the "Head" pointer, allowing us to move backward and forward without deleting history.

```python
class ConversationGraph:
    def __init__(self):
        # O(1) Lookup Table
        self.nodes: Dict[str, ConversationNode] = {}
        
        # The true beginning of the session
        self.root_uuid: Optional[str] = None
        
        # The 'Active' tip. When the user types, new nodes attach here.
        # Rewinding changes this pointer.
        self.current_head_uuid: Optional[str] = None
        
        # Helper to track the latest file snapshots during ingestion
        # before they can be attached to a node.
        self._snapshot_buffer: Dict[str, Dict[str, FileVersion]] = {}
```

---

### 3. Parsing Logic (Ingestion)

The parsing requires a **Two-Pass Strategy** (or Lookaside) because `file-history-snapshot` entries often appear *after* the message they modify, or refer to `messageId`s that serve as foreign keys.

#### Algorithm

1.  **Initialize:** `nodes = {}`, `snapshots = {}`.
2.  **Pass 1 (Raw Ingestion & Classification):**
    *   Read Line $L$.
    *   **Case A: Standard Message (User/Assistant)**
        *   Extract `uuid`, `parentUuid`.
        *   Determine `NodeType`:
            *   If `tool_uses` present $\rightarrow$ `assistant_action`.
            *   If `content` has `tool_result` $\rightarrow$ `tool_execution`.
            *   If text contains `<local-command-stdout>` $\rightarrow$ `context_injection`.
            *   Else $\rightarrow$ `human_prompt`.
        *   Create `ConversationNode`.
    *   **Case B: Snapshot (`file-history-snapshot`)**
        *   Do *not* create a node.
        *   Store in `snapshots` dict: `snapshots[L.messageId] = L.trackedFileBackups`.
    *   **Case C: Queue/System (`queue-operation`)**
        *   Store in a temporary buffer, attach to the *next* processed Node's `system_events` (or previous, depending on timestamp implementation preference).
3.  **Pass 2 (Wiring & Hydration):**
    *   Iterate over `nodes`.
    *   **Linkage:** If `node.parent_uuid` exists, append `node.uuid` to `nodes[parent].children`.
    *   **Hydration:** Check `snapshots[node.uuid]`. If exists, transform raw JSON into `file_system_state` (Dict of `FileVersion`) and attach to the node.

---

### 4. Implementing Operations

#### A. Rewind (Time Travel)
Rewinding moves the "Head" to a past node and restores the environment.

1.  **Identify Target:** User selects Node $X$ (ancestor of `current_head`).
2.  **Move Head:** `self.current_head_uuid = X.uuid`.
3.  **Restore State:**
    *   Access `X.file_system_state`.
    *   For every file in this dictionary:
        *   Locate the backup file on disk using `backup_file_name`.
        *   Overwrite the live file in the workspace with the backup content.
    *   *Note:* Files created *after* Node $X$ (in the future) are left as-is unless specific "deletion logs" are tracked, or the system performs a full git checkout if supported.

#### B. Branching (Alternate History)
Branching happens automatically when actions are taken after a Rewind.

1.  **Pre-condition:** `current_head_uuid` is at Node $X$. Node $X$ already has child $Y$.
2.  **Action:** User sends new prompt.
3.  **Creation:** Create Node $Z$. Set `Z.parent_uuid = X.uuid`.
4.  **Linkage:** Append $Z$ to `X.children`. $X$ now branches to $[Y, Z]$.
5.  **Advance:** `self.current_head_uuid = Z.uuid`.

#### C. Undo Rewind (Switching Branches)
If a user rewinds to $X$, creating branch $Z$, but decides they liked the original future $Y$ better.

1.  **Navigation:** User selects Node $Y$ (or a leaf node descendant of $Y$) in the UI.
2.  **Move Head:** `self.current_head_uuid = Y.uuid`.
3.  **Restore State:** Perform **Restore State** logic using `Y.file_system_state`.

---

### 5. Multi-level Granularity Considerations

The raw graph is too dense for typical users. The UI/API should traverse the graph but filter the *view* based on granularity.

| Granularity Level | Nodes Visible | Use Case |
| :--- | :--- | :--- |
| **L1: Conversation** | `human_prompt`, `assistant_action` (Text only) | "I want to modify my prompt and try again." (Standard ChatGPT style) |
| **L2: Reasoning** | + `assistant_thought`, `assistant_action` (Tool calls) | "The agent used the wrong tool. I want to rewind to before the tool call." |
| **L3: Execution** | + `tool_execution`, `context_injection` | "The tool failed or output bad data. I want to mock a success result." |
| **L4: System (Debug)** | + `snapshots`, `termination` | Developer debugging. Analyzing file state corruption. |

**Logic for L1 Traversal:**
When rendering L1, if the parent of Node $B$ is a `tool_execution` (L3), recursively traverse up `parent_uuid` until an L1 node is found. That becomes the "Visual Parent."

---

### 6. Final Example Data Structure

This is what a fully hydrated Node looks like in the Graph, representing the moment the Assistant decided to fetch documentation.

```json
{
  "uuid": "fc4794f1-7220-46ed-9e55-650b9bc65a18",
  "parent_uuid": "379d0524-90f1-4f6d-b9d5-7a7f2998730e",
  "children": [
    "87fa3979-159d-4abe-a5e5-d3f5e828f125"
  ],
  "timestamp": "2025-12-29T20:43:59.443Z",
  "node_type": "assistant_thought",
  "content": [
    {
      "type": "thinking",
      "thinking": "The user wants me to upgrade the pre_compact.py hook..."
    }
  ],
  "file_system_state": {
    "hooks/pre_compact.py": {
      "backup_file_name": "026831e7ecb41873@v1",
      "version_id": 1,
      "timestamp": "2025-12-29T20:45:21.762Z"
    },
    "commands/compact.md": {
      "backup_file_name": "05f787e0930bbff8@v2",
      "version_id": 2,
      "timestamp": "2025-12-29T20:49:39.209Z"
    }
  },
  "system_events": []
}
```