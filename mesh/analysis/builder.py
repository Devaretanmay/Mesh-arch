"""
Analysis builder — wires parser, graph, and storage together.

Builds call graphs, data flow graphs, and type dependency graphs
using the universal parser and rustworkx-backed MeshGraph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mesh.core.graph import MeshGraph
from mesh.core.parser import UniversalParser, ParsedFunction, ParsedClass
from mesh.core.storage import MeshStorage

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of running analysis."""

    files_analyzed: int
    functions_found: int
    edges_created: int
    duration_seconds: float
    errors: list[str]


class AnalysisBuilder:
    """
    Builds all Mesh graphs from source code.

    Wires:
      - UniversalParser (25-language parsing)
      - MeshGraph (rustworkx-backed)
      - MeshStorage (SQLite persistence)
    """

    def __init__(self, codebase_root: Path):
        """
        Initialize builder.

        Args:
            codebase_root: Root directory of codebase
        """
        self._root = codebase_root
        self._parser = UniversalParser(codebase_root)
        self._storage = MeshStorage(codebase_root)

    def run_full_analysis(self) -> AnalysisResult:
        """
        Run complete analysis: parse all files, build all graphs.

        Returns:
            AnalysisResult with statistics
        """
        import time

        start = time.perf_counter()

        # Clear existing data
        self._storage.clear()

        # Parse all files
        functions = self._parser.parse_directory(self._root)

        # Parse classes for type dependencies
        classes = self._parser.parse_classes_directory(self._root)

        # Build call graph (include classes for searchable index)
        call_graph = self._build_call_graph(functions, classes)

        # Build type dependency graph
        type_graph = self._build_type_graph(classes)

        # Build data flow graph
        data_flow_graph = self._build_data_flow_graph(functions)

        # Store all graphs in database
        self._store_graph(call_graph, "call")
        self._store_graph(type_graph, "type")
        self._store_graph(data_flow_graph, "dataflow")

        duration = time.perf_counter() - start

        return AnalysisResult(
            files_analyzed=len(set(f.file_path for f in functions)),
            functions_found=len(functions),
            edges_created=call_graph.edge_count
            + type_graph.edge_count
            + data_flow_graph.edge_count,
            duration_seconds=duration,
            errors=[],
        )

    def _build_call_graph(
        self, functions: list[ParsedFunction], classes: list[ParsedClass] | None = None
    ) -> MeshGraph:
        """
        Build call graph from parsed functions and classes.

        Args:
            functions: List of parsed functions
            classes: List of parsed classes (optional, for searchable index)

        Returns:
            MeshGraph with call relationships
        """
        graph = MeshGraph("call")

        # Add all function nodes
        for func in functions:
            graph.add_node(
                func.id,
                {
                    "name": func.name,
                    "file_path": func.file_path,
                    "line_start": func.line_start,
                    "line_end": func.line_end,
                    "signature": func.signature,
                    "docstring": func.docstring,
                    "kind": "function",
                    # Control flow info
                    "is_async": func.is_async,
                    "decorators": func.decorators,
                    "branches": func.branches,
                    "loops": func.loops,
                    "exception_handlers": func.exception_handlers,
                    "awaits": func.awaits,
                    "raises": func.raises,
                },
            )

        # Add class nodes to the graph for searchable index
        if classes:
            for cls in classes:
                graph.add_node(
                    cls.id,
                    {
                        "name": cls.name,
                        "file_path": cls.file_path,
                        "line_start": cls.line_start,
                        "line_end": cls.line_end,
                        "bases": cls.bases,
                        "kind": "class",
                    },
                )

        # Build name-to-id mapping for call resolution
        name_to_id: dict[tuple[str, str], str] = {}
        for func in functions:
            key = (func.file_path, func.name)
            name_to_id[key] = func.id

        # Add class names to mapping for searchable index
        if classes:
            for cls in classes:
                key = (cls.file_path, cls.name)
                name_to_id[key] = cls.id

        # Add call edges
        for func in functions:
            for call_name in func.calls:
                # Try to find the called function
                # First, try exact file match
                target_id = name_to_id.get((func.file_path, call_name))

                # If not found, try any file with that name
                if target_id is None:
                    for key, fid in name_to_id.items():
                        if key[1] == call_name:
                            target_id = fid
                            break

                if target_id and target_id != func.id:
                    graph.add_edge(
                        func.id,
                        target_id,
                        {"type": "calls", "call_site_line": func.line_end},
                    )

        # Add control flow edges (branches, loops, exceptions)
        for func in functions:
            func_id = func.id

            # Branch edges (if/else)
            for branch in func.branches:
                graph.add_edge(
                    func_id,
                    func_id,  # Self-loop to mark branch point
                    {
                        "type": "branch",
                        "condition": branch.get("condition", ""),
                        "line": branch.get("line", 0),
                    },
                )

            # Loop edges
            for loop in func.loops:
                graph.add_edge(
                    func_id,
                    func_id,  # Self-loop to mark loop point
                    {
                        "type": "loop",
                        "loop_type": loop.get("type", ""),
                        "line": loop.get("line", 0),
                    },
                )

            # Exception handler edges
            for exc in func.exception_handlers:
                graph.add_edge(
                    func_id,
                    func_id,  # Self-loop to mark exception handler
                    {
                        "type": "exception_handler",
                        "exception_type": exc.get("type", ""),
                        "line": exc.get("line", 0),
                    },
                )

            # Async/await edges
            if func.is_async:
                for await_call in func.awaits:
                    # Try to find the awaited function
                    for target_func in functions:
                        if (
                            await_call in target_func.name
                            or target_func.name in await_call
                        ):
                            graph.add_edge(
                                func_id,
                                target_func.id,
                                {"type": "awaits", "call": await_call},
                            )

        return graph

    def _build_type_graph(self, classes: list[ParsedClass]) -> MeshGraph:
        """
        Build type dependency graph from parsed classes.

        Args:
            classes: List of parsed classes

        Returns:
            MeshGraph with type relationships
        """
        graph = MeshGraph("type")

        # Add all class nodes
        for cls in classes:
            graph.add_node(
                cls.id,
                {
                    "name": cls.name,
                    "file_path": cls.file_path,
                    "line_start": cls.line_start,
                    "line_end": cls.line_end,
                    "bases": cls.bases,
                    "methods": cls.methods,
                    "attributes": cls.attributes,
                    "kind": cls.kind,
                },
            )

        # Build base class mapping
        name_to_id = {}
        for cls in classes:
            key = (cls.file_path, cls.name)
            name_to_id[key] = cls.id
            name_to_id[cls.name] = cls.id

        # Add inheritance edges
        for cls in classes:
            for base in cls.bases:
                target_id = name_to_id.get(base)
                if target_id and target_id != cls.id:
                    graph.add_edge(
                        cls.id,
                        target_id,
                        {"type": "extends"},
                    )

        return graph

    def _build_data_flow_graph(self, functions: list[ParsedFunction]) -> MeshGraph:
        """
        Build data flow graph from parsed functions.

        Tracks how data (parameters and return values) flows between functions.
        If function A returns 'user_id' and function B takes 'user_id' as param,
        creates an edge A -> B with type 'dataflow'.

        Args:
            functions: List of parsed functions

        Returns:
            MeshGraph with data flow relationships
        """
        graph = MeshGraph("dataflow")

        # Add all function nodes with data flow info
        for func in functions:
            graph.add_node(
                func.id,
                {
                    "name": func.name,
                    "file_path": func.file_path,
                    "line_start": func.line_start,
                    "line_end": func.line_end,
                    "params": func.params,
                    "returns": func.returns,
                    "kind": "function",
                },
            )

        # Build param -> function mapping
        # For each param, track which functions accept it
        param_to_funcs: dict[str, list[str]] = {}
        for func in functions:
            for param in func.params:
                param_lower = param.lower()
                if param_lower not in param_to_funcs:
                    param_to_funcs[param_lower] = []
                param_to_funcs[param_lower].append(func.id)

        # Build return -> function mapping
        # For each return value, track which functions produce it
        return_to_funcs: dict[str, list[str]] = {}
        for func in functions:
            for ret in func.returns:
                ret_lower = ret.lower()
                if ret_lower not in return_to_funcs:
                    return_to_funcs[ret_lower] = []
                return_to_funcs[ret_lower].append(func.id)

        # Build data flow edges
        # If function A returns X and function B takes X as param, A -> B
        for func in functions:
            for ret in func.returns:
                ret_lower = ret.lower()
                # Find functions that use this return value as param
                if ret_lower in param_to_funcs:
                    for target_id in param_to_funcs[ret_lower]:
                        if target_id != func.id:
                            # Check if this edge already exists to avoid duplicates
                            edge_exists = False
                            for edge in graph.get_all_edges():
                                if (
                                    edge.get("from_id") == func.id
                                    and edge.get("to_id") == target_id
                                ):
                                    edge_exists = True
                                    break
                            if not edge_exists:
                                graph.add_edge(
                                    func.id,
                                    target_id,
                                    {
                                        "type": "dataflow",
                                        "param": ret,
                                        "flow": "return_to_param",
                                    },
                                )

        return graph

    def _store_graph(self, graph: MeshGraph, graph_type: str) -> None:
        """
        Store graph in database.

        Args:
            graph: MeshGraph to store
            graph_type: Type of graph (call, dataflow, typedep)
        """
        # Store nodes with graph-type prefix to avoid ID collisions
        type_prefix = f"{graph_type}:"
        for node_data in graph.nodes():
            node_id = node_data.get("id", "")
            if not node_id:
                continue
            prefixed_id = f"{type_prefix}{node_id}"
            self._storage.upsert_node(
                node_id=prefixed_id,
                node_type=graph_type,
                file_path=node_data.get("file_path", ""),
                data=node_data,
            )

        # Store edges with prefixed IDs
        for edge_data in graph.get_all_edges():
            from_id = edge_data.get("from_id", "")
            to_id = edge_data.get("to_id", "")
            if from_id and to_id:
                self._storage.upsert_edge(
                    from_id=f"{type_prefix}{from_id}",
                    to_id=f"{type_prefix}{to_id}",
                    edge_type=edge_data.get("type", "calls"),
                    data=edge_data,
                )

    def load_call_graph(self) -> MeshGraph:
        """
        Load call graph from storage.

        Returns:
            MeshGraph with call relationships
        """
        graph = MeshGraph("call")

        # Load nodes
        nodes = self._storage.get_nodes("call")
        for node in nodes:
            graph.add_node(node["id"], node["data"])

        # Load edges
        edges = self._storage.get_edges("calls")
        for edge in edges:
            graph.add_edge(edge["from_id"], edge["to_id"], edge["data"])

        return graph

    @property
    def storage(self) -> MeshStorage:
        """Get storage instance."""
        return self._storage

    def close(self) -> None:
        """Close resources."""
        self._storage.close()


