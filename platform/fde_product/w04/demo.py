"""Export stored runtime evidence, with learner-supplied bad-case judgements."""
from pathlib import Path
from copy import deepcopy
from .io import read_json, dump, report
from ..metrics.coverage import validate_coverage_notes


def run(project, question, output, answer_prompt=None, model=None):
    from ..metrics.agent import MetricsAgent
    agent = MetricsAgent(project, out=output, model=model, answer_prompt=answer_prompt)
    if 'coverage_notes' not in agent.data:
        raise ValueError('DATASET_COVERAGE_REQUIRED')
    validate_coverage_notes(agent.data)
    return agent.ask(question)


def evidence(folder, bad_case, bad_case_reason):
    folder = Path(folder)
    result = read_json(folder / 'result.json')
    dataset = read_json(folder / 'dataset_snapshot.json')
    if 'coverage_notes' not in dataset:
        raise ValueError('RUNTIME_COVERAGE_SNAPSHOT_REQUIRED')
    validate_coverage_notes(dataset)
    query_path = folder / 'query_result.json'
    query = read_json(query_path) if query_path.exists() else result
    queries = []
    if query.get('sql'):
        queries.append({'sql': query['sql'], 'result': deepcopy(query), 'error': None if query.get('status') == 'ok' else str(query.get('reason', query.get('code', 'query failed')))})
    status = 'executed' if queries and query.get('status') == 'ok' else ('failed' if result.get('status') == 'error' or query.get('status') == 'error' else 'not_executed')
    # Keep the actual fallback response on failures, including a query that
    # succeeded before answer generation failed. Never invent SQL or answers.
    answer = result.get('answer') or result.get('reason')
    if not answer:
        raise ValueError('RUNTIME_ANSWER_REQUIRED')
    value = {'question': result['question'], 'agent_answer': answer, 'query_status': status,
             'actual_queries': queries, 'coverage_notes': deepcopy(dataset['coverage_notes']),
             'bad_case': bad_case, 'bad_case_reason': bad_case_reason}
    return value, dataset


def export(annotation, output):
    path = Path(annotation).resolve()
    config = read_json(path)
    runs, datasets = [], []
    for item in config['runs']:
        def resolve(value):
            return path.parent / value
        current, dataset = evidence(resolve(item['run_path']), item['bad_case'], item['bad_case_reason'])
        datasets.append(dataset)
        if 'tuning' in item:
            tuning = item['tuning']
            before, old = evidence(resolve(tuning['before_run_path']), tuning['before_bad_case'], tuning['before_bad_case_reason'])
            datasets.append(old)
            if before.pop('question') != current['question']:
                raise ValueError('TUNING_QUESTION_MISMATCH')
            current['tuning'] = {'before': before, **{key: tuning[key] for key in ['change_location', 'change', 'reason']}}
        runs.append(current)
    # The schema has document-level version strings. Preserve every actual
    # version rather than relabelling older runs with the newest version.
    data_versions = list(dict.fromkeys(d['id'] for d in datasets))
    library_versions = list(dict.fromkeys(d['library_sha256'] for d in datasets))
    result = {'contract_version': 'w04-0.3.0', 'selected_chain': config['selected_chain'],
              'data_version': '；'.join(data_versions), 'query_library_version': '；'.join(library_versions), 'runs': runs}
    return report(output, 'demo_run', result)
