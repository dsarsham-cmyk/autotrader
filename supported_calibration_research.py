"""Fixed five-bin past-only smoothed isotonic calibration; NO ORDERS."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import warnings
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits
from balanced_target_simulator import path,portfolio
from calendar_regular_context import calendar_lookup,calendar_opening_rows,clip_sessions
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from finbert_comparison_audit import check
from forecast_reliability_audit import summarize
from predictive_portfolio_research import partition
from predictive_research import raw_score
from prospective_series_audit import accounting_metrics
from research_calendar_audit import inspect as calendar_audit
from split_context_audit import events_from_pages
from split_predictive_research import flatten


def smoothed_calibrator(scores,labels,dates):
    scores=np.asarray(scores,dtype=float).reshape(-1)
    labels=np.asarray(labels)
    if len(scores)!=len(labels) or len(scores)!=len(dates) or not len(scores):
        raise ValueError('Aligned nonempty past calibration required')
    if not np.isfinite(scores).all() or not np.isin(labels,[0,1]).all():
        raise ValueError('Finite scores and binary labels required')
    edges=np.unique(np.quantile(scores,[.2,.4,.6,.8]))
    assigned=np.searchsorted(edges,scores,side='right')
    bins=[]
    for bucket in sorted(set(assigned)):
        selected=assigned==bucket
        n=int(selected.sum());wins=int(labels[selected].sum())
        bins.append(dict(center=float(scores[selected].mean()),count=n,wins=wins,
            distinct_days=len({d for d,chosen in zip(dates,selected) if chosen}),
            smoothed_probability=(wins+1)/(n+2)))
    model=IsotonicRegression(increasing=True,out_of_bounds='clip',y_min=0,y_max=1)
    model.fit([b['center'] for b in bins],[b['smoothed_probability'] for b in bins],
              sample_weight=[b['count']+2 for b in bins])
    return model,bins


def fold_predict(train,cal,test,model,labels):
    if not train or not cal or not test or max(r['date'] for r in train)>=min(r['date'] for r in cal) or max(r['date'] for r in cal)>=min(r['date'] for r in test):
        raise ValueError('Strict past train/calibration split required')
    if model not in ('logistic','boosted'): raise ValueError('Unknown model')
    classifier=(LogisticRegression(C=.1,max_iter=1000,random_state=19) if model=='logistic'
        else HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=30,
                                             l2_regularization=10,random_state=19,early_stopping=False))
    fitted=make_pipeline(StandardScaler(),classifier)
    fitted.fit(np.asarray([r['features'] for r in train]),[labels[(r['date'],r['symbol'])] for r in train])
    scores=raw_score(fitted,np.asarray([r['features'] for r in cal]))
    cy=[labels[(r['date'],r['symbol'])] for r in cal]
    control=LogisticRegression(C=1,max_iter=1000,random_state=19).fit(scores,cy)
    supported,bins=smoothed_calibrator(scores,cy,[r['date'] for r in cal])
    future=raw_score(fitted,np.asarray([r['features'] for r in test]))
    return control.predict_proba(future)[:,1],supported.predict(future.reshape(-1)),bins


def walk(rows,market,model,target,reference):
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(market.get(r['date'],{}).get(r['symbol'],{}),
                r['signal_price'],target_fraction=target) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items() if o is not None and o['filled']}
    expected={(r['date'],r['symbol']):r for r in reference['forecasts']}
    forecasts=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,test=[partition(rows,d) for d in parts]
        train=[r for r in train if (r['date'],r['symbol']) in labels]
        cal=[r for r in cal if (r['date'],r['symbol']) in labels]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            control,probabilities,bins=fold_predict(train,cal,test,model,labels)
        if caught: raise ValueError('Unresolved fitting warning')
        for r,p in zip(test,control):
            old=expected[(r['date'],r['symbol'])]
            if r['features']!=old['features'] or r['signal_price']!=old['signal_price'] or abs(p-old['probability'])>1e-12:
                raise ValueError('Original model/input reproduction failed')
        forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
        folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],past_calibration_bins=bins))
    if {(r['date'],r['symbol']) for r in forecasts}!=set(expected): raise ValueError('Candidate span changed')
    known=[dict(date=r['date'],symbol=r['symbol'],probability=r['probability'],label=labels[(r['date'],r['symbol'])])
           for r in forecasts if (r['date'],r['symbol']) in labels]
    return forecasts,folds,summarize(known)


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()


def run(data,reference,output):
    original=json.loads(reference.read_bytes())
    if original['status']!='completed_exposed_calendar_predictive_comparison': raise ValueError('Completed reference required')
    for name,expected in original['source_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected: raise ValueError('Reference source changed')
    audit=Path('research_runs/calendar_regular_context/results.json')
    if sha(audit)!=original['input_audit_sha256']: raise ValueError('Input audit changed')
    input_report=json.loads(audit.read_bytes())
    receipt=audit.parent/'calendar_receipt.json'
    split=Path('research_runs/split_context_audit/corporate_actions_receipt.json')
    if sha(receipt)!=input_report['calendar_receipt_sha256'] or sha(split)!=input_report['split_receipt_sha256']:
        raise ValueError('Input receipt changed')
    output.mkdir(parents=True,exist_ok=True)
    protocol=dict(calibration='five_past_quantile_bins_beta_1_1_weighted_isotonic',bins=5,
        prior_successes=1,prior_failures=1,out_of_bounds='clip',models=['logistic','boosted'],
        targets=[.004,.01],warmup=240,calibration_days=60,test_days=20,
        risk_and_execution=original['protocol'],reference_sha256=sha(reference),
        created_utc=datetime.now(timezone.utc).isoformat(),orders=False)
    with (output/'protocol.json').open('x',encoding='utf-8') as handle:
        json.dump(protocol,handle,indent=2,allow_nan=False)
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Historical inputs changed')
    cal=calendar_lookup(json.loads(receipt.read_bytes())['rows'])
    events=events_from_pages(json.loads(split.read_bytes())['pages'],list(observations))
    rows=flatten(calendar_opening_rows(observations,events,cal)[0]);market=market_maps(clip_sessions(observations,cal))
    report=dict(status='running_exposed_supported_calibration_comparison',cases=[],protocol=protocol,
        protocol_sha256=sha(output/'protocol.json'),evidence=evidence,reference_sha256=sha(reference),
        source_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['supported_calibration_research.py','forecast_reliability_audit.py',
                      'balanced_target_simulator.py','predictive_portfolio_research.py']},
        orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed historical research, not independent validation',
            'Stock/day dependence and retrospective original-delivery limits remain',
            'Quantile bins, smoothing and weighted monotonic fit fixed before study run',
            'Past bin support is descriptive, not a certified confidence bound',
            'Known-fill calibration excludes unknown paths without imputation; portfolio missing paths halt ledger'])
    with threadpool_limits(limits=1):
        for old in original['cases']:
            forecasts,folds,reliability=walk(rows,market,old['model'],old['target_fraction'],old)
            case=dict(model=old['model'],target_fraction=old['target_fraction'],folds=folds,
                      forecasts=forecasts,reliability_known_filled=reliability,
                      original_control_reproduced=True,outcomes=[])
            for gate in (.5,.65,.9):
                for cost,delay in ((10,16),(20,16),(10,17)):
                    o=portfolio(forecasts,market,gate,cost,delay,old['target_fraction'])
                    o['known_prefix_metrics']=accounting_metrics(dict(o,profit_usd=o['known_prefix_profit_usd']),forecasts)
                    if not check(o): raise ValueError('Risk/budget invariant failed')
                    case['outcomes'].append(o)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(model=old['model'],target=old['target_fraction'],gate=gate,
                            active_days=o['active_days'],win_rate=o['active_day_win_rate_pct'],net=o['profit_usd'],
                            complete=o['full_period_coverage_complete'])),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_supported_calibration_comparison'
    report['calendar_coverage']=calendar_audit(report,{r['date']:r for r in json.loads(receipt.read_bytes())['rows']})
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/calendar_predictive/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/supported_calibration'))
    a=p.parse_args();run(a.data,a.reference,a.output)
