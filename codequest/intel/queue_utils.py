"""Queue I/O for Linear and ND Helper integrations (CodeQuest-local paths)."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

_QUEUE_DIR = str(Path.home() / ".codequest" / "queues")
LINEAR_QUEUE = os.path.join(_QUEUE_DIR, "linear-queue.json")
ND_QUEUE = os.path.join(_QUEUE_DIR, "nd-queue.json")
ND_WEBHOOK = os.environ.get("ND_WEBHOOK_URL", "http://localhost:3000/api/ingest/webhook")


def load_queue(filepath):
    """Read JSON array from file, return [] on missing/invalid."""
    try:
        with open(filepath, "r") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def save_queue(filepath, queue):
    """Atomic write: write to .tmp then os.replace."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    tmp = filepath + ".tmp"
    with open(tmp, "w") as f:
        json.dump(queue, f, indent=2)
    os.replace(tmp, filepath)


def format_nd_payload(item, chat_context=None):
    """Format card + chat into structured text for ND webhook."""
    name = item.get("name", "Unknown")
    heat = item.get("heat", "")
    rec = item.get("rec", "")
    source = item.get("source", "")
    url = item.get("url", "")
    desc = item.get("desc", "") or item.get("description", "")

    lines = [f"[Tech Pulse] {name} ({heat}/{rec})"]
    if source or url:
        lines.append(f"Source: {source} | URL: {url}")
    if desc:
        lines.append(desc)

    if chat_context:
        lines.append("--- AI Analysis ---")
        for msg in chat_context:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            lines.append(f"{role}: {content}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(f"--- Captured {now} ---")

    return "\n".join(lines)
