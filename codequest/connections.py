"""Project relationship analysis for CodeQuest."""

import json
import os
import re
import time
from pathlib import Path

CACHE_FILE = Path.home() / ".codequest" / "connections.json"
CACHE_TTL = 86400  # 24 hours

# Common cross-project import patterns
PYTHON_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([\w.]+)", re.MULTILINE)
NODE_REQUIRE_RE = re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""")
NODE_IMPORT_RE = re.compile(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""")

# Project type to node color
TYPE_COLORS = {
    "Python": "#4488ff",
    "Node": "#44cc44",
    "Bash": "#ffcc00",
    "Rust": "#ff6633",
    "Go": "#00cccc",
    "Static": "#cc88ff",
    "Unknown": "#888888",
}


def _scan_python_imports(path: Path) -> set[str]:
    """Scan Python files for top-level import names."""
    imports = set()
    try:
        for py_file in path.rglob("*.py"):
            # Skip venvs and hidden dirs
            parts = py_file.relative_to(path).parts
            if any(p.startswith(".") or p in ("venv", ".venv", "env", "node_modules", "__pycache__") for p in parts):
                continue
            try:
                content = py_file.read_text(errors="replace")
                for match in PYTHON_IMPORT_RE.finditer(content):
                    top_module = match.group(1).split(".")[0]
                    imports.add(top_module)
            except OSError:
                continue
    except OSError:
        pass
    return imports


def _scan_node_imports(path: Path) -> set[str]:
    """Scan JS/TS files for import/require names."""
    imports = set()
    try:
        for ext in ("*.js", "*.ts", "*.jsx", "*.tsx", "*.mjs"):
            for js_file in path.rglob(ext):
                parts = js_file.relative_to(path).parts
                if any(p.startswith(".") or p == "node_modules" for p in parts):
                    continue
                try:
                    content = js_file.read_text(errors="replace")
                    for match in NODE_REQUIRE_RE.finditer(content):
                        mod = match.group(1).split("/")[0]
                        if not mod.startswith("."):
                            imports.add(mod)
                    for match in NODE_IMPORT_RE.finditer(content):
                        mod = match.group(1).split("/")[0]
                        if not mod.startswith("."):
                            imports.add(mod)
                except OSError:
                    continue
    except OSError:
        pass
    return imports


def _scan_config_refs(path: Path, all_names: set[str]) -> set[str]:
    """Check config/doc files for references to other project names."""
    refs = set()
    check_files = ["CLAUDE.md", "README.md", "PROJECT_HANDOFF.md", ".env"]
    for fname in check_files:
        fpath = path / fname
        if fpath.is_file():
            try:
                content = fpath.read_text(errors="replace").lower()
                for name in all_names:
                    if name.lower() in content and name != path.name:
                        refs.add(name)
            except OSError:
                continue
    return refs


def _check_git_submodules(path: Path) -> set[str]:
    """Check .gitmodules for submodule references."""
    refs = set()
    gitmodules = path / ".gitmodules"
    if gitmodules.is_file():
        try:
            content = gitmodules.read_text(errors="replace")
            for line in content.splitlines():
                if "path" in line and "=" in line:
                    subpath = line.split("=", 1)[1].strip()
                    refs.add(subpath.split("/")[-1])
        except OSError:
            pass
    return refs


def _check_skills(all_names: set[str]) -> dict[str, set[str]]:
    """Check ~/.claude/skills/ for project-specific skills."""
    skill_refs: dict[str, set[str]] = {}
    skills_dir = Path.home() / ".claude" / "skills"
    if not skills_dir.is_dir():
        return skill_refs

    try:
        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_name = skill_dir.name
            # Check if skill name matches a project
            for name in all_names:
                if name.lower() == skill_name.lower():
                    skill_refs.setdefault(name, set()).add(f"skill:{skill_name}")
                    break
            # Also scan skill content for project refs
            for skill_file in skill_dir.glob("*.md"):
                try:
                    content = skill_file.read_text(errors="replace").lower()
                    for name in all_names:
                        if name.lower() in content:
                            skill_refs.setdefault(name, set()).add(f"skill:{skill_name}")
                except OSError:
                    continue
    except OSError:
        pass
    return skill_refs


