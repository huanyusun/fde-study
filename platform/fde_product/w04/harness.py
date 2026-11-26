"""Run supplied customer hooks; never infer a customer's mapping or counts."""
import importlib.util
import shutil
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from .io import ROOT, dump, read_json, read_inputs, write_csv, sha, load_rules, report


def implementation(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location('w04_customer_solution', path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def new_folder(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def profile(source, dictionary, code, output, data_version):
    source = Path(source).resolve()
    tables = read_inputs(source)
    context = {'source': str(source), 'data_version': data_version, 'dictionary_path': str(Path(dictionary).resolve())}
    result = implementation(code).profile(tables, Path(dictionary).read_text(encoding='utf-8-sig'), context)
    return report(output, 'profile_report', result)


def load(data, library, project):
    command = [sys.executable, str(ROOT / 'tools/w03.py'), 'load', '--data', str(Path(data).resolve()), '--library', str(Path(library).resolve()), '--project', str(Path(project).resolve())]
    process = subprocess.run(command, capture_output=True, text=True, timeout=600)
    if process.returncode:
        raise ValueError('IMPORT_FAILED:' + (process.stdout + process.stderr)[-5000:])
    return read_json(Path(project) / 'dataset.json')


def adapt(source, rules_path, code, output, library, project):
    source = Path(source).resolve()
    rules_path = Path(rules_path).resolve()
    output = Path(output).resolve()
    project = Path(project).resolve()
    if output.exists() or project.exists():
        raise ValueError('NEW_OUTPUT_AND_PROJECT_REQUIRED')
    # No auto-detection of encoding, separators or malformed rows.
    tables = read_inputs(source)
    rules = load_rules(rules_path)
    context = {'source': str(source), 'rules_dir': str(rules_path.parent), 'data_version': rules['data_version']}
    result = implementation(code).adapt(tables, rules, context)
    from ..metrics.engine import TABLES
    from ..metrics.w04_import import OPTIONAL_TABLES, MEMBER_EXTENSIONS
    output = new_folder(output)
    shutil.copytree(source, output / 'raw')
    (output / 'cleaning_rules.yaml').write_bytes(rules_path.read_bytes())
    columns = {**TABLES, **OPTIONAL_TABLES}
    for name, fields in columns.items():
        records = result['tables'][name]
        fields = dict(fields)
        if name == 'members' and records:
            fields.update({k: v for k, v in MEMBER_EXTENSIONS.items() if k in records[0]})
        write_csv(output / 'cleaned' / (name + '.csv'), fields, records)
    # File hashes and serialized row counts are transport facts. Business
    # disposition counts and coverage claims are supplied by the learner.
    manifest = {'id': rules['data_version'], 'contract_version': 'w04-data-0.1.0',
                'coverage': [result['coverage_notes']['time_range']['start'], result['coverage_notes']['time_range']['end_exclusive']],
                'reference_date': result['coverage_notes']['time_range']['end_exclusive'], 'timezone': 'Asia/Shanghai',
                'source_sha256': {p.name: sha(p) for p in sorted(source.glob('*.csv'))},
                'sha256': {p.name: sha(p) for p in sorted((output / 'cleaned').glob('*.csv'))},
                'counts': {k: len(v) for k, v in result['tables'].items()},
                'record_counts': result['record_counts'], 'coverage_notes': result['coverage_notes']}
    dump(output / 'cleaned/manifest.json', manifest)
    dump(output / 'adapter_metadata.json', {k: v for k, v in result.items() if k != 'tables'})
    metadata = load(output / 'cleaned', library, project)
    dump(output / 'import_run.json', {'project': str(project), 'data_version': metadata['id'], 'library_sha256': metadata['library_sha256']})
    return {'output': str(output), 'project': str(project), 'counts': manifest['counts']}


def database_facts(project):
    import duckdb
    project = Path(project)
    con = duckdb.connect(str(project / 'data.duckdb'), read_only=True)
    try:
        names = [row[0] for row in con.execute('show tables').fetchall()]
        counts = {name: con.execute('select count(*) from "' + name + '"').fetchone()[0] for name in names}
        aggregates = con.execute('select count(*),coalesce(sum(paid_cents),0) from raw_orders').fetchone()
        hashes = {}
        for name in names:
            cursor = con.execute('select * from "' + name + '" order by all')
            digest = hashlib.sha256()
            while records := cursor.fetchmany(10000):
                for record in records:
                    digest.update((json.dumps(record, ensure_ascii=False, separators=(',', ':'), default=str) + '\n').encode())
            hashes[name] = digest.hexdigest()
        return {'counts': counts, 'order_count': aggregates[0], 'paid_cents': aggregates[1], 'table_sha256': hashes}
    finally:
        con.close()


def reconcile(run, first, second, code, output):
    run = Path(run)
    payload = {'source': read_inputs(run / 'raw'), 'cleaned': read_inputs(run / 'cleaned'),
               'metadata': read_json(run / 'adapter_metadata.json'), 'manifest': read_json(run / 'cleaned/manifest.json'),
               'first': database_facts(first), 'second': database_facts(second),
               'first_run_id': str(Path(first).resolve()), 'second_run_id': str(Path(second).resolve())}
    result = implementation(code).reconcile(payload)
    return report(output, 'adapter_test_report', result)
