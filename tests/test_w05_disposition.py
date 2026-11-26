"""Candidate disposition (2026-11-05, design 2026-10-12 item 3): with candidates on the cited cohort page, the answer
states whether recommendations were requested; when they were, every candidate is recommended or has a supported
non-recommendation, otherwise the turn cannot pass."""
import unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from jsonschema import validate,ValidationError
from fde_product.w05.integration import final_contract,validate_final
from fde_product.w05.semantics import critical_facts
from fde_product.w05.presentation import fact_summary,suggestion_text

ALLOWED={'identity_verified':True,'member_not_excluded':True,'some_source_account_not_excluded':True,'no_pending_operational_verification':True,'recent_purchase_coverage_complete':True,'recent_effective_purchase_present':True,'selected_channel_has_no_known_restriction':True}

def member(mid,allowed=True,channel_state='no_known_restriction',**changes):
    conditions={**ALLOWED,'selected_channel_has_no_known_restriction':channel_state=='no_known_restriction',**changes}
    return {'status':'ok' if allowed or channel_state=='blocked' or changes else 'unknown','evidence_id':'G'+mid,'member_id':mid,'recommendation_allowed':allowed,
            'recommendation_context':{'channel':'sms'},'policy':{'channels':{'telephone':'no_known_restriction','sms':channel_state}},
            'recommendation_decision':{'conditions':conditions}}

class Disposition(unittest.TestCase):
    def observations(self,members=('M1','M2'),details=None,knowledge_hits=None,blocked=(),unknown=()):
        cohort={'status':'ok','evidence_id':'C','member_ids':list(members),'unknown_members':list(unknown),'blocked_members':list(blocked),'unresolved_sources':[],'coverage_complete':True,'page':{'complete':True}}
        obs=[{'name':'member_cohort','result':cohort}]
        for d in (details if details is not None else [member(m) for m in members]):
            obs.append({'name':'get_member','result':d});obs.append({'name':'member_relations','result':{'status':'ok','evidence_id':'R'+d['member_id'],'member_id':d['member_id']}})
        hits=knowledge_hits if knowledge_hits is not None else [{'node_id':'k1','applicability':'applicable','source':{'conditions':{}}}]
        obs.append({'name':'retrieve_knowledge','result':{'status':'ok','evidence_id':'K','hits':hits}})
        return obs
    def rec(self,mid):return {'member_id':mid,'suggestion':'复核','evidence_ids':['G'+mid,'R'+mid,'K'],'knowledge_node_ids':['k1']}
    def answer(self,obs,recs=(),non=(),requested=True,status='completed',scope=True):
        c=obs[0]['result']
        a={'status':status,'summary':'x','evidence_ids':[o['result']['evidence_id'] for o in obs],'recommendations':list(recs),'member_ids':c['member_ids'],'unknown_member_ids':c['unknown_members'],'blocked_member_ids':c['blocked_members'],'unresolved_source_ids':[]}
        if scope:a.update(task_scope={'recommendations_requested':requested,'statement':'s'},non_recommendations=list(non))
        facts=critical_facts(obs)
        if any(facts.values()):a['critical_facts']=facts
        summary=fact_summary(obs)
        if summary is not None:a['summary']=summary
        for r in a['recommendations']:
            text=suggestion_text(r['member_id'],obs)
            if text is not None:r['suggestion']=text
        return a

    def test_requested_but_empty_recommendations_cannot_pass(self):
        obs=self.observations();self.assertEqual(validate_final(self.answer(obs),obs),(False,'CANDIDATE_NOT_DISPOSED'))
    def test_one_candidate_missing_cannot_pass(self):
        obs=self.observations();self.assertEqual(validate_final(self.answer(obs,[self.rec('M1')]),obs),(False,'CANDIDATE_NOT_DISPOSED'))
    def test_all_recommended_passes(self):
        obs=self.observations();self.assertEqual(validate_final(self.answer(obs,[self.rec('M1'),self.rec('M2')]),obs),(True,'GROUNDED'))
    def test_not_requested_list_only_passes(self):
        obs=self.observations(details=[]);self.assertEqual(validate_final(self.answer(obs,requested=False),obs),(True,'GROUNDED'))
    def test_not_requested_with_recommendations_rejected(self):
        obs=self.observations();self.assertEqual(validate_final(self.answer(obs,[self.rec('M1'),self.rec('M2')],requested=False),obs),(False,'RECOMMENDATIONS_NOT_REQUESTED'))
    def test_missing_task_scope_rejected_when_candidates_exist(self):
        obs=self.observations();self.assertEqual(validate_final(self.answer(obs,[self.rec('M1'),self.rec('M2')],scope=False),obs),(False,'TASK_SCOPE_REQUIRED'))
        with self.assertRaises(ValidationError):validate(self.answer(obs,[self.rec('M1'),self.rec('M2')],scope=False),final_contract(obs))
    def test_empty_cohort_keeps_old_contract(self):
        obs=self.observations(members=(),details=[]);a=self.answer(obs,scope=False)
        self.assertEqual(validate_final(a,obs),(True,'GROUNDED'));self.assertNotIn('task_scope',final_contract(obs)['required'])
    def test_program_blocked_mixed_with_recommendation_can_complete(self):
        obs=self.observations(details=[member('M1'),member('M2',allowed=False,channel_state='blocked')])
        non=[{'member_id':'M2','reason_code':'program_blocked','evidence_ids':['GM2'],'explanation':'短信渠道有明确限制'}]
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1')],non),obs),(True,'GROUNDED'))
    def test_program_blocked_needs_blocking_evidence(self):
        obs=self.observations()
        non=[{'member_id':'M2','reason_code':'program_blocked','evidence_ids':['GM2'],'explanation':'编的'}]
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1')],non),obs),(False,'NON_RECOMMENDATION_REASON_UNSUPPORTED'))
    def test_facts_pending_cannot_complete(self):
        obs=self.observations(details=[member('M1'),member('M2',allowed=False,channel_state='unknown')])
        non=[{'member_id':'M2','reason_code':'facts_pending','evidence_ids':['GM2'],'explanation':'渠道范围待核'}]
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1')],non,status='completed'),obs)[0],False)
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1')],non,status='incomplete'),obs),(True,'GROUNDED'))
    def test_no_applicable_knowledge_requires_real_empty_retrieval(self):
        obs=self.observations(members=('M1',))
        non=[{'member_id':'M1','reason_code':'no_applicable_knowledge','evidence_ids':['GM1','K'],'explanation':'无适用知识'}]
        self.assertEqual(validate_final(self.answer(obs,[],non,status='incomplete'),obs),(False,'NON_RECOMMENDATION_REASON_UNSUPPORTED'))
        obs=self.observations(members=('M1',),knowledge_hits=[])
        self.assertEqual(validate_final(self.answer(obs,[],non,status='incomplete'),obs),(True,'GROUNDED'))
        self.assertEqual(validate_final(self.answer(obs,[],non,status='completed'),obs)[0],False)
    def test_not_requested_reason_contradicts_requested_scope(self):
        obs=self.observations()
        non=[{'member_id':m,'reason_code':'not_requested','evidence_ids':['C'],'explanation':'未要求'} for m in ('M1','M2')]
        self.assertEqual(validate_final(self.answer(obs,[],non),obs),(False,'NON_RECOMMENDATION_REASON_UNSUPPORTED'))
    def test_duplicate_and_outside_rejected(self):
        obs=self.observations()
        dup=[{'member_id':'M1','reason_code':'evidence_missing','evidence_ids':['GM1'],'explanation':'x'}]
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1'),self.rec('M2')],dup),obs),(False,'CANDIDATE_DISPOSITION_DUPLICATE'))
        out=[{'member_id':'M9','reason_code':'evidence_missing','evidence_ids':['C'],'explanation':'x'}]
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1'),self.rec('M2')],out,status='incomplete'),obs),(False,'NON_RECOMMENDATION_OUTSIDE_COHORT'))
    def test_cohort_blocked_member_can_be_explained_from_cohort(self):
        obs=self.observations(blocked=('B1',))
        non=[{'member_id':'B1','reason_code':'program_blocked','evidence_ids':['C'],'explanation':'圈选结果列为阻断'}]
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1'),self.rec('M2')],non),obs),(True,'GROUNDED'))
    def test_history_evidence_rejected(self):
        obs=self.observations(details=[member('M1'),member('M2',allowed=False,channel_state='blocked')])
        non=[{'member_id':'M2','reason_code':'program_blocked','evidence_ids':['OLD'],'explanation':'x'}]
        self.assertEqual(validate_final(self.answer(obs,[self.rec('M1')],non),obs),(False,'NON_RECOMMENDATION_CITATION_REQUIRED'))
    def test_contract_accepts_valid_disposition_shape(self):
        obs=self.observations(details=[member('M1'),member('M2',allowed=False,channel_state='blocked')])
        non=[{'member_id':'M2','reason_code':'program_blocked','evidence_ids':['GM2'],'explanation':'x'}]
        validate(self.answer(obs,[self.rec('M1')],non),final_contract(obs))
        with self.assertRaises(ValidationError):validate(self.answer(obs,[self.rec('M1')],[{**non[0],'reason_code':'other'}]),final_contract(obs))

