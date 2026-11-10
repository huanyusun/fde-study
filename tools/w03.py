#!/usr/bin/env python3
"""W03 helper framework. Standard business queries also use product.py."""
import argparse,json,sys,shutil,importlib.util,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from fde_product.metrics.common import read,dump
from fde_product.models import ModelError

CHECK_TEXT={'building_skill_implemented':'构建 Skill 还是占位内容：写完 customer/w03/build-metrics/SKILL.md。',
 'metric_coverage':'指标库没有覆盖全部目标指标：对照 customer/w03/targets.json 补齐后重新 build、merge。',
 'library_validation':'指标库没有通过加载校验：用 tools/w03.py load 加载，修好报错后再运行预检。',
 'dimension_target_coverage':'维度检查未覆盖全部目标：看 artifacts/w03/library/dimension_check.json，修好后重新加载。',
 'test_coverage':'测试没有覆盖全部目标指标，或报告不完整：补齐 customer/w03/tests.json 后重跑 tools/w03.py test。',
 'self_reported_results':'测试报告里有未通过的用例：修好后重跑 tools/w03.py test。',
 'report_matches_library':'测试报告不是在当前指标库上跑出来的：重新加载 artifacts/w03/library，再重跑 tools/w03.py test。',
 'report':'测试报告读不出来：重跑 tools/w03.py test，生成新报告。'}

