"""MCP tools stub for v2.0."""

import json


def check_code_snippet(
    code: str, target_file: str, call_graph=None, type_deps=None, codebase_root=None
) -> str:
    """Check code snippet for violations."""
    return json.dumps({"is_clean": True, "violations": [], "warnings": []})


def get_tools():
    """Get available tools."""
    return [
        {"name": "mesh_architecture", "description": "Get architectural summary"},
        {"name": "mesh_check", "description": "Check code for violations"},
    ]
