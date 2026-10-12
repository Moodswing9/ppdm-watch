# Changelog

## [Unreleased]
### Fixed
- CI workflow triggered on `main`, but the default branch is `master`, so the test suite never ran on GitHub; it now runs on every push and pull request
- README version badge and `.claude-plugin/plugin.json` synced to 2.1.0

## [2.1.0] — 2026-07-16
### Added
- **Anomaly baseline calibration** — `AnomalyBaseline` learns the normal range of failed jobs, storage utilisation and critical alerts over the first 10 polls, then flags values more than 2.5σ from the mean
- Calibration progress shown in the dashboard
- 7 new tests (37 total)

### Changed
- AI summaries fire only when the baseline confirms a genuine anomaly, replacing the fixed thresholds

## [2.0.0] — 2026-07-10
### Added
- **MCP bridge mode** (`--mcp`) — runs the data collector in the background and serves live dashboard state to Claude Code over MCP stdio, without the TUI. Tools: `get_job_summary`, `get_storage_status`, `get_active_alerts`, `get_health`
- `mcp>=1.0.0` as an optional dependency in `requirements.txt`
- 5 new tests (30 total)

### Changed
- AI summaries upgraded from Claude Haiku 4.5 to Claude Opus 4.7

## [1.3.0] — 2026-05-23
### Added
- Protection engines panel (panel 4 of the TUI) — lists active protection engines from `/protection-engines`
- GitHub Actions CI — pytest on Python 3.11 and 3.12
- 10 new unit tests: `PPDMClient` login success/failure, `_ensure_auth` retry, `DataCollector` state updates and error handling (25 tests total)

### Fixed
- Token expiry corrected to 7 h (25 200 s); retry logic uses exponential backoff up to 3 attempts
- `CLAUDE.md`: corrected `JobSummary` field list, token expiry, and API endpoint table

## [1.2.0] — 2026-04-20
### Added
- AI summaries via Claude Haiku 4.5 — fires on failures, critical alerts, or 3-consecutive-poll rising trends (predictive mode)
- 5-minute cooldown shared between failure and predictive triggers
- `--ai-key` CLI flag to pass Anthropic API key at runtime
- systemd service unit (`ppdmwatch.service`) and `install.sh` one-shot Linux installer

## [1.1.0] — 2026-04-10
### Added
- Daemon mode (`--daemon`) — headless background agent with rotating log files (5 × 10 MB)
- Threshold alerting: critical alerts present, any failed protection jobs, any storage system > 85%
- Windows NSSM service support documented in README

## [1.0.0] — 2026-04-01
### Added
- Live curses TUI: 4 panels (job summary, storage capacity, active alerts, system health), auto-refreshes every `--poll` seconds
- `DataCollector` background thread feeding `DashboardState` with deque trend buffers
- PPDM REST API v2 client: login, token refresh, activities, storage systems, alerts, system health
- `q` to quit, `--no-ssl-verify` for self-signed cert environments
