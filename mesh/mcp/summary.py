"""Enhanced MCP summary for v2.0 - uses all 3 graphs."""

from pathlib import Path
from collections import Counter

from mesh.analysis.builder import (
    detect_duplicates,
    detect_circular_calls,
    detect_naming_violations,
)
from mesh.analysis.taint import detect_taint_violations


def approx_tokens(text: str) -> int:
    """Approximate token count."""
    return max(1, len(text) // 4)


def _get_patterns(call_graph, codebase_root: Path) -> str:
    """Detect architectural pattern from directory structure."""
    try:
        dirs = {p.name.lower() for p in codebase_root.iterdir() if p.is_dir()}
        if (
            {"service", "repo", "dto"} & dirs
            or {"services", "repos", "dtos"} & dirs
            or {"service", "repository"} & dirs
        ):
            return "service-repo-dto"
        if {"controller", "model", "view"} & dirs or {
            "controllers",
            "models",
            "views",
        } & dirs:
            return "MVC"
        if {"route", "handler"} & dirs or {"routes", "handlers"} & dirs:
            return "route-handler"
        if {"core", "api", "domain"} & dirs:
            return "layered"
        return "unknown"
    except Exception:
        return "unknown"


def _get_top_violations(call_graph) -> list[str]:
    """Return top violations as short strings."""
    lines = []
    try:
        dups = detect_duplicates(call_graph)
        for v in dups[:2]:
            name = v.get("message", "").split("(")[0]
            files = len(v.get("related_files", [])) + 1
            lines.append(f"  duplicate: {name}() in {files} files")
    except Exception:
        pass
    try:
        names = detect_naming_violations(call_graph)
        for v in names[:1]:
            msg = v.get("message", "")
            parts = msg.split()
            if parts:
                lines.append(f"  naming: {parts[0]}")
    except Exception:
        pass
    try:
        circs = detect_circular_calls(call_graph)
        for v in circs[:1]:
            msg = v.get("message", "")[:60]
            lines.append(f"  circular: {msg}")
    except Exception:
        pass
    return lines


def _get_reuse_hints(call_graph) -> list[str]:
    """Return most-called functions as reuse hints."""
    try:
        nodes = {n.get("id"): n for n in call_graph.nodes() if n.get("id")}
        in_degrees = {}
        for node_data in call_graph.nodes():
            node_id = node_data.get("id", "")
            if node_id:
                in_degrees[node_id] = call_graph.in_degree(node_id)
        top = sorted(in_degrees.items(), key=lambda x: x[1], reverse=True)[:5]
        hints = []
        for node_id, degree in top:
            if degree < 3:
                break
            node = nodes.get(node_id, {})
            name = node.get("name", node_id)
            hints.append(f"  {name} (called {degree}x)")
        return hints
    except Exception:
        return []


def _extract_top_flows(call_graph, max_flows: int = 5) -> list[str]:
    """
    Extract the top call chains from entry points.

    Entry points are functions with in_degree=0 that are not
    private (don't start with _) and are not test functions.

    Traces 3 hops deep maximum.
    Returns list of flow strings like:
      "scheduler → send_emails → [validate, format, dispatch]"

    This is the key insight the developer was missing:
    not WHAT functions exist, but HOW they connect.
    """
    try:
        flows = []
        nodes = {n.get("id"): n for n in call_graph.nodes() if n.get("id")}

        entry_points = []
        for node_id, node_data in nodes.items():
            name = node_data.get("name", "")
            if (
                name.startswith("_")
                or name.startswith("test_")
                or name in ("__init__", "__main__", "main")
            ):
                continue

            in_deg = call_graph.in_degree(node_id)
            out_deg = call_graph.out_degree(node_id)
            if in_deg == 0 and out_deg > 0:
                entry_points.append((node_id, node_data, out_deg))

        entry_points.sort(key=lambda x: x[2], reverse=True)

        for node_id, node_data, _ in entry_points[:max_flows]:
            chain = _trace_chain(call_graph, node_id, nodes, depth=3)
            if chain:
                flows.append(chain)

        if not flows:
            all_nodes = list(nodes.items())
            all_nodes.sort(key=lambda x: call_graph.out_degree(x[0]), reverse=True)
            for node_id, node_data in all_nodes[:max_flows]:
                name = node_data.get("name", "")
                if name.startswith("_"):
                    continue
                chain = _trace_chain(call_graph, node_id, nodes, depth=2)
                if chain:
                    flows.append(chain)

        return flows[:max_flows]

    except Exception:
        return []


def _trace_chain(
    call_graph,
    start_id: str,
    nodes: dict,
    depth: int = 3,
) -> str:
    """
    Trace a call chain from a starting function.

    Returns a string like:
      "process_order → [validate_order, charge_payment, send_confirmation]"

    At depth 1: just the direct callees
    At depth 2: callees of callees grouped
    At depth 3: full 3-hop chain
    """
    try:
        start_node = nodes.get(start_id, {})
        start_name = start_node.get("name", start_id)

        # Get docstring if available
        start_doc = start_node.get("docstring", "")
        if start_doc:
            # Truncate docstring
            start_doc = " ".join(start_doc.split())[:50]
            if len(start_doc) >= 50:
                start_doc += "..."

        callees_1 = []
        for edge in call_graph.edges():
            if isinstance(edge, dict):
                if edge.get("from_id") == start_id:
                    callee = nodes.get(edge.get("to_id", ""), {})
                    name = callee.get("name", "")
                    if name and not name.startswith("_"):
                        callees_1.append(name)

        callees_1 = list(dict.fromkeys(callees_1))[:4]

        if not callees_1:
            return ""

        if len(callees_1) == 1:
            return f"{start_name} → {callees_1[0]}"
        else:
            callees_str = ", ".join(callees_1[:3])
            if len(callees_1) > 3:
                callees_str += f" +{len(callees_1)-3}"
            return f"{start_name} → [{callees_str}]"

    except Exception:
        return ""


def _extract_data_flows(data_flow_graph, max_flows: int = 5) -> list[str]:
    """
    Extract data flow chains from the data flow graph.

    Returns list of strings like:
      "user_id: get_user → validate_user → create_session (3 hops)"
    """
    try:
        flows = []
        nodes = {n.get("id"): n for n in data_flow_graph.nodes() if n.get("id")}

        if not nodes:
            return []

        # Find starting points (functions that return something but aren't called by others in df graph)
        # For simplicity, find functions with returns that flow to other functions
        for node_id, node in nodes.items():
            returns = node.get("returns", [])
            if not returns:
                continue

            # Trace the chain
            chain = _trace_data_flow_chain(data_flow_graph, node_id, nodes, depth=3)
            if chain:
                flows.append(chain)

        # Sort by chain length (longest first)
        flows.sort(key=lambda x: x.split("(")[-1].split())  # Sort by hop count

        return flows[:max_flows]

    except Exception:
        return []


def _trace_data_flow_chain(
    data_flow_graph,
    start_id: str,
    nodes: dict,
    depth: int = 3,
) -> str:
    """Trace a data flow chain from a starting function."""
    try:
        start_node = nodes.get(start_id, {})
        start_name = start_node.get("name", start_id)
        returns = start_node.get("returns", [])

        if not returns:
            return ""

        # Get the primary return value
        primary_return = returns[0] if returns else "data"

        # Trace where this data flows
        callees = []
        visited = set()
        to_visit = [start_id]
        current_depth = 0

        while to_visit and current_depth < depth:
            current_level = to_visit
            to_visit = []

            for current_id in current_level:
                if current_id in visited:
                    continue
                visited.add(current_id)

                for edge in data_flow_graph.edges():
                    if isinstance(edge, dict) and edge.get("from_id") == current_id:
                        to_id = edge.get("to_id", "")
                        callee = nodes.get(to_id, {})
                        name = callee.get("name", "")
                        if name and not name.startswith("_") and name != start_name:
                            callees.append(name)
                            to_visit.append(to_id)

            current_depth += 1

        callees = list(dict.fromkeys(callees))[:4]

        if not callees:
            return ""

        hops = len(callees) + 1
        if len(callees) == 1:
            return f"{primary_return}: {start_name} → {callees[0]} ({hops} hops)"
        else:
            callees_str = ", ".join(callees[:3])
            if len(callees) > 3:
                callees_str += f" +{len(callees)-3}"
            return f"{primary_return}: {start_name} → [{callees_str}] ({hops} hops)"

    except Exception:
        return ""


def generate_summary(
    call_graph, type_deps, codebase_root, max_tokens=220, data_flow_graph=None
):
    """Generate full architectural summary using all 3 graphs."""
    lines = []

    # Header
    total_funcs = call_graph.node_count if call_graph else 0
    total_types = type_deps.node_count if type_deps else 0

    files_dict = {}
    if call_graph:
        for node_data in call_graph.nodes():
            fp = node_data.get("file_path", "unknown")
            try:
                rel = Path(fp).relative_to(codebase_root)
            except Exception:
                rel = Path(fp)
            files_dict[str(rel)] = files_dict.get(str(rel), 0) + 1

    total_files = len(files_dict)

    lines.append(
        f"[MESH v2 | {codebase_root.name} | {total_files} files | {total_funcs} funcs | {total_types} types]"
    )

    # Naming stats
    if call_graph:
        snake = camel = pascal = 0
        for node_data in call_graph.nodes():
            name = node_data.get("name", "")
            if "_" in name and name == name.lower():
                snake += 1
            elif name and name[0].islower():
                camel += 1
            elif name and name[0].isupper():
                pascal += 1

        total = snake + camel + pascal
        if total > 0:
            pct = (snake * 100) // total
            lines.append(
                f"NAMING: snake_case ({pct}%), camelCase ({camel}), PascalCase ({pascal})"
            )

    # Violations summary
    taint_violations = []
    if call_graph and data_flow_graph:
        try:
            taint_violations = detect_taint_violations(
                call_graph, data_flow_graph, codebase_root
            )
        except Exception:
            pass

    if call_graph:
        dups = detect_duplicates(call_graph)
        circs = detect_circular_calls(call_graph)
        naming = detect_naming_violations(call_graph)
        lines.append(
            f"VIOLATIONS: {len(dups)} duplicates, {len(circs)} circular, {len(naming)} naming"
        )
        if taint_violations:
            lines.append(f"TAINT: {len(taint_violations)} security issues")

    # Expanded top files (more detail)
    if files_dict:
        lines.append("")
        lines.append("TOP FILES (by functions):")
        for fp, count in sorted(files_dict.items(), key=lambda x: -x[1])[:8]:
            lines.append(f"  {fp}: {count} funcs")

    # Imports analysis
    if call_graph:
        import_counter = Counter()
        for edge in call_graph.get_all_edges():
            etype = edge.get("type", "")
            if etype == "imports":
                import_counter["imports"] += 1
        if import_counter:
            lines.append(f"IMPORT edges: {import_counter.get('imports', 0)}")

    # Top classes
    classes_dict = {}
    if type_deps:
        for node in type_deps.nodes():
            fp = node.get("file_path", "")
            try:
                rel = Path(fp).relative_to(codebase_root)
            except Exception:
                rel = Path(fp)
            key = str(rel)
            classes_dict[key] = classes_dict.get(key, 0) + 1

    if classes_dict:
        lines.append("")
        lines.append("TOP CLASSES (by count):")
        for fp, count in sorted(classes_dict.items(), key=lambda kv: -kv[1])[:3]:
            lines.append(f"  {fp}: {count}")

    # Inheritance
    if type_deps:
        lines.append("")
        lines.append("SAMPLE INHERITANCE:")
        inh_count = 0
        for node in type_deps.nodes():
            bases = node.get("bases", [])
            if bases and inh_count < 2:
                name = node.get("name", "?")
                lines.append(f"  {name} -> {', '.join(bases)}")
                inh_count += 1

    # Top called functions - expanded
    if call_graph and call_graph.edge_count > 0:
        called_counter = Counter()
        for edge in call_graph.get_all_edges():
            called_counter[edge.get("to_id", "")] += 1

        func_names = {}
        for node in call_graph.nodes():
            nid = node.get("id", "")
            func_names[nid] = node.get("name", nid[:8])

        if called_counter:
            lines.append("")
            lines.append("TOP CALLED FUNCTIONS (reusable):")
            for called_id, count in called_counter.most_common(5):
                name = func_names.get(called_id, called_id[:8])
                lines.append(f"  {name}: called {count}x")

    # TOP FLOWS section — shows actual execution paths
    flows = _extract_top_flows(call_graph)
    if flows:
        lines.append("")
        lines.append("TOP FLOWS:")
        for flow in flows[:5]:
            lines.append(f"  {flow}")

    # DATA FLOWS section — shows data pipeline chains
    if data_flow_graph and data_flow_graph.edge_count > 0:
        data_flows = _extract_data_flows(data_flow_graph)
        if data_flows:
            lines.append("")
            lines.append("DATA FLOWS:")
            for df in data_flows[:5]:
                lines.append(f"  {df}")

    # CONTROL FLOW section - shows branches, loops, async
    if call_graph:
        async_count = 0
        branch_count = 0
        loop_count = 0
        exception_count = 0
        decorators_found: dict[str, int] = {}

        for node in call_graph.nodes():
            if node.get("is_async"):
                async_count += 1
            if node.get("branches"):
                branch_count += len(node.get("branches", []))
            if node.get("loops"):
                loop_count += len(node.get("loops", []))
            if node.get("exception_handlers"):
                exception_count += len(node.get("exception_handlers", []))
            for dec in node.get("decorators", []):
                decorators_found[dec] = decorators_found.get(dec, 0) + 1

        if async_count or branch_count or loop_count or decorators_found:
            lines.append("")
            lines.append("CONTROL FLOW:")
            if async_count:
                lines.append(f"  {async_count} async functions")
            if branch_count:
                lines.append(f"  {branch_count} branch points (if/else)")
            if loop_count:
                lines.append(f"  {loop_count} loops (for/while)")
            if exception_count:
                lines.append(f"  {exception_count} exception handlers")
            if decorators_found:
                top_decs = sorted(decorators_found.items(), key=lambda x: -x[1])[:3]
                dec_str = ", ".join([f"{d}({c})" for d, c in top_decs])
                lines.append(f"  decorators: {dec_str}")

        lines.append("")
        lines.append("NOTE: Add custom sensitive patterns to .mesh/config.json")
        lines.append(
            "security_patterns: {sensitive_params: [...], sink_functions: [...]}"
        )

    # PATTERNS section
    if call_graph and codebase_root:
        pattern = _get_patterns(call_graph, codebase_root)
        if pattern != "unknown":
            lines.append(f"ARCHITECTURE: {pattern} pattern detected")

    # Directory structure breakdown
    try:
        subdirs = [
            p.name
            for p in codebase_root.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        ]
        if subdirs:
            lines.append(f"MODULES: {', '.join(sorted(subdirs)[:6])}")
    except Exception:
        pass

    # TOP VIOLATIONS section - expanded
    if call_graph:
        lines.append("")
        lines.append("TOP VIOLATIONS:")
        dups = detect_duplicates(call_graph)
        for v in dups[:5]:
            name = v.get("message", "").split("(")[0].strip()
            files = v.get("related_files", [])
            lines.append(f"  DUPLICATE: {name} in {len(files)+1} files")

        naming = detect_naming_violations(call_graph)
        for v in naming[:3]:
            msg = v.get("message", "")
            lines.append(f"  NAMING: {msg[:50]}")

        # Taint violations
        if taint_violations:
            lines.append("")
            lines.append("SECURITY (taint):")
            for tv in taint_violations[:5]:
                kind = tv.get("kind", "taint")
                msg = tv.get("message", "")[:60]
                lines.append(f"  {kind}: {msg}")

    # REUSE section
    if call_graph:
        reuse_hints = _get_reuse_hints(call_graph)
        if reuse_hints:
            lines.append("REUSE:")
            for hint in reuse_hints[:5]:
                lines.append(f"  {hint}")

    # Module dependencies summary
    if call_graph:
        lines.append("")
        lines.append("KEY DEPENDENCIES:")
        edge_types = Counter()
        for edge in call_graph.get_all_edges():
            etype = edge.get("type", "unknown")
            edge_types[etype] += 1
        for etype, count in edge_types.most_common(4):
            lines.append(f"  {etype}: {count} edges")

    summary = "\n".join(lines)

    # Target ~200 tokens
    if max_tokens and approx_tokens(summary) > max_tokens:
        summary_lines = summary.split("\n")
        truncated = []
        current_tokens = 0
        for line in summary_lines:
            line_tokens = approx_tokens(line)
            if current_tokens + line_tokens <= max_tokens:
                truncated.append(line)
                current_tokens += line_tokens
            else:
                break
        summary = "\n".join(truncated)

    return summary


def get_architectural_context(call_graph, data_flow, type_deps, codebase_root):
    """Get architectural context for AI session injection."""
    return generate_summary(
        call_graph, type_deps, codebase_root, data_flow_graph=data_flow
    )
