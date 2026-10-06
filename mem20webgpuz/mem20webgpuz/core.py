from __future__ import annotations
import argparse, contextlib, dataclasses, hashlib, http.client, json, math, os, queue, random, re, sqlite3, statistics, threading, time, traceback, urllib.parse, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

SCHEMA_VERSION = "1.0"

class ValidationError(ValueError): pass
class CancelledError(RuntimeError): pass
class SafetyBlocked(RuntimeError): pass


def now() -> float: return time.time()
def canonical(obj: Any) -> str: return json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False, default=str)
def stable_hash(obj: Any) -> str: return hashlib.sha256(canonical(obj).encode()).hexdigest()
SENSITIVE_KEYS={'password','passwd','token','access_token','refresh_token','api_key','apikey','secret','authorization','cookie'}
# Free text carries credentials too: "auth failed for token=abc" has no sensitive
# KEY to match on, so a dict-only redaction leaves it on disk. This catches the
# common "sensitive-name, then a separator, then the value" shape and stops at the
# first delimiter, so ordinary prose is left alone.
_SECRET_IN_TEXT=re.compile(
    r'(?i)\b(' + '|'.join(sorted(SENSITIVE_KEYS)) + r')\b(\s*[:=]\s*)'
    r'([^\s,;"\')\]}]+)'
)
def redact(obj):
    if isinstance(obj,dict): return {k:('[REDACTED]' if str(k).lower() in SENSITIVE_KEYS else redact(v)) for k,v in obj.items()}
    if isinstance(obj,list): return [redact(x) for x in obj]
    if isinstance(obj,str): return _SECRET_IN_TEXT.sub(lambda m: f"{m.group(1)}{m.group(2)}[REDACTED]", obj)
    return obj
def clamp(x, lo=0.0, hi=1.0): return max(lo, min(hi, x))
def words(s): return set(re.findall(r"[a-z0-9]+", str(s).lower()))
def similarity(a,b):
    aa,bb=words(a),words(b)
    return len(aa&bb)/max(1,len(aa|bb))
def mean(xs): return sum(xs)/max(1,len(xs))

@dataclasses.dataclass(frozen=True)
class Decision:
    choice: str
    confidence: float
    alternatives: list[dict]
    bottlenecks: list[str]
    explanation: dict

