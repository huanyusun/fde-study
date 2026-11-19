import json,sys
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from fde_product.w04.checker import precheck,check_documents,replay
from fde_product.w04.io import dump


def test_blank_submission_fails_by_layer_without_hidden_values(tmp_path):
    result=precheck(tmp_path)
    assert result['passed'] is False
    assert all(set(item)=={'layer','passed'} for item in result['items'])
    assert {'schema','execution','documents'} <= {item['layer'] for item in result['items']}


def test_documents_only_check_headings_not_quality(tmp_path):
    import shutil
    shutil.copytree(ROOT/'templates/w04/documents',tmp_path/'docs')
    (tmp_path/'docs/business_model.md').write_text('自然语言业务模型，沿用原章节。')
    checks=check_documents(tmp_path/'docs')
    assert all(item['passed'] for item in checks)
    # Empty section bodies pass this structural check; judgement stays manual.
    (tmp_path/'docs/demo_plan.md').write_text('# demo\n\n没有章节。\n')
    assert any(not item['passed'] for item in check_documents(tmp_path/'docs'))


def test_customer_code_actually_runs_and_errors_are_redacted(tmp_path):
    root=tmp_path/'work';fixture=tmp_path/'fixture';fixture.mkdir();(fixture/'raw').mkdir()
    dump(fixture/'expected.json',{'data_version':'test'})
    dump(root/'customer/w04/check.json',{'commands':{'profile':[sys.executable,'-c',"raise ValueError('DO_NOT_DISCLOSE_ORACLE')"]}})
    result=replay(root,fixture,tmp_path/'public',teacher=False)
    assert not result['passed'] and 'DO_NOT_DISCLOSE_ORACLE' not in json.dumps(result)
    private=replay(root,fixture,tmp_path/'private',teacher=True)
    assert not private['passed'] and 'DO_NOT_DISCLOSE_ORACLE' in json.dumps(private)


@pytest.mark.parametrize('missing', ['字典过时', '映射错误', '数据暂缺'])
def test_dictionary_difference_categories_must_be_in_headings(tmp_path, missing):
    import shutil
    shutil.copytree(ROOT/'templates/w04/documents', tmp_path/'docs')
    path=tmp_path/'docs/data_diagnosis.md'
    lines=path.read_text().splitlines()
    path.write_text('\n'.join(line.replace(missing, '') if line.startswith('#') else line for line in lines)+'\n')
    # The category still appears in the table, but bodies cannot satisfy headings.
    assert missing in path.read_text()
    result=next(item for item in check_documents(tmp_path/'docs') if item['check']=='data_diagnosis.md:section-2')
    assert result['passed'] is False


def test_dictionary_difference_judgments_remain_manual(tmp_path):
    import shutil
    shutil.copytree(ROOT/'templates/w04/documents', tmp_path/'docs')
    path=tmp_path/'docs/data_diagnosis.md'
    path.write_text('\n'.join(line for line in path.read_text().splitlines() if line.startswith('#'))+'\n')
    (tmp_path/'docs/business_model.md').write_text('自然语言业务模型，沿用原章节。')
    assert all(item['passed'] for item in check_documents(tmp_path/'docs'))


@pytest.mark.parametrize('body', [None, '', '  \n\t'])
def test_missing_or_blank_business_model_fails(tmp_path, body):
    import shutil
    shutil.copytree(ROOT/'templates/w04/documents', tmp_path/'docs')
    if body is not None:
        (tmp_path/'docs/business_model.md').write_text(body)
    checks = check_documents(tmp_path/'docs')
    assert next(i for i in checks if i['check']=='business_model.md:nonempty')['passed'] is False


def test_model_review_does_not_require_changes_or_machine_structure(tmp_path):
    import shutil
    shutil.copytree(ROOT/'templates/w04/documents', tmp_path/'docs')
    (tmp_path/'docs/business_model.md').write_text('自由格式的完整模型由人工核查，不限定标题。')
    path=tmp_path/'docs/model_changes.md'
    path.write_text('\n'.join(line for line in path.read_text().splitlines() if line.startswith('#'))+'\n核对后无需修改；依据由人工核查。\n')
    assert all(i['passed'] for i in check_documents(tmp_path/'docs'))
    path.unlink()
    assert any(not i['passed'] for i in check_documents(tmp_path/'docs') if i['check'].startswith('model_changes.md:'))


