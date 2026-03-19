"""Model downloader for Qwen2.5-Coder-1.5B-Instruct-GGUF.

Downloads from HuggingFace and caches in ~/.mesh/models/
"""

from pathlib import Path
from typing import Optional, Callable

from huggingface_hub import hf_hub_download


MODEL_REPO = "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF"
MODEL_FILE = "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"
MODEL_SIZE_MB = 1000


def get_model_dir() -> Path:
    return Path.home() / ".mesh" / "models"


def get_model_path() -> Path:
    return get_model_dir() / MODEL_FILE


def is_model_downloaded() -> bool:
    return get_model_path().exists()


def get_model_size_mb() -> int:
    if is_model_downloaded():
        return int(get_model_path().stat().st_size / (1024 * 1024))
    return MODEL_SIZE_MB


def download_model(
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Path:
    model_dir = get_model_dir()
    model_dir.mkdir(parents=True, exist_ok=True)

    path = hf_hub_download(
        repo_id=MODEL_REPO,
        filename=MODEL_FILE,
        local_dir=str(model_dir),
        local_dir_use_symlinks=False,
        progress_callback=progress_callback,
    )
    return Path(path)


def ensure_model(
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> tuple[Path, bool]:
    model_path = get_model_path()
    if model_path.exists():
        return model_path, False

    downloaded_path = download_model(progress_callback)
    return downloaded_path, True


def delete_model() -> bool:
    model_path = get_model_path()
    if model_path.exists():
        model_path.unlink()
        return True
    return False
