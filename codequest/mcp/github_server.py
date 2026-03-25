"""CodeQuest GitHub MCP server — exposes GitHub repos, issues, PRs, and search to Claude Code.

Powered by `gh` CLI (talks directly to GitHub API). No external dependencies beyond gh.
"""

import json
import logging
import subprocess
from typing import Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

logger = logging.getLogger(__name__)

server = Server("codequest-github")


def _gh(args: list[str], timeout: int = 30) -> Optional[str]:
    """Run a gh CLI command and return stdout."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode == 0:
            return result.stdout
        logger.warning("gh %s failed: %s", " ".join(args), result.stderr[:200])
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        logger.error("gh command error: %s", e)
        return None


def _gh_json(args: list[str], timeout: int = 30) -> Optional[list | dict]:
    """Run a gh CLI command that returns JSON."""
    out = _gh(args, timeout=timeout)
    if out:
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return None
    return None


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="github_list_repos",
            description="List all GitHub repos for the authenticated user. Shows name, visibility, language, description, last push date, and whether the repo is cloned locally.",
            inputSchema={
                "type": "object",
                "properties": {
                    "visibility": {
                        "type": "string",
                        "description": "Filter by visibility: 'public', 'private', or 'all' (default: all)",
                        "enum": ["all", "public", "private"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max repos to return (default: 50)",
                        "default": 50,
                    },
                },
            },
        ),
        Tool(
            name="github_repo_details",
            description="Get detailed info about a specific GitHub repo: description, topics, default branch, open issues/PR counts, disk usage, creation and push dates, license.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repo name (e.g., 'codequest') or full name (e.g., 'aiwitsam/codequest')",
                    },
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="github_list_issues",
            description="List open issues for a GitHub repo. Shows title, author, labels, and creation date.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repo name (e.g., 'codequest')",
                    },
                    "state": {
                        "type": "string",
                        "description": "Issue state: 'open', 'closed', or 'all' (default: open)",
                        "enum": ["open", "closed", "all"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max issues (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="github_list_prs",
            description="List pull requests for a GitHub repo. Shows title, author, state, branch, and review status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repo name (e.g., 'codequest')",
                    },
                    "state": {
                        "type": "string",
                        "description": "PR state: 'open', 'closed', 'merged', or 'all' (default: open)",
                        "enum": ["open", "closed", "merged", "all"],
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max PRs (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="github_repo_readme",
            description="Read the README content of a GitHub repo without needing it cloned locally.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repo name (e.g., 'codequest')",
                    },
                },
                "required": ["repo"],
            },
        ),
        Tool(
            name="github_search_repos",
            description="Search across all your GitHub repos by keyword. Searches repo names, descriptions, and topics.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (searches name, description, topics)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 20)",
                        "default": 20,
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="github_recent_activity",
            description="Show recent activity across all repos: latest commits, pushes, and events. Good for getting a quick overview of what's been happening.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max events (default: 20)",
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="github_repo_branches",
            description="List branches for a GitHub repo with their last commit info.",
            inputSchema={
                "type": "object",
                "properties": {
                    "repo": {
                        "type": "string",
                        "description": "Repo name (e.g., 'codequest')",
                    },
                },
                "required": ["repo"],
            },
        ),
    ]


def _ensure_owner(repo: str) -> str:
    """Add the authenticated user's owner prefix if not present."""
    if "/" in repo:
        return repo
    # Get authenticated user
    out = _gh(["api", "user", "--jq", ".login"])
    if out:
        return f"{out.strip()}/{repo}"
    return repo


