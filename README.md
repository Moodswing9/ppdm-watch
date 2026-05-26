<div align="center">

# 📺 ppdmwatch

**Real-time terminal monitoring dashboard for Dell PowerProtect Data Manager — the `nsrwatch` equivalent for PPDM**

[![Version](https://img.shields.io/badge/version-1.3.0-6366f1?style=flat-square)](https://github.com/Moodswing9/ppdm-watch/releases)
[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/Moodswing9/ppdm-watch/ci.yml?branch=master&style=flat-square&label=CI)](https://github.com/Moodswing9/ppdm-watch/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.8%2B-3b82f6?style=flat-square)](#requirements)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-f59e0b?style=flat-square)](#installation)
[![Status](https://img.shields.io/badge/status-stable-22c55e?style=flat-square)](#)

</div>

---

## Overview

`ppdmwatch` polls the **PPDM REST API** every few seconds and renders a live, color-coded curses dashboard in your terminal — showing job health, storage system capacity, running sessions, and active alerts. It also runs as a background daemon that writes rotating logs and fires threshold checks automatically.

If you have used `nsrwatch` for NetWorker, this is the same idea for PowerProtect Data Manager.

---

## Features

### 🖥️ Interactive TUI

| Panel | What It Shows |
|:---|:---|
| 📋 Server Summary | Protection + system jobs for the past 24 h — total · running · OK · failed · canceled · queued |
| 💾 Storage Systems | Every registered Data Domain — name · health status · % capacity used |
| ▶️ Running Sessions | Live activity list — ID · type · status · asset name · progress |
| 🔔 Messages & Alerts | Color-coded feed — CRITICAL (red) · WARNING (yellow) · INFO (white) |

### ⚙️ Background Daemon

| Capability | Description |
|:---|:---|
| 🔄 Auto-polling | Configurable interval (default 5 s TUI / 30 s daemon) |
| 📁 Rotating logs | Up to 5 × 10 MB log files under a configurable log directory |
| 🚨 Threshold alerts | Fires on critical alerts, failed jobs, and storage > 85 % |
| 🤖 AI alert summaries | Claude Haiku integration — root cause + action on failures (5-min cooldown). Predictive mode fires when failed jobs or max storage % climb 3 consecutive polls, asking Claude to predict what breaks next |
| 🏥 Health endpoint | `GET /health` HTTP endpoint (default port 8080) returns JSON status — HTTP 200 when connected, 503 when not. Designed for `systemd` `ExecStartPost` health checks and NSSM monitors |
| 🐧 systemd-ready | Drop-in unit file + one-shot `install.sh` for Linux |
| 🪟 Windows support | NSSM wrapper instructions included |

---

## Requirements

- Python **3.8+**
- Dell PPDM **19.10+** (REST API v2)
- `requests`, `urllib3`
- `anthropic` *(optional — enables AI alert summaries via `--ai-key`)*

```bash
pip install -r requirements.txt
```

---

## Getting Started

```bash
# 1. Clone
git clone https://github.com/Moodswing9/ppdm-watch.git
cd ppdm-watch

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch interactive TUI
python ppdmwatch.py --host ppdm01.example.com --username admin --password secret
```

> **Self-signed certificates?** Add `--no-ssl-verify` — common in lab and on-premises environments.

### Background Daemon

```bash
python ppdmwatch.py \
    --host ppdm01.example.com \
    --username admin \
    --password secret \
    --daemon \
    --poll 30 \
    --log-dir /var/log/ppdmwatch \
    --no-ssl-verify
```

---

## TUI Preview

```
 PPDM WATCH | CONNECTED | Health: HEALTHY (98%) | Updated: 2026-04-28 09:15:42 UTC | Press q to quit
────────────────────────────────────────────────────────────────────────────────────────────────────
┌─ Server Summary ───────────────────────────┐┌─ Storage Systems ───────────────────────────┐
│ Protection Jobs (24h): Total: 312  Run:  2 ││ dd9900-a.example.com     HEALTHY   41.2% used│
│   OK: 308  Fail:   1  Canceled:   1        ││ dd9900-b.example.com     HEALTHY   38.7% used│
│ System Jobs (24h):     Total:  18  Run:  0 ││                                              │
│   OK:  18  Fail:   0  Canceled:   0        ││                                              │
│ Queued: 0  |  OK w/ Errors: 2              ││                                              │
│ Critical Alerts: 0  |  Warnings: 1  |  Info: 4                                            │
└────────────────────────────────────────────┘└──────────────────────────────────────────────┘
┌─ Running / Queued Sessions (2) ────────────────────────────────────────────────────────────┐
│  Activity ID                          Type            Status       Asset                   │
│  a1b2c3d4-...                         PROTECT         RUNNING      prod-k8s-namespace      │
│  e5f6g7h8-...                         REPLICATE       RUNNING      oracle-db-01            │
└────────────────────────────────────────────────────────────────────────────────────────────┘
┌─ Messages & Alerts ────────────────────────────────────────────────────────────────────────┐
│  [WARNING] Storage system dd9900-a nearing capacity threshold                              │
│  [INFO] Scheduled maintenance window begins at 22:00 UTC                                   │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## All Options

| Flag | Default | Description |
|:---|:---:|:---|
| `--host` | — | PPDM hostname or IP *(required)* |
| `--username` / `-u` | — | PPDM username *(required)* |
| `--password` / `-p` | — | PPDM password *(required)* |
| `--port` | `8443` | PPDM API port |
| `--poll` | `5` | Polling interval in seconds |
| `--daemon` / `-d` | off | Run as background daemon instead of TUI |
| `--log-dir` | `/var/log/ppdmwatch` | Log directory *(daemon mode)* |
| `--no-ssl-verify` | off | Disable SSL certificate verification |
| `--ai-key KEY` | `$ANTHROPIC_API_KEY` | Anthropic API key for AI alert summaries (omit to disable) |
| `--health-port` | `8080` | Port for `GET /health` HTTP endpoint *(daemon mode only)* |
| `--export [FILE]` | — | One-shot JSON snapshot — authenticate, collect all data, write to FILE (or stdout if omitted), and exit |

---

## PPDM API Endpoints Used

| Panel | Method | Endpoint |
|:---|:---:|:---|
| Authentication | `POST` | `/api/v2/login` |
| Job Summary | `GET` | `/api/v2/activities` |
| Running Sessions | `GET` | `/api/v2/activities` *(status filter)* |
| Storage Systems | `GET` | `/api/v2/storage-systems` |
| Alerts | `GET` | `/api/v2/alerts` |
| System Health | `GET` | `/api/v2/system-health` |

---

## Project Structure

```
ppdm-watch/
├── ppdmwatch.py          # Main application — TUI, daemon, API client
├── tests/
│   └── test_core.py      # Pytest suite — 15 unit tests for core logic
├── ppdmwatch.service     # systemd unit file for Linux deployments
├── install.sh            # One-shot Linux installer (venv, user, credentials, service)
├── requirements.txt      # requests, urllib3 (+ optional anthropic)
└── .env.example          # Credential template
```

---

## Installation

### Linux (systemd)

```bash
chmod +x install.sh
sudo ./install.sh
sudo systemctl start ppdmwatch
sudo systemctl status ppdmwatch
sudo journalctl -u ppdmwatch -f
```

The installer:
- Creates a dedicated `ppdmwatch` system user
- Sets up a Python venv at `/opt/ppdmwatch/venv`
- Stores credentials in `/etc/ppdmwatch/env` (mode `600`)
- Installs and enables the systemd unit

### Windows (NSSM)

```powershell
pip install requests urllib3

nssm install ppdmwatch python `
    "C:\ppdmwatch\ppdmwatch.py" `
    "--host ppdm01 -u admin -p secret" `
    "--daemon --log-dir C:\ppdmwatch\logs --no-ssl-verify --poll 30"

nssm start ppdmwatch
```

---

## Claude Code Plugin

Install as a Claude Code plugin to get `/ppdm-status` directly in your terminal:

```bash
npx skills add Moodswing9/ppdm-watch -g
```

This registers the skill and command globally so you can run `/ppdm-status` from any Claude Code session.

| Command | What it does |
|:---|:---|
| `/ppdm-status` | AI briefing from daemon logs — Status · Current State · Active Issues · Trend · Next Action |
| `/ppdm-status --log-dir /opt/ppdmwatch/logs --lines 500` | Read from a custom log directory |
| `/ppdm-status --health-port 9090` | Poll the live `/health` endpoint on a non-default port |

The skill auto-activates in Claude Code when you ask about PPDM job failures, daemon alerting, curses TUI layout, predictive trend logic, or threshold configuration — no command needed. Requires `ANTHROPIC_API_KEY` and `pip install anthropic`.

---

## More from Moodswing9

| Repo | What it does |
|:---|:---|
| [networker-ppdm](https://github.com/Moodswing9/networker-ppdm) | Python REST API clients, unified `backupctl` CLI, and Claude Code skill for NetWorker, PPDM & Data Domain |
| [ppdm-es-troubleshooter](https://github.com/Moodswing9/ppdm-es-troubleshooter) | Browser-based diagnostic dashboard for PPDM Elasticsearch errors — 10 modules, 7 guided workflows, AI Diagnose |
| [claude-deck-generator](https://github.com/Moodswing9/claude-deck-generator) | AI presentation generator — prompt to `.pptx` / `.html` in seconds, powered by Claude AI |

👉 Full portfolio: [moodswing9.github.io](https://moodswing9.github.io)

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built by [Moodswing9](https://github.com/Moodswing9) · [Portfolio](https://moodswing9.github.io)

</div>
