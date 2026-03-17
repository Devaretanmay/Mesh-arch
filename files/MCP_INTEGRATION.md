# Mesh MCP Integration Guide

Mesh provides an MCP (Model Context Protocol) server that integrates with AI coding tools to provide architectural context automatically.

## Quick Start

```bash
# Install Mesh
pip install mesh-arch

# Initialize analysis
mesh init

# Add to your AI tool
```

---

## Integration with AI Tools

### 1. Qwen Code

```bash
# Add MCP server
qwen mcp add mesh "mesh serve"

# Verify it's added
qwen mcp list

# Use with --allowed flag
qwen --allowed-mcp-server-names mesh -p "How does auth work in this codebase?"
```

**Configuration file location:** `~/.qwen/config.json`

---

### 2. Cursor

#### Option A: Via MCP Server (Recommended)

```bash
# Add to Cursor settings
# File: ~/.cursor/mcp.json

{
  "mcpServers": {
    "mesh": {
      "command": "mesh",
      "args": ["serve"],
      "env": {}
    }
  }
}
```

#### Option B: Via npx

```bash
npx @modelcontextprotocol/server-stdio mesh serve
```

Then add in Cursor Settings > AI > Anthropic:

```
MCP Server: mesh
Command: npx @modelcontextprotocol/server-stdio
Args: mesh serve
```

---

### 3. Claude Code (CLI)

```bash
# Add via claude mcp command
claude mcp add mesh "mesh serve"

# Or manually in ~/.claude/settings.json
```

---

### 4. VS Code (via extensions)

Install "MCP Explorer" extension, then add:

```json
{
  "mcpServers": {
    "mesh": {
      "command": "mesh",
      "args": ["serve"]
    }
  }
}
```

---

## Available Tools

Once connected, Mesh provides 4 MCP tools:

| Tool | Description |
|------|-------------|
| `mesh_architecture` | Get codebase overview with TOP FLOWS |
| `mesh_locate` | Find functions/classes with fuzzy search |
| `mesh_check` | Check for violations |
| `mesh_explain` | AI-powered explanation via Ollama |

---

## Usage Examples

### Architecture Overview

```
You: What's the architecture of this codebase?

Mesh returns:
[MESH v2 | myapp | 45 files | 320 funcs]
NAMING: snake_case (92%)
TOP FLOWS:
  process_request → [validate, auth, execute, respond]
  send_email → [format, queue, dispatch]
```

### Finding Code

```
You: Where's the login function?

Mesh returns:
- login (auth.py:23) - exact match
- login_required (decorators.py:45) - partial match
- handle_login (api.py:112) - fuzzy match
```

### Explaining Code

```
You: How does the payment flow work?

Mesh + Ollama returns:
The payment flow has three stages:
1. validate_payment() - checks card, amount
2. process_transaction() - calls payment provider
3. update_order_status() - marks order complete

Key files: payment.py, orders.py
```

---

## Configuration

### Set Default Ollama Model

```bash
# Create config
mkdir -p .mesh
echo '{"ollama_model": "qwen3.5:9b"}' > .mesh/config.json
```

### Custom Root Directory

```bash
mesh serve --root /path/to/project
```

---

## Troubleshooting

### MCP shows "Disconnected"

This is normal — the server starts on-demand when you ask a question. It's lazy-loaded.

### Tools not appearing

1. Restart the AI tool
2. Check MCP is added: `qwen mcp list`
3. Verify Mesh is installed: `mesh --help`

### Ollama not working

```bash
# Start Ollama
ollama serve

# Install a model
ollama pull qwen3.5:9b
```

---

## CLI Reference

```bash
mesh init          # Analyze codebase
mesh status        # Show statistics  
mesh doctor        # Health check
mesh serve        # Start MCP server
mesh setup        # Interactive wizard
mesh ask "?"      # Ask questions (requires Ollama)
mesh check        # Check violations
```
