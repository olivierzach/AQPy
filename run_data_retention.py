#!/usr/bin/env python3

import argparse
import json
import os

from aqpy.forecast.retention import run_retention


def parse_args():
    parser = argparse.ArgumentParser(
        description="Delete old rows only behind online-training watermark."
    )
    parser.add_argument("--database", default=os.getenv("AQPY_DB_NAME_BME", "bme"))
    parser.add_argument("--table", default="pi")
    parser.add_argument("--time-col", default="t")
    parser.add_argument(
        "--model-name",
        default="",
        help="optional model name; leave empty to use all models watermark",
    )
    parser.add_argument("--retention-days", type=int, default=14)
    parser.add_argument("--safety-hours", type=int, default=12)
    return parser.parse_args()


def main():
    args = parse_args()
    result = run_retention(
        database=args.database,
        table=args.table,
        time_col=args.time_col,
        model_name=(args.model_name or None),
        retention_days=args.retention_days,
        safety_hours=args.safety_hours,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
