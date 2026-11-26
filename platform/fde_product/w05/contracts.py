from datetime import date
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictFloat, model_validator

class Contract(BaseModel):
    model_config=ConfigDict(extra='forbid')

class AggregateFilter(Contract):
    metric: str=Field(pattern=r'^[a-z][a-z0-9_]*$',description='当前指标目录中可按会员计算的指标 ID')
    op: Literal['gte','gt','lte','lt','eq']
    value: Annotated[StrictInt|StrictFloat,Field(allow_inf_nan=False,description='按该指标的原单位填写，金额为分')]

class Page(Contract):
    offset: StrictInt=Field(default=0,ge=0)
    limit: StrictInt=Field(default=100,ge=1,le=1000)

class PurchaseFeatureRequest(Contract):
    member_id: str=Field(min_length=1,max_length=200)
    reference_date: date
    dormant_days: StrictInt=Field(ge=1,le=3650)

class Comparison(Contract):
    metric: str=Field(pattern=r'^[a-z][a-z0-9_]*$',description='用于两期对比的指标 ID；只接受可加总、能按会员计算、非月度类的指标，例如 net_sales_cents')
    baseline_start: date=Field(description='基期起始日（含）')
    baseline_end: date=Field(description='基期结束日（不含）；必须不晚于本期 start')
    direction: Literal['decrease','increase']=Field(description='decrease 表示本期比基期下降，increase 表示上升')
    min_ratio: Annotated[StrictInt|StrictFloat,Field(gt=0,le=100,allow_inf_nan=False,description='变化幅度下限，按基期值的比例填写：下降不少于 50% 填 0.5；下降时不超过 1')]
    min_baseline_value: Annotated[StrictInt|StrictFloat,Field(gt=0,allow_inf_nan=False,description='可选。基期值下限，按该指标的原单位填写，金额为分；用户没有提基期门槛时不填')]|None=None

class CohortRequest(Contract):
    store_id: str|None=None
    store_ids: list[Annotated[str,Field(min_length=1,max_length=64)]]|None=Field(default=None,min_length=1,max_length=50,description='可选。多家注册门店，任一门店有注册关系即在范围内，名单去重；与 store_id 不能同时填。只查一家门店时用 store_id')
    reference_date: date
    start: date
    end: date
    dormant_days: StrictInt|None=Field(default=None,ge=1,le=3650,description='可选。最近有效购买距参考日至少满 N 天；用户没有提这类条件时不填')
    active_within_days: StrictInt|None=Field(default=None,ge=1,le=3650,description='可选。最近有效购买距参考日不足 N 天；与 dormant_days 同填时表示满 dormant_days 天且不足 active_within_days 天')
    metric_filters: list[AggregateFilter]=Field(default_factory=list,max_length=3,description='指标条件，同时满足；同一指标可以分别给下限和上限。没有 comparison 时必填 1～3 条；有 comparison 时可以不填')
    comparison: Comparison|None=Field(default=None,description='可选。两期对比：本期是 start／end，基期在本期之前；只在基期有该指标记录的会员中筛选，本期没有记录按 0 计，基期值不大于 0 的不计算比例')
    tiers: list[Annotated[str,Field(min_length=1,max_length=50)]]|None=Field(default=None,min_length=1,max_length=20,description='可选。会员等级，取值用当前数据里的等级原值，多个值表示任一等级；等级未知的会员不会被丢掉，其余条件满足时列入待核')
    registered_from: date|None=Field(default=None,description='可选。注册日期不早于这一天（含）；注册日期取来源 CRM 已知入会日期的最早值')
    registered_before: date|None=Field(default=None,description='可选。注册日期早于这一天（不含）；注册日期未知的会员不会被丢掉，其余条件满足时列入待核')
    channel: Literal['telephone','sms','all']|None=None
    unsupported_conditions: list[Annotated[str,Field(min_length=1,max_length=200)]]=Field(default_factory=list,max_length=10,description='用户提出、但以上字段无法表达的条件，按用户原话逐条填写，例如会员卡、条件之间的或关系、基期对比以外的多个窗口、月度类指标、超过 3 条指标条件、不带任何指标条件只按属性列会员。没有就不填。填写后本工具不返回名单')
    page: Page=Field(default_factory=Page)
    @model_validator(mode='after')
    def interval(self):
        # A request that declares an inexpressible condition is refused as a whole with CONDITION_NOT_SUPPORTED,
        # so the remaining fields need not combine into a valid list request.
        if self.unsupported_conditions:return self
        if not self.start < self.end <= self.reference_date:raise ValueError('INVALID_HALF_OPEN_WINDOW')
        if self.dormant_days is not None and self.active_within_days is not None and self.dormant_days>=self.active_within_days:raise ValueError('EMPTY_RECENCY_RANGE')
        if self.comparison is None and not self.metric_filters:raise ValueError('METRIC_FILTER_REQUIRED')
        if self.comparison is not None:
            c=self.comparison
            if not c.baseline_start<c.baseline_end:raise ValueError('INVALID_BASELINE_WINDOW')
            if c.direction=='decrease' and c.min_ratio>1:raise ValueError('DECREASE_RATIO_ABOVE_ONE')
            if c.baseline_end>self.start:raise ValueError('BASELINE_MUST_PRECEDE_CURRENT_WINDOW')
        if self.store_id is not None and self.store_ids is not None:raise ValueError('STORE_ID_AND_STORE_IDS_EXCLUSIVE')
        for values in (self.store_ids,self.tiers):
            if values is not None and len(set(values))!=len(values):raise ValueError('DUPLICATE_VALUES')
        if self.registered_from is not None and self.registered_before is not None and self.registered_from>=self.registered_before:raise ValueError('EMPTY_REGISTRATION_RANGE')
        return self

class IdentityEvidence(Contract):
    left: str
    right: str
    relation: Literal['same','different','unresolved']
    evidence_id: str=Field(min_length=1)
    source_file: str=Field(min_length=1)
    source_row: StrictInt=Field(ge=1)
    rule_version: str=Field(min_length=1)

class IdentityResult(Contract):
    source_id: str
    member_id: str|None
    status: Literal['resolved','singleton','unresolved','conflict']
    evidence_ids: list[str]
    mapping_version: str
