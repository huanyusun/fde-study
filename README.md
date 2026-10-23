# FDE Study — 青禾优选 W1 沙盘

FDE(Forward Deployed Engineer)课程的完整学习仓库。本仓库根目录同时是课程要求的**客户交付工作目录**:标准产品工程包解压于此,四份 JSON 作业契约与立项报告按固定路径产出,后续各周继续沿用本仓库与条目编号。

- 课程产品:`0.2.0-w1`,能力矩阵 `w1-capabilities-0.2.0`
- 契约:fit-gap `w01-0.2.1`,其余三份 JSON `w01-0.2.0`
- 客户:青禾优选(连锁零售,虚构沙盘);发起人沈总,诉求「复购下滑 + 识别重点会员 + 直接给运营建议」

## 目录结构

```
├── artifacts/w01/          # W1 四份 JSON 交付物 + fit-gap 填写稿(任务书固定路径)
├── contracts/w01/          # 作业 JSON Schema(字段定义唯一来源)
├── platform/fde_product/   # 标准产品源码(LangGraph Agent、业务、动作、交互、观测)
├── product/                # capabilities.json 能力矩阵、API.md、语义、系统提示词
├── tools/                  # product.py、check_product.py、verify_product.py 等
├── sample_data/            # 松果生活样例数据(与青禾无关,勿用于推算客户)
├── evals/                  # Promptfoo 基础评估
├── tests/                  # 产品回归测试
├── docs/w01/               # project_assessment.md 立项报告(交付物)落此
├── course-materials/w01/   # 课程材料包:邮件/协作/指引/任务书/fit-gap 空白表/案例手册/访谈准备
├── lectures/w01/           # W1 八讲 PPT(PDF 本地保留不进 git,索引见其中 README)
├── notes/w01/              # 我的学习笔记(按 V01–V08 一讲一文件)
└── README.md
```

## W1 交付物(任务书契约)

| 固定路径 | 内容 |
| --- | --- |
| `artifacts/w01/environment_check.json` | 9 项环境检查(runtime/database/tool_registry/product/model_api/checker/label_api/evaluation/trace) |
| `artifacts/w01/product_fit_gap.json` | 逐项诉求适配判断(五类分类 + 待判断)、证据状态、依据与下一步 |
| `artifacts/w01/model_baseline.json` | 真实模型基线:≥4 次场景运行、失败分类与下一步 |
| `artifacts/w01/runtime_evidence.json` | 7 类行为证据文件路径 + SHA-256 |
| `docs/w01/project_assessment.md` | 立项报告:诉求拆解、事实/转述区分、适配判断、风险、下一阶段建议 |

## 常用命令(工程根目录)

```sh
python3 -m venv .venv && .venv/bin/python -m pip --isolated install -r requirements.txt
.venv/bin/python tools/product.py init
.venv/bin/python tools/check_product.py --dry-run
FDE_MODEL_URL=... FDE_MODEL_NAME=... FDE_MODEL_KEY=... .venv/bin/python tools/product.py start --actions
.venv/bin/python tools/verify_product.py --live          # 生成模型基线与运行证据
.venv/bin/python tools/check_product.py --root .         # 公开预检
```

模型配置:`FDE_MODEL_URL`(完整 Chat Completions 地址)+ `FDE_MODEL_NAME` + `FDE_MODEL_KEY`,课程网关用 `FDE_MODEL_PROFILE=gateway-low`;详见 `docs/model-configuration.md`。

## 学习路线(W1)

1. 读材料包(`course-materials/w01/00–05` 顺序)+ 八讲 PPT,笔记落 `notes/w01/`
2. 装环境、跑通松果样例四类分析任务与标签动作闭环,留运行记录
3. `verify_product.py --live` 生成基线与证据 → Promptfoo 评估 → `finalize_evaluation.py`
4. fit-gap 空白表填写 → 转换 JSON;写立项报告
5. `check_product.py --root .` 预检,提交
