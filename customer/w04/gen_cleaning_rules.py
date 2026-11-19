"""生成 artifacts/w04/cleaning_rules.yaml。

数据事实取自 profile_report.json(生成前逐项对账,不符即拒绝生成);
业务口径取自 artifacts/w04/interviews/ 三场访谈(MSG 编号随条目写入)。
重跑: .venv/bin/python customer/w04/gen_cleaning_rules.py
"""
import csv
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / 'artifacts/w04/profile_report.json'
TAGS = ROOT / 'artifacts/w04/tags.txt'
OUT = ROOT / 'artifacts/w04/cleaning_rules.yaml'
MEMBER_CSV = ROOT / 'materials/data/qinghe-w04-v1.1/crm_member_export.csv'

import json

profile = json.loads(PROFILE.read_text(encoding='utf-8'))
dist = {}
for f in profile['fields']:
    if 'distribution' in f:
        dist[(f['source_file'], f['field'])] = {
            d['value']: d['count'] for d in f['distribution']
        }


def count(file, field, pred):
    return sum(n for v, n in dist.get((file, field), {}).items() if pred(v))


def csv_count(field, pred):
    """高基数字段(报告只有 range)的计数,从原始 CSV 只读重算。"""
    with MEMBER_CSV.open(encoding='utf-8', newline='') as fh:
        return sum(1 for row in csv.DictReader(fh) if pred(row[field]))


def expect(name, actual, want):
    if actual != want:
        print(f'[中止] {name}: 实际值 {actual} != 规则引用值 {want}')
        sys.exit(1)


expect('stat 代码 0 条数', count('crm_member_export.csv', 'stat', lambda v: v == '0'), 22296)
expect('src_ch 系统导入条数', count('crm_member_export.csv', 'src_ch', lambda v: v == '系统导入'), 39917)
expect('card_kind 员工卡条数', count('crm_card_export.csv', 'card_kind', lambda v: v == '员工卡'), 299)
expect('card_kind 悦享年卡条数', count('crm_card_export.csv', 'card_kind', lambda v: v == '悦享年卡'), 8178)
expect('card_kind 悦享卡（年）条数', count('crm_card_export.csv', 'card_kind', lambda v: v == '悦享卡（年）'), 1201)
expect('area 华中门店数', count('crm_shop.csv', 'area', lambda v: v == '华中'), 30)
expect('area 西南门店数', count('crm_shop.csv', 'area', lambda v: v == '西南'), 42)
expect('join_dt 斜杠条数', csv_count('join_dt', lambda v: bool(re.match(r'^\d{4}/\d{2}/\d{2}$', v))), 1823)
expect('join_dt 紧凑条数', csv_count('join_dt', lambda v: bool(re.match(r'^\d{8}$', v))), 1790)

missing = ('', 'NULL', '-', '无')
expect(
    'reg_shop 非四位 ASCII 条数',
    csv_count('reg_shop', lambda v: v not in missing and not re.match(r'^\d{4}$', v)),
    6177,
)

with MEMBER_CSV.open(encoding='utf-8', newline='') as fh:
    tag_values = [row['tag'] for row in csv.DictReader(fh)]
for delim in (',', '，', ';', '/'):
    if not any(delim in v for v in tag_values):
        print(f'[中止] 分隔符 {delim!r} 未在 tag 字段任何取值中出现')
        sys.exit(1)

tags = [line.strip() for line in TAGS.read_text(encoding='utf-8').splitlines() if line.strip()]
expect('tags.txt 标签数', len(tags), 16)
LEGAL_TAGS = ['高价值', '价格敏感', '宠物', '生鲜偏好', '母婴-0到3岁', '母婴-3到6岁', '周末家庭',
              '学生', '企业团购', '流失预警', '积分达人', '门店偏好', '夜间购物', '会员日活跃',
              '小程序偏好', '银发族']
expect('tags.txt 内容与访谈清单一致', tags, LEGAL_TAGS)

