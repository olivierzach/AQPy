"""Independent source, coverage, model mathematics and output-policy audit."""
import bisect
import collections
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import numpy as np
from aqpy.forecast.repair_reference import fit_reference,predict_reference


def reference_policy(target,raw,history):
    particle=target in {f'pm{s}_{k}' for s in ('10','25','100') for k in ('st','en')} | {f'p{i}' for i in range(1,7)}
    if not math.isfinite(raw):raise ValueError('Nonfinite forecast')
    baseline=history[-1]
    if particle and raw<0:return 0.,'nonnegative_projection_v1'
    if (target=='humidity' and not 0<=raw<=100) or (target=='aqi_pm' and not 0<=raw<=500) or (target=='pressure' and raw<0):
        return baseline,'physical_persistence_v1'
    if len(history)>=20:
        recent=history[-50:];low=min(recent);high=max(recent)
        span=max(high-low,.1 if target in ('temperature','humidity','pressure') else 1.)
        if raw<low-10*span or raw>high+10*span:return baseline,'causal_stability_persistence_v1'
    return raw,'unchanged'


def same(expected,actual,path='model'):
    if isinstance(expected,dict):
        return max([same(v,actual[k],path+'.'+k) for k,v in expected.items()] or [0.])
    if isinstance(expected,str):
        if expected!=actual:raise ValueError(path+' differs')
        return 0.
    x=np.asarray(expected,dtype=float);y=np.asarray(actual,dtype=float)
    if x.shape!=y.shape or not np.isfinite(y).all() or not np.allclose(x,y,rtol=1e-7,atol=1e-7):
        raise ValueError(path+' differs from independent fit')
    return float(np.max(abs(x-y))) if x.size else 0.


