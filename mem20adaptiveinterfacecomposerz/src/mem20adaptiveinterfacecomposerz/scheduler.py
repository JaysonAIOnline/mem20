from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from .model import ExecutionMode

@dataclass
class Telemetry:
    local_latency_ms: float = 8.0
    cloud_latency_ms: float = 80.0
    local_cost: float = 0.0
    cloud_cost: float = 0.01
    network_quality: float = 1.0
    local_load: float = 0.1
    cloud_available: bool = False
    edge_available: bool = False

@dataclass
class ScheduleDecision:
    mode: str
    confidence: float
    scores: dict[str,float]
    alternatives: list[dict[str,Any]]
    bottlenecks: list[str]
    explanation: dict[str,Any]

class Scheduler:
    def __init__(self) -> None:
        self.mode_biases={"local":0.0,"hybrid":0.0,"cloud":0.0}

    def apply_feedback(self, mode:str, delta:float) -> None:
        if mode in self.mode_biases:
            self.mode_biases[mode]=max(-0.2,min(0.2,self.mode_biases[mode]+float(delta)))

    def choose(self,t:Telemetry,preferred:str|None=None) -> ScheduleDecision:
        # Measured constraints: latency, load, network, availability and cost.
        local=1.0-(min(t.local_latency_ms,1000)/1500)-0.35*max(0,min(t.local_load,1))-min(t.local_cost,1)*0.2
        hybrid=(0.58+0.25*t.network_quality-0.15*min(t.cloud_cost,1)) if (t.cloud_available or t.edge_available) else -1.0
        cloud=(0.65+0.25*t.network_quality-(min(t.cloud_latency_ms,2000)/3000)-0.25*min(t.cloud_cost,1)) if t.cloud_available else -1.0
        scores={"local":local,"hybrid":hybrid,"cloud":cloud}
        for k in scores:scores[k]+=self.mode_biases[k]
        if preferred in scores and scores[preferred]>-0.9:scores[preferred]+=0.08
        ordered=sorted(scores.items(),key=lambda kv:(kv[1],kv[0]),reverse=True)
        mode=ordered[0][0]; gap=ordered[0][1]-ordered[1][1]
        bottlenecks=[]
        if t.network_quality<0.4:bottlenecks.append("degraded_network")
        if t.local_load>0.8:bottlenecks.append("local_saturation")
        if not t.cloud_available:bottlenecks.append("cloud_unavailable")
        return ScheduleDecision(mode=mode,confidence=max(0.05,min(0.99,0.6+gap/2)),scores={k:round(v,5) for k,v in scores.items()},alternatives=[{"mode":m,"score":round(s,5)} for m,s in ordered[1:]],bottlenecks=bottlenecks,explanation={"policy":"telemetry_cost_aware_v1","inputs":t.__dict__,"biases":dict(self.mode_biases)})
