---
name: ppdm-watch
description: Real-time PPDM monitoring — interpret TUI panels, read daemon logs, understand predictive alerting, troubleshoot ppdmwatch connectivity and AI summary issues.
---

# ppdmwatch

Real-time monitoring for Dell PowerProtect Data Manager. Runs as an interactive curses TUI or a headless background daemon with rotating logs and a `/health` HTTP endpoint. The `nsrwatch` equivalent for PPDM.

## Trigger

Activate this skill when the user asks about:
- ppdmwatch, ppdm-watch, PPDM monitoring dashboard, terminal dashboard
- Reading or troubleshooting daemon logs at `--log-dir`
- The `/health` endpoint or liveness probes
- Predictive alerting, trend detection, rising polls
- Claude Haiku AI summaries in the dashboard
- Running ppdmwatch as a service (systemd, NSSM)
- `/ppdm-status` command output

---

## TUI Layout

Four curses panels updated every `--poll` seconds.

### Panel 1 — Server Summary (top-left)
```
Protection Jobs (24h): Total: 312  Run:  2
  OK: 308  Fail:   1  Canceled:   1
System Jobs (24h):     Total:  18  Run:  0
  OK:  18  Fail:   0  Canceled:   0
Queued: 0  |  OK w/ Errors: 2
Critical Alerts: 0  |  Warnings: 1  |  Info: 4
```
- **Protection jobs**: PROTECT, REPLICATE, CLOUD_PROTECT, CLOUD_REPLICATE, CLOUD_TIER
- **System jobs**: RESTORE and all non-protection classes
- `OK w/ Errors` = jobs that completed but logged sub-errors (not failures — monitor for trend)

### Panel 2 — Storage Systems (top-right)
Each row: `<Data Domain hostname>  <health>  <pct>% used`
Health values: `HEALTHY` · `WARNING` · `CRITICAL` · `UNKNOWN`

### Panel 3 — Running / Queued Sessions (middle)
Columns: Activity ID · Type · Status · Asset name
Filtered to `RUNNING` and `QUEUED` statuses only.

### Panel 4 — Messages & Alerts (bottom)
Color-coded feed:

| Color | Severity |
|---|---|
| Red | CRITICAL |
| Yellow | WARNING |
| White | INFO |
| Magenta | AI summary messages |

**Color pair index:** 1=green (OK), 2=red (FAILED/CRITICAL), 3=yellow (WARNING), 4=cyan (RUNNING), 5=white (INFO), 6=magenta (AI messages)

---

## Daemon Mode

Started with `--daemon`. Writes rotating log files instead of rendering a TUI.

**Log format:**
```
2026-04-28 09:15:42,123 [INFO] Connected to ppdm01.example.com (Health: HEALTHY 98%)
2026-04-28 09:15:42,456 [WARNING] Storage system dd9900-a: 87.3% used (threshold: 85%)
2026-04-28 09:15:43,001 [CRITICAL] 3 failed protection jobs detected
2026-04-28 09:15:43,800 [INFO] AI summary: root cause — vProxy unreachable on esxi01
```

**Rotation:** 5 files × 10 MB at `--log-dir` (default `/var/log/ppdmwatch`)
**File pattern:** `ppdmwatch.log`, `ppdmwatch.log.1`, …, `ppdmwatch.log.4`

**Threshold alerts fire when:**
- Any alert with severity `CRITICAL` is active
- `protection_jobs.failed > 0`
- Any storage system > 85% capacity

---

## Health Endpoint

Daemon mode exposes `GET http://127.0.0.1:<health-port>/health` (default port 8080).

**Response — connected (HTTP 200):**
```json
{
  "status": "connected",
  "host": "ppdm01.example.com",
  "last_poll": "2026-04-28T09:15:42Z",
  "health_score": 98,
  "failed_jobs": 1,
  "critical_alerts": 0,
  "max_storage_pct": 41.2
}
```

**Response — disconnected:** HTTP 503 `{"status": "disconnected", "error": "..."}`

Designed for `systemd` `ExecStartPost` health checks and NSSM monitoring.

---

## AI Summaries (AISummarizer)

Model: `claude-haiku-4-5-20251001`. Enabled via `--ai-key` (falls back to `$ANTHROPIC_API_KEY`).

**Structured output via tool-calling.** Uses `tool_choice={"type": "tool", "name": "ppdm_summary"}` to force this exact JSON shape every call:

```json
{
  "root_cause": "string — most likely root cause in 10 words or fewer",
  "action":     "string — single most important action in 10 words or fewer"
}
```

Tool schema name: `ppdm_summary`. Both fields are required strings.

**Reactive mode** — fires when:
- `protection_jobs.failed > 0`, OR
- `alerts_critical > 0`

