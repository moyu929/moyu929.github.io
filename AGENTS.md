# 多 Agent 协作规范

> 本文件对本仓库的**所有协作者**生效：不论你是 CodeBuddy、Trae、Claude Code 还是别的客户端，也不论你是人类。
> 技能定义在 [`skills/`](skills/)（客户端无关）；各客户端的私有目录（`.trae/`、`.claude/`）里只放指向 `skills/` 的指针。
> 数据采集/核验的详细规范在 [`skills/appliance-data-curation/SKILL.md`](skills/appliance-data-curation/SKILL.md)，**动手前先读它**。
>
> ⚠️ 本仓库的口径**多次演进过**（多品牌收录、分区流转、状态枚举都变过）。`docs/audit/` 下的历史报告
> 不删不改，但结论可能已过时 —— **以本文档与 `SKILL.md` 为准**。哪些旧口径已被取代，见
> [`HANDOFF.md`](HANDOFF.md) 第 6 节「口径变更历史」。

---

## 1. 一句话规则

**先认清自己在哪个区：采集方只写 `data/_draft/`，审核修正方只写 `data/_review/`，上线数据只能经 `flow:publish` 进入 `products.json`；动手前先跑 `npm run flow:status`。改动一律走分支 + PR，不直推 `main`（§3.6）。**

---

## 2. 角色与分工

| 角色 | 职责 | 常态可改范围 |
| --- | --- | --- |
| **采集 Agent（A）** | 在草稿区收录新产品、起草订正稿；完成后 `flow:submit` 提交待审 | `data/_draft/`、`public/images/`、`schema.json`、`categories.json`、`data/_sources/`、`scripts/`、`src/` |
| **审核修正 Agent（B）** | **产品级生命周期操作者**（角色唯一；**多 B 并行时按品类分工，见 §3.6**）：认领待入库数据、召回复审已入库数据，在修正区核验修正后 `flow:publish` 入库 | `data/_review/`、`data/<品类>/products.json`（经 flow:publish，或经 library-io 的批量工具）、`docs/audit/` |
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
| **已入库区** | `data/<品类>/products.json` | 线上站点的唯一数据源（当前可信的数据） | 只有 B，且只能经 `flow:publish` 或**同一写入规范的批量工具**（见下） |

**库写入是两层规则**（P1-1 落地后的现实，2026-10-03 起）：

1. **写入动作一律经 `scripts/lib/library-io.mjs` / `library_io.py`** —— 这两个实现提供
   规范序列化（一行一款、整值浮点归一、非 ASCII 不转义）+ 写前指纹校验（拒绝覆盖别人刚改过的库）
   + 文件锁退避重试 + 批量留痕（`actor` → journal 的 `batch-write` 条目）。
   任何人不得自己 `writeFileSync` / `write_text` 写 `products.json`。
2. **产品级生命周期操作走 `flow:*`**（提交/认领/召回/入库/退回/剔除）；
   **批量工具**（`mi:apply`、`img:webp`、`miot:match --apply`、`classify-facets`、`import-brands`）
   经同一规范**直写**库——这是合法且被守卫保护的路径，不是绕过。
   批量工具必须传 `actor`（用 `scriptActor()` / `script_actor()`），否则 `flow:log` 会出现盲区。

⚠️ 别把「B 是唯一操作者」理解成「只有 `flow:publish` 能写库」：批量工具同样是写库者，只是**必须走同一规范**。

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

### 3.6 分支协作协议（2026-10-03 起）

分区仍是数据形态的载体，但**传输与合并交给 git 原生机制**：各方在自己的 worktree / 分支上干活、推分支、开 PR，**合并 PR 即上线**（由编排方代理合并，规则见下）。

| 角色 | 工作位置 | 动作 | 硬边界 |
| --- | --- | --- | --- |
| **采集 A** | 编排方注入的 worktree（如 `../wt-collect-01`），分支 `collect/<任务号>-<品类>` | 分区流程 → `flow:submit` → 推分支 → 开 PR | 只开 PR；不碰 `main`；不进他人的 worktree |
| **修正 B** | 单 B：主目录切分支；**多 B：各自 worktree（`../wt-review-<NN>`，见下「多工作者并行」）** | `gh pr checkout <PR>` → `flow:claim` → 核验修正 → `flow:publish` → 推回 → 通知编排方合并 | 不得直推 `main` |
| **编排方** | 本地 `gh pr merge` | **代理合并**常规批次（CI 全绿 + 描述完整）；升级项先呈报用户；合并后在 issue 报告 | 只合并「绿且无争议」的 PR |
| **用户** | GitHub 网页 / 对话 | 裁决冲突与口径、决定（新增）剔除、随时叫停代理 | 最终否决权 |

