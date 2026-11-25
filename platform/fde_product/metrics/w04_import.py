"""Optional W04 input contract; W03's four-table contract remains unchanged."""
import csv
import json
import re
from pathlib import Path

from .common import digest

MEMBER_EXTENSIONS = {'account_status':'VARCHAR','registered_channel':'VARCHAR','created_at':'DATE'}
OPTIONAL_TABLES = {
    'member_tags': {'member_id':'VARCHAR','tag':'VARCHAR'},
    'member_notes': {'member_id':'VARCHAR','source_file':'VARCHAR','source_row':'BIGINT','source_field':'VARCHAR','raw_text':'VARCHAR','note_text':'VARCHAR','category':'VARCHAR'},
    'quarantine': {'record_type':'VARCHAR','source_file':'VARCHAR','source_row':'BIGINT','reason_code':'VARCHAR','raw_json':'VARCHAR'},
}
REASON_CODES = ['UNLINKED_ACCOUNT','REFUND_EXCEEDS_PAID','UNSUPPORTED_CARD_TYPE','INVALID_DATE','DUPLICATE_PRIMARY_KEY']
RECORD_TABLES = {'member':'members','order':'orders','card':'cards','shop':'stores'}


def header(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return next(csv.reader(f), [])


def is_w04_data(data, manifest):
    data=Path(data)
    return (manifest.get('contract_version')=='w04-data-0.1.0'
            or bool(set(header(data/'members.csv')) & set(MEMBER_EXTENSIONS))
            or any((data/(name+'.csv')).exists() for name in OPTIONAL_TABLES))


def fail_if(con, sql, code):
    if con.execute(sql).fetchone()[0]: raise ValueError(code)


def import_w04(con, data, manifest, base_tables):
    """Import already-cleaned inputs. Reject errors; never clean client records."""
    data=Path(data)
    hashes=manifest.get('source_sha256')
    counts=manifest.get('record_counts')
    if not isinstance(hashes,dict) or not hashes or any(not isinstance(k,str) or not k or Path(k).name!=k or '/' in k or '\\' in k or not re.fullmatch(r'[0-9a-f]{64}',str(v)) for k,v in hashes.items()):
        raise ValueError('SOURCE_HASHES_INVALID')
    if not isinstance(counts,dict) or set(counts)!=set(RECORD_TABLES): raise ValueError('RECORD_COUNTS_INVALID')
    present={name:cols for name,cols in OPTIONAL_TABLES.items() if (data/(name+'.csv')).exists()}
    tables={name:dict(cols) for name,cols in base_tables.items()}
    actual_header=header(data/'members.csv')
    for key,typ in MEMBER_EXTENSIONS.items():
        if key in actual_header: tables['members'][key]=typ
    tables.update(present)
    for name,columns in tables.items():
        path=data/(name+'.csv')
        if manifest.get('sha256',{}).get(path.name)!=digest(path): raise ValueError('DATA_HASH_MISMATCH:'+name)
        cols=header(path)
        if set(cols)!=set(columns) or len(cols)!=len(columns): raise ValueError('CSV_COLUMNS_MISMATCH:'+name)
        # DuckDB casts 1.5 to BIGINT by rounding; source positions must be
        # exact CSV record numbers, so validate their textual representation.
        if name in ('member_notes','quarantine'):
            with path.open(encoding='utf-8-sig',newline='') as f:
                for row in csv.DictReader(f):
                    if name=='member_notes' and (not isinstance(row.get('source_field'),str) or not row['source_field'].strip()):
                        raise ValueError('INVALID_MEMBER_NOTE')
                    if not re.fullmatch(r'[0-9]+',row['source_row']) or int(row['source_row'])<1:
                        raise ValueError('INVALID_SOURCE_ROW:'+name)
        types='{'+','.join("'"+k+"':'"+v+"'" for k,v in columns.items())+'}'
        con.execute('create table raw_'+name+' as select * from read_csv(?, header=true, types='+types+')',[str(path)])
        n=con.execute('select count(*) from raw_'+name).fetchone()[0]
        expected=manifest.get('counts',{}).get(name)
        if type(expected) is not int or n!=expected: raise ValueError('DATA_COUNT_MISMATCH:'+name)
    for name in OPTIONAL_TABLES:
        if name not in present and (manifest.get('counts',{}).get(name,0)!=0 or name+'.csv' in manifest.get('sha256',{})): raise ValueError('OPTIONAL_FILE_MISSING:'+name)
    keys={'members':['member_id'],'orders':['order_id'],'stores':['store_id'],'cards':['card_id'],
          'member_tags':['member_id','tag'],'member_notes':['member_id','source_file','source_row','source_field','note_text'],
          'quarantine':['source_file','source_row']}
    for name in tables:
        cols=keys[name]; null=' or '.join(f'{c} is null' for c in cols)
        fail_if(con,f'select count(*) from raw_{name} where {null}','DUPLICATE_OR_NULL_KEY:'+name)
        fail_if(con,f'select count(*) from (select {",".join(cols)},count(*) n from raw_{name} group by {",".join(cols)} having n>1)','DUPLICATE_OR_NULL_KEY:'+name)
    for name in ['orders','cards']+[n for n in ['member_tags','member_notes'] if n in present]:
        fail_if(con,f'select count(*) from raw_{name} x left join raw_members m using(member_id) where m.member_id is null','UNLINKED_ACCOUNT:'+name)
    if 'account_status' in tables['members']:
        fail_if(con,"select count(*) from raw_members where account_status is null or account_status not in ('活跃','冻结','注销','未激活')",'INVALID_ACCOUNT_STATUS')
    if 'registered_channel' in tables['members']:
        fail_if(con,"select count(*) from raw_members where registered_channel is null or registered_channel not in ('门店','小程序','商城','系统导入')",'INVALID_REGISTERED_CHANNEL')
    if 'created_at' in tables['members']:
        fail_if(con,'select count(*) from raw_members where created_at is null','INVALID_CREATED_AT')
    fail_if(con,"select count(*) from raw_orders where channel is null or channel not in ('门店','小程序','商城')",'INVALID_ORDER_CHANNEL')
    if 'member_tags' in present:
        fail_if(con,"select count(*) from raw_member_tags where trim(tag)=''",'EMPTY_TAG')
    if 'member_notes' in present:
        fail_if(con,"select count(*) from raw_member_notes where source_row<1 or source_field is null or trim(source_field)='' or raw_text is null or note_text is null or trim(note_text)='' or category is null or category not in ('触达限制','客户关系','卡务','联系状态','其他')",'INVALID_MEMBER_NOTE')
    if 'quarantine' in present:
        fail_if(con,"select count(*) from raw_quarantine where source_row<1 or record_type is null or record_type not in ('member','order','card','shop') or reason_code is null or trim(reason_code)='' or raw_json is null or not json_valid(raw_json)",'INVALID_QUARANTINE_RECORD')
        # The JSON must represent all fields as an object; it is never executed.
        fail_if(con,"select count(*) from raw_quarantine where json_type(raw_json)!='OBJECT'",'INVALID_QUARANTINE_JSON')
    for name in ['member_notes','quarantine']:
        if name in present:
            for value, in con.execute(f'select distinct source_file from raw_{name}').fetchall():
                if value not in hashes: raise ValueError('SOURCE_FILE_NOT_IN_MANIFEST:'+name)
    for record,table in RECORD_TABLES.items():
        count=counts[record]
        if not isinstance(count,dict) or set(count)!={'read','accepted','quarantined','deduplicated'} or any(type(v) is not int or v<0 for v in count.values()): raise ValueError('RECORD_COUNTS_INVALID:'+record)
        if count['read']!=count['accepted']+count['quarantined']+count['deduplicated']: raise ValueError('RECONCILIATION_MISMATCH:'+record)
        actual=con.execute('select count(*) from raw_'+table).fetchone()[0]
        if actual!=count['accepted']: raise ValueError('ACCEPTED_COUNT_MISMATCH:'+record)
        quarantined=con.execute('select count(*) from raw_quarantine where record_type=?',[record]).fetchone()[0] if 'quarantine' in present else 0
        if quarantined!=count['quarantined']: raise ValueError('QUARANTINE_COUNT_MISMATCH:'+record)
    for name in present:
        con.execute(f'create view {name} as select * from raw_{name}')
