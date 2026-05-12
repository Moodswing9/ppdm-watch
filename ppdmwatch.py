#!/usr/bin/env python3
"""
ppdmwatch — Real-time monitoring dashboard for Dell PowerProtect Data Manager.
Equivalent to nsrwatch for NetWorker.
"""

__version__ = "1.1.0"
__author__ = "Timur Poyraz"

from __future__ import annotations

import argparse
import copy
import curses
import http.server
import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time
import urllib3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ─── Configuration ────────────────────────────────────────────────────────────

@dataclass
class PPDMConfig:
    host: str
    username: str
    password: str
    port: int = 8443
    poll_interval: int = 5
    verify_ssl: bool = False
    timeout: int = 30

    @property
    def base_url(self) -> str:
        return f"https://{self.host}:{self.port}"


# ─── PPDM API Client ──────────────────────────────────────────────────────────

class PPDMClient:
    def __init__(self, config: PPDMConfig):
        self.config = config
        self.session = requests.Session()
        self.session.verify = config.verify_ssl
        self.token: Optional[str] = None
        self.token_expiry: Optional[float] = None

    def _url(self, path: str) -> str:
        return urljoin(self.config.base_url, path)

    def login(self) -> bool:
        try:
            resp = self.session.post(
                self._url("/api/v2/login"),
                json={"username": self.config.username, "password": self.config.password},
                timeout=self.config.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("access_token")
            # Token valid ~8 h; refresh after 7 h
            self.token_expiry = datetime.now(timezone.utc).timestamp() + 25200
            self.session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            })
            return True
        except Exception as e:
            logging.error(f"Login failed: {e}")
            return False

    def _ensure_auth(self) -> None:
        if not self.token or datetime.now(timezone.utc).timestamp() > self.token_expiry - 300:
            self.login()

    def get_activities(self, filters: str = "", page_size: int = 100) -> List[Dict]:
        self._ensure_auth()
        params: Dict[str, Any] = {"pageSize": page_size}
        if filters:
            params["filter"] = filters
        try:
            resp = self.session.get(
                self._url("/api/v2/activities"), params=params, timeout=self.config.timeout
            )
            resp.raise_for_status()
            return resp.json().get("content", [])
        except Exception as e:
            logging.error(f"Failed to fetch activities: {e}")
            return []

    def get_storage_systems(self) -> List[Dict]:
        self._ensure_auth()
        try:
            resp = self.session.get(
                self._url("/api/v2/storage-systems"), timeout=self.config.timeout
            )
            resp.raise_for_status()
            return resp.json().get("content", [])
        except Exception as e:
            logging.error(f"Failed to fetch storage: {e}")
            return []

    def get_alerts(self, severity: Optional[str] = None) -> List[Dict]:
        self._ensure_auth()
        params: Dict[str, Any] = {"pageSize": 50}
        if severity:
            params["filter"] = f"severity eq '{severity}'"
        try:
            resp = self.session.get(
                self._url("/api/v2/alerts"), params=params, timeout=self.config.timeout
            )
            resp.raise_for_status()
            return resp.json().get("content", [])
        except Exception as e:
            logging.error(f"Failed to fetch alerts: {e}")
            return []

    def get_system_health(self) -> Dict[str, Any]:
        self._ensure_auth()
        try:
            resp = self.session.get(
                self._url("/api/v2/system-health"), timeout=self.config.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logging.error(f"Failed to fetch health: {e}")
            return {}

    def get_protection_engines(self) -> List[Dict]:
        self._ensure_auth()
        try:
            resp = self.session.get(
                self._url("/api/v2/protection-engines"), timeout=self.config.timeout
            )
            resp.raise_for_status()
            return resp.json().get("content", [])
        except Exception as e:
            logging.error(f"Failed to fetch engines: {e}")
            return []


# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class JobSummary:
    total: int = 0
    running: int = 0
    queued: int = 0
    success: int = 0
    failed: int = 0
    canceled: int = 0
    ok_with_errors: int = 0
    unknown: int = 0

    @property
    def completed(self) -> int:
        return self.success + self.failed + self.canceled + self.ok_with_errors


@dataclass
class DashboardState:
    lock: threading.Lock = field(default_factory=threading.Lock, compare=False, repr=False)
    server_uptime: str = "Unknown"
    ppdm_version: str = "Unknown"
    health_score: int = 0
    health_status: str = "Unknown"
    protection_jobs: JobSummary = field(default_factory=JobSummary)
    system_jobs: JobSummary = field(default_factory=JobSummary)
    storage_systems: List[Dict] = field(default_factory=list)
    alerts_critical: int = 0
    alerts_warning: int = 0
    alerts_info: int = 0
    recent_alerts: List[Dict] = field(default_factory=list)
    running_sessions: List[Dict] = field(default_factory=list)
    messages: List[str] = field(default_factory=list)
    last_update: str = ""
    connected: bool = False
    error: Optional[str] = None
    protection_engines: List[Dict] = field(default_factory=list)
    ai_summary: Optional[str] = None


# ─── AI Alert Summariser ──────────────────────────────────────────────────────

class AISummarizer:
    _COOLDOWN = 300  # seconds between Claude calls

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._last_call: float = 0.0

    def _should_call(self, state: DashboardState) -> bool:
        if not _ANTHROPIC_AVAILABLE:
            return False
        if state.protection_jobs.failed == 0 and state.alerts_critical == 0:
            return False
        return (time.time() - self._last_call) >= self._COOLDOWN

    def summarize(self, state: DashboardState) -> Optional[str]:
        if not self._should_call(state):
            return None
        try:
            client = _anthropic.Anthropic(api_key=self._api_key)
            alert_lines = "\n".join(
                f"- [{a.get('severity','?')}] {a.get('message','')}" for a in state.recent_alerts[:5]
            )
            prompt = (
                f"PPDM health: {state.health_status} ({state.health_score}%)\n"
                f"Failed protection jobs (24h): {state.protection_jobs.failed}\n"
                f"Critical alerts: {state.alerts_critical}\n"
                f"Recent alerts:\n{alert_lines}\n\n"
                "In one sentence, state the most likely root cause and the single most important action to take."
            )
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=120,
                system="You are a Dell PPDM expert. Be concise — one sentence only.",
                messages=[{"role": "user", "content": prompt}],
            )
            self._last_call = time.time()
            return msg.content[0].text.strip()
        except Exception as e:
            logging.warning(f"AI summarizer error: {e}")
            return None


