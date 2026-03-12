"""Scan Claude Code skills, plugins, MCP servers, and hooks."""

import json
import re
from pathlib import Path

from codequest.config import get_config


def _parse_yaml_frontmatter(text):
    """Parse YAML frontmatter from a markdown file (simple key: value only)."""
    if not text.startswith("---"):
        return {}
    end = text.find("---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip()
    result = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    return result


def _scan_custom_skills():
    """Scan ~/.claude/skills/*/SKILL.md for custom skills."""
    skills_dir = Path.home() / ".claude" / "skills"
    results = []
    if not skills_dir.is_dir():
        return results

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8", errors="replace")
            meta = _parse_yaml_frontmatter(content)
            triggers = []
            # Look for trigger patterns in content
            for line in content.splitlines():
                lower = line.lower().strip()
                if lower.startswith("- ") and ("when" in lower or "use" in lower):
                    triggers.append(line.strip("- ").strip())

            results.append({
                "name": meta.get("name", skill_dir.name),
                "description": meta.get("description", ""),
                "type": "custom",
                "source_path": str(skill_file),
                "version": meta.get("version"),
                "related_project": meta.get("project"),
                "triggers": triggers[:5],
            })
        except OSError:
            pass

    return results


def _scan_installed_plugins():
    """Parse ~/.claude/plugins/installed_plugins.json."""
    plugins_file = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    results = []
    if not plugins_file.is_file():
        return results

    try:
        data = json.loads(plugins_file.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            return results
        for plugin in data:
            if not isinstance(plugin, dict):
                continue
            results.append({
                "name": plugin.get("name", "unknown"),
                "description": plugin.get("description", ""),
                "type": "official" if plugin.get("marketplace") else "community",
                "source_path": str(plugins_file),
                "version": plugin.get("version"),
                "related_project": None,
                "triggers": [],
            })
    except (OSError, json.JSONDecodeError):
        pass

    return results


def _scan_mcp_servers():
    """Parse mcpServers from ~/.claude/settings.json."""
    settings_files = [
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.local.json",
    ]
    results = []

    for sf in settings_files:
        if not sf.is_file():
            continue
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {})
            if not isinstance(servers, dict):
                continue
            for name, config in servers.items():
                if not isinstance(config, dict):
                    continue
                cmd = config.get("command", "")
                args = config.get("args", [])
                desc = f"{cmd} {' '.join(args[:3])}" if cmd else ""
                results.append({
                    "name": f"MCP: {name}",
                    "description": desc[:200],
                    "type": "mcp",
                    "source_path": str(sf),
                    "version": None,
                    "related_project": None,
                    "triggers": [],
                })
        except (OSError, json.JSONDecodeError):
            pass

    return results


def _scan_hooks():
    """Parse hooks from ~/.claude/settings.json."""
    settings_files = [
        Path.home() / ".claude" / "settings.json",
        Path.home() / ".claude" / "settings.local.json",
    ]
    results = []

    for sf in settings_files:
        if not sf.is_file():
            continue
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            hooks = data.get("hooks", {})
            if not isinstance(hooks, dict):
                continue
            for event_name, hook_list in hooks.items():
                if not isinstance(hook_list, list):
                    continue
                for hook in hook_list:
                    if not isinstance(hook, dict):
                        continue
                    matcher = hook.get("matcher", "")
                    cmd = hook.get("command", "")
                    hook_type = hook.get("type", "command")
                    desc = f"[{event_name}] {hook_type}: {cmd}"
                    if matcher:
                        desc += f" (matcher: {matcher})"
                    results.append({
                        "name": f"Hook: {event_name}",
                        "description": desc[:200],
                        "type": "hook",
                        "source_path": str(sf),
                        "version": None,
                        "related_project": None,
                        "triggers": [event_name],
                    })
        except (OSError, json.JSONDecodeError):
            pass

    return results


def scan_all():
    """Scan all sources and return unified skill dicts."""
    config = get_config()
    annotations = config.get("ai", {}).get("skills_annotations", {})

    all_items = []
    all_items.extend(_scan_custom_skills())
    all_items.extend(_scan_installed_plugins())
    all_items.extend(_scan_mcp_servers())
    all_items.extend(_scan_hooks())

    # Apply config annotations
    for item in all_items:
        if item["name"] in annotations:
            ann = annotations[item["name"]]
            if isinstance(ann, dict):
                if "description" in ann:
                    item["description"] = ann["description"]
                if "related_project" in ann:
                    item["related_project"] = ann["related_project"]

    return all_items
