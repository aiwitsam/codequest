"""Recommendation engine - adapted from tech-pulse formatter."""

from codequest.intel.config import get_my_stack, get_hot_keywords


def score_item(item):
    """Score an item for relevance. Returns (heat, recommendation, reason_str)."""
    text = f"{item.get('name', '')} {item.get('description', '')} {' '.join(item.get('tags', []))}".lower()

    score = 0
    reasons = []

    my_stack = get_my_stack()
    hot_keywords = get_hot_keywords()

    # Check against tech stack
    for category, keywords in my_stack.items():
        for kw in keywords:
            if kw.lower() in text:
                score += 3
                reasons.append(kw)

    # Hot keywords bonus
    for kw in hot_keywords:
        if kw.lower() in text:
            score += 5
            if kw not in reasons:
                reasons.append(kw)

    # Star count bonus for GitHub items
    stars = item.get("stars", 0)
    if stars > 10000:
        score += 4
    elif stars > 1000:
        score += 2

    # Downloads bonus for HF models
    downloads = item.get("downloads", 0)
    if downloads > 100000:
        score += 3
    elif downloads > 10000:
        score += 1

    # Determine heat level
    if score >= 10:
        heat = "Hot"
    elif score >= 5:
        heat = "Warm"
    else:
        heat = "Watch"

    # Determine recommendation
    if score >= 12:
        rec = "Incorporate"
    elif score >= 8:
        rec = "Clone It"
    elif score >= 4:
        rec = "Watch"
    else:
        rec = "Skip"

    reason_str = ", ".join(reasons[:3]) if reasons else "general interest"
    return heat, rec, reason_str


def generate_social_hook(item):
    """Generate a suggested social media post angle."""
    name = item.get("name", "")
    desc = item.get("description", "")[:100]
    source = item.get("source", "")
    stars = item.get("stars", 0)

    if "Hot" in item.get("_heat", ""):
        prefix = "This is the one to watch"
    elif stars and stars > 5000:
        prefix = f"{stars:,} stars and climbing"
    else:
        prefix = "Just spotted this"

    short_desc = desc.split(".")[0] if desc else name
    return f"{prefix}: {short_desc} [{source}]"