# ─── Background Data Collector ────────────────────────────────────────────────

class DataCollector(threading.Thread):
    def __init__(self, client: PPDMClient, state: DashboardState, interval: int,
                 ai_summarizer: Optional["AISummarizer"] = None):
        super().__init__(daemon=True)
        self.client = client
        self.state = state
        self.interval = interval
        self._ai = ai_summarizer
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._collect()
            except Exception as e:
                with self.state.lock:
                    self.state.error = str(e)
                    self.state.connected = False
            self._stop_event.wait(self.interval)

    def _collect(self) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        yesterday = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

        prot_filter = (
            f'startTime ge "{yesterday}" and parentId eq null and '
            f'classType in ("JOB", "JOB_GROUP") and '
            f'category in ("PROTECT", "REPLICATE", "CLOUD_PROTECT", "CLOUD_TIER", "EXPORT_REUSE")'
        )
        prot_jobs = self.client.get_activities(prot_filter, page_size=500)

        sys_filter = (
            f'startTime ge "{yesterday}" and parentId eq null and '
            f'classType in ("JOB", "JOB_GROUP") and '
            f'category in ("CONFIG", "CONSOLE", "DELETE", "DISASTER_RECOVERY", '
            f'"DISCOVER", "MANAGE", "NOTIFY", "SYSTEM", "VALIDATE", "CLOUD_DR")'
        )
        sys_jobs = self.client.get_activities(sys_filter, page_size=500)

        running_filter = (
            'classType in ("JOB", "JOB_GROUP") and '
            'result.status in ("RUNNING", "QUEUED", "CANCELING")'
        )
        running = self.client.get_activities(running_filter, page_size=100)

        storage = self.client.get_storage_systems()
        engines = self.client.get_protection_engines()
        health = self.client.get_system_health()
        critical_alerts = self.client.get_alerts("CRITICAL")
        warning_alerts = self.client.get_alerts("WARNING")
        info_alerts = self.client.get_alerts("INFORMATIONAL")
        all_alerts = self.client.get_alerts()

        def summarize(jobs: List[Dict]) -> JobSummary:
            s = JobSummary(total=len(jobs))
            for j in jobs:
                status = j.get("result", {}).get("status", "UNKNOWN")
                if status == "RUNNING":
                    s.running += 1
                elif status == "QUEUED":
                    s.queued += 1
                elif status == "OK":
                    s.success += 1
                elif status == "FAILED":
                    s.failed += 1
                elif status == "CANCELED":
                    s.canceled += 1
                elif status == "OK_WITH_ERRORS":
                    s.ok_with_errors += 1
                else:
                    s.unknown += 1
            return s

        messages: List[str] = []
        if len(critical_alerts) > 0:
            messages.append(f"CRITICAL: {len(critical_alerts)} critical alert(s) active!")
        for alert in all_alerts[:5]:
            sev = alert.get("severity", "INFO")
            msg = alert.get("message", "No message")
            messages.append(f"[{sev}] {msg[:80]}")

        prot_summary = summarize(prot_jobs)
        sys_summary  = summarize(sys_jobs)

        with self.state.lock:
            self.state.protection_jobs = prot_summary
            self.state.system_jobs = sys_summary
            self.state.running_sessions = running
            self.state.storage_systems = storage
            self.state.protection_engines = engines
            self.state.health_score = health.get("score", 0)
            self.state.health_status = health.get("status", "Unknown")
            self.state.alerts_critical = len(critical_alerts)
            self.state.alerts_warning = len(warning_alerts)
            self.state.alerts_info = len(info_alerts)
            self.state.recent_alerts = all_alerts[:10]
            self.state.messages = messages
            self.state.last_update = now
            self.state.connected = True
            self.state.error = None

        if self._ai:
            ai_text = self._ai.summarize(self.state)
            if ai_text:
                with self.state.lock:
                    self.state.ai_summary = f"[AI] {ai_text}"


