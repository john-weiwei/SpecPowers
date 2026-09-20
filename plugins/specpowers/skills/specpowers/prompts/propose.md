# propose.md — 提案契约（一站式生成 proposal + spec + tasks）

## 触发

当用户调用 `/specpowers-propose "<需求>"` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 来自 state.json 的 feature 字段（explore/fast 阶段确定并锁定，同一流程不变）。

## 定位（v2.0.0 调整）

本阶段合并原 specify（场景定义）+ plan（实现计划）：从 explore 设计文档（或跳过探索的清晰需求）出发，**一次性生成 OpenSpec change 三件套**并全部落盘到 `openspec/changes/<feature>/`（存储路径与 v1.x 完全一致）：

| 产物 | 路径 | 来源 |
|------|------|------|
| proposal.md | `openspec/changes/<feature>/proposal.md` | 从 explore 设计文档提炼（Why/What Changes/Capabilities/**数据流契约**/Impact） |
| spec.md | `openspec/changes/<feature>/specs/<capability>/spec.md` | OpenSpec delta 格式（ADDED Requirements + Scenario） |
| tasks.md | `openspec/changes/<feature>/tasks.md` | superpowers `writing-plans` 瘦身（单一任务清单） |

三件套内部按「proposal → spec → tasks」顺序生成（后一步消费前一步产物），单次命令内完成，用户无需分别触发。

**断点续作**（含 v1.x `plan` 态惰性迁移场景）：若进入本阶段时 spec.md 已存在而 tasks.md 缺失（旧流程中断后升级），按产物存在性增量推进——已有产物校验后复用，只补缺失部分，不盲目重写。

## 重入识别（人工模式迭代轮入口）

执行前置校验**之前**，先读 `.specpowers/state.json` 判断本次调用是否为迭代重入：

- **触发条件**：`stage` = `apply` 且 `feature` 非空（活跃未归档——归档后 stage 已回 `ready`，不在此列）。这表明用户要在**同一个未归档需求**上做调整，需求身份由归档状态唯一决定，调整必须落在当前 change 目录的当前 spec 文件内。
- **交互确认**（必须，禁止静默切换轮次）：

  ```
  检测到未归档需求 <feature>（stage=<stage>，当前 Round <iteration_count>）。本次重入意图是？
  1. 开启 Round <iteration_count+1> 迭代轮 —— 调整/优化需求，调整记录进当前 spec 文件
  2. 取消 —— 继续现有流程（/specpowers-apply 或 /specpowers-archive）
  ```

  - `stage=apply` 且 `mode=fast` 时追加选项：`3. fast→full 流程回退（原 fallback 语义：消耗整个生命周期唯一 1 次回退额度，放弃 fast 产物重新完整生成三件套）`
  - 用户给出调整描述（命令参数）时在选项 1 中原样带入，作为本轮修订依据
- **确认开启迭代轮**：调 `facade iterate [--instruction "<调整描述>"] --root .`（确定性层完成：stage → `propose`、feature 锁定不变、`iteration_count += 1`、不占 fallback 额度）。成功后**不要再调 `facade propose`**（状态已就位），直接按下方「迭代轮」小节增量修订三件套
- **选择取消**：不改任何状态，向用户说明当前可选步骤后结束
- **未触发**（stage 为 `ready`/`explore`/`propose`）：走正常流程——stage=`propose` 的重跑属迭代轮**续作**（`iteration_count ≥ 1` 时按迭代轮小节执行，轮次不变），其余按前置校验常规进入

## 前置校验

