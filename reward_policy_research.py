"""Re-fit classifiers for larger profit targets, never widen stops or sizing."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from predictive_portfolio_research import partition,fit_predict
from quantum_kernel_research import predict as predict_kernel
from neural_convergence_research import fit_probability as predict_neural
from reward_policy_simulator import TARGETS,path,portfolio,economics
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(targets=list(TARGETS),models=['logistic','boosted','mlp','quantum_fidelity'],
    features='21 vwap/volume/regime features',stop_fraction=.01,horizon_minutes=60,
    information_cutoff_minute=30,sip_delay_minutes=15,entry_delay=16,cost_bps=10,
    warmup_dates=240,calibration_dates=60,test_block_dates=20,thresholds=[.5,.65,.9],
    stock_cap=.01,category_cap=.05,max_positions=3,planned_trade_risk=.0005,
    stop_widening=False,budget_increase=False,orders=False,production_approved=False)


def walk(rows,by_date,target,kind):
    if kind not in PROTOCOL['models']: raise ValueError('Unknown classifier')
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(by_date[r['date']][r['symbol']][0],r['signal_price'],target,10,16) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items()};predictions=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,d) for d in parts]
        train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
        metadata={}
        if kind=='mlp': p,metadata=predict_neural(train,cal,test,labels)
        elif kind=='quantum_fidelity': p=predict_kernel(train,cal,test,labels,kind)
        else: p=fit_predict(train,cal,test,kind,labels)
        predictions.extend(dict(r,probability=float(v)) for r,v in zip(test,p))
        filled=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        folds.append(dict(train_last=parts[0][-1],calibration_first=parts[1][0],calibration_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],fit=metadata,filled_test_samples=len(filled),
            brier_filled=float(np.mean([(p[i]-labels[(test[i]['date'],test[i]['symbol'])])**2 for i in filled])) if filled else None))
    return predictions,folds


def run(data,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data);rows=extended_rows(by_date)
    report=dict(status='running_exposed_historical_reward_research',protocol=PROTOCOL,evidence=evidence,
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['reward_policy_simulator.py','reward_policy_research.py','tighter_stop_simulator.py',
                'regime_predictive_research.py','predictive_portfolio_research.py','predictive_research.py',
                'quantum_kernel_research.py','neural_convergence_research.py','active_stock_research.py']},
        theoretical_economics=[economics(t) for t in TARGETS],cases=[],orders=False,
        production_approved=False,independent_validation_pass=False,
        limitations=['All historical outcomes already exposed; target trials not independent evidence',
            'Larger target may be hit less often and leaves a winning trade exposed longer within same 60-minute cap',
            'Improved algebraic break-even is not predicted profitable accuracy or risk-free return',
            'Same fixed stop and planned risk do not guarantee loss bounds under gaps or failed fills',
            'Current universe, full-session exclusions, raw splits, revisions and assumed SIP receipt remain biased',
            'OHLC fills and EOD-peak guard approximations are not live whole-account execution validation',
            'Quantum model remains four-qubit CPU simulation, not quantum hardware'])
    with threadpool_limits(limits=1):
        for target in TARGETS:
            for kind in PROTOCOL['models']:
                predictions,folds=walk(rows,by_date,target,kind)
                case=dict(target_fraction=target,model=kind,folds=folds,outcomes=[])
                for threshold in PROTOCOL['thresholds']:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result=portfolio(predictions,by_date,target,threshold,cost,delay)
                        result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(target=target,model=kind,threshold=threshold,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_historical_reward_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/reward_policy'))
    args=parser.parse_args();run(args.data,args.output)
