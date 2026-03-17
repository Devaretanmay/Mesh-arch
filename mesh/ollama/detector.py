"""
Ollama auto-detection and model discovery.

Detects Ollama installation and lists all installed models.
No configuration required — reads from Ollama's local API.
"""

import json
import shutil
import socket
import urllib.request
from dataclasses import dataclass
from typing import Optional

OLLAMA_API_BASE = "http://localhost:11434"
OLLAMA_TAGS_ENDPOINT = f"{OLLAMA_API_BASE}/api/tags"


@dataclass(frozen=True, slots=True)
class OllamaModel:
    """Represents an installed Ollama model.

    Attributes:
        name: Model name e.g. "qwen3.5:9b"
        family: Model family e.g. "qwen3.5"
        size_bytes: Raw size in bytes
        size_gb: Human readable size
        compatibility: "excellent" | "good" | "partial" | "unknown"
        compatibility_reason: Explanation of rating
        supports_thinking: Whether model supports thinking mode
        is_instruction_tuned: Whether model is instruction tuned
    """

    name: str
    family: str
    size_bytes: int
    size_gb: float
    compatibility: str
    compatibility_reason: str
    supports_thinking: bool
    is_instruction_tuned: bool


@dataclass
class OllamaStatus:
    """Ollama installation and runtime status.

    Attributes:
        is_installed: Whether ollama binary exists
        is_running: Whether ollama serve is running
        models: List of installed models with compatibility ratings
        install_url: URL to download Ollama
        error: Optional error message
    """

    is_installed: bool
    is_running: bool
    models: list[OllamaModel]
    install_url: str = "https://ollama.com/download"
    error: Optional[str] = None


def detect_ollama() -> OllamaStatus:
    """Detects Ollama installation status and lists installed models.

    Returns:
        OllamaStatus with installation and model information.
    """
    is_installed = shutil.which("ollama") is not None

    if not is_installed:
        return OllamaStatus(
            is_installed=False,
            is_running=False,
            models=[],
            error="Ollama not found. Install from https://ollama.com/download",
        )

    is_running = _check_ollama_running()

    if not is_running:
        return OllamaStatus(
            is_installed=True,
            is_running=False,
            models=[],
            error="Ollama is installed but not running. Run: ollama serve",
        )

    models = _list_installed_models()

    return OllamaStatus(
        is_installed=True,
        is_running=True,
        models=models,
    )


def _check_ollama_running() -> bool:
    """Check if Ollama API is reachable.

    Returns:
        True if Ollama service is running on port 11434.
    """
    try:
        sock = socket.create_connection(("localhost", 11434), timeout=2)
        sock.close()
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def _list_installed_models() -> list[OllamaModel]:
    """Fetch installed models from Ollama API.

    Returns:
        List of OllamaModel objects sorted by compatibility.
    """
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_ENDPOINT, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except Exception:
        return []

    models = []
    for m in data.get("models", []):
        name = m.get("name", "")
        size_bytes = m.get("size", 0)
        compatibility, reason, thinking, instruct = _rate_model(name)
        models.append(
            OllamaModel(
                name=name,
                family=name.split(":")[0],
                size_bytes=size_bytes,
                size_gb=round(size_bytes / 1e9, 1),
                compatibility=compatibility,
                compatibility_reason=reason,
                supports_thinking=thinking,
                is_instruction_tuned=instruct,
            )
        )

    # Sort: excellent first, then good, then partial, then unknown
    order = {"excellent": 0, "good": 1, "partial": 2, "unknown": 3}
    return sorted(models, key=lambda m: order.get(m.compatibility, 3))


def _rate_model(name: str) -> tuple[str, str, bool, bool]:
    """Rate a model's compatibility with Mesh.

    Args:
        name: Model name to rate.

    Returns:
        Tuple of (compatibility, reason, supports_thinking, is_instruction_tuned).

    Rating criteria:
        - excellent: known instruction-tuned coding model
        - good: instruction-tuned general model
        - partial: base model or limited instruction following
        - unknown: unrecognised model family
    """
    name_lower = name.lower()

    # Excellent — known strong instruction following + coding
    excellent_families = [
        "qwen3.5",
        "qwen3",
        "qwen2.5-coder",
        "deepseek-coder",
        "deepseek-r1",
        "codestral",
        "codegemma",
    ]
    for family in excellent_families:
        if family in name_lower:
            thinking = "qwen" in name_lower
            return (
                "excellent",
                "Strong instruction following and coding capability",
                thinking,
                True,
            )

    # Good — general instruction-tuned models
    good_families = [
        "llama3",
        "llama3.1",
        "llama3.2",
        "llama3.3",
        "mistral",
        "mixtral",
        "phi3",
        "phi4",
        "gemma2",
        "gemma3",
        "command-r",
    ]
    for family in good_families:
        if family in name_lower:
            return (
                "good",
                "Good instruction following, adequate for Mesh",
                False,
                True,
            )

    # Partial — base models or limited instruction following
    partial_signals = [":base", "-base", "uncensored"]
    for signal in partial_signals:
        if signal in name_lower:
            return (
                "partial",
                "Base model — may not follow architectural constraints",
                False,
                False,
            )

    # Unknown
    return (
        "unknown",
        "Unrecognised model — compatibility not guaranteed",
        False,
        False,
    )