def test_init_preserves_existing_model_and_revision_notes(tmp_path):
    import subprocess
    docs=tmp_path/'docs/w04'
    docs.mkdir(parents=True)
    model=docs/'business_model.md';model.write_text('自己的 W03 模型副本')
    changes=docs/'model_changes.md';changes.write_text('已写入的核对记录')
    result=subprocess.run([sys.executable,str(ROOT/'tools/w04.py'),'init','--workspace',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert model.read_text() == '自己的 W03 模型副本'
    assert changes.read_text() == '已写入的核对记录'
    assert (docs/'metric_changes.md').is_file()
    assert 'business_model.md' in json.loads(result.stdout)['next_step']


def _project_copy(tmp_path):
    import shutil
    project=tmp_path/'project'
    for part in ['tools/w04.py','platform/fde_product','customer/w04','templates/w04']:
        source=ROOT/part;(project/part).parent.mkdir(parents=True,exist_ok=True)
        (shutil.copytree if source.is_dir() else shutil.copy2)(source,project/part,**({'ignore':shutil.ignore_patterns('__pycache__')} if source.is_dir() else {}))
    return project


def test_init_in_project_root_keeps_code_and_can_repeat(tmp_path):
    import subprocess
    project=_project_copy(tmp_path)
    solution=project/'customer/w04/solution.py';solution.write_text('# 自己的实现')
    for attempt in range(2):
        result=subprocess.run([sys.executable,str(project/'tools/w04.py'),'init','--workspace','.'],cwd=project,capture_output=True,text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        added=json.loads(result.stdout)['added']
        assert all(not name.startswith('customer/') for name in added)
        assert (project/'docs/w04/model_changes.md').is_file()
    assert added == []
    assert solution.read_text() == '# 自己的实现'


def test_init_adds_only_missing_customer_files(tmp_path):
    import subprocess
    solution=tmp_path/'customer/w04/solution.py';solution.parent.mkdir(parents=True);solution.write_text('# 已有实现')
    result=subprocess.run([sys.executable,str(ROOT/'tools/w04.py'),'init','--workspace',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert solution.read_text() == '# 已有实现'
    assert (tmp_path/'customer/w04/check.json').is_file()
    assert 'customer/w04/solution.py' not in json.loads(result.stdout)['added']


def test_check_commands_resolve_course_tools_from_project_root(tmp_path):
    shipped=json.loads((ROOT/'customer/w04/check.json').read_text())
    assert all(argv[1]=='{root}/tools/w04.py' for argv in shipped['commands'].values())
    root=tmp_path/'work';fixture=tmp_path/'fixture';(fixture/'raw').mkdir(parents=True)
    dump(fixture/'expected.json',{'data_version':'test'})
    script='import sys;open(sys.argv[1],"w").write(sys.argv[2]);raise SystemExit(1)'
    dump(root/'customer/w04/check.json',{'commands':{'profile':[sys.executable,'-c',script,str(tmp_path/'seen.txt'),'{root}']}})
    replay(root,fixture,tmp_path/'public',teacher=False)
    assert (tmp_path/'seen.txt').read_text() == str(ROOT)


def test_failed_adapt_leaves_reason_and_rerun_names_existing_path(tmp_path):
    from fde_product.w04 import harness
    code=tmp_path/'solution.py';code.write_text("def adapt(tables, rules, context):\n    return {'tables': {}}\n")
    args=[ROOT/'examples/w04/public-check/raw',ROOT/'contracts/w04/cleaning_rules.valid.yaml',code,tmp_path/'run-01/adapt',ROOT/'examples/w03/library',tmp_path/'run-01/project']
    with pytest.raises(KeyError):harness.adapt(*args)
    failure=json.loads((tmp_path/'run-01/adapt/import_failed.json').read_text())
    assert failure['stage']=='write' and failure['project_created'] is False
    with pytest.raises(ValueError) as rerun:harness.adapt(*args)
    assert str(tmp_path/'run-01/adapt') in str(rerun.value) and '请换新的版本路径' in str(rerun.value)


@pytest.mark.parametrize('script,arguments', [('replay.py',['--snapshot','start']),('counterexamples.py',['--raw','raw','--cleaned','cleaned'])])
def test_wutong_scripts_report_existing_output_in_one_line(tmp_path, script, arguments):
    import subprocess
    result=subprocess.run([sys.executable,str(ROOT/'examples/w04/wutong'/script),*arguments,'--output',str(tmp_path)],capture_output=True,text=True)
    assert result.returncode == 2 and 'Traceback' not in result.stderr
    message=json.loads(result.stdout)
    assert message['code']=='OUTPUT_EXISTS' and str(tmp_path) in message['reason']
