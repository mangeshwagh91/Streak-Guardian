"""
scheduler.py — APScheduler-based job runner for Streak Guardian.

Jobs:
  • warning_job  — 10:30 PM  (check + Telegram warning if at risk)
  • protection_job — 11:45 PM (auto-save streaks if needed)
"""

from __future__ import annotations

import traceback
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from config import settings
from database.db import Database
from github.github_checker import GitHubChecker
from github.github_committer import GitHubCommitter
from leetcode.leetcode_checker import LeetCodeChecker
from leetcode.leetcode_submitter import LeetCodeSubmitter
from notifications.telegram_notifier import TelegramNotifier
from logger import get_logger

log = get_logger(__name__)

# ── singleton DB ──────────────────────────────────────────────────────────────
db = Database(settings.app.database_path)


# ── job functions ─────────────────────────────────────────────────────────────

def _check_github() -> bool:
    """Returns True if GitHub has activity today."""
    checker = GitHubChecker(
        username=settings.github.username,
        token=settings.github.token,
    )
    return checker.has_commit_today()


def _check_leetcode() -> bool:
    """Returns True if LeetCode has activity today."""
    checker = LeetCodeChecker(username=settings.leetcode.username)
    return checker.has_submission_today()


def warning_job() -> None:
    """
    10:30 PM job — check activity and send Telegram warning if at risk.
    """
    log.info("═══ Running WARNING CHECK job ═══")

    github_ok = False
    leetcode_ok = False

    # ── GitHub check ──────────────────────────────────────────────────────────
    try:
        github_ok = _check_github()
        db.upsert_streak("github", had_activity=github_ok)
        db.log_action(
            service="github",
            action_type="check",
            status="success",
            detail=f"has_activity={github_ok}",
        )
    except Exception as exc:
        log.exception("GitHub check failed in warning job")
        db.log_action("github", "check", "failure", error=traceback.format_exc())

    # ── LeetCode check ────────────────────────────────────────────────────────
    try:
        leetcode_ok = _check_leetcode()
        db.upsert_streak("leetcode", had_activity=leetcode_ok)
        db.log_action(
            service="leetcode",
            action_type="check",
            status="success",
            detail=f"has_activity={leetcode_ok}",
        )
    except Exception as exc:
        log.exception("LeetCode check failed in warning job")
        db.log_action("leetcode", "check", "failure", error=traceback.format_exc())

    # ── Notification ──────────────────────────────────────────────────────────
    if not github_ok or not leetcode_ok:
        notifier = TelegramNotifier(
            bot_token=settings.telegram.bot_token,
            chat_id=settings.telegram.chat_id,
        )
        sent = notifier.send_warning(github_ok=github_ok, leetcode_ok=leetcode_ok)
        db.log_notification(
            channel="telegram",
            message=f"Warning: github_ok={github_ok}, leetcode_ok={leetcode_ok}",
            status="sent" if sent else "failed",
        )
    else:
        log.info("All streaks active — no warning needed")

    log.info("═══ WARNING CHECK job complete ═══")


