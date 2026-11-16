# 梧桐书店示例字段字典

本例与通用框架使用相同物理结构。四张源表均为 CSV，已整理好主外键；数据是独立合成示例。日期为 Asia/Shanghai 本地 date，金额为整数分。

orders 一行一单：order_id 为主键，member_id 关联 members.member_id，store_id 关联 stores.store_id；ordered_at 为下单日期，status 为 paid 或 cancelled；gross_cents 为原价分，paid_cents 为实付分，refund_cents 为截至快照累计退回分，quantity 为原始购买件数，channel 为渠道。SQL 使用这些实际列名，不存在 paid_amount_cents 或 refund_amount_cents。

members 一行一账户：member_id、registered_at（注册日）、home_store_id（归属门店）、tier（等级）。stores 一行一门店：store_id、region、store_name。cards 表在本例只有表头，未使用任何资格统计：card_id、member_id、card_type、valid_from、valid_until、ended_at、card_paid_cents。

收入计算使用报表说明的业务定义与 orders 字段，不能因框架包含卡模型就添加本例未提出的会员资格规则。
