"""
CodeQuest Web Dashboard - Flask application.

Serves the retro 8-bit themed project dashboard on localhost:8080.
Provides both HTML page routes and JSON API endpoints for project
management, command execution, and AI assistant integration.
"""

from __future__ import annotations

import datetime
import os
import traceback
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    render_template,
    request,
    abort,
)

from codequest import __version__
from codequest.scanner import get_projects, scan_all, save_index, ProjectInfo
from codequest.readme_parser import parse_readme, get_summary_card
from codequest.runner import get_run_commands, execute_command, RunCommand
from codequest.models import ModelSelector
from codequest.config import get_config, save_config


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
        }

    # ------------------------------------------------------------------
    # Page routes (HTML)
    # ------------------------------------------------------------------

    @app.route("/")
    def dashboard():
        """Dashboard grid of project cards."""
        projects = get_projects()
        project_dicts = [_project_to_dict(p) for p in projects]
        return render_template("dashboard.html", projects=project_dicts)

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

        return render_template(
            "project.html",
            project=proj_dict,
            readme_html=readme_html,
            readme_info=readme_info,
            run_commands=run_commands,
            summary_card=summary_card,
        )

    @app.route("/search")
    def search():
        """Search across project names and README content."""
        query = request.args.get("q", "").strip().lower()
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

        return render_template(
            "dashboard.html",
            projects=project_dicts,
            search_query=query,
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
        return render_template("settings.html", config=config)

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
            answer = model_selector.ask(question, context)
            return jsonify({
                "answer": answer,
                "model": model_selector.active_name,
            })
        except Exception as exc:
            return jsonify({
                "answer": f"Error: {exc}",
                "model": "error",
            }), 500

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
