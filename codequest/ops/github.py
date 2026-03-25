"""GitHub repository scanning and management via gh CLI."""

import json
import subprocess
import time
from pathlib import Path
from typing import Optional

CACHE_FILE = Path.home() / ".codequest" / "github_cache.json"
CACHE_TTL = 1800  # 30 minutes


def _run_gh(args: list[str], timeout: int = 30) -> Optional[str]:
    """Run a gh CLI command and return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def is_gh_available() -> bool:
    """Check if gh CLI is installed and authenticated."""
    out = _run_gh(["auth", "status"], timeout=10)
    # gh auth status returns 0 if authenticated
    return out is not None


def scan_repos() -> dict:
    """Scan all GitHub repos for the authenticated user."""
    if not is_gh_available():
        return {
            "repos": [],
            "total": 0,
            "error": "gh CLI not available or not authenticated. Run: gh auth login",
            "scanned_at": time.time(),
        }

    fields = [
        "name", "visibility", "updatedAt", "pushedAt", "description",
        "url", "isPrivate", "isArchived", "isFork", "stargazerCount",
        "forkCount", "primaryLanguage", "diskUsage",
        "defaultBranchRef", "hasIssuesEnabled",
    ]

    out = _run_gh([
        "repo", "list", "--limit", "200",
        "--json", ",".join(fields),
    ], timeout=30)

    if not out:
        return {
            "repos": [],
            "total": 0,
            "error": "Failed to list repos",
            "scanned_at": time.time(),
        }

    try:
        raw_repos = json.loads(out)
    except json.JSONDecodeError:
        return {
            "repos": [],
            "total": 0,
            "error": "Failed to parse gh output",
            "scanned_at": time.time(),
        }

    repos = []
    for r in raw_repos:
        lang = r.get("primaryLanguage")
        lang_name = lang.get("name", "") if isinstance(lang, dict) else ""
        default_branch = r.get("defaultBranchRef")
        branch_name = default_branch.get("name", "main") if isinstance(default_branch, dict) else "main"

        repos.append({
            "name": r.get("name", ""),
            "description": r.get("description", ""),
            "url": r.get("url", ""),
            "visibility": "private" if r.get("isPrivate") else "public",
            "is_archived": r.get("isArchived", False),
            "is_fork": r.get("isFork", False),
            "language": lang_name,
            "stars": r.get("stargazerCount", 0),
            "forks": r.get("forkCount", 0),
            "disk_kb": r.get("diskUsage", 0),
            "default_branch": branch_name,
            "pushed_at": r.get("pushedAt", ""),
            "updated_at": r.get("updatedAt", ""),
        })

    # Sort by most recently pushed
    repos.sort(key=lambda x: x.get("pushed_at", ""), reverse=True)

    public_count = sum(1 for r in repos if r["visibility"] == "public")
    private_count = sum(1 for r in repos if r["visibility"] == "private")
    archived_count = sum(1 for r in repos if r["is_archived"])

    return {
        "repos": repos,
        "total": len(repos),
        "public": public_count,
        "private": private_count,
        "archived": archived_count,
        "scanned_at": time.time(),
    }


def cross_reference_local(github_data: dict, local_projects: list) -> dict:
    """Cross-reference GitHub repos with local projects.

    Returns enriched data showing which repos are cloned locally and which aren't.
    """
    # Build lookup: local project name -> project info
    local_by_name = {}
    local_by_remote = {}
    for p in local_projects:
        local_by_name[p.name.lower()] = p
        if hasattr(p, 'git_remote_url') and p.git_remote_url:
            # Normalize remote URL for matching
            remote = p.git_remote_url.rstrip("/").rstrip(".git").lower()
            local_by_remote[remote] = p

    enriched = []
    for repo in github_data.get("repos", []):
        entry = dict(repo)
        name_lower = repo["name"].lower()
        url_lower = repo["url"].lower()

        # Try to match by name first, then by remote URL
        local = local_by_name.get(name_lower)
        if not local:
            # Check remote URLs
            for remote_url, proj in local_by_remote.items():
                if name_lower in remote_url or url_lower in remote_url:
                    local = proj
                    break

        if local:
            entry["cloned_locally"] = True
            entry["local_path"] = str(local.path)
            entry["local_type"] = local.project_type
            entry["has_local_changes"] = False  # Could check git status but expensive
        else:
            entry["cloned_locally"] = False
            entry["local_path"] = ""
            entry["local_type"] = ""
            entry["has_local_changes"] = False

        enriched.append(entry)

    cloned = sum(1 for e in enriched if e["cloned_locally"])
    not_cloned = sum(1 for e in enriched if not e["cloned_locally"])

    return {
        "repos": enriched,
        "total": len(enriched),
        "cloned_locally": cloned,
        "github_only": not_cloned,
        "public": github_data.get("public", 0),
        "private": github_data.get("private", 0),
        "archived": github_data.get("archived", 0),
        "scanned_at": github_data.get("scanned_at", time.time()),
    }


def load_cache() -> dict:
    """Load cached GitHub scan."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(data: dict) -> None:
    """Save GitHub scan to cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_cache_fresh(cache: dict) -> bool:
    """Check if cache is within TTL."""
    scanned_at = cache.get("scanned_at", 0)
    return (time.time() - scanned_at) < CACHE_TTL


def generate_report(data: dict) -> str:
    """Generate a markdown GitHub repos report."""
    from datetime import datetime

    lines = []
    lines.append("# GitHub Repository Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total repos:** {data.get('total', 0)}")
    lines.append(f"- **Public:** {data.get('public', 0)}")
    lines.append(f"- **Private:** {data.get('private', 0)}")
    lines.append(f"- **Archived:** {data.get('archived', 0)}")
    cloned = data.get("cloned_locally", "?")
    gh_only = data.get("github_only", "?")
    if cloned != "?":
        lines.append(f"- **Cloned locally:** {cloned}")
        lines.append(f"- **GitHub only (not cloned):** {gh_only}")
    lines.append("")

    repos = data.get("repos", [])
    if not repos:
        lines.append("No repos found.")
        return "\n".join(lines)

    # Cloned locally
    cloned_repos = [r for r in repos if r.get("cloned_locally")]
    gh_only_repos = [r for r in repos if not r.get("cloned_locally")]
    archived_repos = [r for r in repos if r.get("is_archived")]

    if cloned_repos:
        lines.append("## Cloned Locally")
        lines.append("")
        lines.append("| Repo | Visibility | Language | Local Path | Last Push |")
        lines.append("|------|-----------|----------|------------|-----------|")
        for r in cloned_repos:
            if r.get("is_archived"):
                continue
            pushed = r.get("pushed_at", "")[:10]
            lines.append(
                f"| {r['name']} | {r['visibility']} | {r.get('language', '-')} "
                f"| `{r.get('local_path', '')}` | {pushed} |"
            )
        lines.append("")

    if gh_only_repos:
        lines.append("## GitHub Only (Not Cloned)")
        lines.append("")
        lines.append("| Repo | Visibility | Language | Description | Last Push |")
        lines.append("|------|-----------|----------|-------------|-----------|")
        for r in gh_only_repos:
            if r.get("is_archived"):
                continue
            pushed = r.get("pushed_at", "")[:10]
            desc = (r.get("description", "") or "-")[:50]
            lines.append(
                f"| {r['name']} | {r['visibility']} | {r.get('language', '-')} "
                f"| {desc} | {pushed} |"
            )
        lines.append("")

    if archived_repos:
        lines.append("## Archived")
        lines.append("")
        for r in archived_repos:
            lines.append(f"- {r['name']} — {r.get('description', '') or 'no description'}")
        lines.append("")

    return "\n".join(lines)
