# Getting Started with Mesh v2.0

Mesh is an architectural coherence layer for AI-generated codebases. It analyzes your code, builds dependency graphs, and helps maintain architectural integrity.

## Quick Start

### 1. Install Mesh

```bash
pip install mesh-arch
```

### 2. Initialize Your Codebase

```bash
cd your-project
mesh init
```

This scans your codebase and builds dependency graphs. First run analyzes all files; subsequent runs are incremental.

### 3. Check Your Code

```bash
mesh check
```

Detects architectural violations like circular dependencies, duplicate function names, and naming convention inconsistencies.

---

## Core Commands

| Command | Description |
|---------|-------------|
| `mesh init` | Analyze codebase and build graphs |
| `mesh status` | Show analysis stats and auth status |
| `mesh check` | Detect architectural violations |
| `mesh doctor` | Full system health check |
| `mesh ask "question"` | Query your codebase (Pro) |

---

## Authentication & Tiers

Mesh has three tiers:

| Tier | Price | Features |
|------|-------|----------|
| **Free** | $0 | Code analysis, violation checking |
| **Personal Pro** | $5/mo | AI queries, summaries |
| **Organization Pro** | $10/mo | Team features, admin controls |

### Logging In

```bash
mesh login
```

Enter your GitHub Personal Access Token when prompted. Get one at: https://github.com/settings/tokens (scope: `read:user`)

Mesh automatically detects:
- No login → Free tier
- Personal GitHub → Personal Pro
- Organization GitHub → must upgrade to Org Pro

---

## Features

### Code Analysis
Mesh parses 26+ languages using ast-grep:
- Python, TypeScript, JavaScript, Java, Go, Rust, C, C++, C#, Ruby, PHP, Swift, Kotlin, Scala, R, MATLAB, Julia, Lua, Perl, Haskell, OCaml, Elixir, Erlang, Clojure, F#, Dart

### Graph Types
- **Call Graph**: Function-to-function dependencies
- **Type Graph**: Class and interface relationships
- **Data Flow Graph**: How data moves through your codebase

### Violation Detection
- Circular dependencies
- Duplicate function names
- Naming convention mismatches
- Sensitive data leaks (passwords → logs)

---

## Optional: AI-Powered Queries

To use `mesh ask`, download the local LLM:

```bash
mesh download-model
```

This downloads Qwen2.5-Coder-1.5B (~1GB). All inference runs locally on your machine.

---

## Git Pre-Commit Hook

Automatically check code before commits:

```bash
mesh install-hook
```

---

## MCP Server

Start the MCP server for AI assistant integration (Cursor, Claude Code):

```bash
mesh serve
```

Requires Pro tier.

---

## Troubleshooting

### "mesh: command not found"
```bash
pip install mesh-arch
```

### Analysis is slow on large codebases
Mesh uses incremental analysis. Run `mesh init` once, then `mesh check` for subsequent runs.

### Model download fails
```bash
mesh download-model
```

Manually download from HuggingFace if needed: https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF

### Tests fail
```bash
pytest tests/ -v
```

---

## Uninstall

```bash
pip uninstall mesh-arch
rm -rf .mesh  # removes analysis database
```
