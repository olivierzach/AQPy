import json
import pathlib


REQUIRED_KEYS = {
    "model_name",
    "model_type",
    "database",
    "table",
    "time_col",
    "target",
    "model_path",
}


def load_model_specs(spec_path):
    path = pathlib.Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found: {path}")
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Model specs file must contain a top-level JSON list.")
    for idx, spec in enumerate(data):
        if not isinstance(spec, dict):
            raise ValueError(f"Spec at index {idx} must be an object.")
        missing = REQUIRED_KEYS - set(spec.keys())
        if missing:
            raise ValueError(f"Spec '{spec.get('model_name', idx)}' missing keys: {sorted(missing)}")
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
