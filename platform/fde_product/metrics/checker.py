"""Public submission precheck. Does not certify business truth or interview completion."""
from pathlib import Path
from .common import read,dump,library_digest
from .builder import verify_library

def check(workspace):
 root=Path(workspace);items=[];targets=set()
 for name in ['docs/w03/business_model.md','docs/w03/model_changes.md','docs/w03/interview_notes.md','docs/w03/sow.md','docs/w03/metric_decisions.md','customer/w03/build-metrics/SKILL.md','customer/w03/tests.json','artifacts/w03/library/metrics.yml','artifacts/w03/metric_test_report.json']:
  p=root/name;items.append({'path':name,'passed':p.is_file() and bool(p.read_text().strip())})
 skill=root/'customer/w03/build-metrics/SKILL.md'
 if skill.exists():items.append({'check':'building_skill_implemented','passed':'UNIMPLEMENTED' not in skill.read_text()})
 library=root/'artifacts/w03/library';library_hash=None
 try:
  summary=verify_library(library);targets={t['id'] for t in read(root/'customer/w03/targets.json')}
  items.append({'check':'metric_coverage','passed':set(summary['metric_ids'])==targets})
  # Load re-runs the three checks; a library copied without passing them is not accepted here.
  items.append({'check':'library_validation','passed':read(library/'validation.json').get('passed') is True})
  library_hash=library_digest(library)
  dims=read(library/'dimension_check.json');fixed={x['id'] for x in read(Path(__file__).resolve().parents[3]/'templates/w03/dimension_targets.json')}
  items.append({'check':'dimension_target_coverage','passed':dims.get('passed') is True and {x['id'] for x in dims.get('items',[]) if x.get('passed')}==fixed})
 except (OSError,ValueError,KeyError,TypeError) as exc:items.append({'check':'library','passed':False,'reason':str(exc)})
 report=root/'artifacts/w03/metric_test_report.json'
 if report.exists():
  try:
   r=read(report);cases=r['cases'];covered={m for c in cases for m in c.get('expected',{}).get('intent',{}).get('metrics',[])}
   items.append({'check':'test_coverage','passed':bool(cases) and targets<=covered and r.get('complete') is True})
   items.append({'check':'self_reported_results','passed':bool(cases) and all(c.get('comparison',{}).get('passed') is True for c in cases),'limitation':'仅检查自报；教师独立复核另行进行'})
   # Executed queries carry the hash of the library their project was loaded from (same formula as load).
   hashes=[c['actual'].get('catalog_sha256') for c in cases if c['actual'].get('status')=='ok' or 'catalog_sha256' in c['actual']]
   same=bool(hashes) and library_hash is not None and all(h==library_hash for h in hashes)
   items.append({'check':'report_matches_library','passed':same,'library_sha256':library_hash,**({} if same else {'reason':'REPORT_LIBRARY_MISMATCH: 报告中的查询不是在由当前 artifacts/w03/library 加载的项目上执行的；请重新加载该库并重跑 test'})})
  except (ValueError,KeyError,TypeError,UnboundLocalError):items.append({'check':'report','passed':False})
 result={'contract_version':'w03-0.1.0','status':'precheck_passed' if all(x['passed'] for x in items) else 'needs_revision','items':items,'manual_review_required':['业务模型更新与来源','构建和判定是否实际开发','独立期望与错误注入','自然语言解释','王经理访谈及 SOW 边界']}
 dump(root/'artifacts/w03/precheck.json',result);return result
