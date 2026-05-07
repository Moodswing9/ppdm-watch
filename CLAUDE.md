# CLAUDE.md — ppdmwatch

## What This Is

`ppdmwatch` is a single-file Python application (`ppdmwatch.py`) that runs in two modes:

- **TUI mode** (default): live curses dashboard — 4 panels, refreshes every `--poll` seconds
- **Daemon mode** (`--daemon`): headless background agent writing rotating logs and firing threshold alerts

Think `nsrwatch` for NetWorker, but for PowerProtect Data Manager.

## Commands

```bash
# TUI mode
python ppdmwatch.py --host ppdm01.example.com -u admin -p secret

# TUI with AI summaries
python ppdmwatch.py --host ppdm01.example.com -u admin -p secret --ai-key sk-ant-...

# Daemon mode
python ppdmwatch.py --host ppdm01.example.com -u admin -p secret \
  --daemon --poll 30 --log-dir /var/log/ppdmwatch

# Skip SSL (lab / self-signed certs — common in PPDM deployments)
python ppdmwatch.py --host ppdm01.example.com -u admin -p secret --no-ssl-verify

# Install dependencies
pip install -r requirements.txt          # requests, urllib3
pip install anthropic                    # optional — AI summaries
```

## Architecture

Everything lives in `ppdmwatch.py`. Classes in order of appearance:

| Class | Role |
|---|---|
| `PPDMConfig` | Dataclass — host, port, credentials, poll interval, SSL flag |
| `PPDMClient` | PPDM REST API v2 client — login, token refresh, all API calls |
| `JobSummary` | Dataclass — counts: total, running, ok, failed, canceled, queued |
| `DashboardState` | Shared mutable state passed between collector and renderer |
| `AISummarizer` | Optional Claude Haiku 4.5 integration — 5-min cooldown, fires on failures |
| `DataCollector` | Background thread — polls PPDM every N seconds, writes into `DashboardState` |
| `Dashboard` | curses TUI renderer — 4 panels, color-coded, `q` to quit |
| `BackgroundDaemon` | Daemon mode — rotating logs, threshold checks every 60 s |

## PPDM API Endpoints

All under `https://<host>:8443/api/v2`:

| Method | Endpoint | Used for |
|---|---|---|
| `POST` | `/login` | Auth — returns `access_token` |
| `GET` | `/activities` | Jobs (protection + system) with filter strings |
| `GET` | `/storage-systems` | Data Domain capacity |
| `GET` | `/alerts` | Active alerts by severity |
| `GET` | `/system-health` | Overall health percentage |

### Activity filter syntax
```
classType in ("JOB","JOB_GROUP") and startTime gt "2024-01-01T00:00:00Z"
```
Filters are OData-style strings passed as `?filter=` query param.

## Key Constraints

- Token expires after ~8 h; `_ensure_auth()` refreshes 5 min before expiry
- `urllib3.disable_warnings()` is called at module level — expected, PPDM commonly uses self-signed certs
- `DashboardState` is shared between `DataCollector` thread and `Dashboard` renderer — no locks, Python GIL is the only protection. Keep writes atomic (single assignment)
- curses `color_pair` map: 1=green, 2=red, 3=yellow, 4=cyan, 5=white, 6=magenta (AI messages)
- AI summaries only fire when `failed > 0` or `alerts_critical > 0` — never on healthy runs
- `--no-ssl-verify` suppresses warnings globally via urllib3, not per-request

## Daemon Mode

Threshold alerts fire when:
- Any critical alerts present
- `protection_jobs.failed > 0`
- Any storage system > 85% capacity

Logs rotate: 5 files × 10 MB at `--log-dir` (default `/var/log/ppdmwatch`).

Linux systemd: `ppdmwatch.service` + `install.sh` (creates dedicated system user, venv, stores credentials at `/etc/ppdmwatch/env` mode 600).

## Files

```
ppdmwatch.py          # Entire application (~640 lines)
ppdmwatch.service     # systemd unit
install.sh            # One-shot Linux installer
requirements.txt      # requests, urllib3, optional anthropic
.env.example          # Credential template
```
