# explore.md — 特性探索契约

## 触发

当用户调用 `/specpowers-explore "<需求>"` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 来自 state.json 的 feature 字段（explore/fast 阶段确定并锁定，同一流程不变）。

## 定位（v2.0.0 调整）

本阶段**只探索，不写流水线产物**：产物 = 探索设计文档（`docs/specpowers/design/`，由内置 specpowers-explore 技能落盘，含数据流结论），并经确定性层登记（`facade record-design-doc`）。`openspec/changes/` 目录在本阶段**不创建**——proposal.md / spec.md / tasks.md 三件套统一由下一阶段 `/specpowers-propose` 一站式生成。

## 重入识别（人工模式迭代轮入口）

执行前置校验**之前**，先读 `.specpowers/state.json` 判断本次调用是否为迭代重入：

- **触发条件**：`stage` ∈ {`propose`, `apply`} 且 `feature` 非空（活跃未归档）。此时 `facade explore` 的常规入口（仅允许 from `ready`）不可用，重跑探索的唯一合理意图是：**同一个未归档需求的方案发生变更**，需要开新迭代轮更新探索结论与设计文档。
- **交互确认**（必须，禁止静默切换轮次）：

  ```
  检测到未归档需求 <feature>（stage=<stage>，当前 Round <iteration_count>）。
  重跑探索意味着方案可能变更。是否开启 Round <iteration_count+1> 迭代轮并更新探索结论（设计文档）？
  1. 是 —— 调 `facade iterate` 开轮（feature 锁定不变），探索后覆盖更新设计文档并追加迭代历史
  2. 否 —— 取消（若仅是场景/范围调整，无需动方案：直接重入 /specpowers-propose 即可）
  ```
- **确认开启**：调 `facade iterate [--instruction "<调整描述>"] --root .`（stage → `propose`、feature 锁定、`iteration_count += 1`），然后按下方「迭代轮」小节执行探索与设计文档覆盖更新；完成后提示用户 `/specpowers-propose` 做三件套增量修订
- **选择取消**：不改任何状态，向用户说明可选步骤后结束
- **未触发**（stage=`ready`）：正常流程——全新需求探索（stage=`init` 时提示先跑 `/specpowers-init`）

## 前置校验

```bash
python -m specpowers_cli.bridge.facade explore "<需求>" --root .
```

- 确认 stage 处于 `ready`
- feature 名已规范化并写入 state.json
- 检查 constitution.md 存在（缺则拒绝）

## 执行步骤

### 第一步：探索项目上下文

<HARD-GATE>
本阶段**必须先调用本插件内置的 `specpowers-explore` 技能**（即 `specpowers:specpowers-explore`，随插件分发无需外部依赖）完成需求探索，然后才允许收口。禁止跳过探索直接读静态文件收口。

specpowers-explore 技能的「静默项目探索 → 2-3 方案统一维度对比 → 唯一推荐 → 设计文档落盘（`docs/specpowers/design/`）→ 结构化探索结论交付」流程必须真实执行——这是下游 propose 阶段的硬依赖。propose 从 explore 进入时会被确定性层校验设计文档是否登记（state.design_doc 非空且文件存在），未登记会被拒收并打回 explore；proposal 的「数据流契约」质量也由设计文档的数据流结论决定（apply 入口确定性层校验段头）。

**分层局限说明**：确定性层的校验只查「设计文档已登记」与「数据流契约**段头存在性**」（形式合规），无法判定探索是否**实质发生**（内容质量）。要绕过校验只需落一份空文档——因此本机制兜的是「最低底线」（连文档都没有 = 肯定没好好探索），**探索的实质质量依赖**：① 本 HARD-GATE 措辞引导真探索（认知层）；② 用户人工 review 设计文档与 proposal 内容（人工层）。三层防御，确定性层不是万能的。
</HARD-GATE>

