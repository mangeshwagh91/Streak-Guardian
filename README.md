# 🛡️ Streak Guardian

> **Production-ready automated streak protection for GitHub contributions and LeetCode submissions.**

Streak Guardian runs silently in the background, monitors your activity, sends Telegram warnings if you're falling behind, and automatically commits/submits on your behalf at 11:45 PM if needed — all with full audit logging and a beautiful admin dashboard.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🐙 **GitHub Protection** | Detects missing commits via REST API and auto-commits `daily-log.txt` |
| 🧩 **LeetCode Protection** | Uses Playwright to submit a stored solution if no submission exists |
| 📱 **Telegram Alerts** | Warning at 10:30 PM + success confirmation after auto-save |
| 📊 **Admin Dashboard** | FastAPI web UI with status cards, log viewer, manual save button |
| 🗄️ **SQLite History** | Full audit log of every check, commit, submission, and notification |
| 🔐 **Secure Config** | All credentials in `.env` — never hardcoded |
| 📋 **Structured Logs** | JSON file logs + coloured console output with rotation |
| 🕐 **APScheduler** | Cron-based scheduling with timezone support |
| 🖥️ **Cross-platform** | Runs on Oracle Cloud, Ubuntu VPS, Raspberry Pi, local machine |

---

## 📁 Project Structure

```
streak-guardian/
│
├── main.py                      ← Entry point (CLI + runs everything)
├── app.py                       ← FastAPI admin dashboard
├── config.py                    ← Typed config from .env
├── scheduler.py                 ← APScheduler jobs (warning + protection)
├── logger.py                    ← Structured rotating logger
│
├── github/
│   ├── __init__.py
│   ├── github_checker.py        ← REST API commit detection
│   └── github_committer.py      ← REST API commit creator (no git binary)
│
├── leetcode/
│   ├── __init__.py
│   ├── leetcode_checker.py      ← GraphQL submission checker
│   └── leetcode_submitter.py    ← Playwright browser automation
│
├── notifications/
│   ├── __init__.py
│   └── telegram_notifier.py     ← Telegram Bot API
│
├── database/
│   ├── __init__.py
│   └── db.py                    ← SQLite layer (streak_log, action_log, notification_log)
│
├── solutions/
│   ├── problem1.py              ← Default Python solution (Two Sum)
│   └── problem1.cpp             ← Default C++ solution
│
├── logs/                        ← Auto-created, rotating JSON logs
├── screenshots/                 ← Playwright screenshots per submission
├── database/streak.db           ← Auto-created SQLite database
│
├── .env                         ← Your secrets (never commit this!)
├── .env.example                 ← Template
├── .gitignore
├── requirements.txt
├── streak-guardian.service      ← systemd unit for Linux
├── deploy.sh                    ← One-shot Linux deployment script
└── README.md
```

---

## 🗄️ Database Schema

