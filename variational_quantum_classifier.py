"""Trainable four-qubit statevector simulation; not hardware/quantum advantage."""
import hashlib
import json
import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from quantum_kernel_research import bounded_sample

PROTOCOL=dict(qubits=4,layers=2,encoding='RY bounded PCA input, reuploaded each layer',
    trainable_gates='RZ then RY per qubit and layer, phase before noncommuting rotation',entangler='CZ ring',readout='four Z expectations plus classical linear head',
    train_cap=600,calibration_cap=600,epochs=80,learning_rate=.03,weight_decay=.01,
    seed=19,cpu_threads=1,complex_dtype='complex64',model='variational circuit, not fixed quantum kernel',orders=False)


def projected(train,calibration,test):
    arrays=[np.asarray([r['features'] for r in rows],dtype=float) for rows in (train,calibration,test)]
    if any(a.ndim!=2 or a.shape[1]<4 or not np.isfinite(a).all() for a in arrays):
        raise ValueError('Finite feature arrays with at least four columns required')
    scaler=StandardScaler().fit(arrays[0]);pca=PCA(n_components=4,random_state=19).fit(scaler.transform(arrays[0]))
    features=[np.pi*np.tanh(pca.transform(scaler.transform(a))/2) for a in arrays]
    return features,dict(scaler_mean=scaler.mean_.tolist(),scaler_scale=scaler.scale_.tolist(),
        pca_components=pca.components_.tolist(),pca_mean=pca.mean_.tolist())


def circuit(angles,weights):
    import torch
    if angles.ndim!=2 or angles.shape[1]!=4 or weights.shape!=(2,4,2): raise ValueError('Invalid circuit shape')
    indices=torch.arange(16,device=angles.device)
    state=torch.zeros((len(angles),16),dtype=torch.complex64,device=angles.device);state[:,0]=1
    def ry(current,theta,q):
        low=indices[(indices&(1<<q))==0];high=low|(1<<q)
        a=current[:,low];b=current[:,high];c=torch.cos(theta/2).reshape(-1,1);s=torch.sin(theta/2).reshape(-1,1)
        updated=current.clone();updated[:,low]=c*a-s*b;updated[:,high]=s*a+c*b
        return updated
    for layer in range(2):
        for q in range(4):
            state=ry(state,angles[:,q],q)
            signs=torch.where((indices&(1<<q))==0,-1.,1.)
            state=state*torch.exp(.5j*weights[layer,q,1]*signs)
            state=ry(state,weights[layer,q,0],q)
        for q in range(4):
            both=((indices>>q)&1)&((indices>>((q+1)%4))&1)
            state=state*torch.where(both.bool(),-1.,1.)
    return state


def observables(states):
    import torch
    indices=torch.arange(16,device=states.device)
    signs=torch.stack([torch.where((indices&(1<<q))==0,1.,-1.) for q in range(4)])
    return states.abs().square()@signs.T


def train_circuit(x,y,cal,test):
    import torch
    torch.set_num_threads(1);torch.manual_seed(19);torch.use_deterministic_algorithms(True)
    angles=torch.tensor(x,dtype=torch.float32);labels=torch.tensor(y,dtype=torch.float32)
    weights=torch.nn.Parameter(.1*torch.randn((2,4,2)))
    head=torch.nn.Parameter(.1*torch.randn(4));bias=torch.nn.Parameter(torch.zeros(()))
    optimizer=torch.optim.Adam([weights,head,bias],lr=.03,weight_decay=.01)
    losses=[]
    for epoch in range(80):
        optimizer.zero_grad();logits=observables(circuit(angles,weights))@head+bias
        loss=torch.nn.functional.binary_cross_entropy_with_logits(logits,labels)
        if not torch.isfinite(loss): raise ValueError('Nonfinite training loss')
        loss.backward()
        if any(p.grad is None or not torch.isfinite(p.grad).all() for p in [weights,head,bias]):
            raise ValueError('Invalid circuit gradient')
        optimizer.step();losses.append(float(loss.detach()))
    with torch.inference_mode():
        scores=[(observables(circuit(torch.tensor(v,dtype=torch.float32),weights))@head+bias).tolist() for v in (cal,test)]
    artifact=dict(weights=weights.detach().tolist(),head=head.detach().tolist(),bias=float(bias.detach()))
    return scores,dict(epochs=80,training_losses=losses,initial_loss=losses[0],final_loss=losses[-1],
        fixed_epoch_budget=True,convergence_certified=False,
        artifact_sha256=hashlib.sha256(json.dumps(artifact,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
        artifact=artifact)


def predict(train,calibration,test,labels,kind):
    train=bounded_sample(train);calibration=bounded_sample(calibration)
    y=np.asarray([labels[(r['date'],r['symbol'])] for r in train]);cy=np.asarray([labels[(r['date'],r['symbol'])] for r in calibration])
    if len(set(y))<2 or len(set(cy))<2: raise ValueError('Two past classes required')
    (x,cx,tx),preprocessing=projected(train,calibration,test)
    if kind=='quantum_variational':
        (cal_score,test_score),training=train_circuit(x,y,cx,tx)
    elif kind=='projected_logistic':
        model=LogisticRegression(C=.1,max_iter=1000,random_state=19).fit(x,y)
        cal_score=model.decision_function(cx);test_score=model.decision_function(tx)
        training=dict(artifact=dict(coefficients=model.coef_.tolist(),intercept=model.intercept_.tolist()))
    else: raise ValueError('Unknown projected model')
    calibrator=LogisticRegression(C=1,max_iter=1000,random_state=19).fit(np.asarray(cal_score).reshape(-1,1),cy)
    result=calibrator.predict_proba(np.asarray(test_score).reshape(-1,1))[:,1]
    return result,dict(training=training,preprocessing=preprocessing,past_train_rows=len(train),past_calibration_rows=len(calibration),
        calibration=dict(coefficients=calibrator.coef_.tolist(),intercept=calibrator.intercept_.tolist()))
