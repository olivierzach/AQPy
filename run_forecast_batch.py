#!/usr/bin/env python3

import argparse
import json
import logging
from aqpy.common.batch import finish_batch
import pathlib

from aqpy.forecast.inference import run_inference
from aqpy.forecast.specs import filter_specs, load_model_specs


def parse_csv(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run forecast inference across model specs."
    )
    parser.add_argument("--spec-file", default="configs/model_specs.json")
    parser.add_argument("--models", default="")
    parser.add_argument("--databases", default="")
    parser.add_argument("--targets", default="")
    parser.add_argument("--families", default="")
    parser.add_argument("--horizon-steps", type=int, default=0)
    return parser.parse_args()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
        horizon = (
            args.horizon_steps
            if args.horizon_steps > 0
            else int(spec.get("forecast_horizon_steps", 12))
        )
        try:
            res = run_inference(
                model_path=str(model_path),
                horizon_steps=horizon,
                database_override=spec["database"],
            )
            results.append({"model_name": spec["model_name"], "result": res})
        except Exception as exc:
            logging.exception("Job failed: %s", spec["model_name"])
            results.append(
                {
                    "model_name": spec["model_name"],
                    "status": "failed",
                    "error": str(exc),
                }
            )
    return finish_batch(results)


if __name__ == "__main__":
    raise SystemExit(main())
