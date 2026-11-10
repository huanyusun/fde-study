"""Deterministic native configuration, declared grain, and query-target checks."""
import re
from pathlib import Path
import duckdb
import yaml
from .common import read, dump

REF = re.compile(r"^ref\(['\"]([a-z][a-z0-9_]*)['\"]\)$")

def relation(sm):
    match = REF.fullmatch(sm['model'])
    if not match:
        raise ValueError('SEMANTIC_MODEL_REF_REQUIRED:' + sm['name'])
    return '"' + match[1] + '"'

def expression(item):
    return str(item.get('expr', item['name']))

def grain_check(project):
    p = Path(project)
    models = yaml.safe_load((p/'models/metrics.yml').read_text())['semantic_models']
    declarations = read(p/'grain_contract.json') if (p/'grain_contract.json').exists() else {}
    con = duckdb.connect(str(p/'data.duckdb'))
    items = []
    providers = {}
    for sm in models:
        for ent in sm.get('entities', []):
            if ent['type'] in ('primary', 'unique'):
                providers.setdefault(ent['name'], []).append((sm, ent))
    try:
        for sm in models:
            table = relation(sm)
            keys = [expression(e) for e in sm.get('entities', []) if e['type'] in ('primary', 'unique')]
            composite = declarations.get(sm['name'], [])
            if sm.get('primary_entity') and not keys and not composite:
                items.append({'model': sm['name'], 'check': 'declared_grain', 'passed': False, 'reason': 'PRIMARY_ENTITY_REQUIRES_GRAIN_COLUMNS'})
            for columns in {tuple(x) for x in [[k] for k in keys] + ([composite] if composite else [])}:
                null_condition = ' or '.join(f'({x}) is null' for x in columns)
                row = con.execute(f"select count(*), count(*) filter (where {null_condition}), count(distinct ({', '.join(columns)})) filter (where not ({null_condition})) from {table}").fetchone()
                items.append({'model': sm['name'], 'check': 'primary_key', 'columns': columns, 'rows': row[0], 'null_rows': row[1], 'duplicate_rows': row[0]-row[1]-row[2], 'passed': row[1] == 0 and row[0] == row[2]})
            for ent in sm.get('entities', []):
                if ent['type'] != 'foreign':
                    continue
                targets = providers.get(ent['name'], [])
                if len(targets) != 1:
                    items.append({'model': sm['name'], 'entity': ent['name'], 'check': 'foreign_key', 'passed': False, 'reason': 'FOREIGN_TARGET_MISSING_OR_AMBIGUOUS'})
                    continue
                target, key = targets[0]
                row = con.execute(f"select count(*) from (select {expression(ent)} as k from {table}) s left join (select distinct {expression(key)} as k from {relation(target)}) t on s.k=t.k where t.k is null").fetchone()
                items.append({'model': sm['name'], 'entity': ent['name'], 'target': target['name'], 'check': 'foreign_key', 'unmatched_rows': row[0], 'passed': row[0] == 0})
    finally:
        con.close()
    result = {'passed': all(x['passed'] for x in items), 'items': items}
    dump(p/'grain_check.json', result)
    return result

