"""
github/github_checker.py — Verifies GitHub commit activity for today.

Uses the GitHub REST API v3 (no external git binary needed).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import httpx

from logger import get_logger

log = get_logger(__name__)


class GitHubChecker:
    """Checks whether the authenticated user made a commit today."""

    _API_BASE = "https://api.github.com"

    def __init__(self, username: str, token: str) -> None:
        self.username = username
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── public ────────────────────────────────────────────────────────────────

    def has_commit_today(self) -> bool:
        """Return True if the user has at least one commit today (UTC date)."""
        today = date.today().isoformat()
        log.info("Checking GitHub activity for %s on %s", self.username, today)

        # Strategy 1: Search commits via events API (fast, no extra permissions)
        try:
            if self._check_via_events(today):
                log.info("✅ GitHub commit detected via events API")
                return True
        except Exception as exc:
            log.warning("Events API check failed: %s — falling back to search", exc)

        # Strategy 2: GitHub search API
        try:
            if self._check_via_search(today):
                log.info("✅ GitHub commit detected via search API")
                return True
        except Exception as exc:
            log.warning("Search API check failed: %s", exc)

        log.info("❌ No GitHub commit found for today (%s)", today)
        return False

    def get_today_commit_sha(self) -> Optional[str]:
        """Return the SHA of the latest commit today, or None."""
        today = date.today().isoformat()
        try:
            return self._latest_commit_sha_from_events(today)
        except Exception:
            return None

    # ── private ───────────────────────────────────────────────────────────────

    def _check_via_events(self, today_iso: str) -> bool:
        url = f"{self._API_BASE}/users/{self.username}/events"
        params = {"per_page": 100}
        with httpx.Client(headers=self._headers, timeout=20) as client:
            # GitHub returns max 300 events over up to 3 pages
            for page in range(1, 4):
                params["page"] = page
                resp = client.get(url, params=params)
                resp.raise_for_status()
                events = resp.json()
                if not events:
                    break
                for event in events:
                    event_date = event.get("created_at", "")[:10]
                    if event_date < today_iso:
                        # Events are newest-first; stop when we pass today
                        return False
                    if event.get("type") == "PushEvent" and event_date == today_iso:
                        return True
        return False

    def _latest_commit_sha_from_events(self, today_iso: str) -> Optional[str]:
        url = f"{self._API_BASE}/users/{self.username}/events"
        with httpx.Client(headers=self._headers, timeout=20) as client:
            resp = client.get(url, params={"per_page": 30})
            resp.raise_for_status()
            for event in resp.json():
                if (
                    event.get("type") == "PushEvent"
                    and event.get("created_at", "")[:10] == today_iso
                ):
                    payload = event.get("payload", {})
                    commits = payload.get("commits", [])
                    if commits:
                        return commits[-1].get("sha")
        return None

    def _check_via_search(self, today_iso: str) -> bool:
        """Use GitHub commit search — rate-limited to 10 req/min for unauth."""
        url = f"{self._API_BASE}/search/commits"
        query = f"author:{self.username} committer-date:{today_iso}"
        with httpx.Client(headers=self._headers, timeout=20) as client:
            resp = client.get(url, params={"q": query, "per_page": 1})
            if resp.status_code == 422:
                # Validation error — search index may not have today yet
                return False
            resp.raise_for_status()
            data = resp.json()
            return data.get("total_count", 0) > 0
