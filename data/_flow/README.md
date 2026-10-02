# 数据流转日志

本目录存放分区流转的**共享事实**，是各 Agent 之间同步状态的依据之一。

- `journal.jsonl`：append-only 日志，一行一条流转记录。**只由 flow 命令追加，任何人不手改。**

每条记录的字段：

| 字段 | 含义 |
| --- | --- |
| `ts` | 流转时间（ISO 8601） |
| `actor` | 操作者（命令的 `--by` 参数） |
| `action` | `submit` / `withdraw` / `claim` / `recall` / `publish` / `return` / `drop` |
| `key` | 产品键（`品类/产品id`） |
| `from` / `to` | 流转前后的分区（`draft` / `intake` / `review` / `library` / `null`） |
| `reason` | 召回 / 退回 / 剔除的原因 |
| `fingerprint` | 内容指纹（召回、剔除时记录，用于事后比对/找回） |
| `supersedes` | 该产品是订正稿（库内有同 id，入库时整条替换） |
| `forced` | claim 时带 `--force`（校验不过仍认领，由审核方在修正区处理） |

查询方式：`npm run flow:log [-n 条数]`，或 `npm run flow:status` 看各区现状 + 最近流转。

规则与协议见仓库根目录 [AGENTS.md](../../AGENTS.md)。
