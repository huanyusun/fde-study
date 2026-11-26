"""Strict c3/legacy workbook adapter; wording is evidence, not inferred permission."""
from datetime import date
from ..w04.io import read_csv

BASE=['会员号','姓名','门店','最近购买','分组','回访日期','回访结果','备注']
def read_workbook(path):
    table=read_csv(path)
    if table['fields'] not in [BASE,BASE+['拉名单日期']]:raise ValueError('WORKBOOK_HEADER_MISMATCH')
    results=[]
    for row in table['rows']:
        raw=row['raw'];list_date=raw.get('拉名单日期')
        if list_date is not None:date.fromisoformat(list_date)
        results.append({'source_id':'CRM:'+raw['会员号'],'source_file':row['source_file'],'source_row':row['source_row'],
            'list_date':list_date,'raw':raw,'restriction_decision':None})
    return {'status':'ok','version':'c3' if '拉名单日期' in table['fields'] else 'legacy','rows':results}
