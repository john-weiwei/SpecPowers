# SpecPowers

> 桥接编排插件 — 在 OpenSpec + superpowers 之上叠加**结构一致性门禁**与**实时卡转人工**。

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-2.7.0-blue)]()

SpecPowers 是一个通用 AI 编码 agent 插件。它不重写任何框架引擎，只编排 OpenSpec、superpowers 两套框架的原生能力，补上它们都没有的两条硬约束：

- **结构一致性门禁** — AI 写代码不能"无中生有"建目录/加依赖
- **实时卡转人工** — 遇到不确定性立刻暂停等人工判定，不静默跳过

> 🧪 **质量保障**：328 个测试用例守护清单/文档/状态机契约一致性（用例数与清单版本由测试自动校验同步）。

> 📖 **完整指南**：前置依赖详解、四条路径对比、架构、项目结构等完整内容见 [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)。

---

## 支持平台

SpecPowers 支持两类安装方式，按你的 agent 选择：

| Agent | 安装方式 | 入口调用 |
|-------|---------|---------|
| **ZCode** | 插件市场（推荐） | `/specpowers:specpowers-init` 或 `/specpowers-init` |
| **Claude Code** | 插件市场（推荐） | `/specpowers:specpowers-init` 或 `/specpowers-init` |
| **Codex CLI** | 插件市场（推荐） | `/specpowers:specpowers-init` 或 `/specpowers-init` 技能直调（四端统一） |
| **WorkBuddy** | 插件市场（推荐）；pip 亦可 | `/specpowers:specpowers-init` 或 `/specpowers-init` |
| Cursor | pip + `specpowers init --integration cursor` | 技能目录 + AGENTS.md 引导 |
| GitHub Copilot | pip + `specpowers init --integration copilot` | 技能目录 + AGENTS.md 引导 |
| Windsurf | pip + `specpowers init --integration windsurf` | 技能目录 + AGENTS.md 引导 |
| 其他任意工具 | pip + `specpowers init --skills-root <路径>` | AGENTS.md 引导（v2.6.0 零枚举接入） |

> 插件市场方式享受完整体验（9 个阶段技能，slash 直调 `/specpowers-xxx`，四端统一入口 + SessionStart 依赖检测）；pip 方式把 11 个技能复制到对应 skills 目录并在项目根 `AGENTS.md` 写入引导段（幂等标记段，引导 agent 按流水线执行），功能等价但无原生 slash 入口。

## 安装

### 方式一：插件市场（推荐 —— ZCode / Claude Code / Codex / WorkBuddy）

四家的插件结构同构，本仓库已内置四份宿主清单（插件目录内 `.zcode-plugin/`、`.claude-plugin/`、`.codex-plugin/`、`.codebuddy-plugin/`）与四份市场入口清单（仓库根 `marketplace.json`、`.claude-plugin/marketplace.json`、`.agents/plugins/marketplace.json`、`.codebuddy-plugin/marketplace.json`）。把本仓库添加为插件市场源后安装：

```bash
# ZCode
/plugin marketplace add https://github.com/john-weiwei/SpecPowers
/plugin install specpowers

# Claude Code
/plugin marketplace add https://github.com/john-weiwei/SpecPowers
/plugin install specpowers@specpowers-marketplace

# Codex CLI（GitHub 简写；安装走插件面板，CLI 无 install 子命令）
codex plugin marketplace add john-weiwei/SpecPowers
# → 之后在 ChatGPT 桌面端 / Codex 插件面板（Plugins Directory）安装并启用 specpowers

# WorkBuddy
/plugin marketplace add john-weiwei/SpecPowers
/plugin install specpowers@specpowers-marketplace
```

插件内嵌 `specpowers_cli` bridge 包（仅依赖 Python ≥ 3.11 标准库）。装好插件即可直接用 `/specpowers-init` 开始（pip 方式才需要先跑安装器命令 `specpowers init`，见下）。

### 方式二：pip（Cursor / Copilot / Windsurf 等无插件市场的工具）

这些工具不支持插件市场，需通过 pip 安装并在项目里初始化（复制 11 个技能到对应 skills 目录 + 在项目根 `AGENTS.md` 写入引导段）；不在列表内的任意工具用 `specpowers init --skills-root <路径>` 指定自己的技能目录（v2.6.0）：

```bash
# 安装
pip install git+https://github.com/john-weiwei/SpecPowers.git@v2.7.0
# 或本地开发：cd 进仓库目录后 pip install -e .

# 验证
specpowers --version
# → SpecPowers CLI v2.7.0

# 在目标项目里初始化（自动检测 agent 类型）
cd my-project
specpowers init                        # 自动检测 AI agent
specpowers init --integration cursor   # 或指定：cursor/copilot/windsurf/codex/zcode/claude
```

**运行依赖**：Python ≥ 3.11（仅 stdlib，零 pip 依赖）、Git ≥ 2.30。

## 前置编排依赖（重要）

SpecPowers 是**桥接层**，编排以下外部能力。安装本插件前请先就绪：

