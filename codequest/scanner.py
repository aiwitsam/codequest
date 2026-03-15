"""Project discovery and indexing for CodeQuest."""

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from codequest.config import get_config, resolve_path, get_exclude_paths, CONFIG_DIR, INDEX_FILE

# Files that indicate a directory is a project root
PROJECT_MARKERS = [
    "README.md",
    "README.rst",
    "README.txt",
    "package.json",
    "setup.py",
    "pyproject.toml",
    "Makefile",
    "Dockerfile",
    ".git",
    "Cargo.toml",
    "go.mod",
    "requirements.txt",
]

# Max age of cached index before a rescan is triggered (24 hours)
INDEX_MAX_AGE = 86400


@dataclass
class ProjectInfo:
    """Metadata about a discovered project."""

    name: str
    path: Path
    project_type: str  # Python, Node, Bash, Rust, Go, Static, Unknown
    readme_path: Optional[Path] = None
    readme_content: str = ""
    last_modified: float = 0.0
    last_accessed: float = 0.0
    is_git_repo: bool = False
    git_remote_url: str = ""
    is_claude_made: bool = False
    has_github: bool = False
    detected_run_commands: list[dict] = field(default_factory=list)
    detected_port: int | None = None


def detect_project_type(path: Path) -> str:
    """Detect what kind of project lives in *path* based on marker files.

    Checks in priority order so that a directory with both package.json and
    a Python marker is classified as Node (the more specific marker wins).
    """
    if (path / "package.json").exists():
        return "Node"
    if (path / "setup.py").exists() or (path / "pyproject.toml").exists() or (path / "requirements.txt").exists():
        return "Python"
    if (path / "Cargo.toml").exists():
        return "Rust"
    if (path / "go.mod").exists():
        return "Go"

    # Check for shell scripts at the top level
    try:
        sh_files = list(path.glob("*.sh"))
        if sh_files:
            return "Bash"
    except OSError:
        pass

    if (path / "index.html").exists():
        return "Static"

    return "Unknown"


def _detect_run_commands(path: Path, project_type: str) -> list[dict]:
    """Detect likely run / start commands for the project."""
    commands: list[dict] = []
    str_path = str(path)

    if project_type == "Node":
        pkg_json = path / "package.json"
        if pkg_json.exists():
            try:
                with open(pkg_json, "r") as f:
                    pkg = json.load(f)
                scripts = pkg.get("scripts", {})
                for key in ("start", "dev", "serve", "build", "test"):
                    if key in scripts:
                        commands.append({"label": f"npm run {key}", "cmd": f"npm run {key}", "cwd": str_path})
            except (json.JSONDecodeError, OSError):
                pass

    elif project_type == "Python":
        if (path / "setup.py").exists():
            commands.append({"label": "pip install -e .", "cmd": "pip install -e .", "cwd": str_path})
        if (path / "pyproject.toml").exists():
            commands.append({"label": "pip install -e .", "cmd": "pip install -e .", "cwd": str_path})
        # Look for a main module or __main__.py
        if (path / "__main__.py").exists():
            commands.append({"label": f"python -m {path.name}", "cmd": f"python -m {path.name}", "cwd": str_path})
        # Look for common entry-point scripts
        for candidate in ("main.py", "app.py", "cli.py", "run.py"):
            if (path / candidate).exists():
                commands.append({"label": f"python {candidate}", "cmd": f"python {candidate}", "cwd": str_path})

    elif project_type == "Rust":
        commands.append({"label": "cargo run", "cmd": "cargo run", "cwd": str_path})
        commands.append({"label": "cargo build", "cmd": "cargo build", "cwd": str_path})

    elif project_type == "Go":
        commands.append({"label": "go run .", "cmd": "go run .", "cwd": str_path})
        commands.append({"label": "go build", "cmd": "go build", "cwd": str_path})

    elif project_type == "Bash":
        try:
            for sh in sorted(path.glob("*.sh"))[:5]:
                commands.append({"label": f"bash {sh.name}", "cmd": f"bash {sh.name}", "cwd": str_path})
        except OSError:
            pass

    # Makefile targets (any project type)
    if (path / "Makefile").exists():
        commands.append({"label": "make", "cmd": "make", "cwd": str_path})

    # Docker
    if (path / "Dockerfile").exists():
        commands.append({"label": "docker build .", "cmd": "docker build .", "cwd": str_path})
    if (path / "docker-compose.yml").exists() or (path / "docker-compose.yaml").exists():
        commands.append({"label": "docker compose up", "cmd": "docker compose up", "cwd": str_path})

    return commands