def audit(directory):
    import fcntl
    root=Path(directory)
    with (root.parent/'.replay-worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _audit(root)


def _audit(root):
    report={'status':'FAIL','checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),'models':[],'failures':[],
            'numerical_tolerance':{'relative':1e-7,'absolute':1e-7}}
    conn=sqlite3.connect(f'file:{root.resolve()}/inventory.sqlite?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA cache_size=-4096')
    def check(ok,message):
        if not ok:raise ValueError(message)
    try:
        check(conn.execute("SELECT value FROM meta WHERE key='repair_prepared'").fetchone() is not None,'Not prepared')
        check(conn.execute('SELECT count(*) FROM repair_tasks WHERE complete=0').fetchone()[0]==0,'Repair tasks incomplete')
        check(conn.execute('PRAGMA quick_check').fetchone()[0]=='ok','SQLite integrity')
        finalized=conn.execute("SELECT value FROM meta WHERE key='repair_finalized'").fetchone() is not None
        # Verify immutable source snapshots and original prediction fingerprints.
        for source in conn.execute('SELECT * FROM sources').fetchall():
            digest=hashlib.sha256();count=0;previous=None
            for row in conn.execute('SELECT seq,ts,y FROM samples WHERE source=? ORDER BY seq',(source['source'],)):
                seq,ts,value=row
                check(seq==count and math.isfinite(value) and (previous is None or ts>previous),'Invalid source sequence')
                digest.update(json.dumps([ts,value],sort_keys=True).encode());count+=1;previous=ts
            check(count==source['rows'] and digest.hexdigest()==source['sha256'],'Source fingerprint mismatch: '+source['source'])
        for m in conn.execute('SELECT * FROM models').fetchall():
            digest=hashlib.sha256();count=0
            for row in conn.execute('SELECT * FROM forecasts WHERE model=? ORDER BY target_ts,id',(m['model'],)):
                digest.update(json.dumps(tuple(row),sort_keys=True).encode());count+=1
            check(count==m['rows'] and digest.hexdigest()==m['sha256'],'Original forecast fingerprint mismatch: '+m['model'])
        ar=conn.execute("SELECT value FROM meta WHERE key='ar_replay_path'").fetchone()
        if ar:
            ar_root=Path(ar[0]);proof=json.loads((ar_root/'validation.json').read_text())
            check(proof['status']=='PASS','Imported AR replay lacks valid audit')
            digest=hashlib.sha256()
            with (ar_root/'replay.sqlite').open('rb') as stream:
                for block in iter(lambda:stream.read(65536),b''):digest.update(block)
            check(digest.hexdigest()==proof['files_sha256']['replay.sqlite'],'Imported AR evidence changed')
            conn.execute('ATTACH DATABASE ? AS ar',(f'file:{ar_root}/replay.sqlite?mode=ro',))
        for model in conn.execute('SELECT * FROM repair_models ORDER BY model').fetchall():
            name=model['model'];spec=json.loads(model['spec']);target_name=spec['target']
            rows=conn.execute('SELECT ts,y FROM samples WHERE source=? ORDER BY ts',(model['source'],)).fetchall()
            times=[r['ts'] for r in rows];values=[r['y'] for r in rows]
            fits={};max_fit_difference=0.
            for fitted in conn.execute('SELECT * FROM repair_fits WHERE model=? ORDER BY issue',(name,)):
                end=bisect.bisect_right(times,fitted['issue'])
                begin=max(0,end-spec.get('max_train_rows',5000),bisect.bisect_left(times,fitted['issue']-spec.get('history_hours',336)*3600))
                check(end-1==fitted['last_seq'] and times[end-1]==fitted['cutoff'] and fitted['cutoff']<=fitted['issue'],'Noncausal fit')
                check(fitted['seed']==spec.get('random_seed',42)+end-1,'Unexpected fit seed')
                check(end-begin>=spec.get('burn_in_rows',200),'Insufficient fit history')
                reference=fit_reference(spec,values[begin:end],fitted['seed']);artifact=json.loads(fitted['artifact'])
                max_fit_difference=max(max_fit_difference,same(reference,artifact))
                fits[fitted['id']]=(reference,fitted['cutoff'])
            counts=collections.Counter();score_groups=collections.defaultdict(lambda:[0,0.,0.,0.,0.,0.])
            original_totals=collections.defaultdict(lambda:[0,0.,0.,0.,0.])
            max_prediction_difference=0.;prediction_cache={}
            horizons={(r[0],r[1]):r[2] for r in conn.execute('SELECT fit_id,issued,max(horizon) FROM repaired WHERE model=? AND fit_id IS NOT NULL GROUP BY fit_id,issued',(name,))}
            # Validate repair coverage for every original forecast, independently
            # deciding whether an output correction/reconstruction was necessary.
            for original in conn.execute('SELECT * FROM forecasts WHERE model=? ORDER BY id',(name,)):
                key='original:'+str(original['id']);seq=bisect.bisect_right(times,original['generated'])-1
                output=conn.execute('SELECT * FROM repaired WHERE model=? AND key=?',(name,key)).fetchone()
                unresolved=conn.execute('SELECT reason FROM unresolved WHERE model=? AND key=?',(name,key)).fetchone()
                if seq<0:
                    check(unresolved is not None and output is None,'Unreported missing pre-issue history');continue
                raw=original['yhat'];finite=raw is not None and isinstance(raw,(int,float)) and math.isfinite(raw)
                rebuild=target_name=='aqi_pm' or not finite or original['generated']>=original['target_ts'] or original['trained_at'] is None or original['trained_at']>original['generated']
                reason=reference_policy(target_name,raw,values[max(0,seq-49):seq+1])[1] if finite else None
                needed=rebuild or reason!='unchanged'
                check(bool(output or unresolved)==needed,'Wrong original repair selection: '+name+'/'+key)
                check(not(output and unresolved),'Conflicting resolved/unresolved status')
                if output:
                    check(output['original_id']==original['id'] and output['horizon']==original['horizon'] and output['target_ts']==original['target_ts'],'Original repair identity mismatch')
                    if not rebuild:check(output['raw_yhat']==original['yhat'] and output['issued']==original['generated'],'Original prediction overwritten')
                elif not needed:
                    i=bisect.bisect_left(times,original['target_ts']);candidates=[k for k in (i-1,i) if 0<=k<len(values)]
                    k=min(candidates,key=lambda k:abs(times[k]-original['target_ts']))
                    if abs(times[k]-original['target_ts'])<=35 and times[k]>original['generated']:
                        a=raw-values[k];b=values[seq]-values[k];acc=original_totals[original['horizon']]
                        for j,v in enumerate((1,abs(a),a*a,abs(b),b*b)):acc[j]+=v
                counts['original_rows']+=1;counts['original_rows_needing_repair']+=needed
            saved={r['horizon']:r for r in conn.execute('SELECT * FROM original_scores WHERE model=?',(name,))}
            check(set(saved)==set(original_totals),'Original score coverage mismatch')
            for h,expected in original_totals.items():
                for column,value in zip(('n','sum_abs','sum_sq','base_abs','base_sq'),expected):
                    check(math.isclose(saved[h][column],value,rel_tol=1e-9,abs_tol=1e-7),'Original score calculation mismatch')
            # Task coverage includes all observed gaps, including missing horizons.
            task_keys=set()
            for task in conn.execute('SELECT * FROM repair_tasks WHERE model=?',(name,)):
                for target in json.loads(task['targets']):
                    key=target['key'];task_keys.add(key)
                    output=conn.execute('SELECT issued,horizon FROM repaired WHERE model=? AND key=?',(name,key)).fetchone()
                    unresolved=conn.execute('SELECT reason FROM unresolved WHERE model=? AND key=?',(name,key)).fetchone()
                    check(bool(output)!=bool(unresolved),'Task missing/duplicated resolution')
                    if output:check(output['issued']==task['issue'] and output['horizon']==target['horizon'],'Task output mismatch')
                    if unresolved:
                        end=bisect.bisect_right(times,task['issue'])
                        begin=max(0,end-spec.get('max_train_rows',5000),bisect.bisect_left(times,task['issue']-spec.get('history_hours',336)*3600))
                        check(end-begin<spec.get('burn_in_rows',200),'Task incorrectly declared unrecoverable')
            issue_times=[r[0] for r in conn.execute('SELECT DISTINCT generated FROM forecasts WHERE model=? ORDER BY generated',(name,))]
            expected_gap_keys=set()
            for a,b in zip(issue_times,issue_times[1:]):
                if b-a<=1200:continue
                issue=a+600
                while issue<b-300:
                    expected_gap_keys.update(f'gap:{issue}:{h}' for h in range(1,spec.get('forecast_horizon_steps',12)+1));issue+=600
            check({k for k in task_keys if k.startswith('gap:')}==expected_gap_keys,'Gap plan coverage mismatch')
            for output in conn.execute('SELECT * FROM repaired WHERE model=? ORDER BY issued,horizon',(name,)):
                seq=bisect.bisect_right(times,output['issued'])-1;check(seq>=0,'Output has no past source')
                history=values[max(0,seq-49):seq+1];raw=output['raw_yhat']
                if output['fit_id'] is not None:
                    check(output['key'] in task_keys,'Unplanned reconstructed output')
                    reference,cutoff=fits[output['fit_id']];check(cutoff==output['train_cutoff'] and cutoff<=output['issued'],'Output fit cutoff mismatch')
                    key=(output['fit_id'],output['issued'])
                    if key not in prediction_cache:
                        begin=max(0,seq+1-spec.get('max_train_rows',5000),bisect.bisect_left(times,output['issued']-spec.get('history_hours',336)*3600))
                        prediction_cache[key]=predict_reference(reference,values[begin:seq+1],horizons[key])
                    expected=prediction_cache[key][output['horizon']-1]
                    check(math.isclose(raw,expected,rel_tol=1e-7,abs_tol=1e-7),'Independent forecast mismatch')
                    max_prediction_difference=max(max_prediction_difference,abs(raw-expected))
                elif output['provenance']=='verified_ar_replay':
                    check(ar is not None,'Unbound imported AR replay')
                    original=conn.execute('SELECT * FROM ar.predictions WHERE model=? AND issued_at=? AND horizon=?',(name,output['issued'],output['horizon'])).fetchone()
                    check(original is not None and original['yhat']==raw and original['train_cutoff']==output['train_cutoff'],'AR replay value changed')
                    check(output['key']==f'ar_replay:{output["issued"]}:{output["horizon"]}','AR replay identity mismatch')
                else:
                    check(output['provenance']=='corrected_original','Unknown repair provenance')
                    check(output['key']=='original:'+str(output['original_id']),'Unbound original correction')
                    original=conn.execute('SELECT * FROM forecasts WHERE model=? AND id=?',(name,output['original_id'])).fetchone()
                    check(original is not None and original['yhat']==raw and original['generated']==output['issued'],'Correction does not match original evidence')
                served,reason=reference_policy(target_name,raw,history)
                check(math.isfinite(served) and output['yhat']==served and output['policy']=='physical_output_v2:'+reason,'Output policy mismatch')
                check(output['baseline']==values[seq] and output['train_cutoff']<=output['issued'],'Noncausal baseline/cutoff')
                if output['alignment']=='next_observation':
                    k=seq+output['horizon']
                    actual=values[k] if k<len(values) else None;actual_at=times[k] if k<len(values) else None
                    # Imported replay stops scoring at its original frozen end.
                    if output['provenance']=='verified_ar_replay' and not finalized:
                        actual,actual_at=original['actual'],original['actual_at']
                        if actual_at is not None:check(k<len(values) and times[k]==actual_at and values[k]==actual,'Imported actual differs from raw tape')
                else:
                    i=bisect.bisect_left(times,output['target_ts']);candidates=[k for k in (i-1,i) if 0<=k<len(values)]
                    k=min(candidates,key=lambda k:abs(times[k]-output['target_ts']))
                    available=abs(times[k]-output['target_ts'])<=35 and times[k]>output['issued']
                    actual=values[k] if available else None;actual_at=times[k] if available else None
                check(output['actual']==actual and output['actual_at']==actual_at,'Wrong or fabricated actual')
                if actual_at is not None:check(actual_at>output['issued'],'Actual is not future')
                check(output['target_ts']>output['issued'],'Repaired forecast is late')
                counts['repair_rows']+=1;counts[output['provenance']]+=1;counts['policy:'+reason]+=1
                if actual is None:counts['unscored']+=1
                else:
                    acc=score_groups[(output['provenance'],output['horizon'])]
                    a=served-actual;b=values[seq]-actual;r=raw-actual
                    for j,v in enumerate((1,abs(a),a*a,abs(b),b*b,abs(r))):acc[j]+=v
            if ar and conn.execute('SELECT 1 FROM ar.jobs WHERE model=?',(name,)).fetchone():
                expected=conn.execute('SELECT count(*) FROM ar.predictions WHERE model=?',(name,)).fetchone()[0]
                check(counts['verified_ar_replay']==expected,'Imported AR coverage mismatch')
            scores=[]
            for (provenance,h),(n,a,a2,b,b2,r) in score_groups.items():
                scores.append({'provenance':provenance,'horizon':h,'n':n,'mae':a/n,'rmse':math.sqrt(a2/n),
                    'baseline_mae':b/n,'baseline_rmse':math.sqrt(b2/n),'raw_mae':r/n,'improvement_pct':100*(b-a)/b if b else None})
            report['models'].append({'model':name,'status':'PASS','counts':dict(counts),'independent_fits':len(fits),
                'max_parameter_difference':max_fit_difference,'max_prediction_difference':max_prediction_difference,'scores':scores,
                'unresolved':conn.execute('SELECT count(*) FROM unresolved WHERE model=?',(name,)).fetchone()[0]})
            print(name,'independent audit PASS',flush=True)
        if finalized:
            from aqpy.forecast.repair_export import sha256
            manifest=json.loads((root/'repair-manifest.json').read_text())
            for filename,digest in manifest['files'].items():
                check(sha256(root/filename)==digest,'Export fingerprint mismatch: '+filename)
            for table,order in [('repaired','model,issued,horizon,key'),('unresolved','model,key')]:
                n=0
                with (root/(table+'.csv')).open(newline='') as stream:
                    reader=csv.reader(stream);cursor=conn.execute(f'SELECT * FROM {table} ORDER BY {order}')
                    check(next(reader)==[c[0] for c in cursor.description],'CSV header mismatch')
                    for row in cursor:
                        check(next(reader,None)==['' if v is None else str(v) for v in row],'CSV differs from audited output');n+=1
                    check(next(reader,None) is None and n==manifest['rows'][table],'CSV row count mismatch')
            report['files_sha256']=manifest['files']
        report['finalized']=finalized
        report['status']='PASS'
    except Exception as exc:
        report['failures'].append(str(exc))
    finally:conn.close()
    report['auditor_sha256']=hashlib.sha256(Path(__file__).read_bytes()+Path(__file__).with_name('repair_reference.py').read_bytes()).hexdigest()
    staged=root/'repair-validation.json.partial';staged.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    staged.replace(root/'repair-validation.json')
    return report
