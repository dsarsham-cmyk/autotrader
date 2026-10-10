"""Past-training stabilization audit, not global optimality or profitable alpha."""
import hashlib
import json
import numpy as np
from sklearn.linear_model import LogisticRegression
from variational_quantum_classifier import circuit,observables,projected
from quantum_kernel_research import bounded_sample

PROTOCOL=dict(minimum_epochs=160,maximum_epochs=512,plateau_window=64,
    maximum_recent_loss_range=1e-5,decision_data='training loss only',
    global_convergence_certified=False,orders=False)


def stabilized(losses):
    if len(losses)<160: return False
    if not np.isfinite(losses).all(): raise ValueError('Nonfinite loss history')
    return max(losses[-64:])-min(losses[-64:])<=1e-5


def artifact_hash(artifact):
    return hashlib.sha256(json.dumps(artifact,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def train(x,y,cal,test,expected_epoch80):
    import torch
    torch.set_num_threads(1);torch.manual_seed(19);torch.use_deterministic_algorithms(True)
    angles=torch.tensor(x,dtype=torch.float32);labels=torch.tensor(y,dtype=torch.float32)
    weights=torch.nn.Parameter(.1*torch.randn((2,4,2)))
    head=torch.nn.Parameter(.1*torch.randn(4));bias=torch.nn.Parameter(torch.zeros(()))
    optimizer=torch.optim.Adam([weights,head,bias],lr=.03,weight_decay=.01)
    losses=[];epoch80=None
    def artifact(): return dict(weights=weights.detach().tolist(),head=head.detach().tolist(),bias=float(bias.detach()))
    for epoch in range(512):
        optimizer.zero_grad();logits=observables(circuit(angles,weights))@head+bias
        loss=torch.nn.functional.binary_cross_entropy_with_logits(logits,labels)
        if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
        loss.backward()
        if any(p.grad is None or not torch.isfinite(p.grad).all() for p in [weights,head,bias]):
            raise ValueError('Invalid training gradient')
        optimizer.step();losses.append(float(loss.detach()))
        if epoch==79:
            epoch80=artifact_hash(artifact())
            if epoch80!=expected_epoch80: raise ValueError('Original80-epoch training trajectory not reproduced')
        if stabilized(losses): break
    with torch.inference_mode():
        scores=[(observables(circuit(torch.tensor(v,dtype=torch.float32),weights))@head+bias).tolist() for v in (cal,test)]
    final=artifact()
    return scores,dict(epochs=len(losses),training_losses=losses,training_loss_plateau=stabilized(losses),
        reached_epoch_cap=len(losses)==512,epoch80_artifact_sha256=epoch80,
        original_epoch80_exactly_reproduced=True,artifact=final,artifact_sha256=artifact_hash(final),
        global_convergence_certified=False)


def predict(train_rows,calibration,test_rows,labels,expected_fold):
    train_rows=bounded_sample(train_rows);calibration=bounded_sample(calibration)
    y=np.asarray([labels[(r['date'],r['symbol'])] for r in train_rows]);cy=np.asarray([labels[(r['date'],r['symbol'])] for r in calibration])
    if len(set(y))<2 or len(set(cy))<2: raise ValueError('Two past classes required')
    (x,cx,tx),preprocessing=projected(train_rows,calibration,test_rows)
    if preprocessing!=expected_fold['training']['preprocessing']: raise ValueError('Past preprocessing changed')
    expected=expected_fold['training']['training']['artifact_sha256']
    (cal_score,test_score),training=train(x,y,cx,tx,expected)
    calibrator=LogisticRegression(C=1,max_iter=1000,random_state=19).fit(np.asarray(cal_score).reshape(-1,1),cy)
    probabilities=calibrator.predict_proba(np.asarray(test_score).reshape(-1,1))[:,1]
    return probabilities,dict(training=training,preprocessing=preprocessing,
        calibration=dict(coefficients=calibrator.coef_.tolist(),intercept=calibrator.intercept_.tolist()))
