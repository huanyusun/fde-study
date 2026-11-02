# FDE Study — 青禾优选 W03

FDE 交付实战营学习与客户交付仓库。当前 W03 工作目录已升级到 `fde-student-w03-0.1.0-c16` 工程，配套材料为 `w03-0.1.0`（2026-11-01 重打包）、任务书 v0.3。W01 学习笔记、访谈记录和交付物保留原路径。

## 从这里开始

1. 阅读 [W03 材料说明](course-materials/w03/00_使用说明.md)和[作业任务书](course-materials/w03/05_作业任务书.md)，按任务书中的 12 步作业路线执行。
2. 按 [W03 安装与使用](docs/w03/README.md)新建 Python 3.11 虚拟环境并安装 `requirements-w03.txt`，配置方式见[模型配置](docs/model-configuration.md)。
3. 先跑梧桐独立样例，再准备自己的 W03 业务模型、访谈、指标构建 Skill 和独立判定程序。

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip --isolated install -r requirements-w03.txt
.venv/bin/python tools/w03.py doctor
```

本目录已执行 `tools/w03.py init --workspace .`，不要重复初始化。`customer/w03/` 和 `docs/w03/` 中的作业文件目前是课程模板，尚未实现、核定或完成；规模数据已解压到 `materials/data/large/`。依赖安装与样例闭环尚未执行。

## 目录索引

| 路径 | 内容 |
| --- | --- |
| [lectures/w03/](lectures/w03/README.md) | V01–V09 九份 PDF 课件，本地保留、不进入 Git |
| [course-materials/w03/](course-materials/w03/00_使用说明.md) | 最新任务书、客户资料、访谈参考、案例与原始 ZIP |
| [course-materials/w03/W02_checkpoint/](course-materials/w03/W02_checkpoint/README.md) | 课程提供的 W02 参考答案，单独保存，不代表本人完成的作业 |
| [materials/w03/](materials/w03/00_材料说明.md) | 工程读取的青禾业务资料 |
| `materials/data/small/`、`materials/data/large/` | 青禾小样本与规模数据；规模 CSV 不进入 Git |
| [docs/w03/](docs/w03/README.md) | 工程说明、构建与测试指南、W03 作业文档模板 |
| `customer/w03/` | 构建配置、38 项指标目标、12 项维度查询目标、Skill 和判定程序模板 |
| `artifacts/w03/` | 后续指标构建和测试产物目录 |
| `platform/fde_product/`、`tools/` | 升级后的运营 Agent、W02 工具与 W03 构建/加载/测试命令 |
| `examples/w03/` | 梧桐独立样例，仅用于环境验证和方法参考 |
| [docs/w01/](docs/w01/README.md)、[notes/w01/](notes/w01/README.md)、[artifacts/w01/](artifacts/w01/README.md) | 保留的 W01 个人成果 |

W03 交付要求与边界以任务书为准。业务规则由自己的指标构建 Skill 从资料与业务模型生成；接入层仅原样读取 CSV。课程 W02 checkpoint 必须标明参考来源，不能作为本人访谈记录。

导入来源、压缩包 SHA-256 和工程/课件文件清单见 [import-manifest.json](course-materials/w03/import-manifest.json)。原 W01 仓库说明保存在 [docs/w01/repository-readme.md](docs/w01/repository-readme.md)，工程版本说明见 [RELEASE.md](RELEASE.md)。
