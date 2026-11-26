"""Course-provided build/load/query adapter. No custom ORM or generator.
Generated files are disposable; existing financial DuckDB remains unchanged.
"""
import os, sys, json, hashlib, subprocess, importlib.util
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[3]
os.environ.setdefault('PYSTOW_HOME',str(ROOT/'.cache/pystow'))
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from linkml_runtime.utils.schemaview import SchemaView
from linkml.generators.jsonschemagen import JsonSchemaGenerator
from jsonschema import Draft202012Validator

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=str)+'\n',newline='\n')
def generate(schema,output):
    schema,output=Path(schema).resolve(),Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    # Schema metamodel validation before invoking official generators.
    import yaml
    from linkml_runtime.linkml_model import meta
    from linkml_runtime.utils.yamlutils import as_dict
    raw=yaml.safe_load(schema.read_text())
    if 'TODO' in schema.read_text():raise ValueError('MODEL_TODO_FILL_CUSTOMER_SOURCE')
    sv=SchemaView(str(schema))
    for cls in ['Member','SourceAccount','Store']:
        if cls not in sv.all_classes():raise ValueError('MODEL_REQUIRED_CLASS:'+cls)
    metamodel=json.loads((Path(meta.__file__).parent/'jsonschema/meta.schema.json').read_text())
    errors=list(Draft202012Validator(metamodel).iter_errors(yaml.safe_load(schema.read_text())))
    if errors:raise ValueError('SCHEMA_INVALID:'+str(errors[0]))
    command=[str(Path(sys.executable).parent/'gen-sqla'),'--sqla-style','2',str(schema)]
    r=subprocess.run(command,capture_output=True,text=True,check=True)
    (output/'orm.py').write_text(r.stdout,newline='\n')
    validators={}
    for c in ['Member','SourceAccount','Store']:
        val=json.loads(JsonSchemaGenerator(str(schema),top_class=c).serialize())
        dump(output/(c+'.schema.json'),val);validators[c]=Draft202012Validator(val)
    dump(output/'build.json',{'schema':'customer/w05/member.linkml.yaml','schema_sha256':sha(schema),'orm_sha256':sha(output/'orm.py'),'command':['gen-sqla','--sqla-style','2','customer/w05/member.linkml.yaml'],'style':2,'patched':False})
    return load_module(output/'orm.py'),validators

def load_module(path):
    name='generated_'+sha(path)
    if name in sys.modules:return sys.modules[name]
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module

def validate_data(data,validators):
    for key,c in [('members','Member'),('accounts','SourceAccount'),('stores','Store')]:
        ids=[x['id'] for x in data[key]]
        if len(ids)!=len(set(ids)):raise ValueError('DUPLICATE_IDENTIFIER:'+c)
        for n,row in enumerate(data[key],1):
            errors=list(validators[c].iter_errors(row))
            if errors:raise ValueError(f'INSTANCE_INVALID:{c}:{n}:'+'.'.join(map(str,errors[0].absolute_path))+':'+errors[0].message)
    accounts={x['id']:x for x in data['accounts']};stores={x['id'] for x in data['stores']}
    membership=Counter()
    for row in data['members']:
        if not row['source_accounts']:raise ValueError('MEMBER_REQUIRES_SOURCE')
        if len(row['source_accounts'])!=len(set(row['source_accounts'])):raise ValueError('DUPLICATE_RELATION')
        for sid in row['source_accounts']:
            if sid not in accounts:raise ValueError('MISSING_REFERENCE:'+sid)
            membership[sid]+=1
        for sid in row.get('registered_stores',[]):
            if sid not in stores:raise ValueError('MISSING_REFERENCE:'+sid)
        # Customer provenance consistency, beyond generic generated FK validation.
        expected={accounts[s]['registered_store'] for s in row['source_accounts'] if accounts[s].get('registered_store')}
        if set(row.get('registered_stores',[]))!=expected:raise ValueError('REGISTRATION_PROVENANCE_MISMATCH')
    if set(membership)!=set(accounts) or any(n!=1 for n in membership.values()):raise ValueError('SOURCE_MUST_HAVE_ONE_FINANCIAL_OWNER')
    for row in accounts.values():
        if row.get('registered_store') and row['registered_store'] not in stores:raise ValueError('MISSING_REFERENCE:'+row['registered_store'])

