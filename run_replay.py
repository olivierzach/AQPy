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
from aqpy.forecast.specs import load_model_specs, filter_specs


def timestamp(value):
    result = dt.datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise argparse.ArgumentTypeError('Include timezone, e.g. 2026-09-12T00:00:00+00:00')
    return result


def main():
    p = argparse.ArgumentParser(description='Isolated chronological replay of configured model families')
    p.add_argument('action', choices=['init','run','status','export'])
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
        specs = filter_specs(load_model_specs(args.spec_file), model_names=list(filter(None,args.models.split(','))),
                             families=list(filter(None,args.families.split(','))))
        result = replay.initialize(args.run_dir,specs,args.start,args.end,args.interval,args.max_mib*1024**2)
    elif args.action == 'run':
        result = replay.run(args.run_dir,args.seconds)
    elif args.action == 'export':
        result = replay.export(args.run_dir)
    else:
        result = replay.status(args.run_dir)
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
