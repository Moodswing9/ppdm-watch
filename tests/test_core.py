"""Unit tests for ppdmwatch pure-function core logic."""

import sys
import os
import types
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

# curses is not available on Windows; inject a stub so ppdmwatch can be imported.
if "curses" not in sys.modules:
    stub = types.ModuleType("curses")
    stub.A_BOLD = 0
    stub.ACS_HLINE = 0
    stub.COLOR_WHITE = stub.COLOR_GREEN = stub.COLOR_RED = 0
    stub.COLOR_YELLOW = stub.COLOR_CYAN = stub.COLOR_MAGENTA = 0
    stub.color_pair = lambda n: 0
    stub.init_pair = lambda *a: None
    stub.newwin = lambda *a: None
    stub.curs_set = lambda n: None
    stub.start_color = lambda: None
    stub.use_default_colors = lambda: None
    sys.modules["curses"] = stub

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ppdmwatch import (
    build_job_summary, build_messages, JobSummary, DashboardState, AISummarizer,
    PPDMConfig, PPDMClient, DataCollector, MCPBridge,
    _MCP_AVAILABLE, __version__,
)


# ── build_job_summary ──────────────────────────────────────────────────────────

def make_job(status: str) -> dict:
    return {"result": {"status": status}}


def test_build_job_summary_empty():
    result = build_job_summary([])
    assert result.total == 0
    assert result.failed == 0
    assert result.success == 0
    assert result.running == 0


def test_build_job_summary_counts_all_statuses():
    jobs = [
        make_job("OK"),
        make_job("OK"),
        make_job("FAILED"),
        make_job("RUNNING"),
        make_job("QUEUED"),
        make_job("CANCELED"),
        make_job("OK_WITH_ERRORS"),
        {"result": {"status": "UNKNOWN_CUSTOM"}},
    ]
    s = build_job_summary(jobs)
    assert s.total == 8
    assert s.success == 2
    assert s.failed == 1
    assert s.running == 1
    assert s.queued == 1
    assert s.canceled == 1
    assert s.ok_with_errors == 1
    assert s.unknown == 1


def test_build_job_summary_missing_result_field():
    jobs = [{"id": "abc"}, {"result": {}}]
    s = build_job_summary(jobs)
    assert s.total == 2
    assert s.unknown == 2


def test_build_job_summary_completed_property():
    jobs = [make_job("OK"), make_job("FAILED"), make_job("CANCELED"), make_job("OK_WITH_ERRORS")]
    s = build_job_summary(jobs)
    assert s.completed == 4


def test_build_job_summary_returns_job_summary_instance():
    result = build_job_summary([make_job("OK")])
    assert isinstance(result, JobSummary)


# ── build_messages ─────────────────────────────────────────────────────────────

def make_alert(severity: str, message: str) -> dict:
    return {"severity": severity, "message": message}


def test_build_messages_no_alerts():
    msgs = build_messages([], [])
    assert msgs == []


def test_build_messages_critical_prefix():
    critical = [make_alert("CRITICAL", "disk full")]
    msgs = build_messages(critical, critical)
    assert msgs[0].startswith("CRITICAL: 1 critical alert(s)")


def test_build_messages_alert_format():
    all_alerts = [make_alert("WARNING", "heap usage high")]
    msgs = build_messages([], all_alerts)
    assert "[WARNING] heap usage high" in msgs[0]


def test_build_messages_truncates_long_message():
    long_msg = "x" * 200
    msgs = build_messages([], [make_alert("INFO", long_msg)])
    assert len(msgs[0]) <= len("[INFO] ") + 80


def test_build_messages_at_most_five_alerts():
    alerts = [make_alert("INFO", f"alert {i}") for i in range(10)]
    msgs = build_messages([], alerts)
    assert len(msgs) == 5


def test_build_messages_critical_plus_alerts_ordering():
    critical = [make_alert("CRITICAL", "node down")]
    all_alerts = [make_alert("WARNING", "disk 80%")]
    msgs = build_messages(critical, all_alerts)
    assert msgs[0].startswith("CRITICAL:")
    assert "[WARNING]" in msgs[1]


# ── AISummarizer._should_predict ───────────────────────────────────────────────

def test_should_predict_false_when_history_too_short():
    state = DashboardState()
    state.failed_jobs_history.append(1)
    state.failed_jobs_history.append(2)
    assert AISummarizer._should_predict(state) is False


def test_should_predict_true_on_rising_failures():
    state = DashboardState()
    for v in [1, 2, 3]:
        state.failed_jobs_history.append(v)
    assert AISummarizer._should_predict(state) is True


def test_should_predict_false_on_stable_failures():
    state = DashboardState()
    for v in [3, 3, 3]:
        state.failed_jobs_history.append(v)
    assert AISummarizer._should_predict(state) is False


def test_should_predict_true_on_rising_storage():
    state = DashboardState()
    for v in [70.0, 75.5, 82.1]:
        state.storage_pct_history.append(v)
    assert AISummarizer._should_predict(state) is True


# ── PPDMClient.login ───────────────────────────────────────────────────────────

def test_ppdm_login_returns_true_on_success():
    config = PPDMConfig(host="ppdm.test", username="admin", password="pass")
    client = PPDMClient(config)
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"access_token": "tok123"}
    with patch.object(client.session, "post", return_value=mock_resp):
        result = client.login()
    assert result is True
    assert client.token == "tok123"


def test_ppdm_login_sets_authorization_header():
    config = PPDMConfig(host="ppdm.test", username="admin", password="pass")
    client = PPDMClient(config)
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"access_token": "hdr-tok"}
    with patch.object(client.session, "post", return_value=mock_resp):
        client.login()
    assert client.session.headers.get("Authorization") == "Bearer hdr-tok"


