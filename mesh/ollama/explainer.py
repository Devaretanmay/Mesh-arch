"""
mesh/ollama/explainer.py

Explains code using Ollama + call graph context.
This is what turns Mesh from a navigation tool into
a comprehension tool.

The flow:
  1. User asks: "how do the verification flows work?"
  2. mesh_locate finds relevant functions (using fuzzy search)
  3. We load their signatures from the codebase
  4. We pass: summary + call chains + signatures to Ollama
  5. Ollama explains in plain English
"""

from pathlib import Path
import json
import logging
import re

logger = logging.getLogger(__name__)

STOP_WORDS = {
    "how",
    "does",
    "do",
    "what",
    "is",
    "are",
    "the",
    "a",
    "an",
    "this",
    "that",
    "these",
    "those",
    "work",
    "works",
    "working",
    "function",
    "functions",
    "method",
    "methods",
    "code",
    "it",
    "tell",
    "me",
    "explain",
    "show",
    "find",
    "get",
    "which",
    "where",
    "when",
    "why",
    "can",
    "could",
    "would",
    "should",
    "and",
    "or",
    "but",
    "for",
    "with",
    "without",
    "between",
    "in",
    "on",
    "at",
    "to",
    "from",
    "of",
    "about",
    "into",
    "differ",
    "difference",
    "similar",
    "same",
    "compare",
    "understand",
    "understanding",
    "know",
    "knowing",
}


def _extract_search_terms(question: str) -> list[str]:
    """
    Extract meaningful search terms from a natural language question.

    "how does GPT process emails?" → ["GPT", "process", "emails"]
    "how do the verification flows differ?" → ["verification", "flows"]
    "what calls send_email?" → ["send_email"]

    Returns list of terms to search, most specific first.
    """
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", question)

    terms = [t for t in tokens if t.lower() not in STOP_WORDS and len(t) >= 3]

    seen = set()
    unique_terms = []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique_terms.append(t)

    if not unique_terms:
        unique_terms = sorted(tokens, key=len, reverse=True)[:3]

    return unique_terms[:4]


def explain_query(
    query: str,
    codebase_root: Path,
    max_functions: int = 8,
) -> str:
    """
    Answer a natural language question about the codebase.

    Uses call graph to find relevant functions,
    loads their signatures, and asks Ollama to explain.

    Returns plain English explanation.
    Falls back to structural summary if Ollama not available.
    """
    from mesh.core.storage import MeshStorage
    from mesh.mcp.server import _score_match
    from mesh.mcp.summary import generate_summary, _extract_top_flows

    storage = MeshStorage(codebase_root)
    if not storage.graphs_exist():
        return "Codebase not analysed. Run: mesh init\n" "Then try again."

    try:
        cg = storage.load_call_graph()
        td = storage.load_type_deps_graph()
        df = storage.load_data_flow_graph()
        storage.close()
    except Exception as e:
        return f"Error loading graphs: {e}"

    # Extract specific search terms from the question
    search_terms = _extract_search_terms(query)

    # Search for each term and merge results
    all_results = []
    seen_names = set()

    for term in search_terms:
        for node_data in cg.nodes():
            name = node_data.get("name", "")
            if not name or name in seen_names:
                continue

            score = _score_match(term, name)
            if score > 0:
                seen_names.add(name)
                all_results.append(
                    {
                        "name": name,
                        "file": node_data.get("file_path", ""),
                        "line": node_data.get("line_start", 0),
                        "score": score,
                    }
                )

    # Sort by score and limit
    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
    relevant_functions = all_results[:max_functions]

    call_context = []
    nodes = {n.get("id"): n for n in cg.nodes() if n.get("id")}

    for fn in relevant_functions[:max_functions]:
        fn_name = fn.get("name", "")
        fn_file = fn.get("file", "")
        fn_line = fn.get("line", 0)

        callers = []
        callees = []

        for edge in cg.edges():
            if isinstance(edge, dict):
                if edge.get("to_id") == fn_name:
                    caller_node = nodes.get(edge.get("from_id"), {})
                    callers.append(caller_node.get("name", ""))
                if edge.get("from_id") == fn_name:
                    callee_node = nodes.get(edge.get("to_id"), {})
                    callees.append(callee_node.get("name", ""))

        callers = list(set(callers))[:3]
        callees = list(set(callees))[:3]

        signature = _load_function_signature(fn_file, fn_name, fn_line, codebase_root)

        call_context.append(
            {
                "name": fn_name,
                "file": fn_file,
                "line": fn_line,
                "signature": signature,
                "callers": callers,
                "callees": callees,
            }
        )

    arch_summary = generate_summary(cg, td, codebase_root, data_flow_graph=df)

    flows = _extract_top_flows(cg, max_flows=3)

    return _ask_ollama(query, arch_summary, call_context, flows, codebase_root)


