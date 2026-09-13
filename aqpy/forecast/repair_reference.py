"""Independent numerical reference for fresh-fit repair adapters.

No production fit, feature or prediction function is called. GRU sequences are
encoded as a bounded matrix, independently of the production per-sequence loop.
"""
import numpy as np


def features(values,lags,extra):
    x=np.asarray(values,dtype=float);start=max(lags)
    columns=[x[start-lag:len(x)-lag] for lag in lags]
    if extra:
        columns += [np.asarray([np.mean(x[max(0,i-width):i]) for i in range(start,len(x))]) for width in (3,12)]
    return np.column_stack(columns),x[start:]


def encode(encoder,sequences):
    seq=np.asarray(sequences,dtype=float)
    h=np.zeros((len(seq),len(encoder['bz'])))
    for i in range(seq.shape[1]):
        x=seq[:,i:i+1]
        z=1/(1+np.exp(-(x@encoder['Wz']+h@encoder['Uz']+encoder['bz'])))
        r=1/(1+np.exp(-(x@encoder['Wr']+h@encoder['Ur']+encoder['br'])))
        candidate=np.tanh(x@encoder['Wh']+(r*h)@encoder['Uh']+encoder['bh'])
        h=(1-z)*h+z*candidate
    return h


def fit_reference(spec,values,seed):
    family=spec['model_type'];lags=spec.get('lags',[1,2,3,6,12]);v=np.asarray(values,dtype=float)
    result={'model_type':family,'lags':lags}
    if family=='adaptive_ar':
        X,y=features(v,lags,False);scale=np.maximum(np.max(abs(X),axis=0),1.)
        weight=spec.get('forgetting_factor',.995)**(np.arange(len(y)-1,-1,-1)/2.)
        A=np.vstack((X/scale*weight[:,None],np.eye(len(lags))/np.sqrt(spec.get('ar_delta',100.))))
        result['theta']=np.linalg.lstsq(A,np.concatenate((y*weight,np.zeros(len(lags)))),rcond=None)[0]/scale
    elif family=='nn_mlp':
        X,y=features(v,lags,True);xm=np.mean(X,axis=0);xs=np.std(X,axis=0);xs=np.where(xs<1e-8,1.,xs)
        ym=float(np.mean(y));ys=float(np.std(y));ys=1. if ys<1e-8 else ys
        X=(X-xm)/xs;y=((y-ym)/ys)[:,None]
        rng=np.random.default_rng(seed);hidden=spec.get('hidden_dim',8)
        w1=rng.normal(0,.1,(X.shape[1],hidden));b1=np.zeros(hidden)
        w2=rng.normal(0,.1,(hidden,1));b2=np.zeros(1)
        rng=np.random.default_rng(seed);rate=spec.get('learning_rate',.01);batch=spec.get('batch_size',64)
        for _ in range(spec.get('epochs',40)):
            order=rng.permutation(len(X));xe=X[order];ye=y[order]
            for start in range(0,len(X),batch):
                x=xe[start:start+batch];actual=ye[start:start+batch]
                z=x@w1+b1;a=np.maximum(z,0);pred=a@w2+b2;error=2*(pred-actual)/len(x)
                dw2=a.T@error;db2=error.sum(axis=0);dz=(error@w2.T)*(z>0)
                dw1=x.T@dz;db1=dz.sum(axis=0)
                w1-=rate*dw1;b1-=rate*db1;w2-=rate*dw2;b2-=rate*db2
        result.update(w1=w1,b1=b1,w2=w2,b2=b2,x_mean=xm,x_std=xs,y_mean=ym,y_std=ys)
    elif family=='rnn_lite_gru':
        length=spec.get('seq_len',24);hidden=spec.get('hidden_dim',8);rng=np.random.default_rng(seed)
        encoder={}
        for gate in ['z','r','h']:
            encoder['W'+gate]=rng.normal(0,.2,(1,hidden));encoder['U'+gate]=rng.normal(0,.2,(hidden,hidden));encoder['b'+gate]=np.zeros(hidden)
        mean=float(np.mean(v));std=float(np.std(v));std=1. if std<1e-8 else std
        normalized=(v-mean)/std
        windows=np.lib.stride_tricks.sliding_window_view(normalized,length)[:-1]
        H=encode(encoder,windows)
        weights=np.linalg.solve(H.T@H+spec.get('rnn_ridge',.001)*np.eye(hidden),H.T@normalized[length:])
        result.update(encoder=encoder,head_w=weights,head_b=0.,x_mean=mean,x_std=std,seq_len=length)
    else:raise ValueError('Unsupported reference family')
    return result


def predict_reference(model,values,horizon):
    family=model['model_type'];history=list(values);predictions=[];lags=model.get('lags',[1,2,3,6,12])
    for _ in range(horizon):
        if family=='adaptive_ar':
            value=float(np.asarray([history[-lag] for lag in lags])@np.asarray(model['theta']))
        elif family=='nn_mlp':
            x=np.asarray([history[-lag] for lag in lags]+[np.mean(history[-3:]),np.mean(history[-12:])])
            x=(x-np.asarray(model['x_mean']))/np.asarray(model['x_std'])
            scaled=np.maximum(x@np.asarray(model['w1'])+np.asarray(model['b1']),0)@np.asarray(model['w2'])+np.asarray(model['b2'])
            value=float(scaled[0]*model['y_std']+model['y_mean'])
        else:
            seq=(np.asarray(history[-model['seq_len']:])-model['x_mean'])/model['x_std']
            encoder={k:np.asarray(v) for k,v in model['encoder'].items() if k!='hidden_dim'}
            h=encode(encoder,seq[None,:])[0]
            value=float((h@np.asarray(model['head_w'])+model['head_b'])*model['x_std']+model['x_mean'])
        history.append(value);predictions.append(value)
    return predictions
