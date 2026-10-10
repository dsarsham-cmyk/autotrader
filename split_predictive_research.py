"""Matched retrospective split-unit input ablation, never production trading."""
import argparse
import hashlib
import json
from pathlib import Path

from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations, opening_rows
from causal_sparse_research import PROTOCOL, market_maps, walk
from causal_sparse_simulator import portfolio
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from prospective_series_audit import accounting_metrics
from split_context_audit import URL, events_from_pages, normalized_opening_rows


def flatten(by_date):
    return [row for date, stocks in sorted(by_date.items()) for symbol, row in sorted(stocks.items())]


def assert_reference(result, expected):
    for key in ['profit_usd', 'daily', 'trades', 'unknown_selections']:
        if result[key] != expected[key]:
            raise ValueError('Original sparse portfolio reference not reproduced')


def run(data, reference, audit_path, output):
    original = json.loads(reference.read_bytes())
    if original['status'] != 'completed_exposed_causal_sparse_research':
        raise ValueError('Completed sparse reference required')
    for name, expected in original['dependency_sha256'].items():
        actual = hashlib.sha256(Path(name).read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if actual != expected:
            raise ValueError('Original reference dependency changed')
    input_audit = json.loads(audit_path.read_bytes())
    if input_audit['status'] != 'exposed_historical_split_input_audit' or not input_audit['no_event_reference_exact']:
        raise ValueError('Completed matched split input audit required')
    receipt_path = audit_path.parent/'corporate_actions_receipt.json'
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != input_audit['corporate_action_receipt_sha256']:
        raise ValueError('Corporate action receipt changed')
    receipt = json.loads(receipt_path.read_bytes())
    if receipt['url'] != URL or not receipt['pages'] or receipt['pages'][-1].get('next_page_token') is not None:
        raise ValueError('Complete own action receipt required')
    observations, evidence = load_observations(data)
    if evidence != original['evidence'] or evidence != input_audit['evidence']:
        raise ValueError('Historical input bytes changed')
    before, reasons = opening_rows(observations)
    events = events_from_pages(receipt['pages'], list(observations))
    after, normalized_reasons, applications = normalized_opening_rows(observations, events)
    if reasons != normalized_reasons or {d: sorted(s) for d,s in before.items()} != {
            d: sorted(s) for d,s in after.items()}:
        raise ValueError('Candidate dates/symbols must be unchanged')
    base_rows, normalized_rows = flatten(before), flatten(after)
    for raw, normalized in zip(base_rows, normalized_rows):
        if any(raw[k] != normalized[k] for k in ['date','symbol','signal_price']):
            raise ValueError('Raw execution units/candidate changed')
    market = market_maps(observations)
    output.mkdir(parents=True, exist_ok=True)
    report = dict(status='running_exposed_split_predictive_comparison', protocol=PROTOCOL,
        evidence=evidence, applications=applications, cases=[], orders=False, production_approved=False,
        independent_validation_pass=False,
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        input_audit_sha256=hashlib.sha256(audit_path.read_bytes()).hexdigest(),
        corporate_action_receipt_sha256=input_audit['corporate_action_receipt_sha256'],
        dependency_sha256=dict(original['dependency_sha256'], **{name:
            hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in
            ['split_context_audit.py','split_predictive_research.py','finbert_comparison_audit.py']}),
        limitations=['Exposed historical dates, not independent validation',
            'Current corporate-action records do not prove original announcement receipt',
            'Only split unit normalization, not dividend/merger/survivorship corrections',
            'Same raw intraday execution prices, labels, budgets, costs and delay assumptions',
            'Frozen prospective benchmark and production engine unchanged'])
    with threadpool_limits(limits=1):
        for feature_set in ['original_raw_context','date_effective_split_context']:
            for model in PROTOCOL['models']:
                old_case = next(case for case in original['cases'] if case['model'] == model)
                if feature_set == 'original_raw_context':
                    forecasts, folds = old_case['forecasts'], old_case['folds']
                    raw_index = {(r['date'],r['symbol']):r for r in base_rows}
                    for forecast in forecasts:
                        raw = raw_index[(forecast['date'],forecast['symbol'])]
                        if any(raw[key] != forecast[key] for key in ['features','signal_price']):
                            raise ValueError('Saved reference forecast inputs changed')
                else:
                    forecasts, folds = walk(normalized_rows, market, model)
                    if [(f['test_first'],f['test_last']) for f in folds] != [
                            (f['test_first'],f['test_last']) for f in old_case['folds']]:
                        raise ValueError('Matched test spans changed')
                case = dict(model=model, feature_set=feature_set, folds=folds, forecasts=forecasts, outcomes=[])
                for gate in PROTOCOL['thresholds']:
                    for cost, delay in [(10,16),(20,16),(10,17)]:
                        result = portfolio(forecasts, market, gate, cost, delay)
                        prefix = dict(result, profit_usd=result['known_prefix_profit_usd'])
                        result['known_prefix_metrics'] = accounting_metrics(prefix, forecasts)
                        result['known_prefix_cost_diagnostic'] = diagnostic(prefix)
                        check(result)
                        if feature_set == 'original_raw_context':
                            expected = next(r for r in old_case['outcomes'] if
                                (r['threshold'],r['costs_bps'],r['delay']) == (gate,cost,delay))
                            assert_reference(result,expected)
                        case['outcomes'].append(result)
                        if cost == 10 and delay == 16:
                            print(json.dumps(dict(feature_set=feature_set, model=model, gate=gate,
                                active_days=result['active_days'], win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'], complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status'] = 'completed_exposed_split_predictive_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--reference',type=Path,default=Path('research_runs/causal_sparse/results.json'))
    parser.add_argument('--audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/split_predictive'))
    args = parser.parse_args()
    run(args.data,args.reference,args.audit,args.output)
