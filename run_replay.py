#!/usr/bin/env python3
from aqpy.common.resources import limit_address_space
limit_address_space(256)
import os
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import argparse
import datetime as dt
import json
import logging
from aqpy.forecast import replay
from aqpy.forecast.specs import load_model_specs, filter_specs, FAMILY_TO_MODEL_TYPES


def timestamp(value):
    result = dt.datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise argparse.ArgumentTypeError('Include timezone, e.g. 2026-09-12T00:00:00+00:00')
    return result


def main():
    p = argparse.ArgumentParser(description='Isolated chronological replay of configured model families')
    p.add_argument('action', choices=['init','run','status','export','validate'])
    p.add_argument('--run-dir', required=True)
    p.add_argument('--spec-file', default='configs/model_specs.json')
    p.add_argument('--models', default='')
    p.add_argument('--families', default='')
    p.add_argument('--start', type=timestamp)
    p.add_argument('--end', type=timestamp)
    p.add_argument('--interval', type=int, default=600)
    p.add_argument('--seconds', type=int, default=45)
    p.add_argument('--max-mib', type=int, default=1024)
    args = p.parse_args()
    if args.interval <= 0 or args.seconds <= 0 or args.max_mib <= 0:
        p.error('Interval, seconds and storage budget must be positive')
    if args.action == 'init':
        if not args.models and not args.families:
            p.error('Select --models or --families explicitly before initializing a replay')
        all_specs = load_model_specs(args.spec_file)
        names = [v.strip() for v in args.models.split(',') if v.strip()]
        families = [v.strip() for v in args.families.split(',') if v.strip()]
        unknown = set(names)-{s['model_name'] for s in all_specs}
        unknown_families = set(families)-set(FAMILY_TO_MODEL_TYPES)
        if unknown or unknown_families:
            p.error(f'Unknown models: {sorted(unknown)}; unknown families: {sorted(unknown_families)}')
        specs = filter_specs(all_specs, model_names=names, families=families)
        if not specs:
            p.error('Selection matched no models')
        result = replay.initialize(args.run_dir,specs,args.start,args.end,args.interval,args.max_mib*1024**2)
    elif args.action == 'run':
        result = replay.run(args.run_dir,args.seconds)
    elif args.action == 'export':
        result = replay.export(args.run_dir)
    elif args.action == 'validate':
        result = replay.validate(args.run_dir)
        print(json.dumps(result,indent=2,allow_nan=False))
        if result['status'] != 'PASS':
            raise SystemExit(1)
        return
    else:
        result = replay.status(args.run_dir)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
