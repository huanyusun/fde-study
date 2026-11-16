"""Build the explicit public W2 candidate, retaining the W1 product entry points."""
from pathlib import Path
import argparse,hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'platform'))
from build_w1_distribution import FILES as W1_FILES
from build_w02_extraction import FILES as EXTRACTION_FILES
NEW_FILES=['tools/build_w02_agent.py','tools/build_w1_distribution.py','product/w02_capabilities.json','pyproject.toml',
 'platform/fde_product/knowledge_io.py','platform/fde_product/natural_knowledge.py',
 'platform/fde_product/w02_natural_checker.py','tools/w02_knowledge.py','tools/check_w02.py',
 'contracts/w02/natural_run.schema.json','docs/w02_knowledge/README.md','docs/w02_check/README.md',
 'templates/w02_natural/knowledge_prompt.txt','templates/w02_delivery/interview_notes.md',
 'templates/w02_delivery/business_model.md','docs/w02_walkthrough/README.md',
 'examples/w02_natural/README.md','examples/w02_natural/business_model.md','tests/test_w02_natural.py',
 'platform/fde_product/extraction_workflow.py','platform/fde_product/workflow_report.py','tools/w02_workflow.py',
 'templates/w02_workflow/workflow.json','templates/w02_workflow/skills/extract-business/SKILL.md',
 'docs/w02_workflow/README.md','examples/w02_workflow/README.md','examples/w02_workflow/workflow.json',
 'examples/w02_workflow/extraction.json','examples/w02_workflow/business_model_start.md',
 'examples/w02_workflow/interview_notes_start.md','tests/test_w02_workflow.py']


def build(output):
    names=sorted(set(W1_FILES+EXTRACTION_FILES+NEW_FILES))
    data={}
    for name in names:
        p=ROOT/name
        if p.is_symlink() or not p.resolve().is_relative_to(ROOT):raise ValueError('SOURCE_PATH_INVALID')
        data[name]=p.read_bytes()
    data['README.md']=(data['README.md'].decode().split('\n## 6.')[0].split('\n## W2 客户知识')[0]+'\n\n## W2 客户知识\n\n从 [W2 完整操作导航](docs/w02_walkthrough/README.md)开始，知识入口见 [自然语言业务模型说明](docs/w02_knowledge/README.md)。提取骨架见 [提取说明](docs/w02_extraction/README.md)。提交前使用 [W2 公开预检](docs/w02_check/README.md)。本包沿用 W1 基座，提供客户知识提取、业务模型更新与使用验证；当前功能见 product/w02_capabilities.json。\n').encode()
    data['platform/fde_product/__init__.py']=b'"""Standard teaching Agent with optional W2 customer knowledge."""\nVERSION="0.2.0-w1"\nCONTRACT_VERSION="w01-0.2.0"\n'
    manifest={'version':'w02-agent-0.5.2-candidate','base_product_version':'0.2.0-w1','runtime_revision':'gateway-stages-20260922','materials_revision':'assignment-guidance-20260922',
              'workflow_version':'w02-workflow-0.1.0','knowledge_version':'w02-natural-0.1.0','checker_version':'w02-checker-0.2.0','contract_version':'w02-natural-0.1.0','extraction_contract_version':'w02-0.1.0-draft','status':'local_candidate',
              'files':{k:hashlib.sha256(v).hexdigest() for k,v in data.items()}}
    data['MANIFEST.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for name,value in sorted(data.items()):
            info=zipfile.ZipInfo('fde-agent-w02/'+name,date_time=(2026,9,20,0,0,0));info.external_attr=0o644<<16
            z.writestr(info,value,compress_type=zipfile.ZIP_DEFLATED)
    return {'path':str(output),'entries':len(data),'bytes':output.stat().st_size,'sha256':hashlib.sha256(output.read_bytes()).hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True)
    print(json.dumps(build(p.parse_args().output)))
