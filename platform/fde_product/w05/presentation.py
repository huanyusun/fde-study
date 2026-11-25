"""Member fact presentation bounded by current structured observations.

No inference from an empty cohort to financial quarantine or company identity.
No prose rewrite: the response contract requires these generated fact strings.
"""
import json
from .contracts import CohortRequest

def text(value):
    return '未知／未提供' if value is None else str(value)

def attribute_text(attributes, field, value):
    """Explain a scalar using explicit source conflicts, without resolving them."""
    conflicts = attributes.get('conflicts', {})
    if isinstance(conflicts, dict):
        values = conflicts.get(field, [])
    elif isinstance(conflicts, list):
        values = [value for item in conflicts if item.get('field') == field
                  for value in item.get('values', [])]
    else:
        values = []
    if not isinstance(values, list):values = []
    values = list(dict.fromkeys(str(v) for v in values if v is not None and str(v)))
    if len(values) < 2:return text(value)
    source = '来源值冲突 ' + json.dumps(values, ensure_ascii=False)
    return source + ('；当前未选定统一值' if value is None else
                     '；当前呈现值 ' + text(value) + '，不表示来源已一致')

def buyer_count_text(result):
    """Only W05's ungrouped buyer_count has this financial-entity summary.
    Numeric results come from this observation, never from a prompt or fixture.
    Other metrics, customer grains, grouping, clarification/errors stay unchanged.
    """
    intent = result.get('intent', {})
    if (result.get('entity_semantics') != 'verified_person_with_unresolved_source_buckets'
        or result.get('precise_person_total_acceptance') != 'pending'
        or result.get('status') not in ('ok', 'partial')
        or intent.get('metrics') != ['buyer_count'] or intent.get('group_by')
        or result.get('columns') != ['buyer_count']
        or len(result.get('rows', [])) != 1):return None
    row = result['rows'][0]
    if len(row) != 1 or type(row[0]) is not int or row[0] < 0:return None
    return (f"本轮购买财务实体数（buyer_count）为 {row[0]}。"
            f"统计窗口 [{intent['start']},{intent['end']})，按当轮工具的筛选条件汇总，未按维度分组。\n"
            "统计粒度为已核实统一会员与未决来源独立财务桶；有效净购买条件为 paid 且实付减退款大于零，"
            "按 member_id 去重，取消和全额退款不计；沿用原公式，运营排除不扣减经营记录。\n"
            "此数不是已确认自然人数，未决来源桶不能当作已核实自然人；精确自然人数及相关分母仍待补证，"
            "precise_person_total_acceptance=pending。该指标不证明身份已全量核实，也不构成实际联系授权。")

def follow_up_text(member):
    requirements = member.get('follow_up_requirements', [])
    if not requirements:
        return '当前接口未列出待补证事项；不另增渠道确认待办。'
    return '当前待补证事项：' + '；'.join(
        f"{item['topic']}，来源账户 {','.join(item['source_ids']) or '见原限制证据'}，找{item['owner']}：{item['question']}"
        for item in requirements)

def recency_text(request):
    if request.dormant_days is not None and request.active_within_days is not None:
        return f'最近有效购买距参考日满 {request.dormant_days} 天且不足 {request.active_within_days} 天'
    if request.dormant_days is not None:return f'最近有效购买距参考日满 {request.dormant_days} 天'
    if request.active_within_days is not None:return f'最近有效购买距参考日不足 {request.active_within_days} 天'
    return '未设置最近有效购买间隔条件'

def store_text(request):
    if request.store_ids is not None:return '、'.join(request.store_ids) + '（多家门店，任一门店有注册关系即在范围内，同一人只列一次）'
    return text(request.store_id) if request.store_id else '全公司范围'

