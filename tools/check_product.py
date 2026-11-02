#!/usr/bin/env python3
"""Portable artifact checker; execution evidence is separately rerun by reviewers."""
import argparse,json,hashlib,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from jsonschema import Draft202012Validator
REQUIRED_CASES={'analysis','clarification','missing_coverage','readonly','http_action','idempotency','undo'}

def check(root,dry=False):
    root=Path(root).resolve();errors=[];values={}
    if dry:
        for p in (ROOT/'contracts/w01').glob('*.schema.json'):Draft202012Validator.check_schema(json.loads(p.read_text()))
        return {'status':'dry_run','note':'Only schemas were checked; learner execution not verified.','errors':[]}
    for name in ['environment_check','product_fit_gap','model_baseline','runtime_evidence']:
        p=root/'artifacts/w01'/(name+'.json')
        try:
            value=json.loads(p.read_text(encoding='utf-8'));schema=json.loads((ROOT/'contracts/w01'/(name+'.schema.json')).read_text())
            errors += [name+': '+e.message for e in Draft202012Validator(schema).iter_errors(value)];values[name]=value
        except (OSError,ValueError):errors.append(name+': MISSING_OR_INVALID')
    if errors:return {'status':'fail','errors':errors}
    versions={v['product_version'] for v in values.values()}
    if len(versions)!=1:errors.append('PRODUCT_VERSION_MISMATCH')
    env=values['environment_check']
    if any(c['status']!='pass' for c in env['checks'].values()):errors.append('ENVIRONMENT_NOT_READY')
    ev=values['runtime_evidence'];cases={c['case_id']:c for c in ev['cases']}
    if len(cases)!=len(ev['cases']) or not REQUIRED_CASES<=cases.keys() or not all(c['passed'] for c in cases.values()):errors.append('REQUIRED_BEHAVIOR_FAILED')
    known={x['id'] for x in json.loads((ROOT/'product/capabilities.json').read_text())['capabilities']}
    for item in values['product_fit_gap']['items']:
        if not set(item['capability_ids'])<=known:errors.append('UNKNOWN_CAPABILITY_ID')
        if item['evidence_status']=='verified' and not item['evidence']:errors.append('VERIFIED_WITHOUT_EVIDENCE')
    if not (root/'docs/w01/project_assessment.md').is_file():errors.append('PROJECT_ASSESSMENT_MISSING')
    notes=[]
    for rel,expected in ev['artifact_hashes'].items():
        # Earlier Windows runs recorded backslash paths and hashed CRLF bytes; Git or zip tools may since have changed line endings.
        p=(root/rel.replace('\\','/')).resolve()
        if not p.is_relative_to(root) or not p.is_file():errors.append('INVALID_EVIDENCE_PATH');continue
        raw=p.read_bytes();lf=raw.replace(b'\r\n',b'\n')
        if hashlib.sha256(raw).hexdigest()==expected:continue
        if expected in (hashlib.sha256(lf).hexdigest(),hashlib.sha256(lf.replace(b'\n',b'\r\n')).hexdigest()):notes.append('LINE_ENDINGS_NORMALIZED: '+rel)
        else:errors.append('EVIDENCE_HASH_MISMATCH: '+rel)
    for c in cases.values():
        if c['evidence'] not in ev['artifact_hashes']:errors.append('CASE_EVIDENCE_NOT_HASHED: '+c['case_id'])
    for r in values['model_baseline']['runs']:
        if r['run_id'] not in ev['artifact_hashes']:errors.append('BASELINE_RUN_NOT_HASHED')
        if r['actual_status']!=r['expected_status'] or not r['passed']:errors.append('MODEL_BASELINE_FAILED: '+r['case_id'])
    if not any(x['case_id']=='analysis' for x in values['model_baseline']['runs']):errors.append('NO_LIVE_ANALYSIS')
    return {'status':'fail' if errors else 'pass','errors':errors,'notes':notes,'limits':['Artifact checks do not prove authorship or replace live behavior replay and rubric review.']}

EVIDENCE_STEP='运行 tools/verify_product.py --live，完成 evals 评估后运行 tools/finalize_evaluation.py。'
MISSING_STEPS={'environment_check':EVIDENCE_STEP,'model_baseline':EVIDENCE_STEP,'runtime_evidence':EVIDENCE_STEP,
    'product_fit_gap':'按 README 自行填写这份文件。'}
HINTS={'PRODUCT_VERSION_MISMATCH':'几份 JSON 的产品版本不一致，用同一版工程重新生成。',
    'ENVIRONMENT_NOT_READY':'环境检查有未通过的项，看 artifacts/w01/environment_check.json 里的 checks，修好后重新生成。',
    'REQUIRED_BEHAVIOR_FAILED':'必测行为缺项或未通过，看 artifacts/w01/runtime_evidence.json 的 cases，修好后重跑 tools/verify_product.py --live。',
    'UNKNOWN_CAPABILITY_ID':'fit-gap 引用了产品没有的能力编号，改成 product/capabilities.json 里已有的编号。',
    'VERIFIED_WITHOUT_EVIDENCE':'fit-gap 里标为 verified 的条目没有写证据，补上证据或改状态。',
    'PROJECT_ASSESSMENT_MISSING':'缺立项报告，写到 docs/w01/project_assessment.md。',
    'INVALID_EVIDENCE_PATH':'运行证据引用的文件不在工程内或已不存在，恢复文件或重跑验证。',
    'BASELINE_RUN_NOT_HASHED':'模型基线的运行记录没有进入证据哈希，重跑 tools/verify_product.py --live。',
    'NO_LIVE_ANALYSIS':'模型基线里没有 analysis 用例的实际运行，重跑 tools/verify_product.py --live。',
    'EVIDENCE_HASH_MISMATCH':'证据文件在生成后被改过，恢复原文件或重跑验证。',
    'CASE_EVIDENCE_NOT_HASHED':'用例证据没有进入证据哈希，重跑 tools/verify_product.py --live。',
    'MODEL_BASELINE_FAILED':'模型基线有用例未通过，看 artifacts/w01/model_baseline.json，修好后重跑 tools/verify_product.py --live。'}

def summary_lines(r):
    """Chinese recap for a learner; the JSON above stays the full result."""
    if r['status']=='pass':return ['预检结果：结构可供审阅，这不代表作业通过']
    rows={}
    for error in r['errors']:
        head,_,detail=error.partition(': ')
        if head in MISSING_STEPS and detail=='MISSING_OR_INVALID':text=f'缺 artifacts/w01/{head}.json，或内容不是合法 JSON：{MISSING_STEPS[head]}'
        elif head in MISSING_STEPS:text=f'artifacts/w01/{head}.json 不符合格式要求，第一处：{detail}'
        elif head in HINTS:text=HINTS[head]+(f'（{detail}）' if detail else '')
        else:text=error
        key=head if head in MISSING_STEPS else error
        rows.setdefault(key,text)
    return [f'预检结果：还差 {len(rows)} 项，暂不能提交',*[f'{i}. {text}' for i,text in enumerate(rows.values(),1)],'全部项和说明见上方 JSON。']

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default=str(ROOT));p.add_argument('--dry-run',action='store_true');a=p.parse_args();r=check(a.root,a.dry_run);print(json.dumps(r,ensure_ascii=False,indent=2),flush=True)
    if r['status']!='dry_run':
        try:print('\n'.join(summary_lines(r)),file=sys.stderr)
        except Exception:pass  # The recap must never change the result.
    raise SystemExit(1 if r['status']=='fail' else 0)
