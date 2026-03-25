"""Dependency scanning for CodeQuest projects."""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

CACHE_FILE = Path.home() / ".codequest" / "deps_cache.json"
REPORT_FILE = Path.home() / ".codequest" / "deps-report.md"
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


def _run_full(cmd: list[str], cwd: str, timeout: int = 60) -> tuple[int, str, str]:
    """Run a command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except (FileNotFoundError, OSError) as e:
        return -1, "", str(e)


def _find_venv_pip(project_path: Path) -> Optional[str]:
    """Find the pip executable in a project's virtualenv."""
    for venv_name in (".venv", "venv", "env"):
        candidate = project_path / venv_name / "bin" / "pip"
        if candidate.exists():
            return str(candidate)
    return None


def _find_venv_python(project_path: Path) -> Optional[str]:
    """Find the python executable in a project's virtualenv."""
    for venv_name in (".venv", "venv", "env"):
        candidate = project_path / venv_name / "bin" / "python"
        if candidate.exists():
            return str(candidate)
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

    venv_pip = _find_venv_pip(project_path)

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
    """Save dependency scan results to cache and generate markdown report."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)
    save_report(data)


def is_cache_fresh(cache: dict, project_name: str) -> bool:
    """Check if cached data for a project is within TTL."""
    entry = cache.get(project_name)
    if not entry:
        return False
    scanned_at = entry.get("scanned_at", 0)
    return (time.time() - scanned_at) < CACHE_TTL


def generate_report(cache_data: dict, severity_filter: Optional[str] = None) -> str:
    """Generate a markdown dependency report from cached scan data.

    Args:
        cache_data: The full deps cache dict (keyed by project name).
        severity_filter: Optional filter - "major", "minor", or "patch".

    Returns:
        Formatted markdown string ready for reading or file output.
    """
    from datetime import datetime

    # Collect projects with outdated deps
    projects_with_deps = []
    for name, data in cache_data.items():
        if data.get("total_outdated", 0) > 0:
            projects_with_deps.append(data)

    # Sort: most major-severity first, then by total outdated
    projects_with_deps.sort(
        key=lambda p: (
            -p.get("severity_counts", {}).get("major", 0),
            -p.get("severity_counts", {}).get("minor", 0),
            -p.get("total_outdated", 0),
        )
    )

    # Totals
    total_pkgs = 0
    total_major = 0
    total_minor = 0
    total_patch = 0
    total_unknown = 0
    for p in projects_with_deps:
        sc = p.get("severity_counts", {})
        total_major += sc.get("major", 0)
        total_minor += sc.get("minor", 0)
        total_patch += sc.get("patch", 0)
        total_unknown += sc.get("unknown", 0)
        total_pkgs += p.get("total_outdated", 0)

    lines = []
    lines.append("# CodeQuest Dependency Report")
    lines.append("")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"Generated: {now}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total outdated packages:** {total_pkgs}")
    lines.append(f"- **Projects affected:** {len(projects_with_deps)} / {len(cache_data)}")
    lines.append(f"- **MAJOR (breaking):** {total_major}")
    lines.append(f"- **Minor (feature):** {total_minor}")
    lines.append(f"- **Patch (bugfix):** {total_patch}")
    if total_unknown:
        lines.append(f"- **Unknown:** {total_unknown}")
    lines.append("")

    if severity_filter:
        lines.append(f"> Filtered to **{severity_filter}** severity only")
        lines.append("")

    # Per-project breakdown
    lines.append("## By Project")
    lines.append("")

    for proj in projects_with_deps:
        deps = proj.get("outdated", [])
        if severity_filter:
            deps = [d for d in deps if d.get("severity") == severity_filter]
        if not deps:
            continue

        sc = proj.get("severity_counts", {})
        name = proj.get("name", "unknown")
        ptype = proj.get("project_type", "?")
        badge_parts = []
        if sc.get("major", 0):
            badge_parts.append(f"{sc['major']} MAJOR")
        if sc.get("minor", 0):
            badge_parts.append(f"{sc['minor']} minor")
        if sc.get("patch", 0):
            badge_parts.append(f"{sc['patch']} patch")
        badge = " | ".join(badge_parts)

        lines.append(f"### {name} ({ptype}) — {len(deps)} outdated [{badge}]")
        lines.append("")
        lines.append("| Package | Current | Latest | Severity | Type |")
        lines.append("|---------|---------|--------|----------|------|")

        # Sort deps: major first, then minor, then patch
        sev_order = {"major": 0, "minor": 1, "patch": 2, "unknown": 3}
        deps.sort(key=lambda d: sev_order.get(d.get("severity", "unknown"), 3))

        for dep in deps:
            sev = dep.get("severity", "?")
            sev_display = f"**{sev.upper()}**" if sev == "major" else sev
            lines.append(
                f"| {dep.get('name', '?')} "
                f"| {dep.get('current', '?')} "
                f"| {dep.get('latest', '?')} "
                f"| {sev_display} "
                f"| {dep.get('type', '?')} |"
            )
        lines.append("")

    if not projects_with_deps:
        lines.append("All projects are up to date!")
        lines.append("")

    return "\n".join(lines)


def save_report(cache_data: dict) -> None:
    """Generate and save the markdown dependency report."""
    report = generate_report(cache_data)
    REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_FILE, "w") as f:
        f.write(report)


# ---------------------------------------------------------------------------
# Dependency Engine: plan, fix, lock, test detection, health scoring
# ---------------------------------------------------------------------------

def _detect_test_command(project_path: str, project_type: str) -> Optional[list[str]]:
    """Detect if a project has a test suite and return the command to run it."""
    pp = Path(project_path)

    if project_type == "Python":
        # Find pytest in venv
        venv_pytest = None
        for venv_name in (".venv", "venv", "env"):
            candidate = pp / venv_name / "bin" / "pytest"
            if candidate.exists():
                venv_pytest = str(candidate)
                break
        if not venv_pytest:
            return None
        # Check that tests actually exist
        has_tests = (
            (pp / "tests").is_dir()
            or (pp / "test").is_dir()
            or any(pp.glob("test_*.py"))
            or any(pp.glob("**/test_*.py"))
        )
        if has_tests:
            return [venv_pytest, "-x", "--tb=short", "-q"]
        return None

    elif project_type == "Node":
        pkg_json = pp / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                test_script = pkg.get("scripts", {}).get("test", "")
                if test_script and "no test specified" not in test_script:
                    return ["npm", "test"]
            except (json.JSONDecodeError, OSError):
                pass
        return None

    return None


def plan_updates(
    project_name: str,
    cache: dict,
    severity_filter: Optional[str] = None,
) -> dict:
    """Generate an update plan for a project with risk classification.

    severity_filter controls inclusion:
      "patch" = only patch, "minor" = patch+minor, "major"/None = all
    """
    entry = cache.get(project_name)
    if not entry:
        return {"project": project_name, "error": "Not found in cache", "updates": []}

    project_path = entry.get("path", "")
    project_type = entry.get("project_type", "")
    pp = Path(project_path)

    # Determine which severities to include
    include_sevs = set()
    if severity_filter == "patch":
        include_sevs = {"patch"}
    elif severity_filter == "minor":
        include_sevs = {"patch", "minor"}
    else:  # "major" or None — include all
        include_sevs = {"patch", "minor", "major", "unknown"}

    venv_pip = _find_venv_pip(pp) if project_type == "Python" else None
    updates = []

    for dep in entry.get("outdated", []):
        sev = dep.get("severity", "unknown")
        if sev not in include_sevs:
            continue

        name = dep.get("name", "")
        latest = dep.get("latest", "?")

        # Risk classification
        if sev == "patch":
            risk = "auto-safe"
            safe = True
        elif sev == "minor":
            risk = "review"
            safe = True
        else:
            risk = "breaking-risk"
            safe = False

        # Build the command
        if project_type == "Python" and venv_pip:
            command = f"{venv_pip} install {name}=={latest}"
        elif project_type == "Node":
            if sev == "major":
                command = f"npm install {name}@{latest}"
            else:
                command = f"npm update {name}"
        else:
            command = f"# Cannot determine update command for {name}"

        updates.append({
            "name": name,
            "current": dep.get("current", "?"),
            "latest": latest,
            "severity": sev,
            "safe": safe,
            "risk": risk,
            "command": command,
        })

    # Sort: safe first, then by severity
    sev_order = {"patch": 0, "minor": 1, "major": 2, "unknown": 3}
    updates.sort(key=lambda u: sev_order.get(u["severity"], 3))

    auto_safe = sum(1 for u in updates if u["risk"] == "auto-safe")
    needs_review = sum(1 for u in updates if u["risk"] == "review")
    breaking = sum(1 for u in updates if u["risk"] == "breaking-risk")

    return {
        "project": project_name,
        "path": project_path,
        "project_type": project_type,
        "updates": updates,
        "summary": {
            "total": len(updates),
            "auto_safe": auto_safe,
            "needs_review": needs_review,
            "breaking_risk": breaking,
        },
    }


def execute_updates(
    project_name: str,
    cache: dict,
    severity_filter: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Execute planned updates for a project.

    Returns results dict with per-package status and optional test results.
    """
    plan = plan_updates(project_name, cache, severity_filter=severity_filter)
    if plan.get("error"):
        return {
            "project": project_name,
            "dry_run": dry_run,
            "error": plan["error"],
            "results": [],
        }

    project_path = plan["path"]
    project_type = plan["project_type"]
    results = []

    for update in plan["updates"]:
        if dry_run:
            results.append({
                "name": update["name"],
                "from_version": update["current"],
                "to_version": update["latest"],
                "severity": update["severity"],
                "risk": update["risk"],
                "status": "dry-run",
                "command": update["command"],
                "output": "",
            })
            continue

        # Parse and execute the command
        cmd_parts = update["command"].split()
        rc, stdout, stderr = _run_full(cmd_parts, project_path, timeout=120)

        results.append({
            "name": update["name"],
            "from_version": update["current"],
            "to_version": update["latest"],
            "severity": update["severity"],
            "risk": update["risk"],
            "status": "success" if rc == 0 else "failed",
            "command": update["command"],
            "output": stderr.strip() if rc != 0 else stdout.strip()[:200],
        })

    # Post-update: generate lock file and run tests (only if not dry run)
    lock_result = None
    test_result = None
    if not dry_run and any(r["status"] == "success" for r in results):
        lock_result = generate_lock_file(project_path, project_type)

        test_cmd = _detect_test_command(project_path, project_type)
        if test_cmd:
            rc, stdout, stderr = _run_full(test_cmd, project_path, timeout=300)
            test_result = {
                "available": True,
                "passed": rc == 0,
                "output": (stdout + stderr).strip()[-500:],  # last 500 chars
            }
        else:
            test_result = {"available": False, "passed": None, "output": ""}

        # Re-scan to update cache
        updated = scan_project(project_name, project_path, project_type)
        cache[project_name] = updated
        save_cache(cache)

    succeeded = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")

    return {
        "project": project_name,
        "dry_run": dry_run,
        "results": results,
        "lock_file": lock_result,
        "tests": test_result,
        "summary": f"{succeeded} updated, {failed} failed" if not dry_run
                   else f"{len(results)} planned (dry run)",
    }


