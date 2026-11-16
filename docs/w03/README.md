# W03：运营 Agent 能力升级

你仍使用原来的运营 Agent 和聊天入口。本周新增“按指标库理解问题，生成并执行查询，再解释结果”的能力。指标构建和指标校验是两个命令行辅助工具，不增加问数网页，也不要求自备 coding Agent。

编写方法先读[构建 Skill 编写指南](skill-guide.md)；它说明六段怎样写、复杂资料怎样处理，以及怎样根据失败记录迭代。安装与操作继续按本文执行。

## 安装与样例闭环

已在 macOS、Python 3.11 上验证；Windows、Linux 如遇问题，请反馈给课程方。保留旧目录，在新目录解压 W03 包；新建 Python 3.11 虚拟环境，安装 `requirements-w03.txt`。dbt、MetricFlow 与 DuckDB 已锁版本，不要在 W02 原环境直接升级依赖。本机没有 `python3.11` 命令时，用你安装 Python 的工具找到 3.11 解释器的完整路径，代替下面第一行的 `python3.11`（例如 uv 可用 `uv python find 3.11`），其余命令不变。

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip --isolated install -r requirements-w03.txt
.venv/bin/python tools/w03.py doctor
```

Windows：先在 PowerShell 执行 `setx PYTHONUTF8 1`，关闭并重新打开所有 PowerShell 窗口后再安装和运行；不开启 UTF-8 模式，读取课程文件时会报 `UnicodeDecodeError: 'gbk' codec can't decode`。建环境用 `py -3.11 -m venv .venv`，其余命令把 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。

按 `docs/model-configuration.md` 配置自己的 `FDE_MODEL_URL`、`FDE_MODEL_NAME`、`FDE_MODEL_KEY`，需支持原生工具调用。`doctor` 只检查配置是否存在，不验证网络。密钥不写入作业和版本库。

```sh
.venv/bin/python tools/w03.py load --library examples/w03/library --data examples/w03/data --project .runtime/wutong-v1 --activate-home .runtime/product
.venv/bin/python tools/product.py start --home .runtime/product
```

打开原聊天页面 `http://127.0.0.1:8765`，问“2026 年 8 月梧桐书店扣退后收入是多少？”。正确样例为 130 元；数据里的金额为分。加载会创建数据库和 dbt 项目，已存在的项目目录不覆盖；每次修改库后用新版本路径加载，并重启 Agent。已经加载过、当时没有加 `--activate-home` 的项目，用 `tools/w03.py activate --project 项目路径 --home .runtime/product` 接入聊天，再重启 Agent。加载失败时绑定不变，输出中的 `active_project` 就是聊天仍在使用的项目。

样例校验实际调用同一标准问数内核（自然语言理解、原生查询、解释），不解析题目另查一遍：

```sh
.venv/bin/python tools/w03.py test --project .runtime/wutong-v1 --cases examples/w03/tests.json --output artifacts/sample-test-v1 --judge-command .venv/bin/python examples/w03/judge.py
```

`examples/w03/build.json`、`build-metrics/SKILL.md` 展示从梧桐资料构建完整语义模型、派生模型和指标库的六段方法，青禾作业仍须依据青禾资料自行开发和迭代。详细步骤见[梧桐样例走读](wutong-walkthrough.md)。可调用 `build --config examples/w03/build.json --output artifacts/sample-build-v1` 验证。示例判定只处理单指标单行，青禾作业必须开发自己的实现，不能直接复制后声称覆盖全部场景。

## 青禾开发与使用

```sh
.venv/bin/python tools/w03.py init --workspace .
.venv/bin/python tools/w03.py build --config customer/w03/build.json --output artifacts/w03/build-v1
```

先完成 W03 业务模型和材料准备，再编写 `customer/w03/build-metrics/SKILL.md`。默认 `UNIMPLEMENTED` 会阻止构建。业务输入在 `materials/w03`，业务模型在 `docs/w03/business_model.md`；targets 只有 38 项 ID 与名称；dimension_targets 只有 12 项查询 ID、中文名和业务含义。构建文件路径相对于 build.json。Skill 由本工具通过你配置的模型 API 执行，无需额外的 coding Agent。

构建配置的 `data` 指向检查所用 CSV 数据目录。框架只提供原样接入表和 manifest 时间骨架；Skill 生成全部业务模型。构建先保存输入、响应、来源检查和三项确定性检查，全部通过才输出库。修改 Skill 后使用新输出目录，保留失败证据。

可以按 ID 选择 `--metrics`，但每批必须依赖闭合，完整语义模型在各批中同名同内容。`merge --inputs 路径1 路径2 --data materials/data/small --output artifacts/w03/library` 遇到同名模型内容冲突会停止；不再只合并 measures。复杂相互依赖的指标建议一次生成。

定稿库固定放在 `artifacts/w03/library`，一律用 `merge` 生成；只有一个构建目录时也用 `merge` 单输入提升：

```sh
.venv/bin/python tools/w03.py merge --inputs artifacts/w03/build-v3 --data materials/data/small --output artifacts/w03/library
```

