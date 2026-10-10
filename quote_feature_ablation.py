"""Matched bar-only vs bar+NBBO-feature development experiment, never orders.

Same known-prefix coverage eligibility, dates, budgets, costs and 15-minute
information delay for both arms. No artificial instantaneous-SIP edge claim.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from active_stock_research import load_universe
from regime_predictive_research import extended_rows
from predictive_portfolio_research import fit_predict,partition,path_outcome,portfolio
from quote_microstructure_research import quote_features,bounds,SYMBOLS,FEATURES,PROTOCOL
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from quantum_kernel_research import predict as predict_kernel

MODELS=['logistic','boosted','classical_rbf','quantum_fidelity']


def matched_rows(data,collection):
    payload=json.loads((collection/'collection_status.json').read_text())
    plan=payload['plan']
    if plan['protocol']!=PROTOCOL: raise ValueError('Changed quote collection protocol')
    expected={(symbol,date) for symbol in SYMBOLS for date in plan['dates']}
    windows=payload['windows']
    keys=[(window['symbol'],window['date']) for window in windows]
    if len(keys)!=len(set(keys)) or set(keys)!=expected:
        raise ValueError('Collection incomplete or duplicate quote windows')
    by_date,evidence=load_universe(data)
    if evidence['hashes']!=plan['bar_cache_sha256']: raise ValueError('Original bar inputs changed')
    base={(row['date'],row['symbol']):row for row in extended_rows(by_date)}
    rows=[];excluded=[];hashes={}
    for window in windows:
        key=(window['date'],window['symbol'])
        if window['status']=='quote_fetch_failed':
            excluded.append(dict(date=key[0],symbol=key[1],reason='Known quote fetch failure'));continue
        path=collection/'quotes'/f'{key[1]}_{key[0]}.json';content=path.read_bytes()
        actual=hashlib.sha256(content).hexdigest()
        if actual!=window['cache_sha256']: raise ValueError('Retained quote byte hash mismatch')
        raw=json.loads(content);start,end=bounds(key[0])
        identity=dict(symbol=key[1],date=key[0],feed='sip',start=start.isoformat(),cutoff=end.isoformat(),seed_seconds=2)
        if raw.get('identity')!=identity or raw.get('pagination_complete') is not True:
            raise ValueError('Retained quote request identity/completeness mismatch')
        features=quote_features(raw['quotes'],start,end)
        hashes[str(path)]=actual
        if features['status']!='usable':
            excluded.append(dict(date=key[0],symbol=key[1],reason='Insufficient known-prefix quote coverage',
                fresh_coverage_pct=features['fresh_coverage_pct']));continue
        if key not in base: raise ValueError('Missing original bar-only signal')
        rows.append(dict(base[key],quote_features=features['features']))
    return rows,by_date,dict(bar_evidence=evidence,quote_cache_sha256=hashes,
        expected_windows=len(expected),retained_candidates=len(rows),exclusions=excluded,
        planned_dates=plan['dates'])


def walk(rows,by_date,kind,use_quotes):
    dates=sorted({row['date'] for row in rows})
    candidates=[dict(row,features=row['features']+row['quote_features'] if use_quotes else row['features']) for row in rows]
    outcomes={(r['date'],r['symbol']):path_outcome(by_date[r['date']][r['symbol']][0],
        r['signal_price'],30,'target_60',10,16) for r in candidates}
    labels={key:outcome['label'] for key,outcome in outcomes.items()}
    predictions=[];folds=[]
    for start in range(100,len(dates),20):
        parts=[dates[:start-30],dates[start-30:start],dates[start:start+20]]
        train,cal,test=[partition(candidates,part) for part in parts]
        train=[row for row in train if outcomes[(row['date'],row['symbol'])]['filled']]
        cal=[row for row in cal if outcomes[(row['date'],row['symbol'])]['filled']]
        if len({labels[(r['date'],r['symbol'])] for r in train})<2 or len({labels[(r['date'],r['symbol'])] for r in cal})<2:
            raise ValueError('Insufficient past classes; no synthetic confident forecast')
        p=(predict_kernel(train,cal,test,labels,kind) if kind in ['classical_rbf','quantum_fidelity']
            else fit_predict(train,cal,test,kind,labels))
        predictions.extend(dict(row,probability=float(value)) for row,value in zip(test,p))
        matched=[i for i,row in enumerate(test) if outcomes[(row['date'],row['symbol'])]['filled']]
        folds.append(dict(train_last=parts[0][-1],calibration_first=parts[1][0],calibration_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],filled_train_rows=len(train),filled_calibration_rows=len(cal),
            filled_test_candidates=len(matched),
            brier_filled=float(np.mean([(p[i]-labels[(test[i]['date'],test[i]['symbol'])])**2 for i in matched])) if matched else None))
    return predictions,folds


def run(data,collection,output):
    output.mkdir(parents=True,exist_ok=True)
    rows,by_date,evidence=matched_rows(data,collection)
    report=dict(status='exposed_historical_exploration_only',evidence=evidence,
        protocol=dict(symbols=SYMBOLS,feature_cutoff='10:00 New York',quote_seconds=10,
            information_delay_minutes=15,execution_latency_minutes=1,
            warmup_dates=100,calibration_dates=30,test_block_dates=20,
            models=MODELS,thresholds=[.5,.65,.9],horizon='target_60',
            quantum_hardware='CPU statevector simulation only',qubits=4,quantum_layers=2,
            kernel_training_cap=600,kernel_calibration_cap=600,
            stock_cap_fraction=.01,category_cap_fraction=.05,max_positions=3,
            stop_fraction=.01,target_fraction=.004,per_side_cost_bps=10,
            no_cost_reduction=True,orders=False),quote_feature_names=FEATURES,
        source_sha256={name:hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for name in ['quote_feature_ablation.py','quote_microstructure_research.py','quote_cost_audit.py',
                'predictive_portfolio_research.py','regime_predictive_research.py','active_stock_research.py',
                'quantum_kernel_research.py']},
        cases=[],independent_validation_pass=False,production_approved=False,orders=False,
        limitations=['Evenly sampled already-exposed dates/current universe are not independent or all-calendar evidence',
            'Ten-second NBBO sample is displayed best quotes, not full depth or executed trade flow',
            'Quote-condition execution eligibility is not modeled; no cost reduction is inferred',
            'Historical quote corrections/publication receipt times cannot be authenticated as original forecasts',
            'Complete-session bar exclusions still create selection bias',
            'One-tick published effects may decay before 15-minute delayed signal execution',
            'Small simulated quantum kernel does not imply hardware/computational advantage or market physics',
            'Minute OHLC fills/stops/guard are simulated, not whole-account broker execution'])
    for kind in MODELS:
        for use_quotes in [False,True]:
            predictions,folds=walk(rows,by_date,kind,use_quotes)
            case=dict(model=kind,feature_set='bars_plus_nbbo' if use_quotes else 'matched_bars_only',folds=folds,outcomes=[])
            for threshold in [.5,.65,.9]:
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(predictions,by_date,30,'target_60',threshold,cost,delay)
                    result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                    case['outcomes'].append(result)
                    print(json.dumps(dict(model=kind,features=case['feature_set'],threshold=threshold,
                        cost_bps=cost,delay=delay,active_days=result['active_days'],net_usd=result['profit_usd'],
                        win_rate=result['active_day_win_rate_pct'],screen_pass=result['target_screen_pass'])),flush=True)
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--collection',type=Path,default=Path('research_runs/quote_microstructure'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/quote_ablation'))
    args=parser.parse_args();run(args.data,args.collection,args.output)
