"""Critical member facts with explicit units, source fields and decision scope.

These facts check structured correspondence, not the truth of arbitrary prose.
"""
from datetime import datetime
from copy import deepcopy
from decimal import Decimal, InvalidOperation

MISSING = {'', '-', 'NULL', '无'}
VALIDATION_SCOPE = {
    'checked': ['current_turn_citations', 'result_status_and_sets',
                'recommendation_policy_and_knowledge', 'structured_critical_facts',
                'candidate_disposition_coverage'],
    'not_checked': ['free_text_fact_correspondence', 'independent_business_acceptance',
                    'task_scope_matches_user_request'],
    'source_review_required': True,
}

def card_value(raw, field, kind):
    text = str(raw.get(field) or '').strip()
    result = {'value': None, 'source_field': field, 'status': 'missing' if text in MISSING else 'invalid'}
    if kind == 'amount':
        result['unit'] = 'CNY'
        if text not in MISSING:
            try:
                value = Decimal(text)
                if value.is_finite() and value * 100 == (value * 100).to_integral_value():
                    result.update(value=format(value, '.2f'), status='known')
            except InvalidOperation:
                pass
    elif text not in MISSING:
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y%m%d', '%Y-%m-%d %H:%M:%S']:
            try:
                result.update(value=datetime.strptime(text, fmt).date().isoformat(), status='known')
                break
            except ValueError:
                pass
    return result

def card_semantics(record, accepted):
    raw = record['raw']
    return {**record, 'semantics': {
        'card_id': raw.get('card_no'), 'card_kind': raw.get('card_kind'),
        'purchase_amount': card_value(raw, 'pay_amt', 'amount'),
        'effective_date': card_value(raw, 'st_dt', 'date'),
        'expiry_date': card_value(raw, 'ed_dt', 'date'),
        'stop_date': card_value(raw, 'stop_dt', 'date'),
        'financial_status': 'accepted_w04_card' if accepted else 'quarantined_w04_card',
        'financial_meaning': '沿用 W04 卡表接受／隔离决定；购卡金额不自动计入订单净消费。',
        'date_boundary_meaning': '原始生效日、到期日、停卡日；未据此推断有效期边界或当前可用状态。',
    }}

def decision_basis(attributes, policy, covered, latest, channel_state):
    conditions = {
        'identity_verified': attributes['identity_status'] == 'verified',
        'member_not_excluded': not policy['member_excluded'],
        'some_source_account_not_excluded': not policy['all_source_accounts_excluded'],
        'no_pending_operational_verification': not bool(policy['pending_verifications']),
        'recent_purchase_coverage_complete': bool(covered),
        'recent_effective_purchase_present': latest is not None,
        'selected_channel_has_no_known_restriction': channel_state == 'no_known_restriction',
    }
    return {'scope': 'detail_recommendation_safety_only; full_cohort_requires_member_cohort',
            'operator': 'all', 'conditions': conditions, 'result': all(conditions.values()),
            'context_only_fields': ['tier'], 'actual_contact_authorized': False}

def follow_up_requirements(attributes, sources, policy, channel_state):
    requirements = []
    unknown_registration = [s['source_id'] for s in sources if not s.get('registered_store')]
    if unknown_registration:
        requirements.append({'topic': 'source_registration', 'owner': '老周',
                             'source_ids': unknown_registration,
                             'question': '补证这些来源账户的注册门店；不能用购买门店替代。'})
    if attributes['identity_status'] != 'verified':
        requirements.append({'topic': 'source_identity', 'owner': '老周',
                             'source_ids': attributes['source_ids'],
                             'question': '核实未决来源身份，不把财务桶当作已核实自然人。'})
    if channel_state == 'unknown':
        requirements.append({'topic': 'contact_channel_scope', 'owner': '小林',
                             'source_ids': sorted({e['source_id'] for e in policy['restriction_evidence'] if e['scope'] == 'unknown'}),
                             'question': '补充确认原限制记录适用的渠道；未知不能作为联系许可。'})
    return requirements

def critical_facts(observations):
    cards, decisions = [], []
    for observation in observations:
        result = observation['result']
        if observation['name'] == 'member_relations':
            for card in result.get('cards', []):
                if 'semantics' in card:
                    cards.append({'evidence_id': result['evidence_id'],
                                  'member_id': result['member_id'],
                                  'source_id': card['source_id'], 'source_file': card['source_file'],
                                  'source_row': card['source_row'], **card['semantics']})
        if observation['name'] == 'get_member' and 'recommendation_decision' in result:
            decisions.append({'evidence_id': result['evidence_id'], 'member_id': result['member_id'],
                              **result['recommendation_decision'],
                              'follow_up_requirements': result.get('follow_up_requirements', [])})
    return deepcopy({'cards': cards, 'recommendation_decisions': decisions})
