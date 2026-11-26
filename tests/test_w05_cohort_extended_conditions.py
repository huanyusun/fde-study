import sys,unittest
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from pydantic import ValidationError
from fde_product.w05.contracts import CohortRequest
from fde_product.w05.service import Service
from fde_product.w05.presentation import cohort_text
BASE={'reference_date':'2026-09-01','start':'2026-03-01','end':'2026-09-01','metric_filters':[{'metric':'net_sales_cents','op':'gte','value':100000}],'channel':'sms'}
COMPARE={'metric':'net_sales_cents','baseline_start':'2025-09-01','baseline_end':'2026-03-01','direction':'decrease','min_ratio':0.5}
OPEN={'member_excluded':False,'all_source_accounts_excluded':False,'pending_verifications':[],'channels':{'sms':'no_known_restriction','telephone':'no_known_restriction'}}
def without(source,*keys):return {k:v for k,v in source.items() if k not in keys}
class Contract(unittest.TestCase):
 def rejected(self,extra,base=BASE):
  with self.assertRaises(ValidationError):CohortRequest.model_validate({**base,**extra})
 def test_new_fields_are_optional(self):
  r=CohortRequest.model_validate(BASE)
  self.assertEqual((r.store_ids,r.tiers,r.registered_from,r.registered_before,r.comparison),(None,None,None,None,None))
 def test_store_id_and_store_ids_are_exclusive(self):
  self.rejected({'store_id':'S1','store_ids':['S2']});self.assertEqual(CohortRequest.model_validate({**BASE,'store_ids':['S1','S2']}).store_ids,['S1','S2'])
 def test_list_bounds_and_duplicates_rejected(self):
  for extra in [{'store_ids':[]},{'store_ids':['S1','S1']},{'store_ids':[str(n) for n in range(51)]},{'store_ids':['']},{'tiers':[]},{'tiers':['金卡','金卡']},{'tiers':'金卡'}]:
   with self.subTest(extra=extra):self.rejected(extra)
 def test_registration_range(self):
  self.rejected({'registered_from':'2024-01-01','registered_before':'2024-01-01'})
  for extra in [{'registered_from':'2024-01-01'},{'registered_before':'2024-01-01'},{'registered_from':'2024-01-01','registered_before':'2024-01-02'}]:
   with self.subTest(extra=extra):CohortRequest.model_validate({**BASE,**extra})
 def test_metric_filters_required_without_comparison(self):
  self.rejected({},without(BASE,'metric_filters'));self.rejected({'metric_filters':[]})
  self.assertEqual(CohortRequest.model_validate({**without(BASE,'metric_filters'),'comparison':COMPARE}).metric_filters,[])
 def test_baseline_must_precede_current_window(self):
  self.rejected({'comparison':{**COMPARE,'baseline_end':'2026-03-02'}});self.rejected({'comparison':{**COMPARE,'baseline_start':'2026-03-01'}})
  self.assertEqual(str(CohortRequest.model_validate({**BASE,'comparison':COMPARE}).comparison.baseline_end),'2026-03-01')
 def test_ratio_bounds(self):
  for value in [0,-0.1,1.01,True,'0.5']:
   with self.subTest(value=value):self.rejected({'comparison':{**COMPARE,'min_ratio':value}})
  CohortRequest.model_validate({**BASE,'comparison':{**COMPARE,'min_ratio':1}});CohortRequest.model_validate({**BASE,'comparison':{**COMPARE,'direction':'increase','min_ratio':2}})
  self.rejected({'comparison':{**COMPARE,'min_baseline_value':0}});self.rejected({'comparison':{**COMPARE,'direction':'flat'}})