- **PR 合并 = 上线时刻**：合并前站点展示上一个已发布版本；`recall` 不再立即下架。
- **合并规则（2026-10-04 起，用户授权）**：**编排方代理合并**常规批次——前置 = CI 全绿 + PR 描述完整（批次/来源/自查）；
  **以下必须先呈报用户拍板**：新增剔除（`flow:drop`）/ 收录范围或口径变更 / 冲突裁决 / 任何有疑问的 PR。
  合并用 `--merge`（保留批次历史）；合并后编排方在 issue / 对话报告。**用户可随时叫停或收回代理（一句话）。**
- **一个 PR = 一个批次**（一波采集 / 一批召回修正），不是一个产品一个 PR。PR 描述用 `.github/pull_request_template.md`。
- 分支命名：`collect/<任务号>-<品类>` / `review/<批次号>` / `feat/<主题>` / `fix/<主题>`。
- 会话开头先 `gh pr list` / `gh issue list` 认领任务，再 `npm run flow:status` 看分区现状、`npm run flow:workers` 看谁占了哪个工作台（防互相踩）。
- **gh 开工自检**：报 command not found → 进程启动早于安装，**重启客户端**即可（临时可用全路径
  `"C:\Program Files\GitHub CLI\gh.exe"`）；报未登录 → 凭据在 Windows 凭据管理器、应自动可用。
  都排不掉时在 issue 报告；凭据失效（401）时请用户跑一次 `gh auth login`（浏览器一次性授权，之后自动管理）。
- **编排方义务**：给子 Agent 注入其 worktree 的绝对路径，**提示词里不出现主仓路径**——这是唯一被实测确认发生过的越界写入向量。

**多工作者并行（A×N / B×N，2026-10-03 起）**

每个工作者一个**独立 worktree**（各自的文件系统副本）：跨工作者的冲突推迟到 PR 合并时，
由 `merge=union`（journal）与**一行一款**（库文件）自动解决——因此**任务分配规则是唯一的额外约束**：

| 事项 | 规则 |
| --- | --- |
| **品类是分配单元** | 同一品类同一时刻**至多一个采集方 + 一个修正方**；不同品类天然互不冲突（产品文件与 `products.json` 都按品类分隔）。 |
| **共享文件串行** | `data/categories.json`、`data/<品类>/schema.json`、`data/_sources/**` 的修改**不与数据批次混在同一次 PR**；同一时刻只由一个工作者改（由编排方串行安排）。 |
| **id 约定** | `<品类前缀>_<品牌>_<型号>`；`submit` 前先查库内与待入库区是否已有同产品，避免「同物不同 id」。 |
| **防双领** | `claim` 在修正区原子创建 `<id>.json.claiming` 占位——同一文件任一时刻只有一个认领者；重复认领会显示原认领人。 |
| **禁止共用工作目录** | 每个工作者只在**自己的** worktree 里跑命令。同一目录被两个会话共用会互相踩分支（2026-10-03 实际发生：一个会话切分支，另一个会话的未提交改动被带着走）。 |

- worktree 命名：采集 `wt-collect-<NN>`、修正 `wt-review-<NN>`、编排 `wt-orch-<NN>`；各自从最新 `main` 出发。
- **开工先查**：`npm run flow:workers`——列出每个工作台的分支、最近操作（journal 关联）、未提交改动涉及的目录；
  对「有改动但关联不到 actor」的工作台会给出提示（共用目录或未留痕会话的兜底信号）。
- **B 的目录形态**：客户端支持「按命令指定工作目录」的，直接在 `wt-review-<NN>` 里干活；不支持的，
  按批次**开子会话、由编排方注入 worktree 路径**（与 A 同一模式）。

**新建 worktree 的引导清单**（每新建一个目录跑一遍）：

```bash
git worktree add ../wt-collect-01 -b collect/01-air-purifier   # 采集方
git worktree add ../wt-review-01  -b review/<批次号>            # 修正方（多 B 并行时）
cd ../wt-collect-01
npm run flow:status     # 自检。不需要 npm install（flow/validate/lint 只用 node 内置模块）
npm run hooks:install   # 启用提交闸门（core.hooksPath 是本机配置，每个 worktree 各需一次）
```

