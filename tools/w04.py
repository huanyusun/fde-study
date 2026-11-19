#!/usr/bin/env python3
"""W04 customer-code harness and runtime evidence export."""
import argparse
import json
import shutil
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'platform'), str(ROOT)]
from fde_product.w04 import harness
from fde_product.w04.io import read_inputs, dump


SCHEMA_FILES = ['artifacts/w04/profile_report.json', 'artifacts/w04/adapter_test_report.json',
                'artifacts/w04/demo_run.json', 'artifacts/w04/cleaning_rules.yaml']


def summary_lines(workspace, result):
    """Chinese recap for a learner; the JSON above stays the full result."""
    if result['passed']:
        return ['预检结果：结构可供审阅，这不代表作业通过']
    from fde_product.w04.checker import check_documents
    # The public result names layers only; its first four items are these files, in this order.
    rows = [f'{name} 缺文件或格式不对：用对应的 tools/w04.py 命令重新生成。'
            for name, item in zip(SCHEMA_FILES, result['items']) if not item['passed']]
    documents = {}
    for item in check_documents(Path(workspace) / 'docs/w04'):
        if not item['passed']:
            name = item['check'].partition(':')[0]
            documents[name] = documents.get(name, 0) + 1
    for name, count in documents.items():
        if name == 'business_model.md':
            rows.append('docs/w04/business_model.md 缺文件或内容为空：运行 tools/w04.py init 后按提示承接 W03 业务模型。')
        elif not (Path(workspace) / 'docs/w04' / name).is_file():
            rows.append(f'缺 docs/w04/{name}：运行 tools/w04.py init 补模板。')
        else:
            rows.append(f'docs/w04/{name} 有 {count} 处小节标题缺失：对照 templates/w04/documents/{name}，保留模板的小节标题。')
    execution = [item for item in result['items'] if item['layer'] == 'execution' and not item['passed']]
    if execution:
        names = sorted({name for item in execution for name in item.get('differences', [])})
        rows.append(f'公开样例重放有 {len(execution)} 处未通过' + (f"（有差异的文件：{'、'.join(names)}）" if names else '')
                    + '：确认 customer/w04/check.json 存在，再修好自己的清洗代码后重跑。')
    return [f'预检结果：还差 {len(rows)} 项，暂不能提交', *[f'{i}. {text}' for i, text in enumerate(rows, 1)],
            '全部项和说明见上方 JSON。']


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('init');p.add_argument('--workspace', required=True)
    p = commands.add_parser('read');p.add_argument('--source', required=True);p.add_argument('--encoding', default='utf-8-sig')
    p = commands.add_parser('profile')
    for arg in ['source','dictionary','code','output','data-version']:p.add_argument('--' + arg, required=True)
    p = commands.add_parser('adapt')
    for arg in ['source','rules','code','output','library','project']:p.add_argument('--' + arg, required=True)
    p = commands.add_parser('load')
    for arg in ['data','library','project']:p.add_argument('--' + arg, required=True)
    p = commands.add_parser('reconcile')
    for arg in ['run','first','second','code','output']:p.add_argument('--' + arg, required=True)
    p = commands.add_parser('run-demo')
    for arg in ['project','question','output']:p.add_argument('--' + arg, required=True)
    p.add_argument('--answer-prompt')
    p = commands.add_parser('export-demo');p.add_argument('--annotation',required=True);p.add_argument('--output',required=True)
    p = commands.add_parser('check');p.add_argument('--workspace',required=True);p.add_argument('--output',required=True)
    args = parser.parse_args()
    if args.command == 'init':
        workspace = Path(args.workspace).resolve()
        added = []
        # Existing files are the learner's work: only missing files are added.
        pairs = [] if workspace == ROOT else [(ROOT / 'customer/w04', workspace / 'customer/w04')]
        pairs.append((ROOT / 'templates/w04/documents', workspace / 'docs/w04'))
        for source, folder in pairs:
            folder.mkdir(parents=True, exist_ok=True)
            for template in sorted(source.iterdir()):
                target = folder / template.name
                if template.is_file() and not target.exists():
                    shutil.copy2(template, target);added.append(str(target.relative_to(workspace)))
        result = {'workspace':str(workspace), 'added':added, 'next_step':'将 W03 business_model.md 或 checkpoint 中的 w03-reference/business_model.md 复制到 docs/w04/business_model.md，保留原提交；按证据核对并在 model_changes.md 记录结果。'}
    elif args.command == 'read':
        result = {name:{'fields':table['fields'],'records':len(table['rows'])} for name,table in read_inputs(args.source,encoding=args.encoding).items()}
    elif args.command == 'profile':result=harness.profile(args.source,args.dictionary,args.code,args.output,args.data_version)
    elif args.command == 'adapt':result=harness.adapt(args.source,args.rules,args.code,args.output,args.library,args.project)
    elif args.command == 'load':result=harness.load(args.data,args.library,args.project)
    elif args.command == 'reconcile':result=harness.reconcile(args.run,args.first,args.second,args.code,args.output)
    elif args.command == 'run-demo':
        from fde_product.w04.demo import run
        result=run(args.project,args.question,args.output,args.answer_prompt)
    elif args.command == 'export-demo':
        from fde_product.w04.demo import export
        result=export(args.annotation,args.output)
    else:
        from fde_product.w04.checker import precheck
        result=precheck(args.workspace);dump(args.output,result)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
    if args.command == 'check':
        try:
            print('\n'.join(summary_lines(args.workspace, result)), file=sys.stderr)
        except Exception:
            pass  # The recap must never change the result.
    return 2 if result.get('passed') is False or result.get('status')=='error' else 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'error','code':type(exc).__name__,'reason':str(exc)},ensure_ascii=False));raise SystemExit(2)
