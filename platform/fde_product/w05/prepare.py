"""Course ETL orchestration; customer identity/attribute/policy hooks remain separate."""
import sys,importlib.util,hashlib,json,shutil,csv,unicodedata
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from .records import read_csv,read_json,write_csv,dump,sha,public_materials,discard_new_output
from .identity import resolve
GRAIN='w05-verified-person-and-unresolved-source-1'
def norm(x):return unicodedata.normalize('NFKC',x).strip().upper()
def date_value(s):
 for fmt in ['%Y-%m-%d','%Y/%m/%d','%Y%m%d','%Y-%m-%d %H:%M:%S']:
  try:return datetime.strptime(s,fmt).date().isoformat()
  except ValueError:pass
 raise ValueError('INVALID_DATE')
def cents(s):
 n=Decimal(s)*100
 if not n.is_finite() or n!=n.to_integral_value():raise ValueError('INVALID_MONEY')
 return int(n)
def customer(path):
 spec=importlib.util.spec_from_file_location('w05_customer_'+sha(path),path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def prepare(raw,w04_cleaned,library,code,output):
 out=Path(output).resolve()
 if out.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
 try:return _prepare(raw,w04_cleaned,library,code,out)
 except BaseException as exc:
  discard_new_output(out,exc);raise

def _prepare(raw,w04_cleaned,library,code,output):
 from ..metrics.engine import TABLES,build_project
 raw,clean,library,code,out=map(lambda p:Path(p).resolve(),(raw,w04_cleaned,library,code,output))
 material=public_materials(raw);m4=read_json(clean/'manifest.json')
 if m4['id']!=material['manifest']['base']['id']:raise ValueError('C3_BASE_REQUIRED')
 if any(m4['source_sha256'].get(n)!=h for n,h in material['manifest']['base']['sha256'].items()):raise ValueError('W04_SOURCE_VERSION_MISMATCH')
 for n,h in m4['sha256'].items():
  if sha(clean/n)!=h:raise ValueError('W04_CLEANED_HASH_MISMATCH')
 from .projection import generate,build_prepared
 schema=code.parent/'member.linkml.yaml'
 if not schema.is_file():raise ValueError('MODEL_SOURCE_MISSING:customer/w05/member.linkml.yaml')
 import tempfile
 with tempfile.TemporaryDirectory(prefix='w05-schema-') as tmp:generate(schema,Path(tmp))
 out.mkdir();impl=customer(code);sources=[]
 for system,filename,idfield,store in [('CRM','crm_member_export.csv','hy_id','reg_shop'),('POS','pos_member_export.csv','pos_member_id',None)]:
  for n,r in enumerate(read_csv(raw/filename),1):sources.append({'source_id':system+':'+r[idfield],'system':system,'source_file':filename,'source_row':n,'registered_store':norm(r[store]) if store else None,'raw':r})
 identity=impl.identity_evidence(sources,material);mapping=resolve([s['source_id'] for s in sources],identity['evidence'],mapping_version=identity['rule_version'],verified_singletons=identity['verified_singletons'])
 bysource={s['source_id']:s for s in sources};mapped={r['source_id']:r for r in mapping};groups=defaultdict(list);buckets={}
 for s in sources:
  mid=mapped[s['source_id']]['member_id']
  if not mid:mid='X'+hashlib.sha256(s['source_id'].encode()).hexdigest()[:24];buckets[s['source_id']]=mid
  groups[mid].append(s)
 attributes=[];members=[];policies=[]
 for mid,records in sorted(groups.items()):
  attrs=impl.member_attributes(mid,records);policy=impl.contact_constraints(mid,records,material,None)
  attributes.append({'member_id':mid,**attrs,'identity_status':'unresolved' if mid.startswith('X') else 'verified'})
  policies.append({'member_id':mid,**policy})
  dates=[date_value(s['raw']['join_dt']) for s in records if s['system']=='CRM'];stores=attrs['registered_stores']
  members.append({'member_id':mid,'registered_at':min(dates) if dates else None,'home_store_id':stores[0] if len(stores)==1 else None,'tier':attrs['tier']})
 metric_ids={sid:r['member_id'] or buckets[sid] for sid,r in mapped.items()};orders=[];order_source=[];cards=[];card_source=[];quarantine=[]
 # Retain the original W04 financial/transport decisions. Operational exclusion
 # never removes source orders, including unresolved account buckets.
 crm_positions={}
 for n,r in enumerate(read_csv(raw/'crm_order_export.csv'),1):crm_positions.setdefault(r['ord_no'],n)
 for r in read_csv(clean/'orders.csv'):
  sid='CRM:'+r['member_id'];mid=metric_ids[sid];oid='CRM:'+r['order_id'];orders.append({**r,'order_id':oid,'member_id':mid});order_source.append({'order_id':oid,'member_id':mid,'source_id':sid,'source_file':'crm_order_export.csv','source_row':crm_positions[r['order_id']]})
 accepted_pos=0
 for n,r in enumerate(read_csv(raw/'pos_order_export.csv'),1):
  sid='POS:'+r['hy_id']
  try:
   paid,refund=cents(r['amt_pay']),cents(r['amt_rfd'])
   if refund>paid:raise ValueError('REFUND_EXCEEDS_PAID')
   if sid not in metric_ids:raise ValueError('SOURCE_NOT_FOUND')
   mid=metric_ids[sid];oid='POS:'+r['ord_no'];status={'已取消':'cancelled','已支付':'paid','已完成':'paid','部分退款':'paid','全额退款':'paid'}[r['ord_stat']]
   orders.append({'order_id':oid,'member_id':mid,'store_id':norm(r['shop_cd']),'ordered_at':date_value(r['ord_tm']),'status':status,'gross_cents':cents(r['amt_total']),'paid_cents':paid,'refund_cents':refund,'quantity':int(r['qty']),'channel':r['ch']});order_source.append({'order_id':oid,'member_id':mid,'source_id':sid,'source_file':'pos_order_export.csv','source_row':n});accepted_pos+=1
  except (ValueError,KeyError):quarantine.append({'source_file':'pos_order_export.csv','source_row':n,'raw':r,'reason':'INVALID_POS_ORDER'})
 positions={r['card_no']:n for n,r in enumerate(read_csv(raw/'crm_card_export.csv'),1)}
 for r in read_csv(clean/'cards.csv'):
  sid='CRM:'+r['member_id'];cards.append({**r,'card_id':'CRM:'+r['card_id'],'member_id':metric_ids[sid]})
 for n,r in enumerate(read_csv(raw/'crm_card_export.csv'),1):card_source.append({'member_id':metric_ids['CRM:'+r['hy_id']],'source_id':'CRM:'+r['hy_id'],'source_file':'crm_card_export.csv','source_row':n,'raw':r})
 cleaned=out/'cleaned';cleaned.mkdir()
 tables={'members':members,'orders':orders,'stores':read_csv(clean/'stores.csv'),'cards':cards}
 for name,rows in tables.items():write_csv(cleaned/(name+'.csv'),rows,list(TABLES[name]))
 (out/'state').mkdir();state=out/'state'
 dump(state/'mapping.json',mapping);dump(state/'identity_findings.json',identity['findings']);dump(state/'unresolved_buckets.json',buckets)
 for name,rows in [('members',attributes),('policies',policies),('sources',sources),('card_sources',card_source)]:
  with (state/(name+'.jsonl')).open('w',newline='\n') as f:
   for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
 write_csv(state/'order_sources.csv',order_source,['order_id','member_id','source_id','source_file','source_row'])
 dump(state/'pos_quarantine.json',quarantine);shutil.copy2(clean/'quarantine.csv',state/'w04_quarantine.csv')
 from .knowledge import build
 build(raw/'knowledge/catalog.json',out/'knowledge-index')
 copied=out/'library';shutil.copytree(library,copied)
 scope=read_json(copied/'scope.json');scope.update(grain_version=GRAIN,statistics_unit='已验证统一会员；未决来源单独保留财务桶，不能计作已验证自然人',scope='青禾 v2 CRM+POS 导出内消费。运营排除不扣减财务，精确自然人数仍需业务补证。POS 独有注册日期和门店未知。');dump(copied/'scope.json',scope)
 targets=read_json(copied/'dimension_targets.json')
 for t in targets:
  if t['id']=='member':t.update(name='统一身份与未决来源桶',meaning='已核实来源组成的自然人；未决账户仅用于金额守恒，独立财务桶不计作已验证自然人')
  if t['id']=='home_store':t.update(name='唯一已知来源注册门店属性',meaning='只有已知关系唯一时保留；多门店和未知为 NULL，全部关系通过会员服务取得')
  if t['id']=='home_store__region':t.update(name='唯一已知注册门店地区属性',meaning='唯一已知注册关系的地区；多门店和未知为 NULL，不能代表全部所属关系')
  if t['id']=='home_store__store_name':t.update(name='唯一已知注册门店名称属性',meaning='唯一已知注册关系的名称；全部关系通过来源账户取得')
  if t['id']=='member__tier':t.update(name='来源一致的会员等级属性',meaning='来源等级一致时保留；冲突为 NULL，原来源等级另查')
 catalog=read_json(copied/'catalog.json')
 identity_metrics={'buyer_count','refund_buyer_count','new_member_count','first_buyer_count','monthly_buyer_count','monthly_repeat_buyer_count','monthly_repeat_rate','monthly_paid_buyer_count','monthly_paid_repeat_buyer_count','monthly_paid_repeat_rate','avg_buyer_value','purchase_frequency'}
 for item in catalog:
  # Keep verbatim historical sources for audit. Effective constraints describe
  # the actual current member entity, without altering original metric SQL.
  if item['id'] in identity_metrics:
   item['source_revision']='W05 QH5-12/需求 v0.2 统一实体粒度替代历史 CRM 账户粒度；原 sources 保留审计，不作为现行粒度。'
   item['definition']='当前 member_id 为已核实统一组件或未决来源独立财务桶；distinct/count 和相关分母遵循原指标条件，不等于精确自然人数。未决财务记录保留，未决身份仍需业务补证。'+('入会日期取来源 CRM 已知入会日期最早值，POS 独有为未知，不用建档日期；不能验收为完整新入会自然人数。' if item['id']=='new_member_count' else '')
   item['constraints']=[x.replace('不同 CRM 会员账户数','不同当前财务实体数').replace('不做跨系统自然人去重','已验证来源已按业务依据关联，未决来源不算作已验证自然人').replace('不同账户数','不同当前财务实体数').replace('同一账户','同一当前财务实体').replace('账户数不等于自然人数','财务实体数不等于精确自然人数') for x in item.get('constraints',[])]
   # A library from an earlier prepare already carries this sentence; add it once.
   if item['definition'] not in item['constraints']:item['constraints'].append(item['definition'])
 dump(copied/'catalog.json',catalog)
 dump(copied/'dimension_targets.json',targets);dump(copied/'entity_semantics.json',{'version':'w05-entity-semantics-2','grain_version':GRAIN,'member':'verified_person_with_unresolved_source_buckets','home_store':'representative_attribute','sources':['03_身份关联与数据使用说明.md','coverage.json'],'unresolved_bucket_policy':'retain_financial_records_not_verified_people'})
 metadata={'id':material['manifest']['id'],'contract_version':'w05-data-1','grain_version':GRAIN,'identity_rule_version':identity['rule_version'],'coverage':material['manifest']['coverage'],'reference_date':material['reference_date'],'timezone':'Asia/Shanghai','counts':{k:len(rows) for k,rows in tables.items()},'sha256':{p.name:sha(p) for p in cleaned.glob('*.csv')},'source_sha256':material['manifest']['sha256'],'coverage_notes':{'source':'本轮 CRM 与旧 POS 完整导出；原 W04 财务隔离继承。未决来源保留独立财务桶，不能解释为自然人。运营员工/异常排除不扣经营指标。','time_range':{'start':material['manifest']['coverage'][0],'end_exclusive':material['manifest']['coverage'][1]},'quarantined':{'member':0,'order':m4['record_counts']['order']['quarantined']+len(quarantine),'card':m4['record_counts']['card']['quarantined'],'shop':0},'identity_unresolved_sources':len(buckets),'precise_person_total_acceptance':'pending'}};dump(cleaned/'manifest.json',metadata)
 build_project(copied,cleaned,out/'project')
 summary={'version':'w05-reconciliation-1','data_version':metadata['id'],'source_accounts':len(sources),'verified_people':len(groups)-len(buckets),'unresolved_source_accounts':len(buckets),'metric_financial_buckets':len(groups),'identity_findings':identity['findings'],'orders':{'source_CRM_read':m4['record_counts']['order']['read'],'CRM_accepted':len(read_csv(clean/'orders.csv')),'CRM_quarantined':m4['record_counts']['order']['quarantined'],'CRM_deduplicated':m4['record_counts']['order']['deduplicated'],'POS_read':material['manifest']['counts']['pos_order_export.csv'],'POS_accepted':accepted_pos,'POS_quarantined':len(quarantine),'combined_accepted':len(orders),'paid_cents':sum(int(r['paid_cents']) for r in orders),'net_paid_cents':sum(int(r['paid_cents'])-int(r['refund_cents']) for r in orders if r['status']=='paid')},'precision_acceptance':'pending; no teacher target used'};dump(out/'reconciliation.json',summary)
 state_manifest={'version':'w05-member-state-1','data_version':metadata['id'],'rules_version':identity['rule_version'],'grain_version':GRAIN,'raw_path':str(raw),'knowledge_index':'knowledge-index','files':{p.name:sha(p) for p in state.iterdir() if p.is_file()},'reconciliation':summary};dump(state/'manifest.json',state_manifest)
 build_prepared(schema,out)
 return {'objects':str(out/'objects'),'output':str(out),'project':str(out/'project'),'state':str(state),'data_version':metadata['id'],'reconciliation':summary}