def create_projection(module,data,database):
    database=Path(database).resolve()
    if database.exists():raise ValueError('NEW_DATABASE_REQUIRED')
    engine=create_engine('duckdb:///'+str(database))
    module.Base.metadata.create_all(engine)
    # Bulk IO uses generated metadata, preserving generated PK/FK/types.
    def bulk(con,table,rows):
        # One set-based INSERT per batch rather than DBAPI row-by-row executemany.
        for offset in range(0,len(rows),1000):
            con.execute(table.insert().values(rows[offset:offset+1000]))
    with engine.begin() as con:
        bulk(con,module.Store.__table__,data['stores'])
        rows=[{**{k:v for k,v in r.items() if k!='registered_store'},'registered_store_id':r.get('registered_store')} for r in data['accounts']]
        bulk(con,module.SourceAccount.__table__,rows)
        bulk(con,module.Member.__table__,[{c.name:r.get(c.name) for c in module.Member.__table__.columns} for r in data['members']])
        for attr in ['source_accounts','registered_stores']:
            links=[{'Member_id':r['id'],attr+'_id':s} for r in data['members'] for s in r.get(attr,[])]
            if links:bulk(con,module.Base.metadata.tables['Member_'+attr],links)
    engine.dispose()

def query(database,generated,member_id):
    module=load_module(generated);engine=create_engine('duckdb:///'+str(Path(database).resolve()),connect_args={'read_only':True})
    with Session(engine) as session:
        member=session.get(module.Member,member_id)
        if member is None:result=None
        else:
            result={'id':member.id,'display_name':member.display_name,'identity_status':member.identity_status,
                    'source_accounts':[{'id':a.id,'system':a.system,'source_file':a.source_file,'source_row':a.source_row,'registered_store':a.registered_store.id if a.registered_store else None,'payload':json.loads(a.payload)} for a in member.source_accounts],
                    'registered_stores':sorted(s.id for s in member.registered_stores),'payload':json.loads(member.payload)}
            # Optional business change is present only when genuinely generated.
            if hasattr(member,'registration_reviewed_at'):result['registration_reviewed_at']=member.registration_reviewed_at
    engine.dispose();return result

def snapshot(prepared):
    prepared=Path(prepared)
    def lines(name):return [json.loads(s) for s in (prepared/'state'/name).read_text().splitlines()]
    import csv
    stores=list(csv.DictReader((prepared/'cleaned/stores.csv').open()))
    return {'stores':[{'id':r['store_id'],'name':r['store_name']} for r in stores],
        'accounts':[{'id':r['source_id'],'system':r['system'],'source_file':r['source_file'],'source_row':r['source_row'],**({'registered_store':r['registered_store']} if r.get('registered_store') else {}),'payload':json.dumps(r,ensure_ascii=False)} for r in lines('sources.jsonl')],
        'members':[{'id':r['member_id'],**({'display_name':r['display_name']} if r.get('display_name') else {}),'identity_status':r['identity_status'],'source_accounts':r['source_ids'],'registered_stores':r['registered_stores'],'payload':json.dumps(r,ensure_ascii=False),**r.get('model_fields',{})} for r in lines('members.jsonl')]}

def build(schema,data,output):
    output=Path(output);module,validators=generate(schema,output/'generated');validate_data(data,validators);dump(output/'input.json',data);create_projection(module,data,output/'objects.duckdb')
    dump(output/'projection.json',{'schema_sha256':sha(schema),'orm_sha256':sha(output/'generated/orm.py'),'input_sha256':sha(output/'input.json'),'database_sha256':sha(output/'objects.duckdb'),'counts':{k:len(v) for k,v in data.items()}})
    return output