```bash
python -m specpowers_cli.bridge.facade propose "<需求>" --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`explore` / `ready`（跳过探索）/ `apply`（fallback 回退）/ `propose`（迭代轮续作，自环幂等）
- **从 explore 进入时**：`state.json` 的 `design_doc` 字段必须非空且文件存在（explore 阶段经 `facade record-design-doc` 登记的探索凭据，倒逼 explore 必须完成探索）
- `.specpowers/constitution.md` 必须存在

## 执行步骤

### 第一步：读取上下文

1. 读取 `.specpowers/constitution.md` — 了解项目原则
2. 如果从 `explore` 进入 — **必然读取 state.json `design_doc` 登记的设计文档**，并**重点读取其中的「数据流」章节与决策摘要**（字段来源/值域是 proposal 数据流契约与 Scenario WHEN/THEN 的输入依据）、capability frontmatter（如有）
3. 如果从 `ready` 进入（跳过探索）— 仅读取 constitution.md，proposal 的数据流契约按与用户交互确认的结论撰写（纯本地特性声明「本特性无跨链路字段」）

### 交互决策原则（AskUserQuestion 使用指引）

本阶段**默认按设计文档/需求自主生成三件套并给出推荐**，不强制打断用户。但当出现以下情况时，**必须主动用 AskUserQuestion 让用户决策**：

| 触发场景 | 处理方式 |
|---------|---------|
| 跳过探索路径下任务拆分有歧义（同一需求可多种拆法） | 列出拆分方案 + 各自粒度/风险，让用户选 |
| 执行方式选择不确定（特性特征不明显） | 列出 conductor/worktree/subagent/TDD 各自适用性 + 推荐 |
| 任务间依赖关系不清晰（循环依赖/顺序难定） | 列出可能的依赖排列，让用户确认 |
| 涉及大粒度决策（如是否拆分独立模块、是否引入新依赖） | 列出选项 + 影响，让用户拍板 |
| **跨链路入参数据来源不明**（回调/接口/MQ 报文中的关键字段无法从设计文档数据流章节追溯到上游产生方与传递链路） | 列出存疑入参 + 字段名假设 + 可能来源环节，让用户确认真实字段名与产生方 |

**AskUserQuestion 格式要求**（与 explore 一致）：
- 每个选项给清晰 label（1-5 词）+ description（影响/取舍）
- 推荐项放第一，label 末尾加「（推荐）」
- 仅在真正需要用户判断时问

### 第二步：解析 capability

从设计文档（或已有 proposal.md）顶部 YAML frontmatter 解析 capability：
- 有 `capability: <名称>` → 共享已有能力（迭代场景），delta 写到 `specs/<capability>/spec.md`
- 无 frontmatter → capability = feature slug（独立能力），delta 写到 `specs/<feature>/spec.md`

### 第三步：生成 proposal.md（三件套之一）

从设计文档提炼方案提案，写入 `openspec/changes/<feature>/proposal.md`。**内容结构**（OpenSpec proposal 模板，**全部中文**）：

```markdown
## Why

[决策摘要的目标 + 方案选择。说明为什么需要这个 change，解决什么问题。]

## What Changes

[决策摘要的方案选择。具体描述新增能力、修改或移除的内容。]

## Capabilities

### New Capabilities

- `<capability>`: <本特性覆盖的业务能力，简要描述>
```

（若是已有能力的迭代，用 `### Modified Capabilities` 替代 `### New Capabilities`）

```markdown
## 数据流契约

> 涉及跨链路字段时按下方「字段卡片」逐个详述；否则写「本特性无跨链路字段」。
> 本小节是 apply 阶段的**硬依赖**——确定性层会校验此段头是否存在，
> 缺失或不合格 proposal 会被 apply 拒收并打回 propose。

### 字段：bizType

- 含义：业务类型，决定走哪条处理分支
- 值域：`{订单,退款,调拨}`
- 运行时来源：上游订单中心 `POST /api/v2/order` 的 `payload.bizType`，经网关透传到下游
- 注入点：`OrderService.handle(ctx)` 中 `ctx.getBizType()` 读取
- 空值处理：缺失时按「订单」兜底 + warn 日志

未确认项：[列出尚需追问/验证的字段及风险]
```

```markdown
## Impact

[决策摘要的边界与约束。受影响的代码、API、依赖、系统。]
```

**格式约定**（让人能读、让 AI 能机械抽取，与设计文档数据流章节一致）：
- 每个跨链路字段一个小节，标题固定 `### 字段：<field>`（AI 按 `^###\s+字段：` 切分）
- 标签行固定为 `- 含义 / - 值域 / - 运行时来源 / - 注入点 / - 空值处理` 五项，顺序不变、不增删（AI 按标签前缀定位）
- 值域用可识别格式：枚举 `{a,b,c}`、区间 `[min,max)`、正则 `re:xxx`、日期/格式 `fmt:yyyy-MM-dd`
- 注入点用全限定名 `类.方法` 或配置 key，不用裸行号

**数据来源纪律**：字段卡片必须从设计文档「数据流」章节逐张抄入，**不得凭空增删**。若发现 spec 场景需要某字段但设计文档数据流章节未覆盖，说明 explore 探索有缺口，应回退到 `/specpowers-explore` 补全，而非在 propose 凭空假设。

