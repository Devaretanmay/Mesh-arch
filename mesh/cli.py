"""
CLI module for Mesh v2.0.

Features:
  - ast-grep-py for parsing (26 languages)
  - rustworkx for graphs
  - SQLite for storage
  - Multi-repo workspace support
"""

import sys
import time
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from mesh.analysis.builder import AnalysisBuilder
from mesh.analysis.workspace import WorkspaceAnalysisBuilder
from mesh.core.storage import MeshStorage
from mesh.core.workspace import get_workspace

console = Console()


@click.group()
def cli():
    """Mesh - Architectural coherence layer for AI-generated code."""
    pass


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
@click.option("--repo", multiple=True, help="Specific repo(s) to analyze")
@click.option("--force", is_flag=True, help="Force re-analysis")
def init(root, repo, force):
    """Initialize Mesh analysis on a codebase or workspace.
    
    Detects all repos in workspace and analyzes them.
    Use --repo to analyze specific repos only.
    """
    codebase_root = Path(root).resolve()

    workspace = get_workspace(codebase_root)
    
    if not workspace.repos:
        console.print("")
        console.print("  [yellow]No repositories found.[/yellow]")
        console.print("  Run in a folder containing git repositories.")
        return

    console.print("")
    console.print("-" * 40)
    console.print("  Mesh v2.0 - Initializing")
    console.print("-" * 40)
    console.print("")
    console.print(f"  Workspace: {codebase_root}")
    console.print(f"  Repos detected: {len(workspace.repos)}")
    console.print("")

    if repo:
        target_repos = [r for r in workspace.repos if r.name in repo or r.id in repo]
        if not target_repos:
            console.print(f"  [yellow]Repo(s) not found: {', '.join(repo)}[/yellow]")
            return
    else:
        target_repos = workspace.repos

    console.print(f"  Analyzing: {', '.join(r.name for r in target_repos)}")
    console.print("")

    builder = WorkspaceAnalysisBuilder(codebase_root)
    builder.detect_and_register_repos()

    for repo_info in target_repos:
        console.print(f"  Analyzing {repo_info.name}...")
        start = time.perf_counter()
        result = builder.analyze_repo(repo_info, force=force)
        elapsed = time.perf_counter() - start

        console.print(f"    Files: {result.files_analyzed}, Functions: {result.functions_found}, "
                     f"Classes: {result.classes_found}, Cross-repo: {result.cross_repo_imports} "
                     f"({elapsed:.2f}s)")

    builder._build_cross_repo_matrix()

    matrix = builder.get_repo_relationships()
    if matrix:
        console.print("")
        console.print("  Repo Relationships:")
        for repo_id, deps in matrix.items():
            if deps.get("depends_on"):
                console.print(f"    {repo_id} -> {', '.join(deps['depends_on'])}")

    builder.close()

    console.print("")
    console.print("  [green]Analysis complete![/green]")


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
def repos(root):
    """Show repository relationships and details."""
    codebase_root = Path(root).resolve()

    builder = WorkspaceAnalysisBuilder(codebase_root)
    workspace = builder.workspace

    if not workspace.repos:
        console.print("  [yellow]No repositories found.[/yellow]")
        builder.close()
        return

    table = Table(title="Repositories in Workspace")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Functions", justify="right")
    table.add_column("Classes", justify="right")
    table.add_column("Edges", justify="right")

    for repo_info in workspace.repos:
        detail = builder.get_repo_detail(repo_info.id)
        metrics = detail.get("metrics", {}) if detail else {}
        node_count = builder.storage.node_count(repo_id=repo_info.id)
        edge_count = builder.storage.edge_count(repo_id=repo_info.id)

        table.add_row(
            repo_info.name,
            repo_info.type,
            str(metrics.get("functions_found", 0)),
            str(metrics.get("classes_found", 0)),
            str(edge_count),
        )

    console.print("")
    console.print(table)

    matrix = builder.get_repo_relationships()
    if matrix:
        console.print("")
        console.print("  Dependencies:")
        for repo_id, deps in matrix.items():
            if deps.get("depends_on"):
                console.print(f"    [cyan]{repo_id}[/cyan] depends on: {', '.join(deps['depends_on'])}")

    builder.close()


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
@click.option("--repo", help="Focus on specific repo")
def context(root, repo):
    """Show complete context graph across all repos."""
    codebase_root = Path(root).resolve()

    builder = WorkspaceAnalysisBuilder(codebase_root)
    ctx = builder.get_complete_context()

    console.print("")
    console.print("-" * 40)
    console.print("  Complete Context")
    console.print("-" * 40)
    console.print("")
    console.print(f"  Repos: {ctx['stats']['total_repos']}")
    console.print(f"  Nodes: {ctx['stats']['total_nodes']}")
    console.print(f"  Edges: {ctx['stats']['total_edges']}")

    if repo:
        console.print("")
        console.print(f"  Focusing on: {repo}")
        repo_edges = [e for e in ctx["edges"] if e["from_repo"] == repo or e["to_repo"] == repo]
        cross_repo_edges = [e for e in repo_edges if e["from_repo"] != e["to_repo"]]
        
        console.print(f"  Edges involving {repo}: {len(repo_edges)}")
        console.print(f"  Cross-repo edges: {len(cross_repo_edges)}")

    builder.close()


