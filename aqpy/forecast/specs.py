import json
import pathlib
import re


REQUIRED_KEYS = {
    "model_name",
    "model_type",
    "database",
    "table",
    "time_col",
    "target",
    "model_path",
}

ALLOWED_MODEL_TYPES = {"nn_mlp", "adaptive_ar", "rnn_lite_gru"}
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_identifier(value):
    return isinstance(value, str) and bool(IDENTIFIER_RE.match(value))


def _expect_positive_int(spec, key):
    value = spec.get(key)
    if value is None:
        return
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Spec '{spec['model_name']}' key '{key}' must be a positive integer.")


def _expect_nonnegative_int(spec, key):
    value = spec.get(key)
    if value is None:
        return
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"Spec '{spec['model_name']}' key '{key}' must be a non-negative integer.")


def _expect_positive_number(spec, key):
    value = spec.get(key)
    if value is None:
        return
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Spec '{spec['model_name']}' key '{key}' must be > 0.")


def _validate_lags(spec):
    lags = spec.get("lags")
    if not isinstance(lags, list) or not lags:
        raise ValueError(f"Spec '{spec['model_name']}' must provide non-empty 'lags'.")
    if not all(isinstance(x, int) and x > 0 for x in lags):
        raise ValueError(f"Spec '{spec['model_name']}' has invalid 'lags'; positive ints required.")
    if len(set(lags)) != len(lags):
        raise ValueError(f"Spec '{spec['model_name']}' has duplicate values in 'lags'.")


def validate_model_specs(specs):
    if not isinstance(specs, list):
        raise ValueError("Model specs file must contain a top-level JSON list.")
    if not specs:
        raise ValueError("Model specs list cannot be empty.")

    seen_model_names = set()
    seen_model_paths = set()

    for idx, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise ValueError(f"Spec at index {idx} must be an object.")

        missing = REQUIRED_KEYS - set(spec.keys())
        if missing:
            raise ValueError(f"Spec '{spec.get('model_name', idx)}' missing keys: {sorted(missing)}")

        model_name = spec["model_name"]
        model_type = spec["model_type"]
        model_path = spec["model_path"]

        for key in ("model_name", "model_path"):
            if not isinstance(spec[key], str) or not spec[key].strip():
                raise ValueError(f"Spec at index {idx} key '{key}' must be a non-empty string.")

        if model_name in seen_model_names:
            raise ValueError(f"Duplicate model_name: '{model_name}'")
        seen_model_names.add(model_name)

        if model_path in seen_model_paths:
            raise ValueError(f"Duplicate model_path: '{model_path}'")
        seen_model_paths.add(model_path)

        if model_type not in ALLOWED_MODEL_TYPES:
            raise ValueError(
                f"Spec '{model_name}' has unsupported model_type '{model_type}'. "
                f"Allowed: {sorted(ALLOWED_MODEL_TYPES)}"
            )

        if spec["database"] not in {"bme", "pms"}:
            raise ValueError(f"Spec '{model_name}' has unsupported database '{spec['database']}'.")

        for key in ("table", "time_col", "target"):
            if not _is_identifier(spec[key]):
                raise ValueError(f"Spec '{model_name}' has invalid SQL identifier for '{key}'.")

        _expect_positive_int(spec, "history_hours")
        _expect_positive_int(spec, "burn_in_rows")
        _expect_positive_int(spec, "max_train_rows")
        _expect_positive_int(spec, "forecast_horizon_steps")
        _expect_nonnegative_int(spec, "min_new_rows")
        _expect_positive_int(spec, "epochs")
        _expect_positive_int(spec, "batch_size")
        _expect_positive_int(spec, "hidden_dim")
        _expect_positive_int(spec, "seq_len")

        if "holdout_ratio" in spec:
            holdout_ratio = spec["holdout_ratio"]
            if not isinstance(holdout_ratio, (int, float)) or holdout_ratio <= 0 or holdout_ratio >= 1:
                raise ValueError(f"Spec '{model_name}' key 'holdout_ratio' must be in (0, 1).")

        _expect_positive_number(spec, "learning_rate")
        _expect_positive_number(spec, "forgetting_factor")
        _expect_positive_number(spec, "ar_delta")
        _expect_positive_number(spec, "rnn_ridge")

        if model_type in {"nn_mlp", "adaptive_ar"}:
            _validate_lags(spec)
        if model_type == "rnn_lite_gru":
            if "seq_len" not in spec:
                raise ValueError(f"Spec '{model_name}' with rnn_lite_gru must provide 'seq_len'.")

        if "max_train_rows" in spec and "burn_in_rows" in spec:
            if spec["max_train_rows"] < spec["burn_in_rows"]:
                raise ValueError(
                    f"Spec '{model_name}' has max_train_rows < burn_in_rows "
                    f"({spec['max_train_rows']} < {spec['burn_in_rows']})."
                )


def load_model_specs(spec_path):
    path = pathlib.Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {path}")
    data = json.loads(path.read_text())
    validate_model_specs(data)
    return data


def filter_specs(specs, model_names=None, databases=None):
    selected = specs
    if model_names:
        allowed = set(model_names)
        selected = [s for s in selected if s["model_name"] in allowed]
    if databases:
        allowed_db = set(databases)
        selected = [s for s in selected if s["database"] in allowed_db]
    return selected
