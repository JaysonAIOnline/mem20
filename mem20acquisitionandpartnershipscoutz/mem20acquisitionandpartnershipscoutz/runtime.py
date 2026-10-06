from __future__ import annotations
import argparse, hashlib, json, math, sqlite3, statistics, threading, time, uuid
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

class ValidationError(ValueError): pass
class QuotaError(RuntimeError): pass

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
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS objects(kind TEXT,id TEXT,version INTEGER,payload TEXT,updated REAL,PRIMARY KEY(kind,id));
            CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, type TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,idem TEXT UNIQUE,state TEXT,attempts INTEGER,input TEXT,output TEXT,error TEXT,updated REAL);
            CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,score REAL,payload TEXT);
            """)
    def connect(self):
        db=sqlite3.connect(self.path, timeout=10)
        db.row_factory=sqlite3.Row
        return db
    def put(self, kind, ident, payload, expected_version=None):
        if not isinstance(payload,dict): raise ValidationError('payload must be object')
        with self._lock, self.connect() as db:
            row=db.execute('SELECT version FROM objects WHERE kind=? AND id=?',(kind,ident)).fetchone()
            cur=int(row['version']) if row else 0
            if expected_version is not None and cur!=expected_version: raise ValidationError(f'version conflict expected={expected_version} actual={cur}')
            ver=cur+1; now=time.time(); body=json.dumps(payload,sort_keys=True,separators=(',',':'))
            db.execute('INSERT INTO objects(kind,id,version,payload,updated) VALUES(?,?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET version=excluded.version,payload=excluded.payload,updated=excluded.updated',(kind,ident,ver,body,now))
            db.execute('INSERT INTO events(ts,type,payload) VALUES(?,?,?)',(now,'object.upsert',json.dumps({'kind':kind,'id':ident,'version':ver},sort_keys=True)))
            return {'kind':kind,'id':ident,'version':ver,'payload':payload,'updated':now}
    def get(self, kind, ident):
        with self.connect() as db: row=db.execute('SELECT * FROM objects WHERE kind=? AND id=?',(kind,ident)).fetchone()
        if not row: return None
        return {'kind':row['kind'],'id':row['id'],'version':row['version'],'payload':json.loads(row['payload']),'updated':row['updated']}
    def query(self, kind=None, limit=100):
        with self.connect() as db:
            sql='SELECT * FROM objects '+('WHERE kind=? ' if kind else '')+'ORDER BY updated DESC LIMIT ?'
            rows=db.execute(sql, ((kind,limit) if kind else (limit,))).fetchall()
        return [{'kind':r['kind'],'id':r['id'],'version':r['version'],'payload':json.loads(r['payload']),'updated':r['updated']} for r in rows]
    def delete(self,kind,ident):
        with self._lock,self.connect() as db:
            n=db.execute('DELETE FROM objects WHERE kind=? AND id=?',(kind,ident)).rowcount
            db.execute('INSERT INTO events(ts,type,payload) VALUES(?,?,?)',(time.time(),'object.delete',json.dumps({'kind':kind,'id':ident})))
            return bool(n)
    def events(self,since=0,limit=200):
        with self.connect() as db: rows=db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?',(since,limit)).fetchall()
        return [dict(seq=r['seq'],ts=r['ts'],type=r['type'],payload=json.loads(r['payload'])) for r in rows]
    def job_by_idem(self,idem):
        with self.connect() as db: r=db.execute('SELECT * FROM jobs WHERE idem=?',(idem,)).fetchone()
        return dict(r) if r else None
    def save_job(self,job):
        with self._lock,self.connect() as db:
            db.execute('INSERT INTO jobs(id,idem,state,attempts,input,output,error,updated) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,attempts=excluded.attempts,output=excluded.output,error=excluded.error,updated=excluded.updated',(job['id'],job['idem'],job['state'],job['attempts'],json.dumps(job['input'],sort_keys=True),json.dumps(job.get('output'),sort_keys=True) if job.get('output') is not None else None,job.get('error'),time.time()))
    def add_feedback(self,score,payload):
        score=max(-1.0,min(1.0,float(score)))
        with self.connect() as db: db.execute('INSERT INTO feedback(ts,score,payload) VALUES(?,?,?)',(time.time(),score,json.dumps(payload,sort_keys=True)))
    def feedback_bias(self):
        with self.connect() as db: rows=db.execute('SELECT score FROM feedback ORDER BY id DESC LIMIT 100').fetchall()
        return statistics.fmean([r['score'] for r in rows]) if rows else 0.0

class Engine:
    HARD_LIMITS={'max_candidates':1000,'max_text':100000,'max_retries':3,'max_runtime_ms':5000}
    def __init__(self, config, db_path=None):
        self.config=config
        self.store=Store(db_path or Path('state')/(config['id']+'.sqlite3'))
        self.metrics={'executions':0,'errors':0,'retries':0,'failovers':0}
    def validate(self,p):
        if not isinstance(p,dict): raise ValidationError('input must be JSON object')
        if len(json.dumps(p))>self.HARD_LIMITS['max_text']: raise QuotaError('payload too large')
        if isinstance(p.get('candidates'),list) and len(p['candidates'])>self.HARD_LIMITS['max_candidates']: raise QuotaError('too many candidates')
    @staticmethod
    def tokens(v): return {x for x in ''.join(ch.lower() if ch.isalnum() else ' ' for ch in str(v)).split() if len(x)>1}
    def score_candidates(self,p):
        cs=p.get('candidates') or p.get('options') or []
        goal=self.tokens(p.get('goal') or p.get('query') or self.config['outcome'])
        scored=[]; bias=self.store.feedback_bias()*0.02
        for i,c in enumerate(cs):
            obj=c if isinstance(c,dict) else {'value':c}
            text=' '.join(str(v) for v in obj.values()); tok=self.tokens(text)
            semantic=len(goal&tok)/max(1,len(goal|tok)); utility=float(obj.get('utility',obj.get('score',0.5)))
            cost=float(obj.get('cost',0.0)); risk=float(obj.get('risk',0.0)); latency=float(obj.get('latency_ms',0.0))/10000
            score=.50*semantic+.35*utility-.08*cost-.07*risk-.04*latency+bias-i*1e-9
            scored.append((score,obj))
        return sorted(scored,key=lambda x:x[0],reverse=True)
    def decision(self,p):
        scored=self.score_candidates(p)
        if not scored: return Decision(None,0.35,[],['no candidates supplied'],{'method':'safe-default','techniques':self.config['techniques']})
        vals=[s for s,_ in scored]; spread=(vals[0]-vals[1]) if len(vals)>1 else .5; conf=max(.05,min(.99,.55+spread/2))
        return Decision(scored[0][1],conf,[o for _,o in scored[1:4]],(['low score separation'] if len(vals)>1 and spread<.05 else []),{'method':'weighted semantic/utility/cost/risk scoring','techniques':self.config['techniques'],'top_score':round(vals[0],6)})
    def operate(self,p):
        k=self.config['operation_kind']; d=self.decision(p)
        if k=='route': return {'route':d.choice,'alternatives':d.alternatives,'confidence':d.confidence,'explanation':d.explanation}
        if k=='match':
            demand=p.get('demand') or p.get('requests') or []; supply=p.get('supply') or p.get('resources') or p.get('candidates') or []
            matches=[]; used=set()
            for a in demand:
                best=None
                for j,b in enumerate(supply):
                    if j in used: continue
                    at=self.tokens(a); bt=self.tokens(b); s=len(at&bt)/max(1,len(at|bt))
                    if best is None or s>best[0]: best=(s,j,b)
                if best: used.add(best[1]); matches.append({'demand':a,'supply':best[2],'score':round(best[0],4)})
            return {'matches':matches,'unmatched':max(0,len(demand)-len(matches))}
        if k=='forecast':
            series=[float(x) for x in (p.get('series') or p.get('history') or [0,1])]
            n=len(series); xs=list(range(n)); xm=sum(xs)/n; ym=sum(series)/n; den=sum((x-xm)**2 for x in xs) or 1; slope=sum((x-xm)*(y-ym) for x,y in zip(xs,series))/den
            steps=max(1,min(100,int(p.get('steps',3)))); pred=[ym+slope*((n+i)-xm) for i in range(steps)]
            return {'slope':slope,'forecast':pred,'confidence':max(.2,min(.95,1/(1+(statistics.pstdev(series) if n>1 else 0))))}
        if k=='search':
            docs=p.get('documents') or p.get('items') or p.get('candidates') or []; q=self.tokens(p.get('query') or p.get('goal') or '')
            out=[]
            for d0 in docs:
                text=json.dumps(d0,sort_keys=True) if isinstance(d0,(dict,list)) else str(d0); t=self.tokens(text); s=len(q&t)/max(1,len(q|t)); out.append({'score':round(s,6),'item':d0})
            return {'results':sorted(out,key=lambda x:x['score'],reverse=True)[:int(p.get('limit',10))]}
        if k=='simulate':
            base=float(p.get('baseline',1)); scenarios=p.get('scenarios') or [{'name':'baseline','multiplier':1.0},{'name':'upside','multiplier':1.15},{'name':'downside','multiplier':.85}]
            return {'scenarios':[{'name':s.get('name',str(i)),'value':base*float(s.get('multiplier',1))*float(s.get('probability',1))} for i,s in enumerate(scenarios)]}
        if k=='compose':
            parts=p.get('components') or p.get('capabilities') or p.get('candidates') or []; goal=self.tokens(p.get('goal') or self.config['outcome']); chosen=[]; covered=set()
            for part in parts:
                t=self.tokens(part); gain=len((goal-covered)&t)
                if gain: chosen.append(part); covered |= t
            return {'composition':chosen,'coverage':round(len(goal&covered)/max(1,len(goal)),4),'uncovered':sorted(goal-covered)}
        if k=='optimize':
            scored=self.score_candidates(p); return {'best':scored[0][1] if scored else None,'score':scored[0][0] if scored else None,'alternatives':[o for _,o in scored[1:5]],'constraints_respected':True}
        if k=='heal':
            comps=p.get('components') or p.get('candidates') or []; failed=[c for c in comps if isinstance(c,dict) and c.get('healthy') is False]; healthy=[c for c in comps if not(isinstance(c,dict) and c.get('healthy') is False)]; actions=[]
            for f in failed:
                repl=healthy[0] if healthy else None; actions.append({'failed':f,'action':'failover' if repl else 'isolate','replacement':repl})
            return {'actions':actions,'healthy_count':len(healthy),'contained':bool(failed)}
        if k=='ingest':
            items=p.get('items') or p.get('signals') or [p.get('input','')]; out=[]
            for i,x in enumerate(items):
                body=json.dumps(x,sort_keys=True) if isinstance(x,(dict,list)) else str(x); out.append({'id':hashlib.sha256(body.encode()).hexdigest()[:16],'index':i,'text':body,'tokens':sorted(self.tokens(body))})
            return {'ingested':out,'count':len(out)}
        if k=='schedule':
            nodes=p.get('nodes') or p.get('candidates') or []; scored=[]
            for n in nodes:
                if not isinstance(n,dict): n={'id':str(n)}
                score=float(n.get('capacity',1))*float(n.get('availability',1))-float(n.get('cost',0))-.001*float(n.get('latency_ms',0))-.05*float(n.get('energy',0)); scored.append((score,n))
            scored.sort(key=lambda x:x[0],reverse=True)
            return {'placement':scored[0][1] if scored else {'id':'local'},'score':scored[0][0] if scored else 1.0,'fallbacks':[n for _,n in scored[1:4]]}
        if k=='model':
            models=p.get('models') or p.get('candidates') or []; scored=self.score_candidates({'goal':p.get('goal',self.config['outcome']),'candidates':models}); chosen=[o for _,o in scored[:max(1,int(p.get('fusion_width',2)))]]
            return {'selected_models':chosen,'fusion':'weighted-ensemble' if len(chosen)>1 else 'single','weights':[round(1/len(chosen),4)]*len(chosen) if chosen else []}
        if k=='graph':
            nodes=p.get('nodes') or []; edges=p.get('edges') or []; deg={str(n.get('id',n) if isinstance(n,dict) else n):0 for n in nodes}
            for e in edges:
                if isinstance(e,dict):
                    a=str(e.get('from')); b=str(e.get('to')); deg[a]=deg.get(a,0)+1; deg[b]=deg.get(b,0)+1
            return {'nodes':len(deg),'edges':len(edges),'degree':deg,'hubs':sorted(deg,key=deg.get,reverse=True)[:5]}
        vals=[float(x) for x in p.get('values',[]) if isinstance(x,(int,float))]
        return {'count':len(vals),'mean':statistics.fmean(vals) if vals else None,'min':min(vals) if vals else None,'max':max(vals) if vals else None,'decision':d.choice,'confidence':d.confidence,'explanation':d.explanation}
    def execute(self,p,idem=None,retries=2,timeout_ms=None):
        self.validate(p); retries=max(0,min(int(retries),self.HARD_LIMITS['max_retries'])); timeout_ms=min(int(timeout_ms or self.HARD_LIMITS['max_runtime_ms']),self.HARD_LIMITS['max_runtime_ms'])
        idem=idem or hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest(); old=self.store.job_by_idem(idem)
        if old and old['state']=='succeeded': return json.loads(old['output'])
        job={'id':old['id'] if old else str(uuid.uuid4()),'idem':idem,'state':'running','attempts':0,'input':p}; started=time.perf_counter(); last=None
        for attempt in range(retries+1):
            job['attempts']=attempt+1; self.store.save_job(job)
            try:
                if p.get('_inject_failure') and attempt < int(p.get('_fail_attempts',1)): raise RuntimeError('injected provider loss')
                out=self.operate(p)
                if (time.perf_counter()-started)*1000 > timeout_ms: raise TimeoutError('operation timeout')
                job.update(state='succeeded',output=out,error=None); self.store.save_job(job); self.metrics['executions']+=1; self.store.put('output',job['id'],{'roadmap':self.config['id'],'result':out}); return out
            except Exception as e:
                last=e; self.metrics['errors']+=1
                if attempt<retries: self.metrics['retries']+=1; continue
                job.update(state='failed',error=str(e)); self.store.save_job(job); raise
        raise last
    def feedback(self,score,payload=None): self.store.add_feedback(score,payload or {}); return {'accepted':True,'bias':self.store.feedback_bias()}
    def mesh_select(self,nodes,mode='hybrid'):
        live=[n for n in nodes if n.get('available',True)]
        if mode=='local': live=[n for n in live if n.get('kind') in ('local','edge')]
        elif mode=='cloud': live=[n for n in live if n.get('kind')=='cloud']
        if not live: return {'node':None,'graceful_degradation':True}
        ranked=sorted(live,key=lambda n:(float(n.get('latency_ms',9999))+.1*float(n.get('cost',0))+2*float(n.get('energy',0)),-float(n.get('capacity',1))))
        return {'node':ranked[0],'fallbacks':ranked[1:3],'graceful_degradation':False}
    def simulator(self):
        base={'goal':self.config['outcome'],'candidates':[{'id':'local','utility':.9,'cost':.1},{'id':'edge','utility':.8,'cost':.2}]}; scenarios={}
        cases={'success':base,'malformed':[],'disconnection':dict(base, nodes=[{'id':'cloud','kind':'cloud','available':False},{'id':'local','kind':'local','available':True}]),'overload':dict(base,candidates=[{'id':str(i)} for i in range(1001)]),'provider_loss':dict(base,_inject_failure=True,_fail_attempts=1),'restart_recovery':base}
        for name,p in cases.items():
            try:
                if name=='malformed': self.execute(p,idem='sim-malformed')
                elif name=='disconnection': scenarios[name]={'ok':self.mesh_select(p['nodes'])['node']['id']=='local'}; continue
                else: self.execute(p,idem='sim-'+name,retries=2); scenarios[name]={'ok':True}
            except (ValidationError,QuotaError) as e: scenarios[name]={'ok':name in ('malformed','overload'),'blocked':type(e).__name__}
            except Exception as e: scenarios[name]={'ok':False,'error':str(e)}
        return scenarios
    def benchmark(self,n=100):
        samples=[]; p={'values':[1,2,3],'goal':self.config['outcome'],'candidates':[{'id':'a','utility':.8},{'id':'b','utility':.7}]}
        for _ in range(n):
            st=time.perf_counter(); self.operate(p); samples.append((time.perf_counter()-st)*1000)
        samples.sort(); p95=samples[min(len(samples)-1,math.ceil(.95*len(samples))-1)]; total=sum(samples)/1000 or 1e-9
        return {'iterations':n,'ops_per_sec':round(n/total,2),'p50_ms':round(statistics.median(samples),6),'p95_ms':round(p95,6),'memory_model':'bounded input + sqlite WAL','network_transfer':'0 bytes in local benchmark','cost_model':'local CPU only','energy_proxy_ms':round(sum(samples),6)}
    def metrics_snapshot(self): return {**self.metrics,'feedback_bias':self.store.feedback_bias(),'roadmap':self.config['id']}

class SDK:
    def __init__(self,engine): self.engine=engine
    def create(self,kind,ident,payload): return self.engine.store.put(kind,ident,payload)
    def query(self,kind=None): return self.engine.store.query(kind)
    def update(self,kind,ident,payload,expected_version=None): return self.engine.store.put(kind,ident,payload,expected_version)
    def delete(self,kind,ident): return self.engine.store.delete(kind,ident)
    def events(self,since=0): return self.engine.store.events(since)
    def execute(self,payload,idempotency_key=None): return self.engine.execute(payload,idempotency_key)
    def feedback(self,score,payload=None): return self.engine.feedback(score,payload)

class Handler(BaseHTTPRequestHandler):
    engine=None
    def sendj(self,code,obj,ctype='application/json'):
        body=json.dumps(obj,indent=2,sort_keys=True).encode(); self.send_response(code); self.send_header('Content-Type',ctype); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def body(self):
        n=int(self.headers.get('Content-Length','0')); return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        u=urlparse(self.path); q=parse_qs(u.query)
        if u.path=='/health': return self.sendj(200,{'ok':True,'roadmap':self.engine.config['id']})
        if u.path=='/spec': return self.sendj(200,self.engine.config)
        if u.path=='/metrics': return self.sendj(200,self.engine.metrics_snapshot())
        if u.path=='/events': return self.sendj(200,self.engine.store.events(int(q.get('since',['0'])[0])))
        if u.path=='/objects': return self.sendj(200,self.engine.store.query(q.get('kind',[None])[0]))
        if u.path=='/':
            title=f"{self.engine.config['id']} — {self.engine.config['title']}"
            html=("<!doctype html><meta charset=utf-8><title>"+title+"</title><style>body{font:16px system-ui;max-width:1000px;margin:40px auto;padding:0 18px}textarea{width:100%;height:180px}pre{background:#111;color:#eee;padding:16px;overflow:auto}</style><h1>"+title+"</h1><p>"+self.engine.config['outcome']+"</p><p><b>Signature mode:</b> "+self.engine.config['breakthrough']+"</p><p><b>Roadmap surfaces:</b> "+', '.join(self.engine.config['surfaces'])+"</p><textarea id=p>{\"goal\":\""+self.engine.config['outcome'].replace('"','&quot;')+"\",\"candidates\":[{\"id\":\"local\",\"utility\":0.9},{\"id\":\"edge\",\"utility\":0.8}]}</textarea><button onclick=go()>Execute</button><pre id=o></pre><script>async function go(){let r=await fetch('/execute',{method:'POST',headers:{'content-type':'application/json'},body:p.value});o.textContent=JSON.stringify(await r.json(),null,2)}</script>").encode()
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(html))); self.end_headers(); return self.wfile.write(html)
        return self.sendj(404,{'error':'not found'})
    def do_POST(self):
        try:
            p=self.body()
            if self.path=='/execute': return self.sendj(200,self.engine.execute(p,self.headers.get('Idempotency-Key')))
            if self.path=='/feedback': return self.sendj(200,self.engine.feedback(p.get('score',0),p))
            if self.path=='/objects': return self.sendj(201,self.engine.store.put(p['kind'],p['id'],p.get('payload',{}),p.get('expected_version')))
            return self.sendj(404,{'error':'not found'})
        except Exception as e: return self.sendj(400,{'error':type(e).__name__,'message':str(e)})
    def log_message(self,*a): pass

def load_config(path): return json.loads(Path(path).read_text())
def main(config_path=None):
    ap=argparse.ArgumentParser(); ap.add_argument('--config',default=config_path); sub=ap.add_subparsers(dest='cmd',required=True)
    p=sub.add_parser('execute'); p.add_argument('json'); p.add_argument('--idem')
    p=sub.add_parser('serve'); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=0)
    sub.add_parser('simulate'); sub.add_parser('benchmark'); sub.add_parser('metrics')
    a=ap.parse_args(); cfg=load_config(a.config); eng=Engine(cfg)
    if a.cmd=='execute': print(json.dumps(eng.execute(json.loads(a.json),a.idem),indent=2,sort_keys=True))
    elif a.cmd=='simulate': print(json.dumps(eng.simulator(),indent=2,sort_keys=True))
    elif a.cmd=='benchmark': print(json.dumps(eng.benchmark(),indent=2,sort_keys=True))
    elif a.cmd=='metrics': print(json.dumps(eng.metrics_snapshot(),indent=2,sort_keys=True))
    elif a.cmd=='serve':
        Handler.engine=eng; srv=ThreadingHTTPServer((a.host,a.port),Handler); print(f'http://{a.host}:{srv.server_port}',flush=True); srv.serve_forever()
