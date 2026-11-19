# 指标修订

## 本次修订的指标 ID 清单

无修订。38 项指标 ID 全部保持不变（order_count、paid_order_count、cancelled_order_count、refund_order_count、partial_refund_order_count、full_refund_order_count、paid_amount_cents、refund_amount_cents、net_sales_cents、discount_amount_cents、avg_order_value_cents、avg_buyer_value_cents、buy_freq、refund_ratio、cancel_ratio 及其余沿用 W03 提交），定义、SQL 与 catalog 均未改动。

## 逐项修订前与修订后定义

无逐项修订。核对记录如下（核对而非修订）：

1. `member_month_stats.sql` 中付费资格过滤 `card_type IN ('悦享年卡', '家庭季卡')`：修订前即为该写法，修订后保持不变。本周发现卡种名称存在新旧并存（悦享年卡 8,178 张、悦享卡（年）1,201 张），若不适配归并，改名前办卡的 1,201 张会漏出付费资格口径；该风险由适配层归并消除（清洗后 card_type 只保留标准名），SQL 在清洗后数据上语义不变。
2. 订单状态映射核对：数据中已支付/已完成/部分退款/全额退款均映射为 paid（142,412 条）、已取消映射为 cancelled（25,841 条），与各指标描述（"paid 包括部分退款与全部退款"等）一致，未改定义。

## 修订依据、来源、原因及适用范围

- 卡种名称归并依据：陈姐访谈确认（chen-jie-1 MSG-06107，`data_diagnosis.md` 第二节 card_kind 行）；对应业务模型修订 R1（`model_changes.md` 逐项修订表第 1 行）。
- 订单状态口径依据：W03 指标描述与 run-02 清洗数据核对（`adapter_test_report.json`、`.runtime/w04/run-02/adapt/cleaned/orders.csv` 状态分布），对应模型修订 R9-①。
- 适用范围：全部 38 项指标在导入后的库上真实执行通过（`artifacts/w04/metrics_run.json`，核对月份 2026-08-01 至 2026-09-01，见执行记录），证明修订/归并未破坏可执行性；数字以库内实际值为准。
- 员工卡隔离（299 张）保证付费会员类指标不受内购卡污染，属数据事实引用，非指标定义变化。
