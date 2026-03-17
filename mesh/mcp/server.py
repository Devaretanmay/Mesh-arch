"""Full JSON-RPC 2.0 MCP stdio server for Mesh v2.0."""

import json
import sys
from pathlib import Path
from typing import Any

from mesh.core.storage import MeshStorage
from mesh.analysis.builder import AnalysisBuilder
from mesh.mcp.summary import get_architectural_context


class GraphLoader:
    """Async graph loader."""

    def __init__(self, codebase_root: Path):
        self.codebase_root = codebase_root
        self.storage = MeshStorage(codebase_root)
        self._loaded = False

    def load(self) -> bool:
        """Load graphs."""
        if not self.storage.graphs_exist():
            builder = AnalysisBuilder(self.codebase_root)
            builder.run_full_analysis()
            builder.close()
        self._loaded = True
        return True

    @property
    def is_loaded(self) -> bool:
        return self._loaded


class MCPServer:
    """Full JSON-RPC 2.0 MCP stdio server."""

    def __init__(self, codebase_root: Path):
        self.root = codebase_root
        self.loader = GraphLoader(codebase_root)
        self._running = False

    def start(self):
        """Start server - handles JSON-RPC 2.0 stdio communication."""
        self._running = True
        self._handle_rpc_loop()

    def _handle_rpc_loop(self):
        """Main loop reading JSON-RPC requests from stdin."""
        while self._running:
            try:
                line = sys.stdin.readline()
                if not line:
                    break

                request = json.loads(line.strip())
                response = self._handle_request(request)

                if response:
                    print(json.dumps(response), flush=True)

            except json.JSONDecodeError:
                self._send_error(None, -32700, "Parse error")
            except Exception as e:
                self._send_error(None, -32603, f"Internal error: {e}")

    def _handle_request(self, request: dict) -> dict | None:
        """Handle a JSON-RPC request."""
        method = request.get("method")
        request_id = request.get("id")

        if method == "initialize":
            return self._response(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "mesh-mcp", "version": "2.0.0"},
                },
            )

        if method == "tools/list":
            return self._response(request_id, {"tools": self.get_tools()})

        if method == "tools/call":
            tool_name = request.get("params", {}).get("name")
            tool_args = request.get("params", {}).get("arguments", {})
            result = self.call_tool(tool_name, tool_args)
            return self._response(
                request_id,
                {
                    "content": [
                        {"type": "text", "text": str(result.get("summary", result))}
                    ]
                },
            )

        if method == "shutdown":
            self._running = False
            return self._response(request_id, None)

        if method == "$/cancel":
            return None

        return self._send_error(request_id, -32601, "Method not found")

    def _response(self, id: Any, result: Any) -> dict:
        """Create JSON-RPC response."""
        response = {"jsonrpc": "2.0", "id": id}
        if result is not None:
            response["result"] = result
        return response

    def _send_error(self, id: Any, code: int, message: str) -> dict:
        """Create JSON-RPC error response."""
        return {
            "jsonrpc": "2.0",
            "id": id,
            "error": {"code": code, "message": message},
        }

    def get_tools(self):
        """Get available tools."""
        return [
            {
                "name": "mesh_architecture",
                "description": "Get architectural summary of codebase including modules, dependencies, and structure",
                "inputSchema": {"type": "object", "properties": {}},
            },
            {
                "name": "mesh_check",
                "description": "Check code for architectural violations and anti-patterns",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to check"},
                        "target_file": {
                            "type": "string",
                            "description": "File path to check",
                        },
                    },
                },
            },
            {
                "name": "mesh_locate",
                "description": "Locate functions, classes, or symbols in the codebase using fuzzy matching",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Symbol name to locate (supports partial/fuzzy matching)",
                        },
                        "type": {
                            "type": "string",
                            "description": "Type: function, class, or module",
                        },
                    },
                },
            },
            {
                "name": "mesh_explain",
                "description": (
                    "Ask a natural language question about the codebase "
                    "and get a plain English explanation. Uses call graph "
                    "analysis combined with Ollama to explain how code works, "
                    "not just where it is. "
                    "Example: 'how do the verification flows work?'"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": (
                                "Natural language question about the codebase. "
                                "Examples: 'how does auth work?', "
                                "'what calls process_payment?', "
                                "'how do these three flows differ?'"
                            ),
                        }
                    },
                    "required": ["question"],
                },
            },
            {
                "name": "mesh_dependencies",
                "description": (
                    "Show what a function depends on (what it calls/imports). "
                    "Returns direct and transitive dependencies at different depth levels. "
                    "Example: What functions does process_order call?"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "function": {
                            "type": "string",
                            "description": "Function name to analyze",
                        },
                        "depth": {
                            "type": "number",
                            "description": "Depth of dependency analysis (1-3, default 1)",
                        },
                    },
                    "required": ["function"],
                },
            },
            {
                "name": "mesh_callers",
                "description": (
                    "Find who calls a specific function. "
                    "Returns all functions that call the target function, with call site locations. "
                    "Example: Who calls validate_token?"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "function": {
                            "type": "string",
                            "description": "Function name to find callers for",
                        },
                    },
                    "required": ["function"],
                },
            },
            {
                "name": "mesh_impact",
                "description": (
                    "Show what breaks if you change a function. "
                    "Analyzes the downstream impact including direct and transitive callers. "
                    "Calculates risk level based on number of affected functions. "
                    "Example: What happens if I change hash_password?"
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "function": {
                            "type": "string",
                            "description": "Function name to analyze impact for",
                        },
                    },
                    "required": ["function"],
                },
            },
        ]

    def call_tool(self, name: str, args: dict) -> dict:
        """Call a tool by name."""
        if name == "mesh_architecture":
            return self._mesh_architecture()
        elif name == "mesh_check":
            return self._mesh_check(args.get("code", ""), args.get("target_file", ""))
        elif name == "mesh_locate":
            return self._mesh_locate(args.get("symbol", ""), args.get("type", ""))
        elif name == "mesh_explain":
            return self._mesh_explain(args.get("question", ""))
        elif name == "mesh_dependencies":
            return self._mesh_dependencies(
                args.get("function", ""), args.get("depth", 1)
            )
        elif name == "mesh_callers":
            return self._mesh_callers(args.get("function", ""))
        elif name == "mesh_impact":
            return self._mesh_impact(args.get("function", ""))
        return {"error": f"Unknown tool: {name}"}

    def _mesh_architecture(self) -> dict:
        """Get architectural summary."""
        if not self.loader.is_loaded:
            self.loader.load()

        storage = self.loader.storage
        try:
            cg = storage.load_call_graph()
        except Exception as e:
            return {"error": f"No graph available. Run mesh init first: {e}"}

        summary = get_architectural_context(cg, None, None, self.root)
        return {"summary": summary}

    def _mesh_check(self, code: str, target_file: str) -> dict:
        """Check code for violations."""
        violations = []
        warnings = []

        if not self.loader.is_loaded:
            self.loader.load()

        storage = self.loader.storage

        try:
            cg = storage.load_call_graph()
            # Check for function name collisions
            import re

            func_names = re.findall(r"def (\w+)\(", code)
            existing_names = {n.get("name", "") for n in cg.nodes()}

            for name in func_names:
                if name in existing_names:
                    violations.append(
                        {
                            "type": "duplicate",
                            "message": f"Function {name}() already exists",
                        }
                    )
        except Exception as e:
            warnings.append(
                {"type": "analysis", "message": f"Could not run analysis: {e}"}
            )

        return {
            "is_clean": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
        }

    def _mesh_locate(self, symbol: str, sym_type: str) -> dict:
        """Locate symbols in the codebase with fuzzy matching."""
        if not self.loader.is_loaded:
            self.loader.load()

        storage = self.loader.storage

        try:
            cg = storage.load_call_graph()
        except Exception as e:
            return {"error": f"Could not locate symbol: {e}"}

        query_lower = symbol.lower().strip()
        results = []
        seen = set()

        for node_data in cg.nodes():
            name = node_data.get("name", "")
            file_path = node_data.get("file_path", "")
            if not name:
                continue

            # Score 1: file stem matching
            file_stem = Path(file_path).stem.lower() if file_path else ""
            file_score = 0
            if query_lower == file_stem:
                file_score = 90
            elif query_lower in file_stem or file_stem in query_lower:
                file_score = 65

            # Score 2: function/class name matching
            name_score = _score_match(symbol, name)

            # Take the higher of the two scores
            score = max(file_score, name_score)

            if score > 0:
                key = (name, file_path)
                if key not in seen:
                    seen.add(key)
                    node_type = node_data.get("kind", "function")
                    if sym_type and sym_type != node_type:
                        continue
                    results.append(
                        {
                            "name": name,
                            "file": file_path,
                            "line": node_data.get("line_start", 0),
                            "type": node_type,
                            "score": score,
                            "match_type": (
                                "file_match"
                                if file_score >= name_score
                                else (
                                    "exact"
                                    if score >= 100
                                    else (
                                        "strong"
                                        if score >= 75
                                        else "partial" if score >= 30 else "fuzzy"
                                    )
                                )
                            ),
                        }
                    )

        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        for r in results:
            del r["score"]

        return {
            "symbol": symbol,
            "results": results[:8],
            "query": symbol,
            "total_searched": len(list(cg.nodes())),
        }

    def _mesh_explain(self, question: str) -> dict:
        """Ask a natural language question about the codebase."""
        if not question.strip():
            return {"summary": "Please provide a question about the codebase."}

        from mesh.ollama.explainer import explain_query

        answer = explain_query(question, self.root)

        return {"summary": answer}

    def _mesh_dependencies(self, function_name: str, depth: int = 1) -> dict:
        """Get dependencies of a function (what it calls/imports)."""
        if not self.loader.is_loaded:
            self.loader.load()

        storage = self.loader.storage
        try:
            cg = storage.load_call_graph()
        except Exception as e:
            return {"error": f"No graph available: {e}"}

        # Find the function
        target_node = None
        for node in cg.nodes():
            if node.get("name") == function_name:
                target_node = node
                break

        if not target_node:
            return {"error": f"Function '{function_name}' not found"}

        target_id = target_node.get("id")
        if not target_id:
            return {"error": f"Function '{function_name}' has no ID"}

        # Get direct dependencies (what it calls)
        dependencies = {
            "function": function_name,
            "direct_calls": [],
            "calls_depth": {},
            "data_dependencies": [],
            "file": target_node.get("file_path", ""),
            "line": target_node.get("line_start", 0),
        }

        # Get direct calls
        for edge in cg.get_all_edges():
            if edge.get("from_id") == target_id and edge.get("type") == "calls":
                to_id = edge.get("to_id")
                if to_id:
                    to_node = self._get_node_by_id(cg, to_id)
                    if to_node:
                        dep = {
                            "function": to_node.get("name", ""),
                            "file": to_node.get("file_path", ""),
                            "line": to_node.get("line_start", 0),
                        }
                        dependencies["direct_calls"].append(dep)

        # Get transitive dependencies if depth > 1
        if depth > 1:
            # Build a simple dependency map
            call_map = {}
            for edge in cg.get_all_edges():
                if edge.get("type") == "calls":
                    from_id = edge.get("from_id")
                    to_id = edge.get("to_id")
                    if from_id and to_id:
                        if from_id not in call_map:
                            call_map[from_id] = []
                        call_map[from_id].append(to_id)

            # BFS to get dependencies at each level
            current_level = [target_id]
            visited = {target_id}

            for level in range(1, depth + 1):
                next_level = []
                level_deps = []

                for node_id in current_level:
                    if node_id in call_map:
                        for dep_id in call_map[node_id]:
                            if dep_id not in visited:
                                visited.add(dep_id)
                                next_level.append(dep_id)
                                dep_node = self._get_node_by_id(cg, dep_id)
                                if dep_node:
                                    dep = {
                                        "function": dep_node.get("name", ""),
                                        "file": dep_node.get("file_path", ""),
                                        "line": dep_node.get("line_start", 0),
                                    }
                                    level_deps.append(dep)

                dependencies["calls_depth"][f"level_{level}"] = level_deps
                current_level = next_level
                if not current_level:
                    break

        # Try to get data flow dependencies if available
        try:
            storage.load_data_flow_graph()
            # For now, we'll note that data flow analysis is available
            dependencies["has_data_flow"] = True
        except Exception:
            dependencies["has_data_flow"] = False

        return dependencies

    def _mesh_callers(self, function_name: str) -> dict:
        """Find who calls a specific function."""
        if not self.loader.is_loaded:
            self.loader.load()

        storage = self.loader.storage
        try:
            cg = storage.load_call_graph()
        except Exception as e:
            return {"error": f"No graph available: {e}"}

        # Find the function
        target_node = None
        for node in cg.nodes():
            if node.get("name") == function_name:
                target_node = node
                break

        if not target_node:
            return {"error": f"Function '{function_name}' not found"}

        target_id = target_node.get("id")
        if not target_id:
            return {"error": f"Function '{function_name}' has no ID"}

        # Find all callers
        callers = []
        call_sites = []

        for edge in cg.get_all_edges():
            if edge.get("to_id") == target_id and edge.get("type") == "calls":
                from_id = edge.get("from_id")
                if from_id:
                    from_node = self._get_node_by_id(cg, from_id)
                    if from_node:
                        caller = {
                            "function": from_node.get("name", ""),
                            "file": from_node.get("file_path", ""),
                            "line": from_node.get("line_start", 0),
                        }
                        callers.append(caller)

                        call_site = {
                            "caller": from_node.get("name", ""),
                            "file": from_node.get("file_path", ""),
                            "line": edge.get("call_site_line", 0),
                            "conditional": edge.get("is_conditional", False),
                        }
                        call_sites.append(call_site)

        return {
            "function": function_name,
            "callers": callers,
            "call_sites": call_sites,
            "total_callers": len(callers),
        }

    def _mesh_impact(self, function_name: str) -> dict:
        """Show what breaks if you change a function."""
        if not self.loader.is_loaded:
            self.loader.load()

        storage = self.loader.storage
        try:
            cg = storage.load_call_graph()
        except Exception as e:
            return {"error": f"No graph available: {e}"}

        # Find the function
        target_node = None
        for node in cg.nodes():
            if node.get("name") == function_name:
                target_node = node
                break

        if not target_node:
            return {"error": f"Function '{function_name}' not found"}

        target_id = target_node.get("id")
        if not target_id:
            return {"error": f"Function '{function_name}' has no ID"}

        # Build reverse call graph (who calls whom)
        reverse_map = {}
        for edge in cg.get_all_edges():
            if edge.get("type") == "calls":
                from_id = edge.get("from_id")
                to_id = edge.get("to_id")
                if from_id and to_id:
                    if to_id not in reverse_map:
                        reverse_map[to_id] = []
                    reverse_map[to_id].append(from_id)

        # BFS to find all functions that depend on this one (transitive callers)
        def get_all_callers(node_id):
            if node_id not in reverse_map:
                return []
            callers = []
            to_check = list(reverse_map[node_id])
            visited = {node_id}

            while to_check:
                current = to_check.pop(0)
                if current not in visited:
                    visited.add(current)
                    callers.append(current)
                    if current in reverse_map:
                        to_check.extend(reverse_map[current])
            return callers

        all_callers = get_all_callers(target_id)

        # Get caller details
        caller_details = []
        for caller_id in all_callers:
            caller_node = self._get_node_by_id(cg, caller_id)
            if caller_node:
                caller_details.append(
                    {
                        "function": caller_node.get("name", ""),
                        "file": caller_node.get("file_path", ""),
                        "line": caller_node.get("line_start", 0),
                    }
                )

        # Calculate risk level
        risk_level = "low"
        if len(all_callers) > 10:
            risk_level = "high"
        elif len(all_callers) > 5:
            risk_level = "medium"

        # Get direct callers (immediate impact)
        direct_callers = []
        if target_id in reverse_map:
            for caller_id in reverse_map[target_id]:
                caller_node = self._get_node_by_id(cg, caller_id)
                if caller_node:
                    direct_callers.append(
                        {
                            "function": caller_node.get("name", ""),
                            "file": caller_node.get("file_path", ""),
                            "line": caller_node.get("line_start", 0),
                        }
                    )

        return {
            "function": function_name,
            "risk_level": risk_level,
            "direct_impact": {"callers": direct_callers, "count": len(direct_callers)},
            "transitive_impact": {
                "callers": caller_details,
                "count": len(caller_details),
            },
            "affected_files": len(set(c["file"] for c in caller_details if c["file"])),
        }

    def _get_node_by_id(self, graph, node_id: str):
        """Helper to get node by ID."""
        for node in graph.nodes():
            if node.get("id") == node_id:
                return node
        return None


