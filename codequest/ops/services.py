"""Service discovery and health monitoring."""

import os
import re
import subprocess
from pathlib import Path

import requests

from codequest.config import get_config


def _parse_systemd_services():
    """Parse ~/.config/systemd/user/*.service files."""
    service_dir = Path.home() / ".config" / "systemd" / "user"
    services = {}
    if not service_dir.is_dir():
        return services

    for sf in sorted(service_dir.glob("*.service")):
        name = sf.stem
        try:
            content = sf.read_text(encoding="utf-8", errors="replace")
            desc = ""
            exec_start = ""
            working_dir = ""
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("Description="):
                    desc = line.split("=", 1)[1]
                elif line.startswith("ExecStart="):
                    exec_start = line.split("=", 1)[1]
                elif line.startswith("WorkingDirectory="):
                    working_dir = line.split("=", 1)[1]

            services[name] = {
                "name": name,
                "description": desc,
                "exec_start": exec_start,
                "working_dir": working_dir,
                "source": "systemd",
            }
        except OSError:
            pass

    return services


def _check_health(port, host="localhost", timeout=3):
    """HTTP GET health check against a port."""
    try:
        resp = requests.get(f"http://{host}:{port}/", timeout=timeout)
        return {
            "status": "up",
            "code": resp.status_code,
            "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
        }
    except requests.ConnectionError:
        return {"status": "down", "code": None, "response_time_ms": None}
    except requests.Timeout:
        return {"status": "timeout", "code": None, "response_time_ms": None}
    except requests.RequestException:
        return {"status": "error", "code": None, "response_time_ms": None}


def _get_systemctl_status(name):
    """Get systemctl --user status for a service."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", name],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return "unknown"


def get_services():
    """Get all services with health status."""
    config = get_config()
    service_ports = config.get("ops", {}).get("service_ports", {})

    # Discover from systemd
    systemd = _parse_systemd_services()

    # Build service list from config ports
    results = []
    for name, port in service_ports.items():
        svc = systemd.get(name, {
            "name": name,
            "description": "",
            "exec_start": "",
            "working_dir": "",
            "source": "config",
        })
        svc["port"] = port
        svc["systemctl_status"] = _get_systemctl_status(name)
        svc["health"] = _check_health(port)
        results.append(svc)

    # Add any systemd services not in config
    for name, svc in systemd.items():
        if name not in service_ports:
            svc["port"] = None
            svc["systemctl_status"] = _get_systemctl_status(name)
            svc["health"] = {"status": "unknown", "code": None, "response_time_ms": None}
            results.append(svc)

    return results


def get_unified_services(process_mgr=None):
    """Merge systemd services with Launchpad-managed processes.

    Returns a combined list where each entry has a 'source' field:
    'systemd', 'launchpad', or 'linked' (when both match).
    """
    base_services = get_services()

    if process_mgr is None:
        return base_services

    managed = process_mgr.list_all()
    if not managed:
        for svc in base_services:
            svc["source"] = "systemd"
        return base_services

    # Build lookup by name and working_dir for matching
    svc_by_name = {s["name"]: s for s in base_services}
    svc_by_dir = {}
    for s in base_services:
        wd = s.get("working_dir", "").rstrip("/")
        if wd:
            svc_by_dir[wd] = s

    matched_svc_names = set()
    results = []

    for proc in managed:
        if proc.status in ("stopped", "killed") and proc.stopped_at > 0:
            import time
            if time.time() - proc.stopped_at > 300:
                continue

        cwd = proc.cwd.rstrip("/")
        matched = svc_by_name.get(proc.project_name) or svc_by_dir.get(cwd)

        if matched:
            matched_svc_names.add(matched["name"])
            entry = dict(matched)
            entry["source"] = "linked"
            entry["launchpad_process"] = proc.to_dict()
            if proc.port:
                entry["port"] = proc.port
            if proc.status in ("starting", "running"):
                entry["health"] = {"status": "up", "code": None, "response_time_ms": None}
            results.append(entry)
        else:
            entry = {
                "name": proc.project_name,
                "description": proc.command,
                "exec_start": proc.command,
                "working_dir": proc.cwd,
                "source": "launchpad",
                "port": proc.port,
                "systemctl_status": "n/a",
                "health": {
                    "status": "up" if proc.status == "running" else (
                        "down" if proc.status in ("failed", "killed") else "unknown"
                    ),
                    "code": None,
                    "response_time_ms": None,
                },
                "launchpad_process": proc.to_dict(),
            }
            results.append(entry)

    # Add unmatched systemd services
    for svc in base_services:
        if svc["name"] not in matched_svc_names:
            svc["source"] = "systemd"
            results.append(svc)

    return results


def get_mesh_status():
    """Get mesh sync status."""
    config = get_config()
    mesh_host = config.get("ops", {}).get("mesh_host", "ubuntu-desktop")

    # Try mesh-status.sh first
    mesh_script = Path.home() / "bin" / "mesh-status.sh"
    if mesh_script.is_file():
        try:
            result = subprocess.run(
                [str(mesh_script)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return {
                "output": result.stdout,
                "connected": result.returncode == 0,
                "mesh_host": mesh_host,
            }
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Fallback: tailscale status
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            peers = data.get("Peer", {})
            connected = any(
                mesh_host.lower() in str(p.get("HostName", "")).lower()
                for p in peers.values()
            )
            return {
                "output": f"Tailscale: {len(peers)} peers",
                "connected": connected,
                "mesh_host": mesh_host,
                "peers": len(peers),
            }
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
        pass

    return {"output": "Mesh status unavailable", "connected": False, "mesh_host": mesh_host}


def _systemctl_action(name, action):
    """Run a systemctl --user action on a whitelisted service."""
    config = get_config()
    service_ports = config.get("ops", {}).get("service_ports", {})
    if name not in service_ports:
        return False, "Service not in whitelist"

    try:
        result = subprocess.run(
            ["systemctl", "--user", action, name],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return True, action.capitalize() + "ed" if action != "stop" else "Stopped"
        return False, result.stderr.strip() or f"{action.capitalize()} failed"
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return False, str(e)


def start_service(name):
    """Start a systemd user service (only if in config whitelist)."""
    return _systemctl_action(name, "start")


def stop_service(name):
    """Stop a systemd user service (only if in config whitelist)."""
    return _systemctl_action(name, "stop")


def restart_service(name):
    """Restart a systemd user service (only if in config whitelist)."""
    return _systemctl_action(name, "restart")
