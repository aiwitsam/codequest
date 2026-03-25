# CodeQuest -- System Architecture

## Overview

Project command center with dual interfaces: a Textual TUI for terminal-native browsing and a Flask web dashboard with a retro 8-bit aesthetic. Auto-discovers projects in the home directory, provides browsing, run-command detection, AI chat (Claude API with Ollama fallback), dependency auditing, project relationship graphing, tech intel feeds, Reddit security intelligence, service monitoring, and security auditing.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.10+ |
| TUI framework | Textual (5 screens) |
| Web framework | Flask |
| Frontend | Jinja2 + retro CSS (PressStart2P font, neon palette) |
| LLM | Anthropic SDK (Claude, primary) + Ollama HTTP (fallback) |
| Scraping | BeautifulSoup4 + lxml + requests |
| Config | YAML (3-layer deep merge: defaults, project, user) |
| Data caching | JSON files in ~/.codequest/ with TTL |

## Architecture

```
┌──────────────────────────────────────────────────┐
│ Dual Interface                                   │
│ ├── Textual TUI (codequest, 5 screens, ~482 LOC)│
│ └── Flask Web Dashboard (codequest --web)        │
│     ├── 68 routes: 16 pages + 21 API + redirects│
│     ├── Templates: 16 Jinja2 files + partials    │
│     ├── 8-bit retro theme (6 presets)            │
│     └── JS modules: app, ollama, pulse, reddit,  │
│         services                                 │
├──────────────────────────────────────────────────┤
│ Core Modules                                     │
│ ├── Scanner (auto-discover projects in ~/)       │
│ │   ProjectInfo dataclass, PROJECT_MARKERS       │
│ │   Index: ~/.codequest/index.json (24h TTL)     │
│ ├── Runner (detect run commands per project)     │
│ │   Reads: package.json, Makefile, __main__.py,  │
│ │   .sh, Dockerfile → RunCommand dataclass       │
│ ├── Config (3-layer YAML merge, singleton)       │
│ ├── README parser (title, sections, quick_start) │
│ ├── Dependencies (pip list, npm outdated)        │
│ │   Cache: ~/.codequest/deps_cache.json (1h TTL) │
│ └── Connections (import scan, config refs, git)  │
│     Cache: ~/.codequest/connections.json (24h)   │
├──────────────────────────────────────────────────┤
│ AI Subsystem (models/)                           │
│ ├── ModelSelector: fallback chain, switch_to()   │
│ ├── Claude backend (Anthropic SDK)               │
│ ├── Ollama backend (HTTP, localhost:11434)        │
│ └── LLMBackend ABC (ask, is_available, name)     │
├──────────────────────────────────────────────────┤
│ AI Toolkit (ai/)                                 │
│ ├── Skills scanner (~/.claude/skills, plugins)   │
│ ├── Skill discovery (community repos)            │
│ └── Ollama hub (list, pull with SSE, delete)     │
├──────────────────────────────────────────────────┤
│ Intel Feed (intel/)                              │
│ ├── Sources: GitHub Trending, HuggingFace,       │
│ │   Ollama registry, Claude/Anthropic releases   │
│ ├── Scoring engine (stack match + hot keywords)  │
│ ├── Queue utils (YAML persistence)              │
│ └── Reddit integration (reddit-sentinel FTS5)    │
├──────────────────────────────────────────────────┤
│ Ops Suite (ops/)                                 │
│ ├── Service monitor (systemd + HTTP health)      │
│ └── Security audit (secrets, SSL, perms, git)    │
├──────────────────────────────────────────────────┤
│ Storage (all JSON file-based, no database)       │
│ ├── ~/.codequest/index.json (project index)      │
│ ├── ~/.codequest/deps_cache.json (dependencies)  │
│ ├── ~/.codequest/connections.json (project graph) │
│ ├── ~/.codequest/config.yaml (user overrides)    │
│ ├── ~/.codequest/queues/ (intel queue YAML)      │
│ └── <project>/.codequest-notes.md (per-project)  │
└──────────────────────────────────────────────────┘
```

## Port Allocation

| Service | Port | Protocol |
|---------|------|----------|
| Web dashboard | **8080** | HTTP |
| Ollama (external) | 11434 | HTTP |

## File Structure

