"""Public structure precheck and deterministic replay audit.

Formal verification uses a separate set of unpublished input samples.
The public response contains only pass/fail and layers.
"""
import csv
import shutil
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from .io import ROOT, read_json, read_inputs, sha, validate, load_rules, dump
from .harness import database_facts

SECTIONS={
    'data_diagnosis.md':[['数据范围','版本','覆盖','来源'],['剖析','异常','字典','证据','字典过时','映射错误','数据暂缺'],['清洗','隔离','保留','对账'],['工作账','CRM'],['数据结论','访谈','推断','待核'],['下一步','核实']],
    'demo_plan.md':[['链路','选择'],['数据可用','验证','证据'],['暂不','待验证'],['运行','bad case'],['判断','假设','继续','缩小','调整']],
    'metric_changes.md':[['指标','ID'],['修订前','修订后'],['依据','来源']],
    'model_changes.md':[['承接','版本','核对','结果'],['修订前','修订后'],['依据','来源','指标','一致性'],['待核','下一步']]
}


def check_documents(folder):
    model=Path(folder)/'business_model.md'
    items=[{'check':'business_model.md:nonempty','layer':'documents',
            'passed':model.is_file() and bool(model.read_text(encoding='utf-8-sig').strip())}]
    for name,groups in SECTIONS.items():
        path=Path(folder)/name
        headings='\n'.join(line for line in path.read_text(encoding='utf-8').splitlines() if re.match(r'^#{1,6}\s',line)) if path.exists() else ''
        for index,terms in enumerate(groups,1):
            items.append({'check':f'{name}:section-{index}','layer':'documents','passed':all(term.casefold() in headings.casefold() for term in terms)})
    return items


def precheck(workspace):
    root=Path(workspace);items=[]
    for name in ['profile_report','adapter_test_report','demo_run']:
        try:validate(name,read_json(root/'artifacts/w04'/f'{name}.json'));good=True
        except Exception:good=False
        items.append({'layer':'schema','passed':good})
    try:load_rules(root/'artifacts/w04/cleaning_rules.yaml');good=True
    except Exception:good=False
    items.append({'layer':'schema','passed':good})
    items+=check_documents(root/'docs/w04')
    # Run the public fixture through the same entry points.
    config=root/'customer/w04/check.json'
    if config.exists():
        try:
            settings=read_json(config)
            fixture=(root/settings['public_fixture']).resolve()
            with tempfile.TemporaryDirectory(prefix='w04-public-check-') as temp:
                result=replay(root,fixture,Path(temp),teacher=False)
            items.extend(result['items'])
        except Exception:items.append({'layer':'execution','passed':False})
    else:items.append({'layer':'execution','passed':False})
    return {'passed':all(i['passed'] for i in items),'items':[{'layer':i['layer'],'passed':i['passed']} for i in items], 'manual_review_required':True}


def _csv(path):
    return [r['raw'] for r in read_inputs(Path(path).parent)[Path(path).name]['rows']]



def normalize_records(rows, table):
    """Notes are exact evidence; only contact restrictions have scored categories."""
    normalized=[]
    for original in rows:
        row=dict(original)
        if 'raw_json' in row:row['raw_json']=json.dumps(json.loads(row['raw_json']),sort_keys=True,ensure_ascii=False)
        if table=='member_notes' and 'category' in row:
            row['category']='触达限制' if row['category']=='触达限制' else '<manual-review>'
        normalized.append(json.dumps({k:str(v) if v is not None else '' for k,v in row.items()},sort_keys=True,ensure_ascii=False))
    return Counter(normalized)


