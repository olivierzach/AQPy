#!/usr/bin/env python3
from aqpy.common.resources import limit_address_space
limit_address_space(128)
import argparse
import json
from aqpy.common.sensor_backup import backup

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Stream daily raw sensor partitions with age and disk rotation')
    p.add_argument('--directory',default='sensor-backups')
    p.add_argument('--keep-days',type=int,default=365)
    p.add_argument('--max-mib',type=int,default=512)
    args=p.parse_args()
    print(json.dumps(backup(args.directory,args.keep_days,args.max_mib*1024**2),indent=2))