- `AGENTS.md`、`HANDOFF.md`、`skills/**`、`docs/**`、钩子脚本**都随 worktree 到位**，无需手工播种。
- `data/_cache/**` 与 `node_modules/` **不随 worktree 走**：数据类工作都不需要；只有爬取类脚本用 `_cache`，用到时从主仓复制（2.7MB）。
- ⚠️ **worktree 目录必须位于该客户端允许写入的范围内**。实测：目录在仓库之外时会被客户端沙箱拦（写入与删除均失败），需在「设置 → 权限与批准 → 自定义配置」把父目录加入允许列表。

**会话纪律（重要）**：客户端项目记忆按**项目路径**派生——在 worktree 这个新路径里开会话，等于另一个项目，读不到主目录的会话历史与记忆。因此**凡需跨会话保留的决定，必须写回仓库文件**（`AGENTS.md` / `HANDOFF.md` / `docs/` / issue），不能只留在对话或客户端记忆里。

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
- **批量工具写库的提交**：提交信息**建议**同样带 `flow` 标记（如 `data: flow:batch mi:apply heater 12 款（来源：小米商城规格页）`）。
  注意提交闸门**只拦 `_intake` / `_review` 的分区文件**，库文件本身不在拦截范围 —— 这是有意的，
  否则每次订正数据都会被拦。批量工具会在 journal 里留一条 `batch-write`（含脚本名与条数），
  写清 `flow` 标记能让「提交信息 ↔ 流转日志」一一对上。
- **不要用 `git add -A` / `git add .`**：显式列出路径。共享工作树里 `-A` 会扫走别人未提交的分区文件
  （2026-10-03 实测发生过：两份文档被扫进他人提交，提交信息与内容不符）。
- 推送前跑 **`npm run check`**（= `validate` + `lint` + `selftest` + `audit:check`）；有 error 不得推送。
  ⚠️ **`check` 与 CI 的检查范围不同，这不是遗漏而是取舍**：`check` 刻意只跑**不依赖 `node_modules`** 的项，
  以便在未 `npm install` 的 worktree 里直接可跑（见 §3.6 引导清单）；`typecheck` 与 `build`（需依赖）
  **只在 CI 把关**，`audit:check`（需快照锁，无快照时静默通过）只在本地。
  → 所以**改动 `src/**` 或类型定义时，类型错误只会在 CI 暴露**；本地想提前发现就先 `npm install` 再跑 `npm run typecheck`。
- **改动一律走分支 + PR，不直推 `main`**（§3.6）：合并 PR 才触发部署；不 force push；不修改 git 配置。
  ⚠️ **`main` 已启用分支保护（2026-10-03）**：直推会被服务器拒绝，且管理员也不能绕过——所以这不是建议，是硬约束。
  已实测确证：`! [remote rejected] HEAD -> main` + `GH006: Changes must be made through a pull request`。
  （边界：`gh api .../branches/main/protection` 读不到配置——集成令牌无管理权限；验证锁是否在，只能靠试推。）
  若某次推送被拒并提示 protected branch，说明你漏走了 PR；**不要**去改设置绕过，按 §3.6 开分支 + PR。
  一个已知边界：A/B 与本机共用同一套密钥，所以「只有用户能合并 PR」是**协议约束**而非技术强制。
- 改动了审核标注字段的提交，在信息里点出「已更新核查状态/来源」。

---

## 6. 目录所有权

| 路径 | 谁能改 | 说明 |
| --- | --- | --- |
| `data/_draft/**` | **只有 A** | 草稿区：收录中的半成品。**不入库**（见 3.1），备份靠「能过校验就 submit」 |
| `data/_intake/**` | A 放入、B 取走（仅经 flow 命令） | 待入库区：交接队列，禁止共编 |
| `data/_review/**` | **只有 B** | 修正区：核验修正中的数据 |
| `data/<品类>/products.json` | **只有 B 经 `flow:publish`**，或经 library-io 的批量工具 | 已入库区：线上唯一数据源（写入一律经 `library-io`，见 3.1） |
| `data/<品类>/schema.json` | A | 共享基础设施；改前看 3.4 的注意项 |
| `data/categories.json` | A | 品类清单与首页顺序 |
| `data/_flow/journal.jsonl` | flow 命令与 library-io 追加，任何人不手改 | 流转日志（append-only，共享事实）。两类条目：`flow:*` 的流转、批量工具的 `batch-write` |
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
