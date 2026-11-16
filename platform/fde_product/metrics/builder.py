"""Generic generation scaffolding. The learner supplies the building Skill."""
import copy,json,re,hashlib,shutil
from pathlib import Path
import yaml
from .common import read,dump,digest,call_json,new_output,configured_model
ROOT=Path(__file__).resolve().parents[3]
NAME=re.compile(r'^[a-z][a-z0-9_]*$')
def verify_library(folder):
 folder=Path(folder);body=yaml.safe_load((folder/'metrics.yml').read_text());catalog=read(folder/'catalog.json');scope=read(folder/'scope.json')
 if (folder/'dimension_targets.json').exists() and read(folder/'dimension_targets.json')!=read(ROOT/'templates/w03/dimension_targets.json'):raise ValueError('DIMENSION_TARGET_CONTRACT_MISMATCH')
 names=[m['name'] for m in body['metrics']];ids=[m['id'] for m in catalog]
 if len(names)!=len(set(names)) or set(names)!=set(ids) or len(ids)!=len(set(ids)):raise ValueError('LIBRARY_METRIC_CATALOG_MISMATCH')
 if not all(NAME.fullmatch(x) for x in names):raise ValueError('METRIC_ID_INVALID')
 measures=[m['name'] for s in body['semantic_models'] for m in s.get('measures',[])]
 if len(measures)!=len(set(measures)):raise ValueError('DUPLICATE_MEASURE_NAME')
 for item in catalog:
  if not all(item.get(k) for k in ['name','unit','sources']):raise ValueError('CATALOG_METADATA_REQUIRED:'+item['id'])
  policy=item.get('query_policy',{})
  if not isinstance(policy,dict) or set(policy)-{'full_month_only'} or ('full_month_only' in policy and type(policy['full_month_only']) is not bool):raise ValueError('QUERY_POLICY_INVALID')
 for f in [folder/'metrics.yml',*folder.glob('*.sql')]:
  text=f.read_text()
  if re.search(r'\b(read_csv\w*|read_parquet|read_json\w*|sqlite_scan|postgres_scan|httpfs|attach|install|load|copy|drop|delete|insert|update|create|env_var|run_query|config)\s*\(?',text,re.I):raise ValueError('UNSUPPORTED_SQL_OPERATION:'+f.name)
  if f.suffix=='.sql' and (not NAME.fullmatch(f.stem) or f.stem in {'orders','members','stores','cards','time_spine'} or not re.match(r'^\s*(with|select)\b',text,re.I)):raise ValueError('CUSTOM_MODEL_CONTRACT_INVALID')
 return {'metrics':len(names),'metric_ids':names,'customer':scope.get('customer')}

def generate(config_path,out,selected=None,model=None):
 config_path=Path(config_path).resolve();cfg=read(config_path);base=config_path.parent;out=new_output(out)
 def path(key):return (base/cfg[key]).resolve()
 skill=path('skill').read_text()
 if not skill.strip() or 'UNIMPLEMENTED' in skill:raise ValueError('STUDENT_SKILL_REQUIRED')
 business=path('business_model').read_text();materials={}
 for item in cfg['materials']:
  p=(base/item).resolve()
  files=sorted(p.rglob('*.md')) if p.is_dir() else [p]
  for f in files:
   if f.suffix.lower()!='.md':raise ValueError('MARKDOWN_MATERIAL_REQUIRED')
   if f.name in materials:raise ValueError('DUPLICATE_SOURCE_NAME:'+f.name)
   materials[f.name]=f.read_text()
 targets=read(path('targets'));ids=[x['id'] for x in targets] if not selected else selected
 if len(set(ids))!=len(ids) or not set(ids)<={x['id'] for x in targets}:raise ValueError('TARGET_SELECTION_INVALID')
 targets=[{'id':x['id'],'name':x['name']} for x in targets if x['id'] in ids]
 from .engine import TABLES
 contract=read(ROOT/'contracts/w03/build_response.example.json')
 dimension_targets=read(ROOT/'templates/w03/dimension_targets.json')
 if not cfg.get('data'):raise ValueError('BUILD_DATA_REQUIRED_FOR_VALIDATION')
 if model is None:model=configured_model(32768)
 out.mkdir(parents=True,exist_ok=False)
 payload={'business_model_filename':'business_model.md','business_model':business,'materials':materials,'targets':targets,'access_tables':TABLES,'dimension_targets':dimension_targets,'native_format':'dbt semantic_models/measures; MetricFlow 0.213; DuckDB','contract':contract}
 dump(out/'input.json',payload)
 (out/'skill_used.md').write_text(skill)
 response=call_json(skill,payload,out/'trace.json',model=model,budget=32768);dump(out/'response.json',response)
 defined=[m['name'] for m in response.get('metrics',[])];pending=[m['metric_id'] for m in response.get('unresolved',[]) if m.get('metric_id')]
 if set(defined)|set(pending)!=set(ids) or set(defined)&set(pending) or len(defined)!=len(set(defined)) or len(pending)!=len(set(pending)):raise ValueError('OUTPUT_TARGET_COVERAGE_INVALID')
 if {m['id'] for m in response.get('catalog',[])}!=set(defined):raise ValueError('OUTPUT_CATALOG_MISMATCH')
 sources={'business_model.md':business,**materials};source_errors=[]
 for item in response.get('catalog',[]):
  for source in item.get('sources',[]):
   if not source.get('quote') or source.get('file') not in sources or source['quote'] not in sources[source['file']]:source_errors.append({'metric_id':item['id'],'source':source})
 for usage in response.get('business_model_usage',[]):
  if not usage.get('quote') or usage['quote'] not in business:source_errors.append({'model_usage':usage})
 dump(out/'source_check.json',{'passed':not source_errors,'errors':source_errors})
 if source_errors:raise ValueError('SOURCE_QUOTE_NOT_EXACT: revise Skill and regenerate; see source_check.json')
 provenance={'skill_sha256':hashlib.sha256(skill.encode()).hexdigest(),'input_hashes':{k:hashlib.sha256(v.encode()).hexdigest() for k,v in sources.items()},'defined':defined,'unresolved':response.get('unresolved',[]),'business_model_usage':response.get('business_model_usage',[])}
 dump(out/'provenance.json',provenance)
 publish_candidate(response,cfg['scope'],dimension_targets,path('data'),out)
 return {'output':str(out),'defined':len(defined),'unresolved':len(pending),'checks_passed':True}

