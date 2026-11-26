#!/usr/bin/env python3
"""Public submission self-check, without hidden counts or teacher implementation."""
import argparse,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from fde_product.w05.records import read_json,read_csv,dump,sha

def check(submission,prepared,binding=None):
 from fde_product.w05.service import load_lines
 import yaml,duckdb
 path=Path(submission)/'artifacts/w05';prepared=Path(prepared);checks={};errors=[]
 def record(name,fn):
  try:checks[name]=bool(fn())
  except Exception as exc:checks[name]=False;errors.append({'check':name,'code':type(exc).__name__})
 dataset=read_json(prepared/'project/dataset.json');state=read_json(prepared/'state/manifest.json');reconciliation=read_json(path/'reconciliation.json');master=read_csv(path/'member_master.csv');mapping=read_json(prepared/'state/mapping.json')
 expected={r['member_id'] for r in mapping if r['member_id']};actual={r['member_id'] for r in master};sources=[s for r in master for s in json.loads(r['source_ids'])];ontology=yaml.safe_load((path/'ontology.yaml').read_text())
 record('block1_version_agreement',lambda:reconciliation['data_version']==dataset['id']==state['data_version'])
 record('block1_master_matches_submitted_mapping_not_hidden_total',lambda:actual==expected and len(actual)==len(master))
 record('block1_each_verified_source_assigned_once',lambda:len(sources)==len(set(sources)) and set(sources)=={r['source_id'] for r in mapping if r['member_id']})
 record('block1_unresolved_finance_explicit',lambda:ontology['financial_unresolved_bucket']=='retained_financial_records_not_people' and reconciliation['precision_acceptance'].startswith('pending'))
 record('block1_registration_vs_purchase_relationships',lambda:'SourceAccount->Store' in ontology['relations'] and 'Order->Store' in ontology['relations'])
 attrs={r['member_id']:r for r in load_lines(prepared/'state/members.jsonl')}
 record('block1_source_registration_sets_preserved',lambda:all(sorted(json.loads(r['registered_stores']))==attrs[r['member_id']]['registered_stores'] for r in master))
 record('block1_knowledge_and_state_hashes',lambda:all(sha(prepared/'state'/n)==h for n,h in state['files'].items()))
 con=duckdb.connect(str(prepared/'project/data.duckdb'),read_only=True)
 try:
  count,net=con.execute("select count(*),sum(case when status='paid' then paid_cents-refund_cents else 0 end) from raw_orders").fetchone()
 finally:con.close()
 record('block1_order_conservation',lambda:count==reconciliation['orders']['combined_accepted'] and net==reconciliation['orders']['net_paid_cents'])
 record('block1_original_metric_validation',lambda:read_json(prepared/'project/validation.json')['passed'])
 record('block2_mvp_report_present',lambda:(path/'mvp_v1_report.json').exists())
 if checks['block2_mvp_report_present']:
  report=read_json(path/'mvp_v1_report.json')
  record('block2_report_version_agreement',lambda:report['data_version']==dataset['id'] and report['rules_version']==state['rules_version'])
  record('block2_original_evidence_and_changes',lambda:bool(report['baseline_evidence']) and bool(report['current_evidence']) and bool(report['change_log']) and all((Path(submission)/p).exists() for p in report['baseline_evidence']+report['current_evidence']))
  record('block2_acceptance_boundary',lambda:report['formal_acceptance'] is False and 'precise_person_total' in report['pending'])
 if binding:
  from fde_product.w05.runtime import MemberService
  svc=MemberService(binding)
  record('shared_service_bound_to_submission',lambda:svc.project.resolve()==(prepared/'project').resolve())
  record('four_public_capabilities',lambda:len(svc.schemas())==4)
  probe=svc.call('get_member',{'member_id':master[0]['member_id'],'channel':'sms'})
  record('program_policy_and_provenance',lambda:probe.get('status') in ['ok','unknown'] and 'recommendation_allowed' in probe and probe.get('versions',{}).get('data_version')==dataset['id'])
 from fde_product.w05.candidate_submission import check_model
 model_checks,model_errors=check_model(submission,prepared,binding)
 checks.update(model_checks);errors.extend(model_errors)
 return {'version':'w05-public-checker-linkml-candidate-1','passed':all(checks.values()),'checks':checks,'errors':errors,'data_version':dataset['id'],'scope':'仅结构、已提交映射一致性、金额守恒、版本和可运行能力。不检查自由文字事实、身份证据正确性或客户验收。','pending':['precise_person_total','course_rubric_acceptance','repaired_submission_review','human_feedback','release']}
