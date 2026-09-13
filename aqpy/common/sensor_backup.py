"""Bounded compressed daily raw snapshots, readable without PostgreSQL tooling."""
import datetime as dt
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil

from aqpy.common.db import connect_db


def rotate(directory, keep_days, max_bytes, today=None, protected=()):
    if keep_days <= 0 or max_bytes <= 0:
        raise ValueError('Backup bounds must be positive')
    directory=Path(directory);today=today or dt.datetime.now(dt.timezone.utc).date()
    files=sorted(directory.glob('*.jsonl.gz'),key=lambda p:(p.name.split('-',1)[1],p.name))
    deleted=[]
    for file in list(files):
        day=dt.date.fromisoformat(file.name.split('-',1)[1].removesuffix('.jsonl.gz'))
        if day < today-dt.timedelta(days=keep_days-1) and file.name not in protected:
            file.unlink();files.remove(file);deleted.append(file.name)
    size=sum(f.stat().st_size for f in directory.iterdir() if f.is_file())
    for file in files:
        if size<=max_bytes:break
        if file.name in protected:continue
        size-=file.stat().st_size;file.unlink();deleted.append(file.name)
    if size>max_bytes:
        raise RuntimeError('Backup disk budget too small for current partition')
    return deleted


def encode_value(value):
    # Preserve non-finite raw evidence explicitly, rather than emit invalid JSON.
    if isinstance(value,float) and not math.isfinite(value):return str(value)
    return value.isoformat() if hasattr(value,'isoformat') else value


def backup(directory, keep_days=365, max_bytes=512*1024**2, databases=('bme','pms')):
    import fcntl
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with (directory/'backup.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        now=dt.datetime.now(dt.timezone.utc);today=now.date()
        rotate(directory,keep_days,max_bytes,today)
        catalog_path=directory/'catalog.json'
        catalog=json.loads(catalog_path.read_text()) if catalog_path.exists() else {}
        for database in databases:
            # Prevent database names escaping partition paths.
            if database not in ('bme','pms'):raise ValueError('Backup supports the configured bme/pms raw stores')
            conn=connect_db(database)
            try:
                conn.set_session(readonly=True,isolation_level='REPEATABLE READ')
                with conn.cursor() as cur:
                    cur.execute("SET LOCAL work_mem='4MB'")
                    cur.execute("SET LOCAL statement_timeout='30s'")
                    cur.execute('SET LOCAL max_parallel_workers_per_gather=0')
                    cur.execute('SELECT min(t),max(t) FROM pi')
                    first,last=cur.fetchone()
                if first is None:raise RuntimeError(f'{database}: no raw readings to back up')
                day=max(first.astimezone(dt.timezone.utc).date(),today-dt.timedelta(days=keep_days-1))
                while day<=min(today,last.astimezone(dt.timezone.utc).date()):
                    name=f'{database}-{day.isoformat()}.jsonl.gz';target=directory/name
                    # Closed days already copied are immutable; refresh yesterday/current day.
                    if target.exists() and name in catalog and day < today-dt.timedelta(days=1):
                        day+=dt.timedelta(days=1);continue
                    start=dt.datetime.combine(day,dt.time.min,dt.timezone.utc)
                    end=min(start+dt.timedelta(days=1),now)
                    staging=directory/(name+'.partial');digest=hashlib.sha256();count=0
                    try:
                        with conn.cursor(name='raw_backup') as cur:
                            cur.itersize=512
                            cur.execute('SELECT * FROM pi WHERE t >= %s AND t < %s ORDER BY t',(start,end))
                            # Named cursors expose description after fetching their first batch.
                            batch=cur.fetchmany(512)
                            columns=[x[0] for x in cur.description]
                            with staging.open('wb') as raw:
                                with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0) as output:
                                    header=json.dumps({'format':1,'database':database,'table':'pi','columns':columns,
                                        'start':start.isoformat(),'end':end.isoformat()})+'\n'
                                    output.write(header.encode());digest.update(header.encode())
                                    while batch:
                                        for row in batch:
                                            line=(json.dumps([encode_value(v) for v in row],allow_nan=False)+'\n').encode()
                                            output.write(line);digest.update(line);count+=1
                                        output.flush();raw.flush()
                                        rotate(directory,keep_days,max_bytes,today,protected=(name,))
                                        if shutil.disk_usage(directory).free < 3*1024**3:
                                            raise RuntimeError('Backup paused: free disk below 3 GiB')
                                        batch=cur.fetchmany(512)
                                raw.flush();os.fsync(raw.fileno())
                        os.replace(staging,target)
                    finally:
                        staging.unlink(missing_ok=True)
                    catalog[name]={'rows':count,'uncompressed_sha256':digest.hexdigest(),
                        'bytes':target.stat().st_size,'snapshot_at':now.isoformat()}
                    rotate(directory,keep_days,max_bytes,today,protected=(name,))
                    print('Saved raw partition:',name,count,'rows',flush=True)
                    day+=dt.timedelta(days=1)
            finally:
                conn.close()
        catalog={k:v for k,v in catalog.items() if (directory/k).exists()}
        staged=catalog_path.with_suffix('.tmp');staged.write_text(json.dumps(catalog,indent=2)+'\n');os.replace(staged,catalog_path)
        result={'status':'ok','completed_at':now.isoformat(),'partitions':len(catalog),
                'rows':sum(v['rows'] for v in catalog.values()),'compressed_bytes':sum(v['bytes'] for v in catalog.values()),
                'keep_days':keep_days,'max_bytes':max_bytes}
        (directory/'status.json').write_text(json.dumps(result,indent=2)+'\n')
        # Metadata is bounded by the finite partition count. Never hide a budget violation.
        if sum(p.stat().st_size for p in directory.iterdir() if p.is_file()) > max_bytes:
            raise RuntimeError('Backup metadata exceeds disk budget; increase the configured limit')
        return result
