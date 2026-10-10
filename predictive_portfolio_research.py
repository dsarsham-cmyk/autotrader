"""Exploratory multi-stock model comparison, NOT untouched validation.

Past dates were already inspected in other research; every outcome here is
development evidence only. Fixed small experiment sleeve; no broker API.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss
from active_stock_research import load_universe
from predictive_research import raw_score, wilson

PROTOCOL = dict(status='exploration_only', calibration='profit conditional on simulated limit fill', universe='fixed current 20-stock universe',
    decision_minutes=[15,30], exits=['60_minutes','session','target_60','target_session'],
    models=['logistic','boosted'], thresholds=[.5,.65,.8,.9],
    stock_cap_fraction=.01, category_cap_fraction=.05, max_positions=3,
    stop_fraction=.01, target_fraction=.004, per_side_cost_bps=10, stress_per_side_cost_bps=20,
    entry_delay_minutes=1, stress_entry_delay_minutes=2,
    max_planned_risk_fraction=.0005, daily_entry_cutoff=.005,
    daily_exit_trigger=.01, permanent_drawdown=.10,
    shorting=False, overnight=False, broker_orders=False,
    independent_forward_start='2026-10-12', target_active_day_win_rate=.9)
FEATURES=['intraday_return','gap','range','location','relative_opening_volume',
          'prior_return','prior_five_return','prior_volatility',
          'market_open_return','cross_section_rank','late_vs_early_return']


def build(by_date, minute):
    history, rows = {}, []
    for date, stocks in sorted(by_date.items()):
        opening_returns={s:float(a[minute-1,3]/a[0,0]-1) for s,(a,_) in stocks.items()}
        market=float(np.mean(list(opening_returns.values())))
        ranked=sorted(opening_returns,key=lambda s:(opening_returns[s],s))
        for symbol,(a,info) in sorted(stocks.items()):
            prior=history.setdefault(symbol,[])
            if len(prior)>=21 and info['prior_dollars']>=20000000:
                close=a[minute-1,3]; first=a[0,0]
                hi,lo=float(a[:minute,1].max()),float(a[:minute,2].min())
                old=[h for h in prior[-21:]]
                feature=[opening_returns[symbol],first/old[-1]-1,(hi-lo)/first,
                    (close-lo)/(hi-lo) if hi>lo else .5,info['relative_volume'],
                    old[-1]/old[-2]-1,old[-1]/old[-6]-1,
                    float(np.std(np.diff(np.log(old)))),market,
                    ranked.index(symbol)/max(1,len(ranked)-1),
                    close/a[4,3]-1]
                if not np.isfinite(feature).all():
                    raise ValueError('Non-finite model features')
                rows.append(dict(date=date,symbol=symbol,features=feature,
                    signal_price=float(close),relative_volume=info['relative_volume']))
            prior.append(float(a[-1,3]))
    return rows


def path_outcome(a, signal_price, minute, horizon, cost_bps=10, delay=1):
    i=minute+delay
    finish=min(385,i+60) if horizon in {'60_minutes','target_60'} else 385
    cost=cost_bps/10000
    # Frozen signal-based limit; no retrospective intrabar fill assumptions.
    limit=signal_price*1.001
    entry=float(a[i,0])*(1+cost)
    stop=float(a[i,0])*.99
    target=float(a[i,0])*1.004 if horizon.startswith('target_') else None
    filled=entry<=limit
    exit_price,exit_minute,reason=float(a[finish,0]),finish,'horizon'
    for k in range(i,finish):
        if float(a[k,2])<=stop:
            exit_price,exit_minute,reason=min(float(a[k,0]),stop),k,'stop'
            break
        if target is not None and float(a[k,1])>=target:
            # Same-minute stop wins if both touched. No favorable gap bonus.
            exit_price,exit_minute,reason=target,k,'target'
            break
    net=exit_price*(1-cost)/entry-1
    return dict(entry=entry,stop=stop,limit=limit,filled=bool(filled),
        exit=exit_price*(1-cost),entry_minute=i,exit_minute=exit_minute,
        reason=reason,label=int(net>0),cost=cost)


def partition(rows, dates):
    chosen=set(dates)
    return [r for r in rows if r['date'] in chosen]


def fit_predict(train, calibration, test, kind, labels):
    # Label map is keyed by date AND symbol; all splits group entire dates.
    x=np.array([r['features'] for r in train]); y=np.array([labels[(r['date'],r['symbol'])] for r in train])
    classifier=(LogisticRegression(C=.1,max_iter=1000,random_state=19) if kind=='logistic'
        else HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,
            min_samples_leaf=30,l2_regularization=10,random_state=19,early_stopping=False))
    model=make_pipeline(StandardScaler(),classifier)
    model.fit(x,y)
    cx=np.array([r['features'] for r in calibration])
    cy=np.array([labels[(r['date'],r['symbol'])] for r in calibration])
    calibrator=LogisticRegression(C=1,max_iter=1000,random_state=19)
    calibrator.fit(raw_score(model,cx),cy)
    tx=np.array([r['features'] for r in test])
    return calibrator.predict_proba(raw_score(model,tx))[:,1]


def walk_forward(rows, by_date, minute, horizon, kind):
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path_outcome(by_date[r['date']][r['symbol']][0],
            r['signal_price'],minute,horizon) for r in rows}
    labels={key:o['label'] for key,o in outcomes.items()}
    predictions,folds=[],[]
    # Fixed expanding training, separate recent calibration, then future fold.
    for start in range(240,len(dates),20):
        train_dates,cal_dates,test_dates=dates[:start-60],dates[start-60:start],dates[start:start+20]
        train,cal,test=[partition(rows,d) for d in [train_dates,cal_dates,test_dates]]
        if not test: continue
        # Predict profit CONDITIONAL on execution. An unfilled past order is
        # not a winning or losing completed trade. Filtering only past train/
        # calibration outcomes is legitimate; test candidates are NOT filtered
        # before prediction, selection or sizing.
        train=[r for r in train if outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if outcomes[(r['date'],r['symbol'])]['filled']]
        p=fit_predict(train,cal,test,kind,labels)
        predictions.extend([dict(r,probability=float(v)) for r,v in zip(test,p)])
        matched=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        folds.append(dict(train_last=train_dates[-1],cal_first=cal_dates[0],
            cal_last=cal_dates[-1],test_first=test_dates[0],test_last=test_dates[-1],
            filled_train_samples=len(train),filled_calibration_samples=len(cal),
            brier_filled=float(brier_score_loss([labels[(test[i]['date'],test[i]['symbol'])] for i in matched],p[matched])) if matched else None))
    return predictions,folds


def portfolio(predictions, by_date, minute, horizon, threshold, costs_bps=10, delay=1):
    equity,peak,permanent=100000.,100000.,False
    daily,trades=[],[]
    dates=sorted({r['date'] for r in predictions})
    for date in dates:
        start=equity
        candidates=[r for r in predictions if r['date']==date and r['probability']>=threshold]
        selected=sorted(candidates,key=lambda r:(-r['probability'],r['symbol']))[:3] if not permanent else []
        positions=[]
        committed=0.
        for r in selected:
            a=by_date[date][r['symbol']][0]
            outcome=path_outcome(a,r['signal_price'],minute,horizon,costs_bps,delay)
            if not outcome['filled']: continue
            risk=outcome['entry']-outcome['stop']*(1-outcome['cost'])
            qty=math.floor(min(start*.01/outcome['limit'],start*.0005/risk,
                               max(0,start*.05-committed)/outcome['limit']))
            if qty<=0: continue
            committed+=qty*outcome['limit']
            positions.append(dict(r,outcome=outcome,qty=qty))
        realized=0.; held=list(positions); worst=0.; guard=False
        for k in range(minute+delay,386):
            for p in list(held):
                o=p['outcome']
                if o['exit_minute']==k:
                    pnl=p['qty']*(o['exit']-o['entry']); realized+=pnl
                    trades.append(dict(date=date,symbol=p['symbol'],pnl=pnl,reason=o['reason']))
                    held.remove(p)
            adverse=start+realized+sum(p['qty']*(by_date[date][p['symbol']][0][k,2]*(1-p['outcome']['cost'])-p['outcome']['entry']) for p in held)
            worst=min(worst,adverse/start-1)
            if (adverse<=start*.99 or adverse<=peak*.9 or adverse<=90000) and held:
                # Latency: liquidate at NEXT minute open, not a known low.
                for p in held:
                    a=by_date[date][p['symbol']][0]
                    px=float(a[min(k+1,389),0])*(1-p['outcome']['cost'])
                    pnl=p['qty']*(px-p['outcome']['entry']);realized+=pnl
                    trades.append(dict(date=date,symbol=p['symbol'],pnl=pnl,reason='account_guard'))
                held=[];guard=True
            if adverse<=peak*.9 or adverse<=90000: permanent=True
        equity=start+realized;peak=max(peak,equity)
        daily.append(dict(date=date,pnl=realized,equity=equity,active=bool(positions),
            committed_usd=committed,worst_marked_pct=worst*100,guard=guard))
    active=[d for d in daily if d['active']]
    wins=sum(d['pnl']>0 for d in active)
    gains=sum(max(0,d['pnl']) for d in daily);losses=-sum(min(0,d['pnl']) for d in daily)
    interval=wilson(wins,len(active))
    return dict(threshold=threshold,costs_bps=costs_bps,delay=delay,
        sessions=len(dates),active_days=len(active),no_trade_days=len(dates)-len(active),
        coverage_pct=len(active)/len(dates)*100 if dates else 0,
        active_day_win_rate_pct=wins/len(active)*100 if active else None,
        win_rate_interval=interval,profit_usd=equity-100000,
        profit_factor=gains/losses if losses else None,
        worst_day_usd=min((d['pnl'] for d in daily),default=0),
        target_screen_pass=bool(len(active)>=100 and interval[0]>=90 and equity>100000),
        independent_validation_pass=False,daily=daily,trades=trades)


def run(directory, output):
    output.mkdir(parents=True,exist_ok=True)
    by_date,evidence=load_universe(directory)
    report=dict(protocol=PROTOCOL,features=FEATURES,evidence=evidence,cases=[],
        source_sha256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        limitations=['All past dates exploratory and already exposed in related research',
            'Fixed current universe creates selection/survivorship bias',
            'SIP data cannot silently substitute for live IEX forecasts',
            'OHLC fills and simultaneous lows are simulated, not tick execution',
            'Calibration is conditional on simulated fills; live fill selection may differ',
            'No model is allowed to place orders; final forward start October 12 or later'])
    for minute in [15,30]:
        rows=build(by_date,minute)
        for horizon in ['60_minutes','session','target_60','target_session']:
            for model in ['logistic','boosted']:
                predictions,folds=walk_forward(rows,by_date,minute,horizon,model)
                case=dict(minute=minute,horizon=horizon,model=model,folds=folds,outcomes=[])
                for threshold in [.5,.65,.8,.9]:
                    for cost,delay in [(10,1),(20,1),(10,2)]:
                        result=portfolio(predictions,by_date,minute,horizon,threshold,cost,delay)
                        case['outcomes'].append(result)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
                best=max(case['outcomes'],key=lambda r:r['profit_usd'])
                print(json.dumps(dict(minute=minute,horizon=horizon,model=model,
                    best_profit=best['profit_usd'],active_days=best['active_days'],
                    win_rate=best['active_day_win_rate_pct'],threshold=best['threshold'],
                    screen_pass=best['target_screen_pass'])),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('cache/active_stocks'))
    p.add_argument('--output',type=Path,default=Path('research_runs/predictive_portfolio'))
    args=p.parse_args();run(args.data,args.output)
