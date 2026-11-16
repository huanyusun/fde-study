"""Check library dependencies against typed empty tables before creating a project."""
import csv,json,re
from pathlib import Path
import duckdb,yaml
from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment
from .w04_import import MEMBER_EXTENSIONS, OPTIONAL_TABLES

REF=re.compile(r"ref\(\s*['\"]([a-z][a-z0-9_]*)['\"]\s*\)")
MODEL_REF=re.compile(r"^ref\(\s*['\"]([a-z][a-z0-9_]*)['\"]\s*\)$")

class LibraryPreflightError(ValueError):
    def __init__(self,report):
        self.report=report
        super().__init__('LIBRARY_PREFLIGHT_FAILED: '+json.dumps(report,ensure_ascii=False))

def check_library(library,data,templates,base_tables,coverage):
    library,data,templates=map(Path,(library,data,templates));issues=[]
    def issue(code,file,message,**extra):issues.append({'code':code,'file':str(file),'message':message,**extra})
    models={p.stem:p for p in templates.glob('*.sql')};models.update({p.stem:p for p in library.glob('*.sql')})
    body=yaml.safe_load((library/'metrics.yml').read_text());grains=json.loads((library/'grain_contract.json').read_text()) if (library/'grain_contract.json').exists() else {}
    dependencies={name:set(REF.findall(p.read_text())) for name,p in models.items()}
    for name,refs in dependencies.items():
        for dep in refs-set(models):issue('MISSING_MODEL',models[name],f'模型 {name} 引用 {dep}，请在指标库补齐 {dep}.sql 或修正 ref。',model=name,missing_model=dep)
    for sm in body.get('semantic_models',[]):
        match=MODEL_REF.fullmatch(sm.get('model',''))
        if not match:issue('INVALID_MODEL_REF',library/'metrics.yml',f'语义模型 {sm["name"]} 的 model 须为 ref(模型名)。',model=sm['name']);continue
        name=match[1]
        if name not in models:issue('MISSING_MODEL',library/'metrics.yml',f'语义模型 {sm["name"]} 引用 {name}，请补齐 {name}.sql 或修正 model。',model=sm['name'],missing_model=name)
        unique=[e for e in sm.get('entities',[]) if e['type'] in ('primary','unique')]
        if sm.get('primary_entity') and not unique and not grains.get(sm['name']):issue('MISSING_GRAIN',library/'grain_contract.json',f'语义模型 {sm["name"]} 缺粒度列；请在 grain_contract.json 声明业务键（例如月度账户模型的 month_start、member_id）。',model=sm['name'])
    env=SandboxedEnvironment(undefined=StrictUndefined);env.globals.clear()
    con=duckdb.connect(':memory:');created=set();blocked=set()
    try:
        schemas={k:dict(v) for k,v in base_tables.items()};schemas.update(OPTIONAL_TABLES)
        for name,types in schemas.items():
            path=data/(name+'.csv')
            if not path.exists():continue
            with path.open(encoding='utf-8-sig',newline='') as f:header=next(csv.reader(f),[])
            if name=='members':types={**types,**MEMBER_EXTENSIONS}
            # The importer retains full header/value checks. This uses only the
            # contract types and the actual column presence, never client rows.
            columns=[f'"{k}" {types[k]}' for k in header if k in types]
            if columns:con.execute(f'create table raw_{name} ('+', '.join(columns)+')')
        pending=set(models)
        while pending:
            ready=[n for n in sorted(pending) if dependencies[n]<=created]
            if not ready:
                for name in sorted(pending):
                    if dependencies[name] & (blocked | (set(dependencies[name])-set(models))):blocked.add(name)
                    elif dependencies[name]<=pending:issue('MODEL_DEPENDENCY_CYCLE',models[name],f'模型 {name} 的引用形成循环，请检查 ref 依赖。',model=name)
                break
            for name in ready:
                pending.remove(name)
                try:
                    sql=env.from_string(models[name].read_text()).render(ref=lambda n:'"'+n+'"',var=lambda n:{'coverage_start':coverage[0],'coverage_end':coverage[1]}[n])
                    con.execute('create view "'+name+'" as '+sql);created.add(name)
                except Exception as exc:
                    blocked.add(name);reason=str(exc)
                    missing=re.search(r'(?:Referenced column|Values list .*?column named)\s+"([^"]+)"',reason)
                    issue('MODEL_SQL_INVALID',models[name],f'模型 {name} 无法绑定列；请检查该 SQL 的来源模型及依赖列。'+reason,model=name,**({'missing_column':missing[1]} if missing else {}))
        for sm in body.get('semantic_models',[]):
            match=MODEL_REF.fullmatch(sm.get('model',''))
            if not match or match[1] not in created:continue
            table='"'+match[1]+'"'
            entries=[(kind,item.get('name',''),str(item.get('expr',item['name']))) for kind in ['entities','dimensions','measures'] for item in sm.get(kind,[])]
            entries += [('grain',str(k),str(k)) for k in grains.get(sm['name'],[])]
            for kind,name,expr in entries:
                try:con.execute('explain select '+expr+' from '+table)
                except Exception as exc:
                    reason=str(exc);missing=re.search(r'Referenced column "([^"]+)"',reason)
                    file=library/'grain_contract.json' if kind=='grain' else library/'metrics.yml'
                    issue('MISSING_COLUMN',file,f'语义模型 {sm["name"]} 的 {kind}.{name} 无法在 {match[1]} 取得列；请补派生列或修正表达式。'+reason,model=sm['name'],entry=name,**({'missing_column':missing[1]} if missing else {}))
    finally:con.close()
    report={'passed':not issues,'issues':issues,'models_checked':sorted(created),'phase':'before_project_creation','client_rows_read':False}
    if issues:raise LibraryPreflightError(report)
    return report
