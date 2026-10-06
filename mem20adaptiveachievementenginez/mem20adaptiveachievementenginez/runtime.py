from __future__ import annotations
import argparse, hashlib, json, math, os, sqlite3, statistics, threading, time, uuid
from collections import OrderedDict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

class ValidationError(ValueError): pass
class QuotaError(RuntimeError): pass
class PolicyError(RuntimeError): pass
class CancelledError(RuntimeError): pass

@dataclass(frozen=True)
class Decision:
    choice: object
    confidence: float
    alternatives: list
    bottlenecks: list
    explanation: dict

class Store:
    def __init__(self, path):
        self.path=str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock=threading.RLock()
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS objects(kind TEXT,id TEXT,version INTEGER,payload TEXT,updated REAL,node TEXT,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,type TEXT,payload TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,idem TEXT UNIQUE,state TEXT,attempts INTEGER,input TEXT,output TEXT,error TEXT,updated REAL,cancel_requested INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,score REAL,payload TEXT);
            CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,label TEXT,payload TEXT);
            ''')
    def connect(self):
        db=sqlite3.connect(self.path, timeout=10)
        db.row_factory=sqlite3.Row
        return db
    def _event(self,db,typ,payload):
        db.execute('INSERT INTO events(ts,type,payload) VALUES(?,?,?)',(time.time(),typ,json.dumps(payload,sort_keys=True,separators=(',',':'))))
    def put(self,kind,ident,payload,expected_version=None,node='local',updated=None):
        if not isinstance(kind,str) or not kind or not isinstance(ident,str) or not ident: raise ValidationError('kind/id required')
        if not isinstance(payload,dict): raise ValidationError('payload must be object')
        with self._lock,self.connect() as db:
            row=db.execute('SELECT version FROM objects WHERE kind=? AND id=?',(kind,ident)).fetchone(); cur=int(row['version']) if row else 0
            if expected_version is not None and cur!=int(expected_version): raise ValidationError(f'version conflict expected={expected_version} actual={cur}')
            ver=cur+1; now=float(updated or time.time()); body=json.dumps(payload,sort_keys=True,separators=(',',':'))
            db.execute('INSERT INTO objects(kind,id,version,payload,updated,node) VALUES(?,?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET version=excluded.version,payload=excluded.payload,updated=excluded.updated,node=excluded.node',(kind,ident,ver,body,now,node))
            self._event(db,'object.upsert',{'kind':kind,'id':ident,'version':ver,'node':node})
        return {'kind':kind,'id':ident,'version':ver,'payload':payload,'updated':now,'node':node}
    def get(self,kind,ident):
        with self.connect() as db: r=db.execute('SELECT * FROM objects WHERE kind=? AND id=?',(kind,ident)).fetchone()
        if not r: return None
        return {'kind':r['kind'],'id':r['id'],'version':r['version'],'payload':json.loads(r['payload']),'updated':r['updated'],'node':r['node']}
    def query(self,kind=None,limit=100):
        with self.connect() as db:
            if kind: rows=db.execute('SELECT * FROM objects WHERE kind=? ORDER BY updated DESC LIMIT ?',(kind,limit)).fetchall()
            else: rows=db.execute('SELECT * FROM objects ORDER BY updated DESC LIMIT ?',(limit,)).fetchall()
        return [{'kind':r['kind'],'id':r['id'],'version':r['version'],'payload':json.loads(r['payload']),'updated':r['updated'],'node':r['node']} for r in rows]
    def delete(self,kind,ident):
        with self._lock,self.connect() as db:
            n=db.execute('DELETE FROM objects WHERE kind=? AND id=?',(kind,ident)).rowcount; self._event(db,'object.delete',{'kind':kind,'id':ident})
        return bool(n)
    def events(self,since=0,limit=200):
        with self.connect() as db: rows=db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?',(int(since),int(limit))).fetchall()
        return [dict(seq=r['seq'],ts=r['ts'],type=r['type'],payload=json.loads(r['payload'])) for r in rows]
    def save_job(self,j):
        with self._lock,self.connect() as db:
            db.execute('INSERT INTO jobs(id,idem,state,attempts,input,output,error,updated,cancel_requested) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,attempts=excluded.attempts,output=excluded.output,error=excluded.error,updated=excluded.updated,cancel_requested=excluded.cancel_requested',(j['id'],j['idem'],j['state'],j['attempts'],json.dumps(j['input'],sort_keys=True),json.dumps(j.get('output'),sort_keys=True) if j.get('output') is not None else None,j.get('error'),time.time(),int(j.get('cancel_requested',0))))
            self._event(db,'job.state',{'id':j['id'],'state':j['state'],'attempts':j['attempts']})
    def job_by_idem(self,idem):
        with self.connect() as db:r=db.execute('SELECT * FROM jobs WHERE idem=?',(idem,)).fetchone()
        return dict(r) if r else None
    def job(self,jid):
        with self.connect() as db:r=db.execute('SELECT * FROM jobs WHERE id=?',(jid,)).fetchone()
        return dict(r) if r else None
    def cancel(self,jid):
        with self._lock,self.connect() as db:
            n=db.execute("UPDATE jobs SET cancel_requested=1,state=CASE WHEN state IN ('succeeded','failed','cancelled') THEN state ELSE 'cancelling' END,updated=? WHERE id=?",(time.time(),jid)).rowcount
            if n:self._event(db,'job.cancel_requested',{'id':jid})
        return bool(n)
    def add_feedback(self,score,payload):
        score=max(-1.0,min(1.0,float(score)))
        with self.connect() as db:db.execute('INSERT INTO feedback(ts,score,payload) VALUES(?,?,?)',(time.time(),score,json.dumps(payload,sort_keys=True)))
    def feedback_bias(self):
        with self.connect() as db:rows=db.execute('SELECT score FROM feedback ORDER BY id DESC LIMIT 100').fetchall()
        return statistics.fmean([r['score'] for r in rows]) if rows else 0.0
    def snapshot(self,label='manual'):
        payload={'objects':self.query(limit=10000),'events':self.events(0,10000)}
        with self.connect() as db:db.execute('INSERT INTO snapshots(ts,label,payload) VALUES(?,?,?)',(time.time(),label,json.dumps(payload,sort_keys=True)))
        return {'label':label,'objects':len(payload['objects']),'events':len(payload['events'])}
    def merge_replica(self,records):
        merged=0; conflicts=0
        for rec in records:
            if not isinstance(rec,dict) or not all(k in rec for k in ('kind','id','payload')): raise ValidationError('invalid replica record')
            cur=self.get(rec['kind'],rec['id']); incoming_ts=float(rec.get('updated',0)); incoming_node=str(rec.get('node','replica'))
            if cur is None or (incoming_ts,incoming_node)>(float(cur['updated']),str(cur.get('node','local'))):
                self.put(rec['kind'],rec['id'],rec['payload'],node=incoming_node,updated=incoming_ts or time.time()); merged+=1
            elif cur['payload']!=rec['payload']: conflicts+=1
        return {'merged':merged,'conflicts':conflicts,'strategy':'deterministic-lww(updated,node)'}

class Engine:
    HARD_LIMITS={'max_candidates':1000,'max_text':100000,'max_retries':3,'max_runtime_ms':5000,'max_concurrent':8}
    def __init__(self,config,db_path=None):
        self.config=config; self.store=Store(db_path or Path('state')/(config['id']+'.sqlite3')); self.metrics={'executions':0,'errors':0,'retries':0,'failovers':0,'policy_blocks':0,'cancellations':0,'cache_hits':0}; self._slots=threading.BoundedSemaphore(self.HARD_LIMITS['max_concurrent']); self._cache=OrderedDict(); self._cache_lock=threading.RLock()
    @staticmethod
    def _size(p): return len(json.dumps(p,sort_keys=True,separators=(',',':')))
    def validate(self,p):
        if not isinstance(p,dict): raise ValidationError('input must be JSON object')
        if self._size(p)>self.HARD_LIMITS['max_text']: raise QuotaError('payload too large')
        if isinstance(p.get('candidates'),list) and len(p['candidates'])>self.HARD_LIMITS['max_candidates']: raise QuotaError('too many candidates')
        if p.get('auto_action') and (p.get('unsafe') or p.get('sensitive') or float(p.get('risk',0))>.75):
            self.metrics['policy_blocks']+=1; raise PolicyError('unsafe/sensitive automatic action blocked')
    @staticmethod
    def tokens(v): return {x for x in ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(v)).split() if len(x)>1}
    def score_candidates(self,p):
        cs=p.get('candidates') or p.get('options') or []; goal=self.tokens(p.get('goal') or p.get('query') or self.config['outcome']); scored=[]; bias=self.store.feedback_bias()*0.02
        for i,c in enumerate(cs):
            o=c if isinstance(c,dict) else {'value':c}; tok=self.tokens(' '.join(str(v) for v in o.values())); sem=len(goal&tok)/max(1,len(goal|tok)); utility=float(o.get('utility',o.get('score',.5))); cost=float(o.get('cost',0)); risk=float(o.get('risk',0)); latency=float(o.get('latency_ms',0))/10000
            scored.append((.50*sem+.35*utility-.08*cost-.07*risk-.04*latency+bias-i*1e-9,o))
        return sorted(scored,key=lambda x:x[0],reverse=True)
    def decision(self,p):
        s=self.score_candidates(p)
        if not s:return Decision(None,.35,[],['no candidates supplied'],{'method':'safe-default','techniques':self.config.get('techniques',[])})
        vals=[x for x,_ in s]; spread=(vals[0]-vals[1]) if len(vals)>1 else .5; conf=max(.05,min(.99,.55+spread/2)); return Decision(s[0][1],conf,[o for _,o in s[1:4]],(['low score separation'] if len(vals)>1 and spread<.05 else []),{'method':'semantic-utility-cost-risk','techniques':self.config.get('techniques',[]),'top_score':round(vals[0],6)})
    def operate(self,p):
        k=self.config.get('operation_kind','analyze'); d=self.decision(p)
        if k=='route': return {'route':d.choice,'alternatives':d.alternatives,'confidence':d.confidence,'explanation':d.explanation}
        if k=='match':
            demand=p.get('demand') or p.get('requests') or []; supply=p.get('supply') or p.get('resources') or p.get('candidates') or []; out=[]; used=set()
            for a in demand:
                best=None
                for j,b in enumerate(supply):
                    if j in used:continue
                    at=self.tokens(a);bt=self.tokens(b);s=len(at&bt)/max(1,len(at|bt)); best=(s,j,b) if best is None or s>best[0] else best
                if best:used.add(best[1]);out.append({'demand':a,'supply':best[2],'score':round(best[0],4)})
            return {'matches':out,'unmatched':max(0,len(demand)-len(out))}
        if k=='forecast':
            series=[float(x) for x in (p.get('series') or p.get('history') or [0,1])]; n=len(series); xs=list(range(n)); xm=sum(xs)/n; ym=sum(series)/n; den=sum((x-xm)**2 for x in xs) or 1; slope=sum((x-xm)*(y-ym) for x,y in zip(xs,series))/den; steps=max(1,min(100,int(p.get('steps',3)))); pred=[ym+slope*((n+i)-xm) for i in range(steps)]
            return {'slope':slope,'forecast':pred,'confidence':max(.2,min(.95,1/(1+(statistics.pstdev(series) if n>1 else 0))))}
        if k=='search':
            docs=p.get('documents') or p.get('items') or p.get('candidates') or [];q=self.tokens(p.get('query') or p.get('goal') or '');out=[]
            for d0 in docs:
                text=json.dumps(d0,sort_keys=True) if isinstance(d0,(dict,list)) else str(d0);t=self.tokens(text);s=len(q&t)/max(1,len(q|t));out.append({'score':round(s,6),'item':d0})
            return {'results':sorted(out,key=lambda x:x['score'],reverse=True)[:int(p.get('limit',10))]}
        if k=='simulate':
            base=float(p.get('baseline',1)); scenarios=p.get('scenarios') or [{'name':'baseline','multiplier':1.0},{'name':'upside','multiplier':1.15},{'name':'downside','multiplier':.85}]; return {'scenarios':[{'name':s.get('name',str(i)),'value':base*float(s.get('multiplier',1))*float(s.get('probability',1))} for i,s in enumerate(scenarios)]}
        if k=='compose':
            parts=p.get('components') or p.get('capabilities') or p.get('candidates') or [];goal=self.tokens(p.get('goal') or self.config['outcome']);chosen=[];covered=set()
            for part in parts:
                t=self.tokens(part);gain=len((goal-covered)&t)
                if gain:chosen.append(part);covered|=t
            return {'composition':chosen or parts[:1],'coverage':round(len(goal&covered)/max(1,len(goal)),4),'uncovered':sorted(goal-covered)[:25]}
        if k=='optimize': return {'best':d.choice,'alternatives':d.alternatives,'confidence':d.confidence,'objective':'maximize utility/fit; minimize cost/risk/latency'}
        if k=='heal':
            comps=p.get('components') or []; bad=[c for c in comps if isinstance(c,dict) and not c.get('healthy',True)]; return {'unhealthy':bad,'actions':[{'component':c.get('id'),'action':'restart-or-failover'} for c in bad],'healthy':not bad}
        if k=='ingest':
            items=p.get('items') or []; return {'accepted':len(items),'artifacts':[{'id':hashlib.sha256(json.dumps(x,sort_keys=True,default=str).encode()).hexdigest()[:16],'type':type(x).__name__} for x in items]}
        if k=='schedule':
            nodes=p.get('nodes') or p.get('candidates') or []; ranked=sorted(nodes,key=lambda n:((float(n.get('cost',0))+.01*float(n.get('latency_ms',0)))/max(.001,float(n.get('capacity',1)))) if isinstance(n,dict) else 999); return {'placement':ranked[0] if ranked else None,'alternatives':ranked[1:3]}
        if k=='model':
            models=p.get('models') or p.get('candidates') or [];sc=self.score_candidates({'goal':p.get('goal',self.config['outcome']),'candidates':models}); chosen=[o for _,o in sc[:max(1,int(p.get('fusion_width',2)))]]; return {'selected_models':chosen,'fusion':'weighted-ensemble' if len(chosen)>1 else 'single','weights':[round(1/len(chosen),4)]*len(chosen) if chosen else []}
        if k=='graph':
            nodes=p.get('nodes') or [];edges=p.get('edges') or [];deg={str(n.get('id',n) if isinstance(n,dict) else n):0 for n in nodes}
            for e in edges:
                if isinstance(e,dict):a=str(e.get('from'));b=str(e.get('to'));deg[a]=deg.get(a,0)+1;deg[b]=deg.get(b,0)+1
            return {'nodes':len(deg),'edges':len(edges),'degree':deg,'hubs':sorted(deg,key=deg.get,reverse=True)[:5]}
        if k=='reward':
            value=float(p.get('value',1));rarity=max(.01,float(p.get('rarity',1)));elig=bool(p.get('eligible',True));timing=max(.1,float(p.get('timing_multiplier',1)));return {'eligible':elig,'reward_value':round(value*rarity*timing,4) if elig else 0,'rules_applied':['value','rarity','eligibility','timing']}
        if k=='progression':
            xp=max(0,float(p.get('xp',0))); thresholds=p.get('thresholds') or [100,250,500,1000]; level=sum(xp>=float(t) for t in thresholds);return {'xp':xp,'level':level,'next_threshold':thresholds[level] if level<len(thresholds) else None}
        if k=='qa':
            tests=p.get('tests') or [];failed=[t for t in tests if isinstance(t,dict) and not t.get('pass',False)];return {'total':len(tests),'failed':len(failed),'release_blocked':bool(failed),'failures':failed[:20]}
        if k=='pipeline':
            stages=p.get('stages') or [];done=[];blocked=[]
            for s in stages:
                o=s if isinstance(s,dict) else {'id':str(s)}
                if o.get('blocked'):blocked.append(o)
                else:done.append(o.get('id',o.get('name','stage')))
            return {'completed':done,'blocked':blocked,'progress':round(len(done)/max(1,len(stages)),4)}
        vals=[float(x) for x in p.get('values',[]) if isinstance(x,(int,float))];return {'count':len(vals),'mean':statistics.fmean(vals) if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None,'decision':d.choice,'confidence':d.confidence,'explanation':d.explanation}
    def _cache_get(self,key):
        with self._cache_lock:
            if key not in self._cache:return None
            self._cache.move_to_end(key);self.metrics['cache_hits']+=1;return self._cache[key]
    def _cache_put(self,key,val):
        with self._cache_lock:
            self._cache[key]=val;self._cache.move_to_end(key)
            while len(self._cache)>128:self._cache.popitem(last=False)
    def execute(self,p,idem=None,retries=2,timeout_ms=None):
        self.validate(p); retries=max(0,min(int(retries),self.HARD_LIMITS['max_retries'])); timeout_ms=min(int(timeout_ms or self.HARD_LIMITS['max_runtime_ms']),self.HARD_LIMITS['max_runtime_ms']); idem=idem or hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest(); old=self.store.job_by_idem(idem)
        if old and old['state']=='succeeded':return json.loads(old['output'])
        cached=self._cache_get(idem)
        if cached is not None:return cached
        if not self._slots.acquire(timeout=.05):raise QuotaError('backpressure: runtime busy')
        try:
            job={'id':old['id'] if old else str(uuid.uuid4()),'idem':idem,'state':'running','attempts':0,'input':p,'cancel_requested':int(old['cancel_requested']) if old else 0};started=time.perf_counter();last=None
            for attempt in range(retries+1):
                cur=self.store.job(job['id'])
                if cur and cur.get('cancel_requested'):
                    job.update(state='cancelled',cancel_requested=1,error='cancelled');self.store.save_job(job);self.metrics['cancellations']+=1;raise CancelledError('job cancelled')
                job['attempts']=attempt+1;self.store.save_job(job)
                try:
                    if p.get('_inject_failure') and attempt<int(p.get('_fail_attempts',1)):raise RuntimeError('injected provider loss')
                    out=self.operate(p)
                    if (time.perf_counter()-started)*1000>timeout_ms:raise TimeoutError('operation timeout')
                    job.update(state='succeeded',output=out,error=None);self.store.save_job(job);self.metrics['executions']+=1;self.store.put('output',job['id'],{'roadmap':self.config['id'],'result':out});self._cache_put(idem,out);return out
                except (PolicyError,ValidationError,QuotaError,CancelledError):raise
                except Exception as e:
                    last=e;self.metrics['errors']+=1
                    if attempt<retries:self.metrics['retries']+=1;continue
                    job.update(state='failed',error=str(e));self.store.save_job(job);raise
            raise last
        finally:self._slots.release()
    def cancel(self,jid):return {'cancelled':self.store.cancel(jid),'job_id':jid}
    def feedback(self,score,payload=None):self.store.add_feedback(score,payload or {});return {'accepted':True,'bias':self.store.feedback_bias()}
    def mesh_select(self,nodes,mode='hybrid'):
        live=[n for n in nodes if n.get('available',True)]
        if mode=='local':live=[n for n in live if n.get('kind') in ('local','edge')]
        elif mode=='cloud':live=[n for n in live if n.get('kind')=='cloud']
        if not live:return {'node':None,'graceful_degradation':True}
        ranked=sorted(live,key=lambda n:(float(n.get('latency_ms',9999))+.1*float(n.get('cost',0))+2*float(n.get('energy',0)),-float(n.get('capacity',1))));return {'node':ranked[0],'fallbacks':ranked[1:3],'graceful_degradation':False}
    def simulator(self):
        base={'goal':self.config['outcome'],'candidates':[{'id':'local','utility':.9,'cost':.1},{'id':'edge','utility':.8,'cost':.2}]};out={}
        def ok(name,fn):
            try: out[name]={'ok':bool(fn())}
            except Exception as e:out[name]={'ok':False,'error':f'{type(e).__name__}: {e}'}
        ok('success',lambda:self.execute(base,idem='sim-success') is not None)
        ok('malformed',lambda:_expect((ValidationError,),lambda:self.execute([],idem='sim-malformed')))
        ok('disconnection',lambda:self.mesh_select([{'id':'cloud','kind':'cloud','available':False},{'id':'local','kind':'local','available':True}])['node']['id']=='local')
        ok('overload',lambda:_expect((QuotaError,),lambda:self.execute({'candidates':[{'id':str(i)} for i in range(1001)]},idem='sim-overload')))
        ok('provider_loss',lambda:self.execute(dict(base,_inject_failure=True,_fail_attempts=1),idem='sim-provider-loss',retries=2) is not None)
        ok('restart_recovery',lambda:self.execute(base,idem='sim-restart')==Engine(self.config,self.store.path).execute(base,idem='sim-restart'))
        ok('adversarial_payload',lambda:_expect((QuotaError,),lambda:self.execute({'blob':'x'*100001},idem='sim-adversarial')))
        ok('privacy_guard',lambda:_expect((PolicyError,),lambda:self.execute({'auto_action':True,'sensitive':True},idem='sim-privacy')))
        ok('misuse_guard',lambda:_expect((PolicyError,),lambda:self.execute({'auto_action':True,'unsafe':True},idem='sim-misuse')))
        ok('replica_conflict',lambda:self._sim_replica())
        return out
    def _sim_replica(self):
        self.store.put('replica-test','x',{'v':1},node='a',updated=100);r=self.store.merge_replica([{'kind':'replica-test','id':'x','payload':{'v':2},'node':'b','updated':200}]);return r['merged']==1 and self.store.get('replica-test','x')['payload']['v']==2
    def benchmark(self,n=100):
        samples=[];p={'values':[1,2,3],'goal':self.config['outcome'],'candidates':[{'id':'a','utility':.8},{'id':'b','utility':.7}]}
        for _ in range(n):st=time.perf_counter();self.operate(p);samples.append((time.perf_counter()-st)*1000)
        samples.sort();p95=samples[min(len(samples)-1,math.ceil(.95*len(samples))-1)];total=sum(samples)/1000 or 1e-9;return {'iterations':n,'ops_per_sec':round(n/total,2),'p50_ms':round(statistics.median(samples),6),'p95_ms':round(p95,6),'memory_model':'bounded input + sqlite WAL + 128-entry LRU','network_transfer':'0 bytes local benchmark','cost_model':'local CPU only','energy_proxy_ms':round(sum(samples),6)}
    def metrics_snapshot(self):return {**self.metrics,'feedback_bias':self.store.feedback_bias(),'roadmap':self.config['id']}

def _expect(types,fn):
    try:fn();return False
    except types:return True

class SDK:
    def __init__(self,engine):self.engine=engine
    def create(self,kind,ident,payload):return self.engine.store.put(kind,ident,payload)
    def query(self,kind=None):return self.engine.store.query(kind)
    def update(self,kind,ident,payload,expected_version=None):return self.engine.store.put(kind,ident,payload,expected_version)
    def delete(self,kind,ident):return self.engine.store.delete(kind,ident)
    def events(self,since=0):return self.engine.store.events(since)
    def subscribe(self,since=0,poll_seconds=.05):
        cursor=int(since)
        while True:
            events=self.engine.store.events(cursor)
            for e in events:cursor=e['seq'];yield e
            time.sleep(poll_seconds)
    def execute(self,payload,idempotency_key=None):return self.engine.execute(payload,idempotency_key)
    def feedback(self,score,payload=None):return self.engine.feedback(score,payload)
    def cancel(self,job_id):return self.engine.cancel(job_id)
    def merge_replica(self,records):return self.engine.store.merge_replica(records)

class Handler(BaseHTTPRequestHandler):
    engine=None
    def sendj(self,code,obj,ctype='application/json'):
        body=json.dumps(obj,indent=2,sort_keys=True).encode();self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def body(self):
        n=int(self.headers.get('Content-Length','0'));return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        u=urlparse(self.path);q=parse_qs(u.query)
        if u.path=='/health':return self.sendj(200,{'ok':True,'roadmap':self.engine.config['id']})
        if u.path=='/spec':return self.sendj(200,self.engine.config)
        if u.path=='/metrics':return self.sendj(200,self.engine.metrics_snapshot())
        if u.path=='/events':return self.sendj(200,self.engine.store.events(int(q.get('since',['0'])[0])))
        if u.path=='/objects':return self.sendj(200,self.engine.store.query(q.get('kind',[None])[0]))
        if u.path=='/':
            title=f"{self.engine.config['id']} — {self.engine.config['title']}";html=("<!doctype html><meta charset=utf-8><title>"+title+"</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:0 18px}textarea{width:100%;height:180px}pre{background:#111;color:#eee;padding:16px;overflow:auto}</style><h1>"+title+"</h1><p>"+self.engine.config['outcome']+"</p><p><b>Breakthrough:</b> "+self.engine.config['breakthrough']+"</p><textarea id=p>{\"goal\":\""+self.engine.config['outcome'].replace('"','&quot;')+"\",\"candidates\":[{\"id\":\"local\",\"utility\":0.9},{\"id\":\"edge\",\"utility\":0.8}]}</textarea><button onclick=go()>Execute</button><pre id=o></pre><script>async function go(){let r=await fetch('/execute',{method:'POST',headers:{'content-type':'application/json'},body:p.value});o.textContent=JSON.stringify(await r.json(),null,2)}</script>").encode();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(html)));self.end_headers();return self.wfile.write(html)
        return self.sendj(404,{'error':'not found'})
    def do_POST(self):
        try:
            p=self.body()
            if self.path=='/execute':return self.sendj(200,self.engine.execute(p,self.headers.get('Idempotency-Key')))
            if self.path=='/feedback':return self.sendj(200,self.engine.feedback(p.get('score',0),p))
            if self.path=='/objects':return self.sendj(201,self.engine.store.put(p['kind'],p['id'],p.get('payload',{}),p.get('expected_version')))
            if self.path=='/replica/merge':return self.sendj(200,self.engine.store.merge_replica(p.get('records',[])))
            if self.path.startswith('/jobs/') and self.path.endswith('/cancel'):return self.sendj(200,self.engine.cancel(self.path.split('/')[2]))
            return self.sendj(404,{'error':'not found'})
        except Exception as e:return self.sendj(400,{'error':type(e).__name__,'message':str(e)})
    def log_message(self,*a):pass

def load_config(path):return json.loads(Path(path).read_text())
def main(config_path=None):
    ap=argparse.ArgumentParser();ap.add_argument('--config',default=config_path);sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('execute');p.add_argument('json');p.add_argument('--idem')
    p=sub.add_parser('serve');p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=0)
    sub.add_parser('simulate');sub.add_parser('benchmark');sub.add_parser('metrics');sub.add_parser('snapshot')
    a=ap.parse_args();cfg=load_config(a.config);eng=Engine(cfg)
    if a.cmd=='execute':print(json.dumps(eng.execute(json.loads(a.json),a.idem),indent=2,sort_keys=True))
    elif a.cmd=='simulate':print(json.dumps(eng.simulator(),indent=2,sort_keys=True))
    elif a.cmd=='benchmark':print(json.dumps(eng.benchmark(),indent=2,sort_keys=True))
    elif a.cmd=='metrics':print(json.dumps(eng.metrics_snapshot(),indent=2,sort_keys=True))
    elif a.cmd=='snapshot':print(json.dumps(eng.store.snapshot(),indent=2,sort_keys=True))
    elif a.cmd=='serve':Handler.engine=eng;srv=ThreadingHTTPServer((a.host,a.port),Handler);print(f'http://{a.host}:{srv.server_port}',flush=True);srv.serve_forever()
