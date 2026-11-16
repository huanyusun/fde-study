# 指标核定与未决项

## 采用依据

生成目录:`artifacts/w03/library/catalog.json`(38 项,构建目录 `artifacts/w03/build-v10`,checks_passed=true,2026-11-09)。Skill 版本:本仓库 `customer/w03/build-metrics/SKILL.md`(**规范对齐版**:纯方法、零客户事实——按任务书"客户的金额、状态、日期和资格留在资料里,Skill 只写方法"要求,将钉板版重构为方法语言;卡种名单、有效期端点、状态条件等由模型构建时从业务模型与材料原文取,资格规则未记录即整族未决;比率类仍用 derived+CASE 置 null,理由见下。历史库留证:`library-v1-pinned`(钉板版)、`library-defective-v4`(buyer_count 聚合错误版)。)

## 核定度量映射(build-v10 采用版本)

按第 7 步核定,当前定稿库的度量名与聚合方式如下(方法在 Skill,采用版本在此):

| 语义模型 | 度量(聚合) |
| --- | --- |
| orders | m_order_count(count)、m_paid_order_count(count)、m_valid_order_count(count)、m_cancelled_order_count(count)、m_refund_order_count(count)、m_partial_refund_order_count(count)、m_full_refund_order_count(count)、m_payment_cents(sum)、m_refund_cents(sum)、m_net_sales_cents(sum)、m_gross_cents(sum)、m_discount_cents(sum)、m_buyer_count(count_distinct)、m_refund_buyer_count(count_distinct)、m_selling_store_count(count_distinct)、m_valid_order_items(sum) |
| members | m_new_member_count(count_distinct) |
| order_validity(派生,首购排序) | m_first_buyer_count(count_distinct)、m_first_order_count(count)、m_first_order_sales_cents(sum)、m_repeat_order_count(count) |
| member_month_stats(派生,账户×月,含付费资格) | m_monthly_buyer_count(count_distinct)、m_monthly_repeat_buyer_count(count_distinct)、m_monthly_paid_buyer_count(count_distinct)、m_monthly_paid_order_count(sum)、m_monthly_paid_sales_cents(sum)、m_monthly_paid_repeat_buyer_count(count_distinct) |

派生 SQL:`order_validity.sql`(有效订单+购买序号/首单标记)、`member_month_stats.sql`(账户×月聚合+月末资格判定,卡种与端点取自业务模型原文)。指标 38 项 = 27 simple + 11 derived(比率/均额全为 derived,expr 见各指标定义)。

- **通用订单 16 项**(`order_count`…`valid_order_items`):采用 `materials/w03/01_订单日报说明.md` 原文口径——有效订单=paid 且实付−退款>0(取消、全退不计);退款按原订单下单日期归属;取消单金额列为 0 仍保留状态条件。目录 sources 引该文件逐字原文。
- **比率 8 项**(`avg_order_value`…`items_per_order`):采用 `02_财务邮件.md` 口径,分子分母为对应基础指标,**分母零时未定义**——全部实现为 derived 指标 `case when <分母>=0 then null else <分子>/<分母> end`(DuckDB 0/0 会返回 nan 而非空值,原生 ratio 类型无法表达该口径,已实测确认)。
- **会员周报 8 项**(`new_member_count`、`first_*`、`repeat_order_count`、`monthly_*`):采用 `03_会员运营周报.md` 原文——观测期首购以测试覆盖期全历史按(下单日期,订单号)排序确定首次再按窗口筛选;月内族仅整月、全门店,人数不跨月加总;月度 3 项设 query_policy.full_month_only=true。
- **付费月报 6 项**(`monthly_paid_*`):采用 `04_本期统计确认邮件.md` + 业务模型付费资格规则(W3 访谈候选定稿):月末最后一天判定,账户名下任一张悦享年卡/家庭季卡在判定日有效即有资格(多卡并集、按账户去重);端点 valid_from 当天起有效、valid_until 当天已无效(不含)、ended_at 当天起无效(陈姐答复,候选定稿、待王经理中期检查点复核)。派生模型 `account_month_paid` 的 SQL 逐字固定并引用 business_model_usage。full_month_only=true。
- **单位**:`count`(计数)、`cents`(金额,整数分)、`ratio`(比率/均额/频次比值);均额类目录单位取 ratio 与生成目录一致,测试期望按目录核对。

