import importlib.util
import numpy as np
import pytest
from quantum_training_plateau import stabilized,train
from variational_quantum_classifier import train_circuit


def test_stabilization_needs_past_history_not_just_epoch_count():
    assert not stabilized([.6]*159)
    assert stabilized([.6]*160)
    assert not stabilized(np.linspace(.7,.6,160).tolist())
    assert not stabilized([.6,.61]*80)
    with pytest.raises(ValueError): stabilized([float('nan')]*160)


@pytest.mark.skipif(importlib.util.find_spec('torch') is None,reason='Torch only in isolated runtime')
def test_epoch80_matches_reference_and_future_rows_do_not_stop_training():
    x=np.random.default_rng(19).normal(size=(20,4));y=np.arange(20)%2
    _,reference=train_circuit(x,y,x[:4],x[:4])
    scores,state=train(x,y,x[:4],x[:4],reference['artifact_sha256'])
    changed,new=train(x,y,x[:4],np.vstack([x[:4],[999.]*4]),reference['artifact_sha256'])
    assert state==new and state['original_epoch80_exactly_reproduced']
    assert state['epochs']<=512 and not state['global_convergence_certified']
    assert np.allclose(scores[1],changed[1][:-1],rtol=0,atol=1e-6)


@pytest.mark.skipif(importlib.util.find_spec('torch') is None,reason='Torch only in isolated runtime')
def test_incompatible_epoch80_checkpoint_fails_closed():
    x=np.zeros((8,4));y=np.arange(8)%2
    with pytest.raises(ValueError,match='trajectory'): train(x,y,x,x,'different')
