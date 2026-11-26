import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'platform'))
from jsonschema import validate,ValidationError
from fde_product.w05.semantics import card_semantics,decision_basis,critical_facts,VALIDATION_SCOPE,follow_up_requirements
from fde_product.w05.integration import final_contract,validate_final
class Semantics(unittest.TestCase):
 def card(self,**raw):
  return {'source_id':'CRM:a','source_file':'cards.csv','source_row':7,'raw':{'card_no':'c','pay_amt':'42.50','st_dt':'2024-02-29','ed_dt':'2025-02-28','stop_dt':'',**raw}}
 def test_amount_and_dates_distinct(self):
  c=self.card();r=card_semantics(c,False);self.assertEqual(r['raw'],c['raw']);s=r['semantics'];self.assertEqual(s['purchase_amount']['value'],'42.50');self.assertEqual(s['purchase_amount']['unit'],'CNY');self.assertEqual(s['expiry_date']['value'],'2025-02-28');self.assertEqual(s['effective_date']['source_field'],'st_dt');self.assertEqual(s['financial_status'],'quarantined_w04_card')
 def test_missing_and_invalid_preserved(self):
  for v in ['',None,'NULL','-','无']:
   s=card_semantics(self.card(pay_amt=v,st_dt=v),True)['semantics'];self.assertIsNone(s['purchase_amount']['value']);self.assertEqual(s['effective_date']['status'],'missing')
  s=card_semantics(self.card(pay_amt='NaN',st_dt='2024-02-30',ed_dt='2030/01/02',stop_dt='20250201'),True)['semantics'];self.assertEqual(s['purchase_amount']['status'],'invalid');self.assertIsNone(s['effective_date']['value']);self.assertEqual(s['expiry_date']['value'],'2030-01-02');self.assertEqual(s['stop_date']['value'],'2025-02-01')
 def test_no_rounding_or_invented_dates(self):
  s=card_semantics(self.card(pay_amt='1.001',ed_dt='broken'),True)['semantics'];self.assertEqual(s['purchase_amount']['status'],'invalid');self.assertIsNone(s['expiry_date']['value'])
 def test_tier_is_context_only_and_conditions_preserve_algorithm(self):
  p={'member_excluded':False,'all_source_accounts_excluded':False,'pending_verifications':[]}
  a={'identity_status':'verified','tier':'普通'};b=decision_basis(a,p,True,'2026-01-01','blocked');self.assertFalse(b['result']);a['tier']='金卡';self.assertEqual(b,decision_basis(a,p,True,'2026-01-01','blocked'));self.assertTrue(decision_basis(a,p,True,'2026-01-01','no_known_restriction')['result']);self.assertFalse(decision_basis(a,p,True,None,'no_known_restriction')['result'])
 def test_each_safety_condition_can_block(self):
  p={'member_excluded':False,'all_source_accounts_excluded':False,'pending_verifications':[]};a={'identity_status':'verified'}
  for k,v in [('member_excluded',True),('all_source_accounts_excluded',True),('pending_verifications',['x'])]:self.assertFalse(decision_basis(a,{**p,k:v},True,'2026-01-01','no_known_restriction')['result'])
  self.assertFalse(decision_basis({'identity_status':'unresolved'},p,True,'2026-01-01','no_known_restriction')['result']);self.assertFalse(decision_basis(a,p,False,'2026-01-01','no_known_restriction')['result'])
 def test_critical_amount_mapping_cannot_change(self):
  obs=[{'name':'member_relations','result':{'status':'ok','evidence_id':'e','member_id':'u','cards':[card_semantics(self.card(),False)]}}];r={'status':'completed','summary':'事实仍需源复核','evidence_ids':['e'],'recommendations':[],'critical_facts':critical_facts(obs)};validate(r,final_contract(obs));self.assertTrue(validate_final(r,obs)[0]);r['critical_facts']['cards'][0]['purchase_amount']['value']='99.00'
  with self.assertRaises(ValidationError):validate(r,final_contract(obs))
  self.assertEqual(validate_final(r,obs),(False,'CRITICAL_FACTS_MISMATCH'))
 def test_critical_basis_cannot_add_tier(self):
  obs=[{'name':'get_member','result':{'status':'ok','evidence_id':'e','member_id':'u','recommendation_decision':{'conditions':{'identity_verified':True},'result':True}}}];r={'status':'completed','summary':'','evidence_ids':['e'],'recommendations':[],'critical_facts':critical_facts(obs)};r['critical_facts']['recommendation_decisions'][0]['conditions']['tier']='普通';self.assertEqual(validate_final(r,obs),(False,'CRITICAL_FACTS_MISMATCH'))
 def test_follow_up_tracks_unknown_field_not_verified_identity(self):
  a={'identity_status':'verified','source_ids':['CRM:a','POS:b']};sources=[{'source_id':'CRM:a','registered_store':'12'},{'source_id':'POS:b','registered_store':None}];p={'restriction_evidence':[{'source_id':'CRM:a','scope':'unknown'}]};r=follow_up_requirements(a,sources,p,'unknown');self.assertEqual([x['topic'] for x in r],['source_registration','contact_channel_scope']);self.assertEqual(r[0]['source_ids'],['POS:b']);self.assertEqual(r[0]['owner'],'老周');self.assertEqual(r[1]['owner'],'小林');self.assertNotIn('source_identity',[x['topic'] for x in r])
 def test_known_registration_and_channel_need_no_follow_up(self):
  self.assertEqual(follow_up_requirements({'identity_status':'verified','source_ids':['a']},[{'source_id':'a','registered_store':'12'}],{'restriction_evidence':[]},'blocked'),[])
 def test_validation_scope_never_claims_prose_acceptance(self):
  self.assertIn('free_text_fact_correspondence',VALIDATION_SCOPE['not_checked']);self.assertTrue(VALIDATION_SCOPE['source_review_required'])
if __name__=='__main__':unittest.main()
