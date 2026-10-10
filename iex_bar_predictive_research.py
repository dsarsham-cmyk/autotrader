"""Separately trained IEX-only features, with SIP used solely for outcomes.

IEX is a single venue, not SIP. Freshness/receipt at 10:00 remains an assumption
until live input receipts and forecasts are anchored before 10:01 entry.
Historical bar revisions are not authenticated original delivery.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
import os
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits
from active_stock_research import load_universe,SYMBOLS,hash_file,download_edges
from macro_context_research import proxy_sessions,context,FIELDS
from predictive_portfolio_research import partition,fit_predict
from neural_convergence_research import fit_probability as fit_neural
from quantum_kernel_research import predict as fit_quantum
from tighter_stop_simulator import path,portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic

FEATURES=FIELDS+['prior_return','last_five_observed_return','last_five_volume_share',
    'prior_terminal_age_fraction','iex_cross_section_mean_return','iex_positive_breadth']
PROTOCOL=dict(input_feed='iex',outcome_feed='sip',adjustment='raw',symbols=list(SYMBOLS),
    cutoff_minute=30,minimum_opening_bars=24,required_terminal_bar_start='09:59 NY',
    prior_terminal_bar_minute_at_least=955,entry_delays=[1,16],warmup_dates=240,
    calibration_dates=60,test_block_dates=20,models=['logistic','boosted','mlp','quantum_fidelity'],
    thresholds=[.5,.65,.9],cost_bps=10,stop_fraction=.01,target_fraction=.004,horizon_minutes=60,
    live_receipt_verified=False,feed_substitution_into_frozen_model=False,
    orders=False,production_approved=False,independent_validation_pass=False)


def fetch_one(symbol,directory):
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import DataFeed,Adjustment
    target=directory/f'{symbol}.csv'
    if target.exists() or target.with_suffix('.metadata.json').exists():
        raise ValueError('Existing IEX cache not overwritten')
    client=StockHistoricalDataClient(os.environ['ALPACA_API_KEY'],os.environ['ALPACA_API_SECRET'])
    edges=download_edges('2024-01-01','2026-10-02');frames=[]
    for left,right in zip(edges,edges[1:]):
        request=StockBarsRequest(symbol_or_symbols=[symbol],timeframe=TimeFrame.Minute,
            start=left.to_pydatetime(),end=right.to_pydatetime(),feed=DataFeed.IEX,adjustment=Adjustment.RAW)
        try: frame=client.get_stock_bars(request).df.reset_index()
        except Exception as error:
            raise RuntimeError(f'IEX historical GET failed for {symbol}: {type(error).__name__}; no fallback') from None
        if not frame.empty: frames.append(frame)
    if not frames: raise ValueError('No IEX bars; no result claimed')
    joined=pd.concat(frames,ignore_index=True).drop_duplicates()
    if joined.duplicated(['symbol','timestamp']).any(): raise ValueError('Contradictory overlapping IEX bars')
    if set(joined.symbol)!={symbol}: raise ValueError('Wrong returned IEX symbol')
    joined=joined.sort_values('timestamp');joined.to_csv(target,index=False)
    target.with_suffix('.metadata.json').write_text(json.dumps(dict(symbol=symbol,feed='iex',adjustment='raw',
        start='2024-01-01',requested_end='2026-10-02',actual_end=edges[-1].isoformat(),
        retrieved_utc=datetime.now(timezone.utc).isoformat(),rows=len(joined),sha256=hash_file(target)),indent=2))
    print(json.dumps(dict(downloaded_iex_symbol=symbol,rows=len(joined))),flush=True)


def download(directory):
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent/'.env');directory.mkdir(parents=True,exist_ok=True)
    if any((directory/f'{s}.csv').exists() or (directory/f'{s}.metadata.json').exists() for s in SYMBOLS):
        raise ValueError('IEX download requires fresh directory; no overwrites')
    with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(lambda s:fetch_one(s,directory),SYMBOLS))


def load_iex(directory):
    observations={};provenance={}
    for symbol in SYMBOLS:
        filename=directory/f'{symbol}.csv';meta=json.loads(filename.with_suffix('.metadata.json').read_text())
        actual=hash_file(filename)
        if meta.get('feed')!='iex' or meta.get('adjustment')!='raw' or meta.get('sha256')!=actual:
            raise ValueError('Own IEX/raw cache required; no SIP substitution')
        frame=pd.read_csv(filename);observations[symbol]=proxy_sessions(frame,symbol)
        provenance[symbol]=dict(metadata=meta,source_sha256=actual,regular_dates=len(observations[symbol]))
    return observations,provenance


def own_contexts(observations):
    rows={};reasons={}
    for symbol,days in sorted(observations.items()):
        prior=[]
        for date,regular in sorted(days.items()):
            opening=regular.loc[regular.minute<600]
            values=None;reason='sparse_or_stale_iex_opening'
            if len(opening)>=24 and int(opening.minute.iloc[-1])==599:
                values,reason=context(opening,prior)
                if values is not None:
                    late=opening.loc[opening.minute>=595]
                    values=values+[prior[-1]['close']/prior[-2]['close']-1,
                        float(late.close.iloc[-1]/late.open.iloc[0]-1),
                        float(late.volume.sum()/opening.volume.sum()),(959-prior[-1]['minute'])/5]
                    rows.setdefault(date,{})[symbol]=dict(features=values,signal_price=float(opening.close.iloc[-1]))
            reasons[(date,symbol)]=reason
            # Today's later bars never qualify its current opening information.
            closing=regular.loc[regular.minute>=955]
            if not closing.empty:
                last=closing.iloc[-1]
                prior.append(dict(close=float(last.close),minute=int(last.minute),volume=float(opening.volume.sum())))
    # Market context uses IEX opening information independently of later SIP
    # outcome completeness; the latter is joined only after feature extraction.
    for date,stocks in rows.items():
        returns=np.asarray([r['features'][0] for r in stocks.values()])
        for row in stocks.values(): row['features']+= [float(returns.mean()),float(np.mean(returns>0))]
    return rows,reasons


def matched_rows(by_date,observations):
    context_rows,reasons=own_contexts(observations);result=[];eligibility={}
    dates=sorted(by_date)
    for date in dates[21:]:
        for symbol in sorted(by_date[date]):
            row=context_rows.get(date,{}).get(symbol)
            reason='eligible' if row is not None else reasons.get((date,symbol),'missing_iex_session')
            eligibility[reason]=eligibility.get(reason,0)+1
            result.append(dict(date=date,symbol=symbol,features=row['features'] if row else [0.]*len(FEATURES),
                # Ineligible selection score is zero; this placeholder never
                # becomes a selected signal or an IEX-compatible forecast.
                signal_price=row['signal_price'] if row else 100.,predecision_eligible=row is not None,
                eligibility_reason=reason))
    return result,eligibility


def walk(rows,by_date,kind,delay):
    if kind not in PROTOCOL['models'] or delay not in PROTOCOL['entry_delays']: raise ValueError('Unknown fixed protocol')
    dates=sorted({r['date'] for r in rows})
    outcomes={(r['date'],r['symbol']):path(by_date[r['date']][r['symbol']][0],r['signal_price'],.01,10,delay) for r in rows}
    labels={k:o['label'] for k,o in outcomes.items()};predictions=[];folds=[]
    for start in range(240,len(dates),20):
        parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
        train,cal,all_test=[partition(rows,d) for d in parts]
        train=[r for r in train if r['predecision_eligible'] and outcomes[(r['date'],r['symbol'])]['filled']]
        cal=[r for r in cal if r['predecision_eligible'] and outcomes[(r['date'],r['symbol'])]['filled']]
        test=[r for r in all_test if r['predecision_eligible']];fit={};p=np.array([])
        if test:
            if kind=='mlp': p,fit=fit_neural(train,cal,test,labels)
            else:
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter('always')
                    p=(fit_quantum(train,cal,test,labels,kind) if kind=='quantum_fidelity'
                        else fit_predict(train,cal,test,kind,labels))
                fit=dict(warning_types=[type(w.message).__name__ for w in caught])
        forecasts={(r['date'],r['symbol']):float(v) for r,v in zip(test,p)}
        predictions.extend(dict(r,probability=forecasts.get((r['date'],r['symbol']),0),
            probability_is_forecast=r['predecision_eligible']) for r in all_test)
        filled=[i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
        folds.append(dict(train_last=parts[0][-1],calibration_first=parts[1][0],calibration_last=parts[1][-1],
            test_first=parts[2][0],test_last=parts[2][-1],fit=fit,eligible_test_rows=len(test),observed_test_rows=len(all_test),
            filled_test_samples=len(filled),brier_filled=float(np.mean([
                (p[i]-labels[(test[i]['date'],test[i]['symbol'])])**2 for i in filled])) if filled else None))
    return predictions,folds


def run(data,iex,output):
    output.mkdir(parents=True,exist_ok=True);by_date,evidence=load_universe(data)
    observations,iex_evidence=load_iex(iex);rows,eligibility=matched_rows(by_date,observations)
    report=dict(status='running_exposed_historical_iex_bar_research',protocol=PROTOCOL,features=FEATURES,
        evidence=evidence,iex_evidence=iex_evidence,eligibility_counts=eligibility,
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['iex_bar_predictive_research.py','macro_context_research.py','neural_convergence_research.py',
                'predictive_portfolio_research.py','predictive_research.py','quantum_kernel_research.py',
                'tighter_stop_simulator.py','active_stock_research.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Own IEX feature model, not substitution into an existing SIP classifier',
            'SIP future execution prices/labels are outcomes only, not current features',
            'IEX is a sparse single venue; observed opening/closing prices are not consolidated quotes',
            'Historical revisions and delivery/inference/anchoring before 10:01 remain unverified',
            'Known historical outcomes; new input download is not independent validation',
            'Current universe, complete-SIP-session exclusions, raw splits and OHLC/EOD guards remain biased',
            'Quantum model is only a four-qubit CPU simulation'])
    with threadpool_limits(limits=1):
        for delay in PROTOCOL['entry_delays']:
            for kind in PROTOCOL['models']:
                predictions,folds=walk(rows,by_date,kind,delay)
                case=dict(entry_delay=delay,model=kind,folds=folds,outcomes=[])
                for threshold in PROTOCOL['thresholds']:
                    for cost,actual_delay in [(10,delay),(20,delay),(10,delay+1)]:
                        result=portfolio(predictions,by_date,.01,threshold,cost,actual_delay)
                        result.update(metrics=accounting_metrics(result,predictions),cost_diagnostic=diagnostic(result))
                        case['outcomes'].append(result)
                        if cost==10 and actual_delay==delay:
                            print(json.dumps(dict(delay=delay,model=kind,threshold=threshold,
                                active_days=result['active_days'],win_rate=result['active_day_win_rate_pct'],
                                net_usd=result['profit_usd'],screen_pass=result['target_screen_pass'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_historical_iex_bar_research'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--iex',type=Path,default=Path('cache/iex_bar_context'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/iex_bar_predictive'))
    parser.add_argument('--download',action='store_true');args=parser.parse_args()
    if args.download: download(args.iex)
    run(args.data,args.iex,args.output)
