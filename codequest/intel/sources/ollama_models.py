"""Scrape Ollama library for new and popular models."""

import requests
from bs4 import BeautifulSoup
from codequest.intel.config import MAX_ITEMS_PER_SOURCE


def fetch_ollama_models():
    """Scrape ollama.com/library for model listings."""
    url = "https://ollama.com/library"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "TechPulse/1.0"})
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [!] Failed to fetch Ollama library: {e}")
        return []

    return _parse_library_page(resp.text)


def _parse_library_page(html):
    """Parse Ollama library page for model cards."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for item in soup.select("li a[href^='/library/']"):
        name_el = item.select_one("h2, span.text-lg, span.font-medium, div.truncate")
        if not name_el:
            name_text = item.get_text(strip=True).split("\n")[0].strip()
        else:
            name_text = name_el.get_text(strip=True)

        if not name_text:
            continue

        href = item.get("href", "")
        desc_el = item.select_one("p, span.text-sm, span.text-neutral-400")
        description = desc_el.get_text(strip=True) if desc_el else ""

        pulls = ""
        for span in item.select("span"):
            text = span.get_text(strip=True).lower()
            if "pull" in text or "download" in text or "k" in text or "m" in text:
                pulls = span.get_text(strip=True)
                break

        results.append({
            "source": "Ollama Library",
            "name": name_text,
            "url": f"https://ollama.com{href}",
            "description": description,
            "pulls": pulls,
        })

    if not results:
        for card in soup.select("[class*='model'], [class*='card'], a[href*='/library/']"):
            text = card.get_text(strip=True)
            href = card.get("href", "")
            if href and "/library/" in href and text:
                name = href.split("/library/")[-1].split("/")[0]
                results.append({
                    "source": "Ollama Library",
                    "name": name,
                    "url": f"https://ollama.com{href}" if href.startswith("/") else href,
                    "description": text[:200],
                    "pulls": "",
                })

    return results[:MAX_ITEMS_PER_SOURCE]
