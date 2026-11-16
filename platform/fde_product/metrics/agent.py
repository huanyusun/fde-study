"""Natural language -> validated intent -> native SQL -> executed evidence."""
import json,uuid,time,threading
from pathlib import Path
from .common import read,dump,call_json
ROOT=Path(__file__).resolve().parents[3]
class MetricsAgent:
 def __init__(self,project,out=None,model=None,answer_prompt=None):
  self.project=Path(project).resolve();self.catalog=read(self.project/'catalog.json');self.scope=read(self.project/'scope.json');self.data=read(self.project/'dataset.json')
  self.out=Path(out) if out else self.project/'runs';self.model=model
  self.active_catalog=[{k:v for k,v in item.items() if k!='sources'} for item in self.catalog] if self.data.get('grain_version')=='w05-verified-person-and-unresolved-source-1' else self.catalog
  self.answer_prompt=Path(answer_prompt) if answer_prompt else ROOT/'product/w03_answer_prompt.txt'
 def ask(self,question,history=None):
  if not isinstance(question,str) or not question.strip() or len(question)>6000:raise ValueError('QUESTION_INVALID')
  from .engine import query_worker
  folder=self.out/str(uuid.uuid4());folder.mkdir(parents=True,exist_ok=False);start=time.monotonic()
  dump(folder/'dataset_snapshot.json',self.data)
  dimensions=read(self.project/'dimensions.json')
  values={k:v['values'] for k,v in dimensions['dimensions'].items() if v['kind']!='time' and len(v['values'])<=1000}
  dictionary_notice={k:{'total':len(v['values']),'omitted_from_prompt':True,'meaning':'完整字典在运行时校验；模型可以引用用户明确给出的值，不能猜值。'} for k,v in dimensions['dimensions'].items() if v['kind']!='time' and len(v['values'])>1000}
  available={**dimensions,'dimensions':{k:{field:value for field,value in v.items() if field!='values'} for k,v in dimensions['dimensions'].items()}}
  try:
   intent=call_json((ROOT/'product/w03_intent_prompt.txt').read_text(),{'question':question,'history':(history or [])[-6:],'customer_context':self.scope,'data_context':self.data,'catalog':self.active_catalog,'filter_values':values,'large_dictionary_notice':dictionary_notice,'available_dimensions':available},folder/'intent-trace.json',model=self.model)
   if intent.get('status') in ['clarify','unsupported']:
    if not isinstance(intent.get('reason'),str) or not intent['reason'].strip():raise ValueError('INTENT_REASON_REQUIRED')
    result={'status':intent['status'],'reason':intent['reason'],'intent':intent}
   elif intent.get('status')=='query':
    intent={k:intent.get(k,[]) for k in ['metrics','start','end','group_by','filters']};result=query_worker(self.project,intent);result.setdefault('intent',intent)
    identity_metrics={'buyer_count','refund_buyer_count','new_member_count','first_buyer_count','monthly_buyer_count','monthly_repeat_buyer_count','monthly_repeat_rate','monthly_paid_buyer_count','monthly_paid_repeat_buyer_count','monthly_paid_repeat_rate','avg_buyer_value','purchase_frequency'}
    if result.get('status')=='ok' and self.data.get('grain_version')=='w05-verified-person-and-unresolved-source-1' and identity_metrics.intersection(intent['metrics']):
     result.update(status='partial',reason='当前统计含未决来源的独立财务桶，不能验收为精确自然人数或相关分母；金额和订单保留。',precise_person_total_acceptance='pending')
    dump(folder/'query_result.json',result)
    if result['status']=='ok':
     answer=call_json(self.answer_prompt.read_text(),{'question':question,'customer_context':self.scope,'data_context':self.data,'result':{k:v for k,v in result.items() if k!='sql'},'definitions':[x for x in self.active_catalog if x['id'] in intent['metrics']]},folder/'answer-trace.json',model=self.model)
     if not isinstance(answer.get('answer'),str):raise ValueError('ANSWER_TEXT_REQUIRED')
     result['answer']=answer['answer']
   else:raise ValueError('INTENT_STATUS_INVALID')
  except Exception as exc:
   result={'status':'error','code':getattr(exc,'code',str(exc) if isinstance(exc,ValueError) else type(exc).__name__),'reason':'本次调用未完成，请查看运行记录；不能把失败当成零。'}
  usage={};accounted=0
  for trace in folder.glob('*-trace.json'):
   observation=read(trace).get('usage',{})
   if observation:accounted+=1
   for key in ('prompt_tokens','completion_tokens','total_tokens'):
    value=observation.get(key)
    if isinstance(value,(int,float)) and not isinstance(value,bool):usage[key]=usage.get(key,0)+value
  if self.data.get('grain_version')=='w05-verified-person-and-unresolved-source-1':result.update(precise_person_total_acceptance='pending',entity_semantics='verified_person_with_unresolved_source_buckets',data_version=self.data['id'],catalog_sha256=self.data['library_sha256'])
  result.update(question=question,trace_id=folder.name,elapsed_seconds=round(time.monotonic()-start,3),model_usage=usage,model_calls_with_usage=accounted);dump(folder/'result.json',result);return result
