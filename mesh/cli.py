"""
CLI module for Mesh v2.0.

Rewired to use new core:
  - ast-grep-py for parsing (26 languages)
  - rustworkx for graphs
  - SQLite for storage
"""

import sys
import time
from pathlib import Path

import click
from rich.console import Console

from mesh.analysis.builder import AnalysisBuilder
from mesh.core.storage import MeshStorage

console = Console()


@click.group()
def cli():
    """Mesh - Architectural coherence layer for AI-generated code."""
    pass


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
def init(root):
    """Initialize Mesh analysis on a codebase."""
    codebase_root = Path(root).resolve()

    console.print("")
    console.print("-" * 40)
    console.print("  Mesh v2.0 - Initializing")
    console.print("-" * 40)
    console.print("")

    builder = AnalysisBuilder(codebase_root)

    console.print(f"  Root: {codebase_root}")
    console.print("  Parsing: ast-grep (26 languages)")
    console.print("  Graph: rustworkx")
    console.print("  Storage: SQLite")
    console.print("")

    console.print("  Running analysis...")
    start = time.perf_counter()
    result = builder.run_full_analysis()
    elapsed = time.perf_counter() - start

    console.print("")
    console.print(f"  Analysis complete in {elapsed:.2f}s")
    console.print(f"    Files:     {result.files_analyzed}")
    console.print(f"    Functions: {result.functions_found}")
    console.print(f"    Edges:    {result.edges_created}")

    from mesh.core.parser import LANGUAGE_MAP

    extensions = {}
    for f in codebase_root.rglob("*"):
        if f.is_file() and not builder._parser.should_skip(f, codebase_root):
            ext = f.suffix.lower()
            if ext in LANGUAGE_MAP:
                extensions[ext] = extensions.get(ext, 0) + 1

    if extensions:
        console.print("")
        console.print("  Languages detected:")
        for ext, count in sorted(extensions.items(), key=lambda x: -x[1])[:10]:
            lang = LANGUAGE_MAP.get(ext, ext)
            console.print(f"    {lang:15} {count:5} files")

    builder.close()


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
def status(root):
    """Show Mesh status and statistics."""
    codebase_root = Path(root).resolve()
    storage = MeshStorage(codebase_root)

    console.print("")
    console.print("-" * 40)
    console.print("  Mesh Status")
    console.print("-" * 40)

    if storage.graphs_exist():
        node_count = storage.node_count()
        edge_count = storage.edge_count()
        console.print(f"  Graph nodes: {node_count}")
        console.print(f"  Graph edges: {edge_count}")
    else:
        console.print("  Run 'mesh init' to analyze a codebase")

    from mesh.llm import is_model_downloaded, get_model_size_mb

    console.print("")
    if is_model_downloaded():
        size = get_model_size_mb()
        console.print(f"  LLM Model: Downloaded ({size}MB)")
    else:
        console.print("  LLM Model: Not downloaded")
        console.print("  Run 'mesh download-model' to download")

    storage.close()


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
@click.option("--report", is_flag=True, help="Generate CTO governance report")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def doctor(root: str, report: bool, json_output: bool) -> None:
    """Comprehensive health check for Mesh."""
    from datetime import datetime

    codebase_root = Path(root).resolve()
    storage = MeshStorage(codebase_root)

    if not storage.graphs_exist():
        console.print("  Run 'mesh init' first")
        storage.close()
        return

    console.print("")
    console.print("-" * 40)
    console.print("  Mesh Health Check")
    console.print("-" * 40)
    console.print("")

    console.print("  Graphs built")
    console.print("  Storage available")

    if report:
        console.print("")
        console.print("-" * 40)
        console.print("  Mesh Governance Report")
        console.print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        console.print("-" * 40)

        nodes = storage.get_nodes()
        edges = storage.get_edges()

        console.print("")
        console.print("  SUMMARY")
        console.print("  " + "-" * 20)
        console.print(f"  Codebase:     {codebase_root.name}")
        console.print(f"  Functions:    {len(nodes)}")
        console.print(f"  Dependencies: {len(edges)}")

        files: dict = {}
        for n in nodes:
            fp = n.get("file_path", "unknown")
            files[fp] = files.get(fp, 0) + 1

        console.print("")
        console.print("  TOP FILES BY FUNCTION COUNT")
        for fp, count in sorted(files.items(), key=lambda x: -x[1])[:5]:
            console.print(f"    {fp}: {count}")

    storage.close()