def added_conditions_text(request, r):
    """Clauses for conditions introduced after 20261013.2; empty for requests that use none of them."""
    parts = []
    if request.tiers is not None:parts.append('会员等级限 ' + '、'.join(request.tiers))
    if request.registered_from is not None or request.registered_before is not None:
        parts.append('注册日期' + '、'.join(([f'不早于 {request.registered_from}'] if request.registered_from is not None else []) + ([f'早于 {request.registered_before}'] if request.registered_before is not None else [])))
    c = request.comparison
    if c is not None:
        unit = r.get('aggregate_evidence',{}).get('units',{}).get(c.metric,'原指标单位')
        parts.append(f"两期对比 {c.metric}：基期 [{c.baseline_start},{c.baseline_end}) 对本期 [{request.start},{request.end})，{'下降' if c.direction=='decrease' else '上升'}不少于 {c.min_ratio}（按基期值的比例）" + (f'，基期值不少于 {c.min_baseline_value}（{unit}）' if c.min_baseline_value is not None else ''))
    return ''.join('，' + part for part in parts)

def cohort_text(observation):
    r = observation['result']; request = CohortRequest.model_validate(observation['args'])
    page = r['page']; total = page['total']; returned = page['returned']
    conditions = '、'.join(f"{f.metric} {f.op} {f.value}（{r.get('aggregate_evidence',{}).get('units',{}).get(f.metric,'原指标单位')}）" for f in request.metric_filters) or '未单独设置指标条件'
    lines = [f"本轮按来源账户注册门店 {store_text(request)}、渠道 {text(request.channel)} 做只读候选分析。参考日 {request.reference_date}，指标窗口 [{request.start},{request.end})，条件 {conditions}，{recency_text(request)}{added_conditions_text(request, r)}；运营排除和限制按程序结果保留。"]
    if returned == 0:
        lines.append('本页为空。' + ('当前筛选的候选总集为空。' if total == 0 else f'当前筛选候选总集有 {total} 名，不能把空页称为空名单。'))
    else:
        lines.append(f'本页有 {returned} 名渠道复核候选，候选总集有 {total} 名。')
    lines.append(f"分页 offset={page['offset']}、limit={page['limit']}、total={total}、returned={returned}、complete={page['complete']}、next_offset={('无下一页' if page.get('next_offset') is None else page['next_offset'])}；只有分页完整时才能称本页覆盖全部候选。")
    lines.append(f"当前筛选范围内：条件命中 {r['condition_hit_count']} 名，运营排除 {r['operational_excluded_count']} 名，待核会员 {len(r.get('unknown_members',[]))} 名、阻断会员 {len(r.get('blocked_members',[]))} 名、未决身份来源 {len(r.get('unresolved_sources',[]))} 个。上述集合只指当前条件／注册门店范围，不代表全公司无待核或无未决身份。")
    if r.get('attribute_conditions', {}).get('applied'):
        pending = r.get('attribute_pending_members', {})
        lines.append(f"其余条件满足、但所要求的属性未知的已核实会员：等级未知 {len(pending.get('tier',[]))} 名，注册日期未知 {len(pending.get('registered_at',[]))} 名。他们不计入条件命中，也没有被当作不满足条件；其中未被运营排除、所查渠道未被阻断的已并入待核会员。等级在来源冲突或没有记录时为未知，注册日期取来源 CRM 已知入会日期的最早值，POS 独有会员为未知。")
    comparison = r.get('comparison_condition')
    if comparison:
        lines.append(f"两期对比只在基期有 {comparison['metric']} 记录的会员中进行，共 {comparison['baseline_candidates']} 个；基期值不大于 0 的 {comparison['non_positive_baseline']} 个不计算比例，未入选" + (f"；基期值低于门槛的 {comparison['below_min_baseline_value']} 个未入选" if comparison.get('min_baseline_value') is not None else '') + f"。满足变化幅度的 {comparison['comparison_hits']} 个；本期没有该指标记录的按 0 计。以上人数未扣除门店、等级、身份等其他条件。")
    scope = r.get('candidate_scope', {})
    if scope.get('zero_value_members_omitted'):
        lines.append(f"本次只在指标窗口内有相应指标记录的会员中筛选。{'、'.join(scope['metrics_whose_conditions_hold_at_zero'])} 的条件按 0 计算也成立，但窗口内没有记录的会员不在结果里，这部分人没有被统计，不能把本名单称为满足该条件的全部会员。")
    recency = request.dormant_days is not None or request.active_within_days is not None
    lines.append((f"最近有效购买判断窗口覆盖={r.get('coverage_complete')}，仅表示该窗口的覆盖条件；" if recency else '本次未设置最近有效购买间隔条件，不涉及该判断窗口的覆盖；') + f"本次圈选没有核查财务隔离记录，不判断隔离记录是否存在或其数量。未决身份来源空集不能证明没有财务隔离记录。")
    notice = r.get('range_notice', {})
    if 'registration_unknown_company_people' in notice:
        lines.append(f"全公司 {notice['registration_unknown_company_people']} 名已核实会员的注册门店关系未知；这些人不能确定属于或不属于所查门店，未重复列入这些门店的待核名单。" if request.store_ids is not None else f"全公司 {notice['registration_unknown_company_people']} 名已核实会员的注册门店关系未知；这些人不能确定属于或不属于本店，未重复列入单店待核名单。" if notice.get('store_query_omits_unknown_registration') else f"全公司注册门店关系未知范围为 {notice['registration_unknown_company_people']} 名已核实会员，未知关系保留。")
    for member in r.get('members', []):
        compared = member.get('comparison')
        lines.append(f"候选 {member['member_id']}：窗口指标 {json.dumps(member['metric_values'],ensure_ascii=False)}，最近有效购买 {text(member['last_effective_purchase'])}，间隔 {text(member['dormant_days'])} 天" + (f"；{compared['metric']} 基期 {compared['baseline_value']}、本期 {compared['current_value']}、变化比例 {compared['change_ratio']}" if compared else '') + '。')
    lines.append('名单只供业务复核，未发现限制不等于联系授权；actual_contact_authorized=false，不执行联系。空候选不另编营销动作。')
    return '\n'.join(lines)