**能力归属（capability frontmatter）**：若第二步解析出共享 capability（迭代场景），proposal.md 顶部写 YAML frontmatter 指定（设计文档已有则原样继承）：

```markdown
---
capability: 用户登录
---
## Why
...
```

- 若文件已存在（迭代轮）则覆盖更新 + 追加「## 迭代历史」（见迭代轮小节）
- **必备小节**：`## Why`、`## What Changes`、`## Capabilities`、`## 数据流契约`、`## Impact`

### 第四步：生成 delta spec（三件套之二）

使用 **OpenSpec delta 格式**生成 spec.md，**全部使用中文**。

> 这是 change 的核心规范文件，apply 阶段验证、archive 阶段合并主规格都依赖它。
> **WHEN/THEN 必须从需求真实提取**，不要填空模板（如"用户执行相关操作"这种无意义内容）。

格式：

```markdown
## ADDED Requirements

### Requirement: <feature>
<本 requirement 描述 feature 要满足的核心能力，含 SHALL 关键字>
The system SHALL <一句话描述 feature 的核心能力>。

#### Scenario: <场景名 1>
- **WHEN** <真实的触发条件，从需求提取>
- **THEN** <真实的预期结果，可测试可验证>

#### Scenario: <场景名 2>
- **WHEN** <触发条件>
- **THEN** <预期结果>
```

**要求**（OpenSpec validator 硬约束）：
- 必须含 `## ADDED Requirements` 段头
- 段内至少一条 `### Requirement: <name>`，name 用 feature slug
- requirement body 必须含 `SHALL` 或 `MUST`
- 每个 requirement 至少一个 `#### Scenario:`
- 每个 Scenario 必须含 `**WHEN**` 和 `**THEN**`

**requirement 名固定用 feature slug**（迭代标识，保证跨次归档不重名冲突）。

**Scenario 与数据流契约的关系**：涉及跨链路字段的 Scenario，其 WHEN/THEN 必须能从 proposal 的「数据流契约」字段来源/值域导出，**不得引入数据流契约之外的未知字段来源**。

写入 `openspec/changes/<feature>/specs/<capability>/spec.md`（capability 来自第二步）。

### 第五步：生成 tasks.md（三件套之三）

调用 superpowers 的 `writing-plans` 技能，但进行瘦身：

**产物归并**：所有任务合并到单一 `openspec/changes/<feature>/tasks.md`。

**内容语言**：**全部使用中文**。

**任务格式**（对齐 superpowers writing-plans 技能的 `Task N` 标题结构 + specpowers 固定字段）：

> **重要**：任务标题必须用 `### Task N: [描述]` 格式（英文 Task + 编号），
> 这是 subagent-driven-development 的 `task-brief` 脚本切分任务的依据
> （脚本按 `^#+ Task N` 匹配，awk 整段透传，不解析字段名）。内容用中文，但标题结构不可改。
> 新增字段只要写在 `### Task N` 标题之后、下一个 Task 标题之前，就会原样进入 task-brief，
> conductor 与 subagent 两种执行模式都能消费。

**字段档位**：先按第六步判定本特性的推荐执行方式，再套对应档位的字段模板。
推荐=conductor（或 fast 模式）用「conductor 档」；推荐=subagent 用「subagent 档」。
用户在 apply 阶段仍可改执行方式，但 tasks.md 字段已按档位定稿，改模式可能需重跑本步。

**conductor 档**（推荐=conductor，或 fast 模式）——轻量字段 + 场景原文：

```markdown
## 推荐执行方式

<!-- 顶部注释块标注推荐方式，apply 阶段读 -->
<!--
推荐：conductor（顺序执行，默认）/ worktree / subagent / TDD
worktree：[推荐 / 可选 / 不推荐]
subagent：[推荐 / 可选 / 不推荐]
TDD：[推荐 / 可选 / 不推荐]
-->

### Task 1: [任务描述]

- [ ] 实现内容：<具体步骤>
- 场景引用：<关联 delta spec 的 Scenario 名 + 该 Scenario 的 WHEN-THEN 原文摘录，供无 spec 上下文时核对>
- 验收标准：<本任务验收标准>
- 依赖：<前置任务，无则写 无>
- 并行：<是/否；若可与其他任务并行，列出可并行的兄弟任务号，如「是，可与 Task 3/5 并行」；否则写 否>
- 检查点：<本任务完成后是否需独立验证；如「完成验证：本地编译通过+单元测试绿色」或「无」；关键集成点建议设检查点>

### Task 2: [任务描述]

- [ ] 实现内容：<具体步骤>
- 场景引用：<Scenario 名 + WHEN-THEN 原文摘录>
- 验收标准：<本任务验收标准>
- 依赖：Task 1
- 并行：<是/否 + 可并行的兄弟任务号；否则写 否>
- 检查点：<本任务完成后是否需独立验证，或写 无>
```

