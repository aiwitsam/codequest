"""Discover available-but-not-installed skills and score them."""

import shutil
from pathlib import Path

from codequest.config import get_config
from codequest.intel.scoring import score_item


def _scan_trailofbits():
    """Scan ~/trailofbits-skills/plugins/ for uninstalled skills."""
    tob_dir = Path.home() / "trailofbits-skills" / "plugins"
    installed_dir = Path.home() / ".claude" / "skills"
    results = []

    if not tob_dir.is_dir():
        return results

    installed_names = set()
    if installed_dir.is_dir():
        installed_names = {d.name for d in installed_dir.iterdir() if d.is_dir()}

    for plugin_dir in sorted(tob_dir.iterdir()):
        if not plugin_dir.is_dir():
            continue
        if plugin_dir.name in installed_names:
            continue

        # Try to read skill description
        desc = ""
        for fname in ("SKILL.md", "README.md", "skill.md"):
            skill_file = plugin_dir / fname
            if skill_file.is_file():
                try:
                    content = skill_file.read_text(encoding="utf-8", errors="replace")
                    # Get first paragraph after frontmatter
                    lines = content.split("---")
                    if len(lines) >= 3:
                        body = lines[2].strip()
                    else:
                        body = content.strip()
                    for line in body.splitlines():
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            desc = stripped[:200]
                            break
                except OSError:
                    pass
                break

        results.append({
            "name": plugin_dir.name,
            "description": desc,
            "source": "Trail of Bits",
            "source_path": str(plugin_dir),
            "installed": False,
        })

    return results


def _scan_community_repos():
    """Scan ~/communitytools for additional skill sources."""
    community_dir = Path.home() / "communitytools"
    results = []

    if not community_dir.is_dir():
        return results

    for item in sorted(community_dir.iterdir()):
        if not item.is_dir():
            continue
        desc = ""
        readme = item / "README.md"
        if readme.is_file():
            try:
                content = readme.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#"):
                        desc = stripped[:200]
                        break
            except OSError:
                pass

        results.append({
            "name": item.name,
            "description": desc,
            "source": "Community",
            "source_path": str(item),
            "installed": False,
        })

    return results


def discover_skills():
    """Discover all available skills with relevance scores."""
    items = []
    items.extend(_scan_trailofbits())
    items.extend(_scan_community_repos())

    # Score each item for relevance
    for item in items:
        heat, rec, reason = score_item(item)
        item["heat"] = heat
        item["rec"] = rec
        item["reason"] = reason

    # Sort by heat (Hot > Warm > Watch)
    heat_order = {"Hot": 0, "Warm": 1, "Watch": 2}
    items.sort(key=lambda x: heat_order.get(x.get("heat", "Watch"), 2))

    return items


def install_skill(source_path, name=None):
    """Install a skill by copying to ~/.claude/skills/."""
    src = Path(source_path)
    if not src.is_dir():
        return False, "Source path does not exist"

    dest_name = name or src.name
    dest = Path.home() / ".claude" / "skills" / dest_name
    if dest.exists():
        return False, f"Skill '{dest_name}' already exists"

    try:
        shutil.copytree(str(src), str(dest))
        return True, f"Installed '{dest_name}'"
    except OSError as e:
        return False, str(e)
