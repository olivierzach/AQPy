#!/usr/bin/env python3
from aqpy.common.resources import limit_address_space
limit_address_space(128)
import argparse
import json
import os
import datetime as dt
import subprocess
from pathlib import Path
from aqpy.forecast.health import check_health
from aqpy.forecast.specs import load_model_specs


def main():
    p=argparse.ArgumentParser(description='Fail visibly on stale or non-finite current AQPy data')
    p.add_argument('--spec-file',default='configs/model_specs.json')
    p.add_argument('--output',default='health/status.json')
    p.add_argument('--backup-directory',default='sensor-backups')
    p.add_argument('--sensor-age',type=int,default=300)
    p.add_argument('--forecast-age',type=int,default=1800)
    p.add_argument('--training-age',type=int,default=7200)
    args=p.parse_args()
    if min(args.sensor_age,args.forecast_age,args.training_age)<=0:
        p.error('Age thresholds must be positive')
    try:
        result=check_health(load_model_specs(args.spec_file),args.sensor_age,args.forecast_age,args.training_age)
        checks=subprocess.run(['systemctl','show','aqi.service','aqi-train-online.service',
            'aqi-forecast.service','aqi-retention.service','aqi-sensor-backup.service',
            '--property=Id,Result,ActiveState'],capture_output=True,text=True,timeout=10)
        if checks.returncode:
            result['failures'].append({'error':'Cannot inspect service health: '+checks.stderr.strip()})
        else:
            for block in checks.stdout.strip().split('\n\n'):
                properties=dict(line.split('=',1) for line in block.splitlines() if '=' in line)
                if properties.get('Result')!='success' or (properties.get('Id')=='aqi.service' and properties.get('ActiveState')!='active'):
                    result['failures'].append({'service':properties.get('Id'),'error':'Service is not healthy','state':properties})
        try:
            backup=json.loads((Path(args.backup_directory)/'status.json').read_text())
            age=(dt.datetime.now(dt.timezone.utc)-dt.datetime.fromisoformat(backup['completed_at'])).total_seconds()
            if backup.get('status')!='ok' or age>30*3600 or backup.get('partitions',0)<2:
                raise ValueError('Sensor backup is stale or incomplete')
        except Exception as exc:
            result['failures'].append({'error':'Backup health: '+str(exc)})
        result['status']='failed' if result['failures'] else 'ok'
    except Exception as exc:
        result={'status':'failed','failures':[{'error':str(exc)}]}
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    staged=path.with_suffix('.tmp');staged.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');os.replace(staged,path)
    print(json.dumps(result,indent=2,allow_nan=False),flush=True)
    return 1 if result['status']=='failed' else 0

if __name__=='__main__':
    raise SystemExit(main())