def notes_match(actual, expected):
    """Score text conservation and contact restrictions, not note boundaries."""
    def text(value):return re.sub(r'[,，;；/\s]', '', value)
    def groups(rows):
        out={}
        for row in rows:
            key=tuple(str(row.get(k,'')) for k in ('member_id','source_file','source_row','source_field','raw_text'))
            group=out.setdefault(key,{'text':'','restrictions':'','restriction_parts':[]})
            group['text']+=text(row['note_text'])
            if row['category']=='触达限制':
                group['restrictions']+=text(row['note_text']);group['restriction_parts'].append(text(row['note_text']))
        return out
    a,e=groups(actual),groups(expected)
    if a.keys()!=e.keys():return False
    for key,truth in e.items():
        if a[key]['text']!=truth['text']:return False
        # A merged note may include ordinary prose alongside the restriction.
        # Its extra non-contact text does not impose a machine boundary rule.
        if truth['restrictions']:
            position=0
            for part in truth['restriction_parts']:
                found=a[key]['restrictions'].find(part,position)
                if found<0:return False
                position=found+len(part)
        elif a[key]['restrictions']:return False
    return True


def records_match(actual, expected, table):
    return notes_match(actual,expected) if table=='member_notes' else normalize_records(actual,table)==normalize_records(expected,table)