@cli.command()
@click.option("--root", default=".", help="Codebase root directory")
def status(root):
    """Show Mesh status and statistics."""
    codebase_root = Path(root).resolve()
    
    from mesh.analysis.workspace import WorkspaceAnalysisBuilder
    from mesh.core.workspace import get_workspace

    workspace = get_workspace(codebase_root)

    console.print("")
    console.print("-" * 40)
    console.print("  Mesh Status")
    console.print("-" * 40)

    console.print(f"  Workspace: {codebase_root.name}")
    console.print(f"  Repositories: {len(workspace.repos)}")

    if workspace.repos:
        builder = WorkspaceAnalysisBuilder(codebase_root)
        
        total_nodes = 0
        total_edges = 0
        for repo in workspace.repos:
            total_nodes += builder.storage.node_count(repo_id=repo.id)
            total_edges += builder.storage.edge_count(repo_id=repo.id)

        console.print(f"  Total nodes: {total_nodes}")
        console.print(f"  Total edges: {total_edges}")

        matrix = builder.get_repo_relationships()
        cross_repo = sum(len(d.get("depends_on", [])) for d in matrix.values())
        if cross_repo > 0:
            console.print(f"  Cross-repo edges: {cross_repo}")

        builder.close()
    else:
        console.print("  Run 'mesh init' to analyze repositories")

    from mesh.llm import is_model_downloaded, get_model_size_mb

    console.print("")
    if is_model_downloaded():
        size = get_model_size_mb()
        console.print(f"  LLM Model: Downloaded ({size}MB)")
    else:
        console.print("  LLM Model: Not downloaded")
        console.print("  Run 'mesh download-model' to download")


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
@click.option("--repo", help="Specific repo to query (for workspaces)")
def ask(question, root, repo):
    """Ask a natural language question about your codebase.

    Examples:

      mesh ask "how does authentication work?"

      mesh ask "what calls send_email?"

      mesh ask "how do the verification flows differ?"

      mesh ask "auth in adminv3" --repo adminv3

    Requires: Download the model first with 'mesh download-model'
    """
    from mesh.llm.explainer import explain_query
    from mesh.llm import is_model_downloaded

    if not is_model_downloaded():
        console.print("")
        console.print("  [yellow]Model not downloaded.[/yellow]")
        console.print("  Run 'mesh download-model' first.")
        return

    root_path = Path(root).resolve()

    console.print(f"\n[dim]Analysing: {question}[/dim]")

    answer = explain_query(question, root_path, repo_id=repo)

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