def detect_duplicates(graph: MeshGraph) -> list[dict]:
    """Detect duplicate function names across different files."""
    from collections import defaultdict

    name_to_locations: dict[str, list[str]] = defaultdict(list)
    for node_data in graph.nodes():
        name = node_data.get("name", "")
        file_path = node_data.get("file_path", "")
        if name and file_path:
            name_to_locations[name].append(file_path)

    violations = []
    for name, locations in name_to_locations.items():
        unique_files = list(set(locations))
        if len(unique_files) > 1:
            violations.append(
                {
                    "kind": "duplicate",
                    "severity": "error",
                    "message": f"{name}() exists in {len(unique_files)} files",
                    "file_path": unique_files[0],
                    "line": 0,
                    "related_files": unique_files[1:],
                    "fix_hint": f"Consolidate {name}() into one location",
                }
            )
    return violations


def detect_circular_calls(graph: MeshGraph) -> list[dict]:
    """Detect circular dependencies using rustworkx."""
    import rustworkx as rx

    violations = []
    try:
        cycles = list(rx.simple_cycles(graph._graph))
        for cycle in cycles:
            if len(cycle) < 2:
                continue
            cycle_ids = []
            for idx in cycle:
                node_data = graph._graph[idx]
                module = (
                    node_data.get("file_path", "").split("/")[0]
                    if node_data.get("file_path")
                    else "unknown"
                )
                if module not in cycle_ids:
                    cycle_ids.append(module)

            if len(set(cycle_ids)) > 1:
                violations.append(
                    {
                        "kind": "circular",
                        "severity": "error",
                        "message": f"Circular dependency: {' -> '.join(cycle_ids)} -> {cycle_ids[0]}",
                        "file_path": cycle_ids[0],
                        "line": 0,
                        "related_files": cycle_ids[1:],
                        "fix_hint": "Extract shared code to a common module",
                    }
                )
    except Exception:
        pass

    return violations


