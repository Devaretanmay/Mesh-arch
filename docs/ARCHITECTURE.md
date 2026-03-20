# Mesh Architecture Documentation

## What is Mesh?

**Mesh** is an **architectural coherence layer for AI-generated codebases**. It analyzes code structure using AST parsing, builds dependency graphs, detects violations, and uses a local LLM to answer questions about code.

### Key Features
- Multi-language code analysis (26 languages via ast-grep)
- Multi-repo workspace support (detects and analyzes multiple git repos)
- Cross-repo dependency detection
- Dependency graph analysis (call graph, data flow, type dependencies)
- Local LLM for code questions (no cloud required)
- Git pre-commit hooks for enforcement
- MCP server for AI coding assistants

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                            │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐  │
│  │  CLI    │ │   MCP   │ │ Git     │ │ Python  │ │ Auth    │  │
│  │Commands │ │ Server  │ │ Hooks   │ │  API    │ │ Login   │  │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘  │
└───────┼───────────┼───────────┼───────────┼───────────┼────────┘
        │           │           │           │           │
┌───────▼───────────▼───────────▼───────────▼───────────▼────────┐
│                      ANALYSIS ENGINE                               │
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │    PARSER       │  │   BUILDER       │  │   ENFORCEMENT   │ │
│  │  (ast-grep)     │→ │  (Graphs)       │  │   (Checker)     │ │
│  │  26 languages   │  │  - Call graph    │  │  - Violations   │ │
│  │  Functions      │  │  - Data flow    │  │  - Hooks        │ │
│  │  Classes        │  │  - Type deps    │  │  - Reports      │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
│                              │                                   │
│  ┌───────────────────────────▼───────────────────────────────┐   │
│  │                     STORAGE (SQLite)                       │   │
│  │  - repos (workspace repos)                                 │   │
│  │  - nodes (functions, classes per repo)                     │   │
│  │  - edges (calls, data flow, cross-repo)                   │   │
│  │  - repo_relationships (cross-repo dependencies)            │   │
│  │  - repo_details (per-repo analysis)                        │   │
│  └───────────────────────────────────────────────────────────┘   │
│                              │                                   │
│  ┌───────────────────────────▼───────────────────────────────┐   │
│  │                  WORKSPACE LAYER                           │   │
│  │  - detect_repos() - Find git repos & submodules           │   │
│  │  - classify_import() - Cross-repo import detection        │   │
│  │  - build_repo_matrix() - Dependency relationships         │   │
│  └───────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
        │
┌───────▼─────────────────────────────────────────────────────────┐
│                      LLM LAYER                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │  LOCAL LLM      │  │  EXPLAINER      │  │  DOWNLOADER     │ │
│  │  (llama.cpp)    │  │  (Prompts)      │  │  (HuggingFace)  │ │
│  │  Qwen2.5-Coder  │  │  Multi-repo     │  │  Auto-download  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Multi-Repo Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    WORKSPACE STRUCTURE                            │
│                                                                  │
│  /workspace/                                                     │
│  ├── .mesh/                                                      │
│  │   ├── config.json       # Workspace configuration           │
│  │   ├── workspace.json    # Detected repos                    │
│  │   └── db/mesh.db        # Single SQLite database           │
│  ├── repo-a/ (git repo)                                           │
│  ├── repo-b/ (git repo)                                           │
│  └── repo-c/ (git submodule)                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Three Data Layers

| Layer | What | Storage |
|-------|------|--------|
| **1. Complete Context** | All symbols from all repos | `nodes`, `edges` tables |
| **2. Repo Relationships** | Which repo calls which | `repo_relationships` table |
| **3. Per-Repo Detail** | Isolated analysis per repo | `repo_details` table |

### Storage Schema

