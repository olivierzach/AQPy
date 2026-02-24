#!/usr/bin/env python3

import argparse
import json

from aqpy.forecast.online_training import run_online_training_step
from aqpy.forecast.specs import filter_specs, load_model_specs


def parse_csv(value):
    if not value:
        return []
    return [x.strip() for x in value.split(",") if x.strip()]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run online training across model specs (multi-sensor, multi-model)."
    )
    parser.add_argument("--spec-file", default="configs/model_specs.json")
    parser.add_argument("--models", default="")
    parser.add_argument("--databases", default="")
    parser.add_argument("--targets", default="")
    parser.add_argument("--families", default="")
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
        try:
            res = run_online_training_step(
                database=spec["database"],
                table=spec["table"],
                time_col=spec["time_col"],
                target=spec["target"],
                model_name=spec["model_name"],
                model_path=spec["model_path"],
                history_hours=spec.get("history_hours", 24 * 14),
                lags=spec.get("lags"),
                holdout_ratio=spec.get("holdout_ratio", 0.2),
                min_new_rows=spec.get("min_new_rows", 30),
                learning_rate=spec.get("learning_rate", 0.01),
                epochs=spec.get("epochs", 40),
                batch_size=spec.get("batch_size", 64),
                hidden_dim=spec.get("hidden_dim", 8),
                model_type=spec.get("model_type", "nn_mlp"),
                forgetting_factor=spec.get("forgetting_factor", 0.995),
                ar_delta=spec.get("ar_delta", 100.0),
                seq_len=spec.get("seq_len", 24),
                burn_in_rows=spec.get("burn_in_rows", 200),
                max_train_rows=spec.get("max_train_rows"),
                rnn_ridge=spec.get("rnn_ridge", 1e-3),
                random_seed=spec.get("random_seed", 42),
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
