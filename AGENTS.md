# 多 Agent 协作规范

> 本文件对本仓库的**所有协作者**生效：不论你是 CodeBuddy、Trae、Claude Code 还是别的客户端，也不论你是人类。
> 技能定义在 [`skills/`](skills/)（客户端无关）；各客户端的私有目录（`.trae/`、`.claude/`）里只放指向 `skills/` 的指针。
> 数据采集/核验的详细规范在 [`skills/appliance-data-curation/SKILL.md`](skills/appliance-data-curation/SKILL.md)，**动手前先读它**。
>
> ⚠️ 本仓库的口径**多次演进过**（多品牌收录、分区流转、状态枚举都变过）。`docs/audit/` 下的历史报告
> 不删不改，但结论可能已过时 —— **以本文档与 `SKILL.md` 为准**。哪些旧口径已被取代，见
> [`HANDOFF.md`](HANDOFF.md) 第 8 节「口径变更历史」。

---

## 1. 一句话规则

**先认清自己在哪个区：采集方只写 `data/_draft/`，审核修正方只写 `data/_review/`，上线数据只能经 `flow:publish` 进入 `products.json`；动手前先跑 `npm run flow:status`。**

---

## 2. 角色与分工

| 角色 | 职责 | 常态可改范围 |
| --- | --- | --- |
| **采集 Agent（A）** | 在草稿区收录新产品、起草订正稿；完成后 `flow:submit` 提交待审 | `data/_draft/`、`public/images/`、`schema.json`、`categories.json`、`data/_sources/`、`scripts/`、`src/` |
| **审核修正 Agent（B）** | **唯一写库者**：认领待入库数据、召回复审已入库数据，在修正区核验修正后 `flow:publish` 入库 | `data/_review/`、`data/<品类>/products.json`（仅经 flow:publish）、`docs/audit/` |
| **用户** | 下达指令；指派角色；裁决退回 / 剔除争议；下达结构冻结 | — |

- 同一个 Agent 可以轮换承担 A / B 角色；**具体由用户指派**（一般看哪方空闲）。
- A 与 B 之间不直接协商，**通过被提交到仓库的文件同步状态**：分区文件本身就是状态，流转日志（`data/_flow/journal.jsonl`）记录谁在什么时候把什么搬到了哪里，审核报告归档 `docs/audit/`。

---

## 3. 分区流转协议（核心）

并行工作最大的风险从来是同一个：**一个 Agent 正在改的数据，被另一个 Agent 同时改掉，或基于过期版本下了结论**。旧版用「快照锁 + 状态标签」防它，实践中暴露两个洞——锁范围的变更没被对方及时捕获，有人越界改了冻结内的数据；审核方把对方收录到一半的数据划进了冻结范围，打断了采集。

现在的解法是**用物理目录隔离数据的状态**：一个产品任一时刻只待在一个分区里，**文件的位置就是它的状态**。各方只写自己的分区，工作区内永远不可能出现别的状态的数据，所以谁都不需要盯状态标签、不需要轮询对方的进展。

### 3.1 四个分区

| 分区 | 位置 | 里面是什么 | 谁在写 |
| --- | --- | --- | --- |
| **草稿区** | `data/_draft/<品类>/<id>.json` | A 收录中的数据（半成品，随意增删改） | 只有 A |
| **待入库区** | `data/_intake/<品类>/<id>.json` | A 已收录完成、等待 B 认领的交接队列 | A 经 `flow:submit` 放入；B 经 `flow:claim` 取走 |
| **修正区** | `data/_review/<品类>/<id>.json` | B 正在核验/修正的数据（新认领的 + 召回复审的） | 只有 B |
| **已入库区** | `data/<品类>/products.json` | 线上站点的唯一数据源（当前可信的数据） | 只有 B，且只能经 `flow:publish` 写入 |

分区文件与流转日志**大部分入库**——它们是各 Agent 之间的共享状态，不入库对方就看不见。
例外是**草稿区**（`data/_draft/`）：它是采集方的私有工作台，按定义无人需要看见，自 2026-10-03 起
**不进 git**（`.gitignore` 排除其内容，只留 `.gitkeep` 占位）。草稿的备份靠纪律换：
**能过校验就 `flow:submit`**（进了待入库区即被 git 跟踪），需要继续改再 `flow:withdraw` 撤回。
前端与构建只读已入库区（`src/data.ts` 的 glob 与 `validate` 都不会碰 `_` 开头的分区目录）。

### 3.2 状态机与命令

