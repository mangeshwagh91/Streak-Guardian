#!/usr/bin/env python3
"""
main.py — Entry point for Streak Guardian.

Usage:
    python main.py                  # Scheduler + dashboard (default)
    python main.py --scheduler-only # Scheduler only
    python main.py --dashboard-only # Dashboard only
    python main.py --check-now      # One-shot check and exit
    python main.py --save-now       # One-shot protection and exit
    python main.py --test-notify    # Test Telegram notification and exit
    python main.py --setup          # Interactive first-time setup helper
"""

from __future__ import annotations

import argparse
import sys
import threading

from logger import get_logger

log = get_logger(__name__)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="🛡️ Streak Guardian — Automated streak protection for GitHub & LeetCode",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--scheduler-only", action="store_true", help="Run the scheduler only (no dashboard)")
    group.add_argument("--dashboard-only", action="store_true", help="Run the dashboard only (no scheduler)")
    group.add_argument("--check-now", action="store_true", help="Check streak status now and exit")
    group.add_argument("--save-now", action="store_true", help="Run protection job now and exit")
    group.add_argument("--test-notify", action="store_true", help="Send a test Telegram notification and exit")
    group.add_argument("--setup", action="store_true", help="Run first-time setup helper")
    return parser.parse_args()


# ── mode handlers ─────────────────────────────────────────────────────────────

def run_check_now() -> None:
    from config import settings
    from github.github_checker import GitHubChecker
    from leetcode.leetcode_checker import LeetCodeChecker

    log.info("Running one-shot status check …")

    checker = GitHubChecker(settings.github.username, settings.github.token)
    gh_ok = checker.has_commit_today()
    log.info("GitHub:   %s", "✅ Active" if gh_ok else "❌ No commit today")

    checker = LeetCodeChecker(settings.leetcode.username)
    lc_ok = checker.has_submission_today()
    log.info("LeetCode: %s", "✅ Active" if lc_ok else "❌ No submission today")

    if gh_ok and lc_ok:
        log.info("🎉 All streaks are safe!")
    else:
        log.warning("⚠️  Some streaks are at risk!")
    sys.exit(0 if (gh_ok and lc_ok) else 1)


def run_save_now() -> None:
    from scheduler import protection_job
    log.info("Running one-shot protection job …")
    protection_job()
    log.info("Protection job complete.")
    sys.exit(0)


def run_test_notify() -> None:
    from config import settings
    from notifications.telegram_notifier import TelegramNotifier

    log.info("Testing Telegram connection …")
    notifier = TelegramNotifier(settings.telegram.bot_token, settings.telegram.chat_id)
    if notifier.test_connection():
        ok = notifier.send(
            "🛡️ <b>Streak Guardian</b> — Test notification\n\n"
            "If you see this, Telegram notifications are working correctly! ✅"
        )
        sys.exit(0 if ok else 1)
    else:
        log.error("Telegram bot verification failed")
        sys.exit(1)


def run_setup() -> None:
    """Interactive first-time setup helper."""
    print("\n" + "═" * 60)
    print("  🛡️  Streak Guardian — First-Time Setup")
    print("═" * 60 + "\n")

    from pathlib import Path
    env_example = Path(__file__).parent / ".env.example"
    env_file = Path(__file__).parent / ".env"

    if env_file.exists():
        print("✅ .env file already exists.")
    else:
        import shutil
        shutil.copy(env_example, env_file)
        print("✅ Created .env from .env.example")

    print("\nSteps to complete setup:")
    print("  1. Open .env and fill in all values")
    print("  2. Add your solution files to solutions/")
    print("  3. Run: python main.py --test-notify")
    print("  4. Run: python main.py --check-now")
    print("  5. Run: python main.py  (to start the full system)\n")

    from pathlib import Path
    solutions_dir = Path(__file__).parent / "solutions"
    solutions_dir.mkdir(exist_ok=True)

    example_py = solutions_dir / "problem1.py"
    if not example_py.exists():
        example_py.write_text(
            "# Two Sum — LeetCode Problem 1\n"
            "# This is the default fallback solution used by Streak Guardian\n\n"
            "class Solution:\n"
            "    def twoSum(self, nums, target):\n"
            "        seen = {}\n"
            "        for i, n in enumerate(nums):\n"
            "            if target - n in seen:\n"
            "                return [seen[target - n], i]\n"
            "            seen[n] = i\n",
            encoding="utf-8",
        )
        print("✅ Created solutions/problem1.py (Two Sum default)")

    example_cpp = solutions_dir / "problem1.cpp"
    if not example_cpp.exists():
        example_cpp.write_text(
            "// Two Sum — LeetCode Problem 1\n"
            "#include <vector>\n"
            "#include <unordered_map>\n"
            "using namespace std;\n\n"
            "class Solution {\n"
            "public:\n"
            "    vector<int> twoSum(vector<int>& nums, int target) {\n"
            "        unordered_map<int,int> seen;\n"
            "        for (int i = 0; i < nums.size(); i++) {\n"
            "            if (seen.count(target - nums[i]))\n"
            "                return {seen[target - nums[i]], i};\n"
            "            seen[nums[i]] = i;\n"
            "        }\n"
            "        return {};\n"
            "    }\n"
            "};\n",
            encoding="utf-8",
        )
        print("✅ Created solutions/problem1.cpp (Two Sum C++ default)")

    print("\n🚀 Setup complete! Edit .env and start with: python main.py\n")
    sys.exit(0)


def run_dashboard(host: str = "0.0.0.0") -> None:
    import uvicorn
    from config import settings
    uvicorn.run(
        "app:app",
        host=host,
        port=settings.app.dashboard_port,
        log_level="warning",
        reload=False,
    )


def run_scheduler_thread() -> threading.Thread:
    from scheduler import run_scheduler
    t = threading.Thread(target=run_scheduler, daemon=True, name="StreakScheduler")
    t.start()
    return t


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # Banner
    log.info("━" * 60)
    log.info("  🛡️  Streak Guardian v1.0.0  starting up")
    log.info("━" * 60)

    if args.check_now:
        run_check_now()
    elif args.save_now:
        run_save_now()
    elif args.test_notify:
        run_test_notify()
    elif args.setup:
        run_setup()
    elif args.scheduler_only:
        from scheduler import run_scheduler
        log.info("Mode: Scheduler only")
        run_scheduler()
    elif args.dashboard_only:
        log.info("Mode: Dashboard only")
        run_dashboard()
    else:
        # Default: run both scheduler and dashboard
        log.info("Mode: Scheduler + Dashboard")
        t = run_scheduler_thread()
        log.info("Scheduler started in background thread")
        try:
            run_dashboard()
        except KeyboardInterrupt:
            log.info("Shutting down …")


if __name__ == "__main__":
    main()
