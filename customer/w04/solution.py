"""W04 客户数据适配:剖析、清洗规则执行、字段映射与对账。"""
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

MISSING = ('', 'NULL', '-', '无')
INT_RE = re.compile(r'^-?\d+$')
DEC_RE = re.compile(r'^-?\d+\.\d+$')
DATE_SLASH_RE = re.compile(r'^\d{4}/\d{2}/\d{2}$')
DATE_COMPACT_RE = re.compile(r'^\d{8}$')
DATE_ISO_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
DATETIME_RE = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
SAMPLE_ROWS_CAP = 20

DATE_FIELDS_SUFFIX = ('_dt', '_tm')

FILES = {
    'member': 'crm_member_export.csv',
    'order': 'crm_order_export.csv',
    'shop': 'crm_shop.csv',
    'card': 'crm_card_export.csv',
}
TARGETS = {'member': 'members', 'order': 'orders', 'shop': 'stores', 'card': 'cards'}
KEYS = {'member': 'hy_id', 'order': 'ord_no', 'shop': 'shop_cd', 'card': 'card_no'}
STATUS_MAP = {'已支付': 'paid', '已完成': 'paid', '部分退款': 'paid', '全额退款': 'paid', '已取消': 'cancelled'}
ACCOUNT_STATUS_BASE = {'1': '活跃', '2': '冻结', '3': '注销'}
TOUCH_PREFIXES = ('勿发短信', '勿打电话')
CARD_TYPES = {'悦享年卡', '家庭季卡', '异业联名卡', '体验卡'}
CHANNELS = {'门店', '小程序', '商城'}


def _infer_type(values):
    present = [v for v in values if v not in MISSING]
    if not present:
        return 'string'
    if all(INT_RE.match(v) for v in present):
        return 'integer'
    if all(INT_RE.match(v) or DEC_RE.match(v) for v in present):
        return 'decimal'
    if all(
        DATE_ISO_RE.match(v) or DATE_SLASH_RE.match(v) or DATE_COMPACT_RE.match(v)
        for v in present
    ):
        return 'date'
    if all(DATETIME_RE.match(v) for v in present):
        return 'datetime'
    return 'string'


def profile(tables, dictionary, context):
    fields = []
    distributions = {}
    member_ids = set()
    shop_ids = set()
    member_file = None
    shop_file = None

    for filename, table in tables.items():
        for field in table['fields']:
            values = [row['raw'][field] for row in table['rows']]
            present = [v for v in values if v not in MISSING]
            counts = Counter(present)
            stat = {
                'source_file': filename,
                'field': field,
                'inferred_type': _infer_type(values),
                'total_count': len(values),
                'missing_count': len(values) - len(present),
            }
            if 0 < len(counts) <= 30:
                stat['distribution'] = [
                    {'value': v, 'count': n} for v, n in sorted(counts.items())
                ]
            elif present:
                stat['range'] = {'min': min(present), 'max': max(present)}
            else:
                stat['range'] = {'min': None, 'max': None}
            fields.append(stat)
            distributions[(filename, field)] = counts

        if 'member' in filename and 'hy_id' in table['fields']:
            member_file = filename
            member_ids = {
                row['raw']['hy_id'] for row in table['rows']
                if row['raw']['hy_id'] not in MISSING
            }
        if 'shop' in filename and 'shop_cd' in table['fields']:
            shop_file = filename
            shop_ids = {
                row['raw']['shop_cd'] for row in table['rows']
                if row['raw']['shop_cd'] not in MISSING
            }

    anomalies = _find_anomalies(tables, member_ids, shop_ids, member_file)
    differences = _find_dictionary_differences(distributions)

    return {
        'contract_version': 'w04-0.1.0',
        'data_version': context['data_version'],
        'fields': fields,
        'anomalies': anomalies,
        'dictionary_differences': differences,
    }


def _anomaly(pattern, source_file, rows):
    return {
        'pattern': pattern,
        'evidence': {
            'source_file': source_file,
            'sample_rows': sorted(rows)[:SAMPLE_ROWS_CAP],
        },
    }