def generate_lock_file(project_path: str, project_type: str) -> dict:
    """Generate a lock file for the project.

    Python: pip freeze > requirements.lock
    Node: npm install (regenerates package-lock.json)
    """
    pp = Path(project_path)

    if project_type == "Python":
        venv_pip = _find_venv_pip(pp)
        if not venv_pip:
            return {
                "project": pp.name,
                "lock_file": "",
                "status": "failed",
                "package_count": 0,
                "error": "No virtualenv found",
            }

        rc, stdout, stderr = _run_full([venv_pip, "freeze"], project_path)
        if rc != 0:
            return {
                "project": pp.name,
                "lock_file": "",
                "status": "failed",
                "package_count": 0,
                "error": stderr.strip(),
            }

        lock_path = pp / "requirements.lock"
        existed = lock_path.exists()
        try:
            lock_path.write_text(stdout)
            pkg_count = len([l for l in stdout.splitlines() if l.strip() and not l.startswith("#")])
            return {
                "project": pp.name,
                "lock_file": str(lock_path),
                "status": "updated" if existed else "created",
                "package_count": pkg_count,
                "error": None,
            }
        except OSError as e:
            return {
                "project": pp.name,
                "lock_file": "",
                "status": "failed",
                "package_count": 0,
                "error": str(e),
            }

    elif project_type == "Node":
        lock_path = pp / "package-lock.json"
        existed = lock_path.exists()
        rc, stdout, stderr = _run_full(["npm", "install"], project_path, timeout=120)
        if lock_path.exists():
            return {
                "project": pp.name,
                "lock_file": str(lock_path),
                "status": "updated" if existed else "created",
                "package_count": 0,  # npm doesn't give a simple count
                "error": None,
            }
        return {
            "project": pp.name,
            "lock_file": "",
            "status": "failed",
            "package_count": 0,
            "error": stderr.strip()[:200],
        }

    return {
        "project": pp.name,
        "lock_file": "",
        "status": "skipped",
        "package_count": 0,
        "error": f"Unsupported project type: {project_type}",
    }


