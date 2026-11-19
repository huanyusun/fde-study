"""W04 适配器单测:合法标签、隔离、金额换算、重复运行一致性。"""
import json
import tempfile
import unittest
from pathlib import Path

import solution


def build_rules():
    def rule(rule_id, action, reason_code):
        return {'rule_id': rule_id, 'condition': condition_text(rule_id),
                'action': action, 'reason_code': reason_code, 'evidence': 'test'}

    def condition_text(rule_id):
        return rule_id

    return {
        'tag_cleaning': {
            'delimiters': [',', '，', ';', '/'],
            'legal_tags_source': 'tags.txt',
            'hyphenated_tag_handling': '整词匹配,不按连字符拆分',
            'unknown_tag_handling': '清单外片段按备注保留',
            'note_extraction': '勿发短信/勿打电话开头为触达限制',
        },
        'invalid_values': [
            {'source_fields': ['stat'], 'values': ['0'],
             'action': '映射为"未激活"', 'reason': '0=未激活'},
            {'source_fields': ['src_ch'], 'values': ['系统导入'],
             'action': '保留并映射为"系统导入"', 'reason': '批量建档'},
        ],
        'abnormal_records': [
            rule('duplicate_member_row', 'deduplicate', 'DUPLICATE_PRIMARY_KEY'),
            rule('duplicate_order_row', 'deduplicate', 'DUPLICATE_PRIMARY_KEY'),
            rule('duplicate_shop_row', 'deduplicate', 'DUPLICATE_PRIMARY_KEY'),
            rule('duplicate_card_row', 'deduplicate', 'DUPLICATE_PRIMARY_KEY'),
            rule('orphan_order', 'quarantine', 'UNLINKED_ACCOUNT'),
            rule('orphan_card', 'quarantine', 'UNLINKED_ACCOUNT'),
            rule('refund_exceeds_paid', 'quarantine', 'REFUND_EXCEEDS_PAID'),
            rule('invalid_calendar_date', 'quarantine', 'INVALID_DATE'),
            rule('unsupported_card_type', 'quarantine', 'UNSUPPORTED_CARD_TYPE'),
            rule('unlinked_store', 'quarantine', 'UNLINKED_STORE'),
            rule('join_dt_format', 'normalize', 'DATE_FORMAT_NON_ISO'),
            rule('shop_code_fullwidth', 'normalize', 'SHOP_CODE_FORMAT'),
        ],
        'raw_preservation': {
            'original_files': '只读保留',
            'notes': '原文保留',
            'quarantine': '完整 raw_json',
        },
    }


MEMBER_RAW = {
    'hy_id': 'QH00000001', 'nm': '测试', 'mobile': '130****0000',
    'birth': '1990-01-01', 'join_dt': '2025/03/16',
    'create_tm': '2025-03-16 10:00:00', 'lv': '普通', 'stat': '1',
    'src_ch': '门店', 'reg_shop': '9801', 'reg_dev': 'abc',
    'tag': '母婴-0到3岁,勿打电话-先留言,待核新品',
}
SHOP_RAW = {'shop_cd': '9801', 'shop_nm': '测试店', 'area': '华东',
            'open_dt': '2023-06-01', 'shop_stat': '营业'}


def build_tables(member_raws=(MEMBER_RAW,), shop_raws=(SHOP_RAW,),
                 order_raws=(), card_raws=()):
    def rows(filename, raws):
        return [{'source_file': filename, 'source_row': index + 1, 'raw': raw}
                for index, raw in enumerate(raws)]

    tables = {
        'crm_member_export.csv': {
            'fields': list(MEMBER_RAW),
            'rows': rows('crm_member_export.csv', member_raws),
        },
        'crm_shop.csv': {
            'fields': list(SHOP_RAW),
            'rows': rows('crm_shop.csv', shop_raws),
        },
        'crm_order_export.csv': {
            'fields': ['ord_no', 'hy_id', 'shop_cd', 'ord_tm', 'ord_stat',
                       'amt_total', 'amt_pay', 'amt_rfd', 'qty', 'ch'],
            'rows': rows('crm_order_export.csv', order_raws),
        },
        'crm_card_export.csv': {
            'fields': ['card_no', 'hy_id', 'card_kind', 'st_dt', 'ed_dt',
                       'stop_dt', 'pay_amt'],
            'rows': rows('crm_card_export.csv', card_raws),
        },
    }
    return tables


def run_adapt(tables):
    with tempfile.TemporaryDirectory() as temp:
        tags = Path(temp) / 'tags.txt'
        tags.write_text('母婴-0到3岁\n价格敏感\n', encoding='utf-8')
        context = {'rules_dir': temp, 'data_version': 'test-v1'}
        return solution.adapt(tables, build_rules(), context)


def order_raw(**overrides):
    raw = {
        'ord_no': 'O00000001', 'hy_id': 'QH00000001', 'shop_cd': '9801',
        'ord_tm': '2026-08-03 10:33:20', 'ord_stat': '已支付',
        'amt_total': '99.90', 'amt_pay': '79.90', 'amt_rfd': '0.00',
        'qty': '2', 'ch': '门店',
    }
    raw.update(overrides)
    return raw


