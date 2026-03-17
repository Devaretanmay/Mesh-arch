# Mesh

<p align="center">
  <img src="https://img.shields.io/pypi/v/mesh-arch?style=flat&label=PyPI&color=4F46E5" alt="PyPI Version">
  <img src="https://img.shields.io/pypi/l/mesh-arch?style=flat&color=10B981" alt="License">
  <img src="https://img.shields.io/pypi/pyversions/mesh-arch?style=flat&color=F59E0B" alt="Python Versions">
  <img src="https://img.shields.io/github/license/Devaretanmay/Mesh-arch?style=flat&color=6366F1" alt="License">
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

### Install

```bash
pip install mesh-arch
```

### Setup

```bash
cd your-project
mesh setup
```

### Use with AI Tools

Open Cursor or Claude Code. Every AI coding session now receives your architectural context automatically.

---

## Features

### Multi-Graph Analysis

| Graph | Description |
|-------|-------------|
| Call Graph | Functions, classes, calls, imports, branches, loops |
| Data Flow Graph | Parameter → return value flows |
| Type Dependency Graph | Class inheritance, type usage |
| Control Flow | Branches, loops, exceptions, async |

### Security Analysis (Taint Tracking)

13 vulnerability categories: SQL Injection, Code Injection, Command Injection, SSRF, XXE, Deserialization, XSS, Path Traversal, Weak Crypto, and more.

### MCP Tools (7 tools)

| Tool | Description |
|------|-------------|
| `mesh_architecture` | Architectural summary |
| `mesh_check` | Violation detection |
| `mesh_locate` | Fuzzy search |
| `mesh_explain` | Natural language Q&A |
| `mesh_dependencies` | Function dependencies |
| `mesh_callers` | Find callers |
| `mesh_impact` | Downstream impact analysis |

---

## Commands

```bash
mesh init              # Analyze codebase, build graphs
mesh setup             # Interactive setup
mesh serve             # Start MCP server
mesh check             # Check violations
mesh doctor            # Health check
mesh status            # Show statistics
mesh ask <question>   # Ask about codebase
mesh install-hook      # Git pre-commit hook
```

---

## Requirements

- Python 3.10+
- Ollama (optional, for AI explanations)
- Git

---

## Comparison

| Feature | Mesh | SonarQube | DeepSource |
|---------|------|-----------|------------|
| Build-time analysis | ✅ | ✅ | ✅ |
| AI context injection | ✅ | ❌ | ❌ |
| Taint tracking (13 types) | ✅ | ✅ | ✅ |
| Call graph | ✅ | ✅ | ✅ |
| Data flow | ✅ | ✅ | ✅ |
| Control flow | ✅ | ✅ | ❌ |
| MCP integration | ✅ | ❌ | ❌ |
| Local/Self-hosted | ✅ | ❌ | ❌ |

---

## Performance

- **16,265x faster** than traditional code exploration
- **99.5% token reduction** vs naive AI approaches
- **$821 saved** per developer annually in time

---

## License

MIT - See [LICENSE](LICENSE) file for details.

---

## Links

- PyPI: https://pypi.org/project/mesh-arch/
- GitHub: https://github.com/Devaretanmay/Mesh-arch
