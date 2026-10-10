"""Retrospective sanity check of an own frozen model, not forward evidence.

The artifact was created after these historical observations. Predictions may
use past-only features but cannot be relabeled as externally anchored forecasts.
No retraining, threshold search, broker access or model promotion.
"""
import argparse
import json
from pathlib import Path

import joblib
import sklearn

from active_stock_research import load_universe,SYMBOLS
from prospective_forecast_evidence import read_manifest,file_digest,source_matches
from prospective_model_collector import current_context
from regime_predictive_research import predict_forecasters,EXTRA_FEATURES
from predictive_portfolio_research import portfolio,FEATURES
from prospective_series_audit import accounting_metrics,probability_diagnostic,VARIANTS
from fixed_trade_cost_diagnostic import diagnostic


def retrospective_predictions(by_date,artifact,first,last):
    if first>last or first<=artifact['trained_through']:
        raise ValueError('Sanity-check dates must follow training, in order')
    rows=[];excluded=[]
    dates=[date for date in sorted(by_date) if first<=date<=last]
    for date in dates:
        current=by_date[date]
        if set(current)!=set(SYMBOLS):
            excluded.append(dict(date=date,reason='Incomplete fixed universe',
                missing_symbols=sorted(set(SYMBOLS)-set(current))))
            continue
        prior={d:stocks for d,stocks in by_date.items() if d<date}
        opening={symbol:current[symbol][0][:30].copy() for symbol in SYMBOLS}
        context=current_context(prior,opening,date)
        prediction=predict_forecasters(artifact['fitted'],context)
        rows.extend(dict(row,**{key:float(values[i]) for key,values in prediction.items()})
            for i,row in enumerate(context))
    return rows,excluded


def run(data,model_dir,first,last,output):
    envelope=read_manifest(model_dir);manifest=envelope['manifest']
    if not source_matches(manifest): raise ValueError('Frozen predictive sources changed')
    path=model_dir/'model.joblib'
    if file_digest(path)!=manifest['artifact_sha256']: raise ValueError('Changed artifact; refuse loading')
    artifact=joblib.load(path)
    if artifact['sklearn_version']!=sklearn.__version__ or artifact['features']!=FEATURES+EXTRA_FEATURES:
        raise ValueError('Frozen runtime/schema mismatch')
    if artifact.get('broker_orders_enabled') is not False or artifact.get('production_approved') is not False:
        raise ValueError('Only own unapproved research artifact allowed')
    by_date,evidence=load_universe(data)
    rows,excluded=retrospective_predictions(by_date,artifact,first,last)
    outcomes=[]
    for cost,delay in VARIANTS:
        result=portfolio(rows,by_date,30,'target_60',.65,cost,delay)
        result.update(metrics=accounting_metrics(result,rows),cost_diagnostic=diagnostic(result))
        outcomes.append(result)
    report=dict(status='retrospective_exploration_only',first=first,last=last,
        manifest_sha256=envelope['manifest_sha256'],source_sha256=file_digest(Path(__file__)),
        data_evidence=evidence,exclusions=excluded,predictions=rows,outcomes=outcomes,
        probability_diagnostic=probability_diagnostic(rows,by_date),
        externally_anchored_forecasts=0,independent_validation_pass=False,
        production_approved=False,orders=False,
        limitations=['Model created after these observations; all dates exploratory',
            'Past-only features do not make a retrospective packet a future forecast',
            'Dates/universe/data were already exposed; exclusions and selection bias remain',
            'OHLC simulated fills and costs are assumptions, not broker execution',
            'Five sessions cannot demonstrate 90% profitable active days or reliable daily income'])
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    for outcome in outcomes:
        print(json.dumps(dict(status=report['status'],cost_bps=outcome['costs_bps'],delay=outcome['delay'],
            sessions=outcome['sessions'],active_days=outcome['active_days'],net_usd=outcome['profit_usd'],
            win_rate=outcome['active_day_win_rate_pct'],exclusions=excluded,
            independent_validation_pass=False,orders=False)),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/prospective_history_v1'))
    parser.add_argument('--model-dir',type=Path,default=Path('research_prospective/control_v2'))
    parser.add_argument('--first',default='2026-10-05');parser.add_argument('--last',default='2026-10-09')
    parser.add_argument('--output',type=Path,default=Path('research_runs/frozen_control_retrospective/results.json'))
    args=parser.parse_args();run(args.data,args.model_dir,args.first,args.last,args.output)
