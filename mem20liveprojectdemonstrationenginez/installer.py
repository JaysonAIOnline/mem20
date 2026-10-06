from __future__ import annotations
import argparse, json, shutil, time
from pathlib import Path

def install(source,target):
    source=Path(source).resolve(); target=Path(target).resolve(); backup=None
    if target.exists():
        backup=target.with_name(target.name+'.rollback-'+str(int(time.time()*1000)))
        shutil.move(str(target),str(backup))
    try:
        shutil.copytree(source,target,ignore=shutil.ignore_patterns('state','*.sqlite3','__pycache__'))
    except Exception:
        if target.exists(): shutil.rmtree(target)
        if backup and backup.exists(): shutil.move(str(backup),str(target))
        raise
    return {'installed':str(target),'rollback_backup':str(backup) if backup else None}

def rollback(target,backup):
    target=Path(target); backup=Path(backup)
    if target.exists(): shutil.rmtree(target)
    shutil.move(str(backup),str(target)); return {'restored':str(target)}

if __name__=='__main__':
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('install'); p.add_argument('source'); p.add_argument('target')
    p=sub.add_parser('rollback'); p.add_argument('target'); p.add_argument('backup')
    a=ap.parse_args(); print(json.dumps(install(a.source,a.target) if a.cmd=='install' else rollback(a.target,a.backup),indent=2))
