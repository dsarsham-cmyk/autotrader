"""Two-stage past-only research: predict stock outcomes, then basket-day profit.

Historical dates are already exposed; this is exploration, never independent
validation or trading authority. Meta labels come from cross-fitted base
forecasts, not in-sample fitted stock probabilities. Limits remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from predictive_portfolio_research import fit_predict,partition,path_outcome,portfolio
from predictive_research import raw_score
from fixed_trade_cost_diagnostic import diagnostic
from prospective_series_audit import accounting_metrics

PROTOCOL=dict(stage_one='boosted stocks, filled-conditional calibration',stock_threshold=.65,
    stock_warmup_dates=120,stock_calibration_dates=40,stock_test_block=20,
    meta_warmup_dates=120,meta_calibration_dates=30,meta_test_block=20,
    meta_models=['logistic','boosted'],meta_thresholds=[.65,.9],
    cutoff_minute=30,information_delay_minutes=15,execution_latency_minutes=1,
    horizon='target_60',stop_fraction=.01,target_fraction=.004,
    category_cap_fraction=.05,stock_cap_fraction=.01,max_positions=3,
    primary_cost_bps=10,stress_cost_bps=20,orders=False,
    target_active_day_win_rate=.9,independent_validation_pass=False)


def stock_crossfit(rows,by_date):
    dates=sorted({row['date'] for row in rows})
    outcomes={(r['date'],r['symbol']):path_outcome(by_date[r['date']][r['symbol']][0],
        r['signal_price'],30,'target_60',10,16) for r in rows}
    labels={key:outcome['label'] for key,outcome in outcomes.items()}
    predictions=[];folds=[]
    for start in range(120,len(dates),20):
        splits=[dates[:start-40],dates[start-40:start],dates[start:start+20]]
        train,cal,test=[partition(rows,part) for part in splits]
        train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
        p=fit_predict(train,cal,test,'boosted',labels)
        predictions.extend(dict(r,probability=float(value)) for r,value in zip(test,p))
        folds.append(dict(train_last=splits[0][-1],calibration_first=splits[1][0],
            calibration_last=splits[1][-1],test_first=splits[2][0],test_last=splits[2][-1],
            filled_train_rows=len(train),filled_calibration_rows=len(cal)))
    return predictions,folds


def day_features(rows):
    """Uses opening features and frozen stock scores only, no fill/outcome data."""
    if not rows or len({r['date'] for r in rows})!=1:
        raise ValueError('Exactly one nonempty signal date required')
    selected=sorted([r for r in rows if r['probability']>=.65],
        key=lambda r:(-r['probability'],r['symbol']))[:3]
    x=np.array([r['features'] for r in rows],dtype=float)
    chosen=np.array([r['features'] for r in selected],dtype=float) if selected else None
    probabilities=sorted([r['probability'] for r in rows],reverse=True)
    features=np.r_[x.mean(axis=0),x.std(axis=0),
        chosen.mean(axis=0) if selected else np.zeros(x.shape[1]),
        (probabilities+[0,0,0])[:3],len(selected),len(rows)]
    if not np.isfinite(features).all(): raise ValueError('Invalid meta features')
    return features.tolist()


def meta_records(predictions,by_date):
    # Base policy is run cumulatively; future labels cannot influence earlier
    # capital or selected baskets. Gated policy can have different share counts.
    baseline=portfolio(predictions,by_date,30,'target_60',.65,10,16)
    days={day['date']:day for day in baseline['daily']}
    records=[]
    for date in sorted(days):
        day=days[date];rows=[r for r in predictions if r['date']==date]
        records.append(dict(date=date,features=day_features(rows),
            base_active=day['active'],base_net_pnl=day['pnl'],label=int(day['pnl']>0)))
    return records


def fit_meta(train,calibration,test,kind):
    # Only PAST activity may condition training. Future test activity is unknown.
    train=[r for r in train if r['base_active']]
    calibration=[r for r in calibration if r['base_active']]
    if len(train)<30 or len(calibration)<10 or len({r['label'] for r in train})<2 or len({r['label'] for r in calibration})<2:
        raise ValueError('Insufficient past active dates/classes for meta calibration')
    classifier=(LogisticRegression(C=.1,max_iter=1000,random_state=31) if kind=='logistic'
        else HistGradientBoostingClassifier(max_iter=60,max_leaf_nodes=3,
            min_samples_leaf=20,l2_regularization=20,early_stopping=False,random_state=31))
    model=make_pipeline(StandardScaler(),classifier)
    x=np.array([r['features'] for r in train]);y=np.array([r['label'] for r in train])
    cx=np.array([r['features'] for r in calibration]);cy=np.array([r['label'] for r in calibration])
    model.fit(x,y)
    calibrator=LogisticRegression(C=.1,max_iter=1000,random_state=31).fit(raw_score(model,cx),cy)
    return calibrator.predict_proba(raw_score(model,np.array([r['features'] for r in test])))[:,1]


def meta_crossfit(records,kind):
    predictions={};folds=[]
    for start in range(120,len(records),20):
        train,cal,test=records[:start-30],records[start-30:start],records[start:start+20]
        fold=dict(train_last=train[-1]['date'],calibration_first=cal[0]['date'],
            calibration_last=cal[-1]['date'],test_first=test[0]['date'],test_last=test[-1]['date'])
        try:
            p=fit_meta(train,cal,test,kind)
            predictions.update({r['date']:float(value) for r,value in zip(test,p)})
            fold.update(status='past_only_meta_forecast',active_train_dates=sum(r['base_active'] for r in train),
                active_calibration_dates=sum(r['base_active'] for r in cal))
        except ValueError as error:
            if str(error)!='Insufficient past active dates/classes for meta calibration': raise
            predictions.update({r['date']:None for r in test})
            fold['status']='no_meta_forecast_insufficient_past_evidence'
        folds.append(fold)
    return predictions,folds


def gate(rows,probabilities,threshold):
    # Keep each test date in accounting even if a gate abstains or cannot fit.
    return [dict(row,probability=row['probability'] if
        probabilities.get(row['date']) is not None and probabilities[row['date']]>=threshold else 0.)
        for row in rows if row['date'] in probabilities]


def run(data,output):
    output.mkdir(parents=True,exist_ok=True)
    by_date,evidence=load_universe(data)
    rows=extended_rows(by_date)
    base,stock_folds=stock_crossfit(rows,by_date)
    records=meta_records(base,by_date)
    future_dates={r['date'] for r in records[120:]}
    baseline=[r for r in base if r['date'] in future_dates]
    report=dict(status='exploration_only',protocol=PROTOCOL,evidence=evidence,
        dependency_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['daily_meta_research.py','regime_predictive_research.py','predictive_portfolio_research.py',
                'active_stock_research.py','fixed_trade_cost_diagnostic.py','predictive_research.py']},
        stock_folds=stock_folds,meta_training_records=records,cases=[],orders=False,
        independent_validation_pass=False,production_approved=False,
        limitations=['All dates already exposed: nested past-only fitting is not independent validation',
            'Meta labels describe the base policy; gated capital/share counts can differ',
            'Small historical active-date calibration samples cannot certify .9 forecasts',
            'Complete-session exclusions and fixed present-day universe remain selection biased',
            'OHLC fills/costs and frozen EOD-peak guard are simulations, not broker execution'])
    variants=[('base_control',None,None,baseline)]
    for kind in PROTOCOL['meta_models']:
        probabilities,folds=meta_crossfit(records,kind)
        for threshold in PROTOCOL['meta_thresholds']:
            variants.append((kind,threshold,dict(probabilities=probabilities,folds=folds),gate(base,probabilities,threshold)))
    for kind,threshold,details,candidates in variants:
        case=dict(meta_model=kind,meta_threshold=threshold,details=details,outcomes=[])
        for cost,delay in [(10,16),(20,16),(10,17)]:
            result=portfolio(candidates,by_date,30,'target_60',.65,cost,delay)
            result.update(cost_diagnostic=diagnostic(result),metrics=accounting_metrics(result,candidates))
            case['outcomes'].append(result)
            print(json.dumps(dict(model=kind,threshold=threshold,cost_bps=cost,delay=delay,
                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
        report['cases'].append(case)
        (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/active_stocks'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/daily_meta'))
    args=parser.parse_args();run(args.data,args.output)