def _load_function_signature(
    file_path: str,
    function_name: str,
    line_number: int,
    root: Path,
    lines_of_context: int = 12,
) -> str:
    """
    Load the actual function signature and first few lines
    from the source file. This gives Ollama real code context.
    """
    try:
        path = Path(file_path)
        if not path.is_absolute():
            path = root / file_path

        if not path.exists():
            return f"def {function_name}(...): ..."

        source_lines = path.read_text(errors="ignore").splitlines()

        start = max(0, line_number - 1)

        for i in range(start, min(start + 5, len(source_lines))):
            if f"def {function_name}" in source_lines[i]:
                start = i
                break

        end = min(start + lines_of_context, len(source_lines))

        # Get just the function definition + first few lines
        snippet_lines = []
        for i in range(start, end):
            line = source_lines[i]
            snippet_lines.append(line)
            # Stop after function body starts (indented code)
            if (
                i > start
                and line.strip()
                and not line.startswith(" ")
                and not line.startswith("\t")
            ):
                break
            # Limit to reasonable length
            if len("\n".join(snippet_lines)) > 500:
                break

        snippet = "\n".join(snippet_lines)

        return snippet

    except Exception:
        return f"def {function_name}(...): ..."


def _ask_ollama(
    query: str,
    arch_summary: str,
    call_context: list[dict],
    flows: list[str],
    root: Path,
) -> str:
    """Ask Ollama to explain."""
    context_parts = []
    for fn in call_context:
        part = f"**{fn['name']}** ({fn['file']}:{fn['line']})"
        if fn["callers"]:
            part += f"\n  ← Called by: {', '.join(fn['callers'][:3])}"
        if fn["callees"]:
            part += f"\n  → Calls: {', '.join(fn['callees'][:3])}"
        if fn["signature"]:
            # Truncate signature for brevity
            sig = fn["signature"].split("\n")[0]
            part += f"\n  Signature: {sig}"
        context_parts.append(part)

    context_str = "\n\n".join(context_parts)

    flows_str = "\n".join(flows) if flows else "No flows detected"

    prompt = f"""You are a code architect explaining a codebase to a developer.

CONTEXT:
{arch_summary}

EXECUTION FLOWS:
{flows_str}

FUNCTIONS:
{context_str}

QUESTION: {query}

Provide a brief, practical answer (2-3 sentences). Focus on:
- What the code DOES (not how)
- Key relationships between components
- Practical guidance for the developer

Be concise. Use bullet points if helpful."""

    try:
        import ollama as ollama_client

        config_path = root / ".mesh" / "config.json"
        model = "qwen3.5:9b"

        if config_path.exists():
            try:
                config = json.loads(config_path.read_text())
                model = config.get("ollama_model", model)
            except Exception:
                pass

        response = ollama_client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 400, "think": False},
        )

        answer = response.message.content.strip() if response.message.content else ""

        # Fallback to thinking content if main content is empty
        if not answer and response.message.thinking:
            answer = response.message.thinking.strip()

        if not answer:
            return _structural_answer(query, call_context, flows, arch_summary)

        fn_names = [fn["name"] for fn in call_context[:3]]
        header = (
            f"Found {len(call_context)} relevant functions: {', '.join(fn_names)}\n"
        )

        if flows:
            header += f"Key flows: {', '.join(flows[:2])}\n"

        return header + answer

    except ImportError:
        return _structural_answer(query, call_context, flows, arch_summary)
    except Exception:
        return _structural_answer(query, call_context, flows, arch_summary)


def _structural_answer(
    query: str,
    call_context: list[dict],
    flows: list[str],
    arch_summary: str,
) -> str:
    """
    Fallback when Ollama is not available.
    Returns structural information with a prompt to start Ollama.
    """
    lines = [f"Relevant functions for '{query}':", ""]

    for fn in call_context:
        lines.append(f"  {fn['name']}")
        lines.append(f"    File: {fn['file']} line {fn['line']}")
        if fn["callers"]:
            lines.append(f"    Called by: {', '.join(fn['callers'])}")
        if fn["callees"]:
            lines.append(f"    Calls: {', '.join(fn['callees'])}")
        lines.append("")

    if not call_context:
        lines.append(f"  No functions found matching '{query}'")
        lines.append("  Try a different search term.")

    if flows:
        lines.append("Key flows in codebase:")
        for flow in flows[:3]:
            lines.append(f"  {flow}")

    lines.extend(
        [
            "---",
            "For natural language explanation, start Ollama:",
            "  ollama serve",
            "Then run mesh ask again.",
        ]
    )

    return "\n".join(lines)
