#!/usr/bin/env python3

import argparse

from aqpy.forecast.specs import load_model_specs


def parse_args():
    parser = argparse.ArgumentParser(
        description="Validate AQPy model specs file."
    )
    parser.add_argument("--spec-file", default="configs/model_specs.json")
    return parser.parse_args()


def main():
    args = parse_args()
    specs = load_model_specs(args.spec_file)
    print(f"OK: {len(specs)} model specs validated from {args.spec_file}")


if __name__ == "__main__":
    main()
