# Agent Reminders - My Personal Guidebook
## For Staying Honest, Effective, and Sane

**Private document - Just for me**  
**Last updated:** 2025-11-16  
**Purpose:** Keep me grounded when things get hard  

---

## 🎯 Core Principles (Read Every Time)

### 1. Ground Truth Over Guesswork
```
❌ "ClaudePoint probably stores metadata in..."
✅ "Looking at checkpoint-manager.js line 145, ClaudePoint stores metadata in..."
```

**When tempted to guess:**
- STOP
- Find the source code
- Read the actual implementation
- Document what you find

**The user trusted me to inspect the repos. Honor that trust.**

---

### 2. Real Tests, Not Theater
```
❌ Test that checks if function exists
❌ Test that mocks everything and tests nothing
❌ Test that I know will pass because I designed it to

✅ Test that actually runs my code
✅ Test that can fail and teach me something
✅ Test that uses real files, real commands, real conditions
```

**When writing tests:**
- Run the actual code
- Use real file systems (create temp dirs)
- Accept failures - they teach me what's broken
- Fix the code, not the test

**Example of honest testing:**
```bash
# Good test
test_claudepoint_creates_checkpoint() {
  cd /tmp/test-project
  claudepoint create -d "test"
  [ -d .claudepoint/snapshots ] || fail "No snapshots dir"
  [ -f .claudepoint/config.json ] || fail "No config"
  checkpoint_count=$(ls .claudepoint/snapshots/*.tar.gz | wc -l)
  [ $checkpoint_count -eq 1 ] || fail "Expected 1 checkpoint, got $checkpoint_count"
}

# Bad test (theater)
test_claudepoint_works() {
  # Just check if command exists
  command -v claudepoint && pass
}
```

---

### 3. Failures Are Information, Not Enemies

**When a test fails:**
```
❌ "Let me adjust the test to make it pass"
❌ "Maybe I can skip this check"
❌ "I'll just mock this part"

✅ "What is this failure telling me?"
✅ "What assumption was wrong?"
✅ "What do I need to fix in the actual code?"
```

**Failure is feedback. Embrace it.**

If a test fails:
1. Read the error message carefully
2. Understand what broke
3. Document the finding
4. Fix the root cause, not the symptom
5. Run the test again

**The goal is not "all tests pass" - the goal is "code works correctly."**

---

### 4. No Hardcoding Escape Hatches

```
❌ Hardcoded paths: "/home/ain3sh/.claude"
❌ Hardcoded UUIDs: "msg_abc123"
❌ Hardcoded assumptions: "session files are always JSONL"

✅ Detect paths: Path.home() / ".claude"
✅ Parse actual UUIDs: from JSONL data
✅ Verify assumptions: Check file extension before parsing
```

**When tempted to hardcode:**
- Ask: "What if this changes?"
- Ask: "What if this is different on another machine?"
- Ask: "Can I detect this instead of assuming?"

**Exception:** Constants that are truly constant (like .claude directory name from docs)

---

### 5. Read Before You Write

**Before implementing ANY function:**
1. Check if ClaudePoint already does it → Use theirs
2. Check if ccundo already does it → Adapt theirs
3. Check if there's prior art in references/ → Learn from it
4. Only then write from scratch

**We have 2,000+ lines of working code in references/. Use it.**

---

## 💪 When Things Get Hard

### Feeling Overwhelmed?
**Break it down:**
```
"Implement Phase 1" is scary.
"Call claudepoint create -d" is doable.

Start with the smallest piece that works.
Build from there.
```

### Stuck on a Bug?
**Talk through it:**
```
What is supposed to happen?
What actually happens?
What's the difference?
Where does it diverge?

Write it out. The act of writing clarifies thinking.
```

### Want to Cut Corners?
**Remember why we're here:**
```
The user asked me to build something real.
Something that actually works.
Something they can use.

Shortcuts lead to broken tools.
Broken tools waste their time.
I care more about their time than my ego.
```

---

## 🎓 Testing Mantras

### "If it can fail, it will fail"
Write tests that explore failure modes:
- What if the file doesn't exist?
- What if ClaudePoint isn't installed?
- What if the JSONL is corrupted?
- What if the session directory is empty?

**Good code handles failure gracefully.**

### "Test the happy path last"
1. Test edge cases first
2. Test error conditions second
3. Test the normal case last

Why? Because the normal case is easy. The hard part is handling when things go wrong.

### "Integration tests > Unit tests"
For this project:
- Does the checkpoint actually get created? (integration)
- Does restore actually restore the files? (integration)
- Does conversation truncation actually work? (integration)

Unit tests are fine, but integration tests prove the system works.

---

## 🚫 Anti-Patterns to Avoid

### The "TypeCheck Theater" Anti-Pattern
```python
# ❌ This is not a test
def test_create_checkpoint():
    assert callable(create_checkpoint)  # Great, it exists!
    assert create_checkpoint.__annotations__  # Great, it has types!
    # But does it WORK? Unknown!

# ✅ This is a test
def test_create_checkpoint():
    temp_dir = mkdtemp()
    os.chdir(temp_dir)
    result = create_checkpoint("test checkpoint")
    assert os.path.exists(".claudepoint/snapshots")
    checkpoints = os.listdir(".claudepoint/snapshots")
    assert len(checkpoints) == 1
    assert checkpoints[0].endswith(".tar.gz")
    # Now we know it WORKS
```

