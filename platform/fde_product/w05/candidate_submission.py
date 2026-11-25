"""Candidate submission supplements; existing business checks stay authoritative."""
import json,shutil
from pathlib import Path
from .records import dump,read_json,sha
from .projection import verify_prepared

def export_model(prepared,submission,code,binding):
    if not code or not binding:raise ValueError('MODEL_EXPORT_REQUIRES_CUSTOMER_CODE_AND_CURRENT_BINDING')
    code,binding,prepared,submission=map(Path,(code,binding,prepared,submission))
    source=code.parent/'member.linkml.yaml'
    metadata=verify_prepared(source,code,prepared)
    from .runtime import MemberService,digest
    service=MemberService(binding)
    if service.project.resolve()!=(prepared/'project').resolve():raise ValueError('EXPORT_BINDING_PREPARED_MISMATCH')
    dependencies={(binding.parent/p).resolve():h for p,h in service.binding['module_dependencies'].items()}
    if dependencies.get(source.resolve())!=sha(source) or dependencies.get(code.resolve())!=sha(code):
        raise ValueError('EXPORT_BINDING_CUSTOMER_MODEL_MISMATCH')
    customer=submission/'customer/w05';customer.mkdir(parents=True)
    shutil.copy2(source,customer/source.name);shutil.copy2(code,customer/code.name)
    root=Path(__file__).resolve().parents[3]
    shutil.copy2(root/'requirements-w05.lock.txt',submission/'requirements-w05.lock.txt')
    target=submission/'artifacts/w05'
    dump(target/'model-build.json',metadata)
    dump(target/'model-binding.json',{'version':'w05-linkml-submission-1','source':'customer/w05/member.linkml.yaml',
        'customer_code':'customer/w05/solution.py','source_sha256':sha(source),'customer_code_sha256':sha(code),
        'lock_sha256':sha(submission/'requirements-w05.lock.txt'),'binding_sha256':sha(binding),
        'binding_dependencies_sha256':digest(service.binding['module_dependencies']),
        'data_version':metadata['data_version'],'rules_version':metadata['rules_version'],
        'generated_orm_sha256':metadata['artifacts']['generated/orm.py'],'rebuild_required_in_new_workspace':True,
        'generate_command':['gen-sqla','--sqla-style','2','customer/w05/member.linkml.yaml']})
    import yaml
    old=yaml.safe_load((target/'ontology.yaml').read_text())
    old['executable_model']={'source':'customer/w05/member.linkml.yaml','sha256':sha(source),'classes':list(yaml.safe_load(source.read_text())['classes'])}
    old['description_only']=True
    (target/'ontology.yaml').write_text(yaml.safe_dump(old,allow_unicode=True,sort_keys=False))

def check_model(submission,prepared,binding):
    submission,prepared=Path(submission),Path(prepared);checks={};errors=[]
    def record(name,fn):
        try:
            fn();checks[name]=True
        except Exception as exc:
            checks[name]=False;errors.append({'check':name,'code':str(exc)[:300]})
    def assert_true(condition,code):
        if not condition:raise ValueError(code)
    def source():
        assert_true((submission/'customer/w05/member.linkml.yaml').is_file(),'MODEL_SOURCE_MISSING')
        assert_true('TODO' not in (submission/'customer/w05/member.linkml.yaml').read_text(),'MODEL_SOURCE_TODO')
    record('model_source_present_and_filled',source)
    def generation():
        m=verify_prepared(submission/'customer/w05/member.linkml.yaml',submission/'customer/w05/solution.py',prepared)
        proof=read_json(submission/'artifacts/w05/model-binding.json')
        assert_true(proof['source_sha256']==m['schema_sha256'] and proof['customer_code_sha256']==m['customer_code_sha256'],'SUBMISSION_MODEL_BUILD_MISMATCH')
        assert_true(proof['generated_orm_sha256']==m['artifacts']['generated/orm.py'],'SUBMISSION_GENERATION_MISMATCH')
        assert_true(proof['lock_sha256']==sha(submission/'requirements-w05.lock.txt'),'DEPENDENCY_LOCK_CHANGED')
    record('model_source_generation_and_batch_current',generation)
    def bound():
        assert_true(bool(binding),'MODEL_CURRENT_BINDING_REQUIRED')
        b=read_json(binding);proof=read_json(submission/'artifacts/w05/model-binding.json')
        assert_true(proof['binding_sha256']==sha(binding),'SUBMISSION_OLD_NEW_BINDING_MISMATCH_REEXPORT_REQUIRED')
        assert_true(b['project'] and not Path(b['project']).is_absolute(),'BINDING_ABSOLUTE_PATH_REBUILD_REQUIRED')
        assert_true(all(not Path(p).is_absolute() for p in b['module_dependencies']),'BINDING_TEACHER_ABSOLUTE_PATH_REBUILD_REQUIRED')
        from .runtime import MemberService
        service=MemberService(binding)
        assert_true(service.project.resolve()==(prepared/'project').resolve(),'BINDING_PREPARED_MISMATCH')
        assert_true(service.dataset['id']==proof['data_version'],'MODEL_BINDING_DATA_VERSION_MISMATCH')
    record('model_current_relative_binding',bound)
    def portable():
        proof=read_json(submission/'artifacts/w05/model-binding.json')
        for name in ['source','customer_code']:
            assert_true(not Path(proof[name]).is_absolute() and (submission/proof[name]).is_file(),'SUBMISSION_SOURCE_PATH_NOT_RELOCATABLE')
        for p in (submission/'requests').rglob('*.json'):
            def visit(x):
                if isinstance(x,dict):
                    for v in x.values():visit(v)
                elif isinstance(x,list):
                    for v in x:visit(v)
                elif isinstance(x,str) and (x.startswith('/Users/') or x.startswith('/home/')):
                    raise ValueError('REQUEST_TEACHER_ABSOLUTE_PATH:'+str(p.relative_to(submission)))
            visit(read_json(p))
    record('model_submission_paths_relocatable',portable)
    return checks,errors
