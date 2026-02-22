#!/usr/bin/env python3

import argparse
import json
import os

from aqpy.forecast.online_training import run_online_training_step


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run one online retraining step and log holdout metrics."
    )
    parser.add_argument("--database", default=os.getenv("AQPY_DB_NAME_BME", "bme"))
    parser.add_argument("--table", default="pi")
    parser.add_argument("--time-col", default="t")
    parser.add_argument("--target", default="temperature")
    parser.add_argument("--model-name", default="aqpy_nn_temperature")
    parser.add_argument("--model-path", default="models/bme_temperature_nn.json")
    parser.add_argument(
        "--model-type",
        choices=["nn_mlp", "adaptive_ar", "rnn_lite_gru"],
        default="nn_mlp",
    )
    parser.add_argument("--history-hours", type=int, default=24 * 14)
    parser.add_argument("--lags", default="1,2,3,6,12")
    parser.add_argument("--seq-len", type=int, default=24)
    parser.add_argument("--holdout-ratio", type=float, default=0.2)
    parser.add_argument("--burn-in-rows", type=int, default=200)
    parser.add_argument("--max-train-rows", type=int, default=0)
    parser.add_argument("--min-new-rows", type=int, default=30)
    parser.add_argument("--learning-rate", type=float, default=0.01)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--hidden-dim", type=int, default=8)
    parser.add_argument("--forgetting-factor", type=float, default=0.995)
    parser.add_argument("--ar-delta", type=float, default=100.0)
    parser.add_argument("--rnn-ridge", type=float, default=1e-3)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main():
    args = parse_args()
    lags = [int(x.strip()) for x in args.lags.split(",") if x.strip()]
    result = run_online_training_step(
        database=args.database,
        table=args.table,
        time_col=args.time_col,
        target=args.target,
        model_name=args.model_name,
        model_path=args.model_path,
        model_type=args.model_type,
        history_hours=args.history_hours,
        lags=lags,
        seq_len=args.seq_len,
        holdout_ratio=args.holdout_ratio,
        burn_in_rows=args.burn_in_rows,
        max_train_rows=(args.max_train_rows if args.max_train_rows > 0 else None),
        min_new_rows=args.min_new_rows,
        learning_rate=args.learning_rate,
        epochs=args.epochs,
        batch_size=args.batch_size,
        hidden_dim=args.hidden_dim,
        forgetting_factor=args.forgetting_factor,
        ar_delta=args.ar_delta,
        rnn_ridge=args.rnn_ridge,
        random_seed=args.random_seed,
    )
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
