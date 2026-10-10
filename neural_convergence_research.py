"""Training-loss stopping audit, NOT epoch selection by test trading profit.

Same architecture/inputs/exits as opening_path_research, max1000 epochs.
Stopping plateau is verified from the recorded TRAIN loss curve; no global
optimality, predictive validity or economic advantage follows from convergence.
"""
import argparse
import hashlib
import json
import math
import warnings
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from opening_path_research import path_rows
from active_stock_research import load_universe
from predictive_portfolio_research import partition
from predictive_research import raw_score
from tighter_stop_simulator import path,portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(feature_sets=['summary','summary_plus_ordered_path'],max_epochs=1000,
    training_loss_tolerance=.00001,training_plateau_patience=20,early_stopping=False,
    random_test_split=False,hidden_layers=[64,32],alpha=10,batch_size=256,
    learning_rate=.001,seed=19,thresholds=[.5,.65,.9],warmup_dates=240,
    calibration_dates=60,test_block_dates=20,entry_delay=16,cost_bps=10,
    stop_fraction=.01,target_fraction=.004,horizon_minutes=60,
    orders=False,production_approved=False,independent_validation_pass=False)


def verify_plateau(loss_curve,tolerance=.00001,patience=20):
    """Replay installed sklearn's train-only no-improvement rule, not P&L."""
    if not loss_curve or not all(math.isfinite(v) for v in loss_curve):
        raise ValueError('Finite nonempty training loss curve required')
    if not math.isfinite(tolerance) or tolerance<=0 or isinstance(patience,bool) or not isinstance(patience,int) or patience<1:
        raise ValueError('Invalid training stopping parameters')
    best=float('inf');count=0
    for loss in loss_curve:
        count=count+1 if loss>best-tolerance else 0
        best=min(best,loss)
    return dict(no_improvement_count=count,plateau_reached=count>patience,
        best_training_loss=best,final_training_loss=loss_curve[-1])


def fit_probability(train,cal,test,labels):
    if not train or not cal or not test or not max(r['date'] for r in train)<min(r['date'] for r in cal):
        raise ValueError('Strict fitting chronology required')
    if not max(r['date'] for r in cal)<min(r['date'] for r in test): raise ValueError('Future test overlap')
    def arrays(rows):
        return np.asarray([r['features'] for r in rows]),np.asarray([labels[(r['date'],r['symbol'])] for r in rows])
    x,y=arrays(train);cx,cy=arrays(cal);tx=np.asarray([r['features'] for r in test])
    if not all(np.isfinite(v).all() for v in [x,cx,tx]) or set(y)!={0,1} or set(cy)!={0,1}:
        raise ValueError('Finite features and both past classes required')
    classifier=MLPClassifier(hidden_layer_sizes=(64,32),alpha=10,max_iter=1000,
        batch_size=256,learning_rate_init=.001,random_state=19,shuffle=False,
        early_stopping=False,n_iter_no_change=20,tol=.00001)
    model=make_pipeline(StandardScaler(),classifier)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always');model.fit(x,y)
        calibrator=LogisticRegression(C=1,max_iter=1000,random_state=19).fit(raw_score(model,cx),cy)
    curve=[float(v) for v in classifier.loss_curve_];check=verify_plateau(curve)
    warning_types=[type(w.message).__name__ for w in caught]
    verified=bool(check['plateau_reached'] and classifier.n_iter_<1000 and 'ConvergenceWarning' not in warning_types)
    return calibrator.predict_proba(raw_score(model,tx))[:,1],dict(
        warning_types=warning_types,fitted_iterations=int(classifier.n_iter_),loss_curve=curve,
        training_plateau_check=check,training_plateau_verified=verified,
        termination='verified_training_plateau' if verified else 'cap_or_unverified',
        random_test_split_used=False,scaler_fit_on_train_only=True,
        calibration_or_test_used_for_stopping=False,global_optimum_proven=False)


def walk(rows,by_date):
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(by_date[r['date']][r['symbol']][0],r['signal_price'],.01,10,16) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items()};predictions=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,d) for d in parts]
        train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
        p,fit=fit_probability(train,cal,test,labels)
        predictions.extend(dict(r,probability=float(v)) for r,v in zip(test,p))
        filled=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        folds.append(dict(train_last=parts[0][-1],calibration_first=parts[1][0],calibration_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],fit=fit,
            filled_test_samples=len(filled),brier_filled=float(np.mean([
                (p[i]-labels[(test[i]['date'],test[i]['symbol'])])**2 for i in filled])) if filled else None))
    return predictions,folds


def run(data,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data);full=path_rows(by_date)
    report=dict(status='running_exposed_historical_convergence_audit',protocol=PROTOCOL,evidence=evidence,
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['neural_convergence_research.py','opening_path_research.py','regime_predictive_research.py',
                'predictive_portfolio_research.py','predictive_research.py','tighter_stop_simulator.py','active_stock_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Historical outcomes already exposed; no independent forward validation',
            'Training-loss plateau is not global convergence, accurate probabilities or profitable execution',
            'Only one fixed training stopping policy; no test-profit epoch search',
            'Fixed universe, complete-session exclusions, raw splits and delayed SIP assumptions remain biased',
            'OHLC fills, costs and approximate EOD account guards are not whole-account execution proof'])
    with threadpool_limits(limits=1):
        for feature_set in PROTOCOL['feature_sets']:
            rows=[dict(r,features=r['features'][:21]) for r in full] if feature_set=='summary' else full
            predictions,folds=walk(rows,by_date)
            case=dict(feature_set=feature_set,model='mlp_train_plateau',feature_count=len(rows[0]['features']),
                folds=folds,outcomes=[])
            for threshold in PROTOCOL['thresholds']:
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(predictions,by_date,.01,threshold,cost,delay)
                    result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                    case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(features=feature_set,threshold=threshold,
                            verified_plateau_folds=sum(f['fit']['training_plateau_verified'] for f in folds),
                            active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                            net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_historical_convergence_audit'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/neural_convergence'))
    args=parser.parse_args();run(args.data,args.output)