@server.call_tool()
async def call_tool(name: str, arguments: dict):

    if name == "github_list_repos":
        visibility = arguments.get("visibility", "all")
        limit = arguments.get("limit", 50)
        fields = "name,visibility,description,primaryLanguage,pushedAt,isArchived,isFork,diskUsage,url"
        args = ["repo", "list", "--limit", str(limit), "--json", fields]
        if visibility == "public":
            args.extend(["--visibility", "public"])
        elif visibility == "private":
            args.extend(["--visibility", "private"])

        repos = _gh_json(args)
        if not repos:
            return [TextContent(type="text", text="No repos found or gh CLI error.")]

        lines = [f"Found {len(repos)} GitHub repo(s):\n"]
        for r in repos:
            lang = r.get("primaryLanguage")
            lang_name = lang.get("name", "") if isinstance(lang, dict) else ""
            vis = "PUBLIC" if r.get("visibility") == "PUBLIC" else "private"
            pushed = (r.get("pushedAt") or "")[:10]
            archived = " [ARCHIVED]" if r.get("isArchived") else ""
            fork = " [FORK]" if r.get("isFork") else ""
            desc = f" — {r['description']}" if r.get("description") else ""
            lines.append(
                f"  {r['name']:<35s} {vis:<8s} {lang_name:<12s} pushed {pushed}{archived}{fork}{desc}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "github_repo_details":
        repo = _ensure_owner(arguments["repo"])
        fields = (
            "name,description,url,visibility,isPrivate,isArchived,isFork,"
            "primaryLanguage,defaultBranchRef,stargazerCount,forkCount,"
            "diskUsage,createdAt,pushedAt,updatedAt,licenseInfo,"
            "hasIssuesEnabled,openIssueCount,openPullRequestCount,"
            "repositoryTopics"
        )
        # Use gh api for richer data
        data = _gh_json(["repo", "view", repo, "--json", fields])
        if not data:
            return [TextContent(type="text", text=f"Repo not found: {repo}")]

        lang = data.get("primaryLanguage")
        lang_name = lang.get("name", "?") if isinstance(lang, dict) else "?"
        branch = data.get("defaultBranchRef")
        branch_name = branch.get("name", "?") if isinstance(branch, dict) else "?"
        license_info = data.get("licenseInfo")
        license_name = license_info.get("name", "None") if isinstance(license_info, dict) else "None"
        topics = data.get("repositoryTopics", [])
        topic_names = [t.get("name", "") for t in topics if isinstance(t, dict)]

        lines = [
            f"# {data.get('name', '?')}",
            f"",
            f"**URL:** {data.get('url', '?')}",
            f"**Visibility:** {'Private' if data.get('isPrivate') else 'Public'}",
            f"**Language:** {lang_name}",
            f"**Default branch:** {branch_name}",
            f"**Description:** {data.get('description') or 'None'}",
            f"**License:** {license_name}",
            f"**Topics:** {', '.join(topic_names) if topic_names else 'None'}",
            f"",
            f"**Stars:** {data.get('stargazerCount', 0)} | **Forks:** {data.get('forkCount', 0)}",
            f"**Open issues:** {data.get('openIssueCount', 0)} | **Open PRs:** {data.get('openPullRequestCount', 0)}",
            f"**Disk usage:** {data.get('diskUsage', 0)} KB",
            f"",
            f"**Created:** {(data.get('createdAt') or '?')[:10]}",
            f"**Last push:** {(data.get('pushedAt') or '?')[:10]}",
            f"**Archived:** {'Yes' if data.get('isArchived') else 'No'}",
            f"**Fork:** {'Yes' if data.get('isFork') else 'No'}",
        ]
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "github_list_issues":
        repo = _ensure_owner(arguments["repo"])
        state = arguments.get("state", "open")
        limit = arguments.get("limit", 20)
        fields = "number,title,author,labels,createdAt,state,comments"
        args = ["issue", "list", "-R", repo, "--limit", str(limit),
                "--json", fields, "--state", state]
        issues = _gh_json(args)
        if not issues:
            return [TextContent(type="text", text=f"No {state} issues found in {repo}.")]

        lines = [f"Found {len(issues)} {state} issue(s) in {repo}:\n"]
        for i in issues:
            author = i.get("author", {}).get("login", "?") if isinstance(i.get("author"), dict) else "?"
            labels = [l.get("name", "") for l in i.get("labels", []) if isinstance(l, dict)]
            label_str = f" [{', '.join(labels)}]" if labels else ""
            created = (i.get("createdAt") or "")[:10]
            lines.append(
                f"  #{i.get('number', '?'):<5d} {i.get('title', '?'):<50s} by {author} ({created}){label_str}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "github_list_prs":
        repo = _ensure_owner(arguments["repo"])
        state = arguments.get("state", "open")
        limit = arguments.get("limit", 20)
        fields = "number,title,author,state,headRefName,baseRefName,createdAt,reviewDecision,isDraft"
        args = ["pr", "list", "-R", repo, "--limit", str(limit),
                "--json", fields, "--state", state]
        prs = _gh_json(args)
        if not prs:
            return [TextContent(type="text", text=f"No {state} PRs found in {repo}.")]

        lines = [f"Found {len(prs)} {state} PR(s) in {repo}:\n"]
        for p in prs:
            author = p.get("author", {}).get("login", "?") if isinstance(p.get("author"), dict) else "?"
            draft = " [DRAFT]" if p.get("isDraft") else ""
            review = p.get("reviewDecision") or ""
            review_str = f" ({review})" if review else ""
            branch = p.get("headRefName", "?")
            created = (p.get("createdAt") or "")[:10]
            lines.append(
                f"  #{p.get('number', '?'):<5d} {p.get('title', '?'):<50s} {branch} by {author} ({created}){draft}{review_str}"
            )
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "github_repo_readme":
        repo = _ensure_owner(arguments["repo"])
        out = _gh(["repo", "view", repo, "--json", "name"], timeout=10)
        if not out:
            return [TextContent(type="text", text=f"Repo not found: {repo}")]
        # Use gh api to get README
        readme = _gh(["api", f"repos/{repo}/readme", "--jq", ".content"], timeout=15)
        if readme:
            import base64
            try:
                content = base64.b64decode(readme.strip()).decode("utf-8")
                return [TextContent(type="text", text=content[:5000])]
            except Exception:
                pass
        # Fallback: try gh repo view
        out = _gh(["repo", "view", repo])
        if out:
            return [TextContent(type="text", text=out[:5000])]
        return [TextContent(type="text", text=f"Could not read README for {repo}.")]

    elif name == "github_search_repos":
        query = arguments["query"]
        limit = arguments.get("limit", 20)
        # Search user's own repos
        user = _gh(["api", "user", "--jq", ".login"])
        if not user:
            return [TextContent(type="text", text="Could not determine GitHub user.")]
        username = user.strip()
        search_query = f"{query} user:{username}"
        fields = "name,description,visibility,primaryLanguage,pushedAt,url"
        repos = _gh_json([
            "search", "repos", search_query,
            "--limit", str(limit), "--json", fields
        ])
        if not repos:
            return [TextContent(type="text", text=f"No repos matching '{query}'.")]

        lines = [f"Found {len(repos)} repo(s) matching '{query}':\n"]
        for r in repos:
            lang = r.get("primaryLanguage")
            lang_name = lang.get("name", "") if isinstance(lang, dict) else ""
            pushed = (r.get("pushedAt") or "")[:10]
            desc = f" — {r['description']}" if r.get("description") else ""
            lines.append(f"  {r['name']:<35s} {lang_name:<12s} pushed {pushed}{desc}")
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "github_recent_activity":
        limit = arguments.get("limit", 20)
        user = _gh(["api", "user", "--jq", ".login"])
        if not user:
            return [TextContent(type="text", text="Could not determine GitHub user.")]
        username = user.strip()
        events = _gh_json([
            "api", f"users/{username}/events",
            "--jq", f".[:{limit}]"
        ])
        if not events:
            return [TextContent(type="text", text="No recent activity found.")]

        lines = ["Recent GitHub activity:\n"]
        for e in events[:limit]:
            etype = e.get("type", "?")
            repo = e.get("repo", {}).get("name", "?")
            created = (e.get("created_at") or "")[:16].replace("T", " ")

            if etype == "PushEvent":
                commits = e.get("payload", {}).get("commits", [])
                msg = commits[0].get("message", "").split("\n")[0][:60] if commits else ""
                lines.append(f"  {created}  PUSH    {repo:<35s} {msg}")
            elif etype == "CreateEvent":
                ref_type = e.get("payload", {}).get("ref_type", "?")
                ref = e.get("payload", {}).get("ref", "")
                lines.append(f"  {created}  CREATE  {repo:<35s} {ref_type}: {ref}")
            elif etype == "IssuesEvent":
                action = e.get("payload", {}).get("action", "?")
                title = e.get("payload", {}).get("issue", {}).get("title", "")[:50]
                lines.append(f"  {created}  ISSUE   {repo:<35s} {action}: {title}")
            elif etype == "PullRequestEvent":
                action = e.get("payload", {}).get("action", "?")
                title = e.get("payload", {}).get("pull_request", {}).get("title", "")[:50]
                lines.append(f"  {created}  PR      {repo:<35s} {action}: {title}")
            else:
                lines.append(f"  {created}  {etype:<8s} {repo}")

        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "github_repo_branches":
        repo = _ensure_owner(arguments["repo"])
        out = _gh(["api", f"repos/{repo}/branches", "--jq",
                    '.[] | .name + " | " + .commit.sha[:7]'])
        if not out:
            return [TextContent(type="text", text=f"Could not list branches for {repo}.")]

        lines = [f"Branches in {repo}:\n"]
        for line in out.strip().splitlines():
            parts = line.split(" | ")
            if len(parts) == 2:
                lines.append(f"  {parts[0]:<30s} ({parts[1]})")
            else:
                lines.append(f"  {line}")
        return [TextContent(type="text", text="\n".join(lines))]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