1. 阅读 `.specpowers/constitution.md` 了解项目原则
2. 阅读 `.specpowers/baseline.json` 了解项目结构
3. **调用内置 `specpowers-explore` 技能进行需求探索**（硬约束，见上 HARD-GATE；技能返回探索结论，含项目上下文/方案对比/推荐/设计文档路径/跨链路字段线索；设计文档落盘在 `docs/specpowers/design/YYYY-MM-DD-{name}-design.md`）
4. 与用户交互，提出澄清问题
5. 运行时数据流溯源（条件触发）

   以 specpowers-explore 探索结论的「跨链路字段线索」小节为起点，自检：本特性是否涉及**跨链路字段**——即数据要跨服务/跨模块/跨层传递，或依赖运行时才确定的值（上游接口注入、配置中心下发、DB 读取、MQ 透传、请求头携带等）。

   - **涉及跨链路字段** → 对每个字段追问以下 6 项（即设计文档数据流章节要写的字段卡片标签，逐项落实，不缺项）：

     | 项（卡片标签） | 说明 |
     |----|------|
     | 字段名 | payload / 接口签名 / 配置 key 中的实际名字（卡片小节标题 `### 字段：<field>`） |
     | 含义 | 业务语义 |
     | 值域 | 用可机械识别格式：枚举写 `{a,b,c}`、区间写 `[min,max)`、正则写 `re:xxx`、格式写 `fmt:yyyy-MM-dd` |
     | 运行时来源 | 从哪个上游注入（接口 / 配置 / DB / MQ / 请求头），含完整传递链路 |
     | 注入点 | 代码哪个位置被读取 / 赋值，用全限定名 `类.方法` 或配置 key |
     | 空值处理 | 缺失/非法时如何兜底：默认值 + 日志级别 / 拒绝 / 抛异常 |

   - **不涉及**（纯本地逻辑 / 纯前端 / 无跨边界数据）→ 跳过溯源，设计文档数据流章节标注「本特性无跨链路字段」

   **禁止靠读类结构臆测字段来源**——类结构只能看出字段存在，看不出运行时来源和值域（这正是 bizType 类缺口的来源）。不确定时**必须用 AskUserQuestion 追问**，问到确认为止。

### 交互决策原则（AskUserQuestion 使用指引）

explore 阶段**默认采用推荐方案**，不强制打断用户。但当出现以下情况时，**必须主动用 AskUserQuestion 让用户决策**：

| 触发场景 | 处理方式 |
|---------|---------|
| 探索结果模糊，无法确切给出结论 | 列出候选方向 + 各自影响 + 推荐，让用户选 |
| 多种技术方案难分优劣（各有显著取舍） | 列出 2-4 个方案，说明每个的优劣，标注推荐项及理由 |
| 需求存在明显歧义/多种合理理解 | 列出不同理解，让用户澄清意图 |
| 涉及不可逆决策（如选型、架构方向） | 即使有推荐也需用户确认 |

**AskUserQuestion 格式要求**：
- 每个选项给清晰的 label（1-5 词）和 description（说明影响/取舍）
- 推荐项放第一个，label 末尾加「（推荐）」
- 问题描述要具体，让用户能直接判断
- 仅在真正需要用户判断时问，能自行合理决定的不要问（避免过度打扰）

### 第二步：收口 — 生成结构化决策摘要

探索结束后，**必须**产生以下结构化摘要，**全部使用中文**（随探索结论交付 propose 阶段，并组织进设计文档）：

```markdown
## 决策摘要

**目标**：[一句话描述本特性要达成的核心目标]

**方案选择**：[选定的技术方案 / 实现路径]

**替代方案**：
- 方案A：[描述] — [不选的原因]
- 方案B：[描述] — [不选的原因]

**边界与约束**：[明确不在本次范围内的内容和已知限制]
```

### 第三步：确认设计文档 + 登记确定性层

specpowers-explore 技能已把设计文档落盘到 `docs/specpowers/design/YYYY-MM-DD-{name}-design.md`。收口时核对/补全以下内容（覆盖写入同一文件）：

