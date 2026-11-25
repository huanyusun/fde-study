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
        shutil.copytree(ROOT / 'customer/w04', workspace / 'customer/w04')
        documents = workspace / 'docs/w04'
        documents.mkdir(parents=True, exist_ok=True)
        for template in (ROOT / 'templates/w04/documents').iterdir():
            target = documents / template.name
            if template.is_file() and not target.exists():
                shutil.copy2(template, target)
        result = {'workspace':str(workspace), 'next_step':'将 W03 business_model.md 或 checkpoint 中的 w03-reference/business_model.md 复制到 docs/w04/business_model.md，保留原提交；按证据核对并在 model_changes.md 记录结果。'}
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
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 2 if result.get('passed') is False or result.get('status')=='error' else 0


if __name__ == '__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'error','code':type(exc).__name__,'reason':str(exc)},ensure_ascii=False));raise SystemExit(2)