def member_text(member, relations, include_orders):
    a=member['attributes'];p=member['policy'];lines=[f"会员 {member['member_id']}：身份 {a['identity_status']}，姓名 {attribute_text(a, 'name', a['display_name'])}；原姓名 {json.dumps(a.get('names',[]),ensure_ascii=False)}，脱敏手机 {json.dumps(a.get('masked_mobiles',[]),ensure_ascii=False)}，等级 {attribute_text(a, 'tier', a['tier'])} 仅作知识上下文，不参与资格判断。"]
    lines.append(f"已知来源注册门店 {json.dumps(a['registered_stores'],ensure_ascii=False)}；购买门店不能替代注册门店。最近有效购买 {text(member['last_effective_purchase'])}，间隔 {text(member['dormant_days'])} 天；沉睡阈值 {member['dormancy_condition']['threshold_days']} 天，gte，匹配 {text(member['dormancy_condition']['matches'])}，仅限最近有效购买条件，不推断完整圈选资格。")
    lines.append(f"渠道限制 {json.dumps(p['channels'],ensure_ascii=False)}；会员排除={p['member_excluded']}，账户排除={json.dumps(p['account_exclusions'],ensure_ascii=False)}，运营待核={json.dumps(p['pending_verifications'],ensure_ascii=False)}；详情建议安全条件={member['recommendation_allowed']}，实际参与判断的条件={json.dumps(member['recommendation_decision']['conditions'],ensure_ascii=False)}。未发现限制不等于授权，禁止或未知不能推荐相应渠道联系，不提供绕行动作。")
    for e in p.get('restriction_evidence', []):
        lines.append(f"限制原文 {e['source_file']} 第 {e['source_row']} 行／{e['source_id']}：{e['quote']}；范围 {e['scope']}，规则 {e['rule_version']}。补充确认原记录：{json.dumps(e.get('confirmation_records',[]),ensure_ascii=False)}")
    if relations:
        for source in relations['accounts']:
            lines.append(f"来源账户 {source['source_id']}，{source['source_file']} 第 {source['source_row']} 行，注册门店 {text(source['registered_store'])}。")
        lines.append(f"实际订单本页 {relations['page']['returned']} 笔／总数 {relations['page']['total']}，分页完整={relations['page']['complete']}；逐笔原值与来源保留在当轮 member_relations。")
        if include_orders:
            for o in relations['orders']:
                provenance=o['provenance'];lines.append(f"订单 {o['order_id']}：{o['ordered_at']}，购买门店 {o['store_id']}，状态 {o['status']}，原价 {o['gross_cents']} 分、实付 {o['paid_cents']} 分、退款 {o['refund_cents']} 分、件数 {o['quantity']}，渠道 {o['channel']}；来源 {provenance['source_id']}／{provenance['source_file']} 第 {provenance['source_row']} 行。")
        if not relations['cards']:lines.append('当轮未返回卡记录，不推断卡是否存在或全局隔离数量。')
        for card in relations['cards']:
            s=card['semantics'];lines.append(f"卡 {s['card_id']}（{s['card_kind']}）：购卡金额 {text(s['purchase_amount']['value'])} CNY／元，生效日 {text(s['effective_date']['value'])}，到期日 {text(s['expiry_date']['value'])}，停卡日 {text(s['stop_date']['value'])}；{card['source_id']}／{card['source_file']} 第 {card['source_row']} 行，{s['financial_status']}。购卡金额不自动计入订单净消费，不推断日期边界或当前可用状态。")
    lines.append(follow_up_text(member))
    lines.append('本轮未获实际联系授权，只有数据支持的当前补证事项列为待办；业务复核边界保持。')
    return '\n'.join(lines)