- **架构设计 / 组件划分 / 接口定义 / 错误处理**：技能已生成，按决策摘要校正
- **`## 数据流` 章节**（本阶段核心增量）：跨链路字段按字段卡片逐个详述（标签行固定 `- 含义 / - 值域 / - 运行时来源 / - 注入点 / - 空值处理` 五项，顺序不变、不增删）；纯本地特性则声明「本特性无跨链路字段」。**本章节是 propose 生成 proposal「## 数据流契约」的唯一来源**，缺失或空泛会传导为下游 proposal 质量缺口
- **格式约定**（让人能读、让 AI 能机械抽取）：每个跨链路字段一个小节，标题固定 `### 字段：<field>`（AI 按 `^###\s+字段：` 切分）；值域用可识别格式（枚举 `{a,b,c}`、区间 `[min,max)`、正则 `re:xxx`、日期/格式 `fmt:yyyy-MM-dd`）；注入点用全限定名 `类.方法` 或配置 key，不用裸行号
- **能力归属（capability）**：探索时若识别出**本特性是已有能力的迭代**（团队已归档过同领域 feature），需在设计文档头部写 YAML frontmatter 指定共享 capability：
  ```markdown
  ---
  capability: 用户登录
  ---
  ```
  - `capability` = 已归档的业务能力名（跨迭代不变，对应 `openspec/specs/<capability>/spec.md`）
  - 未指定时，capability 默认 = feature slug（独立能力，feature 间隔离）
  - **迭代场景**：feature slug 用新名（如 `用户登录-oauth`），capability 指向已有能力（`用户登录`），归档时新 requirement 累积到同一主规格，不覆盖旧版本
- 内容语言：**中文**；若文件已存在则覆盖更新

**登记（必须，硬依赖）**：设计文档落盘后立即调确定性层登记路径，供 propose 前置校验：

```bash
python -m specpowers_cli.bridge.facade record-design-doc <设计文档路径> --root .
```

- 登记失败（文件不存在）会非 0 退出，须修正后重试
- 未登记的设计文档在 propose 阶段不被承认（state.design_doc 为空 → propose 拒收并打回 explore）

#### 未收敛 / 否决处理

探索未收敛或被否决时，设计文档标题（首个 `#` 标题）标注状态：

| 形式 | 标题标注 |
|------|-----------|
| 未收敛 | 标题注 `[未收敛]`，保留当前讨论状态、剩余分歧点（auto 停靠语义见 auto.md） |
| 否决记录 | 标题注 `[已否决]`，记录否决原因和讨论过程 |

**但凡调用了 explore，设计文档必须落盘并登记。不存"探索了但不落盘"的情况。**

### 第四步：通知用户

```
✅ docs/specpowers/design/YYYY-MM-DD-{name}-design.md 已生成并登记
下一步：/specpowers-propose "<需求>"（一站式生成 proposal.md + spec.md + tasks.md）
```

## 判小信号映射（参考）

当 agent 在此阶段或后续阶段做"小/非小"判定时，参考以下信号：

| 信号 | 含义 | 典型场景 |
|------|------|---------|
| `bugfix` | 修复缺陷 | 修 bug、补边界条件 |
| `单文件` | 仅涉及 1 个文件 | 小改动 |
| `无新场景` | 不新增业务场景 | 重构、优化 |
| `纯配置` | 仅配置修改 | 改 yaml/json/env |
| `纯文案` | 仅文案修改 | 改 copy、i18n |
| `纯重构` | 不改行为 | 重命名、提取方法 |

## 迭代轮：设计文档覆盖 + 迭代历史（多轮迭代，auto 与人工模式通用）

当本轮是迭代轮且**方案相对上一轮发生变更**时（人工模式由 `/specpowers-explore`、`/specpowers-propose` 重入识别与用户确认，见「重入识别」小节；auto 模式由 auto 契约按「已定方案」判定）：

- 设计文档**覆盖更新**（以本轮有效八要素为准），但文末必须**追加「## 迭代历史」小节**（已有则续写），记录本轮变化点，保证决策痕迹可追溯：

```markdown
## 迭代历史

### Round <N>（<日期>）

- 输入：<新设计文档 <路径> / 口头指令 "<摘要>">
- 变化点：<相对上一轮的方案/边界/依赖变化，逐条列出；无变化则写「仅场景与范围调整，方案未变」>
```

- **feature 锁定**：迭代轮 feature 已由确定性层锁定（`state.json` 的 feature 字段，重入确认后的 `facade iterate` 或 `auto new-round` 轮次切换时均不改动），设计文档仍更新原路径，change 目录不迁移（`openspec/changes/<锁定slug>/` 由 propose 维护）
- **调用方式**：迭代轮更新设计文档是**认知任务直接落盘**，不调 `facade explore`（其语义是"从 ready 开新特性"，与迭代轮 stage=propose 冲突）；stage 保持 propose，更新后须重新 `facade record-design-doc` 刷新登记
- 首轮（非迭代轮）行为不变：按上方执行步骤全新生成

## 后续步骤

完成后 stage 跃迁到 `explore`，下一步：`/specpowers-propose "<需求>"`。
