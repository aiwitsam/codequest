"""Thin wrapper around reddit-sentinel for CodeQuest integration."""

import subprocess
import threading


class RedditIntelWrapper:
    """Read-only wrapper around SentinelStore for search and stats."""

    def __init__(self):
        self._store = None

    def _get_store(self):
        if self._store is None:
            try:
                from reddit_sentinel.store import SentinelStore
                self._store = SentinelStore()
            except ImportError:
                return None
        return self._store

    def search(self, query, subreddit=None, limit=20):
        """FTS5 search across intel."""
        store = self._get_store()
        if not store:
            return []
        try:
            results = store.search(query, limit=limit)
            if subreddit:
                results = [r for r in results if r.get("subreddit") == subreddit]
            return results
        except Exception:
            return []

    def get_stats(self):
        """Get database statistics."""
        store = self._get_store()
        if not store:
            return {"total_posts": 0, "total_intel": 0, "error": "reddit-sentinel not available"}
        try:
            return store.get_stats()
        except Exception as e:
            return {"total_posts": 0, "total_intel": 0, "error": str(e)}

    def get_recent(self, hours=24):
        """Get recent intel items."""
        store = self._get_store()
        if not store:
            return []
        try:
            return store.get_recent_intel(since_hours=hours)
        except Exception:
            return []

    def get_cves(self, limit=50):
        """Get intel items that have CVE IDs."""
        store = self._get_store()
        if not store:
            return []
        try:
            results = store.get_recent_intel(since_hours=720)  # 30 days
            cve_items = [r for r in results if r.get("cve_ids") and r["cve_ids"] != "[]"]
            return cve_items[:limit]
        except Exception:
            return []

    def trigger_scrape(self):
        """Run reddit-sentinel scrape in background thread."""
        def _run():
            try:
                subprocess.run(
                    ["reddit-sentinel", "scrape"],
                    capture_output=True,
                    timeout=120,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                pass

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return True
