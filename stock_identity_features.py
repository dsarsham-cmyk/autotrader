"""Fixed symbol vocabulary, no learned future membership or outcome inputs."""
import numpy as np
from active_stock_research import SYMBOLS
from causal_opening_inventory import FEATURES

MODES = ['price_only','stock_intercepts','stock_intercepts_and_slopes']


def feature_names(mode):
    if mode not in MODES:
        raise ValueError('Unknown predeclared identity feature set')
    names = list(FEATURES)
    if mode != 'price_only':
        names += ['stock:'+symbol for symbol in SYMBOLS]
    if mode == 'stock_intercepts_and_slopes':
        names += [symbol+':'+name for symbol in SYMBOLS for name in FEATURES]
    return names


def augment(row,mode):
    if row['symbol'] not in SYMBOLS:
        raise ValueError('Unknown symbol outside fixed research universe')
    names = feature_names(mode)
    values = np.asarray(row['features'],dtype=float)
    if values.shape != (len(FEATURES),) or not np.isfinite(values).all():
        raise ValueError('Finite original causal16 features required')
    encoded = list(row['features'])
    if mode != 'price_only':
        encoded += [float(symbol == row['symbol']) for symbol in SYMBOLS]
    if mode == 'stock_intercepts_and_slopes':
        encoded += [float(v) if symbol == row['symbol'] else 0.
                    for symbol in SYMBOLS for v in values]
    if len(encoded) != len(names):
        raise ValueError('Identity feature schema mismatch')
    return dict(row,features=encoded)
