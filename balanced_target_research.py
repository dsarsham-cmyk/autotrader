"""Own-label1% target on corrected causal/sparse inputs; no production changes."""
import argparse
import hashlib
import json
from pathlib import Path
import warnings
import numpy as np
from threadpoolctl import threadpool_limits
from balanced_target_simulator import path,portfolio
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from predictive_portfolio_research import partition,fit_predict
from prospective_series_audit import accounting_metrics
from split_context_audit import events_from_pages,normalized_opening_rows
from split_predictive_research import flatten,assert_reference


def walk(rows,market,model,target):
    if model not in ('logistic','boosted'): raise ValueError('Unknown model')
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(market.get(r['date'],{}).get(r['symbol'],{}),
        r['signal_price'],target_fraction=target) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items() if o is not None and o['filled']}
    forecasts=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,d) for d in parts]
        train=[r for r in train if (r['date'],r['symbol']) in labels]
        cal=[r for r in cal if (r['date'],r['symbol']) in labels]
        if max(r['date'] for r in cal)>=min(r['date'] for r in test): raise ValueError('Past-only calibration required')
        with warnings.catch_warnings(record=True) as observed:
            warnings.simplefilter('always')
            probabilities=fit_predict(train,cal,test,model,labels)
        if observed: raise ValueError('Unresolved fitting warning')
        forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
        known=[(i,labels[(r['date'],r['symbol'])]) for i,r in enumerate(test) if (r['date'],r['symbol']) in labels]
        folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],known_filled_train=len(train),
            known_filled_cal=len(cal),forecast_candidates=len(test),known_filled_test=len(known),
            brier_known_filled=float(np.mean([(probabilities[i]-label)**2 for i,label in known])) if known else None))
    return forecasts,folds


def economics(target,cost_bps):
    cost=cost_bps/10000
    gain=(1+target)*(1-cost)/(1+cost)-1
    loss=1-.99*(1-cost)/(1+cost)
    return dict(target_fraction=target,per_side_cost_bps=cost_bps,ideal_gain_fraction=gain,
        ideal_loss_fraction=loss,ideal_trade_breakeven_win_pct=loss/(loss+gain)*100,
        limitations='Algebra only: no horizon exits, gaps, fill/latency uncertainty or forecast')


def run(data,reference,input_audit,output):
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_split_predictive_comparison': raise ValueError('Completed reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Reference source changed')
    if hashlib.sha256(input_audit.read_bytes()).hexdigest()!=original['input_audit_sha256']:
        raise ValueError('Input audit changed')
    receipt=input_audit.parent/'corporate_actions_receipt.json'
    if hashlib.sha256(receipt.read_bytes()).hexdigest()!=original['corporate_action_receipt_sha256']:
        raise ValueError('Split receipt changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Historical inputs changed')
    events=events_from_pages(json.loads(receipt.read_bytes())['pages'],list(observations))
    by_date,_,_=normalized_opening_rows(observations,events)
    rows=flatten(by_date);row_index={(r['date'],r['symbol']):r for r in rows};market=market_maps(observations)
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_balanced_target_comparison',cases=[],evidence=evidence,
        protocol=dict(targets=[.004,.01],stop=.01,horizon_minutes=60,models=['logistic','boosted'],
            gates=[.5,.65,.9],cost_delay_variants=[(10,16),(20,16),(10,17)],training_cost_bps=10,
            training_delay=16,warmup_dates=240,calibration_dates=60,test_block_dates=20,
            stock_cap=.01,category_cap=.05,max_positions=3,planned_trade_risk=.0005,orders=False),
        economics=[economics(t,c) for t in (.004,.01) for c in (10,20)],
        reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        input_audit_sha256=original['input_audit_sha256'],corporate_action_receipt_sha256=original['corporate_action_receipt_sha256'],
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['balanced_target_simulator.py','balanced_target_research.py','finbert_comparison_audit.py']}),
        orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Earlier target studies used different inputs/full-session filters; not first-ever target research',
            'Own past labels for1% target; no reuse of .4% outcome probabilities for new policy',
            'Exposed historical comparisons, not independent validation or a daily income guarantee',
            'Same stops/budgets/latency/cost/horizon; later exit may add exposure time without increased sizing',
            'Missing selected outcomes stop whole ledger; raw gaps and conservative same-bar stop-first remain',
            'Current universe/revisions/receipt delivery and intraminute OHLC execution remain limitations'])
    with threadpool_limits(limits=1):
        for target in (.004,.01):
            for model in ('logistic','boosted'):
                old=next(c for c in original['cases'] if c['feature_set']=='date_effective_split_context' and c['model']==model)
                if target==.004:
                    forecasts,folds=old['forecasts'],old['folds']
                    for f in forecasts:
                        row=row_index[(f['date'],f['symbol'])]
                        if any(f[k]!=row[k] for k in ['features','signal_price']): raise ValueError('Original forecast inputs changed')
                else:
                    forecasts,folds=walk(rows,market,model,target)
                    if [(f['test_first'],f['test_last']) for f in folds]!=[(f['test_first'],f['test_last']) for f in old['folds']]:
                        raise ValueError('Matched forecast span changed')
                case=dict(model=model,target_fraction=target,folds=folds,forecasts=forecasts,outcomes=[])
                for gate in (.5,.65,.9):
                    for cost,delay in ((10,16),(20,16),(10,17)):
                        result=portfolio(forecasts,market,gate,cost,delay,target)
                        prefix=dict(result,profit_usd=result['known_prefix_profit_usd'])
                        result['known_prefix_metrics']=accounting_metrics(prefix,forecasts)
                        result['known_prefix_cost_diagnostic']=diagnostic(prefix)
                        check(result)
                        if target==.004:
                            expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(gate,cost,delay))
                            assert_reference(result,expected)
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(target=target,model=model,gate=gate,active_days=result['active_days'],
                                win_rate=result['active_day_win_rate_pct'],net_usd=result['profit_usd'],
                                known_prefix_net=result['known_prefix_profit_usd'],complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_balanced_target_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/split_predictive/results.json'))
    p.add_argument('--input-audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/balanced_target'))
    a=p.parse_args();run(a.data,a.reference,a.input_audit,a.output)
