"""Shared file and model IO; no instructor configuration discovery."""
import hashlib,json,re,time
from pathlib import Path
from ..models import CompatibleModel,ModelError

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=str)+'\n',newline='\n')
def read(path):return json.loads(Path(path).read_text())
def call_json(system,payload,trace,*,model=None,budget=8192):
 model=model or CompatibleModel(max_tokens=budget,retry_max_tokens=budget*2,timeout=180,retry_timeout=240)
 messages=[{'role':'system','content':system},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
 start=time.monotonic();record={'messages':messages,'model':getattr(model,'model','test-double')}
 try:
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