| 依赖 | 类型 | 影响阶段 | 必需性 | 安装方式 |
|------|------|---------|--------|---------|
| **OpenSpec CLI** | 命令行工具 | archive（归档） | 必需 | `npm install -g @funneler/openspec` |
| **superpowers 插件** | agent skill 包 | propose / apply（explore 引擎内置于 explore 契约、review 用内置 specpowers-review 技能，均随插件分发无需预装） | 推荐 | `/plugin install superpowers` |

**自动检测**：插件内置 SessionStart hook，会话启动时自动检测上述依赖，缺失会在首条回复中提示安装方法——无需手动检查（ZCode / Claude Code / Codex 均生效；Codex 侧 hook 需通过信任审核后运行，未信任时自动跳过，可按下方命令手动确认；WorkBuddy 首版暂不注册 hooks，需手动确认）。同一 hook 还会**只读探测活跃需求**（v2.3.0）：检测到未完成的特性流水线 / auto 断点 / 未归档 change 时，在首条回复中提示续跑入口；零活跃零噪音，跨机接管（state 独立而工件共享）时同样提示。

**WorkBuddy 技能行为异常时先验 CLI 可达**（v2.5.1）：确定性层命令（状态跃迁/设计文档登记）经 `python -m specpowers_cli.bridge.facade <子命令>` 调用，包不可达时改用包装脚本（pip 安装形态位于 `.workbuddy/skills/specpowers/bin/specpowers.bat`，插件市场形态位于插件目录 `scripts/specpowers_cli/bin/`，详见主技能 SKILL.md「执行方式」节）；CLI 不可达时未初始化拦截、propose 登记校验等确定性兜底全部缺位，症状即技能"不守约"——先执行 `specpowers.bat status --root .` 确认 CLI 正常，再检查技能正文是否为 v2.5.1+（跨端契约定位与 explore 硬性产出契约自该版本起生效）。

手动确认（可选）：
```bash
openspec --version          # OpenSpec CLI 可用性
# superpowers 插件在 agent 的插件管理界面查看
```

> - 未装 OpenSpec CLI：仅 archive 阶段会拒绝执行（提示安装），其余阶段正常。
> - 未装 superpowers：propose/apply 会降级为纯提示词引导（无原生 skill 加持），功能可用但体验打折；explore 引擎内置于 explore 契约、review 用内置 specpowers-review 技能，均不受影响。

---

## 快速开始

### 1. 生成项目原则 + 基线（每个项目一次性）

```
/specpowers-init
```

agent 自动读取 `templates/constitution-template.md` 内联生成 `.specpowers/constitution.md`（插件自包含，无需外部依赖），并扫描项目结构生成 `.specpowers/baseline.json`。

> **忘了先 init？没关系（v2.5.0 起）**：直接调用 `/specpowers-explore` / `/specpowers-propose` / `/specpowers-fast` / `/specpowers-apply` / `/specpowers-archive` 时，技能会先检查 `.specpowers/constitution.md` 与 `.specpowers/baseline.json`——任一缺失即告知你并自动执行上面的初始化流程，完成后带着原输入继续目标阶段；确定性层在命令入口同步兜底，未初始化不会静默劣化（如 propose 读不到 constitution 自行编原则）。显式 `/specpowers-init` 仍是最推荐的开局方式（可第一时间确认项目原则再开工）。

> pip 方式用户需先在项目里跑安装器命令 `specpowers init`（见上方"安装 → 方式二"，复制技能目录并写入 AGENTS.md 引导段）；插件市场用户装好插件即可直接用 `/specpowers-init`。

### 2. 启动特性开发

> **新用户只需理解一个决策点**——四个启动入口怎么选；后续流转阶段（apply / archive）无需记忆，会话启动探测与各阶段完成提示会告诉你下一步敲什么。

| 场景 | 入口 |
|------|------|
| 需要探索 | `/specpowers-explore "需求"` |
| 直接开写 | `/specpowers-propose "需求"` |
| 小改动 | `/specpowers-fast "需求"` |
| 已有定稿设计文档，全流程自动 | `/specpowers-auto "设计文档路径"` |

### 3. 执行任务（apply）

```
/specpowers-apply
```