class LegalTagTests(unittest.TestCase):
    def test_legal_tag_kept_and_notes_classified(self):
        result = run_adapt(build_tables())
        self.assertEqual(
            result['tables']['member_tags'],
            [{'member_id': 'QH00000001', 'tag': '母婴-0到3岁'}])
        notes = result['tables']['member_notes']
        by_text = {note['note_text']: note['category'] for note in notes}
        self.assertEqual(by_text['勿打电话-先留言'], '触达限制')
        self.assertEqual(by_text['待核新品'], '其他')
        for note in notes:
            self.assertEqual(
                note['raw_text'], '母婴-0到3岁,勿打电话-先留言,待核新品')
            self.assertEqual(note['source_field'], 'tag')

    def test_hyphenated_tag_not_split(self):
        raw = dict(MEMBER_RAW, tag='母婴-0到3岁')
        result = run_adapt(build_tables(member_raws=(raw,)))
        self.assertEqual(
            result['tables']['member_tags'],
            [{'member_id': 'QH00000001', 'tag': '母婴-0到3岁'}])
        self.assertEqual(result['tables']['member_notes'], [])


class QuarantineTests(unittest.TestCase):
    def test_orphan_order_quarantined_with_raw_json(self):
        orphan = order_raw(ord_no='O00000002', hy_id='QH99999999')
        result = run_adapt(build_tables(order_raws=(order_raw(), orphan)))
        self.assertEqual(len(result['tables']['quarantine']), 1)
        quarantined = result['tables']['quarantine'][0]
        self.assertEqual(quarantined['reason_code'], 'UNLINKED_ACCOUNT')
        self.assertEqual(quarantined['source_row'], 2)
        self.assertEqual(json.loads(quarantined['raw_json']), orphan)
        counts = result['record_counts']['order']
        self.assertEqual(counts, {'read': 2, 'accepted': 1,
                                  'quarantined': 1, 'deduplicated': 0})

    def test_duplicate_order_row_deduplicated(self):
        first = order_raw()
        second = dict(first)
        result = run_adapt(build_tables(order_raws=(first, second)))
        counts = result['record_counts']['order']
        self.assertEqual(counts['deduplicated'], 1)
        self.assertEqual(counts['accepted'], 1)
        self.assertEqual(len(result['tables']['orders']), 1)

    def test_staff_card_quarantined(self):
        card = {'card_no': 'C00000001', 'hy_id': 'QH00000001',
                'card_kind': '员工卡', 'st_dt': '2025-01-01',
                'ed_dt': '2026-01-01', 'stop_dt': '', 'pay_amt': '0.00'}
        result = run_adapt(build_tables(card_raws=(card,)))
        self.assertEqual(result['tables']['cards'], [])
        self.assertEqual(
            result['tables']['quarantine'][0]['reason_code'],
            'UNSUPPORTED_CARD_TYPE')

    def test_renamed_card_type_normalized(self):
        card = {'card_no': 'C00000002', 'hy_id': 'QH00000001',
                'card_kind': '悦享卡（年）', 'st_dt': '2025-01-01',
                'ed_dt': '2026-01-01', 'stop_dt': '', 'pay_amt': '199.00'}
        result = run_adapt(build_tables(card_raws=(card,)))
        self.assertEqual(result['tables']['cards'][0]['card_type'], '悦享年卡')
        self.assertEqual(result['tables']['cards'][0]['card_paid_cents'], 19900)


class MoneyTests(unittest.TestCase):
    def test_yuan_to_cents_conversion(self):
        result = run_adapt(build_tables(order_raws=(order_raw(),)))
        order = result['tables']['orders'][0]
        self.assertEqual(order['gross_cents'], 9990)
        self.assertEqual(order['paid_cents'], 7990)
        self.assertEqual(order['refund_cents'], 0)

    def test_refund_exceeds_paid_quarantined(self):
        bad = order_raw(ord_no='O00000003', amt_pay='50.00', amt_rfd='60.00')
        result = run_adapt(build_tables(order_raws=(order_raw(), bad)))
        self.assertEqual(
            result['tables']['quarantine'][-1]['reason_code'],
            'REFUND_EXCEEDS_PAID')
        self.assertEqual(len(result['tables']['orders']), 1)

    def test_date_formats_normalized(self):
        raw = dict(MEMBER_RAW, join_dt='20250316')
        result = run_adapt(build_tables(member_raws=(raw,)))
        self.assertEqual(result['tables']['members'][0]['registered_at'],
                         '2025-03-16')

    def test_lowercase_store_code_normalized(self):
        raw = dict(MEMBER_RAW, reg_shop='j946', tag='')
        shop = dict(SHOP_RAW, shop_cd='J946')
        result = run_adapt(build_tables(member_raws=(raw,), shop_raws=(shop,)))
        self.assertEqual(len(result['tables']['members']), 1)
        self.assertEqual(result['tables']['members'][0]['home_store_id'], 'J946')
        self.assertEqual(result['tables']['quarantine'], [])

    def test_stat_zero_maps_to_inactive(self):
        raw = dict(MEMBER_RAW, stat='0', tag='')
        result = run_adapt(build_tables(member_raws=(raw,)))
        self.assertEqual(result['tables']['members'][0]['account_status'],
                         '未激活')


class DeterminismTests(unittest.TestCase):
    def test_repeat_run_identical(self):
        tables = build_tables(order_raws=(
            order_raw(),
            order_raw(),
            order_raw(ord_no='O00000004', hy_id='QH99999999'),
        ))
        first = run_adapt(tables)
        second = run_adapt(tables)
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
