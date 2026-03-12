"""Scrape GitHub Trending repos."""

import requests
from bs4 import BeautifulSoup
from codequest.intel.config import GITHUB_LANGUAGES, GITHUB_TOPICS, MAX_ITEMS_PER_SOURCE


def fetch_trending(since="daily"):
    """Fetch trending repos across configured languages."""
    results = []
    seen = set()

    for lang in GITHUB_LANGUAGES:
        url = f"https://github.com/trending/{lang}?since={since}"
        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "TechPulse/1.0"})
            resp.raise_for_status()
            results.extend(_parse_trending_page(resp.text, lang, seen))
        except requests.RequestException as e:
            print(f"  [!] Failed to fetch trending/{lang}: {e}")

    return results[:MAX_ITEMS_PER_SOURCE]


def fetch_topic_repos():
    """Fetch repos from AI/ML GitHub topics via API."""
    results = []
    seen = set()

    for topic in GITHUB_TOPICS:
        url = "https://api.github.com/search/repositories"
        params = {
            "q": f"topic:{topic}",
            "sort": "stars",
            "order": "desc",
            "per_page": 5,
        }
        try:
            resp = requests.get(url, params=params, timeout=15,
                                headers={"Accept": "application/vnd.github.v3+json",
                                          "User-Agent": "TechPulse/1.0"})
            resp.raise_for_status()
            data = resp.json()
            for repo in data.get("items", []):
                full_name = repo["full_name"]
                if full_name in seen:
                    continue
                seen.add(full_name)
                results.append({
                    "source": "GitHub Topics",
                    "name": full_name,
                    "url": repo["html_url"],
                    "description": repo.get("description", "") or "",
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "topic": topic,
                })
        except requests.RequestException as e:
            print(f"  [!] Failed to fetch topic {topic}: {e}")

    return results[:MAX_ITEMS_PER_SOURCE]


def _parse_trending_page(html, language, seen):
    """Parse GitHub trending HTML page."""
    soup = BeautifulSoup(html, "lxml")
    items = []

    for article in soup.select("article.Box-row"):
        name_el = article.select_one("h2 a")
        if not name_el:
            continue

        full_name = name_el.get("href", "").strip("/")
        if not full_name or full_name in seen:
            continue
        seen.add(full_name)

        desc_el = article.select_one("p")
        description = desc_el.get_text(strip=True) if desc_el else ""

        stars_el = article.select_one("a[href$='/stargazers']")
        stars_text = stars_el.get_text(strip=True) if stars_el else "0"
        stars = _parse_star_count(stars_text)

        lang_el = article.select_one("[itemprop='programmingLanguage']")
        lang = lang_el.get_text(strip=True) if lang_el else language

        today_el = article.select_one("span.d-inline-block.float-sm-right")
        today_stars = today_el.get_text(strip=True) if today_el else ""

        items.append({
            "source": "GitHub Trending",
            "name": full_name,
            "url": f"https://github.com/{full_name}",
            "description": description,
            "stars": stars,
            "language": lang,
            "today_stars": today_stars,
        })

    return items


def _parse_star_count(text):
    """Parse star count strings like '1,234' or '12.5k'."""
    text = text.strip().replace(",", "")
    if text.lower().endswith("k"):
        try:
            return int(float(text[:-1]) * 1000)
        except ValueError:
            return 0
    try:
        return int(text)
    except ValueError:
        return 0
