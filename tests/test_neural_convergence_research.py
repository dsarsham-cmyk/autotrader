import numpy as np
import pytest
import neural_convergence_research as research


def test_training_plateau_replay_requires_more_than_patience():
    assert not research.verify_plateau([1,.9]+[.9]*20)['plateau_reached']
    assert research.verify_plateau([1,.9]+[.9]*21)['plateau_reached']
    reset=research.verify_plateau([1,.9]+[.9]*21+[.8])
    assert not reset['plateau_reached'] and reset['no_improvement_count']==0
    assert reset['best_training_loss']==.8


@pytest.mark.parametrize('curve',[[],[float('nan')],[float('inf')]])
def test_invalid_loss_evidence_fails_closed(curve):
    with pytest.raises(ValueError): research.verify_plateau(curve)


def rows():
    rng=np.random.default_rng(19)
    values=[dict(date=f'{i:04d}',symbol='A',features=rng.normal(size=4).tolist()) for i in range(160)]
    labels={(r['date'],'A'):i%2 for i,r in enumerate(values)}
    return values,labels


def test_future_features_labels_do_not_change_training_stopping_or_other_forecasts():
    values,labels=rows()
    before,metadata=research.fit_probability(values[:100],values[100:140],values[140:],labels)
    values[-1]['features']=[1e6]*4;labels[(values[-1]['date'],'A')]=1-labels[(values[-1]['date'],'A')]
    after,modified=research.fit_probability(values[:100],values[100:140],values[140:],labels)
    assert np.allclose(before[:-1],after[:-1]) and metadata==modified
    assert not metadata['calibration_or_test_used_for_stopping']
    assert not metadata['global_optimum_proven']
    assert len(metadata['loss_curve'])==metadata['fitted_iterations']


def test_calibration_labels_do_not_change_training_stopping():
    values,labels=rows()
    _,metadata=research.fit_probability(values[:100],values[100:140],values[140:],labels)
    for r in values[100:140]: labels[(r['date'],'A')]=1-labels[(r['date'],'A')]
    _,modified=research.fit_probability(values[:100],values[100:140],values[140:],labels)
    assert metadata==modified  # calibrator may change; training loss/epochs cannot


def test_chronological_overlap_rejected():
    values,labels=rows()
    with pytest.raises(ValueError,match='overlap'):
        research.fit_probability(values[:100],values[100:140],values[130:],labels)
