"""Fit on known PAST sparse outcomes; forecast every causal opening candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations,opening_rows,FEATURES
from causal_sparse_simulator import path,portfolio
from predictive_portfolio_research import partition,fit_predict
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(models=['logistic','boosted'],thresholds=[.5,.65,.9],features=FEATURES,
    warmup_dates=240,calibration_dates=60,test_block_dates=20,
    cutoff=30,information_delay=15,entry_delay=16,horizon=60,cost_bps=10,
    stop=.01,target=.004,stock_cap=.01,category_cap=.05,max_positions=3,
    planned_trade_risk=.0005,orders=False,production_approved=False)


def market_maps(observations):
    market={}
    for symbol,days in observations.items():
        for date,regular in days.items():
            market.setdefault(date,{})[symbol]={int(row.minute)-570:
                np.asarray([row.open,row.high,row.low,row.close,row.volume],dtype=float)
                for row in regular.itertuples()}
    return market


def walk(rows,market,kind):
    if kind not in PROTOCOL['models']: raise ValueError('Unknown model')
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(market.get(r['date'],{}).get(r['symbol'],{}),r['signal_price']) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items() if o is not None and o['filled']}
    forecasts=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,p) for p in parts]
        train=[r for r in train if (r['date'],r['symbol']) in labels]
        cal=[r for r in cal if (r['date'],r['symbol']) in labels]
        probabilities=fit_predict(train,cal,test,kind,labels)
        forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
        known=[(i,labels[(r['date'],r['symbol'])]) for i,r in enumerate(test) if (r['date'],r['symbol']) in labels]
        folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],known_filled_train=len(train),
            known_filled_cal=len(cal),forecast_candidates=len(test),known_filled_test=len(known),
            brier_known_filled=float(np.mean([(probabilities[i]-label)**2 for i,label in known])) if known else None))
    return forecasts,folds


def run(directory,output):
    observations,evidence=load_observations(directory);by_date,reasons=opening_rows(observations)
    rows=[r for date,stocks in sorted(by_date.items()) for s,r in sorted(stocks.items())]
    market=market_maps(observations);output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_causal_sparse_research',protocol=PROTOCOL,evidence=evidence,
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in
            ['causal_sparse_research.py','causal_sparse_simulator.py','causal_opening_inventory.py',
             'macro_context_research.py','predictive_portfolio_research.py','predictive_research.py',
             'prospective_series_audit.py','fixed_trade_cost_diagnostic.py','active_stock_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed historical dates, not independent forward evidence',
            'Replacement16 features and prior-terminal history differ from old21-feature studies; not exact causal ablation',
            'Missing whole observed days require an external exchange calendar',
            'Known past fills/outcomes determine training only; all test candidates forecast before test outcome filtering',
            'Missing selected outcomes stop cumulative ledger, not removed to improve statistics',
            'Fixed current universe, raw splits/revisions, unverified original receipts and OHLC assumptions remain'])
    with threadpool_limits(limits=1):
        for kind in PROTOCOL['models']:
            forecasts,folds=walk(rows,market,kind)
            case=dict(model=kind,folds=folds,forecasts=forecasts,outcomes=[])
            for threshold in PROTOCOL['thresholds']:
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(forecasts,market,threshold,cost,delay)
                    result['known_prefix_metrics']=accounting_metrics(result,forecasts)
                    result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                    case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps({k:result[k] for k in ['threshold','active_days','profit_usd',
                            'known_prefix_profit_usd','active_day_win_rate_pct','full_period_coverage_complete']}
                            |dict(model=kind,unknown_selected_dates=len(result['unknown_selections']))),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_causal_sparse_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--output',type=Path,default=Path('research_runs/causal_sparse/results.json').parent)
    a=p.parse_args();run(a.data,a.output)
