"""
Ollama-backed inference server for Mesh.

Reads model config from .mesh/config.json.
Uses the Ollama Python SDK for inference.
Handles thinking mode for compatible models.
"""

import json
from pathlib import Path
from typing import Optional

MESH_SYSTEM_PROMPT = """You are a coding assistant with deep architectural awareness of this specific codebase.

When you see [MESH CONTEXT] in a message, treat everything inside it as authoritative architectural constraints. You MUST:
- Never create functions that already exist (check MODULES section)
- Follow the naming convention exactly (check NAMING section)
- Respect module boundaries (check CONSTRAINTS section)
- Use existing patterns not new ones (check PATTERNS section)
- Never introduce circular dependencies

Violating these constraints produces architecturally broken code.
Follow them precisely. The MESH CONTEXT is ground truth."""

THINKING_TRIGGER_KEYWORDS = [
    "new module",
    "refactor",
    "add service",
    "create class",
    "authentication",
    "database",
    "payment",
    "middleware",
    "architecture",
    "redesign",
    "extract",
    "reorganise",
    "circular",
    "dependency",
    "interface",
    "abstract",
]


class OllamaInferenceServer:
    """Provides code generation using the user's installed Ollama model.

    Loads model config from .mesh/config.json.
    Falls back gracefully if Ollama is unavailable.
    """

    def __init__(self, codebase_root: Path):
        """Initialize the inference server.

        Args:
            codebase_root: Root directory of the codebase.
        """
        self.codebase_root = codebase_root
        self.config = self._load_config()
        self._ollama_available: Optional[bool] = None

    def _load_config(self) -> dict:
        """Load model config from .mesh/config.json.

        Returns:
            Config dict or empty dict if not found.
        """
        config_path = self.codebase_root / ".mesh" / "config.json"
        if not config_path.exists():
            return {}
        try:
            return json.loads(config_path.read_text())
        except (json.JSONDecodeError, IOError):
            return {}

    @property
    def model_name(self) -> Optional[str]:
        """Get configured model name."""
        return self.config.get("model")

    @property
    def supports_thinking(self) -> bool:
        """Check if configured model supports thinking mode."""
        return self.config.get("supports_thinking", False)

    def is_available(self) -> bool:
        """Check if Ollama is running and model is accessible.

        Returns:
            True if Ollama and model are available.
        """
        if self._ollama_available is not None:
            return self._ollama_available

        if not self.model_name:
            self._ollama_available = False
            return False

        try:
            import ollama

            ollama.show(self.model_name)
            self._ollama_available = True
        except Exception:
            self._ollama_available = False

        return self._ollama_available

    def generate(
        self,
        user_request: str,
        arch_context: str,
        timeout_seconds: int = 60,
    ) -> str:
        """Generate code using the configured Ollama model.

        Injects architectural context as structured system prompt.
        Enables thinking mode for architecturally complex requests.

        Args:
            user_request: User's coding request.
            arch_context: Architectural context from GAT encoder.
            timeout_seconds: Generation timeout.

        Returns:
            Generated code text.

        Raises:
            OllamaUnavailable: If model is not accessible.
            OllamaGenerationFailed: If generation fails.
        """
        if not self.is_available():
            raise OllamaUnavailable(
                f"Model {self.model_name!r} not available. Run: mesh setup"
            )

        import ollama

        use_thinking = self.supports_thinking and self._is_complex_request(user_request)

        messages = [
            {"role": "system", "content": MESH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"[MESH CONTEXT]\n{arch_context}\n[/MESH CONTEXT]\n\n"
                    f"{user_request}"
                ),
            },
        ]

        options = {
            "temperature": 0.2,
            "num_ctx": 8192,
        }

        if use_thinking:
            # Qwen3.5 thinking mode — add think tag
            messages[-1]["content"] = "/think\n" + messages[-1]["content"]

        try:
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                options=options,
                timeout=timeout_seconds,
            )
            return response.message.content
        except Exception as e:
            raise OllamaGenerationFailed(f"Generation failed: {e}") from e

    def _is_complex_request(self, request: str) -> bool:
        """Detect if a request is architecturally complex.

        Complex requests get thinking mode if supported.

        Args:
            request: User request text.

        Returns:
            True if request is architecturally complex.
        """
        request_lower = request.lower()
        return any(kw in request_lower for kw in THINKING_TRIGGER_KEYWORDS)


class OllamaUnavailable(Exception):
    """Raised when Ollama or configured model is not accessible."""

    pass


class OllamaGenerationFailed(Exception):
    """Raised when Ollama generation fails."""

    pass
