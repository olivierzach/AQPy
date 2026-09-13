"""Streaming, model-independent audit of a completed replay and its scores."""
import datetime as dt
import csv
import hashlib
import json
import math
import os
import sqlite3
from pathlib import Path


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def validate(run_dir, scores=None):
    """Check provenance, full schedule, causal alignment and independently summed scores.

    Does not refit models or claim to recover their historical live parameters.
    Memory is bounded by model/horizon counts, independent of history length.
    Caller must exclude concurrent writers (the replay worker lock does this).
    """
    root = Path(run_dir)
    report = {'status': 'FAIL', 'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
              'scope': 'source integrity, schedule, causal alignment, finite values, scores; no model refits',
              'models': [], 'failures': []}
    conn = sqlite3.connect(f'file:{root.resolve()}/replay.sqlite?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA cache_size=-4096')
    def check(condition, message):
        if not condition:
            raise ValueError(message)
    try:
        check(conn.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'SQLite integrity')
        config = json.loads(conn.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])
        report['configuration'] = config
        check(config['interval'] > 0, 'Invalid interval')
        jobs = list(conn.execute('SELECT * FROM jobs ORDER BY model'))
        check(bool(jobs), 'No model jobs')
        expected_scores = {}
        for job in jobs:
            name = job['model']; spec = json.loads(job['spec'])
            check(job['completed'], f'{name}: replay is incomplete')
            manifest = json.loads(conn.execute('SELECT value FROM meta WHERE key=?', ('tape:'+name,)).fetchone()[0])
            digest = hashlib.sha256(); previous = first = warmup = None; count = 0; largest_gap = 0.
            for row in conn.execute('SELECT seq,ts,y FROM samples WHERE model=? ORDER BY seq', (name,)):
                seq, ts, y = row
                check(seq == count and math.isfinite(ts) and math.isfinite(y), f'{name}: invalid source row')
                check(previous is None or ts > previous, f'{name}: unordered source')
                if previous is not None: largest_gap = max(largest_gap, ts-previous)
                if first is None: first = ts
                previous = ts; count += 1
                if count == spec.get('burn_in_rows', 200): warmup = ts
                digest.update(json.dumps([ts,y], sort_keys=True, allow_nan=False).encode())
            check(warmup is not None and count == manifest['rows'] and first == manifest['first']
                  and previous == manifest['last'] and digest.hexdigest() == manifest['sha256'], f'{name}: source hash/coverage mismatch')
            for key, actual, compare in [('start',first,lambda a,b:a>=b),('end',previous,lambda a,b:a<=b)]:
                if config.get(key):
                    check(compare(actual,dt.datetime.fromisoformat(config[key]).timestamp()), f'{name}: source outside requested {key}')
            issue = first + math.ceil((warmup-first)/config['interval'])*config['interval']
            cursor = iter(conn.execute('SELECT * FROM predictions WHERE model=? ORDER BY issued_at,horizon', (name,)))
            issues = fits = skipped = scored = tail = 0
            last_fit = -1; cutoff = None
            while issue <= previous:
                latest = conn.execute('SELECT seq,ts,y FROM samples WHERE model=? AND ts<=? ORDER BY ts DESC LIMIT 1', (name,issue)).fetchone()
                available = conn.execute('SELECT count(*) FROM (SELECT 1 FROM samples WHERE model=? AND ts<=? AND ts>=? ORDER BY ts DESC LIMIT ?)',
                    (name,issue,issue-spec.get('history_hours',336)*3600,spec.get('burn_in_rows',200))).fetchone()[0]
                if available < spec.get('burn_in_rows',200):
                    skipped += 1; issue += config['interval']; continue
                if last_fit < 0 or latest['seq']-last_fit >= spec.get('min_new_rows',30):
                    fits += 1; last_fit = latest['seq']; cutoff = latest['ts']
                for horizon in range(1,spec.get('forecast_horizon_steps',12)+1):
                    p = next(cursor, None)
                    check(p is not None and p['issued_at'] == issue and p['horizon'] == horizon, f'{name}: missing/extra forecast or horizon')
                    check(p['train_cutoff'] == cutoff and cutoff <= issue and p['target_seq'] == latest['seq']+horizon,
                          f'{name}: causal training/target alignment')
                    check(math.isfinite(p['yhat']) and p['baseline'] == latest['y'], f'{name}: nonfinite forecast or incorrect baseline')
                    target = conn.execute('SELECT ts,y FROM samples WHERE model=? AND seq=?', (name,p['target_seq'])).fetchone()
                    if target is None:
                        check(p['actual'] is None and p['actual_at'] is None, f'{name}: fabricated tail actual')
                        tail += 1
                    else:
                        check(p['actual'] == target['y'] and p['actual_at'] == target['ts'] and target['ts'] > issue, f'{name}: wrong/missing actual')
                        a = p['yhat']-target['y']; b = p['baseline']-target['y']
                        totals = expected_scores.setdefault((name,horizon),[0,0.,0.,0.,0.])
                        for i,v in enumerate([1,abs(a),a*a,abs(b),b*b]): totals[i] += v
                        check(all(math.isfinite(v) for v in totals), f'{name}: nonfinite score')
                        scored += 1
                issues += 1; issue += config['interval']
            check(next(cursor,None) is None, f'{name}: extra predictions')
            check(issues == job['issues'] and fits == job['fits'] and issue == job['next_issue'], f'{name}: checkpoint/count mismatch')
            check(last_fit == job['last_train_seq'] and cutoff == job['train_cutoff'], f'{name}: final training checkpoint mismatch')
            report['models'].append({'model': name, 'specification': spec, 'source': manifest,
                'largest_source_gap_seconds': largest_gap, 'warmup_rows': spec.get('burn_in_rows',200),
                'skipped_ticks_insufficient_history': skipped, 'issues': issues, 'fits': fits,
                'predictions': scored+tail, 'scored': scored, 'unavailable_tail': tail})
        check(conn.execute('SELECT count(*) FROM predictions WHERE model NOT IN (SELECT model FROM jobs)').fetchone()[0] == 0, 'Unknown prediction model')
        if scores is None:
            scores = json.loads((root/'scores.json').read_text())
        check(len(scores) == len(expected_scores), 'Score group count mismatch')
        seen = set()
        for record in scores:
            key = (record['model'],record['horizon'])
            check(key in expected_scores and key not in seen, 'Unexpected/duplicate score group'); seen.add(key)
            n,a,a2,b,b2 = expected_scores[key]
            expected = {'n': n, 'mae': a/n, 'rmse': math.sqrt(a2/n), 'baseline_mae': b/n, 'baseline_rmse': math.sqrt(b2/n),
                        'mae_improvement_pct': 100*(b-a)/b if b else None}
            for field,value in expected.items():
                actual = record[field]
                check(actual is None if value is None else actual is not None and math.isfinite(actual) and math.isclose(actual,value,rel_tol=1e-9,abs_tol=1e-10),
                      f'{key}: score mismatch: {field}')
        if (root/'predictions.csv').exists():
            with (root/'predictions.csv').open(newline='') as stream:
                reader = csv.reader(stream)
                cursor = conn.execute('SELECT * FROM predictions ORDER BY model,issued_at,horizon')
                check(next(reader,None) == [c[0] for c in cursor.description], 'CSV header mismatch')
                for row in cursor:
                    check(next(reader,None) == ['' if v is None else str(v) for v in row], 'CSV prediction mismatch')
                check(next(reader,None) is None, 'Extra CSV rows')
        report['status'] = 'PASS'
    except (ValueError, TypeError, KeyError, IndexError, sqlite3.Error, OSError) as exc:
        report['failures'].append(str(exc))
    finally:
        conn.close()
    report['files_sha256'] = {name: digest_file(root/name) for name in ['replay.sqlite','scores.json','predictions.csv'] if (root/name).exists()}
    staging = root/'validation.json.partial'
    staging.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    os.replace(staging,root/'validation.json')
    return report
