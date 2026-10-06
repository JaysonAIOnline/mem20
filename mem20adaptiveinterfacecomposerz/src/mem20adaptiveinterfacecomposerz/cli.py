from __future__ import annotations
import argparse,json,tempfile
from .runtime import InterfaceComposerRuntime,RuntimeConfig
from .model import Capability,UserIntent
from .api import make_server
from .simulator import run_scenario
from .benchmark import benchmark

def main():
    p=argparse.ArgumentParser(prog="mem20adaptiveinterfacecomposerz");p.add_argument("--db",default="interface_composer.db");sp=p.add_subparsers(dest="cmd",required=True)
    a=sp.add_parser("register");a.add_argument("json_file")
    a=sp.add_parser("compose");a.add_argument("task");a.add_argument("--mode",choices=["local","hybrid","cloud"])
    sp.add_parser("capabilities");sp.add_parser("jobs")
    a=sp.add_parser("serve");a.add_argument("--host",default="127.0.0.1");a.add_argument("--port",type=int,default=8783)
    a=sp.add_parser("simulate");a.add_argument("scenario",choices=["success","malformed_input","disconnection","overload","provider_loss","restart_recovery"])
    a=sp.add_parser("benchmark");a.add_argument("--runs",type=int,default=20)
    args=p.parse_args()
    if args.cmd=="simulate":print(json.dumps(run_scenario(args.scenario),indent=2));return
    if args.cmd=="benchmark":print(json.dumps(benchmark(args.runs),indent=2));return
    rt=InterfaceComposerRuntime(RuntimeConfig(db_path=args.db))
    try:
        if args.cmd=="register":print(json.dumps({"revision":rt.register_capability(Capability.from_dict(json.load(open(args.json_file))))},indent=2))
        elif args.cmd=="compose":print(json.dumps(rt.compose(UserIntent(args.task),preferred_mode=args.mode),indent=2))
        elif args.cmd=="capabilities":print(json.dumps(rt.query_capabilities(),indent=2))
        elif args.cmd=="jobs":print(json.dumps([j.to_dict() for j in rt.state.list_jobs()],indent=2))
        elif args.cmd=="serve":
            s=make_server(rt,args.host,args.port);print(f"http://{args.host}:{args.port}");s.serve_forever()
    finally:
        if args.cmd!="serve":rt.close()
if __name__=="__main__":main()