def replay(workspace,fixture,output,*,teacher=False):
    workspace=Path(workspace).resolve();fixture=Path(fixture).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    config=read_json(workspace/'customer/w04/check.json')
    isolated=output/'input'
    shutil.copytree(fixture/'raw',isolated/'raw')
    if (fixture/'dictionary.md').exists():shutil.copy2(fixture/'dictionary.md',isolated/'dictionary.md')
    expected=read_json(fixture/'expected.json')
    items=[];commands=[]
    def check(name,layer,passed,details=None):
        row={'check':name,'layer':layer,'passed':bool(passed)}
        if teacher:row['details']=details
        items.append(row)
    def execute(key,values):
        tokens=config['commands'][key]
        if not isinstance(tokens,list) or not tokens or not all(isinstance(t,str) for t in tokens):raise ValueError('CHECK_COMMAND_MUST_BE_ARGV')
        args=[token.format(**values) for token in tokens]
        proc=subprocess.run(args,cwd=workspace,capture_output=True,text=True,timeout=600)
        commands.append({'stage':key,'argv':args,'returncode':proc.returncode,'stdout':proc.stdout,'stderr':proc.stderr})
        if proc.returncode:raise ValueError('CUSTOMER_COMMAND_FAILED:'+key)
    fixture_hashes={str(p.relative_to(fixture)):sha(p) for p in fixture.rglob('*') if p.is_file()}
    try:
        vals={'python':sys.executable,'workspace':str(workspace),'source':str(isolated/'raw'),'dictionary':str(isolated/'dictionary.md'),'output':str(output/'profile_report.json'),'run':str(output/'adapt-a'),'first':str(output/'project-a'),'second':str(output/'project-b'),'project':str(output/'project-a'),'data_version':expected['data_version']}
        execute('profile',vals)
        profile=validate('profile_report',read_json(output/'profile_report.json'))
        vals['output']=str(output/'adapt-a');execute('adapt',vals)
        vals.update(output=str(output/'adapt-b'),project=str(output/'project-b'));execute('adapt',vals)
        vals['output']=str(output/'adapter_test_report.json');execute('reconcile',vals)
        report=validate('adapter_test_report',read_json(output/'adapter_test_report.json'))
        check('commands','execution',True)
        raw=read_inputs(fixture/'raw')
        field_report={(f['source_file'],f['field']):f for f in profile['fields']}
        statistics_ok=True
        for name,table in raw.items():
            for field in table['fields']:
                stated=field_report.get((name,field),{})
                values=[r['raw'][field] for r in table['rows']]
                missing=sum(v in ('','NULL','-','无') for v in values)
                statistics_ok &= stated.get('total_count')==len(values) and stated.get('missing_count')==missing
        check('field_statistics','profile',statistics_ok)
        for case in expected.get('anomalies',[]):
            found=any(re.search(case['pattern'],a['pattern'],re.I) and a['evidence'].get('source_file')==case['source_file'] and bool(set(a['evidence'].get('sample_rows',[]))&set(case['rows'])) for a in profile['anomalies'])
            check(case['name'],'profile',found,case if teacher else None)
        runs=[]
        for suffix in ['a','b']:
            base=output/f'adapt-{suffix}';manifest=read_json(base/'cleaned/manifest.json')
            from ..metrics.coverage import validate_coverage_notes
            validate_coverage_notes(manifest)
            cleaned=read_inputs(base/'cleaned');db=database_facts(output/f'project-{suffix}')
            check('coverage-'+suffix,'coverage','coverage_notes' in manifest)
            check('source-hashes-'+suffix,'provenance',all(manifest['source_sha256'].get(name)==sha(fixture/'raw'/name)==sha(base/'raw'/name) for name in raw))
            for name,expected_rows in expected['tables'].items():
                actual=[r['raw'] for r in cleaned[name+'.csv']['rows']]
                check(name+'-'+suffix,'records',records_match(actual,expected_rows,name),{'expected':expected_rows,'actual':actual} if teacher else None)
                import duckdb
                connection=duckdb.connect(str(output/f'project-{suffix}'/'data.duckdb'),read_only=True)
                try:
                    cursor=connection.execute('select * from raw_'+name)
                    columns=[d[0] for d in cursor.description]
                    imported=[dict(zip(columns,row)) for row in cursor.fetchall()]
                finally:connection.close()
                check('imported-'+name+'-'+suffix,'records',records_match(imported,expected_rows,name))
            for row in cleaned['quarantine.csv']['rows']:
                r=row['raw'];original=raw[r['source_file']]['rows'][int(r['source_row'])-1]['raw']
                check('quarantine-source-'+suffix,'provenance',json.loads(r['raw_json'])==original)
            for row in cleaned['member_notes.csv']['rows']:
                r=row['raw'];original=raw[r['source_file']]['rows'][int(r['source_row'])-1]['raw']
                check('note-source-'+suffix,'provenance',r['source_field'] in original and r['raw_text']==original[r['source_field']])
            counts=manifest['record_counts']
            check('actual-counts-'+suffix,'reconciliation',counts==expected['record_counts'],{'expected':expected['record_counts'],'actual':counts} if teacher else None)
            for kind,table in [('member','members'),('order','orders'),('shop','stores'),('card','cards')]:
                c=counts[kind]
                check('balance-'+kind+'-'+suffix,'reconciliation',c['read']==c['accepted']+c['quarantined']+c['deduplicated'] and c['accepted']==db['counts']['raw_'+table])
            actual_orders=[r['raw'] for r in cleaned['orders.csv']['rows']]
            check('money-'+suffix,'reconciliation',sum(int(r['paid_cents']) for r in actual_orders)==db['paid_cents'])
            runs.append({'hashes':{p.name:sha(p) for p in (base/'cleaned').glob('*')},'db':db})
        check('repeat','repeat',runs[0]==runs[1])
        report_counts={r['record_type']:{k:r[k] for k in ['read','accepted','quarantined','deduplicated']} for r in report['record_counts']}
        check('report-truth','reconciliation',report_counts==expected['record_counts'] and report['test_result']['passed'] is True and report['repeat_import']['before']==runs[0]['db']['counts'] and report['repeat_import']['after']==runs[1]['db']['counts'] and report['repeat_import']['first_run_id']!=report['repeat_import']['second_run_id'])
    except Exception as exc:
        check('replay','execution',False,str(exc) if teacher else None)
    after={str(p.relative_to(fixture)):sha(p) for p in fixture.rglob('*') if p.is_file()}
    check('fixture-preserved','provenance',after==fixture_hashes)
    result={'passed':bool(items) and all(i['passed'] for i in items),'items':items if teacher else [{'layer':i['layer'],'passed':i['passed']} for i in items]}
    if teacher:result['commands']=commands
    return result
