"""
notifications/telegram_notifier.py — Sends Telegram messages via Bot API.
"""

from __future__ import annotations

from typing import Optional

import httpx

from logger import get_logger

log = get_logger(__name__)

_TG_BASE = "https://api.telegram.org"


class TelegramNotifier:
    """Sends messages to a Telegram chat via a bot token."""

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._base_url = f"{_TG_BASE}/bot{bot_token}"

    # ── public ────────────────────────────────────────────────────────────────

    def send(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Send a text message.
        Returns True on success, False on failure (logs the error).
        """
        url = f"{self._base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                log.info("✅ Telegram notification sent (chat_id=%s)", self.chat_id)
                return True
        except Exception as exc:
            log.error("❌ Failed to send Telegram notification: %s", exc)
            return False

    def send_warning(self, github_ok: bool, leetcode_ok: bool) -> bool:
        """Send a warning notification about at-risk streaks."""
        if github_ok and leetcode_ok:
            return True  # Nothing to warn about

        at_risk = []
        if not github_ok:
            at_risk.append("GitHub")
        if not leetcode_ok:
            at_risk.append("LeetCode")

        services = " and ".join(at_risk)
        message = (
            "⚠️ <b>Streak Guardian Warning</b>\n\n"
            f"No <b>{services}</b> activity detected today.\n"
            "Automatic protection will run at 11:45 PM.\n\n"
            "⏰ <i>You still have time to do it manually!</i>"
        )
        return self.send(message)

    def send_success(self, actions: list[str]) -> bool:
        """Send a success notification after auto-save actions."""
        if not actions:
            return True
        action_list = "\n".join(f"  ✅ {a}" for a in actions)
        message = (
            "🛡️ <b>Streak Guardian — Streak Saved!</b>\n\n"
            "The following actions were taken automatically:\n"
            f"{action_list}\n\n"
            "Your streaks are safe for today! 🎉"
        )
        return self.send(message)

    def send_error(self, service: str, error_msg: str) -> bool:
        """Send an error alert."""
        message = (
            "🔴 <b>Streak Guardian Error</b>\n\n"
            f"Service: <b>{service}</b>\n"
            f"Error: <code>{error_msg[:300]}</code>\n\n"
            "⚠️ Manual intervention may be required!"
        )
        return self.send(message)

    def send_status_report(self, github_ok: bool, leetcode_ok: bool) -> bool:
        """Send a daily status report."""
        gh_icon = "✅" if github_ok else "❌"
        lc_icon = "✅" if leetcode_ok else "❌"
        all_ok = github_ok and leetcode_ok
        overall = "🟢 All streaks active!" if all_ok else "🔴 Streaks at risk!"

        message = (
            "📊 <b>Streak Guardian — Daily Status</b>\n\n"
            f"{gh_icon} GitHub commit: {'Active' if github_ok else 'Missing'}\n"
            f"{lc_icon} LeetCode submission: {'Active' if leetcode_ok else 'Missing'}\n\n"
            f"<b>{overall}</b>"
        )
        return self.send(message)

    def test_connection(self) -> bool:
        """Verify bot token and chat ID work correctly."""
        url = f"{self._base_url}/getMe"
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(url)
                resp.raise_for_status()
                bot_name = resp.json().get("result", {}).get("username", "unknown")
                log.info("Telegram bot verified: @%s", bot_name)
                return True
        except Exception as exc:
            log.error("Telegram bot verification failed: %s", exc)
            return False
