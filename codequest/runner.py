"""
Run command detection and execution module for CodeQuest.

Auto-detects runnable commands from project files (package.json, Makefile,
Python entry points, shell scripts, Dockerfiles) and provides both blocking
and streaming execution interfaces.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator


@dataclass
class RunCommand:
    """Represents a detected or configured run command."""

    label: str
    command: str
    cwd: str
    source: str = ""


def detect_run_commands(project_path: Path) -> list[RunCommand]:
    """Auto-detect run commands by inspecting project files.

    Checks (in order): package.json, Makefile, Python projects,
    executable shell scripts, and Dockerfiles.

    Args:
        project_path: Root directory of the project to scan.

    Returns:
        Deduplicated list of RunCommand instances.
    """
    project_path = Path(project_path).resolve()
    cwd = str(project_path)
    commands: list[RunCommand] = []
    seen: set[str] = set()

    def _add(label: str, command: str, source: str) -> None:
        if command not in seen:
            seen.add(command)
            commands.append(RunCommand(label=label, command=command, cwd=cwd, source=source))

    # ── a. package.json ──────────────────────────────────────────────
    pkg_json = project_path / "package.json"
    if pkg_json.is_file():
        try:
            with open(pkg_json, "r", encoding="utf-8") as fh:
                pkg = json.load(fh)
            scripts: dict = pkg.get("scripts", {})
            priority_order = ["start", "dev", "build", "test", "serve"]
            ordered_names = [s for s in priority_order if s in scripts]
            ordered_names += [s for s in scripts if s not in priority_order]
            for name in ordered_names:
                _add(f"npm run {name}", f"npm run {name}", "package.json")
        except (json.JSONDecodeError, OSError):
            pass

    # ── b. Makefile ──────────────────────────────────────────────────
    makefile = project_path / "Makefile"
    if makefile.is_file():
        try:
            with open(makefile, "r", encoding="utf-8") as fh:
                makefile_text = fh.read()
            targets = re.findall(r"^(\w+):", makefile_text, re.MULTILINE)
            priority_order = ["run", "start", "dev", "build", "all", "test"]
            ordered_targets = [t for t in priority_order if t in targets]
            ordered_targets += [t for t in targets if t not in priority_order]
            for target in ordered_targets:
                _add(f"make {target}", f"make {target}", "Makefile")
        except OSError:
            pass

    # ── c. Python projects ───────────────────────────────────────────
    # __main__.py  →  python -m <package>
    main_module = project_path / "__main__.py"
    if main_module.is_file():
        package_name = project_path.name
        _add(f"python -m {package_name}", f"python -m {package_name}", "__main__.py")

    # Also check for a src-layout __main__.py inside a sub-package
    for child in project_path.iterdir():
        if child.is_dir() and (child / "__main__.py").is_file() and (child / "__init__.py").is_file():
            pkg_name = child.name
            _add(f"python -m {pkg_name}", f"python -m {pkg_name}", f"{pkg_name}/__main__.py")

    # setup.py / pyproject.toml entry points
    setup_py = project_path / "setup.py"
    if setup_py.is_file():
        try:
            with open(setup_py, "r", encoding="utf-8") as fh:
                setup_text = fh.read()
            # Look for console_scripts entries
            for match in re.finditer(
                r"""['\"](\w[\w-]*)['\"]\s*=\s*['\"]""", setup_text
            ):
                cmd_name = match.group(1)
                _add(cmd_name, cmd_name, "setup.py")
        except OSError:
            pass

    pyproject = project_path / "pyproject.toml"
    if pyproject.is_file():
        try:
            # Try tomllib first (Python 3.11+)
            try:
                import tomllib  # type: ignore[import-not-found]
                with open(pyproject, "rb") as fh:
                    toml_data = tomllib.load(fh)
                # [project.scripts]
                scripts_section = toml_data.get("project", {}).get("scripts", {})
                for cmd_name in scripts_section:
                    _add(cmd_name, cmd_name, "pyproject.toml")
                # [tool.poetry.scripts]
                poetry_scripts = (
                    toml_data.get("tool", {}).get("poetry", {}).get("scripts", {})
                )
                for cmd_name in poetry_scripts:
                    _add(cmd_name, cmd_name, "pyproject.toml")
            except (ImportError, ModuleNotFoundError):
                # Fallback: regex extraction
                with open(pyproject, "r", encoding="utf-8") as fh:
                    toml_text = fh.read()
                in_scripts = False
                for line in toml_text.splitlines():
                    stripped = line.strip()
                    if re.match(
                        r"\[(project\.scripts|tool\.poetry\.scripts)\]", stripped
                    ):
                        in_scripts = True
                        continue
                    if in_scripts:
                        if stripped.startswith("["):
                            in_scripts = False
                            continue
                        m = re.match(r"""(\w[\w-]*)\s*=""", stripped)
                        if m:
                            cmd_name = m.group(1)
                            _add(cmd_name, cmd_name, "pyproject.toml")
        except OSError:
            pass

    # Common Python entry-point files
    if (project_path / "app.py").is_file():
        _add("python app.py", "python app.py", "app.py")

    if (project_path / "main.py").is_file():
        _add("python main.py", "python main.py", "main.py")

    if (project_path / "manage.py").is_file():
        _add(
            "python manage.py runserver",
            "python manage.py runserver",
            "manage.py",
        )

    # ── d. Executable .sh files in project root ─────────────────────
    for sh_file in sorted(project_path.glob("*.sh")):
        if sh_file.is_file() and os.access(sh_file, os.X_OK):
            name = sh_file.name
            _add(f"bash {name}", f"bash {name}", name)

    # ── e. Dockerfile ────────────────────────────────────────────────
    dockerfile = project_path / "Dockerfile"
    if dockerfile.is_file():
        project_name = project_path.name.lower().replace(" ", "-")
        _add(
            f"docker build -t {project_name} .",
            f"docker build -t {project_name} .",
            "Dockerfile",
        )
        _add(
            f"docker run {project_name}",
            f"docker run {project_name}",
            "Dockerfile",
        )

    return commands


