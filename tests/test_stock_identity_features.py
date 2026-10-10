from copy import deepcopy
import numpy as np
import pytest
from active_stock_research import SYMBOLS
from causal_opening_inventory import FEATURES
from stock_identity_features import MODES,augment,feature_names


def row(symbol='AAPL'):
    return dict(date='2026-09-01',symbol=symbol,features=[i/10 for i in range(16)],signal_price=100.)


@pytest.mark.parametrize('mode',MODES)
def test_feature_dimensions_names_and_raw_units(mode):
    original = row()
    saved = deepcopy(original)
    encoded = augment(original,mode)
    names = feature_names(mode)
    assert len(names) == len(set(names)) == len(encoded['features'])
    assert len(names) == {'price_only':16,'stock_intercepts':36,'stock_intercepts_and_slopes':356}[mode]
    assert encoded['features'][:16] == original['features']
    assert encoded['signal_price'] == original['signal_price']
    assert original == saved
    encoded['features'][0] = 99
    assert original == saved


def test_stock_identity_has_only_its_fixed_vocabulary_slot():
    encoded = augment(row('NVDA'),'stock_intercepts')['features'][16:]
    assert sum(encoded) == 1
    assert encoded[SYMBOLS.index('NVDA')] == 1
    assert augment(row('AAPL'),'stock_intercepts')['features'][16:] != encoded


def test_symbol_specific_slope_block_does_not_leak_other_stock_values():
    original = row('NVDA')
    features = augment(original,'stock_intercepts_and_slopes')['features']
    blocks = np.asarray(features[36:]).reshape(20,16)
    assert blocks[SYMBOLS.index('NVDA')] == pytest.approx(original['features'])
    for i,symbol in enumerate(SYMBOLS):
        if symbol != 'NVDA':
            assert not blocks[i].any()


def test_other_future_candidates_cannot_change_current_encoding():
    original = row()
    before = augment(original,'stock_intercepts_and_slopes')
    future = row('TSLA')
    future.update(date='2027-01-01',features=[1e9]*16)
    augment(future,'stock_intercepts_and_slopes')
    assert augment(original,'stock_intercepts_and_slopes') == before


def test_unknown_symbols_modes_and_nonfinite_or_wrong_base_are_rejected():
    for original,mode in [(row('UNKNOWN'),'stock_intercepts'),(row(),'unknown'),
                          (dict(row(),features=[1]*17),'stock_intercepts'),
                          (dict(row(),features=[float('nan')]*16),'stock_intercepts')]:
        with pytest.raises(ValueError):
            augment(original,mode)