def inspect_project(project):
    """Run in a fresh process: dbt / MetricFlow maintain process-global state."""
    from dbt_metricflow.cli.cli_configuration import CLIConfiguration
    from dbt_metricflow.cli.dbt_connectors.dbt_config_accessor import dbtArtifacts
    from metricflow_semantic_interfaces.validations.semantic_manifest_validator import SemanticManifestValidator
    from metricflow.engine.metricflow_engine import MetricFlowQueryRequest
    p = Path(project).resolve()
    failures = []
    try:
        cfg = CLIConfiguration()
        cfg.setup(dbt_profiles_path=p, dbt_project_path=p)
        manifest = dbtArtifacts.build_semantic_manifest_from_dbt_project_root(project_root=p)
        validation = SemanticManifestValidator(max_workers=1).validate_semantic_manifest(manifest)
        if validation.has_blocking_issues:
            raise ValueError(str(validation))
        metric_names = [m.name for m in cfg.mf.list_metrics()]
        # Compile every metric against the actual warehouse. This catches expressions
        # that parse but refer to columns absent from the loaded relation.
        for name in metric_names:
            req = MetricFlowQueryRequest.create(metric_names=[name])
            sql = cfg.mf.explain(mf_request=req).sql_statement.without_descriptions.sql
            con = duckdb.connect(str(p/'data.duckdb'))
            try:
                con.execute('explain ' + sql)
            finally:
                con.close()
        dump(p/'metricflow_check.json', {'passed': True, 'metrics_compiled': metric_names, 'validator': 'SemanticManifestValidator; native explain + DuckDB EXPLAIN'})
    except Exception as exc:
        dump(p/'metricflow_check.json', {'passed': False, 'reason': str(exc)})
        failures.append('METRICFLOW_CONFIG_INVALID')
        cfg = None
    try:
        if not grain_check(p)['passed']:
            failures.append('GRAIN_CHECK_FAILED')
    except Exception as exc:
        dump(p/'grain_check.json', {'passed': False, 'reason': str(exc)})
        failures.append('GRAIN_CHECK_FAILED')
    try:
        targets = read(p/'dimension_targets.json')
        actual = set()
        per_metric = {}
        if cfg is not None:
            for name in metric_names:
                dimensions = cfg.mf.list_group_bys(metric_names=[name], include_derived_time_granularities=True)
                names = {getattr(d, 'dunder_name', None) or d.name for d in dimensions}
                resolved = {}
                for target in targets:
                    key = target['id']
                    candidates = [n for n in names if n == key or n.endswith('__'+key)]
                    if key in names:resolved[key] = key
                    elif len(candidates) == 1:resolved[key] = candidates[0]
                per_metric[name] = resolved
                actual.update(resolved)
        pending = {x['dimension_id']: x for x in read(p/'unresolved.json') if x.get('dimension_id') and x.get('missing_facts') and x.get('reason')}
        items = [{'id': t['id'], 'queryable': t['id'] in actual, 'unresolved': pending.get(t['id']), 'passed': t['id'] in actual or t['id'] in pending} for t in targets]
        report = {'passed': all(x['passed'] for x in items), 'items': items, 'available': sorted(actual & {t['id'] for t in targets}), 'per_metric': per_metric}
        dump(p/'dimension_check.json', report)
        if not report['passed']:
            failures.append('DIMENSION_TARGET_COVERAGE_FAILED')
        if cfg is not None:
            build_dimension_manifest(p, report)
    except Exception as exc:
        dump(p/'dimension_check.json', {'passed': False, 'reason': str(exc)})
        failures.append('DIMENSION_TARGET_COVERAGE_FAILED')
    dump(p/'validation.json', {'passed': not failures, 'failures': failures})
    return {'passed': not failures, 'failures': failures}

def build_dimension_manifest(project, report):
    p = Path(project)
    models = yaml.safe_load((p/'models/metrics.yml').read_text())['semantic_models']
    bindings = {}
    for sm in models:
        primaries = [e['name'] for e in sm.get('entities', []) if e['type'] in ('primary', 'unique')]
        for ent in sm.get('entities', []):
            if ent['type'] in ('primary', 'unique'):
                bindings[ent['name']] = {'kind': 'entity', 'model': sm['name'], 'relation': relation(sm), 'expression': expression(ent)}
        for primary in primaries:
            for dim in sm.get('dimensions', []):
                bindings[primary+'__'+dim['name']] = {'kind': 'dimension', 'model': sm['name'], 'relation': relation(sm), 'expression': expression(dim)}
    entries = {}
    con = duckdb.connect(str(p/'data.duckdb'))
    try:
        for target in read(p/'dimension_targets.json'):
            key = target['id']
            if key not in report['available']:
                continue
            if key.startswith('metric_time__'):
                entries[key] = {**target, 'kind': 'time', 'values': []}
                continue
            binding = bindings.get(key)
            if binding is None:
                raise ValueError('DIMENSION_BINDING_MISSING:' + key)
            values = con.execute(f"select distinct {binding['expression']} as v from {binding['relation']} where ({binding['expression']}) is not null order by 1").fetchall()
            entries[key] = {**target, **binding, 'values': [str(r[0]) for r in values]}
    finally:
        con.close()
    dump(p/'dimensions.json', {'dimensions': entries, 'per_metric': report['per_metric']})
