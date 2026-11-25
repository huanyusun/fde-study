#!/usr/bin/env python3
"""Direct course entry to shared W05 functions; outputs must use fresh paths."""
import argparse,json,sys,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
def read(p):return json.loads(Path(p).read_text())
def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['export','prepare','bind','resolve','map-records','query','recent','workbook','knowledge-build','knowledge-query','service-call','_query-worker'])
    p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--project');p.add_argument('--index');p.add_argument('--binding');a=p.parse_args();out=Path(a.output)
    if out.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
    if a.command=='export':
        from fde_product.w05.submission import export
        result=export(**read(a.input),output=a.output);print(json.dumps(result,ensure_ascii=False));return
    elif a.command in ['prepare','bind']:
        request=read(a.input)
        if a.command=='prepare':
            from fde_product.w05.prepare import prepare
            result=prepare(**request,output=a.output);print(json.dumps(result,ensure_ascii=False));return
        from fde_product.w05.binding import bind
        result=bind(**request)
    elif a.command=='workbook':
        from fde_product.w05.workbook import read_workbook
        result=read_workbook(a.input)
    elif a.command=='knowledge-build':
        from fde_product.w05.knowledge import build
        result=build(a.input,a.output);print(json.dumps(result,ensure_ascii=False));return
    else:
        request=read(a.input)
        if a.command=='service-call':
            from fde_product.w05.runtime import MemberService
            result=MemberService(a.binding).call(request['name'],request['args'])
        elif a.command=='resolve':
            from fde_product.w05.identity import resolve
            result=resolve(**request)
        elif a.command=='map-records':
            from fde_product.w05.identity import map_records
            result=map_records(**request)
        elif a.command=='recent':
            from fde_product.w05.features import recent_purchase
            import duckdb
            project=Path(a.project);con=duckdb.connect(str(project/'data.duckdb'),read_only=True)
            try:result=recent_purchase(con,read(project/'dataset.json'),request)
            finally:con.close()
        elif a.command=='knowledge-query':
            from fde_product.w05.knowledge import retrieve
            result=retrieve(a.index,**request)
        elif a.command=='_query-worker':
            from fde_product.w05.query import aggregate_query
            result=aggregate_query(a.project,**request)
        else:
            # MetricFlow keeps one project context per process, as in W03.
            process=subprocess.run([sys.executable,str(Path(__file__).resolve()),'_query-worker','--input',a.input,'--output',a.output,'--project',a.project],capture_output=True,text=True,timeout=180)
            if process.returncode:raise ValueError('QUERY_WORKER_FAILED:'+process.stderr[-3000:])
            print(json.dumps(read(a.output),ensure_ascii=False));return
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
