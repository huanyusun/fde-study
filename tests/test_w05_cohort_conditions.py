import sys,unittest
from datetime import date
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from pydantic import ValidationError
from fde_product.w05.contracts import CohortRequest
from fde_product.w05.service import Service
from fde_product.w05.presentation import cohort_text
BASE={'reference_date':'2026-09-01','start':'2025-09-01','end':'2026-09-01','metric_filters':[{'metric':'net_sales_cents','op':'gte','value':300000}],'channel':'sms'}
# Days from the last effective purchase to 2026-09-01: A 68, B 5, C 60, D 59, E none.
LAST={'A':'2026-06-25','B':'2026-08-27','C':'2026-07-03','D':'2026-07-04'}
class Contract(unittest.TestCase):
 def test_recency_is_optional(self):
  r=CohortRequest.model_validate(BASE);self.assertIsNone(r.dormant_days);self.assertIsNone(r.active_within_days)
 def test_original_request_still_valid(self):self.assertEqual(CohortRequest.model_validate({**BASE,'dormant_days':60}).dormant_days,60)
 def test_bounds_and_empty_range_rejected(self):
  for extra in [{'dormant_days':0},{'active_within_days':0},{'dormant_days':90,'active_within_days':90},{'dormant_days':90,'active_within_days':60}]:
   with self.subTest(extra=extra):
    with self.assertRaises(ValidationError):CohortRequest.model_validate({**BASE,**extra})
 def test_recency_band_accepted(self):self.assertEqual(CohortRequest.model_validate({**BASE,'dormant_days':60,'active_within_days':180}).active_within_days,180)
 def test_same_metric_bounds_select_metric_once(self):
  r=CohortRequest.model_validate({**BASE,'metric_filters':[{'metric':'net_sales_cents','op':'gte','value':100000},{'metric':'net_sales_cents','op':'lt','value':300000},{'metric':'valid_order_count','op':'gte','value':2}]})
  self.assertEqual(Service.aggregate_intent(object.__new__(Service),r)['metrics'],['net_sales_cents','valid_order_count'])
class Unsupported(unittest.TestCase):
 def test_declared_condition_returns_no_list(self):
  s=object.__new__(Service);s.dataset={'reference_date':'2026-09-01'}
  def fail(r):raise AssertionError('aggregate must not run')
  s.aggregates=fail;r=s.cohort({**BASE,'dormant_days':60,'unsupported_conditions':['只要金卡会员']})
  self.assertEqual((r['status'],r['code'],r['member_ids'],r['unsupported_conditions']),('unsupported','CONDITION_NOT_SUPPORTED',[],['只要金卡会员']))
 def test_final_answer_cannot_be_completed(self):
  from fde_product.w05.integration import validate_final
  obs=[{'name':'member_cohort','args':{},'result':{'status':'unsupported','code':'CONDITION_NOT_SUPPORTED','member_ids':[],'evidence_id':'e1'}}]
  answer={'summary':'x','evidence_ids':['e1'],'recommendations':[],'member_ids':[],'unknown_member_ids':[],'blocked_member_ids':[],'unresolved_source_ids':[]}
  self.assertEqual(validate_final({**answer,'status':'completed'},obs),(False,'PARTIAL_RESULT_CANNOT_COMPLETE'))
  for status in ['incomplete','clarification','refused']:
   with self.subTest(status=status):self.assertTrue(validate_final({**answer,'status':status},obs)[0])
 def test_empty_and_oversized_entries_rejected(self):
  for value in [[''],['x'*201],['a']*11]:
   with self.subTest(value=value):
    with self.assertRaises(ValidationError):CohortRequest.model_validate({**BASE,'unsupported_conditions':value})
class Recency(unittest.TestCase):
 def service(self,covered=True):
  s=object.__new__(Service);s.dataset={'reference_date':'2026-09-01'};s.manifest={'data_version':'test','files':{},'rules_version':'test'};s.unknown_store_count=0
  policy={'member_excluded':False,'all_source_accounts_excluded':False,'pending_verifications':[],'channels':{'sms':'no_known_restriction','telephone':'no_known_restriction'}}
  s.members={m:{'identity_status':'verified','registered_stores':['S'],'source_ids':[]} for m in 'ABCDE'};s.policies={m:dict(policy) for m in 'ABCDE'}
  s.last_dates=lambda ref:{m:date.fromisoformat(d) for m,d in LAST.items()};s.covered=lambda ref,days:covered
  s.aggregates=lambda r:{'status':'ok','columns':['member','net_sales_cents'],'rows':[[m,400000] for m in 'ABCDE'],'sql':'','aggregate_sql':'','aggregate_parameters':[],'data_sha256':'','catalog_sha256':'','units':{'net_sales_cents':'cents'}}
  return s
 def run_cohort(self,covered=True,**extra):return self.service(covered).cohort({**BASE,**extra})
 def test_dormant_boundary_unchanged(self):
  r=self.run_cohort(dormant_days=60);self.assertEqual(r['member_ids'],['A','C']);self.assertEqual(r['unknown_members'],['E']);self.assertEqual(r['status'],'partial')
 def test_without_recency_keeps_every_metric_match(self):
  r=self.run_cohort();self.assertEqual(r['member_ids'],list('ABCDE'));self.assertEqual(r['unknown_members'],[]);self.assertEqual(r['status'],'ok')
  self.assertFalse(r['recency_condition']['applied']);self.assertIsNone(r['members'][4]['last_effective_purchase']);self.assertIsNone(r['members'][4]['dormant_days'])
 def test_active_is_exact_complement_of_dormant(self):
  r=self.run_cohort(active_within_days=60);self.assertEqual(r['member_ids'],['B','D']);self.assertEqual(r['unknown_members'],[])
 def test_active_without_coverage_keeps_missing_purchase_unknown(self):
  r=self.run_cohort(covered=False,active_within_days=60);self.assertEqual(r['member_ids'],[]);self.assertEqual(r['unknown_members'],['B','D','E']);self.assertEqual(r['status'],'partial')
 def test_recency_band(self):self.assertEqual(self.run_cohort(dormant_days=59,active_within_days=68)['member_ids'],['C','D'])
 def test_summary_states_applied_conditions(self):
  for extra,phrase in [({'dormant_days':60},'最近有效购买距参考日满 60 天；'),({'active_within_days':30},'最近有效购买距参考日不足 30 天；'),({'dormant_days':60,'active_within_days':180},'满 60 天且不足 180 天；'),({},'未设置最近有效购买间隔条件；')]:
   with self.subTest(extra=extra):
    args={**BASE,**extra};self.assertIn(phrase,cohort_text({'name':'member_cohort','args':args,'result':self.service().cohort(args)}))
  self.assertIn('不涉及该判断窗口的覆盖',cohort_text({'name':'member_cohort','args':BASE,'result':self.service().cohort(BASE)}))
if __name__=='__main__':unittest.main()
