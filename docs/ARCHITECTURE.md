# Mesh Architecture Documentation

## What is Mesh?

**Mesh** is an **architectural coherence layer for AI-generated codebases**. It analyzes code structure using AST parsing, builds dependency graphs, detects violations, and uses a local LLM to answer questions about code.

### Key Features
- Multi-language code analysis (26 languages via ast-grep)
- Dependency graph analysis (call graph, data flow, type dependencies)
- Local LLM for code questions (no cloud required)
- Git pre-commit hooks for enforcement
- MCP server for AI coding assistants

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐    │
│  │  CLI    │ │   MCP   │ │ Git     │ │ Python  │ │ Auth    │    │
│  │ Commands│ │ Server  │ │ Hooks   │ │   API   │ │ Login   │    │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘    │
└───────┼───────────┼───────────┼───────────┼───────────┼─────────┘
        │           │           │           │           │
┌───────▼───────────▼───────────▼───────────▼───────────▼─────────┐
│                      ANALYSIS ENGINE                               │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │    PARSER       │  │   BUILDER       │  │   ENFORCEMENT   │  │
│  │  (ast-grep)    │→ │  (Graphs)       │  │   (Checker)     │  │
│  │  26 languages  │  │  - Call graph   │  │  - Violations  │  │
│  │  Functions     │  │  - Data flow    │  │  - Hooks       │  │
│  │  Classes       │  │  - Type deps    │  │  - Reports     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│                              │                                     │
│  ┌───────────────────────────▼───────────────────────────────┐   │
│  │                     STORAGE (SQLite)                       │   │
│  │  - Nodes (functions, classes)                              │   │
│  │  - Edges (calls, data flow, type refs)                    │   │
│  │  - Analysis results                                       │   │
│  └───────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────┐
│                      LLM LAYER                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │  LOCAL LLM      │  │  EXPLAINER      │  │  DOWNLOADER     │  │
│  │  (llama.cpp)    │  │  (Prompts)      │  │  (HuggingFace) │  │
│  │  Qwen2.5-Coder  │  │  Code analysis   │  │  Auto-download │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Architecture

```
USER COMMAND
     │
     ▼
┌────────────┐
│  CLI Parse │
└─────┬──────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                        ANALYSIS PIPELINE                          │
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐ │
│  │  FILE     │───▶│  AST     │───▶│  GRAPH   │───▶│SQLite    │ │
│  │  FINDER   │    │  PARSE   │    │  BUILDER │    │  STORE   │ │
│  │           │    │ast-grep  │    │rustworkx │    │          │ │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘ │
│                        │                    │                   │
│                        │                    │                   │
│                  ┌─────▼─────┐        ┌──────▼──────┐          │
│                  │ FUNCTIONS  │        │   EDGES     │          │
│                  │ - name    │        │ - calls     │          │
│                  │ - file    │        │ - imports   │          │
│                  │ - line    │        │ - inherits  │          │
│                  │ - params  │        │ - type_refs │          │
│                  │ - returns │        │             │          │
│                  └───────────┘        └─────────────┘          │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     QUERY / ENFORCEMENT                           │
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────┐        │
│  │  LLM QUERY       │              │  VIOLATION CHECK  │        │
│  │  (mesh ask)      │              │  (mesh check)     │        │
│  │                   │              │                   │        │
│  │  1. Get context  │              │  1. Load graph    │        │
│  │  2. Build prompt │              │  2. Run rules    │        │
│  │  3. Local LLM    │              │  3. Report       │        │
│  │  4. Return ans   │              │                   │        │
│  └──────────────────┘              └──────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### 1. Core Layer (`mesh/core/`)

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `parser.py` | AST parsing | `UniversalParser`, `LANGUAGE_MAP` |
| `graph.py` | Graph data structure | `MeshGraph` (rustworkx-backed) |
| `storage.py` | SQLite persistence | `MeshStorage` |

**Parser Capabilities:**
- 26 programming languages
- Functions, classes, methods
- Imports and dependencies
- Decorators and annotations

**Graph Types:**
- `call` - Function call relationships
- `import` - Import statements
- `inherit` - Class inheritance
- `cfg` - Control flow

### 2. Analysis Layer (`mesh/analysis/`)

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `builder.py` | Orchestrates analysis | `AnalysisBuilder.run_full_analysis()` |
| `taint.py` | Security analysis | `TaintTracker`, sources, sinks |

**Builder Operations:**
1. Parse all supported files
2. Build call graph
3. Build data flow graph
4. Build type dependency graph
5. Detect violations

**Violation Detection:**
- Duplicate functions
- Naming inconsistencies
- Long dependency chains
- Circular dependencies
- Security taint (SQL injection, XSS, etc.)

### 3. LLM Layer (`mesh/llm/`)

| Module | Purpose |
|--------|---------|
| `local.py` | llama-cpp-python wrapper |
| `downloader.py` | Model download from HuggingFace |
| `explainer.py` | Code analysis prompts |

**Model: Qwen2.5-Coder-1.5B-Instruct**
- Size: ~1GB (Q4_K_M quantization)
- Context: 32K tokens (8K used)
- Trained on: 5.5T tokens of code
- Platform: llama-cpp-python (CPU)

**System Prompt:**
```
You are Mesh, an expert code analysis assistant.
You analyze codebases and provide clear explanations.
```

### 4. Enforcement Layer (`mesh/enforcement/`)

| Module | Purpose |
|--------|---------|
| `checker.py` | Run violation checks |
| `hook.py` | Git pre-commit hook |
| `reporter.py` | Generate violation reports |
| `history.py` | Track violation history |

### 5. MCP Server (`mesh/mcp/`)

Model Context Protocol server for AI coding assistants.

| Tool | Purpose |
|------|---------|
| `mesh_architecture` | Get codebase overview |
| `mesh_check` | Run violation check |
| `mesh_locate` | Find function definitions |
| `mesh_explain` | Explain a function |
| `mesh_dependencies` | Show function dependencies |
| `mesh_callers` | Find who calls a function |
| `mesh_impact` | Show downstream impact |

### 6. CLI Layer (`mesh/cli.py`)

| Command | Description |
|---------|-------------|
| `mesh init` | Initialize codebase analysis |
| `mesh check` | Check for violations |
| `mesh ask` | Ask questions (LLM-powered) |
| `mesh status` | Show analysis status |
| `mesh doctor` | Health check |
| `mesh serve` | Start MCP server |
| `mesh install-hook` | Install git hook |
| `mesh login` | GitHub authentication |
| `mesh upgrade` | Show pricing |

---

## Test Results Summary

| Repository | Files | Functions | Analysis Time | Languages |
|------------|-------|-----------|--------------|-----------|
| **FastAPI** | 408 | 1,112 | 8.4s | Python, JS |
| **Execa** | 184 | 938 | 0.9s | JS, TS |
| **Mesh (self)** | 17 | 229 | 2.2s | Python |

**Observations:**
- FastAPI: Large Python project, good call graph (5,978 edges)
- Execa: JS/TS project, few edges (modular design)
- Django/React: Too large for current implementation (>5min timeout)

**Recommendations:**
- Large repos (>500 files): Consider incremental analysis
- Timeout: Add progress indicator for long operations
- Multi-repo: Add workspace support

---

## User Flows

### Flow 1: First-Time Setup
```
1. pip install mesh-arch
2. mesh download-model      # Download LLM (~1GB)
3. cd my-project
4. mesh init                # Analyze codebase
5. mesh status             # Verify
```

### Flow 2: Daily Development
```
1. mesh check              # Check for violations
2. mesh ask "how does auth work?"  # Understand code
3. git commit              # Hook blocks violations
```

### Flow 3: Code Review
```
1. mesh doctor             # Health check
2. mesh check --report     # Full violation report
3. mesh ask "what changed?" # Explain changes
```

### Flow 4: AI Assistant Integration
```
1. mesh serve              # Start MCP server
2. Connect Cursor/Claude Code
3. Use MCP tools to query codebase
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| Parser | `ast-grep-py` | Multi-language AST parsing |
| Graph | `rustworkx` | High-performance graph operations |
| Storage | `SQLite` | Persistent storage |
| LLM | `llama-cpp-python` + `Qwen2.5-Coder-1.5B` | Local inference |
| CLI | `click` + `rich` | Command-line interface |
| Auth | `keyring` + GitHub PAT | Secure token storage |

