"""Monitor Anthropic/Claude updates from docs and changelog."""

import requests
from bs4 import BeautifulSoup


def fetch_claude_updates():
    """Fetch recent updates from Anthropic docs changelog."""
    results = []

    urls = [
        "https://docs.anthropic.com/en/docs/about-claude/models",
        "https://docs.anthropic.com/en/api/changelog",
    ]

    for url in urls:
        try:
            resp = requests.get(url, timeout=15,
                                headers={"User-Agent": "TechPulse/1.0"})
            resp.raise_for_status()
            results.extend(_parse_changelog(resp.text, url))
        except requests.RequestException as e:
            print(f"  [!] Failed to fetch {url}: {e}")

    # GitHub releases for anthropic-sdk-python
    try:
        resp = requests.get(
            "https://api.github.com/repos/anthropics/anthropic-sdk-python/releases",
            timeout=15,
            params={"per_page": 5},
            headers={"Accept": "application/vnd.github.v3+json",
                      "User-Agent": "TechPulse/1.0"},
        )
        resp.raise_for_status()
        for release in resp.json():
            results.append({
                "source": "Anthropic SDK",
                "name": release.get("name") or release.get("tag_name", ""),
                "url": release.get("html_url", ""),
                "description": (release.get("body", "") or "")[:300],
                "date": release.get("published_at", ""),
            })
    except requests.RequestException as e:
        print(f"  [!] Failed to fetch Anthropic SDK releases: {e}")

    # Claude Code CLI releases
    try:
        resp = requests.get(
            "https://api.github.com/repos/anthropics/claude-code/releases",
            timeout=15,
            params={"per_page": 5},
            headers={"Accept": "application/vnd.github.v3+json",
                      "User-Agent": "TechPulse/1.0"},
        )
        resp.raise_for_status()
        for release in resp.json():
            results.append({
                "source": "Claude Code",
                "name": release.get("name") or release.get("tag_name", ""),
                "url": release.get("html_url", ""),
                "description": (release.get("body", "") or "")[:300],
                "date": release.get("published_at", ""),
            })
    except requests.RequestException as e:
        print(f"  [!] Failed to fetch Claude Code releases: {e}")

    return results


def _parse_changelog(html, base_url):
    """Parse changelog/docs page for update entries."""
    soup = BeautifulSoup(html, "lxml")
    results = []

    for heading in soup.select("h2, h3"):
        text = heading.get_text(strip=True)
        desc_parts = []
        for sib in heading.find_next_siblings():
            if sib.name in ("h2", "h3"):
                break
            desc_parts.append(sib.get_text(strip=True))

        description = " ".join(desc_parts)[:300]
        if text and description:
            results.append({
                "source": "Anthropic Docs",
                "name": text,
                "url": base_url,
                "description": description,
            })

    return results[:10]
