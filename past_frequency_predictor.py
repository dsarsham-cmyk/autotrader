"""Past-only base rates, not calibrated evidence of future profitability."""
from collections import Counter
import numpy as np
from active_stock_research import SYMBOLS

KINDS = ['recent_global_frequency','recent_stock_shrink_frequency']
PRIOR_ROW_MASS = 20


def predict(calibration,test,labels,kind):
    if kind not in KINDS or not calibration or not test:
        raise ValueError('Known baseline and nonempty dated partitions required')
    if max(r['date'] for r in calibration) >= min(r['date'] for r in test):
        raise ValueError('All frequency evidence must precede forecast dates')
    for rows in [calibration,test]:
        keys = [(r['date'],r['symbol']) for r in rows]
        if len(keys) != len(set(keys)) or any(r['symbol'] not in SYMBOLS for r in rows):
            raise ValueError('Unique fixed-universe candidates required')
    wins,counts = Counter(),Counter()
    for row in calibration:
        key = (row['date'],row['symbol'])
        if key not in labels or labels[key] not in (0,1):
            raise ValueError('Known binary past outcomes required')
        counts[row['symbol']] += 1
        wins[row['symbol']] += int(labels[key])
    n,k = sum(counts.values()),sum(wins.values())
    global_probability = (k+1)/(n+2)  # Fixed Laplace smoothing, no test tuning.
    probabilities = {symbol: global_probability if kind == KINDS[0] else
        (wins[symbol]+PRIOR_ROW_MASS*global_probability)/(counts[symbol]+PRIOR_ROW_MASS)
        for symbol in SYMBOLS}
    values = np.asarray([probabilities[r['symbol']] for r in test])
    metadata = dict(model=kind,calibration_first=min(r['date'] for r in calibration),
        calibration_last=max(r['date'] for r in calibration),past_known_filled_rows=n,
        past_wins=k,global_probability=global_probability,prior_row_mass=PRIOR_ROW_MASS,
        stock_counts=dict(counts),stock_wins=dict(wins),stock_probabilities=probabilities,
        labels_after_calibration_used=False,uncertainty_certified=False,orders=False)
    return values,metadata
