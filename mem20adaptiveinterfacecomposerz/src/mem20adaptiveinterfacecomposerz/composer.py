from __future__ import annotations
import hashlib, re, uuid
from typing import Any
from .model import Capability, UserIntent, InterfacePlan, JobState, canonical_json
from .security import permits_risk, automatic_action_allowed

TOKEN_RE=re.compile(r"[a-z0-9_\-]+",re.I)

def tokens(text:str)->set[str]: return {x.lower() for x in TOKEN_RE.findall(text)}

def semantic_score(intent:UserIntent, cap:Capability) -> float:
    it=tokens(" ".join((intent.task,*intent.goals,*intent.required_tags,*intent.preferred_actions)))
    ct=tokens(" ".join((cap.title,cap.description,*cap.tags,*cap.actions)))
    overlap=len(it&ct)/max(1,len(it|ct))
    action_bonus=0.12*len(set(a.lower() for a in intent.preferred_actions)&set(a.lower() for a in cap.actions))
    tag_bonus=0.08*len(set(t.lower() for t in intent.required_tags)&set(t.lower() for t in cap.tags))
    latency_penalty=min(cap.latency_ms/10000,0.15); cost_penalty=min(cap.cost/10,0.15)
    return max(0.0,min(1.0,overlap+action_bonus+tag_bonus+0.2-latency_penalty-cost_penalty))

class InterfaceComposer:
    MAX_SELECTED=12
    MAX_CONTROLS=64

    def compose(self,job_id:str,intent:UserIntent,capabilities:list[Capability],mode:str,feedback_weights:dict[str,float]|None=None)->InterfacePlan:
        intent.validate(); feedback_weights=feedback_weights or {}
        viable=[]; blocked=[]
        required={t.lower() for t in intent.required_tags}
        for cap in capabilities:
            cap.validate()
            if cap.capability_id in intent.prohibited_capabilities: blocked.append(cap.capability_id); continue
            if not permits_risk(cap.risk,intent.max_risk): blocked.append(cap.capability_id); continue
            if required and not required.issubset({t.lower() for t in cap.tags}): continue
            score=semantic_score(intent,cap)+max(-0.1,min(0.1,feedback_weights.get(cap.capability_id,0.0)))
            viable.append((score,cap))
        viable.sort(key=lambda x:(x[0],x[1].capability_id),reverse=True)
        chosen=viable[:self.MAX_SELECTED]
        if not chosen:
            confidence=0.05; bottlenecks=["no_compatible_capabilities"]
        else:
            confidence=min(0.99,0.45+sum(s for s,_ in chosen[:3])/max(1,min(3,len(chosen)))*0.5)
            bottlenecks=[]
        if blocked:bottlenecks.append(f"safety_or_policy_blocked:{len(blocked)}")
        controls=[]; commands=[]; selected=[]; requires_confirmation=False
        for score,cap in chosen:
            selected.append({"capability_id":cap.capability_id,"title":cap.title,"score":round(score,5),"risk":cap.risk,"version":cap.version})
            for action in cap.actions[:8]:
                auto=intent.auto_execute and automatic_action_allowed(cap.risk)
                if intent.auto_execute and not auto: requires_confirmation=True
                control={"id":f"{cap.capability_id}:{action}","label":action.replace("_"," ").title(),"kind":"action","capability_id":cap.capability_id,"action":action,"risk":cap.risk,"automatic_allowed":auto}
                controls.append(control); commands.append({"command":action,"capability_id":cap.capability_id,"requires_confirmation":not automatic_action_allowed(cap.risk)})
                if len(controls)>=self.MAX_CONTROLS:break
            if len(controls)>=self.MAX_CONTROLS:break
        sections=[
            {"id":"task","title":"Current Job","kind":"status","content":{"task":intent.task,"state":JobState.RUNNING.value,"mode":mode}},
            {"id":"actions","title":"Task Actions","kind":"controls","controls":controls},
            {"id":"inspector","title":"Live Inspector","kind":"event_stream","filters":[job_id]},
            {"id":"recovery","title":"Recovery","kind":"recovery","controls":[{"id":"cancel","label":"Cancel Job"},{"id":"retry","label":"Retry Failed Step"}]},
        ]
        alternatives=[{"capability_id":c.capability_id,"score":round(s,5)} for s,c in viable[self.MAX_SELECTED:self.MAX_SELECTED+5]]
        explanation={"strategy":"constraint_filter+semantic_match+telemetry_cost_schedule","candidate_count":len(capabilities),"viable_count":len(viable),"blocked":blocked,"hard_safety_preserved":True}
        pid="plan_"+uuid.uuid4().hex
        return InterfacePlan(pid,job_id,intent.task,selected,sections,commands,round(confidence,5),alternatives,bottlenecks,explanation,requires_confirmation,mode,job_state=JobState.RUNNING.value)

    def rebuild(self,plan:InterfacePlan,new_job_state:str,progress:float|None=None,artifact:dict[str,Any]|None=None)->InterfacePlan:
        d=plan.to_dict(); d["generation"]=plan.generation+1; d["job_state"]=new_job_state
        d["sections"]=[dict(s) for s in plan.sections]
        status=dict(d["sections"][0]); content=dict(status.get("content",{})); content["state"]=new_job_state
        if progress is not None:content["progress"]=max(0.0,min(1.0,float(progress)))
        if artifact is not None:content["latest_artifact"]=artifact
        status["content"]=content; d["sections"][0]=status
        d["explanation"]=dict(d["explanation"],rebuild_reason="job_state_changed")
        return InterfacePlan.from_dict(d)

    @staticmethod
    def cache_key(intent:UserIntent,capabilities:list[Capability],mode:str)->str:
        payload={"intent":intent.to_dict(),"caps":[c.to_dict() for c in sorted(capabilities,key=lambda c:c.capability_id)],"mode":mode}
        return hashlib.sha256(canonical_json(payload).encode()).hexdigest()
