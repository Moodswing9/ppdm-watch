---
description: Generate an AI-driven status briefing from ppdmwatch daemon logs — surfaces failures, trends, and the single most important action
argument-hint: "[--log-dir <path>] [--lines N] [--health-port <port>]"
allowed-tools: ["Bash", "Read", "Glob"]
---

The user wants a ppdmwatch status briefing. Arguments: $ARGUMENTS

**Execute every step yourself. Do not ask the user to run commands.**

## Step 1 — Locate the log directory

Parse `$ARGUMENTS` for `--log-dir <path>` (default: `/var/log/ppdmwatch` on Linux/macOS, `C:\ppdmwatch\logs` on Windows).
Parse `--lines N` for how many recent log lines to analyse (default: 300).
Parse `--health-port <port>` for the daemon health endpoint (default: 8080).

Use Glob to find `ppdmwatch.log` under the log directory. If the directory doesn't exist or contains no log files, stop:
> "No ppdmwatch log files found at `<path>`. Is the daemon running? Start it with `python ppdmwatch.py --daemon --log-dir <path>`"

## Step 2 — Try the live health endpoint

Use the Bash tool to query the daemon's health HTTP endpoint:

```bash
python3 -c "
import urllib.request, json, sys
try:
    with urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3) as r:
        print(json.dumps(json.loads(r.read()), indent=2))
except Exception as e:
    print(f'health_endpoint_unavailable: {e}')
" 2>&1
```

Substitute the actual health port from Step 1. If unavailable, note it and continue — the log files are the primary source.

## Step 3 — Read the daemon log

Use the Bash tool to read the last N lines from the most recent log file:

```bash
python3 -c "
import os, glob

log_dir = '/var/log/ppdmwatch'   # ← substitute actual log dir
n_lines = 300                     # ← substitute actual --lines value

# Find all rotating log files, pick the newest
pattern = os.path.join(log_dir, 'ppdmwatch.log*')
files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
if not files:
    print('NO_LOG_FILES')
    raise SystemExit(1)

lines = []
for f in files:
    try:
        with open(f) as fh:
            lines = fh.readlines() + lines
        if len(lines) >= n_lines:
            break
    except Exception:
        continue

print(''.join(lines[-n_lines:]))
" 2>&1
```

If the output is `NO_LOG_FILES`, stop with the message from Step 1.

## Step 4 — Run the AI briefing

Use the Bash tool to pipe the log content through Claude Haiku 4.5. Substitute the actual log content (from Step 3) and the health JSON (from Step 2, or `"unavailable"`) into the script:

```bash
python3 - << 'PYEOF'
import re, anthropic

LOG_CONTENT   = """<paste log lines here>"""     # ← substitute Step 3 output
HEALTH_JSON   = """<paste health JSON here>"""   # ← substitute Step 2 output (or "unavailable")

def redact(text):
    text = re.sub(r'\b(\d{1,3}\.\d{1,3})\.\d{1,3}\.\d{1,3}\b', r'\1.x.x', text)
    text = re.sub(r'(?i)(password|passwd|secret)[=: ]+\S+', r'\1=[REDACTED]', text)
    return text

log = redact(LOG_CONTENT[:40000])

system = """You are a senior Dell PowerProtect Data Manager (PPDM) operations engineer monitoring a live environment via ppdmwatch daemon logs.

The log format is: TIMESTAMP [LEVEL] MESSAGE
Levels: ERROR (critical failures), WARNING (threshold breaches, degraded state), INFO (routine polls).

Produce a concise terminal briefing with this exact structure:

## Status: [HEALTHY | DEGRADED | CRITICAL]

## Current State
2–3 sentences. Reference the most recent log entries. Include: failed job count, critical alert count, storage headroom (if visible), and whether the daemon is connected.

## Active Issues
Bullet list of current problems with severity. If none, say "No active issues detected."

## Trend
One sentence: is the environment improving, stable, or worsening based on the last N entries?

## Single Most Important Action
One specific action the operator should take right now — or "None required" if healthy.
Provide the exact command if applicable."""

health_note = f"\n\nLive /health endpoint response:\n{HEALTH_JSON}" if HEALTH_JSON != "unavailable" else ""

user_content = f"Recent ppdmwatch daemon log (most recent entries last):{health_note}\n\n```\n{log}\n```"

client = anthropic.Anthropic()
with client.messages.stream(
    model='claude-haiku-4-5-20251001',
    max_tokens=600,
    system=system,
    messages=[{'role': 'user', 'content': user_content}],
) as stream:
    for text in stream.text_stream:
        print(text, end='', flush=True)
print()
PYEOF
```

## Step 5 — Handle errors

| Error | Response |
|---|---|
| `AuthenticationError` | "Set your API key: `export ANTHROPIC_API_KEY=sk-ant-…`" |
| `ModuleNotFoundError: anthropic` | "Install the SDK: `pip install anthropic`" |
| Log directory not found | Report the path and show the daemon start command |
| Health endpoint timeout | Note it as "daemon not running or health port blocked" and proceed with logs only |

## Expected output format

The briefing Claude Haiku should produce looks like this — match this structure exactly:

```
## Status: DEGRADED

## Current State
As of 09:15:42 UTC, ppdmwatch is connected to ppdm01.example.com (Health: 94%). 1 protection
job failed in the last poll cycle. Storage systems are within normal bounds (max 41.2% used).

## Active Issues
- **[HIGH]** 1 failed PROTECT job — asset: prod-k8s-namespace (vProxy unreachable)
- **[WARNING]** Storage dd9900-a at 81.3% — approaching 85% threshold

## Trend
Environment is stable overall but the vProxy failure has appeared in the last 3 consecutive
polls, suggesting a persistent connectivity issue rather than a transient error.

## Single Most Important Action
Verify vProxy connectivity from PPDM to the ESXi host:
  curl -sk -H "Authorization: Bearer <token>" https://ppdm01:8443/api/v2/vcenters
```
