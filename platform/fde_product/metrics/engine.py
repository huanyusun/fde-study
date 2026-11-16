"""Native MetricFlow execution. One customer/project per worker process."""
import os,json,shutil,subprocess,sys,time,re,hashlib,tempfile,threading,csv
from pathlib import Path
from datetime import datetime,timedelta
import yaml,duckdb
from .common import read,dump,digest,library_digest
_CONTEXT_LOCK=threading.RLock()
_ACTIVE_PROJECT=None
ROOT=Path(__file__).resolve().parents[3]
os.environ['DBT_SEND_ANONYMOUS_USAGE_STATS']='false'
from dbt_metricflow.cli.cli_configuration import CLIConfiguration
from metricflow.engine.metricflow_engine import MetricFlowQueryRequest

TABLES={
 'members':{'member_id':'VARCHAR','registered_at':'DATE','home_store_id':'VARCHAR','tier':'VARCHAR'},
 'stores':{'store_id':'VARCHAR','region':'VARCHAR','store_name':'VARCHAR'},
 'orders':{'order_id':'VARCHAR','member_id':'VARCHAR','store_id':'VARCHAR','ordered_at':'DATE','status':'VARCHAR','gross_cents':'BIGINT','paid_cents':'BIGINT','refund_cents':'BIGINT','quantity':'BIGINT','channel':'VARCHAR'},
 'cards':{'card_id':'VARCHAR','member_id':'VARCHAR','card_type':'VARCHAR','valid_from':'DATE','valid_until':'DATE','ended_at':'DATE','card_paid_cents':'BIGINT'}}

def build_project(library,data,project):
 library=Path(library).resolve();data=Path(data).resolve();p=Path(project).resolve()
 if p.exists():raise ValueError('PROJECT_ALREADY_EXISTS: use a new version path')
 from .builder import verify_library
 verify_library(library)
 manifest=read(data/'manifest.json')
 for date in manifest['coverage']:datetime.strptime(date,'%Y-%m-%d')
 if len(manifest['coverage'])!=2 or manifest['coverage'][0]>=manifest['coverage'][1]:raise ValueError('DATA_COVERAGE_INVALID')
 for name in TABLES:
  if digest(data/(name+'.csv'))!=manifest['sha256'][name+'.csv']:raise ValueError('DATA_HASH_MISMATCH:'+name)
 p.mkdir(parents=True)
 shutil.copytree(ROOT/'templates/w03/models',p/'models')
 shutil.copy2(library/'metrics.yml',p/'models/metrics.yml')
 for extra in library.glob('*.sql'):shutil.copy2(extra,p/'models'/extra.name)
 for name in ['catalog.json','scope.json']:shutil.copy2(library/name,p/name)
 for name,default in [('dimension_targets.json',read(ROOT/'templates/w03/dimension_targets.json')),('grain_contract.json',{}),('unresolved.json',[])]:dump(p/name,read(library/name) if (library/name).exists() else default)
 library_hash=library_digest(library)
 metadata={**manifest,'id':manifest.get('id',data.name),'library_sha256':library_hash}
 dump(p/'dataset.json',metadata)
 con=duckdb.connect(str(p/'data.duckdb'))
 try:
  for name,columns in TABLES.items():
   types='{'+','.join("'"+k+"':'"+v+"'" for k,v in columns.items())+'}'
   with (data/(name+'.csv')).open(newline='') as raw:
    header=next(csv.reader(raw))
   if set(header)!=set(columns) or len(header)!=len(columns):raise ValueError('CSV_COLUMNS_MISMATCH:'+name)
   con.execute('create table raw_'+name+' as select * from read_csv(?, header=true, types='+types+')',[str(data/(name+'.csv'))])
   if con.execute('select count(*) from raw_'+name).fetchone()[0]!=manifest['counts'][name]:raise ValueError('DATA_COUNT_MISMATCH:'+name)
  for name,key in [('members','member_id'),('orders','order_id'),('stores','store_id'),('cards','card_id')]:
   if con.execute(f'select count(*)-count(distinct {key}) from raw_{name}').fetchone()[0]:raise ValueError('DUPLICATE_OR_NULL_KEY:'+name)
  for name in ['orders','cards']:
   if con.execute(f'select count(*) from raw_{name} x left join raw_members m using(member_id) where m.member_id is null').fetchone()[0]:raise ValueError('UNLINKED_ACCOUNT:'+name)
 finally:con.close()
 (p/'dbt_project.yml').write_text(yaml.safe_dump({'name':'w03','version':'1.0','config-version':2,'profile':'w03','model-paths':['models'],'vars':{'coverage_start':manifest['coverage'][0],'coverage_end':manifest['coverage'][1]},'flags':{'send_anonymous_usage_stats':False},'models':{'w03':{'+materialized':'view'}}}))
 (p/'profiles.yml').write_text(yaml.safe_dump({'w03':{'target':'dev','outputs':{'dev':{'type':'duckdb','path':str(p/'data.duckdb'),'schema':'main','threads':1}}}}))
 binary=Path(sys.executable).parent/('dbt.exe' if os.name=='nt' else 'dbt')
 r=subprocess.run([str(binary),'run','--profiles-dir',str(p),'--project-dir',str(p)],capture_output=True,text=True,timeout=300)
 (p/'build.log').write_text(r.stdout+r.stderr)
 if r.returncode:
  for name in ['dimension_check.json','grain_check.json','metricflow_check.json']:dump(p/name,{'passed':False,'reason':'DBT_BUILD_FAILED; checks not executed'})
  raise ValueError('DBT_BUILD_FAILED: '+str(p/'build.log'))
 check=subprocess.run([sys.executable,str(ROOT/'tools/w03.py'),'_inspect-worker','--project',str(p)],capture_output=True,text=True,timeout=300)
 (p/'validation.log').write_text(check.stdout+check.stderr)
 if check.returncode or not (p/'validation.json').exists() or not read(p/'validation.json').get('passed'):raise ValueError('PROJECT_VALIDATION_FAILED: '+str(p/'validation.log'))
 return p

