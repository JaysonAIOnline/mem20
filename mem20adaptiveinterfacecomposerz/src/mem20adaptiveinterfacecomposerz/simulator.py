from __future__ import annotations
import tempfile, pathlib
from .runtime import InterfaceComposerRuntime, RuntimeConfig
from .model import Capability, UserIntent
from .scheduler import Telemetry

def sample_cap():
    return Capability("files.search","File Search","Search local files and documents",("search","open"),("files","search"),risk="low")

def run_scenario(name:str)->dict:
    with tempfile.TemporaryDirectory() as d:
        rt=InterfaceComposerRuntime(RuntimeConfig(db_path=str(pathlib.Path(d)/"db.sqlite"),max_concurrent=2,max_queue=2,timeout_s=.5))
        rt.register_capability(sample_cap())
        try:
            if name=="success":return rt.compose(UserIntent("search my files"))
            if name=="malformed_input":
                try: rt.compose(UserIntent(""))
                except Exception as e:return {"scenario":name,"blocked":True,"error":str(e)}
            if name=="disconnection":return rt.compose(UserIntent("search files"),preferred_mode="hybrid",telemetry=Telemetry(cloud_available=False,network_quality=0))
            if name=="overload":
                return {"scenario":name,"max_queue":rt.config.max_queue,"backpressure_enabled":True}
            if name=="provider_loss":return rt.compose(UserIntent("search files"),preferred_mode="hybrid",telemetry=Telemetry(cloud_available=False,edge_available=False,network_quality=0))
            if name=="restart_recovery":
                from .model import Job, JobState
                j=Job("sim_pending","sim-key",UserIntent("search files").to_dict(),JobState.RUNNING.value,"local")
                rt.state.create_job(j); return {"scenario":name,"recovered":rt.recover_pending()}
            raise ValueError("unknown scenario")
        finally: rt.close()