```
~/codequest/
├── codequest/
│   ├── __init__.py          (version: 2.0.0)
│   ├── __main__.py          (argparse: --web, --scan, --config, --port)
│   ├── app.py               (Textual TUI, 5 screens, ~482 LOC)
│   ├── scanner.py           (project auto-discovery, ProjectInfo dataclass)
│   ├── runner.py            (run command detection, RunCommand dataclass)
│   ├── config.py            (3-layer YAML merge, DEFAULT_CONFIG, singleton)
│   ├── readme_parser.py     (Markdown parsing, ReadmeInfo dataclass)
│   ├── deps.py              (pip/npm dependency scanning with caching)
│   ├── connections.py       (project relationship graph, import scanning)
│   ├── process_manager.py   (process lifecycle management)
│   ├── assets/
│   │   └── pixel_art.py     (ASCII art: LOGO, WELCOME_ART, ICONS, BADGES)
│   ├── models/
│   │   ├── __init__.py      (ModelSelector: fallback chain, switch_to, list_models)
│   │   ├── base.py          (LLMBackend ABC)
│   │   ├── claude_backend.py (Anthropic SDK)
│   │   └── ollama_backend.py (Ollama HTTP)
│   ├── ai/
│   │   ├── skills_scanner.py (scan ~/.claude/skills, plugins, MCP servers, hooks)
│   │   ├── skill_discovery.py (discover uninstalled community skills)
│   │   └── ollama_hub.py    (Ollama model management with SSE pull)
│   ├── intel/
│   │   ├── scoring.py       (score_item: stack match + hot keywords)
│   │   ├── config.py        (my_stack from main config)
│   │   ├── queue_utils.py   (YAML queue persistence)
│   │   ├── reddit.py        (reddit-sentinel FTS5 wrapper)
│   │   └── sources/         (github_trending, huggingface, ollama_models, claude_updates)
│   ├── ops/
│   │   ├── services.py      (systemd user service discovery + HTTP health checks)
│   │   └── security.py      (secrets, SSL certs, file perms, git repo audit)
│   └── web/
│       ├── server.py        (Flask app, ~1,559 LOC, 68 routes)
│       ├── templates/       (16 templates: dashboard, project, deps, connections, settings, assistant, ai/*, intel/*, ops/*)
│       └── static/          (css/retro.css, js/*, fonts/PressStart2P, img/sprites/)
├── config.yaml              (project defaults)
├── setup.py
├── requirements.txt
└── docs/
```

## Data Storage

| Path | Contents | TTL |
|------|----------|----|
| `~/.codequest/index.json` | Project index cache | 24h |
| `~/.codequest/deps_cache.json` | Dependency scan results | 1h |
| `~/.codequest/connections.json` | Project relationship graph | 24h |
| `~/.codequest/config.yaml` | User config overrides | permanent |
| `~/.codequest/queues/` | Intel queue data (YAML files) | permanent |
| `<project>/.codequest-notes.md` | Per-project notes | permanent |

## Dependencies on Other Projects

| Project | Relationship |
|---------|-------------|
| Ollama (localhost:11434) | LLM fallback when Claude API unavailable; model hub management |
| reddit-sentinel | Intel feed reads `~/.reddit-sentinel/sentinel.db` via FTS5 for security intel |
| All ~/projects | Scanner auto-discovers and indexes all projects in home directory |
| systemd services | Ops suite monitors all user-level systemd services for health |

## External Service Dependencies

| Service | Required? | Auth | Purpose |
|---------|-----------|------|---------|
| Claude API | No (primary LLM) | ANTHROPIC_API_KEY | AI chat, project analysis |
| Ollama | No (fallback LLM) | None (local) | Offline AI, model hub |
| GitHub Trending | No (intel feed) | None (public) | Trending repo scraping |
| HuggingFace API | No (intel feed) | None (public) | Trending models/spaces |
| GitHub CLI (gh) | No (repo info) | gh auth | Repository visibility, changelog |

## Environment Variables

```bash
# LLM (optional, one or both)
ANTHROPIC_API_KEY=sk-ant-...

# Optional (auto-detected)
EDITOR=nano                # For --config command
```

## Deployment

### Local Development
```bash
cd ~/codequest
source .venv/bin/activate
codequest              # Launch TUI
codequest --web        # Launch web dashboard (localhost:8080)
codequest --scan       # Rebuild project index
codequest --config     # Edit config in $EDITOR
```

### Systemd Service (production)
```ini
[Unit]
Description=CodeQuest Project Command Center Web Dashboard
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/codequest
ExecStart=%h/codequest/.venv/bin/codequest --web --port 8080
EnvironmentFile=-%h/.config/mesh-env
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

### Mesh Sync
- Synced to Ubuntu server via `~/bin/mesh-sync.sh`
- Excludes: .venv/, __pycache__/, *.pyc
- Index cache regenerated per machine (scans local filesystem)
- UFW: allow port 8080 on tailscale0 interface

## Known Constraints

- No database: all state is JSON files with TTL-based cache invalidation
- Flask web server is single-threaded (development server); not production-hardened
- Scanner only goes 1 level deep in home directory by default
- LLM fallback chain: Claude API (best quality, costs money) → Ollama (free, local, lower quality)
- Reddit intel requires reddit-sentinel installed with populated FTS5 database
- Dependency scanning shells out to `pip list --outdated` and `npm outdated` (slow for large projects)
- Service monitor only works with systemd user-level services
- 35 Python files in the codequest package
- PressStart2P font must be bundled (no CDN fallback)
- No authentication on web dashboard; intended for local/mesh access only
