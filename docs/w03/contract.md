# W03 工具接口

## 指标库如何交给 MetricFlow

LLM 不直接把自由文本交给 MetricFlow。构建 Skill 先把业务概念与字段关系写成原生语义模型和指标定义；框架落盘 `metrics.yml`。其中 semantic_models 声明实体主外键、维度、默认统计时间和 measures，metrics 声明 simple/ratio 等定义及其依赖。课程只提供 raw 表加载、原样接入的 members／stores／cards／orders 及按 manifest 覆盖期生成的 time_spine。全部带业务规则的排序、汇总或资格模型由 Skill 生成，model_sql 可包含多个派生模型。原生 dbt 构建和 MetricFlow 0.213.0 编译实际使用这些文件，保留 semantic_models/measures 旧格式。

`catalog.json` 是运营 Agent 理解中文的目录，包含 ID、中文名、别名、单位、constraints、sources 和 query_policy；它不是另一个执行引擎。`scope.json` 描述客户及范围。sources 必须是输入文件名和连续原文 quote。业务材料、模型、来源与执行定义一起版本化。

自然语言理解输出结构化意图，再由程序核查允许范围、日期和筛选值，调用 MetricFlow。MetricFlow 接收指标 ID、维度、时间与筛选表达式，生成 SQL 并在只读查询链路执行；Agent 根据实际结果解释。本周只实现有限运行语法，不能据此宣称“任意指标、任意条件”。增加新业务定义需构建新库，当前 38 项以外不默认存在。

## 构建输出

完整 JSON 形状见 `contracts/w03/build_response.example.json`。每个指标目标要么完整定义，要么以 metric_id 列 unresolved，不能重复或遗漏。semantic_models 返回完整 name、model、entities、dimensions、defaults 和 measures；model 为 `ref('模型名')`，SQL 内用 `{{ ref('模型名') }}`。measure 名称全局唯一，ratio 引用已定义 metric ID，依赖须闭合。dimensions[].name 使用局部属性名，查询 ID 由实体前缀组合。

`model_sql` 的键是合法小写模型名，不得与接入表或 time_spine 重名；值必须以 SELECT／WITH 开头，保留危险操作检查。`grain_keys` 按语义模型名给出实际粒度列名列表，组合粒度逐列列出。business_model_usage 的 quote 必须是业务模型连续原文；used_for 支持字符串或 `{kind, name}` 对象，kind 为 semantic_model、dimension、derived_model、metric。

构建配置新增 `data`（相对于 build.json），用于在实际数据上检查；不会把 CSV 或现有库作为模型生成输入。输入提供接入层表结构、指标目标与 `templates/w03/dimension_targets.json`，不提供固定骨架。维度目标仅列 ID、中文名和业务含义。缺少关系依据时以 dimension_id、missing_facts、reason 列 unresolved。

### 发布前的三项检查

- `dimension_check.json`：目标必须在实际 MetricFlow 语义图中可查询，或有明确未决说明。多跳原生路径只有唯一匹配时才映射到目标 ID，运行时保留每项指标的实际路径。
- `grain_check.json`：主实体（含 unique 连接目标）检查重复和空值；grain_keys 检查声明的单键或组合粒度；外键以左关联统计未匹配行数。任何未匹配行都拦截，不能把错误关系解释成没有业务。
- `metricflow_check.json`：原生解析、SemanticManifestValidator，以及每项指标的原生 SQL 编译和数据库 EXPLAIN。检查不证明业务语义正确，仍须独立核算。

候选文件在构建目录的 candidate 下，失败保留响应与检查记录；三项全部通过才在输出目录顶层生成可加载库。加载任何库也重新执行三项检查，不能复制一份旧检查报告绕过验证。未决指标不进入 catalog。

`merge --data 数据目录` 合并完整语义模型，也用于把单个构建目录提升为定稿库 `artifacts/w03/library`；输出目录须不存在。同名模型任何内容不一致均报冲突，SQL、粒度声明、客户和来源版本也须一致；合并后重新检查。分批必须各自依赖闭合且共享模型内容完全一致，否则请一次生成完整库或重新生成相互一致的批次，不再自动拼接同名模型的 measures。

catalog 单位使用 count、cents、ratio、cents_per_order、cents_per_member、orders_per_member、items_per_order 等有明确含义的标识；金额展示为元需换算。月度定义需设置 `query_policy: {"full_month_only": true}`，由程序落实完整自然月、全门店全渠道与跨月按月展示限制，不能只写在说明里。

框架校验来源存在、引用准确和结构一致，但不能证明业务解释正确。错误模型仍可能生成结构正确的错误库，需要业务核查和独立期望。

## 查询与结果

意图示例：

```json
{"metrics":["order_count"],"start":"2026-08-01","end":"2026-09-01","group_by":["store"],"filters":[{"field":"order__channel","op":"eq","value":"门店"}]}
```

时间为半开区间，Asia/Shanghai；end 当天不包含。eq 是字符串，in 是字符串数组，多条件为 AND。原生可达维度才可组合，不支持任意 OR、任意 SQL 或自由用户表达式。可用维度来自本次加载的 dimensions.json，是维度目标与实际可查询维度的交集；多个指标组合还取各自可达维度的交集。筛选取值从语义模型对应列取得，eq／in 和 AND 的语法不变；整月指标保留更严格限制。

结果 status 为 ok、clarify、unsupported 或 error。成功含 intent、sql、columns、rows、units、data_version、data_sha256、catalog_sha256、answer 和 trace_id。无数据覆盖不能按零；覆盖内没有订单的加总可为零；零分母比率未定义为 null。多维结果按维度键比对，不依赖行顺序。金额与比例要检查单位，SQL 不要求文本逐字相同。

## 测试与判定

`tests.json` 为数组，每项含 id、question、expected，建议附 expected_source 解释手算或独立核算来源。expected 包含 status；成功还需 intent、columns、rows、units，可锁数据与库版本哈希。期望在运行前确定，不能将本轮实际结果复制成期望。

判定进程标准输入为 `{"expected": ..., "actual": ...}`，标准输出为 `{"passed": true, "differences": []}`。程序须纯比较，不能再调用 LLM 或另起查数引擎。任何后端语言均可，用 `--judge-command` 指定启动程序；其它命令参数写在 `--judge-command` 前。框架开跑先执行一次自身对比来检查判定可运行；这不验证判定严谨性，须另做错误注入。

覆盖状态、指标、时间、分组、筛选、单位、空值、数值容差、漏行与多行。对 answer 是否忠实解释证据作人工语义核查，不能因为机器判定 passed 就声称业务已验收。
