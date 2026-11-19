"""Five real, reproducible failures and their corrections on Wutong exports."""
import argparse
import csv
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path
import duckdb
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'platform'))
from fde_product.w04.io import read_csv,write_csv,dump


def run(raw,cleaned,online,output):
    raw,cleaned,output=map(Path,[raw,cleaned,output]);online=Path(online) if online else None;output.mkdir(parents=True,exist_ok=False)
    results={};con=duckdb.connect(':memory:')
    # Use actual member records, projected to three explicit fields.
    source=read_csv(raw/'读者导出.csv')['rows'][:1001]
    bad=output/'missing-column.csv'
    with bad.open('w',newline='',encoding='utf-8') as handle:
        writer=csv.writer(handle);writer.writerow(['读者编号','会员级别','办证门店'])
        for i,r in enumerate(source):writer.writerow([r['raw']['读者编号'],r['raw']['会员级别']]+([] if i==900 else [r['raw']['办证门店']]))
    query=con.execute('select * from read_csv(?)',[str(bad)]);columns=len(query.description);rows=len(query.fetchall())
    try:read_csv(bad,expected_fields=['读者编号','会员级别','办证门店']);strict='unexpected success'
    except ValueError as exc:strict=str(exc)
    results['one_column']={'expected':'自动探测得到 1 列但仍成功；显式表头和宽度检查拒绝第 901 条记录','actual':{'detected_columns':columns,'rows':rows,'fixed':strict},'passed':columns==1 and rows==1001 and 'record=901' in strict}
    tags=[r['raw']['tag'] for r in read_csv(cleaned/'member_tags.csv')['rows']]
    wrong=[t for t in tags if '/' not in t]
    slash=[t for t in tags if '/' in t]
    results['slash_tag']={'expected':'错误规则删掉合法斜杠标签；修正后完整保留','actual':{'before':len(tags),'wrong_after':len(wrong),'lost':len(slash),'sample':slash[:3],'fixed_preserved':len(slash)},'passed':len(slash)>0 and len(wrong)<len(tags)}
    orders=read_csv(cleaned/'orders.csv')['rows'];fault=output/'cast-error.csv'
    write_csv(fault,['order_id','paid_cents'],[{'order_id':orders[0]['raw']['order_id'],'paid_cents':orders[0]['raw']['paid_cents']},{'order_id':orders[1]['raw']['order_id'],'paid_cents':'not-an-integer'}])
    sql="read_csv(?,header=true,columns={'order_id':'VARCHAR','paid_cents':'BIGINT'},ignore_errors=true)"
    apparent=con.execute('select count(*) from '+sql,[str(fault)]).fetchone()[0]
    con.execute('create table ignored as select * from '+sql,[str(fault)]);persisted=con.execute('select count(*) from ignored').fetchone()[0]
    accepted=[];quarantine=[]
    for row in read_csv(fault)['rows']:
        try:int(row['raw']['paid_cents']);accepted.append(row['raw'])
        except ValueError:quarantine.append({'source_file':fault.name,'source_row':row['source_row'],'reason_code':'INVALID_INTEGER','raw_json':json.dumps(row['raw'],ensure_ascii=False)})
    write_csv(output/'cast-quarantine.csv',['source_file','source_row','reason_code','raw_json'],quarantine)
    results['ignore_errors']={'expected':'直接 count 为 2，落表仅 1；修正为接受 1＋持久隔离 1','actual':{'apparent_count':apparent,'persisted_count':persisted,'accepted':len(accepted),'quarantined':len(quarantine)},'passed':apparent==2 and persisted==1 and len(accepted)+len(quarantine)==2}
    con.execute('create table appended as select * from read_csv(?)',[str(cleaned/'orders.csv')]);first=con.execute('select count(*) from appended').fetchone()[0]
    con.execute('insert into appended select * from read_csv(?)',[str(cleaned/'orders.csv')]);second=con.execute('select count(*) from appended').fetchone()[0]
    fresh=[]
    for _ in range(2):
        independent=duckdb.connect(':memory:');independent.execute('create table loaded as select * from read_csv(?)',[str(cleaned/'orders.csv')]);fresh.append(independent.execute('select count(*) from loaded').fetchone()[0]);independent.close()
    results['repeat_append']={'expected':'追加导入翻倍；独立全量重导不累积','actual':{'first':first,'append_second':second,'fresh_imports':fresh},'passed':second==2*first and fresh==[first,first]}
    if online is None:
        results['source_gap']={'status':'skipped','reason':'需要未导出平台的订单，学员包不提供'}
    else:
        # Teaching calculation uses W03 monthly valid-order repeat definition.
        def counts(records):
            c=Counter()
            for r in records:
                if r['ordered_at'].startswith('2026-08') and r['status']=='paid' and int(r['paid_cents'])>int(r['refund_cents']):c[r['member_id']]+=1
            buyers=len(c);repeat=sum(n>=2 for n in c.values());return {'buyers':buyers,'repeat_buyers':repeat,'rate':repeat/buyers if buyers else None}
        store_rows=[r['raw'] for r in orders]
        internet=[]
        for r in read_csv(online)['rows']:
            r=r['raw'];internet.append({'member_id':r['读者编号'],'ordered_at':r['结账时刻'][:10],'status':'cancelled' if r['结账状态']=='已撤单' else 'paid','paid_cents':int(Decimal(r['实际收款'])*100),'refund_cents':int(Decimal(r['已退金额'])*100)})
        local,full=counts(store_rows),counts(store_rows+internet)
        results['source_gap']={'expected':'门店数据算出的月内复购低于补齐线上后的结果；不能据此断言全渠道下降','actual':{'store_only':local,'store_plus_online_teaching_truth':full,'wrong_claim':'把门店库当成全渠道，并将未导出的线上交易当零','fixed':'回答仅覆盖已导入门店数据；线上未知，需取得另一平台记录后判断'},'passed':local['rate']<full['rate']}
    con.close();dump(output/'results.json',results)
    if not all(r.get('passed',r.get('status')=='skipped') for r in results.values()):raise ValueError('COUNTEREXAMPLE_EXPECTATION_FAILED')
    return results


def output_exists(exc):
    # Each replay writes a new directory; an existing one may hold an earlier or unfinished run.
    print(json.dumps({'status':'error','code':'OUTPUT_EXISTS','reason':'输出目录已存在：'+str(exc.filename)+'。上次运行未完成或已存在，请换一个新的 --output 路径。'},ensure_ascii=False));raise SystemExit(2)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ['raw','cleaned','output']:p.add_argument('--'+arg,required=True)
    p.add_argument('--online')
    a=p.parse_args()
    try:results=run(a.raw,a.cleaned,a.online,a.output)
    except FileExistsError as exc:output_exists(exc)
    print(json.dumps(results,ensure_ascii=False,indent=2))
