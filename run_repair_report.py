#!/usr/bin/env python3
from aqpy.common.resources import limit_address_space
limit_address_space(256)
import argparse
from aqpy.forecast.repair_report import build

p=argparse.ArgumentParser(description='Create verified model-by-model repair dispositions')
p.add_argument('--run',action='append',required=True,dest='runs')
p.add_argument('--output-directory',required=True)
a=p.parse_args()
build(a.runs,a.output_directory)
