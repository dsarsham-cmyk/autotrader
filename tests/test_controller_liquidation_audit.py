from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from snapshot import controller_audit_check
from paper_safety import apply_policy


NOW = datetime(2026, 10, 22, 18, 51, tzinfo=timezone.utc)


def safety(reason="liquidation confirmed; no re-entry today", day="2026-10-22",
           cause_reason="broker protection missing or unverified"):
    return {"fresh": True, "errors": [], "entry_blocked": True, "reason": reason,
            "liquidation_cause": {"day": day, "reason": cause_reason,
                                  "fatal_protection_symbols": ["SPXL"],
                                  "completed_at": "2026-10-22T13:37:10Z"}}


def test_completed_current_protection_fault_is_not_healthy():
    value = safety()
    original = deepcopy(value)
    check = controller_audit_check(value, NOW)
    assert check["status"] == "bad"
    assert "SPXL" in check["detail"] and "today" in check["detail"]
    assert value == original


def test_generic_legacy_completion_is_unverified():
    value = safety()
    value.pop("liquidation_cause")
    assert controller_audit_check(value, NOW)["status"] == "warn"


def test_null_cause_is_unverified_not_an_exception():
    value = safety()
    value["liquidation_cause"] = None
    assert controller_audit_check(value, NOW)["status"] == "warn"


def test_real_policy_end_of_day_reason_is_nonfatal():
    state = {"day": "2026-10-22"}
    clock = {"timestamp": "2026-10-22T19:56:00Z", "next_close": "2026-10-22T20:00:00Z", "is_open": True}
    policy = {"entry_loss_limit_pct": .005, "daily_loss_limit_pct": .01,
              "starting_equity": 100000, "max_account_loss_pct": .10,
              "max_drawdown_pct": .10, "close_buffer_seconds": 300}
    apply_policy(state, {"equity": "100000", "last_equity": "100000"}, clock, [], policy)
    assert state["liquidating"] == "end of session"
    assert controller_audit_check({"fresh": True, **state}, NOW)["status"] == "warn"


@pytest.mark.parametrize("completed", [False, True])
def test_normal_end_of_day_is_not_protection_failure(completed):
    value = safety(cause_reason="end of session")
    value["liquidation_cause"]["fatal_protection_symbols"] = []
    if not completed:
        value["liquidating"] = "end of session"
        value["reason"] = "end of session"
    assert controller_audit_check(value, NOW)["status"] == ("good" if completed else "warn")


def test_previous_day_incident_is_not_current_failure():
    value = safety(reason="", day="2026-10-21")
    value["entry_blocked"] = False
    assert controller_audit_check(value, NOW)["status"] == "good"


@pytest.mark.parametrize("day", [None, "garbage", "2026-10-99", "2026-10-23"])
def test_unknown_or_future_incident_date_is_not_healthy(day):
    assert controller_audit_check(safety(reason="", day=day), NOW)["status"] == "warn"


def test_market_date_uses_new_york_not_utc():
    now = datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)
    assert controller_audit_check(safety(), now)["status"] == "bad"


@pytest.mark.parametrize("extra", [{"fresh": False}, {"errors": ["timeout"]}])
def test_missing_freshness_or_errors_fail_closed(extra):
    value = {"fresh": True, "errors": [], **extra}
    assert controller_audit_check(value, NOW)["status"] == "bad"


def test_dashboard_cause_is_rendered_as_text_not_html():
    html = Path("index.html").read_text(encoding="utf-8")
    assert '$("safetyCause").textContent=liquidationCauseText(s);' in html
    assert '$("safetyCause").innerHTML' not in html
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for pure renderer unit test")
    start = html.index("function liquidationCauseText(")
    end = html.index("function renderSafety", start)
    attack = "<img src=x onerror=alert(1)>"
    fixture = safety()
    fixture["liquidation_cause"].update(reason=attack, observed_at="2026-10-22T13:36:05Z")
    fixture["liquidation_cause"]["fatal_protection_symbols"] = [attack]
    script = html[start:end] + "\nprocess.stdout.write(liquidationCauseText(" + json.dumps(fixture) + "));"
    result = subprocess.run([node, "-e", script], text=True, capture_output=True, check=True)
    assert attack in result.stdout
    assert "2026-10-22T13:36:05Z" in result.stdout
    assert "Flattening confirmed" in result.stdout


def test_audit_messages_never_parse_server_text_as_html():
    html = Path("index.html").read_text(encoding="utf-8")
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node unavailable for DOM renderer unit test")
    start = html.index("function renderAuditMessages(")
    end = html.index("function auditView", start)
    attack = '<img src=x onerror=alert(1)>'
    stub = '''
    class Element {
      constructor(){this.children=[];this.textContent="";this.className="";}
      set innerHTML(value){throw Error("HTML parsing forbidden");}
      append(...values){this.children.push(...values);}
      replaceChildren(...values){this.children=values;}
    }
    const elements={auditChecks:new Element(),auditCallout:new Element()};
    const $=id=>elements[id];
    const document={createElement:()=>new Element()};
    '''
    script = stub + html[start:end] + "\nrenderAuditMessages(" + json.dumps({"summary": attack, "checks": [
        {"status": attack, "label": attack, "detail": attack}]}) + ");"
    script += '''
    if(elements.auditChecks.children[0].className!=="check warn")throw Error("unsafe class");
    console.log(elements.auditCallout.children[1].textContent);
    console.log(elements.auditChecks.children[0].children[1].textContent);
    '''
    result = subprocess.run([node, "-e", script], text=True, capture_output=True, check=True)
    assert result.stdout.count(attack) == 2
