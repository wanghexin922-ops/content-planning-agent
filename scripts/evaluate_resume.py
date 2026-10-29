"""Verify terminal failure recovery in three separate CLI processes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8')
sys.path.insert(0,str(ROOT/'src'))
from content_planner.common import write_json, read_json


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['mock','live'],default='mock')
    args=parser.parse_args()
    out=ROOT/'examples'/f'{args.mode}_resume'
    if out.exists():
        shutil.copytree(out,ROOT/'examples/history'/(args.mode+'-resume-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')))
    out.mkdir(parents=True,exist_ok=True)
    request={'request_id':'terminal-failure-recovery','theme':'推广视频字幕工具','audience':'短视频创作者','budget':10,'deadline':'2026-10-29T18:00:00+08:00'}
    write_json(out/'input.json',request)
    records=[]
    with tempfile.TemporaryDirectory(prefix='planner-resume-') as tmp:
        db=Path(tmp)/'state.sqlite'
        for name, extra in [('first_run',['--fail','save_plan:-1']),('resumed',['--resume']),('repeated',[])]:
            command=[sys.executable,str(ROOT/'planner.py'),'--mode',args.mode,'--input',str(out/'input.json'),'--db',str(db),'--out',str(out/name),'--now','2026-10-28T10:00:00+08:00',*extra]
            process=subprocess.run(command,cwd=ROOT,env=dict(os.environ,PYTHONIOENCODING='utf-8'),capture_output=True,text=True,encoding='utf-8',timeout=300)
            records.append({'stage':name,'exit_code':process.returncode,'mode':args.mode,'extra_arguments':extra})
            if not (out/name/'output.json').exists():
                write_json(out/'execution-error.json',{'stage':name,'exit_code':process.returncode,'message':process.stderr})
                print('CLI execution failed; see execution-error.json')
                return 1
        a,b,c=[read_json(out/name/'output.json') for name in ('first_run','resumed','repeated')]
        with closing(sqlite3.connect(db)) as connection:
            plans=connection.execute('SELECT count(*) FROM plans').fetchone()[0]
        new_steps=b['steps'][len(a['steps']):]
        checks={
            'first_terminal_failed':a['status']=='failed' and not a['saved'],
            'resumed_completed':b['status']=='completed' and b['saved'],
            'failure_history_unchanged':b['steps'][:len(a['steps'])]==a['steps'],
            'successful_artifacts_unchanged':a['successful_artifacts']==b['successful_artifacts'],
            'no_repeated_search_or_script':not any(s['tool'] in ('search_materials','generate_script') for s in new_steps),
            'exactly_one_plan':plans==1,
            'repeat_no_new_tools':c['replayed'] and c['tool_calls']==b['tool_calls'] and c['plan_id']==b['plan_id'],
            'exit_codes':[r['exit_code'] for r in records]==[2,0,0],
        }
        write_json(out/'evaluation-summary.json',{'mode':args.mode,'executed_at':datetime.now(timezone.utc).isoformat(),'fixed_business_clock':'2026-10-28T10:00:00+08:00','checks':checks,'passed':all(checks.values()),'processes':records,'resume_actions':[s['tool'] for s in new_steps]})
        print(json.dumps({'mode':args.mode,'passed':all(checks.values()),'checks':checks},ensure_ascii=False))
        return 0 if all(checks.values()) else 1


if __name__=='__main__':
    raise SystemExit(main())
