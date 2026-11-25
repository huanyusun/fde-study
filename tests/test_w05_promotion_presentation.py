"""Regression: source conflicts vs absence and W05 buyer-count grain."""
import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from fde_product.w05.presentation import attribute_text,text,fact_summary
from fde_product.w05.integration import final_contract,validate_final
from jsonschema import validate,ValidationError
class PromotionPresentation(unittest.TestCase):
 def metric(self,count=7):
  return [{'name':'query_metrics','result':{'status':'partial','evidence_id':'current','entity_semantics':'verified_person_with_unresolved_source_buckets','precise_person_total_acceptance':'pending','intent':{'metrics':['buyer_count'],'start':'2025-09-01','end':'2026-09-01','group_by':[],'filters':[]},'columns':['buyer_count'],'rows':[[count]]}}]
 def test_conflict_is_not_absence_and_does_not_choose_a_value(self):
  a={'conflicts':{'tier':['普通','银卡']}};before=copy.deepcopy(a);s=attribute_text(a,'tier',None);self.assertIn('来源值冲突',s);self.assertIn('普通',s);self.assertIn('银卡',s);self.assertIn('当前未选定统一值',s);self.assertNotIn('未知／未提供',s);self.assertEqual(a,before)
 def test_name_conflict_and_legacy_list_shape(self):
  for conflicts in [{'name':['甲','乙']},[{'field':'name','values':['甲','乙']}]]:
   s=attribute_text({'conflicts':conflicts},'name',None);self.assertIn('来源值冲突',s);self.assertIn('当前未选定统一值',s)
 def test_normal_missing_and_other_nulls_remain_distinct(self):
  self.assertEqual(attribute_text({'conflicts':{}},'name','单一姓名'),'单一姓名');self.assertEqual(attribute_text({'conflicts':{'tier':['普通','银卡']}},'name',None),'未知／未提供');self.assertEqual(text(None),'未知／未提供');self.assertEqual(text(0),'0');self.assertEqual(text(False),'False')
 def test_representative_with_conflict_does_not_claim_sources_agree(self):
  s=attribute_text({'conflicts':{'tier':['普通','银卡']}},'tier','普通');self.assertIn('不表示来源已一致',s);self.assertNotIn('未选定',s)
 def test_single_repeated_value_not_conflict(self):
  self.assertEqual(attribute_text({'conflicts':{'name':['甲','甲']}},'name',None),'未知／未提供')
 def test_current_tool_count_zero_and_dynamic_counts(self):
  for number in [0,7,123]:
   s=fact_summary(self.metric(number));self.assertTrue(s.startswith(f'本轮购买财务实体数（buyer_count）为 {number}。'));self.assertIn('不是已确认自然人数',s);self.assertIn('pending',s)
 def test_grain_summary_is_const_not_free_prose(self):
  obs=self.metric();r={'status':'incomplete','summary':fact_summary(obs),'evidence_ids':['current'],'recommendations':[]};validate(r,final_contract(obs));self.assertTrue(validate_final(r,obs)[0]);r['summary']='购买会员数为7，后文才提示待核'
  with self.assertRaises(ValidationError):validate(r,final_contract(obs))
  self.assertEqual(validate_final(r,obs),(False,'FACT_SUMMARY_SCOPE_MISMATCH'))
 def test_non_target_metrics_grains_groupings_unchanged(self):
  mutations=[lambda r:r.update(entity_semantics='source_account'),lambda r:r['intent'].update(metrics=['net_sales_cents']),lambda r:r['intent'].update(group_by=['store']),lambda r:r.update(status='error'),lambda r:r.update(rows=[])]
  for change in mutations:
   obs=self.metric();change(obs[0]['result']);self.assertIsNone(fact_summary(obs))
if __name__=='__main__':unittest.main()
