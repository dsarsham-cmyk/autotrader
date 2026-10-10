"""Predeclared60/120-minute holds; unchanged budgets/stops, no broker orders."""
import math
import numpy as np
from predictive_research import wilson
from fixed_trade_cost_diagnostic import trade_record

INITIAL=100000.


def path(bars,signal_price,cost_bps=10,delay=16,horizon=60):
    if horizon not in (60,120) or isinstance(horizon,bool): raise ValueError('Unknown holding horizon')
    if delay not in (16,17) or isinstance(delay,bool): raise ValueError('Unknown fixed timing')
    if not math.isfinite(cost_bps) or not 0<=cost_bps<10000: raise ValueError('Invalid cost')
    if not math.isfinite(signal_price) or signal_price<=0: raise ValueError('Invalid signal')
    def bar(k):
        if k not in bars: return None
        a=np.asarray(bars[k],dtype=float)
        if a.shape!=(5,) or not np.isfinite(a).all() or (a[:4]<=0).any() or a[4]<0:
            raise ValueError('Invalid observed bar')
        if a[1]<max(a[0],a[3],a[2]) or a[2]>min(a[0],a[3]): raise ValueError('Invalid OHLC')
        return a
    i=30+delay;finish=i+horizon;first=bar(i)
    if first is None: return None
    cost=cost_bps/10000;raw=float(first[0]);entry=raw*(1+cost)
    stop=raw*.99;target=raw*1.004;limit=signal_price*1.001
    result=dict(entry=entry,stop=stop,limit=limit,filled=entry<=limit,cost=cost,entry_minute=i)
    if not result['filled']: return result
    reason='horizon';minute=finish;exit_price=None
    for k in range(i,finish):
        a=bar(k)
        if a is None: return None
        if a[2]<=stop: exit_price=min(float(a[0]),stop);minute=k;reason='stop';break
        if a[1]>=target: exit_price=target;minute=k;reason='target';break
    if exit_price is None:
        a=bar(finish)
        if a is None: return None
        exit_price=float(a[0])
    net=exit_price*(1-cost)
    return dict(result,exit=net,exit_minute=minute,reason=reason,label=int(net/entry-1>0))


def portfolio(predictions,market,threshold,cost_bps=10,delay=16,horizon=60):
    if horizon not in (60,120) or isinstance(horizon,bool): raise ValueError('Unknown holding horizon')
    if not math.isfinite(threshold) or not 0<=threshold<=1: raise ValueError('Invalid gate')
    grouped={};seen=set()
    for row in predictions:
        key=(row['date'],row['symbol'])
        if key in seen: raise ValueError('Duplicate forecast')
        seen.add(key)
        if not math.isfinite(row['probability']) or not 0<=row['probability']<=1:
            raise ValueError('Invalid probability')
        grouped.setdefault(row['date'],[]).append(row)
    equity=peak=INITIAL;permanent=False;daily=[];trades=[];unknown=[];ledger_stopped=False
    for date,rows in sorted(grouped.items()):
        start=equity;committed=0.;positions=[]
        candidates=sorted([r for r in rows if r['probability']>=threshold],
            key=lambda r:(-r['probability'],r['symbol']))[:3] if not permanent else []
        outcomes={r['symbol']:path(market.get(date,{}).get(r['symbol'],{}),r['signal_price'],cost_bps,delay,horizon)
            for r in candidates}
        missing=[s for s,o in outcomes.items() if o is None]
        if missing:
            unknown.append(dict(date=date,symbols=missing,status='selected_unknown_outcome',
                selection_scope='model_rank_before_fill_and_risk_sizing'))
            ledger_stopped=True
        if ledger_stopped: continue
        for row in candidates:
            outcome=outcomes[row['symbol']]
            if not outcome['filled']: continue
            risk=outcome['entry']-outcome['stop']*(1-outcome['cost'])
            qty=math.floor(min(start*.01/outcome['limit'],start*.0005/risk,
                max(0,start*.05-committed)/outcome['limit']))
            if qty<=0: continue
            committed+=qty*outcome['limit'];positions.append(dict(row,outcome=outcome,qty=qty))
        held=list(positions);realized=0.;worst=0.;guard=False
        def close(position,price,reason,minute):
            o=position['outcome']
            trade=trade_record(date,position['symbol'],position['qty'],o['entry'],price,o['cost'],reason)
            trade.update(stop_fraction=.01,planned_stop=o['stop'],reserved_usd=position['qty']*o['limit'],
                entry_minute=o['entry_minute'],exit_minute=minute)
            trades.append(trade);return trade['pnl']
        for k in range(30+delay,31+delay+horizon):
            for position in list(held):
                o=position['outcome']
                if o['exit_minute']==k:
                    realized+=close(position,o['exit'],o['reason'],k);held.remove(position)
            adverse=start+realized+sum(p['qty']*(market[date][p['symbol']][k][2]*(1-p['outcome']['cost'])-p['outcome']['entry']) for p in held)
            worst=min(worst,adverse/start-1)
            if (adverse<=start*.99 or adverse<=peak*.9 or adverse<=90000) and held:
                for p in held:
                    realized+=close(p,float(market[date][p['symbol']][k+1][0])*(1-p['outcome']['cost']),'account_guard',k+1)
                held=[];guard=True
            if adverse<=peak*.9 or adverse<=90000: permanent=True
        if held: raise ValueError('Unclosed modeled position')
        equity=start+realized;peak=max(peak,equity)
        daily.append(dict(date=date,pnl=realized,equity=equity,active=bool(positions),
            committed_usd=committed,worst_marked_pct=worst*100,guard=guard,
            realized_loss_exceeded_daily_trigger=realized<-.01*start,permanent_halt=permanent))
    complete=not ledger_stopped;active=[d for d in daily if d['active']];wins=sum(d['pnl']>0 for d in active)
    interval=wilson(wins,len(active))
    return dict(status='complete_observed_forecast_span_simulation' if complete else 'incomplete_selected_outcome_ledger',
        threshold=threshold,costs_bps=cost_bps,delay=delay,horizon_minutes=horizon,stop_fraction=.01,
        expected_forecast_sessions=len(grouped),known_prefix_sessions=len(daily),sessions=len(daily),
        active_days=len(active),no_trade_days=len(daily)-len(active),unknown_selections=unknown,
        full_period_coverage_complete=complete,profit_usd=equity-INITIAL if complete else None,
        known_prefix_profit_usd=equity-INITIAL,
        active_day_win_rate_pct=wins/len(active)*100 if active and complete else None,
        known_prefix_active_day_win_rate_pct=wins/len(active)*100 if active else None,
        win_rate_interval=interval if complete else None,
        target_screen_pass=bool(complete and len(active)>=100 and interval[0]>=90 and equity>INITIAL),
        independent_validation_pass=False,production_approved=False,orders=False,daily=daily,trades=trades,
        limitations=['Same observed opening universe; independent exchange calendar audit required',
            'Unknown selected outcome stops cumulative ledger; no loss-unknown dates skipped',
            'Two-hour exposure is longer, not a claim of identical realized risk',
            'OHLC fills, costs and next-minute guards modeled, not actual execution'])
