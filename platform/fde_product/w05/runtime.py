"""One registered, versioned service for direct calls and the actual Agent graph."""
import hashlib,importlib.util,json
from pathlib import Path
from jsonschema import validate,ValidationError
from duckdb import Error as DuckDBError

NAMES={'member_cohort','get_member','member_relations','retrieve_knowledge'}
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
class MemberService:
    def __init__(self,binding):
        self.binding_path=Path(binding).resolve();self.binding=json.loads(self.binding_path.read_text());b=self.binding
        required={'version','project','module','module_sha256','configuration'}
        if not required<=set(b) or set(b)-required-{'module_dependencies'} or b['version']!='w05-member-binding-1':raise ValueError('MEMBER_BINDING_INVALID')
        if 'objects' not in b['configuration']:raise ValueError('MODEL_BINDING_REQUIRED_REPREPARE_REBIND')
        self.project=(self.binding_path.parent/b['project']).resolve();self.module_path=(self.binding_path.parent/b['module']).resolve()
        if hashlib.sha256(self.module_path.read_bytes()).hexdigest()!=b['module_sha256']:raise ValueError('MEMBER_MODULE_VERSION_CHANGED_REBIND_REQUIRED')
        dependencies=b.get('module_dependencies',{})
        if not isinstance(dependencies,dict):raise ValueError('MEMBER_DEPENDENCY_MANIFEST_INVALID')
        for path,expected in dependencies.items():
            if hashlib.sha256((self.binding_path.parent/path).resolve().read_bytes()).hexdigest()!=expected:raise ValueError('MEMBER_DEPENDENCY_VERSION_CHANGED_REBIND_REQUIRED')
        self.dataset=json.loads((self.project/'dataset.json').read_text())
        spec=importlib.util.spec_from_file_location('w05_registered_'+b['module_sha256'],self.module_path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.implementation=module.create_service({'project':str(self.project),'dataset':self.dataset,'configuration':{**b['configuration'],**{k:str((self.binding_path.parent/b['configuration'][k]).resolve()) for k in ['state','objects'] if k in b['configuration']}}})
        self.tool_schemas=self.implementation.schemas()
        if {t['function']['name'] for t in self.tool_schemas}!=NAMES or len(self.tool_schemas)!=len(NAMES):raise ValueError('MEMBER_TOOL_CONTRACT_REQUIRED')
        self.parameters={t['function']['name']:t['function']['parameters'] for t in self.tool_schemas}
        self.version={'binding_version':b['version'],'module_sha256':b['module_sha256'],'data_version':self.dataset['id'],
            'data_snapshot_sha256':hashlib.sha256((self.project/'dataset.json').read_bytes()).hexdigest(),'grain_version':self.dataset.get('grain_version'),'mapping_version':self.dataset.get('identity_rule_version'),'module_dependencies_sha256':digest(dependencies)}
    def schemas(self):return self.tool_schemas
    def call(self,name,args):
        try:
            for path,expected in self.binding.get('module_dependencies',{}).items():
                dependency=(self.binding_path.parent/path).resolve()
                if not dependency.is_file() or hashlib.sha256(dependency.read_bytes()).hexdigest()!=expected:
                    return {'status':'error','code':'MEMBER_DEPENDENCY_VERSION_CHANGED_REBIND_REQUIRED','versions':self.version}
            if name not in NAMES:raise ValueError('UNSUPPORTED_MEMBER_TOOL')
            validate(args,self.parameters[name]);result=self.implementation.call(name,args)
            if not isinstance(result,dict) or result.get('status') not in ['ok','partial','conflict','unknown','not_found','unsupported','error']:raise ValueError('MEMBER_RESULT_CONTRACT_INVALID')
            if result.get('versions',{}).get('data_version',self.dataset['id'])!=self.dataset['id']:raise ValueError('MEMBER_RESULT_DATA_VERSION_MISMATCH')
        except (ValueError,KeyError,TypeError,ValidationError,NotImplementedError) as e:
            result={'status':'error','code':'MEMBER_MODULE_UNIMPLEMENTED' if isinstance(e,NotImplementedError) else 'MEMBER_TOOL_CONTRACT_FAILED'}
        except (OSError,DuckDBError):
            # Missing, moved or locked prepared files fail this call only, not the whole turn.
            result={'status':'error','code':'MEMBER_DATA_UNAVAILABLE'}
        result=json.loads(json.dumps(result,ensure_ascii=False,default=str))
        result={**result,'versions':{**result.get('versions',{}),**self.version}}
        result['evidence_id']=digest({k:v for k,v in result.items() if k!='evidence_id'})
        return result

def active_binding(home):
    path=Path(home)/'member-binding.json'
    return path if path.exists() else None
