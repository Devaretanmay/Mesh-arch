"""Local LLM wrapper using llama-cpp-python.

Uses Qwen2.5-Coder-1.5B-Instruct for code analysis.
"""

import os
from pathlib import Path
from typing import Optional

from llama_cpp import Llama


MODEL_NAME = "Qwen2.5-Coder-1.5B-Instruct-GGUF"
DEFAULT_CONTEXT_SIZE = 8192


class LocalLLM:
    def __init__(
        self,
        model_path: Path,
        n_ctx: int = DEFAULT_CONTEXT_SIZE,
        n_threads: Optional[int] = None,
    ):
        self.model_path = model_path
        self.n_ctx = n_ctx
        self._llm: Optional[Llama] = None
        self._n_threads = n_threads or max(4, (os.cpu_count() or 4) - 1)

    def _ensure_loaded(self) -> Llama:
        if self._llm is None:
            self._llm = Llama(
                model_path=str(self.model_path),
                n_ctx=self.n_ctx,
                n_threads=self._n_threads,
                verbose=False,
            )
        return self._llm

    def chat(self, messages: list[dict], max_tokens: int = 512) -> str:
        llm = self._ensure_loaded()
        prompt = self._format_chat_prompt(messages)
        output = llm(
            prompt,
            max_tokens=max_tokens,
            stop=["<|endoftext|>", "<|im_end|>"],
            echo=False,
        )
        return output["choices"][0]["text"].strip()

    def complete(self, prompt: str, max_tokens: int = 512) -> str:
        llm = self._ensure_loaded()
        output = llm(
            prompt,
            max_tokens=max_tokens,
            stop=["<|endoftext|>", "<|im_end|>"],
            echo=False,
        )
        return output["choices"][0]["text"].strip()

    def _format_chat_prompt(self, messages: list[dict]) -> str:
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"<|im_start|>system\n{content}<|im_end|>\n"
            elif role == "user":
                prompt += f"<|im_start|>user\n{content}<|im_end|>\n"
            elif role == "assistant":
                prompt += f"<|im_start|>assistant\n{content}<|im_end|>\n"
        prompt += "<|im_start|>assistant\n"
        return prompt

    def unload(self) -> None:
        self._llm = None


def create_llm(model_path: Path) -> LocalLLM:
    return LocalLLM(model_path)