def protection_job() -> None:
    """
    11:45 PM job — auto-save streaks if still missing.
    """
    log.info("═══ Running PROTECTION job ═══")
    actions_taken: list[str] = []

    # ── GitHub protection ─────────────────────────────────────────────────────
    try:
        github_ok = _check_github()
        if github_ok:
            log.info("GitHub: commit already exists — skipping")
            db.upsert_streak("github", had_activity=True)
            db.log_action("github", "check", "skipped", "commit already exists")
        else:
            log.info("GitHub: no commit found — creating one …")
            committer = GitHubCommitter(
                username=settings.github.username,
                token=settings.github.token,
                repo_owner=settings.github.repo_owner,
                repo_name=settings.github.repo_name,
                branch=settings.github.branch,
                email=settings.github.email,
            )
            committer.ensure_repo_exists()
            result = committer.commit_daily_log()

            db.upsert_streak("github", had_activity=True, auto_saved=True, detail=result["sha"][:12])
            db.log_action("github", "commit", "success", detail=result["commit_url"])
            actions_taken.append(f"GitHub commit pushed ({result['sha'][:8]})")
            log.info("GitHub streak saved ✅")

    except Exception as exc:
        log.exception("GitHub protection failed")
        db.log_action("github", "commit", "failure", error=traceback.format_exc())
        notifier = TelegramNotifier(settings.telegram.bot_token, settings.telegram.chat_id)
        notifier.send_error("GitHub", str(exc))

    # ── LeetCode protection ───────────────────────────────────────────────────
    try:
        leetcode_ok = _check_leetcode()
        if leetcode_ok:
            log.info("LeetCode: submission already exists — skipping")
            db.upsert_streak("leetcode", had_activity=True)
            db.log_action("leetcode", "check", "skipped", "submission already exists")
        else:
            log.info("LeetCode: no submission found — submitting solution …")

            # Load solution from solutions/ folder
            solution_file = (
                settings.app.solutions_dir / settings.leetcode.default_solution_file
            )
            if not solution_file.exists():
                raise FileNotFoundError(
                    f"Solution file not found: {solution_file}\n"
                    "Add your solution files to the solutions/ directory."
                )
            solution_code = solution_file.read_text(encoding="utf-8")

            submitter = LeetCodeSubmitter(
                username=settings.leetcode.username,
                session_cookie=settings.leetcode.session_cookie,
                csrf_token=settings.leetcode.csrf_token,
                screenshots_dir=settings.app.screenshots_dir,
                language_id=settings.leetcode.language_id,
            )
            result = submitter.submit(
                problem_slug=settings.leetcode.default_problem_slug,
                solution_code=solution_code,
            )

            # success=True OR status='submitted'/'timeout' both mean the submit was sent
            submission_sent = result.get("success") or result.get("status") in ("submitted", "timeout")
            if submission_sent:
                db.upsert_streak("leetcode", had_activity=True, auto_saved=True,
                                 detail=result.get("status", ""))
                db.log_action("leetcode", "submit", "success",
                              detail=f"status={result.get('status')}, screenshot={result.get('screenshot_path')}")
                actions_taken.append(
                    f"LeetCode solution submitted ({settings.leetcode.default_problem_slug} — {result.get('status')})"
                )
                log.info("LeetCode streak saved ✅")
            else:
                raise RuntimeError(f"Submission failed: {result.get('status')}")

    except Exception as exc:
        log.exception("LeetCode protection failed")
        db.log_action("leetcode", "submit", "failure", error=traceback.format_exc())
        notifier = TelegramNotifier(settings.telegram.bot_token, settings.telegram.chat_id)
        notifier.send_error("LeetCode", str(exc))

    # ── Success notification ──────────────────────────────────────────────────
    if actions_taken:
        notifier = TelegramNotifier(settings.telegram.bot_token, settings.telegram.chat_id)
        sent = notifier.send_success(actions_taken)
        db.log_notification(
            channel="telegram",
            message="Streak saved: " + ", ".join(actions_taken),
            status="sent" if sent else "failed",
        )

    log.info("═══ PROTECTION job complete ═══")


# ── scheduler setup ───────────────────────────────────────────────────────────

def build_scheduler() -> BlockingScheduler:
    """Build and configure the APScheduler instance."""
    tz = settings.app.timezone

    # Parse "HH:MM" times
    warn_h, warn_m = settings.app.warning_check_time.split(":")
    prot_h, prot_m = settings.app.protection_run_time.split(":")

    scheduler = BlockingScheduler(timezone=tz)

    scheduler.add_job(
        warning_job,
        trigger=CronTrigger(hour=int(warn_h), minute=int(warn_m), timezone=tz),
        id="warning_job",
        name="10:30 PM warning check",
        max_instances=1,
        misfire_grace_time=300,
        replace_existing=True,
    )

    scheduler.add_job(
        protection_job,
        trigger=CronTrigger(hour=int(prot_h), minute=int(prot_m), timezone=tz),
        id="protection_job",
        name="11:45 PM streak protection",
        max_instances=1,
        misfire_grace_time=300,
        replace_existing=True,
    )

    log.info(
        "Scheduler configured — warning=%s, protection=%s (tz=%s)",
        settings.app.warning_check_time,
        settings.app.protection_run_time,
        str(tz),
    )
    return scheduler


def run_scheduler() -> None:
    """Start the blocking scheduler (blocks until interrupted)."""
    scheduler = build_scheduler()
    log.info("Starting Streak Guardian scheduler …")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped by user")
