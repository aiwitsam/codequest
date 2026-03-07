import os

from codequest.models.base import LLMBackend


class ClaudeBackend(LLMBackend):
    """Claude API backend (requires internet + API key)."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model
        self._api_key = os.environ.get("ANTHROPIC_API_KEY", "")

    @property
    def name(self) -> str:
        return f"Claude ({self.model})"

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            import requests
            resp = requests.get("https://api.anthropic.com", timeout=3)
            return resp.status_code < 500
        except Exception:
            return False

    def ask(self, question: str, context: str) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"You are a helpful coding assistant. "
                            f"Here is context about a project:\n\n{context}\n\n"
                            f"Question: {question}"
                        ),
                    }
                ],
            )
            return message.content[0].text
        except Exception as e:
            return f"Error from Claude API: {e}"
