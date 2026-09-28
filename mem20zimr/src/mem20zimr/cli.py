from __future__ import annotations
import argparse, json, os
from pathlib import Path
from .runtime import MicroappRuntime
from .api import serve
from .builder import build
from .simulator import run as simulate, SCENARIOS
from .benchmark import benchmark

import functools

try:
    from mem20cliz import json_main
except ImportError as _exc:  # never fail silently: a hidden fallback looks like success
    import sys as _sys

    def json_main(func):
        @functools.wraps(func)
        def _warn(*a, **k):
            _sys.stderr.write(
                "warning: mem20cliz unavailable, --json disabled for this CLI (%s)\n" % _exc
            )
            return func(*a, **k)

        return _warn

def runtime(args):
    trust={args.signer:args.secret} if getattr(args,"secret",None) else {}
    endpoints={"edge":getattr(args,"edge_endpoint",None),"cloud":getattr(args,"cloud_endpoint",None)}
    return MicroappRuntime(args.state,trust,endpoints,max_concurrent=getattr(args,"max_concurrent",4))

@json_main
def main():
    p=argparse.ArgumentParser(prog="fs-microapp"); p.add_argument("--state",default=str(Path.home()/".freestack/rm002/state.db")); p.add_argument("--signer",default="lab"); p.add_argument("--secret",default=os.environ.get("FREESTACK_SIGNING_SECRET","dev-secret")); p.add_argument("--edge-endpoint",default=os.environ.get("FREESTACK_EDGE_ENDPOINT")); p.add_argument("--cloud-endpoint",default=os.environ.get("FREESTACK_CLOUD_ENDPOINT")); p.add_argument("--max-concurrent",type=int,default=4)
    s=p.add_subparsers(dest="cmd",required=True)
    b=s.add_parser("build"); b.add_argument("source"); b.add_argument("output"); b.add_argument("--app-id",required=True); b.add_argument("--version",default="1.0.0"); b.add_argument("--kind",choices=["python","web"],default="python"); b.add_argument("--entrypoint",required=True); b.add_argument("--modes",default="local")
    i=s.add_parser("inspect"); i.add_argument("bundle")
    l=s.add_parser("launch"); l.add_argument("bundle"); l.add_argument("--payload",default="{}"); l.add_argument("--mode")
    a=s.add_parser("serve"); a.add_argument("--host",default="127.0.0.1"); a.add_argument("--port",type=int,default=8765)
    j=s.add_parser("jobs")
    c=s.add_parser("cancel"); c.add_argument("job_id")
    sim=s.add_parser("simulate"); sim.add_argument("bundle"); sim.add_argument("scenario",choices=SCENARIOS)
    bench=s.add_parser("benchmark"); bench.add_argument("bundle"); bench.add_argument("--runs",type=int,default=5)
    args=p.parse_args()
    if args.cmd=="build": print(build(args.source,args.output,app_id=args.app_id,version=args.version,kind=args.kind,entrypoint=args.entrypoint,signer=args.signer,secret=args.secret,supported_modes=args.modes.split(",")))
    elif args.cmd=="inspect": print(json.dumps(runtime(args).inspect(args.bundle).to_dict(),indent=2))
    elif args.cmd=="launch": print(json.dumps(runtime(args).launch(args.bundle,json.loads(args.payload),preferred_mode=args.mode).__dict__,indent=2,default=str))
    elif args.cmd=="serve": serve(runtime(args),args.host,args.port)
    elif args.cmd=="jobs": print(json.dumps(runtime(args).store.list_jobs(),indent=2))
    elif args.cmd=="cancel": runtime(args).cancel(args.job_id); print(args.job_id)
    elif args.cmd=="simulate":
        r=simulate(runtime(args),args.bundle,args.scenario); print(json.dumps(getattr(r,"__dict__",r),indent=2,default=str))
    elif args.cmd=="benchmark": print(json.dumps(benchmark(runtime(args),args.bundle,args.runs),indent=2))

if __name__=="__main__": main()
