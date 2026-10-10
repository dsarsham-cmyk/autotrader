"""Chronological trainable-circuit comparison on causal price inputs, NO ORDERS."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations,opening_rows
from causal_sparse_research import market_maps
from causal_sparse_simulator import path,portfolio
from predictive_portfolio_research import partition
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from finbert_comparison_audit import check
from variational_quantum_classifier import predict,PROTOCOL


def run(data,output):
    import torch
    if torch.__version__!='2.13.0+cpu': raise ValueError('Pinned isolated CPU Torch runtime required')
    observations,evidence=load_observations(data);by_date,reasons=opening_rows(observations)
    rows=[r for date,stocks in sorted(by_date.items()) for symbol,r in sorted(stocks.items())]
    market=market_maps(observations);dates=sorted(by_date)
    outcomes={(r['date'],r['symbol']):path(market[r['date']][r['symbol']],r['signal_price']) for r in rows}
    labels={key:o['label'] for key,o in outcomes.items() if o is not None and o['filled']}
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_variational_quantum_comparison',protocol=PROTOCOL,evidence=evidence,
        packages={n:importlib.metadata.version(n) for n in ['torch','numpy','scikit-learn','scipy','pandas','threadpoolctl']},
        dependency_sha256={n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in
            ['variational_quantum_classifier.py','variational_quantum_research.py','causal_opening_inventory.py',
             'causal_sparse_research.py','causal_sparse_simulator.py','predictive_portfolio_research.py','predictive_research.py',
             'quantum_kernel_research.py','prospective_series_audit.py','fixed_trade_cost_diagnostic.py','finbert_comparison_audit.py']},
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Classical CPU statevector simulation, not quantum hardware or quantum advantage',
            'Previously exposed historical outcomes, not independent validation',
            'Fixed80-epoch training budget, not proof of a global optimum or training convergence',
            'Four-dimensional compression/bounded600 training rows may lose predictive information',
            'Fixed universe/raw corporate actions/original receipts/modeled execution remain'])
    with threadpool_limits(limits=1):
        for kind in ['projected_logistic','quantum_variational']:
            forecasts=[];folds=[]
            for start in range(240,len(dates),20):
                parts=[dates[:start-60],dates[start-60:start],dates[start:start+20]]
                train,cal,test=[partition(rows,p) for p in parts]
                train=[r for r in train if (r['date'],r['symbol']) in labels];cal=[r for r in cal if (r['date'],r['symbol']) in labels]
                probabilities,training=predict(train,cal,test,labels,kind)
                forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
                known=[(i,labels[(r['date'],r['symbol'])]) for i,r in enumerate(test) if (r['date'],r['symbol']) in labels]
                folds.append(dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
                    test_first=parts[2][0],test_last=parts[2][-1],training=training,
                    forecast_candidates=len(test),known_filled_test=len(known),
                    brier_known_filled=float(np.mean([(probabilities[i]-label)**2 for i,label in known])) if known else None))
                print(json.dumps(dict(model=kind,fold=len(folds),test_last=parts[2][-1],orders=False)),flush=True)
            case=dict(model=kind,feature_set='past_scaled_PCA4',folds=folds,outcomes=[])
            for gate in [.5,.65,.9]:
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(forecasts,market,gate,cost,delay)
                    result['known_prefix_metrics']=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)
                    result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                    check(result);case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(model=kind,gate=gate,active_days=result['active_days'],net_usd=result['profit_usd'],
                            win_rate=result['active_day_win_rate_pct'],complete=result['full_period_coverage_complete'])),flush=True)
            report['cases'].append(case);(output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_variational_quantum_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--output',type=Path,default=Path('research_runs/variational_quantum'))
    a=p.parse_args();run(a.data,a.output)
