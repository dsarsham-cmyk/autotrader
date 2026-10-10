import numpy as np
import pytest
from quantum_kernel_research import quantum_states, fidelity_kernel, bounded_sample, predict


def test_states_normalized_and_kernel_psd():
    angles=np.random.default_rng(3).normal(size=(20,4))
    states=quantum_states(angles)
    assert np.allclose(np.linalg.norm(states,axis=1),1)
    kernel=fidelity_kernel(states,states)
    assert np.allclose(np.diag(kernel),1)
    assert np.allclose(kernel,kernel.T)
    assert np.linalg.eigvalsh(kernel).min()>-1e-10


def test_encoding_distinguishes_inputs():
    states=quantum_states(np.array([[0,0,0,0],[1,2,3,4]]))
    assert fidelity_kernel(states,states)[0,1]<.99


def test_nonfinite_rejected():
    with pytest.raises(ValueError):
        quantum_states(np.full((1,4),np.nan))


def test_subsample_deterministic_and_preserves_time_order():
    rows=list(range(1000))
    selected=bounded_sample(rows)
    assert len(selected)==600 and selected==sorted(set(selected))
    assert selected[0]==0 and selected[-1]==999


@pytest.mark.parametrize('kind',['classical_rbf','quantum_fidelity'])
def test_future_candidate_cannot_change_other_predictions(kind):
    rng=np.random.default_rng(9)
    rows=[dict(date=str(i),symbol='A',features=rng.normal(size=11)) for i in range(90)]
    labels={(r['date'],'A'):i%2 for i,r in enumerate(rows)}
    first=predict(rows[:50],rows[50:80],rows[80:],labels,kind)
    rows[-1]['features']=np.full(11,1e6)
    second=predict(rows[:50],rows[50:80],rows[80:],labels,kind)
    assert np.allclose(first[:-1],second[:-1])
    assert np.isfinite(second).all() and ((second>=0)&(second<=1)).all()
