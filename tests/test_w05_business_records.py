import sys,unittest,importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from fde_product.w05.records import current_records,verify_basis
class Records(unittest.TestCase):
 def row(self,id='r1',**kw):return {'record_id':id,'status':'current','valid_from':'2026-08-31','valid_until':'2026-09-02','replaces_record_id':'',**kw}
 def test_date_does_not_replace_record(self):
  valid,_=current_records([self.row(),self.row('r2',valid_from='2026-09-01')],'2026-09-01');self.assertEqual(len(valid),2)
 def test_explicit_effective_replacement(self):
  valid,ignored=current_records([self.row(),self.row('r2',replaces_record_id='r1')],'2026-09-01');self.assertEqual([r['record_id'] for _,r in valid],['r2']);self.assertEqual(ignored[0]['reason'],'EXPLICITLY_REPLACED')
 def test_inactive_cannot_override_valid_ban(self):
  valid,_=current_records([self.row(),self.row('r2',status='revoked',replaces_record_id='r1')],'2026-09-01');self.assertEqual([r['record_id'] for _,r in valid],['r1'])
 def test_failed_migration_never_valid(self):
  self.assertFalse(current_records([self.row(status='failed')],'2026-09-01',('success',))[0])
 def test_half_open_expiry(self):self.assertFalse(current_records([self.row(valid_until='2026-09-01')],'2026-09-01')[0])
 def test_unknown_replacement_rejected(self):
  with self.assertRaises(ValueError):current_records([self.row(replaces_record_id='missing')],'2026-09-01')
 def test_duplicate_source_record_rejected(self):
  with self.assertRaises(ValueError):current_records([self.row(),self.row()],'2026-09-01')
 def test_business_basis_tied_to_specified_account(self):
  mat={'business_basis.csv':[{'document_id':'B','source_accounts':'CRM:A|POS:B'}]};r={'basis_file':'business_basis.csv','basis_row':'1','basis_document_id':'B','source_id':'CRM:A'};self.assertTrue(verify_basis(r,mat));self.assertFalse(verify_basis({**r,'source_id':'CRM:C'},mat));self.assertFalse(verify_basis({**r,'basis_row':'0'},mat))
 def test_raw_basis_source_account_matches(self):
  mat={'business_basis.csv':[{'document_id':'B','source_accounts':'CRM:A'}],'crm_member_export.csv':[{'hy_id':'C'}]};r={'basis_file':'crm_member_export.csv','basis_row':'1','basis_document_id':'B','source_id':'CRM:A'};self.assertFalse(verify_basis(r,mat))
class DormancyBoundary(unittest.TestCase):
 def service(self,latest,covered=True):
  from fde_product.w05.service import Service
  from datetime import date
  s=object.__new__(Service);s.dataset={'reference_date':'2026-09-01'};s.members={'M':{'identity_status':'verified','tier':'金卡','source_ids':[]}};s.sources={};s.policies={'M':{'member_excluded':False,'all_source_accounts_excluded':False,'pending_verifications':[],'channels':{'sms':'no_known_restriction','telephone':'no_known_restriction'}}};s.last_dates=lambda ref:{'M':date.fromisoformat(latest)} if latest else {};s.covered=lambda ref,days:covered
  return s
 def test_at_least_threshold_inclusive_and_above(self):
  s=self.service('2026-06-25')
  for threshold,expected in [(60,True),(68,True),(69,False)]:
   with self.subTest(threshold=threshold):self.assertIs(s.detail({'member_id':'M','channel':'sms','dormant_days':threshold})['dormancy_condition']['matches'],expected)
 def test_missing_last_purchase_remains_unknown(self):self.assertIsNone(self.service(None).detail({'member_id':'M','channel':'sms'})['dormancy_condition']['matches'])
 def test_incomplete_coverage_remains_unknown(self):self.assertIsNone(self.service('2026-06-25',False).detail({'member_id':'M','channel':'sms'})['dormancy_condition']['matches'])
if __name__=='__main__':unittest.main()