`merge` 不写入已存在的目录。更新定稿库时，先把旧的 `artifacts/w03/library` 改名留存或删除，再执行上面的命令；不要把新构建目录复制覆盖到旧目录上，旧版本留下的 SQL 文件会被一起加载。定稿库变化后，用新版本路径重新加载并重跑测试。

完整库通过检查后加载小样本；路径假设数据包放在 `materials/data`：

```sh
.venv/bin/python tools/w03.py load --library artifacts/w03/library --data materials/data/small --project .runtime/qinghe-small-v1 --activate-home .runtime/product
.venv/bin/python tools/product.py start --home .runtime/product
```

聊天入口此时使用青禾指标库。原松果消费比较和样例标签功能保留，但只用于松果独立样例。青禾查数不等于已支持自然语言圈选、营销执行或身份合并。

自行开发 `customer/w03/tests.json` 与 `judge.py`（可替换为其他后端语言）。测试框架把期望和 Agent 实际结果通过标准输入交给判定程序；程序输出一份 JSON。默认判定文件会报 `STUDENT_JUDGE_REQUIRED`，测试前必须实现。完整接口和字段见 [契约](contract.md)。测试集、独立期望、判定程序自检和结果定位的写法见[测试与判定编写指南](test-guide.md)。

```sh
.venv/bin/python tools/w03.py test --project .runtime/qinghe-small-v1 --cases customer/w03/tests.json --output artifacts/w03/test-small-v1 --judge-command .venv/bin/python customer/w03/judge.py
```

在规模数据上新建 `.runtime/qinghe-large-v1` 再验证；期望必须基于对应数据集独立计算，不能照抄小样本答案。最后将选定报告复制到 `artifacts/w03/metric_test_report.json`，执行 `check --workspace .`。预检检查交付结构、指标与维度目标覆盖及自报结果，并核对报告中实际执行的查询来自由当前 `artifacts/w03/library` 加载的项目（`catalog_sha256` 一致）；定稿库换过就要重新加载并重跑测试。教师另查语义与错误注入。

## 接续 W02 业务模型

W02 提取工具代码、Skill 默认版与输入输出契约没有改动。不覆盖 W02 的已交文档；将自己的模型复制为 `docs/w03/business_model.md`，保留 W02 原版。缺少起点可用 W03 材料包 `W02_checkpoint/` 文件夹中的 W2 checkpoint（W02 参考答案），注明采用情况。

沿用 `tools/w02_workflow.py` 的 init、inspect、start、report、review、resume、revise、apply。初始化后，在 `customer/w02/workflow.json` 中把 business_model、notes 分别指向 `docs/w03/business_model.md` 和 `docs/w03/interview_notes.md`，goal 写本周缺口；在 extraction.json 中替换成自己的 W03 导出访谈。所有路径相对于工作空间。也可另存任务配置，再给 inspect/start 的 `--task` 指定文件。报告和运行档案仍位于 `artifacts/w02`，这是复用工具的内部路径，并不代表输出退回 W02。

导出访谈沿用 W02 transcript 格式并标 week=3，提取工具直接兼容。运行前 `inspect` 核对目标路径，核查后才 `apply`。若新事实没有进入新模型，需继续调整提取目标、提示词或 Skill；保留迭代记录，不能只提交一个文件名变为 W03 的旧模型。

原始业务文档均为 Markdown，数据为 CSV；访谈服务的可验证导出沿用 W02 JSON 契约（含正文、角色和原始消息 ID），直接交给原提取工具。构建工具通常读取更新后的模型即可；要补充访谈正文时，把相关原文和消息 ID 保存为 Markdown 材料，不另开发文件格式解析工具。你提交的指标核定记录由你汇总来源、冲突与访谈确认形成，课程方不在首发包提供完整答案表。

## W03 访谈与必要时的事实补充

W03 访谈页面与 W01／W02 一样：选择周次和角色、预约、聊天、导出。将定义或查询证据带回去核查时，直接继续普通访谈；不另开回访入口，不要求每个角色谈两次，也没有额外回访配额。原网页整页刷新后生效，账号和历史保留。

业务信息遗漏或 Agent 回答不稳定造成阻断时，课程方决定是否直接分发事实补充。它不是默认定时发放，也不从 Agent 页面领取。补充只含原始业务信息，MD 供阅读，同源 JSON 兼容现有 W02 提取工具；完整 W03 模型、指标库和测试答案不在其中。

收到补充后，把 JSON 放进自己的工作空间，按实际相对路径加入 extraction.json 的 sources，与真实导出并列保存。不要把 MD 填入只接受 JSON 的 sources。补充文件明确标为 origin=fixture、课程方材料版本与来源编号，没有编造自己的问题；不能冒充本人访谈或充抵必访证据。提取目标／自己的 Skill 应区分两种来源、合并重复但保留引用、将真正矛盾留待核查；审阅后再 apply。W02 工具源码、默认 Skill 和契约无需升级。

## 失败与恢复

先看运行目录的 trace、source_check、grain_check、dimension_check、metricflow_check 或 validation-project/build.log。失败不当零，未定义不猜测，零分母不填 0。Skill 缺失先开发；来源不匹配检查引用连续原文；原生编译失败查字段、粒度、依赖和公式；模型失败查自己的 API 配置与预算。每次修改新建版本路径，保留原失败证据。停止聊天服务后再切换加载项目。
