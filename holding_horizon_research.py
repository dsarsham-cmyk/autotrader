"""Own past labels for each predeclared holding duration; NO ORDERS."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations,opening_rows
from causal_sparse_research import market_maps
from predictive_portfolio_research import partition,fit_predict
from holding_horizon_simulator import path,portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from finbert_comparison_audit import check

PROTOCOL=dict(horizons_minutes=[60,120],models=['logistic','boosted'],gates=[.5,.65,.9],
    cost_delay_variants=[(10,16),(20,16),(10,17)],training_cost_bps=10,training_delay=16,
    warmup_dates=240,calibration_dates=60,test_dates_per_fold=20,
    stop_fraction=.01,target_fraction=.004,stock_cap=.01,category_cap=.05,
    max_positions=3,planned_trade_risk=.0005,shorting=False,overnight=False,orders=False)


def walk(rows,market,model,horizon):
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(market.get(r['date'],{}).get(r['symbol'],{}),r['signal_price'],horizon=horizon) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items() if o is not None and o['filled']}
    forecasts=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,p) for p in parts]
        train=[r for r in train if (r['date'],r['symbol']) in labels]
        cal=[r for r in cal if (r['date'],r['symbol']) in labels]
        probabilities=fit_predict(train,cal,test,model,labels)
        forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
        known=[(i,labels[(r['date'],r['symbol'])]) for i,r in enumerate(test) if (r['date'],r['symbol']) in labels]
        folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],known_filled_train=len(train),
            known_filled_cal=len(cal),forecast_candidates=len(test),known_filled_test=len(known),
            brier_known_filled=float(np.mean([(probabilities[i]-label)**2 for i,label in known])) if known else None))
    return forecasts,folds


def run(data,reference,output):
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_causal_sparse_research': raise ValueError('Completed reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Reference dependencies changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Reference observations changed')
    by_date,reasons=opening_rows(observations)
    rows=[r for date,stocks in sorted(by_date.items()) for symbol,r in sorted(stocks.items())]
    market=market_maps(observations);output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_holding_horizon_comparison',protocol=PROTOCOL,
        evidence=evidence,reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['holding_horizon_simulator.py','holding_horizon_research.py','finbert_comparison_audit.py']}),
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed historical outcomes; not independent validation',
            'Longer hold changes exposure time, not budget or stop distances',
            'Missing selected outcomes remain unknown, no retrospective substitution',
            'Fixed present universe, raw corporate actions, unverified original receipts and modeled fills remain'])
    with threadpool_limits(limits=1):
        for horizon in PROTOCOL['horizons_minutes']:
            for model in PROTOCOL['models']:
                forecasts,folds=walk(rows,market,model,horizon)
                case=dict(model=model,feature_set=f'causal_price_hold_{horizon}',horizon_minutes=horizon,folds=folds,outcomes=[])
                for gate in PROTOCOL['gates']:
                    for cost,delay in PROTOCOL['cost_delay_variants']:
                        result=portfolio(forecasts,market,gate,cost,delay,horizon)
                        result['known_prefix_metrics']=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)
                        result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                        check(result)
                        if horizon==60:
                            old=next(c for c in original['cases'] if c['model']==model)
                            expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(gate,cost,delay))
                            if any(result[k]!=expected[k] for k in ['profit_usd','daily','trades','unknown_selections']):
                                raise ValueError('One-hour reference not reproduced')
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(horizon=horizon,model=model,gate=gate,active_days=result['active_days'],
                                win_rate=result['active_day_win_rate_pct'],net_usd=result['profit_usd'],
                                full_period=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case);(output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_holding_horizon_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/causal_sparse/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/holding_horizon'))
    a=p.parse_args();run(a.data,a.reference,a.output)