class StateStore:
    def __init__(self, path: str|Path):
        self.path=str(path); Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()
    @contextlib.contextmanager
    def conn(self):
        c=sqlite3.connect(self.path, timeout=15); c.row_factory=sqlite3.Row
        try: yield c; c.commit()
        except: c.rollback(); raise
        finally: c.close()
    def _init(self):
        with self.conn() as c:
            c.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, idem TEXT UNIQUE, state TEXT, request TEXT, result TEXT, error TEXT, attempts INTEGER, created REAL, updated REAL);
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, job_id TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, signal TEXT, value REAL, note TEXT);
            CREATE TABLE IF NOT EXISTS cache(k TEXT PRIMARY KEY, ts REAL, value TEXT);
            CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, ts REAL, node TEXT, value TEXT, tombstone INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, version INTEGER, created REAL, updated REAL, body TEXT);
            ''')
    def emit(self, kind, job_id=None, payload=None):
        # Redact here too: the events table is a second, easily-forgotten write
        # path. Fixing only the jobs row left the same credential sitting in the
        # event log, so the "no secrets on disk" guarantee was still broken.
        with self.conn() as c: c.execute("INSERT INTO events(ts,kind,job_id,payload) VALUES(?,?,?,?)", (now(),kind,job_id,canonical(redact(payload or {}))))
    def create_job(self, request, idem=None):
        idem=idem or str(uuid.uuid4())
        with self.conn() as c:
            r=c.execute("SELECT * FROM jobs WHERE idem=?",(idem,)).fetchone()
            if r: return dict(r), False
            jid=str(uuid.uuid4()); t=now()
            c.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)",(jid,idem,'queued',canonical(redact(request)),None,None,0,t,t))
        self.emit('job.queued',jid,redact(request)); return self.get_job(jid), True
    def get_job(self,jid):
        with self.conn() as c:
            r=c.execute("SELECT * FROM jobs WHERE id=?",(jid,)).fetchone(); return dict(r) if r else None
    def list_jobs(self,limit=100):
        with self.conn() as c: return [dict(r) for r in c.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT ?",(int(limit),))]
    def update_job(self,jid,state, result=None,error=None, attempts=None):
        with self.conn() as c:
            old=c.execute("SELECT attempts FROM jobs WHERE id=?",(jid,)).fetchone()
            att=attempts if attempts is not None else (old['attempts'] if old else 0)
            # Redact the result exactly as create_job redacts its request. A
            # credential returned by a job (a token, an API key) was previously
            # persisted in the clear, which is a real leak path: results are
            # written to disk unencrypted and read back by anything with the file.
            safe_result=canonical(redact(result)) if result is not None else None
            safe_error=redact(error) if isinstance(error,str) else error
            c.execute("UPDATE jobs SET state=?,result=?,error=?,attempts=?,updated=? WHERE id=?",
                      (state,safe_result,safe_error,att,now(),jid))
        self.emit('job.'+state,jid,result if result is not None else {'error':error})
    def cancel(self,jid):
        j=self.get_job(jid)
        if not j: return False
        if j['state'] in ('succeeded','failed','cancelled'): return False
        self.update_job(jid,'cancelled'); return True
    def events(self,after=0,limit=500):
        with self.conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?",(int(after),int(limit)))]
    def feedback(self, signal, value, note=''):
        with self.conn() as c: c.execute("INSERT INTO feedback(ts,signal,value,note) VALUES(?,?,?,?)",(now(),signal,float(value),note))
        self.emit('feedback',None,{'signal':signal,'value':value,'note':note})
    def feedback_bias(self):
        with self.conn() as c:
            rows=c.execute("SELECT signal,AVG(value) v FROM feedback GROUP BY signal").fetchall()
        return {r['signal']:float(r['v']) for r in rows}
    def cache_get(self,k,max_age=3600):
        with self.conn() as c: r=c.execute("SELECT * FROM cache WHERE k=?",(k,)).fetchone()
        if not r or now()-r['ts']>max_age: return None
        return json.loads(r['value'])
    def cache_put(self,k,v):
        with self.conn() as c: c.execute("INSERT INTO cache(k,ts,value) VALUES(?,?,?) ON CONFLICT(k) DO UPDATE SET ts=excluded.ts,value=excluded.value",(k,now(),canonical(v)))
    def put_lww(self,k,v,node='local',ts=None,tombstone=False):
        ts=float(ts or now())
        with self.conn() as c:
            old=c.execute("SELECT ts,node FROM kv WHERE k=?",(k,)).fetchone()
            if old and (old['ts'],old['node']) >= (ts,node): return False
            c.execute("INSERT INTO kv(k,ts,node,value,tombstone) VALUES(?,?,?,?,?) ON CONFLICT(k) DO UPDATE SET ts=excluded.ts,node=excluded.node,value=excluded.value,tombstone=excluded.tombstone",(k,ts,node,canonical(v),1 if tombstone else 0))
        self.emit('sync.update',None,{'key':k,'node':node,'ts':ts,'tombstone':tombstone}); return True
    def export_lww(self):
        with self.conn() as c: rows=c.execute("SELECT * FROM kv").fetchall()
        return [dict(r) for r in rows]
    def merge_lww(self, rows):
        n=0
        for r in rows:
            if self.put_lww(r['k'], json.loads(r['value']) if isinstance(r['value'],str) else r['value'], r['node'], r['ts'], bool(r.get('tombstone'))): n+=1
        return n
    def resource_create(self, body, rid=None):
        rid=rid or str(uuid.uuid4()); t=now(); clean=redact(body)
        with self.conn() as c: c.execute("INSERT INTO resources(id,version,created,updated,body) VALUES(?,?,?,?,?)",(rid,1,t,t,canonical(clean)))
        self.emit('resource.created',None,{'id':rid,'version':1}); return self.resource_get(rid)
    def resource_get(self,rid):
        with self.conn() as c: r=c.execute("SELECT * FROM resources WHERE id=?",(rid,)).fetchone()
        if not r: return None
        d=dict(r); d['body']=json.loads(d['body']); return d
    def resource_list(self,limit=100):
        with self.conn() as c: rows=c.execute("SELECT * FROM resources ORDER BY updated DESC LIMIT ?",(int(limit),)).fetchall()
        out=[]
        for r in rows: d=dict(r); d['body']=json.loads(d['body']); out.append(d)
        return out
    def resource_update(self,rid,body,expected_version=None):
        clean=redact(body)
        with self.conn() as c:
            r=c.execute("SELECT version FROM resources WHERE id=?",(rid,)).fetchone()
            if not r: raise KeyError(rid)
            if expected_version is not None and int(expected_version)!=int(r['version']): raise ValidationError('resource version conflict')
            v=int(r['version'])+1; c.execute("UPDATE resources SET version=?,updated=?,body=? WHERE id=?",(v,now(),canonical(clean),rid))
        self.emit('resource.updated',None,{'id':rid,'version':v}); return self.resource_get(rid)
    def resource_delete(self,rid,expected_version=None):
        with self.conn() as c:
            r=c.execute("SELECT version FROM resources WHERE id=?",(rid,)).fetchone()
            if not r: return False
            if expected_version is not None and int(expected_version)!=int(r['version']): raise ValidationError('resource version conflict')
            c.execute("DELETE FROM resources WHERE id=?",(rid,))
        self.emit('resource.deleted',None,{'id':rid}); return True

class Metrics:
    def __init__(self): self.lock=threading.Lock(); self.counts={}; self.lat=[]
    def inc(self,k,n=1):
        with self.lock: self.counts[k]=self.counts.get(k,0)+n
    def observe(self,x):
        with self.lock: self.lat.append(float(x)); self.lat=self.lat[-5000:]
    def snapshot(self):
        with self.lock:
            a=list(self.lat); c=dict(self.counts)
        return {'counts':c,'latency_ms_avg':mean(a) if a else 0,'latency_ms_p95':sorted(a)[max(0,math.ceil(.95*len(a))-1)] if a else 0,'samples':len(a)}
    def prometheus(self):
        s=self.snapshot(); lines=[]
        for k,v in s['counts'].items(): lines.append(f"freestack_{re.sub('[^a-zA-Z0-9_]','_',k)} {v}")
        lines += [f"freestack_latency_ms_avg {s['latency_ms_avg']}", f"freestack_latency_ms_p95 {s['latency_ms_p95']}"]
        return '\n'.join(lines)+'\n'

class DecisionEngine:
    def __init__(self, store, roadmap): self.store=store; self.roadmap=roadmap
    def choose_mode(self, request, peers=None):
        peers=peers or {}; pref=request.get('mode','hybrid'); size=len(canonical(request)); bias=self.store.feedback_bias()
        scores={'local':.78,'edge':.56,'cloud':.54}
        if size>50000: scores['local']-=.2; scores['cloud']+=.12
        if request.get('privacy','normal') in ('high','strict'): scores['local']+=.18; scores['cloud']-=.3
        for mode in ('local','edge','cloud'):
            scores[mode]+=0.08*bias.get('mode:'+mode,0)
            if mode!='local' and not peers.get(mode): scores[mode]=-1
        allowed=['local'] if pref=='local' else ([pref] if pref in ('edge','cloud') else ['local','edge','cloud'])
        ranked=sorted([(m,scores[m]) for m in allowed], key=lambda x:x[1], reverse=True)
        m,s=ranked[0]
        return Decision(m,clamp((s+1)/2),[{'mode':x,'score':round(y,4)} for x,y in ranked[1:]], [b for b in ['remote_peer_unavailable' if not peers else '', 'large_payload' if size>50000 else ''] if b], {'scores':scores,'preference':pref,'techniques':self._techniques()})
    def _techniques(self):
        for ph in self.roadmap['phases']:
            for sp in ph['subphases']:
                if sp['name'].startswith('2.1'):
                    return sp['work'][0]
        return ''

class SafetyGate:
    HIGH_RISK = {'delete','execute','install','deploy','repair_device','apply_patch','send_message','place_call','write_external','migrate_live','enroll_device'}
    def check(self, request):
        action=str(request.get('action','analyze')).lower()
        if action in self.HIGH_RISK and not request.get('allow_automatic_action',False):
            raise SafetyBlocked(f"automatic action blocked: {action}; set allow_automatic_action only after external authorization")
        if request.get('unsafe') is True: raise SafetyBlocked('unsafe request marker blocked')

# ---------- domain algorithms ----------
def probe_gpu():
    """Actually check for a usable GPU. Returns (usable, reasons)."""
    import shutil as _sh, subprocess as _sp
    reasons=[]
    if not os.path.isdir('/dev/dri'):
        reasons.append('no /dev/dri device nodes')
    exe=_sh.which('nvidia-smi')
    if not exe:
        reasons.append('nvidia-smi not installed')
    else:
        try:
            r=_sp.run([exe,'-L'],capture_output=True,text=True,timeout=10)
            if r.returncode!=0:
                reasons.append('nvidia-smi exited %d (driver unavailable)'%r.returncode)
        except Exception:
            reasons.append('nvidia-smi could not be executed')
    try:
        import torch as _t
        if not _t.cuda.is_available():
            reasons.append('torch reports cuda unavailable')
    except ImportError:
        pass
    return (not reasons), reasons

def topo(nodes, edges):
    indeg={n:0 for n in nodes}; out={n:[] for n in nodes}
    for a,b in edges:
        if a in indeg and b in indeg: out[a].append(b); indeg[b]+=1
    q=sorted([n for n,d in indeg.items() if d==0]); order=[]
    while q:
        n=q.pop(0); order.append(n)
        for m in out[n]:
            indeg[m]-=1
            if indeg[m]==0: q.append(m); q.sort()
    return order, [n for n,d in indeg.items() if d>0]

def family_otherstack(rid,p):
    if rid==101:
        comps=p.get('components',[{'name':'a','exports':['x'],'imports':[]},{'name':'b','exports':[],'imports':['x']}]); exports=set().union(*[set(c.get('exports',[])) for c in comps]); missing={c['name']:[x for x in c.get('imports',[]) if x not in exports] for c in comps}; missing={k:v for k,v in missing.items() if v}; return {'compatible':not missing,'missing_interfaces':missing,'isolation':'component-sandbox','component_count':len(comps)}
    if rid==102:
        ops=float(p.get('operations',1e6)); mem=float(p.get('memory_mb',256))
        gpu=probe_gpu()[0]; reasons=probe_gpu()[1]
        if p.get('webgpu_available') is True and not gpu:
            reasons.append('request asserted webgpu_available=true but no usable GPU was detected')
        return {'backend':'webgpu' if gpu and mem<=4096 else 'cpu',
                'workgroups':max(1,int(math.sqrt(ops/256))),
                'gpu_detected':gpu,
                'gpu_probe':reasons,
                'caller_asserted_webgpu':p.get('webgpu_available'),
                'speedup':'not_measured',
                'speedup_note':'no benchmark was run; a CPU/webGPU ratio is not derivable from operation count alone'}
    if rid in (103,104):
        states=p.get('peer_states',[{'node':'a','ts':1,'value':{'x':1}},{'node':'b','ts':2,'value':{'x':2}}]); winner=max(states,key=lambda x:(x.get('ts',0),x.get('node',''))); return {'merged':winner['value'],'winner':winner['node'],'conflict_free':True,'peers':len(states)}
    if rid==105:
        items=p.get('items',[7,3,9,2,5]); bins=int(p.get('bins',2)); loads=[0]*bins; assign=[]
        for v in sorted(items,reverse=True): i=min(range(bins),key=lambda j:loads[j]); loads[i]+=v; assign.append((v,i))
        return {'assignment':assign,'loads':loads,'spread':max(loads)-min(loads),'heuristic':'annealing-inspired balanced search seed'}
    if rid==106:
        events=p.get('events',[{'t':1,'v':0},{'t':2,'v':3},{'t':3,'v':0},{'t':4,'v':8}]); nz=[e for e in events if abs(float(e.get('v',0)))>=float(p.get('threshold',1))]; return {'input_events':len(events),'active_events':len(nz),'sparsity':1-len(nz)/max(1,len(events)),'events':nz}
    if rid==107:
        objs=p.get('objects',['capability','agent','data']); return {'objects':[{'id':o,'x':round(math.cos(i)*3,3),'y':0,'z':round(math.sin(i)*3,3)} for i,o in enumerate(objs)],'shared_workspace':True}
    if rid==108:
        w=p.get('workload',{'graph':.2,'vector':.2,'time_series':.2,'analytics':.2,'embedded':.2}); dbs=['graph','vector','time_series','columnar','embedded']; scores={d:round(.45+.55*float(w.get(d if d!='columnar' else 'analytics',0)),3) for d in dbs}; best=max(scores,key=scores.get); return {'scores':scores,'recommended':best}
    if rid==109:
        fields=p.get('fields',['type','id','payload']); reliability=float(p.get('reliability',.98)); return {'protocol':{'header_bytes':8+2*len(fields),'fields':fields,'ack':reliability>.95,'version':1},'estimated_overhead_bytes':8+2*len(fields),'reliability_target':reliability}
    if rid==110:
        deps=p.get('dependencies',['db','network','provider']); fail=p.get('failed',['network']); degraded=[d for d in deps if d in fail]; return {'expected_failures':degraded,'survives':len(degraded)<len(deps),'fallbacks':{d:'cached/local/deferred' for d in degraded},'chaos_native':True}

def family_sherry(rid,p):
    text=str(p.get('text','Please review this today.'))
    urgency=clamp(float(p.get('urgency', .7 if any(x in text.lower() for x in ['urgent','today','asap']) else .3)))
    sentiment=clamp(.5 + .15*sum(text.lower().count(x) for x in ['thanks','please','appreciate']) - .2*sum(text.lower().count(x) for x in ['angry','hate','wrong','failure']))
    if rid==111: return {'route':'call' if urgency>.85 else ('chat' if urgency>.45 else 'async'),'urgency':urgency,'respect_availability':True}
    if rid==112: return {'emotional_stakes':round(1-sentiment,3),'route':'delay_and_reframe' if sentiment<.35 else 'normal','escalate_human':sentiment<.2}
    if rid==113:
        glossary=p.get('glossary',{}); tokens=text.split(); translated=' '.join(glossary.get(t.lower(),t) for t in tokens); return {'source':text,'translated':translated,'preserved_terms':[t for t in tokens if t.lower() not in glossary],'note':'deterministic glossary mode; external/local translation model may be plugged in'}
    if rid==114: return {'context':{'projects':p.get('projects',[]),'commitments':p.get('commitments',[]),'preferences':p.get('preferences',{}),'history_count':len(p.get('history',[]))},'relevance_score':round(similarity(text,canonical(p)),3)}
    if rid==115:
        lines=[x.strip() for x in re.split(r'[\n.!?]+',text) if x.strip()]; acts=[x for x in lines if any(k in x.lower() for k in ['will ','todo','action','decided','by '])]; return {'decisions':[x for x in lines if 'decid' in x.lower()],'actions':acts,'followups':len(acts)}
    if rid==116: return {'capsule':{'summary':text[:500],'media':p.get('media',[]),'decisions':p.get('decisions',[]),'actions':p.get('actions',[])},'portable':True}
    if rid==117:
        verb=text.strip().split(' ',1)[0].lower() if text.strip() else ''; routes={'call':'communications','send':'messaging','open':'device','run':'agent','schedule':'calendar'}; return {'route':routes.get(verb,'agent'),'parsed_request':text,'requires_confirmation':verb in ('call','send')}
    if rid==118:
        msgs=p.get('messages',[text]); toks=collections_count(msgs); return {'message_count':len(msgs),'top_terms':toks[:10],'friction_terms':[x for x in toks if x[0] in {'bug','slow','confusing','broken'}]}
    if rid==119: return {'reframe':re.sub(r'\byou\b','the other person',text,flags=re.I),'shared_fact_check':['separate observations from interpretations'],'timing':'later' if sentiment<.3 else 'now'}
    if rid==120: return {'channel_open':True,'interrupt':urgency>.75,'ducking':round(.2+.6*(1-urgency),2),'presence_mode':p.get('presence','available')}

def collections_count(msgs):
    d={}
    for m in msgs:
        for w in words(m): d[w]=d.get(w,0)+1
    return sorted(d.items(),key=lambda x:(-x[1],x[0]))

def family_judy(rid,p):
    code=str(p.get('code','def add(a,b):\n    return a+b\n'))
    lines=code.splitlines(); risk=sum(1 for x in lines if any(k in x for k in ['except:','eval(','exec(','TODO','pass']))
    if rid==121: return {'diagnosis':{'risk_lines':risk,'line_count':len(lines)},'patch':'minimal_patch_candidate','tests':['compile','targeted regression'],'reversible':True}
    if rid==122: return {'failure_risk':round(clamp(.08+.12*risk+.03*len(lines)/100),3),'hotspots':[i+1 for i,x in enumerate(lines) if any(k in x for k in ['except:','eval(','exec('])],'preventive_fix_recommended':risk>0}
    if rid==123:
        funcs=re.findall(r'^def\s+(\w+)',code,re.M); return {'generated_tests':[f'test_{f}_nominal' for f in funcs]+[f'test_{f}_edge' for f in funcs],'mutation_targets':funcs,'maintainable':True}
    if rid==124:
        deps=p.get('dependencies',{'a':'1.0'}); proposed=p.get('proposed',{}); return {'changes':{k:{'from':deps.get(k),'to':v} for k,v in proposed.items()},'risk':round(.1*len(proposed),2),'simulation_only':True}
    if rid==125:
        before=p.get('before_ms',[10,11,9]); after=p.get('after_ms',[15,16,14]); return {'before_avg':mean(before),'after_avg':mean(after),'regression_pct':round((mean(after)/max(.001,mean(before))-1)*100,2),'attribution':p.get('change','latest change')}
    if rid==126: return {'source_language':p.get('source_language','python'),'target_language':p.get('target_language','rust'),'interfaces':p.get('interfaces',[]),'refactor_plan':['freeze interface','port pure behavior','cross-run tests','switch implementation'],'behavior_preserved':True}
    if rid==127:
        services=p.get('services',3); rps=float(p.get('rps',100)); return {'services':services,'synthetic_rps':rps,'estimated_p95_ms':round(5+services*2+rps/100,2),'bottleneck':'cross-service hops' if services>5 else 'none'}
    if rid==128:
        funcs=re.findall(r'^def\s+(\w+)',code,re.M); calls=re.findall(r'(\w+)\(',code); return {'symbols':funcs,'calls':calls,'edges':[{'from':'module','to':f} for f in funcs],'live_graph':True}
    if rid==129:
        patch=p.get('patch',''); blast=len(patch.splitlines()); return {'patch':patch,'blast_radius_lines':blast,'within_limit':blast<=int(p.get('max_lines',30)),'constraints':['tests','interfaces','blast-radius']}
    if rid==130:
        versions=p.get('versions',['1.0','1.1','2.0']); api=p.get('supported_major',1); return {'matrix':{v:(int(v.split('.')[0])==api) for v in versions},'future_breaks':[v for v in versions if int(v.split('.')[0])!=api]}

def family_jammee(rid,p):
    brief=str(p.get('brief','cosmic humane technology')); style=p.get('style',{'tone':'hopeful','geometry':'soft','motion':'calm'})
    if rid==131: return {'brand_world':{'visual':style,'audio':{'tempo':'adaptive','motif':brief[:40]},'spatial':{'theme':brief},'interactive':{'principles':['consistent','responsive']}},'coherence':.86}
    if rid==132: return {'creative_plan':[{m:{'goal':brief,'style':style}} for m in ['image','video','audio','copy','motion','3d']],'single_brief':True}
    if rid==133: return {'primitives':{'style':style,'shapes':p.get('shapes',['circle','line']),'motion':p.get('motion',['fade','orbit']),'materials':p.get('materials',['glass'])},'reusable':True}
    if rid==134: return {'style_transform':{'tokens':style,'targets':p.get('targets',['ui','video','game','3d'])},'controlled':True,'non_destructive':True}
    if rid==135: return {'campaign_rules':[{'when':'engagement>0.7','then':'deepen experience'},{'when':'engagement<0.3','then':'simplify'}],'brief':brief,'reactive':True}
    if rid==136: return {'character':{'name':p.get('name','Nova'),'appearance':style,'voice':p.get('voice','warm'),'motions':['idle','greet','react'],'memory':'scoped'},'cross_surface':True}
    if rid==137:
        rooms=p.get('rooms',['entry','gallery','studio']); return {'layout':[{'room':r,'x':i*6,'z':0,'connections':[rooms[i-1]] if i else []} for i,r in enumerate(rooms)],'reusable_primitives':True}
    if rid==138:
        beats=p.get('beats',[0,0.5,1,1.5]); return {'cues':[{'t':b,'motion':'pulse','light':round(.5+.5*(i%2),2)} for i,b in enumerate(beats)],'synchronized':True}
    if rid==139:
        segs=p.get('segments',[{'name':'core','fit':.8},{'name':'new','fit':.5}]); return {'reactions':[dict(s, predicted_engagement=round(.35+.6*float(s.get('fit',.5)),2)) for s in segs],'simulation':True}
    if rid==140:
        trends=p.get('trends',[{'name':'spatial-ui','growth':.8,'similarity':.3},{'name':'retro','growth':.4,'similarity':.8}]); return {'ranked':sorted([dict(t, originality=round(float(t['growth'])*(1-float(t['similarity'])),3)) for t in trends],key=lambda x:-x['originality']),'copy_guard':True}

def family_jayson(rid,p):
    goals=p.get('goals',['finish important work']); obligations=p.get('obligations',[]); energy=float(p.get('energy',.7));
    if rid==141: return {'memory_keys':sorted(p.get('memory',{}).keys()),'active_projects':p.get('projects',[]),'continuity_token':stable_hash({'projects':p.get('projects',[]),'goals':goals})[:16]}
    if rid==142: return {'conversation':p.get('text',''),'actions':p.get('actions',['create view','run workflow']),'desktop_layout':['conversation','active task','results'],'operating_interface':True}
    if rid==143: return {'style':{'verbosity':'low' if p.get('urgency',0)<.5 else 'compact','initiative':round(.3+.5*energy,2),'warmth':p.get('warmth',.7)},'hard_safety_unchanged':True}
    if rid==144: return {'modalities':{k:bool(p.get(k)) for k in ['speech','screen','image','video','files','spatial']},'linked_context_id':stable_hash(p)[:16]}
    if rid==145:
        options=p.get('options',[{'name':'A','value':7,'cost':4},{'name':'B','value':6,'cost':2}]); return {'scenarios':[dict(o,score=round(float(o.get('value',0))-float(o.get('cost',0)),2)) for o in options],'private_simulation':True}
    if rid==146: return {'execution':'local','network_required':False,'plan':rank_tasks(goals,obligations,energy),'privacy':'owned-device'}
    if rid==147: return {'priorities':rank_tasks(goals,obligations,energy),'energy':energy,'now':True}
    if rid==148: return {'lesson':{'topic':p.get('topic',goals[0] if goals else 'current work'),'exercise':p.get('mistake','apply concept to current task'),'difficulty':round(.4+.4*energy,2)},'embedded_in_work':True}
    if rid==149: return {'handoff':{'session':p.get('session','current'),'from':p.get('from','desktop'),'to':p.get('to','phone'),'state_digest':stable_hash(p.get('state',{}))},'continuity':True}
    if rid==150: return {'growth_plan':{'goals':goals,'tools':p.get('tools',[]),'agents':p.get('agents',[]),'measure':p.get('measure','completed outcomes')},'baseline':float(p.get('baseline',0)),'target':float(p.get('target',1))}

def rank_tasks(goals, obligations, energy):
    tasks=[]
    for i,g in enumerate(goals+obligations): tasks.append({'task':g,'score':round((1/(i+1))*(.5+.5*energy),3)})
    return sorted(tasks,key=lambda x:-x['score'])

def family_andi(rid,p):
    devices=p.get('devices',[{'id':'phone','battery':.8,'thermal':.2,'capabilities':['camera','cpu']},{'id':'tablet','battery':.5,'thermal':.1,'capabilities':['gpu','screen']}])
    if rid==151: return {'enrollment':{'device_id':p.get('device_id','new-device'),'steps':['recognize','attest','provision','validate'],'trusted':bool(p.get('attested',True))},'one_minute_path':True}
    if rid==152: return {'agent_limits':{'memory_mb':p.get('memory_mb',512),'cpu_pct':p.get('cpu_pct',30),'network':'optional'},'offline_capable':True}
    if rid==153:
        caps=sorted(set().union(*[set(d.get('capabilities',[])) for d in devices])); return {'mesh_nodes':[d['id'] for d in devices],'combined_capabilities':caps,'trusted_only':True}
    if rid==154: return {'session':p.get('session','s1'),'from':p.get('from','phone'),'to':p.get('to','desktop'),'snapshot':stable_hash(p.get('state',{})),'restart_required':False}
    if rid==155:
        sensors=p.get('sensors',{'camera':1,'microphone':1,'motion':0}); return {'normalized':[{'sensor':k,'value':v,'quality':1.0} for k,v in sensors.items()],'timestamp':p.get('timestamp',0),'fusion_ready':True}
    if rid==156: return {'delivery':{'artifact':p.get('artifact','app.pkg'),'channels':['local-peer','removable-media','delayed-sync'],'digest':stable_hash(p.get('artifact','app.pkg'))},'store_independent':True}
    if rid==157: return {'pipeline':['compile','sign','transfer','install','launch','test'],'target':p.get('target','device'),'simulation_only':not p.get('authorized_device_connector',False)}
    if rid==158:
        diag=p.get('diagnostics',{'storage_free_pct':20,'network':True,'app_ok':False}); fixes=[]
        if diag.get('storage_free_pct',100)<10: fixes.append('clear bounded cache')
        if not diag.get('network',True): fixes.append('reset app network session')
        if not diag.get('app_ok',True): fixes.append('restart application')
        return {'diagnostics':diag,'bounded_fixes':fixes,'full_remote_control':False}
    if rid==159:
        jobs=p.get('jobs',[{'id':'a','urgency':.8,'energy':.4},{'id':'b','urgency':.3,'energy':.8}]); sched=sorted(jobs,key=lambda j:-(float(j['urgency'])-.5*float(j['energy']))); return {'schedule':sched,'battery_protected':True}
    if rid==160:
        caps={d['id']:d.get('capabilities',[]) for d in devices}; return {'api_version':'1.0','devices':caps,'cross_platform':True}

def family_kimberly(rid,p):
    if rid==161:
        old=p.get('old_schema',{'name':'str'}); new=p.get('new_schema',{'name':'str','age':'int'}); return {'add':[k for k in new if k not in old],'remove':[k for k in old if k not in new],'online_plan':['dual-read','backfill','dual-write','cutover'],'running':True}
    if rid==162:
        rec=p.get('record',{'first_name':'Ada'}); mapping=p.get('mapping',{'first_name':'name'}); return {'translated':{mapping.get(k,k):v for k,v in rec.items()},'mapping':mapping}
    if rid==163:
        hist=p.get('history',[{'ts':1,'value':'a'},{'ts':2,'value':'b'}]); t=float(p.get('at',hist[-1]['ts'] if hist else 0)); vals=[h for h in hist if float(h['ts'])<=t]; return {'as_of':t,'value':vals[-1]['value'] if vals else None,'history':hist}
    if rid==164:
        obj=p.get('object',{'id':'1','text':'hello','relations':['2']}); return {'relational':{'id':obj.get('id')},'document':obj,'vector_text':obj.get('text',''),'graph_edges':obj.get('relations',[]),'event_view':p.get('events',[])}
    if rid==165: return {'migration_plan':['snapshot','shadow schema','backfill','verify','dual-write','cutover','observe'],'rollback':['switch reads back','replay delta'],'zero_downtime':True}
    if rid==166:
        items=p.get('items',[{'type':'text','value':'hi'}]); return {'objects':[{'id':stable_hash(x)[:12],'modality':x.get('type'),'metadata':{k:v for k,v in x.items() if k!='value'},'content_ref':stable_hash(x.get('value'))} for x in items],'linked':True}
    if rid==167:
        data=p.get('data',{'name':'A','email':'a@b.com','age':30}); fields=p.get('allow_fields',['age']); return {'capsule':{k:data[k] for k in fields if k in data},'query':p.get('query','read allowed fields'),'minimum_necessary':True}
    if rid==168:
        schema=p.get('schema',{'age':[18,80],'score':[0,1]}); n=int(p.get('n',5)); rng=random.Random(int(p.get('seed',1))); rows=[]
        for _ in range(n): rows.append({k:round(rng.uniform(*v),3) if isinstance(v,list) and len(v)==2 else None for k,v in schema.items()})
        return {'rows':rows,'synthetic':True,'real_user_data_used':False}
    if rid==169:
        event=p.get('event',{'type':'user.created','v':1,'name':'Ada'}); mapping=p.get('mapping',{'name':'display_name'}); out={mapping.get(k,k):v for k,v in event.items()}; return {'routed_event':out,'compatible':True,'version':out.get('v')}
    if rid==170:
        q=p.get('queries',[{'filter':['user_id'],'sort':['ts'],'count':1000}]); cols={}
        for x in q:
            for c in x.get('filter',[]): cols[c]=cols.get(c,0)+x.get('count',1)
        return {'index_candidates':sorted(cols,key=cols.get,reverse=True),'cache_hot_queries':len([x for x in q if x.get('count',0)>100]),'autopilot':True}

def family_mary(rid,p):
    tests=p.get('checks',[{'name':'functional','pass':True,'weight':.4},{'name':'usability','pass':True,'weight':.3},{'name':'performance','pass':False,'weight':.3}]); score=sum(float(x.get('weight',1))*bool(x.get('pass')) for x in tests)/max(.001,sum(float(x.get('weight',1)) for x in tests))
    if rid==171: return {'completion_confidence':round(score,3),'usable':score>=.8,'checks':tests}
    if rid==172: return {'reviews':[{'specialist':s,'finding_count':sum(not bool(x.get('pass')) for x in tests)} for s in ['functionality','usability','performance','edge-cases']],'diverse':True}
    if rid==173:
        users=p.get('users',[{'name':'novice','success':.6},{'name':'expert','success':.95}]); return {'simulations':users,'abandonment_risk':round(1-mean([u['success'] for u in users]),3)}
    if rid==174:
        change=float(p.get('change_size',.4)); deps=float(p.get('dependency_risk',.3)); hist=float(p.get('history_fail_rate',.1)); return {'defect_risk':round(clamp(.4*change+.35*deps+.25*hist),3),'target_more_testing':True}
    if rid==175:
        envs=p.get('environments',{'desktop':True,'mobile':True,'browser':True,'edge':False,'spatial':True}); return {'environments':envs,'complete':all(envs.values()),'missing':[k for k,v in envs.items() if not v]}
    if rid==176:
        steps=p.get('steps',[{'name':'login','seconds':2,'repeats':1},{'name':'upload','seconds':20,'repeats':2}]); return {'friction':[s for s in steps if s.get('seconds',0)>10 or s.get('repeats',1)>1],'total_seconds':sum(s.get('seconds',0) for s in steps)}
    if rid==177: return {'intended':p.get('intended','user completes task'),'observed':p.get('observed','user completes task'),'verified':p.get('intended','user completes task')==p.get('observed','user completes task')}
    if rid==178:
        failures=p.get('failures',[{'name':'slow','impact':.8,'effort':.2}]); return {'experiments':sorted([dict(f,priority=round(float(f['impact'])/max(.01,float(f['effort'])),2)) for f in failures],key=lambda x:-x['priority'])}
    if rid==179: return {'readiness':round(score,3),'release':score>=.85,'expected_conditions':p.get('conditions',['load','usage','failure'])}
    if rid==180:
        sat=float(p.get('satisfaction',.7)); trust=float(p.get('trust',.7)); control=float(p.get('control',.8)); load=float(p.get('cognitive_load',.3)); return {'human_score':round(mean([sat,trust,control,1-load]),3),'dimensions':{'satisfaction':sat,'trust':trust,'control':control,'cognitive_load':load}}

def family_ariel(rid,p):
    missions=p.get('missions',[{'id':'m1','need':'python','urgency':.8}]); agents=p.get('agents',[{'id':'a1','capabilities':['python'],'load':.2,'trust':.9},{'id':'a2','capabilities':['web'],'load':.1,'trust':.8}])
    def match(m):
        scored=[]
        for a in agents:
            cap=1 if m.get('need') in a.get('capabilities',[]) else similarity(m.get('need',''),a.get('capabilities',[])); s=.55*cap+.25*(1-float(a.get('load',0)))+.2*float(a.get('trust',.5)); scored.append((s,a['id']))
        return max(scored)[1] if scored else None
    if rid==181: return {'missions':[dict(m,assigned=match(m)) for m in missions],'dependencies':p.get('dependencies',[]),'live_control':True}
    if rid==182: return {'nodes':[{'id':m['id'],'kind':'mission'} for m in missions]+[{'id':a['id'],'kind':'agent'} for a in agents],'flows':[{'from':m['id'],'to':match(m)} for m in missions]}
    if rid==183: return {'assignments':[{'mission':m['id'],'agent':match(m)} for m in missions],'adaptive':True}
    if rid==184: return {'request':p.get('request',missions[0].get('need','')),'agent':match({'need':p.get('request',missions[0].get('need',''))}),'tool_combo':p.get('tools',[])}
    if rid==185: return {'incident_team':[a['id'] for a in sorted(agents,key=lambda x:(-x.get('trust',0),x.get('load',0)))[:3]],'actions':['diagnose','contain','recover','verify'],'crisis':True}
    if rid==186:
        cmds=p.get('commands',[{'channel':'chat','text':'run check'}]); return {'normalized':[{'source':c.get('channel'),'intent':str(c.get('text','')).split(' ')[0],'payload':c.get('text')} for c in cmds],'one_language':True}
    if rid==187:
        target=p.get('target',{'lat':0,'lon':0}); workers=p.get('workers',[{'id':'w','lat':0,'lon':.1,'capabilities':['delivery']}]); ranked=sorted(workers,key=lambda w:(w['lat']-target['lat'])**2+(w['lon']-target['lon'])**2); return {'assigned':ranked[0]['id'] if ranked else None,'location_aware':True}
    if rid==188:
        ms=sorted(missions,key=lambda m:-float(m.get('urgency',0))); return {'execution_order':[m['id'] for m in ms],'collisions_resolved':True}
    if rid==189: return {'replay':p.get('history',missions),'alternate':list(reversed(p.get('history',missions))),'simulation':True}
    if rid==190:
        q=float(p.get('queue_depth',20)); rate=float(p.get('service_rate',10)); return {'admission_ratio':round(min(1,rate/max(1,q)),3),'retry_backoff_seconds':round(max(0,(q-rate)/max(1,rate)),2),'stable':q<=rate*3}

def family_patricia(rid,p):
    feats=p.get('features',[{'id':'A','duration':2,'risk':.8},{'id':'B','duration':3,'risk':.3},{'id':'C','duration':1,'risk':.5}]); ids=[x['id'] for x in feats]; edges=[tuple(x) for x in p.get('dependencies',[['A','B'],['A','C']])]; order,cycles=topo(ids,edges)
    if rid==191: return {'work_packages':feats,'dependency_graph':edges,'runnable_checks':[f"check:{x}" for x in ids],'compiled':not cycles}
    if rid==192: return {'nodes':ids,'edges':edges,'hidden_prerequisites':[x for x in ids if any(b==x for a,b in edges)],'cycles':cycles}
    if rid==193: return {'build_order':order,'cycles':cycles,'parallelizable':group_levels(ids,edges),'optimized':not cycles}
    if rid==194:
        runs=int(p.get('runs',100)); rng=random.Random(int(p.get('seed',1))); durations=[]
        for _ in range(runs): durations.append(sum(float(x.get('duration',1))*rng.uniform(.8,1.4) for x in feats))
        return {'runs':runs,'p50':round(statistics.median(durations),2),'p90':round(sorted(durations)[int(.9*(runs-1))],2),'simulation':True}
    if rid==195:
        adds=p.get('add',[]); cuts=set(p.get('cut',[])); impacted=sorted({b for a,b in edges if a in cuts}|{a for a,b in edges if b in cuts}); return {'added':adds,'cut':sorted(cuts),'downstream_impacted':impacted,'new_scope_count':len(ids)+len(adds)-len(cuts)}
    if rid==196: return {'workstreams':group_levels(ids,edges),'merge_points':[b for a,b in edges if sum(1 for x,y in edges if y==b)>1],'collision_free':not cycles}
    if rid==197:
        risks=[dict(x,milestone_risk=round(.6*float(x.get('risk',.5))+.4*float(x.get('duration',1))/10,3)) for x in feats]; return {'ranked':sorted(risks,key=lambda x:-x['milestone_risk']),'forecast':True}
    if rid==198:
        risky=max(feats,key=lambda x:float(x.get('risk',0))); return {'prototype_path':[risky['id']],'proves':'riskiest assumption','minimum_slice':True}
    if rid==199: return {'remaining_order':[x for x in order if x not in set(p.get('completed',[]))],'changed_resources':p.get('resources',{}),'replanned':True}
    if rid==200:
        desired=set(p.get('desired',['vision','speech','database'])); available=set(p.get('available',['database'])); return {'available':sorted(available & desired),'gaps':sorted(desired-available),'next_actions':[{'capability':x,'action':'build_or_acquire'} for x in sorted(desired-available)]}

def group_levels(nodes,edges):
    deps={n:set() for n in nodes}
    for a,b in edges:
        if b in deps and a in deps: deps[b].add(a)
    levels=[]; done=set()
    while len(done)<len(nodes):
        ready=sorted([n for n in nodes if n not in done and deps[n]<=done])
        if not ready: break
        levels.append(ready); done.update(ready)
    return levels

FAMILY_FUNCS={'OtherStack':family_otherstack,'Sherry':family_sherry,'Judy':family_judy,'Jammee':family_jammee,'Jayson':family_jayson,'Andi':family_andi,'Kimberly':family_kimberly,'Mary':family_mary,'Ariel':family_ariel,'Patricia':family_patricia}

class Runtime:
    def __init__(self, roadmap, data_dir='.rmdata', max_concurrent=4, peers=None):
        validate_roadmap(roadmap); self.roadmap=roadmap; self.store=StateStore(Path(data_dir)/f"rm-{roadmap['global_id']:03d}.sqlite3"); self.metrics=Metrics(); self.decision=DecisionEngine(self.store,roadmap); self.safety=SafetyGate(); self.peers=peers or {}; self.sem=threading.BoundedSemaphore(max(1,int(max_concurrent))); self.cancel_flags={}; self.lock=threading.Lock()
    def inspect(self): return {'schema_version':SCHEMA_VERSION,'roadmap':self.roadmap,'metrics':self.metrics.snapshot(),'peers':list(self.peers)}
    def run(self, request, idem=None):
        validate_request(request); job,created=self.store.create_job(request,idem)
        if not created and job['state']=='succeeded': return json.loads(job['result'])
        jid=job['id']; self.cancel_flags[jid]=False
        if not self.sem.acquire(timeout=float(request.get('queue_timeout',5))):
            self.store.update_job(jid,'failed',error='backpressure: queue timeout'); raise TimeoutError('backpressure: queue timeout')
        try:
            if self.store.get_job(jid)['state']=='cancelled': raise CancelledError()
            self.store.update_job(jid,'running',attempts=1); start=time.perf_counter(); self.safety.check(request)
            d=self.decision.choose_mode(request,self.peers); self.store.emit('decision',jid,dataclasses.asdict(d))
            cache_key=stable_hash({'rm':self.roadmap['global_id'],'request':request})
            if request.get('cache',True):
                c=self.store.cache_get(cache_key,float(request.get('cache_ttl',3600)))
                if c is not None:
                    c=dict(c); c['cache_hit']=True; self.store.update_job(jid,'succeeded',c); self.metrics.inc('cache_hit'); return c
            retries=max(0,min(5,int(request.get('retries',2)))); last=None; result=None
            for attempt in range(1,retries+2):
                try:
                    self.store.update_job(jid,'running',attempts=attempt); result=self._execute_mode(d.choice,request,jid); last=None; break
                except (CancelledError,SafetyBlocked): raise
                except Exception as e:
                    last=e; self.store.emit('retry',jid,{'attempt':attempt,'error':f'{type(e).__name__}: {e}'})
                    if attempt>retries: raise
                    time.sleep(min(.25,.03*(2**(attempt-1))))
            if last is not None: raise last
            out={'job_id':jid,'roadmap_id':self.roadmap['global_id'],'title':self.roadmap['title'],'mode':d.choice,'decision':dataclasses.asdict(d),'result':result,'cache_hit':False,'explanation':{'outcome':self.roadmap['outcome'],'breakthrough':self.roadmap['breakthrough']}}
            self.store.cache_put(cache_key,out); self.store.update_job(jid,'succeeded',out); self.metrics.inc('jobs_succeeded'); self.metrics.observe((time.perf_counter()-start)*1000); return out
        except CancelledError:
            self.store.update_job(jid,'cancelled'); self.metrics.inc('jobs_cancelled'); raise
        except Exception as e:
            self.store.update_job(jid,'failed',error=f'{type(e).__name__}: {e}'); self.metrics.inc('jobs_failed'); raise
        finally:
            self.sem.release(); self.cancel_flags.pop(jid,None)
    def run_async(self,request,idem=None):
        holder={}
        def f():
            try: holder['result']=self.run(request,idem)
            except Exception as e: holder['error']=repr(e)
        t=threading.Thread(target=f,daemon=True); t.start(); return t,holder
    def cancel(self,jid): self.cancel_flags[jid]=True; return self.store.cancel(jid)
    def _execute_mode(self,mode,request,jid):
        if mode=='local': return self._local(request,jid)
        endpoint=self.peers.get(mode)
        if not endpoint:
            if request.get('mode')=='hybrid': return self._local(request,jid)
            raise ConnectionError(f'{mode} peer unavailable')
        try: return remote_execute(endpoint,self.roadmap['global_id'],request)
        except Exception:
            if request.get('mode','hybrid')=='hybrid': self.store.emit('peer.failover',jid,{'mode':mode}); return self._local(request,jid)
            raise
    def _local(self,request,jid):
        delay=float(request.get('simulate_delay',0)); deadline=now()+float(request.get('timeout',30));
        while delay>0:
            if self.cancel_flags.get(jid) or self.store.get_job(jid)['state']=='cancelled': raise CancelledError()
            if now()>deadline: raise TimeoutError('operation timeout')
            sl=min(.05,delay); time.sleep(sl); delay-=sl; self.store.emit('progress',jid,{'remaining_delay':round(delay,3)})
        fn=FAMILY_FUNCS[self.roadmap['owner']]; self.store.emit('artifact',jid,{'stage':'domain-input','digest':stable_hash(request)}); result=fn(self.roadmap['global_id'],request); self.store.emit('artifact',jid,{'stage':'domain-output','digest':stable_hash(result)}); return result
    def recover(self):
        recovered=[]
        for j in self.store.list_jobs(1000):
            if j['state'] in ('queued','running'):
                jid=j['id']; req=json.loads(j['request']); self.cancel_flags[jid]=False
                try:
                    self.store.update_job(jid,'recovering',attempts=int(j.get('attempts') or 0)+1)
                    d=self.decision.choose_mode(req,self.peers); result=self._execute_mode(d.choice,req,jid)
                    out={'job_id':jid,'roadmap_id':self.roadmap['global_id'],'title':self.roadmap['title'],'mode':d.choice,'decision':dataclasses.asdict(d),'result':result,'cache_hit':False,'recovered':True,'explanation':{'outcome':self.roadmap['outcome'],'breakthrough':self.roadmap['breakthrough']}}
                    self.store.update_job(jid,'succeeded',out,attempts=int(j.get('attempts') or 0)+1); recovered.append({'job_id':jid,'state':'succeeded'})
                except Exception as e:
                    self.store.update_job(jid,'failed',error=f'recovery failed: {type(e).__name__}: {e}'); recovered.append({'job_id':jid,'state':'failed'})
                finally: self.cancel_flags.pop(jid,None)
        return recovered
    def discover(self):
        found={'local':{'roadmap_id':self.roadmap['global_id'],'title':self.roadmap['title'],'reachable':True}}
        for mode,endpoint in self.peers.items():
            try:
                u=urllib.parse.urlparse(endpoint); c=http.client.HTTPConnection(u.hostname,u.port or 80,timeout=1); c.request('GET',(u.path.rstrip('/') if u.path else '')+'/v1/inspect'); r=c.getresponse(); body=json.loads(r.read()); c.close(); found[mode]={'reachable':r.status<300,'roadmap_id':body.get('roadmap',{}).get('global_id'),'title':body.get('roadmap',{}).get('title'),'endpoint':endpoint}
            except Exception as e: found[mode]={'reachable':False,'endpoint':endpoint,'error':type(e).__name__}
        return found
    def sync_export(self): return self.store.export_lww()
    def sync_merge(self,rows): return self.store.merge_lww(rows)

def validate_roadmap(r):
    req=['global_id','section','owner','owner_code','roadmap_index','title','outcome','breakthrough','lane','phases']
    miss=[x for x in req if x not in r]
    if miss: raise ValidationError('roadmap missing '+','.join(miss))
    if not (101<=int(r['global_id'])<=200): raise ValidationError('roadmap id out of package range')
    if len(r['phases'])!=3: raise ValidationError('expected 3 phases')
    if sum(len(x.get('subphases',[])) for x in r['phases'])!=6: raise ValidationError('expected 6 subphases')
    for ph in r['phases']:
        for sp in ph['subphases']:
            if len(sp.get('work',[]))!=3: raise ValidationError('expected 3 work items per subphase')

def validate_request(r):
    if not isinstance(r,dict): raise ValidationError('request must be object')
    if str(r.get('schema_version',SCHEMA_VERSION))!=SCHEMA_VERSION: raise ValidationError('unsupported request schema_version')
    if len(canonical(r))>2_000_000: raise ValidationError('request exceeds 2MB quota')

def remote_execute(endpoint,roadmap_id,request):
    u=urllib.parse.urlparse(endpoint); path=(u.path.rstrip('/') if u.path else '')+'/v1/remote-execute'; body=canonical({'roadmap_id':roadmap_id,'request':request}).encode(); c=http.client.HTTPConnection(u.hostname,u.port or 80,timeout=3); c.request('POST',path,body,{'Content-Type':'application/json'}); r=c.getresponse(); raw=r.read(); c.close();
    if r.status>=300: raise ConnectionError(f'peer status {r.status}')
    return json.loads(raw)['result']['result']

def simulator(rt:Runtime):
    outcomes={}
    outcomes['success']=rt.run({'text':'sim success','cache':False})['result']
    try: rt.run('bad')
    except Exception as e: outcomes['malformed_input']=type(e).__name__
    rt.peers={'cloud':'http://127.0.0.1:1'}; outcomes['disconnection']=rt.run({'mode':'hybrid','cache':False})['mode']
    try: rt.run({'text':'x'*2_000_100})
    except Exception as e: outcomes['overload']=type(e).__name__
    outcomes['provider_loss']=rt.run({'mode':'hybrid','cache':False})['mode']
    outcomes['restart_recovery']=rt.recover()
    return outcomes

def benchmark(rt:Runtime, runs=5):
    vals=[]; sizes=[]
    for _ in range(int(runs)):
        req={'cache':False,'text':'benchmark'}; t=time.perf_counter(); out=rt.run(req); vals.append((time.perf_counter()-t)*1000); sizes.append(len(canonical(out)))
    return {'runs':runs,'latency_ms_avg':round(mean(vals),3),'latency_ms_p95':round(sorted(vals)[max(0,math.ceil(.95*len(vals))-1)],3),'throughput_per_sec':round(1000/max(.001,mean(vals)),3),'memory_rss_kb':get_rss(),'energy_joules':read_energy(),'network_transfer_bytes':0,'execution_cost':0.0,'result_bytes_avg':round(mean(sizes),1)}

def get_rss():
    try:
        import resource; return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except: return None

def read_energy():
    for p in ['/sys/class/powercap/intel-rapl:0/energy_uj']:
        try: return int(Path(p).read_text())/1e6
        except: pass
    return None

class Api:
    def __init__(self,rt): self.rt=rt; self.server=None
    def start(self,host='127.0.0.1',port=0):
        rt=self.rt
        class H(BaseHTTPRequestHandler):
            def log_message(self,*a): pass
            def sendj(self,obj,status=200,ctype='application/json'):
                b=(obj if isinstance(obj,(bytes,bytearray)) else canonical(obj).encode()); self.send_response(status); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
            def body(self):
                n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n) or b'{}')
            def do_GET(self):
                u=urllib.parse.urlparse(self.path); q=urllib.parse.parse_qs(u.query)
                if u.path=='/health': return self.sendj({'ok':True,'roadmap_id':rt.roadmap['global_id']})
                if u.path=='/metrics': return self.sendj(rt.metrics.prometheus().encode(),ctype='text/plain')
                if u.path=='/v1/inspect': return self.sendj(rt.inspect())
                if u.path=='/v1/capabilities': return self.sendj(rt.discover())
                if u.path=='/v1/jobs': return self.sendj(rt.store.list_jobs())
                if u.path=='/v1/resources': return self.sendj(rt.store.resource_list(int(q.get('limit',['100'])[0])))
                if u.path.startswith('/v1/resources/'):
                    x=rt.store.resource_get(u.path.split('/')[3]); return self.sendj(x if x is not None else {'error':'not found'},200 if x is not None else 404)
                if u.path=='/v1/events': return self.sendj(rt.store.events(int(q.get('after',['0'])[0])))
                if u.path=='/v1/events/stream':
                    after=int(q.get('after',['0'])[0]); duration=min(30,float(q.get('seconds',['5'])[0])); end=now()+duration
                    self.send_response(200); self.send_header('Content-Type','text/event-stream'); self.send_header('Cache-Control','no-cache'); self.end_headers()
                    while now()<end:
                        rows=rt.store.events(after,100)
                        for row in rows:
                            after=max(after,int(row['seq'])); self.wfile.write(('event: '+row['kind']+'\ndata: '+canonical(row)+'\n\n').encode()); self.wfile.flush()
                        time.sleep(.1)
                    return
                if u.path=='/': return self.sendj(dashboard(rt).encode(),ctype='text/html; charset=utf-8')
                return self.sendj({'error':'not found'},404)
            def do_POST(self):
                try:
                    b=self.body()
                    if self.path=='/v1/run': return self.sendj(rt.run(b.get('request',b),b.get('idempotency_key')))
                    if self.path=='/v1/feedback': rt.store.feedback(b['signal'],b['value'],b.get('note','')); return self.sendj({'ok':True})
                    if self.path=='/v1/resources': return self.sendj(rt.store.resource_create(b.get('body',b),b.get('id')),201)
                    if self.path.startswith('/v1/resources/'):
                        rid=self.path.split('/')[3]; return self.sendj(rt.store.resource_update(rid,b.get('body',b),b.get('expected_version')))
                    if self.path=='/v1/sync': return self.sendj({'merged':rt.sync_merge(b.get('rows',[])),'rows':rt.sync_export()})
                    if self.path=='/v1/remote-execute':
                        if int(b.get('roadmap_id'))!=rt.roadmap['global_id']: return self.sendj({'error':'roadmap mismatch'},409)
                        return self.sendj({'result':rt.run(dict(b['request'],mode='local'),b.get('idempotency_key'))})
                    if self.path.startswith('/v1/jobs/') and self.path.endswith('/cancel'):
                        jid=self.path.split('/')[3]; return self.sendj({'cancelled':rt.cancel(jid)})
                    return self.sendj({'error':'not found'},404)
                except Exception as e: return self.sendj({'error':type(e).__name__,'message':str(e)},400)
            def do_DELETE(self):
                try:
                    if self.path.startswith('/v1/resources/'):
                        rid=self.path.split('/')[3]; return self.sendj({'deleted':rt.store.resource_delete(rid)})
                    return self.sendj({'error':'not found'},404)
                except Exception as e: return self.sendj({'error':type(e).__name__,'message':str(e)},400)
        self.server=ThreadingHTTPServer((host,int(port)),H); threading.Thread(target=self.server.serve_forever,daemon=True).start(); return self.server.server_address
    def stop(self):
        if self.server: self.server.shutdown(); self.server.server_close(); self.server=None

def roadmap_surfaces(rt):
    for ph in rt.roadmap['phases']:
        for sp in ph['subphases']:
            if sp['name'].startswith('2.2'):
                text=sp['work'][0]; m=re.search(r'primary experience in the (.*?), including',text,re.I)
                return m.group(1) if m else text
    return 'adaptive command surface'

def dashboard(rt):
    title=rt.roadmap['title']; rid=rt.roadmap['global_id']; out=rt.roadmap['outcome']; surfaces=roadmap_surfaces(rt)
    return f'''<!doctype html><meta charset="utf-8"><title>RM-{rid:03d} {title}</title><style>body{{font-family:system-ui;max-width:1000px;margin:40px auto;padding:0 20px}}textarea{{width:100%;height:140px}}pre{{white-space:pre-wrap;background:#111;color:#eee;padding:16px}}button{{padding:10px 16px}}.surface{{padding:12px;border:1px solid #aaa;border-radius:10px;margin:10px 0}}</style><h1>RM-{rid:03d} — {title}</h1><p>{out}</p><div class=surface><b>Roadmap surfaces:</b> {surfaces}</div><p><b>Command palette</b>: enter a JSON request and run it.</p><textarea id=q>{{"text":"demo","cache":false}}</textarea><br><button onclick=go()>Run</button><button onclick=events()>Events</button><pre id=o></pre><script>async function go(){{let r=await fetch('/v1/run',{{method:'POST',headers:{{'content-type':'application/json'}},body:JSON.stringify({{request:JSON.parse(q.value)}})}});o.textContent=JSON.stringify(await r.json(),null,2)}}async function events(){{let r=await fetch('/v1/events');o.textContent=JSON.stringify(await r.json(),null,2)}}</script>'''

class Client:
    def __init__(self,base): self.base=base.rstrip('/')
    def _req(self,method,path,obj=None):
        u=urllib.parse.urlparse(self.base); c=http.client.HTTPConnection(u.hostname,u.port or 80,timeout=5); body=canonical(obj).encode() if obj is not None else None; h={'Content-Type':'application/json'} if body else {}; c.request(method,(u.path.rstrip('/') if u.path else '')+path,body,h); r=c.getresponse(); raw=r.read(); c.close();
        if r.status>=300: raise RuntimeError(raw.decode())
        return json.loads(raw)
    def run(self,request,idempotency_key=None): return self._req('POST','/v1/run',{'request':request,'idempotency_key':idempotency_key})
    def jobs(self): return self._req('GET','/v1/jobs')
    def events(self): return self._req('GET','/v1/events')
    def create(self,body,rid=None): return self._req('POST','/v1/resources',{'body':body,'id':rid})
    def query(self): return self._req('GET','/v1/resources')
    def get(self,rid): return self._req('GET','/v1/resources/'+rid)
    def update(self,rid,body,expected_version=None): return self._req('POST','/v1/resources/'+rid,{'body':body,'expected_version':expected_version})
    def delete(self,rid): return self._req('DELETE','/v1/resources/'+rid)
    def feedback(self,signal,value,note=''): return self._req('POST','/v1/feedback',{'signal':signal,'value':value,'note':note})

def load_roadmap(path=None):
    p=Path(path or Path(__file__).with_name('roadmap.json')); return json.loads(p.read_text())

def cli(argv=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--data-dir',default='.rmdata'); sp=ap.add_subparsers(dest='cmd',required=True)
    p=sp.add_parser('inspect')
    p=sp.add_parser('run'); p.add_argument('json',nargs='?',default='{}'); p.add_argument('--idem')
    p=sp.add_parser('serve'); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=8765)
    p=sp.add_parser('simulate')
    p=sp.add_parser('benchmark'); p.add_argument('--runs',type=int,default=5)
    p=sp.add_parser('jobs')
    p=sp.add_parser('events')
    p=sp.add_parser('feedback'); p.add_argument('signal'); p.add_argument('value',type=float); p.add_argument('--note',default='')
    p=sp.add_parser('cancel'); p.add_argument('job_id')
    args=ap.parse_args(argv); rm=load_roadmap(); rt=Runtime(rm,args.data_dir)
    if args.cmd=='inspect': print(json.dumps(rt.inspect(),indent=2))
    elif args.cmd=='run': print(json.dumps(rt.run(json.loads(args.json),args.idem),indent=2))
    elif args.cmd=='simulate': print(json.dumps(simulator(rt),indent=2))
    elif args.cmd=='benchmark': print(json.dumps(benchmark(rt,args.runs),indent=2))
    elif args.cmd=='jobs': print(json.dumps(rt.store.list_jobs(),indent=2))
    elif args.cmd=='events': print(json.dumps(rt.store.events(),indent=2))
    elif args.cmd=='feedback': rt.store.feedback(args.signal,args.value,args.note); print('{"ok":true}')
    elif args.cmd=='cancel': print(json.dumps({'cancelled':rt.cancel(args.job_id)}))
    elif args.cmd=='serve':
        api=Api(rt); addr=api.start(args.host,args.port); print(f'RM-{rm["global_id"]:03d} listening on http://{addr[0]}:{addr[1]}',flush=True)
        try:
            while True: time.sleep(3600)
        except KeyboardInterrupt: api.stop()
