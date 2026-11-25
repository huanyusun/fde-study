"""Public business-record IO and reference-time validity, without matching rules."""
import csv,json,hashlib
from pathlib import Path
from datetime import date

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_csv(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def read_json(p):return json.loads(Path(p).read_text())
def dump(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',newline='\n')
def discard_new_output(out,exc):
 """Remove the output directory a failed run created, so a partial result cannot pass for a finished one.

 Callers refuse an existing output path before starting; FileExistsError means another run owns it."""
 out=Path(out)
 if isinstance(exc,FileExistsError) or not out.is_dir():return
 for log in ['project/build.log','project/validation.log']:
  if (out/log).is_file():exc.add_note('输出目录已删除，'+log+' 末尾如下：\n'+(out/log).read_text(errors='replace')[-3000:])
 import shutil;shutil.rmtree(out,ignore_errors=True)
def write_csv(p,rows,fields):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fields,lineterminator='\n');w.writeheader();w.writerows(rows)
def public_materials(raw):
 raw=Path(raw);manifest=read_json(raw/'manifest.json')
 for name,h in manifest['sha256'].items():
  if sha(raw/name)!=h:raise ValueError('PUBLIC_SOURCE_HASH_MISMATCH:'+name)
 material={'raw_dir':str(raw),'manifest':manifest,'coverage':read_json(raw/'coverage.json'),'reference_date':manifest['reference_date']}
 for name in ['business_basis.csv','migration_records.csv','account_review_records.csv','operational_verification.csv','contact_scope_confirmation.csv','小林工作账_勿扰名单.csv','小林工作账_回访名单.csv','crm_member_export.csv','pos_member_export.csv']:material[name]=read_csv(raw/name)
 return material

def current_records(rows,reference_date,states=('current',)):
 """Only explicit effective replacements retire a record; date alone doesn't."""
 ref=date.fromisoformat(reference_date);ids={r['record_id']:r for r in rows}
 if len(ids)!=len(rows):raise ValueError('DUPLICATE_BUSINESS_RECORD_ID')
 valid=[];ignored=[]
 for n,r in enumerate(rows,1):
  try:effective=date.fromisoformat(r['valid_from'])<=ref<date.fromisoformat(r['valid_until'])
  except (ValueError,KeyError):effective=False
  if r.get('status') in states and effective:valid.append((n,r))
  else:ignored.append({'record_id':r['record_id'],'source_row':n,'reason':'INACTIVE_OR_UNCONFIRMED_RECORD'})
 replacements={r.get('replaces_record_id') for _,r in valid if r.get('replaces_record_id')}
 if not replacements<=set(ids):raise ValueError('REPLACEMENT_TARGET_NOT_FOUND')
 for n,r in valid:
  if r['record_id'] in replacements:ignored.append({'record_id':r['record_id'],'source_row':n,'reason':'EXPLICITLY_REPLACED'})
 return [(n,r) for n,r in valid if r['record_id'] not in replacements],ignored

def verify_basis(record,materials):
 rows=materials.get(record['basis_file'])
 if rows is None:return False
 try:
  number=int(record['basis_row'])
  if number<1:return False
  r=rows[number-1]
 except (ValueError,IndexError):return False
 if '_basis_ids' not in materials:materials['_basis_ids']={b['document_id']:set(b['source_accounts'].split('|')) for b in materials.get('business_basis.csv',[])}
 if record.get('basis_document_id') not in materials['_basis_ids']:return False
 declared={record.get(k) for k in ['source_id','left_source_id','right_source_id','pos_source_id','crm_source_id'] if record.get(k)}
 if not declared<=materials['_basis_ids'][record['basis_document_id']]:return False
 if record['basis_file']=='business_basis.csv':return record['basis_document_id']==r.get('document_id')
 sid=record.get('source_id','')
 source_number=r.get('hy_id',r.get('会员号',r.get('会员编号','')))
 return bool(source_number) and sid=='CRM:'+source_number
