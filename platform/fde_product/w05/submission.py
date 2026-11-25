"""Export the two existing assignment blocks; no additional assignment."""
from pathlib import Path
import json,yaml
from .records import read_json,write_csv,dump,discard_new_output
from .service import load_lines

def export(prepared,output,mvp_report=None,customer_code=None,binding=None):
 out=Path(output).resolve()
 if out.exists():raise ValueError('NEW_SUBMISSION_REQUIRED')
 # Check the request before writing anything.
 if not customer_code or not binding:raise ValueError('MODEL_EXPORT_REQUIRES_CUSTOMER_CODE_AND_CURRENT_BINDING')
 try:return _export(prepared,out,mvp_report,customer_code,binding)
 except BaseException as exc:
  discard_new_output(out,exc);raise

def _export(prepared,output,mvp_report,customer_code,binding):
 prepared,out=Path(prepared).resolve(),Path(output).resolve()
 target=out/'artifacts/w05';target.mkdir(parents=True)
 rows=[]
 for r in load_lines(prepared/'state/members.jsonl'):
  if r['identity_status']!='verified':continue
  rows.append({'member_id':r['member_id'],'display_name':r['display_name'],'tier':r['tier'],'source_ids':json.dumps(r['source_ids']),'registered_stores':json.dumps(r['registered_stores']),'conflicts':json.dumps(r['conflicts'],ensure_ascii=False)})
 write_csv(target/'member_master.csv',rows,['member_id','display_name','tier','source_ids','registered_stores','conflicts']);dump(target/'reconciliation.json',read_json(prepared/'reconciliation.json'))
 ontology={'version':'w05-ontology-1','grain':'verified_person','financial_unresolved_bucket':'retained_financial_records_not_people','concepts':['Member','SourceAccount','Order','Card','Store','IdentityEvidence','OperationalVerification','ContactConstraint','KnowledgeSnippet'],'relations':{'SourceAccount->Member':'only_verified_identity_evidence','SourceAccount->Store':'registration_relation_unknown_allowed_multistore_retained','Order->Store':'purchase_store_separate_from_registration','Order->SourceAccount':'source_lineage_always_retained','Member->ContactConstraint':'all_verified_sources_merged_by_channel','Member->OperationalVerification':'scope_and_coverage_required','KnowledgeSnippet->Member':'conditions_checked_against_program_context'},'source_records':'mapping.json and source lineage retained with prepared state; original exports unchanged'}
 (target/'ontology.yaml').write_text(yaml.safe_dump(ontology,allow_unicode=True,sort_keys=False))
 if mvp_report:dump(target/'mvp_v1_report.json',read_json(mvp_report))
 from .candidate_submission import export_model
 export_model(prepared,out,customer_code,binding)
 return {'submission':str(out),'member_master_rows':len(rows),'required_blocks':['member_master/reconciliation/ontology/affected_library','mvp_v1_report and original_run_evidence'],'acceptance':'结构自检与工程证据；未决身份业务补证、修后作业复核、真人反馈及业务验收待完成。'}
