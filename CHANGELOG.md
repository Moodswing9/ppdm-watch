# Changelog

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
