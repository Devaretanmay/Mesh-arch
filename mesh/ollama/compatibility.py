"""
Model compatibility ratings for Mesh.

Provides detailed compatibility analysis for Ollama models
with Mesh's architectural context injection system.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CompatibilityReport:
    """Compatibility report for a model.

    Attributes:
        model_name: Name of the model
        compatibility: "excellent" | "good" | "partial" | "unknown"
        score: Numeric score 0-100
        reasoning: Detailed explanation
        supports_thinking: Whether model supports thinking mode
        is_instruction_tuned: Whether model is instruction tuned
        recommended_for_production: Whether suitable for production
        notes: Additional notes or warnings
    """

    model_name: str
    compatibility: str
    score: int
    reasoning: str
    supports_thinking: bool
    is_instruction_tuned: bool
    recommended_for_production: bool
    notes: str = ""


# Known model families with their compatibility ratings
MODEL_FAMILIES = {
    # Excellent — known strong instruction following + coding
    "qwen3.5": {
        "compatibility": "excellent",
        "score": 95,
        "supports_thinking": True,
        "is_instruction_tuned": True,
        "notes": "Best overall for Mesh. Strong architectural constraint following.",
    },
    "qwen3": {
        "compatibility": "excellent",
        "score": 93,
        "supports_thinking": True,
        "is_instruction_tuned": True,
        "notes": "Excellent coding model with thinking mode.",
    },
    "qwen2.5-coder": {
        "compatibility": "excellent",
        "score": 92,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Specialized coding model, excellent constraint following.",
    },
    "deepseek-coder": {
        "compatibility": "excellent",
        "score": 90,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Strong coding capabilities, good architectural awareness.",
    },
    "deepseek-r1": {
        "compatibility": "excellent",
        "score": 91,
        "supports_thinking": True,
        "is_instruction_tuned": True,
        "notes": "Reasoning model with strong coding abilities.",
    },
    "codestral": {
        "compatibility": "excellent",
        "score": 89,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Mistral's coding model, excellent for Mesh.",
    },
    "codegemma": {
        "compatibility": "excellent",
        "score": 88,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Google's coding model, good constraint following.",
    },
    # Good — general instruction-tuned models
    "llama3.3": {
        "compatibility": "good",
        "score": 82,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Latest Llama, good general purpose model.",
    },
    "llama3.2": {
        "compatibility": "good",
        "score": 80,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Efficient Llama variant.",
    },
    "llama3.1": {
        "compatibility": "good",
        "score": 80,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Solid instruction following.",
    },
    "llama3": {
        "compatibility": "good",
        "score": 78,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Original Llama 3, still capable.",
    },
    "mistral": {
        "compatibility": "good",
        "score": 79,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Mistral's flagship model.",
    },
    "mixtral": {
        "compatibility": "good",
        "score": 81,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "MoE architecture, good performance.",
    },
    "phi4": {
        "compatibility": "good",
        "score": 77,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Microsoft's compact model.",
    },
    "phi3": {
        "compatibility": "good",
        "score": 75,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Efficient small model.",
    },
    "gemma3": {
        "compatibility": "good",
        "score": 76,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Google's latest Gemma.",
    },
    "gemma2": {
        "compatibility": "good",
        "score": 74,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Previous Gemma generation.",
    },
    "command-r": {
        "compatibility": "good",
        "score": 78,
        "supports_thinking": False,
        "is_instruction_tuned": True,
        "notes": "Cohere's command model.",
    },
}


def get_compatibility_report(model_name: str) -> CompatibilityReport:
    """Get detailed compatibility report for a model.

    Args:
        model_name: Model name e.g. "qwen3.5:9b"

    Returns:
        CompatibilityReport with detailed analysis.
    """
    name_lower = model_name.lower()

    # Check known families
    for family, info in MODEL_FAMILIES.items():
        if family in name_lower:
            return CompatibilityReport(
                model_name=model_name,
                compatibility=info["compatibility"],
                score=info["score"],
                reasoning=f"Recognised as {family} family. {info['notes']}",
                supports_thinking=info["supports_thinking"],
                is_instruction_tuned=info["is_instruction_tuned"],
                recommended_for_production=info["compatibility"]
                in ("excellent", "good"),
                notes=info.get("notes", ""),
            )

    # Check for base models
    partial_signals = [":base", "-base", "uncensored", "raw"]
    for signal in partial_signals:
        if signal in name_lower:
            return CompatibilityReport(
                model_name=model_name,
                compatibility="partial",
                score=40,
                reasoning="Base or uncensored model — may not follow constraints",
                supports_thinking=False,
                is_instruction_tuned=False,
                recommended_for_production=False,
                notes="Consider using an instruction-tuned model instead.",
            )

    # Unknown model
    return CompatibilityReport(
        model_name=model_name,
        compatibility="unknown",
        score=50,
        reasoning="Unrecognised model family — compatibility not guaranteed",
        supports_thinking=False,
        is_instruction_tuned=False,
        recommended_for_production=False,
        notes="Test thoroughly before production use.",
    )


def is_model_compatible(model_name: str, min_compatibility: str = "good") -> bool:
    """Check if a model meets minimum compatibility threshold.

    Args:
        model_name: Model name to check.
        min_compatibility: Minimum compatibility level required.

    Returns:
        True if model meets or exceeds minimum compatibility.
    """
    report = get_compatibility_report(model_name)
    order = {"excellent": 3, "good": 2, "partial": 1, "unknown": 0}
    min_order = order.get(min_compatibility, 0)
    report_order = order.get(report.compatibility, 0)
    return report_order >= min_order


def get_recommended_models() -> list[str]:
    """Get list of recommended model names.

    Returns:
        List of recommended model family names.
    """
    return [
        family
        for family, info in MODEL_FAMILIES.items()
        if info["compatibility"] in ("excellent", "good")
    ]