class Fixture(unittest.TestCase):
 # Members: A gold S1, B silver S1+S2, C tier unknown S2, D gold S3, E gold S1 excluded with unknown tier, F unknown tier blocked on sms, X unresolved bucket.
 def service(self,rows=None):
  s=object.__new__(Service);s.dataset={'reference_date':'2026-09-01'};s.manifest={'data_version':'test','files':{},'rules_version':'test'};s.unknown_store_count=0;s.cache={}
  member=lambda tier,stores,status='verified':{'identity_status':status,'registered_stores':stores,'source_ids':['SRC'],'tier':tier}
  s.members={'A':member('金卡',['S1']),'B':member('银卡',['S1','S2']),'C':member(None,['S2']),'D':member('金卡',['S3']),'E':member(None,['S1']),'F':member(None,['S1']),'X':member('金卡',['S1'],'unresolved')}
  s.policies={m:{**OPEN,'channels':dict(OPEN['channels'])} for m in s.members};s.policies['E']['member_excluded']=True;s.policies['F']['channels']['sms']='blocked'
  s.last_dates=lambda ref:{};s.covered=lambda ref,days:True;s.existing_stores=lambda:{'S1','S2','S3'}
  s.metric_kinds=lambda:{'types':{'net_sales_cents':'simple','refund_order_count':'simple','refund_amount_rate':'ratio'},'monthly':set(),'by_member':{'net_sales_cents','refund_order_count','refund_amount_rate'}}
  s.registered_dates=lambda:{'A':date(2024,1,1),'B':date(2024,6,30),'D':date(2025,1,1),'E':date(2024,1,1),'F':date(2024,1,1),'X':date(2024,1,1)}
  s.aggregates=lambda r:{'status':'ok','columns':['member','net_sales_cents'],'rows':rows or [[m,400000] for m in s.members],'sql':'','aggregate_sql':'','aggregate_parameters':[],'data_sha256':'','catalog_sha256':'','units':{'net_sales_cents':'cents'}}
  return s
 def run_cohort(self,**extra):return self.service().cohort({**BASE,**extra})
class Stores(Fixture):
 def test_any_listed_store_and_one_person_once(self):
  r=self.run_cohort(store_ids=['S1','S2']);self.assertEqual(r['member_ids'],['A','B','C']);self.assertEqual(r['condition_hit_member_ids'],['A','B','C','E','F'])
  self.assertEqual(r['store_scope']['store_ids'],['S1','S2']);self.assertEqual(r['store_scope']['mode'],'multiple_stores');self.assertTrue(r['range_notice']['store_query_omits_unknown_registration'])
 def test_one_listed_store_matches_only_its_members(self):self.assertEqual(self.run_cohort(store_ids=['S3'])['member_ids'],['D'])
 def test_missing_store_is_named(self):
  r=self.run_cohort(store_ids=['S1','S9','S8']);self.assertEqual((r['status'],r['code'],r['missing_store_ids'],r['member_ids']),('not_found','STORE_NOT_FOUND',['S9','S8'],[]))
 def test_company_scope_reports_no_store_list(self):
  r=self.run_cohort(store_id=None);self.assertIsNone(r['store_scope']['store_ids']);self.assertEqual(r['store_scope']['mode'],'company')
