import requests

from codequest.models.base import LLMBackend

OLLAMA_URL = "http://localhost:11434"


class OllamaBackend(LLMBackend):
    """Ollama local LLM backend (fully offline)."""

    def __init__(self, model: str = "gemma3:4b"):
        self.model = model

    @property
    def name(self) -> str:
        return f"Ollama ({self.model})"

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
            if resp.status_code != 200:
                return False
            models = [m["name"] for m in resp.json().get("models", [])]
            # Check if our model (or a variant) is available
            return any(self.model in m for m in models)
        except Exception:
            return False

    def ask(self, question: str, context: str) -> str:
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": self.model,
                    "prompt": (
                        f"You are a helpful coding assistant. "
                        f"Here is context about a project:\n\n{context}\n\n"
                        f"Question: {question}"
                    ),
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("response", "No response from model.")
        except requests.Timeout:
            return "Ollama request timed out. The model may be loading."
        except Exception as e:
            return f"Error from Ollama: {e}"
