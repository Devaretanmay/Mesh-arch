# Getting Started with Mesh v2.0

Mesh is an architectural coherence layer for AI-generated codebases. It analyzes your code, builds dependency graphs, and helps maintain architectural integrity across single repos or multi-repo workspaces.

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

For multi-repo workspaces (detects all git repos automatically):

```bash
cd /path/to/workspace
mesh init
```

This scans your codebase and builds dependency graphs. First run analyzes all files.

### 3. Check Your Code

```bash
mesh check
```

Detects architectural violations like circular dependencies, duplicate function names, and naming convention inconsistencies.

---

## Core Commands

| Command | Description |
|---------|-------------|
| `mesh init` | Analyze codebase(s) and build graphs |
| `mesh init --repo <name>` | Analyze specific repo only |
| `mesh status` | Show analysis stats |
| `mesh repos` | Show all repos and dependencies |
| `mesh context` | Show complete cross-repo graph |
| `mesh context --repo <name>` | Focus on specific repo |
| `mesh check` | Detect architectural violations |
| `mesh doctor` | Full system health check |
| `mesh ask "question"` | Query your codebase with AI |

---

## Multi-Repo Support

Mesh automatically detects git repositories in your workspace:

```bash
# Analyze all repos
mesh init

# Analyze specific repo
mesh init --repo backend

# View repo relationships
mesh repos

# See cross-repo dependencies
mesh context
```

### How It Works

1. **Detection**: Scans for folders with `.git` directories
2. **Analysis**: Analyzes each repo independently
3. **Cross-repo Detection**: Maps imports between repos
4. **Relationship Matrix**: Builds dependency graph across repos

Example output:
```
Repositories in Workspace
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━┓
┃ Name                   ┃ Type ┃ Functions ┃ Classes ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━┩
│ backend                │ git  │       234 │      45 │
│ frontend               │ git  │       156 │      28 │
└────────────────────────┴──────┴───────────┴─────────┘

Dependencies:
  backend depends on: shared-lib
  frontend depends on: backend, shared-lib
```

---

## Authentication

Login is optional but unlocks Pro features:

```bash
mesh login
```

Enter your GitHub Personal Access Token when prompted. Get one at: https://github.com/settings/tokens (scope: `read:user`)

**All features are free** - login just marks you as a Pro user.

---

## Features

### Code Analysis
Mesh parses 26+ languages using ast-grep:
- Python, TypeScript, JavaScript, Java, Go, Rust, C, C++, C#, Ruby, PHP, Swift, Kotlin, Scala, R, MATLAB, Julia, Lua, Perl, Haskell, OCaml, Elixir, Erlang, Clojure, F#, Dart

### Graph Types
- **Call Graph**: Function-to-function dependencies
- **Type Graph**: Class and interface relationships
- **Data Flow Graph**: How data moves through your codebase

### Multi-Repo Analysis
- Automatic repo detection
- Cross-repo import mapping
- Dependency matrix between repos

### Violation Detection
- Circular dependencies
- Duplicate function names
- Naming convention mismatches
- Sensitive data leaks (passwords → logs)

---

## AI-Powered Queries

To use `mesh ask`, download the local LLM:

```bash
mesh download-model
```

This downloads Qwen2.5-Coder-1.5B (~1GB). All inference runs locally on your machine.

```bash
# Query across all repos
mesh ask "how does authentication work?"

# Query specific repo
mesh ask "auth in backend" --repo backend
```

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

---

## Troubleshooting

### "mesh: command not found"
```bash
pip install mesh-arch
```

### Analysis is slow on large codebases
Mesh uses optimized parallel parsing. For multi-repo, use `--repo` to analyze specific repos.

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
