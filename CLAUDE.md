# CodeQuest - Claude Code Project Guide

## What This Is

CodeQuest v2.0.0 is a project command center with dual interfaces (Textual TUI + Flask web dashboard). It auto-discovers projects in the user's home directory and provides browsing, running, AI chat, dependency auditing, project relationship graphing, intel feeds, and service monitoring — all with a retro 8-bit aesthetic.

## How to Run

```bash
# Activate the venv
source ~/codequest/.venv/bin/activate

# TUI (default)
codequest

# Web dashboard
codequest --web              # localhost:8080
codequest --web --port 9000  # custom port

# Rescan projects
codequest --scan

# Edit config
codequest --config
```

## Project Structure

```
codequest/                  # Package root
├── __init__.py             # Version: 2.0.0
├── __main__.py             # CLI entry (argparse)
├── app.py                  # Textual TUI (~482 LOC, 5 screens)
├── scanner.py              # Project discovery (~150 LOC)
│                           #   ProjectInfo dataclass, PROJECT_MARKERS
│                           #   Index cache: ~/.codequest/index.json (24h TTL)
├── runner.py               # Run command detection (~280 LOC)
│                           #   Detects from package.json, Makefile, __main__.py, .sh, Dockerfile
│                           #   RunCommand dataclass, execute_command() with streaming
├── config.py               # Config management (~152 LOC)
│                           #   DEFAULT_CONFIG dict, deep merge, singleton pattern
│                           #   Project file: config.yaml | User file: ~/.codequest/config.yaml
├── readme_parser.py        # Markdown parsing (~80 LOC)
│                           #   ReadmeInfo dataclass (title, description, sections, quick_start)
├── deps.py                 # Dependency scanning (~200 LOC)
│                           #   scan_python() via pip list --outdated
│                           #   scan_javascript() via npm outdated
│                           #   Cache: ~/.codequest/deps_cache.json (1h TTL)
├── connections.py          # Project relationship graph (~200 LOC)
│                           #   Python/Node import scanning, config ref detection, submodules
│                           #   Cache: ~/.codequest/connections.json (24h TTL)
├── assets/
│   └── pixel_art.py        # ASCII art: LOGO, WELCOME_ART, ICONS, BADGES
├── models/                 # LLM backends
│   ├── base.py             # LLMBackend ABC (ask, is_available, name)
│   ├── claude_backend.py   # Anthropic SDK (ANTHROPIC_API_KEY from env)
│   ├── ollama_backend.py   # Ollama HTTP (localhost:11434)
│   └── __init__.py         # ModelSelector: fallback chain, switch_to(), list_models()
├── ai/                     # AI Toolkit subsystem
│   ├── skills_scanner.py   # Scan ~/.claude/skills, plugins, MCP servers, hooks
│   ├── skill_discovery.py  # Discover uninstalled skills (Trail of Bits, community repos)
│   └── ollama_hub.py       # Ollama model management (list, pull with SSE, delete)
├── intel/                  # Intel Feed subsystem
│   ├── scoring.py          # score_item(): stack match + hot keywords → heat badges
│   ├── config.py           # my_stack definition (reads from main config)
│   ├── queue_utils.py      # YAML queue persistence at ~/.codequest/queues/
│   ├── reddit.py           # reddit-sentinel wrapper (FTS5 search, CVE extraction)
│   └── sources/            # Scrapers
│       ├── github_trending.py   # BeautifulSoup HTML scraper
│       ├── huggingface.py       # HuggingFace API
│       ├── ollama_models.py     # Ollama public registry
│       └── claude_updates.py    # Anthropic releases RSS
├── ops/                    # Ops Suite subsystem
│   ├── services.py         # systemd user service discovery + HTTP health checks
│   └── security.py         # Security audit (secrets, SSL certs, file perms, git repos)
└── web/                    # Flask web dashboard
    ├── server.py           # Main Flask app (~1,559 LOC, 68 routes: 10 pages + 21 API + redirects)
    ├── templates/          # Jinja2 HTML
    │   ├── base.html       # Layout: nav with 3 dropdown menus + retro footer
    │   ├── dashboard.html  # Project grid with cards, badges, type filters
    │   ├── project.html    # Detail view: README, commands, git log, notes, AI Q&A
    │   ├── dependencies.html
    │   ├── connections.html
    │   ├── settings.html   # Theme picker (6 presets), config editor
    │   ├── assistant.html
    │   ├── ai/             # skills.html, skill_detail.html, ollama.html, discover.html
    │   ├── intel/          # pulse.html, reddit.html
    │   └── ops/            # services.html, security.html
    └── static/
        ├── css/retro.css   # 8-bit theme (PressStart2P font, neon, grid)
        ├── js/             # app.js, ollama.js, pulse.js, reddit.js, services.js
        ├── fonts/          # PressStart2P-Regular.ttf
        └── img/sprites/    # Sprite assets
```

## Route Map (Web Dashboard)

