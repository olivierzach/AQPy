#!/usr/bin/env python3

import argparse
import json
import pathlib

from aqpy.forecast.backfill import run_backfill
from aqpy.forecast.specs import filter_specs, load_model_specs


def parse_csv(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run idempotent historical one-step backfill across model specs."
    )
    parser.add_argument("--spec-file", default="configs/model_specs.json")
    parser.add_argument("--models", default="")
    parser.add_argument("--databases", default="")
    parser.add_argument("--targets", default="")
    parser.add_argument("--families", default="")
    parser.add_argument("--backfill-hours", type=int, default=48)
    parser.add_argument("--append", action="store_true", help="Do not replace existing rows in window.")
    return parser.parse_args()


def main():
    args = parse_args()
    specs = load_model_specs(args.spec_file)
    specs = filter_specs(
        specs,
        model_names=parse_csv(args.models),
        databases=parse_csv(args.databases),
        targets=parse_csv(args.targets),
        families=[x.lower() for x in parse_csv(args.families)],
    )
    results = []
    for spec in specs:
        model_path = pathlib.Path(spec["model_path"])
        if not model_path.exists():
            results.append(
                {
                    "model_name": spec["model_name"],
                    "status": "skipped",
                    "reason": f"model not found: {model_path}",
                }
            )
            continue
        try:
            res = run_backfill(
                model_path=str(model_path),
                backfill_hours=args.backfill_hours,
                database_override=spec["database"],
                replace_existing=not args.append,
            )
            results.append({"model_name": spec["model_name"], "result": res})
        except Exception as exc:
            results.append(
                {
                    "model_name": spec["model_name"],
                    "status": "failed",
                    "error": str(exc),
                }
            )
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
