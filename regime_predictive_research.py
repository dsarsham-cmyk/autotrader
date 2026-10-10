"""Past-only VWAP/volume signals plus expected profit and downside forecasts.

Development research on exposed dates; no independent validation or orders.
Gate thresholds are fixed before this experiment, not optimized on test folds.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

from active_stock_research import load_universe
from predictive_portfolio_research import build, partition, path_outcome, portfolio, FEATURES
from predictive_research import raw_score

EXTRA_FEATURES=['distance_from_opening_vwap','opening_path_efficiency',
    'opening_realized_volatility','same_window_relative_volume',
    'opening_range_vs_prior_daily_range','last_five_return','last_five_volume_share',
    'cross_section_dispersion','market_positive_breadth','market_above_vwap_breadth']


def vwap(a,minute):
    window=a[:minute]
    volume=window[:,4]
    if volume.sum()<=0: raise ValueError('No opening volume')
    return float(np.dot((window[:,1]+window[:,2]+window[:,3])/3,volume)/volume.sum())


def extended_rows(by_date,minute=30):
    base={(r['date'],r['symbol']):r for r in build(by_date,minute)}
    rows=[]
    history={}
    for date,stocks in sorted(by_date.items()):
        changes=[a[minute-1,3]/a[0,0]-1 for a,_ in stocks.values()]
        dispersion=float(np.std(changes))
        positive=float(np.mean(np.array(changes)>0))
        above=float(np.mean([a[minute-1,3]>vwap(a,minute) for a,_ in stocks.values()]))
        for symbol,(a,_) in sorted(stocks.items()):
            prior=history.setdefault(symbol,[])
            key=(date,symbol)
            if key in base:
                if len(prior)<20: raise ValueError('Insufficient past volume history')
                close=a[minute-1,3]
                prices=np.r_[a[0,0],a[:minute,3]]
                changes_price=np.diff(prices)
                movement=float(np.abs(changes_price).sum())
                opening_volume=float(a[:minute,4].sum())
                prior_volume=float(np.mean([p[0] for p in prior[-20:]]))
                prior_range=float(np.mean([p[1] for p in prior[-20:]]))
                extra=[close/vwap(a,minute)-1,
                    float((prices[-1]-prices[0])/movement) if movement else 0,
                    float(np.sqrt(np.sum(np.diff(np.log(prices))**2))),
                    opening_volume/prior_volume if prior_volume else 0,
                    float((a[:minute,1].max()-a[:minute,2].min())/a[0,0])/prior_range if prior_range else 0,
                    close/a[minute-6,3]-1,float(a[minute-5:minute,4].sum()/opening_volume),
                    dispersion,positive,above]
                if not np.isfinite(extra).all(): raise ValueError('Nonfinite regime feature')
                rows.append(dict(base[key],features=base[key]['features']+extra))
            # Full-session data are appended only AFTER this session's signal.
            history[symbol].append((float(a[:minute,4].sum()),
                float((a[:,1].max()-a[:,2].min())/a[0,0])))
    return rows


def forecasts(train,calibration,test,outcomes):
    x=np.array([r['features'] for r in train])
    cx=np.array([r['features'] for r in calibration])
    tx=np.array([r['features'] for r in test])
    def returns(rows):
        return np.array([outcomes[(r['date'],r['symbol'])]['exit']/
            outcomes[(r['date'],r['symbol'])]['entry']-1 for r in rows])
    y,cy=returns(train),returns(calibration)
    if len(set(y>0))<2 or len(set(cy>0))<2:
        raise ValueError('Two outcomes required for separate calibration')
    settings=dict(max_iter=100,max_leaf_nodes=7,min_samples_leaf=30,
        l2_regularization=10,random_state=19,early_stopping=False)
    classifier=HistGradientBoostingClassifier(**settings).fit(x,y>0)
    calibrator=LogisticRegression(C=1,random_state=19).fit(raw_score(classifier,cx),cy>0)
    mean=HistGradientBoostingRegressor(loss='squared_error',**settings).fit(x,y)
    downside=HistGradientBoostingRegressor(loss='quantile',quantile=.1,**settings).fit(x,y)
    # Fixed past calibration corrections; never fit on the next test block.
    mean_offset=float(np.mean(cy-mean.predict(cx)))
    downside_offset=float(np.quantile(cy-downside.predict(cx),.1))
    return dict(probability=calibrator.predict_proba(raw_score(classifier,tx))[:,1],
        mean_return=mean.predict(tx)+mean_offset,
        q10_return=downside.predict(tx)+downside_offset)


def run(data,output):
    by_date,evidence=load_universe(data)
    extended=extended_rows(by_date)
    dates=sorted({r['date'] for r in extended})
    report=dict(status='exploration_only',independent_validation_pass=False,evidence=evidence,
        dependency_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['regime_predictive_research.py','predictive_portfolio_research.py',
                'fixed_trade_cost_diagnostic.py','active_stock_research.py','predictive_research.py']},
        protocol=dict(decision_minute=30,horizons=['target_60','target_session'],
            feature_sets=['baseline','vwap_volume_regime'],thresholds=[.65,.9],
            gate_variants=['probability_only','positive_mean_and_q10_above_minus_1pct'],
            mean_minimum=0,q10_minimum=-.01,orders=False),
        limitations=['Exposed dates are exploratory; no independent forward evidence',
            'Fixed present-day stock universe and complete-session exclusions create selection bias',
            'VWAP is a bar typical-price approximation, not trade-level exact VWAP',
            'Q10 describes a distribution tail, not a guaranteed maximum loss',
            'Past-only fit does not eliminate repeated-experiment selection bias',
            'OHLC execution, costs and portfolio guards retain simulator limitations'],cases=[])
    output.mkdir(parents=True,exist_ok=True)
    for horizon in ['target_60','target_session']:
        outcomes={(r['date'],r['symbol']):path_outcome(by_date[r['date']][r['symbol']][0],
            r['signal_price'],30,horizon) for r in extended}
        for feature_set in ['baseline','vwap_volume_regime']:
            rows=[dict(r,features=r['features'][:len(FEATURES)]) for r in extended] if feature_set=='baseline' else extended
            predictions,folds=[],[]
            for start in range(240,len(dates),20):
                train,cal,test=[partition(rows,d) for d in
                    [dates[:start-60],dates[start-60:start],dates[start:start+20]]]
                train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
                cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
                forecast=forecasts(train,cal,test,outcomes)
                predictions.extend(dict(r,**{k:float(v[i]) for k,v in forecast.items()}) for i,r in enumerate(test))
                matched=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
                actual=np.array([outcomes[(test[i]['date'],test[i]['symbol'])]['exit']/
                    outcomes[(test[i]['date'],test[i]['symbol'])]['entry']-1 for i in matched])
                folds.append(dict(train_last=dates[start-61],calibration_last=dates[start-1],
                    test_first=dates[start],test_last=dates[min(start+19,len(dates)-1)],
                    brier_filled=float(brier_score_loss(actual>0,forecast['probability'][matched])) if matched else None,
                    mean_absolute_return_error=float(np.mean(abs(actual-forecast['mean_return'][matched]))) if matched else None,
                    fraction_below_q10=float(np.mean(actual<forecast['q10_return'][matched])) if matched else None))
            for gate in ['probability_only','positive_mean_and_q10_above_minus_1pct']:
                selected=[dict(r,probability=r['probability'] if gate=='probability_only' or
                    (r['mean_return']>0 and r['q10_return']>-.01) else 0.) for r in predictions]
                case=dict(feature_set=feature_set,model='boosted_probability_mean_q10',horizon=horizon,
                    gate=gate,minute=30,folds=folds,outcomes=[])
                for threshold in [.65,.9]:
                    for cost,delay in [(10,1),(20,1),(10,2)]:
                        case['outcomes'].append(portfolio(selected,by_date,30,horizon,threshold,cost,delay))
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
                print(json.dumps(dict(features=feature_set,horizon=horizon,gate=gate,primary=[
                    {k:r[k] for k in ['threshold','active_days','active_day_win_rate_pct','profit_usd','target_screen_pass']}
                    for r in case['outcomes'] if r['costs_bps']==10 and r['delay']==1])),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/active_stocks'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/regime_predictive'))
    args=parser.parse_args();run(args.data,args.output)
