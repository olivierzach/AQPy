#!/usr/bin/env python3
from aqpy.common.resources import limit_address_space
limit_address_space(128)
import argparse
import datetime as dt
from aqpy.forecast.repair_inventory import snapshot,analyze

p=argparse.ArgumentParser(description='Freeze evidence for targeted repair without modifying production')
p.add_argument('--directory',required=True)
p.add_argument('--spec-file',default='configs/model_specs.json')
p.add_argument('--end',type=dt.datetime.fromisoformat)
p.add_argument('--max-mib',type=int,default=512)
p.add_argument('--analyze',action='store_true')
a=p.parse_args()
if a.end and a.end.tzinfo is None:p.error('End timestamp must include timezone')
if a.max_mib<=0:p.error('Storage budget must be positive')
if a.analyze:analyze(a.directory)
else:snapshot(a.directory,a.spec_file,a.end,a.max_mib)
