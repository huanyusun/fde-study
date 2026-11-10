# 梧桐样例：从业务资料生成语义模型和指标库

准备自己编写构建方法时，先读[构建 Skill 编写指南](skill-guide.md)。本篇保留梧桐实际输入、生成物、检查及问数走读。

本例是独立教学数据。目录里的样例库由配置的模型 API 从空目录生成，使用 MetricFlow 0.213.0 的 semantic_models／measures 格式。学员可以阅读完成结果，再换新输出路径自行构建。相同输入不保证每次生成成功，检查失败时先定位原因，保留失败记录，再按任务授权决定重试或修订 Skill。

样例由原样六段 Skill 经真实模型调用生成，三项检查和独立查询全部通过，未手工修改生成结果。

## 1．输入分别负责什么

| 输入 | 作用 |
| --- | --- |
| `examples/w03/business_model.md` | 订单、会员与门店的关系、订单粒度，以及月内大额会员的已确认业务定义 |
| `examples/w03/materials/report.md` | 只计 paid、扣除退回、按原订单日期归月等口径 |
| `examples/w03/materials/data_dictionary.md` | 物理字段、单位和关联 |
| `examples/w03/targets.json` | 6 项指标的 ID 和中文名 |
| `templates/w03/dimension_targets.json` | 12 项查询维度的 ID、中文名与含义 |
| `examples/w03/data/` | 四张原始 CSV 和 manifest；用来加载及检查，不作为生成答案塞进提示词 |
| `examples/w03/build-metrics/SKILL.md` | 如何把上述输入转换为完整模型的方法 |

课程接入层只加载 raw 表并保留原有数据检查，再原样提供 members、stores、cards、orders。time_spine 从 manifest 的半开覆盖期生成。本例覆盖 2024-09-01 至 2026-09-01，结束日不含。

## 2．Skill 六段怎样分工

1. **目标与输入**：分清业务概念、统计口径与物理字段，逐项处理目标。
2. **候选及依据**：核对对象、时间、条件、单位，并保留输入中的连续引文。
3. **字段与计算转换**：把核实过的条件落到字段表达式与聚合方式。
4. **依赖与输出协议**：保证指标依赖、中文目录、查询限制与 JSON 契约一致。
5. **未决、冲突与修订**：缺事实或有冲突时写清问题，不凭常识补公式。
6. **语义模型与派生模型**：从对象和关系生成实体、维度和模型；声明每行粒度；将需要先汇总的业务规则实现为派生 SQL，并遵守原生格式限制。

这些是方法。金额门槛、订单状态和退款归期来自本例客户材料。

## 3．真实生成的模型

本次完成样例包含 orders、members、stores、stores_home、monthly_member_receipts 五个语义模型。前四个表达订单、账户、成交门店与归属门店角色；派生模型按 month_start 和 member_id 汇总扣退后收入。模型名可由构建者选择，不是课程强制答案。

本次派生 SQL 先筛 paid，再计算 paid_cents－refund_cents，最后按月份和会员汇总。生成的 member_month_key 是连接用的主实体；粒度检查同时检查真实的 `month_start＋member_id`，不能用一个人工序号掩盖重复汇总行。月内大额会员数在这张表上对达到已确认门槛的行计数，并设置 `query_policy.full_month_only=true`。

主要生成物：

- `metrics.yml`：完整 semantic_models、measures 和 metrics。
- `monthly_member_receipts.sql`：带业务规则的派生模型。
- `catalog.json`：中文目录、单位、来源和限制。
- `grain_contract.json`：各语义模型的实际粒度列。
- `dimension_targets.json`、`unresolved.json`、`scope.json`：目标、未决与业务范围。
- 三份检查报告及 `provenance.json`：检查结果和输入追溯。

## 4．从空目录构建与三项检查

以下命令假设已按 README 安装依赖并配置自己的模型。输出目录已存在时，换一个版本名称。

```sh
.venv/bin/python tools/w03.py build --config examples/w03/build.json --output artifacts/wutong-build-01
```

构建先保存输入、使用的 Skill、原始响应与来源检查。候选落在 `candidate/`，经过原生加载后检查：

| 报告 | 本次样例结果 | 检查范围 |
| --- | --- | --- |
| `dimension_check.json` | 12 项可查询、无未决 | 目标 ID 是否能通过实际语义关系查询 |
| `grain_check.json` | 全部通过 | 主键无空无重、外键未匹配行数为 0；月表 4 行，“月份＋会员”无空无重 |
| `metricflow_check.json` | 6 项指标全部通过 | 原生解析、配置校验、逐指标 SQL 编译及数据库 EXPLAIN |

任一失败都不会在输出目录顶层生成可加载库。失败候选与报告保留以便排障。通过这些检查仍不能证明业务口径正确，下一步必须对照独立核算。

## 5．加载与问数

可以加载自己新生成的库，也可以使用包内完成样例：

```sh
.venv/bin/python tools/w03.py load --library examples/w03/library --data examples/w03/data --project .runtime/wutong-01 --activate-home .runtime/product
.venv/bin/python tools/product.py start --home .runtime/product
```

在原聊天入口问数。以下结果已实际运行并与原始 CSV 独立核算比较：

| 问题 | 结果与独立依据 |
| --- | --- |
| 2026 年 8 月扣退后收入 | 13000 分，即 130.00 元；10000－2000＋5000 |
| 2026 年 8 月退回占比 | 2000／15000，约 0.133333 |
| 2026 年 8 月按成交门店列收入 | W01 为 8000 分，W02 为 5000 分 |
| 2026 年 7 月月内大额会员数 | 1；W1 两单合计 10000 分，恰好达到门槛；W2 全额退款后为 0 |
| 2026 年 8 月月内大额会员数 | 0；W1 为 8000 分、W2 为 5000 分，覆盖内已知没有人达到门槛 |

`examples/w03/tests.json` 有 3 条独立单指标用例，原有的简单判定程序可直接运行：

```sh
.venv/bin/python tools/w03.py test --project .runtime/wutong-01 --cases examples/w03/tests.json --output artifacts/wutong-test-01 --judge-command .venv/bin/python examples/w03/judge.py
```

本次这 3 条真实 Agent 测试通过。多指标、分组、空值与复杂错误比较需要扩展判定程序，不能把单指标样例当成完整测试能力。具体写法、自检和定位方法见[测试与判定编写指南](test-guide.md)。

## 6．沿记录排障

- 返回 YAML 或非 JSON：看 trace 中原始响应，修订输出协议后重新生成。
- 原生解析失败：看 validation-project/build.log，检查局部维度名、保留词、实体命名和依赖。metric_time、month 等不能作为普通维度名。
- 主键重复或外键未匹配：看 grain_check 的具体模型、列和行数，再核对关系与实际粒度。
- 缺维度：看 dimension_check；缺业务关系时列未决，有依据时修订语义模型方法。
- 数字错误：先核对问法、意图、数据版本和实际 SQL，再查业务条件，不能修改独立期望迎合结果。

教师曾在真实生成结果的副本中注入重复主键、错误外键、缺渠道维度，均被构建拦下。另把月度累计错写成单笔最大值，7 月得到 0；把扣退后收入错写成实付累计，得到 2。后两者能通过结构检查，但独立期望 1 检出了口径错误。由此区分“程序执行成功”和“业务计算正确”。

每次修订使用新的构建和项目目录。真实学员试做、作者审阅和正式发放另行确认。
