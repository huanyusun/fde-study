"""Shared read-only member capability; all hard decisions derive from bound data."""
import json,sys,subprocess,tempfile,hashlib
from pathlib import Path
from collections import defaultdict
from datetime import date,timedelta
from decimal import Decimal
from .records import read_json,read_csv,sha,dump
from .contracts import CohortRequest,Page
from .knowledge import retrieve
from .semantics import card_semantics,decision_basis,follow_up_requirements

def load_lines(path):
 with Path(path).open() as f:return [json.loads(s) for s in f if s.strip()]
def _tool(name,description,properties,required):return {'type':'function','function':{'name':name,'description':description,'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}}
OPS={'gte':lambda a,b:a>=b,'gt':lambda a,b:a>b,'lte':lambda a,b:a<=b,'lt':lambda a,b:a<b,'eq':lambda a,b:a==b}
def number(value):return Decimal(str(value))
PAGE={'type':'object','properties':{'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':1000}},'additionalProperties':False}
class Service:
 def __init__(self,context):
  self.project=Path(context['project']);self.dataset=context['dataset'];self.state=Path(context['configuration']['state']);self.manifest=read_json(self.state/'manifest.json')
  if self.dataset['id']!=self.manifest['data_version']:raise ValueError('STATE_DATA_VERSION_MISMATCH')
  for name,h in self.manifest['files'].items():
   if sha(self.state/name)!=h:raise ValueError('STATE_HASH_MISMATCH')
  from .projection import read_objects
  objects=Path(context['configuration']['objects'])
  self.members,self.sources=read_objects(objects/'objects.duckdb',objects/'generated/orm.py')
  self.policies={r['member_id']:r for r in load_lines(self.state/'policies.jsonl')}
  self.mapping=read_json(self.state/'mapping.json');self.buckets=read_json(self.state/'unresolved_buckets.json')
  self.cards=defaultdict(list)
  for r in load_lines(self.state/'card_sources.jsonl'):self.cards[r['member_id']].append(r)
  self.source_orders={r['order_id']:r for r in read_csv(self.state/'order_sources.csv')};self.cache={}
  self.unknown_store_count=sum(not r['registered_stores'] and r['identity_status']=='verified' for r in self.members.values())
 def schemas(self):
  return [
   {'type':'function','function':{'name':'member_cohort','description':'通过原 MetricFlow 指标计算统一会员圈选：metric_filters 使用当前指标目录中可按会员计算的指标（最多 3 条、同时满足，同一指标可给上下限），可选最近有效购买间隔条件 dormant_days（至少满 N 天）或 active_within_days（不足 N 天）；可选会员等级 tiers（当前数据的等级取值：'+'、'.join(self.known_tiers())+'）、注册日期 registered_from／registered_before、多家注册门店 store_ids（与 store_id 不能同时填）；可选两期对比 comparison（基期窗口在本期 start 之前，按 direction 与 min_ratio 筛选下降或上升的会员，此时 metric_filters 可以不填）。随后应用来源账户注册门店、运营核验和分渠道限制。条件按用户实际要求填写，不自行增删；金额单位是分，用户说的是元时，把元数乘以 100 再填。当前快照 reference_date=2026-09-01。示例：本轮沉睡召回任务（近 12 个月净消费不少于 3000 元、距最近有效购买满 60 天）为 net_sales_cents>=300000、dormant_days=60、start=2025-09-01、end=2026-09-01。等级或注册日期未知的会员不会被丢掉，其余条件满足时列入待核。用户提出的条件不能用这些字段表达时（例如会员卡、条件之间的或关系、基期对比以外的多个窗口、月度类指标、超过 3 条指标条件、不带任何指标条件只按属性列会员），把原话逐条填入 unsupported_conditions，不能丢掉这些条件后照常圈选；填写后本工具不返回名单，应向用户说明缺口。门店未知只给范围说明，不重复纳入每家店待核。channel 不填时只是条件分析，不提供单一可联系总数。分页后 member_ids 为本页。','parameters':CohortRequest.model_json_schema()}},
   _tool('get_member','取得已验证会员属性、原始来源、最近消费及程序决定的详情安全条件（recommendation_decision），tier 仅用于知识上下文，不参与资格；完整圈选另查 member_cohort。须明确 channel。',{'member_id':{'type':'string'},'reference_date':{'type':'string','format':'date'},'dormant_days':{'type':'integer','minimum':1,'maximum':3650},'channel':{'enum':['telephone','sms','all']}},['member_id']),
   _tool('member_relations','查看来源账户、所有注册门店关系、实际订单及原始卡记录，包括财务隔离的卡；cards.semantics 的购卡金额单位 CNY（元），生效／到期／停卡日分别对应 st_dt／ed_dt／stop_dt，raw 保留。购买门店不能替代注册门店。',{'member_id':{'type':'string'},'page':PAGE},['member_id']),
   _tool('retrieve_knowledge','通过真实 LlamaIndex 本地知识索引检索业务依据原文，包含文件、版本、有效期、适用条件及片段 ID。知识不能解除程序禁联规则。',{'query':{'type':'string','minLength':1,'maxLength':2000},'reference_date':{'type':'string','format':'date'},'context':{'type':'object'},'level':{'enum':['domain','definition','usage']},'limit':{'type':'integer','minimum':1,'maximum':20}},['query'])]
 def call(self,name,args):
  if name=='member_cohort':return self.cohort(args)
  if name=='get_member':return self.detail(args)
  if name=='member_relations':return self.relations(args)
  return retrieve(self.knowledge_index(),args['query'],args.get('reference_date',self.dataset['reference_date']),context=args.get('context'),level=args.get('level'),limit=args.get('limit',5))
 def knowledge_index(self):
  # The index sits next to state in the prepared directory. Older manifests stored an absolute
  # path, which would still point at the original after a copy or move.
  stored=Path(self.manifest['knowledge_index'])
  return self.state.parent/('knowledge-index' if stored.is_absolute() else stored)
 def aggregate_intent(self,r):
  # Two bounds on one metric select that metric once; both comparisons still apply.
  return {'metrics':list(dict.fromkeys(f.metric for f in r.metric_filters)),'group_by':['member'],'start':str(r.start),'end':str(r.end),'filters':[]}
 def run_aggregate(self,intent,filters):
  key=json.dumps([intent,filters],sort_keys=True)
  if key not in self.cache:
   with tempfile.TemporaryDirectory(prefix='w05-aggregate-') as folder:
    inp,out=Path(folder)/'in.json',Path(folder)/'out.json';dump(inp,{'intent':intent,'filters':filters,'_all':True})
    worker=Path(__file__).resolve().parents[3]/'tools/w05.py'
    done=subprocess.run([sys.executable,str(worker),'_query-worker','--input',str(inp),'--output',str(out),'--project',str(self.project)],capture_output=True,text=True,timeout=180)
    if done.returncode:raise ValueError('MEMBER_AGGREGATE_FAILED')
    self.cache[key]=read_json(out)
  return self.cache[key]
 def aggregates(self,r):return self.run_aggregate(self.aggregate_intent(r),[f.model_dump() for f in r.metric_filters])
 def known_tiers(self):
  # The values actually compared: tiers present on bound member objects.
  if 'tiers' not in self.cache:self.cache['tiers']=sorted({a['tier'] for a in self.members.values() if a.get('tier')})
  return self.cache['tiers']
 def existing_stores(self):
  if 'stores' not in self.cache:
   import duckdb
   con=duckdb.connect(str(self.project/'data.duckdb'),read_only=True)
   try:self.cache['stores']={x[0] for x in con.execute('select store_id from raw_stores').fetchall()}
   finally:con.close()
  return self.cache['stores']
 def registered_dates(self):
  if 'registered' not in self.cache:
   import duckdb
   con=duckdb.connect(str(self.project/'data.duckdb'),read_only=True)
   try:self.cache['registered']=dict(con.execute('select member_id,registered_at from raw_members where registered_at is not null').fetchall())
   finally:con.close()
  return self.cache['registered']
 def metric_kinds(self):
  if 'kinds' not in self.cache:
   import yaml
   self.cache['kinds']={'types':{m['name']:m.get('type') for m in yaml.safe_load((self.project/'models/metrics.yml').read_text())['metrics']},
    'monthly':{m['id'] for m in read_json(self.project/'catalog.json') if m.get('query_policy',{}).get('full_month_only')},
    'by_member':{k for k,v in read_json(self.project/'dimensions.json')['per_metric'].items() if 'member' in v}}
  return self.cache['kinds']
 def compared(self,r):
  """Two-window comparison on one additive metric. Candidates are members with a baseline record;
  a covered current window without a record is a known zero; a non-positive baseline has no ratio."""
  c=r.comparison;kinds=self.metric_kinds();metrics=list(dict.fromkeys([f.metric for f in r.metric_filters]+[c.metric]))
  if c.metric not in kinds['types']:return {'status':'unsupported','code':'COMPARISON_METRIC_NOT_SUPPORTED','reason':'对比指标未定义','member_ids':[]}
  if kinds['types'][c.metric]!='simple' or c.metric in kinds['monthly'] or c.metric not in kinds['by_member']:return {'status':'unsupported','code':'COMPARISON_METRIC_NOT_SUPPORTED','reason':'两期对比只接受可加总、能按会员计算、非月度类的指标','member_ids':[]}
  base=self.run_aggregate({'metrics':[c.metric],'group_by':['member'],'start':str(c.baseline_start),'end':str(c.baseline_end),'filters':[]},[])
  if base['status']!='ok':return {**base,'comparison_window':'baseline'}
  current=self.run_aggregate({'metrics':metrics,'group_by':['member'],'start':str(r.start),'end':str(r.end),'filters':[]},[])
  if current['status']!='ok':return {**current,'comparison_window':'current'}
  member=current['columns'].index('member');now={row[member]:dict(zip(current['columns'],row)) for row in current['rows']}
  member=base['columns'].index('member');value=base['columns'].index(c.metric);rows=[];detail={};stats={'baseline_candidates':0,'non_positive_baseline':0,'below_min_baseline_value':0,'comparison_hits':0,'current_missing_counted_as_zero':0}
  for row in base['rows']:
   mid=row[member]
   if row[value] is None:continue
   stats['baseline_candidates']+=1;before=number(row[value])
   if before<=0:stats['non_positive_baseline']+=1;continue
   if c.min_baseline_value is not None and before<number(c.min_baseline_value):stats['below_min_baseline_value']+=1;continue
   values=now.get(mid,{});raw=values.get(c.metric);after=number(raw) if raw is not None else Decimal(0);change=(after-before)/before
   if (-change if c.direction=='decrease' else change)<number(c.min_ratio):continue
   stats['comparison_hits']+=1
   # Inside this candidate set a missing additive value in the covered current window is zero; ratios stay undefined.
   filled={m:(0 if values.get(m) is None and kinds['types'].get(m)=='simple' else values.get(m)) for m in metrics}
   if not all(filled[f.metric] is not None and OPS[f.op](number(filled[f.metric]),number(f.value)) for f in r.metric_filters):continue
   if raw is None:stats['current_missing_counted_as_zero']+=1
   rows.append([mid]+[filled[m] for m in metrics]);detail[mid]={'metric':c.metric,'baseline_value':row[value],'current_value':filled[c.metric],'change_ratio':float(round(change,6))}
  evidence=['sql','aggregate_sql','aggregate_parameters','data_sha256','catalog_sha256','units']
  return {'status':'ok','columns':['member']+metrics,'rows':rows,**{k:current[k] for k in evidence},'comparison':detail,'comparison_stats':stats,'baseline_evidence':{k:base[k] for k in evidence}}
 def attribute_state(self,r,mid,a,registered):
  """None: an attribute is known and fails. Otherwise the list of requested attributes that are unknown."""
  pending=[]
  if r.tiers is not None:
   if a.get('tier') is None:pending.append('tier')
   elif a['tier'] not in r.tiers:return None
  if r.registered_from is not None or r.registered_before is not None:
   day=registered.get(mid)
   if day is None:pending.append('registered_at')
   elif (r.registered_from is not None and day<r.registered_from) or (r.registered_before is not None and day>=r.registered_before):return None
  return pending
 def last_dates(self,ref):
  key='recent:'+ref
  if key not in self.cache:
   import duckdb
   con=duckdb.connect(str(self.project/'data.duckdb'),read_only=True)
   try:self.cache[key]=dict(con.execute("select member_id,max(ordered_at) from raw_orders where ordered_at<? and status='paid' and paid_cents>refund_cents group by member_id",[ref]).fetchall())
   finally:con.close()
  return self.cache[key]
 def covered(self,ref,days):return date.fromisoformat(self.dataset['coverage'][0])<=ref-timedelta(days=days) and date.fromisoformat(self.dataset['coverage'][1])>=ref
 def channel_state(self,p,channel):
  if channel=='all':return 'blocked' if 'blocked' in p['channels'].values() else 'unknown' if 'unknown' in p['channels'].values() else 'no_known_restriction'
  return p['channels'][channel] if channel else 'unspecified'
 def cohort(self,args):
  r=CohortRequest.model_validate(args)
  # A declared but inexpressible condition must not be dropped: no list is produced for a narrower question.
  if r.unsupported_conditions:return {'status':'unsupported','code':'CONDITION_NOT_SUPPORTED','unsupported_conditions':r.unsupported_conditions,'supported_conditions':'可按会员计算的指标条件（1～3 条，同时满足，同一指标可给上下限）、指标窗口、最近有效购买间隔、会员等级、注册日期、一家或多家注册门店或全公司、同一指标的两期对比（下降或上升）、联系渠道','member_ids':[]}
  if str(r.reference_date)!=self.dataset['reference_date']:return {'status':'unsupported','code':'REPREPARE_POLICY_FOR_REFERENCE_DATE','member_ids':[]}
  if r.tiers is not None:
   # A value outside the bound data is a wrong question, not an empty cohort.
   known=self.known_tiers();invalid=[t for t in r.tiers if t not in known]
   if invalid:return {'status':'unsupported','code':'TIER_VALUE_NOT_IN_DATA','invalid_tiers':invalid,'known_tiers':known,'member_ids':[]}
  aggregate=self.compared(r) if r.comparison is not None else self.aggregates(r)
  if aggregate['status']!='ok':return {**aggregate,'status':'unsupported'}
  if r.store_id is not None:
   import duckdb
   con=duckdb.connect(str(self.project/'data.duckdb'),read_only=True)
   try:exists=con.execute('select 1 from raw_stores where store_id=?',[r.store_id]).fetchone()
   finally:con.close()
   if not exists:return {'status':'not_found','code':'STORE_NOT_FOUND','member_ids':[]}
  if r.store_ids is not None:
   found=self.existing_stores();missing=[x for x in r.store_ids if x not in found]
   if missing:return {'status':'not_found','code':'STORE_NOT_FOUND','missing_store_ids':missing,'member_ids':[]}
  stores=set(r.store_ids) if r.store_ids is not None else {r.store_id} if r.store_id else set()
  by_attribute=r.tiers is not None or r.registered_from is not None or r.registered_before is not None;registered=self.registered_dates() if r.registered_from is not None or r.registered_before is not None else {};pending_attribute={'tier':[],'registered_at':[]}
  index=aggregate['columns'].index('member');last=self.last_dates(str(r.reference_date));days=[d for d in (r.dormant_days,r.active_within_days) if d is not None];recency=bool(days);coverage=self.covered(r.reference_date,max(days)) if recency else True;hits=[];excluded=[];eligible=[];unknown=[];blocked=[];unresolved=[];financial=[];channels={c:{'eligible':[],'blocked':[],'unknown':[]} for c in ['telephone','sms']}
  for row in aggregate['rows']:
   mid=row[index];a=self.members[mid];p=self.policies[mid]
   if stores and not stores.intersection(a['registered_stores']):continue
   latest=last.get(mid);age=(r.reference_date-latest).days if latest else None
   if r.dormant_days is not None and age is not None and age<r.dormant_days:continue
   if r.active_within_days is not None:
    # No effective purchase inside a covered window cannot be recent; uncovered stays unknown below.
    if age is None:
     if coverage:continue
    elif age>=r.active_within_days:continue
   pending=self.attribute_state(r,mid,a,registered) if by_attribute else []
   if pending is None:continue
   if a['identity_status']!='verified':
    financial.append(mid)
    # Confirmed abnormal accounts are retained in finance but aren't candidates.
    if not p['all_source_accounts_excluded']:unresolved.extend(a['source_ids'])
    continue
   if pending:
    # An unknown requested attribute is neither a hit nor a miss: kept for review unless the member cannot be a candidate anyway.
    for name in pending:pending_attribute[name].append(mid)
    if p['member_excluded'] or p['all_source_accounts_excluded']:continue
    for c in channels:
     if self.channel_state(p,c)!='blocked':channels[c]['unknown'].append(mid)
    if self.channel_state(p,r.channel)!='blocked':unknown.append(mid)
    continue
   hits.append(mid)
   if p['member_excluded'] or p['all_source_accounts_excluded']:excluded.append(mid);continue
   for c in channels:
    state=self.channel_state(p,c)
    kind='blocked' if state=='blocked' else 'unknown' if recency and (not coverage or latest is None) or p['pending_verifications'] or state=='unknown' else 'eligible'
    channels[c][kind].append(mid)
   state=self.channel_state(p,r.channel)
   if state=='blocked':blocked.append(mid)
   elif recency and (not coverage or latest is None) or p['pending_verifications'] or state=='unknown':unknown.append(mid)
   else:eligible.append(mid)
  eligible.sort();selected=eligible[r.page.offset:r.page.offset+r.page.limit];token=hashlib.sha256(json.dumps([self.manifest['data_version'],self.manifest['files'],{k:v for k,v in args.items() if k!='page'}],sort_keys=True).encode()).hexdigest()
  values={row[index]:{k:v for k,v in zip(aggregate['columns'],row) if k!='member'} for row in aggregate['rows']};compared=aggregate.get('comparison',{})
  member_values=[{'member_id':mid,'metric_values':values[mid],'window':{'start':str(r.start),'end_exclusive':str(r.end)},'last_effective_purchase':str(last[mid]) if last.get(mid) else None,'dormant_days':(r.reference_date-last[mid]).days if last.get(mid) else None,**({'comparison':compared[mid]} if r.comparison is not None else {})} for mid in selected]
  # A member without any record in the window is left out. That only matters when every condition would also hold at zero,
  # and zero is a real value only for additive metrics.
  zero=[]
  if r.comparison is None and all(OPS[f.op](0,f.value) for f in r.metric_filters):
   filtered=list(dict.fromkeys(f.metric for f in r.metric_filters));kinds=self.metric_kinds()['types']
   if all(kinds.get(m)=='simple' for m in filtered):zero=filtered
  candidate_scope={'basis':'members_with_a_baseline_record_of_the_compared_metric; missing additive values in the covered current window count as zero','zero_value_members_omitted':False,'message':'本次只在基期有对比指标记录的会员中筛选；本期没有记录的可加总指标按 0 计。'} if r.comparison is not None else {'basis':'members_with_a_record_of_the_filtered_metrics_in_the_window','zero_value_members_omitted':bool(zero),'metrics_whose_conditions_hold_at_zero':zero,'message':'本次只在指标窗口内有相应指标记录的会员中筛选。'+('窗口内没有记录的会员不在结果里，尽管按 0 计算他们满足全部指标条件；这部分人没有被统计。' if zero else '')}
  comparison=None if r.comparison is None else {**json.loads(r.comparison.model_dump_json()),'current_start':str(r.start),'current_end_exclusive':str(r.end),'basis':'change_ratio=(current-baseline)/baseline; decrease keeps -change_ratio>=min_ratio, increase keeps change_ratio>=min_ratio; non-positive baseline has no ratio and is not selected',**aggregate['comparison_stats']}
  return {'status':'partial' if unknown or unresolved or not coverage else 'ok','coverage_complete':coverage,'member_ids':selected,'members':member_values,'unknown_members':sorted(unknown),'blocked_members':sorted(blocked),'unresolved_sources':sorted(set(unresolved)),'excluded_member_ids':sorted(excluded),'condition_hit_member_ids':sorted(hits),'condition_hit_count':len(hits),'operational_excluded_count':len(excluded),'channels':{c:{k:len(v) for k,v in d.items()} for c,d in channels.items()},'channel':r.channel,'recency_condition':{'dormant_days':r.dormant_days,'active_within_days':r.active_within_days,'applied':recency,'basis':'days_from_last_effective_purchase_to_reference_date; dormant_days gte, active_within_days lt'},
   'store_scope':{'store_ids':sorted(stores) if stores else None,'mode':'multiple_stores' if r.store_ids is not None else 'single_store' if stores else 'company','basis':'any_source_account_registration_in_the_listed_stores; one person is listed once'},
   'attribute_conditions':{'tiers':r.tiers,'registered_from':str(r.registered_from) if r.registered_from else None,'registered_before_exclusive':str(r.registered_before) if r.registered_before else None,'applied':by_attribute,'basis':'tier: member attribute, null when sources conflict or none is recorded; registered_at: earliest known CRM join date, null for POS-only members'},
   'attribute_pending_members':{k:sorted(v) for k,v in pending_attribute.items()},'comparison_condition':comparison,'candidate_scope':candidate_scope,
   'cohort_kind':'channel_candidates' if r.channel else 'condition_analysis','eligible_count':len(eligible) if r.channel else None,'condition_analysis_count':len(eligible) if not r.channel else None,'financial_bucket_hits':len(financial),'range_notice':{'registration_unknown_company_people':self.unknown_store_count,'store_query_omits_unknown_registration':bool(stores),'message':'注册门店未知的人群保留在全公司数据；不能确定属于或不属于当前门店，未重复列入单店待核名单。'},'actual_contact_authorized':False,'result_scope':{'coverage_complete':'recent_effective_purchase_window_only' if recency else 'not_applicable_without_recency_condition','unresolved_sources':'current_filter_and_registration_scope_identity_only','financial_quarantine_review':'not_assessed','empty_candidates':'does_not_prove_absence_of_other_records'},'page':{'total':len(eligible),'returned':len(selected),'offset':r.page.offset,'limit':r.page.limit,'next_offset':r.page.offset+len(selected) if r.page.offset+len(selected)<len(eligible) else None,'complete':r.page.offset==0 and len(selected)==len(eligible),'snapshot_token':token},'aggregate_evidence':{k:aggregate[k] for k in ['sql','aggregate_sql','aggregate_parameters','data_sha256','catalog_sha256','units']+(['baseline_evidence'] if r.comparison is not None else [])},'rules_version':self.manifest['rules_version']}
 def detail(self,args):
  mid=args['member_id'];a=self.members.get(mid)
  if args.get('reference_date',self.dataset['reference_date'])!=self.dataset['reference_date']:return {'status':'unsupported','member_id':mid,'code':'REPREPARE_POLICY_FOR_REFERENCE_DATE'}
  if not a:return {'status':'not_found','member_id':mid}
  p=self.policies[mid];ref=date.fromisoformat(args.get('reference_date',self.dataset['reference_date']));days=args.get('dormant_days',60);latest=self.last_dates(str(ref)).get(mid);covered=self.covered(ref,days);state=self.channel_state(p,args.get('channel'))
  allowed=a['identity_status']=='verified' and not p['member_excluded'] and not p['all_source_accounts_excluded'] and not p['pending_verifications'] and covered and latest is not None and state=='no_known_restriction'
  uncertain=a['identity_status']!='verified' or not covered or latest is None or p['pending_verifications'] or state=='unknown'
  return {'status':'unknown' if uncertain else 'ok','member_id':mid,'attributes':a,'policy':p,'last_effective_purchase':str(latest) if latest else None,'dormant_days':(ref-latest).days if latest else None,'dormancy_condition':{'threshold_days':days,'operator':'gte','matches':((ref-latest).days>=days) if latest and covered else None,'scope':'recent_effective_purchase_only; full_cohort_requires_member_cohort'},'recommendation_allowed':allowed,'recommendation_decision':decision_basis(a,p,covered,latest,state),'presentation_scope':'current_member_facts_v1','recommendation_context_purpose':'knowledge_applicability_only; tier does not decide recommendation_allowed','follow_up_owners':{'source_identity_and_registration':'老周','contact_channel_scope':'小林'},'follow_up_requirements':follow_up_requirements(a,[self.sources[s] for s in a['source_ids']],p,state),'recommendation_context':{'channel':args.get('channel'),'identity':'verified' if a['identity_status']=='verified' else 'unresolved','tier':a['tier']},'coverage_complete':covered,'reference_date':str(ref),'actual_contact_authorized':False}
 def relations(self,args):
  mid=args['member_id'];a=self.members.get(mid)
  if not a:return {'status':'not_found','member_id':mid}
  page=Page.model_validate(args.get('page',{}));import duckdb
  con=duckdb.connect(str(self.project/'data.duckdb'),read_only=True)
  try:
   cur=con.execute('select * from raw_orders where member_id=? order by ordered_at,order_id',[mid]);names=[x[0] for x in cur.description];rows=[{k:str(v) if hasattr(v,'isoformat') else v for k,v in zip(names,row)} for row in cur.fetchall()]
   accepted_cards={x[0] for x in con.execute('select card_id from raw_cards where member_id=?',[mid]).fetchall()}
  finally:con.close()
  selected=rows[page.offset:page.offset+page.limit]
  for r in selected:r['provenance']=self.source_orders[r['order_id']]
  return {'status':'ok' if a['identity_status']=='verified' else 'unknown','member_id':mid,'accounts':[self.sources[s] for s in a['source_ids']],'registered_stores':a['registered_stores'],'orders':selected,'cards':[card_semantics(c,'CRM:'+c['raw']['card_no'] in accepted_cards) for c in self.cards.get(mid,[])],'card_scope':'原始卡记录含财务隔离项；不表示这些卡进入原 W04 指标。','coverage':self.dataset['coverage'],'page':{'total':len(rows),'returned':len(selected),'offset':page.offset,'limit':page.limit,'next_offset':page.offset+len(selected) if page.offset+len(selected)<len(rows) else None,'complete':page.offset==0 and len(selected)==len(rows)}}
