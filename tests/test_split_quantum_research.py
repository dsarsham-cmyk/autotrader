from copy import deepcopy
import pytest
from split_quantum_research import ARMS, MODELS, match_fold


def fold():
    return dict(test_first='2026-09-01',test_last='2026-09-30',
        training=dict(preprocessing=dict(scaler_mean=[1,2,3,4]),
                      training=dict(artifact=dict(weights=[1,2]))))


def test_quantum_controls_require_same_span_preprocessing_and_artifact():
    reference = fold()
    match_fold(deepcopy(reference),reference)
    changed = deepcopy(reference)
    changed['test_first'] = '2026-09-02'
    with pytest.raises(ValueError,match='span'):
        match_fold(changed,reference)
    changed = deepcopy(reference)
    changed['training']['preprocessing']['scaler_mean'][0] = 0
    with pytest.raises(ValueError,match='preprocessing'):
        match_fold(changed,reference)
    changed = deepcopy(reference)
    changed['training']['training']['artifact']['weights'][0] = 0
    with pytest.raises(ValueError,match='artifact'):
        match_fold(changed,reference)


def test_comparison_retains_both_inputs_and_both_quantum_training_budgets():
    assert ARMS == ['original_raw_context','date_effective_split_context']
    assert MODELS == ['projected_logistic','quantum_variational','quantum_training_stabilization']
