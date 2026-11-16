#!/usr/bin/env python3
"""Rebuild the chosen snapshot in a new directory with the installed course runtime."""
import argparse,json,sys,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'platform'))
from fde_product.w04 import harness
from fde_product.w04.io import dump,read_inputs


def replay(snapshot,output):
    base=Path(__file__).resolve().parent/'snapshots'/snapshot
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    shutil.copytree(base/'customer',output/'customer');shutil.copytree(base/'materials',output/'materials')
    code=output/'customer/w04/solution.py';materials=output/'materials';raw=materials/'raw'
    tables=read_inputs(raw)
    if snapshot=='start':
        # Course-provided import works without any student implementation.
        harness.load(ROOT/'examples/w03/data',ROOT/'examples/w03/library',output/'prepared-import')
        failures=[]
        for name,fn in [('profile',lambda:harness.profile(raw,materials/'导出字段手册.md',code,output/'profile_report.json','wutong-w04-v1')),('adapt',lambda:harness.adapt(raw,materials/'cleaning_rules.yaml',code,output/'adapter',ROOT/'examples/w03/library',output/'project-a'))]:
            try:fn()
            except NotImplementedError as exc:failures.append(str(exc))
        result={'snapshot':'start','readable_records':{k:len(v['rows']) for k,v in tables.items()},'prepared_import_passed':True,'blank_failures':failures,'passed':len(failures)==2}
    else:
        harness.profile(raw,materials/'导出字段手册.md',code,output/'profile_report.json','wutong-w04-v1')
        harness.adapt(raw,materials/'cleaning_rules.yaml',code,output/'adapter',ROOT/'examples/w03/library',output/'project-a')
        harness.load(output/'adapter/cleaned',ROOT/'examples/w03/library',output/'project-b')
        report=harness.reconcile(output/'adapter',output/'project-a',output/'project-b',code,output/'adapter_test_report.json')
        result={'snapshot':'complete','passed':report['test_result']['passed'],'record_counts':report['record_counts']}
    dump(output/'replay_result.json',result);return result


def output_exists(exc):
    # Each replay writes a new directory; an existing one may hold an earlier or unfinished run.
    print(json.dumps({'status':'error','code':'OUTPUT_EXISTS','reason':'输出目录已存在：'+str(exc.filename)+'。上次运行未完成或已存在，请换一个新的 --output 路径。'},ensure_ascii=False));raise SystemExit(2)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot',choices=['start','complete'],required=True);p.add_argument('--output',required=True);a=p.parse_args()
    try:r=replay(a.snapshot,a.output)
    except FileExistsError as exc:output_exists(exc)
    print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['passed'] else 2)
