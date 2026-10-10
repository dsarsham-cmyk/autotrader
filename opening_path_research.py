"""Ordered opening-bar representation, matched linear vs neural classifiers.

Dense MLP with learned weights; NOT a quantum processor, LLM or future oracle.
All observations already exposed. No orders or frozen-control replacement.
"""
import argparse
import hashlib
import json
import warnings
from pathlib import Path
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from predictive_portfolio_research import partition
from predictive_research import raw_score
from tighter_stop_simulator import path,portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(feature_sets=['summary','summary_plus_ordered_path'],models=['logistic','mlp'],
    channels=['close_log_return','log_high_low_range','log_close_open_body','log1p_relative_minute_volume'],
    opening_minutes=30,prior_volume_sessions=20,hidden_layers=[64,32],mlp_alpha=10,
    mlp_epochs=100,mlp_batch_size=256,mlp_learning_rate=.001,random_state=19,
    chronological_split=[240,60,20],thresholds=[.5,.65,.9],information_delay_minutes=15,
    entry_delay=16,stop_fraction=.01,target_fraction=.004,horizon_minutes=60,
    costs_bps=10,orders=False,production_approved=False,independent_validation_pass=False)


def ordered_features(opening,prior_volumes):
    a=np.asarray(opening,dtype=float);past=np.asarray(prior_volumes,dtype=float)
    if a.shape!=(30,5) or past.shape!=(20,30): raise ValueError('Exact opening/prior volume windows required')
    if not np.isfinite(a).all() or not np.isfinite(past).all() or (a[:,:4]<=0).any() or (a[:,4]<0).any() or (past<0).any():
        raise ValueError('Invalid opening/path values')
    if (a[:,1]<a[:,[0,3]].max(axis=1)).any() or (a[:,2]>a[:,[0,3]].min(axis=1)).any():
        raise ValueError('Inconsistent opening OHLC')
    previous=np.r_[a[0,0],a[:-1,3]]
    # Every volume denominator uses prior completed opening windows only.
    mean_volume=np.maximum(1,past.mean(axis=0))
    channels=np.column_stack([np.log(a[:,3]/previous),np.log(a[:,1]/a[:,2]),
        np.log(a[:,3]/a[:,0]),np.log1p(a[:,4]/mean_volume)])
    return channels.ravel().tolist()  # minute-major ordering retained


def path_rows(by_date):
    base={(r['date'],r['symbol']):r for r in extended_rows(by_date)}
    histories={};rows=[]
    for date,stocks in sorted(by_date.items()):
        for symbol,(a,_) in sorted(stocks.items()):
            past=histories.setdefault(symbol,[]);key=(date,symbol)
            if key in base:
                extra=ordered_features(a[:30],past[-20:])
                rows.append(dict(base[key],features=base[key]['features']+extra))
            past.append(np.asarray(a[:30,4],dtype=float).copy())
    return rows


def fit_probability(train,cal,test,labels,kind):
    if kind not in PROTOCOL['models']: raise ValueError('Unknown classifier')
    if not train or not cal or not test or not max(r['date'] for r in train)<min(r['date'] for r in cal):
        raise ValueError('Strict fitting chronology required')
    if not max(r['date'] for r in cal)<min(r['date'] for r in test): raise ValueError('Future test overlap')
    def arrays(rows):
        return np.asarray([r['features'] for r in rows]),np.asarray([labels[(r['date'],r['symbol'])] for r in rows])
    x,y=arrays(train);cx,cy=arrays(cal);tx=np.asarray([r['features'] for r in test])
    if not all(np.isfinite(v).all() for v in [x,cx,tx]) or set(y)!={0,1} or set(cy)!={0,1}:
        raise ValueError('Finite features and two past classes required')
    classifier=(LogisticRegression(C=.1,max_iter=1000,random_state=19) if kind=='logistic'
        else MLPClassifier(hidden_layer_sizes=(64,32),alpha=10,max_iter=100,
            batch_size=256,learning_rate_init=.001,random_state=19,shuffle=False,
            early_stopping=False,n_iter_no_change=100))
    model=make_pipeline(StandardScaler(),classifier)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        model.fit(x,y)
        calibrator=LogisticRegression(C=1,max_iter=1000,random_state=19).fit(raw_score(model,cx),cy)
    return calibrator.predict_proba(raw_score(model,tx))[:,1],dict(
        warning_types=[type(w.message).__name__ for w in caught],
        fitted_iterations=np.asarray(classifier.n_iter_).ravel().tolist(),
        random_test_split_used=False,scaler_fit_on_train_only=True)


def walk(rows,by_date,kind):
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(by_date[r['date']][r['symbol']][0],r['signal_price'],.01,10,16) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items()};predictions=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,d) for d in parts]
        train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
        p,fit=fit_probability(train,cal,test,labels,kind)
        predictions.extend(dict(r,probability=float(v)) for r,v in zip(test,p))
        filled=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        folds.append(dict(train_last=parts[0][-1],calibration_first=parts[1][0],calibration_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],fit=fit,
            filled_test_samples=len(filled),brier_filled=float(np.mean([
                (p[i]-labels[(test[i]['date'],test[i]['symbol'])])**2 for i in filled])) if filled else None))
    return predictions,folds


def run(data,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data);full=path_rows(by_date)
    report=dict(status='running_exposed_historical_research',protocol=PROTOCOL,evidence=evidence,
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['opening_path_research.py','regime_predictive_research.py','predictive_portfolio_research.py',
                'predictive_research.py','tighter_stop_simulator.py','active_stock_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Already exposed historical dates; not an independent test',
            'Dense MLP receives ordered channels, not an RNN/transformer or quantum processor',
            'Fixed epochs may not converge; warning types and fit iterations retained',
            'Delayed SIP receipt, selection-biased current universe, complete-session exclusions and raw splits remain',
            'Bar-relative volume is not order-book depth; OHLC fills/costs/guard assumptions are not execution validation'])
    with threadpool_limits(limits=1):
        for feature_set in PROTOCOL['feature_sets']:
            rows=[dict(r,features=r['features'][:21]) for r in full] if feature_set=='summary' else full
            for kind in PROTOCOL['models']:
                predictions,folds=walk(rows,by_date,kind)
                case=dict(feature_set=feature_set,model=kind,feature_count=len(rows[0]['features']),folds=folds,outcomes=[])
                for threshold in PROTOCOL['thresholds']:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result=portfolio(predictions,by_date,.01,threshold,cost,delay)
                        result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                        case['outcomes'].append(result)
                        if cost==10 and delay==16:
                            print(json.dumps(dict(features=feature_set,model=kind,threshold=threshold,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_historical_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/opening_path'))
    args=parser.parse_args();run(args.data,args.output)