```sql
-- Daily streak tracking
CREATE TABLE streak_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    log_date    TEXT NOT NULL,       -- YYYY-MM-DD
    service     TEXT NOT NULL,       -- 'github' | 'leetcode'
    had_activity INTEGER NOT NULL,   -- 1 = active, 0 = missing
    auto_saved  INTEGER NOT NULL,    -- 1 = system saved it
    checked_at  TEXT NOT NULL,       -- ISO datetime of last check
    detail      TEXT,                -- commit SHA or submission status
    UNIQUE(log_date, service)
);

-- Every automated action
CREATE TABLE action_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    action_time TEXT NOT NULL,
    service     TEXT NOT NULL,       -- 'github' | 'leetcode' | 'system'
    action_type TEXT NOT NULL,       -- 'check' | 'commit' | 'submit' | 'notify'
    status      TEXT NOT NULL,       -- 'success' | 'failure' | 'skipped'
    detail      TEXT,
    error       TEXT                 -- traceback on failure
);

-- Outbound notification history
CREATE TABLE notification_log (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_at TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'telegram',
    message TEXT NOT NULL,
    status  TEXT NOT NULL            -- 'sent' | 'failed'
);
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- A GitHub Personal Access Token (PAT) with `repo` scope
- A Telegram Bot token + chat ID
- LeetCode account with known-good solutions saved locally

### 1. Clone and enter the project

```bash
git clone https://github.com/YOUR_USERNAME/streak-guardian.git
cd streak-guardian
```

### 2. Create a virtual environment

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux / macOS
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure environment variables

```bash
cp .env.example .env
# Open .env in your editor and fill in ALL values
```

Key variables to set:

| Variable | Where to get it |
|---|---|
| `GITHUB_USERNAME` | Your GitHub username |
| `GITHUB_TOKEN` | [github.com/settings/tokens](https://github.com/settings/tokens) → New token → `repo` scope |
| `GITHUB_REPO_NAME` | Name of repo to commit to (created automatically if missing) |
| `GITHUB_EMAIL` | Email shown in git commits |
| `LEETCODE_USERNAME` | Your LeetCode username |
| `LEETCODE_PASSWORD` | Your LeetCode password |
| `TELEGRAM_BOT_TOKEN` | Create via [@BotFather](https://t.me/BotFather) on Telegram |
| `TELEGRAM_CHAT_ID` | Send a message to your bot, then visit `api.telegram.org/bot<TOKEN>/getUpdates` |
| `TIMEZONE` | Your local timezone, e.g. `Asia/Kolkata`, `America/New_York` |

### 5. Add your solutions

Place solution files in the `solutions/` folder. The default is `solutions/problem1.py` (Two Sum).

Edit `.env` to set:
```env
LEETCODE_DEFAULT_PROBLEM_SLUG=two-sum
LEETCODE_DEFAULT_SOLUTION_FILE=problem1.py
LEETCODE_LANGUAGE_ID=71   # 71=python3, 54=cpp, 62=java
```

### 6. Run setup helper

```bash
python main.py --setup
```

### 7. Test your configuration

```bash
# Test Telegram
python main.py --test-notify

# Check current streak status
python main.py --check-now

# Run protection manually
python main.py --save-now
```

### 8. Start the full system

```bash
python main.py
```

Dashboard available at: **http://localhost:8000**

---

## ⚙️ CLI Reference

```
python main.py                   # Scheduler + Dashboard (default)
python main.py --scheduler-only  # Scheduler only (no web UI)
python main.py --dashboard-only  # Dashboard only (no scheduler)
python main.py --check-now       # One-shot check and exit
python main.py --save-now        # One-shot protection and exit
python main.py --test-notify     # Test Telegram and exit
python main.py --setup           # First-time setup helper
```

---

## 🖥️ Admin Dashboard

Open **http://localhost:8000** to access the dashboard.

### Features:
- **Status cards** — Live GitHub and LeetCode streak status with auto-saved badges
- **Check Now** — Instantly check streak status from the browser
- **Save Streak Now** — Manually trigger auto-protection with one click
- **Action log** — Every check, commit, and submission
- **Notification log** — All Telegram messages sent
- **Streak history** — 30-day calendar view

### API Endpoints:

| Method | Path | Description |
|---|---|---|
| GET | `/` | Dashboard HTML |
| GET | `/api/status` | Current streak status |
| GET | `/api/logs` | Recent actions |
| GET | `/api/streaks` | Streak history |
| GET | `/api/notifications` | Notification history |
| POST | `/api/check-now` | Trigger live check |
| POST | `/api/save-now` | Trigger protection job |
| GET | `/health` | Health check |
| GET | `/docs` | OpenAPI docs |

---

## 🐧 Linux Deployment (Ubuntu / Oracle Cloud / Raspberry Pi)

### Option A: Automated (Recommended)

```bash
# 1. Upload project to server
scp -r streak-guardian/ ubuntu@YOUR_SERVER_IP:/opt/streak-guardian/

# 2. SSH into server
ssh ubuntu@YOUR_SERVER_IP

# 3. Run deployment script
cd /opt/streak-guardian
bash deploy.sh

# 4. Fill in .env
cp .env.example .env
nano .env

# 5. Start service
sudo systemctl start streak-guardian
sudo systemctl status streak-guardian
```

### Option B: Manual

```bash
# Install Python
sudo apt install python3 python3-pip python3-venv -y