### Pages
| Route | Template | Description |
|-------|----------|-------------|
| `/` | dashboard.html | Project grid with type filter tabs |
| `/project/<name>` | project.html | Project detail (README, commands, git, notes, AI) |
| `/search` | dashboard.html | Full-text search results |
| `/settings` | settings.html | Theme picker + config editor |
| `/dependencies` | dependencies.html | Dependency audit view |
| `/connections` | connections.html | Project relationship graph |
| `/ai/assistant` | assistant.html | LLM chat interface |
| `/ai/skills` | skills.html | Installed skills browser |
| `/ai/skills/<name>` | skill_detail.html | Single skill detail |
| `/ai/ollama` | ollama.html | Ollama model manager |
| `/ai/discover` | discover.html | Community skill discovery |
| `/intel/pulse` | pulse.html | Tech intel feed with scoring |
| `/intel/reddit` | reddit.html | Reddit security intel |
| `/ops/services` | services.html | Service health dashboard |
| `/ops/security` | security.html | Security audit results |
| `/assistant` | — | 301 redirect to `/ai/assistant` |

### API Endpoints
| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/api/projects` | List all projects |
| GET | `/api/project/<name>` | Single project data |
| POST | `/api/rescan` | Rebuild project index |
| POST | `/api/run/<name>` | Execute a project command |
| POST | `/api/ask` | LLM query |
| GET | `/api/models` | Available LLM backends |
| POST | `/api/model/switch` | Switch active model |
| GET/POST | `/api/notes/<name>` | Per-project notes |
| POST | `/api/open-editor/<name>` | Open project in editor |
| GET | `/api/editors` | Available editors |
| POST | `/api/bulk/open-editor` | Open multiple projects |
| GET | `/api/changelog/<name>` | Git log (30 commits) |
| GET | `/api/repo-visibility/<name>` | Public/private via `gh` CLI |
| GET | `/api/git-status/<name>` | Git working tree status |
| GET | `/api/stats/<name>` | File counts, LOC, size (10-min cache) |
| GET | `/api/theme/presets` | Theme preset list |
| POST | `/api/theme` | Apply theme |
| POST | `/api/favorite/<name>` | Toggle favorite |
| GET/POST | `/api/favorites` | Favorite list |
| GET/POST | `/api/tags` | Tag management |
| POST | `/api/deps/scan` | Scan all dependencies |
| POST | `/api/deps/scan/<name>` | Scan one project |
| GET | `/api/deps/status` | Scan progress |
| GET | `/api/deps/data` | Scan results |
| GET | `/api/connections/data` | Relationship graph data |
| POST | `/api/connections/refresh` | Rebuild graph |

## Data Paths

| Path | Purpose | TTL |
|------|---------|-----|
| `~/.codequest/config.yaml` | User config (overrides project defaults) | — |
| `~/.codequest/index.json` | Project index cache | 24h |
| `~/.codequest/deps_cache.json` | Dependency scan results | 1h |
| `~/.codequest/connections.json` | Project graph cache | 24h |
| `~/.codequest/queues/` | Intel queue data (YAML) | — |
| `<project>/.codequest-notes.md` | Per-project notes | — |

## Config System

Three-layer deep merge: `DEFAULT_CONFIG` (config.py) ← `config.yaml` (repo) ← `~/.codequest/config.yaml` (user).

The `get_config()` function is a singleton — first call loads and caches. Use `save_config()` to persist user changes.

Key config sections: `scan_paths`, `exclude_paths`, `llm` (backend selection), `intel` (my_stack, hot_keywords), `ops` (service_ports, mesh_host), `theme`, `integrations`.

## Coding Conventions

- **Python >= 3.10**, type hints where useful
- **Flask** for web, **Textual** for TUI — keep them independent (no shared state beyond config + scanner)
- **Config**: all user-facing settings go in DEFAULT_CONFIG with sane defaults; never hardcode paths
- **Caching**: use JSON files in `~/.codequest/` with TTL constants at the top of each module
- **LLM**: always go through `ModelSelector` (models/__init__.py), never call backends directly
- **Templates**: all extend `base.html`, use retro CSS classes, keep JS in separate files under `static/js/`
- **Routes**: page routes return rendered templates, API routes return JSON; prefix API routes with `/api/`
- **Error handling**: wrap network calls (LLM, scraping, health checks) in try/except; never crash the dashboard
- **No secrets in code**: API keys come from env vars or `~/.codequest/config.yaml` (gitignored via user home dir)
- **Theme**: PressStart2P font, neon color palette, retro-green default. 6 presets defined in server.py `THEME_PRESETS`

## Dependencies

Core: textual, flask, pyyaml, requests, anthropic, beautifulsoup4, lxml

Optional system tools: `gh` (GitHub CLI), `ollama`, systemd (for service monitoring)

## Testing

No test suite yet. Manual verification via:
```bash
# Check all imports resolve
python -c "from codequest.web.server import app; print(f'{len(app.url_map._rules)} routes')"

# Check scanner works
codequest --scan

# Check web starts
codequest --web
```
