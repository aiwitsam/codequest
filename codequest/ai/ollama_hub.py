"""Ollama Hub - model management beyond basic chat."""

import subprocess
import requests

from codequest.config import get_config


def _get_base_url():
    config = get_config()
    return config.get("ai", {}).get("ollama_url", "http://localhost:11434")


def list_models():
    """GET /api/tags - list installed models."""
    try:
        resp = requests.get(f"{_get_base_url()}/api/tags", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = []
        for m in data.get("models", []):
            models.append({
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "size_gb": round(m.get("size", 0) / (1024**3), 1),
                "modified_at": m.get("modified_at", ""),
                "parameter_size": m.get("details", {}).get("parameter_size", ""),
                "family": m.get("details", {}).get("family", ""),
                "quantization": m.get("details", {}).get("quantization_level", ""),
            })
        return models
    except (requests.RequestException, ValueError):
        return []


def running_models():
    """GET /api/ps - list currently loaded models."""
    try:
        resp = requests.get(f"{_get_base_url()}/api/ps", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        models = []
        for m in data.get("models", []):
            models.append({
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "size_vram": m.get("size_vram", 0),
                "expires_at": m.get("expires_at", ""),
            })
        return models
    except (requests.RequestException, ValueError):
        return []


def pull_model(name):
    """POST /api/pull with stream=true - yields progress dicts."""
    try:
        resp = requests.post(
            f"{_get_base_url()}/api/pull",
            json={"name": name, "stream": True},
            stream=True,
            timeout=600,
        )
        resp.raise_for_status()
        import json
        for line in resp.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    yield data
                except ValueError:
                    pass
    except requests.RequestException as e:
        yield {"error": str(e)}


def delete_model(name):
    """DELETE /api/delete - remove a model."""
    try:
        resp = requests.delete(
            f"{_get_base_url()}/api/delete",
            json={"name": name},
            timeout=30,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def gpu_info():
    """Get GPU info via nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
                "--format=csv,noheader",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 5:
                return {
                    "name": parts[0],
                    "memory_total": parts[1],
                    "memory_used": parts[2],
                    "memory_free": parts[3],
                    "gpu_utilization": parts[4],
                    "available": True,
                }
        return {"available": False, "error": "Parse error"}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {"available": False, "error": "nvidia-smi not available"}