**subagent 档**（推荐=subagent）——subagent 是零上下文执行单元，只看 brief、看不到设计文档/proposal/spec/代码库/前置任务实现，必须把以下硬数据显式写入每个 Task：

```markdown
### Task N: [任务描述]

- [ ] 实现内容：<具体步骤>
- 场景引用：<Scenario 名 + WHEN-THEN 原文摘录>
- 验收标准：<本任务验收标准>
- 检查点：<本任务完成后 subagent 须自验的内容，如「编译通过+对应单测绿色」或「无」；controller 在 spec-reviewer 审查前据此判断是否放行>
- 依赖：<前置任务编号，无则写 无>
- 并行：<是/否 + 可并行的兄弟任务号；subagent 模式下 controller 据此决定是否并行派发；无并行可能则写 否>
- 前置产出契约：<若依赖前置任务，列出前置任务产出的精确符号——常量全名/方法签名/DTO 类名+字段，让本任务 subagent 不必回读前置实现；无依赖则写 无>
- 代码锚点：<目标文件相对路径 + 类全限定名 + 方法签名 + 锚点代码片段（方法内某段唯一代码，供行号漂移后定位），禁止只写行号>
- 依赖 API：<本任务调用的精确方法签名 + 参考调用点（类:行）+ Bean 获取方式（@Autowired / SpringBeanUtil.getBeanOfType，非 Spring 托管时注明）>
- 数据来源：<本任务涉及的每个跨链路字段，逐一列出 字段名=取值表达式 + 值域 + 空值处理；从 proposal 数据流契约字段卡片抄入对应标签（取值表达式=运行时来源，附注入点全限定名）；无跨链路字段则写 无>
- 触发条件：<何种输入/状态下才执行本任务逻辑，如 rechargeType 为 CLOTHING_GIFT_CARD 才触发；无条件则写 始终>
- 异常策略：<try-catch 范围 + 日志级别 + 是否阻断主流程；对齐项目规范「打印整个异常而非只打印 msg」>
- 验证命令：<编译命令如 mvn -pl xxx test-compile -am -o -q（无 ERROR 即过）；或测试运行 mvn test -Dtest=类#方法>
- 卡住升级：<连续编译失败 2 次 / 找不到 API 签名 / 数据来源不明 → 返回主 session 问用户，禁止瞎猜>
```

> subagent 档字段覆盖了 7 类缺口：第4类场景原文、第1类代码锚点、第2类 API 契约、第3类数据来源、第7类前置产出、第8类验证+升级路径。第5类测试模板与第6类项目编码规范及其余项目原则（质量/测试/UX/性能）走 constitution.md 统一管道——apply 阶段 controller 从 `.specpowers/constitution.md` 摘录全部原则注入每个 task 的 Context（subagent 隔离上下文，看不到 AGENTS.md/CLAUDE.md/constitution.md，必须显式注入），不重复进 task。

#### 字段填充指引（各字段数据来源，避免凭空填写）

- **代码锚点 / 依赖 API**：查代码库（grep 类名/方法签名定位文件，摘录方法签名与唯一代码片段）。禁止写裸行号（前置任务改动会让行号漂移）。
- **数据来源**：从 `openspec/changes/<feature>/proposal.md` 的「## 数据流契约」字段卡片逐张抄入（每张卡片含 字段名/值域/运行时来源/注入点/空值处理 五个标签）。若数据流契约未覆盖本任务所需字段，**不得自行假设**——触发第七步「跨链路入参数据来源回溯」向用户澄清。
- **前置产出契约**：从已完成的前置 Task 小节的「实现内容」提取产出的符号（常量全名/方法签名/DTO 字段）。若前置 Task 尚未实现，契约即本 feature 对该产出的约定，后续前置 Task 实现时必须遵守。
- **场景原文**：从 `openspec/changes/<feature>/specs/<capability>/spec.md` 摘录 WHEN-THEN 原文，不要只写 Scenario 名。
- **验证命令**：查项目 build 工具（有 `pom.xml` → mvn；有 `package.json` → npm/yarn；有 `pyproject.toml` → pytest）。
- **并行**：判断本任务是否与兄弟任务无文件冲突、无数据依赖。可并行的典型场景：不同模块的同级任务、同模块内只读不同文件的任务。注意：并行任务不得修改同一文件。
- **检查点**：在关键集成点（如 foundational 任务完成、某 user story 闭环、跨模块对接前）设检查点。检查点内容须可独立验证（编译通过/测试绿色/接口对接成功）。