def detect_circular_dependencies(graph: MeshGraph) -> list[dict]:
    """Alias for detect_circular_calls."""
    return detect_circular_calls(graph)


def detect_naming_violations(graph: MeshGraph) -> list[dict]:
    """Auto-detect naming convention and flag violations."""
    from collections import Counter

    def classify_name(name: str) -> str:
        if "_" in name and name == name.lower():
            return "snake_case"
        elif name and name[0].islower() and any(c.isupper() for c in name[1:]):
            return "camelCase"
        elif name and name[0].isupper():
            return "PascalCase"
        return "other"

    convention_counts: Counter = Counter()
    node_conventions: list[tuple[dict, str]] = []

    for node_data in graph.nodes():
        name = node_data.get("name", "")
        if not name or name.startswith("_") or name in ("__init__", "__main__"):
            continue
        conv = classify_name(name)
        convention_counts[conv] += 1
        node_conventions.append((node_data, conv))

    if not convention_counts:
        return []

    majority = convention_counts.most_common(1)[0][0]
    total = sum(convention_counts.values())
    majority_pct = convention_counts[majority] / total if total > 0 else 0

    if majority_pct < 0.70:
        return []

    violations = []
    for node_data, conv in node_conventions:
        if conv != majority and conv != "other":
            name = node_data.get("name", "")
            file_path = node_data.get("file_path", "")
            violations.append(
                {
                    "kind": "naming",
                    "severity": "warning",
                    "message": f"{name}() uses {conv} but codebase is {int(majority_pct*100)}% {majority}",
                    "file_path": file_path,
                    "line": node_data.get("line_start", 0),
                    "related_files": [],
                    "fix_hint": f"Rename to {majority} convention",
                }
            )

    return violations