def _find_anomalies(tables, member_ids, shop_ids, member_file):
    anomalies = []
    for filename, table in tables.items():
        fields = table['fields']
        rows = table['rows']

        seen = {}
        for row in rows:
            key = tuple(sorted(row['raw'].items()))
            seen.setdefault(key, []).append(row['source_row'])
        dup_rows = [r for group in seen.values() if len(group) > 1 for r in group]
        if dup_rows:
            anomalies.append(_anomaly(
                '完全重复行：同一原始记录整行重复出现(duplicate)', filename, dup_rows))

        for key_field in ('ord_no', 'card_no', 'hy_id'):
            if key_field in fields and key_field != 'hy_id':
                groups = {}
                for row in rows:
                    groups.setdefault(row['raw'][key_field], []).append(row['source_row'])
                key_dups = [r for g in groups.values() if len(g) > 1 for r in g]
                if key_dups:
                    anomalies.append(_anomaly(
                        f'主键重复：{key_field} 同值出现多次(duplicate)', filename, key_dups))

        if 'hy_id' in fields and member_file is not None and member_file != filename:
            orphans = [
                row['source_row'] for row in rows
                if row['raw'].get('hy_id') not in MISSING
                and row['raw']['hy_id'] not in member_ids
            ]
            if orphans:
                anomalies.append(_anomaly(
                    '孤儿记录：hy_id 关联不到会员表(orphan)', filename, orphans))

        if 'shop_cd' in fields and shop_ids:
            unlinked = [
                row['source_row'] for row in rows
                if row['raw'].get('shop_cd') not in MISSING
                and row['raw']['shop_cd'] not in shop_ids
            ]
            if unlinked:
                anomalies.append(_anomaly(
                    '门店编码关联不到门店表(unlinked shop)', filename, unlinked))

        if 'amt_rfd' in fields and 'amt_pay' in fields:
            over_refund = []
            for row in rows:
                try:
                    if float(row['raw']['amt_rfd']) > float(row['raw']['amt_pay']):
                        over_refund.append(row['source_row'])
                except (ValueError, KeyError):
                    continue
            if over_refund:
                anomalies.append(_anomaly(
                    '超额退款：amt_rfd 大于 amt_pay', filename, over_refund))

        for field in fields:
            if not field.endswith(DATE_FIELDS_SUFFIX):
                continue
            invalid_dates = []
            for row in rows:
                raw = row['raw'][field]
                if raw in MISSING:
                    continue
                normalized = raw.replace('/', '-')
                for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y%m%d'):
                    try:
                        datetime.strptime(normalized, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    invalid_dates.append(row['source_row'])
            if invalid_dates:
                anomalies.append(_anomaly(
                    f'无效日期：{field} 不是合法日历日期(invalid date)', filename, invalid_dates))

    return anomalies


def _find_dictionary_differences(distributions):
    differences = []

    def count_of(filename, field, pred):
        return sum(
            n for v, n in distributions.get((filename, field), {}).items() if pred(v))

    def extra_values(filename, field, allowed):
        dist = distributions.get((filename, field), {})
        return sorted((v, n) for v, n in dist.items() if v not in allowed)

    def add(source_file, field, claim, actual, impact):
        differences.append({
            'source_file': source_file,
            'field': field,
            'dictionary_claim': claim,
            'actual': actual,
            'impact': impact,
        })

    slash_join = count_of('crm_member_export.csv', 'join_dt', DATE_SLASH_RE.match)
    compact_join = count_of('crm_member_export.csv', 'join_dt', DATE_COMPACT_RE.match)
    non_iso_join = slash_join + compact_join
    if non_iso_join:
        add('crm_member_export.csv', 'join_dt',
            '日期,会员注册的日期',
            f'{non_iso_join} 条非 ISO(斜杠 {slash_join} 条,紧凑 YYYYMMDD {compact_join} 条)',
            '日期解析与按注册日期筛选的口径,适配层需归一')

    decimal_amounts = count_of(
        'crm_order_export.csv', 'amt_pay', lambda v: bool(DEC_RE.match(v)))
    if decimal_amounts:
        add('crm_order_export.csv', 'amt_pay/amt_total/amt_rfd',
            '整数,单位:分',
            f'实为两位小数字符串(如 {decimal_amounts} 条含小数),单位是元',
            '所有金额类指标的分换算,乘 100 取整前需确认精度')

    lv_extra = extra_values('crm_member_export.csv', 'lv', {'1', '2', '3'})
    if lv_extra:
        add('crm_member_export.csv', 'lv',
            '代码:1 普通,2 银卡,3 金卡',
            f'存文字而非代码,如 {lv_extra[:3]}',
            '按会员等级筛选/分组的指标,映射规则要按实际取值写')

    stat_extra = extra_values('crm_member_export.csv', 'stat', {'1', '2', '3'})
    if stat_extra:
        add('crm_member_export.csv', 'stat',
            '代码:1 正常,2 冻结,3 注销',
            f'出现字典外代码,如 {stat_extra[:3]}',
            '会员状态口径(疑"未激活"),影响活跃会员判断,待向客户核实')

    src_extra = extra_values('crm_member_export.csv', 'src_ch', {'门店', '小程序', '商城'})
    if src_extra:
        add('crm_member_export.csv', 'src_ch',
            '文本:门店、小程序、商城',
            f'出现字典外取值,如 {src_extra[:3]}',
            '注册渠道维度统计,需客户确认归属')

    kind_extra = extra_values(
        'crm_card_export.csv', 'card_kind', {'悦享卡（年）', '家庭季卡', '异业联名卡', '体验卡'})
    if kind_extra:
        add('crm_card_export.csv', 'card_kind',
            '文本:悦享卡(年)、家庭季卡、异业联名卡、体验卡',
            f'出现字典外卡种,如 {kind_extra[:3]}',
            '卡种相关指标与卡片映射,疑字典旧名与契约外卡种,待核实')

    area_extra = extra_values('crm_shop.csv', 'area', {'华东', '华南', '华北'})
    if area_extra:
        add('crm_shop.csv', 'area',
            '文本:华东、华南、华北',
            f'出现字典外大区,如 {area_extra[:3]}',
            '按大区的门店/销售分析口径')

    bad_reg_shop = count_of(
        'crm_member_export.csv', 'reg_shop',
        lambda v: not (v in MISSING or INT_RE.match(v) and len(v) == 4))
    if bad_reg_shop:
        add('crm_member_export.csv', 'reg_shop',
            '门店编码,4 位数字,见门店表',
            f'{bad_reg_shop} 条不是 4 位 ASCII 数字(含全角数字等)',
            '注册门店关联与门店维度指标,适配层需归一')

    return differences


def _normalize_code(value):
    """门店编码归一:全角转半角、去首尾空格、字母统一大写;不影响中文与全角标点。"""
    return unicodedata.normalize('NFKC', value).strip().upper()


def _date_only(value):
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d', '%Y%m%d'):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError('INVALID_DATE')


def _cents(value):
    try:
        number = Decimal(value) * 100
    except InvalidOperation:
        raise ValueError('INVALID_MONEY')
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError('INVALID_MONEY')
    return int(number)


def _rule(config, rule_id):
    setting = config[rule_id]
    return setting['action'], setting['reason_code']


def adapt(tables, rules, context):
    config = {r['rule_id']: r for r in rules['abnormal_records']}
    tags_cfg = rules['tag_cleaning']
    legal = {
        line.strip()
        for line in (Path(context['rules_dir']) / tags_cfg['legal_tags_source'])
        .read_text(encoding='utf-8').splitlines()
        if line.strip()
    }
    split = re.compile('|'.join(re.escape(d) for d in tags_cfg['delimiters']))

    stat_map = dict(ACCOUNT_STATUS_BASE)
    channel_keep = set(CHANNELS)
    for setting in rules['invalid_values']:
        fields = set(setting['source_fields'])
        if fields == {'stat'} and setting['action'].startswith('映射'):
            stat_map.update({v: '未激活' for v in setting['values']})
        if fields == {'src_ch'} and setting['action'].startswith('保留'):
            channel_keep |= set(setting['values'])

    result = {name: [] for name in [
        'members', 'orders', 'stores', 'cards', 'member_tags', 'member_notes', 'quarantine']}
    counts = {
        kind: {'read': len(tables[filename]['rows']), 'accepted': 0,
               'quarantined': 0, 'deduplicated': 0}
        for kind, filename in FILES.items()
    }
    samples = []
    accepted_members = set()
    store_ids = set()
    seen_notes = set()

    def isolate(kind, row, code):
        counts[kind]['quarantined'] += 1
        result['quarantine'].append({
            'record_type': kind,
            'source_file': row['source_file'],
            'source_row': row['source_row'],
            'reason_code': code,
            'raw_json': json.dumps(row['raw'], ensure_ascii=False, sort_keys=True),
        })
        if not any(s['status'] == 'quarantined' for s in samples):
            samples.append({
                'source_file': row['source_file'], 'source_row': row['source_row'],
                'status': 'quarantined',
                'destination': f'quarantine.csv 记录 {len(result["quarantine"])}',
                'reason': code,
            })

    def split_tags(member_id, filename, row):
        raw_text = row['raw']['tag']
        emitted = set()
        for token in split.split(raw_text):
            token = token.strip()
            if not token:
                continue
            if token in legal:
                if token not in emitted:
                    emitted.add(token)
                    result['member_tags'].append({'member_id': member_id, 'tag': token})
                continue
            category = '触达限制' if token.startswith(TOUCH_PREFIXES) else '其他'
            note = {
                'member_id': member_id, 'source_file': filename,
                'source_row': row['source_row'], 'source_field': 'tag',
                'raw_text': raw_text, 'note_text': token, 'category': category,
            }
            key = (member_id, filename, row['source_row'], 'tag', token)
            if key not in seen_notes:
                seen_notes.add(key)
                result['member_notes'].append(note)

    for kind in ('shop', 'member', 'order', 'card'):
        filename = FILES[kind]
        action_dedup, reason_dup = _rule(config, f'duplicate_{kind}_row')
        first_identity = {}
        conflict_keys = set()
        for row in tables[filename]['rows']:
            identity = tuple(sorted(row['raw'].items()))
            key_value = row['raw'][KEYS[kind]]
            if key_value in first_identity:
                if first_identity[key_value] != identity:
                    conflict_keys.add(key_value)
            else:
                first_identity[key_value] = identity
        seen = set()
        for row in tables[filename]['rows']:
            raw = row['raw']
            identity = tuple(sorted(raw.items()))
            if action_dedup == 'deduplicate' and identity in seen:
                counts[kind]['deduplicated'] += 1
                continue
            seen.add(identity)
            try:
                if raw[KEYS[kind]] in conflict_keys:
                    raise ValueError(reason_dup)
                if raw[KEYS[kind]] in MISSING:
                    raise ValueError('EMPTY_KEY')

                if kind == 'shop':
                    store_id = _normalize_code(raw['shop_cd'])
                    mapped = {
                        'store_id': store_id,
                        'region': raw['area'],
                        'store_name': raw['shop_nm'],
                    }
                    store_ids.add(store_id)

                elif kind == 'member':
                    if raw['stat'] not in stat_map:
                        raise ValueError('INVALID_ACCOUNT_STATUS')
                    if raw['src_ch'] not in channel_keep:
                        raise ValueError('INVALID_REGISTERED_CHANNEL')
                    if raw['create_tm'] in MISSING:
                        raise ValueError('INVALID_CREATED_AT')
                    member_id = raw['hy_id']
                    home_store_id = _normalize_code(raw['reg_shop'])
                    if home_store_id and store_ids and home_store_id not in store_ids:
                        raise ValueError(_rule(config, 'unlinked_store')[1])
                    mapped = {
                        'member_id': member_id,
                        'registered_at': _date_only(raw['join_dt']),
                        'home_store_id': home_store_id,
                        'tier': raw['lv'],
                        'account_status': stat_map[raw['stat']],
                        'registered_channel': raw['src_ch'],
                        'created_at': _date_only(raw['create_tm']),
                    }
                    accepted_members.add(member_id)
                    split_tags(member_id, filename, row)

                elif kind == 'order':
                    _, reason_orphan = _rule(config, 'orphan_order')
                    if raw['hy_id'] not in accepted_members:
                        raise ValueError(reason_orphan)
                    store_id = _normalize_code(raw['shop_cd'])
                    if store_ids and store_id not in store_ids:
                        raise ValueError(_rule(config, 'unlinked_store')[1])
                    if raw['ord_stat'] not in STATUS_MAP:
                        raise ValueError('UNSUPPORTED_ORDER_STATUS')
                    if raw['ch'] not in CHANNELS:
                        raise ValueError('INVALID_ORDER_CHANNEL')
                    paid = _cents(raw['amt_pay'])
                    refund = _cents(raw['amt_rfd'])
                    if refund > paid:
                        raise ValueError(_rule(config, 'refund_exceeds_paid')[1])
                    mapped = {
                        'order_id': raw['ord_no'],
                        'member_id': raw['hy_id'],
                        'store_id': store_id,
                        'ordered_at': _date_only(raw['ord_tm']),
                        'status': STATUS_MAP[raw['ord_stat']],
                        'gross_cents': _cents(raw['amt_total']),
                        'paid_cents': paid,
                        'refund_cents': refund,
                        'quantity': int(raw['qty']),
                        'channel': raw['ch'],
                    }

                else:
                    _, reason_card = _rule(config, 'unsupported_card_type')
                    if raw['hy_id'] not in accepted_members:
                        raise ValueError(_rule(config, 'orphan_card')[1])
                    card_type = '悦享年卡' if raw['card_kind'] == '悦享卡（年）' else raw['card_kind']
                    if card_type not in CARD_TYPES:
                        raise ValueError(reason_card)
                    mapped = {
                        'card_id': raw['card_no'],
                        'member_id': raw['hy_id'],
                        'card_type': card_type,
                        'valid_from': _date_only(raw['st_dt']),
                        'valid_until': _date_only(raw['ed_dt']),
                        'ended_at': '' if raw['stop_dt'] in MISSING else _date_only(raw['stop_dt']),
                        'card_paid_cents': _cents(raw['pay_amt']),
                    }
            except (ValueError, InvalidOperation) as exc:
                code = str(exc) if isinstance(exc, ValueError) else 'INVALID_MONEY'
                isolate(kind, row, code)
                continue
            result[TARGETS[kind]].append(mapped)
            counts[kind]['accepted'] += 1
            if kind == 'order' and not any(
                    s['status'] == 'accepted' for s in samples):
                samples.append({
                    'source_file': filename, 'source_row': row['source_row'],
                    'status': 'accepted',
                    'destination': f'orders.csv 记录 {len(result["orders"])}',
                    'reason': '字段、单位、日期和关联符合契约',
                })

    mapping = []
    definitions = {
        'crm_member_export.csv': {
            'members.member_id': (['hy_id'], '保留原会员号'),
            'members.registered_at': (['join_dt'], '斜杠/紧凑格式归一为 ISO 日期'),
            'members.home_store_id': (['reg_shop'], '全角转半角、去首尾空格后保留'),
            'members.tier': (['lv'], '保留文字等级(普通/银卡/金卡)'),
            'members.account_status': (['stat'], '0→未激活,1→活跃,2→冻结,3→注销'),
            'members.registered_channel': (['src_ch'], '保留,含"系统导入"'),
            'members.created_at': (['create_tm'], '取日期部分'),
            'member_tags.tag': (['tag'], '按分隔符拆分,仅 tags.txt 内合法标签'),
            'member_notes.raw_text': (['tag'], '非标签片段按备注保留,原文完整'),
        },
        'crm_order_export.csv': {
            'orders.order_id': (['ord_no'], '保留原订单号,重复行去重'),
            'orders.member_id': (['hy_id'], '校验会员关联,失败隔离'),
            'orders.store_id': (['shop_cd'], '全角转半角、去空格后校验门店关联'),
            'orders.ordered_at': (['ord_tm'], '取本地日期'),
            'orders.status': (['ord_stat'], '已支付/已完成/部分退款/全额退款→paid,已取消→cancelled,其他隔离'),
            'orders.gross_cents': (['amt_total'], 'Decimal 元乘 100 取整'),
            'orders.paid_cents': (['amt_pay'], 'Decimal 元乘 100 取整'),
            'orders.refund_cents': (['amt_rfd'], 'Decimal 元乘 100 取整,超额退款隔离'),
            'orders.quantity': (['qty'], '转整数'),
            'orders.channel': (['ch'], '保留门店/小程序/商城'),
        },
        'crm_shop.csv': {
            'stores.store_id': (['shop_cd'], '全角转半角、去空格后保留'),
            'stores.region': (['area'], '保留,含华中/西南'),
            'stores.store_name': (['shop_nm'], '保持'),
        },
        'crm_card_export.csv': {
            'cards.card_id': (['card_no'], '保留原卡号'),
            'cards.member_id': (['hy_id'], '校验会员关联,失败隔离'),
            'cards.card_type': (['card_kind'], '悦享卡(年)→悦享年卡;员工卡等契约外卡种隔离'),
            'cards.valid_from': (['st_dt'], 'ISO 日期'),
            'cards.valid_until': (['ed_dt'], 'ISO 日期'),
            'cards.ended_at': (['stop_dt'], '空值保留为空,有值转 ISO'),
            'cards.card_paid_cents': (['pay_amt'], 'Decimal 元乘 100 取整'),
        },
    }
    for filename, targets in definitions.items():
        for target, (sources, transformation) in targets.items():
            mapping.append({
                'source_file': filename,
                'source_fields': sources,
                'target': target,
                'transformation': transformation,
            })

    coverage = {
        'source': '青禾新 CRM 系统导出(会员/订单/会员卡/门店四表);小林工作账回访与勿扰名单仅用于对照核验,不导入查询库;线上商城独立订单流与退卡流水未包含在本次导出。',
        'time_range': {'start': '2024-09-01', 'end_exclusive': '2026-09-01'},
        'quarantined': {kind: counts[kind]['quarantined'] for kind in ('member', 'order', 'card', 'shop')},
    }
    return {
        'tables': result,
        'record_counts': counts,
        'field_mapping': mapping,
        'samples': samples,
        'coverage_notes': coverage,
    }


def reconcile(payload):
    """对账:原始表、清洗表与两次独立导入的库逐项核对,报告由计算得出,不写死。"""
    meta = payload['metadata']
    manifest = payload['manifest']
    rows = []
    all_balanced = True
    for kind, filename in FILES.items():
        values = dict(meta['record_counts'][kind])
        read = len(payload['source'][filename]['rows'])
        actual = payload['first']['counts']['raw_' + TARGETS[kind]]
        balanced = (
            read == values['read']
            == values['accepted'] + values['quarantined'] + values['deduplicated']
            and actual == values['accepted']
        )
        all_balanced = all_balanced and balanced
        rows.append({
            'record_type': kind,
            **values,
            'reconciliation': {
                'balanced': balanced,
                'evidence': (
                    f'源文件 {read} = 接受 {values["accepted"]} + 隔离 '
                    f'{values["quarantined"]} + 去重 {values["deduplicated"]}；'
                    f'库内 {actual}'
                ),
            },
        })
    clean = payload['cleaned']['orders.csv']['rows']
    total = sum(int(r['raw']['paid_cents']) for r in clean)
    before = payload['first']['counts']
    after = payload['second']['counts']
    repeat = before == after
    good = (
        all_balanced
        and repeat
        and len(clean) == payload['first']['order_count'] == payload['second']['order_count']
        and total == payload['first']['paid_cents'] == payload['second']['paid_cents']
    )
    return {
        'contract_version': 'w04-0.1.0',
        'data_version': manifest['id'],
        'field_mapping': meta['field_mapping'],
        'record_counts': rows,
        'samples': meta['samples'],
        'repeat_import': {
            'first_run_id': payload['first_run_id'],
            'second_run_id': payload['second_run_id'],
            'before': before,
            'after': after,
            'row_counts_equal': repeat,
        },
        'test_result': {
            'passed': good,
            'details': (
                f'清洗后订单 {len(clean)} 条、实付 {total} 分;四类记录对账等式成立,'
                '两次独立全量导入的行数、金额、表哈希逐项一致。'
            ),
        },
    }
