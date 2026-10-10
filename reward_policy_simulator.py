"""Alternative profit targets; fixed existing stop, budgets and time horizon.

Not an order engine. Targets change outcomes; they cannot create predictive
information. Gap losses are not capped artificially at planned stop amounts.
"""
import math
import numpy as np
from tighter_stop_simulator import path as reference_path
from predictive_research import wilson
from fixed_trade_cost_diagnostic import trade_record

TARGETS=(.004,.008,.012)
INITIAL=100000.


def validate_target(target_fraction):
    if isinstance(target_fraction,bool) or target_fraction not in TARGETS:
        raise ValueError('Only predeclared profit targets .4%, .8%, 1.2% allowed')


def path(a,signal_price,target_fraction,cost_bps=10,delay=16):
    validate_target(target_fraction)
    # Reuse strict OHLC, cost, signal and latency validation, not its old exit.
    reference=reference_path(a,signal_price,.01,cost_bps,delay)
    a=np.asarray(a,dtype=float);i=reference['entry_minute'];finish=min(385,i+60)
    raw=float(a[i,0]);target=raw*(1+target_fraction)
    exit_price,minute,reason=float(a[finish,0]),finish,'horizon'
    for k in range(i,finish):
        if float(a[k,2])<=reference['stop']:
            exit_price,minute,reason=min(float(a[k,0]),reference['stop']),k,'stop';break
        if float(a[k,1])>=target:
            exit_price,minute,reason=target,k,'target';break
    exit_net=exit_price*(1-reference['cost'])
    return dict(reference,exit=exit_net,exit_minute=minute,reason=reason,
        label=int(exit_net/reference['entry']-1>0),target_fraction=target_fraction)


def economics(target_fraction,cost_bps=10):
    validate_target(target_fraction)
    if not math.isfinite(cost_bps) or not 0<=cost_bps<10000: raise ValueError('Invalid cost')
    cost=cost_bps/10000
    gain=(1+target_fraction)*(1-cost)/(1+cost)-1
    loss=1-.99*(1-cost)/(1+cost)
    return dict(target_fraction=target_fraction,ideal_target_net_fraction=gain,
        ideal_stop_net_loss_fraction=loss,
        exact_trade_breakeven_pct=loss/(loss+gain)*100 if gain>0 else None,
        status='algebra_not_forecast_no_gaps_or_horizon_exits')


def portfolio(predictions,by_date,target_fraction,threshold,cost_bps=10,delay=16):
    validate_target(target_fraction)
    if not math.isfinite(threshold) or not 0<=threshold<=1: raise ValueError('Invalid probability gate')
    grouped={};seen=set()
    for row in predictions:
        key=(row['date'],row['symbol'])
        if key in seen: raise ValueError('Duplicate forecast')
        seen.add(key)
        if not math.isfinite(row['probability']) or not 0<=row['probability']<=1:
            raise ValueError('Invalid probability')
        grouped.setdefault(row['date'],[]).append(row)
    equity=peak=INITIAL;permanent=False;daily=[];trades=[]
    for date,rows in sorted(grouped.items()):
        start=equity;committed=0.;positions=[]
        chosen=sorted([r for r in rows if r['probability']>=threshold],key=lambda r:(-r['probability'],r['symbol']))[:3] if not permanent else []
        for row in chosen:
            outcome=path(by_date[date][row['symbol']][0],row['signal_price'],target_fraction,cost_bps,delay)
            if not outcome['filled']: continue
            risk=outcome['entry']-outcome['stop']*(1-outcome['cost'])
            qty=math.floor(min(start*.01/outcome['limit'],start*.0005/risk,
                max(0,start*.05-committed)/outcome['limit']))
            if qty<=0: continue
            committed+=qty*outcome['limit'];positions.append(dict(row,outcome=outcome,qty=qty))
        held=list(positions);realized=0.;worst=0.;guard=False
        def close(position,px,reason,minute):
            outcome=position['outcome']
            trade=trade_record(date,position['symbol'],position['qty'],outcome['entry'],px,outcome['cost'],reason)
            trade.update(target_fraction=target_fraction,planned_stop=outcome['stop'],
                reserved_usd=position['qty']*outcome['limit'],entry_minute=outcome['entry_minute'],exit_minute=minute)
            trades.append(trade);return trade['pnl']
        for k in range(30+delay,386):
            for position in list(held):
                outcome=position['outcome']
                if outcome['exit_minute']==k:
                    realized+=close(position,outcome['exit'],outcome['reason'],k);held.remove(position)
            adverse=start+realized+sum(p['qty']*(by_date[date][p['symbol']][0][k,2]*(1-p['outcome']['cost'])-p['outcome']['entry']) for p in held)
            worst=min(worst,adverse/start-1)
            if (adverse<=start*.99 or adverse<=peak*.9 or adverse<=90000) and held:
                for position in held:
                    a=by_date[date][position['symbol']][0];minute=min(k+1,389)
                    realized+=close(position,float(a[minute,0])*(1-position['outcome']['cost']),'account_guard',minute)
                held=[];guard=True
            if adverse<=peak*.9 or adverse<=90000: permanent=True
        equity=start+realized;peak=max(peak,equity)
        daily.append(dict(date=date,pnl=realized,equity=equity,active=bool(positions),
            committed_usd=committed,worst_marked_pct=worst*100,guard=guard,
            realized_loss_exceeded_daily_trigger=realized<-.01*start,permanent_halt=permanent))
    active=[d for d in daily if d['active']];wins=sum(d['pnl']>0 for d in active)
    interval=wilson(wins,len(active));gains=sum(max(0,d['pnl']) for d in daily);losses=-sum(min(0,d['pnl']) for d in daily)
    return dict(target_fraction=target_fraction,threshold=threshold,costs_bps=cost_bps,delay=delay,
        sessions=len(daily),active_days=len(active),no_trade_days=len(daily)-len(active),
        coverage_pct=len(active)/len(daily)*100 if daily else 0,
        active_day_win_rate_pct=wins/len(active)*100 if active else None,win_rate_interval=interval,
        profit_usd=equity-INITIAL,profit_factor=gains/losses if losses else None,
        worst_day_usd=min((d['pnl'] for d in daily),default=0),
        daily_trigger_gap_overshoot_days=sum(d['realized_loss_exceeded_daily_trigger'] for d in daily),
        target_screen_pass=bool(len(active)>=100 and interval[0]>=90 and equity>INITIAL),
        independent_validation_pass=False,production_approved=False,orders=False,daily=daily,trades=trades)