def _score_match(query: str, function_name: str) -> int:
    """
    Score how well a query matches a function name.
    Returns 0-100. Higher = better match.

    Handles:
    - Exact matches
    - Substring matches
    - Token overlap (most useful — handles partial names)
    - Partial token matches (handles typos)
    """
    q = query.lower().strip()
    n = function_name.lower().strip()

    if not q or not n:
        return 0

    if q == n:
        return 100

    if q in n:
        return 85

    if n in q:
        return 75

    q_tokens = set(q.replace("_", " ").split())
    n_tokens = set(n.replace("_", " ").split())

    q_tokens = {t for t in q_tokens if len(t) >= 3}
    n_tokens = {t for t in n_tokens if len(t) >= 3}

    if q_tokens and n_tokens:
        overlap = q_tokens & n_tokens
        if overlap:
            score = int((len(overlap) / len(q_tokens)) * 70)
            return max(score, 30)

    for qt in q_tokens:
        for nt in n_tokens:
            if len(qt) >= 3 and len(nt) >= 3:
                if qt.startswith(nt[:4]) or nt.startswith(qt[:4]):
                    return 20

    return 0


def create_server(codebase_root: Path) -> MCPServer:
    """Create MCP server."""
    return MCPServer(codebase_root)


def main():
    """Main entry point for MCP server."""
    root = Path.cwd()
    server = create_server(root)
    server.start()


if __name__ == "__main__":
    main()