```sql
-- Workspace repos
CREATE TABLE repos (
    id TEXT PRIMARY KEY,
    name TEXT,
    path TEXT,
    type TEXT,  -- 'git' or 'submodule'
    last_analyzed TIMESTAMP
);

-- All nodes (layer 1)
CREATE TABLE nodes (
    id TEXT,
    repo_id TEXT,  -- Which repo it belongs to
    type TEXT,
    file_path TEXT,
    data JSON,
    PRIMARY KEY (id, repo_id)
);

-- All edges including cross-repo (layer 1)
CREATE TABLE edges (
    from_id TEXT,
    to_id TEXT,
    from_repo TEXT,  -- Track cross-repo edges
    to_repo TEXT,
    type TEXT,
    data JSON
);

-- Repo dependency matrix (layer 2)
CREATE TABLE repo_relationships (
    source_repo TEXT,
    target_repo TEXT,
    relationship_type TEXT,
    count INTEGER
);

-- Per-repo detail (layer 3)
CREATE TABLE repo_details (
    repo_id TEXT PRIMARY KEY,
    functions JSON,
    classes JSON,
    violations JSON,
    metrics JSON
);
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
│                  │ - params  │        │ - cross-repo│          │
│                  └───────────┘        └─────────────┘          │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     MULTI-REPO LAYER                             │
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │  WORKSPACE        │              │  CROSS-REPO      │         │
│  │  DETECTION        │              │  IMPORTS         │         │
│  │                   │              │                   │         │
│  │  1. detect_repos │              │  1. classify_imp │         │
│  │  2. git/submod   │              │  2. map to repos │         │
│  │                   │              │  3. build_matrix │         │
│  └──────────────────┘              └──────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     QUERY / ENFORCEMENT                           │
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────┐         │
│  │  LLM QUERY       │              │  VIOLATION CHECK  │         │
│  │  (mesh ask)      │              │  (mesh check)    │         │
│  │                   │              │                   │         │
│  │  1. Get context  │              │  1. Load graph   │         │
│  │  2. Build prompt │              │  2. Run rules    │         │
│  │  3. Local LLM    │              │  3. Report       │         │
│  │  4. Return ans   │              │                   │         │
│  └──────────────────┘              └──────────────────┘         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Breakdown

### 1. Core Layer (`mesh/core/`)

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `parser.py` | AST parsing | `UniversalParser`, `LANGUAGE_MAP` |
| `graph.py` | Graph data structure | `MeshGraph` (rustworkx-backed) |
| `storage.py` | SQLite persistence | `MeshStorage` (multi-repo schema) |
| `workspace.py` | Repo detection | `detect_repos()`, `classify_import()` |

**Parser Capabilities:**
- 26 programming languages
- Functions, classes, methods
- Imports and dependencies
- Decorators and annotations

**Graph Types:**
- `call` - Function call relationships
- `type` - Class inheritance
- `dataflow` - Data flow analysis
- `cross_repo_import` - Inter-repo imports

### 2. Analysis Layer (`mesh/analysis/`)

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `builder.py` | Single-repo analysis | `AnalysisBuilder.run_full_analysis()` |
| `workspace.py` | Multi-repo analysis | `WorkspaceAnalysisBuilder.analyze_all_repos()` |
| `taint.py` | Security analysis | `TaintTracker`, sources, sinks |

**Builder Operations:**
1. Parse all supported files
2. Build call graph
3. Build data flow graph
4. Build type dependency graph
5. Detect violations

**Workspace Operations:**
1. Detect all git repos & submodules
2. Analyze each repo independently
3. Detect cross-repo imports
4. Build repo dependency matrix

### 3. LLM Layer (`mesh/llm/`)

| Module | Purpose |
|--------|---------|
| `local.py` | llama-cpp-python wrapper |
| `downloader.py` | Model download from HuggingFace |
| `explainer.py` | Multi-repo code analysis prompts |

**Model: Qwen2.5-Coder-1.5B-Instruct**
- Size: ~1GB (Q4_K_M quantization)
- Context: 32K tokens (8K used)
- Trained on: 5.5T tokens of code
- Platform: llama-cpp-python (CPU/GPU)

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

### 6. Auth Layer (`mesh/auth/`)

| Module | Purpose |
|--------|---------|
| `client.py` | GitHub API client |
| `storage.py` | Keyring token storage |
| `tier.py` | Free/Pro detection |

### 7. CLI Layer (`mesh/cli.py`)

| Command | Description |
|---------|-------------|
| `mesh init` | Analyze codebase(s) |
| `mesh init --repo <name>` | Analyze specific repo |
| `mesh status` | Show analysis stats |
| `mesh repos` | Show repo relationships |
| `mesh context` | Show cross-repo graph |
| `mesh check` | Check for violations |
| `mesh ask "question"` | AI-powered query |
| `mesh ask --repo <name>` | Query specific repo |
| `mesh doctor` | Health check |
| `mesh serve` | Start MCP server |
| `mesh install-hook` | Install git hook |
| `mesh login` | GitHub authentication |
| `mesh download-model` | Download LLM model |

---

## Test Results Summary

| Repository | Repos | Files | Functions | Analysis Time |
|------------|-------|-------|-----------|---------------|
| **Trace Workspace** | 4 | 351 | 1,663 | ~2s |
| **FastAPI** | 1 | 408 | 1,112 | 8.4s |
| **Execa** | 1 | 184 | 938 | 0.9s |
| **Mesh (self)** | 1 | 35 | 501 | 1.2s |

**Trace Workspace Dependencies:**
- trace-be-adminv3 → trace-be-apiservicev3
- trace-be-auto-email-servicev3 → trace-be-apiservicev3, trace-be-reportv3
- trace-be-reportv3 → trace-be-apiservicev3

---

## User Flows

### Flow 1: First-Time Setup
```
1. pip install mesh-arch
2. mesh download-model      # Download LLM (~1GB)
3. cd my-project
4. mesh init                # Analyze codebase
5. mesh status              # Verify
```

### Flow 2: Multi-Repo Workspace
```
1. cd /path/to/workspace
2. mesh init                 # Detects all repos automatically
3. mesh repos                # See all repos & dependencies
4. mesh init --repo backend  # Re-analyze specific repo
```

### Flow 3: Daily Development
```
1. mesh check              # Check for violations
2. mesh ask "how does auth work?"  # Understand code
3. git commit              # Hook blocks violations
```

### Flow 4: Cross-Repo Analysis
```
1. mesh context            # See full cross-repo graph
2. mesh context --repo api  # Focus on specific repo
3. mesh ask "api calls" --repo api  # Query with context
```

### Flow 5: AI Assistant Integration
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
| Storage | `SQLite` | Persistent storage (WAL mode) |
| LLM | `llama-cpp-python` + `Qwen2.5-Coder-1.5B` | Local inference |
| CLI | `click` + `rich` | Command-line interface |
| Auth | `keyring` + GitHub PAT | Secure token storage |

---

## Performance Characteristics

| Operation | Time | Memory |
|-----------|------|--------|
| `mesh init` (100 files) | ~1s | ~50MB |
| `mesh init` (500 files) | ~5-10s | ~100MB |
| `mesh init` (4 repos, 350 files) | ~2s | ~150MB |
| `mesh ask` (first run) | ~10s (model load) | ~2GB |
| `mesh ask` (subsequent) | ~2-3s | ~2GB |
| `mesh check` | <1s | ~50MB |

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
│   ├── storage.py       # MeshStorage (SQLite, multi-repo)
│   └── workspace.py     # Repo detection & classification
├── analysis/              # Code analysis
│   ├── __init__.py
│   ├── builder.py       # AnalysisBuilder (single repo)
│   ├── workspace.py     # WorkspaceAnalysisBuilder (multi-repo)
│   └── taint.py         # TaintTracker
├── enforcement/           # Violation enforcement
│   ├── __init__.py
│   ├── checker.py       # ViolationChecker
│   ├── hook.py          # Git hook
│   ├── history.py        # Violation history
│   ├── ignorer.py        # Ignore patterns
│   └── reporter.py       # Report generation
├── llm/                   # Local LLM
│   ├── __init__.py
│   ├── local.py          # llama-cpp wrapper
│   ├── downloader.py     # HuggingFace download
│   └── explainer.py      # Multi-repo code explainer
└── mcp/                   # MCP server
    ├── __init__.py
    ├── server.py         # MCPServer
    ├── tools.py          # Tool definitions
    └── summary.py         # Summary generator
```

---

## Conclusion

Mesh v2.0 provides a complete, local-first solution for understanding and enforcing architectural patterns in codebases. With multi-repo support, graph-based analysis, and local LLM capabilities:

- **Privacy**: All processing done locally
- **Speed**: Rustworkx for fast graph operations
- **Multi-Repo**: Automatic repo detection and cross-repo dependency mapping
- **Simplicity**: Single CLI command to analyze single repos or entire workspaces
- **Power**: Natural language queries about code
- **Enforcement**: Git hooks to block violations

The system handles both single repos and multi-repo workspaces, with automatic detection and cross-repo import analysis.
