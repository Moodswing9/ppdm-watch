<div align="center">

# 📺 ppdmwatch

**Real-time terminal monitoring dashboard for Dell PowerProtect Data Manager — the `nsrwatch` equivalent for PPDM**

[![Version](https://img.shields.io/badge/version-1.0.0-6366f1?style=flat-square)](https://github.com/Moodswing9/ppdm-watch/releases)
[![License](https://img.shields.io/badge/license-All%20Rights%20Reserved-ef4444?style=flat-square)](#license)
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
| 🐧 systemd-ready | Drop-in unit file + one-shot `install.sh` for Linux |
| 🪟 Windows support | NSSM wrapper instructions included |

---

## Requirements

- Python **3.8+**
- Dell PPDM **19.10+** (REST API v2)
- `requests`, `urllib3`

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
├── ppdmwatch.py          # Main application — TUI, daemon, API client (~350 lines)
├── ppdmwatch.service     # systemd unit file for Linux deployments
├── install.sh            # One-shot Linux installer (venv, user, credentials, service)
├── requirements.txt      # requests, urllib3
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

## License

Copyright (c) 2026 Timur Poyraz. All rights reserved.

No part of this software may be reproduced, distributed, or modified in any form or by any means without express written permission from the copyright holder.

---

<div align="center">

Built by [Moodswing9](https://github.com/Moodswing9) · [Portfolio](https://moodswing9.github.io/Index/)

</div>
