import run_all
import json


class _Process:
    def __init__(self, code=None):
        self.code = code

    def poll(self):
        return self.code


def test_health_is_online_when_both_scenarios_run():
    procs = [
        ("config_high.yaml", "HIGH RISK", _Process()),
        ("config_low.yaml", "LOW RISK", _Process()),
    ]

    health = run_all.build_health(procs, {"HIGH RISK": 0, "LOW RISK": 1}, None)

    assert health["ok"] is True
    assert health["mode"] == "paper"
    assert health["scenarios"]["high"]["running"] is True
    assert health["scenarios"]["low"]["restarts"] == 1


def test_health_reports_a_stopped_scenario():
    procs = [
        ("config_high.yaml", "HIGH RISK", _Process(1)),
        ("config_low.yaml", "LOW RISK", _Process()),
    ]

    health = run_all.build_health(procs, {}, "2026-09-17")

    assert health["ok"] is False
    assert health["scenarios"]["high"]["running"] is False
    assert health["last_daily_report"] == "2026-09-17"


def test_live_dashboard_refresh_publishes_snapshot(monkeypatch, tmp_path):
    dashboard = tmp_path / "dashboard.json"
    payload = {"last_updated": "2026-09-18T00:00:00Z", "account": {"equity": 101000}}

    import snapshot
    monkeypatch.setattr(snapshot, "DASHBOARD", str(dashboard))
    monkeypatch.setattr(snapshot, "main", lambda: dashboard.write_text(
        json.dumps(payload), encoding="utf-8"
    ))
    run_all.LIVE_DASHBOARD_STATE.clear()

    result = run_all.refresh_live_dashboard_once()

    assert result == payload
    assert run_all.LIVE_DASHBOARD_STATE == payload
