# ppdmwatch

**Real-time terminal dashboard for Dell PowerProtect Data Manager — the `nsrwatch` equivalent for PPDM.**

`ppdmwatch` polls the PPDM REST API and renders a live curses TUI showing job health, storage status, running sessions, and alerts. It also runs as a background daemon that logs to file and checks alert thresholds automatically.

---

## Screenshot

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

## Features

- **Live curses TUI** — auto-refreshes every second, press `q` to quit
- **Job summary** — protection and system jobs for the last 24 h (total / running / OK / failed / canceled / queued)
- **Storage systems** — name, status, and % capacity for each registered Data Domain
- **Running sessions** — activity ID, type, status, asset name, and progress
- **Messages & alerts** — color-coded CRITICAL / WARNING / INFO feed
- **Background daemon** — logs to rotating file, checks alert and capacity thresholds every 60 s
- **Systemd service** — ready-to-use unit file and `install.sh` for Linux deployments

---

## Requirements

- Python 3.8+
- PPDM 19.10+ (REST API v2)
- `requests`, `urllib3`

```bash
pip install -r requirements.txt
```

---

## Quick Start

### Interactive TUI

```bash
python ppdmwatch.py --host ppdm01.example.com --username admin --password secret
```

With self-signed / lab certificates:

```bash
python ppdmwatch.py --host ppdm01.example.com -u admin -p secret --no-ssl-verify
```

### Background Daemon

```bash
python ppdmwatch.py --host ppdm01.example.com -u admin -p secret \
    --daemon \
    --poll 30 \
    --log-dir /var/log/ppdmwatch \
    --no-ssl-verify
```

---

## All Options

| Flag | Default | Description |
|---|---|---|
| `--host` | — | PPDM hostname or IP (required) |
| `--username` / `-u` | — | PPDM username (required) |
| `--password` / `-p` | — | PPDM password (required) |
| `--port` | `8443` | PPDM API port |
| `--poll` | `5` | Polling interval in seconds |
| `--daemon` / `-d` | off | Run as background daemon |
| `--log-dir` | `/var/log/ppdmwatch` | Log directory (daemon mode) |
| `--no-ssl-verify` | off | Disable SSL certificate verification |

---

## Linux Service Installation

```bash
chmod +x install.sh
sudo ./install.sh
sudo systemctl start ppdmwatch
sudo journalctl -u ppdmwatch -f
```

The installer creates a dedicated `ppdmwatch` system user, sets up a Python venv under `/opt/ppdmwatch`, stores credentials in `/etc/ppdmwatch/env` (mode 600), and enables the systemd unit.

### Windows (NSSM)

```powershell
pip install requests
nssm install ppdmwatch "python" "C:\ppdmwatch\ppdmwatch.py --host ppdm01 -u admin -p secret --daemon --log-dir C:\ppdmwatch\logs --no-ssl-verify --poll 30"
nssm start ppdmwatch
```

---

## PPDM API Endpoints Used

| Panel | Endpoint |
|---|---|
| Job Summary | `GET /api/v2/activities` |
| Storage Systems | `GET /api/v2/storage-systems` |
| Running Sessions | `GET /api/v2/activities` (status filter) |
| Alerts | `GET /api/v2/alerts` |
| System Health | `GET /api/v2/system-health` |
| Authentication | `POST /api/v2/login` |

---

## License

MIT © 2026 Timur Poyraz
