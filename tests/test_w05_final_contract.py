import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from jsonschema import validate,ValidationError
from fde_product.w05.integration import final_contract,validate_final
class FinalContract(unittest.TestCase):
 def observations(self,status='ok'):
  return [{'name':'member_cohort','result':{'status':status,'evidence_id':'current','member_ids':['U1'],'unknown_members':[],'blocked_members':[],'unresolved_sources':[],'coverage_complete':True,'page':{'complete':True}}}]
 def answer(self):return {'status':'completed','summary':'当前结果','evidence_ids':['current'],'recommendations':[],'member_ids':['U1'],'unknown_member_ids':[],'blocked_member_ids':[],'unresolved_source_ids':[],'task_scope':{'recommendations_requested':False,'statement':'只要名单'},'non_recommendations':[]}
 def test_missing_collection_not_repaired(self):
  answer=self.answer();del answer['member_ids']
  with self.assertRaises(ValidationError):validate(answer,final_contract(self.observations()))
 def test_previous_turn_evidence_not_allowed(self):
  answer=self.answer();answer['evidence_ids'].append('previous')
  with self.assertRaises(ValidationError):validate(answer,final_contract(self.observations()))
 def test_altered_member_set_not_allowed(self):
  answer=self.answer();answer['member_ids']=['U9']
  with self.assertRaises(ValidationError):validate(answer,final_contract(self.observations()))
 def test_partial_cannot_complete_even_when_shape_correct(self):
  obs=self.observations('partial');answer=self.answer();validate(answer,final_contract(obs));self.assertEqual(validate_final(answer,obs),(False,'PARTIAL_RESULT_CANNOT_COMPLETE'))
if __name__=='__main__':unittest.main()
