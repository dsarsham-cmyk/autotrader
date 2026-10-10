"""Matched raw/split-normalized classical and simulated quantum predictors.

Fixed80 and train-only plateau variants are all retained, never selected by
future profit. CPU only; no deployment, quantum hardware or broker orders.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from threadpoolctl import threadpool_limits
from causal_opening_inventory import load_observations, opening_rows
from causal_sparse_research import market_maps
from causal_sparse_simulator import path, portfolio
from finbert_comparison_audit import check
from fixed_trade_cost_diagnostic import diagnostic
from predictive_portfolio_research import partition
from prospective_series_audit import accounting_metrics
from quantum_training_plateau import predict as plateau_predict
from split_context_audit import events_from_pages, normalized_opening_rows
from split_predictive_research import assert_reference, flatten
from variational_quantum_classifier import predict as fixed_predict

MODELS = ['projected_logistic', 'quantum_variational', 'quantum_training_stabilization']
ARMS = ['original_raw_context', 'date_effective_split_context']


def verify_reference(report, status):
    if report['status'] != status:
        raise ValueError('Completed matching quantum reference required')
    for name, expected in report['dependency_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() != expected:
            raise ValueError('Quantum reference source changed')
    for name, expected in report['packages'].items():
        if importlib.metadata.version(name) != expected:
            raise ValueError('Quantum reference runtime changed')


def match_fold(actual, expected):
    if (actual['test_first'], actual['test_last']) != (expected['test_first'], expected['test_last']):
        raise ValueError('Original quantum fold span changed')
    if actual['training']['preprocessing'] != expected['training']['preprocessing']:
        raise ValueError('Original preprocessing not reproduced')
    if actual['training']['training']['artifact'] != expected['training']['training']['artifact']:
        raise ValueError('Original fitted artifact not reproduced')


def run(data, fixed_reference, plateau_reference, input_audit, output):
    import torch
    if torch.__version__ != '2.13.0+cpu':
        raise ValueError('Pinned isolated CPU Torch required')
    fixed = json.loads(fixed_reference.read_bytes())
    stabilized = json.loads(plateau_reference.read_bytes())
    verify_reference(fixed, 'completed_exposed_variational_quantum_comparison')
    verify_reference(stabilized, 'completed_exposed_quantum_training_stabilization')
    audit = json.loads(input_audit.read_bytes())
    if audit['status'] != 'exposed_historical_split_input_audit' or not audit['no_event_reference_exact']:
        raise ValueError('Completed split input audit required')
    receipt_path = input_audit.parent/'corporate_actions_receipt.json'
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != audit['corporate_action_receipt_sha256']:
        raise ValueError('Corporate-action receipt changed')
    observations, evidence = load_observations(data)
    if any(evidence != r['evidence'] for r in [fixed, stabilized, audit]):
        raise ValueError('Historical observation bytes changed')
    raw, reasons = opening_rows(observations)
    receipt = json.loads(receipt_path.read_bytes())
    events = events_from_pages(receipt['pages'], list(observations))
    corrected, new_reasons, applications = normalized_opening_rows(observations, events)
    if reasons != new_reasons or {d:sorted(s) for d,s in raw.items()} != {d:sorted(s) for d,s in corrected.items()}:
        raise ValueError('Split normalization changed eligibility')
    market, dates = market_maps(observations), sorted(raw)
    raw_rows = flatten(raw)
    outcomes = {(r['date'],r['symbol']):path(market[r['date']][r['symbol']],r['signal_price']) for r in raw_rows}
    labels = {key:o['label'] for key,o in outcomes.items() if o is not None and o['filled']}
    report = dict(status='running_exposed_split_quantum_comparison', cases=[], evidence=evidence,
        packages=fixed['packages'], applications=applications, orders=False, production_approved=False,
        independent_validation_pass=False, protocol=dict(arms=ARMS, models=MODELS,
            gates=[.5,.65,.9],cost_delay_variants=[(10,16),(20,16),(10,17)],
            warmup_dates=240,calibration_dates=60,test_block_dates=20,train_cap=600,calibration_cap=600,
            quantum_qubits=4,quantum_layers=2,seed=19,epoch80=80,plateau_minimum=160,plateau_cap=512,
            stock_cap=.01,category_cap=.05,max_positions=3,planned_risk=.0005,stop=.01,target=.004,
            cpu_simulation=True,orders=False),
        input_audit_sha256=hashlib.sha256(input_audit.read_bytes()).hexdigest(),
        corporate_action_receipt_sha256=audit['corporate_action_receipt_sha256'],
        references={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [fixed_reference,plateau_reference]},
        dependency_sha256=dict(stabilized['dependency_sha256'], **{n:
            hashlib.sha256(Path(n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in
            ['split_context_audit.py','split_predictive_research.py','split_quantum_research.py']}),
        limitations=['Previously exposed outcomes, not independent forward validation',
            'CPU statevector simulation, not quantum hardware or demonstrated quantum advantage',
            'Train-only stabilization does not certify a global optimum',
            'Current split records do not authenticate historical announcement delivery',
            'Past-only PCA4/600-row compression may discard useful information',
            'Fixed present universe, revisions, modeled costs/fills remain; production/frozen sources untouched'])
    output.mkdir(parents=True, exist_ok=True)
    with threadpool_limits(limits=1):
        for arm in ARMS:
            rows = raw_rows if arm == ARMS[0] else flatten(corrected)
            if [(r['date'],r['symbol'],r['signal_price']) for r in rows] != [
                    (r['date'],r['symbol'],r['signal_price']) for r in raw_rows]:
                raise ValueError('Current raw units changed')
            epoch80_folds = []
            for model in MODELS:
                forecasts, folds = [], []
                old_case = next(c for c in (stabilized if model == MODELS[2] else fixed)['cases']
                                if c['model'] == model)
                for index,start in enumerate(range(240,len(dates),20)):
                    parts = [dates[:start-60],dates[start-60:start],dates[start:start+20]]
                    train, cal, test = [partition(rows,p) for p in parts]
                    train = [r for r in train if (r['date'],r['symbol']) in labels]
                    cal = [r for r in cal if (r['date'],r['symbol']) in labels]
                    if model == MODELS[2]:
                        probabilities, training = plateau_predict(train,cal,test,labels,epoch80_folds[index])
                    else:
                        probabilities, training = fixed_predict(train,cal,test,labels,model)
                    fold = dict(train_last=parts[0][-1],cal_first=parts[1][0],cal_last=parts[1][-1],
                        test_first=parts[2][0],test_last=parts[2][-1],training=training,
                        forecast_candidates=len(test))
                    if arm == ARMS[0]:
                        match_fold(fold,old_case['folds'][index])
                    if model == MODELS[1]:
                        epoch80_folds.append(fold)
                    folds.append(fold)
                    forecasts.extend(dict(r,probability=float(p)) for r,p in zip(test,probabilities))
                    print(json.dumps(dict(arm=arm,model=model,fold=index+1,
                        epochs=training['training'].get('epochs'),orders=False)),flush=True)
                case = dict(model=model,feature_set=arm,folds=folds,forecasts=forecasts,outcomes=[])
                for gate in [.5,.65,.9]:
                    for cost,delay in [(10,16),(20,16),(10,17)]:
                        result = portfolio(forecasts,market,gate,cost,delay)
                        prefix = dict(result,profit_usd=result['known_prefix_profit_usd'])
                        result['known_prefix_metrics'] = accounting_metrics(prefix,forecasts)
                        result['known_prefix_cost_diagnostic'] = diagnostic(prefix)
                        check(result)
                        if arm == ARMS[0]:
                            expected = next(o for o in old_case['outcomes'] if
                                (o['threshold'],o['costs_bps'],o['delay']) == (gate,cost,delay))
                            assert_reference(result,expected)
                        case['outcomes'].append(result)
                        if cost == 10 and delay == 16:
                            print(json.dumps(dict(arm=arm,model=model,gate=gate,active_days=result['active_days'],
                                net_usd=result['profit_usd'],win_rate=result['active_day_win_rate_pct'],
                                complete=result['full_period_coverage_complete'])),flush=True)
                report['cases'].append(case)
                (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    report['status'] = 'completed_exposed_split_quantum_comparison'
    (output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/daily_meta_extended'))
    parser.add_argument('--fixed-reference',type=Path,default=Path('research_runs/variational_quantum_corrected/results.json'))
    parser.add_argument('--plateau-reference',type=Path,default=Path('research_runs/quantum_training_plateau/results.json'))
    parser.add_argument('--input-audit',type=Path,default=Path('research_runs/split_context_audit/results.json'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/split_quantum'))
    args = parser.parse_args()
    run(args.data,args.fixed_reference,args.plateau_reference,args.input_audit,args.output)