def _detect_port(path: Path, project_type: str) -> int | None:
    """Detect a statically declared port from project files."""
    str_path = str(path)

    # package.json: scripts containing --port NNNN or -p NNNN
    if project_type == "Node":
        pkg_json = path / "package.json"
        if pkg_json.exists():
            try:
                with open(pkg_json, "r") as f:
                    pkg = json.load(f)
                scripts = pkg.get("scripts", {})
                for val in scripts.values():
                    m = re.search(r"(?:--port|-p)\s+(\d{4,5})", val)
                    if m:
                        return int(m.group(1))
            except (json.JSONDecodeError, OSError):
                pass

    # Python entry points: port=NNNN patterns
    if project_type == "Python":
        for candidate in ("app.py", "main.py", "server.py"):
            fpath = path / candidate
            if fpath.is_file():
                try:
                    content = fpath.read_text(encoding="utf-8", errors="replace")[:8192]
                    m = re.search(r"port\s*=\s*(\d{4,5})", content)
                    if m:
                        return int(m.group(1))
                except OSError:
                    pass

    # Dockerfile: EXPOSE NNNN
    dockerfile = path / "Dockerfile"
    if dockerfile.is_file():
        try:
            content = dockerfile.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"^EXPOSE\s+(\d{4,5})", content, re.MULTILINE)
            if m:
                return int(m.group(1))
        except OSError:
            pass

    # .env / .env.local: PORT=NNNN
    for env_file in (".env", ".env.local"):
        env_path = path / env_file
        if env_path.is_file():
            try:
                content = env_path.read_text(encoding="utf-8", errors="replace")
                m = re.search(r"^PORT\s*=\s*(\d{4,5})", content, re.MULTILINE)
                if m:
                    return int(m.group(1))
            except OSError:
                pass

    return None