# ─── TUI Dashboard ────────────────────────────────────────────────────────────

class Dashboard:
    def __init__(self, state: DashboardState):
        self.state = state
        self.screen = None

    def _draw_box(self, win, title: str) -> None:
        win.box()
        if title:
            win.addstr(0, 2, f" {title} ", curses.A_BOLD)

    def _color_for_status(self, status: str) -> int:
        s = status.upper()
        if s in ("OK", "SUCCESS", "GOOD", "HEALTHY"):
            return curses.color_pair(2)
        if s in ("FAILED", "CRITICAL", "ERROR", "DEGRADED"):
            return curses.color_pair(3)
        if s in ("WARNING", "OK_WITH_ERRORS"):
            return curses.color_pair(4)
        if s in ("RUNNING", "QUEUED", "CANCELING"):
            return curses.color_pair(5)
        return curses.color_pair(1)

    def _truncate(self, text: str, width: int) -> str:
        if len(text) <= width:
            return text
        return text[: width - 3] + "..."

    def run(self, stdscr) -> None:
        self.screen = stdscr
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_WHITE, -1)    # Normal
        curses.init_pair(2, curses.COLOR_GREEN, -1)    # Success
        curses.init_pair(3, curses.COLOR_RED, -1)      # Failed / Critical
        curses.init_pair(4, curses.COLOR_YELLOW, -1)   # Warning
        curses.init_pair(5, curses.COLOR_CYAN, -1)     # Running
        curses.init_pair(6, curses.COLOR_MAGENTA, -1)  # Header
        stdscr.nodelay(True)
        while True:
            key = stdscr.getch()
            if key == ord("q"):
                break
            self._render()
            time.sleep(1)

    def _render(self) -> None:
        with self.state.lock:
            state = copy.copy(self.state)
        self.screen.clear()
        h, w = self.screen.getmaxyx()

        if h < 24 or w < 80:
            self.screen.addstr(0, 0, "Terminal too small — need at least 80x24.")
            self.screen.refresh()
            return

        # ── Header ──
        conn = "CONNECTED" if state.connected else "DISCONNECTED"
        header = (
            f" ppdmwatch v{__version__} | {conn} | "
            f"Health: {state.health_status} ({state.health_score}%) | "
            f"Updated: {state.last_update} | q = quit "
        )
        self.screen.attron(curses.color_pair(6) | curses.A_BOLD)
        self.screen.addstr(0, 0, header[: w - 1])
        self.screen.attroff(curses.color_pair(6) | curses.A_BOLD)
        self.screen.hline(1, 0, curses.ACS_HLINE, w)

        if state.error:
            self.screen.attron(curses.color_pair(3) | curses.A_BOLD)
            self.screen.addstr(1, 0, f" ERROR: {state.error}"[: w - 1])
            self.screen.attroff(curses.color_pair(3) | curses.A_BOLD)

        # ── Layout ──
        left_w = w // 2
        right_w = w - left_w

        # Panel 1: Server / Job Summary (top-left)
        sum_h = 8
        sum_win = curses.newwin(sum_h, left_w, 2, 0)
        self._draw_box(sum_win, "Server Summary")
        pj = state.protection_jobs
        sj = state.system_jobs
        lines = [
            f"Protection Jobs (24h): Total:{pj.total:>4}  Run:{pj.running:>3}  OK:{pj.success:>4}  "
            f"Fail:{pj.failed:>3}  Canceled:{pj.canceled:>3}",
            f"System Jobs     (24h): Total:{sj.total:>4}  Run:{sj.running:>3}  OK:{sj.success:>4}  "
            f"Fail:{sj.failed:>3}  Canceled:{sj.canceled:>3}",
            f"Queued: {pj.queued + sj.queued}  |  OK w/ Errors: {pj.ok_with_errors + sj.ok_with_errors}",
            "",
            f"Critical Alerts: {state.alerts_critical}  |  Warnings: {state.alerts_warning}  "
            f"|  Info: {state.alerts_info}",
        ]
        for i, line in enumerate(lines[: sum_h - 2]):
            color = curses.color_pair(3) if ("Fail" in line and pj.failed > 0) else curses.color_pair(1)
            sum_win.addstr(i + 1, 2, self._truncate(line, left_w - 4), color)
        sum_win.refresh()

        # Panel 2: Storage Systems (top-right)
        stor_win = curses.newwin(sum_h, right_w, 2, left_w)
        self._draw_box(stor_win, "Storage Systems")
        if not state.storage_systems:
            stor_win.addstr(1, 2, "No storage systems found.", curses.color_pair(4))
        for i, stor in enumerate(state.storage_systems[: sum_h - 3]):
            name = stor.get("name", "Unknown")
            status = stor.get("status", "Unknown")
            cap = stor.get("capacity", {})
            used = cap.get("used", 0)
            total = cap.get("total", 1)
            pct = (used / total * 100) if total > 0 else 0
            line = f" {name[:25]:25} {status:10} {pct:.1f}% used"
            stor_win.addstr(i + 1, 2, self._truncate(line, right_w - 4), self._color_for_status(status))
        stor_win.refresh()

        # Panel 3: Running / Queued Sessions (middle, full width)
        sess_y = 2 + sum_h
        eng_h = min(max(len(state.protection_engines) + 3, 4), 8)
        sess_h = min(8, h - sess_y - eng_h - 4)
        sess_h = max(sess_h, 4)
        sess_win = curses.newwin(sess_h, w, sess_y, 0)
        self._draw_box(sess_win, f"Running / Queued Sessions ({len(state.running_sessions)})")
        hdr = f" {'Activity ID':<38} {'Type':<15} {'Status':<12} {'Asset':<25} {'Progress':<10}"
        sess_win.addstr(1, 2, hdr[: w - 4], curses.A_BOLD | curses.color_pair(6))
        for i, job in enumerate(state.running_sessions[: sess_h - 4]):
            jid = job.get("id", "N/A")[:36]
            jtype = job.get("category", "N/A")[:14]
            status = job.get("result", {}).get("status", "N/A")[:11]
            asset = (job.get("name") or job.get("assetName") or "N/A")[:24]
            progress = str(job.get("progress", "N/A"))
            line = f" {jid:<38} {jtype:<15} {status:<12} {asset:<25} {progress:<10}"
            sess_win.addstr(i + 2, 2, self._truncate(line, w - 4), self._color_for_status(status))
        sess_win.refresh()

        # Panel 4: Protection Engines
        eng_y = sess_y + sess_h
        eng_win = curses.newwin(eng_h, w, eng_y, 0)
        self._draw_box(eng_win, f"Protection Engines ({len(state.protection_engines)})")
        hdr = f" {'Name':<30} {'Type':<20} {'State':<15} {'Address':<25}"
        eng_win.addstr(1, 2, hdr[: w - 4], curses.A_BOLD | curses.color_pair(6))
        for i, eng in enumerate(state.protection_engines[: eng_h - 3]):
            name = eng.get("name", "N/A")[:29]
            etype = eng.get("type", "N/A")[:19]
            estate = eng.get("state", eng.get("status", "N/A"))[:14]
            addr = eng.get("address", eng.get("hostname", "N/A"))[:24]
            line = f" {name:<30} {etype:<20} {estate:<15} {addr:<25}"
            eng_win.addstr(i + 2, 2, self._truncate(line, w - 4), self._color_for_status(estate))
        eng_win.refresh()

        # Panel 5: Messages & Alerts (bottom)
        msg_y = eng_y + eng_h
        msg_h = h - msg_y
        if msg_h > 2:
            msg_win = curses.newwin(msg_h, w, msg_y, 0)
            self._draw_box(msg_win, "Messages & Alerts")
            display_msgs = list(state.messages)
            if state.ai_summary:
                display_msgs.insert(0, state.ai_summary)
            for i, msg in enumerate(display_msgs[: msg_h - 2]):
                if msg.startswith("[AI]"):
                    color = curses.color_pair(6) | curses.A_BOLD
                elif msg.startswith("CRITICAL") or "[CRITICAL]" in msg:
                    color = curses.color_pair(3) | curses.A_BOLD
                elif "[WARNING]" in msg:
                    color = curses.color_pair(4)
                else:
                    color = curses.color_pair(1)
                msg_win.addstr(i + 1, 2, self._truncate(msg, w - 4), color)
            msg_win.refresh()

        self.screen.refresh()


