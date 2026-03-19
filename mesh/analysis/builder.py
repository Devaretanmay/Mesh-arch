"""
Analysis builder — High-performance graph analysis engine.

Optimizations:
- Single-pass parsing (functions + classes together)
- Parallel file processing
- Batch SQLite writes with transactions
- Incremental analysis support
- Progress callbacks
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from mesh.core.graph import MeshGraph
from mesh.core.parser import UniversalParser, ParsedFunction, ParsedClass, ParseResult
from mesh.core.storage import MeshStorage

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    files_analyzed: int
    functions_found: int
    classes_found: int
    edges_created: int
    duration_seconds: float
    errors: list[str]
    incremental: bool = False
    skipped_files: int = 0


class AnalysisBuilder:
    """
    High-performance graph analysis builder.
    
    Features:
    - Parallel file parsing
    - Single-pass extraction
    - Batch database writes
    - Incremental analysis
    - Progress callbacks
    """

    def __init__(self, codebase_root: Path, workers: int = 4):
        self._root = codebase_root
        self._parser = UniversalParser(codebase_root, workers=workers)
        self._storage = MeshStorage(codebase_root)
        self._progress_callback: Callable[[str, int, int], None] | None = None

    def set_progress_callback(self, callback: Callable[[str, int, int], None] | None) -> None:
        self._progress_callback = callback
        self._parser.set_progress_callback(callback)

    def _report_progress(self, message: str, current: int, total: int) -> None:
        if self._progress_callback:
            self._progress_callback(message, current, total)

    def run_full_analysis(self) -> AnalysisResult:
        import time
        start = time.perf_counter()
        errors = []

        self._storage.clear()

        parse_result = self._parser.parse_directory(self._root)
        functions = parse_result.functions
        classes = parse_result.classes
        errors.extend(parse_result.errors)

        self._report_progress("Building graphs", 0, 1)

        call_graph = self._build_call_graph(functions, classes)
        type_graph = self._build_type_graph(classes)
        data_flow_graph = self._build_data_flow_graph(functions)

        self._report_progress("Saving to database", 0, 1)

        self._storage.begin_transaction()
        try:
            self._store_graph(call_graph, "call")
            self._store_graph(type_graph, "type")
            self._store_graph(data_flow_graph, "dataflow")
            self._storage.commit_transaction()
        except Exception as e:
            self._storage.rollback_transaction()
            errors.append(f"Database error: {e}")

        duration = time.perf_counter() - start

        return AnalysisResult(
            files_analyzed=len(set(f.file_path for f in functions)),
            functions_found=len(functions),
            classes_found=len(classes),
            edges_created=call_graph.edge_count + type_graph.edge_count + data_flow_graph.edge_count,
            duration_seconds=duration,
            errors=errors,
        )

    def run_incremental_analysis(self) -> AnalysisResult:
        import time
        start = time.perf_counter()
        errors = []
        skipped = 0

        current_hashes = self._storage.get_all_file_hashes()
        new_hashes = {h.path: h for h in self._parser.get_file_hashes(self._root)}

        changed_files = []
        for path, new_hash in new_hashes.items():
            old_hash = current_hashes.get(path)
            if old_hash != new_hash.hash:
                changed_files.append(path)
            else:
                skipped += 1

        if not changed_files:
            self._report_progress("No changes", 1, 1)
            return AnalysisResult(
                files_analyzed=0,
                functions_found=0,
                classes_found=0,
                edges_created=0,
                duration_seconds=time.perf_counter() - start,
                errors=[],
                incremental=True,
                skipped_files=len(current_hashes),
            )

        self._report_progress(f"Incremental: {len(changed_files)} files changed", 0, len(changed_files))

        for file_path_str in changed_files:
            file_path = Path(file_path_str)
            result = self._parser.parse_file(file_path, self._root)
            
            if result.functions or result.classes:
                self._clear_file_nodes(file_path_str)
                
                file_functions = result.functions
                file_classes = result.classes
                
                call_graph = self._build_call_graph(file_functions, file_classes)
                type_graph = self._build_type_graph(file_classes)
                data_flow_graph = self._build_data_flow_graph(file_functions)
                
                self._store_graph(call_graph, "call")
                self._store_graph(type_graph, "type")
                self._store_graph(data_flow_graph, "dataflow")

        self._storage.save_file_hashes([{
            "path": h.path,
            "hash": h.hash,
            "mtime": h.mtime,
            "size": h.size,
        } for h in new_hashes.values()])

        all_functions = [n["data"].get("name") for n in self._storage.get_nodes("call")]
        all_classes = [n["data"].get("name") for n in self._storage.get_nodes("type")]

        duration = time.perf_counter() - start

        return AnalysisResult(
            files_analyzed=len(changed_files),
            functions_found=len(all_functions),
            classes_found=len(all_classes),
            edges_created=self._storage.edge_count(),
            duration_seconds=duration,
            errors=errors,
            incremental=True,
            skipped_files=skipped,
        )

    def _clear_file_nodes(self, file_path: str) -> None:
        conn = self._storage._get_conn()
        conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        conn.execute("DELETE FROM edges WHERE from_id IN (SELECT id FROM nodes WHERE file_path = ?)", (file_path,))
        conn.commit()

    def _build_call_graph(
        self, functions: list[ParsedFunction], classes: list[ParsedClass] | None = None
    ) -> MeshGraph:
        graph = MeshGraph("call")

        name_to_id: dict[tuple[str, str], str] = {}
        id_to_func: dict[str, ParsedFunction] = {}

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
                    "is_async": func.is_async,
                    "decorators": func.decorators,
                    "branches": func.branches,
                    "loops": func.loops,
                    "exception_handlers": func.exception_handlers,
                    "awaits": func.awaits,
                    "raises": func.raises,
                    "imports": func.imports,
                },
            )
            name_to_id[(func.file_path, func.name)] = func.id
            id_to_func[func.id] = func

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
                        "methods": cls.methods,
                        "kind": "class",
                    },
                )
                name_to_id[(cls.file_path, cls.name)] = cls.id

        existing_edges: set[tuple[str, str, str]] = set()

        for func in functions:
            for call_name in func.calls:
                target_id = name_to_id.get((func.file_path, call_name))

                if target_id is None:
                    for (fp, name), fid in name_to_id.items():
                        if name == call_name:
                            target_id = fid
                            break

                if target_id and target_id != func.id:
                    edge_key = (func.id, target_id, "calls")
                    if edge_key not in existing_edges:
                        graph.add_edge(func.id, target_id, {"type": "calls", "call_site_line": func.line_end})
                        existing_edges.add(edge_key)

        for func in functions:
            if func.branches:
                for branch in func.branches:
                    graph.add_edge(func.id, func.id, {
                        "type": "branch",
                        "condition": branch.get("condition", ""),
                        "line": branch.get("line", 0),
                    })

            if func.loops:
                for loop in func.loops:
                    graph.add_edge(func.id, func.id, {
                        "type": "loop",
                        "loop_type": loop.get("type", ""),
                        "line": loop.get("line", 0),
                    })

            if func.exception_handlers:
                for exc in func.exception_handlers:
                    graph.add_edge(func.id, func.id, {
                        "type": "exception_handler",
                        "exception_type": exc.get("type", ""),
                        "line": exc.get("line", 0),
                    })

        return graph

    def _build_type_graph(self, classes: list[ParsedClass]) -> MeshGraph:
        graph = MeshGraph("type")

        name_to_id: dict[str, str] = {}

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
            name_to_id[cls.name] = cls.id

        for cls in classes:
            for base in cls.bases:
                target_id = name_to_id.get(base)
                if target_id and target_id != cls.id:
                    graph.add_edge(cls.id, target_id, {"type": "extends"})

        return graph

    def _build_data_flow_graph(self, functions: list[ParsedFunction]) -> MeshGraph:
        graph = MeshGraph("dataflow")

        param_to_funcs: dict[str, set[str]] = {}
        return_to_funcs: dict[str, set[str]] = {}

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

            for param in func.params:
                param_lower = param.lower()
                if param_lower not in param_to_funcs:
                    param_to_funcs[param_lower] = set()
                param_to_funcs[param_lower].add(func.id)

            for ret in func.returns:
                ret_lower = ret.lower()
                if ret_lower not in return_to_funcs:
                    return_to_funcs[ret_lower] = set()
                return_to_funcs[ret_lower].add(func.id)

        existing_edges: set[tuple[str, str]] = set()

        for func in functions:
            for ret in func.returns:
                ret_lower = ret.lower()
                if ret_lower in param_to_funcs:
                    for target_id in param_to_funcs[ret_lower]:
                        if target_id != func.id:
                            edge_key = (func.id, target_id)
                            if edge_key not in existing_edges:
                                graph.add_edge(func.id, target_id, {
                                    "type": "dataflow",
                                    "param": ret,
                                    "flow": "return_to_param",
                                })
                                existing_edges.add(edge_key)

        return graph

    def _store_graph(self, graph: MeshGraph, graph_type: str) -> None:
        type_prefix = f"{graph_type}:"
        
        nodes_batch = []
        for node_data in graph.nodes():
            node_id = node_data.get("id", "")
            if not node_id:
                continue
            prefixed_id = f"{type_prefix}{node_id}"
            nodes_batch.append((prefixed_id, graph_type, node_data.get("file_path", ""), node_data))

        edges_batch = []
        for edge_data in graph.get_all_edges():
            from_id = edge_data.get("from_id", "")
            to_id = edge_data.get("to_id", "")
            if from_id and to_id:
                edges_batch.append((
                    f"{type_prefix}{from_id}",
                    f"{type_prefix}{to_id}",
                    edge_data.get("type", graph_type),
                    edge_data,
                ))

        self._storage.upsert_node_batch(nodes_batch)
        self._storage.upsert_edge_batch(edges_batch)

    @property
    def storage(self) -> MeshStorage:
        return self._storage

    def close(self) -> None:
        self._storage.close()


DEFAULT_SENSITIVE_PARAMS: set[str] = {
    "password", "token", "secret", "api_key", "apikey", "auth", "credential",
    "private_key", "session_id", "ssn", "credit_card", "cvv", "pin",
    "access_token", "refresh_token", "jwt", "bearer", "authorization",
    "x_api_key", "client_secret",
}

DEFAULT_SINK_FUNCTIONS: set[str] = {
    "log", "print", "console.log", "logger", "debug", "info", "warn", "error",
    "writeFile", "write_file", "request", "fetch", "axios", "send", "sendmail",
    "mail", "notify", "alert",
}


def detect_duplicates(graph: MeshGraph) -> list[dict]:
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
            violations.append({
                "kind": "duplicate",
                "severity": "warning",
                "message": f"{name}() exists in {len(unique_files)} files",
                "file_path": unique_files[0],
                "line": 0,
                "related_files": unique_files[1:],
                "fix_hint": f"Consolidate {name}() into one location",
            })
    return violations


def detect_naming_violations(graph: MeshGraph) -> list[dict]:
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
    
    majority_convention, majority_count = convention_counts.most_common(1)[0]
    total = sum(convention_counts.values())
    majority_pct = majority_count / total if total > 0 else 0
    
    if majority_pct < 0.70:
        return []
    
    violations = []
    for node_data, conv in node_conventions:
        if conv != majority_convention and conv != "other":
            violations.append({
                "kind": "naming",
                "severity": "warning",
                "message": f"{node_data.get('name')}() uses {conv} but codebase is {int(majority_pct*100)}% {majority_convention}",
                "file_path": node_data.get("file_path", ""),
                "line": node_data.get("line_start", 0),
                "related_files": [],
                "fix_hint": f"Rename to {majority_convention}",
            })
    return violations


def detect_circular_dependencies(graph: MeshGraph) -> list[dict]:
    import rustworkx as rx
    
    violations = []
    try:
        cycles = list(rx.simple_cycles(graph._graph))
        seen_modules: set[str] = set()
        
        for cycle in cycles:
            if len(cycle) < 2:
                continue
            
            modules = set()
            for idx in cycle:
                node_data = graph._graph[idx]
                module = node_data.get("file_path", "unknown").split("/")[0]
                if module not in seen_modules:
                    modules.add(module)
                    seen_modules.add(module)
            
            if len(modules) > 1:
                cycle_str = " -> ".join(sorted(modules))
                violations.append({
                    "kind": "circular",
                    "severity": "error",
                    "message": f"Circular dependency: {cycle_str}",
                    "file_path": list(modules)[0],
                    "line": 0,
                    "related_files": sorted(list(modules)[1:]),
                    "fix_hint": "Extract shared code to a common module",
                })
    except Exception:
        pass
    
    return violations


def detect_data_flow_violations(data_flow_graph: MeshGraph) -> list[dict]:
    violations = []
    sensitive_params = DEFAULT_SENSITIVE_PARAMS.copy()
    sink_functions = DEFAULT_SINK_FUNCTIONS.copy()
    
    nodes = {n.get("id"): n for n in data_flow_graph.nodes() if n.get("id")}
    
    for node_id, node in nodes.items():
        params = node.get("params", [])
        returns = node.get("returns", [])
        
        has_sensitive_input = any(any(sp in p.lower() for sp in sensitive_params) for p in params)
        has_sensitive_output = any(any(sp in r.lower() for sp in sensitive_params) for r in returns)
        
        if not has_sensitive_input and not has_sensitive_output:
            continue
        
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
            violations.append({
                "kind": "sensitive_data_leak",
                "severity": "error",
                "message": f"Sensitive data flows to: {', '.join(set(sink_calls))}",
                "file_path": node.get("file_path", ""),
                "line": node.get("line_start", 0),
                "related_files": list(set(sink_calls)),
                "fix_hint": "Encrypt or mask sensitive data before logging/external calls",
            })
    
    return violations


detect_circular_calls = detect_circular_dependencies