def get_recommended_model(models: list[OllamaModel]) -> Optional[OllamaModel]:
    """Returns the best available model for Mesh.

    Prefers qwen3.5:9b if available, otherwise best rated model.

    Args:
        models: List of available OllamaModel objects.

    Returns:
        Best OllamaModel or None if list is empty.
    """
    # Check for preferred model first
    preferred = ["qwen3.5:9b", "qwen3.5:latest", "qwen3:8b"]
    for pref in preferred:
        for m in models:
            if m.name == pref:
                return m

    # Otherwise return first excellent or good model
    for compat in ["excellent", "good"]:
        for m in models:
            if m.compatibility == compat:
                return m

    return models[0] if models else None


@dataclass
class HardwareSpec:
    """Detected hardware specifications."""

    os: str  # "darwin", "linux", "windows"
    arch: str  # "arm64", "x86_64"
    ram_gb: float
    has_nvidia: bool
    has_metal: bool  # Apple Silicon
    gpu_name: str | None

    @property
    def tier(self) -> str:
        """Determine hardware tier for model recommendations."""
        if self.has_nvidia:
            return "high"
        if self.has_metal:
            if self.ram_gb >= 16:
                return "high"
            elif self.ram_gb >= 8:
                return "medium"
            return "low"
        # No GPU
        return "cloud_only"


def detect_hardware() -> HardwareSpec:
    """Auto-detect hardware specifications.

    Returns:
        HardwareSpec with detected specs and tier.
    """
    import platform
    import subprocess

    os_name = platform.system().lower()
    arch = platform.machine()

    # Detect RAM
    try:
        import psutil

        ram_bytes = psutil.virtual_memory().total
        ram_gb = ram_bytes / (1024**3)
    except Exception:
        ram_gb = 8.0  # default assumption

    # Detect GPU
    has_nvidia = False
    has_metal = False
    gpu_name = None

    # Check for NVIDIA
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            has_nvidia = True
            gpu_name = result.stdout.strip().split("\n")[0]
    except Exception:
        pass

    # Check for Apple Silicon (Metal)
    if os_name == "darwin":
        try:
            import torch

            if torch.backends.mps.is_available():
                has_metal = True
                gpu_name = "Apple Silicon"
        except Exception:
            pass

    return HardwareSpec(
        os=os_name,
        arch=arch,
        ram_gb=round(ram_gb, 1),
        has_nvidia=has_nvidia,
        has_metal=has_metal,
        gpu_name=gpu_name,
    )


# Model recommendations by tier
MODEL_RECOMMENDATIONS = {
    "low": {
        "local": [
            ("phi3:3.8b", "2.3GB", "Basic but fast"),
            ("llama3.2:3b", "2GB", "Fast & capable"),
            ("phi3:4b", "2.3GB", "Microsoft's small model"),
        ],
        "cloud": [
            ("glm-5:cloud", "Instant", "Best for speed"),
            ("qwen3.5:cloud", "Fast", "Good reasoning"),
        ],
    },
    "medium": {
        "local": [
            ("llama3.2:7b", "4GB", "Recommended ★"),
            ("qwen2.5:7b", "4.7GB", "Great for code"),
            ("phi3:14b", "8GB", "More capable"),
        ],
        "cloud": [
            ("glm-5:cloud", "Instant", "Best for speed"),
            ("qwen3.5:cloud", "Fast", "Good reasoning"),
        ],
    },
    "high": {
        "local": [
            ("qwen2.5:14b", "9GB", "Recommended ★"),
            ("llama3.1:8b", "5GB", "Meta's best"),
            ("qwen2.5:7b", "4.7GB", "Great for code"),
        ],
        "cloud": [
            ("glm-5:cloud", "Instant", "Best for speed"),
            ("qwen3.5:cloud", "Fast", "Good reasoning"),
        ],
    },
    "cloud_only": {
        "local": [],
        "cloud": [
            ("glm-5:cloud", "Recommended ★", "No local GPU needed"),
            ("qwen3.5:cloud", "Fast", "Good reasoning"),
            ("minimax-m2.5:cloud", "Excellent", "Top reasoning"),
        ],
    },
}


def get_model_recommendations(
    hardware: HardwareSpec,
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Get recommended local and cloud models for hardware.

    Args:
        hardware: Detected hardware specs.

    Returns:
        Tuple of (local_models, cloud_models) with (name, size, reason).
    """
    tier = hardware.tier
    recs = MODEL_RECOMMENDATIONS.get(tier, MODEL_RECOMMENDATIONS["cloud_only"])
    return recs["local"], recs["cloud"]
