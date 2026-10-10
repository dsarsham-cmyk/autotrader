"""Fixed recency half-lives on split-normalized inputs; NO ORDERS."""
import argparse
import hashlib
import json
from pathlib import Path
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from causal_sparse_simulator import path,portfolio
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from predictive_portfolio_research import partition
from prospective_series_audit import accounting_metrics
from recency_predictor import fit
from split_context_audit import events_from_pages,normalized_opening_rows
from split_predictive_research import assert_reference,flatten

PROTOCOL = dict(half_lives_sessions=[None,60,120],models=['logistic','boosted'],gates=[.5,.65,.9],
    cost_delay_variants=[(10,16),(20,16),(10,17)],weighted_scaler=True,weighted_classifier=True,
    weighted_calibration=True,weight_normalization='mean1 separately train/calibration',
    warmup_dates=240,calibration_dates=60,test_block_dates=20,
    stop=.01,target=.004,horizon_minutes=60,stock_cap=.01,category_cap=.05,
    max_positions=3,planned_risk=.0005,orders=False)


def run(data,reference,input_audit,output):
    original = json.loads(reference.read_bytes())
    if original['status'] != 'completed_exposed_split_predictive_comparison':
        raise ValueError('Completed split-normalized reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() != expected:
            raise ValueError('Reference source changed')
    audit = json.loads(input_audit.read_bytes())
    if hashlib.sha256(input_audit.read_bytes()).hexdigest() != original['input_audit_sha256']:
        raise ValueError('Original split input audit changed')
    receipt_path = input_audit.parent/'corporate_actions_receipt.json'
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != original['corporate_action_receipt_sha256']:
        raise ValueError('Split receipt changed')
    observations,evidence = load_observations(data)
    if evidence != original['evidence'] or evidence != audit['evidence']:
        raise ValueError('Matched input bytes changed')
    receipt = json.loads(receipt_path.read_bytes())
    events = events_from_pages(receipt['pages'],list(observations))
    by_date,reasons,applications = normalized_opening_rows(observations,events)
    rows,dates,market = flatten(by_date),sorted(by_date),market_maps(observations)
    outcomes = {(r['date'],r['symbol']):path(market[r['date']][r['symbol']],r['signal_price']) for r in rows}
    labels = {key:o['label'] for key,o in outcomes.items() if o is not None and o['filled']}
    report = dict(status='running_exposed_recency_comparison',protocol=PROTOCOL,evidence=evidence,
        cases=[],applications=applications,orders=False,production_approved=False,independent_validation_pass=False,
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        input_audit_sha256=original['input_audit_sha256'],
        dependency_sha256=dict(original['dependency_sha256'], **{name:
            hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in
            ['recency_predictor.py','recency_predictive_research.py']}),
        limitations=['Previously exposed outcomes; no independent validation',
            'Decay is a fixed hypothesis, not evidence that market drift causes production losses',
            'Row-weight effective size is not count of independent trading observations',
            'Existing current universe/revision/announcement receipt/modeled execution limitations remain',
            'No risk/cost change or frozen/production model modification'])
    output.mkdir(parents=True,exist_ok=True)
    with threadpool_limits(limits=1):
        for half_life in PROTOCOL['half_lives_sessions']:
            for model in PROTOCOL['models']:
                old = next(c for c in original['cases'] if
                    c['feature_set'] == 'date_effective_split_context' and c['model'] == model)
                if half_life is None:
                    forecasts,folds = old['forecasts'],old['folds']
                    index = {(r['date'],r['symbol']):r for r in rows}
                    if any(any(f[k] != index[(f['date'],f['symbol'])][k] for k in ['features','signal_price'])
                           for f in forecasts):
                        raise ValueError('Original normalized forecast inputs changed')
                else:
                    forecasts,folds = [],[]
                    for start in range(240,len(dates),20):
                        parts = [dates[:start-60],dates[start-60:start],dates[start:start+20]]
                        train,cal,test = [partition(rows,p) for p in parts]
                        train = [r for r in train if (r['date'],r['symbol']) in labels]
                        cal = [r for r in cal if (r['date'],r['symbol']) in labels]
                        probabilities,training = fit(train,cal,test,labels,model,dates[:start],half_life)
                        forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
                        folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
                            test_first=parts[2][0],test_last=parts[2][-1],training=training))
                if [(f['test_first'],f['test_last']) for f in folds] != [
                        (f['test_first'],f['test_last']) for f in old['folds']]:
                    raise ValueError('Matched test dates changed')
                case = dict(model=model,feature_set=f'split_context_recency_{half_life}',
                            half_life_sessions=half_life,folds=folds,forecasts=forecasts,outcomes=[])
                for gate in PROTOCOL['gates']:
                    for cost,delay in PROTOCOL['cost_delay_variants']:
                        result = portfolio(forecasts,market,gate,cost,delay)
                        prefix = dict(result,profit_usd=result['known_prefix_profit_usd'])
                        result['known_prefix_metrics'] = accounting_metrics(prefix,forecasts)
                        result['known_prefix_cost_diagnostic'] = diagnostic(prefix)
                        check(result)
                        if half_life is None:
                            expected = next(o for o in old['outcomes'] if
                                (o['threshold'],o['costs_bps'],o['delay']) == (gate,cost,delay))
                            assert_reference(result,expected)
                        case['outcomes'].append(result)
                        if cost == 10 and delay == 16:
                            print(json.dumps(dict(model=model,half_life=half_life,gate=gate,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status'] = 'completed_exposed_recency_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--reference',type=Path,default=Path('research_runs/split_predictive/results.json'))
    parser.add_argument('--input-audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/recency_predictive'))
    args = parser.parse_args()
    run(args.data,args.reference,args.input_audit,args.output)
