"""Fetch trending models and spaces from Hugging Face."""

import requests
from codequest.intel.config import MAX_ITEMS_PER_SOURCE


def fetch_trending_models():
    """Fetch trending models from Hugging Face API."""
    url = "https://huggingface.co/api/models"
    params = {
        "sort": "likes7d",
        "limit": MAX_ITEMS_PER_SOURCE,
    }
    try:
        resp = requests.get(url, params=params, timeout=15,
                            headers={"User-Agent": "TechPulse/1.0"})
        resp.raise_for_status()
        models = resp.json()
    except requests.RequestException as e:
        print(f"  [!] Failed to fetch HF models: {e}")
        return []

    results = []
    for m in models:
        model_id = m.get("modelId", m.get("id", ""))
        results.append({
            "source": "Hugging Face Models",
            "name": model_id,
            "url": f"https://huggingface.co/{model_id}",
            "description": m.get("pipeline_tag", "") or "",
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "tags": m.get("tags", [])[:5],
        })

    return results


def fetch_trending_spaces():
    """Fetch trending spaces from Hugging Face API."""
    url = "https://huggingface.co/api/spaces"
    params = {
        "sort": "likes7d",
        "limit": 10,
    }
    try:
        resp = requests.get(url, params=params, timeout=15,
                            headers={"User-Agent": "TechPulse/1.0"})
        resp.raise_for_status()
        spaces = resp.json()
    except requests.RequestException as e:
        print(f"  [!] Failed to fetch HF spaces: {e}")
        return []

    results = []
    for s in spaces:
        space_id = s.get("id", "")
        results.append({
            "source": "Hugging Face Spaces",
            "name": space_id,
            "url": f"https://huggingface.co/spaces/{space_id}",
            "description": s.get("cardData", {}).get("title", "") if isinstance(s.get("cardData"), dict) else "",
            "likes": s.get("likes", 0),
            "sdk": s.get("sdk", ""),
        })

    return results
