"""
app.py — FastAPI admin dashboard for Streak Guardian.

Endpoints:
  GET  /              — Dashboard HTML page
  GET  /api/status    — Current streak status (JSON)
  GET  /api/logs      — Recent action logs (JSON)
  GET  /api/streaks   — Recent streak history (JSON)
  GET  /api/notifications — Recent notifications (JSON)
  POST /api/save-now  — Manually trigger protection job
  POST /api/check-now — Run check only (no auto-save)
  GET  /health        — Health check
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from database.db import Database
from github.github_checker import GitHubChecker
from leetcode.leetcode_checker import LeetCodeChecker
from logger import get_logger
import scheduler as sched_module

log = get_logger(__name__)

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Streak Guardian Dashboard",
    description="Admin dashboard for monitoring and controlling GitHub & LeetCode streak protection.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db = Database(settings.app.database_path)


# ── utility ───────────────────────────────────────────────────────────────────

def _row_to_dict(row) -> dict:
    if row is None:
        return {}
    return dict(row)


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ── API routes ────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/api/status")
def api_status():
    github_row = _row_to_dict(db.get_streak("github"))
    lc_row = _row_to_dict(db.get_streak("leetcode"))

    github_ok = bool(github_row.get("had_activity", False))
    leetcode_ok = bool(lc_row.get("had_activity", False))

    return {
        "date": datetime.now().date().isoformat(),
        "timestamp": datetime.now().isoformat(),
        "github": {
            "active": github_ok,
            "auto_saved": bool(github_row.get("auto_saved", False)),
            "checked_at": github_row.get("checked_at"),
            "detail": github_row.get("detail"),
        },
        "leetcode": {
            "active": leetcode_ok,
            "auto_saved": bool(lc_row.get("auto_saved", False)),
            "checked_at": lc_row.get("checked_at"),
            "detail": lc_row.get("detail"),
        },
        "all_safe": github_ok and leetcode_ok,
    }


@app.get("/api/logs")
def api_logs(limit: int = 50):
    rows = db.get_recent_actions(limit=min(limit, 200))
    return {"actions": _rows_to_list(rows)}


@app.get("/api/streaks")
def api_streaks(days: int = 30):
    rows = db.get_recent_streaks(days=min(days, 90))
    return {"streaks": _rows_to_list(rows)}


@app.get("/api/notifications")
def api_notifications(limit: int = 20):
    rows = db.get_recent_notifications(limit=min(limit, 100))
    return {"notifications": _rows_to_list(rows)}


@app.post("/api/check-now")
def api_check_now():
    """Run a live status check without auto-saving."""
    log.info("Manual check triggered from dashboard")
    result: dict[str, Any] = {}

    try:
        checker = GitHubChecker(settings.github.username, settings.github.token)
        github_ok = checker.has_commit_today()
        db.upsert_streak("github", had_activity=github_ok)
        db.log_action("github", "check", "success", detail=f"manual check — has_activity={github_ok}")
        result["github"] = {"active": github_ok}
    except Exception as exc:
        result["github"] = {"error": str(exc)}
        db.log_action("github", "check", "failure", error=traceback.format_exc())

    try:
        checker = LeetCodeChecker(settings.leetcode.username)
        lc_ok = checker.has_submission_today()
        db.upsert_streak("leetcode", had_activity=lc_ok)
        db.log_action("leetcode", "check", "success", detail=f"manual check — has_activity={lc_ok}")
        result["leetcode"] = {"active": lc_ok}
    except Exception as exc:
        result["leetcode"] = {"error": str(exc)}
        db.log_action("leetcode", "check", "failure", error=traceback.format_exc())

    return result


@app.post("/api/save-now")
def api_save_now():
    """Manually trigger the protection job in a background thread."""
    log.info("Manual 'Save Now' triggered from dashboard")

    def _run():
        try:
            sched_module.protection_job()
        except Exception:
            log.exception("Manual protection job failed")

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return {
        "status": "started",
        "message": "Protection job is running in the background. Check logs for results.",
    }


# ── Dashboard HTML ────────────────────────────────────────────────────────────

_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Streak Guardian — Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d2e; --surface2: #252840;
    --accent: #6c63ff; --accent2: #ff6584; --green: #4ade80;
    --red: #f87171; --yellow: #fbbf24; --text: #e2e8f0;
    --text-muted: #94a3b8; --border: rgba(255,255,255,0.08);
    --radius: 12px; --glow: 0 0 20px rgba(108,99,255,0.3);
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Inter', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  /* Header */
  .header { background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 1.25rem 2rem; display: flex; align-items: center; justify-content: space-between;
    position: sticky; top: 0; z-index: 100; backdrop-filter: blur(10px); }
  .header h1 { font-size: 1.4rem; font-weight: 700; background: linear-gradient(135deg, var(--accent), var(--accent2));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .header .timestamp { font-size: 0.8rem; color: var(--text-muted); }

  /* Layout */
  .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  .grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5rem; }

  /* Cards */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 1.5rem; transition: transform 0.2s, box-shadow 0.2s; }
  .card:hover { transform: translateY(-2px); box-shadow: var(--glow); }
  .card-title { font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--text-muted); margin-bottom: 1rem; }

  /* Status cards */
  .status-card { position: relative; overflow: hidden; }
  .status-card .glow-bg { position: absolute; top: -50%; right: -50%;
    width: 150px; height: 150px; border-radius: 50%; filter: blur(40px); opacity: 0.15; }
  .status-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
  .status-name { font-size: 1.1rem; font-weight: 600; margin-bottom: 0.5rem; }
  .status-badge { display: inline-flex; align-items: center; gap: 0.4rem;
    padding: 0.3rem 0.75rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }
  .badge-ok { background: rgba(74, 222, 128, 0.15); color: var(--green); border: 1px solid rgba(74,222,128,0.3); }
  .badge-fail { background: rgba(248, 113, 113, 0.15); color: var(--red); border: 1px solid rgba(248,113,113,0.3); }
  .badge-auto { background: rgba(251, 191, 36, 0.15); color: var(--yellow); border: 1px solid rgba(251,191,36,0.3); margin-left: 0.5rem; }
  .status-meta { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.75rem; }

  /* Action buttons */
  .actions { display: flex; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .btn { padding: 0.6rem 1.4rem; border: none; border-radius: 8px; font-size: 0.875rem;
    font-weight: 600; cursor: pointer; transition: all 0.2s; font-family: inherit; }
  .btn-primary { background: var(--accent); color: white; }
  .btn-primary:hover { background: #5a52d5; box-shadow: 0 0 15px rgba(108,99,255,0.5); }
  .btn-success { background: rgba(74,222,128,0.2); color: var(--green); border: 1px solid rgba(74,222,128,0.4); }
  .btn-success:hover { background: rgba(74,222,128,0.35); }
  .btn-danger { background: rgba(248,113,113,0.2); color: var(--red); border: 1px solid rgba(248,113,113,0.4); }
  .btn-danger:hover { background: rgba(248,113,113,0.35); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* Log table */
  .log-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
  .log-table th { color: var(--text-muted); font-weight: 500; text-align: left;
    padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
  .log-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid rgba(255,255,255,0.04); }
  .log-table tr:last-child td { border-bottom: none; }
  .tag { padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }
  .tag-success { background: rgba(74,222,128,0.15); color: var(--green); }
  .tag-failure { background: rgba(248,113,113,0.15); color: var(--red); }
  .tag-skipped { background: rgba(148,163,184,0.15); color: var(--text-muted); }
  .tag-github { background: rgba(108,99,255,0.15); color: var(--accent); }
  .tag-leetcode { background: rgba(255,101,132,0.15); color: var(--accent2); }

  /* Toast */
  .toast { position: fixed; bottom: 2rem; right: 2rem; background: var(--surface2);
    border: 1px solid var(--border); border-radius: var(--radius); padding: 1rem 1.5rem;
    font-size: 0.875rem; z-index: 9999; transform: translateY(100px); opacity: 0;
    transition: all 0.3s; max-width: 350px; }
  .toast.show { transform: translateY(0); opacity: 1; }
  .toast.success { border-color: rgba(74,222,128,0.4); }
  .toast.error { border-color: rgba(248,113,113,0.4); }

  /* Loading spinner */
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid transparent;
    border-top-color: currentColor; border-radius: 50%; animation: spin 0.7s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }

  /* Responsive */
  @media (max-width: 768px) {
    .grid-2, .grid-3 { grid-template-columns: 1fr; }
    .container { padding: 1rem; }
  }
  .section-title { font-size: 1rem; font-weight: 600; margin-bottom: 1rem; color: var(--text); }
  .empty-state { text-align: center; color: var(--text-muted); padding: 2rem; font-size: 0.875rem; }
  .pulse { animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
  .divider { height: 1px; background: var(--border); margin: 1.5rem 0; }
</style>
</head>
<body>

<div class="header">
  <h1>🛡️ Streak Guardian</h1>
  <span class="timestamp" id="current-time">Loading…</span>
</div>

<div class="container">

  <!-- Action buttons -->
  <div class="actions" style="margin-top: 1.5rem;">
    <button class="btn btn-primary" onclick="checkNow(this)">🔍 Check Now</button>
    <button class="btn btn-success" onclick="saveNow(this)">⚡ Save Streak Now</button>
    <button class="btn" style="background:var(--surface2);color:var(--text-muted);" onclick="loadAll()">🔄 Refresh</button>
  </div>

  <!-- Status cards -->
  <div class="grid-2" style="margin-bottom: 1.5rem;">
    <div class="card status-card" id="github-card">
      <div class="glow-bg" style="background: #6c63ff;" id="github-glow"></div>
      <div class="card-title">GitHub Streak</div>
      <div class="status-icon">🐙</div>
      <div class="status-name">GitHub Commits</div>
      <div id="github-status"><span class="status-badge badge-fail pulse">⏳ Loading…</span></div>
      <div class="status-meta" id="github-meta"></div>
    </div>
    <div class="card status-card" id="leetcode-card">
      <div class="glow-bg" style="background: #ff6584;" id="lc-glow"></div>
      <div class="card-title">LeetCode Streak</div>
      <div class="status-icon">🧩</div>
      <div class="status-name">LeetCode Submissions</div>
      <div id="lc-status"><span class="status-badge badge-fail pulse">⏳ Loading…</span></div>
      <div class="status-meta" id="lc-meta"></div>
    </div>
  </div>

  <div class="divider"></div>

  <!-- Action log + Notifications -->
  <div class="grid-2">
    <div class="card">
      <div class="section-title">📋 Recent Actions</div>
      <div id="actions-table"><div class="empty-state">Loading…</div></div>
    </div>
    <div class="card">
      <div class="section-title">🔔 Notifications</div>
      <div id="notif-table"><div class="empty-state">Loading…</div></div>
    </div>
  </div>

  <div class="divider"></div>

  <!-- Streak history -->
  <div class="card">
    <div class="section-title">📅 Streak History (Last 30 Days)</div>
    <div id="streak-table"><div class="empty-state">Loading…</div></div>
  </div>

</div>

<!-- Toast notification -->
<div class="toast" id="toast"></div>

<script>
  // ── helpers ────────────────────────────────────────────────────────────────
  function showToast(msg, type='success') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `toast show ${type}`;
    setTimeout(() => t.className = 'toast', 3500);
  }

  async function apiFetch(url, method='GET') {
    const resp = await fetch(url, { method });
    if (!resp.ok) throw new Error(await resp.text());
    return resp.json();
  }

  function tag(cls, text) {
    return `<span class="tag ${cls}">${text}</span>`;
  }

  // ── Status ─────────────────────────────────────────────────────────────────
  async function loadStatus() {
    try {
      const d = await apiFetch('/api/status');

      // GitHub
      const ghOk = d.github.active;
      const ghAuto = d.github.auto_saved;
      document.getElementById('github-status').innerHTML =
        `<span class="status-badge ${ghOk ? 'badge-ok' : 'badge-fail'}">${ghOk ? '✅ Active' : '❌ Missing'}</span>`
        + (ghAuto ? '<span class="status-badge badge-auto">🤖 Auto-saved</span>' : '');
      document.getElementById('github-meta').textContent =
        d.github.checked_at ? `Last checked: ${d.github.checked_at}` : 'Not checked yet today';
      document.getElementById('github-glow').style.background = ghOk ? '#4ade80' : '#f87171';

      // LeetCode
      const lcOk = d.leetcode.active;
      const lcAuto = d.leetcode.auto_saved;
      document.getElementById('lc-status').innerHTML =
        `<span class="status-badge ${lcOk ? 'badge-ok' : 'badge-fail'}">${lcOk ? '✅ Active' : '❌ Missing'}</span>`
        + (lcAuto ? '<span class="status-badge badge-auto">🤖 Auto-saved</span>' : '');
      document.getElementById('lc-meta').textContent =
        d.leetcode.checked_at ? `Last checked: ${d.leetcode.checked_at}` : 'Not checked yet today';
      document.getElementById('lc-glow').style.background = lcOk ? '#4ade80' : '#f87171';
    } catch(e) { console.error(e); }
  }

  // ── Action log ─────────────────────────────────────────────────────────────
  async function loadActions() {
    try {
      const d = await apiFetch('/api/logs?limit=20');
      const rows = d.actions;
      if (!rows.length) {
        document.getElementById('actions-table').innerHTML = '<div class="empty-state">No actions yet</div>';
        return;
      }
      const html = `<table class="log-table"><thead><tr>
        <th>Time</th><th>Service</th><th>Action</th><th>Status</th><th>Detail</th>
      </tr></thead><tbody>` + rows.map(r => `<tr>
        <td style="color:var(--text-muted);white-space:nowrap">${r.action_time?.slice(11,19) || ''}</td>
        <td>${tag(r.service === 'github' ? 'tag-github' : 'tag-leetcode', r.service)}</td>
        <td>${r.action_type}</td>
        <td>${tag('tag-' + r.status, r.status)}</td>
        <td style="color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${r.detail || ''}">${r.detail || '—'}</td>
      </tr>`).join('') + '</tbody></table>';
      document.getElementById('actions-table').innerHTML = html;
    } catch(e) { console.error(e); }
  }

  // ── Notifications ──────────────────────────────────────────────────────────
  async function loadNotifications() {
    try {
      const d = await apiFetch('/api/notifications?limit=10');
      const rows = d.notifications;
      if (!rows.length) {
        document.getElementById('notif-table').innerHTML = '<div class="empty-state">No notifications yet</div>';
        return;
      }
      const html = `<table class="log-table"><thead><tr>
        <th>Time</th><th>Status</th><th>Message</th>
      </tr></thead><tbody>` + rows.map(r => `<tr>
        <td style="color:var(--text-muted);white-space:nowrap">${r.sent_at?.slice(0,19) || ''}</td>
        <td>${tag('tag-' + r.status, r.status)}</td>
        <td style="color:var(--text-muted);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${r.message}">${r.message}</td>
      </tr>`).join('') + '</tbody></table>';
      document.getElementById('notif-table').innerHTML = html;
    } catch(e) { console.error(e); }
  }

  // ── Streak history ─────────────────────────────────────────────────────────
  async function loadStreaks() {
    try {
      const d = await apiFetch('/api/streaks?days=14');
      const rows = d.streaks;
      if (!rows.length) {
        document.getElementById('streak-table').innerHTML = '<div class="empty-state">No streak history yet</div>';
        return;
      }
      const html = `<table class="log-table"><thead><tr>
        <th>Date</th><th>Service</th><th>Activity</th><th>Auto-saved</th><th>Detail</th>
      </tr></thead><tbody>` + rows.map(r => `<tr>
        <td>${r.log_date}</td>
        <td>${tag(r.service === 'github' ? 'tag-github' : 'tag-leetcode', r.service)}</td>
        <td>${tag(r.had_activity ? 'tag-success' : 'tag-failure', r.had_activity ? '✅ Yes' : '❌ No')}</td>
        <td>${r.auto_saved ? tag('tag-skipped', '🤖 Yes') : '—'}</td>
        <td style="color:var(--text-muted)">${r.detail || '—'}</td>
      </tr>`).join('') + '</tbody></table>';
      document.getElementById('streak-table').innerHTML = html;
    } catch(e) { console.error(e); }
  }

  // ── Buttons ────────────────────────────────────────────────────────────────
  async function checkNow(btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Checking…';
    try {
      const d = await apiFetch('/api/check-now', 'POST');
      showToast('✅ Check complete! Refreshing status…');
      await loadAll();
    } catch(e) {
      showToast('❌ Check failed: ' + e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = '🔍 Check Now';
    }
  }

  async function saveNow(btn) {
    if (!confirm('This will commit to GitHub and submit to LeetCode if streaks are missing. Continue?')) return;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Saving…';
    try {
      const d = await apiFetch('/api/save-now', 'POST');
      showToast('⚡ Protection job started! Check logs for results.');
      setTimeout(loadAll, 5000);
    } catch(e) {
      showToast('❌ Failed: ' + e.message, 'error');
    } finally {
      setTimeout(() => { btn.disabled = false; btn.innerHTML = '⚡ Save Streak Now'; }, 3000);
    }
  }

  // ── Time display ───────────────────────────────────────────────────────────
  function updateTime() {
    document.getElementById('current-time').textContent = new Date().toLocaleString();
  }

  function loadAll() {
    return Promise.all([loadStatus(), loadActions(), loadNotifications(), loadStreaks()]);
  }

  // ── Init ───────────────────────────────────────────────────────────────────
  updateTime();
  setInterval(updateTime, 1000);
  loadAll();
  setInterval(loadAll, 60000);  // auto-refresh every minute
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return HTMLResponse(content=_DASHBOARD_HTML)