### 第六步：执行方式推荐

tasks.md 顶部「## 推荐执行方式」注释块（模板见第五步 conductor 档）给出本特性**推荐的**执行方式，apply 阶段由用户最终选择。

> 这是推荐而非强制。apply 阶段会提示用户，用户拥有最终选择权。
> 注释块统一用第五步 conductor 档模板里的格式，不要另造措辞。

- 优化模式（fast）：**禁止推荐 worktree 和 subagent**（fast 仅允许 TDD 作为可选能力）

- **worktree 推荐判定**（满足以下任一才推荐/可选 worktree，否则标 不推荐）：
  - **隔离工作区收益**：存在 ≥ 2 条互不依赖且各自较长的并行任务链（每条链需多次提交/验证），在独立 worktree 推进可避免主分支索引被来回切换污染、降低半成品互相覆盖风险。
  - **多人并行开发特性**：多个任务天然分属不同模块/责任人，各自在自己的 worktree 推进，主分支保持干净直到合并。
  - **需在隔离工作树验证**：改动涉及破坏性重构（如大范围重命名/删除/目录迁移），需在独立 worktree 先验证再合并，避免主分支长期处于不可编译状态。
  - **不推荐 worktree 的典型场景**：单链路线性特性、任务数 ≤ 5 的连续上下文特性、或无并行需求的单点改动——worktree 切换与合并开销高于隔离收益，直接 conductor 在主分支推进更划算。
  - **与 subagent 的区别**：worktree 隔离的是 git 工作区（仍由主 session 顺序执行），subagent 隔离的是执行上下文（每任务一个零上下文执行单元）。两者可叠加（如 subagent 在各自 worktree 跑），但默认按上方判定独立标注。
  - worktree 推荐与否只影响注释块 `worktree：` 一栏的标注，不影响第五步字段档位（worktree 仍用「conductor 档」字段）。

- **subagent 推荐判定**（满足以下任一才推荐 subagent，否则默认 conductor）：
  - 任务数 ≥ 15 且存在可并行的独立链路（如 A→B 与 C→D 互不依赖，可派给 subagent 并行）
  - 算法/状态机密集任务（适合独立 subagent 跑 TDD 红绿循环，避免污染主上下文）
  - 多模块跨团队特性（任务天然边界清晰，subagent 隔离收益高）
  - **不推荐 subagent 的典型场景**：9 任务以下的 CRUD 级连续上下文特性——subagent brief 准备成本（每个 task 扩 3-5 倍篇幅 + 数据流预先排查）高于并行收益，conductor 自执行更划算。
  - **中间区间（10-14 任务）**：默认 conductor；仅当存在明确的独立并行链路（至少 2 条互不依赖的任务链）时，才升级为 subagent，并在 tasks.md 注释块说明升级理由。
  - 本判定决定第五步套用「conductor 档」还是「subagent 档」字段模板。

- **TDD 推荐判定**（满足以下任一才推荐/可选 TDD，否则标 不推荐）：
  - **核心业务逻辑 / 算法 / 状态机**：有明确输入输出契约、可独立单元测试的逻辑单元（计费、折扣、风控规则、排序/匹配算法等）——红-绿-重构收益最高。
  - **回归风险高的逻辑改动**：改动位于被多处依赖的核心路径，需先用测试锁定既有行为再重构（特性开关、兼容性分支）。
  - **不推荐 TDD 的典型场景**：纯 UI/布局调整、配置改动、胶水接线（@Autowired 连线、controller 转调 service 的薄壳）、数据迁移/脚本类无清晰单元测试落点的改动——强行 TDD 反而徒增测试桩维护负担。
  - **与执行编排的关系**：TDD 是「能力」而非「编排」，可与 conductor / worktree / subagent 任一叠加（如「推荐 subagent + 可选 TDD」）。注释块 `TDD：` 一栏据此标注，字段档位仍由 worktree/subagent 判定决定。

