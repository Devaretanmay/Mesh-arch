"""
Interactive setup wizard for Mesh.

Guides the developer through:
1. Codebase analysis (Phase 1)
2. Ollama detection and installation
3. Model selection from installed models
4. MCP server registration with Cursor/Claude Code
5. Saves config to .mesh/config.json
"""

import json
import subprocess
import time
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.prompt import IntPrompt, Prompt

from mesh.core.storage import MeshStorage
from mesh.ollama.detector import (
    OllamaModel,
    OllamaStatus,
    detect_hardware,
    detect_ollama,
    get_model_recommendations,
)

console = Console()


class SetupAborted(Exception):
    """Raised when setup is cancelled or cannot complete."""

    pass


def run_setup_wizard(codebase_root: Path) -> dict:
    """Run the full interactive setup wizard.

    Args:
        codebase_root: Root directory of the codebase.

    Returns:
        The saved config dict on success.

    Raises:
        SetupAborted: If user cancels or setup cannot complete.
    """
    console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
    console.print("[bold cyan]  Mesh Setup Wizard[/bold cyan]")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")

    # Step 1: Verify codebase is analysed
    _step_verify_codebase(codebase_root)

    # Step 2: Check/install Ollama
    status = _step_check_ollama()

    # Step 3: Select model
    selected_model = _step_select_model(status)

    # Step 4: Register with editors
    _step_register_editors(codebase_root)

    # Step 5: Save config
    config = _save_config(codebase_root, selected_model)

    # Done
    _print_success(selected_model)

    return config


def _step_verify_codebase(codebase_root: Path) -> None:
    """Verify mesh init has been run.

    Args:
        codebase_root: Root directory of the codebase.
    """
    console.print("[bold]Step 1/4:[/bold] Checking codebase analysis...")

    storage = MeshStorage(codebase_root)
    if not storage.graphs_exist():
        console.print("  [yellow]⚠ Codebase not analysed yet.[/yellow]")
        console.print("  Running mesh init...")
        # Import and run init
        from mesh.cli import init

        init.callback(root=str(codebase_root))
    else:
        call_graph = storage.load_call_graph()
        console.print(
            f"  [green]✓[/green] "
            f"{len(call_graph.nodes())} functions | "
            f"{len(call_graph.edges())} dependencies"
        )


def _step_check_ollama() -> OllamaStatus:
    """Check Ollama installation, guide install if missing.

    Returns:
        OllamaStatus with installation and model information.

    Raises:
        SetupAborted: If Ollama cannot be installed or started.
    """
    console.print("\n[bold]Step 2/4:[/bold] Checking for Ollama...")

    status = detect_ollama()

    if not status.is_installed:
        console.print("  [yellow]✗ Ollama not found.[/yellow]")
        console.print("\n  Ollama runs AI models locally.")
        console.print("  Install it from: [link]https://ollama.com/download[/link]")
        console.print("\n  Opening download page...")
        webbrowser.open("https://ollama.com/download")
        Prompt.ask("\n  Press Enter when Ollama is installed")
        status = detect_ollama()
        if not status.is_installed:
            console.print(
                "[red]  Ollama still not found. "
                "Please install and run 'mesh setup' again.[/red]"
            )
            raise SetupAborted("Ollama not installed")

    if not status.is_running:
        console.print("  [yellow]⚠ Ollama installed but not running.[/yellow]")
        console.print("  Starting Ollama...")
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)
        status = detect_ollama()
        if not status.is_running:
            console.print(
                "[red]  Could not start Ollama. "
                "Run 'ollama serve' in another terminal.[/red]"
            )
            raise SetupAborted("Ollama not running")

    console.print("  [green]✓[/green] Ollama running")

    if not status.models:
        console.print("\n  [yellow]No models installed yet.[/yellow]")
        console.print("  Recommended: [bold]ollama pull qwen3.5:9b[/bold]")
        console.print("  Smaller option: [bold]ollama pull qwen3.5:4b[/bold]")
        Prompt.ask("\n  Install a model then press Enter")
        status = detect_ollama()
        if not status.models:
            raise SetupAborted("No models installed")

    return status


