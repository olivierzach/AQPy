#!/usr/bin/env python3

import argparse
import json
import os

from aqpy.forecast.retention import run_retention
from aqpy.forecast.specs import filter_specs, load_model_specs


def parse_csv(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def env_int(name, default):
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run retention per source database/table from model specs."
    )
    parser.add_argument("--spec-file", default="configs/model_specs.json")
    parser.add_argument("--models", default="")
    parser.add_argument("--databases", default="")
    parser.add_argument("--targets", default="")
    parser.add_argument("--families", default="")
    parser.add_argument("--retention-days", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--safety-hours", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--raw-retention-days",
        type=int,
        default=env_int("AQPY_RETENTION_DAYS_RAW", env_int("AQPY_RETENTION_DAYS", 180)),
    )
    parser.add_argument(
        "--raw-safety-hours",
        type=int,
        default=env_int(
            "AQPY_RETENTION_SAFETY_HOURS_RAW",
            env_int("AQPY_RETENTION_SAFETY_HOURS", 24),
        ),
    )
    parser.add_argument(
        "--pred-retention-days",
        type=int,
        default=env_int(
            "AQPY_RETENTION_DAYS_PREDICTIONS",
            env_int("AQPY_RETENTION_DAYS", 180),
        ),
    )
    parser.add_argument(
        "--pred-safety-hours",
        type=int,
        default=env_int("AQPY_RETENTION_SAFETY_HOURS_PREDICTIONS", 0),
    )
    args = parser.parse_args()
    if args.retention_days is not None:
        args.raw_retention_days = args.retention_days
    if args.safety_hours is not None:
        args.raw_safety_hours = args.safety_hours
    return args


def collect_retention_sources(
    specs, raw_retention_days, raw_safety_hours, pred_retention_days, pred_safety_hours
):
    unique_sources = {}
    databases = set()
    skipped_sources = []
    for spec in specs:
        databases.add(spec["database"])
        # Retention deletes rows; only run against base raw sensor tables.
        if spec["table"] != "pi":
            skipped_sources.append(
                {
                    "database": spec["database"],
                    "table": spec["table"],
                    "time_col": spec["time_col"],
                    "reason": "non-raw source table; raw retention skipped",
                }
            )
            continue
        key = (spec["database"], spec["table"], spec["time_col"], "raw")
        unique_sources[key] = {
            "database": spec["database"],
            "table": spec["table"],
            "time_col": spec["time_col"],
            "retention_days": raw_retention_days,
            "safety_hours": raw_safety_hours,
            "use_training_watermark": True,
        }

    for db in sorted(databases):
        key = (db, "predictions", "predicted_for", "predictions")
        unique_sources[key] = {
            "database": db,
            "table": "predictions",
            "time_col": "predicted_for",
            "retention_days": pred_retention_days,
            "safety_hours": pred_safety_hours,
            "use_training_watermark": False,
        }

    return list(unique_sources.values()), skipped_sources


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

    unique_sources, skipped_sources = collect_retention_sources(
        specs=specs,
        raw_retention_days=args.raw_retention_days,
        raw_safety_hours=args.raw_safety_hours,
        pred_retention_days=args.pred_retention_days,
        pred_safety_hours=args.pred_safety_hours,
    )

    results = []
    results.extend(skipped_sources)
    for source in unique_sources:
        try:
            res = run_retention(
                database=source["database"],
                table=source["table"],
                time_col=source["time_col"],
                model_name=None,
                retention_days=source["retention_days"],
                safety_hours=source["safety_hours"],
                use_training_watermark=source["use_training_watermark"],
            )
            results.append(
                {
                    "database": source["database"],
                    "table": source["table"],
                    "time_col": source["time_col"],
                    "retention_days": source["retention_days"],
                    "safety_hours": source["safety_hours"],
                    "use_training_watermark": source["use_training_watermark"],
                    "result": res,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "database": source["database"],
                    "table": source["table"],
                    "time_col": source["time_col"],
                    "retention_days": source["retention_days"],
                    "safety_hours": source["safety_hours"],
                    "use_training_watermark": source["use_training_watermark"],
                    "status": "failed",
                    "error": str(exc),
                }
            )
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