```
            flow:submit              flow:claim                flow:publish
  草稿区 ───────────────▶ 待入库区 ────────────────▶ 修正区 ────────────────▶ 已入库区
  _draft                 _intake                  _review                  products.json
  A 的工作台              A→B 的交接队列            B 的工作台                线上站点唯一数据源
 （半成品，只有 A 写）     （A 放入，B 取走）         （核验修正中，只有 B 写）   （只有 B 经 publish 写）

  回流：flow:withdraw（A 撤回）/ flow:return（B 退回）：待入库区 → 草稿区
        flow:recall（召回复审）：已入库区 → 修正区
        flow:drop（剔除收录，需用户确认）：修正区 → 删除
```

| 命令 | 谁 | 流转 | 要点 |
| --- | --- | --- | --- |
| `npm run flow:submit -- <品类/id>...` | A | 草稿区 → 待入库区 | **收录完成的唯一出口**。先过校验（schema 合法 + 6 个审核标注字段齐 + `verify_status` 取值规范），不过不收 |
| `npm run flow:withdraw -- <品类/id>...` | A | 待入库区 → 草稿区 | 提交后想继续改就撤回；已被认领则失败 |
| `npm run flow:claim -- <品类/id>...` | B | 待入库区 → 修正区 | 认领开始核验；提交后 schema 又改过导致校验不过时，可用 `--force` 先领回自己区再修 |
| `npm run flow:recall -- <品类/id>... --reason "…"` | B | 已入库区 → 修正区 | 召回复审。**产品暂时下架**，重新 publish 前站点不展示它 |
| `npm run flow:publish -- <品类/id>...` | B | 修正区 → 已入库区 | 入库前再过一遍校验；入完对整个品类复检，不过关**自动回滚**（库还原、产品退回修正区）。库内有同 id 时整条替换且保持原位置 |
| `npm run flow:return -- <品类/id> --reason "…"` | B | 待入库区 → 草稿区 | 不符收录标准（白牌/海外版/证据不足）退回给 A |
| `npm run flow:drop -- <品类/id> --reason "…"` | B | 修正区 → 删除 | 召回后判定根本不该收录。属于收录范围变更，**须用户确认**；日志记指纹，git 历史可找回 |
| `npm run flow:status [--category X] [--zone draft\|intake\|review]` | 任意 | — | 看四个区现状 + 最近流转；**动手前先跑这个** |
| `npm run flow:log [-n N]` | 任意 | — | 流转日志（谁、何时、把什么从哪搬到哪、为什么） |

所有流转命令都支持 `--by <名字>` 标注操作者（日志溯源用），**请务必带上**。

### 3.3 三条铁律

1. **已入库区不可直接手改。** B 修旧数据走 `recall → 修正 → publish`；A 发现库内数据有问题时，把该产品从库复制到草稿区、改好后 `flow:submit`——工具发现库内有同 id 会自动按「订正稿」处理（claim/publish 时整条替换）。任何人都不存在「顺手改一下线上数据」这个动作。
2. **半成品不进交接队列。** 草稿区里怎么乱都行，但只有通过 `flow:submit` 校验的数据才会出现在待入库区——B 认领时拿到的**必然是 A 宣称已完成的成品**。这就是草稿区与待入库区分成两个区的原因：旧协议里「审核方把收录到一半的数据划进冻结范围」这类事故在结构上不可能再发生。
3. **流转即提交。** flow 命令**不做任何 git 操作**，跑完当场提交（前缀 `data`，写明动作、对象与原因），`data/_flow/journal.jsonl` 一并入库。它是 append-only 的共享事实：出了分歧以日志 + 分区现状为准。

### 3.4 设计取舍

- **为什么是四个区，不是三个。** 待入库区是 A/B 的**交接队列**，双方都会碰它；若 A 直接在这里收录，B 认领时仍可能拿到半成品。草稿区把「正在录」和「录完了」物理分开后，每个区都有了唯一写入方：`_draft` 只 A 写、`_review` 只 B 写、库只 B 经 publish 写，`_intake` 只有「A 放入 / B 取走」两个原子动作，没有共编。
- **文件位置即状态。** 不需要状态标签、不需要心跳/轮询对方的锁——看一眼 `flow:status`（甚至直接看目录）就知道全站数据分布。旧协议「锁范围变更没被及时捕获」的问题不复存在，因为不再有需要捕获的隐形状态。
- **订正稿机制。** 同一个 id 可以同时存在于库内和待入库区/修正区（A 的订正稿先到，B 还没入库）。工具在 submit/claim/status 时都会标注「订正稿」，publish 时整条替换并保持数组位置；修正区已有某产品文件时，claim 会拒绝，先 publish 或 drop 那份。
- **站点可见性。** 访客只看到已入库区。召回会让产品**暂时下架**，所以大批量审核要按「召回一批 → 修正 → 入库一批」滚动推进，不要把整个品类长期挂在修正区。
- **图片不走分区。** `public/images/<品类>/<id>.webp` 与产品在哪个分区无关，A 录入时直接放图；分区流转只搬 JSON。
- **schema 是共享基础设施，不分区。** A 新建品类时直接在 `data/<品类>/` 建 `schema.json`（收录期间可以只有 schema 没有 `products.json`，`validate` 对这种未登记目录降为提示）；首批产品 `flow:submit` 的同一提交里把品类登记进 `categories.json`；`flow:publish` 检测到未登记会拒绝入库。改已有 schema 前先 `flow:status --category <品类>` 看有没有在修产品；publish 永远按**当前** schema 校验，schema 改坏了天然兜底。

