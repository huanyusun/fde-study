#!/usr/bin/env python3
"""Strict whitelist packaging: no credentials, teacher results, future data or answers."""
from pathlib import Path
import argparse,json,hashlib,zipfile
ROOT=Path(__file__).resolve().parents[1]
FILES=['README.md','RELEASE.md','requirements.txt','requirements.in','product/semantics.json','product/system_prompt.txt','product/capabilities.json','product/API.md','evals/provider.py','evals/promptfooconfig.yaml','evals/README.md','tests/test_product_v2.py','tests/test_product_interaction.py','tests/test_model_policy.py','docs/model-configuration.md']
FILES += ['platform/fde_product/'+x+'.py' for x in ['models','business','agent','actions','tag_mock','observability','web','interaction']]
FILES += ['tools/'+x for x in ['product.py','check_product.py','verify_product.py','interaction_scenarios.py','finalize_evaluation.py','probe_custom_contract.mjs','run_custom_probe.py']]
FILES += [str(p.relative_to(ROOT)) for p in (ROOT/'sample_data').iterdir() if p.suffix in ('.csv','.json')]
FILES += ['contracts/w01/'+x+'.schema.json' for x in ['environment_check','product_fit_gap','model_baseline','runtime_evidence']]
def build(output):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    data={name:(ROOT/name).read_bytes() for name in sorted(FILES)}
    data['README.md']=(data['README.md'].decode().split('\n## 6.')[0]+'\n').encode()
    data['platform/fde_product/__init__.py']=b'"""W1 standard membership Agent."""\nVERSION = "0.2.0-w1"\nCONTRACT_VERSION = "w01-0.2.0"\n'
    data['pyproject.toml']=b'[tool.pytest.ini_options]\npythonpath = ["platform"]\ntestpaths = ["tests"]\n'
    for folder in ['customer','connectors','patches','artifacts/w01','docs/w01']:
        data[folder+'/README.md']=('本目录用于学员按周增加客户实现或交付证据。字段与行为以 contracts/w01 和 product/API.md 为准；初始包不预填客户答案。\n').encode()
    manifest={'product_version':'0.2.0-w1','runtime_revision':'gateway-stages-20260922','contract_version':'w01-0.2.0','fit_gap_contract_version':'w01-0.2.1','files':{k:hashlib.sha256(v).hexdigest() for k,v in data.items()}}
    data['MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in sorted(data.items()):z.writestr(name,content)
    print(json.dumps({'path':str(output),'files':len(data),'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}));return output
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();build(a.output)
