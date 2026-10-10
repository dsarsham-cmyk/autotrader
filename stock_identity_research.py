"""Chronological stock intercept/slope hypothesis with unchanged trade risk."""
import argparse
import hashlib
import json
from pathlib import Path
import warnings
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps,walk
from causal_sparse_simulator import portfolio
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from prospective_series_audit import accounting_metrics
from split_context_audit import events_from_pages,normalized_opening_rows
from split_predictive_research import assert_reference,flatten
from stock_identity_features import MODES,augment,feature_names

PROTOCOL = dict(feature_sets=MODES,models=['logistic','boosted'],gates=[.5,.65,.9],
    cost_delay_variants=[(10,16),(20,16),(10,17)],warmup_dates=240,calibration_dates=60,test_block_dates=20,
    stop=.01,target=.004,horizon_minutes=60,stock_cap=.01,category_cap=.05,
    max_positions=3,planned_risk=.0005,orders=False)


def run(data,reference,input_audit,output):
    original = json.loads(reference.read_bytes())
    if original['status'] != 'completed_exposed_split_predictive_comparison':
        raise ValueError('Completed split-normalized reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() != expected:
            raise ValueError('Reference source changed')
    if hashlib.sha256(input_audit.read_bytes()).hexdigest() != original['input_audit_sha256']:
        raise ValueError('Original input audit changed')
    receipt_path = input_audit.parent/'corporate_actions_receipt.json'
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != original['corporate_action_receipt_sha256']:
        raise ValueError('Original split receipt changed')
    observations,evidence = load_observations(data)
    if evidence != original['evidence']:
        raise ValueError('Matched historical observations changed')
    receipt = json.loads(receipt_path.read_bytes())
    events = events_from_pages(receipt['pages'],list(observations))
    by_date,reasons,applications = normalized_opening_rows(observations,events)
    raw_rows,market = flatten(by_date),market_maps(observations)
    report = dict(status='running_exposed_stock_identity_comparison',protocol=PROTOCOL,
        cases=[],evidence=evidence,applications=applications,orders=False,production_approved=False,
        independent_validation_pass=False,
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        input_audit_sha256=original['input_audit_sha256'],
        dependency_sha256=dict(original['dependency_sha256'], **{name:
            hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in
            ['stock_identity_features.py','stock_identity_research.py']}),
        limitations=['Previously exposed outcomes, not independent financial validation',
            'Fixed present-day stock vocabulary retains survivorship/selection bias',
            'More parameters may overfit; no future-derived vocabulary or test-result model selection',
            'Conditional past simulated-fill labels, historical revisions/unverified original receipts/fill assumptions remain',
            'Identity does not establish sector causality or change stock/category/stop/cost risk constraints',
            'Production and frozen prospective model untouched'])
    output.mkdir(parents=True,exist_ok=True)
    with threadpool_limits(limits=1):
        for mode in MODES:
            rows = [augment(row,mode) for row in raw_rows]
            for model in PROTOCOL['models']:
                old = next(c for c in original['cases'] if c['feature_set'] == 'date_effective_split_context' and c['model'] == model)
                fitting_warnings = []
                if mode == 'price_only':
                    forecasts,folds = old['forecasts'],old['folds']
                    indexed = {(r['date'],r['symbol']):r for r in rows}
                    if any(any(f[k] != indexed[(f['date'],f['symbol'])][k] for k in ['features','signal_price'])
                           for f in forecasts):
                        raise ValueError('Original control input features changed')
                else:
                    with warnings.catch_warnings(record=True) as observed:
                        warnings.simplefilter('always')
                        forecasts,folds = walk(rows,market,model)
                    fitting_warnings = [dict(category=w.category.__name__,message=str(w.message)) for w in observed]
                    if fitting_warnings:
                        raise ValueError('Identity model has unresolved fitting warnings: '+json.dumps(fitting_warnings))
                if [(f['test_first'],f['test_last']) for f in folds] != [
                        (f['test_first'],f['test_last']) for f in old['folds']]:
                    raise ValueError('Matched forecast spans changed')
                known_test = sum(f['known_filled_test'] for f in folds)
                pooled_brier = sum(f['brier_known_filled']*f['known_filled_test'] for f in folds if f['known_filled_test'])/known_test
                case = dict(model=model,feature_set=mode,feature_names=feature_names(mode),folds=folds,
                    forecasts=forecasts,outcomes=[],fitting_warnings=fitting_warnings,
                    descriptive_brier_known_filled=pooled_brier,known_filled_test_candidates=known_test)
                for gate in PROTOCOL['gates']:
                    for cost,delay in PROTOCOL['cost_delay_variants']:
                        result = portfolio(forecasts,market,gate,cost,delay)
                        prefix = dict(result,profit_usd=result['known_prefix_profit_usd'])
                        result['known_prefix_metrics'] = accounting_metrics(prefix,forecasts)
                        result['known_prefix_cost_diagnostic'] = diagnostic(prefix)
                        check(result)
                        if mode == 'price_only':
                            expected = next(o for o in old['outcomes'] if
                                (o['threshold'],o['costs_bps'],o['delay']) == (gate,cost,delay))
                            assert_reference(result,expected)
                        case['outcomes'].append(result)
                        if cost == 10 and delay == 16:
                            print(json.dumps(dict(model=model,features=mode,gate=gate,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],complete=result['full_period_coverage_complete'],
                                descriptive_brier_known_filled=pooled_brier)),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status'] = 'completed_exposed_stock_identity_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--reference',type=Path,default=Path('research_runs/split_predictive/results.json'))
    parser.add_argument('--input-audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/stock_identity'))
    args = parser.parse_args()
    run(args.data,args.reference,args.input_audit,args.output)