### 3.5 紧急修改

线上数据有错、等不了完整流程时：B 一次做完 `recall → 改 → publish`（几个命令几十秒），提交信息写明「紧急订正」。**不存在**绕过分区直接改库的通道——紧急的是时效，不是流程。

---

## 4. 快照锁（降级为结构冻结工具）

分区流转落地后，**产品级日常互斥由分区天然保证，快照锁不再用于日常审核**。它保留给两类场景：

1. **全库结构变更**（schema 大改、字段批量迁移、脚本全量重写数据）或**发版验收**前，把全站拍成快照冻结，防止变更期间被并发干扰；
2. 查询历史：`npm run audit:list` / `audit:diff` 看旧快照与遗留结论。

命令不变：`audit:snapshot` / `audit:check` / `audit:status` / `audit:diff` / `audit:release` / `audit:list`（详见 `data/_locks/README.md`）。两点注意：

- 结构冻结生效期间**暂停所有 flow 流转**——召回/入库会搬动库内产品，`audit:check` 会把这类正常动作报成越界。
- `npm run check` 仍会跑 `audit:check`；没有生效快照时它安静通过。

---

## 5. 提交与推送纪律

- 一次提交只做一件事；提交信息前缀：`feat` / `fix` / `data` / `docs` / `chore`。
- **流转动作随做随提交**：每个 flow 命令跑完就 commit，把分区文件与 `data/_flow/journal.jsonl` 一起提交；建议信息格式（**注意带 `flow` 标记**，提交闸门据此放行，见下）：
  - `data: flow:submit heater/ht_x（来源：…）`（submit）
  - `data: flow:publish heater/ht_x，订正功率参数（依据：官方规格页）`（publish）
  - `data: flow:recall heater/ht_x 复审（原因：…）`（recall）
  - `data: flow:claim <提交人> 的 N 款（提交人 …）`（claim）
- **提交闸门（本机需启用一次）**：`npm run hooks:install` 启用 `scripts/hooks/commit-msg` ——
  提交里含 `data/_intake/**` 或 `data/_review/**` 的文件时，提交信息**必须含 `flow` 字样**，否则拒绝提交。
  它挡的是「顺手 `git add -A` 把别人的半成品捎带进自己的提交」这类事故。
  ⚠️ 边界（不要指望它万能）：**合并提交不检查**（分支合并由 PR + CI 把关）；`git commit --no-verify` 可绕过；
  它是**本地防线**，真正的门是 PR 上的 CI。每个 clone / worktree 各需启用一次（`core.hooksPath` 是本机配置）。
- **改数据的提交必须写明来源与核验方式**，例如：
  `data: 补录洗地机 5 Pro 参数（来源：太平洋规格表 + 小米商城在售价）`。
- **不要用 `git add -A` / `git add .`**：显式列出路径。共享工作树里 `-A` 会扫走别人未提交的分区文件
  （2026-10-03 实测发生过：两份文档被扫进他人提交，提交信息与内容不符）。
- 推送前跑 **`npm run check`**（= `validate` + `audit:check`）；有 error 不得推送。
- 只推 `main` 触发部署；**不 force push `main`**；**不修改 git 配置**。
- 改动了审核标注字段的提交，在信息里点出「已更新核查状态/来源」。

---

## 6. 目录所有权

| 路径 | 谁能改 | 说明 |
| --- | --- | --- |
| `data/_draft/**` | **只有 A** | 草稿区：收录中的半成品。**不入库**（见 3.1），备份靠「能过校验就 submit」 |
| `data/_intake/**` | A 放入、B 取走（仅经 flow 命令） | 待入库区：交接队列，禁止共编 |
| `data/_review/**` | **只有 B** | 修正区：核验修正中的数据 |
| `data/<品类>/products.json` | **只有 B**，仅经 `flow:publish` | 已入库区：线上唯一数据源 |
| `data/<品类>/schema.json` | A | 共享基础设施；改前看 3.4 的注意项 |
| `data/categories.json` | A | 品类清单与首页顺序 |
| `data/_flow/journal.jsonl` | flow 命令追加，任何人不手改 | 流转日志（append-only，共享事实） |
| `data/_sources/**` | A 写，B 读 | 溯源、补丁、图片与抓取清单 |
| `data/_cache/**` | 任何人生成 | 抓取缓存，**已 gitignore**，不入库 |
| `data/_locks/**` | **只有 B** | 审核快照锁（结构冻结用）；A 只读 |
| `docs/audit/**` | **只有 B** | 审核报告归档；A 只读 |
| `public/images/**` | A | 产品图，文件名 = 产品 id（不随分区流转） |
| `scripts/**` | 谁都行，改了要说明 | 采集/校验/流转工具 |
| `src/**` | A | 站点代码 |
| `skills/**`、`AGENTS.md`、`README.md`、`HANDOFF.md` | 谁都行 | 规范与文档 |

