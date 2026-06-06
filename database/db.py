"""
database/db.py — SQLite database layer for Streak Guardian.

Manages:
  • streak_log      — daily activity records
  • action_log      — automated actions taken
  • notification_log — outbound notifications sent
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Generator, Optional

from logger import get_logger

log = get_logger(__name__)


# ── schema ────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
-- Daily streak status per service
CREATE TABLE IF NOT EXISTS streak_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date        TEXT    NOT NULL,          -- ISO date YYYY-MM-DD
    service         TEXT    NOT NULL,          -- 'github' | 'leetcode'
    had_activity    INTEGER NOT NULL DEFAULT 0,-- 1 = yes, 0 = no
    auto_saved      INTEGER NOT NULL DEFAULT 0,-- 1 = system committed/submitted
    checked_at      TEXT    NOT NULL,          -- ISO datetime
    detail          TEXT,                      -- extra info (commit sha, submission id)
    UNIQUE(log_date, service)
);

-- Every automated action the system takes
CREATE TABLE IF NOT EXISTS action_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action_time TEXT    NOT NULL,   -- ISO datetime
    service     TEXT    NOT NULL,   -- 'github' | 'leetcode' | 'system'
    action_type TEXT    NOT NULL,   -- 'commit' | 'submit' | 'check' | 'notify' …
    status      TEXT    NOT NULL,   -- 'success' | 'failure' | 'skipped'
    detail      TEXT,               -- human-readable description or error
    error       TEXT                -- full traceback on failure
);

-- Telegram / notification history
CREATE TABLE IF NOT EXISTS notification_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at     TEXT NOT NULL,
    channel     TEXT NOT NULL DEFAULT 'telegram',
    message     TEXT NOT NULL,
    status      TEXT NOT NULL   -- 'sent' | 'failed'
);

CREATE INDEX IF NOT EXISTS idx_streak_date   ON streak_log(log_date);
CREATE INDEX IF NOT EXISTS idx_action_time   ON action_log(action_time);
CREATE INDEX IF NOT EXISTS idx_notif_sent_at ON notification_log(sent_at);
"""


# ── connection pool (thread-local) ────────────────────────────────────────────

_local = threading.local()


class Database:
    """Thread-safe SQLite wrapper using thread-local connections."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ── internal ──────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        if not hasattr(_local, "conn") or _local.conn is None:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            _local.conn = conn
        return _local.conn

    def _init_schema(self) -> None:
        with self.cursor() as cur:
            cur.executescript(SCHEMA_SQL)
        log.debug("Database schema initialised at %s", self.db_path)

    @contextmanager
    def cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        conn = self._connect()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    # ── streak_log ────────────────────────────────────────────────────────────

    def upsert_streak(
        self,
        service: str,
        had_activity: bool,
        auto_saved: bool = False,
        detail: str = "",
        log_date: Optional[date] = None,
    ) -> None:
        today = (log_date or date.today()).isoformat()
        now = datetime.now().isoformat(timespec="seconds")
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO streak_log (log_date, service, had_activity, auto_saved, checked_at, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(log_date, service) DO UPDATE SET
                    had_activity = excluded.had_activity,
                    auto_saved   = excluded.auto_saved,
                    checked_at   = excluded.checked_at,
                    detail       = excluded.detail
                """,
                (today, service, int(had_activity), int(auto_saved), now, detail),
            )

    def get_streak(self, service: str, log_date: Optional[date] = None) -> Optional[sqlite3.Row]:
        today = (log_date or date.today()).isoformat()
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM streak_log WHERE log_date=? AND service=?",
                (today, service),
            )
            return cur.fetchone()

    def get_recent_streaks(self, days: int = 30) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM streak_log
                ORDER BY log_date DESC, service
                LIMIT ?
                """,
                (days * 2,),
            )
            return cur.fetchall()

    # ── action_log ────────────────────────────────────────────────────────────

    def log_action(
        self,
        service: str,
        action_type: str,
        status: str,
        detail: str = "",
        error: str = "",
    ) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO action_log (action_time, service, action_type, status, detail, error)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now, service, action_type, status, detail, error),
            )
            return cur.lastrowid  # type: ignore[return-value]

    def get_recent_actions(self, limit: int = 50) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM action_log ORDER BY action_time DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    # ── notification_log ──────────────────────────────────────────────────────

    def log_notification(self, channel: str, message: str, status: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        with self.cursor() as cur:
            cur.execute(
                "INSERT INTO notification_log (sent_at, channel, message, status) VALUES (?,?,?,?)",
                (now, channel, message, status),
            )

    def get_recent_notifications(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.cursor() as cur:
            cur.execute(
                "SELECT * FROM notification_log ORDER BY sent_at DESC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()