---

## Performance Characteristics

| Operation | Time | Memory |
|-----------|------|--------|
| `mesh init` (100 files) | ~1s | ~50MB |
| `mesh init` (500 files) | ~5-10s | ~100MB |
| `mesh ask` (first run) | ~10s (model load) | ~2GB |
| `mesh ask` (subsequent) | ~2-3s | ~2GB |
| `mesh check` | <1s | ~50MB |

---

## Future Improvements

1. **Incremental Analysis** - Only re-analyze changed files
2. **Progress Indicators** - Show progress for large codebases
3. **Parallel Parsing** - Multi-threaded file processing
4. **GPU Acceleration** - Metal/CUDA for faster LLM
5. **Larger Context** - Use full 32K context window
6. **Better JS/TS Support** - Improve call graph for JavaScript
7. **Workspace Mode** - Analyze multiple repos

---

## File Structure

```
mesh/
├── __init__.py
├── cli.py                 # CLI commands
├── auth/                  # GitHub authentication
│   ├── __init__.py
│   ├── client.py         # GitHub API
│   ├── storage.py        # Keyring storage
│   └── tier.py           # Free/Pro detection
├── core/                  # Core analysis
│   ├── __init__.py
│   ├── graph.py         # MeshGraph (rustworkx)
│   ├── parser.py        # UniversalParser (ast-grep)
│   └── storage.py       # MeshStorage (SQLite)
├── analysis/              # Code analysis
│   ├── __init__.py
│   ├── builder.py       # AnalysisBuilder
│   └── taint.py         # TaintTracker
├── enforcement/           # Violation enforcement
│   ├── __init__.py
│   ├── checker.py       # ViolationChecker
│   ├── hook.py         # Git hook
│   ├── history.py       # Violation history
│   ├── ignorer.py       # Ignore patterns
│   └── reporter.py      # Report generation
├── llm/                   # Local LLM
│   ├── __init__.py
│   ├── local.py         # llama-cpp wrapper
│   ├── downloader.py    # HuggingFace download
│   └── explainer.py    # Code explainer
└── mcp/                   # MCP server
    ├── __init__.py
    ├── server.py        # MCPServer
    ├── tools.py         # Tool definitions
    └── summary.py       # Summary generator
```

---

## Conclusion

Mesh provides a complete, local-first solution for understanding and enforcing architectural patterns in AI-generated codebases. With its multi-language support, graph-based analysis, and local LLM capabilities, it offers:

- **Privacy**: All processing done locally
- **Speed**: Rustworkx for fast graph operations
- **Simplicity**: Single CLI command to analyze
- **Power**: Natural language queries about code
- **Enforcement**: Git hooks to block violations

The system is production-ready for small-to-medium projects and continues to improve with each iteration.
