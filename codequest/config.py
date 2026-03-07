"""Configuration management for CodeQuest."""

from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "scan_paths": [],
    "auto_discover": True,
    "auto_discover_paths": ["~/"],
    "exclude_paths": [
        "~/node_modules",
        "~/snap",
        "~/thinclient_drives",
        "~/.cache",
        "~/.local",
        "~/cuda",
        "~/lib",
        "~/.vscode-server",
        "~/.claude",
        "~/SNNLA_audit",
        "~/bankruptcy-creditor-info",
    ],
    "overrides": {},
    "llm": {
        "primary": "claude",
        "claude_model": "claude-sonnet-4-6",
        "offline_model": "gemma3:4b",
        "fallback_model": "llama3.2:3b",
        "force_backend": None,
    },
    "web": {
        "port": 8080,
        "auto_open_browser": True,
    },
    "theme": "retro-green",
    "first_run_complete": False,
}

CONFIG_DIR = Path.home() / ".codequest"
PROJECT_CONFIG_FILE = Path(__file__).parent.parent / "config.yaml"
USER_CONFIG_FILE = CONFIG_DIR / "config.yaml"
INDEX_FILE = CONFIG_DIR / "index.json"

_config = None


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base, filling in missing keys from base."""
    merged = base.copy()
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict:
    """Load config from user file if it exists, else project default, merged with DEFAULT_CONFIG."""
    config = {}

    # Determine which file to load (user override takes precedence)
    if USER_CONFIG_FILE.exists():
        config_file = USER_CONFIG_FILE
    elif PROJECT_CONFIG_FILE.exists():
        config_file = PROJECT_CONFIG_FILE
    else:
        return DEFAULT_CONFIG.copy()

    with open(config_file, "r") as f:
        loaded = yaml.safe_load(f)

    if loaded and isinstance(loaded, dict):
        config = loaded

    # Merge with defaults so missing keys are filled in
    return _deep_merge(DEFAULT_CONFIG, config)


def save_config(config: dict) -> None:
    """Save config to the user config directory, creating it if needed."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(USER_CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def get_config() -> dict:
    """Return cached config singleton, loading on first call."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def resolve_path(p: str) -> Path:
    """Expand ~ and resolve a path string to an absolute Path."""
    return Path(p).expanduser().resolve()


def get_exclude_paths() -> set[Path]:
    """Return the set of resolved exclude paths from config."""
    config = get_config()
    return {resolve_path(p) for p in config.get("exclude_paths", [])}
