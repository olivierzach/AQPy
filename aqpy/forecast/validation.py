import math


def require_finite(value, path="value"):
    """Reject invalid numbers before publishing artifacts or database rows."""
    if isinstance(value, dict):
        for key, item in value.items():
            require_finite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            require_finite(item, f"{path}[{index}]")
    elif isinstance(value, (int, float)) and not math.isfinite(value):
        raise ValueError(f"Non-finite number at {path}")
