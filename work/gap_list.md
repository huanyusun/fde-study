# W05 缺口清单（路线第 1 步）

> 依据五份客户材料（`course-materials/w05/客户材料/01~05`）、`data/w05-v2/` 数据实测与 `coverage.json` 整理。

## 1. 无关联边孤立账户能否视为独立自然人？
- 缺口：在 `migration_records.csv` 与 `account_review_records.csv` 中没有任何关联边的 CRM/POS 来源账户，是否可以全部视为独立自然人（`verified_singletons`）？
- 影响：直接影响 `identity_evidence` 返回的 `verified_singletons`，进而影响已核实会员总数、未决独立财务桶数量及所有人数类指标。
- 已有依据：`data/w05-v2/coverage.json` `account_review`（声明已核对两来源全部导出账户开户/迁移留档，未确认登记人的例外由 `operational_verification.csv` 列明，其余未列关联来源为独立开户对象）；数据实测 `operational_verification.csv` 中 `kind=abnormal_identity` 共 `12,001` 个 CRM 账户（且均无任何关联边）。
- 下一步：**材料与覆盖声明已明确，直接引用**——仅将 `all_source_ids - abnormal_identity_ids` 纳入独立开户资格，12,001 个异常身份账户保留为未决独立财务桶（`unresolved`）；全公司精确自然人数保留待核，后续向老周补证登记人留档。

## 2. 导出外账户引用（11 条 `account_review_records.csv`）如何处理？
- 缺口：`account_review_records.csv` 第 35928–35938 行共 11 条 `same` 记录的右端 CRM 账户不在本次 `crm_member_export.csv` 中，是否建边或补行？
- 影响：影响 `identity_evidence`（若强行建边会触发 `EVIDENCE_SOURCE_NOT_FOUND`）及对应 11 个左端账户的完整消费历史。
- 已有依据：`03_身份关联与数据使用说明.md` 第二节（“引用的账户如果不在本次导出中，保留历史引用和缺失说明，不凭空补出账户资料或订单”）；`coverage.json` `limits`（“引用导出外账户保留缺失，不新增来源行”）。
- 下一步：**材料已明确，直接引用**——不建边，将这 11 条记录及缺失右端账户信息写入 `findings`，并保留待核向老周确认历史归档范围。

## 3. 非 `success` 迁移记录（3 条）如何处理？
- 缺口：`migration_records.csv` 第 39918–39920 行存在 `failed`、`revoked`、`unknown` 各 1 条历史尝试记录，是否采信或视为不同人？
- 影响：影响 `identity_evidence` 边集与 `findings`。
- 已有依据：`03_身份关联与数据使用说明.md` 第二节（失败/撤销/失效/状态不明不能作为当前自动合并依据，且迁移失败也不等于确认是两个人）。
- 下一步：**材料已明确，直接引用**——经 `current_records(..., states=("success",))` 过滤不建边，并将 3 条记录及原因写入 `findings`。

## 4. 旧 POS 账户缺少注册门店与卡务导出如何处理？
- 缺口：`pos_member_export.csv` 仅含 `pos_member_id`、`name`、`mobile`，无注册门店与卡务字段，是否可用 POS 订单的 `shop_cd`（购买门店）反填？
- 影响：影响 `member_attributes` 的 `registered_stores`、单店圈选名单及门店范围说明。
- 已有依据：`02_W05新需求说明.md` 第四节、`03_身份关联与数据使用说明.md` 第一、三节、`coverage.json` `limits`（购买门店不能代替注册门店；POS 独有缺少注册门店保持未知，不反填，单店查询只说明范围缺口）。
- 下一步：**材料已明确，直接引用**——POS 账户 `registered_store` 恒为 `None`，`registered_stores` 仅汇总 CRM 来源注册门店；POS 补导保留待核（老周）。

## 5. CRM 姓名缺失标记与多来源属性冲突如何区分？
- 缺口：`crm_member_export.csv` 的 `nm` 列含空串（4,179）、`NULL`（888）、`无`（521）、`-`（112）；多来源合并后若姓名或等级不同，如何返回 `display_name`、`tier`、`conflicts`？
- 影响：影响 `member_attributes` 输出，以及 A/C 组验证对“属性冲突 / 真实缺失 / 正常值”的区分表达。
- 已有依据：`03_身份关联与数据使用说明.md` 第三节、`05_作业任务书.md` 第三节第 2 步、`06_输入与工程说明.md` 第三节（缺失标记不能当真实姓名或制造假冲突；多来源真实不同值记入 `conflicts` 且 `display_name`/`tier` 为 `None`）。
- 下一步：**材料已明确，直接引用**——规范化过滤缺失占位符（`""`/`"NULL"`/`"无"`/`"-"`），真实多值记录冲突并置代表属性为 `None`。如未来业务需要冲突展示优先级，再向小林/老周确认（记为待核）。

## 6. 员工与异常身份核验的作用范围是否一致？
- 缺口：`operational_verification.csv` 中 `employee`（307 条）与 `abnormal_identity`（12,001 条）是否都直接排除整个统一会员？
- 影响：影响 `contact_constraints` 的 `member_excluded`、`account_exclusions` 与 `all_source_accounts_excluded`。
- 已有依据：`04_运营对象核验说明.md` 第一节与 `operational_verification.csv` 的 `scope` 列（员工为 `member`，通过已核实身份作用于整个会员；异常身份为 `account`，只排除指定来源账户，不无条件传播给其他账户）。
- 下一步：**材料已明确，直接引用**——严格按 `scope` 区分处理。

## 7. 联系限制来源（CRM 备注、勿扰工作账、补充确认、回访名单）及 26 条渠道待核如何处理？
- 缺口：CRM `tag` 列有 443 条含 `勿打电话`/`勿发短信`（含空格/斜杠分隔写法）；小林勿扰工作账 121 条仅有原因无渠道，配套 `contact_scope_confirmation.csv` 确认了 95 条（`telephone` 27、`sms` 42、`all` 26），另有 26 条为 `status=pending, channel_scope=unknown`；如何计算双渠道状态？
- 影响：影响 `contact_constraints` 返回的 `channels`、`status`、`restriction_evidence`，及 B/C 组推荐与不建议判断。
- 已有依据：`05_联系限制与建议说明.md` 第一节、`docs/w04/business_model.md` R7、数据实测。
- 下一步：**规则已明确，26 条待核保留待核**——代码合并全部来源限制，明确禁止置 `blocked`，`pending/unknown` 置 `unknown`（绝不推定允许），并由小林后续补证确认那 26 条的渠道范围。

## 8. 指标库中仍保留 W04“CRM 账户”与“POS 未导出”描述
- 缺口：W04 指标库 `work/library/` 的 `scope.json`、`catalog.json`、`metrics.yml` 仍描述为“CRM 会员账户”或旧口径，未反映 `buyer_count` 已变为“购买财务实体数”及 POS 已接入。
- 影响：影响指标查询结果说明与 Agent 对 `buyer_count` 首句粒度的正确表达（E 组验证）。
- 已有依据：`05_作业任务书.md` 第三节第 4 步、`06_输入与工程说明.md` 第四节。
- 下一步：在路线第 4 步按规范更新 `work/library/` 的 `catalog.json`、`metrics.yml`、`scope.json` 并用新准备目录重跑生效。
