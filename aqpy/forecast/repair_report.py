"""Generate a concise, auditable model-by-model repair disposition."""
import collections
import datetime as dt
import json
import math
from pathlib import Path
import sqlite3


def metrics(rows):
    scored=[r for r in rows if r['actual'] is not None]
    def mae(key):return sum(abs(r[key]-r['actual']) for r in scored)/len(scored) if scored else None
    return {'scored':len(scored),'served_mae':mae('yhat'),'raw_mae':mae('raw_yhat'),'persistence_mae':mae('baseline')}


def build(run_directories,output_directory):
    runs=[];models={}
    for directory in map(Path,run_directories):
        validation=json.loads((directory/'repair-validation.json').read_text())
        if validation.get('status')!='PASS' or not validation.get('finalized'):
            raise ValueError(f'{directory}: finalized independent PASS audit required')
        publication=json.loads((directory/'publication.json').read_text())
        if not publication.get('databases') or any(x['status']!='PASS' for x in publication['databases']):
            raise ValueError(f'{directory}: verified publication required')
        conn=sqlite3.connect(f'file:{directory.resolve()}/inventory.sqlite?mode=ro',uri=True);conn.row_factory=sqlite3.Row
        try:
            config=json.loads(conn.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])
            run={'run':directory.name,'end':config['end'],'forecast_start':config.get('forecast_start'),
                 'auditor_sha256':validation['auditor_sha256'],'models':len(validation['models'])}
            runs.append(run)
            audited={m['model']:m for m in validation['models']}
            for model in conn.execute('SELECT * FROM repair_models ORDER BY model'):
                name=model['model'];spec=json.loads(model['spec']);entry=models.setdefault(name,{
                    'model':name,'database':spec['database'],'source_table':spec['table'],'target':spec['target'],
                    'model_type':spec['model_type'],'snapshot_rows':0,'repaired_rows':0,'replaced_originals':0,
                    'added_rows':0,'unresolved':0,'provenance':collections.Counter(),'runs':[],'score_rows':[]})
                original=conn.execute('SELECT count(*) FROM forecasts WHERE model=?',(name,)).fetchone()[0]
                repair_rows=[dict(r) for r in conn.execute('SELECT * FROM repaired WHERE model=?',(name,))]
                unresolved=conn.execute('SELECT count(*) FROM unresolved WHERE model=?',(name,)).fetchone()[0]
                replaced=len({r['original_id'] for r in repair_rows if r['original_id'] is not None})
                provenance=collections.Counter(r['provenance'].split(':',1)[0] for r in repair_rows)
                entry['snapshot_rows']+=original;entry['repaired_rows']+=len(repair_rows)
                entry['replaced_originals']+=replaced;entry['added_rows']+=len(repair_rows)-replaced
                entry['unresolved']+=unresolved;entry['provenance'].update(provenance)
                entry['runs'].append(directory.name);entry['score_rows'].extend(repair_rows)
                if audited[name]['status']!='PASS':raise ValueError(name+' lacks model PASS')
        finally:conn.close()
    output=[]
    for name in sorted(models):
        item=models[name];item['provenance']=dict(item['provenance']);item['metrics']=metrics(item.pop('score_rows'))
        if item['repaired_rows']:
            item['disposition']='verified repair; unavailable source explicitly recorded' if item['unresolved'] else 'verified repair'
        else:item['disposition']='unrecoverable missing source' if item['unresolved'] else 'valid existing history; no repair needed'
        output.append(item)
    result={'generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'runs':runs,'models':output,
            'definition':'Each repair run passed independent source, coverage, causal-fit, recursive-prediction, actual-alignment, policy, score, export and publication checks.'}
    destination=Path(output_directory);destination.mkdir(parents=True,exist_ok=True)
    (destination/'model-dispositions.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    lines=['# Verified model dispositions','',result['definition'],'',
           '| Model | Source | Snapshot | Repaired | Added | Unresolved | Served / raw / persistence MAE | Disposition |',
           '|---|---|---:|---:|---:|---:|---|---|']
    for item in output:
        score=item['metrics'];values=[score[k] for k in ('served_mae','raw_mae','persistence_mae')]
        quality=' / '.join('n/a' if x is None else f'{x:.4g}' for x in values)+f" (n={score['scored']})"
        lines.append(f"| {item['model']} | {item['database']}.{item['source_table']}.{item['target']} | {item['snapshot_rows']} | {item['repaired_rows']} | {item['added_rows']} | {item['unresolved']} | {quality} | {item['disposition']} |")
    (destination/'MODEL_DISPOSITIONS.md').write_text('\n'.join(lines)+'\n')
    return result
