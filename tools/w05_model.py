#!/usr/bin/env python3
"""Small hand-edit path; no model credentials or AI API."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'platform'))
from fde_product.w05.projection import build,query
from fde_product.w05.records import discard_new_output
p=argparse.ArgumentParser();p.add_argument('--schema',required=True);p.add_argument('--data',required=True);p.add_argument('--output',required=True);a=p.parse_args()
out=Path(a.output)
if out.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
try:build(a.schema,json.loads(Path(a.data).read_text()),out)
except BaseException as exc:
    discard_new_output(out,exc);raise
print(json.dumps([query(out/'objects.duckdb',out/'generated/orm.py',r['id']) for r in json.loads(Path(a.data).read_text())['members']],ensure_ascii=False,default=str))
