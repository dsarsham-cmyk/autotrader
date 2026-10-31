"""Run the actual workflow fallback snippet; no provider or broker access."""
import json
from pathlib import Path
import textwrap

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = [
    ('predictive-prospective.yml', 'cloud_status.json',
     '1365f9a6efa87210fd9b3e053d4195f191ebc178'),
    ('causal-shadow-prospective.yml', 'causal_shadow_cloud_status.json',
     '7dec3a115c0ad4c0fef7edca7f5e724679e4228f'),
]


def snippet(workflow):
    text = (ROOT / '.github/workflows' / workflow).read_text()
    block = text.split('      - name: Record unavailable evidence explicitly\n', 1)[1]
    block = block.split('      - name:', 1)[0]
    assert 'if: always()' in block
    code = block.split("          python - <<'PY'\n", 1)[1].split('          PY\n', 1)[0]
    return compile(textwrap.dedent(code), workflow, 'exec')


@pytest.mark.parametrize('workflow,status_name,pinned', WORKFLOWS)
@pytest.mark.parametrize('eligible', [False, True])
def test_missing_status_never_becomes_no_trade_or_forecast(
        tmp_path, monkeypatch, workflow, status_name, pinned, eligible):
    code = snippet(workflow)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PLAN_RUN', str(eligible).lower())
    monkeypatch.setenv('VALIDATE_ONLY', 'false')
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    if eligible:
        with pytest.raises(SystemExit):
            exec(code, {})
    else:
        exec(code, {})
    value = json.loads((tmp_path / 'research_runs' / status_name).read_text())
    assert value['status'] == 'evidence_unavailable_not_a_no_trade_day'
    assert value['recorded_sessions'] == 0
    assert value['absence_is_no_trade'] is False
    assert value['orders'] is False and value['production_approved'] is False
    assert value['workflow_run_id'] == '123'
    text = (ROOT / '.github/workflows' / workflow).read_text()
    assert f'ref: {pinned}' in text
    assert 'if-no-files-found: error' in text


@pytest.mark.parametrize('workflow,status_name,pinned', WORKFLOWS)
def test_existing_collector_status_is_not_overwritten(
        tmp_path, monkeypatch, workflow, status_name, pinned):
    code = snippet(workflow)
    monkeypatch.chdir(tmp_path)
    path = tmp_path / 'research_runs' / status_name
    path.parent.mkdir()
    original = b'{"status":"collection_failed_no_forecast_claim"}'
    path.write_bytes(original)
    exec(code, {})
    assert path.read_bytes() == original


@pytest.mark.parametrize('workflow,status_name,pinned', WORKFLOWS)
def test_missing_manual_validation_status_fails(
        tmp_path, monkeypatch, workflow, status_name, pinned):
    code = snippet(workflow)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('PLAN_RUN', 'false')
    monkeypatch.setenv('VALIDATE_ONLY', 'true')
    with pytest.raises(SystemExit):
        exec(code, {})
    value = json.loads((tmp_path / 'research_runs' / status_name).read_text())
    assert value['validation_requested'] is True
    assert value['recorded_sessions'] == 0
