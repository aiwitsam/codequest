"""Process lifecycle management for CodeQuest Launchpad.

Provides a thread-safe in-memory process registry for launching,
monitoring, and stopping project processes with port detection.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator, Optional

from codequest.config import get_config

# Regex patterns to detect port numbers from process output
PORT_PATTERNS = [
    re.compile(
        r"(?:listening|running|started|serving)\s+(?:on|at)\s+"
        r"(?:https?://)?(?:localhost|0\.0\.0\.0|127\.0\.0\.1)[:\s]+(\d{4,5})",
        re.IGNORECASE,
    ),
    re.compile(
        r"Local:\s+https?://(?:localhost|0\.0\.0\.0|127\.0\.0\.1):(\d{4,5})",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://(?:localhost|0\.0\.0\.0|127\.0\.0\.1):(\d{4,5})",
        re.IGNORECASE,
    ),
]


@dataclass
class ManagedProcess:
    """A process managed by the Launchpad."""

    id: str
    project_name: str
    command: str
    cwd: str
    pid: Optional[int] = None
    status: str = "starting"  # starting | running | stopped | failed | killed
    port: Optional[int] = None
    url: Optional[str] = None
    started_at: float = 0.0
    stopped_at: float = 0.0
    exit_code: Optional[int] = None
    output_lines: deque = field(default_factory=lambda: deque(maxlen=1000))
    _process: Optional[subprocess.Popen] = field(default=None, repr=False)
    _output_index: int = field(default=0, repr=False)

    def to_dict(self) -> dict:
        """Serializable snapshot for API responses."""
        return {
            "id": self.id,
            "project_name": self.project_name,
            "command": self.command,
            "cwd": self.cwd,
            "pid": self.pid,
            "status": self.status,
            "port": self.port,
            "url": self.url,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "exit_code": self.exit_code,
            "output_line_count": len(self.output_lines),
            "last_output": list(self.output_lines)[-5:] if self.output_lines else [],
        }


class ProcessManager:
    """Thread-safe in-memory process registry."""

    def __init__(self) -> None:
        self._processes: dict[str, ManagedProcess] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _build_env(cwd: str) -> dict[str, str]:
        """Build environment for subprocess with full user PATH and venv."""
        env = os.environ.copy()

        extra_paths = []

        # Check for project venv
        cwd_path = Path(cwd)
        for venv_dir in (".venv", "venv"):
            venv_bin = cwd_path / venv_dir / "bin"
            if venv_bin.is_dir():
                extra_paths.append(str(venv_bin))
                env["VIRTUAL_ENV"] = str(cwd_path / venv_dir)
                break

        # Prepend extra paths to existing PATH
        if extra_paths:
            existing = env.get("PATH", "")
            env["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + existing

        return env

    def start(self, project_name: str, command: str, cwd: str) -> str:
        """Spawn a process and return its ID.

        If a process with the same project+command is already running,
        returns the existing process ID instead.
        """
        config = get_config()
        launch_config = config.get("launch", {})
        max_processes = launch_config.get("max_processes", 10)

        with self._lock:
            # Duplicate guard
            for proc in self._processes.values():
                if (
                    proc.project_name == project_name
                    and proc.command == command
                    and proc.status in ("starting", "running")
                ):
                    return proc.id

            # Max process limit
            active = sum(
                1 for p in self._processes.values()
                if p.status in ("starting", "running")
            )
            if active >= max_processes:
                raise RuntimeError(
                    f"Max processes ({max_processes}) reached. Stop one first."
                )

            proc_id = uuid.uuid4().hex[:12]
            max_lines = launch_config.get("max_output_lines", 1000)

            managed = ManagedProcess(
                id=proc_id,
                project_name=project_name,
                command=command,
                cwd=cwd,
                started_at=time.time(),
                output_lines=deque(maxlen=max_lines),
            )
            self._processes[proc_id] = managed

        # Spawn outside the lock
        try:
            env = self._build_env(cwd)
            popen = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
                env=env,
            )
            managed._process = popen
            managed.pid = popen.pid
            managed.status = "running"

            # Check port overrides
            port_overrides = launch_config.get("port_overrides", {})
            if project_name in port_overrides:
                managed.port = int(port_overrides[project_name])
                managed.url = f"http://localhost:{managed.port}"

            # Start reader thread
            reader = threading.Thread(
                target=self._read_output,
                args=(managed,),
                daemon=True,
                name=f"proc-reader-{proc_id}",
            )
            reader.start()

        except Exception as exc:
            managed.status = "failed"
            managed.stopped_at = time.time()
            managed.output_lines.append(f"[ERROR] Failed to start: {exc}")

        return proc_id

    def _read_output(self, managed: ManagedProcess) -> None:
        """Reader thread: consume stdout and detect ports."""
        proc = managed._process
        if proc is None or proc.stdout is None:
            return

        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                managed.output_lines.append(line)

                # Port detection (only if not already detected)
                if managed.port is None:
                    for pattern in PORT_PATTERNS:
                        m = pattern.search(line)
                        if m:
                            port = int(m.group(1))
                            if 1024 <= port <= 65535:
                                managed.port = port
                                managed.url = f"http://localhost:{port}"
                            break

            proc.wait()
            managed.exit_code = proc.returncode
            managed.stopped_at = time.time()

            if managed.status == "running":
                managed.status = "stopped" if proc.returncode == 0 else "failed"

        except Exception as exc:
            managed.output_lines.append(f"[ERROR] Reader crashed: {exc}")
            managed.status = "failed"
            managed.stopped_at = time.time()

    def stop(self, process_id: str) -> bool:
        """Stop a process: SIGTERM, wait 5s, SIGKILL if needed."""
        with self._lock:
            managed = self._processes.get(process_id)
            if not managed or managed.status not in ("starting", "running"):
                return False

        proc = managed._process
        if proc is None:
            managed.status = "stopped"
            managed.stopped_at = time.time()
            return True

        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)

            managed.exit_code = proc.returncode
            managed.status = "killed"
            managed.stopped_at = time.time()
            managed.output_lines.append("[Process stopped]")
            return True

        except Exception:
            managed.status = "failed"
            managed.stopped_at = time.time()
            return False

    def get(self, process_id: str) -> Optional[ManagedProcess]:
        """Get a managed process by ID."""
        with self._lock:
            return self._processes.get(process_id)

    def get_by_project(self, project_name: str) -> list[ManagedProcess]:
        """Get all processes for a project."""
        with self._lock:
            return [
                p for p in self._processes.values()
                if p.project_name == project_name
            ]

    def list_all(self) -> list[ManagedProcess]:
        """List all managed processes."""
        with self._lock:
            return list(self._processes.values())

    def stream_output(self, process_id: str) -> Generator[dict, None, None]:
        """Generator yielding new output for SSE streaming."""
        managed = self.get(process_id)
        if not managed:
            yield {"type": "exit", "exit_code": -1, "status": "not_found"}
            return

        yield {"type": "status", "status": managed.status, "pid": managed.pid}

        # Stream existing output
        seen = 0
        for line in list(managed.output_lines):
            yield {"type": "output", "line": line}
            seen += 1

        # Stream new output as it arrives
        while managed.status in ("starting", "running"):
            current_lines = list(managed.output_lines)
            if len(current_lines) > seen:
                for line in current_lines[seen:]:
                    yield {"type": "output", "line": line}

                    # Check for port detection
                    if managed.port is not None:
                        yield {
                            "type": "port",
                            "port": managed.port,
                            "url": managed.url,
                        }
                seen = len(current_lines)

            time.sleep(0.1)

        # Final output flush
        current_lines = list(managed.output_lines)
        if len(current_lines) > seen:
            for line in current_lines[seen:]:
                yield {"type": "output", "line": line}

        yield {
            "type": "exit",
            "exit_code": managed.exit_code,
            "status": managed.status,
        }

    def to_dict(self, process_id: str) -> Optional[dict]:
        """Serializable snapshot for a single process."""
        managed = self.get(process_id)
        return managed.to_dict() if managed else None

    def cleanup(self) -> int:
        """Prune dead processes older than 1 hour. Returns count removed."""
        cutoff = time.time() - 3600
        removed = 0
        with self._lock:
            to_remove = [
                pid for pid, p in self._processes.items()
                if p.status in ("stopped", "failed", "killed")
                and p.stopped_at > 0
                and p.stopped_at < cutoff
            ]
            for pid in to_remove:
                del self._processes[pid]
                removed += 1
        return removed
