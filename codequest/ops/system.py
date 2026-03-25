"""Linux system update scanning and management."""

import json
import os
import platform
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

CACHE_FILE = Path.home() / ".codequest" / "system_cache.json"
CACHE_TTL = 3600  # 1 hour


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except (FileNotFoundError, OSError) as e:
        return -1, "", str(e)


def get_system_info() -> dict:
    """Gather basic system information."""
    info = {
        "hostname": platform.node(),
        "os": "",
        "kernel": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "uptime": "",
        "disk_usage": [],
    }

    # OS pretty name
    rc, out, _ = _run(["lsb_release", "-ds"])
    if rc == 0 and out.strip():
        info["os"] = out.strip().strip('"')
    else:
        info["os"] = f"{platform.system()} {platform.release()}"

    # Uptime
    rc, out, _ = _run(["uptime", "-p"])
    if rc == 0:
        info["uptime"] = out.strip()

    # Disk usage (main partitions only, skip virtual/snap mounts)
    rc, out, _ = _run(["df", "-h", "--output=target,size,used,avail,pcent", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"])
    skip_prefixes = ("/snap/", "/usr/lib/wsl", "/usr/lib/modules", "/init", "/mnt/wslg")
    if rc == 0:
        lines = out.strip().splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 5:
                mount = parts[0]
                if any(mount.startswith(p) for p in skip_prefixes):
                    continue
                info["disk_usage"].append({
                    "mount": mount,
                    "size": parts[1],
                    "used": parts[2],
                    "available": parts[3],
                    "percent": parts[4],
                })

    return info


def scan_apt_updates() -> dict:
    """Scan for available apt package updates.

    Returns dict with upgradable packages categorized by type.
    """
    # Run apt update first (may need sudo, will work without for cache check)
    _run(["sudo", "apt", "update", "-qq"], timeout=60)

    # Get list of upgradable packages
    rc, out, _ = _run(["apt", "list", "--upgradable"], timeout=30)
    if rc != 0 and not out:
        return {
            "packages": [],
            "total": 0,
            "security": 0,
            "regular": 0,
            "error": "Could not check for updates",
            "scanned_at": time.time(),
        }

    packages = []
    for line in out.splitlines():
        if "/" not in line or "Listing..." in line:
            continue

        # Format: package/source version [upgradable from: old_version]
        match = re.match(
            r'^(\S+?)/([\S]+)\s+(\S+)\s+(\S+)(?:\s+\[upgradable from:\s+(\S+)\])?',
            line
        )
        if match:
            name = match.group(1)
            source = match.group(2)
            new_version = match.group(3)
            arch = match.group(4)
            old_version = match.group(5) or "?"

            # Classify: security vs regular
            is_security = "-security" in source

            # Classify importance
            if is_security:
                importance = "security"
            elif name in ("linux-image", "linux-headers", "linux-generic",
                          "linux-libc-dev", "systemd", "openssl", "libssl",
                          "openssh-server", "openssh-client", "sudo", "bash",
                          "libc6", "libgnutls30", "curl", "wget", "git"):
                importance = "critical"
            elif name.startswith("lib"):
                importance = "library"
            else:
                importance = "regular"

            packages.append({
                "name": name,
                "current": old_version,
                "available": new_version,
                "source": source,
                "importance": importance,
                "is_security": is_security,
            })

    security_count = sum(1 for p in packages if p["is_security"])
    critical_count = sum(1 for p in packages if p["importance"] == "critical")

    return {
        "packages": packages,
        "total": len(packages),
        "security": security_count,
        "critical": critical_count,
        "regular": len(packages) - security_count - critical_count,
        "scanned_at": time.time(),
    }


def scan_system_tools() -> list[dict]:
    """Check versions of commonly used system tools."""
    tools = [
        {"name": "git", "cmd": ["git", "--version"], "parse": r"git version ([\d.]+)"},
        {"name": "node", "cmd": ["node", "--version"], "parse": r"v?([\d.]+)"},
        {"name": "npm", "cmd": ["npm", "--version"], "parse": r"([\d.]+)"},
        {"name": "python3", "cmd": ["python3", "--version"], "parse": r"Python ([\d.]+)"},
        {"name": "pip", "cmd": ["pip", "--version"], "parse": r"pip ([\d.]+)"},
        {"name": "docker", "cmd": ["docker", "--version"], "parse": r"Docker version ([\d.]+)"},
        {"name": "ollama", "cmd": ["ollama", "--version"], "parse": r"([\d.]+)"},
        {"name": "gh", "cmd": ["gh", "--version"], "parse": r"gh version ([\d.]+)"},
        {"name": "curl", "cmd": ["curl", "--version"], "parse": r"curl ([\d.]+)"},
        {"name": "openssl", "cmd": ["openssl", "version"], "parse": r"OpenSSL ([\d.]+\w*)"},
    ]

    results = []
    for tool in tools:
        rc, out, _ = _run(tool["cmd"])
        if rc == 0 and out:
            match = re.search(tool["parse"], out)
            version = match.group(1) if match else out.strip()[:30]
            results.append({
                "name": tool["name"],
                "version": version,
                "installed": True,
            })
        else:
            results.append({
                "name": tool["name"],
                "version": "not installed",
                "installed": False,
            })

    return results


def scan_all() -> dict:
    """Full system scan: info + apt updates + tool versions."""
    return {
        "system_info": get_system_info(),
        "apt_updates": scan_apt_updates(),
        "tools": scan_system_tools(),
        "scanned_at": time.time(),
    }


def load_cache() -> dict:
    """Load cached system scan."""
    if not CACHE_FILE.exists():
        return {}
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(data: dict) -> None:
    """Save system scan to cache."""
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_cache_fresh(cache: dict) -> bool:
    """Check if cache is within TTL."""
    scanned_at = cache.get("scanned_at", 0)
    return (time.time() - scanned_at) < CACHE_TTL


def generate_report(data: dict) -> str:
    """Generate a human-readable system update report."""
    from datetime import datetime

    lines = []
    lines.append("# System Update Report")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # System info
    info = data.get("system_info", {})
    lines.append("## System Info")
    lines.append("")
    lines.append(f"- **OS:** {info.get('os', '?')}")
    lines.append(f"- **Kernel:** {info.get('kernel', '?')}")
    lines.append(f"- **Hostname:** {info.get('hostname', '?')}")
    lines.append(f"- **Uptime:** {info.get('uptime', '?')}")
    lines.append("")

    # Disk
    disks = info.get("disk_usage", [])
    if disks:
        lines.append("## Disk Usage")
        lines.append("")
        lines.append("| Mount | Size | Used | Available | Used% |")
        lines.append("|-------|------|------|-----------|-------|")
        for d in disks:
            lines.append(f"| {d['mount']} | {d['size']} | {d['used']} | {d['available']} | {d['percent']} |")
        lines.append("")

    # APT updates
    apt = data.get("apt_updates", {})
    total = apt.get("total", 0)
    security = apt.get("security", 0)
    critical = apt.get("critical", 0)
    lines.append("## Package Updates")
    lines.append("")
    lines.append(f"- **Total available:** {total}")
    lines.append(f"- **Security updates:** {security}")
    lines.append(f"- **Critical packages:** {critical}")
    lines.append(f"- **Regular updates:** {apt.get('regular', 0)}")
    lines.append("")

    if total > 0:
        # Group by importance
        pkgs = apt.get("packages", [])
        for importance in ["security", "critical", "regular", "library"]:
            group = [p for p in pkgs if p["importance"] == importance]
            if not group:
                continue
            label = importance.upper()
            lines.append(f"### {label} ({len(group)})")
            lines.append("")
            lines.append("| Package | Current | Available |")
            lines.append("|---------|---------|-----------|")
            for p in sorted(group, key=lambda x: x["name"]):
                lines.append(f"| {p['name']} | {p['current']} | {p['available']} |")
            lines.append("")

    # Tools
    tools = data.get("tools", [])
    if tools:
        lines.append("## System Tools")
        lines.append("")
        lines.append("| Tool | Version | Status |")
        lines.append("|------|---------|--------|")
        for t in tools:
            status = "installed" if t["installed"] else "**NOT INSTALLED**"
            lines.append(f"| {t['name']} | {t['version']} | {status} |")
        lines.append("")

    # Update instructions
    lines.append("## How to Update")
    lines.append("")
    lines.append("### Quick update (safe — patches and security fixes):")
    lines.append("```bash")
    lines.append("sudo apt update && sudo apt upgrade -y")
    lines.append("```")
    lines.append("")
    lines.append("### Full update (includes held-back packages):")
    lines.append("```bash")
    lines.append("sudo apt update && sudo apt full-upgrade -y")
    lines.append("```")
    lines.append("")
    lines.append("### Clean up old packages:")
    lines.append("```bash")
    lines.append("sudo apt autoremove -y && sudo apt autoclean")
    lines.append("```")
    lines.append("")
    if security > 0:
        lines.append(f"**{security} security updates available — update soon.**")
        lines.append("")

    return "\n".join(lines)
