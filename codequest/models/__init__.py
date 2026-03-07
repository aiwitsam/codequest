"""LLM model selector with fallback chain."""

from codequest.models.base import LLMBackend
from codequest.models.claude_backend import ClaudeBackend
from codequest.models.ollama_backend import OllamaBackend


class ModelSelector:
    """Select the best available LLM backend with fallback chain."""

    def __init__(self, config: dict | None = None):
        if config is None:
            from codequest.config import get_config
            config = get_config()

        llm_cfg = config.get("llm", {})
        force = llm_cfg.get("force_backend")

        self._backends: list[LLMBackend] = []

        if force == "ollama":
            self._backends = [
                OllamaBackend(llm_cfg.get("offline_model", "gemma3:4b")),
                OllamaBackend(llm_cfg.get("fallback_model", "llama3.2:3b")),
            ]
        elif force == "claude":
            self._backends = [
                ClaudeBackend(llm_cfg.get("claude_model", "claude-sonnet-4-6")),
            ]
        else:
            # Default chain: Claude -> Ollama primary -> Ollama fallback
            self._backends = [
                ClaudeBackend(llm_cfg.get("claude_model", "claude-sonnet-4-6")),
                OllamaBackend(llm_cfg.get("offline_model", "gemma3:4b")),
                OllamaBackend(llm_cfg.get("fallback_model", "llama3.2:3b")),
            ]

        self._active: LLMBackend | None = None

    @property
    def active_backend(self) -> LLMBackend | None:
        """Return the first available backend."""
        if self._active and self._active.is_available():
            return self._active
        for backend in self._backends:
            if backend.is_available():
                self._active = backend
                return backend
        self._active = None
        return None

    @property
    def active_name(self) -> str:
        b = self.active_backend
        return b.name if b else "No AI available"

    @property
    def is_available(self) -> bool:
        return self.active_backend is not None

    def ask(self, question: str, context: str) -> str:
        backend = self.active_backend
        if not backend:
            return "No AI backend available. Set ANTHROPIC_API_KEY or start Ollama."
        return backend.ask(question, context)

    def status(self) -> list[dict]:
        """Return status of all backends."""
        results = []
        for b in self._backends:
            results.append({
                "name": b.name,
                "available": b.is_available(),
                "active": b is self._active,
            })
        return results