def find_naming_violations(graph: MeshGraph, type_graph: Any = None) -> list[dict]:
    """Alias for detect_naming_violations (for compatibility)."""
    return detect_naming_violations(graph)


# Default security patterns for data flow violation detection
DEFAULT_SENSITIVE_PARAMS: set[str] = {
    "password",
    "token",
    "secret",
    "api_key",
    "apikey",
    "auth",
    "credential",
    "private_key",
    "session_id",
    "ssn",
    "credit_card",
    "cvv",
    "pin",
    "access_token",
    "refresh_token",
    "jwt",
    "bearer",
    "authorization",
    "x_api_key",
    "client_secret",
}

DEFAULT_SINK_FUNCTIONS: set[str] = {
    "log",
    "print",
    "console.log",
    "logger",
    "debug",
    "info",
    "warn",
    "error",
    "writeFile",
    "write_file",
    "request",
    "fetch",
    "axios",
    "http.request",
    "http.post",
    "http.get",
    "send",
    "sendmail",
    "mail",
    "notify",
    "alert",
    "stdout",
    "stderr",
}


def load_security_config(codebase_root: Path) -> dict:
    """Load security configuration from .mesh/config.json."""
    config_path = codebase_root / ".mesh" / "config.json"
    if config_path.exists():
        try:
            import json

            return json.loads(config_path.read_text())
        except Exception:
            pass
    return {}


def get_security_patterns(codebase_root: Path) -> tuple[set[str], set[str]]:
    """
    Get security patterns from config or defaults.

    Returns:
        Tuple of (sensitive_params, sink_functions)
    """
    config = load_security_config(codebase_root)
    security = config.get("security_patterns", {})

    sensitive_params = set(security.get("sensitive_params", []))
    if not sensitive_params:
        sensitive_params = DEFAULT_SENSITIVE_PARAMS.copy()
    else:
        sensitive_params = sensitive_params | DEFAULT_SENSITIVE_PARAMS

    sink_functions = set(security.get("sink_functions", []))
    if not sink_functions:
        sink_functions = DEFAULT_SINK_FUNCTIONS.copy()
    else:
        sink_functions = sink_functions | DEFAULT_SINK_FUNCTIONS

    return sensitive_params, sink_functions


