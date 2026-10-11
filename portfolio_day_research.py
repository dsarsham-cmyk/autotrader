"""Past-only portfolio-day classifier on an unfiltered reference policy.

Permission scores are not stock probabilities. No orders or model promotion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import warnings
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from balanced_target_simulator import portfolio
from calendar_regular_context import calendar_lookup,clip_sessions
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from finbert_comparison_audit import check
from predictive_research import raw_score
from prospective_series_audit import accounting_metrics
from research_calendar_audit import inspect as calendar_audit


def day_features(forecasts):
    groups={};seen=set()
    for f in forecasts:
        key=(f['date'],f['symbol'])
        if key in seen: raise ValueError('Duplicate forecast')
        seen.add(key);groups.setdefault(f['date'],[]).append(f)
    features={}
    for date,rows in sorted(groups.items()):
        values=np.asarray([r['features'] for r in rows],dtype=float)
        p=np.asarray([r['probability'] for r in rows],dtype=float)
        if values.shape!=(len(rows),16) or not np.isfinite(values).all() or not np.isfinite(p).all() or (p<0).any() or (p>1).any():
            raise ValueError('Valid 16 causal features and probabilities required')
        chosen=sorted([r for r in rows if r['probability']>=.65],key=lambda r:(-r['probability'],r['symbol']))[:3]
        selected=np.mean([r['features'] for r in chosen],axis=0).tolist() if chosen else [0.]*16
        scores=[r['probability'] for r in chosen]
        features[date]=values.mean(axis=0).tolist()+selected+[
            max(scores) if scores else 0.,float(np.mean(scores)) if scores else 0.,
            float(np.std(scores)) if scores else 0.,len(rows)/20,len(chosen)/3]
    return features


def fit_day(train,cal,future,features,labels):
    if max(train)>=min(cal) or max(cal)>=min(future): raise ValueError('Strict past-only daily split required')
    fitted=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=1000,random_state=19))
    fitted.fit([features[d] for d in train],[labels[d] for d in train])
    calibrator=LogisticRegression(C=1,max_iter=1000,random_state=19)
    calibrator.fit(raw_score(fitted,np.asarray([features[d] for d in cal])),[labels[d] for d in cal])
    return calibrator.predict_proba(raw_score(fitted,np.asarray([features[d] for d in future])))[:,1]


def schedule(forecasts,daily):
    features=day_features(forecasts);dates=sorted(features)
    if [d['date'] for d in daily]!=dates: raise ValueError('Complete reference daily ledger required')
    if any(type(d['active']) is not bool or not np.isfinite(d['pnl']) or (not d['active'] and d['pnl']!=0) for d in daily):
        raise ValueError('Invalid reference daily accounting')
    labels={d['date']:int(d['pnl']>0) for d in daily if d['active']}
    decisions={d:dict(date=d,day_probability=None,reason='warmup90',train_last=None,cal_last=None) for d in dates}
    folds=[]
    for start in range(90,len(dates),20):
        train=[d for d in dates[:start-30] if d in labels]
        cal=[d for d in dates[start-30:start] if d in labels]
        future=dates[start:start+20]
        reason='eligible'
        if len(train)<30 or len(cal)<10: reason='insufficient_past_active_support'
        elif len({labels[d] for d in train})<2 or len({labels[d] for d in cal})<2: reason='past_one_class'
        probabilities=[None]*len(future)
        if reason=='eligible':
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                probabilities=fit_day(train,cal,future,features,labels)
            if caught: raise ValueError('Unresolved fitting warning')
        fold=dict(train_last=train[-1] if train else None,cal_first=cal[0] if cal else None,
            cal_last=cal[-1] if cal else None,test_first=future[0],test_last=future[-1],
            train_active_days=len(train),cal_active_days=len(cal),reason=reason)
        folds.append(fold)
        for date,p in zip(future,probabilities):
            if p is not None and (not np.isfinite(p) or not 0<=p<=1): raise ValueError('Invalid day probability')
            decisions[date]=dict(date=date,day_probability=float(p) if p is not None else None,
                reason=reason,train_last=fold['train_last'],cal_last=fold['cal_last'])
    return [decisions[d] for d in dates],folds


def apply_permission(forecasts,decisions,gate):
    if gate not in (.65,.9): raise ValueError('Fixed day gates only')
    permissions={d['date']:d['day_probability'] is not None and d['day_probability']>=gate for d in decisions}
    if len(permissions)!=len(decisions) or set(permissions)!={f['date'] for f in forecasts}:
        raise ValueError('Complete unique daily schedule required')
    return [dict(f,forecast_probability=f['probability'],day_trading_permitted=permissions[f['date']],
        probability=f['probability'] if permissions[f['date']] else 0.,
        zero_score_is_permission_not_probability=True) for f in forecasts]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run(data,reference,output):
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_calendar_predictive_comparison': raise ValueError('Completed reference required')
    for n,h in original['source_sha256'].items():
        if hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=h: raise ValueError('Reference source changed')
    audit=Path('research_runs/calendar_regular_context/results.json')
    if sha(audit)!=original['input_audit_sha256']: raise ValueError('Input audit changed')
    receipt=audit.parent/'calendar_receipt.json'
    if sha(receipt)!=json.loads(audit.read_bytes())['calendar_receipt_sha256']: raise ValueError('Calendar changed')
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_portfolio_day_comparison',cases=[],reference_sha256=sha(reference),
        protocol=dict(stock_gate=.65,day_gates=[.65,.9],warmup_dates=90,refit_block_dates=20,
            calibration_dates=30,minimum_train_active=30,minimum_cal_active=10,day_model='logistic_C01',
            day_features='universe_mean16_selected_top3_mean16_score_max_mean_std_universe_count_selected_count',
            label='net_positive_unfiltered_reference_day_conditional_on_activity',
            label_training_cost_bps=10,label_training_delay=16,unchanged_risk=original['protocol']),
        source_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['portfolio_day_research.py','balanced_target_simulator.py','predictive_research.py']},
        orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed nested historical analysis, not independent prospective validation',
            'Reference label is counterfactual unfiltered policy, not filtered realized history',
            'Past reference outcomes only; current equity/P&L/outcomes never enter day features',
            'One shared baseline10bps/delay16 schedule reused for stress, not stress-outcome tuning',
            'Zero permission score is NOT a forecast probability; original stock probability retained',
            'Warmup/insufficient-support/no-trade days never count as wins'])
    with threadpool_limits(limits=1):
        prepared=[]
        for old in original['cases']:
            baseline=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(.65,10,16))
            if not baseline['full_period_coverage_complete'] or not check(baseline): raise ValueError('Complete valid reference required')
            decisions,folds=schedule(old['forecasts'],baseline['daily'])
            prepared.append((old,decisions,folds))
        observations,evidence=load_observations(data)
        if evidence!=original['evidence']: raise ValueError('Historical inputs changed')
        report['evidence']=evidence
        market=market_maps(clip_sessions(observations,calendar_lookup(json.loads(receipt.read_bytes())['rows'])))
        for old,decisions,folds in prepared:
            for gate in (.65,.9):
                selected=apply_permission(old['forecasts'],decisions,gate)
                case=dict(model=old['model'],target_fraction=old['target_fraction'],day_gate=gate,
                    folds=old['folds'],day_model_folds=folds,day_schedule=decisions,forecasts=selected,outcomes=[])
                for cost,delay in ((10,16),(20,16),(10,17)):
                    o=portfolio(selected,market,.65,cost,delay,old['target_fraction'])
                    o.update(day_gate=gate,known_prefix_metrics=accounting_metrics(
                        dict(o,profit_usd=o['known_prefix_profit_usd']),selected))
                    if not check(o): raise ValueError('Risk/budget invariant failed')
                    case['outcomes'].append(o)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(model=old['model'],target=old['target_fraction'],day_gate=gate,
                            active=o['active_days'],win_rate=o['active_day_win_rate_pct'],net=o['profit_usd'],
                            complete=o['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_portfolio_day_comparison'
    report['calendar_coverage']=calendar_audit(report,{r['date']:r for r in json.loads(receipt.read_bytes())['rows']})
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/calendar_predictive/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/portfolio_day'))
    a=p.parse_args();run(a.data,a.reference,a.output)