## 冲突、未决与不支持

- 四处访谈分歧(端点规则/卡种名单/多卡并存/记录归属)已在业务模型按王经理分歧记录法处理为「非实质冲突:分工不同或信息缺口」;其中端点与多卡并集已按候选定稿进入计算,并列入测试覆盖(8 月与 7 月付费族对照用例验证端点两个方向、M00014 双卡接力、M00018 非付费卡种)。见 `docs/w03/business_model.md` 未知与分歧节,此处不重复。
- `monthly_paid_*` 只支持完整自然月、全门店全渠道(材料 04 明确限制,非缺陷);跨月查询按月分别展示(产品 full_month_only 策略拦截,已测)。
- 暂不支持按门店/渠道拆分付费月报——材料 04 原文限制,状态:已定,无需访谈。
- 生产环境自然人去重/旧 POS 身份合并、退卡停卡生产记录归属、小林名单书面依据等仍为未决(见 `interview_notes.md` 下一轮起点),均不影响本期测试库计算。

## 解释人工核查

方法:逐例读取 traces 的 answer-trace(reply),核对客户识别、时段、筛选与口径表述、有无把已知说成未知;数值由判定程序独立比较,不在此重复。**定稿轮(test-small-v7)15 个 ok 用例全部复核通过**:客户识别为青禾、时段与筛选表述准确、成交门店/归属门店无混淆、覆盖内真实零值与"分母零未定义"表述清晰(自动化标记检查 + 关键用例人工细读,复核脚本输出与抽查记录见 traces)。下表为过程轮次的核查发现,保留作证据。

| 用例 | 客户识别 | 时间/筛选/口径表述 | 有没有把已知说成未知 | 结论 |
| --- | --- | --- | --- | --- |
| aug-order-counts(4e75cbd0) | 青禾 ✓ | 8月、含取消说明、三族口径各一句 ✓ | 无 | 通过 |
| aug-refund-counts(b11b7d10) | 青禾 ✓ | 4=1+3 勾稽说明 ✓ | 无 | 通过 |
| aug-amounts(ffaf52c8) | 青禾 ✓ | 退款按原单日期归属、退款不冲减优惠、元展示 ✓ | 无 | 通过 |
| aug-buyer-store-items(v1:6aae188f) | 青禾 ✓ | v1 把"成交门店"说成"归属门店"(语义错位、数值正确),复跑后表述正确并澄清"不代表会员归属门店";定稿轮 v7 自动标记复核无混淆 | 无 | 通过(复跑复验) |
| aug-ratios(67ce8a43) | 青禾 ✓ | 元/单、%展示正确,未加筛选说明 ✓ | 无 | 通过 |
| aug-first-purchase(bbfbb422) | 青禾 ✓ | "非终身首购"限定 ✓ | 无 | 通过 |
| aug-monthly-general(5933aa66) | 青禾 ✓ | 整月全门店、账户≠自然人 ✓ | 无 | 通过 |
| aug-paid-family(8722305f) | 青禾 ✓ | 月末资格+当月订单口径 ✓ | 无 | 通过 |
| jul-core(e7b7dccf) | 青禾 ✓ | 7月各口径 ✓ | 无 | 通过 |
| jul-paid-family(07678825) | 青禾 ✓ | 复购率 0 特意说明"分母大于零的真实零值,非未定义" ✓ | 无 | 通过 |
| sep2024-first(f78061bc) | 青禾 ✓ | 覆盖期起点、"不代表终身首购" ✓ | 无 | 通过 |
| mar2026-empty(9cdea0f5) | 青禾 ✓ | 计数为 0、比率"未定义(覆盖内真实零,非缺失)" ✓ | 无 | 通过 |
| aug-group-store(f2fe0eb6) | 青禾 ✓ | 按成交门店分组、东八区 ✓ | 无 | 通过 |
| aug-filter-channel(18fd2fb6) | 青禾 ✓ | 明确"已应用渠道=小程序筛选" ✓ | 无 | 通过 |
| cross-month-monthly(3ad424f2) | 青禾 ✓ | "整月独立计算,人数不能跨月加总" ✓ | 无 | 通过 |

