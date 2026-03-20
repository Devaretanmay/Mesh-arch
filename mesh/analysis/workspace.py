"""
Workspace analysis builder for Mesh.

Analyzes multiple repositories in a workspace:
- Detects and enumerates repos
- Analyzes each repo independently
- Detects cross-repo dependencies
- Builds repo relationship matrix
- Stores everything in a single database

Three data layers:
1. Complete Context: All repos in one graph
2. Repo Relationships: Summary of connections
3. Per-Repo Detail: Isolated analysis per repo
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from mesh.core.graph import MeshGraph
from mesh.core.parser import (
    CrossRepoImport,
    ParsedClass,
    ParsedFunction,
    RepoParseResult,
    UniversalParser,
    WorkspaceParseResult,
)
from mesh.core.storage import MeshStorage, Repo
from mesh.core.workspace import (
    RepoInfo,
    WorkspaceInfo,
    build_repo_relationship_matrix,
    classify_import,
    detect_workspace,
    get_workspace,
    resolve_cross_repo_imports,
    save_workspace_config,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceAnalysisResult:
    repos_analyzed: int
    files_analyzed: int
    functions_found: int
    classes_found: int
    cross_repo_edges: int
    duration_seconds: float
    errors: list[str]


@dataclass
class RepoAnalysisResult:
    repo_id: str
    files_analyzed: int
    functions_found: int
    classes_found: int
    cross_repo_imports: int
    duration_seconds: float
    errors: list[str]


class WorkspaceAnalysisBuilder:
    """
    Analyzes multiple repositories in a workspace.
    
    Features:
    - Auto-detect repos in workspace
    - Parallel repo analysis
    - Cross-repo dependency detection
    - Unified storage for all repos
    - Repo relationship matrix
    """

    def __init__(
        self,
        workspace_root: Path,
        workers: int = 4,
        repo_workers: int = 2,
    ):
        self._workspace_root = workspace_root
        self._workers = workers
        self._repo_workers = repo_workers
        self._storage = MeshStorage(workspace_root)
        self._workspace: WorkspaceInfo | None = None
        self._progress_callback: Callable[[str, int, int], None] | None = None

    @property
    def storage(self) -> MeshStorage:
        return self._storage

    @property
    def workspace(self) -> WorkspaceInfo:
        if self._workspace is None:
            self._workspace = get_workspace(self._workspace_root)
        return self._workspace

    def set_progress_callback(self, callback: Callable[[str, int, int], None] | None):
        self._progress_callback = callback

    def _report_progress(self, message: str, current: int, total: int):
        if self._progress_callback:
            self._progress_callback(message, current, total)

    def detect_and_register_repos(self) -> list[RepoInfo]:
        workspace = self.workspace
        
        for repo_info in workspace.repos:
            repo = Repo(
                id=repo_info.id,
                name=repo_info.name,
                path=str(repo_info.path),
                type=repo_info.type,
            )
            self._storage.save_repo(repo)
        
        save_workspace_config(workspace)
        
        return workspace.repos

    def analyze_repo(
        self,
        repo_info: RepoInfo,
        force: bool = False,
    ) -> RepoAnalysisResult:
        start = time.perf_counter()
        errors = []
        files_analyzed = 0
        functions_found = 0
        classes_found = 0
        cross_repo_imports = []

        parser = UniversalParser(repo_info.path, workers=self._repo_workers)
        
        all_functions: list[ParsedFunction] = []
        all_classes: list[ParsedClass] = []
        
        existing_hashes = self._storage.get_all_file_hashes(repo_info.id)
        
        for file_path in repo_info.path.rglob("*"):
            if not file_path.is_file():
                continue
            
            if parser.should_skip(file_path, repo_info.path):
                continue
            
            try:
                result = parser.parse_file(file_path, repo_info.path)
                
                if result.errors:
                    errors.extend(result.errors)
                
                if result.functions or result.classes:
                    files_analyzed += 1
                    functions_found += len(result.functions)
                    classes_found += len(result.classes)
                    all_functions.extend(result.functions)
                    all_classes.extend(result.classes)
                    
                    file_imports = [
                        imp for imp in result.functions[0].imports
                        if imp and not imp.startswith('.')
                    ] if result.functions else []
                    
                    for imp in file_imports:
                        target_repo_id, imp_type = classify_import(imp, self.workspace, repo_info)
                        if target_repo_id and target_repo_id != repo_info.id:
                            cross_repo_imports.append(CrossRepoImport(
                                source_repo=repo_info.id,
                                target_repo=target_repo_id,
                                import_path=imp,
                                imported_names=[],
                                file_path=str(file_path),
                                line=0,
                                type=imp_type,
                            ))
            
            except Exception as e:
                errors.append(f"{file_path}: {e}")
        
        self._report_progress(f"Analyzing {repo_info.name}", files_analyzed, 1)
        
        self._store_repo_data(repo_info, all_functions, all_classes, cross_repo_imports)
        
        self._storage.update_repo_analysis_time(repo_info.id)
        
        duration = time.perf_counter() - start
        
        return RepoAnalysisResult(
            repo_id=repo_info.id,
            files_analyzed=files_analyzed,
            functions_found=functions_found,
            classes_found=classes_found,
            cross_repo_imports=len(cross_repo_imports),
            duration_seconds=duration,
            errors=errors,
        )

    def _store_repo_data(
        self,
        repo_info: RepoInfo,
        functions: list[ParsedFunction],
        classes: list[ParsedClass],
        cross_repo_imports: list[CrossRepoImport],
    ):
        self._storage.clear(repo_info.id)
        
        call_graph = self._build_call_graph(functions, classes)
        type_graph = self._build_type_graph(classes)
        data_flow_graph = self._build_data_flow_graph(functions)
        
        self._storage.begin_transaction()
        try:
            self._store_graph(call_graph, "call", repo_info.id)
            self._store_graph(type_graph, "type", repo_info.id)
            self._store_graph(data_flow_graph, "dataflow", repo_info.id)
            
            for imp in cross_repo_imports:
                self._storage.upsert_edge(
                    from_id=f"import:{imp.import_path}",
                    to_id=f"repo:{imp.target_repo}:module",
                    edge_type="cross_repo_import",
                    data={
                        "import_path": imp.import_path,
                        "imported_names": imp.imported_names,
                        "file_path": imp.file_path,
                        "line": imp.line,
                        "type": imp.type,
                    },
                    from_repo=repo_info.id,
                    to_repo=imp.target_repo,
                )
            
            func_data = [
                {"id": f.id, "name": f.name, "file_path": f.file_path,
                 "line": f.line_start, "calls": f.calls, "params": f.params}
                for f in functions
            ]
            class_data = [
                {"id": c.id, "name": c.name, "file_path": c.file_path,
                 "line": c.line_start, "bases": c.bases, "methods": c.methods}
                for c in classes
            ]
            
            self._storage.save_repo_detail(
                repo_id=repo_info.id,
                functions=func_data,
                classes=class_data,
                violations=[],
                metrics={
                    "files_analyzed": len(set(f.file_path for f in functions)),
                    "functions_found": len(functions),
                    "classes_found": len(classes),
                    "cross_repo_imports": len(cross_repo_imports),
                },
            )
            
            self._storage.commit_transaction()
        except Exception as e:
            self._storage.rollback_transaction()
            raise

    def _build_call_graph(
        self,
        functions: list[ParsedFunction],
        classes: list[ParsedClass],
    ) -> MeshGraph:
        graph = MeshGraph("call")
        
        class_map = {c.name: c for c in classes}
        
        for func in functions:
            node_data = {
                "name": func.name,
                "file_path": func.file_path,
                "line_start": func.line_start,
                "line_end": func.line_end,
                "kind": func.kind,
                "is_async": func.is_async,
            }
            graph.add_node(func.id, node_data)
        
        for cls in classes:
            node_data = {
                "name": cls.name,
                "file_path": cls.file_path,
                "line_start": cls.line_start,
                "line_end": cls.line_end,
                "kind": cls.kind,
                "bases": cls.bases,
            }
            graph.add_node(cls.id, node_data)
        
        for func in functions:
            for call in func.calls:
                if call in class_map:
                    graph.add_edge(func.id, class_map[call].id, {"type": "calls_class"})
                else:
                    graph.add_edge(func.id, call, {"type": "calls"})
        
        for cls in classes:
            for base in cls.bases:
                if base in class_map:
                    graph.add_edge(cls.id, class_map[base].id, {"type": "inherits"})
        
        return graph

    def _build_type_graph(self, classes: list[ParsedClass]) -> MeshGraph:
        graph = MeshGraph("type")
        
        for cls in classes:
            node_data = {
                "name": cls.name,
                "file_path": cls.file_path,
                "line_start": cls.line_start,
                "line_end": cls.line_end,
                "kind": cls.kind,
                "bases": cls.bases,
                "attributes": cls.attributes,
            }
            graph.add_node(cls.id, node_data)
        
        for cls in classes:
            for base in cls.bases:
                graph.add_edge(cls.id, base, {"type": "inherits"})
        
        return graph

    def _build_data_flow_graph(self, functions: list[ParsedFunction]) -> MeshGraph:
        graph = MeshGraph("dataflow")
        
        for func in functions:
            node_data = {
                "name": func.name,
                "file_path": func.file_path,
                "params": func.params,
                "returns": func.returns,
                "raises": func.raises,
            }
            graph.add_node(func.id, node_data)
        
        for func in functions:
            if func.raises:
                for exc in func.raises:
                    graph.add_edge(func.id, exc, {"type": "raises"})
        
        return graph

    def _store_graph(self, graph: MeshGraph, graph_type: str, repo_id: str) -> None:
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

        self._storage.upsert_node_batch(nodes_batch, repo_id)
        self._storage.upsert_edge_batch(edges_batch, repo_id, repo_id)

    def analyze_all_repos(self, force: bool = False) -> WorkspaceAnalysisResult:
        start = time.perf_counter()
        errors = []
        
        repos = self.detect_and_register_repos()
        
        if not repos:
            return WorkspaceAnalysisResult(
                repos_analyzed=0,
                files_analyzed=0,
                functions_found=0,
                classes_found=0,
                cross_repo_edges=0,
                duration_seconds=time.perf_counter() - start,
                errors=["No repositories found in workspace"],
            )
        
        total_repos = len(repos)
        total_files = 0
        total_functions = 0
        total_classes = 0
        total_cross_repo = 0
        
        for i, repo in enumerate(repos):
            self._report_progress(f"Analyzing {repo.name}", i + 1, total_repos)
            
            result = self.analyze_repo(repo, force=force)
            
            errors.extend(result.errors)
            total_files += result.files_analyzed
            total_functions += result.functions_found
            total_classes += result.classes_found
            total_cross_repo += result.cross_repo_imports
        
        self._build_cross_repo_matrix()
        
        duration = time.perf_counter() - start
        
        return WorkspaceAnalysisResult(
            repos_analyzed=len(repos),
            files_analyzed=total_files,
            functions_found=total_functions,
            classes_found=total_classes,
            cross_repo_edges=total_cross_repo,
            duration_seconds=duration,
            errors=errors,
        )

    def _build_cross_repo_matrix(self) -> None:
        cross_repo_edges = self._storage.get_cross_repo_edges()
        
        matrix = {}
        for edge in cross_repo_edges:
            src = edge["from_repo"]
            tgt = edge["to_repo"]
            
            if src not in matrix:
                matrix[src] = {}
            if tgt not in matrix[src]:
                matrix[src][tgt] = 0
            matrix[src][tgt] += 1
        
        relationships = []
        for src, targets in matrix.items():
            for tgt, count in targets.items():
                relationships.append({
                    "source_repo": src,
                    "target_repo": tgt,
                    "relationship_type": "imports",
                    "count": count,
                })
        
        self._storage.save_repo_relationships(relationships)

    def get_complete_context(self) -> dict:
        nodes = self._storage.get_nodes()
        edges = self._storage.get_edges()
        repos = self._storage.get_repos()
        
        return {
            "repos": [
                {"id": r.id, "name": r.name, "path": r.path, "type": r.type}
                for r in repos
            ],
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_repos": len(repos),
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            },
        }

    def get_repo_relationships(self) -> dict:
        return self._storage.get_repo_matrix()

    def get_repo_detail(self, repo_id: str) -> dict | None:
        return self._storage.get_repo_detail(repo_id)

    def close(self) -> None:
        self._storage.close()
