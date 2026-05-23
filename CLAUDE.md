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
| `JobSummary` | Dataclass — counts: total, running, success, failed, canceled, queued, ok_with_errors, unknown |
| `DashboardState` | Shared mutable state passed between collector and renderer |
| `AISummarizer` | Optional Claude Haiku 4.5 integration — 5-min cooldown, fires on failures or rising trends |
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
| `GET` | `/protection-engines` | Protection engine list |

### Activity filter syntax
```
classType in ("JOB","JOB_GROUP") and startTime gt "2024-01-01T00:00:00Z"
```
Filters are OData-style strings passed as `?filter=` query param.

## Key Constraints

- Token expires after 7 h (25 200 s); `_ensure_auth()` refreshes 5 min before expiry and retries up to 3 times with exponential backoff
- `urllib3.disable_warnings()` is called at module level — expected, PPDM commonly uses self-signed certs
- `DashboardState` is shared between `DataCollector` thread and `Dashboard` renderer — no locks, Python GIL is the only protection. Keep writes atomic (single assignment). It carries two `deque(maxlen=6)` trend buffers: `failed_jobs_history` and `storage_pct_history`
- curses `color_pair` map: 1=white (normal), 2=green (success), 3=red (failed/critical), 4=yellow (warning), 5=cyan (running), 6=magenta (header/AI)
- AI summaries fire when `failed > 0` or `alerts_critical > 0`, **or** when failed-job count or max storage % has risen for 3 consecutive polls (predictive mode — asks Claude what breaks next)
- Predictive mode cooldown is shared with the failure cooldown (5 min)
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
ppdmwatch.py          # Entire application
ppdmwatch.service     # systemd unit
install.sh            # One-shot Linux installer
requirements.txt      # requests, urllib3, optional anthropic
.env.example          # Credential template
tests/
  test_core.py        # 15 pytest unit tests for build_job_summary, build_messages, AISummarizer._should_predict
.claude/
  commands/
    ppdm-status.md    # /ppdm-status — AI briefing from daemon logs
```
