# CodeQuest

Your project command center with a retro 8-bit UI.

CodeQuest auto-discovers projects in your home directory and gives you a unified dashboard to browse, run, analyze, and monitor them — through both a terminal TUI and a web interface.

## Quick Start

```bash
# Clone and install
git clone https://github.com/aiwitsam/codequest.git
cd codequest
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Launch the TUI
codequest

# Or launch the web dashboard
codequest --web
```

On first run, CodeQuest scans `~/` for projects (anything with a `package.json`, `setup.py`, `Cargo.toml`, `go.mod`, `Makefile`, `.git`, or similar markers) and builds an index at `~/.codequest/index.json`.

## Interfaces

### Terminal TUI (Textual)

The default interface. Retro pixel-art dashboard with keyboard-driven navigation.

| Key | Action |
|-----|--------|
| `/` | Search projects |
| `r` | Run project commands |
| `w` | Open web dashboard |
| `s` | Settings |
| `F5` | Rescan projects |
| `?` | Help overlay |
| `q` | Quit |

Screens: Welcome (first-run onboarding), Dashboard (project grid with type filters), Project Detail (README + run commands + AI Q&A), Settings, Help.

### Web Dashboard (Flask)

Launch with `codequest --web` (default: `localhost:8080`).

**Core pages:**
- `/` — Project grid with cards, badges, and stats
- `/project/<name>` — Detail view with tabs for README, commands, git log, notes
- `/search` — Full-text search across all projects
- `/dependencies` — Dependency audit (outdated packages by severity)
- `/connections` — Project relationship graph (imports, config refs, submodules)
- `/settings` — Theme picker (6 retro presets), config editor, rescan

**AI Toolkit** (dropdown menu):
- `/ai/skills` — Browse your installed Claude Code skills, plugins, and MCP servers
- `/ai/discover` — Discover uninstalled skills from community repos with relevance scoring
- `/ai/ollama` — Manage Ollama models (list, pull with SSE progress, delete)
- `/ai/assistant` — Chat with Claude or Ollama about your projects

**Intel Feed** (dropdown menu):
- `/intel/pulse` — Tech intelligence feed from GitHub Trending, HuggingFace, Ollama, and Anthropic releases, scored against your stack
- `/intel/reddit` — Security intel from Reddit via FTS5 search, with CVE badges

**Ops** (dropdown menu):
- `/ops/services` — Systemd service health monitoring with HTTP checks and auto-refresh
- `/ops/security` — Security audit results (exposed secrets, SSL certs, file permissions)

## CLI

```
codequest              Launch TUI (default)
codequest --web        Launch web dashboard
codequest --scan       Rescan and rebuild project index
codequest --config     Open config in your $EDITOR
codequest --port 9000  Custom port for web dashboard
```

## Architecture

```
codequest/
├── __main__.py         CLI entry point
├── app.py              Textual TUI (5 screens)
├── scanner.py          Project auto-discovery
├── runner.py           Run command detection & execution
├── config.py           Config management (YAML, deep merge)
├── readme_parser.py    Markdown parsing for project READMEs
├── deps.py             Dependency scanning (pip, npm)
├── connections.py      Project relationship graph
├── assets/
│   └── pixel_art.py    8-bit ASCII art and badges
├── models/
│   ├── base.py         LLMBackend ABC
│   ├── claude_backend.py   Anthropic SDK integration
│   └── ollama_backend.py   Ollama HTTP client
├── ai/
│   ├── skills_scanner.py   Scan installed skills/plugins/MCP
│   ├── skill_discovery.py  Discover community skills
│   └── ollama_hub.py       Ollama model management
├── intel/
│   ├── scoring.py      Relevance scoring engine
│   ├── config.py       Tech stack definition
│   ├── queue_utils.py  Queue persistence (YAML)
│   ├── reddit.py       reddit-sentinel wrapper
│   └── sources/        Scrapers (GitHub, HF, Ollama, Claude)
├── ops/
│   ├── services.py     Systemd service discovery + health
│   └── security.py     Security audit aggregator
└── web/
    ├── server.py       Flask app (68 routes)
    ├── templates/      HTML templates (16 files)
    └── static/         CSS, JS, fonts, sprites
```

## Configuration

CodeQuest uses a layered config system:

1. **Hardcoded defaults** in `codequest/config.py`
2. **Project defaults** in `config.yaml` (ships with repo)
3. **User overrides** in `~/.codequest/config.yaml` (created on first run)

Each layer deep-merges into the previous, so you only need to specify what you want to change.

### Key settings

```yaml
# Which directories to scan
auto_discover: true
auto_discover_paths:
  - ~/
exclude_paths:
  - ~/node_modules
  - ~/.cache

# AI backend
llm:
  primary: ollama          # or "claude"
  claude_model: claude-sonnet-4-6
  offline_model: mistral:7b

# Intel scoring - what's in your stack
intel:
  my_stack:
    languages: [python, javascript, bash]
    frameworks: [flask, react, node]
  hot_keywords: [llm, agent, automation]

# Service health monitoring
ops:
  service_ports:
    my-api: 8081
    my-worker: 9000
  mesh_host: ""            # Tailscale hostname for mesh ops

# Theme
theme: retro-green         # phosphor-green, classic-neon, amber-crt, ice-blue, hot-pink, dracula
```

## Data Storage

| Path | Purpose | TTL |
|------|---------|-----|
| `~/.codequest/config.yaml` | User configuration | Persistent |
| `~/.codequest/index.json` | Project index cache | 24 hours |
| `~/.codequest/deps_cache.json` | Dependency scan cache | 1 hour |
| `~/.codequest/connections.json` | Relationship graph cache | 24 hours |
| `~/.codequest/queues/` | Intel queue data | Persistent |
| `<project>/.codequest-notes.md` | Per-project notes | Persistent |

## Optional Integrations

These are not required but unlock additional features when available:

| Tool | Feature |
|------|---------|
| [Ollama](https://ollama.com) | Local LLM for AI assistant and offline use |
| `ANTHROPIC_API_KEY` env var | Claude API for AI assistant |
| [reddit-sentinel](https://github.com/aiwitsam/reddit-sentinel) | Reddit security intel on `/intel/reddit` |
| `gh` CLI | GitHub repo visibility detection |
| systemd user services | Service health monitoring on `/ops/services` |

## Requirements

- Python >= 3.10
- Dependencies: textual, flask, pyyaml, requests, anthropic, beautifulsoup4, lxml

## License

MIT