def fact_summary(observations):
    cohorts=[o for o in observations if o['name']=='member_cohort' and 'result_scope' in o['result']]
    members=[o['result'] for o in observations if o['name']=='get_member' and o['result'].get('presentation_scope')=='current_member_facts_v1']
    metric_lines=[buyer_count_text(o['result']) for o in observations if o['name']=='query_metrics']
    metric_lines=[line for line in metric_lines if line is not None]
    if not cohorts and not members and not metric_lines:return None
    lines=metric_lines + ([cohort_text(cohorts[-1])] if cohorts else [])
    relations={o['result']['member_id']:o['result'] for o in observations if o['name']=='member_relations' and 'accounts' in o['result']}
    lines.extend(member_text(m,relations.get(m['member_id']),not cohorts) for m in members)
    knowledge=[h for o in observations if o['name']=='retrieve_knowledge' for h in o['result'].get('hits',[]) if h.get('applicability')=='applicable']
    if knowledge:lines.append('已取得适用知识依据：'+','.join(h['node_id'] for h in knowledge)+'；来源、有效期和原片段保留在当轮检索证据。')
    return '\n'.join(lines)

def suggestion_text(member_id,observations):
    cohorts=[o['result'] for o in observations if o['name']=='member_cohort' and 'result_scope' in o['result']]
    members=[o['result'] for o in observations if o['name']=='get_member' and o['result'].get('member_id')==member_id and o['result'].get('presentation_scope')=='current_member_facts_v1']
    if not cohorts or not members:return None
    cohort=cohorts[-1];member=members[-1];values=next((m for m in cohort.get('members',[]) if m['member_id']==member_id),None)
    if not values:return None
    return f"仅供业务复核的 {text(cohort['channel'])} 渠道候选 {member_id}：窗口指标 {json.dumps(values['metric_values'],ensure_ascii=False)}，最近有效购买 {text(values['last_effective_purchase'])}，间隔 {text(values['dormant_days'])} 天；详情安全条件 {member['recommendation_allowed']}。建议以附列适用知识证据供业务人员复核，不代表已获联系授权，不执行触达。{follow_up_text(member)} 补证提醒不新增资格条件。"