if __name__=='__main__':unittest.main()


class NothingToDispose(unittest.TestCase):
    """2026-11-06 (author, merged W05～W08 plan items 1, 2, 4): with nobody to dispose of, extra disposition or empty set
    fields do not fail the format; a failed answer shows the program's fixed text, never the model's."""
    def test_empty_page_tolerates_stated_scope(self):
        obs=Disposition().observations(members=(),details=[]);a=Disposition().answer(obs,requested=False,scope=True)
        validate(a,final_contract(obs));self.assertEqual(validate_final(a,obs),(True,'GROUNDED'))
        a['non_recommendations']=[{'member_id':'M1','reason_code':'not_requested','evidence_ids':['C'],'explanation':'x'}]
        with self.assertRaises(ValidationError):validate(a,final_contract(obs))
    def test_refused_selection_tolerates_empty_sets_and_scope(self):
        obs=[{'name':'member_cohort','result':{'status':'error','code':'TOOL_DENIED','evidence_id':'D'}}]
        a={'status':'incomplete','summary':'没有权限','evidence_ids':['D'],'recommendations':[],'member_ids':[],'unknown_member_ids':[],'blocked_member_ids':[],'unresolved_source_ids':[],
           'task_scope':{'recommendations_requested':False,'statement':'s'},'non_recommendations':[]}
        validate(a,final_contract(obs));self.assertEqual(validate_final(a,obs),(True,'GROUNDED'))
        a['member_ids']=['M1']
        with self.assertRaises(ValidationError):validate(a,final_contract(obs))
    def test_list_only_schema_says_leave_empty(self):
        obs=Disposition().observations()
        self.assertIn('留空',final_contract(obs)['properties']['non_recommendations']['description'])
    def test_failed_summary_is_program_text(self):
        from fde_product.w05.integration import failed_summary
        self.assertEqual(failed_summary({'properties':{'summary':{'type':'string','const':'程序摘要'}}},'X'),'程序摘要')
        self.assertIn('FINAL_TYPED_CONTRACT',failed_summary({'properties':{'summary':{'type':'string'}}},'FINAL_TYPED_CONTRACT'))