class Tiers(Fixture):
 def test_unknown_tier_goes_to_review_not_dropped(self):
  r=self.run_cohort(tiers=['金卡'],store_id=None)
  self.assertEqual(r['member_ids'],['A','D']);self.assertEqual(r['condition_hit_member_ids'],['A','D'])
  self.assertEqual(r['attribute_pending_members'],{'tier':['C','E','F'],'registered_at':[]})
  # E is operationally excluded and F is blocked on the requested channel: listed as pending, not as review candidates.
  self.assertEqual(r['unknown_members'],['C']);self.assertEqual(r['status'],'partial')
  self.assertEqual(r['channels'],{'telephone':{'eligible':2,'blocked':0,'unknown':2},'sms':{'eligible':2,'blocked':0,'unknown':1}})
 def test_several_tiers(self):self.assertEqual(self.run_cohort(tiers=['金卡','银卡'],store_id=None)['member_ids'],['A','B','D'])
 def test_value_outside_data_is_rejected_before_any_aggregate(self):
  s=self.service()
  def fail(r):raise AssertionError('aggregate must not run')
  s.aggregates=fail;r=s.cohort({**BASE,'tiers':['金卡','钻石']})
  self.assertEqual((r['status'],r['code'],r['invalid_tiers'],r['known_tiers'],r['member_ids']),('unsupported','TIER_VALUE_NOT_IN_DATA',['钻石'],['金卡','银卡'],[]))
 def test_unresolved_identity_keeps_its_own_path(self):
  r=self.run_cohort(tiers=['金卡'],store_id=None);self.assertEqual(r['financial_bucket_hits'],1);self.assertEqual(r['unresolved_sources'],['SRC']);self.assertNotIn('X',r['unknown_members'])
 def test_without_attribute_condition_nothing_is_pending(self):
  r=self.run_cohort(store_id=None);self.assertFalse(r['attribute_conditions']['applied']);self.assertEqual(r['attribute_pending_members'],{'tier':[],'registered_at':[]});self.assertEqual(r['member_ids'],['A','B','C','D'])
class Registration(Fixture):
 def test_half_open_range(self):
  self.assertEqual(self.run_cohort(registered_from='2024-01-01',registered_before='2024-06-30',store_id=None)['condition_hit_member_ids'],['A','E','F'])
  self.assertEqual(self.run_cohort(registered_from='2024-01-02',store_id=None)['member_ids'],['B','D'])
  self.assertEqual(self.run_cohort(registered_before='2024-01-01',store_id=None)['condition_hit_member_ids'],[])
 def test_unknown_date_goes_to_review(self):
  r=self.run_cohort(registered_from='2024-06-01',store_id=None);self.assertEqual(r['member_ids'],['B','D']);self.assertEqual(r['attribute_pending_members']['registered_at'],['C']);self.assertEqual(r['unknown_members'],['C'])
 def test_known_failing_attribute_wins_over_unknown_one(self):
  # C: tier unknown and date unknown -> pending on both. A: gold but registered too early -> not selected, not pending.
  r=self.run_cohort(tiers=['金卡'],registered_from='2024-06-01',store_id=None);self.assertEqual(r['member_ids'],['D']);self.assertEqual(r['attribute_pending_members'],{'tier':['C'],'registered_at':['C']})
  # B is silver with a known date: the known tier fails, so B is not pending.
  self.assertNotIn('B',r['unknown_members'])
