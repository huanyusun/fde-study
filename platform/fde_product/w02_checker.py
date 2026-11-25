"""Public W2 evidence precheck. It never executes submitted code or awards a grade."""
import hashlib
from .customer_knowledge import Workspace, load_ontology, review_history, check_run as check_context_run
from .interview_extraction import ROOT, VERSION, CheckError, require, validate, index

CHECKER_VERSION = 'w02-checker-0.1.0'
KINDS = {'definition', 'conflict', 'unknown', 'unimplemented'}
ROLES = {'ROLE-ZHOU', 'ROLE-LIN', 'ROLE-CHEN'}
RUBRIC = {
    'T01': '更换一小段访谈输入后复跑，核对候选变化，并解释自己的程序或配置。',
    'T02': '抽查原话是否支持结论、限定条件与复核理由，不能只检查引用存在。',
    'T03': '解释对象、属性、关系与候选动作的选择；未知和冲突是否保留。',
    'T04': '更换问题或定义后复跑，确认提交版本进入实际调用且回答采用正确。',
    'T05': '审阅四类回答及本人访谈问题，核对修正原因或原结果正确的依据。',
    'D01': '核对三位角色的实际提问是否取得本周相关信息，寒暄不算完成。',
    'D02': '核对至少一组冲突的不同说法、限定条件及向谁取得什么证据。',
    'D03': '审阅纪要及能拍板、能否决、需要知道、真正在意四方面的来源。',
    'D04': '对照已提交的 W1 快照与同编号条目，核对修改理由或无变化的依据。',
}
HINTS = {
    'SOURCE_NOT_FOUND': '补齐引用文件；路径以交付仓库为基准。',
    'HASH_MISMATCH': '恢复该次运行的原始快照；修改后另建运行，勿重写历史。',
    'QUOTE_NOT_FOUND': '回到对应会议及消息，按原始字节中的原话定位摘录。',
    'REVIEW_REQUIRED': '逐条人工核查；拒绝的候选不能进入本体。',
    'REVISION_NOTE_REQUIRED': '改变内容应标 revised 并说明理由，保留初始候选。',
    'SCHEMA_INVALID': '对照公开 Schema 修正字段，不改变业务结论凑格式。',
    'LIVE_EXTRACTION_REQUIRED': '提供自己实际调用模型生成的候选与完整运行记录。',
    'REQUIRED_ROLES_MISSING': '补访缺失角色，保留 W2 live 原文及双方消息。W1 转换不算 W2 访谈。',
    'CONFLICT_REQUIRED': '保留至少一组有原文依据的未决冲突与核实计划。',
    'EXAMPLE_COVERAGE_MISSING': '在独立样例上实际运行缺少的情形；检查报告列出已覆盖类别。',
    'CUSTOMER_RUN_REQUIRED': '用本人访谈问题实际调用，采用与最终提交相同版本的青禾本体。',
    'W1_IDS_MISSING': '本周 fit-gap 保留前周条目编号；修改理由写入既有纪要。',
    'ONTOLOGY_COMPONENT_MISSING': '完成对象、属性、关系及候选动作的表达；数量不作为质量分数。',
}


def gate(item):
    return 'technical' if item.startswith('T') else 'delivery'


class AuditWorkspace(Workspace):
    """Stable reads for a report; manifest binds feedback to the inspected bytes."""
    def __init__(self, root):
        super().__init__(root)
        self.files = {}
        self.size = 0

    def raw(self, rel):
        self.path(rel)
        if rel not in self.files:
            data = super().raw(rel)
            self.size += len(data)
            require(len(self.files) < 5000 and self.size <= 128_000_000, 'SOURCE_BUDGET_EXCEEDED')
            self.files[rel] = data
        return self.files[rel]


def run_contract(ws, path):
    """Common contract only; alternative stacks remain eligible for human replay."""
    run = ws.load(path)
    ws.schema('run_evidence', run)
    for group in ('implementation', 'configuration', 'inputs', 'outputs'):
        for ref in run[group]:
            require(ws.ref(ref['path']) == ref, 'HASH_MISMATCH', ref['path'])
    if run['stage'] == 'context' and run['status'] == 'succeeded':
        require(run['ontology']['file'] in run['inputs'] and run['request'] in run['outputs']
                and run['response'] in run['outputs'], 'RUN_REFERENCE_INVALID', path)
        for ref in (run['request'], run['response']):
            require(ws.raw(ref['path']).strip(), 'EMPTY_DOCUMENT', ref['path'])
        ontology = ws.verify(run['ontology']['file'])
        ws.schema('ontology', ontology)
        require(run['ontology']['artifact_id'] == ontology['artifact_id'] and
                run['ontology']['revision'] == ontology['revision'], 'REFERENCE_INVALID', path)
        # A copied ontology alone is not enough: the linked facts must be an input too.
        facts_inputs = [ref for ref in run['inputs'] if ref['sha256'] == ontology['facts']['sha256']]
        require(bool(facts_inputs), 'RUN_FACTS_REQUIRED', path)
        facts = ws.verify(facts_inputs[0])
        ws.schema('interview_facts', facts)
        require(facts['scope_id'] == ontology['scope_id'], 'SCOPE_MISMATCH', path)
        review_history(ws, facts)
    return run