def query_worker(project,intent):
 with tempfile.TemporaryDirectory(prefix='fde-w03-query-') as tmp:
  inp=Path(tmp)/'request.json';out=Path(tmp)/'response.json';dump(inp,intent)
  r=subprocess.run([sys.executable,str(ROOT/'tools/w03.py'),'_query-worker','--project',str(Path(project).resolve()),'--input',str(inp),'--output',str(out)],capture_output=True,text=True,timeout=180)
  if not out.exists():return {'status':'error','code':'QUERY_WORKER_FAILED','reason':r.stderr[-2000:]}
  return read(out)

class Engine:
 def __init__(self,project,read_only=False):
  global _ACTIVE_PROJECT
  with _CONTEXT_LOCK:
   self.read_only=read_only
   self._initialize(project)
   _ACTIVE_PROJECT=str(self.project.resolve())
 def _initialize(self,project):
  self.project=Path(project)
  if not (self.project/'validation.json').exists() or not read(self.project/'validation.json').get('passed'):raise ValueError('PROJECT_NOT_VALIDATED')
  profiles_dir=self.project
  if getattr(self,'read_only',False):
   # The query worker only reads: a read-only copy of the profile lets concurrent workers share data.duckdb.
   self._profiles=tempfile.TemporaryDirectory(prefix='fde-w03-profile-');profiles=yaml.safe_load((self.project/'profiles.yml').read_text())
   for profile in profiles.values():
    for output in profile.get('outputs',{}).values():output['config_options']={**(output.get('config_options') or {}),'access_mode':'READ_ONLY'}
   (Path(self._profiles.name)/'profiles.yml').write_text(yaml.safe_dump(profiles));profiles_dir=Path(self._profiles.name)
  self.cfg=CLIConfiguration();self.cfg.setup(dbt_profiles_path=profiles_dir,dbt_project_path=self.project)
  self.dataset=json.loads((self.project/'dataset.json').read_text())
  self.dataset_hash=__import__('hashlib').sha256(json.dumps({k:v for k,v in self.dataset.items() if k!="library_sha256"},sort_keys=True).encode()).hexdigest()
  self.metric_names={m.name for m in self.cfg.mf.list_metrics()}
  self.dimensions=read(self.project/'dimensions.json')
  self.allowed_values={k:set(v['values']) for k,v in self.dimensions['dimensions'].items()}
  self.policies={m['id']:m.get('query_policy',{}) for m in json.loads((self.project/'catalog.json').read_text())}
  self.units={m['id']:m.get('unit') for m in json.loads((self.project/'catalog.json').read_text())}
  self.definitions={m['name']:m for m in yaml.safe_load((self.project/'models/metrics.yml').read_text())['metrics']}
 def query(self,intent):
  with _CONTEXT_LOCK:
   if _ACTIVE_PROJECT!=str(self.project.resolve()):raise RuntimeError('PROJECT_CONTEXT_CHANGED: isolate each dataset/customer in its own worker process')
   return self._query(intent)
 def _query(self,intent):
  if not isinstance(intent,dict):return {'status':'unsupported','reason':'查询意图格式错误'}
  metrics=intent.get('metrics',[]);group=intent.get('group_by',[]);start=intent.get('start');end=intent.get('end');filters=intent.get('filters',[])
  if not isinstance(metrics,list) or not all(isinstance(x,str) for x in metrics) or len(set(metrics))!=len(metrics):return {'status':'unsupported','reason':'指标列表非法'}
  if not isinstance(group,list) or not all(isinstance(x,str) for x in group) or len(set(group))!=len(group) or not isinstance(filters,list):return {'status':'unsupported','reason':'维度或筛选格式错误'}
  if start and end:
   try:
    for value in (start,end):
     if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError()
     datetime.strptime(value,'%Y-%m-%d')
   except (ValueError,TypeError):return {'status':'unsupported','reason':'需要有效的 ISO 日期'}
  if not start or not end:return {'status':'clarify','reason':'需要明确时间范围'}
  if start<self.dataset['coverage'][0] or end>self.dataset['coverage'][1] or start>=end:return {'status':'unsupported','reason':'超出数据覆盖或时间范围非法'}
  if not metrics or not set(metrics)<=self.metric_names:return {'status':'unsupported','reason':'指标未定义'}
  if any(self.policies.get(m,{}).get('full_month_only') for m in metrics):
   if start[-2:]!='01' or end[-2:]!='01' or filters or set(group)-{'metric_time__month'}:return {'status':'unsupported','reason':'所选指标只支持完整自然月、全门店全渠道'}
   delta=(int(end[:4])-int(start[:4]))*12+int(end[5:7])-int(start[5:7])
   if delta!=1 and group!=['metric_time__month']:return {'status':'unsupported','reason':'所选月度指标跨月查询必须按月展示'}
  allowed=set(self.dimensions['dimensions'])
  for metric in metrics:allowed &= set(self.dimensions['per_metric'].get(metric,[]))
  if not set(group)<=allowed:return {'status':'unsupported','reason':'分组维度未支持当前指标'}
  mapping={}
  for key in allowed:
   names={self.dimensions['per_metric'][m][key] for m in metrics}
   if len(names)==1:mapping[key]=names.pop()
  if not set(group)<=set(mapping):return {'status':'unsupported','reason':'指标之间的维度路径不同，需分别查询'}
  wh=[]
  for f in filters:
   if not isinstance(f,dict) or set(f)!={'field','op','value'}:return {'status':'unsupported','reason':'筛选格式错误'}
   field=f['field'];op=f['op'];v=f['value']
   if not isinstance(field,str) or not isinstance(op,str):return {'status':'unsupported','reason':'筛选格式错误'}
   if field not in mapping or field.startswith('metric_time') or op not in ['eq','in']:return {'status':'unsupported','reason':'筛选条件未支持'}
   if op=='eq' and not isinstance(v,str):return {'status':'unsupported','reason':'eq 需要单个字符串值'}
   if op=='in' and not isinstance(v,list):return {'status':'unsupported','reason':'in 需要字符串列表'}
   vals=v if isinstance(v,list) else [v]
   if not vals or len(vals)>50 or not all(isinstance(x,str) for x in vals):return {'status':'unsupported','reason':'筛选值非法'}
   if not set(vals)<=self.allowed_values.get(field,set()):return {'status':'unsupported','reason':'筛选值不在本次测试数据字典或实体范围中，不能视为零'}
   safe=["'"+x.replace("'","''")+"'" for x in vals]
   native_field=mapping[field]
   lhs="{{ Entity('"+native_field+"') }}" if self.dimensions['dimensions'][field]['kind']=='entity' else "{{ Dimension('"+native_field+"') }}"
   wh.append(lhs+' in ('+','.join(safe)+')')
  # Dates are normalized to a half-open interval; native MF end is inclusive.
  req=MetricFlowQueryRequest.create(metric_names=metrics,group_by_names=[mapping[k] for k in group] or None,time_constraint_start=datetime.fromisoformat(start),time_constraint_end=datetime.fromisoformat(end)-timedelta(days=1),where_constraints=wh or None)
  ts=time.monotonic()
  try:expl=self.cfg.mf.explain(mf_request=req);res=self.cfg.mf.query(mf_request=req)
  except Exception as exc:return {'status':'error','code':'NATIVE_QUERY_FAILED','reason':str(exc),'intent':intent}
  df=res.result_df
  # A covered empty aggregate has a known zero for additive/count metrics only.
  # Ratios remain undefined; absent coverage was rejected above.
  rows=[list(row) for row in df.rows]
  if not group:
   for row in rows:
    for i,c in enumerate(df.column_names):
     if row[i] is None and self.definitions.get(c,{}).get('type')=='simple':row[i]=0
  return {'status':'ok','intent':intent,'sql':expl.sql_statement.without_descriptions.sql,'columns':[{mapping[k]:k for k in group}.get(c,c) for c in df.column_names],'rows':[[str(v) if hasattr(v,'isoformat') else v for v in row] for row in rows],'seconds':round(time.monotonic()-ts,3),'units':{m:self.units.get(m) for m in metrics},'data_version':self.dataset['id'],'data_sha256':self.dataset_hash,'catalog_sha256':self.dataset['library_sha256']}

