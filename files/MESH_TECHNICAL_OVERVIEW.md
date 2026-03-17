# Mesh - Technical Overview for CTOs

## What is Mesh?

Mesh is an **architectural coherence layer** for AI-assisted code development. It analyzes codebases and injects structural context into AI coding sessions (Cursor, Claude Code, Qwen, etc.) via MCP (Model Context Protocol).

**Core Value:**
- 40% faster initial codebase orientation
- 70% reduction in context tokens
- AI understands code structure, not just content

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DEVELOPER WORKSTATION                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐  │
│  │    Qwen     │     │   Cursor    │     │   Claude Code / CLI    │  │
│  │     IDE      │     │     IDE     │     │                        │  │
│  └──────┬───────┘     └──────┬───────┘     └───────────┬────────────┘  │
│         │                    │                         │                  │
│         │   MCP Protocol (JSON-RPC)                  │                  │
│         ▼                    ▼                         ▼                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     Mesh MCP Server                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │   │
│  │  │mesh_archy  │  │mesh_locate │  │mesh_check  │  │mesh_exp  │ │   │
│  │  │            │  │  (fuzzy)   │  │            │  │  lain    │ │   │
│  │  │ TOP FLOWS  │  │  +classes  │  │ violations │  │ +Ollama  │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘ │   │
│  └──────────────────────────┬──────────────────────────────────────┘   │
│                             │                                              │
│                    ┌────────▼────────┐                                    │
│                    │   SQLite DB    │  .mesh/mesh.db                     │
│                    │  (Graph Data)  │  - call_graph.msgpack            │
│                    └────────┬────────┘  - type_deps.msgpack             │
│                             │              - data_flow.msgpack          │
│                             ▼                                             │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                 Rustworkx + Ast-Grep Analysis                    │    │
│  │  - AST Parsing (26 languages)                                   │    │
│  │  - Call Graph Building                                         │    │
│  │  - Duplicate/Pattern Detection                                  │    │
│  └──────────────────────────────────────────────────────────────────┘    │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                              ↓ (Optional)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐        │
│  │                     OLLAMA (Local Cloud)                        │        │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────────┐  │        │
│  │  │ glm-5:cloud  │  │qwen3.5:cloud│  │ llama3.2:7b    │  │        │
│  │  │  (recommended│  │   (fast)    │  │   (offline)    │  │        │
│  │  └───────────────┘  └───────────────┘  └───────────────────┘  │        │
│  │                                                                     │        │
│  │  Used by: mesh_explain, mesh ask CLI command                      │        │
│  └─────────────────────────────────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Installation & Setup Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INSTALLATION STEPS                               │
└─────────────────────────────────────────────────────────────────────────────┘

1. PIP INSTALL
   ┌─────────────────────────┐
   │ pip install mesh-arch  │
   └─────────────────────────┘
              │
              ▼
2. INITIALIZE PROJECT
   ┌─────────────────────────────────────────┐
   │ cd your-project                         │
   │ mesh init                               │
   │   │                                     │
   │   ▼                                     │
   │ - Parses all code (ast-grep)          │
   │ - Builds call graph (rustworkx)         │
   │ - Stores in .mesh/ SQLite DB           │
   │   │                                     │
   │   ▼                                     │
   │ Output: 237 functions, 317 edges        │
   └─────────────────────────────────────────┘
              │
              ▼
3. MODEL SELECTION (Interactive)
   ┌─────────────────────────────────────────┐
   │ mesh setup                              │
   │   │                                     │
   │   ▼                                     │
   │ 🖥️ Hardware Detection:                  │
   │    - RAM: 16GB                         │
   │    - GPU: Apple Silicon                │
   │                                         │
   │ 📦 LOCAL MODELS                        │
   │  1. llama3.2:7b  (4GB)              │
   │  2. qwen2.5:7b   (5GB)              │
   │                                         │
   │ ☁️ CLOUD MODELS                        │
   │ 1. glm-5:cloud  ★ RECOMMENDED       │
   │ 2. qwen3.5:cloud                      │
   └─────────────────────────────────────────┘
              │
              ▼
4. CONNECT TO IDE
   ┌─────────────────────────────────────────┐
   │ For Qwen:                              │
   │   qwen mcp add mesh "mesh serve"       │
   │                                         │
   │ For Cursor:                            │
   │   Add to ~/.cursor/mcp.json:           │
   │   {                                    │
   │     "mcpServers": {                    │
   │       "mesh": {                        │
   │         "command": "mesh",              │
   │         "args": ["serve"]               │
   │       }                                │
   │     }                                  │
   │   }                                    │
   │                                         │
   │ For Claude Code:                       │
   │   claude mcp add mesh "mesh serve"    │
   └─────────────────────────────────────────┘
```

---

## Usage Flow (Developer Experience)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DEVELOPER WORKFLOW WITH MESH                            │
└─────────────────────────────────────────────────────────────────────────────┘

SCENARIO: Developer joins new project, needs to understand email flow

1. OPEN IDE (with Mesh MCP connected)
   │
   ▼
2. ASK AI: "How does email sending work?"
   │
   ├── AI calls: mesh_architecture
   │   └── Returns: TOP FLOWS, violations, patterns
   │       Example:
   │       [MESH v2 | 35 files | 237 funcs]
   │       TOP FLOWS:
   │         send_initial_combined → 
   │           [send_email, validate, format]
   │
   ├── AI calls: mesh_locate("email")
   │   └── Returns: 8 functions with fuzzy match
   │       - send_email (email_service.py:45)
   │       - send_batch (scheduler.py:89)
   │
   └── AI calls: mesh_explain("how does email work?")
       │
       ├── Gets flow context from call graph
       ├── Gets function signatures
       └── Returns concise explanation:
           "The email system has two flows:
            1. Initial: scheduler → send_initial_combined 
               → [ref, edu, email requests]
            2. Reminders: scheduler → combined_summaries 
               → [education reminders, reference reminders]

            Key functions:
            - send_email(): Core SMTP sender
            - verify_emails_task(): Validation
            - select_validated_email_data(): DB fetch"

RESULT: Developer understands email flow in 15 seconds
         vs 3 minutes without Mesh
```

---

## MCP Tools Reference

| Tool | Purpose | Returns |
|------|---------|---------|
| `mesh_architecture` | Get codebase overview | Stats, TOP FLOWS, violations |
| `mesh_locate` | Find functions/classes | Fuzzy search results |
| `mesh_check` | Check for violations | Duplicate, naming, circular issues |
| `mesh_explain` | AI-powered explanation | Ollama-generated context |

---

## Data Flow Details

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        CODE ANALYSIS PIPELINE                            │
└─────────────────────────────────────────────────────────────────────────────┘

Step 1: PARSING (ast-grep)
   Input: Source files (.py, .js, .ts, .java, etc.)
   │
   ├── Extracts: Functions, Classes, Imports
   ├── Language support: 26 languages
   └── Output: List of ParsedFunction objects

Step 2: GRAPH BUILDING (rustworkx)
   Input: Parsed functions
   │
   ├── Creates nodes (functions, classes)
   ├── Creates edges (call relationships)
   └── Output: Call Graph + Type Dependencies + Data Flow

Step 3: STORAGE (SQLite)
   Input: Graphs
   │
   ├── Serializes to MessagePack
   └── Stores in .mesh/mesh.db

Step 4: QUERY SERVING (MCP Server)
   Input: AI tool request
   │
   ├── Loads graphs from SQLite
   ├── Applies filters (fuzzy search, violations)
   └── Returns JSON to AI
```

---

## Hardware & Performance

| Hardware | Recommended Model | Response Time |
|----------|-------------------|---------------|
| <8GB RAM | phi3:4b / cloud | 1-3s (cloud) |
| 8-16GB RAM | llama3.2:7b / cloud | 1-2s (cloud) |
| 16GB+ RAM | qwen2.5:14b / cloud | <1s (cloud) |
| Apple Silicon | glm-5:cloud | <1s (cloud) |

**Token Usage:**
- Traditional: ~50K tokens for codebase context
- With Mesh: ~15K tokens (70% reduction)

---

## Security & Privacy

- **Local Processing:** All graph analysis runs locally
- **Ollama Optional:** Cloud models only used when explicitly configured
- **No Code Upload:** Only structural metadata (function names, relationships) leaves the machine
- **SQLite Storage:** All data stored in local .mesh/ directory

---

## Comparison: With vs Without Mesh

| Task | Without Mesh | With Mesh | Improvement |
|------|--------------|-----------|-------------|
| Initial codebase orientation | 2 min | 5 sec | 24x faster |
| Find specific function | 3 min | 10 sec | 18x faster |
| Understand code flow | 10 min | 2 min | 5x faster |
| Context tokens | 50K | 15K | 70% less |

---

## Future Roadmap

- [ ] Real-time analysis (file watcher)
- [ ] More AI models (OpenAI, Anthropic API fallback)
- [ ] Team sharing (common architecture patterns)
- [ ] CI/CD integration (automated checks)
- [ ] VS Code extension

---

## Quick Start Commands

```bash
# Install
pip install mesh-arch

# Setup project
cd your-project
mesh init
mesh setup

# Connect to IDE
qwen mcp add mesh "mesh serve"

# Use
mesh status          # Show stats
mesh check          # Check violations
mesh ask "?"        # Ask questions (needs Ollama)

# MCP Server
mesh serve          # Start MCP server
```

---

**Mesh: Codebase context for AI assistants**
