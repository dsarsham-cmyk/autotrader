"""Same circuit/data, longer training with train-only stabilization. NO ORDERS."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations,opening_rows
from causal_sparse_research import market_maps
from causal_sparse_simulator import path,portfolio
from predictive_portfolio_research import partition
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from finbert_comparison_audit import check
from quantum_training_plateau import predict,PROTOCOL


def run(data,reference,output):
    raw=reference.read_bytes();original=json.loads(raw)
    if original['status']!='completed_exposed_variational_quantum_comparison': raise ValueError('Completed corrected circuit reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected: raise ValueError('Reference source changed')
    if any(importlib.metadata.version(n)!=v for n,v in original['packages'].items()): raise ValueError('Reference runtime changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Reference observations changed')
    by_date,reasons=opening_rows(observations)
    rows=[r for date,stocks in sorted(by_date.items()) for symbol,r in sorted(stocks.items())]
    market=market_maps(observations);dates=sorted(by_date)
    outcomes={(r['date'],r['symbol']):path(market[r['date']][r['symbol']],r['signal_price']) for r in rows}
    labels={key:o['label'] for key,o in outcomes.items() if o is not None and o['filled']}
    old=next(c for c in original['cases'] if c['model']=='quantum_variational')
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_quantum_training_stabilization',protocol=PROTOCOL,
        reference_sha256=hashlib.sha256(raw).hexdigest(),evidence=evidence,packages=original['packages'],
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['quantum_training_plateau.py','quantum_plateau_research.py']}),
        cases=[dict(old,model='quantum80_reference')],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Training loss plateau does not prove global convergence or forecast accuracy',
            'Same exposed historical outcomes, not independent validation',
            'All train/calibration labels past only; future outcome completeness does not select candidates',
            'Same circuit, limits, costs, fixed universe and modeled execution assumptions remain'])
    forecasts=[];folds=[]
    with threadpool_limits(limits=1):
        for index,start in enumerate(range(240,len(dates),20)):
            parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
            train,cal,test=[partition(rows,p) for p in parts]
            train=[r for r in train if (r['date'],r['symbol']) in labels];cal=[r for r in cal if (r['date'],r['symbol']) in labels]
            expected=old['folds'][index]
            if expected['test_first']!=parts[2][0] or expected['test_last']!=parts[2][-1]: raise ValueError('Reference fold changed')
            probabilities,training=predict(train,cal,test,labels,expected)
            forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
            folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
                test_first=parts[2][0],test_last=parts[2][-1],training=training))
            print(json.dumps(dict(fold=index+1,epochs=training['training']['epochs'],plateau=training['training']['training_loss_plateau'],
                original_epoch80_reproduced=True,orders=False)),flush=True)
        case=dict(model='quantum_training_stabilization',feature_set='same_past_PCA4',folds=folds,outcomes=[])
        for gate in [.5,.65,.9]:
            for cost,delay in [(10,16),(20,16),(10,17)]:
                result=portfolio(forecasts,market,gate,cost,delay)
                result['known_prefix_metrics']=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)
                result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                check(result);case['outcomes'].append(result)
                if cost==10 and delay==16:
                    print(json.dumps(dict(gate=gate,active_days=result['active_days'],net_usd=result['profit_usd'],
                        win_rate=result['active_day_win_rate_pct'],complete=result['full_period_coverage_complete'])),flush=True)
        report['cases'].append(case)
    report['status']='completed_exposed_quantum_training_stabilization'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/variational_quantum_corrected/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/quantum_training_plateau'))
    a=p.parse_args();run(a.data,a.reference,a.output)
