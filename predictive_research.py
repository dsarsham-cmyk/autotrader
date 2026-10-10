"""Isolated probabilistic research: no broker imports, orders or promotion.

QQQ-only present-day hypothesis. All features end at 09:34:59 NY. Entry
09:36 open allows a full minute of latency; exit 15:55, static 1% stop.
Costs charged both ways. Final chronological 20% never used to fit/select.
This is not a replay of the production strategy and cannot certify its edge.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import brier_score_loss, log_loss
from intraday_research import sessions

FEATURES = ['opening_return', 'opening_range', 'opening_location', 'gap',
            'relative_volume', 'prior_return', 'prior_five_return', 'prior_volatility']
THRESHOLDS = [.5, .6, .7, .8, .9]
RULES = dict(symbol='QQQ', feature_cutoff='09:35 NY', entry='09:36 NY',
             exit='15:55 NY', stop_fraction=.01, capital_fraction=.05,
             max_planned_account_risk=.0005, entry_loss_cutoff=.005,
             liquidation_loss_trigger=.01, reserve_fraction=.20,
             cost_bps_each_side=10, target_active_day_win_rate=.90,
             final_test_fraction=.20, calibration_fraction=.20,
             same_day_reentry=False, overnight=False, order_submission=False)


def opening_features(opening, history):
    """Only five completed opening minutes and 21 prior complete sessions."""
    if len(opening) != 5 or len(history) < 21:
        raise ValueError('Need exactly five opening bars and 21 prior sessions')
    first, last = float(opening.iloc[0].open), float(opening.iloc[-1].close)
    high, low = float(opening.high.max()), float(opening.low.min())
    closes = [h['close'] for h in history]
    returns = np.diff(np.log(closes[-21:]))
    vol = float(opening.volume.sum())
    feature = [last/first-1, (high-low)/first,
               (last-low)/(high-low) if high > low else .5,
               first/closes[-1]-1, vol/np.mean([h['opening_volume'] for h in history[-20:]]),
               closes[-1]/closes[-2]-1, closes[-1]/closes[-6]-1,
               float(np.std(returns))]
    if not np.isfinite(feature).all():
        raise ValueError('Non-finite features')
    return feature


def example(date, bars, history, costs_bps=10, delay=1):
    """Feature construction cannot read the future, labels deliberately do."""
    opening = bars.iloc[:5]
    feature = opening_features(opening, history)
    last = float(opening.iloc[-1].close)
    index = 5+delay
    cost = costs_bps/10000
    # The completed signal fixes a limit; a gap above it is NOT filled later.
    limit = last*(1+cost)
    raw_entry = float(bars.iloc[index].open)
    entry = raw_entry*(1+cost)
    filled = entry <= limit
    stop = raw_entry*(1-RULES['stop_fraction'])
    exit_raw, exit_reason = float(bars.iloc[385].open), 'session'
    for _, bar in bars.iloc[index:385].iterrows():
        if float(bar.low) <= stop:
            exit_raw, exit_reason = min(float(bar.open), stop), 'stop'
            break
    net_return = exit_raw*(1-cost)/entry-1
    return dict(date=date, features=feature, filled=bool(filled),
                net_return=float(net_return), label=int(net_return > 0),
                raw_entry=raw_entry, entry=entry, exit=exit_raw*(1-cost),
                stop=stop, limit=limit, cost_fraction=cost, exit_reason=exit_reason)


def dataset(days):
    history, records = [], []
    for date, bars in days:
        if len(history) >= 21:
            records.append(example(date, bars, history))
        history.append(dict(close=float(bars.iloc[-1].close),
                            opening_volume=float(bars.iloc[:5].volume.sum())))
    return records


def split(records):
    n = len(records)
    if n < 200:
        raise ValueError('At least 200 feature-complete sessions required')
    left, right = int(n*.6), int(n*.8)
    return records[:left], records[left:right], records[right:]


def arrays(records):
    return np.array([r['features'] for r in records]), np.array([r['label'] for r in records])


def raw_score(model, x):
    p = np.clip(model.predict_proba(x)[:, 1], 1e-6, 1-1e-6)
    return np.log(p/(1-p)).reshape(-1, 1)


def fit(train, calibration, kind):
    x, y = arrays(train)
    if len(set(y)) < 2:
        raise ValueError('Training needs both outcomes')
    classifier = (LogisticRegression(C=1, max_iter=1000, random_state=7) if kind == 'logistic'
                  else MLPClassifier(hidden_layer_sizes=(16,), alpha=1,
                       max_iter=1000, random_state=7, shuffle=False, early_stopping=False))
    model = make_pipeline(StandardScaler(), classifier)
    model.fit(x, y)
    cx, cy = arrays(calibration)
    if len(set(cy)) < 2:
        raise ValueError('Calibration needs both outcomes')
    calibrator = LogisticRegression(C=1, max_iter=1000, random_state=7)
    calibrator.fit(raw_score(model, cx), cy)
    return model, calibrator


def probability(model, calibrator, records):
    return calibrator.predict_proba(raw_score(model, arrays(records)[0]))[:, 1]


def wilson(wins, count):
    if not count:
        return [None, None]
    p, z = wins/count, 1.96
    center = (p+z*z/(2*count))/(1+z*z/count)
    radius = z*math.sqrt(p*(1-p)/count+z*z/(4*count*count))/(1+z*z/count)
    return [round((center-radius)*100, 3), round((center+radius)*100, 3)]


def evaluate(records, probabilities, threshold):
    equity, peak, max_dd = 100000., 100000., 0.
    trades, daily = [], []
    halted = False
    for row, p in zip(records, probabilities):
        selected = p >= threshold and not halted
        pnl = 0.
        if selected and row['filled']:
            # Cash-only small research sleeve. Stop sizing includes friction.
            qty = math.floor(min(equity*.05/row['limit'],
                equity*.0005/(row['entry']-row['stop']*(1-row.get('cost_fraction',.001)))))
            pnl = qty*(row['exit']-row['entry'])
            if qty:
                trades.append(dict(date=row['date'], probability=float(p),
                                   qty=qty, pnl=pnl, exit_reason=row['exit_reason']))
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, 1-equity/peak)
        halted = halted or equity <= 90000 or equity <= peak*.9
        daily.append(dict(date=row['date'], equity=equity, pnl=pnl))
    wins = sum(t['pnl'] > 0 for t in trades)
    gains = sum(max(0,t['pnl']) for t in trades)
    losses = -sum(min(0,t['pnl']) for t in trades)
    count = len(trades)
    return dict(threshold=threshold, sessions=len(records), active_days=count,
        no_trade_days=len(records)-count, coverage_pct=count/len(records)*100,
        win_rate_pct=wins/count*100 if count else None,
        win_rate_95pct_interval=wilson(wins,count), net_profit_usd=equity-100000,
        return_pct=(equity/100000-1)*100, max_close_drawdown_pct=max_dd*100,
        profit_factor=gains/losses if losses else None,
        average_win_usd=gains/wins if wins else None,
        average_loss_usd=losses/(count-wins) if count>wins else None,
        worst_day_usd=min(d['pnl'] for d in daily),
        target_demonstrated=bool(count>=100 and wilson(wins,count)[0]>=90 and equity>100000),
        trades=trades, daily=daily)


def run(path, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(path)
    days, excluded = sessions(data)
    records = dataset(days)
    train, cal, test = split(records)
    report = dict(rules=RULES, features=FEATURES, mode='offline research, no orders',
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),
        complete_sessions=len(days), excluded_sessions=len(excluded),
        splits={name:dict(first=rows[0]['date'],last=rows[-1]['date'],count=len(rows))
                for name,rows in [('train',train),('calibration',cal),('test',test)]},
        baseline=evaluate(test,np.ones(len(test)),0), models={},
        limitations=['One symbol and one fixed horizon; not production portfolio replay',
            'Minute OHLC simulation is not tick execution; stop gaps can exceed planned risk',
            'QQQ SIP-trained models cannot silently run on IEX observations',
            'Test thresholds are descriptive; no winner is selected on final test',
            'Final test is now consumed; further tuning needs new untouched data',
            'No real money or automatic model promotion'])
    for kind in ['logistic','neural']:
        model, calibrator = fit(train,cal,kind)
        p = probability(model,calibrator,test)
        y = arrays(test)[1]
        weights = (model[-1].coef_.tolist() if kind=='logistic'
                   else [a.tolist() for a in model[-1].coefs_])
        report['models'][kind]=dict(brier=float(brier_score_loss(y,p)),
            log_loss=float(log_loss(y,p,labels=[0,1])),
            probability_range=[float(min(p)),float(max(p))],
            learned_weights=weights, calibration_weights=calibrator.coef_.tolist(),
            outcomes=[evaluate(test,p,t) for t in THRESHOLDS])
        joblib.dump(dict(model=model,calibrator=calibrator,features=FEATURES,
            trained_through=cal[-1]['date'],rules=RULES,mode='shadow_only'),
            output.parent/f'{kind}_shadow.joblib')
        print(kind, json.dumps({k:v for k,v in report['models'][kind].items()
                               if k not in ['learned_weights','outcomes']}),flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print('Results:', output,flush=True)
    return report


def shadow_probability(artifact, opening, prior_sessions):
    """Read an OWN locally generated artifact only (joblib is executable).

    No quote/order clients. Caller must supply same SIP feed, completed NY
    opening minutes and chronologically prior sessions, never today's close.
    Returned candidate is informational and has no trading authority.
    """
    if artifact.get('mode') != 'shadow_only' or artifact.get('features') != FEATURES:
        raise ValueError('Not a compatible shadow artifact')
    x=np.array([opening_features(opening,prior_sessions)])
    p=float(artifact['calibrator'].predict_proba(raw_score(artifact['model'],x))[0,1])
    return dict(probability=p, threshold=.9, passes_research_threshold=p>=.9,
                broker_orders_enabled=False, validated_for_production=False)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/intraday/QQQ_1m.csv'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/predictive/results.json'))
    args=parser.parse_args()
    run(args.data,args.output)
