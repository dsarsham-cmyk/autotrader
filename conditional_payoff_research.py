"""Past-only conditional payoff models and matched portfolio selection.

Expected net return = P(win)*E(net|win) - (1-P(win))*E(loss|not win).
Exposed history only; no orders or replacement of the frozen prospective model.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from predictive_portfolio_research import fit_predict, partition
from tighter_stop_simulator import path, portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

PROTOCOL=dict(stop_fraction=.01,target_fraction=.004,horizon_minutes=60,
    information_cutoff_minute=30,sip_delay_minutes=15,entry_delay=16,
    warmup_dates=240,calibration_dates=60,test_block_dates=20,
    models=['logistic_ridge','boosted'],thresholds=[.5,.65,.9],
    selectors=['probability_only','positive_expectancy_probability_rank','positive_expectancy_net_rank'],
    expected_return_minimum=0,per_side_cost_bps=10,stock_cap=.01,category_cap=.05,
    max_positions=3,planned_trade_risk=.0005,orders=False,production_approved=False)


def net_returns(rows,outcomes):
    values=[]
    for row in rows:
        outcome=outcomes[(row['date'],row['symbol'])]
        if not outcome['filled']: raise ValueError('Fit requires past filled outcomes only')
        value=outcome['exit']/outcome['entry']-1
        if not math.isfinite(value): raise ValueError('Nonfinite past return')
        values.append(value)
    return np.asarray(values)


def fit_amounts(train,cal,outcomes,kind):
    if kind not in PROTOCOL['models']: raise ValueError('Unknown payoff model')
    if not train or not cal or max(r['date'] for r in train)>=min(r['date'] for r in cal):
        raise ValueError('Strict train/calibration chronology required')
    x=np.asarray([r['features'] for r in train]);cx=np.asarray([r['features'] for r in cal])
    y,cy=net_returns(train,outcomes),net_returns(cal,outcomes)
    if not np.isfinite(x).all() or not np.isfinite(cx).all(): raise ValueError('Invalid features')
    fitted={}
    for name,mask,cmask,target,ctarget in [
        ('gain',y>0,cy>0,y,cy),('loss',y<=0,cy<=0,-y,-cy)]:
        if mask.sum()<30 or cmask.sum()<10:
            raise ValueError('Insufficient conditional payoff samples')
        regressor=(make_pipeline(StandardScaler(),Ridge(alpha=10)) if kind=='logistic_ridge'
            else HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=7,
                min_samples_leaf=30,l2_regularization=10,random_state=19,early_stopping=False))
        # Basis-point targets avoid treating tiny fractional returns as zero scale.
        regressor.fit(x[mask],target[mask]*10000)
        offset=float(np.mean(ctarget[cmask]-regressor.predict(cx[cmask])/10000))
        fitted[name]=regressor;fitted[name+'_offset']=offset
        fitted[name+'_train_samples']=int(mask.sum());fitted[name+'_calibration_samples']=int(cmask.sum())
    return fitted


def predict_amounts(fitted,test,probabilities):
    x=np.asarray([r['features'] for r in test]);p=np.asarray(probabilities,dtype=float)
    if len(p)!=len(test) or not np.isfinite(p).all() or ((p<0)|(p>1)).any():
        raise ValueError('Invalid calibrated probabilities')
    if not np.isfinite(x).all(): raise ValueError('Invalid test features')
    gain=np.maximum(0,fitted['gain'].predict(x)/10000+fitted['gain_offset'])
    loss=np.maximum(0,fitted['loss'].predict(x)/10000+fitted['loss_offset'])
    return dict(probability=p,conditional_gain=gain,conditional_loss=loss,
        expected_net_return=p*gain-(1-p)*loss)


def walk(rows,by_date,kind):
    if kind not in PROTOCOL['models']: raise ValueError('Unknown payoff model')
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(by_date[r['date']][r['symbol']][0],
        r['signal_price'],.01,10,16) for r in rows}
    labels={key:o['label'] for key,o in outcomes.items()};predictions=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,d) for d in parts]
        if not max(r['date'] for r in cal)<min(r['date'] for r in test):
            raise ValueError('Future test overlaps calibration')
        train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
        fitted=fit_amounts(train,cal,outcomes,kind)
        p=fit_predict(train,cal,test,'logistic' if kind=='logistic_ridge' else 'boosted',labels)
        forecast=predict_amounts(fitted,test,p)
        predictions.extend(dict(r,**{key:float(value[i]) for key,value in forecast.items()})
            for i,r in enumerate(test))
        filled=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        actual=np.asarray([outcomes[(test[i]['date'],test[i]['symbol'])]['exit']/
            outcomes[(test[i]['date'],test[i]['symbol'])]['entry']-1 for i in filled])
        folds.append(dict(train_last=parts[0][-1],calibration_first=parts[1][0],
            calibration_last=parts[1][-1],test_first=parts[2][0],test_last=parts[2][-1],
            conditional_samples={k:v for k,v in fitted.items() if k.endswith('_samples')},
            filled_test_samples=len(filled),
            brier_filled=float(np.mean((p[filled]-(actual>0))**2)) if filled else None,
            expected_return_mae=float(np.mean(abs(actual-forecast['expected_net_return'][filled]))) if filled else None,
            expected_return_bias=float(np.mean(forecast['expected_net_return'][filled]-actual)) if filled else None))
    return predictions,folds


def selection(predictions,selector,threshold):
    """Ordinal simulator scores are NOT probabilities; actual forecasts retained.

    Choose before evaluating fills. No replacement with a lower-ranked stock
    after learning that one of the three selected orders would not fill.
    """
    if selector not in PROTOCOL['selectors']: raise ValueError('Unknown selector')
    if not math.isfinite(threshold) or not 0<=threshold<=1: raise ValueError('Invalid threshold')
    grouped={};seen=set()
    for row in predictions:
        key=(row['date'],row['symbol'])
        if key in seen: raise ValueError('Duplicate symbol/date')
        seen.add(key)
        if not math.isfinite(row['probability']) or not 0<=row['probability']<=1:
            raise ValueError('Invalid forecast probability')
        if not math.isfinite(row['expected_net_return']): raise ValueError('Invalid expected return')
        grouped.setdefault(row['date'],[]).append(row)
    selected=[]
    for date,rows in sorted(grouped.items()):
        eligible=[r for r in rows if r['probability']>=threshold and
            (selector=='probability_only' or r['expected_net_return']>0)]
        rank_key='expected_net_return' if selector=='positive_expectancy_net_rank' else 'probability'
        chosen=sorted(eligible,key=lambda r:(-r[rank_key],r['symbol']))[:3]
        scores={r['symbol']:1-i*.1 for i,r in enumerate(chosen)}
        selected.extend(dict(r,forecast_probability=r['probability'],
            probability=scores.get(r['symbol'],0),selection_score_is_probability=False) for r in rows)
    return selected


def run(data,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data);rows=extended_rows(by_date)
    report=dict(status='running_exposed_historical_research',protocol=PROTOCOL,evidence=evidence,
        dependency_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['conditional_payoff_research.py','tighter_stop_simulator.py','regime_predictive_research.py',
                'predictive_portfolio_research.py','prospective_series_audit.py','active_stock_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['All historical dates already exposed; repeated experiments are development only',
            'Predicted positive expectancy is not proof of real profit; errors can compound across heads',
            'Conditional gain/loss models are fitted only on past fills; real execution selection may differ',
            'Fixed present-day universe, full-session exclusions and raw splits remain biased',
            'Assumed delayed SIP receipt, minute OHLC stop-first fills and EOD guards are not live execution',
            'Ranking score is an ordinal selector, not a calibrated probability; no independent evidence'])
    for kind in PROTOCOL['models']:
        predictions,folds=walk(rows,by_date,kind)
        for selector in PROTOCOL['selectors']:
            case=dict(model=kind,selector=selector,folds=folds,outcomes=[])
            for threshold in PROTOCOL['thresholds']:
                selected=selection(predictions,selector,threshold)
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(selected,by_date,.01,.5,cost,delay)
                    result['probability_threshold']=threshold
                    result['simulator_threshold_is_ordinal']=True
                    result.update(metrics=accounting_metrics(result,selected),cost_diagnostic=diagnostic(result))
                    case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(model=kind,selector=selector,threshold=threshold,
                            active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                            net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_historical_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/conditional_payoff'))
    args=parser.parse_args();run(args.data,args.output)
