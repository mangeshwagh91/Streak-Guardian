"""
leetcode/leetcode_submitter.py — Submits a LeetCode solution using Playwright.

Flow:
  1. Launch headless Chromium.
  2. Navigate to the problem page.
  3. Log in (cookie-based session reuse where possible).
  4. Paste the solution code into the Monaco editor.
  5. Click Submit and wait for the result.
  6. Save a screenshot.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from logger import get_logger

log = get_logger(__name__)

_LC_BASE = "https://leetcode.com"


class LeetCodeSubmitter:
    """Automates LeetCode problem submission with Playwright."""

    def __init__(
        self,
        username: str,
        password: str,
        screenshots_dir: Path,
        language_id: int = 71,  # 71 = python3
    ) -> None:
        self.username = username
        self.password = password
        self.screenshots_dir = screenshots_dir
        self.language_id = language_id
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    # ── public entry point ────────────────────────────────────────────────────

    def submit(self, problem_slug: str, solution_code: str) -> dict:
        """
        Synchronous wrapper around the async implementation.

        Returns dict with keys: success, status, submission_id, screenshot_path.
        """
        return asyncio.run(self._submit_async(problem_slug, solution_code))

    # ── async core ────────────────────────────────────────────────────────────

    async def _submit_async(self, problem_slug: str, solution_code: str) -> dict:
        from playwright.async_api import async_playwright, TimeoutError as PwTimeout

        result = {
            "success": False,
            "status": "unknown",
            "submission_id": None,
            "screenshot_path": None,
        }

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
            )

            page = await context.new_page()

            try:
                # ── Step 1: Login ──────────────────────────────────────────
                log.info("Navigating to LeetCode login page …")
                await page.goto(f"{_LC_BASE}/accounts/login/", wait_until="networkidle", timeout=30_000)
                await page.wait_for_timeout(2000)

                await page.fill("#id_login", self.username)
                await page.fill("#id_password", self.password)

                # Bypass reCAPTCHA — take screenshot for manual inspection if it appears
                await page.click("#signin_btn")
                await page.wait_for_timeout(4000)

                # Check login success
                current_url = page.url
                if "login" in current_url or "accounts" in current_url:
                    # Try alternate selector patterns
                    try:
                        await page.wait_for_selector(".username", timeout=5000)
                    except PwTimeout:
                        log.warning("Login may have failed — CAPTCHA or invalid credentials?")
                        ss = self._screenshot_path("login_failed")
                        await page.screenshot(path=str(ss), full_page=True)
                        result["screenshot_path"] = str(ss)
                        result["status"] = "login_failed"
                        return result

                log.info("✅ Logged in to LeetCode")

                # ── Step 2: Navigate to problem ───────────────────────────
                problem_url = f"{_LC_BASE}/problems/{problem_slug}/"
                log.info("Navigating to problem: %s", problem_url)
                await page.goto(problem_url, wait_until="networkidle", timeout=30_000)
                await page.wait_for_timeout(3000)

                # ── Step 3: Set language if needed ────────────────────────
                await self._set_language(page)

                # ── Step 4: Paste solution ────────────────────────────────
                log.info("Injecting solution code …")
                await self._inject_code(page, solution_code)
                await page.wait_for_timeout(1500)

                # ── Step 5: Screenshot before submit ──────────────────────
                ss_before = self._screenshot_path(f"{problem_slug}_before_submit")
                await page.screenshot(path=str(ss_before), full_page=False)
                log.info("Screenshot saved: %s", ss_before)

                # ── Step 6: Submit ────────────────────────────────────────
                log.info("Clicking Submit button …")
                await self._click_submit(page)

                # ── Step 7: Wait for result ───────────────────────────────
                verdict = await self._wait_for_verdict(page)
                result["status"] = verdict
                result["success"] = verdict in ("Accepted", "Wrong Answer", "Runtime Error")
                # Any result (even WA/RE) counts as a submission → streak saved

                # ── Step 8: Screenshot after result ──────────────────────
                ss_after = self._screenshot_path(f"{problem_slug}_result")
                await page.screenshot(path=str(ss_after), full_page=False)
                result["screenshot_path"] = str(ss_after)
                log.info("Submission result: %s — screenshot: %s", verdict, ss_after)

            except Exception as exc:
                log.exception("Playwright submission error: %s", exc)
                try:
                    ss_err = self._screenshot_path("error")
                    await page.screenshot(path=str(ss_err), full_page=True)
                    result["screenshot_path"] = str(ss_err)
                except Exception:
                    pass
                result["status"] = f"error: {exc}"
            finally:
                await context.close()
                await browser.close()

        return result

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _set_language(self, page) -> None:
        """Click the language dropdown and select the desired language."""
        try:
            # LeetCode's language button shows the current language text
            lang_map = {71: "Python3", 54: "C++", 62: "Java", 91: "JavaScript", 92: "TypeScript"}
            target_lang = lang_map.get(self.language_id, "Python3")

            # Try to find and click the language dropdown
            lang_btn = page.locator("[data-cy='lang-select']").first
            if await lang_btn.count() > 0:
                await lang_btn.click()
                await page.wait_for_timeout(500)
                # Click the language option
                option = page.get_by_text(target_lang, exact=True).first
                if await option.count() > 0:
                    await option.click()
                    await page.wait_for_timeout(1000)
                    log.info("Language set to %s", target_lang)
            else:
                log.debug("Language dropdown not found — skipping language selection")
        except Exception as exc:
            log.warning("Could not set language: %s", exc)

    async def _inject_code(self, page, code: str) -> None:
        """Inject code into the Monaco / CodeMirror editor."""
        # Escape code for JavaScript injection
        escaped = json.dumps(code)

        injected = await page.evaluate(
            f"""() => {{
                // Monaco editor
                try {{
                    const models = window.monaco?.editor?.getModels();
                    if (models && models.length > 0) {{
                        models[0].setValue({escaped});
                        return "monaco";
                    }}
                }} catch(e) {{}}

                // CodeMirror 5
                try {{
                    const cm = document.querySelector('.CodeMirror')?.CodeMirror;
                    if (cm) {{
                        cm.setValue({escaped});
                        return "codemirror5";
                    }}
                }} catch(e) {{}}

                return null;
            }}"""
        )

        if not injected:
            # Fallback: select-all + type
            log.warning("Editor injection via JS failed — using keyboard fallback")
            editor = page.locator(".monaco-editor").first
            if await editor.count() > 0:
                await editor.click()
                await page.keyboard.press("Control+a")
                await page.keyboard.type(code, delay=5)
            else:
                raise RuntimeError("Could not find editor on page")

        log.debug("Code injected via: %s", injected)

    async def _click_submit(self, page) -> None:
        """Click the submit button."""
        selectors = [
            "button[data-cy='submit-code-btn']",
            "button:has-text('Submit')",
            "[data-testid='submit-code-btn']",
        ]
        for sel in selectors:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click()
                return
        raise RuntimeError("Submit button not found on page")

    async def _wait_for_verdict(self, page, timeout_ms: int = 30_000) -> str:
        """Wait for the submission result panel."""
        from playwright.async_api import TimeoutError as PwTimeout
        verdict_selectors = [
            "[data-e2e-locator='submission-result']",
            ".result-container",
            ":has-text('Accepted')",
            ":has-text('Wrong Answer')",
            ":has-text('Runtime Error')",
            ":has-text('Time Limit Exceeded')",
        ]
        try:
            await page.wait_for_selector(
                ", ".join(verdict_selectors[:2]),
                timeout=timeout_ms,
            )
        except PwTimeout:
            log.warning("Verdict panel did not appear within %ds", timeout_ms // 1000)
            return "timeout"

        await page.wait_for_timeout(1000)
        content = await page.content()

        for verdict in ["Accepted", "Wrong Answer", "Runtime Error",
                        "Time Limit Exceeded", "Memory Limit Exceeded",
                        "Compilation Error"]:
            if verdict in content:
                return verdict
        return "submitted"

    def _screenshot_path(self, label: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.screenshots_dir / f"{ts}_{label}.png"
