"""Own-label comparison for next-minute tightening stop, no production orders."""
import argparse
import hashlib
import json
from pathlib import Path
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations,opening_rows
from causal_sparse_research import market_maps
from predictive_portfolio_research import partition,fit_predict
from profit_lock_simulator import path,portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from finbert_comparison_audit import check

PROTOCOL=dict(activation_gross_fraction=.003,protected_net_fraction=.0002,
    activation_rule='prior completed bar high and close above cost-adjusted stop plus one cent',
    protection_latency_minutes=1,initial_stop=.01,target=.004,horizon_minutes=60,
    stock_cap=.01,category_cap=.05,max_positions=3,planned_risk=.0005,orders=False)


def walk(rows,market,model,protect):
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(market[r['date']][r['symbol']],r['signal_price'],protect=protect) for r in rows}
    labels={key:o['label'] for key,o in outcomes.items() if o is not None and o['filled']}
    forecasts=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,p) for p in parts]
        train=[r for r in train if (r['date'],r['symbol']) in labels];cal=[r for r in cal if (r['date'],r['symbol']) in labels]
        probabilities=fit_predict(train,cal,test,model,labels)
        forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
        folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],known_filled_train=len(train),known_filled_cal=len(cal),
            forecast_candidates=len(test)))
    return forecasts,folds


def run(data,reference,output):
    raw=reference.read_bytes();original=json.loads(raw)
    if original['status']!='completed_exposed_causal_sparse_research': raise ValueError('Completed reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected: raise ValueError('Reference source changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Reference observations changed')
    by_date,reasons=opening_rows(observations)
    rows=[r for date,stocks in sorted(by_date.items()) for symbol,r in sorted(stocks.items())];market=market_maps(observations)
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_profit_lock_comparison',protocol=PROTOCOL,evidence=evidence,
        reference_sha256=hashlib.sha256(raw).hexdigest(),
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['profit_lock_simulator.py','profit_lock_research.py','finbert_comparison_audit.py']}),
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Previously exposed historical outcomes, not independent validation',
            'Minute-close decision and next-minute amended stop are modeled, not confirmed broker replacement',
            'Initial stop unchanged and never lowered; gaps may still execute below tightened stop',
            'No update when proposed protected stop is at/above profit target',
            'Fixed universe/raw revisions/original receipts and OHLC execution assumptions remain'])
    with threadpool_limits(limits=1):
        for protect in [False,True]:
            for model in ['logistic','boosted']:
                forecasts,folds=walk(rows,market,model,protect)
                case=dict(model=model,feature_set='profit_lock' if protect else 'fixed_stop',folds=folds,outcomes=[])
                for gate in [.5,.65,.9]:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result=portfolio(forecasts,market,gate,cost,delay,protect)
                        result['known_prefix_metrics']=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)
                        result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                        check(result)
                        if not protect:
                            old=next(c for c in original['cases'] if c['model']==model)
                            expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(gate,cost,delay))
                            if any(result[k]!=expected[k] for k in ['daily','trades','profit_usd','unknown_selections']):
                                raise ValueError('Fixed-stop reference not reproduced')
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(protect=protect,model=model,gate=gate,active_days=result['active_days'],
                                win_rate=result['active_day_win_rate_pct'],net_usd=result['profit_usd'],complete=result['full_period_coverage_complete'],
                                profit_lock_exits=sum(t['reason']=='profit_lock' for t in result['trades']))),flush=True)
                report['cases'].append(case);(output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_profit_lock_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/causal_sparse/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/profit_lock'))
    a=p.parse_args();run(a.data,a.reference,a.output)
