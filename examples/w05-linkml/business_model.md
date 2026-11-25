# 独立模型例子及依据

这是教学自造的小数据，不是青禾正式记录，不修改正式业务口径。原始小表在 raw/，对象来源与行号对照在 source_map.csv；M1 的关系是依据教学核查／回执给出的独立预期，不靠姓名或手机相同推断。

已核实会员 M1 有 CRM:A1、CRM:A2、POS:P1 三个来源账户。核查依据支持三者为同一人；两个 CRM 账户分别注册在 S1、S2。POS 没有注册门店，不从购买地点补齐。POS:P2 的身份未决，以 X1 财务桶保留；桶不计作已核实自然人。M1 的显示名有一致来源，X1 姓名未知。

业务主键是 M1/X1、CRM:A1 等及 S1/S2；数据库没有另造整数身份。每个账户保留原文件和不含表头的来源行号。会员遍历来源账户和全部注册门店，来源账户可遍历其已知注册门店。

| 业务说明 | YAML 定义 | 生成及运行 |
| --- | --- | --- |
| 业务身份或未决财务桶 | Member.id / identity_status 枚举 | 字符串主键、数据库枚举、查询状态 |
| 名称可未知 | display_name 无 required | 可空列，查询返回 null |
| 一个会员多来源 | source_accounts，range SourceAccount，multivalued，非内联 | 关联表与 SQLAlchemy relationship |
| 多个注册关系并存 | registered_stores，range Store，multivalued | 第二张关联表，遍历 S1/S2 |
| POS 注册关系未知 | SourceAccount.registered_store 无 required | 可空外键，遍历返回 null |
| 记录可定位 | source_file、source_row 必填，整数且 >=1 | 生成类型；实例校验检查下界，数据库检查 NOT NULL |
| 全部旧字段仍可返回 | payload 为来源适配层 JSON 字符串 | 存储保留字段；内部结构和业务语义仍由 Python 管理 |

Markdown 是语义依据，程序不自动解析这份 Markdown。手工整理为 member.mine.yaml 后，标准 LinkML 生成器读取 YAML。这里不宣称前周的 Markdown 未被构建程序读取。

模型变更例子：增加必填日期 registration_reviewed_at，含义是“注册关系核查日期”，不表示会员入会日期。示例假定两对象关系均于 2026-08-31 核查；生产数据未自动获得这个值。学员仍需按来源提供它。实际 before/after、生成差异、旧实例拒绝结果见运行目录，不用修改生成文件。
