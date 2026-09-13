"""Bounded, resumable, read-only snapshot for targeted historical repairs."""
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3

from aqpy.common.db import connect_db
from aqpy.forecast.specs import load_model_specs
from aqpy.forecast.output_policy import in_domain


def source_key(spec):
    return '.'.join(spec[k] for k in ('database','table','target'))


def open_inventory(directory):
    conn=sqlite3.connect(str(Path(directory)/'inventory.sqlite'))
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA cache_size=-4096')
    conn.execute('PRAGMA synchronous=FULL')
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
        row=conn.execute("SELECT value FROM meta WHERE key='config'").fetchone()
        if row:
            config=json.loads(row[0]);conn.execute(f"PRAGMA max_page_count={config.get('max_mib',512)*1024**2//4096}")
    return conn


def snapshot(directory, spec_file='configs/model_specs.json', end=None, max_mib=512):
    """Resume at source/model boundaries. Original timestamps/outputs stay intact."""
    specs=load_model_specs(spec_file)
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    local=open_inventory(root)
    local.executescript('''
      CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
      CREATE TABLE IF NOT EXISTS sources(source TEXT PRIMARY KEY,rows INTEGER,first REAL,last REAL,sha256 TEXT);
      CREATE TABLE IF NOT EXISTS samples(source TEXT,seq INTEGER,ts REAL,y REAL,
        PRIMARY KEY(source,seq),UNIQUE(source,ts));
      CREATE TABLE IF NOT EXISTS models(model TEXT PRIMARY KEY,spec TEXT,rows INTEGER,sha256 TEXT);
      CREATE TABLE IF NOT EXISTS forecasts(model TEXT,id INTEGER,generated REAL,target_ts REAL,horizon INTEGER,
        yhat REAL,version TEXT,trained_at REAL,PRIMARY KEY(model,id));
      CREATE INDEX IF NOT EXISTS forecast_time ON forecasts(model,target_ts);
    ''')
    old=local.execute("SELECT value FROM meta WHERE key='config'").fetchone()
    config={'end':(end or dt.datetime.now(dt.timezone.utc)).isoformat(),'max_mib':max_mib,'specs':specs}
    if old:
        config=json.loads(old[0])
        if config['specs']!=specs:raise ValueError('Inventory specifications changed')
    else:
        local.execute('INSERT INTO meta VALUES (?,?)',('config',json.dumps(config,sort_keys=True)));local.commit()
    end=dt.datetime.fromisoformat(config['end'])
    local.execute(f"PRAGMA max_page_count={config['max_mib']*1024**2//4096}")
    def budget():
        if shutil.disk_usage(root).free<3*1024**3:raise RuntimeError('Less than 3 GiB free disk')
        if sum(p.stat().st_size for p in root.rglob('*') if p.is_file())>config['max_mib']*1024**2:
            raise RuntimeError('Inventory disk budget exceeded')
        if sum(p.stat().st_size for p in root.parent.rglob('*') if p.is_file())>2*1024**3:
            raise RuntimeError('Combined replay storage exceeds 2 GiB')
    try:
        for database in sorted({s['database'] for s in specs}):
            pg=connect_db(database);pg.set_session(readonly=True,isolation_level='REPEATABLE READ')
            try:
                with pg.cursor() as cur:
                    cur.execute("SET LOCAL statement_timeout='30s'")
                    cur.execute("SET LOCAL work_mem='4MB'")
                    cur.execute('SET LOCAL max_parallel_workers_per_gather=0')
                    cur.execute('SELECT min(t) FROM pi');first=cur.fetchone()[0]
                for spec in [s for s in specs if s['database']==database]:
                    source=source_key(spec);name=spec['model_name'];budget()
                    if not local.execute('SELECT 1 FROM sources WHERE source=?',(source,)).fetchone():
                        digest=hashlib.sha256();n=0;first_ts=last_ts=None
                        with local,pg.cursor(name='repair_source') as cur:
                            cur.itersize=512
                            cur.execute(f"SELECT {spec['time_col']},{spec['target']} FROM {spec['table']} WHERE {spec['time_col']} >= %s AND {spec['time_col']}<=%s ORDER BY {spec['time_col']}",(first,end))
                            for ts,y in cur:
                                ts=ts.timestamp();y=float(y) if y is not None else None
                                if y is None or not math.isfinite(y):raise ValueError(f'Invalid raw source {source} at {ts}')
                                if last_ts is not None and ts<=last_ts:raise ValueError('Duplicate/unordered raw timestamp')
                                local.execute('INSERT INTO samples VALUES (?,?,?,?)',(source,n,ts,y))
                                digest.update(json.dumps([ts,y],sort_keys=True).encode())
                                if n==0:first_ts=ts
                                last_ts=ts;n+=1
                                if n%512==0:budget()
                            local.execute('INSERT INTO sources VALUES (?,?,?,?,?)',(source,n,first_ts,last_ts,digest.hexdigest()))
                    if local.execute('SELECT 1 FROM models WHERE model=?',(name,)).fetchone():continue
                    digest=hashlib.sha256();n=0
                    with local,pg.cursor(name='repair_forecasts') as cur:
                        cur.itersize=512
                        cur.execute('''SELECT p.id,p.generated_at,p.predicted_for,p.horizon_step,p.yhat,p.model_version,r.trained_at
                          FROM predictions p LEFT JOIN model_registry r ON r.model_name=p.model_name AND r.model_version=p.model_version
                          WHERE p.target=%s AND p.model_name=%s AND p.predicted_for >= %s AND p.predicted_for<=%s
                          ORDER BY p.predicted_for,p.id''',(spec['target'],name,first,end))
                        for pid,generated,target,h,y,version,trained in cur:
                            if y is not None and not math.isfinite(y):y=str(y)
                            row=(name,pid,generated.timestamp(),target.timestamp(),h,y,version,trained.timestamp() if trained else None)
                            local.execute('INSERT INTO forecasts VALUES (?,?,?,?,?,?,?,?)',row)
                            digest.update(json.dumps(row,sort_keys=True).encode());n+=1
                            if n%512==0:budget()
                        local.execute('INSERT INTO models VALUES (?,?,?,?)',(name,json.dumps(spec,sort_keys=True),n,digest.hexdigest()))
                    print(name,n,'forecasts frozen',flush=True)
            finally:pg.close()
        (root/'snapshot-complete').touch()
    finally:local.close()


