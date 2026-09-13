"""Publish only independently validated evidence, preserving original forecasts."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3

from psycopg2.extras import execute_values,Json
from aqpy.common.db import connect_db
from aqpy.forecast.repair_export import sha256


def timestamp(value):
    return dt.datetime.fromtimestamp(value,dt.timezone.utc) if value is not None else None


def prediction_row(run_id,spec,row):
    return (run_id,row['model'],row['key'],row['original_id'],timestamp(row['issued']),timestamp(row['target_ts']),
            spec['database'],spec['table'],spec['target'],row['horizon'],row['raw_yhat'],row['yhat'],row['baseline'],
            row['actual'],timestamp(row['actual_at']),timestamp(row['train_cutoff']),row['provenance'],row['policy'],row['alignment'])


def digest_row(digest,row):
    # PostgreSQL stores timestamps with microsecond precision. Normalize both
    # sides identically; this also verifies every individual imported value.
    values=[v.astimezone(dt.timezone.utc).isoformat() if isinstance(v,dt.datetime) else v for v in row]
    digest.update(json.dumps(values,sort_keys=True,allow_nan=False).encode())


def publish(directory,max_rows=1000000):
    import fcntl
    root=Path(directory)
    with (root.parent/'.replay-worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _publish(root,max_rows)


def _publish(root,max_rows):
    validation=json.loads((root/'repair-validation.json').read_text())
    if validation.get('status')!='PASS' or not validation.get('finalized'):
        raise ValueError('A finalized independent PASS audit is required')
    for file,digest in validation['files_sha256'].items():
        if sha256(root/file)!=digest:raise ValueError('Audited evidence changed: '+file)
    evidence=validation['files_sha256']['inventory.sqlite'];run_id=root.name
    c=sqlite3.connect(f'file:{root.resolve()}/inventory.sqlite?mode=ro',uri=True);c.row_factory=sqlite3.Row
    c.execute('PRAGMA cache_size=-4096')
    models={r['model']:json.loads(r['spec']) for r in c.execute('SELECT * FROM repair_models')}
    report={'run_id':run_id,'evidence_sha256':evidence,'databases':[]}
    try:
        for database in sorted({s['database'] for s in models.values()}):
            pg=connect_db(database)
            try:
                with pg.cursor() as cur:
                    cur.execute("SET statement_timeout='30s'");cur.execute("SET lock_timeout='2s'")
                    cur.execute("SET work_mem='4MB'");cur.execute('SET max_parallel_workers_per_gather=0')
                    cur.execute("SELECT pg_try_advisory_lock(hashtext('aqpy_history_repair_publish'))")
                    if not cur.fetchone()[0]:raise RuntimeError('Another publication is active')
                    cur.execute('SELECT evidence_sha256 FROM history_repair.runs WHERE run_id=%s',(run_id,))
                    old=cur.fetchone()
                    if old and old[0]!=evidence:raise ValueError('Run ID already binds different evidence')
                    names=[n for n,s in models.items() if s['database']==database]
                    needed=sum(c.execute('SELECT count(*) FROM repaired WHERE model=?',(n,)).fetchone()[0] for n in names)
                    cur.execute('SELECT count(*) FROM history_repair.predictions WHERE run_id<>%s',(run_id,))
                    if cur.fetchone()[0]+needed>max_rows:raise RuntimeError('Repair row storage budget exceeded')
                    unresolved_needed=sum(c.execute('SELECT count(*) FROM unresolved WHERE model=?',(n,)).fetchone()[0] for n in names)
                    cur.execute('SELECT count(*) FROM history_repair.unresolved WHERE run_id<>%s',(run_id,))
                    if cur.fetchone()[0]+unresolved_needed>max_rows:raise RuntimeError('Unresolved row storage budget exceeded')
                    cur.execute('SELECT count(*) FROM history_repair.runs WHERE run_id<>%s',(run_id,))
                    if cur.fetchone()[0]>=128:raise RuntimeError('Repair run storage budget exceeded')
                    cur.execute("SELECT coalesce(sum(pg_total_relation_size(c.oid)),0) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='history_repair' AND c.relkind='r'")
                    if cur.fetchone()[0]>1024**3:raise RuntimeError('Repair database storage exceeds 1 GiB')
                    cur.execute('INSERT INTO history_repair.runs(run_id,evidence_sha256,validation) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                                (run_id,evidence,Json(validation)))
                pg.commit()
                expected=hashlib.sha256();expected_unresolved=hashlib.sha256();count=unresolved_count=0
                for name in sorted(names):
                    batch=[]
                    for row in c.execute('SELECT * FROM repaired WHERE model=? ORDER BY key',(name,)):
                        record=prediction_row(run_id,models[name],row);digest_row(expected,record);batch.append(record);count+=1
                        if len(batch)>=256:
                            with pg.cursor() as cur:execute_values(cur,'INSERT INTO history_repair.predictions VALUES %s ON CONFLICT DO NOTHING',batch)
                            pg.commit();batch=[]
                    if batch:
                        with pg.cursor() as cur:execute_values(cur,'INSERT INTO history_repair.predictions VALUES %s ON CONFLICT DO NOTHING',batch)
                        pg.commit()
                    batch=[]
                    for row in c.execute('SELECT * FROM unresolved WHERE model=? ORDER BY key',(name,)):
                        original_id=int(row['key'].split(':')[1]) if row['key'].startswith('original:') else None
                        record=(run_id,name,row['key'],original_id,row['reason']);digest_row(expected_unresolved,record)
                        batch.append(record);unresolved_count+=1
                        if len(batch)>=256:
                            with pg.cursor() as cur:execute_values(cur,'INSERT INTO history_repair.unresolved VALUES %s ON CONFLICT DO NOTHING',batch)
                            pg.commit();batch=[]
                    if batch:
                        with pg.cursor() as cur:execute_values(cur,'INSERT INTO history_repair.unresolved VALUES %s ON CONFLICT DO NOTHING',batch)
                        pg.commit()
                actual=hashlib.sha256();actual_unresolved=hashlib.sha256();seen=missing=0
                with pg.cursor(name='verify_repairs') as cur:
                    cur.itersize=256
                    cur.execute('SELECT * FROM history_repair.predictions WHERE run_id=%s ORDER BY model_name COLLATE "C",repair_key COLLATE "C"',(run_id,))
                    for row in cur:digest_row(actual,row);seen+=1
                with pg.cursor(name='verify_unresolved') as cur:
                    cur.itersize=256
                    cur.execute('SELECT * FROM history_repair.unresolved WHERE run_id=%s ORDER BY model_name COLLATE "C",repair_key COLLATE "C"',(run_id,))
                    for row in cur:digest_row(actual_unresolved,row);missing+=1
                if (seen,actual.hexdigest(),missing,actual_unresolved.hexdigest())!=(count,expected.hexdigest(),unresolved_count,expected_unresolved.hexdigest()):
                    raise ValueError('Published rows differ from audited evidence')
                with pg.cursor() as cur:
                    cur.execute('''SELECT count(*) FROM history_repair.predictions a
                        JOIN history_repair.predictions b ON a.original_id=b.original_id AND a.run_id<>b.run_id
                        JOIN history_repair.runs r ON r.run_id=b.run_id
                        WHERE a.run_id=%s AND r.published_at IS NOT NULL''',(run_id,))
                    if cur.fetchone()[0]:raise ValueError('Original rows overlap another published run')
                    cur.execute('UPDATE history_repair.runs SET published_at=coalesce(published_at,now()) WHERE run_id=%s',(run_id,))
                pg.commit()
                report['databases'].append({'database':database,'status':'PASS','rows':count,'unresolved':unresolved_count,
                    'rows_sha256':actual.hexdigest(),'unresolved_sha256':actual_unresolved.hexdigest()})
            finally:pg.close()
    finally:c.close()
    (root/'publication.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