class Comparison(Fixture):
 # Baseline / current net sales: A 1000/500 (-50%), B 1000/501 (-49.9%), C 1000/none (-100%), D 0/300 (zero baseline), E 2000/3000 (+50%), F 400/100 (-75%).
 def compared(self,comparison,filters=(),current_extra=None):
  s=self.service();s.metric_kinds=lambda:{'types':{'net_sales_cents':'simple','valid_order_count':'simple','avg_order_value':'ratio','monthly_buyer_count':'simple','store_only':'simple'},'monthly':{'monthly_buyer_count'},'by_member':{'net_sales_cents','valid_order_count','avg_order_value','monthly_buyer_count'}}
  s.policies={m:{**OPEN,'channels':dict(OPEN['channels'])} for m in s.members}
  base={'A':1000,'B':1000,'C':1000,'D':0,'E':2000,'F':400};now={'A':500,'B':501,'D':300,'E':3000,'F':100};calls=[]
  def run(intent,filters):
   calls.append(intent)
   if intent['start']=='2025-09-01':rows=[[m,v] for m,v in base.items()]
   else:rows=[[m]+[v if name=='net_sales_cents' else (current_extra or {}).get(name,{}).get(m) for name in intent['metrics']] for m,v in now.items()]
   return {'status':'ok','columns':['member']+intent['metrics'],'rows':rows,'sql':'SQL '+intent['start'],'aggregate_sql':'','aggregate_parameters':[],'data_sha256':'d','catalog_sha256':'c','units':{m:'cents' for m in intent['metrics']}}
  s.run_aggregate=run;s.calls=calls
  return s,s.cohort({**without(BASE,'metric_filters'),'store_id':None,'metric_filters':list(filters),'comparison':{**COMPARE,**comparison}})
 def test_decrease_boundary_missing_current_and_zero_baseline(self):
  s,r=self.compared({});self.assertEqual(r['member_ids'],['A','C','F'])
  stats=r['comparison_condition'];self.assertEqual((stats['baseline_candidates'],stats['non_positive_baseline'],stats['comparison_hits'],stats['current_missing_counted_as_zero']),(6,1,3,1))
  values={m['member_id']:m for m in r['members']}
  self.assertEqual(values['C']['comparison'],{'metric':'net_sales_cents','baseline_value':1000,'current_value':0,'change_ratio':-1.0});self.assertEqual(values['A']['comparison']['change_ratio'],-0.5);self.assertEqual(values['C']['metric_values'],{'net_sales_cents':0})
  self.assertEqual([c['start'] for c in s.calls],['2025-09-01','2026-03-01']);self.assertEqual(r['aggregate_evidence']['baseline_evidence']['sql'],'SQL 2025-09-01')
  self.assertFalse(r['candidate_scope']['zero_value_members_omitted'])
 def test_increase_and_baseline_floor(self):
  self.assertEqual(self.compared({'direction':'increase','min_ratio':0.5})[1]['member_ids'],['E'])
  s,r=self.compared({'min_baseline_value':1000});self.assertEqual(r['member_ids'],['A','C']);self.assertEqual(r['comparison_condition']['below_min_baseline_value'],1)
 def test_metric_filters_apply_to_current_window_with_additive_zero(self):
  # Current net sales below 200: C counts as zero, F is 100.
  self.assertEqual(self.compared({},[{'metric':'net_sales_cents','op':'lt','value':200}])[1]['member_ids'],['C','F'])
  # A ratio metric without a current record stays undefined and cannot satisfy a condition.
  extra={'avg_order_value':{'A':250,'F':50}}
  self.assertEqual(self.compared({},[{'metric':'avg_order_value','op':'lte','value':300}],extra)[1]['member_ids'],['A','F'])
 def test_unsupported_comparison_metrics(self):
  for metric in ['avg_order_value','monthly_buyer_count','store_only','no_such_metric']:
   with self.subTest(metric=metric):
    s,r=self.compared({'metric':metric});self.assertEqual((r['status'],r['code'],r['member_ids']),('unsupported','COMPARISON_METRIC_NOT_SUPPORTED',[]));self.assertEqual(s.calls,[])
 def test_engine_refusal_of_a_window_is_passed_on(self):
  s,_=self.compared({})
  s.run_aggregate=lambda intent,filters:{'status':'unsupported','reason':'超出数据覆盖或时间范围非法'}
  r=s.cohort({**without(BASE,'metric_filters'),'store_id':None,'comparison':COMPARE});self.assertEqual((r['status'],r['comparison_window']),('unsupported','baseline'))
 def test_comparison_combines_with_attributes(self):
  s,_=self.compared({});r=s.cohort({**without(BASE,'metric_filters'),'store_ids':['S1'],'tiers':['金卡'],'comparison':COMPARE})
  self.assertEqual(r['member_ids'],['A']);self.assertEqual(r['attribute_pending_members']['tier'],['F'])