def _read_readme(path: Path) -> tuple[Optional[Path], str]:
    """Find and read the first README file in *path*."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme = path / name
        if readme.is_file():
            try:
                content = readme.read_text(encoding="utf-8", errors="replace")
                return readme, content
            except OSError:
                return readme, ""
    return None, ""


def _git_info(path: Path) -> dict:
    """Gather git metadata for *path*. Returns a dict with git-related fields."""
    info = {
        "is_git_repo": False,
        "git_remote_url": "",
        "is_claude_made": False,
        "has_github": False,
    }

    git_dir = path / ".git"
    if not git_dir.exists():
        return info

    info["is_git_repo"] = True

    # Get remote URL
    try:
        result = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            # Parse first remote line: origin\thttps://... (fetch)
            first_line = result.stdout.strip().splitlines()[0]
            parts = first_line.split()
            if len(parts) >= 2:
                info["git_remote_url"] = parts[1]
                if "github.com" in parts[1]:
                    info["has_github"] = True
    except (subprocess.TimeoutExpired, OSError):
        pass

    # Check for Claude authorship
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--format=%an %ae", "--max-count=100"],
            capture_output=True,
            text=True,
            cwd=str(path),
            timeout=5,
        )
        if result.returncode == 0 and "claude" in result.stdout.lower():
            info["is_claude_made"] = True
    except (subprocess.TimeoutExpired, OSError):
        pass

    if not info["is_claude_made"]:
        try:
            result = subprocess.run(
                ["git", "log", "--all", "--grep=Co-Authored-By: Claude", "--max-count=1", "--format=%H"],
                capture_output=True,
                text=True,
                cwd=str(path),
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                info["is_claude_made"] = True
        except (subprocess.TimeoutExpired, OSError):
            pass

    return info


def scan_project(path: Path) -> ProjectInfo:
    """Build a ProjectInfo for a single project directory."""
    path = path.resolve()
    project_type = detect_project_type(path)
    readme_path, readme_content = _read_readme(path)
    git = _git_info(path)
    run_commands = _detect_run_commands(path, project_type)
    detected_port = _detect_port(path, project_type)

    # Use the project root directory mtime (fast, no deep recursion)
    try:
        last_modified = os.path.getmtime(str(path))
    except OSError:
        last_modified = 0.0

    try:
        last_accessed = os.path.getatime(str(path))
    except OSError:
        last_accessed = 0.0

    return ProjectInfo(
        name=path.name,
        path=path,
        project_type=project_type,
        readme_path=readme_path,
        readme_content=readme_content,
        last_modified=last_modified,
        last_accessed=last_accessed,
        is_git_repo=git["is_git_repo"],
        git_remote_url=git["git_remote_url"],
        is_claude_made=git["is_claude_made"],
        has_github=git["has_github"],
        detected_run_commands=run_commands,
        detected_port=detected_port,
    )


def _has_project_marker(path: Path) -> bool:
    """Return True if *path* contains at least one PROJECT_MARKER."""
    for marker in PROJECT_MARKERS:
        if (path / marker).exists():
            return True
    return False


def discover_projects(
    scan_paths: list[str],
    auto_discover: bool,
    auto_discover_paths: list[str],
    exclude_paths: set[Path],
) -> list[ProjectInfo]:
    """Discover projects from explicit paths and optional auto-discovery.

    Args:
        scan_paths: Explicit directories to treat as projects.
        auto_discover: Whether to walk auto_discover_paths looking for projects.
        auto_discover_paths: Base directories to scan 1-2 levels deep.
        exclude_paths: Resolved paths to skip entirely.
    """
    seen: set[Path] = set()
    projects: list[ProjectInfo] = []

    def _add_project(p: Path) -> None:
        resolved = p.resolve()
        if resolved in seen:
            return
        if resolved in exclude_paths:
            return
        seen.add(resolved)
        if resolved.is_dir():
            projects.append(scan_project(resolved))

    # 1. Explicit scan_paths
    for sp in scan_paths:
        _add_project(resolve_path(sp))

    # 2. Auto-discover: walk 1-2 levels deep in auto_discover_paths
    if auto_discover:
        for base_str in auto_discover_paths:
            base = resolve_path(base_str)
            if not base.is_dir():
                continue
            if base in exclude_paths:
                continue

            try:
                for child in sorted(base.iterdir()):
                    if not child.is_dir():
                        continue
                    child_resolved = child.resolve()
                    if child_resolved in exclude_paths:
                        continue
                    # Skip hidden directories (except .git-containing projects)
                    if child.name.startswith("."):
                        continue

                    # Level 1: check if child itself is a project
                    if _has_project_marker(child_resolved):
                        _add_project(child_resolved)
                        continue

                    # Level 2: check children of child
                    try:
                        for grandchild in sorted(child_resolved.iterdir()):
                            if not grandchild.is_dir():
                                continue
                            gc_resolved = grandchild.resolve()
                            if gc_resolved in exclude_paths:
                                continue
                            if grandchild.name.startswith("."):
                                continue
                            if _has_project_marker(gc_resolved):
                                _add_project(gc_resolved)
                    except (OSError, PermissionError):
                        continue
            except (OSError, PermissionError):
                continue

    return projects


def scan_all() -> list[ProjectInfo]:
    """Load config, discover all projects, return sorted by name."""
    config = get_config()
    exclude = get_exclude_paths()

    projects = discover_projects(
        scan_paths=config.get("scan_paths", []),
        auto_discover=config.get("auto_discover", True),
        auto_discover_paths=config.get("auto_discover_paths", ["~/"]),
        exclude_paths=exclude,
    )

    projects.sort(key=lambda p: p.name.lower())
    return projects


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _project_to_dict(proj: ProjectInfo) -> dict:
    """Convert a ProjectInfo to a JSON-serializable dict."""
    return {
        "name": proj.name,
        "path": str(proj.path),
        "project_type": proj.project_type,
        "readme_path": str(proj.readme_path) if proj.readme_path else None,
        "readme_content": proj.readme_content,
        "last_modified": proj.last_modified,
        "last_accessed": proj.last_accessed,
        "is_git_repo": proj.is_git_repo,
        "git_remote_url": proj.git_remote_url,
        "is_claude_made": proj.is_claude_made,
        "has_github": proj.has_github,
        "detected_run_commands": proj.detected_run_commands,
        "detected_port": proj.detected_port,
    }


def _dict_to_project(d: dict) -> ProjectInfo:
    """Reconstruct a ProjectInfo from a deserialized dict."""
    return ProjectInfo(
        name=d["name"],
        path=Path(d["path"]),
        project_type=d["project_type"],
        readme_path=Path(d["readme_path"]) if d.get("readme_path") else None,
        readme_content=d.get("readme_content", ""),
        last_modified=d.get("last_modified", 0.0),
        last_accessed=d.get("last_accessed", 0.0),
        is_git_repo=d.get("is_git_repo", False),
        git_remote_url=d.get("git_remote_url", ""),
        is_claude_made=d.get("is_claude_made", False),
        has_github=d.get("has_github", False),
        detected_run_commands=d.get("detected_run_commands", []),
        detected_port=d.get("detected_port"),
    )


# ---------------------------------------------------------------------------
# Index persistence
# ---------------------------------------------------------------------------

def load_index() -> list[ProjectInfo]:
    """Load the project index from ~/.codequest/index.json.

    Returns an empty list if the file does not exist or is older than 24 hours.
    """
    if not INDEX_FILE.exists():
        return []

    try:
        age = time.time() - os.path.getmtime(str(INDEX_FILE))
        if age > INDEX_MAX_AGE:
            return []
    except OSError:
        return []

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        return [_dict_to_project(d) for d in data]
    except (json.JSONDecodeError, OSError, KeyError, TypeError):
        return []


def save_index(projects: list[ProjectInfo]) -> None:
    """Persist the project list to ~/.codequest/index.json."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = [_project_to_dict(p) for p in projects]
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_projects(force_rescan: bool = False) -> list[ProjectInfo]:
    """Return the list of known projects, using the cached index when fresh.

    If *force_rescan* is True or the cache is stale / missing, a full
    scan_all() is performed and the results are saved to disk.
    """
    if not force_rescan:
        cached = load_index()
        if cached:
            return cached

    projects = scan_all()
    save_index(projects)
    return projects
