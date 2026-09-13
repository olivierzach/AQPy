#!/usr/bin/env python3
from aqpy.common.resources import limit_address_space
limit_address_space(256)
import os
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import argparse
from aqpy.forecast.targeted_repair import prepare,run

p=argparse.ArgumentParser(description='Repair only profiled forecast defects and gaps')
p.add_argument('action',choices=['prepare','run','finalize','validate','publish'])
p.add_argument('--directory',required=True)
p.add_argument('--ar-replay')
p.add_argument('--seconds',type=int,default=45)
a=p.parse_args()
if a.action=='prepare':prepare(a.directory,a.ar_replay)
elif a.action=='run':run(a.directory,a.seconds)
elif a.action=='finalize':
    from aqpy.forecast.repair_export import finalize
    finalize(a.directory)
elif a.action=='publish':
    from aqpy.forecast.repair_publish import publish
    publish(a.directory)
else:
    from aqpy.forecast.repair_validation import audit
    raise SystemExit(0 if audit(a.directory)['status']=='PASS' else 1)
