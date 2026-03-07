from abc import ABC, abstractmethod


class LLMBackend(ABC):
    """Abstract interface for LLM backends."""

    @abstractmethod
    def ask(self, question: str, context: str) -> str:
        """Send a question with project context to the LLM."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is currently available."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend."""
        ...
