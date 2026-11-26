#!/usr/bin/env python3
"""Explicit public allow-list; never includes instructor/interview/runtime files."""
import argparse,json,hashlib,zipfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
def archive(path,entries,kind,version,data_version,manifest_name='MANIFEST.json'):
 manifest={'version':version,'kind':kind,'state':'engineering_candidate_not_issued','data_version':data_version,'rules_version':'qinghe-w05-rules-20261008.1','pending':['unresolved_business_evidence','repaired_submission_review','human_feedback','formal_release'],'files':{n:sha(data) for n,data in sorted(entries.items())}}
 with zipfile.ZipFile(path,'x',zipfile.ZIP_DEFLATED) as z:
  for name,data in sorted({**entries,manifest_name:(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()}.items()):
   info=zipfile.ZipInfo(name,date_time=(2026,10,11,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16;z.writestr(info,data)
 with zipfile.ZipFile(path) as z:
  assert all(sha(z.read(n))==h for n,h in manifest['files'].items())
 return {'path':str(path),'files':len(entries)+1,'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size}
def build(raw,output,version='w05-engineering-candidate-20261011.13',data_archive=None):
 raw,out=Path(raw),Path(output);out.mkdir(parents=True,exist_ok=False);entries={};data_version=json.loads((raw/'manifest.json').read_text())['id']
 files=['tests/test_w05_presentation.py','tests/test_w05_semantics.py','tests/test_w05_business_records.py','tests/test_w05_final_contract.py','requirements-w05.lock.txt','requirements-w03.txt','customer/w05/solution.py','customer/w05/service.py','customer/w04/solution.py','customer/w04/README.md','customer/w04/test_solution.py','customer/w04/check.json','tools/product.py','tools/w03.py','tools/w04.py','tools/w05.py','tools/w05_check.py','tools/build_w05_candidate.py','docs/w05/README.md','product/system_prompt.txt','product/semantics.json','product/w03_intent_prompt.txt','product/w03_answer_prompt.txt','product/w05_policy.json']
 for name in files:entries[name]=(ROOT/name).read_bytes()
 roots=['platform/fde_product/metrics','platform/fde_product/w04','platform/fde_product/w05','sample_data','templates/w03','templates/w04','contracts/w04','contracts/w05','examples/w03']
 for root in roots:
  for p in sorted((ROOT/root).rglob('*')):
   if p.is_file() and '__pycache__' not in p.parts and p.suffix in ['.py','.md','.json','.yaml','.yml','.sql','.csv','.txt']:entries[str(p.relative_to(ROOT))]=p.read_bytes()
 for p in sorted((ROOT/'platform/fde_product').glob('*.py')):entries[str(p.relative_to(ROOT))]=p.read_bytes()
 entries['README.md']=b'# W05 engineering candidate\n\nSee docs/w05/README.md. Complete the three customer TODOs using your own W03 library and W04 c3 output. This candidate has no instructor fallback, interview configuration or model credentials. Not released.\n'
 assert all(not n.startswith(('instructor/','scenarios/','.env','.runtime/')) and 'truth' not in n and '__pycache__' not in n for n in entries)
 code=archive(out/('fde-student-w05-'+version.removeprefix('w05-engineering-')+'.zip'),entries,'student_engineering_three_TODO',version,data_version)
 data={str(p.relative_to(raw)):p.read_bytes() for p in sorted(raw.rglob('*')) if p.is_file() and p.name.casefold()!='manifest.json'};data['manifest.json']=(raw/'manifest.json').read_bytes();manifest=json.loads(data['manifest.json']);assert manifest['synthetic'] is True
 assert all(sha(data[n])==h for n,h in manifest['sha256'].items());dataset_path=out/'qinghe-w05-v2-candidate-20261011.2.zip'
 if data_archive:
  source=Path(data_archive)
  with zipfile.ZipFile(source) as z:
   assert json.loads(z.read('manifest.json'))['id']==data_version
   assert all(z.read(n)==b for n,b in data.items() if n!='PACKAGE_MANIFEST.json')
  shutil.copyfile(source,dataset_path)
  dataset={'path':str(dataset_path),'files':len(zipfile.ZipFile(dataset_path).namelist()),'sha256':sha(dataset_path.read_bytes()),'bytes':dataset_path.stat().st_size,'reused_bytes':True}
 else:dataset=archive(dataset_path,data,'public_synthetic_business_records',version,data_version,manifest_name='PACKAGE_MANIFEST.json')
 result={'version':version,'student':code,'data':dataset,'exclusions':['teacher_reference','hidden_generator_sources','expected_member_lists','private_config','interview_candidates','run_evidence'],'status':'candidate_not_released'};(out/'package-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--raw',required=True);p.add_argument('--output',required=True);p.add_argument('--data-archive');a=p.parse_args();print(json.dumps(build(a.raw,a.output,data_archive=a.data_archive),ensure_ascii=False,indent=2))
