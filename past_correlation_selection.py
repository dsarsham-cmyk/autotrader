"""Greedy probability rank with only prior-session pair correlations."""
from bisect import bisect_left
import hashlib
import json
import math
import numpy as np

PROTOCOL=dict(lookback_observed_sessions=60,minimum_joint_sessions=40,
    maximum_positive_correlation=.5,max_positions=3,missing_pair='reject_additional_candidate',
    history_return='observed_regular_open_to_last_15_55_or_later_close',orders=False)


def return_history(observations):
    result={}
    for symbol,days in observations.items():
        result[symbol]={}
        for date,bars in days.items():
            first=bars.loc[bars.minute==570];last=bars.loc[bars.minute>=955]
            if len(first)!=1 or last.empty: continue
            value=float(last.close.iloc[-1]/first.open.iloc[0]-1)
            if not math.isfinite(value): raise ValueError('Invalid historical return')
            result[symbol][date]=value
    return result


def pair_history(history,first,second,date):
    dates=sorted(set(history[first])|set(history[second]))
    end=bisect_left(dates,date);window=dates[max(0,end-60):end]
    joint=[d for d in window if d in history[first] and d in history[second]]
    pairs=[[history[first][d],history[second][d]] for d in joint]
    digest=hashlib.sha256(json.dumps(list(zip(joint,pairs)),separators=(',',':')).encode()).hexdigest()
    correlation=None
    if len(joint)>=40:
        array=np.asarray(pairs,dtype=float)
        if not np.isfinite(array).all(): raise ValueError('Nonfinite pair history')
        if np.std(array[:,0])>0 and np.std(array[:,1])>0:
            correlation=float(np.corrcoef(array.T)[0,1])
            if not math.isfinite(correlation): raise ValueError('Invalid correlation')
    return dict(first=first,second=second,correlation=correlation,joint_sessions=len(joint),
        latest_history_date=joint[-1] if joint else None,history_sha256=digest)


def select(rows,history,threshold,diversify):
    if not math.isfinite(threshold) or not 0<threshold<=1: raise ValueError('Invalid selection threshold')
    grouped={};seen=set()
    for r in rows:
        key=(r['date'],r['symbol'])
        if key in seen: raise ValueError('Duplicate candidate')
        seen.add(key)
        if not math.isfinite(r['probability']) or not 0<=r['probability']<=1: raise ValueError('Invalid probability')
        grouped.setdefault(r['date'],[]).append(r)
    selected=[];evidence=[]
    for date,candidates in sorted(grouped.items()):
        ranked=sorted([r for r in candidates if r['probability']>=threshold],key=lambda r:(-r['probability'],r['symbol']))
        chosen=[];checks=[]
        for r in ranked:
            if len(chosen)==3: break
            pairs=[pair_history(history,r['symbol'],old['symbol'],date) for old in chosen] if diversify else []
            approved=all(p['correlation'] is not None and p['correlation']<=.5 for p in pairs)
            checks.append(dict(symbol=r['symbol'],accepted=approved,pairs=pairs))
            if approved: chosen.append(r)
        # Keep below-gate candidates with genuine unchanged probabilities so
        # no-eligible dates remain present; portfolio cannot turn them into fills.
        selected.extend(chosen+[r for r in candidates if r['probability']<threshold])
        evidence.append(dict(date=date,chosen=[r['symbol'] for r in chosen],checks=checks))
    return selected,evidence
