"""
config.py — Central configuration loader for Streak Guardian.

Reads all settings from environment variables (via .env) and exposes
typed, validated Config / Settings dataclasses to the rest of the app.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Load .env from project root (works when run from any directory)
_PROJECT_ROOT = Path(__file__).parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)


# ── helpers ──────────────────────────────────────────────────────────────────

def _require(key: str) -> str:
    """Return env-var value or raise a clear error if missing."""
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example → .env and fill in all values."
        )
    return val


def _optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ── sub-configs ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GitHubConfig:
    username: str
    token: str
    repo_name: str
    repo_owner: str
    branch: str
    email: str

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        return cls(
            username=_require("GITHUB_USERNAME"),
            token=_require("GITHUB_TOKEN"),
            repo_name=_require("GITHUB_REPO_NAME"),
            repo_owner=_require("GITHUB_REPO_OWNER"),
            branch=_optional("GITHUB_BRANCH", "main"),
            email=_require("GITHUB_EMAIL"),
        )


@dataclass(frozen=True)
class LeetCodeConfig:
    username: str
    password: str
    default_problem_slug: str
    default_solution_file: str
    language_id: int

    @classmethod
    def from_env(cls) -> "LeetCodeConfig":
        return cls(
            username=_require("LEETCODE_USERNAME"),
            password=_require("LEETCODE_PASSWORD"),
            default_problem_slug=_optional("LEETCODE_DEFAULT_PROBLEM_SLUG", "two-sum"),
            default_solution_file=_optional("LEETCODE_DEFAULT_SOLUTION_FILE", "problem1.py"),
            language_id=int(_optional("LEETCODE_LANGUAGE_ID", "71")),
        )


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str

    @classmethod
    def from_env(cls) -> "TelegramConfig":
        return cls(
            bot_token=_require("TELEGRAM_BOT_TOKEN"),
            chat_id=_require("TELEGRAM_CHAT_ID"),
        )


@dataclass(frozen=True)
class AppConfig:
    timezone: ZoneInfo
    log_level: str
    dashboard_port: int
    warning_check_time: str    # "HH:MM"
    protection_run_time: str   # "HH:MM"
    database_path: Path
    project_root: Path
    solutions_dir: Path
    logs_dir: Path
    screenshots_dir: Path
    encryption_key: str

    @classmethod
    def from_env(cls) -> "AppConfig":
        root = _PROJECT_ROOT
        tz_str = _optional("TIMEZONE", "UTC")
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            raise ValueError(f"Invalid TIMEZONE value: '{tz_str}'")

        return cls(
            timezone=tz,
            log_level=_optional("LOG_LEVEL", "INFO").upper(),
            dashboard_port=int(_optional("DASHBOARD_PORT", "8000")),
            warning_check_time=_optional("WARNING_CHECK_TIME", "22:30"),
            protection_run_time=_optional("PROTECTION_RUN_TIME", "23:45"),
            database_path=root / _optional("DATABASE_PATH", "database/streak.db"),
            project_root=root,
            solutions_dir=root / "solutions",
            logs_dir=root / "logs",
            screenshots_dir=root / "screenshots",
            encryption_key=_optional("ENCRYPTION_KEY", ""),
        )


# ── master config ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Settings:
    github: GitHubConfig
    leetcode: LeetCodeConfig
    telegram: TelegramConfig
    app: AppConfig

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            github=GitHubConfig.from_env(),
            leetcode=LeetCodeConfig.from_env(),
            telegram=TelegramConfig.from_env(),
            app=AppConfig.from_env(),
        )


# Singleton — import and use `settings` anywhere in the project
settings: Settings = Settings.load()
