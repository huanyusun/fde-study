"""Explicit installation on the existing product home, with complete dependencies."""
from pathlib import Path
from .records import read_json,dump,sha

def bind(prepared,home,customer_code):
 prepared,home,code=map(lambda p:Path(p).resolve(),(prepared,home,customer_code))
 from .prepare import GRAIN
 from .projection import verify_prepared
 verify_prepared(code.parent/'member.linkml.yaml',code,prepared)
 if read_json(prepared/'project/dataset.json').get('grain_version')!=GRAIN:raise ValueError('W05_PROJECT_REQUIRED')
 home.mkdir(parents=True,exist_ok=True)
 if (home/'member-binding.json').exists() or (home/'metrics-binding.json').exists():raise ValueError('EXISTING_BINDING_PRESERVED_USE_NEW_HOME')
 factory=Path(__file__).resolve().parents[3]/'customer/w05/service.py'
 dependencies={str(p):sha(p) for p in (Path(__file__).parent).glob('*.py')};dependencies[str(code)]=sha(code)
 dependencies[str(factory)]=sha(factory)
 dependencies.update({str(p):sha(p) for p in code.parent.rglob('*.py')})
 dependencies.update({str(p):sha(p) for p in (prepared/'state').iterdir() if p.is_file()})
 dependencies.update({str(p):sha(p) for p in (prepared/'objects').rglob('*') if p.is_file() and '__pycache__' not in p.parts})
 dependencies[str(code.parent/'member.linkml.yaml')]=sha(code.parent/'member.linkml.yaml')
 dependencies[str(factory.parents[2]/'requirements-w05.lock.txt')]=sha(factory.parents[2]/'requirements-w05.lock.txt')
 dependencies.update({str(p):sha(p) for p in (prepared/'knowledge-index').rglob('*') if p.is_file()})
 root=factory.parents[2]
 for rel in ['platform/fde_product/metrics/agent.py','platform/fde_product/metrics/engine.py','platform/fde_product/metrics/semantic_contract.py','product/w03_intent_prompt.txt','product/w03_answer_prompt.txt']:
  dependencies[str(root/rel)]=sha(root/rel)
 import os
 relative=lambda p:os.path.relpath(p,home)
 dependencies={relative(p):h for p,h in dependencies.items()}
 dump(home/'member-binding.json',{'version':'w05-member-binding-1','project':relative(prepared/'project'),'module':relative(factory),'module_sha256':sha(factory),'module_dependencies':dependencies,'configuration':{'state':relative(prepared/'state'),'objects':relative(prepared/'objects')}})
 dump(home/'metrics-binding.json',{'project':relative(prepared/'project'),'contract_version':'w03-0.1.0'})
 return {'home':str(home),'data_version':read_json(prepared/'state/manifest.json')['data_version'],'shared_tools':4,'default_entry':'tools/product.py run|serve|start'}
