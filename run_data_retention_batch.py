#!/usr/bin/env python3

import argparse
import json

from aqpy.forecast.retention import run_retention
from aqpy.forecast.specs import filter_specs, load_model_specs


def parse_csv(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run retention per source database/table from model specs."
    )
    parser.add_argument("--spec-file", default="configs/model_specs.json")
    parser.add_argument("--models", default="")
    parser.add_argument("--databases", default="")
    parser.add_argument("--retention-days", type=int, default=14)
    parser.add_argument("--safety-hours", type=int, default=12)
    return parser.parse_args()


def main():
    args = parse_args()
    specs = load_model_specs(args.spec_file)
    specs = filter_specs(
        specs,
        model_names=parse_csv(args.models),
        databases=parse_csv(args.databases),
    )

    unique_sources = {}
    for spec in specs:
        key = (spec["database"], spec["table"], spec["time_col"])
        unique_sources[key] = True

    results = []
    for database, table, time_col in unique_sources.keys():
        res = run_retention(
            database=database,
            table=table,
            time_col=time_col,
            model_name=None,
            retention_days=args.retention_days,
            safety_hours=args.safety_hours,
        )
        results.append(
            {
                "database": database,
                "table": table,
                "time_col": time_col,
                "result": res,
            }
        )
    print(json.dumps(results, indent=2, default=str))


if __name__ == "__main__":
    main()
