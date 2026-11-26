"""Default W05 extension: existing MetricFlow and member tools in the same chat."""
import hashlib,json,re
from pathlib import Path
from ..metrics.integration import UpgradedAgent
from ..models import ModelError,public_message
from .runtime import MemberService,NAMES,digest
from .semantics import critical_facts,VALIDATION_SCOPE
from .presentation import fact_summary,suggestion_text

REASONS=['program_blocked','facts_pending','no_applicable_knowledge','not_requested','evidence_missing']
# Reasons that leave a fact or a step open: the answer can record them but cannot be completed.
OPEN_REASONS={'facts_pending','no_applicable_knowledge','evidence_missing'}

def parse_final(content):
    raw=(content or '').strip();match=re.fullmatch(r'```(?:json)?\s*\n([\s\S]*?)\n```',raw,re.I)
    return json.loads(match.group(1) if match else raw)

def cohort_candidates(cohort):
    return list(dict.fromkeys(list(cohort.get('member_ids',[]))+list(cohort.get('unknown_members',[]))+list(cohort.get('blocked_members',[]))))

def final_contract(observations):
    ids=[o['result']['evidence_id'] for o in observations if o['result'].get('evidence_id')]
    cited={'type':'array','items':{'type':'string','enum':ids},'minItems':1}
    properties={'status':{'enum':['completed','incomplete','clarification','refused']},'summary':{'type':'string'},'evidence_ids':cited,'recommendations':{'type':'array','items':{'type':'object','properties':{'member_id':{'type':'string'},'suggestion':{'type':'string'},'evidence_ids':cited,'knowledge_node_ids':{'type':'array','items':{'type':'string'},'minItems':1}},'required':['member_id','suggestion','evidence_ids','knowledge_node_ids'],'additionalProperties':False}}}
    facts=critical_facts(observations)
    if any(facts.values()):properties['critical_facts']={'type':'object','const':facts}
    summary=fact_summary(observations)
    if summary is not None:properties['summary']={'type':'string','const':summary}
    required=list(properties)
    cohorts=[o['result'] for o in observations if o['name']=='member_cohort' and 'member_ids' in o['result']]
    if cohorts:
        cohort=cohorts[-1]
        for mid in cohort['member_ids']:
            suggestion=suggestion_text(mid,observations)
            if suggestion is not None:
                properties['recommendations']['items'].setdefault('allOf',[]).append({'if':{'properties':{'member_id':{'const':mid}}},'then':{'properties':{'suggestion':{'const':suggestion}}}})
        for key,source in [('member_ids','member_ids'),('unknown_member_ids','unknown_members'),('blocked_member_ids','blocked_members'),('unresolved_source_ids','unresolved_sources')]:
            values=cohort.get(source,[])
            if key=='unresolved_source_ids':values=[v['source_id'] if isinstance(v,dict) else v for v in values]
            properties[key]={'type':'array','items':{'type':'string'},'const':values};required.append(key)
        # Candidate disposition: the model states whether this turn asks for recommendations; when it does, every
        # candidate on the page gets a recommendation or a reasoned non-recommendation (validate_final checks coverage).
        # An empty cohort (empty page, unsupported condition) has nobody to dispose of and keeps the old contract.
        candidates=cohort_candidates(cohort)
        if candidates:
            properties['task_scope']={'type':'object','properties':{'recommendations_requested':{'type':'boolean'},'statement':{'type':'string'}},'required':['recommendations_requested','statement'],'additionalProperties':False};required.append('task_scope')
            item={'type':'object','properties':{'member_id':{'type':'string','enum':candidates},'reason_code':{'enum':REASONS},'evidence_ids':cited,'explanation':{'type':'string'}},'required':['member_id','reason_code','evidence_ids','explanation'],'additionalProperties':False}
            properties['non_recommendations']={'type':'array','items':item,'description':'recommendations_requested=false 时留空数组，不逐人列 not_requested；为 true 时，本页名单里没有建议的人各写一条。'};required.append('non_recommendations')
    else:properties['recommendations']['maxItems']=0
    if 'task_scope' not in properties:
        # Nobody to dispose of (no cohort, an empty page, a refused or unsupported selection): the two disposition fields
        # are optional and carry nothing, so a model that still states the task scope is not failed on the format alone.
        properties['task_scope']={'type':'object','properties':{'recommendations_requested':{'type':'boolean'},'statement':{'type':'string'}},'required':['recommendations_requested','statement'],'additionalProperties':False}
        properties['non_recommendations']={'type':'array','maxItems':0}
    if not cohorts:
        # No selection result this turn (refused, failed or never called): the set fields may appear only empty.
        for key in ['member_ids','unknown_member_ids','blocked_member_ids','unresolved_source_ids']:properties[key]={'type':'array','maxItems':0}
    return {'type':'object','properties':properties,'required':required,'additionalProperties':False}