def analyze(directory):
    """Profile actual trajectories and individual forecast defects without fitting."""
    import bisect
    import collections
    import statistics
    root=Path(directory);conn=open_inventory(root)
    report={'models':[],'note':'Gaps are observed issue gaps; proposed timestamps are reconstructed cadence, not original missing row IDs.'}
    conn.executescript('''CREATE TABLE IF NOT EXISTS defects(model TEXT,id INTEGER,reason TEXT,PRIMARY KEY(model,id,reason));''')
    try:
        conn.execute('DELETE FROM defects')
        for model in conn.execute('SELECT * FROM models ORDER BY model').fetchall():
            spec=json.loads(model['spec']);name=model['model'];source=source_key(spec)
            raw=conn.execute('SELECT ts,y FROM samples WHERE source=? ORDER BY ts',(source,)).fetchall()
            times=[r['ts'] for r in raw];values=[r['y'] for r in raw]
            issues=set();metrics=collections.defaultdict(lambda:[0,0.,0.,0.,0.]);counts=collections.Counter()
            finite_values=[];worst=[]
            for p in conn.execute('SELECT * FROM forecasts WHERE model=? ORDER BY target_ts',(name,)):
                counts['rows']+=1;issues.add(p['generated']);reasons=[];y=p['yhat']
                finite=y is not None and isinstance(y,(float,int)) and math.isfinite(y)
                if not finite:reasons.append('nonfinite')
                elif not in_domain(spec['target'],y):reasons.append('physical_domain')
                if p['generated']>=p['target_ts']:reasons.append('late')
                if p['trained_at'] is None:reasons.append('missing_registry')
                elif p['trained_at']>p['generated']:reasons.append('future_model')
                for reason in reasons:
                    counts[reason]+=1;conn.execute('INSERT INTO defects VALUES (?,?,?)',(name,p['id'],reason))
                if finite:finite_values.append(y)
                i=bisect.bisect_left(times,p['target_ts']);cand=[k for k in (i-1,i) if 0<=k<len(times)]
                k=min(cand,key=lambda k:abs(times[k]-p['target_ts']))
                baseline=bisect.bisect_right(times,p['generated'])-1
                if not finite or 'late' in reasons or 'future_model' in reasons or 'missing_registry' in reasons:continue
                if abs(times[k]-p['target_ts'])>35 or times[k]<=p['generated'] or baseline<0:
                    counts['unmatched']+=1;continue
                a=y-values[k];b=values[baseline]-values[k]
                for key in ('all',str(p['horizon'])):
                    acc=metrics[key]
                    for j,v in enumerate((1,abs(a),a*a,abs(b),b*b)):acc[j]+=v
                # Keep only a few worst observed errors, including nearby source context.
                candidate={'absolute_error':abs(a),'id':p['id'],'issued':p['generated'],'target':p['target_ts'],
                           'prediction':y,'actual':values[k],'baseline':values[baseline],'horizon':p['horizon']}
                if len(worst)<5 or abs(a)>worst[-1]['absolute_error']:
                    worst.append(candidate);worst.sort(key=lambda r:r['absolute_error'],reverse=True);del worst[5:]
            issues=sorted(issues)
            gaps=[{'start':a,'end':b,'seconds':b-a} for a,b in zip(issues,issues[1:]) if b-a>1200]
            summaries={}
            for key,(n,a,a2,b,b2) in metrics.items():
                summaries[key]={'n':n,'mae':a/n,'baseline_mae':b/n,'rmse':math.sqrt(a2/n),
                                'baseline_rmse':math.sqrt(b2/n),'improvement_pct':100*(b-a)/b if b else None}
            item={'model':name,'spec':spec,'counts':dict(counts),'issues':len(issues),'first_issue':issues[0] if issues else None,
                  'last_issue':issues[-1] if issues else None,'gaps':gaps,
                  'raw':{'rows':len(raw),'first':times[0],'last':times[-1],'min':min(values),'max':max(values),
                         'median':statistics.median(values),'distinct':len(set(values)),
                         'physical_invalid':sum(not in_domain(spec['target'],v) for v in values),
                         'max_gap_seconds':max(b-a for a,b in zip(times,times[1:]))},
                  'forecast_min':min(finite_values) if finite_values else None,'forecast_max':max(finite_values) if finite_values else None,
                  'metrics':summaries,'worst_errors':worst}
            report['models'].append(item);conn.commit()
            (root/'inventory-profile.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
            print(name,dict(counts),'gaps',len(gaps),flush=True)
    finally:conn.close()
    return report