CHECK_TEXT={'readable_submission_and_prepared_inputs':'提交目录或准备目录读不出来：核对 --submission、--prepared 路径，以及 artifacts/w05 下的文件是否齐全。',
 'block1_version_agreement':'对账、数据集和状态的数据版本不一致：用同一版本重新生成。',
 'block1_master_matches_submitted_mapping_not_hidden_total':'会员主档与提交的映射不一致：从映射重新生成 member_master.csv。',
 'block1_each_verified_source_assigned_once':'已确认的来源账号没有恰好归到一位会员：检查映射与 source_ids。',
 'block1_unresolved_finance_explicit':'未解决的财务记录没有按要求标明：核对 ontology.yaml 和对账里的精度验收写法。',
 'block1_registration_vs_purchase_relationships':'本体缺注册门店或购买门店的关系：在 ontology.yaml 的 relations 里补上。',
 'block1_source_registration_sets_preserved':'主档里的注册门店集合与准备数据不一致：不要合并或丢掉来源的注册门店。',
 'block1_knowledge_and_state_hashes':'准备目录的状态文件与清单哈希不一致：重新准备，不要手改。',
 'block1_order_conservation':'订单数或净支付金额对不上：核对 reconciliation.json 与数据。',
 'block1_original_metric_validation':'原指标校验未通过：看准备目录 project/validation.json。',
 'block2_mvp_report_present':'缺 artifacts/w05/mvp_v1_report.json：按任务书生成。',
 'block2_report_version_agreement':'MVP 报告的数据或规则版本不是当前版本：更新后重新生成。',
 'block2_original_evidence_and_changes':'MVP 报告缺基线证据、当前证据或变更记录，或引用的文件不存在：补齐。',
 'block2_acceptance_boundary':'MVP 报告的验收边界写法不符合要求：核对 formal_acceptance 和 pending 两个字段。',
 'shared_service_bound_to_submission':'共享服务没有绑定本次提交的项目：重新绑定后再运行。',
 'four_public_capabilities':'共享服务的公开能力不是 4 个：核对服务配置。',
 'program_policy_and_provenance':'服务返回缺策略字段或版本来源：核对 get_member 的返回。',
 'model_source_present_and_filled':'模型源文件缺失或未填写：完成 LinkML 模型源文件。',
 'model_source_generation_and_batch_current':'模型生成结果不是当前版本：改动模型或代码后重新生成并重跑批处理。',
 'model_current_relative_binding':'服务绑定不是当前版本或不是相对路径：重新导出绑定。',
 'model_submission_paths_relocatable':'提交里有换目录后失效的路径：改成相对路径后重新导出。'}

def summary_lines(result):
 """Chinese recap for a learner; the JSON above stays the full result. Pending items stay out of it."""
 if result['passed']:return ['预检结果：结构可供审阅，这不代表作业通过']
 rows=[CHECK_TEXT.get(name,name) for name,good in result['checks'].items() if not good]
 return [f'预检结果：还差 {len(rows)} 项，暂不能提交',*[f'{i}. {text}' for i,text in enumerate(rows,1)],'全部项和说明见上方 JSON。']

def main():
 p=argparse.ArgumentParser();p.add_argument('--submission',required=True);p.add_argument('--prepared',required=True);p.add_argument('--binding');p.add_argument('--output',required=True);a=p.parse_args()
 if Path(a.output).exists():raise ValueError('NEW_CHECK_OUTPUT_REQUIRED')
 try:r=check(a.submission,a.prepared,a.binding)
 except (OSError,ValueError,KeyError,TypeError) as exc:r={'version':'w05-public-checker-1','passed':False,'checks':{'readable_submission_and_prepared_inputs':False},'errors':[{'code':type(exc).__name__,'reason':str(exc)}],'scope':'输入无法读取或契约格式不满足，未执行验收。'}
 dump(a.output,r);print(json.dumps(r,ensure_ascii=False,indent=2),flush=True)
 try:print('\n'.join(summary_lines(r)),file=sys.stderr)
 except Exception:pass  # The recap must never change the result.
 raise SystemExit(0 if r['passed'] else 1)
if __name__=='__main__':main()
