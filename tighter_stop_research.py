"""Re-fit each tighter exit policy on past labels, not favorable hindsight.

Fixed 1% reference, .5% and .25% stops; other budgets, timing, target and costs
unchanged. Exposed histories are development data, not prospective evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from predictive_portfolio_research import fit_predict,partition
from quantum_kernel_research import predict as predict_kernel
from tighter_stop_simulator import path,portfolio,theoretical_economics
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(stops=[.01,.005,.0025],target=.004,cutoff_minute=30,sip_delay_minutes=15,
    execution_latency_minutes=1,horizon_minutes=60,warmup_dates=240,calibration_dates=60,test_block_dates=20,
    models=['logistic','boosted','classical_rbf','quantum_fidelity'],thresholds=[.5,.65,.9],
    per_side_cost_bps=10,stock_cap=.01,category_cap=.05,max_positions=3,max_planned_risk=.0005,
    daily_entry_cutoff=.005,daily_exit_trigger=.01,permanent_drawdown=.1,
    stop_widening_allowed=False,orders=False,independent_validation_pass=False)


def walk(rows,by_date,stop,model):
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(by_date[r['date']][r['symbol']][0],r['signal_price'],stop,10,16) for r in rows}
    labels={key:outcome['label'] for key,outcome in outcomes.items()}
    predictions=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,part) for part in parts]
        train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
        p=(predict_kernel(train,cal,test,labels,model) if model in ['classical_rbf','quantum_fidelity']
            else fit_predict(train,cal,test,model,labels))
        predictions.extend(dict(r,probability=float(value)) for r,value in zip(test,p))
        matched=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        folds.append(dict(stop_fraction=stop,train_last=parts[0][-1],calibration_first=parts[1][0],
            calibration_last=parts[1][-1],test_first=parts[2][0],test_last=parts[2][-1],
            filled_train_rows=len(train),filled_calibration_rows=len(cal),
            brier_filled=float(np.mean([(p[i]-labels[(test[i]['date'],test[i]['symbol'])])**2 for i in matched])) if matched else None))
    return predictions,folds


def run(data,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data);rows=extended_rows(by_date)
    report=dict(status='exposed_historical_stop_research_only',protocol=PROTOCOL,evidence=evidence,
        dependency_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['tighter_stop_simulator.py','tighter_stop_research.py','regime_predictive_research.py',
                'predictive_portfolio_research.py','quantum_kernel_research.py','active_stock_research.py']},
        theoretical_economics=[dict(stop_fraction=stop,**theoretical_economics(stop)) for stop in PROTOCOL['stops']],
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['All historical dates exposed; stop/model trials are not independent validation',
            'Tighter stops can be hit more often; lower loss alone does not prove positive expectancy or 90% days',
            'Gap execution can exceed stop/daily-trigger amounts; planned risk is not a guaranteed bound',
            'Minute OHLC assumes stop-first ordering and immediate modeled fills; no tick/broker execution validation',
            'Frozen EOD peak guard approximation and one simultaneous entry cannot prove whole-account intraday guards',
            'Raw splits, present-day universe and complete-session exclusions remain biased',
            'Quantum model is only a small four-qubit CPU simulation'])
    for stop in PROTOCOL['stops']:
        for model in PROTOCOL['models']:
            predictions,folds=walk(rows,by_date,stop,model)
            case=dict(stop_fraction=stop,model=model,folds=folds,outcomes=[])
            for threshold in PROTOCOL['thresholds']:
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(predictions,by_date,stop,threshold,cost,delay)
                    result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                    case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(stop=stop,model=model,threshold=threshold,
                            active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                            net_usd=result['profit_usd'],worst_day=result['worst_day_usd'],
                            screen_pass=result['target_screen_pass'])),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/tighter_stops'))
    args=parser.parse_args();run(args.data,args.output)
