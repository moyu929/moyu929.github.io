# 多 Agent 协作规范

> 本文件对本仓库的**所有协作者**生效：不论你是 CodeBuddy、Trae、Claude Code 还是别的客户端，也不论你是人类。
> 技能定义在 [`skills/`](skills/)（客户端无关）；各客户端的私有目录（`.trae/`、`.claude/`）里只放指向 `skills/` 的指针。
> 数据采集/核验的详细规范在 [`skills/appliance-data-curation/SKILL.md`](skills/appliance-data-curation/SKILL.md)，**动手前先读它**。

---

## 1. 一句话规则

**动手改数据前先跑 `npm run audit:status`；被审核快照冻结的产品，在快照 `release` 之前谁都不能改。**

---

## 2. 角色与分工

| 角色 | 职责 | 常态可改范围 |
| --- | --- | --- |
| **采集 Agent（A）** | 敏捷响应修改要求；采集、补录、订正产品信息 | `data/`、`public/images/`、`scripts/`、页面代码 |
| **审核 Agent（B）** | 用户下达审核指令时，先**快照审核范围**，再逐条核对并出报告 | `docs/audit/`、`data/_locks/` |
| **用户** | 下达指令；审核完成后决定由哪一方接整改 | — |

- 同一个 Agent 可以轮换承担 A / B 角色；**具体由用户指派**（一般看哪方空闲）。
- A 与 B 之间不直接协商，**通过用户与被提交到仓库的文件**（快照锁、审核报告）同步状态。

---

## 3. 审核冻结协议（核心）

并行工作最大的风险是：A 在加新品类/新型号的同时，B 正在审核一批产品；
A 的改动让 B 的审核结论基于过期数据，或 B 报告的结论被 A 顺手改掉。

解决办法是**快照 + 冻结 + 事后校验**：

```
用户下达审核指令
      │
      ▼
① B 冻结范围   npm run audit:snapshot -- --label "空气净化器验收" --by agent-b --category air-purifier
      │         └─ 写入 data/_locks/<id>.json：范围清单 + 每款产品的内容指纹（含字段级）
      ▼
② 冻结期       A 不得修改范围内产品的任何字段（增删条目、改 img 同样禁止）
      │         A 仍可自由改动：其它品类、范围外的产品
      │         需要越界时：先请用户/B 执行 audit:release，再改
      ▼
③ B 逐条审核   B 在 docs/audit/ 出报告（模板见第 8 节），可随时用 npm run audit:check 确认没人动过
      │
      ▼
④ B 解除冻结   npm run audit:release -- <id> --note "审核完成"
      │
      ▼
⑤ 用户指派     A 或 B 按报告整改 → 改字段 + 同步更新 6 个审核标注字段 → 提交
```

**命令速查**

| 命令 | 用途 |
| --- | --- |
| `npm run audit:snapshot -- --label "标签" --by agent-b [--category 品类...] [--product 品类/产品id...]` | 拍快照并冻结；不给范围=全站冻结；范围过大时只记整条指纹 |
| `npm run audit:status [品类[/产品id]...]` | 查某范围是否被冻结（**改动前先查这个**） |
| `npm run audit:check [-- --strict] [-- --json]` | 检测冻结范围内是否有人越界改动；`--strict` 有违规时退出码 1 |
| `npm run audit:diff -- <快照id>` | 看具体哪几款、哪些字段被改了 |
| `npm run audit:release -- <快照id> --note "说明"` | 解除冻结；若冻结期内有改动，会记录在快照里 |
| `npm run audit:list` | 列出所有快照与状态 |

**设计取舍**

- **粒度到「单款产品」而不是「整个文件」**：`products.json` 是一个品类一个文件，
  锁文件级会让 A 连该品类的新型号都不能加；锁到产品才能做到「审核期间照常扩品类」。
- **快照文件入库**（`data/_locks/*.json`）：它是两个 Agent 之间的共享状态，
  不入库则双方看不到对方的冻结。文件含哈希，不含原始数据，体积可控。
- **`audit:check` 是提醒而不是闸门**：`npm run check` 会跑它，但 CI（`deploy.yml`）只跑
  `validate` + `build`，不会因为越界改动而挂掉部署——否则用户临时要求改冻结数据时会被卡死。
  越界必须**在提交信息里写明**，并在快照 `release` 时留 `--note`。

---

## 4. 提交与推送纪律

- 一次提交只做一件事；提交信息前缀：`feat` / `fix` / `data` / `docs` / `chore`。
- **改数据的提交必须写明来源与核验方式**，例如：
  `data: 补录洗地机 5 Pro 参数（来源：太平洋规格表 + 小米商城在售价）`。
- 推送前跑 **`npm run check`**（= `validate` + `audit:check`）；有 error 不得推送。
- 只推 `main` 触发部署；**不 force push `main`**；**不修改 git 配置**。
- 改动了审核标注字段的提交，在信息里点出「已更新核查状态/来源」。