def analyze_all(projects: list[dict]) -> dict:
    """Analyze all project relationships. Returns {nodes, edges}."""
    all_names = {p["name"] for p in projects}
    project_map = {p["name"]: p for p in projects}

    # Build nodes
    nodes = []
    for p in projects:
        nodes.append({
            "id": p["name"],
            "label": p["name"],
            "type": p.get("project_type", "Unknown"),
            "color": TYPE_COLORS.get(p.get("project_type", "Unknown"), "#888888"),
            "group": p.get("project_type", "Unknown"),
        })

    edges = []
    edge_set = set()  # dedup

    # Collect imports per project
    project_imports: dict[str, set[str]] = {}
    for p in projects:
        path = Path(p["path"])
        ptype = p.get("project_type", "")
        if ptype == "Python":
            project_imports[p["name"]] = _scan_python_imports(path)
        elif ptype == "Node":
            project_imports[p["name"]] = _scan_node_imports(path)
        else:
            project_imports[p["name"]] = set()

    # 1. Cross-project imports
    name_to_lower = {n.lower().replace("-", "_").replace(" ", "_"): n for n in all_names}
    for proj_name, imports in project_imports.items():
        for imp in imports:
            imp_norm = imp.lower().replace("-", "_")
            if imp_norm in name_to_lower and name_to_lower[imp_norm] != proj_name:
                target = name_to_lower[imp_norm]
                key = tuple(sorted([proj_name, target])) + ("imports",)
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({
                        "from": proj_name,
                        "to": target,
                        "label": "imports",
                        "strength": 3,
                    })

    # 2. Config/doc references
    for p in projects:
        path = Path(p["path"])
        refs = _scan_config_refs(path, all_names)
        for ref in refs:
            key = tuple(sorted([p["name"], ref])) + ("references",)
            if key not in edge_set:
                edge_set.add(key)
                edges.append({
                    "from": p["name"],
                    "to": ref,
                    "label": "references",
                    "strength": 2,
                })

    # 3. Shared dependencies (find pairs sharing >=3 deps)
    for i, p1 in enumerate(projects):
        for p2 in projects[i + 1:]:
            imp1 = project_imports.get(p1["name"], set())
            imp2 = project_imports.get(p2["name"], set())
            shared = imp1 & imp2
            # Filter out stdlib/common modules
            shared -= {"os", "sys", "json", "re", "time", "pathlib", "typing",
                       "subprocess", "datetime", "logging", "collections",
                       "react", "next", "express", "path", "fs", "http", "url"}
            if len(shared) >= 3:
                key = tuple(sorted([p1["name"], p2["name"]])) + ("shared-deps",)
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({
                        "from": p1["name"],
                        "to": p2["name"],
                        "label": f"shared deps ({len(shared)})",
                        "strength": 1,
                    })

    # 4. Git submodules
    for p in projects:
        path = Path(p["path"])
        sub_refs = _check_git_submodules(path)
        for ref in sub_refs:
            if ref in all_names:
                key = tuple(sorted([p["name"], ref])) + ("submodule",)
                if key not in edge_set:
                    edge_set.add(key)
                    edges.append({
                        "from": p["name"],
                        "to": ref,
                        "label": "submodule",
                        "strength": 3,
                    })

    # 5. Skill references
    skill_refs = _check_skills(all_names)
    for proj_name, skills in skill_refs.items():
        for skill_ref in skills:
            # Link the project to any other project that shares the same skill
            skill_name = skill_ref.replace("skill:", "")
            for other_name in all_names:
                if other_name != proj_name and other_name.lower() == skill_name.lower():
                    key = tuple(sorted([proj_name, other_name])) + ("skill",)
                    if key not in edge_set:
                        edge_set.add(key)
                        edges.append({
                            "from": proj_name,
                            "to": other_name,
                            "label": "has skill",
                            "strength": 2,
                        })

    return {
        "nodes": nodes,
        "edges": edges,
        "analyzed_at": time.time(),
    }


def load_cache() -> dict:
    """Load cached connection analysis."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(data: dict) -> None:
    """Save connection analysis to cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_cache_fresh(cache: dict) -> bool:
    """Check if cache is within TTL."""
    analyzed_at = cache.get("analyzed_at", 0)
    return (time.time() - analyzed_at) < CACHE_TTL
