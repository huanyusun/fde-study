"""Wutong bookshop only. These field names and rules are not Qinghe's adapter."""
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import csv
import json
import re

FILES={'member':'读者导出.csv','order':'销售流水.csv','shop':'门店名册.csv','card':'读者卡.csv'}
TABLES={'member':'members','order':'orders','shop':'stores','card':'cards'}
KEYS={'member':'读者编号','order':'票据号','shop':'店号','card':'卡编号'}
MISSING={'','NULL','-','无'}


def date_value(value):
    for fmt in ['%Y-%m-%d','%d/%m/%Y','%Y年%m月%d日','%Y-%m-%d %H:%M:%S']:
        try:return datetime.strptime(value,fmt).date().isoformat()
        except ValueError:pass
    raise ValueError('INVALID_DATE')


def cents(value):
    number=Decimal(value)*100
    if not number.is_finite() or number!=number.to_integral_value():raise ValueError('INVALID_MONEY')
    return int(number)


def profile(tables,dictionary,context):
    fields=[];anomalies=[];differences=[]
    for filename,table in tables.items():
        for field in table['fields']:
            values=[r['raw'][field] for r in table['rows']];present=[v for v in values if v not in MISSING];counts=Counter(values)
            kind='string'
            if present and all(re.fullmatch(r'-?\d+',v) for v in present):kind='integer'
            elif present and all(re.fullmatch(r'-?\d+\.\d+',v) for v in present):kind='decimal'
            stat={'source_file':filename,'field':field,'inferred_type':kind,'missing_count':sum(v in MISSING for v in values),'total_count':len(values)}
            if len(counts)<=30 and counts:stat['distribution']=[{'value':v,'count':n} for v,n in sorted(counts.items())]
            else:
                comparable=[Decimal(v) for v in present] if kind in ('integer','decimal') else present
                stat['range']={'min':str(min(comparable)) if comparable else None,'max':str(max(comparable)) if comparable else None}
            fields.append(stat)
        seen=set();duplicates=[]
        for row in table['rows']:
            key=tuple(row['raw'].items())
            if key in seen:duplicates.append(row['source_row'])
            seen.add(key)
        if duplicates:anomalies.append({'pattern':f'完全重复行：{len(duplicates)} 条','evidence':{'source_file':filename,'sample_rows':duplicates[:20]}})
    members={r['raw']['读者编号'] for r in tables[FILES['member']]['rows']}
    orders=tables[FILES['order']]['rows']
    for pattern,predicate in [('孤儿订单',lambda r:r['读者编号'] not in members),('契约外渠道',lambda r:r['收款入口']!='书店收银')]:
        rows=[r['source_row'] for r in orders if predicate(r['raw'])]
        if rows:anomalies.append({'pattern':f'{pattern}：{len(rows)} 条原始记录（含重复时需另去重）','evidence':{'source_file':FILES['order'],'sample_rows':rows[:20]}})
    dates=[r['source_row'] for r in tables[FILES['member']]['rows'] if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',r['raw']['办证日期'])]
    if dates:
        anomalies.append({'pattern':f'日期混用：{len(dates)} 条非 ISO 写法','evidence':{'source_file':FILES['member'],'sample_rows':dates[:20]}})
        differences.append({'source_file':FILES['member'],'field':'办证日期','dictionary_claim':'统一 YYYY-MM-DD','actual':f'{len(dates)} 条使用日/月/年或中文日期','impact':'按多格式显式解析，不能仅按一种日期格式丢弃'})
    amounts=[r for r in orders if '.' in r['raw']['实际收款']]
    if amounts and '整数分' in dictionary:
        anomalies.append({'pattern':'金额包含小数，与字典整数分不符','evidence':{'source_file':FILES['order'],'sample_rows':[r['source_row'] for r in amounts[:8]]}})
        differences.append({'source_file':FILES['order'],'field':'实际收款','dictionary_claim':'整数分','actual':f'{len(amounts)} 条金额带小数；示例 {amounts[0]["raw"]["实际收款"]}，例题核对以元为单位','impact':'规则按 Decimal 乘 100，避免金额缩小 100 倍'})
    special=[r['source_row'] for r in tables[FILES['member']]['rows'] if '；' in r['raw']['备注标签']]
    if special:differences.append({'source_file':FILES['member'],'field':'备注标签','dictionary_claim':'竖线分隔，手册原清单只有 6 项','actual':'还使用中文分号，存在新增标签夜读同行；井号开头为手记','impact':'不能按斜杠拆分合法标签；备注单独保留，未知标签不删除'})
    return {'contract_version':'w04-0.1.0','data_version':context['data_version'],'fields':fields,'anomalies':anomalies,'dictionary_differences':differences}


def adapt(tables,rules,context):
    config={r['rule_id']:r for r in rules['abnormal_records']}
    for setting in rules['invalid_values']:
        if setting['action']!='keep_raw':raise ValueError('INVALID_VALUE_ACTION_UNSUPPORTED')
        # These optional raw-only fields are intentionally retained verbatim.
        for filename in FILES.values():
            for record in tables[filename]['rows']:
                for field in setting['source_fields']:
                    if field in record['raw'] and record['raw'][field] in setting['values']:
                        if not isinstance(record['raw'][field],str):raise ValueError('RAW_VALUE_MUST_BE_STRING')
    if config['money_yuan']['condition']!='decimal_yuan' or config['money_yuan']['action']!='normalize':raise ValueError('MONEY_RULE_UNSUPPORTED')
    if config['dates']['condition']!='iso_or_dmy_or_chinese_date' or config['dates']['action']!='normalize':raise ValueError('DATE_RULE_UNSUPPORTED')
    tags_cfg=rules['tag_cleaning'];prefix=tags_cfg['note_extraction']
    if prefix!='#':raise ValueError('WUTONG_NOTE_PREFIX_REQUIRED')
    known=set((Path(context['rules_dir'])/tags_cfg['legal_tags_source']).read_text().splitlines())
    split=re.compile('|'.join(re.escape(d) for d in tags_cfg['delimiters']))
    result={name:[] for name in ['members','orders','stores','cards','member_tags','member_notes','quarantine']}
    counts={kind:{'read':len(tables[filename]['rows']),'accepted':0,'quarantined':0,'deduplicated':0} for kind,filename in FILES.items()}
    samples=[];accepted_members=set();stores=set()
    def isolate(kind,row,code):
        counts[kind]['quarantined']+=1
        result['quarantine'].append({'record_type':kind,'source_file':row['source_file'],'source_row':row['source_row'],'reason_code':code,'raw_json':json.dumps(row['raw'],ensure_ascii=False,sort_keys=True)})
        if not any(s['status']=='quarantined' for s in samples):samples.append({'source_file':row['source_file'],'source_row':row['source_row'],'status':'quarantined','destination':f'quarantine.csv 记录 {len(result["quarantine"])}','reason':code})
    for kind in ['shop','member','order','card']:
        filename=FILES[kind];seen=set();key_values=defaultdict(set)
        for row in tables[filename]['rows']:key_values[row['raw'][KEYS[kind]]].add(tuple(row['raw'].items()))
        for row in tables[filename]['rows']:
            raw=row['raw'];identity=tuple(raw.items())
            if identity in seen and config['duplicate']['action']=='deduplicate':counts[kind]['deduplicated']+=1;continue
            seen.add(identity)
            if len(key_values[raw[KEYS[kind]]])>1:isolate(kind,row,config['duplicate_key']['reason_code']);continue
            try:
                if kind=='shop':
                    mapped={'store_id':raw['店号'],'store_name':raw['门店名称'],'region':raw['所属区域']};stores.add(raw['店号'])
                elif kind=='member':
                    if raw['办证门店'] not in stores:raise ValueError('UNLINKED_STORE')
                    mapped={'member_id':raw['读者编号'],'registered_at':date_value(raw['办证日期']),'home_store_id':raw['办证门店'],'tier':raw['会员级别']}
                    accepted_members.add(raw['读者编号'])
                    emitted=set()
                    for token in split.split(raw['备注标签']):
                        token=token.strip()
                        if not token:continue
                        if token in known or not token.startswith(prefix):
                            if token not in emitted:result['member_tags'].append({'member_id':raw['读者编号'],'tag':token});emitted.add(token)
                        else:
                            category='触达限制' if ('不要电话' in token or '勿拨打电话' in token) else ('联系状态' if '打不通' in token or '接不通' in token else ('卡务' if '卡' in token else '其他'))
                            note={'member_id':raw['读者编号'],'source_file':filename,'source_row':row['source_row'],'source_field':'备注标签','raw_text':raw['备注标签'],'note_text':token,'category':category}
                            if note not in result['member_notes']:result['member_notes'].append(note)
                elif kind=='order':
                    if raw['读者编号'] not in accepted_members and config['orphan']['action']=='quarantine':raise ValueError(config['orphan']['reason_code'])
                    if raw['收款入口']!='书店收银' and config['channel']['action']=='quarantine':raise ValueError(config['channel']['reason_code'])
                    if raw['成交店号'] not in stores:raise ValueError('UNLINKED_STORE')
                    status_map={'已撤单':'cancelled','已结账':'paid','部分退货':'paid','已退清':'paid'}
                    if raw['结账状态'] not in status_map:raise ValueError('UNSUPPORTED_ORDER_STATUS')
                    paid,refund=cents(raw['实际收款']),cents(raw['已退金额'])
                    if refund>paid:raise ValueError('REFUND_EXCEEDS_PAID')
                    mapped={'order_id':raw['票据号'],'member_id':raw['读者编号'],'store_id':raw['成交店号'],'ordered_at':date_value(raw['结账时刻']),'status':status_map[raw['结账状态']],'gross_cents':cents(raw['书品原额']),'paid_cents':paid,'refund_cents':refund,'quantity':int(raw['册数']),'channel':'门店' if raw['收款入口']=='书店收银' else raw['收款入口']}
                else:
                    # W03 Wutong has no card qualification business. Unexpected
                    # card rows remain traceable rather than guessed into QH types.
                    raise ValueError('UNSUPPORTED_CARD_TYPE')
            except (ValueError,InvalidOperation) as exc:
                code=str(exc) if isinstance(exc,ValueError) else 'INVALID_MONEY'
                isolate(kind,row,code);continue
            result[TABLES[kind]].append(mapped);counts[kind]['accepted']+=1
            if kind=='order' and not any(s['status']=='accepted' for s in samples):samples.append({'source_file':filename,'source_row':row['source_row'],'status':'accepted','destination':f'orders.csv 记录 {len(result["orders"])}','reason':'字段、单位、日期和关联符合契约'})
    mapping=[]
    definitions={'读者导出.csv':{'members.member_id':(['读者编号'],'保留稳定原编号'),'members.registered_at':(['办证日期'],'按规则解析 ISO、日/月/年、中文日期'),'members.home_store_id':(['办证门店'],'保留原门店号'),'members.tier':(['会员级别'],'保留等级'),'member_tags.tag':(['备注标签'],'先识别合法标签，保留未知标签'),'member_notes.raw_text':(['备注标签'],'井号备注拆分，完整原文保留')},'销售流水.csv':{'orders.order_id':(['票据号'],'保留原票据号'),'orders.member_id':(['读者编号'],'校验会员关联'),'orders.store_id':(['成交店号'],'校验门店关联'),'orders.ordered_at':(['结账时刻'],'取本地日期'),'orders.status':(['结账状态'],'已撤单转 cancelled；已结账、部分退货、已退清转 paid；其他隔离'),'orders.gross_cents':(['书品原额'],'Decimal 元乘 100'),'orders.paid_cents':(['实际收款'],'Decimal 元乘 100'),'orders.refund_cents':(['已退金额'],'Decimal 元乘 100'),'orders.quantity':(['册数'],'转整数'),'orders.channel':(['收款入口'],'书店收银转门店，其他隔离')},'门店名册.csv':{'stores.store_id':(['店号'],'保持'),'stores.store_name':(['门店名称'],'保持'),'stores.region':(['所属区域'],'保持')}}
    for filename,targets in definitions.items():
        for target,(sources,transformation) in targets.items():mapping.append({'source_file':filename,'source_fields':sources,'target':target,'transformation':transformation})
    coverage={'source':'门店收银系统导出；线上订单在另一平台，本次未导出。','time_range':{'start':'2024-09-01','end_exclusive':'2026-09-01'},'quarantined':{k:v['quarantined'] for k,v in counts.items()}}
    return {'tables':result,'record_counts':counts,'field_mapping':mapping,'samples':samples,'coverage_notes':coverage}


def reconcile(payload):
    meta=payload['metadata'];manifest=payload['manifest'];rows=[];all_balanced=True
    for kind,filename in FILES.items():
        values=dict(meta['record_counts'][kind]);read=len(payload['source'][filename]['rows']);actual=payload['first']['counts']['raw_'+TABLES[kind]]
        balanced=read==values['read']==values['accepted']+values['quarantined']+values['deduplicated'] and actual==values['accepted']
        all_balanced=all_balanced and balanced
        rows.append({'record_type':kind,**values,'reconciliation':{'balanced':balanced,'evidence':f'源文件 {read} = 接受 {values["accepted"]} + 隔离 {values["quarantined"]} + 去重 {values["deduplicated"]}；库内 {actual}'}})
    clean=payload['cleaned']['orders.csv']['rows'];total=sum(int(r['raw']['paid_cents']) for r in clean)
    before,after=payload['first']['counts'],payload['second']['counts'];repeat=before==after
    good=all_balanced and repeat and len(clean)==payload['first']['order_count']==payload['second']['order_count'] and total==payload['first']['paid_cents']==payload['second']['paid_cents']
    return {'contract_version':'w04-0.1.0','data_version':manifest['id'],'field_mapping':meta['field_mapping'],'record_counts':rows,'samples':meta['samples'],'repeat_import':{'first_run_id':payload['first_run_id'],'second_run_id':payload['second_run_id'],'before':before,'after':after,'row_counts_equal':repeat},'test_result':{'passed':good,'details':f'清洗后订单 {len(clean)} 条，实付 {total} 分；两次独立导入计数、金额逐项比对。'}}