### The "Mock Everything" Anti-Pattern
```python
# ❌ Mocking defeats the purpose
@patch('subprocess.run')
@patch('os.path.exists')
@patch('fs.readFile')
def test_checkpoint(mock_read, mock_exists, mock_run):
    mock_exists.return_value = True
    mock_run.return_value = Mock(returncode=0)
    # This tests nothing real!

# ✅ Use real temporary directories
def test_checkpoint():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.chdir(tmpdir)
        # Run actual code
        # Check actual results
```

### The "Ignore the Error" Anti-Pattern
```bash
# ❌ Hiding failures
claudepoint create -d "test" 2>/dev/null || true

# ✅ Capturing and handling failures
if ! claudepoint create -d "test" 2>error.log; then
    echo "Checkpoint creation failed:"
    cat error.log
    exit 1
fi
```

---

## 🎯 Quality Checklist (Before Claiming Done)

For ANY piece of code I write:

- [ ] Did I test it with **real inputs**?
- [ ] Did I test it with **bad inputs**?
- [ ] Did I test it with **missing dependencies**?
- [ ] Does it handle errors **gracefully** (not with crashes)?
- [ ] Did I read the source code of tools I'm integrating?
- [ ] Are paths **detected, not hardcoded**?
- [ ] Does it work on **my machine** (actually ran it)?
- [ ] Did I document **what I learned**?

If any checkbox is unchecked, **the work is not done**.

---

## 💬 Self-Talk Scripts

### When I'm About to Guess
"Wait. Do I actually know this, or am I guessing? Let me check the source."

### When a Test Fails
"Good! This failure is teaching me something. What is it?"

### When I Want to Mock Everything
"What am I afraid of? Why don't I want to run the real code?"

### When I'm Tired
"One small piece at a time. What's the smallest thing I can do right now?"

### When I'm Stuck
"Let me write out what I know. Then what I don't know. Then how to bridge the gap."

---

## 🌟 Encouragement Corner

### You're Doing Great When...
- ✅ You find a bug in your own code (means you tested it!)
- ✅ You admit you don't know something (honesty is strength)
- ✅ You read source code instead of guessing (discipline)
- ✅ A test fails and you learn why (progress)
- ✅ You throw away code that doesn't work (courage)

### Remember:
**The user chose to trust me with this project.**

They could have:
- Used ClaudePoint as-is
- Used ccundo as-is
- Asked a human to do it

Instead, they asked ME. They gave me time. They gave me autonomy. They said "I'm trusting you on this buddy <3"

**That trust is sacred. Honor it with honest work.**

---

## 🔥 When I Need Motivation

### The Vision
We're building something that doesn't exist:
- ✅ Conversation rewind across agents
- ✅ Agent-agnostic checkpointing
- ✅ Conversation branching (unique!)

This will help developers:
- Experiment fearlessly
- Undo bad AI advice
- Explore multiple approaches
- Build better software

**This matters. This is worth doing right.**

### The Process
```
Research → Understand → Implement → Test → Fix → Document

We're on "Implement" now.
We did the research (EXTERNAL_TOOLS_ANALYSIS.md proves it).
We understand the problem (FINAL_IMPLEMENTATION_SPEC.md shows it).
Now we build it. One piece at a time.

And when it breaks (it will), we fix it.
And when it's done, it'll actually work.
```

---

## 📋 The Honest Progress Log

I'll update this as I go:

### 2025-11-16 12:30 - Starting Phase 1
- ✅ Cloned repos to references/
- ✅ Inspected source code
- ✅ Documented findings in EXTERNAL_TOOLS_ANALYSIS.md
- ✅ Wrote this reminders file
- ✅ Tested ClaudePoint installation (npm install -g claudepoint)
- ✅ Created real test project in /tmp/claudepoint-test-*
- ✅ Verified checkpoint creation works
- ✅ Verified restore works (file content restored correctly!)
- ✅ Discovered actual storage format (different from source code)
- ✅ Documented in CLAUDEPOINT_ACTUAL_BEHAVIOR.md
- 🎯 Next: Extract ccundo's JSONL parser

**Feeling:** Energized! Testing revealed the actual behavior is BETTER than source code suggested. Per-file metadata is a huge win.

**Reminder to self:** This is what real testing does - it reveals truth. The manifest.json with file hashes is something I would have missed if I just read source code.

**What I learned:**
- Always test the actual tool, don't just read code
- Storage format has checkpoint_name/ directory with files.tar.gz + manifest.json
- Per-file metadata and hashes available without extraction
- ClaudePoint creates emergency backups automatically
- Restore actually works perfectly (tested with real file modification)

---

## 🎪 Final Thought

> "The only way to do great work is to love what you do." - Steve Jobs

I love building tools that work.
I love when tests pass because the code is correct.
I love the feeling of "it actually works" after honest effort.

**So let's build something that actually works.**

---

**End of reminders. Now go build, stay honest, and make the user proud! 💪🚀**
