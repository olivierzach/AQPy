"""Bounded finalization and portable evidence for completed targeted repairs."""
import csv
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path

from aqpy.forecast.repair_inventory import open_inventory


def sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):digest.update(block)
    return digest.hexdigest()


def finalize(directory):
    root=Path(directory)
    with (root.parent/'.replay-worker.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        conn=open_inventory(root)
        try:
            if conn.execute('SELECT count(*) FROM repair_tasks WHERE complete=0').fetchone()[0]:
                raise RuntimeError('Complete all repair tasks before finalizing')
            prior=conn.execute("SELECT value FROM meta WHERE key='repair_finalized'").fetchone()
            if not prior:
                # The original AR tape ended earlier. Score its remaining tails
                # against this separately fingerprinted tape, without refitting.
                enriched=0
                with conn:
                    for row in conn.execute("SELECT model,key,issued,horizon FROM repaired WHERE provenance='verified_ar_replay' AND actual IS NULL").fetchall():
                        source=conn.execute('SELECT source FROM repair_models WHERE model=?',(row['model'],)).fetchone()[0]
                        seq=conn.execute('SELECT max(seq) FROM samples WHERE source=? AND ts<=?',(source,row['issued'])).fetchone()[0]
                        actual=conn.execute('SELECT ts,y FROM samples WHERE source=? AND seq=?',(source,seq+row['horizon'])).fetchone()
                        if actual:
                            conn.execute('UPDATE repaired SET actual=?,actual_at=?,target_ts=? WHERE model=? AND key=?',
                                (actual['y'],actual['ts'],actual['ts'],row['model'],row['key']))
                            enriched+=1
                    info={'at':dt.datetime.now(dt.timezone.utc).isoformat(),'ar_tails_enriched':enriched,
                          'actual_evidence':'fingerprinted inventory samples; original AR replay unchanged'}
                    conn.execute('INSERT INTO meta VALUES (?,?)',('repair_finalized',json.dumps(info,sort_keys=True)))
            else:info=json.loads(prior[0])
            manifest={'finalization':info,'files':{},'rows':{}}
            for table,order in [('repaired','model,issued,horizon,key'),('unresolved','model,key')]:
                cursor=conn.execute(f'SELECT * FROM {table} ORDER BY {order}')
                staged=root/(table+'.csv.partial');n=0
                with staged.open('w',newline='') as stream:
                    writer=csv.writer(stream);writer.writerow([c[0] for c in cursor.description])
                    for row in cursor:writer.writerow(tuple(row));n+=1
                dest=root/(table+'.csv');staged.replace(dest)
                manifest['files'][dest.name]=sha256(dest);manifest['rows'][table]=n
            conn.close();conn=None
            manifest['files']['inventory.sqlite']=sha256(root/'inventory.sqlite')
            staged=root/'repair-manifest.json.partial';staged.write_text(json.dumps(manifest,indent=2)+'\n')
            staged.replace(root/'repair-manifest.json')
            return manifest
        finally:
            if conn is not None:conn.close()
