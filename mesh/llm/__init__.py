"""Mesh LLM module - Local inference with llama-cpp-python.

Uses Qwen2.5-Coder-1.5B-Instruct-GGUF for code analysis.
"""

from mesh.llm.local import LocalLLM, create_llm
from mesh.llm.downloader import (
    ensure_model,
    download_model,
    get_model_path,
    get_model_size_mb,
    is_model_downloaded,
    delete_model,
    MODEL_REPO,
    MODEL_FILE,
)
from mesh.llm.explainer import CodeExplainer, explain_query

__all__ = [
    "LocalLLM",
    "create_llm",
    "ensure_model",
    "download_model",
    "get_model_path",
    "get_model_size_mb",
    "is_model_downloaded",
    "delete_model",
    "MODEL_REPO",
    "MODEL_FILE",
    "CodeExplainer",
    "explain_query",
]