def detect_data_flow_violations(
    data_flow_graph: MeshGraph,
    codebase_root: Path | None = None,
    max_chain_length: int = 5,
) -> list[dict]:
    """
    Detect data flow violations.

    Args:
        data_flow_graph: The data flow graph
        codebase_root: Root of the codebase (for loading config)
        max_chain_length: Maximum allowed chain length before warning

    Returns:
        List of violation dicts
    """
    violations = []

    # Load custom patterns if config available
    sensitive_params = DEFAULT_SENSITIVE_PARAMS.copy()
    sink_functions = DEFAULT_SINK_FUNCTIONS.copy()

    if codebase_root:
        sensitive_params, sink_functions = get_security_patterns(codebase_root)

    # Build node lookup
    nodes = {n.get("id"): n for n in data_flow_graph.nodes() if n.get("id")}

    # 1. Detect long data chains
    for node_id in nodes:
        chain_length = _trace_data_chain_length(data_flow_graph, node_id, nodes)
        if chain_length > max_chain_length:
            node = nodes[node_id]
            violations.append(
                {
                    "kind": "dataflow_long_chain",
                    "severity": "warning",
                    "message": f"Data flows through {chain_length} functions (max: {max_chain_length})",
                    "file_path": node.get("file_path", ""),
                    "line": node.get("line_start", 0),
                    "related_files": [],
                    "fix_hint": f"Consider breaking the data flow chain at {node.get('name')}",
                }
            )

    # 2. Detect sensitive data leaks
    for node_id, node in nodes.items():
        params = node.get("params", [])
        returns = node.get("returns", [])

        # Check if function handles sensitive data
        has_sensitive_input = any(
            any(sp in p.lower() for sp in sensitive_params) for p in params
        )
        has_sensitive_output = any(
            any(sp in r.lower() for sp in sensitive_params) for r in returns
        )

        if not has_sensitive_input and not has_sensitive_output:
            continue

        # Check if it calls sink functions
        sink_calls = []
        for edge in data_flow_graph.edges():
            if isinstance(edge, dict) and edge.get("from_id") == node_id:
                to_id = edge.get("to_id", "")
                callee = nodes.get(to_id, {})
                callee_name = callee.get("name", "").lower()
                for sink in sink_functions:
                    if sink in callee_name:
                        sink_calls.append(callee.get("name", to_id))

        if sink_calls:
            violations.append(
                {
                    "kind": "dataflow_sensitive_leak",
                    "severity": "error",
                    "message": f"Sensitive data flows to: {', '.join(set(sink_calls))}",
                    "file_path": node.get("file_path", ""),
                    "line": node.get("line_start", 0),
                    "related_files": list(set(sink_calls)),
                    "fix_hint": "Encrypt or mask sensitive data before logging/external calls",
                }
            )

    # 3. Detect missing validation (input -> storage without validation)
    # This is simplified: check if input flows directly to common storage patterns
    storage_functions = {
        "save",
        "persist",
        "store",
        "write",
        "insert",
        "update",
        "delete",
        "save_to_db",
        "save_to_file",
        "persist_to",
        "commit",
        "flush",
    }

    for node_id, node in nodes.items():
        params = node.get("params", [])

        # Check if this is an input function (takes params, has no returns or returns bool)
        has_input = len(params) > 0
        returns_data = node.get("returns", [])
        is_getter = len(returns_data) > 0 and any(
            r.lower() in ["user", "data", "result", "item", "entity"]
            for r in returns_data
        )

        if not has_input or is_getter:
            continue

        # Trace where this input flows
        validation_found = False
        storage_found = False

        visited = set()
        to_visit = [node_id]

        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            visited.add(current)

            for edge in data_flow_graph.edges():
                if isinstance(edge, dict) and edge.get("from_id") == current:
                    to_id = edge.get("to_id", "")
                    callee = nodes.get(to_id, {})
                    callee_name = callee.get("name", "").lower()

                    # Check for validation patterns
                    if any(
                        v in callee_name
                        for v in ["validate", "check", "verify", "auth", "permit"]
                    ):
                        validation_found = True

                    # Check for storage patterns
                    if any(s in callee_name for s in storage_functions):
                        storage_found = True

                    to_visit.append(to_id)

        if has_input and storage_found and not validation_found:
            violations.append(
                {
                    "kind": "dataflow_no_validation",
                    "severity": "error",
                    "message": "Input parameter flows to storage without validation",
                    "file_path": node.get("file_path", ""),
                    "line": node.get("line_start", 0),
                    "related_files": [],
                    "fix_hint": "Add validation before storing data",
                }
            )

    return violations


def _trace_data_chain_length(
    data_flow_graph: MeshGraph,
    start_id: str,
    nodes: dict,
    visited: set | None = None,
) -> int:
    """Trace the maximum depth of data flow from a starting function."""
    if visited is None:
        visited = set()

    if start_id in visited:
        return 0
    visited.add(start_id)

    max_depth = 0
    for edge in data_flow_graph.edges():
        if isinstance(edge, dict) and edge.get("from_id") == start_id:
            to_id = edge.get("to_id", "")
            depth = _trace_data_chain_length(
                data_flow_graph, to_id, nodes, visited.copy()
            )
            max_depth = max(max_depth, depth + 1)

    return max_depth