class Scope(Fixture):
 def test_upper_bound_only_condition_declares_omitted_zero_members(self):
  low={'metric':'net_sales_cents','op':'lt','value':100000};high={'metric':'net_sales_cents','op':'gte','value':100000}
  # Flagged only when every condition holds at zero and zero is a real value: additive metrics, not ratios.
  for filters,expected in [([low],True),([high],False),([high,{'metric':'net_sales_cents','op':'lt','value':300000}],False),([{'metric':'net_sales_cents','op':'eq','value':0}],True),([low,{'metric':'refund_order_count','op':'eq','value':0}],True),([high,{'metric':'refund_order_count','op':'eq','value':0}],False),([{'metric':'refund_amount_rate','op':'lt','value':0.1}],False),([low,{'metric':'refund_amount_rate','op':'lt','value':0.1}],False)]:
   with self.subTest(filters=filters):
    rows=[[m,400000]+[0]*(len({f['metric'] for f in filters})-1) for m in 'ABCD'];s=self.service(rows);columns=['member']+list(dict.fromkeys(f['metric'] for f in filters));base=s.aggregates(None);s.aggregates=lambda r:{**base,'columns':columns}
    r=s.cohort({**BASE,'metric_filters':filters,'store_id':None});self.assertEqual(r['candidate_scope']['zero_value_members_omitted'],expected)
    self.assertEqual('窗口内没有记录的会员不在结果里' in cohort_text({'name':'member_cohort','args':{**BASE,'metric_filters':filters,'store_id':None},'result':r}),expected)
class Summary(Fixture):
 def text(self,**extra):
  args={**BASE,**extra};return cohort_text({'name':'member_cohort','args':args,'result':self.service().cohort(args)})
 def test_added_conditions_are_stated(self):
  for extra,phrases in [({'tiers':['金卡','银卡'],'store_id':None},['会员等级限 金卡、银卡；','等级未知 3 名','没有被当作不满足条件']),({'registered_from':'2024-06-01','store_id':None},['注册日期不早于 2024-06-01；','注册日期未知 1 名']),({'registered_from':'2024-01-01','registered_before':'2025-01-01','store_id':None},['注册日期不早于 2024-01-01、早于 2025-01-01；']),({'store_ids':['S1','S2']},['注册门店 S1、S2（多家门店','所查门店'])]:
   with self.subTest(extra=extra):
    summary=self.text(**extra)
    for phrase in phrases:self.assertIn(phrase,summary)
 def test_requests_without_added_conditions_gain_no_sentence(self):
  summary=self.text(store_id=None)
  for phrase in ['会员等级','注册日期','两期对比','多家门店','窗口内没有记录']:self.assertNotIn(phrase,summary)
 def test_comparison_is_stated(self):
  s,r=Comparison.compared(Comparison(),{'min_baseline_value':1000});args={**without(BASE,'metric_filters'),'store_id':None,'metric_filters':[],'comparison':{**COMPARE,'min_baseline_value':1000}}
  summary=cohort_text({'name':'member_cohort','args':args,'result':r})
  for phrase in ['条件 未单独设置指标条件，','两期对比 net_sales_cents：基期 [2025-09-01,2026-03-01) 对本期 [2026-03-01,2026-09-01)，下降不少于 0.5','基期值不少于 1000（cents）','基期值不大于 0 的 1 个不计算比例','本期没有该指标记录的按 0 计','net_sales_cents 基期 1000、本期 0、变化比例 -1.0']:self.assertIn(phrase,summary)
class ToolText(Fixture):
 def test_description_lists_data_tiers_and_remaining_gaps(self):
  description=self.service().schemas()[0]['function']['description']
  self.assertIn('当前数据的等级取值：金卡、银卡',description)
  gaps=description[description.index('不能用这些字段表达时'):description.index('把原话逐条填入')]
  for phrase in ['会员卡','或关系','月度类指标']:self.assertIn(phrase,gaps)
  for phrase in ['会员等级','注册日期','多家门店']:self.assertNotIn(phrase,gaps)
 def test_declared_condition_still_returns_no_list(self):
  r=self.run_cohort(tiers=['金卡'],unsupported_conditions=['只要持有年卡的会员']);self.assertEqual((r['status'],r['code'],r['member_ids']),('unsupported','CONDITION_NOT_SUPPORTED',[]));self.assertIn('会员等级',r['supported_conditions'])
