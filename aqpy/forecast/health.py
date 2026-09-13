"""Small indexed health checks; invalid current data fails the scheduled service."""
import datetime as dt
import json
from pathlib import Path

from aqpy.common.db import connect_db
from aqpy.forecast.validation import require_finite
from aqpy.forecast.retention import _validate_identifier as validate_identifier


def assess_artifact(spec):
    artifact = json.loads(Path(spec['model_path']).read_text())
    if not isinstance(artifact, dict):
        raise ValueError('Model artifact must be an object')
    require_finite(artifact, spec['model_name'])
    for key in ('model_version','model_type','model_name'):
        if not artifact.get(key):
            raise ValueError(f'Missing model field: {key}')
    if artifact['model_name'] != spec['model_name'] or artifact['model_type'] != spec['model_type']:
        raise ValueError('Model artifact identity mismatch')
    return artifact


def check_recent_predictions(rows, now, max_age):
    if not rows:
        raise ValueError('No recent predictions')
    require_finite([float(r[0]) for r in rows], 'recent forecasts')
    newest = max(r[1] for r in rows)
    if (now-newest).total_seconds() > max_age:
        raise ValueError('Forecast generation is stale')


def check_health(specs, sensor_age=300, forecast_age=1800, training_age=7200):
    now = dt.datetime.now(dt.timezone.utc)
    failures = []
    for database in sorted({s['database'] for s in specs}):
        try:
            conn = connect_db(database)
        except Exception as exc:
            failures.append({'database':database,'error':str(exc)})
            continue
        try:
            conn.set_session(readonly=True,autocommit=True)
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout='10s'")
                cur.execute("SET work_mem='4MB'")
                cur.execute('SET max_parallel_workers_per_gather=0')
                checked = set()
                for spec in [s for s in specs if s['database']==database]:
                    name = spec['model_name']
                    try:
                        table,target,tc = [validate_identifier(spec[k]) for k in ('table','target','time_col')]
                        source = (table,target,tc)
                        if source not in checked:
                            cur.execute(f'SELECT {tc},{target} FROM {table} ORDER BY {tc} DESC LIMIT 64')
                            rows = cur.fetchall()
                            if not rows or (now-rows[0][0]).total_seconds() > sensor_age:
                                raise ValueError(f'Sensor source {table}.{target} is stale')
                            if any(r[1] is None for r in rows):
                                raise ValueError(f'Sensor source {table}.{target} contains nulls')
                            require_finite([float(r[1]) for r in rows], 'recent sensor readings')
                            checked.add(source)
                        assess_artifact(spec)
                        cur.execute('''SELECT last_trained_at FROM online_training_state WHERE model_name=%s''',(name,))
                        state = cur.fetchone()
                        if not state or (now-state[0]).total_seconds() > training_age:
                            raise ValueError('Training state missing or stale')
                        cur.execute('''SELECT yhat,generated_at FROM predictions WHERE target=%s AND model_name=%s
                          AND predicted_for >= %s ORDER BY predicted_for DESC LIMIT 256''',
                          (target,name,now-dt.timedelta(seconds=forecast_age)))
                        check_recent_predictions(cur.fetchall(),now,forecast_age)
                        cur.execute('''SELECT holdout_mae,holdout_rmse,baseline_mae,baseline_rmse,
                          mae_improvement_pct,rmse_improvement_pct FROM online_training_metrics
                          WHERE model_name=%s AND recorded_at >= %s ORDER BY recorded_at DESC''',
                          (name,now-dt.timedelta(seconds=training_age)))
                        metrics = cur.fetchall()
                        if not metrics:
                            raise ValueError('Recent training metrics missing')
                        require_finite([[float(x) for x in r] for r in metrics], 'recent training metrics')
                    except Exception as exc:
                        failures.append({'database':database,'model':name,'error':str(exc)})
        finally:
            conn.close()
    return {'checked_at':now.isoformat(),'status':'failed' if failures else 'ok',
            'models_checked':len(specs),'failures':failures}
