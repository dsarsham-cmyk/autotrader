import importlib.util
import numpy as np
import pytest
from variational_quantum_classifier import projected,predict,circuit,observables,train_circuit

TORCH=importlib.util.find_spec('torch') is not None


def rows():
    return [dict(date=f'{i:04d}',symbol='A',features=v.tolist()) for i,v in enumerate(np.random.default_rng(19).normal(size=(80,6)))]


def test_projection_scaling_is_past_only():
    r=rows();before,state=projected(r[:40],r[40:60],r[60:])
    future=[dict(v,features=[999.]*6) for v in r[60:]]
    after,new=projected(r[:40],r[40:60],future)
    assert state==new and np.array_equal(before[0],after[0]) and np.array_equal(before[1],after[1])


def test_classical_control_future_rows_do_not_change_other_predictions():
    r=rows();labels={(v['date'],'A'):i%2 for i,v in enumerate(r)}
    before,state=predict(r[:40],r[40:60],r[60:],labels,'projected_logistic')
    after,new=predict(r[:40],r[40:60],r[60:]+[dict(r[-1],features=[999.]*6)],labels,'projected_logistic')
    assert state==new and np.allclose(before,after[:-1],rtol=0,atol=1e-12)


@pytest.mark.skipif(not TORCH,reason='Torch only in isolated research runtime')
def test_circuit_preserves_norm_and_has_finite_parameter_gradients():
    import torch
    x=torch.tensor([[.2,.4,.6,.8],[-.1,.3,.5,.9]])
    w=torch.full((2,4,2),.17,requires_grad=True)
    state=circuit(x,w)
    assert torch.allclose(state.abs().square().sum(1),torch.ones(2),atol=1e-6)
    result=observables(state);assert (result.abs()<=1+1e-6).all()
    result.sum().backward();assert torch.isfinite(w.grad).all() and w.grad.abs().sum()>0


@pytest.mark.skipif(not TORCH,reason='Torch only in isolated research runtime')
def test_actual_training_is_deterministic_and_test_rows_do_not_change_weights():
    x=np.random.default_rng(19).normal(size=(40,4));y=np.arange(40)%2
    scores,state=train_circuit(x,y,x[:10],x[10:15])
    changed,new=train_circuit(x,y,x[:10],np.vstack([x[10:15],[999.]*4]))
    assert state==new and state['epochs']==80 and np.isfinite(state['training_losses']).all()
    assert np.array_equal(scores[0],changed[0]) and np.allclose(scores[1],changed[1][:-1],rtol=0,atol=1e-6)


@pytest.mark.skipif(not TORCH,reason='Torch only in isolated research runtime')
def test_zero_rotation_angles_leave_zero_state():
    import torch
    s=circuit(torch.zeros((2,4)),torch.zeros((2,4,2)))
    assert torch.equal(s[:,0],torch.ones(2,dtype=torch.complex64))
    assert torch.equal(observables(s),torch.ones((2,4)))


@pytest.mark.skipif(not TORCH,reason='Torch only in isolated research runtime')
def test_terminal_phase_parameters_affect_noncommuting_readout():
    import torch
    x=torch.tensor([[.2,.4,.6,.8],[-.1,.3,.5,.9]])
    w=torch.full((2,4,2),.17,requires_grad=True)
    observables(circuit(x,w)).sum().backward()
    assert (w.grad[1,:,1].abs()>.001).all()
