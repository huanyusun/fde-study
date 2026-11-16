# 梧桐指标构建方法

## 一、目标与输入
按输入的目标 ID 逐项处理，不新增、不改名、不遗漏。业务模型提供对象、关系和粒度；报表说明提供统计口径；字段字典提供实际列名和单位。根据输入资料构建完整的语义模型、实体、维度和 measures。不得凭字段名或常识推断口径，不得加入资料没有提出的规则（例如会员资格）。

## 二、候选及依据
为每个目标整理：统计对象与粒度、统计时间、计入与排除条件、金额或数量构成、聚合方式、单位。每一项都要在输入中找到依据。catalog 的 sources 使用输入文件名和连续原文 quote，引文必须逐字出现在该文件中，并能支持对应的定义。business_model_usage 只记录实际采用的业务模型原句。

## 三、字段与计算转换
按已核实的粒度写 measure：行级表达式只使用字典中存在的列；计入与排除条件写进表达式（例如不满足条件时取 0）；金额类指标逐项核对计入项与扣减项是否齐全。选择与统计对象一致的聚合方式。simple 指标通过 type_params.measure 引用 measure。

## 四、依赖与输出协议
比率指标用 ratio 类型，numerator 与 denominator 引用已定义的指标 ID，不引用 measure 名或公式文字。measure 名称全局唯一。按输入中的 native_format 与 contract 的写法输出，不使用其他版本的 YAML 结构。catalog 只收录已定义指标，未决目标不得进入 catalog。catalog 为每个已定义指标给出 id、name、aliases、unit、constraints、sources、query_policy；单位使用 count、cents、ratio 等明确标识；资料明确要求只按完整自然月查询时 query_policy.full_month_only 为 true，否则为 false。model_sql 只在确需客户 SQL 模型时填写，否则为空对象。只返回一个 JSON 对象，包含 semantic_models、metrics、catalog、model_sql、grain_keys、unresolved、business_model_usage，不返回 Markdown 或 YAML。

## 五、未决、冲突与修订
资料缺少某个目标的定义，或资料之间说法冲突时，把该目标列入 unresolved，写明缺什么依据或冲突在哪里，不要为了覆盖目标而补写公式。每个目标只能出现在已定义或未决其中一边。

## 六、语义模型与派生模型
把业务对象映射到语义模型，把已确认关系映射到实体主键与外键，把属性映射到维度。输入 access_tables 是原样接入表结构，只有 time_spine 由框架按覆盖期提供，不预置任何业务排序、月表或资格列。每个 semantic_model 返回 name、model、entities、dimensions、defaults（有统计时间时）和 measures；model 用 ref('模型名')，SQL 中的模型引用用 {{ ref('模型名') }}。

逐个核对 dimension_targets。实体查询 ID 对应实体名，属性查询 ID 用主实体名__维度名。同一物理对象在关系中有不同角色时，须分别表达这些角色；维度必须能从实际指标沿实体关系查询。确实缺少关系依据时，在 unresolved 以 dimension_id、missing_facts、reason 说明，不能凭空连接。

先声明一行代表什么，再写聚合。每个模型的 grain_keys 给出实际粒度列名列表；单键按主键检查，组合粒度逐列检查，不能用会吞掉空值的拼接逃避检查。主实体必须无重复无空值，外键必须指向相同业务对象的唯一实体。需要排序、汇总或资格判定等业务规则时，先按业务模型和材料生成独立派生 SQL，再为结果建立语义模型和指标；名称自行选择，不覆盖接入模型。处理月度人数时先得到每月每对象一行，再按已确认条件计数，避免一对多关联放大人数或金额。

SQL 仅使用 SELECT/WITH 和原生 dbt ref，不使用文件、网络、DDL 或 DML。语义模型继续使用 semantic_models/measures 旧写法，兼容 MetricFlow 0.213.0。每个引用的指标依赖必须在本次输出内闭合，否则相关指标列未决。business_model_usage 的 used_for 可写 kind（semantic_model、dimension、derived_model、metric）和 name，quote 仍是业务模型连续原文。不要把构建检查或自己的推断写成客户事实。

原生配置约束：dimensions[].name 只填属性的局部名，不把带双下划线的查询 ID 填进 name；查询 ID 的实体前缀由 MetricFlow 自动组合。一个实体名只能有一个 primary/unique 目标，其他关联用 foreign。同一实体和维度名的配对也必须唯一；若原表与派生表表示不同的行集合或粒度，为派生表声明自己的主实体名，或使用独立 primary_entity 加 grain_keys，不复制另一个模型的主实体及时间维度配对。grain_keys 对每个模型给出实际列名列表，组合键逐列列出，不填 SQL 表达式。构建前逐项检查这些约束，不依赖程序替换名称。

metric_time 是 MetricFlow 的查询保留名；day、month、year 等时间粒度词也是保留名，不能作为实体或维度名。时间维度使用字典中的日期列名，或派生表自己生成的非保留日期列名，在 defaults.agg_time_dimension 中引用；metric_time__day／month 仅用作查询目标 ID。任何有 dimensions 的模型必须声明 primary 实体或 primary_entity。
