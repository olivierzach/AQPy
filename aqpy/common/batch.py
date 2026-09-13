import json
import logging


def finish_batch(results):
    """Keep all per-item results, but make partial failures visible to systemd."""
    failed = [r for r in results if r.get("status") == "failed" or r.get("result", {}).get("status") == "failed"]
    print(json.dumps(results, indent=2, default=str, allow_nan=False), flush=True)
    if failed:
        logging.error("Batch failed: %d of %d jobs failed", len(failed), len(results))
    else:
        logging.info("Batch completed: %d jobs", len(results))
    return 1 if failed else 0
