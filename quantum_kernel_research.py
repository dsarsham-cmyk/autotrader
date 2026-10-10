"""Classical versus simulated quantum fidelity kernels; research, never orders.

Four qubits, two H/RZ/CZ encoding layers. Statevector simulation on an ordinary
CPU is not quantum hardware or a claim of quantum computational advantage.
All previously inspected historical dates are exploratory, not independent.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import rbf_kernel
from sklearn.metrics import brier_score_loss

from active_stock_research import load_universe
from predictive_portfolio_research import build, partition, path_outcome, portfolio


def quantum_states(angles):
    angles = np.asarray(angles, dtype=float)
    if angles.ndim != 2 or angles.shape[1] != 4 or not np.isfinite(angles).all():
        raise ValueError('Expected finite four-dimensional angles')
    states = np.zeros((len(angles), 16), dtype=complex)
    states[:, 0] = 1
    indices = np.arange(16)
    for _ in range(2):
        for qubit in range(4):
            low = indices[(indices & (1 << qubit)) == 0]
            high = low | (1 << qubit)
            a, b = states[:, low].copy(), states[:, high].copy()
            states[:, low] = (a + b) / np.sqrt(2)
            states[:, high] = (a - b) / np.sqrt(2)
            signs = np.where(indices & (1 << qubit), 1., -1.)
            states *= np.exp(.5j * angles[:, qubit, None] * signs)
        for qubit in range(4):
            neighbour = (qubit + 1) % 4
            both = ((indices >> qubit) & 1) & ((indices >> neighbour) & 1)
            states[:, both.astype(bool)] *= -1
    return states


def fidelity_kernel(left, right):
    return np.clip(np.abs(left @ right.conj().T) ** 2, 0., 1.)


def bounded_sample(rows, maximum=600):
    # Uniform deterministic subsample of past rows; no label-based selection.
    if len(rows) <= maximum:
        return rows
    return [rows[i] for i in np.linspace(0, len(rows)-1, maximum, dtype=int)]


def predict(train, calibration, test, labels, kind):
    train = bounded_sample(train)
    calibration = bounded_sample(calibration)
    x = np.array([r['features'] for r in train])
    cx = np.array([r['features'] for r in calibration])
    tx = np.array([r['features'] for r in test])
    y = np.array([labels[(r['date'], r['symbol'])] for r in train])
    cy = np.array([labels[(r['date'], r['symbol'])] for r in calibration])
    if len(set(y)) < 2 or len(set(cy)) < 2:
        raise ValueError('Training and calibration require both outcomes')
    scaler = StandardScaler().fit(x)
    projection = PCA(n_components=4, whiten=False, random_state=19).fit(scaler.transform(x))
    # Identical past-only dimensionality reduction for both comparisons.
    features = [np.pi*np.tanh(projection.transform(scaler.transform(v))/2)
                for v in (x, cx, tx)]
    if kind == 'quantum_fidelity':
        states = [quantum_states(v) for v in features]
        kernels = [fidelity_kernel(v, states[0]) for v in states]
    elif kind == 'classical_rbf':
        kernels = [rbf_kernel(v, features[0], gamma=.25) for v in features]
    else:
        raise ValueError('Unknown kernel')
    model = SVC(C=1., kernel='precomputed', probability=False).fit(kernels[0], y)
    calibrator = LogisticRegression(C=1., random_state=19).fit(
        model.decision_function(kernels[1]).reshape(-1, 1), cy)
    return calibrator.predict_proba(model.decision_function(kernels[2]).reshape(-1, 1))[:, 1]


def run(data, output):
    by_date, evidence = load_universe(data)
    rows = build(by_date, 15)
    dates = sorted({r['date'] for r in rows})
    report = dict(status='exploration_only', independent_validation_pass=False,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
        evidence=evidence, protocol=dict(qubits=4, layers=2, hardware='classical CPU simulation',
        training_cap=600, calibration_cap=600, decision_minute=15,
        kernels=['classical_rbf', 'quantum_fidelity'], horizons=['60_minutes', 'target_60'],
        thresholds=[.5, .65, .8, .9], cost_stress=[10, 20], orders=False),
        limitations=['Previously inspected dates: no independent validation',
            'Fixed present-day stock universe: survivorship and selection bias',
            'OHLC simulated execution and assumed costs, not measured broker fills',
            'Small four-qubit model and bounded historical training sample',
            'No quantum hardware, quantum advantage, or forecast guarantee claimed'], cases=[])
    output.mkdir(parents=True, exist_ok=True)
    for horizon in ['60_minutes', 'target_60']:
        outcomes = {(r['date'], r['symbol']): path_outcome(
            by_date[r['date']][r['symbol']][0], r['signal_price'], 15, horizon) for r in rows}
        labels = {key: value['label'] for key, value in outcomes.items()}
        for kind in ['classical_rbf', 'quantum_fidelity']:
            predictions, folds = [], []
            for start in range(240, len(dates), 20):
                parts = [partition(rows, d) for d in
                    (dates[:start-60], dates[start-60:start], dates[start:start+20])]
                train, cal = [[r for r in part if outcomes[(r['date'], r['symbol'])]['filled']]
                              for part in parts[:2]]
                test = parts[2]
                p = predict(train, cal, test, labels, kind)
                predictions.extend(dict(r, probability=float(v)) for r, v in zip(test, p))
                matched = [i for i,r in enumerate(test) if outcomes[(r['date'],r['symbol'])]['filled']]
                folds.append(dict(train_last=dates[start-61], calibration_last=dates[start-1],
                    test_first=dates[start], test_last=dates[min(start+19,len(dates)-1)],
                    brier_filled=float(brier_score_loss(
                        [labels[(test[i]['date'],test[i]['symbol'])] for i in matched], p[matched]))
                    if matched else None))
            case = dict(kernel=kind, horizon=horizon, folds=folds, outcomes=[])
            for threshold in [.5,.65,.8,.9]:
                for cost,delay in [(10,1),(20,1),(10,2)]:
                    case['outcomes'].append(portfolio(predictions,by_date,15,horizon,threshold,cost,delay))
            report['cases'].append(case)
            (output/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False))
            primary = [r for r in case['outcomes'] if r['costs_bps']==10 and r['delay']==1]
            print(json.dumps(dict(kernel=kind,horizon=horizon,primary=[
                {k:r[k] for k in ('threshold','active_days','active_day_win_rate_pct','profit_usd','target_screen_pass')}
                for r in primary])), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,default=Path('cache/active_stocks'))
    parser.add_argument('--output',type=Path,default=Path('research_runs/quantum_kernel'))
    args=parser.parse_args()
    run(args.data,args.output)