---

## 5. 目录所有权

| 路径 | 谁能改 | 说明 |
| --- | --- | --- |
| `data/<品类>/products.json` | A（**未冻结的**产品） | 产品数据；冻结产品见 `data/_locks/` |
| `data/<品类>/schema.json` | A | 字段定义；新增字段要全品类一致 |
| `data/categories.json` | A | 品类清单与首页顺序 |
| `data/_sources/**` | A 写，B 读 | 溯源、补丁、图片与抓取清单；**B 审核时只读** |
| `data/_cache/**` | 任何人生成 | 抓取缓存，**已 gitignore**，不入库 |
| `data/_locks/**` | **只有 B** | 审核快照锁；A 只读 |
| `docs/audit/**` | **只有 B** | 审核报告归档；A 只读 |
| `public/images/**` | A | 产品图，文件名 = 产品 id |
| `scripts/**` | 谁都行，改了要说明 | 采集/校验工具 |
| `src/**` | A | 站点代码 |
| `skills/**`、`AGENTS.md`、`README.md`、`HANDOFF.md` | 谁都行 | 规范与文档 |

---

## 6. 数据红线（摘要）

完整版见 [`skills/appliance-data-curation/SKILL.md`](skills/appliance-data-curation/SKILL.md)。

1. 收录**中国大陆的多品牌**型号：小米/米家自有品牌与主流家电品牌同等收录、同等展示，
   分组维度是品牌，不是「小米 vs 竞品」；海外版、港台版、白牌不收。每款产品必须有 `brand` 字段。
2. 数值**必须可溯源**；查不到就写 `查不到`，**禁止估算、换算、补零**。
3. 只采公开信息：不抓登录后内容、不绕过访问控制、不收录个人信息或商业秘密。
4. 每款产品必须带 6 个审核标注字段（`verify_status` / `verify_date` / `verify_source` /
   `verify_url` / `change_log` / `updated_at`），且状态判定要能从 `data/_sources/` 里查到依据。
5. 第三方来源有系统性错标（如把 `2800W` 写成 `28W`、把 `L` 写成 `ml`），
   对可疑值一律留空，别照抄。
6. **媒体（含 AI 聚合内容）只能印证，不能单独定值**：媒体值可用来校验已有数据是否自洽，
   或与另一家独立媒体一致时作为补充；**仅凭一条媒体信息不得给产品定参数**。
   媒体之间互相转载不算多源印证，且要标注媒体名与链接。

---

## 7. 冲突与恢复

| 情况 | 处理 |
| --- | --- |
| 发现某产品被冻结但仍被改了 | `npm run audit:check` 定位 → 用 `npm run audit:diff -- <id>` 看字段 → 请用户裁决是保留还是回滚 |
| 两个 Agent 同时改同一个产品 | 后者先 `git pull --rebase`；冲突时以**有来源记录的一方**为准，另一方在 `change_log` 里留说明 |
| 快照范围拍错了（漏了/多了） | 直接 `release` 旧的、重新 `snapshot` 新的；不要手改快照文件 |
| 需要紧急改冻结数据 | 用户口头确认后 `release` → 改 → 提交信息写明；快照里会留下 `violationsAtRelease` |

---

## 8. 审核报告模板

报告放 `docs/audit/`，文件名 `审核_<范围>_<YYYY-MM-DD>.md`：

```markdown
# 审核报告：<范围>

- **快照 id**：<data/_locks 里的 id>
- **范围**：<品类 / 产品数>
- **审核日期**：YYYY-MM-DD
- **审核方**：agent-?

## 结论摘要

| 结论 | 数量 |
| --- | ---: |
| 已证实 | |
| 存疑（需再核） | |
| 数据错误（需订正） | |
| 来源不足，应降级为「待核验」 | |

## 逐条明细

| 品类/产品 | 字段 | 现值 | 审核结论 | 依据链接 | 建议动作 |
| --- | --- | --- | --- | --- | --- |

## 待补项

- [ ] <需要谁去补什么>

## 给整改方的提示

- 整改后请同步更新 `verify_status` / `verify_date` / `verify_source` / `change_log`
- 请在提交信息里引用本报告
```

---

## 9. 客户端无关约定

- **技能放 `skills/<name>/SKILL.md`**（标准 skill 格式：YAML frontmatter + 正文）。
- `.trae/skills/`、`.claude/skills/` 等各客户端目录**只放指针文件**，内容指向 `skills/`，
  避免同一份规范多份副本漂移。
- 各客户端的本地配置与产物（`.trae-html-share-packages/`、`.claude/settings.local.json`、
  `.codebuddy/` 等）已在 `.gitignore` 中排除，**不要提交**。
- 工作区整理原则：**根目录只放入口文档**（`README.md` / `AGENTS.md` / `HANDOFF.md`），
  审核报告归档 `docs/audit/`，溯源材料进 `data/_sources/`，抓取缓存进 `data/_cache/`（不入库）。
