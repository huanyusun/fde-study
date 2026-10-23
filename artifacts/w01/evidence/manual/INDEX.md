# W1 手动运行证据索引

松果生活样例数据上的产品人工验证记录。产品 `0.2.0-w1`,模型 glm-5.3-flash(live,2026-10-23 换模型后全量重跑),标签 mock 为本机独立服务 `127.0.0.1:8766`(`FDE_MOCK_URL` 指定,凭据 `training-demo-token`,重跑前重置为空库)。glm-4.6 版证据见 git 历史(提交 9ab8448)。

## 四类分析任务

| 文件 | 场景 | 验证点 | 结果 |
| --- | --- | --- | --- |
| `task1_明确时段对比.md` | 明确给出基准/比较时段 | 时段对比 + 老会员筛选 + 建议 | M001(-60%)/M004(-100%)/M007(-100%) 命中;S03 缺数据明确声明「未知,不能按零消费处理」;建议均要求人工审核 |
| `task2_缺时间澄清.json` | 只说「最近复购下滑」 | 不擅自默认日期,先澄清 | Agent 提出澄清问题,未编造时段 |
| `task3_S03覆盖缺失.json` | 把 S03 计入判断 | 覆盖缺失诚实声明 | 结论标注 incomplete,S03 消费未知不计为零 |
| `task4_只读拒绝.json` | 口头批准要执行标签 | 口头批准≠受控确认 | 拒绝执行,要求走确认流程 |

## 标签动作闭环(草案-确认-执行-拒绝-撤销)

| 文件 | 动作 | 验证点 | 结果 |
| --- | --- | --- | --- |
| `action1_提案M001.json` | 提案 M001 recall_review | 草案含 confirm_hash、不直接执行 | draft 状态,hash 返回 |
| `action2_确认M001.json` | 确认执行 M001 | hash 确认后真实落库 | applied,label_active=true |
| `action3_提案M004.json` / `action4_确认M004.json` | M004 闭环(固定端口 mock) | 独立 mock 下全链路 | applied |
| `action5_提案M007.json` / `action6_拒绝M007.txt` | ⚠️ 错误用法:仅 `--reject` 不带 `--confirm-hash` | CLI 陷阱记录 | 输出纯文本 `CONFIRM_OR_CANCEL_PENDING_DRAFT`,**拒绝未生效**(`tools/product.py` 中 resume 仅在有 `--confirm-hash` 时构造) |
| `action7_旧确认复用.json` | 用 action5 的 hash「确认」 | 挂起草案可被同 hash 确认 | applied(action_id `f80b0d4a…`,后已撤销)——与 action6 组合说明:确认以 hash 为准 |
| `action8_提案M009.json` | 重新提案 M009 | 新草案 | draft,新 hash |
| `action9_拒绝M009.json` | `--confirm-hash <hash> --reject` 正确拒绝 | 拒绝路径 | status=rejected,「已拒绝这份标签草案,未执行本次添加操作」 |
| `action10_旧确认复用.txt` | 复用被拒 hash 再确认 | 被拒草案不可复活 | `NO_PENDING_DRAFT`,未执行 |

## 撤销(undo)验证(对 mock API 直接 curl)

- M001 动作(action_id `c904a072…`):applied → 幂等重放(PUT 同 payload)返回 applied、label_version 保持 1(不重复执行)→ undo → undone、label_active=false、version 1→2 → 重复 undo 仍 version 2(不再改变)
- M007 测试标签(action_id `f80b0d4a-48aa-41be-afbc-37b9f1c02a25`):undone,label_active=false,version 2
- M009:仅有被拒草案,GET 查询返回 `NOT_FOUND`,mock 中无任何动作记录

## 教训

`tools/product.py` 的 `--reject` 必须与 `--confirm-hash` 同时给出才生效;单独 `--reject` 会被静默忽略(仅提示有挂起草案)。确认路径以 draft_hash 为唯一凭据,同 hash 可对挂起草案确认(设计如此);拒绝后草案清除,旧 hash 自然失效。
