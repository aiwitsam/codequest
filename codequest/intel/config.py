"""Intel Feed configuration - adapted from tech-pulse."""

from codequest.config import get_config

# Defaults (same as tech-pulse)
GITHUB_LANGUAGES = ["", "python", "javascript", "typescript", "rust", "go"]
GITHUB_TOPICS = ["machine-learning", "llm", "ai", "deep-learning", "generative-ai"]

MY_STACK = {
    "languages": ["python", "javascript", "typescript", "bash", "html", "css"],
    "frameworks": ["next.js", "react", "node", "express", "flask", "fastapi", "django"],
    "tools": ["ollama", "claude", "anthropic", "openai", "huggingface", "docker",
              "git", "npm", "pip", "selenium", "playwright", "puppeteer"],
    "domains": ["security", "scanning", "automation", "web scraping", "ai", "ml",
                "llm", "wordpress", "ssl", "email", "chrome extension", "cli"],
}

HOT_KEYWORDS = ["claude", "anthropic", "ollama", "llm", "agent", "mcp", "rag",
                "fine-tune", "quantization", "gguf", "security", "scanner",
                "automation", "scraping", "chrome extension"]

MAX_ITEMS_PER_SOURCE = 15


def get_my_stack():
    """Return MY_STACK merged with config overrides."""
    config = get_config()
    intel_config = config.get("intel", {})
    override = intel_config.get("my_stack", {})
    if override:
        merged = dict(MY_STACK)
        for key in ("languages", "frameworks", "tools", "domains"):
            if key in override:
                merged[key] = override[key]
        return merged
    return MY_STACK


def get_hot_keywords():
    """Return HOT_KEYWORDS merged with config overrides."""
    config = get_config()
    intel_config = config.get("intel", {})
    return intel_config.get("hot_keywords", HOT_KEYWORDS)