def summary_lines(result):
 """Chinese recap for a learner; the JSON above stays the full result."""
 if result['status']=='precheck_passed':return ['预检结果：结构可供审阅，这不代表作业通过']
 missing={};rows=[]
 for item in result['items']:
  if item['passed']:continue
  if 'path' in item:
   folder,_,name=item['path'].rpartition('/');missing.setdefault(folder,[]).append(name)
  elif item.get('check')=='library':rows.append('指标库还没有生成或读不出来：先用 tools/w03.py build、merge 生成 artifacts/w03/library，再用 load 校验。')
  else:rows.append(CHECK_TEXT.get(item.get('check'),str(item.get('check'))+'：'+str(item.get('reason','看上方 JSON 中这一项。'))))
 rows=[f"{folder} 下缺文件或内容为空：{'、'.join(names)}。" for folder,names in missing.items()]+rows
 return [f'预检结果：还差 {len(rows)} 项，暂不能提交',*[f'{i}. {text}' for i,text in enumerate(rows,1)],'全部项和说明见上方 JSON。']

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 s=sub.add_parser('init');s.add_argument('--workspace',required=True)
 s=sub.add_parser('doctor')
 s=sub.add_parser('_inspect-worker');s.add_argument('--project',required=True)
 s=sub.add_parser('build');s.add_argument('--config',required=True);s.add_argument('--output',required=True);s.add_argument('--metrics',help='comma-separated target IDs; omit for all')
 s=sub.add_parser('merge');s.add_argument('--data',required=True);s.add_argument('--inputs',nargs='+',required=True);s.add_argument('--output',required=True)
 s=sub.add_parser('load');s.add_argument('--library',required=True);s.add_argument('--data',required=True);s.add_argument('--project',required=True);s.add_argument('--activate-home',help='Bind to the existing product home; default startup then uses the upgraded Agent')
 s=sub.add_parser('activate',help='Bind an already loaded and validated project to the product home');s.add_argument('--project',required=True);s.add_argument('--home',required=True)
 s=sub.add_parser('query');s.add_argument('--project',required=True);s.add_argument('--input',required=True);s.add_argument('--output',required=True)
 s=sub.add_parser('_query-worker');s.add_argument('--project',required=True);s.add_argument('--input',required=True);s.add_argument('--output',required=True)
 s=sub.add_parser('test');s.add_argument('--project',required=True);s.add_argument('--cases',required=True);s.add_argument('--output',required=True);s.add_argument('--cwd');s.add_argument('--judge-command',nargs='+',required=True)
 s=sub.add_parser('check');s.add_argument('--workspace',required=True)
 a=p.parse_args()
 if a.command=='init':
  out=Path(a.workspace).resolve();out.mkdir(parents=True,exist_ok=True);customer=out/'customer/w03'
  if customer.exists():raise ValueError('WORKSPACE_ALREADY_INITIALIZED')
  shutil.copytree(ROOT/'templates/w03/customer',customer);shutil.copy2(ROOT/'templates/w03/targets.json',customer/'targets.json');shutil.copy2(ROOT/'templates/w03/dimension_targets.json',customer/'dimension_targets.json')
  for folder in ['docs/w03','artifacts/w03','materials/w03']: (out/folder).mkdir(parents=True,exist_ok=True)
  for name in ['business_model.md','model_changes.md','interview_notes.md','sow.md']:
   f=out/'docs/w03'/name
   if not f.exists():f.write_text('# '+name+'\n\n请依据原始资料与实际运行记录完成，不覆盖 W02 提交。\n')
  for template in (ROOT/'templates/w03/documents').glob('*.md'):
   dest=out/'docs/w03'/template.name
   if not dest.exists() or dest.read_text().startswith('# '+template.name):shutil.copy2(template,dest)
  result={'workspace':str(out),'build_config':str(customer/'build.json'),'next':'复制学员材料；承接 W02 业务模型和补充访谈，完成模型更新，再开发构建 Skill 与判定代码。'}
 elif a.command=='doctor':
  missing=[x for x in ['duckdb','dbt_metricflow','yaml','langgraph','jsonschema'] if importlib.util.find_spec(x) is None]
  result={'python':sys.version.split()[0],'missing_dependencies':missing,'model_configured':all(os.environ.get(x) for x in ['FDE_MODEL_URL','FDE_MODEL_NAME','FDE_MODEL_KEY']),'network_call_performed':False}
 elif a.command=='_inspect-worker':
  from fde_product.metrics.validation import inspect_project
  result=inspect_project(a.project)
  if not result['passed']:result['status']='error'
 elif a.command=='build':
  from fde_product.metrics.builder import generate
  result=generate(a.config,a.output,a.metrics.split(',') if a.metrics else None)
 elif a.command=='merge':
  from fde_product.metrics.builder import merge
  result=merge(a.inputs,a.output,a.data)
 elif a.command=='load':
  from fde_product.metrics.engine import build_project
  try:
   if Path(a.project).exists():raise ValueError('PROJECT_ALREADY_EXISTS: '+str(Path(a.project).resolve())+'; load a changed library to a new version path, or bind this loaded project with: tools/w03.py activate --project '+a.project+' --home <product home>')
   result={'project':str(build_project(a.library,a.data,a.project))}
  except (ValueError,OSError) as exc:
   result={'status':'error','code':str(exc)}
   if a.activate_home:
    # The chat keeps the previous binding; say which project it still uses.
    binding=Path(a.activate_home)/'metrics-binding.json'
    result['active_project']=read(binding)['project'] if binding.exists() else None
    result['note']='加载失败，绑定未改变；聊天入口仍使用 active_project'+('。' if binding.exists() else '（为 null 表示未加载指标库）。')
  if a.activate_home and result.get('status')!='error':
   dump(Path(a.activate_home)/'metrics-binding.json',{'project':result['project'],'contract_version':'w03-0.1.0'})
   result['activated_home']=str(Path(a.activate_home).resolve())
 elif a.command=='activate':
  project=Path(a.project).resolve()
  if not (project/'dataset.json').exists() or not (project/'validation.json').exists() or read(project/'validation.json').get('passed') is not True:raise ValueError('PROJECT_NOT_VALIDATED: '+str(project)+'; load the library first')
  dump(Path(a.home)/'metrics-binding.json',{'project':str(project),'contract_version':'w03-0.1.0'})
  result={'project':str(project),'activated_home':str(Path(a.home).resolve()),'next':'重启 tools/product.py 后聊天入口使用该项目'}
 elif a.command in ('query','_query-worker'):
  from fde_product.metrics.engine import Engine,query_worker
  try:result=Engine(a.project,read_only=True).query(read(a.input)) if a.command=='_query-worker' else query_worker(a.project,read(a.input))
  except Exception as exc:result={'status':'error','code':type(exc).__name__,'reason':str(exc)}
  dump(a.output,result)
 elif a.command=='test':
  from fde_product.metrics.validator import run_cases
  from fde_product.metrics.common import configured_model
  configured_model()  # Model configuration is checked before the output path is created.
  result=run_cases(a.project,a.cases,a.judge_command,a.output,a.cwd)
 else:
  from fde_product.metrics.checker import check
  result=check(a.workspace)
 print(json.dumps(result,ensure_ascii=False,indent=2,default=str),flush=True)
 if a.command=='check':
  try:print('\n'.join(summary_lines(result)),file=sys.stderr)
  except Exception:pass  # The recap must never change the result.
 return 2 if result.get('status')=='error' else 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,OSError) as exc:print(json.dumps({'status':'error','code':str(exc)},ensure_ascii=False));raise SystemExit(2)
 except ModelError as exc:print(json.dumps({'status':'error','code':exc.code},ensure_ascii=False));raise SystemExit(2)