def legacy_precheck(workspace, *, runs=None, ontology='artifacts/w02/ontology.yaml',
             w1_fit_gap='artifacts/w01/product_fit_gap.json', w2_fit_gap=None):
    ws = AuditWorkspace(workspace)
    issues, completed, runtime = [], [], []

    def attempt(item, label, fn):
        try:
            value = fn()
            completed.append({'item': item, 'check': label})
            return value
        except (CheckError, UnicodeError, KeyError, TypeError, IndexError, StopIteration) as exc:
            code = exc.code if isinstance(exc, CheckError) else 'EVIDENCE_STRUCTURE_INVALID'
            issues.append({'gate': gate(item), 'item': item, 'code': code,
                           'path': (exc.location if isinstance(exc, CheckError) else '') or label,
                           'next_step': HINTS.get(code, '核对所示位置、公开契约与关联版本，再运行预检；语义由助教复核。')})
            return None

    facts_path = 'artifacts/w02/interview_facts.json'
    def facts_check():
        f = ws.load(facts_path)
        review_history(ws, f)
        require(f['scope_id'] == 'qinghe', 'SCOPE_MISMATCH', facts_path)
        return f
    facts = attempt('T02', facts_path, facts_check)

    if facts is not None:
        def origin_check():
            r = run_contract(ws, facts['origin_run']['path'])
            require(r['mode'] == 'live', 'LIVE_EXTRACTION_REQUIRED', facts['origin_run']['path'])
            candidate = ws.verify(next(x for x in r['outputs'] if x['path'].endswith('/candidates.json')))
            require(all(any(ref['sha256'] == s['file']['sha256'] for ref in r['inputs'])
                        for s in candidate['sources']), 'EXTRACTION_INPUT_MISMATCH')
            return r
        attempt('T01', facts['origin_run']['path'], origin_check)

        def roles_check():
            found = set()
            for s in facts['sources']:
                t = ws.verify(s['file'])
                if (t['scope_id'] == 'qinghe' and t['week'] == 2 and t['origin'] == 'live'
                    and t['state'] in ('active', 'ended') and
                    {'user', 'assistant'} <= {m['speaker'] for m in t['messages'] if m['content'].strip()}):
                    found.add(t['role_id'])
            require(ROLES <= found, 'REQUIRED_ROLES_MISSING', ','.join(sorted(ROLES-found)))
            return sorted(found)
        roles = attempt('D01', 'W2 角色覆盖', roles_check)
        attempt('D02', facts_path+'/conflicts', lambda: require(bool(facts['conflicts']), 'CONFLICT_REQUIRED'))
    else:
        roles = None

    def ontology_check():
        o, f = load_ontology(ws, ontology, 'qinghe')
        require(o['facts'] == ws.ref(facts_path), 'SUBMITTED_FACTS_MISMATCH', ontology)
        require(o['links'] and o['candidate_actions'] and any(x['attributes'] for x in o['objects']),
                'ONTOLOGY_COMPONENT_MISSING', ontology)
        return o
    accepted_ontology = attempt('T03', ontology, ontology_check)

    for p in ('docs/w02/interview_notes.md', 'docs/w02/stakeholder_map.md'):
        attempt('D03', p, lambda p=p: require(bool(ws.raw(p).decode('utf-8').strip()), 'EMPTY_DOCUMENT', p))

    def fit_check(path):
        f = ws.load(path)
        validate(Workspace(ROOT).load('contracts/w01/product_fit_gap.schema.json'), f, path)
        index(f['items'])
        return f
    old = attempt('D04', w1_fit_gap, lambda: fit_check(w1_fit_gap))
    if w2_fit_gap is None and ws.path('artifacts/w02/product_fit_gap.json').exists():
        w2_fit_gap = 'artifacts/w02/product_fit_gap.json'
    if w2_fit_gap is not None:
        def continuity():
            current = fit_check(w2_fit_gap)
            require(ws.path(w2_fit_gap) != ws.path(w1_fit_gap), 'W1_SNAPSHOT_OVERWRITTEN', w2_fit_gap)
            if old is not None:
                require({x['id'] for x in old['items']} <= {x['id'] for x in current['items']},
                        'W1_IDS_MISSING', w2_fit_gap)
            return current
        attempt('D04', w2_fit_gap, continuity)

    if runs is None:
        # One level only: snapshots contain earlier run.json files and must not count again.
        folder = ws.path('artifacts/w02/context_runs')
        selected = sorted(p.relative_to(ws.root).as_posix() for p in folder.glob('*/run.json'))
    else:
        selected = list(dict.fromkeys(runs))
    require(len(selected) <= 100, 'RUN_LIMIT_EXCEEDED')
    coverage = {'example': set(), 'customer': set()}
    run_ids = set()
    for path in selected:
        def inspect_run():
            r = run_contract(ws, path)
            require(r['stage'] == 'context', 'CONTEXT_RUN_REQUIRED', path)
            require(r['run_id'] not in run_ids, 'DUPLICATE_RUN_ID', path)
            run_ids.add(r['run_id'])
            known = (r.get('model') or {}).get('adapter_version') == 'w02-knowledge-0.1.0'
            if known:
                check_context_run(ws, path)
            result = {'path': path, 'run_id': r['run_id'], 'mode': r['mode'], 'status': r['status'],
                      'validation': 'adapter_checked' if known else 'common_contract_only',
                      'review': 'pending', 'adopted': False, 'reason': 'failed_or_non_live'}
            if r['status'] != 'succeeded' or r['mode'] != 'live':
                return result
            o = ws.verify(r['ontology']['file'])
            group = {'fictional-library': 'example', 'qinghe': 'customer'}.get(o['scope_id'])
            result['reason'] = 'scope_not_eligible'
            if group is None:
                return result
            result['scope'] = group
            if known:
                settings = [ref for ref in r['configuration'] if ref['path'].endswith('/settings.json')]
                require(len(settings) == 1, 'CONFIGURATION_MISMATCH', path)
                if not ws.verify(settings[0])['include_knowledge']:
                    result['reason'] = 'baseline'; return result
            if group == 'customer' and (accepted_ontology is None or
                    r['ontology']['file']['sha256'] != ws.ref(ontology)['sha256']):
                result['reason'] = 'not_submitted_ontology'; return result
            result.update(adopted=True, reason='structural_coverage_only', kinds=sorted({c['kind'] for c in r['checks']}))
            coverage[group].update(result['kinds'])
            return result
        result = attempt('T04', path, inspect_run)
        if result is not None:
            runtime.append(result)
    attempt('T05', '独立样例四类问题', lambda: require(KINDS <= coverage['example'], 'EXAMPLE_COVERAGE_MISSING'))
    attempt('T05', '本人访谈问题', lambda: require(bool(coverage['customer']), 'CUSTOMER_RUN_REQUIRED'))
    return {
        'checker_version': CHECKER_VERSION, 'contract_version': VERSION,
        'status': 'needs_revision' if issues else 'ready_for_review', 'final_gate': 'not_determined',
        'options': {'runs': selected, 'ontology': ontology, 'w1_fit_gap': w1_fit_gap, 'w2_fit_gap': w2_fit_gap},
        'issues': issues, 'completed': completed, 'runtime': runtime, 'roles': roles,
        'coverage': {k: sorted(v) for k, v in coverage.items()},
        'review_queue': [{'gate': gate(i), 'item': i, 'status': 'pending', 'instruction': text}
                         for i, text in RUBRIC.items()],
        'files': {p: hashlib.sha256(data).hexdigest() for p, data in sorted(ws.files.items())},
        'limits': ['哈希与 live 标签仅核对提交记录，不能证明真实执行或作者身份。',
                   '其他适配器只检查公共契约，需教师核对请求含义并更换输入复跑。',
                   '未选择的历史运行不参与覆盖；保留失败记录，人工审阅修订来路。',
                   'W1 快照需与前周实际提交比对；文件存在不能证明未被覆盖。'],
    }


def precheck(workspace, *, format='auto', **options):
    """New public CLI selects natural; auto preserves historical teacher records."""
    require(format in ('auto','natural','legacy'),'WORKFLOW_INVALID')
    if format=='auto':
        from pathlib import Path
        format='natural' if (Path(workspace)/'customer/w02/knowledge.json').exists() or (Path(workspace)/'docs/w02/business_model.md').exists() else 'legacy'
    if format=='natural':
        from .w02_natural_checker import precheck as natural_precheck
        return natural_precheck(workspace,**options)
    return legacy_precheck(workspace,**options)
