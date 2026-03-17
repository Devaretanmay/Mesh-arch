# Mesh — Phase Run Guide
# How to run each phase in OpenCode with MiniMax-M2.5

═══════════════════════════════════════════════════
SETUP — DO ONCE
═══════════════════════════════════════════════════

Install OpenCode:
  curl -fsSL https://opencode.ai/install | bash

Set model:
  export MINIMAX_API_KEY=your_key_here

Create project:
  mkdir mesh && cd mesh
  cp mesh-phases/AGENTS.md ./AGENTS.md
  mkdir handoffs

Open OpenCode:
  opencode

═══════════════════════════════════════════════════
PHASE 1 — THE WATCHER (3 weeks)
═══════════════════════════════════════════════════

Paste this into OpenCode exactly:

---
Read mesh-phases/phase1-watcher.md completely.
Then read AGENTS.md.

You are building Mesh Phase 1: The Watcher.
Build everything specified in the phase prompt.
Follow all coding standards, write all tests,
complete all security checks.
Do not stop until every item in Definition of Done is checked.
Write handoffs/phase1_done.md when complete.
---

Gate before Phase 2:
  pytest tests/ --cov=mesh    # must be >90% coverage
  python tests/benchmark.py   # all targets must pass
  cat handoffs/phase1_done.md # must exist

═══════════════════════════════════════════════════
PHASE 2 — THE ENFORCER (3 weeks)
═══════════════════════════════════════════════════

Paste this into OpenCode exactly:

---
Read handoffs/phase1_done.md first.
Then read mesh-phases/phase2-enforcer.md completely.
Then read AGENTS.md.

You are building Mesh Phase 2: The Enforcer.
Phase 1 is complete. Build everything in the phase prompt.
Follow all coding standards, write all tests,
complete all security checks.
Do not stop until every item in Definition of Done is checked.
Write handoffs/phase2_done.md when complete.
---

Gate before Phase 3:
  # Manual test required:
  mesh install-hook
  # make a bad commit → must be blocked
  # make a clean commit → must pass
  pytest tests/ --cov=mesh    # >90% coverage

═══════════════════════════════════════════════════
PHASE 3 — THE ARCHITECT (4 weeks)
═══════════════════════════════════════════════════

Paste this into OpenCode exactly:

---
Read handoffs/phase1_done.md and handoffs/phase2_done.md first.
Then read mesh-phases/phase3-architect.md completely.
Then read AGENTS.md.

You are building Mesh Phase 3: The Architect.
Phases 1 and 2 are complete. Build everything in the phase prompt.
Follow all coding standards, write all tests,
complete all security checks.
Do not stop until every item in Definition of Done is checked.
Write handoffs/phase3_done.md when complete.
---

Gate before Phase 4:
  mesh serve &
  mesh setup-cursor
  # Open Cursor — mesh MCP tools must appear
  # Ask AI to add a feature — context must be injected
  pytest tests/ --cov=mesh    # >90% coverage

═══════════════════════════════════════════════════
PHASE 4 — THE COMPRESSOR (8 weeks)
═══════════════════════════════════════════════════

Paste this into OpenCode exactly:

---
Read ALL three handoff files first:
handoffs/phase1_done.md
handoffs/phase2_done.md  
handoffs/phase3_done.md

Then read mesh-phases/phase4-compressor.md completely.
Then read AGENTS.md.

You are building Mesh Phase 4: The Compressor.
Phases 1, 2, and 3 are complete.
This is the ML training phase.
Build the dataset pipeline, model architecture, and training loop.
Then train the model until validation F1 > 0.68.
Complete all security checks.
Write handoffs/phase4_done.md with final metrics.
---

Gate before Phase 5:
  python scripts/evaluate.py  # mean F1 must be >0.68
  # mesh serve must return 50-token embedding (not 200-token summary)
  # Phase 3 fallback must still work if model file removed

═══════════════════════════════════════════════════
PHASE 5 — THE NATIVE MODEL (6 weeks)
═══════════════════════════════════════════════════

Paste this into OpenCode exactly:

---
Read ALL four handoff files first:
handoffs/phase1_done.md
handoffs/phase2_done.md
handoffs/phase3_done.md
handoffs/phase4_done.md

Then read mesh-phases/phase5-native-model.md completely.
Then read AGENTS.md.

You are building Mesh Phase 5: The Native Model.
All previous phases are complete.
Build the fine-tuning dataset, run LoRA fine-tuning on
Qwen2.5-Coder-7B-Instruct, export to GGUF, and verify
coherence improvement >40% on the benchmark.
Do not ship if coherence improvement is under 40%.
Complete all security checks including model hash verification.
Write handoffs/phase5_done.md with final benchmark results.
---

Final verification — the product is done when:
  pip install -e .
  mesh init
  mesh serve &
  mesh model install
  mesh setup-cursor
  # Cursor uses local Mesh model
  # Ask AI to add a feature
  # It generates code with zero violations
  # It never creates duplicate functions
  # It follows naming conventions automatically

═══════════════════════════════════════════════════
QUICK REFERENCE — WHAT EACH PHASE OWNS
═══════════════════════════════════════════════════

Phase 1  mesh/analysis/     mesh/graph/       mesh/detection/
Phase 2  mesh/enforcement/  (adds to cli.py)
Phase 3  mesh/mcp/          (adds to cli.py)
Phase 4  mesh/model/        scripts/train.py
Phase 5  mesh/finetune/     mesh/local_model/

Never modify another phase's files unless explicitly told to integrate.