def failed_summary(schema,code):
    """What the reader sees when the answer fails validation: the program's fixed summary of this turn when the contract
    has one, otherwise one fixed sentence. The model's own text stays in model_claim only."""
    fixed=schema.get('properties',{}).get('summary',{}).get('const') if isinstance(schema,dict) else None
    return fixed if isinstance(fixed,str) else f'这一轮的回答没有通过程序校验（{code}），不能采用。请换个问法重新提问；问题还在的话，把校验码告诉维护人员。'

def validate_disposition(result,cohort,recommendations,good,citations):
    """Every candidate of the cited cohort page is either recommended or not, with a reason the evidence supports."""
    scope=result.get('task_scope')
    if not cohort_candidates(cohort) and not result.get('non_recommendations'):return True,None
    if not isinstance(scope,dict) or not isinstance(scope.get('recommendations_requested'),bool):return False,'TASK_SCOPE_REQUIRED'
    requested=scope['recommendations_requested'];non=result.get('non_recommendations',[])
    if not isinstance(non,list) or not all(isinstance(x,dict) for x in non):return False,'NON_RECOMMENDATIONS_INVALID'
    expected=list(cohort['member_ids']);unknown=set(cohort.get('unknown_members',[]));blocked=set(cohort.get('blocked_members',[]))
    rec_ids=[x.get('member_id') for x in recommendations];non_ids=[x.get('member_id') for x in non]
    if len(set(rec_ids))!=len(rec_ids) or len(set(non_ids))!=len(non_ids) or set(rec_ids)&set(non_ids):return False,'CANDIDATE_DISPOSITION_DUPLICATE'
    if not set(rec_ids)<=set(expected):return False,'RECOMMENDATION_SET_MISMATCH'
    if not set(non_ids)<=set(expected)|unknown|blocked:return False,'NON_RECOMMENDATION_OUTSIDE_COHORT'
    if not requested:
        if recommendations:return False,'RECOMMENDATIONS_NOT_REQUESTED'
        if any(x.get('reason_code')!='not_requested' for x in non):return False,'NON_RECOMMENDATION_REASON_UNSUPPORTED'
    elif set(expected)-set(rec_ids)-set(non_ids):return False,'CANDIDATE_NOT_DISPOSED'
    for x in non:
        mid=x.get('member_id');reason=x.get('reason_code');ids=x.get('evidence_ids',[])
        if reason not in REASONS or not isinstance(x.get('explanation'),str):return False,'NON_RECOMMENDATION_INVALID'
        if not isinstance(ids,list) or not ids or any(e not in good for e in ids):return False,'NON_RECOMMENDATION_CITATION_REQUIRED'
        cited=[good[e] for e in ids]
        member=next((o['result'] for o in cited if o['name']=='get_member' and o['result'].get('member_id')==mid),None)
        from_cohort=cohort['evidence_id'] in ids
        if reason=='not_requested':
            ok=not requested and from_cohort
        elif reason=='program_blocked':
            conditions=(member or {}).get('recommendation_decision',{}).get('conditions',{})
            channel=((member or {}).get('recommendation_context') or {}).get('channel')
            channels=((member or {}).get('policy') or {}).get('channels',{})
            ok=(from_cohort and mid in blocked) or (member is not None and member.get('recommendation_allowed') is not True and (conditions.get('member_not_excluded') is False or conditions.get('some_source_account_not_excluded') is False or (channel in channels and channels[channel]=='blocked') or (channel=='all' and 'blocked' in channels.values())))
        elif reason=='facts_pending':
            ok=(from_cohort and mid in unknown) or (member is not None and member.get('recommendation_allowed') is not True)
        elif reason=='no_applicable_knowledge':
            knowledge=[o['result'] for o in cited if o['name']=='retrieve_knowledge']
            ok=member is not None and bool(knowledge) and not any(h.get('applicability')=='applicable' for k in knowledge for h in k.get('hits',[]))
        else:ok=True
        if not ok:return False,'NON_RECOMMENDATION_REASON_UNSUPPORTED'
        if reason in OPEN_REASONS and result.get('status')=='completed':return False,'NON_RECOMMENDATION_REQUIRES_INCOMPLETE'
    return True,None

