# Mesh

<p align="center">
  <img src="https://img.shields.io/pypi/v/mesh-arch?style=flat&label=PyPI&color=4F46E5" alt="PyPI Version">
  <img src="https://img.shields.io/pypi/l/mesh-arch?style=flat&color=10B981" alt="License">
  <img src="https://img.shields.io/pypi/pyversions/mesh-arch?style=flat&color=F59E0B" alt="Python Versions">
  <img src="https://img.shields.io/github/license/anomalyco/mesh-arch?style=flat&color=6366F1" alt="License">
</p>

**Architectural coherence layer for AI-generated codebases**

Mesh ensures AI-generated code follows your codebase's architecture. It detects duplicate functions, circular dependencies, naming violations, data flow issues, and security vulnerabilities before they enter your codebase.

---

## Why Mesh?

AI coding assistants (Cursor, Claude Code, GitHub Copilot) are powerful but don't know your codebase's architecture. They generate code that:
- Creates duplicate functions
- Introduces circular dependencies  
- Violates naming conventions
- Causes security vulnerabilities (SQL injection, XSS, etc.)

**Mesh fixes this** by injecting your codebase's architecture INTO every AI coding session.

---

## Quickstart

### Step 1 — Install

```bash
pip install mesh-ai
```

### Step 2 — Setup

```bash
cd your-project
mesh setup
```

The setup wizard will:
- Analyze your codebase
- Detect Ollama (install guide if needed)
- Show installed AI models with compatibility ratings
- Register Mesh with Cursor and Claude Code

### Step 3 — Code with AI

Open Cursor or Claude Code. Every AI coding session now receives your architectural context automatically.

---

## Features

### 🕸️ Multi-Graph Analysis

Mesh builds **4 interconnected graphs**:

| Graph | Description |
|-------|-------------|
| **Call Graph** | Functions, classes, calls, imports, branches, loops |
| **Data Flow Graph** | Parameter → return value flows across functions |
| **Type Dependency Graph** | Class inheritance, type usage |
| **Control Flow** | Branches (if/else), loops (for/while), exceptions, async |

### 🛡️ Security Analysis (Taint Tracking)

13 vulnerability categories detected:

| Category | Severity | Examples |
|----------|----------|----------|
| SQL Injection | 🔴 Error | `execute(user_input)` |
| Code Injection | 🔴 Error | `eval(user_data)` |
| Command Injection | 🔴 Error | `os.system(user_cmd)` |
| SSRF | 🔴 Error | `requests.get(url)` |
| XXE | 🔴 Error | `xml.etree.parse(xml)` |
| Deserialization | 🔴 Error | `pickle.loads(data)` |
| XSS | 🟡 Warning | `render(user_content)` |
| Path Traversal | 🟡 Warning | `open(user_path)` |
| Weak Crypto | 🔵 Info | `hashlib.md5(data)` |
| Insecure Random | 🔵 Info | `random.random()` |

### 🔍 Violation Detectors

- **Duplicates** — Duplicate function definitions across files
- **Circular Calls** — A → B → C → A cycles
- **Naming Violations** — snake_case, camelCase, PascalCase enforcement
- **Data Flow Issues** — Long chains, sensitive data leaks, missing validation

### 🤖 MCP Tools (7 tools)

| Tool | Description |
|------|-------------|
| `mesh_architecture` | Get architectural summary |
| `mesh_check` | Check code for violations |
| `mesh_locate` | Fuzzy search functions/classes |
| `mesh_explain` | Ask natural language questions |
| `mesh_dependencies` | Show what a function calls |
| `mesh_callers` | Find who calls a function |
| `mesh_impact` | Show downstream impact + risk |

---

## Commands

```bash
mesh init              # Analyze codebase, build graphs
mesh setup             # Interactive setup wizard
mesh serve             # Start MCP server
mesh check             # Check for violations
mesh doctor            # Health check
mesh status            # Show statistics
mesh ask <question>   # Ask about codebase
mesh model list        # List Ollama models
mesh install-hook      # Install git pre-commit hook
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER / AI TOOL                          │
│              (Cursor, Claude Code, VS Code, CLI)                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CLI (9 commands)                              │
│  init │ setup │ serve │ check │ doctor │ status │ ask │ model  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Server (7 tools)                         │
│  architecture │ check │ locate │ explain │ dependencies │ etc.  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ENFORCEMENT LAYER                           │
│   Violation Checker │ Git Hook │ CI/CD │ Storage (SQLite)       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     ANALYSIS LAYER                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │            UniversalParser (25 languages)                  │ │
│  │  Python, TypeScript, Java, Go, Rust, C++, etc.           │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                 AnalysisBuilder                             │ │
│  │  Call Graph + Data Flow + Type Graph + Control Flow         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                             │                                   │
│                             ▼                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │              Violation Detectors                            │ │
│  │  duplicates │ circular │ naming │ data_flow │ taint        │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Comparison

| Feature | Mesh | SonarQube | DeepSource | Copilot |
|---------|------|-----------|------------|---------|
| Build-time analysis | ✅ | ✅ | ✅ | ❌ |
| AI context injection | ✅ | ❌ | ❌ | ✅ |
| Taint tracking (13 types) | ✅ | ✅ | ✅ | Via CodeQL |
| Call graph | ✅ | ✅ | ✅ | Limited |
| Data flow | ✅ | ✅ | ✅ | Limited |
| Control flow | ✅ | ✅ | ✅ | ❌ |
| MCP integration | ✅ | ❌ | ❌ | ❌ |
| Local/Self-hosted | ✅ | ❌ | ❌ | ❌ |

---

## Requirements

- **Python** 3.10+
- **Ollama** (for AI model inference)
- **Git** (for pre-commit hooks)

---

## Installation

### Basic

```bash
pip install mesh-ai
```

### With Development Tools

```bash
pip install -e ".[dev]"
```

---

## Configuration

Mesh stores configuration in `.mesh/config.json`:

```json
{
  "model": "qwen3.5:9b",
  "ignored_patterns": ["test_*.py", "**/migrations/**"],
  "taint_tracking": {
    "sources": ["custom_source"],
    "sinks": {
      "sql": ["custom_query"],
      "xss": ["custom_render"]
    },
    "sanitizers": ["custom_validate"]
  }
}
```

---

## Development

```bash
# Run tests
pytest tests/ -v

# Format
black mesh/ tests/

# Lint
ruff check mesh/

# Type check
mypy mesh/
```

---

## License

MIT

---

## Links

- **PyPI**: https://pypi.org/project/mesh-arch/
- **GitHub**: https://github.com/anomalyco/mesh-arch
- **Documentation**: (add your docs URL)
- **Issues**: (add your issues URL)

## License

MIT License - see [LICENSE](LICENSE) file for details.