## 测试与回归记录

| 轮次 | 报告目录 | 失败现象 | 错误来源 | 改了什么 | 回归结果 |
| --- | --- | --- | --- | --- | --- |
| 构建试跑 build-try1/2 | `artifacts/w03/build-try1`、`build-try2` | MODEL_TIMEOUT(180s/240s) | 产品环境:glm-5.3-flash 默认深度思考叠加输出预算 | 模型档位 compatible→deepseek-low(框架文档内配置,顶层 thinking 参数,z.ai 实测接受);FDE_MODEL_TIMEOUT=240、MAX_TOKENS=32768 | 单指标 190s→通过(try3) |
| 构建试跑 try4/5 | `artifacts/w03/build-try4`、`build-try5` | JSON 带围栏和尾注;PROJECT_VALIDATION(模型漏发 4 个接入模型) | 构建(模型行为) | Skill 四段:裸 JSON 首尾字符约束 | 引出钉板 Skill |
| 分批 b1/b2 | `artifacts/w03/build-b1`、`build-b2` | 17 项/25 项通过(44s/53s) | — | 验证钉板方案有效 | b2 含全部通用 25 项 |
| 分批 b3/b4/b5 及 v2/v3 | `artifacts/w03/build-b3*`、`b4*`、`b5*` | 派生模型缺语义模型与 grain_keys;SQL 少投影 paid_cents;derived 键名误用 input_metrics;维度目标批级覆盖不足;business_model_usage 编造引文;JSON 尾注 | 构建(方法缺口+模型抖动) | Skill 六段钉板派生模型/SQL/grain_keys;四段钉 derived 形状(metrics 键);五段禁编造引文;批次纪律改为**一次生成完整库**(指南 §7.1) | `build-v1` 38/38 全过(102s) |
| Skill 规范化重构(v2) | `artifacts/w03/build-v2` | MODEL_TIMEOUT:拆除钉板后模型自行生成全部语义模型 JSON,输出量超 240s | 构建(输出经济性) | Skill 加"输出精炼"方法(描述一句话、sources≤2) | 见 v3 |
| Skill 规范化重构(v3) | `artifacts/w03/build-v3` | DBT 解析错误:模型把 query_policy/constraints 写进指标定义(这两个字段只允许在 catalog) | 构建(方法歧义) | Skill 四段明确指标定义对象只含 name/label/description/type/type_params | 见 v4 |
| Skill 规范化重构(v4) | `artifacts/w03/build-v4` | 结构检查过,但小样本抓到 buyer_count/refund_buyer_count 聚合用 count(行数)而非 count_distinct(语义漂移,结构检查管不住——指南 §9) | 构建(聚合词义) | Skill 三段强化去重自查规则 | 见 v5 |
| Skill 规范化重构(v5/v6/v7/v8/v9) | `artifacts/w03/build-v5*`…`v9` | v5 SQL 少投影+占位词;v6/v8/v9 MODEL_TIMEOUT;v7 度量重名 | 构建(生成质量+240s 边界) | 补投影完整/禁占位词/度量唯一名规则;输出精炼(aliases 空、单引文、无 label/模型描述) | 见 v10 |
| Skill 规范化重构(v10,**定稿**) | `artifacts/w03/build-v10` | 无失败,38/38 全过(238s);语义抽查全绿(无占位词、无重名、去重聚合正确、资格端点正确) | — | Skill 定稿为纯方法版;小样本/规模按纪律用新项目(qinghe-small-v3/qinghe-large-v3)全量复测 | 定稿库 `artifacts/w03/library` |
| 复测 small-v6 / large-v4 | `artifacts/w03/test-small-v6`、`test-large-v4` | small 17/18(aug-ratios 服务端返回混控制字符);large 5/9(后 4 例 MODEL_HTTP_429 限流) | 产品(模型服务瞬态/限流) | 冷却后原样重跑 | 见 v7/v5 |
| **定稿 small-v7 / large-v5** | `artifacts/w03/test-small-v7`、`test-large-v5` | 无失败,**18/18 与 9/9 全过** | — | 选定 small-v7 报告复制为 `artifacts/w03/metric_test_report.json` | **通过** |
| 小样本第 1 轮 test-small-v1 | `artifacts/w03/test-small-v1` | 17/18;cross-month 分组键格式 `2026-07-01` vs `2026-07-01 00:00:00` | 期望(格式),数值全对 | 判定程序对日期型分组键做语义归一(其余仍严格) | 见 v2 |
| 小样本第 2 轮 test-small-v2 | `artifacts/w03/test-small-v2` | 16/18;no-time-clarify、unknown-metric 两例 status=error(JSON 解析抖动、SSLError,1 秒即失败) | 产品(模型服务瞬时故障) | 无业务修改,原样重跑 | 见 v3 |
| 小样本第 3 轮 test-small-v3 | `artifacts/w03/test-small-v3` | 无失败,**18/18 全过**;aug-buyer-store-items 解释复核正确 | — | 选定本轮报告复制为 `artifacts/w03/metric_test_report.json` | 通过 |
| 判定列对齐修正 | — | 判定程序升级:列按名对齐(引擎可无意义重排列),日期型分组键归一 | 判定 | 9 类注入重验仍全拒、原始对照全过 | — |
| 规模第 1 轮 test-large-v1 | `artifacts/w03/test-large-v1` | large-aug-members:引擎列序重排(值全对,期望层位置对齐误判);large-jul-first:repeat_order_count 期望 29497 实际 29524——**审核程序把"第二笔及以后"错写成"严格晚于首单日期"**,同日第二笔漏计 27 笔 | 期望(审核程序语义)+判定(列对齐) | audit_expectations 改为按排序序号取"第二笔及以后"(与指标库 row_number 语义一致);判定程序按列名对齐 | 见 v2 |
| 小样本第 4 轮 test-small-v4 | `artifacts/w03/test-small-v4` | 无失败,**18/18 全过**(判定程序修正后按纪律全量复测) | — | 选定本轮报告复制为 `artifacts/w03/metric_test_report.json` | 通过 |
| 规模第 2 轮 test-large-v2 | `artifacts/w03/test-large-v2` | 无失败,**9/9 全过**(30 万订单;含付费族两月对照、门店分组、问法变体;9 例共 234.6s) | — | 期望由审核程序对 large 独立重算 | 通过 |
| 判定非恒真证明 | `artifacts/w03/judge-checks/` | 9 类注入(错指标/错日期/错筛选/漏组/元分混淆/比例×100/null改零/篡改数值/error伪装ok)全部被拒;6 份原始对照全部通过 | — | `customer/w03/make_injections.py` 生成并复验 | ALL OK |
| 规模回归 test-large-v1 | `artifacts/w03/test-large-v1` | (待运行) | — | — | (填写) |

环境:macOS(x86_64)、Python 3.11.14(uv cpython)、模型 glm-5.3-flash(api.z.ai,deepseek-low 档)、单例耗时见报告 `actual.elapsed_seconds`(小样本 8–36s/例)。小样本判定命令:`tools/w03.py test --project .runtime/qinghe-small-v1 --cases customer/w03/tests.json --judge-command .venv/bin/python customer/w03/judge.py`;规模:`--project .runtime/qinghe-large-v1 --cases customer/w03/tests-large.json`,期望由同一审核程序按 `materials/data/large` 独立重算。
