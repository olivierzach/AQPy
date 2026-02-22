#!/usr/bin/env python3

import argparse
import json
import os

from aqpy.forecast.training import train_model


def parse_args():
    parser = argparse.ArgumentParser(description="Train lag-based time-series model.")
    parser.add_argument("--database", default=os.getenv("AQPY_DB_NAME_BME", "bme"))
    parser.add_argument("--table", default="pi")
    parser.add_argument("--time-col", default="t")
    parser.add_argument("--target", default="temperature")
    parser.add_argument("--history-hours", type=int, default=24 * 14)
    parser.add_argument("--lags", default="1,2,3,6,12")
    parser.add_argument("--model-name", default="aqpy_linear_lag")
    parser.add_argument(
        "--model-path",
        default="models/bme_temperature_model.json",
    )
    parser.add_argument("--register", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    lags = [int(x.strip()) for x in args.lags.split(",") if x.strip()]
    payload = train_model(
        database=args.database,
        table=args.table,
        time_col=args.time_col,
        target=args.target,
        history_hours=args.history_hours,
        lags=lags,
        model_name=args.model_name,
        model_path=args.model_path,
        register=args.register,
    )
    print(f"Model written: {args.model_path}")
    print(json.dumps(payload["metrics"], indent=2))
    if args.register:
        print("Registered model in model_registry")


if __name__ == "__main__":
    main()