def test_ppdm_login_returns_false_on_exception():
    config = PPDMConfig(host="ppdm.test", username="admin", password="pass")
    client = PPDMClient(config)
    with patch.object(client.session, "post", side_effect=Exception("connection refused")):
        result = client.login()
    assert result is False
    assert client.token is None


# ── PPDMClient._ensure_auth ────────────────────────────────────────────────────

def test_ensure_auth_skips_when_token_valid():
    config = PPDMConfig(host="ppdm.test", username="admin", password="pass")
    client = PPDMClient(config)
    client.token = "valid-token"
    client.token_expiry = datetime.now(timezone.utc).timestamp() + 7200
    with patch.object(client, "login") as mock_login:
        client._ensure_auth()
    mock_login.assert_not_called()


def test_ensure_auth_retries_three_times_on_total_failure():
    config = PPDMConfig(host="ppdm.test", username="admin", password="pass")
    client = PPDMClient(config)
    client.token = None
    with patch.object(client, "login", return_value=False) as mock_login:
        with patch("ppdmwatch.time.sleep"):
            client._ensure_auth()
    assert mock_login.call_count == 3


def test_ensure_auth_stops_retrying_after_first_success():
    config = PPDMConfig(host="ppdm.test", username="admin", password="pass")
    client = PPDMClient(config)
    client.token = None
    with patch.object(client, "login", side_effect=[False, True]) as mock_login:
        with patch("ppdmwatch.time.sleep"):
            client._ensure_auth()
    assert mock_login.call_count == 2


# ── DataCollector ──────────────────────────────────────────────────────────────

def _make_mock_ppdm_client():
    mock = MagicMock()
    mock.get_activities.return_value = []
    mock.get_storage_systems.return_value = []
    mock.get_alerts.return_value = []
    mock.get_system_health.return_value = {}
    mock.get_protection_engines.return_value = []
    return mock


def test_data_collector_sets_connected_true_on_success():
    state = DashboardState()
    collector = DataCollector(_make_mock_ppdm_client(), state, interval=5)
    collector._collect()
    assert state.connected is True


def test_data_collector_counts_protection_jobs():
    client = _make_mock_ppdm_client()
    client.get_activities.side_effect = [
        [{"result": {"status": "OK"}}, {"result": {"status": "FAILED"}}],
        [],
        [],
    ]
    state = DashboardState()
    collector = DataCollector(client, state, interval=5)
    collector._collect()
    assert state.protection_jobs.success == 1
    assert state.protection_jobs.failed == 1


def test_data_collector_appends_storage_pct_history():
    client = _make_mock_ppdm_client()
    client.get_storage_systems.return_value = [
        {"capacity": {"used": 80, "total": 100}},
    ]
    state = DashboardState()
    collector = DataCollector(client, state, interval=5)
    collector._collect()
    assert len(state.storage_pct_history) == 1
    assert abs(state.storage_pct_history[-1] - 80.0) < 0.01


def test_data_collector_run_catches_error_and_marks_disconnected():
    state = DashboardState()
    collector = DataCollector(_make_mock_ppdm_client(), state, interval=0)
    calls = {"n": 0}

    def _fail_once():
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("PPDM unreachable")
        collector.stop()

    with patch.object(collector, "_collect", side_effect=_fail_once):
        collector.run()

    assert state.connected is False
    assert state.error == "PPDM unreachable"


# ── Version ────────────────────────────────────────────────────────────────────

def test_version_is_v2():
    assert __version__ == "2.0.0"


# ── MCP availability flag ──────────────────────────────────────────────────────

def test_mcp_available_is_bool():
    assert isinstance(_MCP_AVAILABLE, bool)


# ── MCPBridge ─────────────────────────────────────────────────────────────────

def test_mcp_bridge_init():
    state = DashboardState()
    bridge = MCPBridge(state)
    assert bridge._state is state


def test_mcp_bridge_run_exits_when_mcp_not_available():
    import ppdmwatch
    state = DashboardState()
    bridge = MCPBridge(state)
    original = ppdmwatch._MCP_AVAILABLE
    try:
        ppdmwatch._MCP_AVAILABLE = False
        with pytest.raises(SystemExit):
            bridge.run()
    finally:
        ppdmwatch._MCP_AVAILABLE = original


def test_mcp_bridge_state_snapshot_structure():
    """Verify that DashboardState fields used by MCPBridge tools have the expected structure."""
    import json
    state = DashboardState()
    state.protection_jobs = JobSummary(total=10, running=2, success=7, failed=1)
    state.last_update = "2026-07-10T00:00:00Z"
    state.connected = True
    state.health_score = 95
    state.health_status = "GOOD"
    state.alerts_critical = 0
    state.alerts_warning = 1
    state.alerts_info = 3

    # Validate the JSON snapshot shape used by get_job_summary
    with state.lock:
        pj = state.protection_jobs
        snap = json.dumps({
            "protection_jobs": {
                "total": pj.total, "running": pj.running, "queued": pj.queued,
                "success": pj.success, "failed": pj.failed,
            },
            "connected": state.connected,
            "last_update": state.last_update,
        })
    result = json.loads(snap)
    assert result["protection_jobs"]["total"] == 10
    assert result["protection_jobs"]["failed"] == 1
    assert result["connected"] is True

    # Validate the JSON snapshot shape used by get_active_alerts
    with state.lock:
        alerts_snap = json.loads(json.dumps({
            "critical": state.alerts_critical,
            "warning": state.alerts_warning,
            "info": state.alerts_info,
        }))
    assert alerts_snap["critical"] == 0
    assert alerts_snap["warning"] == 1