def calculate_health_score(
    project_name: str, project_path: str, project_type: str, cache: dict
) -> dict:
    """Calculate a health score (0-100) for a project.

    Factors (weighted):
      - % packages up to date: 40 points
      - No major outdated: 15 points
      - Has lock file: 15 points
      - Has tests: 15 points
      - Has README: 10 points
      - Scan freshness (< 24h): 5 points
    """
    pp = Path(project_path)
    entry = cache.get(project_name, {})
    factors = {}

    # 1. % up to date (40 pts)
    total_outdated = entry.get("total_outdated", 0)
    # We need total installed to compute %; estimate from lock file or use outdated as proxy
    if total_outdated == 0:
        up_to_date_score = 40
        detail = "All packages up to date"
    else:
        # Penalize proportionally: 0 outdated = 40, 5 = 30, 10 = 20, 20+ = 0
        penalty = min(total_outdated * 2, 40)
        up_to_date_score = max(40 - penalty, 0)
        detail = f"{total_outdated} outdated packages"
    factors["up_to_date"] = {"score": up_to_date_score, "max": 40, "detail": detail}

    # 2. No major outdated (15 pts)
    major_count = entry.get("severity_counts", {}).get("major", 0)
    if major_count == 0:
        no_major_score = 15
        detail = "No major version gaps"
    else:
        no_major_score = max(15 - (major_count * 5), 0)
        detail = f"{major_count} major version gaps"
    factors["no_major"] = {"score": no_major_score, "max": 15, "detail": detail}

    # 3. Has lock file (15 pts)
    has_lock = False
    if project_type == "Python":
        has_lock = (pp / "requirements.lock").exists()
        # Also check if requirements.txt uses == pinning throughout
        if not has_lock:
            req = pp / "requirements.txt"
            if req.exists():
                try:
                    lines = [l.strip() for l in req.read_text().splitlines()
                             if l.strip() and not l.startswith("#") and not l.startswith("-")]
                    if lines and all("==" in l for l in lines):
                        has_lock = True
                except OSError:
                    pass
    elif project_type == "Node":
        has_lock = (pp / "package-lock.json").exists()

    lock_score = 15 if has_lock else 0
    factors["has_lock_file"] = {
        "score": lock_score, "max": 15,
        "detail": "Lock file present" if has_lock else "No lock file",
    }

    # 4. Has tests (15 pts)
    test_cmd = _detect_test_command(project_path, project_type)
    test_score = 15 if test_cmd else 0
    factors["has_tests"] = {
        "score": test_score, "max": 15,
        "detail": "Test suite detected" if test_cmd else "No tests found",
    }

    # 5. Has README (10 pts)
    has_readme = (pp / "README.md").exists() or (pp / "README.rst").exists()
    readme_score = 10 if has_readme else 0
    factors["has_readme"] = {
        "score": readme_score, "max": 10,
        "detail": "README present" if has_readme else "No README",
    }

    # 6. Scan freshness (5 pts)
    scanned_at = entry.get("scanned_at", 0)
    fresh = (time.time() - scanned_at) < 86400 if scanned_at else False
    fresh_score = 5 if fresh else 0
    factors["scan_fresh"] = {
        "score": fresh_score, "max": 5,
        "detail": "Scanned within 24h" if fresh else "Scan data stale or missing",
    }

    # Total
    total = sum(f["score"] for f in factors.values())
    if total >= 90:
        grade = "A"
    elif total >= 75:
        grade = "B"
    elif total >= 60:
        grade = "C"
    elif total >= 40:
        grade = "D"
    else:
        grade = "F"

    return {
        "project": project_name,
        "score": total,
        "grade": grade,
        "factors": factors,
    }
