"""Shared file and model IO; no instructor configuration discovery."""
import hashlib,json,re,time
from pathlib import Path
from ..models import CompatibleModel,ModelError

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',newline='\n')
def read(path):return json.loads(Path(path).read_text())
def library_digest(folder):
 # Recorded in dataset.json at load and returned as catalog_sha256 with every executed query.
 folder=Path(folder);return hashlib.sha256(json.dumps({f.name:digest(f) for f in sorted(folder.iterdir()) if f.suffix in ['.json','.yml','.sql']},sort_keys=True).encode()).hexdigest()
def new_output(path):
 # Checked before any work so that a failed precheck never takes the output name.
 path=Path(path).resolve()
 if path.exists():raise ValueError('OUTPUT_ALREADY_EXISTS: '+str(path)+'; use a new version path')
 return path
def configured_model(budget=8192):return CompatibleModel(max_tokens=budget,retry_max_tokens=budget*2,timeout=180,retry_timeout=240)
def call_json(system,payload,trace,*,model=None,budget=8192):
 messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
 start=time.monotonic();record={'messages':messages,'model':getattr(model,'model','test-double') if model is not None else None}
 try:
  # Constructed inside try: a configuration failure is still written to the trace.
  if model is None:model=configured_model(budget);record['model']=getattr(model,'model','test-double')
  reply,usage=model.complete(messages,[]);content=reply.get('content','').strip()
  record.update(reply={k:reply[k] for k in ('role','content') if k in reply},usage=usage)
  if content.startswith('```'):content=re.sub(r'^```(?:json)?\s*|\s*```$','',content)
  result=json.loads(content)
  if not isinstance(result,dict):raise ValueError('MODEL_JSON_OBJECT_REQUIRED')
  return result
 except Exception as exc:
  record['error']=getattr(exc,'code',type(exc).__name__);raise
 finally:
  record.update(seconds=round(time.monotonic()-start,3),call=getattr(model,'last_call',{}));dump(trace,record)