# ─── Health HTTP Server ───────────────────────────────────────────────────────

class HealthServer(threading.Thread):
    """Minimal HTTP server exposing GET /health for systemd/NSSM liveness probes."""

    def __init__(self, state: DashboardState, port: int = 8080) -> None:
        super().__init__(daemon=True)
        self._state = state
        self._port = port

    def run(self) -> None:
        state = self._state

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/health":
                    self.send_response(404)
                    self.end_headers()
                    return
                with state.lock:
                    body = json.dumps({
                        "connected":              state.connected,
                        "health_status":          state.health_status,
                        "health_score":           state.health_score,
                        "alerts_critical":        state.alerts_critical,
                        "protection_jobs_failed": state.protection_jobs.failed,
                        "last_update":            state.last_update,
                    }).encode()
                    code = 200 if state.connected else 503
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args) -> None:
                pass  # silence access logs

        with http.server.HTTPServer(("", self._port), _Handler) as httpd:
            httpd.serve_forever()


# ─── Background Daemon ────────────────────────────────────────────────────────

class BackgroundDaemon:
    def __init__(self, client: PPDMClient, config: PPDMConfig, log_dir: str,
                 ai_summarizer: Optional["AISummarizer"] = None,
                 health_port: int = 8080):
        self.client = client
        self.config = config
        self.log_dir = log_dir
        self.state = DashboardState()
        self.collector = DataCollector(client, self.state, config.poll_interval,
                                       ai_summarizer=ai_summarizer)
        self.health_server = HealthServer(self.state, port=health_port)
        self.logger = self._setup_logging()
        self._stop_event = threading.Event()

    def _setup_logging(self) -> logging.Logger:
        os.makedirs(self.log_dir, exist_ok=True)
        log_file = os.path.join(self.log_dir, "ppdmwatch.log")
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger = logging.getLogger("ppdmwatch")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        return logger

    def _check_thresholds(self) -> None:
        if self.state.alerts_critical > 0:
            self.logger.error(f"CRITICAL ALERTS: {self.state.alerts_critical}")
        if self.state.protection_jobs.failed > 0:
            self.logger.warning(f"Failed protection jobs (24h): {self.state.protection_jobs.failed}")
        for stor in self.state.storage_systems:
            cap = stor.get("capacity", {})
            used = cap.get("used", 0)
            total = cap.get("total", 1)
            if total > 0 and (used / total) > 0.85:
                self.logger.warning(
                    f"Storage {stor.get('name')} at {used / total * 100:.1f}% capacity"
                )
        if self.state.ai_summary:
            self.logger.info(self.state.ai_summary)
            self.state.ai_summary = None

    def run(self) -> None:
        self.logger.info("PPDM Watch Agent starting...")
        if not self.client.login():
            self.logger.error("Initial login failed — retrying in background.")
        self.health_server.start()
        self.logger.info(f"Health endpoint: http://0.0.0.0:{self.health_server._port}/health")
        self.collector.start()
        while not self._stop_event.is_set():
            self._check_thresholds()
            self._stop_event.wait(60)
        self.collector.stop()
        self.collector.join()
        self.logger.info("PPDM Watch Agent stopped.")

    def stop(self) -> None:
        self._stop_event.set()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=f"ppdmwatch v{__version__} — nsrwatch for Dell PowerProtect Data Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Interactive TUI:
    ppdmwatch.py --host ppdm01.example.com -u admin -p secret

  Background daemon:
    ppdmwatch.py --host ppdm01.example.com -u admin -p secret --daemon --poll 30

  No SSL verification (lab / self-signed certs):
    ppdmwatch.py --host ppdm01.example.com -u admin -p secret --no-ssl-verify