def get_run_commands(
    project_path: Path, overrides: dict | None = None
) -> list[RunCommand]:
    """Return run commands for a project, using config overrides if available.

    Args:
        project_path: Root directory of the project.
        overrides: Optional dict mapping project path strings to lists of
                   command dicts (keys: label, command, cwd, source).

    Returns:
        List of RunCommand instances.
    """
    project_path = Path(project_path).resolve()
    key = str(project_path)

    if overrides and key in overrides:
        return [
            RunCommand(
                label=entry.get("label", entry.get("command", "")),
                command=entry["command"],
                cwd=entry.get("cwd", key),
                source=entry.get("source", "config"),
            )
            for entry in overrides[key]
        ]

    return detect_run_commands(project_path)


def execute_command(
    cmd: RunCommand,
    callback=None,
    timeout: int = 300,
) -> subprocess.CompletedProcess:
    """Execute a RunCommand and return the result.

    Args:
        cmd: The RunCommand to execute.
        callback: Optional callable; if provided, output is not captured
                  (it goes to the parent process stdout/stderr).
        timeout: Maximum seconds to wait (default 300 = 5 minutes).

    Returns:
        subprocess.CompletedProcess with stdout/stderr when no callback,
        or with None streams when a callback is provided.

    Raises:
        subprocess.TimeoutExpired: Re-raised after logging if the command
            exceeds the timeout.
    """
    try:
        capture = callback is None
        result = subprocess.run(
            cmd.command,
            cwd=cmd.cwd,
            capture_output=capture,
            text=True,
            timeout=timeout,
            shell=True,
        )
        if callback is not None:
            callback(result)
        return result
    except subprocess.TimeoutExpired:
        raise
    except Exception as exc:
        # Return a synthetic CompletedProcess so callers always get a result.
        return subprocess.CompletedProcess(
            args=cmd.command,
            returncode=-1,
            stdout="",
            stderr=str(exc),
        )


def execute_command_streaming(cmd: RunCommand) -> Generator[str, None, None]:
    """Execute a RunCommand and yield stdout/stderr lines as they arrive.

    Uses subprocess.Popen with merged stdout+stderr for real-time output.

    Args:
        cmd: The RunCommand to execute.

    Yields:
        Individual lines of combined stdout and stderr output.
    """
    process = subprocess.Popen(
        cmd.command,
        cwd=cmd.cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        shell=True,
    )
    try:
        if process.stdout is not None:
            for line in process.stdout:
                yield line
        process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()
