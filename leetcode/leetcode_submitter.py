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
        session_cookie: str,
        csrf_token: str,
        screenshots_dir: Path,
        language_id: int = 71,  # 71 = python3
    ) -> None:
        self.username = username
        self.session_cookie = session_cookie
        self.csrf_token = csrf_token
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
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )

            # Inject session cookies — skips login page entirely
            await context.add_cookies([
                {
                    "name": "LEETCODE_SESSION",
                    "value": self.session_cookie,
                    "domain": ".leetcode.com",
                    "path": "/",
                    "httpOnly": True,
                    "secure": True,
                },
                {
                    "name": "csrftoken",
                    "value": self.csrf_token,
                    "domain": ".leetcode.com",
                    "path": "/",
                    "httpOnly": False,
                    "secure": False,
                },
            ])
            log.info("Session cookies injected — skipping login page")

            page = await context.new_page()

            try:
                # ── Step 1: Verify cookie session ──────────────────────────
                log.info("Verifying LeetCode session via cookies …")
                await page.goto("https://leetcode.com/", wait_until="load", timeout=60_000)
                await page.wait_for_timeout(2000)

                # If cookies are invalid, LeetCode redirects to /accounts/login/
                if "login" in page.url or "accounts" in page.url:
                    log.warning("Session cookie expired — redirected to login page")
                    ss = self._screenshot_path("session_expired")
                    await page.screenshot(path=str(ss), full_page=False)
                    result["screenshot_path"] = str(ss)
                    result["status"] = "session_expired"
                    return result

                log.info("Session valid — logged in as %s", self.username)

                # ── Step 2: Navigate to problem ───────────────────────────
                problem_url = f"{_LC_BASE}/problems/{problem_slug}/"
                log.info("Navigating to problem: %s", problem_url)
                await page.goto(problem_url, wait_until="load", timeout=60_000)
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
                result["success"] = verdict in (
                    "Accepted", "Wrong Answer", "Runtime Error",
                    "Compile Error", "Time Limit Exceeded", "Memory Limit Exceeded"
                )
                # ANY verdict = submission happened = streak saved

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
        """Switch the editor language using the dropdown in the new LeetCode UI."""
        lang_map = {71: "Python3", 54: "C++", 62: "Java", 91: "JavaScript", 92: "TypeScript"}
        target_lang = lang_map.get(self.language_id, "Python3")
        try:
            await page.wait_for_timeout(1000)

            # The language button in new LeetCode shows current lang e.g. "C++ ▾" or "Python3 ▾"
            # Find any button that looks like a language selector
            lang_btn = None
            for selector in [
                "[data-cy='lang-select']",
                "button.ant-btn:has-text('C++')",
                "button.ant-btn:has-text('Python')",
                "button.ant-btn:has-text('Java')",
                ".ant-select-selector",
            ]:
                el = page.locator(selector).first
                if await el.count() > 0:
                    lang_btn = el
                    break

            # Also try: look for any button near the top of the editor area
            if lang_btn is None:
                # Try finding by current language text in top toolbar
                for lang_name in ["C++", "Python3", "Java", "JavaScript", "TypeScript"]:
                    el = page.locator(f"button:has-text('{lang_name}')").first
                    if await el.count() > 0:
                        lang_btn = el
                        break

            if lang_btn is None:
                log.warning("Language dropdown not found — code will be submitted in current language")
                return

            current_text = (await lang_btn.inner_text()).strip()
            if target_lang in current_text:
                log.info("Language already set to %s", target_lang)
                return

            log.info("Switching language from '%s' to %s", current_text, target_lang)
            await lang_btn.click()
            await page.wait_for_timeout(1000)

            # Click the target language option in the dropdown list
            option = page.get_by_text(target_lang, exact=True).first
            if await option.count() > 0:
                await option.click()
                await page.wait_for_timeout(2000)  # wait for editor to reload with new lang
                log.info("Language switched to %s", target_lang)
            else:
                log.warning("Could not find '%s' in language dropdown", target_lang)
        except Exception as exc:
            log.warning("Could not set language: %s", exc)

    async def _inject_code(self, page, code: str) -> None:
        """Inject code into the Monaco editor on the new LeetCode UI."""
        escaped = json.dumps(code)

        # Wait for Monaco editor to fully initialise (new LeetCode can be slow)
        await page.wait_for_timeout(3000)

        injected = await page.evaluate(
            f"""() => {{
                // New LeetCode: Monaco is accessible via window.monaco
                try {{
                    const editor = window.monaco?.editor;
                    if (editor) {{
                        const models = editor.getModels();
                        if (models && models.length > 0) {{
                            models[0].setValue({escaped});
                            return "monaco-models";
                        }}
                        // Try getting focused editor
                        const active = editor.getFocusedCodeEditor() || editor.getEditors()?.[0];
                        if (active) {{
                            active.getModel()?.setValue({escaped});
                            return "monaco-focused";
                        }}
                    }}
                }} catch(e) {{ console.error('Monaco inject error:', e); }}

                // CodeMirror 5 fallback
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
            log.warning("Editor injection via JS failed — using keyboard fallback")
            # New LeetCode: the editor view is inside .view-lines or .monaco-editor
            for editor_sel in [
                ".view-lines",
                ".monaco-editor .inputarea",
                ".monaco-editor",
            ]:
                editor = page.locator(editor_sel).first
                if await editor.count() > 0:
                    await editor.click()
                    await page.wait_for_timeout(300)
                    # Select all existing code and replace
                    await page.keyboard.press("Control+a")
                    await page.wait_for_timeout(200)
                    await page.keyboard.type(code, delay=10)
                    log.info("Code injected via keyboard fallback (%s)", editor_sel)
                    return
            raise RuntimeError("Could not find editor on page")

        log.info("Code injected via: %s", injected)

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

    async def _wait_for_verdict(self, page, timeout_ms: int = 60_000) -> str:
        """Wait for the submission result panel in the new LeetCode UI."""
        from playwright.async_api import TimeoutError as PwTimeout

        # New LeetCode shows result in left panel tab (e.g. "Compile Error" tab appears)
        # Also navigates to a submissions URL sometimes
        verdicts = [
            "Accepted", "Wrong Answer", "Runtime Error",
            "Time Limit Exceeded", "Memory Limit Exceeded",
            "Compile Error", "Output Limit Exceeded",
        ]

        # Wait up to timeout polling for a verdict in page content
        import time
        start = time.time()
        while (time.time() - start) < (timeout_ms / 1000):
            await page.wait_for_timeout(2000)
            try:
                content = await page.content()
                for verdict in verdicts:
                    if verdict in content:
                        log.info("Verdict detected: %s", verdict)
                        return verdict
            except Exception:
                pass

        log.warning("Verdict not detected within %ds", timeout_ms // 1000)
        return "submitted"  # assume submitted even if we can't read verdict

    def _screenshot_path(self, label: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.screenshots_dir / f"{ts}_{label}.png"
