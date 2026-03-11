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

        # Build Ollama backends from config list (or legacy keys)
        ollama_models = llm_cfg.get("ollama_models", [])
        if not ollama_models:
            # Fallback to legacy config keys
            for key in ("offline_model", "fallback_model"):
                m = llm_cfg.get(key)
                if m:
                    ollama_models.append(m)

        if force == "ollama":
            self._backends = [OllamaBackend(m) for m in ollama_models]
        elif force == "claude":
            self._backends = [
                ClaudeBackend(llm_cfg.get("claude_model", "claude-sonnet-4-6")),
            ]
        else:
            # Default: all Ollama models (Claude only if API key is configured)
            primary = llm_cfg.get("primary", "ollama")
            if primary == "claude":
                self._backends.append(
                    ClaudeBackend(llm_cfg.get("claude_model", "claude-sonnet-4-6"))
                )
            self._backends.extend(OllamaBackend(m) for m in ollama_models)

        self._active: LLMBackend | None = None

    @property
    def active_backend(self) -> LLMBackend | None:
        """Return the active backend (user-selected or first available)."""
        if self._active is not None:
            return self._active
        for backend in self._backends:
            if backend.is_available():
                self._active = backend
                return backend
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

    def ask_with(self, question: str, context: str, model_name: str) -> tuple[str, str]:
        """Ask using a specific model by name. Returns (answer, model_name)."""
        backend = self.get_backend(model_name)
        if not backend:
            return ("Model not found or unavailable.", model_name)
        return (backend.ask(question, context), backend.name)

    def get_backend(self, name: str) -> LLMBackend | None:
        """Find a backend by its name string."""
        for b in self._backends:
            if b.name == name:
                return b
        return None

    def switch_to(self, name: str) -> bool:
        """Switch the active model by name. Returns True if found."""
        backend = self.get_backend(name)
        if backend:
            self._active = backend
            return True
        return False

    def list_models(self) -> list[dict]:
        """Return all models with name, available, and active flags."""
        # Ensure _active is set
        self.active_backend
        results = []
        for b in self._backends:
            results.append({
                "name": b.name,
                "available": b.is_available(),
                "active": b is self._active,
            })
        return results

    def status(self) -> list[dict]:
        """Return status of all backends."""
        return self.list_models()
