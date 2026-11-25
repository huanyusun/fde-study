"""Public submission precheck. Does not certify business truth or interview completion."""
from pathlib import Path
from .common import read,dump
from .builder import verify_library

def check(workspace):
 root=Path(workspace);items=[];targets=set()
 for name in ['docs/w03/business_model.md','docs/w03/model_changes.md','docs/w03/interview_notes.md','docs/w03/sow.md','docs/w03/metric_decisions.md','customer/w03/build-metrics/SKILL.md','customer/w03/tests.json','artifacts/w03/library/metrics.yml','artifacts/w03/metric_test_report.json']:
  p=root/name;items.append({'path':name,'passed':p.is_file() and bool(p.read_text().strip())})
 skill=root/'customer/w03/build-metrics/SKILL.md'
 if skill.exists():items.append({'check':'building_skill_implemented','passed':'UNIMPLEMENTED' not in skill.read_text()})
 library=root/'artifacts/w03/library'
 try:
  summary=verify_library(library);targets={t['id'] for t in read(root/'customer/w03/targets.json')}
  items.append({'check':'metric_coverage','passed':set(summary['metric_ids'])==targets})
  dims=read(library/'dimension_check.json');fixed={x['id'] for x in read(Path(__file__).resolve().parents[3]/'templates/w03/dimension_targets.json')}
  items.append({'check':'dimension_target_coverage','passed':dims.get('passed') is True and {x['id'] for x in dims.get('items',[]) if x.get('passed')}==fixed})
 except (OSError,ValueError,KeyError,TypeError) as exc:items.append({'check':'library','passed':False,'reason':str(exc)})
 report=root/'artifacts/w03/metric_test_report.json'
 if report.exists():
  try:
   r=read(report);cases=r['cases'];covered={m for c in cases for m in c.get('expected',{}).get('intent',{}).get('metrics',[])}
   items.append({'check':'test_coverage','passed':bool(cases) and targets<=covered and r.get('complete') is True})
   items.append({'check':'self_reported_results','passed':bool(cases) and all(c.get('comparison',{}).get('passed') is True for c in cases),'limitation':'仅检查自报；教师独立复核另行进行'})
  except (ValueError,KeyError,TypeError,UnboundLocalError):items.append({'check':'report','passed':False})
 result={'contract_version':'w03-0.1.0','status':'precheck_passed' if all(x['passed'] for x in items) else 'needs_revision','items':items,'manual_review_required':['业务模型更新与来源','构建和判定是否实际开发','独立期望与错误注入','自然语言解释','王经理访谈及 SOW 边界']}
 dump(root/'artifacts/w03/precheck.json',result);return result
