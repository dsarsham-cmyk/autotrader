"""Isolated stop-policy simulator; fixed stock/category budgets, NEVER orders.

Only stricter stops <=1% allowed. Original frozen sources remain unchanged.
Gap/slippage can exceed planned stop losses: triggers are not loss guarantees.
"""
import math
import numpy as np
from predictive_research import wilson
from fixed_trade_cost_diagnostic import trade_record

INITIAL=100000.


def validate_stop(stop_fraction):
    if isinstance(stop_fraction,bool) or not math.isfinite(stop_fraction) or not 0<stop_fraction<=.01:
        raise ValueError('Only finite positive stops no wider than existing 1% allowed')


def path(a,signal_price,stop_fraction,cost_bps=10,delay=16):
    validate_stop(stop_fraction)
    a=np.asarray(a,dtype=float)
    if a.shape!=(390,5) or not np.isfinite(a).all() or (a[:,:4]<=0).any() or (a[:,4]<0).any():
        raise ValueError('Complete finite positive OHLCV required')
    if (a[:,1]<a[:,2]).any() or (a[:,1]<a[:,[0,3]].max(axis=1)).any() or (a[:,2]>a[:,[0,3]].min(axis=1)).any():
        raise ValueError('Inconsistent OHLC prices')
    if not math.isfinite(signal_price) or signal_price<=0 or not 0<=cost_bps<10000:
        raise ValueError('Invalid signal price/cost')
    if isinstance(delay,bool) or not isinstance(delay,int) or not 1<=delay<355:
        raise ValueError('Invalid execution timing')
    i=30+delay;finish=min(385,i+60);cost=cost_bps/10000
    raw=float(a[i,0]);entry=raw*(1+cost);stop=raw*(1-stop_fraction);target=raw*1.004
    limit=signal_price*1.001;filled=entry<=limit
    exit_price,exit_minute,reason=float(a[finish,0]),finish,'horizon'
    for k in range(i,finish):
        if float(a[k,2])<=stop:
            exit_price,exit_minute,reason=min(float(a[k,0]),stop),k,'stop';break
        if float(a[k,1])>=target:
            exit_price,exit_minute,reason=target,k,'target';break
    net=exit_price*(1-cost)/entry-1
    return dict(entry=entry,stop=stop,limit=limit,filled=bool(filled),exit=exit_price*(1-cost),
        entry_minute=i,exit_minute=exit_minute,reason=reason,label=int(net>0),cost=cost)


def theoretical_economics(stop_fraction,cost_bps=10):
    validate_stop(stop_fraction);cost=cost_bps/10000
    gain=(1.004*(1-cost)/(1+cost)-1)
    loss=(1-(1-stop_fraction)*(1-cost)/(1+cost))
    return dict(ideal_target_net_fraction=gain,ideal_stop_net_loss_fraction=loss,
        exact_target_stop_trade_breakeven_win_rate_pct=100*loss/(gain+loss) if gain>0 else None,
        status='algebra_only_no_gaps_or_other_costs',
        note='Trade break-even is not day accuracy; gap/latency and variable horizon exits change economics')


def portfolio(predictions,by_date,stop_fraction,threshold,cost_bps=10,delay=16):
    validate_stop(stop_fraction)
    if not math.isfinite(threshold) or not 0<=threshold<=1: raise ValueError('Invalid probability threshold')
    grouped={};seen=set()
    for row in predictions:
        key=(row['date'],row['symbol'])
        if key in seen: raise ValueError('Duplicate symbol/date forecast')
        seen.add(key)
        if not math.isfinite(row['probability']) or not 0<=row['probability']<=1:
            raise ValueError('Invalid predicted probability')
        grouped.setdefault(row['date'],[]).append(row)
    equity=peak=INITIAL;permanent=False;daily=[];trades=[]
    for date,rows in sorted(grouped.items()):
        start=equity;committed=0.;positions=[]
        candidates=sorted([r for r in rows if r['probability']>=threshold],key=lambda r:(-r['probability'],r['symbol']))[:3] if not permanent else []
        for row in candidates:
            outcome=path(by_date[date][row['symbol']][0],row['signal_price'],stop_fraction,cost_bps,delay)
            if not outcome['filled']: continue
            risk=outcome['entry']-outcome['stop']*(1-outcome['cost'])
            qty=math.floor(min(start*.01/outcome['limit'],start*.0005/risk,
                max(0,start*.05-committed)/outcome['limit']))
            if qty<=0: continue
            committed+=qty*outcome['limit'];positions.append(dict(row,outcome=outcome,qty=qty))
        held=list(positions);realized=0.;worst=0.;guard=False
        def close_position(position,px,reason,minute):
            outcome=position['outcome']
            trade=trade_record(date,position['symbol'],position['qty'],outcome['entry'],px,outcome['cost'],reason)
            trade.update(stop_fraction=stop_fraction,planned_stop=outcome['stop'],
                reserved_usd=position['qty']*outcome['limit'],entry_minute=outcome['entry_minute'],exit_minute=minute)
            trades.append(trade)
            return trade['pnl']
        for k in range(30+delay,386):
            for position in list(held):
                outcome=position['outcome']
                if outcome['exit_minute']==k:
                    realized+=close_position(position,outcome['exit'],outcome['reason'],k);held.remove(position)
            adverse=start+realized+sum(p['qty']*(by_date[date][p['symbol']][0][k,2]*(1-p['outcome']['cost'])-p['outcome']['entry']) for p in held)
            worst=min(worst,adverse/start-1)
            if (adverse<=start*.99 or adverse<=peak*.9 or adverse<=90000) and held:
                for position in held:
                    a=by_date[date][position['symbol']][0];minute=min(k+1,389)
                    px=float(a[minute,0])*(1-position['outcome']['cost'])
                    realized+=close_position(position,px,'account_guard',minute)
                held=[];guard=True
            if adverse<=peak*.9 or adverse<=90000: permanent=True
        equity=start+realized;peak=max(peak,equity)
        daily.append(dict(date=date,pnl=realized,equity=equity,active=bool(positions),
            committed_usd=committed,worst_marked_pct=worst*100,guard=guard,
            realized_loss_exceeded_daily_trigger=realized<-.01*start,
            permanent_halt=permanent))
    active=[d for d in daily if d['active']];wins=sum(d['pnl']>0 for d in active)
    interval=wilson(wins,len(active));gains=sum(max(0,d['pnl']) for d in daily);losses=-sum(min(0,d['pnl']) for d in daily)
    return dict(stop_fraction=stop_fraction,threshold=threshold,costs_bps=cost_bps,delay=delay,
        sessions=len(daily),active_days=len(active),no_trade_days=len(daily)-len(active),
        coverage_pct=len(active)/len(daily)*100 if daily else 0,
        active_day_win_rate_pct=wins/len(active)*100 if active else None,win_rate_interval=interval,
        profit_usd=equity-INITIAL,profit_factor=gains/losses if losses else None,
        worst_day_usd=min((d['pnl'] for d in daily),default=0),
        target_screen_pass=bool(len(active)>=100 and interval[0]>=90 and equity>INITIAL),
        actual_tighter_stop_planned_risk_pass=all(t['quantity']*(t['entry']-t['planned_stop']*(1-t['per_side_cost_bps']/10000))
            <=(INITIAL if index==0 else daily[index-1]['equity'])*.0005+1e-7
            for index,day in enumerate(daily) for t in trades if t['date']==day['date']),
        daily_trigger_gap_overshoot_days=sum(d['realized_loss_exceeded_daily_trigger'] for d in daily),
        independent_validation_pass=False,production_approved=False,orders=False,daily=daily,trades=trades)
