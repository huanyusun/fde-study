import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from fde_product.w05.presentation import fact_summary,follow_up_text
from fde_product.w05.integration import final_contract,validate_final
from jsonschema import validate,ValidationError
class Presentation(unittest.TestCase):
 def cohort(self):
  return [{'name':'member_cohort','args':{'store_id':'test','reference_date':'2026-09-01','start':'2025-09-01','end':'2026-09-01','dormant_days':60,'metric_filters':[{'metric':'net_sales_cents','op':'gte','value':300000}],'channel':'sms'},'result':{'status':'ok','evidence_id':'e','result_scope':{'financial_quarantine_review':'not_assessed'},'member_ids':[],'members':[],'unknown_members':[],'blocked_members':[],'unresolved_sources':[],'condition_hit_count':0,'operational_excluded_count':0,'coverage_complete':True,'page':{'total':0,'returned':0,'offset':0,'limit':100,'complete':True,'next_offset':None},'range_notice':{'registration_unknown_company_people':8,'store_query_omits_unknown_registration':True}}}]
 def result(self,obs):
  return {'status':'completed','summary':fact_summary(obs),'evidence_ids':['e'],'recommendations':[],'member_ids':[],'unknown_member_ids':[],'blocked_member_ids':[],'unresolved_source_ids':[]}
 def test_empty_complete_scope_and_old_false_claim_rejected(self):
  obs=self.cohort();r=self.result(obs);validate(r,final_contract(obs));self.assertTrue(validate_final(r,obs)[0]);r['summary']='覆盖完整，无待核或隔离来源行'
  with self.assertRaises(ValidationError):validate(r,final_contract(obs))
  self.assertEqual(validate_final(r,obs),(False,'FACT_SUMMARY_SCOPE_MISMATCH'))
 def test_pending_blocked_can_coexist_with_no_candidates(self):
  obs=self.cohort();obs[0]['result'].update(unknown_members=['u'],blocked_members=['b'],status='partial');s=fact_summary(obs);self.assertIn('候选总集为空',s);self.assertIn('待核会员 1 名、阻断会员 1 名',s)
 def test_empty_page_is_not_empty_total(self):
  obs=self.cohort();obs[0]['result']['page'].update(total=3,offset=4,complete=False);self.assertIn('不能把空页称为空名单',fact_summary(obs))
 def test_unknown_registration_is_range_not_per_store_queue(self):
  s=fact_summary(self.cohort());self.assertIn('8 名',s);self.assertIn('不能确定属于或不属于本店',s);self.assertIn('未重复列入单店待核名单',s)
 def test_quarantined_record_preserved_without_absence_inference(self):
  obs=self.cohort();card={'raw':{'card_no':'test'},'semantics':{'financial_status':'quarantined_w04_card'}};obs.append({'name':'member_relations','result':{'member_id':'u','accounts':[],'cards':[card]}});before=copy.deepcopy(obs);s=fact_summary(obs);self.assertEqual(obs,before);self.assertIn('不判断隔离记录是否存在或其数量',s)
 def test_channel_owner_only_when_current_channel_requirement_exists(self):
  reg={'topic':'source_registration','owner':'老周','source_ids':['POS:test'],'question':'补证注册门店'};channel={'topic':'contact_channel_scope','owner':'小林','source_ids':['CRM:test'],'question':'确认原限制渠道'}
  self.assertNotIn('小林',follow_up_text({'follow_up_requirements':[reg]}));self.assertIn('小林',follow_up_text({'follow_up_requirements':[reg,channel]}));self.assertNotIn('小林',follow_up_text({'follow_up_requirements':[]}))
 def test_metric_only_summary_contract_is_unchanged(self):
  self.assertIsNone(fact_summary([{'name':'query_metrics','result':{'status':'ok','evidence_id':'e'}}]))
if __name__=='__main__':unittest.main()