def build_prepared(schema, prepared):
    """Materialize one batch. Fixed core mapping consumes the existing customer hooks."""
    schema,prepared=Path(schema).resolve(),Path(prepared).resolve()
    output=prepared/'objects'; output.mkdir()
    data=snapshot(prepared)
    module,validators=generate(schema,output/'generated')
    validate_data(data,validators)
    create_projection(module,data,output/'objects.duckdb')
    artifacts={p.relative_to(output).as_posix():sha(p) for p in (output/'generated').iterdir() if p.is_file()}
    artifacts['objects.duckdb']=sha(output/'objects.duckdb')
    state=json.loads((prepared/'state/manifest.json').read_text())
    dump(output/'projection.json',{'version':'w05-linkml-projection-candidate-1','schema_sha256':sha(schema),
        'customer_code_sha256':sha(schema.parent/'solution.py'),'data_version':state['data_version'],
        'rules_version':state['rules_version'],'state_files':state['files'],'artifacts':artifacts,
        'counts':{k:len(v) for k,v in data.items()},'generated_files_patched':False})
    return output

def verify_prepared(schema,code,prepared):
    schema,code,prepared=map(Path,(schema,code,prepared));o=prepared/'objects'
    m=json.loads((o/'projection.json').read_text())
    if m['schema_sha256']!=sha(schema):raise ValueError('MODEL_SOURCE_CHANGED_REPREPARE_REQUIRED')
    if m['customer_code_sha256']!=sha(code):raise ValueError('CUSTOMER_CODE_CHANGED_REPREPARE_REQUIRED')
    state=json.loads((prepared/'state/manifest.json').read_text())
    if m['data_version']!=state['data_version'] or m['rules_version']!=state['rules_version'] or m['state_files']!=state['files']:
        raise ValueError('OBJECT_PREPARED_BATCH_MISMATCH')
    for name,h in m['artifacts'].items():
        if sha(o/name)!=h:raise ValueError('OBJECT_GENERATION_OR_DATABASE_CHANGED_REBUILD_REQUIRED:'+name)
    for name,h in m['state_files'].items():
        if sha(prepared/'state'/name)!=h:raise ValueError('OBJECT_STATE_CHANGED_REPREPARE_REQUIRED:'+name)
    return m

def read_objects(database,generated):
    """One immutable batch at service construction; all tools see the same typed fields.
    Bulk selects use generated classes and generated relationship metadata.
    No request writes into the old service dictionaries.
    """
    from collections import defaultdict
    module=load_module(generated)
    engine=create_engine('duckdb:///'+str(Path(database).resolve()),connect_args={'read_only':True})
    links={}
    with engine.connect() as con:
        for attr in ['source_accounts','registered_stores']:
            values=defaultdict(list)
            for mid,sid in con.execute(select(module.Base.metadata.tables['Member_'+attr])):
                values[mid].append(sid)
            links[attr]=values
    members,sources={},{}
    with Session(engine) as session:
        for obj in session.scalars(select(module.Member)).yield_per(2000):
            row=json.loads(obj.payload)
            row.update(member_id=obj.id,display_name=obj.display_name,identity_status=obj.identity_status,
                source_ids=sorted(links['source_accounts'][obj.id]),registered_stores=sorted(links['registered_stores'][obj.id]))
            extra={c.name:getattr(obj,c.name) for c in module.Member.__table__.columns if c.name not in {'id','display_name','identity_status','payload'}}
            if extra:row['model_fields']={k:str(v) if hasattr(v,'isoformat') else v for k,v in extra.items()}
            members[obj.id]=row
        for obj in session.scalars(select(module.SourceAccount)).yield_per(2000):
            row=json.loads(obj.payload)
            row.update(source_id=obj.id,system=obj.system,source_file=obj.source_file,source_row=obj.source_row,
                registered_store=obj.registered_store_id)
            sources[obj.id]=row
    engine.dispose()
    return members,sources