class Declared(Fixture):
 # 20261014.2: once a condition is declared, the request is refused as a whole; no list-request check runs first.
 # The two shapes are the actual tool arguments of real-model questions Q12 and Q14 on 20261014.1.
 Q12={'reference_date':'2026-09-01','start':'2025-09-01','end':'2026-09-01','store_id':'2656','channel':'sms','unsupported_conditions':['净消费至少3000元（net_sales_cents>=300000分）','有效订单至少5笔（valid_order_count>=5）','两个条件满足任意一个就算（条件之间的或关系）']}
 Q14={'reference_date':'2026-09-01','start':'2025-09-01','end':'2026-09-01','tiers':['金卡'],'store_id':'2656','channel':'sms','unsupported_conditions':['不带任何指标条件只按等级列出会员（只按属性列会员）']}
 def refused(self,args):
  s=self.service()
  def fail(*a):raise AssertionError('no aggregate or lookup may run')
  s.aggregates=fail;s.run_aggregate=fail;s.registered_dates=fail;s.existing_stores=fail
  r=s.cohort(args);self.assertEqual((r['status'],r['code'],r['member_ids']),('unsupported','CONDITION_NOT_SUPPORTED',[]));self.assertEqual(r['unsupported_conditions'],args['unsupported_conditions'])
 def test_real_model_shapes(self):
  for args in [self.Q12,self.Q14]:
   with self.subTest(args=args['unsupported_conditions'][0]):self.refused(args)
 def test_cross_field_rules_do_not_preempt_the_declaration(self):
  declared={'unsupported_conditions':['只要持有年卡的会员']}
  for extra in [{'metric_filters':[]},{'start':'2026-09-01'},{'dormant_days':90,'active_within_days':60},{'store_id':'S1','store_ids':['S2']},{'tiers':['金卡','金卡']},{'store_ids':['S1','S1']},
                {'registered_from':'2025-01-01','registered_before':'2024-01-01'},{'tiers':['钻石']},{'comparison':{**COMPARE,'baseline_end':'2026-04-01'}},{'comparison':{**COMPARE,'baseline_start':'2026-03-01'}},
                {'comparison':{**COMPARE,'min_ratio':1.5}},{'comparison':{**COMPARE,'metric':'avg_order_value'}}]:
   with self.subTest(extra=extra):self.refused({**BASE,**extra,**declared})
 def test_same_rules_still_reject_an_undeclared_request(self):
  for extra in [{'metric_filters':[]},{'start':'2026-09-01'},{'dormant_days':90,'active_within_days':60},{'store_id':'S1','store_ids':['S2']},{'tiers':['金卡','金卡']},
                {'registered_from':'2025-01-01','registered_before':'2024-01-01'},{'comparison':{**COMPARE,'baseline_end':'2026-04-01'}},{'comparison':{**COMPARE,'baseline_start':'2026-03-01'}},{'comparison':{**COMPARE,'min_ratio':1.5}}]:
   with self.subTest(extra=extra):
    with self.assertRaises(ValidationError):CohortRequest.model_validate({**BASE,**extra})
 def test_field_types_and_bounds_still_apply(self):
  # Shape rules that the tool schema itself states keep rejecting, declared or not.
  for extra in [{'tiers':[]},{'metric_filters':[{'metric':'net_sales_cents','op':'gte','value':1}]*4},{'comparison':{**COMPARE,'min_ratio':0}},{'comparison':{**COMPARE,'direction':'flat'}}]:
   with self.subTest(extra=extra):
    with self.assertRaises(ValidationError):CohortRequest.model_validate({**BASE,**extra,'unsupported_conditions':['只要持有年卡的会员']})
if __name__=='__main__':unittest.main()
