"""Code analysis using local LLM.

Wraps LocalLLM with code-specific prompts for codebase analysis.
"""

from pathlib import Path
from typing import Optional

from mesh.core.storage import MeshStorage
from mesh.llm.local import LocalLLM
from mesh.llm.downloader import ensure_model


SYSTEM_PROMPT = """You are Mesh, an expert code analysis assistant. 
You analyze codebases and provide clear, concise explanations of code architecture.

Be specific and reference actual function names and file paths when explaining."""


class CodeExplainer:
    def __init__(self):
        self._llm: Optional[LocalLLM] = None

    def _get_llm(self) -> LocalLLM:
        if self._llm is None:
            model_path, _ = ensure_model()
            self._llm = LocalLLM(model_path)
        return self._llm

    def explain(
        self,
        query: str,
        context: dict,
        max_tokens: int = 512,
    ) -> str:
        llm = self._get_llm()
        
        functions = context.get("functions", [])
        call_graph = context.get("call_graph", "")
        files = context.get("files", [])
        violations = context.get("violations", [])
        repos = context.get("repos", [])
        cross_repo_deps = context.get("cross_repo_dependencies", "")

        prompt_parts = []

        if repos:
            repo_list = ", ".join(r.get("name", r.get("id", "")) for r in repos)
            prompt_parts.append(f"Repositories in workspace:\n{repo_list}")

        if cross_repo_deps:
            prompt_parts.append(cross_repo_deps)

        if files:
            file_list = "\n".join(f"- {f}" for f in files[:20])
            prompt_parts.append(f"Key files in codebase:\n{file_list}")

        if functions:
            func_list = "\n".join(f"- {f}" for f in functions[:30])
            prompt_parts.append(f"Functions in codebase:\n{func_list}")

        if call_graph:
            prompt_parts.append(f"Call relationships:\n{call_graph}")

        if violations:
            violation_list = "\n".join(f"- {v}" for v in violations[:10])
            prompt_parts.append(f"Architectural issues:\n{violation_list}")

        context_str = "\n\n".join(prompt_parts) if prompt_parts else "No additional context."

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""Analyze this codebase based on the following context:

{context_str}

Question: {query}

Answer the question based on the provided context. If the context doesn't contain enough information, say so.""",
            },
        ]

        return llm.chat(messages, max_tokens=max_tokens)

    def summarize(self, codebase_info: dict, max_tokens: int = 512) -> str:
        llm = self._get_llm()

        files = codebase_info.get("files", [])
        functions = codebase_info.get("functions", [])
        edges = codebase_info.get("dependencies", 0)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""Analyze this codebase:

Files: {len(files)}
Functions: {len(functions)}
Dependencies: {edges}

Top files by function count:
{self._format_top_files(files)}

Provide a brief architectural summary of the codebase.""",
            },
        ]

        return llm.chat(messages, max_tokens=max_tokens)

    def _format_top_files(self, files: list[dict]) -> str:
        if not files:
            return "No files"

        top = sorted(files, key=lambda x: x.get("count", 0), reverse=True)[:10]
        return "\n".join(f"- {f['file']}: {f.get('count', 0)} functions" for f in top)

    def unload(self) -> None:
        if self._llm:
            self._llm.unload()
            self._llm = None


def explain_query(query: str, root_path: Path, repo_id: str | None = None) -> str:
    from mesh.analysis.builder import AnalysisBuilder
    from mesh.analysis.workspace import WorkspaceAnalysisBuilder
    from mesh.core.workspace import get_workspace

    workspace = get_workspace(root_path)
    is_workspace = len(workspace.repos) > 1

    if is_workspace:
        builder = WorkspaceAnalysisBuilder(root_path)
        repos = builder.storage.get_repos()
        
        if not repos:
            builder.detect_and_register_repos()
            for repo in workspace.repos:
                builder.analyze_repo(repo)
        
        context = _build_workspace_context(builder, repo_id)
        builder.close()
    else:
        storage = MeshStorage(root_path)

        if not storage.graphs_exist():
            storage.close()
            builder = AnalysisBuilder(root_path)
            builder.run_full_analysis()
            builder.close()
            storage = MeshStorage(root_path)

        context = _build_single_repo_context(storage, repo_id)
        storage.close()

    explainer = CodeExplainer()
    try:
        return explainer.explain(query, context)
    finally:
        explainer.unload()


def _build_workspace_context(builder: WorkspaceAnalysisBuilder, focus_repo: str | None = None) -> dict:
    workspace = builder.workspace
    repos = builder.storage.get_repos()
    
    context = {
        "repos": [
            {"id": r.id, "name": r.name, "type": r.type}
            for r in repos
        ],
        "files": [],
        "functions": [],
        "call_graph": "",
        "cross_repo_dependencies": "",
        "violations": [],
    }
    
    for repo in repos:
        if focus_repo and repo.id != focus_repo:
            continue
        
        detail = builder.get_repo_detail(repo.id)
        if detail:
            for func in detail.get("functions", [])[:20]:
                context["functions"].append(f"{repo.name}::{func.get('name', '')}")
            
            for cls in detail.get("classes", [])[:10]:
                context["functions"].append(f"{repo.name}::class::{cls.get('name', '')}")
    
    matrix = builder.get_repo_relationships()
    if matrix:
        lines = ["Repository dependencies:"]
        for repo_id, deps in matrix.items():
            if deps.get("depends_on"):
                lines.append(f"  {repo_id} depends on: {', '.join(deps['depends_on'])}")
        context["cross_repo_dependencies"] = "\n".join(lines)
    
    return context


def _build_single_repo_context(storage: MeshStorage, repo_id: str | None = None) -> dict:
    nodes = storage.get_nodes(repo_id=repo_id)
    
    files: dict[str, int] = {}
    for n in nodes:
        fp = n.get("file_path", "unknown")
        files[fp] = files.get(fp, 0) + 1
    
    context = {
        "files": list(files.keys()),
        "functions": [n.get("name", "") for n in nodes],
        "call_graph": _build_call_graph_summary(storage, repo_id),
        "violations": [],
    }
    
    return context


def _build_call_graph_summary(storage: MeshStorage, repo_id: str | None = None) -> str:
    edges = storage.get_edges(repo_id=repo_id)
    if not edges:
        return "No call dependencies found."

    cross_repo = [e for e in edges if e.get("from_repo") != e.get("to_repo")]
    same_repo = [e for e in edges if e.get("from_repo") == e.get("to_repo")]

    lines = []

    if cross_repo:
        lines.append("Cross-repo dependencies:")
        for edge in cross_repo[:10]:
            lines.append(f"  {edge.get('from_repo')} → {edge.get('to_repo')}: {edge.get('type', 'calls')}")

    calls = [e for e in same_repo if e.get("type") == "calls"]
    if calls:
        lines.append("\nKey call relationships:")
        for edge in calls[:15]:
            caller = edge.get("from_id", "")
            callee = edge.get("to_id", "")
            if caller and callee:
                lines.append(f"  {caller} → {callee}")

    if not lines:
        return "No function calls detected."

    return "\n".join(lines)
