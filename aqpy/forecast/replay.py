"""Isolated, bounded chronological replay. Never writes to production databases."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

import numpy as np

from aqpy.forecast.validation import require_finite

VERSION = 1
ROOT_BUDGET = 2*1024**3


def storage_bytes(directory):
    return sum(p.stat().st_size for p in Path(directory).rglob('*') if p.is_file())
FAMILIES = {'adaptive_ar', 'nn_mlp', 'rnn_lite_gru'}


def dumps(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def open_run(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA cache_size=-4096')
    conn.execute('PRAGMA synchronous=FULL')
    return conn


def schema(conn):
    conn.executescript('''
    CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE samples (model TEXT, seq INTEGER, ts REAL, y REAL NOT NULL,
      PRIMARY KEY(model,seq), UNIQUE(model,ts));
    CREATE TABLE jobs (model TEXT PRIMARY KEY, spec TEXT, next_issue REAL,
      last_train_seq INTEGER DEFAULT -1, train_cutoff REAL, artifact TEXT,
      completed INTEGER DEFAULT 0, issues INTEGER DEFAULT 0, fits INTEGER DEFAULT 0);
    CREATE TABLE predictions (model TEXT, issued_at REAL, horizon INTEGER,
      target_seq INTEGER, train_cutoff REAL NOT NULL, yhat REAL NOT NULL,
      baseline REAL NOT NULL, actual REAL, actual_at REAL,
      PRIMARY KEY(model,issued_at,horizon));
    CREATE INDEX pending_scores ON predictions(model,target_seq) WHERE actual IS NULL;
    ''')


def validate_spec(spec):
    from aqpy.forecast.repository import validate_identifier
    if spec['model_type'] not in FAMILIES:
        raise ValueError(f"Unsupported replay family: {spec['model_type']}")
    for key in ('table', 'time_col', 'target'):
        validate_identifier(spec[key])
    for key, default in [('burn_in_rows', 200), ('max_train_rows', 5000),
                         ('min_new_rows', 30), ('forecast_horizon_steps', 12)]:
        value = spec.get(key, default)
        if not isinstance(value, int) or value <= 0:
            raise ValueError(f'{key} must be a positive integer')
    if any(not isinstance(lag, int) or lag <= 0 for lag in spec.get('lags', [1, 2, 3, 6, 12])):
        raise ValueError('Lags must be positive integers')
    if spec.get('history_hours', 336) <= 0 or spec.get('seq_len', 24) <= 0:
        raise ValueError('History and sequence length must be positive')
    if spec.get('max_train_rows', 5000) > 5000:
        raise ValueError('Replay window is capped at 5000 readings')
    if spec.get('burn_in_rows', 200) > spec.get('max_train_rows', 5000):
        raise ValueError('Burn-in exceeds training window')
    if spec.get('forecast_horizon_steps', 12) > 120:
        raise ValueError('Replay horizon capped at 120 observations')
    if spec.get('seq_len', 24) >= spec.get('burn_in_rows', 200):
        raise ValueError('Burn-in must exceed sequence length')
    if max(spec.get('lags', [1, 2, 3, 6, 12])) >= spec.get('burn_in_rows', 200):
        raise ValueError('Burn-in must exceed maximum lag')


def add_tape(conn, spec, rows, interval=600):
    """Consume an ordered iterable with bounded memory; reject bad tape, never skip it."""
    validate_spec(spec)
    if interval <= 0:
        raise ValueError('Issue interval must be positive')
    digest = hashlib.sha256()
    previous = None
    warmup = None
    first = None
    count = 0
    for ts, value in rows:
        ts = float(ts.timestamp() if hasattr(ts, 'timestamp') else ts)
        value = float(value)
        require_finite([ts, value], 'replay tape')
        if previous is not None and ts <= previous:
            raise ValueError('Tape timestamps must be unique and increasing')
        conn.execute('INSERT INTO samples VALUES (?,?,?,?)', (spec['model_name'], count, ts, value))
        digest.update(dumps([ts, value]).encode())
        first = ts if first is None else first
        count += 1
        previous = ts
        if count == spec.get('burn_in_rows', 200):
            warmup = ts
    if warmup is None:
        raise ValueError(f"{spec['model_name']}: insufficient history for burn-in")
    issue = first + math.ceil((warmup-first)/interval)*interval
    conn.execute('INSERT INTO jobs(model,spec,next_issue) VALUES (?,?,?)',
                 (spec['model_name'], dumps(spec), issue))
    conn.execute('INSERT INTO meta VALUES (?,?)', ('tape:'+spec['model_name'], dumps(
        {'sha256': digest.hexdigest(), 'rows': count, 'first': first, 'last': previous})))


def initialize(run_dir, specs, start=None, end=None, interval=600, max_bytes=1024**3):
    from aqpy.common.db import connect_db
    if not specs:
        raise ValueError('No models selected')
    for spec in specs:
        validate_spec(spec)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    destination = run_dir/'replay.sqlite'
    if destination.exists():
        raise ValueError('Run already exists; resume it instead')
    staging = run_dir/'snapshot.partial'
    # Only this private unfinished staging file is replaced on initialization retry.
    staging.unlink(missing_ok=True)
    local = open_run(staging)
    try:
        schema(local)
        local.execute(f'PRAGMA max_page_count={max(1,int(max_bytes*.8)//4096)}')
        end = end or dt.datetime.now(dt.timezone.utc)
        if start is not None and start >= end:
            raise ValueError('Start must precede end')
        local.execute('INSERT INTO meta VALUES (?,?)', ('config', dumps({
            'version': VERSION, 'interval': interval, 'end': end.isoformat(),
            'start': start.isoformat() if start else None,
            'max_bytes': max_bytes, 'policy': 'fresh_refit_past_only_next_observation_horizons',
            'code_sha256': code_hash()})))
        for database in sorted({s['database'] for s in specs}):
            pg = connect_db(database)
            try:
                pg.set_session(readonly=True, isolation_level='REPEATABLE READ')
                with pg.cursor() as cur:
                    cur.execute("SET LOCAL statement_timeout='30s'")
                    cur.execute("SET LOCAL work_mem='4MB'")
                    cur.execute('SET LOCAL max_parallel_workers_per_gather=0')
                for spec in [s for s in specs if s['database'] == database]:
                    with pg.cursor(name='replay_export') as cur:
                        cur.itersize = 512
                        sql = f"SELECT {spec['time_col']}, {spec['target']} FROM {spec['table']} WHERE {spec['time_col']} <= %s"
                        params = [end]
                        if start is not None:
                            sql += f" AND {spec['time_col']} >= %s"
                            params.append(start)
                        cur.execute(sql+f" ORDER BY {spec['time_col']}", params)
                        def bounded_rows():
                            for i, row in enumerate(cur):
                                if i % 512 == 0:
                                    if (staging.stat().st_size > max_bytes or storage_bytes(run_dir.parent) > ROOT_BUDGET
                                            or shutil.disk_usage(run_dir).free < 3*1024**3):
                                        raise RuntimeError('Snapshot storage budget reached')
                                yield row
                        add_tape(local, spec, bounded_rows(), interval)
                    print('Frozen tape:', spec['model_name'], flush=True)
            finally:
                pg.close()
        local.commit()
    finally:
        local.close()
    os.replace(staging, destination)
    return status(run_dir)


def code_hash():
    files = ['replay.py', 'adaptive_ar.py', 'nn_model.py', 'rnn_lite.py', 'features.py', 'validation.py']
    return hashlib.sha256(b''.join(Path(__file__).with_name(f).read_bytes() for f in files)).hexdigest()


def fit(spec, values, seed):
    """All transformations and fits consume only observations at/before the cutoff."""
    from aqpy.forecast.features import build_ar_feature_matrix, build_feature_matrix
    from aqpy.forecast.adaptive_ar import fit_weighted_ar
    from aqpy.forecast.nn_model import train_mlp_regressor
    from aqpy.forecast.rnn_lite import fit_gru_lite_head
    family = spec['model_type']
    lags = spec.get('lags', [1, 2, 3, 6, 12])
    if family == 'adaptive_ar':
        X, y = build_ar_feature_matrix(values, lags)
        model = fit_weighted_ar(X, y, spec.get('forgetting_factor', .995), spec.get('ar_delta', 100.))
    elif family == 'nn_mlp':
        X, y = build_feature_matrix(values, lags)
        model = train_mlp_regressor(X, y, hidden_dim=spec.get('hidden_dim', 8),
            learning_rate=spec.get('learning_rate', .01), epochs=spec.get('epochs', 40),
            batch_size=spec.get('batch_size', 64), seed=seed)
    elif family == 'rnn_lite_gru':
        model = fit_gru_lite_head(values, seq_len=spec.get('seq_len', 24),
            hidden_dim=spec.get('hidden_dim', 8), ridge=spec.get('rnn_ridge', .001), seed=seed)
    else:
        raise ValueError(f'Unsupported family: {family}')
    model.update(model_type=family, lags=lags)
    require_finite(model, 'replay model')
    return model


def predict(model, values, horizon):
    from aqpy.forecast import adaptive_ar, nn_model, rnn_lite
    if model['model_type'] == 'adaptive_ar':
        result = adaptive_ar.recursive_predict(model, values, model['lags'], horizon)
    elif model['model_type'] == 'nn_mlp':
        result = nn_model.recursive_predict(model, values, model['lags'], horizon)
    else:
        result = rnn_lite.recursive_predict(model, values, horizon)
    require_finite(result, 'replay predictions')
    if len(result) != horizon:
        raise ValueError('Wrong prediction horizon')
    return result


def reveal(conn, model, seq):
    # Score only observations already revealed by the virtual clock.
    conn.execute('''UPDATE predictions SET
      actual=(SELECT y FROM samples s WHERE s.model=predictions.model AND s.seq=target_seq),
      actual_at=(SELECT ts FROM samples s WHERE s.model=predictions.model AND s.seq=target_seq)
      WHERE model=? AND actual IS NULL AND target_seq<=?''', (model, seq))


def step(conn, job, interval):
    spec = json.loads(job['spec'])
    model_name = job['model']
    issue = job['next_issue']
    # Latest observed row; no future values are returned to fit or predict.
    latest = conn.execute('SELECT seq,ts FROM samples WHERE model=? AND ts<=? ORDER BY ts DESC LIMIT 1',
                          (model_name, issue)).fetchone()
    end = conn.execute('SELECT seq,ts FROM samples WHERE model=? ORDER BY seq DESC LIMIT 1', (model_name,)).fetchone()
    if issue > end['ts']:
        with conn:
            reveal(conn, model_name, end['seq'])
            conn.execute('UPDATE jobs SET completed=1 WHERE model=?', (model_name,))
        return
    if latest is None:
        raise RuntimeError('Missing warm-up tape')
    history_start = issue-spec.get('history_hours', 336)*3600
    rows = conn.execute('SELECT ts,y FROM samples WHERE model=? AND ts<=? AND ts>=? ORDER BY ts DESC LIMIT ?',
        (model_name, issue, history_start, spec.get('max_train_rows', 5000))).fetchall()[::-1]
    if len(rows) < spec.get('burn_in_rows', 200):
        with conn:
            reveal(conn, model_name, latest['seq'])
            conn.execute('UPDATE jobs SET next_issue=? WHERE model=?', (issue+interval, model_name))
        return
    values = np.asarray([r['y'] for r in rows], dtype=float)
    artifact = json.loads(job['artifact']) if job['artifact'] else None
    retrain = artifact is None or latest['seq']-job['last_train_seq'] >= spec.get('min_new_rows', 30)
    cutoff = job['train_cutoff']
    if retrain:
        artifact = fit(spec, values, spec.get('random_seed', 42)+latest['seq'])
        cutoff = latest['ts']
    forecasts = predict(artifact, values, spec.get('forecast_horizon_steps', 12))
    if cutoff > issue:
        raise RuntimeError('Training cutoff exceeds forecast issue time')
    with conn:
        reveal(conn, model_name, latest['seq'])
        conn.executemany('INSERT INTO predictions(model,issued_at,horizon,target_seq,train_cutoff,yhat,baseline) VALUES (?,?,?,?,?,?,?)',
            [(model_name, issue, h, latest['seq']+h, cutoff, float(y), float(values[-1])) for h,y in enumerate(forecasts,1)])
        # Predictions, model and clock checkpoint are one durable transaction.
        conn.execute('''UPDATE jobs SET next_issue=?, artifact=?, train_cutoff=?,
          last_train_seq=?, issues=issues+1, fits=fits+? WHERE model=?''',
          (issue+interval, dumps(artifact), cutoff, latest['seq'] if retrain else job['last_train_seq'], int(retrain), model_name))


def pause_reason(run_dir, max_bytes, check_live=True):
    mem = dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    if int(mem['MemAvailable'].split()[0]) < 600*1024:
        return 'available RAM below 600 MiB'
    if shutil.disk_usage(run_dir).free < 3*1024**3:
        return 'free disk below 3 GiB'
    if sum(p.stat().st_size for p in Path(run_dir).iterdir() if p.is_file()) > max_bytes:
        raise RuntimeError('Replay storage budget exceeded')
    if storage_bytes(Path(run_dir).parent) > ROOT_BUDGET:
        raise RuntimeError('Combined replay storage exceeds 2 GiB; archive completed runs')
    if check_live:
        result = subprocess.run(['systemctl','show','aqi-train-online.service','aqi-forecast.service','aqi-retention.service',
                                 '--property=ActiveState','--value'], capture_output=True,text=True,timeout=5)
        if result.returncode:
            raise RuntimeError('Cannot inspect live service state: '+result.stderr.strip())
        if any(s in ('activating','active','deactivating') for s in result.stdout.splitlines()):
            return 'live training/forecast/retention is running'
    return None


def run(run_dir, seconds=45, max_events=None, check_resources=True):
    import fcntl
    run_dir = Path(run_dir)
    with (run_dir.parent/'.replay-worker.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        conn = open_run(run_dir/'replay.sqlite')
        try:
            config = json.loads(conn.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])
            if config['version'] != VERSION or config['code_sha256'] != code_hash():
                raise RuntimeError('Replay implementation changed; use the original code or initialize a new run')
            deadline = time.monotonic()+seconds
            events = 0
            checked_at = 0.0
            while time.monotonic() < deadline and (max_events is None or events < max_events):
                job = conn.execute('SELECT * FROM jobs WHERE completed=0 ORDER BY next_issue,model LIMIT 1').fetchone()
                if job is None:
                    (run_dir/'complete').touch()
                    break
                if check_resources and time.monotonic()-checked_at >= 2:
                    checked_at = time.monotonic()
                    reason = pause_reason(run_dir, config['max_bytes'])
                    if reason:
                        print('Replay paused:',reason,flush=True)
                        break
                step(conn, job, config['interval'])
                events += 1
        finally:
            conn.close()
    result = status(run_dir)
    print(dumps(result), flush=True)
    return result


def status(run_dir):
    conn = open_run(Path(run_dir)/'replay.sqlite')
    try:
        jobs = [dict(r) for r in conn.execute('SELECT model,completed,issues,fits,next_issue,train_cutoff FROM jobs ORDER BY model')]
        return {'complete': all(j['completed'] for j in jobs), 'jobs': jobs,
                'predictions': conn.execute('SELECT count(*) FROM predictions').fetchone()[0],
                'scored': conn.execute('SELECT count(*) FROM predictions WHERE actual IS NOT NULL').fetchone()[0]}
    finally:
        conn.close()


def export(run_dir):
    import fcntl
    with (Path(run_dir).parent/'.replay-worker.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _export(run_dir)


def validate(run_dir):
    import fcntl
    from aqpy.forecast.replay_validation import validate as audit
    with (Path(run_dir).parent/'.replay-worker.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return audit(run_dir)


def _export(run_dir):
    import csv
    run_dir = Path(run_dir)
    conn = open_run(run_dir/'replay.sqlite')
    try:
        if not status(run_dir)['complete']:
            raise RuntimeError('Complete the replay before exporting validated results')
        (run_dir/'validation.json').unlink(missing_ok=True)
        # Streaming output; no full-history materialization.
        import io
        config = json.loads(conn.execute("SELECT value FROM meta WHERE key='config'").fetchone()[0])
        staging = run_dir/'predictions.csv.partial'
        staging.unlink(missing_ok=True)
        used = sum(p.stat().st_size for p in run_dir.iterdir() if p.is_file())
        root_used = storage_bytes(run_dir.parent)
        try:
            with staging.open('w') as f:
                cur = conn.execute('SELECT * FROM predictions ORDER BY model,issued_at,horizon')
                def write_row(row):
                    nonlocal used, root_used
                    buffer = io.StringIO();csv.writer(buffer).writerow(row)
                    line = buffer.getvalue();used += len(line.encode());root_used += len(line.encode())
                    if used > config['max_bytes']-1024*1024 or root_used > ROOT_BUDGET:
                        raise RuntimeError('Export exceeds run storage budget; increase budget or use SQLite directly')
                    f.write(line)
                write_row([c[0] for c in cur.description])
                for row in cur:write_row(row)
            os.replace(staging,run_dir/'predictions.csv')
        finally:
            staging.unlink(missing_ok=True)
        records = []
        for r in conn.execute('''SELECT model,horizon,count(*) AS n,
          avg(abs(yhat-actual)) AS mae,avg((yhat-actual)*(yhat-actual)) AS mse,
          avg(abs(baseline-actual)) AS baseline_mae,avg((baseline-actual)*(baseline-actual)) AS baseline_mse
          FROM predictions WHERE actual IS NOT NULL GROUP BY model,horizon'''):
            record = dict(r)
            record['rmse'] = math.sqrt(record.pop('mse'))
            record['baseline_rmse'] = math.sqrt(record.pop('baseline_mse'))
            record['mae_improvement_pct'] = (100*(record['baseline_mae']-record['mae'])/record['baseline_mae']
                                             if record['baseline_mae'] else None)
            records.append(record)
        (run_dir/'scores.json').write_text(dumps(records)+'\n')
        (run_dir/'status.json').write_text(dumps(status(run_dir))+'\n')
        from aqpy.forecast.replay_validation import validate as audit
        report = audit(run_dir, records)
        if report['status'] != 'PASS':
            raise RuntimeError('Replay validation failed: '+ '; '.join(report['failures']))
        return records
    finally:
        conn.close()