rules = {
    'contract_version': 'w04-0.1.0',
    'data_version': 'qinghe-w04-v1.1',
    'tag_cleaning': {
        'delimiters': [',', '，', ';', '/'],
        'legal_tags_source': 'tags.txt',
        'hyphenated_tag_handling': '连字符是标签与备注内部的组成字符,不是分隔符;先按 tags.txt 整词匹配合法标签(如"母婴-0到3岁"),禁止按连字符拆分 (xiao-lin-1 MSG-06100)',
        'unknown_tag_handling': '仅 tags.txt 中经客户确认的 16 个标准标签进入 member_tags;清单外的片段一律作为完整备注写入 member_notes 并保留原文,未经确认的暂定词(如"待核新品")按备注保留并在诊断报告列为待核 (xiao-lin-1 MSG-06100)',
        'note_extraction': '拆出的非标签片段一条备注一行,raw_text 保留 tag 字段完整原值、note_text 为片段原文、source_field=tag;以"勿发短信"或"勿打电话"开头的片段 category=触达限制,其余 category=其他;"勿扰""暂勿来电""号码是错的"等写法无客户依据,不归触达限制、按备注保留列待核 (xiao-lin-1 MSG-06102)',
    },
    'invalid_values': [
        {
            'source_fields': ['hy_id'],
            'values': ['', 'NULL', '-', '无'],
            'action': '隔离该记录',
            'reason': '会员主键为空,无法入库与关联',
        },
        {
            'source_fields': ['ord_no', 'card_no'],
            'values': ['', 'NULL', '-', '无'],
            'action': '隔离该记录',
            'reason': '订单号/卡号主键为空',
        },
        {
            'source_fields': ['amt_total', 'amt_pay', 'amt_rfd', 'pay_amt', 'qty'],
            'values': ['', 'NULL', '-', '无'],
            'action': '隔离该记录',
            'reason': '金额或件数缺失,无法完成元→分换算与汇总',
        },
        {
            'source_fields': ['stat'],
            'values': ['0'],
            'action': '映射为"未激活"',
            'reason': '老周确认 0=未激活,到店或小程序激活后变 1 (lao-zhou-1 MSG-06087)',
        },
        {
            'source_fields': ['src_ch'],
            'values': ['系统导入'],
            'action': '保留并映射为"系统导入"',
            'reason': '老周确认为批量建档账户,契约 registered_channel 已含该值 (lao-zhou-1 MSG-06089)',
        },
    ],
    'abnormal_records': [
        {
            'rule_id': 'duplicate_member_row',
            'condition': 'crm_member_export.csv 中整行字段值完全相同的重复记录',
            'action': 'deduplicate',
            'reason_code': 'DUPLICATE_PRIMARY_KEY',
            'evidence': '同一 hy_id 重复出现;重复行计入 deduplicated 桶',
        },
        {
            'rule_id': 'duplicate_order_row',
            'condition': 'crm_order_export.csv 中整行完全相同或 ord_no 同值重复的记录(同单重复导出)',
            'action': 'deduplicate',
            'reason_code': 'DUPLICATE_PRIMARY_KEY',
            'evidence': 'profile_report.json 异常"完全重复行/主键重复",首条保留、其余去重',
        },
        {
            'rule_id': 'duplicate_shop_row',
            'condition': 'crm_shop.csv 中整行完全相同或 shop_cd 同值冲突的记录',
            'action': 'deduplicate',
            'reason_code': 'DUPLICATE_PRIMARY_KEY',
            'evidence': '同重复行口径',
        },
        {
            'rule_id': 'duplicate_card_row',
            'condition': 'crm_card_export.csv 中整行完全相同或 card_no 同值冲突的记录',
            'action': 'deduplicate',
            'reason_code': 'DUPLICATE_PRIMARY_KEY',
            'evidence': '同重复行口径',
        },
        {
            'rule_id': 'orphan_order',
            'condition': '订单 hy_id 归一后仍无法在会员表找到',
            'action': 'quarantine',
            'reason_code': 'UNLINKED_ACCOUNT',
            'evidence': 'profile_report.json 异常"孤儿记录",隔离保留完整原记录',
        },
        {
            'rule_id': 'orphan_card',
            'condition': '会员卡 hy_id 归一后仍无法在会员表找到',
            'action': 'quarantine',
            'reason_code': 'UNLINKED_ACCOUNT',
            'evidence': '同孤儿订单口径',
        },
        {
            'rule_id': 'refund_exceeds_paid',
            'condition': 'amt_rfd(元转分后)大于 amt_pay',
            'action': 'quarantine',
            'reason_code': 'REFUND_EXCEEDS_PAID',
            'evidence': 'profile_report.json 异常"超额退款",金额口径见访谈 lao-zhou-1 MSG-06085',
        },
        {
            'rule_id': 'invalid_calendar_date',
            'condition': '日期字段(join_dt/birth/st_dt/ed_dt/stop_dt/ord_tm)无法解析为合法日历日期,如 2026-02-30',
            'action': 'quarantine',
            'reason_code': 'INVALID_DATE',
            'evidence': '预检边界样例注入的损坏日期;与格式归一(join_dt_format)区分',
        },
        {
            'rule_id': 'unsupported_card_type',
            'condition': 'card_kind 等于"员工卡"',
            'action': 'quarantine',
            'reason_code': 'UNSUPPORTED_CARD_TYPE',
            'evidence': '陈姐确认员工卡为内购福利、不算会员权益不计入付费会员资格 (chen-jie-1 MSG-06109),299 张全部 pay_amt=0.00',
        },
        {
            'rule_id': 'unlinked_store',
            'condition': 'reg_shop/shop_cd 全角转半角、去首尾空格、字母统一大写归一后,仍无法在门店表找到(字母前缀编码本身合法)',
            'action': 'quarantine',
            'reason_code': 'UNLINKED_STORE',
            'evidence': '自定义原因码;编码规则见 lao-zhou-1 MSG-06093,2025 年后新店带字母前缀',
        },
        {
            'rule_id': 'join_dt_format',
            'condition': 'join_dt 为 YYYY/MM/DD 或 YYYYMMDD 写法',
            'action': 'normalize',
            'reason_code': 'DATE_FORMAT_NON_ISO',
            'evidence': '斜杠 1,823 条+紧凑 1,790 条,归一为 ISO;老周确认字段含义、格式按数据归一 (lao-zhou-1 MSG-06091)',
        },
        {
            'rule_id': 'shop_code_fullwidth',
            'condition': 'reg_shop/shop_cd 含全角数字/字母、首尾空格或小写字母',
            'action': 'normalize',
            'reason_code': 'SHOP_CODE_FORMAT',
            'evidence': '6,177 条非四位;全角转半角、去空格后重试门店关联,仍失配走 unlinked_store',
        },
    ],
    'raw_preservation': {
        'original_files': '原始 CSV 只读保留于 materials/data/qinghe-w04-v1.1,不修改、不重写;manifest.json 记录各文件行数与 SHA-256',
        'notes': 'member_notes.csv 每条备注保留 source_file、source_row、source_field=tag、raw_text(tag 字段完整原值)、note_text(片段原文)、category;备注不拆碎片、不删原文,同一片段的来源两列齐全',
        'quarantine': 'quarantine.csv 每条保留 record_type、source_file、source_row、reason_code、raw_json(json.dumps(row["raw"], ensure_ascii=False) 写完整原记录);隔离不丢弃,计数入 record_counts.quarantined',
    },
}

header = (
    '# 本文件由 customer/w04/gen_cleaning_rules.py 生成,勿手改;重跑命令见该脚本 docstring。\n'
    '# 数据事实对账自 artifacts/w04/profile_report.json;业务口径出处 artifacts/w04/interviews/。\n'
)
body = yaml.safe_dump(rules, allow_unicode=True, sort_keys=False, width=100)
OUT.write_text(header + body, encoding='utf-8')
print(f'[OK] 对账 12 项全部一致,已生成 {OUT}')
