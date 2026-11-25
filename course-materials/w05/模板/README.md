# W05 请求与报告模板

这些是原生 JSON 空白模板，直接填写并保存即可作为工程输入，不需要从表格或 Markdown 再转换。模板未附代码答案、运行结果或通过标记。安装和参数细节见工程包 `docs/w05/README.md`，执行及提交要求见[任务书](../05_作业任务书.md)。

先把需要的模板复制到自己的工程工作目录，替换所有 `YOUR_*`。命令从解压后的工程根目录执行，相对路径也按该目录解析；先建立工作父目录，输出目标本身保持尚不存在。每次输出使用新路径，以下命令中的 `YOUR_*` 同样需要替换。

| 模板 | 用法 |
| --- | --- |
| [prepare.json](prepare.json) | 填原始 v2、自己的 W04 c3 清洗目录、有效指标库及客户源码；源码同目录须有填好的 `member.linkml.yaml`；执行 `python tools/w05.py prepare --input prepare.json --output YOUR_NEW_PREPARED` |
| [bind.json](bind.json) | 填新准备目录、运行 home 和同版源码；执行 `python tools/w05.py bind --input bind.json --output YOUR_NEW_BIND_RESULT.json`，再按工程说明初始化该 home |
| [cohort.json](cohort.json) | B 组主条件短信请求；执行 `python tools/w05.py service-call --binding YOUR_HOME/member-binding.json --input cohort.json --output YOUR_NEW_COHORT_RESULT.json`；第二家门店另存请求 |
| [detail.json](detail.json)、[relations.json](relations.json) | 填自己计算出的统一 ID，用同一个 `service-call` 入口分别查询会员与关系；不填教师示例 ID |
| [knowledge.json](knowledge.json) | 按实际问题检索书面依据，保留来源版本与适用条件 |
| [mvp_v1_report.json](mvp_v1_report.json) | 填写本周同一份报告，空数组和 `not_run` 不表示通过；数据及规则版本与自己的实际准备结果一致 |
| [export.json](export.json) | 填写准备目录、报告、客户 `solution.py` 及当前 `member-binding.json` 四个路径；执行 `python tools/w05.py export --input export.json --output YOUR_NEW_SUBMISSION`，随后按任务书补齐其他提交文件 |

对象定义的唯一源在工程 `customer/w05/member.linkml.yaml`，直接填写包内模板，不在本目录维护第二份模型。导出会附客户源、YAML、依赖锁和模型生成／绑定记录；完整 Markdown、有效指标库、状态和原始证据仍按任务书补齐。

`baseline_evidence`、`current_evidence`、每组 `evidence_files` 中的路径都相对提交根目录，例如 `evidence/before/normal.json`，对应文件须实际复制进去。不同实现的统一 ID 可不同，验证按来源关系和结果含义核对。

`change_log` 每项说明修改位置、原因、前后版本、预期影响及前后证据；`time_log` 每项记录阶段、起止时间、实际分钟数及是否为等待。`scope_and_evidence` 记录模型及口径变化、材料和沟通来源、推断、未决影响及范围判断，可按实际情况扩展，不预填发生过的访谈或客户确认。

用命令行保留同一 Agent 会话时，第一次 `tools/product.py run` 的输出中取得实际会话 ID，后续调用传入 `--session`。运行结果完整另存，不能只复制摘要；具体配置仍见工程说明。所有调用只做分析和建议，不使用动作开关。
