"""Past-only exponential sample weighting; not a trading recommendation."""
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from predictive_research import raw_score


def past_weights(rows, history_dates, cutoff, half_life):
    if isinstance(half_life,bool) or half_life not in [60,120]:
        raise ValueError('Predeclared60/120-session half-life required')
    if not rows or not history_dates or history_dates != sorted(set(history_dates)):
        raise ValueError('Nonempty sorted unique history required')
    if any(date >= cutoff for date in history_dates):
        raise ValueError('Weight history must precede forecast cutoff')
    index = {date:i for i,date in enumerate(history_dates)}
    if any(row['date'] not in index for row in rows):
        raise ValueError('Every weighted row must be known past history')
    ages = np.asarray([len(history_dates)-1-index[row['date']] for row in rows],dtype=float)
    weights = np.exp2(-ages/half_life)
    weights /= weights.mean()  # Preserve total row mass/regularization convention.
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError('Finite positive sample weights required')
    return weights


def weight_summary(weights, rows):
    return dict(rows=len(rows),oldest_date=min(r['date'] for r in rows),
        newest_date=max(r['date'] for r in rows),minimum=float(weights.min()),
        maximum=float(weights.max()),mean=float(weights.mean()),
        row_weight_effective_size=float(weights.sum()**2/np.dot(weights,weights)),
        effective_size_is_independent_observation_count=False)


def fit(train,calibration,test,labels,kind,history_dates,half_life):
    if kind not in ['logistic','boosted'] or not all([train,calibration,test]):
        raise ValueError('Known model and nonempty chronological partitions required')
    cutoff = min(r['date'] for r in test)
    if max(r['date'] for r in train) >= min(r['date'] for r in calibration) or max(
            r['date'] for r in calibration) >= cutoff:
        raise ValueError('Strict train/calibration/test chronology required')
    x,cx,tx = [np.asarray([r['features'] for r in rows],dtype=float)
               for rows in [train,calibration,test]]
    if any(a.ndim != 2 or not np.isfinite(a).all() or a.shape[1] != x.shape[1] for a in [x,cx,tx]):
        raise ValueError('Finite matching feature matrices required')
    y,cy = [np.asarray([labels[(r['date'],r['symbol'])] for r in rows])
            for rows in [train,calibration]]
    if set(y) != {0,1} or set(cy) != {0,1}:
        raise ValueError('Two known past label classes required')
    weights = past_weights(train,history_dates,cutoff,half_life)
    cal_weights = past_weights(calibration,history_dates,cutoff,half_life)
    classifier = (LogisticRegression(C=.1,max_iter=1000,random_state=19) if kind == 'logistic'
        else HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,min_samples_leaf=30,
                                            l2_regularization=10,random_state=19,early_stopping=False))
    model = Pipeline([('scale',StandardScaler()),('classifier',classifier)])
    model.fit(x,y,scale__sample_weight=weights,classifier__sample_weight=weights)
    calibrator = LogisticRegression(C=1,max_iter=1000,random_state=19)
    calibrator.fit(raw_score(model,cx),cy,sample_weight=cal_weights)
    probabilities = calibrator.predict_proba(raw_score(model,tx))[:,1]
    if not np.isfinite(probabilities).all():
        raise ValueError('Nonfinite forecast probabilities')
    metadata = dict(half_life_sessions=half_life,weight_history_last=history_dates[-1],
        forecast_cutoff=cutoff,train_weight_summary=weight_summary(weights,train),
        calibration_weight_summary=weight_summary(cal_weights,calibration),
        scaler_mean=model.named_steps['scale'].mean_.tolist(),
        scaler_scale=model.named_steps['scale'].scale_.tolist(),
        calibration_coefficients=calibrator.coef_.tolist(),calibration_intercept=calibrator.intercept_.tolist(),
        future_labels_used=False,orders=False)
    return probabilities,metadata