**Predictive mode** — fires even with zero failures when:
- `failed_jobs_history[-1] > failed_jobs_history[-2] > failed_jobs_history[-3]`, OR
- `storage_pct_history[-1] > storage_pct_history[-2] > storage_pct_history[-3]`

Both are `deque(maxlen=6)` fields on `DashboardState`, updated every poll.
Predictive prompt asks Claude to forecast what will break next.

**Cooldown:** 5 minutes between any AI calls (reactive and predictive share the same timer).

**Display:** Magenta `[AI]` message at the bottom of Panel 4.

---

## DashboardState Key Fields

Shared between `DataCollector` thread and `Dashboard` renderer. No locks — GIL protects single-assignment writes.

| Field | Type | Description |
|---|---|---|
| `connected` | bool | Whether last poll succeeded |
| `health_score` | int | PPDM system health % |
| `protection_jobs` | JobSummary | 24h protection job counts |
| `system_jobs` | JobSummary | 24h system job counts |
| `storage_systems` | List[Dict] | Data Domain capacity rows |
| `running_sessions` | List[Dict] | Active/queued activities |
| `messages` | List[str] | Alert feed |
| `failed_jobs_history` | Deque[int] | Rolling 6-poll failed count |
| `storage_pct_history` | Deque[float] | Rolling 6-poll max storage % |
| `ai_message` | Optional[str] | Latest AI summary text |
| `last_update` | Optional[datetime] | Timestamp of last successful poll |

---

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ConnectionRefusedError` on startup | Wrong host/port or PPDM unreachable | Verify `--host` and `--port 8443` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Self-signed PPDM cert | Add `--no-ssl-verify` |
| 401 on login | Wrong credentials | Check `--username` / `--password` |
| 401 mid-session after hours | Token expired, refresh failed | Check PPDM connectivity — `_ensure_auth()` should refresh 5 min before expiry |
| Garbled display / curses crash | Terminal too small | Resize to at least 80×24 |
| No AI summaries despite `--ai-key` | `anthropic` package not installed | `pip install anthropic` |
| AI summaries stop mid-session | 5-min cooldown or quota exhausted | Normal — wait 5 min; check Anthropic dashboard |
| `/health` returns 503 | Daemon disconnected from PPDM | Check daemon logs at `--log-dir` |

---

## CLI Flags

| Flag | Default | Notes |
|---|---|---|
| `--host` | required | PPDM hostname or IP |
| `--username` / `-u` | required | PPDM admin user |
| `--password` / `-p` | required | PPDM password |
| `--port` | `8443` | PPDM API port |
| `--poll` | `5` (TUI) / `30` (daemon) | Polling interval in seconds |
| `--daemon` / `-d` | off | Run headless with rotating logs |
| `--log-dir` | `/var/log/ppdmwatch` | Daemon log directory |
| `--no-ssl-verify` | off | Skip SSL cert check (common for PPDM lab/on-prem) |
| `--ai-key KEY` | `$ANTHROPIC_API_KEY` | Anthropic key for AI summaries |
| `--health-port` | `8080` | Daemon HTTP health endpoint port |
| `--export [FILE]` | — | One-shot JSON snapshot: authenticate, collect all data, write to FILE (or stdout if omitted), then exit |

---

## Few-Shot Examples

**Q: The magenta "[AI]" message says "3 consecutive rising polls" but there are no failures. Is something broken?**
A: No — predictive mode triggered. `storage_pct_history` has grown for 3 consecutive polls. No jobs have failed yet, but max storage % across Data Domain systems is climbing. Claude Haiku is predicting what breaks next (likely watermark breach or disk-full backup failures). Watch storage Panel 2 closely.

**Q: "OK w/ Errors: 2" — should I be worried?**
A: Not immediately. `OK_WITH_ERRORS` means the job completed but logged sub-errors (skipped files, a warning event). If the count grows each poll cycle, investigate the specific assets — run `/ppdm-failed-jobs` or check the PPDM activity log.

**Q: How do I read ppdmwatch logs with /ppdm-status?**
A: `/ppdm-status` hits the live `/health` endpoint first (if daemon is running), then reads rotating log files from `--log-dir`. Produces a 5-section briefing: Status badge → Current State → Active Issues → Trend → Single Most Important Action.

**Q: How do I install ppdmwatch as a Windows service?**
A: Use NSSM:
```powershell
nssm install ppdmwatch python `
    "C:\ppdmwatch\ppdmwatch.py" `
    "--host ppdm01 -u admin -p secret --daemon --log-dir C:\ppdmwatch\logs --no-ssl-verify --poll 30"
nssm start ppdmwatch
```
