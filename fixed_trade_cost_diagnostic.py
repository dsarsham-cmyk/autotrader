"""Accounting sensitivity on FIXED trades, not executable strategy replays."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def trade_record(date,symbol,quantity,entry,exit_price,cost,reason):
    if not 0<=cost<1 or quantity<=0:
        raise ValueError('Invalid trade accounting input')
    raw_entry=entry/(1+cost)
    raw_exit=exit_price/(1-cost)
    net=quantity*(exit_price-entry)
    gross=quantity*(raw_exit-raw_entry)
    return dict(date=date,symbol=symbol,quantity=quantity,entry=entry,exit=exit_price,
        raw_entry=raw_entry,raw_exit=raw_exit,pnl=net,gross_pnl=gross,
        cost_drag=gross-net,per_side_cost_bps=cost*10000,reason=reason)


def diagnostic(outcome):
    trades=outcome['trades']
    dates={d['date'] for d in outcome['daily'] if d['active']}
    for trade in trades:
        if trade['date'] not in dates:
            raise ValueError('Trade on a supposedly inactive date')
        required=('quantity','raw_entry','raw_exit','pnl','gross_pnl','cost_drag')
        if not all(k in trade and math.isfinite(trade[k]) for k in required):
            raise ValueError('Missing or invalid accounting evidence; rerun research')
        if not math.isclose(trade['gross_pnl']-trade['cost_drag'],trade['pnl'],abs_tol=1e-7):
            raise ValueError('Trade gross/net mismatch')
    if not math.isclose(sum(t['pnl'] for t in trades),outcome['profit_usd'],abs_tol=1e-6):
        raise ValueError('Trade/account result mismatch')
    variants=[]
    for bps in [0,1,2,5,10,20]:
        cost=bps/10000
        by_date={date:0. for date in dates}
        for t in trades:
            by_date[t['date']]+=t['quantity']*(t['raw_exit']*(1-cost)-t['raw_entry']*(1+cost))
        variants.append(dict(per_side_cost_bps=bps,active_days=len(dates),
            profit_usd=sum(by_date.values()),
            active_day_win_rate_pct=sum(value>0 for value in by_date.values())/len(dates)*100 if dates else None))
    return dict(status='fixed_trade_accounting_only',independent_validation_pass=False,
        gross_pnl=sum(t['gross_pnl'] for t in trades),net_pnl=sum(t['pnl'] for t in trades),
        assumed_cost_drag=sum(t['cost_drag'] for t in trades),variants=variants,
        limitations=['Same fills, quantity, entry/exit prices, stops and guard actions are frozen',
            'Lower costs may alter live fills, sizing, calibration and guards: not modeled here',
            'Zero-cost outcomes are diagnostics, not deployable or validated strategies'])


def run(inputs,output):
    report=dict(status='exploration_only',cases=[],input_hashes={})
    for path in inputs:
        raw=path.read_bytes()
        report['input_hashes'][str(path)]=hashlib.sha256(raw).hexdigest()
        source=json.loads(raw)
        primary_delay=source.get('protocol',{}).get('entry_delay',1)
        for case in source['cases']:
            for result in case['outcomes']:
                if result['costs_bps']!=10 or result['delay']!=primary_delay: continue
                report['cases'].append(dict(input=str(path),
                    model=case.get('model',case.get('kernel')),minute=case.get('minute',15),
                    feature_set=case.get('feature_set'),gate=case.get('gate'),entry_delay=primary_delay,
                    horizon=case['horizon'],threshold=result['threshold'],**diagnostic(result)))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps(dict(output=str(output),cases=len(report['cases']),
        independently_validated=False)))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('inputs',nargs='+',type=Path)
    parser.add_argument('--output',type=Path,default=Path('research_runs/cost_diagnostic/results.json'))
    args=parser.parse_args()
    run(args.inputs,args.output)
