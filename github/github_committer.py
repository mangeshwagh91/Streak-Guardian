"""
github/github_committer.py — Creates a commit via the GitHub Contents API.

No local git installation required — uses pure REST API calls.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from logger import get_logger

log = get_logger(__name__)


class GitHubCommitter:
    """
    Creates / updates a file in a GitHub repo via the Contents API.

    Writes to  <repo>/daily-log.txt  with the current timestamp.
    """

    _API_BASE = "https://api.github.com"

    def __init__(
        self,
        username: str,
        token: str,
        repo_owner: str,
        repo_name: str,
        branch: str,
        email: str,
    ) -> None:
        self.username = username
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.branch = branch
        self.email = email
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── public ────────────────────────────────────────────────────────────────

    def commit_daily_log(self) -> dict:
        """
        Update daily-log.txt with today's timestamp and commit it.

        Returns a dict with keys: sha, commit_url, message.
        Raises on failure.
        """
        file_path = "daily-log.txt"
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        content_str = self._build_log_content(file_path, timestamp)
        log.info("Committing daily-log.txt to %s/%s@%s", self.repo_owner, self.repo_name, self.branch)

        sha = self._get_file_sha(file_path)
        result = self._put_file(file_path, content_str, sha, timestamp)

        commit_sha = result["commit"]["sha"]
        commit_url = result["commit"]["html_url"]
        log.info("✅ Committed successfully — SHA: %s", commit_sha[:12])
        log.info("   %s", commit_url)

        return {
            "sha": commit_sha,
            "commit_url": commit_url,
            "message": f"🛡️ Streak Guardian: daily log {timestamp}",
        }

    def ensure_repo_exists(self) -> bool:
        """
        Check if the repo exists; if not, create it as a private repo.
        Returns True if it already existed.
        """
        url = f"{self._API_BASE}/repos/{self.repo_owner}/{self.repo_name}"
        with httpx.Client(headers=self._headers, timeout=20) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                log.debug("Repo %s/%s already exists.", self.repo_owner, self.repo_name)
                return True
            if resp.status_code == 404:
                log.info("Repo not found — creating %s/%s …", self.repo_owner, self.repo_name)
                self._create_repo()
                return False
            resp.raise_for_status()
        return False

    # ── private ───────────────────────────────────────────────────────────────

    def _build_log_content(self, file_path: str, timestamp: str) -> str:
        """
        Try to fetch the existing file content and append to it;
        fall back to a fresh log if the file doesn't exist yet.
        """
        existing = self._get_file_content(file_path)
        if existing:
            return existing + f"\n{timestamp}"
        header = (
            "# Streak Guardian — Daily Log\n"
            "# Auto-generated — do not edit manually\n"
            "#\n"
        )
        return header + f"{timestamp}\n"

    def _get_file_sha(self, file_path: str) -> Optional[str]:
        url = f"{self._API_BASE}/repos/{self.repo_owner}/{self.repo_name}/contents/{file_path}"
        params = {"ref": self.branch}
        with httpx.Client(headers=self._headers, timeout=20) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json().get("sha")

    def _get_file_content(self, file_path: str) -> Optional[str]:
        url = f"{self._API_BASE}/repos/{self.repo_owner}/{self.repo_name}/contents/{file_path}"
        params = {"ref": self.branch}
        with httpx.Client(headers=self._headers, timeout=20) as client:
            resp = client.get(url, params=params)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            encoded = resp.json().get("content", "")
            return base64.b64decode(encoded).decode("utf-8")

    def _put_file(
        self,
        file_path: str,
        content: str,
        sha: Optional[str],
        timestamp: str,
    ) -> dict:
        url = f"{self._API_BASE}/repos/{self.repo_owner}/{self.repo_name}/contents/{file_path}"
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        body: dict = {
            "message": f"🛡️ Streak Guardian: daily log {timestamp}",
            "content": encoded,
            "branch": self.branch,
            "committer": {
                "name": self.username,
                "email": self.email,
            },
            "author": {
                "name": self.username,
                "email": self.email,
            },
        }
        if sha:
            body["sha"] = sha

        with httpx.Client(headers=self._headers, timeout=30) as client:
            resp = client.put(url, json=body)
            resp.raise_for_status()
            return resp.json()

    def _create_repo(self) -> None:
        url = f"{self._API_BASE}/user/repos"
        body = {
            "name": self.repo_name,
            "description": "🛡️ Streak Guardian — automated activity log",
            "private": True,
            "auto_init": True,
        }
        with httpx.Client(headers=self._headers, timeout=30) as client:
            resp = client.post(url, json=body)
            resp.raise_for_status()
        log.info("✅ Created private repo: %s/%s", self.repo_owner, self.repo_name)
