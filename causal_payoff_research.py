"""Conditional payoff forecasts on corrected causal/sparse price inputs.

Earlier payoff work used different21-feature/full-session-filtered inputs.
This retains all current opening candidates and unknown selected outcomes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import warnings
import numpy as np
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from causal_sparse_simulator import path,portfolio
from conditional_payoff_research import fit_amounts,predict_amounts,selection
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from predictive_portfolio_research import partition,fit_predict
from prospective_series_audit import accounting_metrics
from split_context_audit import events_from_pages,normalized_opening_rows
from split_predictive_research import assert_reference,flatten

MODELS = ['logistic_ridge','boosted']
SELECTORS = ['probability_only','positive_expectancy_probability_rank','positive_expectancy_net_rank']


def walk(rows,market,kind):
    if kind not in MODELS:
        raise ValueError('Unknown conditional payoff model')
    dates = sorted({r['date'] for r in rows})
    outcomes = {(r['date'],r['symbol']):path(market.get(r['date'],{}).get(r['symbol'],{}),r['signal_price']) for r in rows}
    labels = {key:o['label'] for key,o in outcomes.items() if o is not None and o['filled']}
    forecasts,folds = [],[]
    for start in range(240,len(dates),20):
        parts = [dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test = [partition(rows,d) for d in parts]
        train = [r for r in train if (r['date'],r['symbol']) in labels]
        cal = [r for r in cal if (r['date'],r['symbol']) in labels]
        if max(r['date'] for r in cal) >= min(r['date'] for r in test):
            raise ValueError('Past calibration must precede forecasts')
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            fitted = fit_amounts(train,cal,outcomes,kind)
            probabilities = fit_predict(train,cal,test,'logistic' if kind=='logistic_ridge' else 'boosted',labels)
            amounts = predict_amounts(fitted,test,probabilities)
        if observed:
            raise ValueError('Unresolved payoff fitting warnings')
        forecasts.extend(dict(row,**{name:float(values[i]) for name,values in amounts.items()})
                         for i,row in enumerate(test))
        known = [i for i,r in enumerate(test) if (r['date'],r['symbol']) in labels]
        actual = np.asarray([outcomes[(test[i]['date'],test[i]['symbol'])]['exit']/
            outcomes[(test[i]['date'],test[i]['symbol'])]['entry']-1 for i in known])
        folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],forecast_candidates=len(test),
            conditional_samples={key:value for key,value in fitted.items() if key.endswith('_samples')},
            gain_offset=fitted['gain_offset'],loss_offset=fitted['loss_offset'],
            known_filled_test=len(known),expected_return_mae=float(np.mean(
                abs(actual-amounts['expected_net_return'][known]))) if known else None,
            expected_return_bias=float(np.mean(amounts['expected_net_return'][known]-actual)) if known else None))
    return forecasts,folds


def run(data,reference,input_audit,output):
    original = json.loads(reference.read_bytes())
    if original['status'] != 'completed_exposed_split_predictive_comparison':
        raise ValueError('Completed sparse/split-normalized reference required')
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
        raise ValueError('Historical observation bytes changed')
    receipt = json.loads(receipt_path.read_bytes())
    events = events_from_pages(receipt['pages'],list(observations))
    by_date,reasons,applications = normalized_opening_rows(observations,events)
    rows,market = flatten(by_date),market_maps(observations)
    report = dict(status='running_exposed_causal_payoff_comparison',cases=[],evidence=evidence,
        protocol=dict(models=MODELS,selectors=SELECTORS,probability_gates=[.5,.65,.9],
            cost_delay_variants=[(10,16),(20,16),(10,17)],training_cost_bps=10,training_delay=16,
            stock_cap=.01,category_cap=.05,max_positions=3,planned_risk=.0005,
            stop=.01,target=.004,horizon_minutes=60,expected_return_minimum=0,
            warmup_dates=240,calibration_dates=60,test_block_dates=20,orders=False),
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        input_audit_sha256=original['input_audit_sha256'],
        dependency_sha256=dict(original['dependency_sha256'],**{name:
            hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in
            ['conditional_payoff_research.py','causal_payoff_research.py']}),
        orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Previously exposed outcomes, not independent evidence or formula promotion',
            'P(win)*mean(gain) minus P(loss)*mean(loss) combines errors across fitted heads',
            'Payoff targets use modeled10bps/delay16 outcomes; cost/latency stress forecasts not recalibrated',
            'Ordinal selection scores are not probabilities; true probability threshold retained separately',
            'All opening candidates remain, missing selected outcomes stop entire ledger',
            'Present universe/revisions/original announcement/feed delivery and fill assumptions remain',
            'No frozen prospective source/model or production changes'])
    output.mkdir(parents=True,exist_ok=True)
    with threadpool_limits(limits=1):
        for model in MODELS:
            forecasts,folds = walk(rows,market,model)
            old = next(c for c in original['cases'] if c['feature_set']=='date_effective_split_context'
                       and c['model']==('logistic' if model=='logistic_ridge' else 'boosted'))
            if [(f['test_first'],f['test_last']) for f in folds] != [
                    (f['test_first'],f['test_last']) for f in old['folds']]:
                raise ValueError('Matched fold dates changed')
            old_forecasts = {(f['date'],f['symbol']):f for f in old['forecasts']}
            for row in forecasts:
                expected = old_forecasts[(row['date'],row['symbol'])]
                if any(row[key] != expected[key] for key in ['features','signal_price','probability']):
                    raise ValueError('Original probability forecasts not exactly reproduced')
            for selector in SELECTORS:
                case = dict(model=model,feature_set='split_normalized_causal16',selector=selector,
                            folds=folds,forecasts=forecasts,outcomes=[])
                for gate in [.5,.65,.9]:
                    selected = selection(forecasts,selector,gate)
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result = portfolio(selected,market,.5,cost,delay)
                        result.update(probability_threshold=gate,simulator_threshold_is_ordinal=True)
                        prefix = dict(result,profit_usd=result['known_prefix_profit_usd'])
                        result['known_prefix_metrics'] = accounting_metrics(prefix,selected)
                        result['known_prefix_cost_diagnostic'] = diagnostic(prefix)
                        check(result)
                        if selector=='probability_only':
                            expected = next(o for o in old['outcomes'] if
                                (o['threshold'],o['costs_bps'],o['delay'])==(gate,cost,delay))
                            assert_reference(result,expected)
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(model=model,selector=selector,probability_gate=gate,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status'] = 'completed_exposed_causal_payoff_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--reference',type=Path,default=Path('research_runs/split_predictive/results.json'))
    parser.add_argument('--input-audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/causal_payoff'))
    args = parser.parse_args()
    run(args.data,args.reference,args.input_audit,args.output)