def validate_final(result,observations):
    if not isinstance(result,dict) or result.get('status') not in ['completed','incomplete','clarification','refused']:return False,'FINAL_SCHEMA'
    citations=result.get('evidence_ids',[])
    if not isinstance(citations,list) or not all(isinstance(x,str) for x in citations):return False,'FINAL_CITATIONS'
    good={o['result'].get('evidence_id'):o for o in observations if o['result'].get('status') in ['ok','conflict','partial','unknown','not_found','unsupported','error','clarify']}
    if any(e not in good for e in citations):return False,'UNKNOWN_EVIDENCE'
    if result['status'] in ['completed','incomplete'] and (not observations or not citations):return False,'CURRENT_TURN_EVIDENCE_REQUIRED'
    if result['status']=='completed':
        for o in observations:
            r=o['result']
            if r.get('status')!='ok' or r.get('coverage_complete') is False or r.get('page',{}).get('complete') is False:return False,'PARTIAL_RESULT_CANNOT_COMPLETE'
            if r.get('evidence_id') not in citations:return False,'REQUESTED_TOOL_EVIDENCE_OMITTED'
    cohorts=[o['result'] for o in observations if o['name']=='member_cohort' and 'member_ids' in o['result']]
    recommendations=result.get('recommendations',[])
    if not isinstance(recommendations,list):return False,'RECOMMENDATIONS_INVALID'
    if not cohorts and (result.get('member_ids') or recommendations):return False,'COHORT_EVIDENCE_REQUIRED'
    if cohorts:
        cohort=cohorts[-1];expected=cohort['member_ids']
        if sorted(result.get('member_ids',[]))!=sorted(expected):return False,'MEMBER_SET_MISMATCH'
        if cohort['evidence_id'] not in citations:return False,'COHORT_CITATION_REQUIRED'
        for key in ['unknown_member_ids','blocked_member_ids','unresolved_source_ids']:
            actual=cohort.get({'unknown_member_ids':'unknown_members','blocked_member_ids':'blocked_members','unresolved_source_ids':'unresolved_sources'}[key],[])
            if key=='unresolved_source_ids':actual=[x['source_id'] if isinstance(x,dict) else x for x in actual]
            if sorted(result.get(key,[]))!=sorted(actual):return False,'BOUNDARY_SET_MISMATCH'
    for recommendation in recommendations:
        mid=recommendation.get('member_id');ids=recommendation.get('evidence_ids',[])
        if not ids or any(e not in good for e in ids):return False,'RECOMMENDATION_CITATION_REQUIRED'
        cited=[good[e] for e in ids]
        if not all(any(o['name']==name and o['result'].get('member_id')==mid for o in cited) for name in ['get_member','member_relations']):return False,'MEMBER_AND_RELATION_EVIDENCE_REQUIRED'
        knowledge=[o['result'] for o in cited if o['name']=='retrieve_knowledge']
        if not knowledge:return False,'KNOWLEDGE_EVIDENCE_REQUIRED'
        member=next(o['result'] for o in cited if o['name']=='get_member' and o['result'].get('member_id')==mid)
        if member.get('recommendation_allowed') is not True:return False,'PROGRAM_POLICY_BLOCK'
        nodes=recommendation.get('knowledge_node_ids',[])
        if not nodes or not all(isinstance(n,str) for n in nodes):return False,'KNOWLEDGE_NODE_CITATION_REQUIRED'
        hits={h['node_id']:h for k in knowledge for h in k.get('hits',[])}
        context=member.get('recommendation_context',{})
        for node in nodes:
            h=hits.get(node)
            if not h or h.get('applicability')!='applicable':return False,'KNOWLEDGE_NOT_APPLICABLE'
            conditions=h.get('source',{}).get('conditions')
            if not isinstance(conditions,dict) or any(k not in context or context[k] not in (v if isinstance(v,list) else [v]) for k,v in conditions.items()):return False,'KNOWLEDGE_PROGRAM_CONTEXT_MISMATCH'
    if cohorts:
        passed,code=validate_disposition(result,cohorts[-1],recommendations,good,citations)
        if not passed:return passed,code

    summary=fact_summary(observations)
    if summary is not None and result.get('summary')!=summary:return False,'FACT_SUMMARY_SCOPE_MISMATCH'
    for recommendation in recommendations:
        suggestion=suggestion_text(recommendation.get('member_id'),observations)
        if suggestion is not None and recommendation.get('suggestion')!=suggestion:return False,'FOLLOW_UP_SCOPE_MISMATCH'
    facts=critical_facts(observations)
    if any(facts.values()) and result.get('critical_facts')!=facts:return False,'CRITICAL_FACTS_MISMATCH'
    return True,'GROUNDED'

