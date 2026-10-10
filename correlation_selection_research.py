"""Matched fixed forecasts, diversified selection; no future outcome pruning."""
import argparse
import hashlib
import json
from pathlib import Path
from causal_opening_inventory import load_observations
from causal_sparse_research import market_maps
from causal_sparse_simulator import portfolio
from prospective_series_audit import accounting_metrics
from fixed_trade_cost_diagnostic import diagnostic
from finbert_comparison_audit import check
from past_correlation_selection import return_history,select,PROTOCOL


def run(data,reference,output):
    raw=reference.read_bytes();original=json.loads(raw)
    if original['status']!='completed_exposed_causal_sparse_research': raise ValueError('Completed reference required')
    for name,expected in original['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=expected:
            raise ValueError('Forecast-producing source changed')
    observations,evidence=load_observations(data)
    if evidence!=original['evidence']: raise ValueError('Market source changed')
    market=market_maps(observations);history=return_history(observations)
    output.mkdir(parents=True,exist_ok=True)
    report=dict(status='running_exposed_correlation_selection_comparison',protocol=PROTOCOL,
        reference_sha256=hashlib.sha256(raw).hexdigest(),evidence=evidence,
        dependency_sha256=dict(original['dependency_sha256'],**{n:hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
            for n in ['past_correlation_selection.py','correlation_selection_research.py','finbert_comparison_audit.py']}),
        cases=[],orders=False,production_approved=False,independent_validation_pass=False,
        limitations=['Exposed historical outcomes; not independent validation',
            'Prior correlation is risk context, not a claim of stable future correlation or alpha',
            'Unknown additional pair prevents selection; no past-return imputation',
            'Fixed universe, raw stock history/revisions, original receipts and modeled execution remain'])
    for diversified in [False,True]:
        for old in original['cases']:
            forecasts=old['forecasts']
            case=dict(model=old['model'],feature_set='past_correlation' if diversified else 'probability_rank',
                folds=old['folds'],outcomes=[],selection_evidence={})
            for gate in [.5,.65,.9]:
                selected,decisions=select(forecasts,history,gate,diversified)
                case['selection_evidence'][str(gate)]=decisions
                if {r['date'] for r in selected}!={r['date'] for r in forecasts}: raise ValueError('Selection dropped forecast date')
                for cost,delay in [(10,16),(20,16),(10,17)]:
                    result=portfolio(selected,market,gate,cost,delay)
                    result['known_prefix_metrics']=accounting_metrics(dict(result,profit_usd=result['known_prefix_profit_usd']),forecasts)
                    result['known_prefix_cost_diagnostic']=diagnostic(dict(result,profit_usd=result['known_prefix_profit_usd']))
                    check(result)
                    if not diversified:
                        expected=next(o for o in old['outcomes'] if (o['threshold'],o['costs_bps'],o['delay'])==(gate,cost,delay))
                        if any(result[k]!=expected[k] for k in ['profit_usd','daily','trades','unknown_selections']):
                            raise ValueError('Probability-ranked reference not reproduced')
                    case['outcomes'].append(result)
                    if cost==10 and delay==16:
                        print(json.dumps(dict(diversified=diversified,model=old['model'],gate=gate,
                            active_days=result['active_days'],net_usd=result['profit_usd'],win_rate=result['active_day_win_rate_pct'],
                            full_period=result['full_period_coverage_complete'])),flush=True)
            report['cases'].append(case);(output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status']='completed_exposed_correlation_selection_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False));return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    p.add_argument('--reference',type=Path,default=Path('research_runs/causal_sparse/results.json'))
    p.add_argument('--output',type=Path,default=Path('research_runs/correlation_selection'))
    a=p.parse_args();run(a.data,a.reference,a.output)
