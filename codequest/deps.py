"""Dependency scanning for CodeQuest projects."""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

CACHE_FILE = Path.home() / ".codequest" / "deps_cache.json"
CACHE_TTL = 3600  # 1 hour


def _run(cmd: list[str], cwd: str, timeout: int = 30) -> Optional[str]:
    """Run a command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def _classify_severity(current: str, latest: str) -> str:
    """Compare version strings to determine severity: major, minor, or patch."""
    try:
        cur_parts = current.split(".")
        lat_parts = latest.split(".")
        # Strip non-numeric prefixes (e.g. ^1.2.3 or ~1.2.3)
        for i, part in enumerate(cur_parts):
            cur_parts[i] = "".join(c for c in part if c.isdigit())
        for i, part in enumerate(lat_parts):
            lat_parts[i] = "".join(c for c in part if c.isdigit())

        cur_major = int(cur_parts[0]) if cur_parts[0] else 0
        lat_major = int(lat_parts[0]) if lat_parts[0] else 0
        if lat_major > cur_major:
            return "major"

        cur_minor = int(cur_parts[1]) if len(cur_parts) > 1 and cur_parts[1] else 0
        lat_minor = int(lat_parts[1]) if len(lat_parts) > 1 and lat_parts[1] else 0
        if lat_minor > cur_minor:
            return "minor"

        return "patch"
    except (ValueError, IndexError):
        return "patch"


def scan_python(path: str) -> list[dict]:
    """Scan a Python project for outdated packages."""
    outdated = []
    project_path = Path(path)

    # Check for venv
    venv_pip = None
    for venv_name in (".venv", "venv", "env"):
        candidate = project_path / venv_name / "bin" / "pip"
        if candidate.exists():
            venv_pip = str(candidate)
            break

    if venv_pip:
        output = _run([venv_pip, "list", "--outdated", "--format=json"], path, timeout=60)
        if output:
            try:
                pkgs = json.loads(output)
                for pkg in pkgs:
                    outdated.append({
                        "name": pkg.get("name", ""),
                        "current": pkg.get("version", "?"),
                        "latest": pkg.get("latest_version", "?"),
                        "severity": _classify_severity(
                            pkg.get("version", "0"), pkg.get("latest_version", "0")
                        ),
                        "type": "direct",
                    })
            except json.JSONDecodeError:
                pass
    else:
        # Parse requirements.txt as fallback (no version comparison available)
        req_file = project_path / "requirements.txt"
        if req_file.exists():
            try:
                for line in req_file.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-"):
                        name = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].strip()
                        if name:
                            outdated.append({
                                "name": name,
                                "current": "installed",
                                "latest": "unknown",
                                "severity": "unknown",
                                "type": "direct",
                            })
            except OSError:
                pass

    return outdated


def scan_node(path: str) -> list[dict]:
    """Scan a Node.js project for outdated packages."""
    outdated = []
    output = _run(["npm", "outdated", "--json"], path, timeout=60)
    if output:
        try:
            pkgs = json.loads(output)
            for name, info in pkgs.items():
                current = info.get("current", "?")
                latest = info.get("latest", "?")
                dep_type = info.get("type", "dependencies")
                outdated.append({
                    "name": name,
                    "current": current,
                    "latest": latest,
                    "severity": _classify_severity(current, latest),
                    "type": "dev" if "dev" in dep_type.lower() else "direct",
                })
        except json.JSONDecodeError:
            pass
    return outdated


def scan_project(name: str, path: str, project_type: str) -> dict:
    """Scan a single project for outdated dependencies."""
    if project_type == "Python":
        deps = scan_python(path)
    elif project_type == "Node":
        deps = scan_node(path)
    else:
        deps = []

    severity_counts = {"major": 0, "minor": 0, "patch": 0, "unknown": 0}
    for d in deps:
        sev = d.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    return {
        "name": name,
        "path": path,
        "project_type": project_type,
        "outdated": deps,
        "total_outdated": len(deps),
        "severity_counts": severity_counts,
        "scanned_at": time.time(),
    }


def scan_all(projects: list[dict]) -> dict:
    """Scan all projects. projects is a list of dicts with name, path, project_type."""
    results = {}
    for p in projects:
        ptype = p.get("project_type", "")
        if ptype in ("Python", "Node"):
            results[p["name"]] = scan_project(p["name"], p["path"], ptype)
    return results


def load_cache() -> dict:
    """Load cached dependency scan results."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(data: dict) -> None:
    """Save dependency scan results to cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_cache_fresh(cache: dict, project_name: str) -> bool:
    """Check if cached data for a project is within TTL."""
    entry = cache.get(project_name)
    if not entry:
        return False
    scanned_at = entry.get("scanned_at", 0)
    return (time.time() - scanned_at) < CACHE_TTL