### 第七步：自审核

三件套全部落盘后进行自我审核：
- 每个任务是否覆盖 delta spec 中的 Scenario
- 依赖关系是否合理
- 推荐执行方式是否符合特性特征（如 TDD 适合核心逻辑、worktree 适合多人并行等）
- proposal 数据流契约是否与设计文档数据流章节一致（无凭空字段）
- **跨链路入参数据来源回溯（第3类，最关键）**：对每个涉及「跨模块/跨系统/跨进程」入参的任务（典型如回调 handler、消息消费者、对外暴露接口的下游消费者），逐个追问入参字段的**运行时数据来源**——该值在调用方那头叫什么、由谁产生、经哪条链路传过来、payload 里是否有对应字段。任一入参无法从 proposal 数据流契约卡片追溯到明确产生方与传递链路时，**不得放过**：回到上方「交互决策原则」用 AskUserQuestion 向用户澄清真实字段名与来源，缺口补齐后再定稿 tasks.md。避免把数据来源缺口拖延到 apply 阶段返工——conductor 模式下本类盲区会返工，subagent 模式下会直接卡死或瞎猜。
- **前置产出契约一致性（第7类）**：依赖前置任务的每个 Task，其「前置产出契约」列出的常量名/方法签名/DTO 字段，必须与前置 Task 的「实现内容」描述一致。若前置 Task 尚未实现（本 feature 内），契约即为本 feature 对该产出的约定，后续前置 Task 实现时必须遵守此契约——subagent 无上下文，契约不一致会导致它回读前置实现或直接失败。
- **subagent 档字段完整性（第1/2/3/8类）**：若推荐=subagent，逐个 Task 核对：代码锚点是否含文件路径+方法签名（非裸行号）、依赖 API 是否含完整签名+Bean 获取方式、数据来源是否覆盖该任务全部跨链路字段、验证命令是否可执行。任一缺失，补齐后再定稿。

### 第八步：落盘收尾

tasks.md **末尾追加「## 依赖与并行说明」小节**（最后一个 Task 之后），汇总：
- **关键路径**：列出阻塞后续任务的前置链（如 Task 1→3→6 为关键路径）
- **可并行组**：列出可同时派发的任务组（如 [Task 2, Task 4, Task 5] 可并行）
- **检查点序列**：按执行顺序列出所有标注了检查点的 Task 及其验证内容

此小节不参与 task-brief 切分（awk 只切 `### Task N` 段落，末尾的 `##` 小节不会被误切），供 apply 阶段 controller 规划执行顺序与并行派发。

**禁止自动 git commit**：只生成文件，不执行 `git add` / `git commit`。后续各阶段（含 archive 归档）同样不提交代码，提交由用户自行完成。

### 第九步：通知用户

```
✅ openspec/changes/<feature>/proposal.md 已生成（含「## 数据流契约」）
✅ openspec/changes/<feature>/specs/<capability>/spec.md 已生成
✅ openspec/changes/<feature>/tasks.md 已生成（推荐执行方式 + N 个任务）
下一步：/specpowers-apply
```

## 约束

- delta 格式严格遵循 OpenSpec 规范（validator 会校验）
- Scenario 的 WHEN/THEN 必须真实、可测试、可验证，禁止填空
- 若设计文档/proposal.md 存在，capability 必须从其 frontmatter 解析
- 迭代场景（capability ≠ feature）：requirement 名用 feature slug，与主规格已有 requirement 累积不冲突

## 瘦身原则（tasks.md）

- 只有一个 tasks.md 文件
- 不生成 research.md / data-model.md / contracts.md / quickstart.md
- 任务格式固定（OpenSpec 复选框 + specpowers 固定字段），禁止自由发散
- tasks.md 结构：顶部「## 推荐执行方式」注释块 + 中部 `### Task N` 序列 + 末尾「## 依赖与并行说明」小节；**迭代轮**另有轮次小节（`## Round <N>`）与「## 已作废」小节，均在「依赖与并行说明」之前。禁止插入 Phase/Stage 标题（破坏 task-brief 锚点）

## 迭代轮：三件套增量修订（多轮迭代，auto 与人工模式通用）

当本轮是迭代轮（`state.json` 的 `iteration_count` ≥ 1——入口可以是 `/specpowers-propose`、`/specpowers-explore` 重入识别确认（人工模式，见「重入识别」小节）或 `/specpowers-auto`（无人值守））时，三件套不做盲目重写，按各自规则增量演进（方案变更时 explore 已先更新设计文档，见 explore.md 迭代轮小节）：