def publish_candidate(response,scope,targets,data,out):
 """Failed candidates are diagnostic-only; no root metrics.yml is published."""
 out=Path(out);candidate=out/'candidate';candidate.mkdir()
 for name,body in response.get('model_sql',{}).items():
  if not NAME.fullmatch(name) or name in {'orders','members','stores','cards','time_spine'}:raise ValueError('CUSTOM_MODEL_NAME_INVALID')
  (candidate/(name+'.sql')).write_text(body,newline='\n')
 models=response.get('semantic_models',[])
 if not models or len({s['name'] for s in models})!=len(models):raise ValueError('SEMANTIC_MODELS_REQUIRED_OR_DUPLICATE')
 grains=response.get('grain_keys',{})
 if set(grains)!={sm['name'] for sm in models}:raise ValueError('GRAIN_KEYS_REQUIRED_FOR_EVERY_MODEL')
 for name,keys in grains.items():
  if not isinstance(keys,list) or not keys or not all(isinstance(k,str) and NAME.fullmatch(k) for k in keys):raise ValueError('GRAIN_COLUMNS_REQUIRED:'+name)
 for sm in models:
  if not all(k in sm for k in ['name','model','entities','dimensions']):raise ValueError('COMPLETE_SEMANTIC_MODEL_REQUIRED')
 (candidate/'metrics.yml').write_text(yaml.safe_dump({'version':2,'semantic_models':models,'metrics':response['metrics']},allow_unicode=True,sort_keys=False),newline='\n')
 for name,value in [('catalog.json',response['catalog']),('scope.json',scope),('dimension_targets.json',targets),('grain_contract.json',response.get('grain_keys',{})),('unresolved.json',response.get('unresolved',[]))]:dump(candidate/name,value)
 dump(candidate/'candidate_only.json',{'status':'validating'})
 project=out/'validation-project'
 try:
  verify_library(candidate)
  from .engine import build_project
  build_project(candidate,data,project)
 finally:
  for name in ['grain_check.json','dimension_check.json','metricflow_check.json','validation.json']:
   if (project/name).exists():shutil.copy2(project/name,out/name)
 # Only executable inputs are copied; traces and credentials are never library inputs.
 for f in candidate.iterdir():
  if f.name!='candidate_only.json':shutil.copy2(f,out/f.name)
 dump(candidate/'candidate_only.json',{'status':'validated','published_to':str(out)})

def merge(folders,out,data):
 out=new_output(out);models={};metrics=[];catalog=[];provenance=[];scope=None;sqls={};grains={};targets=None;unresolved=[]
 for f in map(Path,folders):
  verify_library(f)
  p=read(f/'provenance.json')
  if any(x.get('metric_id') for x in p.get('unresolved',[])):raise ValueError('UNRESOLVED_BATCH:'+str(f))
  if provenance and p['input_hashes']!=provenance[0]['input_hashes']:raise ValueError('BATCH_SOURCE_VERSION_MISMATCH')
  current=read(f/'scope.json')
  if scope is not None and scope!=current:raise ValueError('BATCH_CUSTOMER_MISMATCH')
  scope=current;provenance.append(p);body=yaml.safe_load((f/'metrics.yml').read_text());metrics.extend(body['metrics']);catalog.extend(read(f/'catalog.json'))
  for sm in body['semantic_models']:
   if sm['name'] in models and models[sm['name']]!=sm:raise ValueError('BATCH_SEMANTIC_MODEL_CONFLICT:'+sm['name'])
   models[sm['name']]=copy.deepcopy(sm)
  for source in f.glob('*.sql'):
   text=source.read_text()
   if source.stem in sqls and sqls[source.stem]!=text:raise ValueError('BATCH_SQL_CONFLICT')
   sqls[source.stem]=text
  for name,keys in read(f/'grain_contract.json').items():
   if name in grains and grains[name]!=keys:raise ValueError('BATCH_GRAIN_CONFLICT')
   grains[name]=keys
  current_targets=read(f/'dimension_targets.json')
  if targets is not None and targets!=current_targets:raise ValueError('BATCH_DIMENSION_TARGET_CONFLICT')
  targets=current_targets;unresolved.extend(read(f/'unresolved.json'))
 response={'semantic_models':list(models.values()),'metrics':metrics,'catalog':catalog,'model_sql':sqls,'grain_keys':grains,'unresolved':unresolved}
 out.mkdir(parents=True,exist_ok=False);dump(out/'response.json',response)
 publish_candidate(response,scope,targets,data,out)
 dump(out/'provenance.json',{'batches':provenance})
 return verify_library(out)