""",
    )
    p.add_argument("--host", required=True, help="PPDM hostname or IP")
    p.add_argument("--username", "-u", required=True, help="PPDM username")
    p.add_argument("--password", "-p", required=True, help="PPDM password")
    p.add_argument("--port", type=int, default=8443, help="PPDM API port (default: 8443)")
    p.add_argument("--poll", type=int, default=5, help="Polling interval in seconds (default: 5)")
    p.add_argument("--daemon", "-d", action="store_true", help="Run as background daemon")
    p.add_argument("--log-dir", default="/var/log/ppdmwatch", help="Log directory (daemon mode)")
    p.add_argument("--ai-key", default=os.environ.get("ANTHROPIC_API_KEY"), help="Anthropic API key for AI alert summaries (or set ANTHROPIC_API_KEY)")
    p.add_argument("--no-ssl-verify", action="store_true", help="Disable SSL certificate verification")
    p.add_argument("--health-port", type=int, default=8080, help="Port for /health HTTP endpoint in daemon mode (default: 8080)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    config = PPDMConfig(
        host=args.host,
        username=args.username,
        password=args.password,
        port=args.port,
        poll_interval=args.poll,
        verify_ssl=not args.no_ssl_verify,
    )
    client = PPDMClient(config)

    ai_summarizer = AISummarizer(args.ai_key) if args.ai_key and _ANTHROPIC_AVAILABLE else None
    if args.ai_key and not _ANTHROPIC_AVAILABLE:
        print("Warning: anthropic package not installed — AI summaries disabled. Run: pip install anthropic", file=sys.stderr)

    if args.daemon:
        daemon = BackgroundDaemon(client, config, args.log_dir, ai_summarizer=ai_summarizer,
                                  health_port=args.health_port)

        def _signal_handler(sig, frame):
            daemon.stop()

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)
        daemon.run()
    else:
        if not client.login():
            print("Authentication failed. Check --host, --username, and --password.", file=sys.stderr)
            sys.exit(1)
        state = DashboardState()
        collector = DataCollector(client, state, config.poll_interval, ai_summarizer=ai_summarizer)
        collector.start()
        dashboard = Dashboard(state)
        try:
            curses.wrapper(dashboard.run)
        except KeyboardInterrupt:
            pass
        finally:
            collector.stop()
            collector.join()


if __name__ == "__main__":
    main()