# Create project directory
sudo mkdir -p /opt/streak-guardian
sudo chown $USER:$USER /opt/streak-guardian

# Copy files
cp -r . /opt/streak-guardian/
cd /opt/streak-guardian

# Virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Configure
cp .env.example .env
nano .env

# systemd service
sudo cp streak-guardian.service /etc/systemd/system/
# Edit paths in the service file if needed:
sudo nano /etc/systemd/system/streak-guardian.service

sudo systemctl daemon-reload
sudo systemctl enable streak-guardian
sudo systemctl start streak-guardian
```

### Service Management

```bash
# Status
sudo systemctl status streak-guardian

# View live logs
journalctl -u streak-guardian -f

# Restart
sudo systemctl restart streak-guardian

# Stop
sudo systemctl stop streak-guardian
```

---

## ⏰ Cron Alternative (No systemd)

If you prefer cron instead of systemd (or on macOS/Windows):

```bash
crontab -e
```

Add these lines (adjust path and timezone as needed):

```cron
# Streak Guardian — Warning check at 10:30 PM
30 22 * * * cd /opt/streak-guardian && venv/bin/python main.py --scheduler-only >> logs/cron.log 2>&1

# Alternative: Run protection at 11:45 PM only
45 23 * * * cd /opt/streak-guardian && venv/bin/python main.py --save-now >> logs/cron.log 2>&1
```

**Windows Task Scheduler:**
1. Open Task Scheduler → Create Basic Task
2. Trigger: Daily at 11:45 PM
3. Action: Start a program
   - Program: `C:\path\to\venv\Scripts\python.exe`
   - Arguments: `C:\path\to\streak-guardian\main.py --save-now`
   - Start in: `C:\path\to\streak-guardian\`

---

## 🔐 Security

- **Never** commit `.env` — it's in `.gitignore`
- Use a **fine-grained GitHub PAT** scoped to only the log repository
- Use a **separate private repo** for the log commits
- The LeetCode password is only used in the Playwright session (never logged)
- Enable **2FA** on GitHub — PATs still work with 2FA
- On Linux, run as a **non-root user** (the service uses `User=ubuntu`)
- Optionally enable config encryption by setting `ENCRYPTION_KEY` in `.env`

---

## 🔧 Troubleshooting

### GitHub commit not appearing in contributions
- Make sure the repo is owned by you (not an organization)
- The email in `GITHUB_EMAIL` must match a verified email on your GitHub account
- Private repo contributions only show if you have that setting enabled in your GitHub profile

### LeetCode login failing
- LeetCode has CAPTCHA — if it triggers, the automation will fail
- Check `screenshots/` for a `login_failed_*.png` screenshot
- Try logging in manually first to clear any suspicious activity flags
- Consider using LeetCode cookies (future enhancement)

### Telegram messages not arriving
- Run `python main.py --test-notify` to verify the bot works
- Make sure you sent at least one message TO the bot first (it can't initiate conversations)
- Check `TELEGRAM_CHAT_ID` — get it from `api.telegram.org/bot<TOKEN>/getUpdates`

### Playwright browser crashes on Raspberry Pi
- Install additional system libraries: `sudo apt install libgbm1 libasound2`
- Use `--no-sandbox` flag (already set in the code)
- On Pi Zero / 512 MB RAM: use `--scheduler-only` mode without Playwright

---

## 📝 Adding More Problems

1. Add your solution file to `solutions/`:
   ```
   solutions/
   ├── problem1.py       # Two Sum (default)
   ├── problem42.py      # Trapping Rain Water
   └── problem206.py     # Reverse Linked List
   ```

2. Update `.env`:
   ```env
   LEETCODE_DEFAULT_PROBLEM_SLUG=trapping-rain-water
   LEETCODE_DEFAULT_SOLUTION_FILE=problem42.py
   ```

The system always uses the problem and file specified in `.env` for auto-protection.

---

## 📄 License

MIT — use freely, contribute back.

---

## 🙏 Credits

Built with:
- [FastAPI](https://fastapi.tiangolo.com/)
- [Playwright](https://playwright.dev/python/)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [httpx](https://www.python-httpx.org/)
- [python-dotenv](https://github.com/theskumar/python-dotenv)