def _step_select_model(status: OllamaStatus) -> OllamaModel:
    """Display model table with hardware detection and let user select.

    Args:
        status: OllamaStatus with installed models.

    Returns:
        Selected OllamaModel.

    Raises:
        SetupAborted: If no valid model is selected.
    """
    # Step 1: Detect hardware
    console.print("\n[bold]Step 3/4:[/bold] Selecting AI model...")
    console.print("  Detecting hardware...")

    hardware = detect_hardware()

    # Step 2: Show hardware info
    gpu_info = hardware.gpu_name or "None"
    if hardware.has_metal:
        gpu_info = "Apple Silicon"

    console.print(f"  🖥️  [bold]Hardware:[/bold] {hardware.ram_gb}GB RAM, {gpu_info}")
    console.print(f"  📊 [bold]Tier:[/bold] {hardware.tier.upper()}\n")

    # Step 3: Get recommendations
    local_recs, cloud_recs = get_model_recommendations(hardware)

    # Step 4: Check what's actually installed
    installed_names = {m.name for m in status.models}

    # Find which recommended local models are actually installed
    available_local = []
    for name, size, reason in local_recs:
        if name in installed_names:
            available_local.append((name, size, reason + " (installed)"))

    # If nothing installed, show what's available to download
    if not available_local:
        for name, size, reason in local_recs:
            available_local.append(
                (name, size, reason + " (run: ollama pull " + name.split(":")[0] + ")")
            )

    # Cloud models are always available
    available_cloud = []
    for name, size, reason in cloud_recs:
        available_cloud.append((name, size, reason))

    # Build selection menu
    options = []

    console.print("[bold]📦 LOCAL MODELS[/bold] (run offline, needs hardware)")
    console.print("─" * 50)

    if available_local:
        for i, (name, size, reason) in enumerate(available_local, 1):
            console.print(f"  {i}. {name:20} {size:>6}  {reason}")
            options.append(("local", name))
    else:
        console.print(
            "  [dim]No local models detected. Install with: ollama pull <model>[/dim]"
        )

    console.print("\n[bold]☁️  CLOUD MODELS[/bold] (fast, no local resources)")
    console.print("─" * 50)

    for i_offset, (name, size, reason) in enumerate(
        available_cloud, len(available_local) + 1
    ):
        console.print(f"  {i_offset}. {name:20} {size:>6}  {reason}")
        options.append(("cloud", name))

    console.print()

    # Get user choice
    max_choice = len(options)
    if max_choice == 0:
        console.print(
            "  [yellow]No models available. Please install Ollama and pull a model.[/yellow]"
        )
        console.print("  [dim]Visit: https://ollama.com/download[/dim]")
        raise SetupAborted("No models available")

    default = 1
    # Default to first cloud model for speed
    for i, (model_type, name) in enumerate(options, 1):
        if model_type == "cloud" and "glm" in name:
            default = i
            break

    choice = IntPrompt.ask(
        "  Select model",
        default=default,
        choices=[str(i) for i in range(1, max_choice + 1)],
    )

    selected_type, selected_name = options[choice - 1]

    console.print(f"\n  [green]✓[/green] Selected [bold]{selected_name}[/bold]")

    # Find or create the OllamaModel
    for m in status.models:
        if m.name == selected_name:
            return m

    # If cloud model not in list, create a temporary one
    return OllamaModel(
        name=selected_name,
        family=selected_name.split(":")[0],
        size_bytes=0,
        size_gb=0,
        compatibility="excellent",
        compatibility_reason="Cloud model",
        supports_thinking=False,
        is_instruction_tuned=True,
    )


def _step_register_editors(codebase_root: Path) -> None:
    """Register MCP server with Cursor and Claude Code.

    Args:
        codebase_root: Root directory of the codebase.
    """
    console.print("\n[bold]Step 4/4:[/bold] Registering with editors...")

    cursor_config = codebase_root / ".cursor" / "mcp.json"
    claude_config = Path.home() / ".claude" / "mcp.json"

    registered = []

    # Cursor
    _write_mcp_config(cursor_config)
    registered.append("Cursor")

    # Claude Code
    _write_mcp_config(claude_config)
    registered.append("Claude Code")

    for editor in registered:
        console.print(f"  [green]✓[/green] {editor} registered")


def _write_mcp_config(config_path: Path) -> None:
    """Write or merge mesh MCP server config.

    Args:
        config_path: Path to config file.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)

    mesh_entry = {
        "mesh": {
            "command": "mesh",
            "args": ["serve"],
            "env": {},
        }
    }

    if config_path.exists():
        try:
            existing = json.loads(config_path.read_text())
            if "mcpServers" not in existing:
                existing["mcpServers"] = {}
            existing["mcpServers"].update(mesh_entry)
            config_path.write_text(json.dumps(existing, indent=2))
        except (json.JSONDecodeError, KeyError):
            # Corrupted config — write fresh
            config_path.write_text(json.dumps({"mcpServers": mesh_entry}, indent=2))
    else:
        config_path.write_text(json.dumps({"mcpServers": mesh_entry}, indent=2))


def _save_config(codebase_root: Path, model: OllamaModel) -> dict:
    """Save selected model to .mesh/config.json.

    Args:
        codebase_root: Root directory of the codebase.
        model: Selected OllamaModel.

    Returns:
        Saved config dict.
    """
    config_path = codebase_root / ".mesh" / "config.json"

    # Load existing config if present
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except json.JSONDecodeError:
            config = {}
    else:
        config = {}

    config.update(
        {
            "model": model.name,
            "model_family": model.family,
            "provider": "ollama",
            "supports_thinking": model.supports_thinking,
            "is_instruction_tuned": model.is_instruction_tuned,
            "compatibility": model.compatibility,
        }
    )

    config_path.write_text(json.dumps(config, indent=2))
    return config


def _print_success(model: OllamaModel) -> None:
    """Print success message.

    Args:
        model: Selected OllamaModel.
    """
    console.print("\n[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]")
    console.print("[bold green]  ✓ Mesh is ready.[/bold green]")
    console.print("[bold]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/bold]\n")
    console.print(f"  Model:  [bold]{model.name}[/bold]")
    console.print(f"  Rating: {model.compatibility}")
    console.print("\n  [dim]Start the MCP server:[/dim]")
    console.print("    [bold]mesh serve[/bold]")
    console.print("\n  [dim]Then open Cursor — architectural context[/dim]")
    console.print("  [dim]will be injected automatically.[/dim]\n")
