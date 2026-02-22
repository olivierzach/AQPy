#!/usr/bin/env python3

import argparse

from aqpy.forecast.inference import run_inference


def parse_args():
    parser = argparse.ArgumentParser(description="Run edge forecast inference.")
    parser.add_argument(
        "--model-path",
        default="models/bme_temperature_nn.json",
    )
    parser.add_argument("--database", default=None)
    parser.add_argument("--horizon-steps", type=int, default=12)
    return parser.parse_args()


def main():
    args = parse_args()
    result = run_inference(
        model_path=args.model_path,
        horizon_steps=args.horizon_steps,
        database_override=args.database,
    )
    print(
        f"Inserted {result['inserted']} predictions for {result['target']} "
        f"using {result['model_name']}:{result['model_version']}"
    )


if __name__ == "__main__":
    main()