**proposal.md — 覆盖 + 迭代历史**：
- proposal.md **覆盖更新**（以本轮有效八要素为准），但文末必须**追加「## 迭代历史」小节**（已有则续写），记录本轮变化点：

```markdown
## 迭代历史

### Round <N>（<日期>）

- 输入：<新设计文档 <路径> / 口头指令 "<摘要>">
- 变化点：<相对上一轮的方案/边界/依赖变化，逐条列出；无变化则写「仅场景与范围调整，方案未变」>
```

- **feature 锁定**：迭代轮 feature 已由确定性层锁定，proposal.md 仍写入原 change 目录（`openspec/changes/<锁定slug>/`），不新建目录
- **调用方式**：迭代轮更新 proposal 是**认知任务直接落盘**，不调 `facade propose`（其常规入口不含本语境）；stage 保持 propose
- **注意**：方案变更轮（explore 重跑）必须重新从更新后的设计文档提炼 proposal；仅场景/范围调整轮 proposal 可原样保留（追加迭代历史即可）

**spec.md — 增量修订**：
- **对照本轮有效场景清单增量修订**现有 delta spec。场景清单来源：auto 迭代轮取八要素「必测场景清单」；人工迭代轮取用户本轮调整描述与现有 spec 的合并结果：

| 现有场景 vs 本轮清单 | 处理 |
|----------------------|------|
| 场景仍存在但描述有变 | 按本轮清单更新 WHEN/THEN（保持 Scenario 名稳定，便于 tasks/apply 追踪） |
| 场景仍存在且无变化 | 原样保留 |
| 场景已从清单删除 | 从 delta 中移除该 Scenario（归档前 delta 只在 change 内，移除安全） |
| 清单新增场景 | 按 OpenSpec delta 格式追加 |

- 修订完成后在 spec.md 末尾追加一行 HTML 注释记录轮次痕迹：`<!-- Round <N> 修订：+<新增数> / ~<更新数> / -<删除数> -->`
- **硬底线**：无论多小的迭代，本轮调整必须反映到 spec.md（这是「归档前所有调整记录在当前 spec 文件内」的落点），轻量迭代也不例外

**tasks.md — 分轮演进（任务台账差异同步）**：
- 不重新生成 tasks.md，而是把现有文件作为**任务台账**做**差异同步**：
  1. **读现状**：现有 tasks.md 各任务勾选状态（`[x]`/`[ ]`）+ 本轮有效八要素「修改范围表」+ 现有代码事实
  2. **差异分析**，产出三类变更：
     - 上轮**未完成且仍有效**的任务 → 原样保留在原小节，继续待办
     - 被本轮调整**作废**的任务（对应场景已从 spec 删除等）→ 移入末尾「## 已作废」小节：删除线包裹标题 + 作废依据留痕（`- ~~### Task 2: xxx~~ — Round <N> 作废，依据：<spec 场景删除 / 设计文档章节>`），**不物理删除**
     - 本轮**新增**任务 → 写入新轮次小节 `## Round <N>（<输入摘要>）`，任务编号延续全局递增（避免跨轮重号），格式沿用对应档位模板，每个任务标注涉及文件路径、验收要点、对应 spec 场景
  3. **已完成任务**（`[x]`）一律不动，跨轮保留

apply 侧消费规则：**只执行未勾选且未作废的任务**（见 apply.md 迭代轮小节）。轮次小节不破坏 task-brief 切分（脚本按 `^#+ Task N` 匹配整段，`## Round` 标题不影响）。

archive 的「任务全部完成」判定**跳过「已作废」小节**（作废 ≠ 待办，见 archive.md）。

首轮（非迭代轮）行为不变：按上方执行步骤全新生成，任务编号即 Round 1 内容（无需显式 Round 标题，保持「## 推荐执行方式」+ `### Task N` 原结构）。

## 回退场景（fallback）

当从 `apply` 回退到 `propose` 时（fast 用户"升级为完整流程"）：
- stage 从 `apply` → `propose`
- mode 重置为 `full`
- fallback_count += 1
- 原因：用户认为优化模式不适用，升级为完整流程（放弃 fast 产物，重新完整生成三件套）

## 后续步骤

完成后 stage 跃迁到 `propose`，下一步：`/specpowers-apply`。