---

## 7. 数据红线（摘要）

完整版见 [`skills/appliance-data-curation/SKILL.md`](skills/appliance-data-curation/SKILL.md)。

1. 收录**中国大陆的多品牌**型号：小米/米家自有品牌与主流家电品牌同等收录、同等展示，分组维度是品牌，不是「小米 vs 竞品」；海外版、港台版、白牌不收。每款产品必须有 `brand` 字段。
2. 数值**必须可溯源**；查不到就写 `查不到`，**禁止估算、换算、补零**。
3. 只采公开信息：不抓登录后内容、不绕过访问控制、不收录个人信息或商业秘密。
4. 每款产品必须带 6 个审核标注字段（`verify_status` / `verify_date` / `verify_source` / `verify_url` / `change_log` / `updated_at`），且状态判定要能从 `data/_sources/` 里查到依据。`flow:submit` 与 `flow:publish` 会强制校验这 6 个字段。
5. 第三方来源有系统性错标（如把 `2800W` 写成 `28W`、把 `L` 写成 `ml`），对可疑值一律留空，别照抄。
6. **媒体（含 AI 聚合内容）只能印证，不能单独定值**：媒体值可用来校验已有数据是否自洽，或与另一家独立媒体一致时作为补充；**仅凭一条媒体信息不得给产品定参数**。媒体之间互相转载不算多源印证，且要标注媒体名与链接。

---

## 8. 冲突与恢复

| 情况 | 处理 |
| --- | --- |
| `claim` 时文件不见了 | 被 A `withdraw` 撤回或另一名 B 先领走：`git pull` 后看 `flow:log`，再决定 |
| A 提交后发现还要改 | `flow:withdraw` 撤回继续改；已被认领则等 B 修正结论（B 会 return 或 publish） |
| A 与 B 都想改同一个已入库产品 | A 的订正稿走 `submit` 排队，B 直接 `recall` 修；两边都在修正区时 B 统一处理，结论记 `change_log` |
| `publish` 后发现数据有问题 | 再次 `recall → 修正 → publish`；误操作可用 git 历史与日志指纹回溯 |
| 误 `drop` / 误 `return` | 日志记了内容指纹，git 历史可找回；`drop` 本应经用户确认，发生误剔先报告用户 |
| 两个 Agent 同时跑 flow 命令 | 命令是短原子操作，失败方会得到明确报错；`git pull --rebase` 后重试即可 |
| 快照锁生效期间有人流转 | 结构冻结期间本应暂停流转；若已发生，用 `audit:diff` 看影响面，请用户裁决保留或回滚 |
| 快照范围拍错了 | 直接 `release` 旧的、重新 `snapshot` 新的；不要手改快照文件 |

---

## 9. 审核报告模板

报告放 `docs/audit/`，文件名 `审核_<范围>_<YYYY-MM-DD>.md`：

```markdown
# 审核报告：<范围>

- **流转记录**：data/_flow/journal.jsonl（可用 flow:log 摘录本批 claim/recall/publish）
- **快照 id**：<仅当使用了结构冻结快照；一般审核留空>
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
| 退回采集方（flow:return） | |
| 剔除收录（flow:drop，用户已确认） | |

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

## 10. 客户端无关约定

- **技能放 `skills/<name>/SKILL.md`**（标准 skill 格式：YAML frontmatter + 正文）。
- `.trae/skills/`、`.claude/skills/` 等各客户端目录**只放指针文件**，内容指向 `skills/`，避免同一份规范多份副本漂移。
- 各客户端的本地配置与产物（`.trae-html-share-packages/`、`.claude/settings.local.json`、`.codebuddy/` 等）已在 `.gitignore` 中排除，**不要提交**。
- 工作区整理原则：**根目录只放入口文档**（`README.md` / `AGENTS.md` / `HANDOFF.md`），审核报告归档 `docs/audit/`，溯源材料进 `data/_sources/`，抓取缓存进 `data/_cache/`（不入库）。
- 流转工具支持 `FLOW_DATA_DIR=<目录>` 环境变量把流转指向临时数据副本，用于测试——**测试时务必用它**，不要拿真实分区练手。
