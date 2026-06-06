"""
leetcode/leetcode_checker.py — Checks LeetCode submission activity for today.

Uses the LeetCode GraphQL API (public, no login required for submission queries).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

import httpx

from logger import get_logger

log = get_logger(__name__)

_GRAPHQL_URL = "https://leetcode.com/graphql"

# GraphQL query to fetch recent submissions for a user
_RECENT_SUBMISSIONS_QUERY = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    id
    title
    titleSlug
    timestamp
  }
}
"""

# Alternative: get ALL recent submissions (accepted + attempted)
_ALL_SUBMISSIONS_QUERY = """
query recentSubmissions($username: String!) {
  recentSubmissionList(username: $username) {
    id
    title
    titleSlug
    statusDisplay
    timestamp
  }
}
"""


class LeetCodeChecker:
    """Checks whether the user has any LeetCode submission today."""

    def __init__(self, username: str) -> None:
        self.username = username
        self._headers = {
            "Content-Type": "application/json",
            "Referer": "https://leetcode.com",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
        }

    # ── public ────────────────────────────────────────────────────────────────

    def has_submission_today(self) -> bool:
        """Return True if the user has at least one submission today."""
        log.info("Checking LeetCode activity for user: %s", self.username)

        # Try accepted submissions first (faster, more reliable)
        try:
            if self._check_accepted_today():
                log.info("✅ LeetCode accepted submission detected today")
                return True
        except Exception as exc:
            log.warning("Accepted-submissions check failed: %s — trying all submissions", exc)

        # Fall back: check all recent submissions
        try:
            if self._check_all_submissions_today():
                log.info("✅ LeetCode submission (any status) detected today")
                return True
        except Exception as exc:
            log.warning("All-submissions check failed: %s", exc)

        log.info("❌ No LeetCode submission found for today")
        return False

    def get_today_submission_count(self) -> int:
        """Return count of submissions today (0 if unknown)."""
        try:
            subs = self._fetch_accepted_submissions(limit=20)
            today_ts = self._today_midnight_ts()
            return sum(1 for s in subs if int(s.get("timestamp", 0)) >= today_ts)
        except Exception:
            return 0

    # ── private ───────────────────────────────────────────────────────────────

    def _today_midnight_ts(self) -> int:
        """Unix timestamp for today's midnight UTC."""
        today = date.today()
        midnight = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        return int(midnight.timestamp())

    def _check_accepted_today(self) -> bool:
        subs = self._fetch_accepted_submissions(limit=20)
        today_ts = self._today_midnight_ts()
        for sub in subs:
            if int(sub.get("timestamp", 0)) >= today_ts:
                return True
        return False

    def _check_all_submissions_today(self) -> bool:
        today_ts = self._today_midnight_ts()
        payload = {
            "query": _ALL_SUBMISSIONS_QUERY,
            "variables": {"username": self.username},
        }
        with httpx.Client(headers=self._headers, timeout=20) as client:
            resp = client.post(_GRAPHQL_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()

        subs = (data.get("data") or {}).get("recentSubmissionList") or []
        for sub in subs:
            if int(sub.get("timestamp", 0)) >= today_ts:
                return True
        return False

    def _fetch_accepted_submissions(self, limit: int = 20) -> list[dict]:
        payload = {
            "query": _RECENT_SUBMISSIONS_QUERY,
            "variables": {"username": self.username, "limit": limit},
        }
        with httpx.Client(headers=self._headers, timeout=20) as client:
            resp = client.post(_GRAPHQL_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return (data.get("data") or {}).get("recentAcSubmissionList") or []