@cli.command()
@click.option("--root", default=".", help="Codebase root")
def serve(root):
    """Start MCP server for Cursor and Claude Code integration."""
    from mesh.mcp.server import create_server

    codebase_root = Path(root).resolve()
    server = create_server(codebase_root)
    server.start()


@cli.command()
def setup():
    """Download LLM model and configure Mesh."""
    from mesh.llm import download_model, is_model_downloaded

    if is_model_downloaded():
        console.print("  Model already downloaded.")
        return

    console.print("")
    console.print("  Downloading Qwen2.5-Coder-1.5B-Instruct-GGUF...")
    console.print("  This may take a few minutes...")

    success = download_model()

    if success:
        console.print("")
        console.print("  [green]Model downloaded successfully![/green]")
    else:
        console.print("")
        console.print("  [red]Download failed. Run 'mesh download-model' to retry.[/red]")


@cli.command()
@click.argument("question")
@click.option("--root", default=".", help="Codebase root")
def ask(question, root):
    """Ask a natural language question about your codebase.

    Examples:

      mesh ask "how does authentication work?"

      mesh ask "what calls send_email?"

      mesh ask "how do the verification flows differ?"

    Requires: Download the model first with 'mesh download-model'
    """
    from mesh.llm.explainer import explain_query

    root_path = Path(root).resolve()

    console.print(f"\n[dim]Analysing: {question}[/dim]")

    answer = explain_query(question, root_path)

    console.print(answer)
    console.print()


@cli.command()
def download_model():
    """Download the Qwen2.5-Coder-1.5B model for local inference."""
    from mesh.llm import download_model, is_model_downloaded

    if is_model_downloaded():
        console.print("  Model already downloaded.")
        return

    console.print("")
    console.print("  Downloading Qwen2.5-Coder-1.5B-Instruct-GGUF...")
    console.print("  This may take a few minutes...")

    success = download_model()

    if success:
        console.print("")
        console.print("  [green]Model downloaded successfully![/green]")
    else:
        console.print("")
        console.print("  [red]Download failed. Run 'mesh download-model' to retry.[/red]")


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
@click.option(
    "--pre-commit",
    is_flag=True,
    help="Run in pre-commit mode (exit non-zero on violations)",
)
@click.option(
    "--strict", is_flag=True, help="Check entire codebase, not just staged files"
)
def check(root, pre_commit, strict):
    """Check code for architectural violations."""
    from mesh.enforcement.checker import ViolationChecker

    codebase_root = Path(root).resolve()

    if not (codebase_root / ".git").exists():
        console.print("  Not a git repository")
        return

    checker = ViolationChecker(codebase_root)
    result = checker.check_staged(strict=strict)

    if result.is_clean:
        console.print("  No violations found")
    else:
        console.print(f"  Found {len(result.violations)} violation(s)")
        for v in result.violations[:10]:
            console.print(f"    {v.severity}: {v.message} ({v.file_path})")

    if pre_commit:
        sys.exit(0 if result.is_clean else 1)


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
def install_hook(root):
    """Install git pre-commit hook."""
    from mesh.enforcement.hook import HookManager

    codebase_root = Path(root).resolve()
    manager = HookManager(codebase_root)
    result = manager.install_hook()

    if result["success"]:
        console.print(f"  {result['message']}")
    else:
        console.print(f"  {result['message']}")


@cli.command()
@click.option("--token", help="GitHub Personal Access Token")
def login(token):
    """Authenticate with GitHub using a Personal Access Token.

    Get a token from: https://github.com/settings/tokens
    Required scope: read:user
    """
    from mesh.auth.tier import get_detector

    if not token:
        console.print("")
        console.print("[yellow]Enter your GitHub Personal Access Token:[/yellow]")
        console.print("[dim]Get one at: https://github.com/settings/tokens[/dim]")
        console.print("[dim]Required scope: read:user[/dim]")
        token = click.prompt("", type=str, hide_input=True)

    if not token.startswith(("ghp_", "github_pat_")):
        console.print("[red]Error: Token must start with 'ghp_' or 'github_pat_'[/red]")
        return

    console.print("")
    console.print("  Authenticating with GitHub...")

    detector = get_detector()
    success, tier, message = detector.detect_and_save(token)

    if success:
        console.print("")
        console.print(f"  [green]Success![/green] {message}")
        console.print("  All features unlocked.")
    else:
        console.print(f"  [red]Failed: {message}[/red]")


@cli.command()
def logout():
    """Clear stored GitHub authentication."""
    from mesh.auth.tier import get_detector

    detector = get_detector()
    detector.logout()

    console.print("")
    console.print("  [green]Logged out successfully[/green]")
    console.print("  Authentication cleared.")


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
