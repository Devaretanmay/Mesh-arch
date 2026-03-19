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

        prompt_parts = []
        
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


def explain_query(query: str, root_path: Path) -> str:
    from mesh.analysis.builder import AnalysisBuilder

    storage = MeshStorage(root_path)

    if not storage.graphs_exist():
        storage.close()
        builder = AnalysisBuilder(root_path)
        builder.run_full_analysis()
        builder.close()
        storage = MeshStorage(root_path)

    nodes = storage.get_nodes()
    
    files: dict[str, int] = {}
    for n in nodes:
        fp = n.get("file_path", "unknown")
        files[fp] = files.get(fp, 0) + 1
    
    context = {
        "files": list(files.keys()),
        "functions": [n.get("name", "") for n in nodes],
        "call_graph": _build_call_graph_summary(storage),
        "violations": [],
    }
    storage.close()

    explainer = CodeExplainer()
    try:
        return explainer.explain(query, context)
    finally:
        explainer.unload()


def _build_call_graph_summary(storage: MeshStorage) -> str:
    edges = storage.get_edges()
    if not edges:
        return "No call dependencies found."

    calls = [e for e in edges if e.get("edge_type") == "calls"]
    if not calls:
        return "No function calls detected."

    top_calls = sorted(calls, key=lambda x: x.get("count", 0), reverse=True)[:15]
    lines = ["Key call relationships:"]
    for edge in top_calls:
        caller = edge.get("from_node", "")
        callee = edge.get("to_node", "")
        if caller and callee:
            lines.append(f"  {caller} → {callee}")

    return "\n".join(lines)