propose 生成 tasks.md 后，apply 接管执行：提示选择执行方式 → **结构门禁**比对 git diff 与 baseline.json（三态判定：通过 / 转人工 / 打回）→ 调用 superpowers 能力池执行编码。详见下方 [apply 阶段详解](#apply-阶段详解)。

### apply 阶段详解

apply 是流水线的**执行核心**，组合了两件事：

**1. 结构门禁（SpecPowers 独有）**

apply 启动时比对 `git diff`，两道检查：

- **结构基线比对**：与 `baseline.json` 对照，发现 AI 代码"无中生有"建目录/加依赖时，三态判定：

| 判定 | 触发条件 | 行为 |
|------|---------|------|
| ✅ 通过 | 改动在已知结构内 | 继续执行 |
| ⚠️ 转人工 | 新建目录/新依赖类型/新模式 | 标记，archive 时人工确认 |
| ❌ 打回 | 明显结构违规 | 拒绝继续 |

- **修改范围比对**（v2.3.0）：propose 在 tasks.md 声明「修改范围：」路径前缀，门禁将实际改动与之做前缀比对，越界文件**转人工**裁决（放行并更新声明 / 回退改动）——把"转人工"从"新结构"细化到"越界改动"；流水线工件（`openspec/`、`.specpowers/`、`docs/specpowers/`）自动豁免

**2. 能力池调度（superpowers）**

根据 tasks.md 顶部注释块的推荐，apply 启动时提示用户选择执行方式，然后调用对应的 superpowers 技能：

| 执行方式 | superpowers 技能 | 说明 |
|---------|-----------------|------|
| conductor | `executing-plans` | 顺序执行所有任务（默认） |
| worktree | `using-git-worktrees` | 隔离工作区并行开发 |
| subagent | `subagent-driven-development` | 每个任务一个 AI 子代理 |
| TDD | `test-driven-development` | 红-绿-重构循环 |

> propose 给出推荐方式，用户最终选择。fast 模式禁 worktree/subagent。

### 4. 收尾

```
/specpowers-archive
```

### 5. 归档前调整需求（多轮迭代）

**归档前，所有调整都视为同一个需求的新迭代轮**，记录进当前 change 目录的同一个 spec 文件；归档即宣告需求终结、开启全新需求：

- **人工模式**：直接重入 `/specpowers-propose "调整描述"`（场景/范围调整）或 `/specpowers-explore`（方案变更）——识别到未归档的活跃需求时会与你确认开启新迭代轮，feature 锁定不变，spec 增量修订、tasks 分轮演进（已完成任务保留、被调整作废的任务留痕）；方案变更轮 v2.7.0 起**不再改写基线设计文档**，改为在 change 目录新落 `design-round-<N>.md` 简易设计文档（只写本轮增量：输入/方案对比/详细设计变更点/修改范围增量，归档时随 change 整体归档）——省 token 关键：基线冻结不再逐轮重读重写整份文档，且设计文档的唯一下游消费者 propose 的迭代轮读取清单同步锁死（现有 proposal + 最新 design-round，基线仅按需局部查阅）
- **auto 模式**：重入 `/specpowers-auto`（新文档 / 原文档 / `--instruction "口头调整"`），自动三分判定全新（fresh）/ 续跑（resume）/ 迭代轮（iterate）

> 注意：想开**全新需求**但当前需求未归档时，请先 `/specpowers-archive` 归档或 `/specpowers-reset` 重置——未归档的活跃需求会接管 auto 的新文档输入，将其判定为旧需求的迭代轮（需求身份由归档状态唯一决定）。

> **会话粘滞（v2.7.0）**：对话中用过 specpowers 技能且需求未归档时，后续消息默认先做相关性判定——相关消息走流程、无关消息照常回答+末尾一行活跃需求提醒、拿不准一律按相关；解除条件 = 归档或 reset。ZCode/Claude/Codex 由 UserPromptSubmit hook 逐轮注入锚点行（feature/stage/Round + capability + 修改范围，零活跃零注入），WorkBuddy/pip 形态靠技能正文条款。与「每阶段开新会话省 token」不冲突：粘滞是**对话内不跑偏**，跨阶段换会话建议不变。

### 💡 省 token 建议

各阶段产物**全部落盘**（`state.json` + `openspec/changes/`），阶段间不依赖对话记忆——因此人工模式推荐**每阶段完成即开新会话**再触发下一条命令：长会话中上下文逐轮累积并重复计费，是 token 消耗的主因；新会话只加载当阶段契约，会话启动探测（v2.3.0）会自动提示续跑入口，跨机接管同样支持。`/specpowers-auto` 无人值守模式例外（单会话直通是其设计）。此外，v2.3.1 起契约已分层按需加载（auto 迭代轮 / review 编排等低频细则不再预载入上下文）。宿主支持 prompt 缓存时，固定的指令前缀可按缓存价计费，建议同一需求内避免频繁切换模型。

---

## 流水线

```
init ─▶ ready ─┬─ explore → propose → apply → archive → ready
               ├─ propose ──→ apply → archive → ready
               ├─ auto ─── 无人值守驱动上述阶段（含 specpowers-review 审查，默认不归档）──▶ ready
               ├─ fast → 用户编码 → apply → archive → ready
               └─ 迭代重入 ─→ 归档前任意阶段重入 propose/explore（或 auto 重入），
                              确认后受控回 propose：feature 锁定不变，
                              spec 增量修订 + tasks 分轮演进（归档即新需求）
```

> **v2.0.0**：阶段重命名 constitution→init、brainstorm→explore、build→apply；specify+plan 合并为 **propose**（一次生成 proposal.md + spec.md + tasks.md 三件套，存储路径不变）。旧项目 `state.json` 自动惰性迁移，无需 reset。

### 阶段技能详解（v2.4.0 起 9 条命令转为技能，slash 名不变）

| 技能（slash 名不变） | 依赖 | 做什么 | 产物 |
|------|------|--------|------|
| `/specpowers-init` | — | 内联生成项目原则（质量/测试/UX/性能，插件自包含），同时扫描顶层目录、依赖清单、源码目录规律 → 结构基线 | `.specpowers/constitution.md` + `.specpowers/baseline.json` |
| `/specpowers-explore "需求"` | init | 按 explore 契约内联的探索引擎细则静默探索项目 → 2-3 方案统一维度对比 → 唯一推荐 → 设计文档落盘（含数据流结论）→ `record-design-doc` 登记；未归档重入=同需求方案变更迭代轮（经确认开轮，设计文档覆盖更新 + 迭代历史） | `docs/specpowers/design/YYYY-MM-DD-{name}-design.md`（探索设计文档） |
| `/specpowers-propose "需求"` | explore（或 ready） | 一站式生成 OpenSpec change 三件套：从设计文档提炼 proposal.md（含「## 数据流契约」）→ OpenSpec 场景格式 spec.md → superpowers `writing-plans` 瘦身 tasks.md（声明执行方式推荐：conductor / worktree / subagent / TDD）；未归档重入=同需求迭代轮（经确认开轮，spec 增量修订、tasks 分轮演进） | `openspec/changes/<feature>/proposal.md` + `specs/<capability>/spec.md` + `tasks.md` |
| `/specpowers-apply` | propose（或 ready+fast） | ① 提示用户选择执行方式（conductor/worktree/subagent/TDD）；② 结构门禁：结构基线比对（git diff vs baseline.json，三态判定）+ 修改范围比对（实际改动 vs tasks.md 声明，越界转人工）；③ 调用 superpowers 能力池执行编码 | 代码变更 |
| `/specpowers-archive` | apply | 三职责收尾：原则核查（constitution 合规）→ 产物标记 → 合体后校验（多分支合并时检查结构一致性）。full 与 fast 统一走 `openspec archive`（强依赖 openspec CLI），合并 delta 到主规格 + change 快照归档 | `openspec/specs/<capability>/spec.md`（主规格，fast 模式下 capability = feature）+ `openspec/changes/archive/`（快照） |
| `/specpowers-fast "需求"` | init | 优化模式入口：agent 判定需求是否为“小改动”（bugfix/单文件/纯配置/纯文案/纯重构），确认后跳过 explore/propose，直接编码 → apply → archive | 验收清单 3-5 条 |
| `/specpowers-auto "设计文档路径"` | ready（fresh 首轮；任意活跃状态可重入，三分判定 fresh/resume/iterate） | 无人值守模式入口：以设计文档为唯一权威输入，解析八要素（功能名/方案/调用链/必测场景/修改范围/编码约束/降级策略/硬性边界）后先做**需求澄清**（五维检查 → 推进深度上限：方案未定等缺陷不停摆，停靠 explore 产出未收敛草案待补结论），再依次驱动 init → explore → propose → apply → specpowers-review（内置审查技能），**任何轮次默认都不归档**（`--archive` 或手动 `/specpowers-archive` 显式收口，`--archive` 先过收口前置检查）；所有确认/门禁节点自动裁决并留痕，review 修复最多 2 轮，仅硬阻断才停；中断后重入即续跑；**归档前重入（新文档/原文档/口头指令）都是同一需求的新迭代轮**（feature 锁定、spec 增量修订、tasks 分轮演进），归档即新需求 | 汇总报告（澄清结论/产物清单/审查结论/编译测试/遗留风险） |
| `/specpowers-baseline` | — | 手动刷新结构基线，重新扫描项目顶层目录/依赖/源码规律 → 覆盖 `baseline.json` | 更新 `baseline.json` |
| `/specpowers-reset` | — | 重置流水线状态：清除 `state.json` 和 `.lock`，回到 `ready` 重新开始（不丢 baseline） | — |

---

## 团队协作

| 文件 | Git 策略 | 说明 |
|------|---------|------|
| `openspec/changes/<feature>/proposal.md` | ✅ 提交 | proposal（方案提案，含数据流契约），团队可见 |
| `docs/specpowers/design/*-design.md` | ✅ 提交 | specpowers-explore 探索产出的设计文档，团队可见 |
| `openspec/changes/<feature>/specs/<capability>/spec.md` | ✅ 提交 | spec（场景 + 验收条件），团队可见 |
| `openspec/changes/<feature>/tasks.md` | ✅ 提交 | tasks（可执行任务列表），团队可见 |
| `.specpowers/constitution.md` | ✅ 提交 | 项目原则全员一致 |
| `.specpowers/baseline.json` | ✅ 提交 | 团队共享结构基线 |
| `.specpowers/state.json` | 🚫 gitignore | 每人流水线独立 |
| `.specpowers/.lock` | 🚫 gitignore | 仅本机有效 |
| `.specpowers/reports/` | 🚫 gitignore | 门禁判定报告本机留痕 |

---

## 本插件自身开销（诚实声明）

借鉴这批 harness 开源项目的共同文化：披露插件自身的成本与能力边界，不做单向宣传。

| 开销项 | 说明 |
|--------|------|
| SessionStart hook | 每次会话启动运行一次依赖检测（Python 子进程，通常亚秒级；Windows 经 run-hook.cmd 包装略有额外开销） |
| 上下文占用 | 技能列表常驻系统提示（v2.4.0 起 11 个技能 ≈ 每会话 ~300 token，description 已按 ≤25 词精简）；SKILL.md 正文按需加载；各阶段 prompts 契约仅在该阶段加载，不常驻对话。auto 模式全流程串行多阶段，token 开销显著高于单阶段使用 |
| 门禁运行成本 | 结构门禁/修改范围比对 = 一次 git diff + 文本解析，毫秒级；真正的成本是**打回/转人工带来的返工轮次**——设计意图是"拦住比返工便宜"，小改动场景可能感到约束 |
| 测试维护 | 清单/契约一致性用例随版本增长，对插件自身的改动自由度是约束，换取升级安全 |

**门禁覆盖边界**：结构门禁拦的是"无中生有"的**结构变更**（新顶层目录/新依赖类型/新架构层目录）与**越界改动**（超出 tasks.md 修改范围声明），**不拦截**已声明路径内的代码质量缺陷——后者由 specpowers-review 审查与项目自身测试兜底。确定性校验只兜最低底线（如 explore 的设计文档登记只查"已登记"，不查探索质量），实质质量依赖 HARD-GATE 契约引导 + 人工 review 双层。

---

## 升级

已安装旧版本的用户，按安装方式选择升级命令：

### v2.0.0 破坏性变更须知（v1.x 用户必读）

v2.0.0 完成阶段重命名与流程缩减（六阶段 → 五阶段），**旧命令名已移除**（一刀切，无别名）：

| v1.x 命令 | v2.0.0 命令 | 变化 |
|-----------|------------|------|
| `/specpowers-constitution` | `/specpowers-init` | 仅改名（产物仍为 `.specpowers/constitution.md`） |
| `/specpowers-brainstorm` | `/specpowers-explore` | 收口产物改为探索设计文档（`docs/specpowers/design/`），不再直接写 proposal.md |
| `/specpowers-specify` + `/specpowers-plan` | `/specpowers-propose` | **两阶段合并**：一次生成 proposal.md + spec.md + tasks.md 三件套，产物路径不变 |
| `/specpowers-build` | `/specpowers-apply` | 仅改名 |

- facade 子命令同步重命名（`init` / `explore` / `propose` / `apply`），旧子命令已删除
- 旧项目 **`state.json` 自动惰性迁移**（旧阶段名读出即归一，无需 reset，可从断点继续）
- 产物落盘路径与 v1.x 完全一致（`openspec/changes/<feature>/` 三件套 + `.specpowers/` 固定产物）

### 插件市场方式（ZCode / Claude Code / WorkBuddy）

```bash
# 1. 刷新市场源（重新拉取 GitHub 上的最新插件内容）
/plugin marketplace update specpowers-marketplace

# 2. 重装插件
/plugin install specpowers
```

> 若 install 提示"已安装"而未更新，先卸载再装：`/plugin uninstall specpowers` → `/plugin install specpowers`。

Codex CLI 对应（升级市场源后，在插件面板重新安装/刷新 specpowers）：

```bash
codex plugin marketplace upgrade specpowers-marketplace
```

### pip 方式（Cursor / Copilot / Windsurf 等）

```bash
pip install --upgrade git+https://github.com/john-weiwei/SpecPowers.git@v2.7.0

# 验证
specpowers --version
# → SpecPowers CLI v2.7.0

# 已用 pip 初始化过的项目建议重装刷新技能与 AGENTS.md 引导段（命令名已全部更新）
cd my-project
specpowers init --force
```

### 版本变更记录

| 版本 | 变更内容 |
|------|---------|
| v2.7.0 | **迭代轮简易设计文档（省 token）+ 会话粘滞（软粘滞）**：① 迭代轮不再「覆盖重写基线设计文档 + 追加迭代历史 + 重新 record-design-doc」（每轮重读重写整份文档且逐轮膨胀，token 消耗大头），改为**基线设计文档冻结不动**（`state.design_doc` 永远指向首轮文档、迭代轮不再重新登记，propose 门禁天然满足），方案变更轮新落简易设计文档 `openspec/changes/<feature>/design-round-<N>.md`（N=iteration_count 路径确定性推导，固定四节：本轮输入/方案对比（仅当分叉）/详细设计变更点（仅变化项）/修改范围增量；随 change 归档整体进 archive/ 保留设计演进链）；② propose 迭代轮读取清单锁死（现有 proposal.md + 最新 design-round-<N>.md，基线仅按需局部查阅、禁止整份重读）——设计文档唯一下游消费者是 propose（apply 读三件套、review 读 git diff、archive 不读设计文档），读侧不增反降、写侧大幅节省且不随轮次膨胀；③ 三件套增量规则（proposal 覆盖+迭代历史/spec 增量修订/tasks 分轮演进）完全不动；CLI/确定性层零改动；④ 会话粘滞——对话加载过任一 specpowers 技能且需求未归档时，后续消息默认先做相关性判定（六级规则：流程指令→结构化锚点→语义重叠→明显新需求→都不中→拿不准一律按相关），相关走流程/无关照常回答+末尾一行活跃需求提醒/新需求提示先归档，解除条件=归档或 reset（对话结束宿主侧不可观测，如实以磁盘状态为界；判定零额外读取、每条消息独立判定、确定性层状态机仍是最终防线）；⑤ 逐轮锚点行注入——`facade sticky-note` 子命令 + `resume_probe.sticky_note`（feature/stage/Round + capability + 修改范围前缀，本地文件 IO 零 LLM token，缺工件降级简版，零活跃零输出）+ hooks.json 注册 UserPromptSubmit 调新脚本 `hooks/session-sticky`（复用 check-deps 项目根定位与 bin 包装范式，失败静默 exit 0）；WorkBuddy/pip 形态无 hook 机制，靠主技能 SKILL.md「会话粘滞」小节条款 + 5 个流水线薄入口粘滞行覆盖；⑥ 测试新增 17 用例（sticky_note 9 + sticky-note 子命令 3 + design-round/粘滞/hooks 防回潮锚点 5），用例数同步 328 |
| v2.6.0 | **任意 agent 工具通用接入（零枚举化）**：① 定位句去枚举化——7 个契约技能与主技能 SKILL.md 的插件根变量表述从封闭端清单改为「模式 + 举例」（`*_PLUGIN_ROOT` 形态，如 ZCode/Claude/WorkBuddy 等，新工具同理），新 agent 工具无需再改技能正文；② 安装器 `--skills-root <路径>` 参数——与 `--integration` 互斥，任意不在七种内置集成之列的工具一步接入（11 技能整目录落位 + AGENTS.md 引导段），零代码改动；③ AGENTS.md 引导段默认生成（幂等标记段 `<!-- specpowers:begin/end -->`，重装整段替换、段前段后用户内容保留）——AGENTS.md 是跨工具事实标准，对不读取 skills 目录的规则驱动型工具是模型发现入口的唯一途径，同时兑现文档长期宣称的"pip 生成 rules 文件"（修正 README/GETTING-STARTED/pyproject 共 11 处陈旧表述为"复制技能目录 + 写入 AGENTS.md 引导段"）；④ `facade locate` 自描述命令——输出 JSON 报告 CLI 包路径、候选 skills 目录（插件市场/源码树与 pip 两形态自动探测）、技能清单、探索契约存在性、bin 包装脚本路径，模型在任何工具里执行一次即完成自定位，不依赖宿主环境变量与项目状态；⑤ 支持平台表补「其他任意工具 `--skills-root`」行，测试新增通用接入 5 用例（--skills-root 安装/AGENTS.md 幂等含段后内容保留/互斥报错/locate 源码树报告/locate 免 root）与 `*_PLUGIN_ROOT` 模式锚点防回潮（防回潮成封闭端枚举）；⑥ `to_scenario` 死函数删除——openspec 适配器残留的该函数（无任何调用方/CLI 暴露/契约引用）docstring 自称「brief.md 为 explore 阶段产出」却全库无路径约定，曾诱导模型把 brief.md 写到目标项目根目录（explore 产出实际由设计文档承担，brief.md 从不是注册产物），测试新增防回潮用例，用例数同步 311 |
| v2.5.1 | **跨端契约遵从修复（WorkBuddy 上 explore 不展示方案/连环提问/不落盘设计文档的根因治理）**：① 契约文件定位修复——9 个阶段技能正文统一写明主技能目录真实位置（兄弟目录定位句 + 插件市场 `${PLUGIN_ROOT}` 四端变量含 WorkBuddy `${CODEBUDDY_PLUGIN_ROOT}` + pip 形态 `<skills_root>` 路径示例 + Glob 兜底搜索句），消除裸相对路径 `prompts/<stage>.md` 在不级联加载主技能上下文的宿主上的断链（此前仅 specpowers-init 写明位置）；② explore 硬性产出契约前置——`specpowers-explore` 新增「硬性产出契约（HARD DELIVERABLES）」节，契约文件不可读时四条底线仍成立（静默探索禁止逐个提问循环/方案统一维度对比表+唯一推荐必须展示在对话中/设计文档必须 Write 落盘 `docs/specpowers/design/`/落盘后必须 record-design-doc 登记），并修正正文第 3 步无限定鼓励提问的反向误导措辞（改为"仅不可逆决策在结论后一次性批量提问，默认不打断"）；③ 主技能 CLI fallback 补全——「执行方式」节补 pip 安装形态包装脚本路径（`<skills_root>\specpowers\bin\specpowers.bat`，如 WorkBuddy `.workbuddy\skills\specpowers\bin\`）与 WorkBuddy 变量条目，消除 pip 形态下 `python -m` 失败无 fallback 可循的断点；④ 确定性层增强——check-deps 环境变量兜底链补读 `CODEBUDDY_PLUGIN_ROOT`（为后续 WorkBuddy hooks 实测铺路），record-design-doc 登记 advisory 段头检查（缺「## 方案对比」/「## 详细设计」段头警告不阻断，给空壳文档留可追溯信号，不误伤项目自有设计文档约定）；⑤ **pip 安装器断链修复**——`specpowers init --integration <agent>` 的技能拷贝段仍指向 v2.4.0 已删除的 commands/ 目录（`commands_dir.exists()` 恒为 False 静默跳过），pip 形态下 9 个阶段技能从未被安装（WorkBuddy pip 用户没有任何阶段入口）——改为直接整目录拷贝 `skills/specpowers-*`（9 阶段技能 + 内置 review，与插件市场 11 技能集合一致），删除 commands 时代死代码（`_get_commands_dir`/`_with_skill_name`）；⑥ **bin 包装脚本 cp936 兼容修复**——`specpowers.bat` 的 UTF-8 中文注释在中文 Windows 默认代码页（cp936）下被 cmd 错误解码、命令拆分错乱导致整个脚本无法执行（WorkBuddy 上 CLI fallback 直接崩），全文件改 ASCII-only；⑦ 测试新增防回潮断言（9 技能主技能目录定位锚点 + 7 契约技能 Glob 兜底句 + explore 硬产出锚点）与 advisory 两用例，新建 tests/test_installer.py 安装器产物完整性测试（11 技能集合/定位链闭合/bat ASCII-only），README 补 WorkBuddy CLI 可达性排查指引，用例数同步 305 |
| v2.5.0 | **初始化前置自动补跑（新用户不 init 直接开工不再静默劣化）**：① 5 个流水线薄入口技能（explore/propose/apply/archive/fast）Outline 统一加第 0 步「Init check first」——`.specpowers/constitution.md` 与 `baseline.json` 任一缺失 = 未初始化，告知用户后自动加载 `prompts/init.md` 完整执行 specpowers-init，再带着原输入继续目标技能（auto 编排本就内置 init、baseline/reset/init 为维护或初始化动作不适用）；② 确定性层兜底——dispatcher route 入口新增 `_check_initialized`（位于 transition 校验与锁之前）：未初始化时五阶段命令直接拒绝并给出「Run /specpowers-init first」可执行指引，替代原含糊的 "Valid from stages: ready" 报错（`_handle_fast` 内部 baseline 硬门禁因被统一覆盖而移除）；③ 契约措辞同步——explore.md「stage=init 时提示先跑 init」与 fast_mode.md「缺则拒绝」升级为自动补跑语义，主技能 SKILL.md「执行方式」新增「初始化前置」全局规则；④ 测试新增 route 层未初始化三用例（五阶段拦截给指引 / init·baseline·reset 放行 / 已初始化项目正常进入 transition 校验）与薄入口第 0 步防回潮断言，README/GETTING-STARTED 快速开始补「忘了先 init」说明，用例数同步 298 |
| v2.4.0 | **命令转技能：四端入口统一 + 探索引擎并入 explore 契约**（slash 调用名零破坏，`prompts/` 分层契约与确定性层逻辑零改动）：① 9 条阶段命令全部转为阶段技能（`skills/specpowers-<stage>/`，共 11 个技能），ZCode/Claude/CodeBuddy 三端清单删 `commands` 键，Codex 端从「无命令入口」变为 9 个显式技能直调（四端统一）；技能 description 统一精简为动词开头 ≤25 词（技能列表常驻系统提示的必修课），模型可经 Skill 工具自主调度阶段（auto 编排、resume 探测提示后直接续跑），并按描述语义反向建议入口（说「小改动」建议 fast、说「卡了」建议 reset）；② 探索引擎细则（四步流程/必须做禁止做规则表/方案对比·设计文档·探索结论三模板）内联并入 `prompts/explore.md` 第一步（HARD-GATE 措辞改为「必须完整执行」），删除引擎独立技能目录——11 个技能全部为用户可用入口，无内部单元以技能身份暴露，token 不增反降（省去技能包装开销约 30 行）；③ `prompts/auto.md` 编排第 3 步改为「经 explore 契约（含探索引擎细则）执行」；④ 测试新增阶段技能完整性断言（frontmatter name=目录名/契约引用不断链/无 $ARGUMENTS·handoffs·allowed-tools 残留/description 动词开头）与防回潮断言（commands/ 目录不存在、三端清单无 commands 键、skills/ 目录集合恰 11 个无 -engine 残留、explore.md 引擎细则锚点防误删、插件本体与用户文档无「内置 specpowers-explore 技能」残留表述），README 快速开始强化四入口引导（新用户只需理解一个决策点），README/GETTING-STARTED 用例数同步 294 |
| v2.3.1 | **token 消耗优化（契约分层按需加载，流程与产物零变更）**：① `prompts/auto.md`（30KB→14KB）拆出四份按需加载细则 `prompts/refs/`（迭代轮编排 `auto-iteration.md` / review 编排与归档收口 `auto-review.md` / 完整裁决规则表 `auto-adjudication.md` / explore 停靠 `auto-explore-halt.md`），fresh 主路径只载主契约，主契约保留精简裁决原则与按需加载索引；② review 审查规则唯一来源 `references/review-guidelines.md`（15.6KB→10KB）同样分层——Pass 4 跨文件数据流细则 `dataflow-tracking.md` 命中触发条件才加载、单方法调用链穿透细则 `method-review.md` 仅单方法模式加载、Codex 英文溯源移 `codex-origin.md` 不进执行上下文，review SKILL.md 同步引用；③ 主 SKILL.md（11KB→6KB）瘦身为路由层（合并「三个概念/三个开关」入命令参考、契约文件表一句话化）；④ auto 路径下 propose 优先消费 `auto_base.json` 八要素 `parsed` 字段，不全文重读设计文档（数据流章节仍按需回查）；⑤ 文档新增「省 token 建议」（人工模式推荐阶段间开新会话 + prompt 缓存提示）；⑥ 新增契约分层资源完整性测试（refs/ 与 review references/ 细则防误删 + 主契约引用防断链），README/GETTING-STARTED 用例数同步 286 |
| v2.3.0 | 门禁与续跑双增强（借鉴 Comet 的任务级路径门禁与 resume-probe 机制，落地为本仓库确定性实现）：① apply 结构门禁新增**修改范围比对**——propose 在 tasks.md 顶部注释块声明「修改范围：」路径前缀，gate 输出附 scope 比对结果，越界文件转人工（迭代轮取各轮声明并集，声明缺失 undeclared 兼容旧产物，流水线工件豁免）；② **活跃需求探测（ambient resume）**——SessionStart hook 顺带只读探测未完成流水线 / auto 断点 / 未归档 change，首条回复提示续跑命令，零活跃零噪音（bridge 新增只读子命令 resume-probe，探测绝不写状态、异常静默降级）；③ 修复 bin/specpowers 对 Windows 商店 python3 stub 的误判（command -v 命中假解释器导致包装脚本恒败，改用最小指令验证）；gate 命令新增 git_util.diff_name_only（core.quotepath=off 保中文路径）；④ **archive 场景覆盖核查**（规范即验收标尺）——归档前确定性校验 delta spec 每个 `#### Scenario:` 至少被一个任务的「场景引用」覆盖（新增 archive_auditor.scenario_coverage，宽松匹配防误报，fast 无场景自动跳过，提示不阻断不打回）；⑤ **gate 判定报告落盘**（借鉴 RTK recall 句柄）——有结构信号或越界改动时完整判定 JSON 落盘 `.specpowers/reports/`，输出附 report 句柄路径，人机按路径回查明细；⑥ constitution 模板新增可选「实现倾向」段（借鉴 Ponytail 七层决策阶梯，防过度工程原则可判定化）；⑦ explore/review 契约新增检索工具优先提示（项目已装 codegraph 类检索 MCP 时优先使用，避免盲目 grep） |
| v2.2.2 | 质量加固：Windows 中文编码链路（stdout/子进程显式 UTF-8）、结构门禁 src_patterns 深度对齐 + rename 折叠路径解析、init 幂等语义、锁释放竞态加固 + ctypes 句柄声明、run-hook.cmd 退出码透传 + superpowers 探测路径修正、清单 description 漂移修齐 + 11 项一致性断言、补 LICENSE、init 集成矩阵移除 cline/Aider、测试提速（git 仓库模板化）+ 假测试清理 |
| v2.2.1 | Codex 端图标补全：portable 根清单 interface 补 `logo` 与 `brandColor`（#4F46E5），`.codex-plugin/` 回退清单补齐同构 interface 六字段 |
| v2.2.0 | Codex 宿主清单注册 SessionStart hooks（依赖自动检测 ZCode / Claude Code / Codex 三端生效，Codex 需信任审核）；SKILL.md 修正 PLUGIN_ROOT 变量名 |
| v2.1.0 | 新增内置 `specpowers-review` 代码审查技能（git 上下文收集三模式 / 多 Pass 审查 / P0-P3 分级），auto 模式 review 切换内置引用 |
| v2.0.1 | 去除 specpowers-explore 技能「源 auto-brainstorm」溯源描述 |
| v2.0.0 | **破坏性变更**：六阶段收敛为五阶段（init → explore → propose → apply → archive），旧命令名移除，详见上方须知 |
| v1.3.0 | auto 模式新增需求澄清步骤（五维检查 + 推进深度上限 + 停靠 explore 产出未收敛草案） |
| v1.2.0 | auto 模式多轮迭代：未归档重入即同需求迭代轮（三分判定 + feature 锁定 + 归档收口） |
| v1.1.2 | 安全与健壮性修复 |
| v1.1.1 | specpowers-auto 命令可通过插件更新分发 |
| v1.1.0 | 命令文件统一加 specpowers- 前缀防撞名 |
| v1.0.1 | README 补充升级命令 |
| v1.0.0 | SpecPowers 多平台插件化首发 |

---

## 许可

MIT
