"""Bounded raw recursive checks before publishing a trained model."""
import numpy as np

from aqpy.forecast import adaptive_ar, nn_model, rnn_lite
from aqpy.forecast.output_policy import correct_output

VERSION = 'recursive_gate_v1'


def assess(model, values, holdout_start, horizon_steps=12):
    """Probe latest inputs and eight causal holdout origins, without output clipping.

    Scores describe these sampled recursive windows, not all historical forecasts.
    Tiny negative particle projections have the same tolerance as the watchdog.
    """
    if horizon_steps < 1:
        raise ValueError('Forecast horizon must be positive')
    values = [float(v) for v in values]
    needed = max(50, max(model['lags']) + 1, int(model.get('seq_len', 0)))
    first = max(needed, int(holdout_start))
    origins = {len(values)}
    if first < len(values):
        origins.update(int(i) for i in np.linspace(first, len(values) - 1, 8))
    errors, baseline_errors = [], []
    minimum, maximum = float('inf'), float('-inf')
    for origin in sorted(origins):
        history = values[max(0, origin - needed):origin]
        if len(history) < needed:
            raise ValueError('Insufficient history for recursive stability check')
        kind = model['model_type']
        if kind == 'nn_mlp':
            predictions = nn_model.recursive_predict(model, history, model['lags'], horizon_steps)
        elif kind == 'adaptive_ar':
            predictions = adaptive_ar.recursive_predict(model, history, model['lags'], horizon_steps)
        elif kind == 'rnn_lite_gru':
            predictions = rnn_lite.recursive_predict(model, history, horizon_steps)
        else:
            raise ValueError('Unsupported stability model: ' + kind)
        for step, raw in enumerate(predictions):
            _, reason = correct_output(model['target'], raw, history[-1], history)
            if 'persistence' in reason or (reason == 'nonnegative_projection_v1' and raw < -1.):
                raise ValueError(f'Recursive stability rejected origin={origin} step={step + 1}: {raw} ({reason})')
            minimum, maximum = min(minimum, float(raw)), max(maximum, float(raw))
            if origin + step < len(values):
                actual = values[origin + step]
                errors.append(abs(float(raw) - actual))
                baseline_errors.append(abs(history[-1] - actual))
    return {'version': VERSION, 'status': 'PASS', 'horizon_steps': horizon_steps,
            'origins': len(origins), 'scored_predictions': len(errors),
            'raw_min': minimum, 'raw_max': maximum,
            'sampled_recursive_mae': float(np.mean(errors)) if errors else None,
            'sampled_persistence_mae': float(np.mean(baseline_errors)) if errors else None}
