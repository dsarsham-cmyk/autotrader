"""Does price/identity learning beat a chronological base-rate forecast?"""
import argparse
import hashlib
import json
from pathlib import Path
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from causal_sparse_simulator import path,portfolio
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from past_frequency_predictor import KINDS,predict
from predictive_portfolio_research import partition
from prospective_series_audit import accounting_metrics
from split_context_audit import events_from_pages,normalized_opening_rows
from split_predictive_research import flatten


def run(data,reference,input_audit,output):
    original = json.loads(reference.read_bytes())
    if original['status'] != 'completed_exposed_stock_identity_comparison':
        raise ValueError('Completed stock identity reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() != expected:
            raise ValueError('Reference source changed')
    if hashlib.sha256(input_audit.read_bytes()).hexdigest() != original['input_audit_sha256']:
        raise ValueError('Split input audit changed')
    audit = json.loads(input_audit.read_bytes())
    receipt_path = input_audit.parent/'corporate_actions_receipt.json'
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != audit['corporate_action_receipt_sha256']:
        raise ValueError('Split receipt changed')
    observations,evidence = load_observations(data)
    if evidence != original['evidence']:
        raise ValueError('Historical observation bytes changed')
    receipt = json.loads(receipt_path.read_bytes())
    events = events_from_pages(receipt['pages'],list(observations))
    by_date,reasons,applications = normalized_opening_rows(observations,events)
    rows,dates,market = flatten(by_date),sorted(by_date),market_maps(observations)
    outcomes = {(r['date'],r['symbol']):path(market[r['date']][r['symbol']],r['signal_price']) for r in rows}
    labels = {key:o['label'] for key,o in outcomes.items() if o is not None and o['filled']}
    report = dict(status='running_exposed_past_frequency_comparison',evidence=evidence,
        protocol=dict(models=KINDS,prior_row_mass=20,recent_dates=60,warmup_dates=240,
            test_block_dates=20,gates=[.5,.65,.9],cost_delay_variants=[(10,16),(20,16),(10,17)],
            stock_cap=.01,category_cap=.05,max_positions=3,planned_risk=.0005,
            stop=.01,target=.004,horizon_minutes=60,orders=False),
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        input_audit_sha256=original['input_audit_sha256'],
        dependency_sha256=dict(original['dependency_sha256'],**{name:
            hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in
            ['past_frequency_predictor.py','past_frequency_research.py']}),
        cases=list(original['cases']),brier_comparisons=[],orders=False,
        production_approved=False,independent_validation_pass=False,
        limitations=['Exposed historical outcomes, not independent forward validation',
            'Frequency forecasts are conditional on past modeled fills, not unconditional profit promises',
            'Fixed shrinkage mass20 not optimized using test profit; same past global counts inform shrinkage',
            'Descriptive Brier scores use known-filled future outcomes only for scoring, not candidate filtering',
            'Equal-probability selection retains fixed alphabetical tie rule, not future outcomes',
            'Survivorship/revisions/original delivery/cost/fill assumptions remain; frozen/production untouched'])
    output.mkdir(parents=True,exist_ok=True)
    reference_dates = [(f['test_first'],f['test_last']) for f in original['cases'][0]['folds']]
    for kind in KINDS:
        forecasts,folds = [],[]
        for start in range(240,len(dates),20):
            cal_dates,test_dates = dates[start-60:start],dates[start:start+20]
            cal,test = [partition(rows,d) for d in [cal_dates,test_dates]]
            cal = [r for r in cal if (r['date'],r['symbol']) in labels]
            probabilities,counts = predict(cal,test,labels,kind)
            forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
            known = [(i,labels[(r['date'],r['symbol'])]) for i,r in enumerate(test)
                     if (r['date'],r['symbol']) in labels]
            squared_error = sum((probabilities[i]-label)**2 for i,label in known)
            folds.append(dict(train_last=dates[start-61],cal_first=cal_dates[0],cal_last=cal_dates[-1],
                test_first=test_dates[0],test_last=test_dates[-1],frequency_evidence=counts,
                known_filled_test=len(known),squared_error_known_filled=float(squared_error)))
        if [(f['test_first'],f['test_last']) for f in folds] != reference_dates:
            raise ValueError('Matched forecast dates changed')
        known_count = sum(f['known_filled_test'] for f in folds)
        brier = sum(f['squared_error_known_filled'] for f in folds)/known_count
        if any(c['known_filled_test_candidates'] != known_count for c in original['cases']):
            raise ValueError('Matched known-filled scoring membership count changed')
        # Check exact membership/labels, not merely matching sample counts.
        actual_keys = [(r['date'],r['symbol']) for r in forecasts if (r['date'],r['symbol']) in labels]
        for old in original['cases']:
            old_keys = [(r['date'],r['symbol']) for r in old['forecasts'] if (r['date'],r['symbol']) in labels]
            if old_keys != actual_keys:
                raise ValueError('Known outcome scoring membership changed')
            scored = sum((r['probability']-labels[(r['date'],r['symbol'])])**2 for r in old['forecasts']
                         if (r['date'],r['symbol']) in labels)/known_count
            if abs(scored-old['descriptive_brier_known_filled'])>1e-12:
                raise ValueError('Original Brier not reproduced')
            report['brier_comparisons'].append(dict(baseline=kind,model=old['model'],
                feature_set=old['feature_set'],known_filled_candidates=known_count,
                baseline_brier=brier,model_brier=scored,model_minus_baseline=scored-brier))
        case = dict(model=kind,feature_set='past_outcome_frequency_only',folds=folds,
            forecasts=forecasts,outcomes=[],known_filled_test_candidates=known_count,
            descriptive_brier_known_filled=brier)
        for gate in [.5,.65,.9]:
            for cost,delay in [(10,16),(20,16),(10,17)]:
                result = portfolio(forecasts,market,gate,cost,delay)
                prefix = dict(result,profit_usd=result['known_prefix_profit_usd'])
                result['known_prefix_metrics'] = accounting_metrics(prefix,forecasts)
                result['known_prefix_cost_diagnostic'] = diagnostic(prefix)
                check(result);case['outcomes'].append(result)
                if cost==10 and delay==16:
                    print(json.dumps(dict(model=kind,gate=gate,active_days=result['active_days'],
                        win_rate=result['active_day_win_rate_pct'],net_usd=result['profit_usd'],
                        complete=result['full_period_coverage_complete'],descriptive_brier_known_filled=brier)),flush=True)
        report['cases'].append(case)
        (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status'] = 'completed_exposed_past_frequency_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--reference',type=Path,default=Path('research_runs/stock_identity/results.json'))
    parser.add_argument('--input-audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/past_frequency'))
    args = parser.parse_args()
    run(args.data,args.reference,args.input_audit,args.output)
