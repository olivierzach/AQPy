"""Target only demonstrated history defects; keep original evidence immutable."""
import bisect
import collections
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

from aqpy.common.pm_index import particle_index,DEFINITION
from aqpy.forecast.output_policy import correct_output,POLICY_VERSION
from aqpy.forecast.repair_inventory import open_inventory,source_key


def schema(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS repair_models(model TEXT PRIMARY KEY,spec TEXT,source TEXT,
        last_fit_seq INTEGER DEFAULT -1,fit_id INTEGER,complete INTEGER DEFAULT 0);
      CREATE TABLE IF NOT EXISTS repair_tasks(model TEXT,issue REAL,targets TEXT,reason TEXT,
        complete INTEGER DEFAULT 0,PRIMARY KEY(model,issue));
      CREATE TABLE IF NOT EXISTS repair_fits(id INTEGER PRIMARY KEY,model TEXT,issue REAL,
        cutoff REAL,last_seq INTEGER,seed INTEGER,artifact TEXT);
      CREATE TABLE IF NOT EXISTS repaired(model TEXT,key TEXT,issued REAL,target_ts REAL,horizon INTEGER,
        raw_yhat REAL,yhat REAL,baseline REAL,actual REAL,actual_at REAL,train_cutoff REAL,
        provenance TEXT,policy TEXT,original_id INTEGER,fit_id INTEGER,alignment TEXT,
        PRIMARY KEY(model,key));
      CREATE INDEX IF NOT EXISTS repair_output_time ON repaired(model,target_ts);
      CREATE TABLE IF NOT EXISTS unresolved(model TEXT,key TEXT,reason TEXT,PRIMARY KEY(model,key));
      CREATE TABLE IF NOT EXISTS original_scores(model TEXT,horizon INTEGER,n INTEGER,
        sum_abs REAL,sum_sq REAL,base_abs REAL,base_sq REAL,PRIMARY KEY(model,horizon));
    ''')


def implementation_hash():
    from aqpy.forecast.replay import code_hash
    return hashlib.sha256((code_hash()+Path(__file__).read_text()+
        Path(__file__).with_name('output_policy.py').read_text()+
        Path(__file__).parents[1].joinpath('common/pm_index.py').read_text()).encode()).hexdigest()


def load_source(conn,source):
    rows=conn.execute('SELECT ts,y FROM samples WHERE source=? ORDER BY ts',(source,)).fetchall()
    return [r['ts'] for r in rows],[r['y'] for r in rows]


def observed(times,values,issue):
    seq=bisect.bisect_right(times,issue)-1
    return seq,values[max(0,seq-49):seq+1]


def matched_actual(times,values,issue,target):
    i=bisect.bisect_left(times,target)
    candidates=[k for k in (i-1,i) if 0<=k<len(times)]
    if not candidates:return None,None
    k=min(candidates,key=lambda k:abs(times[k]-target))
    if abs(times[k]-target)>35 or times[k]<=issue:return None,None
    return values[k],times[k]


def add_task(conn,name,issue,target,reason):
    prior=conn.execute('SELECT targets,reason FROM repair_tasks WHERE model=? AND issue=?',(name,issue)).fetchone()
    targets=json.loads(prior['targets']) if prior else []
    if target not in targets:targets.append(target)
    reason=','.join(sorted(set((prior['reason'].split(',') if prior else [])+[reason])))
    conn.execute('INSERT OR REPLACE INTO repair_tasks(model,issue,targets,reason) VALUES (?,?,?,?)',
                 (name,issue,json.dumps(sorted(targets,key=lambda t:(t['horizon'],t['key'])),sort_keys=True),reason))


def changed_target(conn,name,original_id,spec):
    """Use per-forecast provenance across a target-definition deployment."""
    if spec['target']!='aqi_pm':return False
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='forecast_sources'").fetchone():
        row=conn.execute('SELECT source_table FROM forecast_sources WHERE model=? AND id=?',(name,original_id)).fetchone()
        if row is None:raise ValueError('Missing frozen forecast source provenance')
        table=row[0]
    else:
        table=json.loads(conn.execute('SELECT spec FROM models WHERE model=?',(name,)).fetchone()[0])['table']
    return table!='pms_aqi_v2'


def put_output(conn,name,key,issue,target,h,raw,history,actual,actual_at,cutoff,
               provenance,original_id=None,fit_id=None,alignment='nearest_35s',target_name=None):
    if target_name is None:
        target_name=json.loads(conn.execute('SELECT spec FROM repair_models WHERE model=?',(name,)).fetchone()[0])['target']
    value,reason=correct_output(target_name,raw,history[-1],history)
    conn.execute('INSERT INTO repaired VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (name,key,issue,target,h,float(raw),value,float(history[-1]),actual,actual_at,cutoff,
         provenance,POLICY_VERSION+':'+reason,original_id,fit_id,alignment))


def prepare(directory,ar_replay=None):
    root=Path(directory);conn=open_inventory(root);schema(conn)
    if conn.execute("SELECT 1 FROM meta WHERE key='repair_prepared'").fetchone():
        conn.close();return
    if not (root/'snapshot-complete').exists():raise RuntimeError('Complete the source snapshot first')
    profile=json.loads((root/'inventory-profile.json').read_text())
    old_code=conn.execute("SELECT value FROM meta WHERE key='repair_code'").fetchone()
    if old_code and old_code[0]!=implementation_hash():raise RuntimeError('Repair code changed during preparation')
    conn.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('repair_code',implementation_hash()));conn.commit()
    replay=None
    if ar_replay:
        source_root=Path(ar_replay)
        if not (source_root/'validated').exists():raise RuntimeError('AR replay must be validated')
        replay=sqlite3.connect(f'file:{source_root}/replay.sqlite?mode=ro',uri=True);replay.row_factory=sqlite3.Row
        conn.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('ar_replay_path',str(source_root.resolve())))
        conn.execute('INSERT OR IGNORE INTO meta VALUES (?,?)',('ar_replay_validation_sha256',hashlib.sha256((source_root/'validation.json').read_bytes()).hexdigest()))
        conn.commit()
    try:
        # Corrected target derived only from the frozen raw particle measurements.
        new_source='pms.pms_aqi_v2.aqi_pm'
        needs_index=any(item['spec']['target']=='aqi_pm' for item in profile['models'])
        if needs_index and not conn.execute('SELECT 1 FROM sources WHERE source=?',(new_source,)).fetchone():
            if any(not conn.execute('SELECT 1 FROM sources WHERE source=?',(source,)).fetchone()
                   for source in ('pms.pi.pm100_st','pms.pi.pm25_st')):
                raise ValueError('Corrected index requires frozen PM2.5 and PM10 sensor sources')
            with conn:
                digest=hashlib.sha256();n=0;first=last=None
                for row in conn.execute('''SELECT a.seq,a.ts,a.y,b.y FROM samples a JOIN samples b ON b.source=? AND b.ts=a.ts
                    WHERE a.source=? ORDER BY a.seq''',('pms.pi.pm100_st','pms.pi.pm25_st')):
                    seq,ts,p25,p10=row;y=float(particle_index(p25,p10))
                    conn.execute('INSERT INTO samples VALUES (?,?,?,?)',(new_source,n,ts,y))
                    digest.update(json.dumps([ts,y],sort_keys=True).encode());n+=1
                    if first is None:first=ts
                    last=ts
                conn.execute('INSERT INTO sources VALUES (?,?,?,?,?)',(new_source,n,first,last,digest.hexdigest()))
                conn.execute('INSERT INTO meta VALUES (?,?)',('derived_target_definition',DEFINITION))
        for item in profile['models']:
            name=item['model']
            if conn.execute('SELECT 1 FROM repair_models WHERE model=?',(name,)).fetchone():continue
            spec=dict(item['spec']);is_aqi=spec['target']=='aqi_pm'
            if is_aqi:spec['table']='pms_aqi_v2'
            source=source_key(spec);times,values=load_source(conn,source)
            original_metrics=collections.defaultdict(lambda:[0,0.,0.,0.,0.])
            with conn:
                conn.execute('INSERT INTO repair_models(model,spec,source) VALUES (?,?,?)',(name,json.dumps(spec,sort_keys=True),source))
                for p in conn.execute('SELECT * FROM forecasts WHERE model=? ORDER BY generated,target_ts',(name,)):
                    seq,history=observed(times,values,p['generated'])
                    key='original:'+str(p['id'])
                    if not history:
                        conn.execute('INSERT INTO unresolved VALUES (?,?,?)',(name,key,'no source before issuance'));continue
                    invalid=p['yhat'] is None or not isinstance(p['yhat'],(float,int)) or not math.isfinite(p['yhat'])
                    late=p['generated']>=p['target_ts']
                    bad_model=p['trained_at'] is None or p['trained_at']>p['generated']
                    target_changed=changed_target(conn,name,p['id'],spec)
                    if target_changed or invalid or late or bad_model:
                        # Late rows reconstruct from their input-time origin, never after their target.
                        issue=min(p['generated'],p['target_ts']-60*p['horizon']) if late else p['generated']
                        reason='corrected_target' if target_changed else 'late' if late else 'invalid_model' if bad_model else 'nonfinite'
                        add_task(conn,name,issue,{'key':key,'horizon':p['horizon'],'target_ts':p['target_ts'],'original_id':p['id']},reason)
                        continue
                    actual,actual_at=matched_actual(times,values,p['generated'],p['target_ts'])
                    served,reason=correct_output(spec['target'],p['yhat'],history[-1],history)
                    if reason!='unchanged':
                        put_output(conn,name,key,p['generated'],p['target_ts'],p['horizon'],p['yhat'],history,
                                   actual,actual_at,p['trained_at'],'corrected_original',p['id'],target_name=spec['target'])
                    elif actual is not None:
                        a=p['yhat']-actual;b=history[-1]-actual;acc=original_metrics[p['horizon']]
                        for i,v in enumerate((1,abs(a),a*a,abs(b),b*b)):acc[i]+=v
                for h,acc in original_metrics.items():conn.execute('INSERT INTO original_scores VALUES (?,?,?,?,?,?,?)',(name,h,*acc))
                for gap in item['gaps']:
                    issue=gap['start']+600
                    while issue<gap['end']-300:
                        for h in range(1,spec.get('forecast_horizon_steps',12)+1):
                            add_task(conn,name,issue,{'key':f'gap:{issue}:{h}','horizon':h,'original_id':None},'missing_issue')
                        issue+=600
                if replay and replay.execute('SELECT 1 FROM jobs WHERE model=?',(name,)).fetchone():
                    for p in replay.execute('SELECT * FROM predictions WHERE model=? ORDER BY issued_at,horizon',(name,)):
                        seq,history=observed(times,values,p['issued_at'])
                        target=p['actual_at'] if p['actual_at'] is not None else max(p['issued_at']+1,times[seq]+p['horizon']*60)
                        key=f'ar_replay:{p["issued_at"]}:{p["horizon"]}'
                        put_output(conn,name,key,p['issued_at'],target,p['horizon'],p['yhat'],history,p['actual'],p['actual_at'],
                                   p['train_cutoff'],'verified_ar_replay',alignment='next_observation',target_name=spec['target'])
            print(name,'repair plan prepared',flush=True)
        conn.execute('INSERT INTO meta VALUES (?,?)',('repair_prepared','true'));conn.commit()
        write_status(root,conn)
    finally:
        if replay:replay.close()
        conn.close()


def write_status(root,conn):
    models=[]
    for r in conn.execute('SELECT model FROM repair_models ORDER BY model'):
        name=r[0]
        total,done=conn.execute('SELECT count(*),coalesce(sum(complete),0) FROM repair_tasks WHERE model=?',(name,)).fetchone()
        output=conn.execute('SELECT count(*) FROM repaired WHERE model=?',(name,)).fetchone()[0]
        unresolved=conn.execute('SELECT count(*) FROM unresolved WHERE model=?',(name,)).fetchone()[0]
        models.append({'model':name,'tasks':total,'completed_tasks':done,'repair_rows':output,'unresolved':unresolved})
    result={'complete':all(m['tasks']==m['completed_tasks'] for m in models),'models':models}
    (root/'repair-status.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def run(directory,seconds=45,check_resources=True):
    import fcntl
    from aqpy.forecast.replay import fit,predict,pause_reason
    root=Path(directory)
    with (root.parent/'.replay-worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        conn=open_inventory(root)
        try:
            if conn.execute("SELECT value FROM meta WHERE key='repair_code'").fetchone()[0]!=implementation_hash():
                raise RuntimeError('Repair implementation changed; use pinned code')
            if not conn.execute("SELECT 1 FROM meta WHERE key='repair_prepared'").fetchone():raise RuntimeError('Prepare repairs first')
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                task=conn.execute('SELECT * FROM repair_tasks WHERE complete=0 ORDER BY issue,model LIMIT 1').fetchone()
                if task is None:
                    (root/'repairs-complete').touch();break
                if check_resources:
                    reason=pause_reason(root,1024**3)
                    if reason:print('Repair paused:',reason,flush=True);break
                job=conn.execute('SELECT * FROM repair_models WHERE model=?',(task['model'],)).fetchone()
                spec=json.loads(job['spec']);name=job['model'];issue=task['issue']
                rows=conn.execute('''SELECT seq,ts,y FROM samples WHERE source=? AND ts<=? AND ts>=?
                    ORDER BY ts DESC LIMIT ?''',(job['source'],issue,issue-spec.get('history_hours',336)*3600,spec.get('max_train_rows',5000))).fetchall()[::-1]
                targets=json.loads(task['targets'])
                with conn:
                    if len(rows)<spec.get('burn_in_rows',200):
                        for t in targets:conn.execute('INSERT OR REPLACE INTO unresolved VALUES (?,?,?)',(name,t['key'],'insufficient historical warm-up'))
                    else:
                        seq=rows[-1]['seq'];values=[r['y'] for r in rows]
                        fit_id=job['fit_id']
                        if fit_id is None or seq-job['last_fit_seq']>=spec.get('min_new_rows',30):
                            seed=spec.get('random_seed',42)+seq
                            artifact=fit(spec,values,seed);cutoff=rows[-1]['ts']
                            cur=conn.execute('INSERT INTO repair_fits(model,issue,cutoff,last_seq,seed,artifact) VALUES (?,?,?,?,?,?)',
                                (name,issue,cutoff,seq,seed,json.dumps(artifact,sort_keys=True,allow_nan=False)))
                            fit_id=cur.lastrowid
                            conn.execute('UPDATE repair_models SET last_fit_seq=?,fit_id=? WHERE model=?',(seq,fit_id,name))
                        else:
                            fitted=conn.execute('SELECT * FROM repair_fits WHERE id=?',(fit_id,)).fetchone()
                            artifact=json.loads(fitted['artifact']);cutoff=fitted['cutoff']
                        preds=predict(artifact,values,max(t['horizon'] for t in targets))
                        for t in targets:
                            h=t['horizon']
                            if 'target_ts' in t:
                                target=t['target_ts']
                                actual_row=conn.execute('''SELECT ts,y FROM samples WHERE source=? AND ts BETWEEN ? AND ? AND ts>?
                                    ORDER BY abs(ts-?) LIMIT 1''',(job['source'],target-35,target+35,issue,target)).fetchone()
                                actual=actual_row['y'] if actual_row else None;actual_at=actual_row['ts'] if actual_row else None
                                alignment='nearest_35s'
                            else:
                                actual_row=conn.execute('SELECT ts,y FROM samples WHERE source=? AND seq=?',(job['source'],seq+h)).fetchone()
                                actual=actual_row['y'] if actual_row else None;actual_at=actual_row['ts'] if actual_row else None
                                target=actual_at if actual_at is not None else max(issue+1,rows[-1]['ts']+h*60)
                                alignment='next_observation'
                            put_output(conn,name,t['key'],issue,target,h,preds[h-1],values[-50:],actual,actual_at,cutoff,
                                'targeted_reconstruction:'+task['reason'],t.get('original_id'),fit_id,alignment,target_name=spec['target'])
                    conn.execute('UPDATE repair_tasks SET complete=1 WHERE model=? AND issue=?',(name,issue))
            result=write_status(root,conn);print(json.dumps(result),flush=True);return result
        finally:conn.close()