class MemberAgent(UpgradedAgent):
    def __init__(self,*args,member_binding,**kwargs):
        self.member_service=MemberService(member_binding)
        configured=kwargs.get('metrics_project')
        if configured and Path(configured).resolve()!=self.member_service.project:raise ValueError('METRICS_MEMBER_CUSTOMER_BINDING_MISMATCH')
        kwargs['metrics_project']=self.member_service.project
        super().__init__(*args,**kwargs)
        self.prompt='你是只读会员运营助手，支持指标问数、会员圈选、详情及关联记录、规则知识。旧指标查询用 query_metrics；会员任务组合四个会员工具。每轮必须取得当轮证据，同一会话支持任务切换和组合。禁止自行写 SQL、计算名单、改条件、忽略未知或执行动作。返回 JSON：status、summary、evidence_ids、recommendations；涉及圈选时另含 member_ids、unknown_member_ids、blocked_member_ids、unresolved_source_ids。完整状态由工具覆盖和分页决定；未知或部分结果用 incomplete。建议逐个附 get_member、member_relations、retrieve_knowledge 的证据，只有程序返回 recommendation_allowed=true 才能建议。knowledge 有适用条件；每个建议含 knowledge_node_ids，逐条引用已返回且适用的知识片段，条件须匹配 get_member 的程序 recommendation_context。没有支持的条件应澄清或拒绝，不能漏条件。指标返回的 answer 和 rows 是证据，不自行补数。当前指标目录：'+json.dumps([{'id':x['id'],'name':x['name'],'unit':x['unit']} for x in self.metrics.catalog],ensure_ascii=False)
        self.prompt+='\n严格输出约定：recommendations 只用于用户明确要求的圈选会员建议；资料查询、限制解释、故障排查和指标任务一律 recommendations=[]。每条建议必须含 member_id、suggestion、evidence_ids（详情、关系、知识三个工具结果的完整 evidence_id）、knowledge_node_ids；禁止用 target/action/basis 替代这些字段。圈选最终必须返回 member_ids、unknown_member_ids、blocked_member_ids、unresolved_source_ids，与最后圈选工具结果逐项一致；空列表也保留。顶层 evidence_ids 引用当轮每个工具结果的完整 evidence_id，不能用 trace_id、节点 ID 或省略前后字符。error/clarify 可用于引用失败或澄清证据，但失败和 partial/unknown 必须 incomplete，不可 completed。未指定渠道不说单一可联系人数，actual_contact_authorized=false 不等于已获联系授权。精确自然人数若程序标为待定，保留待定，不将财务桶算作人。'
        self.prompt+='\n候选处置约定：涉及圈选时必须返回 task_scope（recommendations_requested 布尔值、statement 一句话说明本轮理解的任务）和 non_recommendations。用户要求给建议时 recommendations_requested=true，本页 member_ids 里每人要么有一条 recommendation，要么有一条 non_recommendation，漏一人不能完成；只要名单、不要建议时为 false，recommendations 为空。non_recommendation 含 member_id、reason_code、evidence_ids、explanation：program_blocked 引用程序禁止或排除的当轮证据；facts_pending 引用待核事实，结果须 incomplete；no_applicable_knowledge 引用同会员详情和本轮知识检索且无适用片段，结果须 incomplete；evidence_missing 表示还缺工具证据，结果须 incomplete；not_requested 只在 recommendations_requested=false 时用。不能为了完成而把需要建议的任务声明成不需要。recommendations_requested=false 时 non_recommendations 留空数组，不逐人列 not_requested。圈选为空、被拒或没有圈选时不需要这两个字段。'
        self.prompt+='\n最终助手消息仅包含一个 JSON 对象，第一字符为 {，最后字符为 }。JSON 之外不得有说明、前言、后记或 Markdown 围栏。summary 写清结果和边界，其余说明也放入 summary；建议对象严格采用上面的字段。此格式是运行入口的输出契约。'
        self.formal_result_contract=self.member_service.dataset.get('grain_version')=='w05-verified-person-and-unresolved-source-1'
        if self.formal_result_contract:self.prompt+='\n正式青禾结果优先调用 submit_member_analysis；也可输出完全满足同一 schema 的纯 JSON，所有必填集合和当前证据都须完整，禁止仅在 summary 描述集合。该响应工具只提交分析结果，不执行业务动作。按工具 schema 的必填字段和当前工具证据填写；圈选 ID 与边界集合由当前工具结果约束，空列表也必填。先取得业务证据，响应工具才会出现。历史引用不能混入本轮。'
        self.prompt+='\nsummary 简洁说明用户本轮询问的事实与必要边界。沉睡条件按实际间隔天数大于等于阈值判断（gte），直接引用 get_member.dormancy_condition.matches；未知保持未知。会员详情只说明最近消费条件及限制，不能推断完整圈选资格；完整资格必须引用当轮 member_cohort。未做圈选时不主动说属于或不属于主名单。只引用返回的卡记录，不凭空添加卡种、年限或其他业务解释；cards=[] 只说明未返回卡记录。'
        self.prompt+='\n关键事实契约：当响应 schema 含 critical_facts，按当前工具原值完整填写卡语义及 recommendation_decisions。summary 中卡的购卡金额和单位引用 purchase_amount；生效日引用 effective_date，到期日引用 expiry_date，停卡日引用 stop_date。缺失／非法为未知，不用金额表示日期，也不由卡种推定年限。原始来源及 W04 隔离状态保留；卡金额不自动计入订单净消费。程序详情资格依据仅引用 recommendation_decision.conditions；recommendation_context 只供知识适用，等级等上下文不能说成资格条件，详情安全条件不等于完整主条件圈选。\n业务表达：名单称渠道复核候选，不称已授权可联系人数；未发现限制不等于授权。注册门店与身份来源补证找老周，联系渠道范围确认找小林，分开说清。含未决来源的购买统计直接称购买财务实体，不先称已验证自然人数。summary 用易读业务语言，不复述无助判断的内部校验字段；必要的限制原文、来源行、确认状态、金额和日期保留。GROUNDED／validation_passed 只表示所列结构、证据与程序约束通过，未验证全部自由文字事实或完成业务验收。'
        self.prompt+='\n补证事项以 get_member.follow_up_requirements 的具体 topic、source_ids 和 owner 为准：身份 verified 时保持已核实关系，不能因注册门店未知再要求核实是否同一会员。注册门店待核须明确是哪一来源账户找老周，渠道范围待核须携原限制记录找小林。关联核查摘要保留已返回的实际订单要点、最近有效购买与沉睡条件，以及原卡来源文件和行；无需重复所有程序字段或校验代码。购买统计首句直接称购买财务实体数；后续解释已核实统一会员与未决来源桶，不先称自然人数。'
        self.prompt+='\n会员事实说明由当轮结构化结果生成。最终 schema 的 summary／suggestion 若带 const，须完整使用该原值，不自由改写；这不是原答替换或字符串删除。空名单、空页、待核／阻断、注册关系未知与财务隔离范围各不相同；圈选未做隔离核查。当前补证事项只按程序列出的实际 topic，不能把角色一般分工增加为当前待办。模型继续取得工具、选择适用知识并提交状态／集合／引用；无数据支持的额外补证或隔离结论会被契约拒绝。'
        self.prompt_hash=hashlib.sha256(self.prompt.encode()).hexdigest()
    def schemas(self,action_mode):
        return [x for x in super().schemas(False) if x['function']['name']=='query_metrics']+self.member_service.schemas()
    def tool_node(self,state):
        messages=list(state['messages']);obs=list(state['observations']);usage=dict(state.get('usage',{}))
        calls=messages[-1].get('tool_calls',[])
        finals=[c for c in calls if c.get('function',{}).get('name')=='submit_member_analysis']
        if self.formal_result_contract and finals:
            from jsonschema import validate,ValidationError
            result={};passed=False;code='FINAL_TOOL_MUST_BE_SEPARATE'
            try:
                result=json.loads(finals[0]['function']['arguments'])
                if len(calls)==1:
                    validate(result,final_contract(obs));passed,code=validate_final(result,obs)
            except (ValueError,TypeError,KeyError,ValidationError):code='FINAL_TYPED_CONTRACT'
            answer={**result,'validation_passed':passed,'validation_code':code,'validation_scope':VALIDATION_SCOPE}
            if not passed:answer.update(status='incomplete',summary=failed_summary(final_contract(obs),code),model_claim=result)
            messages.append({'role':'tool','tool_call_id':finals[0]['id'],'content':json.dumps({'accepted':passed,'validation_code':code,'validation_scope':VALIDATION_SCOPE})})
            return {'messages':messages,'observations':obs,'result':answer,'draft':None,'usage':usage}
        for i,c in enumerate(calls):
            name=c.get('function',{}).get('name','');args=None
            try:
                args=json.loads(c['function']['arguments'])
                if i>=8:raise ValueError('TOO_MANY_CALLS')
                if name=='query_metrics':
                    if set(args)!={'question'}:raise ValueError('INVALID_METRIC_ARGUMENTS')
                    history=[{'role':m['role'],'content':m.get('content','')} for m in state['messages'][:-1] if m.get('role') in ['user','assistant'] and not m.get('tool_calls')]
                    result=self.metrics.ask(args['question'],history)
                    result={**result,'evidence_id':digest(result)}
                    for k,v in result.get('model_usage',{}).items():
                        if isinstance(v,(int,float)) and not isinstance(v,bool):usage[k]=usage.get(k,0)+v
                elif name in NAMES:result=self.member_service.call(name,args)
                else:raise ValueError('TOOL_FORBIDDEN')
            except (ValueError,KeyError,TypeError):result={'status':'error','code':'INVALID_ARGUMENTS_OR_TOOL'}
            obs.append({'name':name,'args':args,'result':result,'call_id':c.get('id','invalid')})
            messages.append({'role':'tool','tool_call_id':c.get('id','invalid'),'content':json.dumps(result,ensure_ascii=False)})
        return {'messages':messages,'observations':obs,'draft':None,'usage':usage}
    def model_node(self,state):
        if state.get('result'):return {'result':state['result']}
        if state['steps']>=10:return {'result':{'status':'incomplete','summary':'CALL_LIMIT'}}
        inventory=[{'tool':o['name'],'evidence_id':o['result'].get('evidence_id')} for o in state['observations'] if o['result'].get('evidence_id')]
        turn_rule='这是当前轮唯一允许引用的工具证据清单：'+json.dumps(inventory,ensure_ascii=False)+'。历史会话只用于理解需求；历史轮次的指标证据即使真实，也不得添加到本轮 evidence_ids 或建议中。消费条件及数值直接引用本轮 member_cohort.members；不能用上一轮全公司/月度指标替代个体年度消费。清单为空时先调用工具。保持严格 JSON 及当前轮证据约定。'
        schemas=self.schemas(False)
        if self.formal_result_contract and inventory:schemas=schemas+[{'type':'function','function':{'name':'submit_member_analysis','description':'提交当前轮的只读分析结果；严格按 schema 填写已验证工具的当前集合与证据，不能引用历史轮次；不执行联系。','parameters':final_contract(state['observations'])}}]
        try:message,usage=self.model.complete([{'role':'system','content':self.prompt}]+state['messages']+[{'role':'system','content':turn_rule}],schemas)
        except ModelError as e:return {'result':{'status':'incomplete','summary':e.code},'steps':state['steps']+1}
        message=public_message(message);update={'messages':state['messages']+[message],'steps':state['steps']+1,'usage':{k:state.get('usage',{}).get(k,0)+usage.get(k,0) for k in ['prompt_tokens','completion_tokens','total_tokens']}}
        if not message.get('tool_calls'):
            try:result=parse_final(message.get('content'));passed,code=validate_final(result,state['observations'])
            except (ValueError,TypeError,KeyError):result={};passed=False;code='FINAL_JSON'
            if self.formal_result_contract:
                from jsonschema import validate,ValidationError
                try:validate(result,final_contract(state['observations']))
                except (ValidationError,ValueError,TypeError):passed=False;code='FINAL_TYPED_CONTRACT'
            update['result']={**result,'validation_passed':passed,'validation_code':code,'validation_scope':VALIDATION_SCOPE}
            if not passed:update['result'].update(status='incomplete',summary=failed_summary(final_contract(state['observations']),code),model_claim=result)
        return update
