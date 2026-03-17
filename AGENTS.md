# Mesh — Build Rules for OpenCode + MiniMax-M2.5

## What We're Building
Mesh encodes your entire codebase architecture into 50 tokens — injected
silently into every AI coding session so the model knows your full system
before generating a single line.

## Model
MiniMax-M2.5 via OpenCode. This model writes spec before code.
Always read the full phase prompt before writing anything.

## Non-Negotiable Rules

1. Read the current phase prompt completely before writing any code
2. Read all handoffs/ files from previous phases before starting
3. Run tests after every file you write: pytest tests/ -x -q
4. Never touch files outside your current phase scope
5. Never make network calls except where explicitly specified
6. Type hints on every function. No exceptions.
7. Docstrings on every public method — explain WHY not what
8. Run security checks before marking any phase done
9. Write handoffs/<phase>_done.md when phase is complete
10. Performance benchmarks must pass before marking done

## Current Phase
Check which phase prompt file you have been given.
Only build what that phase specifies.

## Phase Dependencies
Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
Never skip a phase. Never build ahead.

## Test Command
```bash
pytest tests/ -v --cov=mesh --cov-report=term-missing
```

## Lint Commands
```bash
black mesh/ tests/
mypy mesh/
ruff check mesh/
```

## Benchmark Command
```bash
python tests/benchmark.py
```

## Handoff Format
See bottom of each phase prompt for exact handoff format.
Write it to handoffs/<phase_name>_done.md when done.

## Security First
Every phase has a security review section.
Complete every item before marking phase done.
A security bug is worse than a missing feature.

## Definition of Done
Phase is ONLY done when every checkbox in the phase prompt
"Definition of Done" section is checked.
Do not mark done early. Do not skip checklist items.
