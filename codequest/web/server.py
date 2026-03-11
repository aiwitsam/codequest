"""
CodeQuest Web Dashboard - Flask application.

Serves the retro 8-bit themed project dashboard on localhost:8080.
Provides both HTML page routes and JSON API endpoints for project
management, command execution, and AI assistant integration.
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import time
import traceback
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    abort,
)

import threading

from codequest import __version__
from codequest.scanner import get_projects, scan_all, save_index, ProjectInfo
from codequest.readme_parser import parse_readme, get_summary_card
from codequest.runner import get_run_commands, execute_command, RunCommand
from codequest.models import ModelSelector
from codequest.config import get_config, save_config
from codequest.deps import (
    scan_project as deps_scan_project,
    scan_all as deps_scan_all,
    load_cache as deps_load_cache,
    save_cache as deps_save_cache,
)
from codequest.connections import (
    analyze_all as connections_analyze,
    load_cache as connections_load_cache,
    save_cache as connections_save_cache,
    is_cache_fresh as connections_cache_fresh,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_timestamp(ts: float) -> str:
    """Convert a UNIX timestamp to a human-readable date string."""
    if ts <= 0:
        return "Unknown"
    dt = datetime.datetime.fromtimestamp(ts)
    return dt.strftime("%b %-d, %Y")


def _project_to_dict(proj: ProjectInfo) -> dict:
    """Serialize a ProjectInfo to a JSON-friendly dict."""
    readme_info = parse_readme(proj.readme_content) if proj.readme_content else None
    description = ""
    if readme_info and readme_info.description:
        description = readme_info.description
    elif proj.readme_content:
        # Grab first non-blank, non-heading line
        for line in proj.readme_content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped
                break

    return {
        "name": proj.name,
        "path": str(proj.path),
        "project_type": proj.project_type,
        "readme_path": str(proj.readme_path) if proj.readme_path else None,
        "readme_content": proj.readme_content,
        "last_modified": proj.last_modified,
        "last_modified_fmt": _format_timestamp(proj.last_modified),
        "last_accessed": proj.last_accessed,
        "is_git_repo": proj.is_git_repo,
        "git_remote_url": proj.git_remote_url,
        "is_claude_made": proj.is_claude_made,
        "has_github": proj.has_github,
        "detected_run_commands": proj.detected_run_commands,
        "description": description,
    }


def _find_project(name: str, projects: list[ProjectInfo]) -> ProjectInfo | None:
    """Find a project by name (case-insensitive)."""
    for p in projects:
        if p.name.lower() == name.lower():
            return p
    return None


NOTES_FILENAME = ".codequest-notes.md"

# ---------------------------------------------------------------------------
# Theme presets & helpers
# ---------------------------------------------------------------------------

THEME_PRESETS = {
    "phosphor-green": {
        "green": "#66ff99",
        "cyan": "#00ffff",
        "magenta": "#ff00ff",
        "amber": "#ffbf00",
    },
    "classic-neon": {
        "green": "#39ff14",
        "cyan": "#00ffff",
        "magenta": "#ff00ff",
        "amber": "#ffbf00",
    },
    "amber-crt": {
        "green": "#ffbf00",
        "cyan": "#ffe066",
        "magenta": "#ff8c00",
        "amber": "#ffdd57",
    },
    "ice-blue": {
        "green": "#00e5ff",
        "cyan": "#40c4ff",
        "magenta": "#b388ff",
        "amber": "#80d8ff",
    },
    "hot-pink": {
        "green": "#ff4081",
        "cyan": "#ff80ab",
        "magenta": "#f50057",
        "amber": "#ffab40",
    },
    "dracula": {
        "green": "#50fa7b",
        "cyan": "#8be9fd",
        "magenta": "#ff79c6",
        "amber": "#f1fa8c",
    },
}


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse a hex color string to an (R, G, B) tuple."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return (102, 255, 153)  # fallback
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def _derive_theme(colors: dict) -> dict:
    """From 4 base hex colors, derive dim and glow variants for CSS injection."""
    theme = {}
    for name, hex_val in colors.items():
        r, g, b = _hex_to_rgb(hex_val)
        theme[name] = hex_val
        theme[f"{name}_dim"] = f"#{int(r * 0.38):02x}{int(g * 0.38):02x}{int(b * 0.38):02x}"
        theme[f"{name}_glow"] = f"rgba({r}, {g}, {b}, 0.35)"
        theme[f"{name}_bg"] = f"rgba({r}, {g}, {b}, 0.06)"
        theme[f"{name}_bg_hover"] = f"rgba({r}, {g}, {b}, 0.1)"
    return theme


def _get_theme_colors() -> dict:
    """Return derived theme dict from current config."""
    config = get_config()
    base_colors = config.get("theme_colors", THEME_PRESETS["phosphor-green"])
    return _derive_theme(base_colors)


# ---------------------------------------------------------------------------
# Git changelog & repo visibility helpers
# ---------------------------------------------------------------------------

def _get_changelog(project_path: str, max_count: int = 30) -> list[dict]:
    """Get git commit history for a project."""
    git_dir = Path(project_path) / ".git"
    if not git_dir.exists():
        return []
    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--max-count={max_count}",
                "--format=%H|%h|%an|%ar|%s",
            ],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        entries = []
        for line in result.stdout.strip().splitlines():
            parts = line.split("|", 4)
            if len(parts) == 5:
                entries.append({
                    "hash": parts[0],
                    "short_hash": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                    "message": parts[4],
                })
        return entries
    except (subprocess.TimeoutExpired, OSError):
        return []


def _parse_github_repo(remote_url: str) -> str | None:
    """Extract 'owner/repo' from a GitHub remote URL."""
    # HTTPS: https://github.com/owner/repo.git
    m = re.match(r"https?://github\.com/([^/]+/[^/]+?)(?:\.git)?/?$", remote_url)
    if m:
        return m.group(1)
    # SSH: git@github.com:owner/repo.git
    m = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", remote_url)
    if m:
        return m.group(1)
    return None


_visibility_cache: dict[str, str] = {}


def _get_repo_visibility(remote_url: str) -> str:
    """Check if a GitHub repo is public or private using gh CLI."""
    if not remote_url:
        return "unknown"

    repo_slug = _parse_github_repo(remote_url)
    if not repo_slug:
        return "unknown"

    if repo_slug in _visibility_cache:
        return _visibility_cache[repo_slug]

    try:
        result = subprocess.run(
            ["gh", "repo", "view", repo_slug, "--json", "visibility", "-q", ".visibility"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            vis = result.stdout.strip().upper()
            if vis in ("PUBLIC", "PRIVATE", "INTERNAL"):
                _visibility_cache[repo_slug] = vis.lower()
                return _visibility_cache[repo_slug]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    _visibility_cache[repo_slug] = "unknown"
    return "unknown"


# ---------------------------------------------------------------------------
# Dependency scan state
# ---------------------------------------------------------------------------

_deps_scan_status = {"running": False, "progress": 0, "total": 0, "current": ""}
_deps_scan_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Project stats cache (10-minute TTL)
# ---------------------------------------------------------------------------

_stats_cache: dict[str, dict] = {}
_STATS_TTL = 600


def _get_project_stats(project_path: str) -> dict:
    """Get file count, LOC, and directory size for a project."""
    now = time.time()
    if project_path in _stats_cache:
        cached = _stats_cache[project_path]
        if now - cached.get("_ts", 0) < _STATS_TTL:
            return cached

    path = Path(project_path)
    stats: dict = {"_ts": now}
    file_counts: dict[str, int] = {}
    total_loc = 0

    try:
        for f in path.rglob("*"):
            rel_parts = f.relative_to(path).parts
            if any(p.startswith(".") or p in ("node_modules", "venv", ".venv", "env",
                    "__pycache__", ".git", "dist", "build", ".next") for p in rel_parts):
                continue
            if f.is_file():
                ext = f.suffix.lower() or "(no ext)"
                file_counts[ext] = file_counts.get(ext, 0) + 1
                # Count lines for known text types
                if ext in (".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go",
                           ".sh", ".html", ".css", ".md", ".json", ".yaml",
                           ".yml", ".toml", ".txt", ".sql", ".mjs"):
                    try:
                        total_loc += sum(1 for _ in f.open(errors="replace"))
                    except OSError:
                        pass
    except OSError:
        pass

    # Directory size
    try:
        result = subprocess.run(
            ["du", "-sh", str(path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            stats["size"] = result.stdout.split()[0]
        else:
            stats["size"] = "?"
    except (subprocess.TimeoutExpired, OSError):
        stats["size"] = "?"

    # Sort by count descending, keep top 10
    sorted_exts = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
    stats["file_counts"] = dict(sorted_exts[:10])
    stats["total_files"] = sum(file_counts.values())
    stats["total_loc"] = total_loc

    _stats_cache[project_path] = stats
    return stats


def _get_notes(project_path: str) -> str:
    """Read project notes from .codequest-notes.md."""
    notes_path = Path(project_path) / NOTES_FILENAME
    if notes_path.is_file():
        try:
            return notes_path.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def _save_notes(project_path: str, content: str) -> None:
    """Write project notes to .codequest-notes.md."""
    notes_path = Path(project_path) / NOTES_FILENAME
    notes_path.write_text(content, encoding="utf-8")


def _render_markdown_to_html(md_text: str) -> str:
    """Convert markdown to HTML. Uses the markdown library if available,
    otherwise wraps in <pre> tags."""
    if not md_text:
        return ""
    try:
        import markdown
        return markdown.markdown(
            md_text,
            extensions=["fenced_code", "tables", "toc"],
        )
    except ImportError:
        # Fallback: basic HTML-escaped pre block
        from markupsafe import escape
        return f'<pre class="readme-raw">{escape(md_text)}</pre>'


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.secret_key = os.urandom(24)

    # Create model selector once at app level
    model_selector = ModelSelector()

    # ------------------------------------------------------------------
    # Jinja helpers
    # ------------------------------------------------------------------
    @app.template_filter("format_date")
    def format_date_filter(ts: float) -> str:
        return _format_timestamp(ts)

    @app.context_processor
    def inject_globals():
        projects = get_projects()
        return {
            "version": __version__,
            "project_count": len(projects),
            "active_model": model_selector.active_name,
            "theme": _get_theme_colors(),
        }

    # ------------------------------------------------------------------
    # Page routes (HTML)
    # ------------------------------------------------------------------

    @app.route("/")
    def dashboard():
        """Dashboard grid of project cards."""
        config = get_config()
        favorites = config.get("favorites", [])
        tags = config.get("tags", {})
        all_tags = sorted({t for tlist in tags.values() for t in tlist})

        projects = get_projects()
        project_dicts = [_project_to_dict(p) for p in projects]

        # Annotate with favorites and tags
        for pd in project_dicts:
            pd["is_favorite"] = pd["name"] in favorites
            pd["tags"] = tags.get(pd["name"], [])

        # Sort favorites to top
        project_dicts.sort(key=lambda p: (not p["is_favorite"], p["name"].lower()))

        return render_template(
            "dashboard.html",
            projects=project_dicts,
            all_tags=all_tags,
        )

    @app.route("/project/<name>")
    def project_detail(name: str):
        """Project detail page."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            abort(404)

        proj_dict = _project_to_dict(proj)
        readme_info = parse_readme(proj.readme_content) if proj.readme_content else None
        readme_html = _render_markdown_to_html(proj.readme_content)
        run_commands = get_run_commands(proj.path)
        summary_card = get_summary_card(readme_info) if readme_info else ""

        project_notes = _get_notes(proj.path)

        config = get_config()

        return render_template(
            "project.html",
            project=proj_dict,
            readme_html=readme_html,
            readme_info=readme_info,
            run_commands=run_commands,
            summary_card=summary_card,
            project_notes=project_notes,
            integrations=config.get("integrations", {}),
        )

    @app.route("/search")
    def search():
        """Search across project names and README content."""
        query = request.args.get("q", "").strip().lower()
        config = get_config()
        favorites = config.get("favorites", [])
        tags = config.get("tags", {})
        all_tags = sorted({t for tlist in tags.values() for t in tlist})

        projects = get_projects()
        if query:
            filtered = []
            for p in projects:
                if query in p.name.lower():
                    filtered.append(p)
                elif query in p.readme_content.lower():
                    filtered.append(p)
                elif query in p.project_type.lower():
                    filtered.append(p)
            project_dicts = [_project_to_dict(p) for p in filtered]
        else:
            project_dicts = [_project_to_dict(p) for p in projects]

        for pd in project_dicts:
            pd["is_favorite"] = pd["name"] in favorites
            pd["tags"] = tags.get(pd["name"], [])

        return render_template(
            "dashboard.html",
            projects=project_dicts,
            search_query=query,
            all_tags=all_tags,
        )

    @app.route("/assistant")
    def assistant():
        """AI chat page."""
        projects = get_projects()
        project_names = [p.name for p in projects]
        backends = model_selector.status()
        return render_template(
            "assistant.html",
            project_names=project_names,
            backends=backends,
        )

    @app.route("/settings")
    def settings():
        """Config editor page."""
        config = get_config()
        return render_template(
            "settings.html",
            config=config,
            theme_presets=THEME_PRESETS,
            current_theme=config.get("theme", "phosphor-green"),
            theme_colors=config.get("theme_colors", THEME_PRESETS["phosphor-green"]),
            integrations=config.get("integrations", {}),
        )

    @app.route("/dependencies")
    def dependencies():
        """Dependencies overview page."""
        cache = deps_load_cache()
        return render_template("dependencies.html", deps_data=cache)

    @app.route("/connections")
    def connections():
        """Project connections graph page."""
        return render_template("connections.html")

    # ------------------------------------------------------------------
    # API endpoints (JSON)
    # ------------------------------------------------------------------

    @app.route("/api/projects")
    def api_projects():
        """Return all indexed projects as JSON array."""
        projects = get_projects()
        return jsonify([_project_to_dict(p) for p in projects])

    @app.route("/api/project/<name>")
    def api_project(name: str):
        """Single project details as JSON."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404
        return jsonify(_project_to_dict(proj))

    @app.route("/api/run/<name>", methods=["POST"])
    def api_run(name: str):
        """Execute a command in a project's directory."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404

        data = request.get_json(silent=True) or {}
        command_str = data.get("command", "").strip()
        if not command_str:
            return jsonify({"error": "No command provided"}), 400

        cmd = RunCommand(
            label=command_str,
            command=command_str,
            cwd=str(proj.path),
        )

        try:
            result = execute_command(cmd, timeout=60)
            return jsonify({
                "output": (result.stdout or "") + (result.stderr or ""),
                "returncode": result.returncode,
            })
        except Exception as exc:
            return jsonify({
                "output": f"Error: {exc}\n{traceback.format_exc()}",
                "returncode": -1,
            })

    @app.route("/api/ask", methods=["POST"])
    def api_ask():
        """AI assistant endpoint."""
        data = request.get_json(silent=True) or {}
        question = data.get("question", "").strip()
        project_name = data.get("project", "").strip()
        use_model = data.get("model", "").strip()

        if not question:
            return jsonify({"error": "No question provided"}), 400

        # Build context from project if specified
        context = ""
        if project_name:
            projects = get_projects()
            proj = _find_project(project_name, projects)
            if proj:
                readme_info = parse_readme(proj.readme_content) if proj.readme_content else None
                context_parts = [
                    f"Project: {proj.name}",
                    f"Type: {proj.project_type}",
                    f"Path: {proj.path}",
                ]
                if readme_info:
                    context_parts.append(f"README Summary:\n{get_summary_card(readme_info)}")
                context = "\n".join(context_parts)

        try:
            if use_model:
                answer, model_name = model_selector.ask_with(question, context, use_model)
            else:
                answer = model_selector.ask(question, context)
                model_name = model_selector.active_name
            return jsonify({
                "answer": answer,
                "model": model_name,
            })
        except Exception as exc:
            return jsonify({
                "answer": f"Error: {exc}",
                "model": "error",
            }), 500

    # ------------------------------------------------------------------
    # Model Selection API
    # ------------------------------------------------------------------

    @app.route("/api/models")
    def api_models():
        """Return all available LLM models with status."""
        return jsonify({"models": model_selector.list_models()})

    @app.route("/api/model/switch", methods=["POST"])
    def api_model_switch():
        """Switch the globally active LLM model."""
        data = request.get_json(silent=True) or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "No model name provided"}), 400
        if model_selector.switch_to(name):
            return jsonify({"active": name})
        return jsonify({"error": f"Model '{name}' not found or unavailable"}), 400

    @app.route("/api/notes/<name>", methods=["GET"])
    def api_get_notes(name: str):
        """Get project notes."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404
        return jsonify({"notes": _get_notes(proj.path)})

    @app.route("/api/notes/<name>", methods=["POST"])
    def api_save_notes(name: str):
        """Save project notes to .codequest-notes.md."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404

        data = request.get_json(silent=True) or {}
        content = data.get("notes", "")

        try:
            _save_notes(proj.path, content)
            return jsonify({"saved": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/open-editor/<name>", methods=["POST"])
    def api_open_editor(name: str):
        """Open a project in VS Code or Cursor."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404

        data = request.get_json(silent=True) or {}
        editor = data.get("editor", "code")

        if editor not in ("code", "cursor"):
            return jsonify({"error": "Unknown editor"}), 400

        try:
            subprocess.Popen(
                [editor, str(proj.path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return jsonify({"opened": True, "editor": editor})
        except FileNotFoundError:
            return jsonify({"error": f"{editor} is not installed or not in PATH"}), 404
        except OSError as exc:
            return jsonify({"error": str(exc)}), 500

    @app.route("/api/editors")
    def api_editors():
        """Check which editors are available."""
        import shutil
        return jsonify({
            "code": shutil.which("code") is not None,
            "cursor": shutil.which("cursor") is not None,
        })

    @app.route("/api/settings", methods=["POST"])
    def api_save_settings():
        """Save all non-theme settings."""
        data = request.get_json(silent=True) or {}
        config = get_config()

        if "scan_paths" in data:
            val = data["scan_paths"]
            if isinstance(val, list) and all(isinstance(v, str) for v in val):
                config["scan_paths"] = val

        if "auto_discover" in data:
            config["auto_discover"] = bool(data["auto_discover"])

        if "auto_discover_paths" in data:
            val = data["auto_discover_paths"]
            if isinstance(val, list) and all(isinstance(v, str) for v in val):
                config["auto_discover_paths"] = val

        if "exclude_paths" in data:
            val = data["exclude_paths"]
            if isinstance(val, list) and all(isinstance(v, str) for v in val):
                config["exclude_paths"] = val

        if "llm" in data:
            llm = config.get("llm", {})
            llm_data = data["llm"]
            for key in ("primary", "claude_model"):
                if key in llm_data and isinstance(llm_data[key], str):
                    llm[key] = llm_data[key].strip()
            if "ollama_models" in llm_data and isinstance(llm_data["ollama_models"], list):
                llm["ollama_models"] = [
                    str(m).strip() for m in llm_data["ollama_models"] if str(m).strip()
                ]
            if "force_backend" in llm_data:
                fb = llm_data["force_backend"]
                llm["force_backend"] = fb if fb in ("claude", "ollama") else None
            config["llm"] = llm

        if "web" in data:
            web = config.get("web", {})
            if "port" in data["web"]:
                try:
                    port = int(data["web"]["port"])
                    if 1024 <= port <= 65535:
                        web["port"] = port
                except (ValueError, TypeError):
                    pass
            if "auto_open_browser" in data["web"]:
                web["auto_open_browser"] = bool(data["web"]["auto_open_browser"])
            config["web"] = web

        if "integrations" in data:
            integ = config.get("integrations", {})
            for key in ("linear_team", "jira_instance", "jira_project", "asana_workspace"):
                if key in data["integrations"] and isinstance(data["integrations"][key], str):
                    integ[key] = data["integrations"][key].strip()
            config["integrations"] = integ

        save_config(config)

        # Bust the cached config
        from codequest import config as config_module
        config_module._config = None

        return jsonify({"saved": True})

    @app.route("/api/theme/presets")
    def api_theme_presets():
        """Return available theme presets."""
        return jsonify(THEME_PRESETS)

    @app.route("/api/theme", methods=["POST"])
    def api_save_theme():
        """Save theme colors to config."""
        global _config
        data = request.get_json(silent=True) or {}
        preset_name = data.get("preset", "custom")
        colors = data.get("colors", {})

        # Validate: must have all 4 color keys
        required = {"green", "cyan", "magenta", "amber"}
        if not required.issubset(colors.keys()):
            return jsonify({"error": "Missing color keys"}), 400

        # Validate hex format
        for key in required:
            val = colors[key]
            if not re.match(r"^#[0-9a-fA-F]{6}$", val):
                return jsonify({"error": f"Invalid hex color for {key}: {val}"}), 400

        config = get_config()
        config["theme"] = preset_name
        config["theme_colors"] = {k: colors[k] for k in required}
        save_config(config)

        # Bust the cached config so it reloads
        from codequest import config as config_module
        config_module._config = None

        return jsonify({"saved": True, "theme": _derive_theme(colors)})

    @app.route("/api/changelog/<name>")
    def api_changelog(name: str):
        """Return git commit history for a project."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404
        entries = _get_changelog(str(proj.path))
        return jsonify({"entries": entries, "is_git": proj.is_git_repo})

    @app.route("/api/repo-visibility/<name>")
    def api_repo_visibility(name: str):
        """Return whether a GitHub repo is public or private."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404
        visibility = _get_repo_visibility(proj.git_remote_url)
        return jsonify({"visibility": visibility})

    @app.route("/api/rescan", methods=["POST"])
    def api_rescan():
        """Re-index projects."""
        try:
            projects = scan_all()
            save_index(projects)
            return jsonify({"count": len(projects)})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    # ------------------------------------------------------------------
    # Git status API (Phase 1A)
    # ------------------------------------------------------------------

    @app.route("/api/git-status/<name>")
    def api_git_status(name: str):
        """Return git status for a project."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404
        if not proj.is_git_repo:
            return jsonify({"error": "Not a git repo"}), 400

        project_path = str(proj.path)
        result_data = {"dirty": False, "ahead": 0, "behind": 0, "branch": ""}

        # Get current branch
        try:
            r = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=project_path, timeout=5,
            )
            if r.returncode == 0:
                result_data["branch"] = r.stdout.strip()
        except (subprocess.TimeoutExpired, OSError):
            pass

        # Check for dirty working tree
        try:
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, cwd=project_path, timeout=5,
            )
            if r.returncode == 0:
                result_data["dirty"] = bool(r.stdout.strip())
        except (subprocess.TimeoutExpired, OSError):
            pass

        # Check ahead/behind upstream
        try:
            r = subprocess.run(
                ["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                capture_output=True, text=True, cwd=project_path, timeout=5,
            )
            if r.returncode == 0:
                parts = r.stdout.strip().split()
                if len(parts) == 2:
                    result_data["ahead"] = int(parts[0])
                    result_data["behind"] = int(parts[1])
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass

        return jsonify(result_data)

    # ------------------------------------------------------------------
    # Favorites API (Phase 1B)
    # ------------------------------------------------------------------

    @app.route("/api/favorite/<name>", methods=["POST"])
    def api_toggle_favorite(name: str):
        """Toggle favorite status for a project."""
        config = get_config()
        favorites = config.get("favorites", [])
        if name in favorites:
            favorites.remove(name)
            is_fav = False
        else:
            favorites.append(name)
            is_fav = True
        config["favorites"] = favorites
        save_config(config)
        from codequest import config as config_module
        config_module._config = None
        return jsonify({"favorite": is_fav})

    @app.route("/api/favorites")
    def api_favorites():
        """Return list of favorite project names."""
        config = get_config()
        return jsonify({"favorites": config.get("favorites", [])})

    # ------------------------------------------------------------------
    # Tags API (Phase 1C)
    # ------------------------------------------------------------------

    @app.route("/api/tags/<name>", methods=["POST"])
    def api_set_tags(name: str):
        """Set tags for a project."""
        data = request.get_json(silent=True) or {}
        new_tags = data.get("tags", [])
        if not isinstance(new_tags, list):
            return jsonify({"error": "tags must be a list"}), 400

        config = get_config()
        tags = config.get("tags", {})
        tags[name] = [str(t).strip() for t in new_tags if str(t).strip()]
        config["tags"] = tags
        save_config(config)
        from codequest import config as config_module
        config_module._config = None
        return jsonify({"tags": tags[name]})

    @app.route("/api/tags")
    def api_tags():
        """Return all tags."""
        config = get_config()
        return jsonify({"tags": config.get("tags", {})})

    # ------------------------------------------------------------------
    # Dependencies API (Phase 2)
    # ------------------------------------------------------------------

    @app.route("/api/deps/scan", methods=["POST"])
    def api_deps_scan():
        """Trigger a full dependency scan in background."""
        with _deps_scan_lock:
            if _deps_scan_status["running"]:
                return jsonify({"error": "Scan already running"}), 409

        projects = get_projects()
        scannable = [
            {"name": p.name, "path": str(p.path), "project_type": p.project_type}
            for p in projects
            if p.project_type in ("Python", "Node")
        ]

        with _deps_scan_lock:
            _deps_scan_status["running"] = True
            _deps_scan_status["progress"] = 0
            _deps_scan_status["total"] = len(scannable)
            _deps_scan_status["current"] = ""

        def _run_scan():
            cache = deps_load_cache()
            for i, p in enumerate(scannable):
                with _deps_scan_lock:
                    _deps_scan_status["progress"] = i
                    _deps_scan_status["current"] = p["name"]
                result = deps_scan_project(p["name"], p["path"], p["project_type"])
                cache[p["name"]] = result
            deps_save_cache(cache)
            with _deps_scan_lock:
                _deps_scan_status["running"] = False
                _deps_scan_status["progress"] = len(scannable)
                _deps_scan_status["current"] = "done"

        thread = threading.Thread(target=_run_scan, daemon=True)
        thread.start()
        return jsonify({"started": True, "total": len(scannable)})

    @app.route("/api/deps/scan/<name>", methods=["POST"])
    def api_deps_scan_single(name: str):
        """Scan a single project's dependencies."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404

        result = deps_scan_project(proj.name, str(proj.path), proj.project_type)
        cache = deps_load_cache()
        cache[proj.name] = result
        deps_save_cache(cache)
        return jsonify(result)

    @app.route("/api/deps/status")
    def api_deps_status():
        """Check dependency scan progress."""
        with _deps_scan_lock:
            return jsonify(dict(_deps_scan_status))

    @app.route("/api/deps/data")
    def api_deps_data():
        """Return cached dependency scan results."""
        cache = deps_load_cache()
        return jsonify(cache)

    # ------------------------------------------------------------------
    # Connections API (Phase 3)
    # ------------------------------------------------------------------

    @app.route("/api/connections/data")
    def api_connections_data():
        """Return project connection graph data."""
        cache = connections_load_cache()
        if connections_cache_fresh(cache):
            return jsonify(cache)
        # Auto-refresh if stale
        projects = get_projects()
        proj_dicts = [
            {"name": p.name, "path": str(p.path), "project_type": p.project_type}
            for p in projects
        ]
        result = connections_analyze(proj_dicts)
        connections_save_cache(result)
        return jsonify(result)

    @app.route("/api/connections/refresh", methods=["POST"])
    def api_connections_refresh():
        """Re-analyze project connections."""
        projects = get_projects()
        proj_dicts = [
            {"name": p.name, "path": str(p.path), "project_type": p.project_type}
            for p in projects
        ]
        result = connections_analyze(proj_dicts)
        connections_save_cache(result)
        return jsonify(result)

    # ------------------------------------------------------------------
    # Project Stats API (Phase 4A)
    # ------------------------------------------------------------------

    @app.route("/api/stats/<name>")
    def api_project_stats(name: str):
        """Return file stats for a project."""
        projects = get_projects()
        proj = _find_project(name, projects)
        if not proj:
            return jsonify({"error": "Project not found"}), 404
        stats = _get_project_stats(str(proj.path))
        # Don't expose internal timestamp
        result = {k: v for k, v in stats.items() if not k.startswith("_")}
        return jsonify(result)

    # ------------------------------------------------------------------
    # Bulk Actions API (Phase 4B)
    # ------------------------------------------------------------------

    @app.route("/api/bulk/open-editor", methods=["POST"])
    def api_bulk_open_editor():
        """Open multiple projects in VS Code."""
        data = request.get_json(silent=True) or {}
        names = data.get("names", [])
        editor = data.get("editor", "code")
        if editor not in ("code", "cursor"):
            return jsonify({"error": "Unknown editor"}), 400

        projects = get_projects()
        opened = []
        for name in names:
            proj = _find_project(name, projects)
            if proj:
                try:
                    subprocess.Popen(
                        [editor, str(proj.path)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    opened.append(name)
                except (FileNotFoundError, OSError):
                    pass
        return jsonify({"opened": opened})

    # ------------------------------------------------------------------
    # Error handlers
    # ------------------------------------------------------------------

    @app.errorhandler(404)
    def not_found(e):
        return render_template(
            "base.html",
            error_title="404 - NOT FOUND",
            error_message="The quest continues... but not here.",
        ), 404

    return app


# ---------------------------------------------------------------------------
# Run helper
# ---------------------------------------------------------------------------

def run_server(port: int = 8080) -> None:
    """Start the Flask development server."""
    config = get_config()
    web_config = config.get("web", {})
    port = web_config.get("port", port)
    app = create_app()
    print(f"\n  >> CodeQuest Web Dashboard starting on http://localhost:{port}")
    print(f"  >> Press Ctrl+C to stop\n")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run_server()
