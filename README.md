# SpecPowers

> 桥接编排插件 — 在 OpenSpec + superpowers 之上叠加**结构一致性门禁**与**实时卡转人工**。

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Version](https://img.shields.io/badge/version-1.0.1-blue)]()

SpecPowers 是一个通用 AI 编码 agent 插件。它不重写任何框架引擎，只编排 OpenSpec、superpowers 两套框架的原生能力，补上它们都没有的两条硬约束：

- **结构一致性门禁** — AI 写代码不能"无中生有"建目录/加依赖
- **实时卡转人工** — 遇到不确定性立刻暂停等人工判定，不静默跳过

---

## 安装

### 方式一：插件市场（推荐 —— ZCode / Claude Code / Codex）

三家的插件结构同构，本仓库已内置三份清单（`.zcode-plugin/`、`.claude-plugin/`、`.codex-plugin/`）。把本仓库添加为插件市场源后一行安装：

```bash
# ZCode / Claude Code
/plugin marketplace add https://github.com/john-weiwei/SpecPowers
/plugin install specpowers

# Codex CLI
codex plugin marketplace add https://github.com/john-weiwei/SpecPowers
codex plugin install specpowers
```

插件内嵌 `specpowers_cli` bridge 包（仅依赖 Python ≥ 3.11 标准库）。安装后无需 `init`，直接用 `/specpowers-constitution` 开始。

### 方式二：pip（Cursor / Copilot / Windsurf / Cline / Aider 等无插件市场的工具）

这些工具不支持插件市场，需通过 pip 安装并在项目里初始化（自动生成对应 rules 文件）：

```bash
# 安装
pip install git+https://github.com/john-weiwei/SpecPowers.git@v1.0.1
# 或本地开发：cd 进仓库目录后 pip install -e .

# 验证
specpowers --version
# → SpecPowers CLI v1.0.1

# 在目标项目里初始化（自动检测 agent 类型）
cd my-project
specpowers init                        # 自动检测 AI agent
specpowers init --integration cursor   # 或指定：cursor/copilot/windsurf/cline/codex/zcode/claude
```

**运行依赖**：Python ≥ 3.11（仅 stdlib，零 pip 依赖）、Git ≥ 2.30。

## 升级

已安装旧版本的用户，按安装方式选择升级命令：

### 插件市场方式（ZCode / Claude Code）

```bash
# 1. 刷新市场源（重新拉取 GitHub 上的最新插件内容）
/plugin marketplace update specpowers-marketplace

# 2. 重装插件
/plugin install specpowers
```

> 若 install 提示"已安装"而未更新，先卸载再装：`/plugin uninstall specpowers` → `/plugin install specpowers`。

Codex CLI 对应：

```bash
codex plugin marketplace update specpowers-marketplace
codex plugin install specpowers
```

### pip 方式（Cursor / Copilot / Windsurf / Cline 等）

```bash
pip install --upgrade git+https://github.com/john-weiwei/SpecPowers.git@v1.0.1

# 验证
specpowers --version
# → SpecPowers CLI v1.0.1
```

## 前置编排依赖（重要）

SpecPowers 是**桥接层**，编排以下外部能力。安装本插件前请先就绪：

| 依赖 | 类型 | 影响阶段 | 必需性 | 安装方式 |
|------|------|---------|--------|---------|
| **OpenSpec CLI** | 命令行工具 | archive（归档） | 必需 | `npm install -g @funneler/openspec` |
| **superpowers 插件** | agent skill 包 | brainstorm / plan / build | 推荐 | `/plugin install superpowers` |

**自动检测**：插件内置 SessionStart hook，会话启动时自动检测上述依赖，缺失会在首条回复中提示安装方法——无需手动检查。

手动确认（可选）：
```bash
openspec --version          # OpenSpec CLI 可用性
# superpowers 插件在 agent 的插件管理界面查看
```

> - 未装 OpenSpec CLI：仅 archive 阶段会拒绝执行（提示安装），其余阶段正常。
> - 未装 superpowers：brainstorm/plan/build 会降级为纯提示词引导（无原生 skill 加持），功能可用但体验打折。

---

## 快速开始

### 1. 生成项目原则 + 基线（每个项目一次性）

```
/specpowers-constitution
```

agent 自动读取 `templates/constitution-template.md` 内联生成 `.specpowers/constitution.md`（插件自包含，无需外部依赖），并扫描项目结构生成 `.specpowers/baseline.json`。

> pip 方式用户需先在项目里跑 `specpowers init`（见上方"安装 → 方式二"）；插件市场用户装好插件即可直接用本命令。

### 2. 启动特性开发

| 场景 | 命令 |
|------|------|
| 需要探索 | `/specpowers-brainstorm "需求"` |
| 直接开写 | `/specpowers-specify "需求"` |
| 小改动 | `/specpowers-fast "需求"` |
| 已有定稿设计文档，全流程自动 | `/specpowers-auto "设计文档路径"` |

### 3. 收尾

```
/specpowers-archive
```

### 4. 归档前调整需求（多轮迭代）

**归档前，所有调整都视为同一个需求的新迭代轮**，记录进当前 change 目录的同一个 spec 文件；归档即宣告需求终结、开启全新需求：

- **人工模式**：直接重入 `/specpowers-specify "调整描述"`（场景/范围调整）或 `/specpowers-brainstorm`（方案变更）——识别到未归档的活跃需求时会与你确认开启新迭代轮，feature 锁定不变，spec 增量修订、tasks 分轮演进（已完成任务保留、被调整作废的任务留痕）
- **auto 模式**：重入 `/specpowers-auto`（新文档 / 原文档 / `--instruction "口头调整"`），自动三分判定全新（fresh）/ 续跑（resume）/ 迭代轮（iterate）

> 注意：想开**全新需求**但当前需求未归档时，请先 `/specpowers-archive` 归档或 `/specpowers-reset` 重置——未归档的活跃需求会接管 auto 的新文档输入，将其判定为旧需求的迭代轮（需求身份由归档状态唯一决定）。

---

## 流水线

```
constitution → ready ─┬─ brainstorm → specify → plan → build → archive → ready
                     ├─ specify ────→ plan → build → archive → ready
                     ├─ auto ─── 无人值守依次驱动上述全部阶段（含 codex-review）──→ ready
                     ├─ fast → 用户编码 → build → archive → ready
                     └─ 迭代重入 ─→ 归档前任意阶段重入 specify/brainstorm（或 auto 重入），
                                    确认后受控回 specify：feature 锁定不变，
                                    spec 增量修订 + tasks 分轮演进（归档即新需求）
```

### 阶段命令详解

| 命令 | 依赖 | 做什么 | 产物 |
|------|------|--------|------|
| `/specpowers-constitution` | — | 内联生成项目原则（质量/测试/UX/性能，插件自包含），同时扫描顶层目录、依赖清单、源码目录规律 → 结构基线 | `.specpowers/constitution.md` + `.specpowers/baseline.json` |
| `/specpowers-brainstorm "需求"` | constitution | 调 superpowers 的 `brainstorming` 探索需求，提出方案并对比优劣，最终产出一份结构化决策摘要；未归档重入=同需求方案变更迭代轮（经确认开轮，proposal 覆盖更新 + 迭代历史） | `openspec/changes/<feature>/proposal.md` |
| `/specpowers-specify "需求"` | brainstorm（或 ready） | 读取 proposal.md（如有）和 constitution.md，用 OpenSpec 场景格式描述要构建什么，定义可测试的验收条件；未归档重入=同需求场景调整迭代轮（经确认开轮，spec 增量修订） | `openspec/changes/<feature>/specs/<capability>/spec.md` |
| `/specpowers-plan` | specify | 调 superpowers 的 `writing-plans`，将 spec.md 拆成可执行任务列表，并声明本特性适合哪种执行方式（conductor 顺序执行 / worktree 隔离 / subagent 并行 / TDD 测试驱动） | `openspec/changes/<feature>/tasks.md` |
| `/specpowers-build` | plan（或 ready+fast） | ① 提示用户选择执行方式（conductor/worktree/subagent/TDD）；② 结构门禁：比对 git diff 与 baseline.json，三态判定（通过/转人工/打回）；③ 调用 superpowers 能力池执行编码 | 代码变更 |
| `/specpowers-archive` | build | 三职责收尾：原则核查（constitution 合规）→ 产物标记 → 合体后校验（多分支合并时检查结构一致性）。full 与 fast 统一走 `openspec archive`（强依赖 openspec CLI），合并 delta 到主规格 + change 快照归档 | `openspec/specs/<feature>/spec.md`（主规格）+ `openspec/changes/archive/`（快照） |
| `/specpowers-fast "需求"` | constitution | 优化模式入口：agent 判定需求是否为“小改动”（bugfix/单文件/纯配置/纯文案/纯重构），确认后跳过 brainstorm/specify/plan，直接编码 → build → archive | 验收清单 3-5 条 |
| `/specpowers-auto "设计文档路径"` | ready（fresh 首轮；任意活跃状态可重入，三分判定 fresh/resume/iterate） | 无人值守模式入口：以设计文档为唯一权威输入，解析八要素（功能名/方案/调用链/必测场景/修改范围/编码约束/降级策略/硬性边界）后依次驱动 constitution → brainstorm → specify → plan → build → codex-review → archive；所有确认/门禁节点自动裁决并留痕，review 修复最多 2 轮，仅硬阻断才停；中断后重入即续跑；**归档前重入（新文档/原文档/口头指令）都是同一需求的新迭代轮**（feature 锁定、spec 增量修订、tasks 分轮演进），归档即新需求 | 汇总报告（产物清单/审查结论/编译测试/遗留风险） |
| `/specpowers-baseline` | — | 手动刷新结构基线，重新扫描项目顶层目录/依赖/源码规律 → 覆盖 `baseline.json` | 更新 `baseline.json` |
| `/specpowers-reset` | — | 重置流水线状态：清除 `state.json` 和 `.lock`，回到 `ready` 重新开始（不丢 baseline） | — |

### 四条路径对比

| | 常规（full） | 跳过探索 | 无人值守（auto） | 优化（fast） |
|---|---|---|---|---|
| **入口** | `/specpowers-brainstorm` | `/specpowers-specify` | `/specpowers-auto "设计文档路径"` | `/specpowers-fast` |
| **适用** | 新特性，需求待梳理 | 需求已清晰 | 已有定稿设计文档，全程无需人工介入 | bugfix、单文件、纯配置/文案/重构 |
| **阶段** | brainstorm → specify → plan → build → archive | specify → plan → build → archive | constitution → … → build → codex-review → archive | 用户编码 → build → archive |
| **产物** | proposal + delta spec + tasks | delta spec + tasks | 全套产物 + 汇总报告 | 验收清单(delta spec) + 主规格合并 |
| **能力池** | 全部可用 | 全部可用 | 全部可用 | 仅 TDD（禁 worktree/subagent） |
| **回退** | — | — | 硬阻断停下后重入续跑；归档前重入=同需求迭代轮 | 可升级为完整流程（1 次） |

### build 阶段详解

build 是流水线的**执行核心**，组合了两件事：

**1. 结构门禁（SpecPowers 独有）**

比对 `git diff` 与 `baseline.json`，发现 AI 代码"无中生有"建目录/加依赖时，三态判定：

| 判定 | 触发条件 | 行为 |
|------|---------|------|
| ✅ 通过 | 改动在已知结构内 | 继续执行 |
| ⚠️ 转人工 | 新建目录/新依赖类型/新模式 | 标记，archive 时人工确认 |
| ❌ 打回 | 明显结构违规 | 拒绝继续 |

**2. 能力池调度（superpowers）**

根据 plan.md 的建议，build 启动时提示用户选择执行方式，然后调用对应的 superpowers 技能：

| 执行方式 | superpowers 技能 | 说明 |
|---------|-----------------|------|
| conductor | `executing-plans` | 顺序执行所有任务（默认） |
| worktree | `using-git-worktrees` | 隔离工作区并行开发 |
| subagent | `subagent-driven-development` | 每个任务一个 AI 子代理 |
| TDD | `test-driven-development` | 红-绿-重构循环 |

> plan.md 给出推荐方式，用户最终选择。fast 模式禁 worktree/subagent。

---

## 支持平台

SpecPowers 支持两类安装方式，按你的 agent 选择：

| Agent | 安装方式 | 命令调用 |
|-------|---------|---------|
| **ZCode** | 插件市场（推荐） | `/specpowers:specpowers-constitution` 或 `/specpowers-constitution` |
| **Claude Code** | 插件市场（推荐） | `/specpowers:specpowers-constitution` 或 `/specpowers-constitution` |
| **Codex CLI** | 插件市场（推荐） | skill 自动激活（Codex 无自定义 slash 命令） |
| Cursor | pip + `specpowers init --integration cursor` | 自然语言触发（rules 引导） |
| GitHub Copilot | pip + `specpowers init --integration copilot` | 自然语言触发（rules 引导） |
| Windsurf | pip + `specpowers init --integration windsurf` | 自然语言触发（rules 引导） |
| Cline | pip + `specpowers init --integration cline` | 自然语言触发（rules 引导） |
| WorkBuddy | pip + `specpowers init --integration workbuddy` | 自然语言触发（rules 引导） |

> 插件市场方式享受完整体验（9 个 slash 命令 + SessionStart 依赖检测）；pip 方式生成 rules 文件引导 agent 按流水线执行，功能等价但无原生 slash 命令。

## 架构

```
┌──────────────────────────────────────┐
│  认知层 (SKILL.md + 7 prompts/)      │  ← agent 加载执行
│  constitution / brainstorm /         │
│  specify / plan / build / archive    │
├──────────────────────────────────────┤
│  确定性层 (Python, 仅 stdlib)        │  ← skill 通过 Bash 调用
│  facade → dispatcher                 │
│  ├─ modules/ (扫描/门禁/审计)        │
│  ├─ adapters/ (OpenSpec)             │
│  └─ core/ (git/lock/state/platform)  │
└──────────────────────────────────────┘
```

- **认知层**：纯 Markdown 指令集，作为 skill 插件被 agent 加载
- **确定性层**：Python 内部 helper，执行基线扫描、状态机、文件锁、git 操作等确定逻辑

---

## 项目结构

```
specpowers/
├── marketplace.json             ← 插件市场入口清单
├── pyproject.toml               ← 包配置（pip 安装场景）
├── plugins/
│   └── specpowers/              ← 插件根（三平台共用）
│       ├── .zcode-plugin/plugin.json     ← ZCode 清单
│       ├── .claude-plugin/plugin.json    ← Claude Code 清单
│       ├── .codex-plugin/plugin.json     ← Codex 清单
│       ├── commands/            ← 9 个 slash 命令（带 specpowers- 前缀防撞名）
│       │   ├── specpowers-constitution.md
│       │   ├── specpowers-brainstorm.md
│       │   └── … (specpowers-specify/plan/build/archive/fast/baseline/reset)
│       ├── skills/specpowers/   ← 主编排 skill
│       │   ├── SKILL.md
│       │   ├── prompts/         ← 7 个阶段契约
│       │   └── templates/       ← constitution 生成模板
│       └── scripts/specpowers_cli/  ← 内嵌 Python bridge 包
│           ├── main.py          ← specpowers init 安装器
│           ├── bridge/          ← 确定性执行层
│           │   ├── facade.py
│           │   ├── dispatcher.py
│           │   ├── core/        ← git_util / lock / fs_state / platform / errors
│           │   ├── modules/     ← baseline_scanner / structure_gate / …
│           │   └── adapters/    ← openspec
│           └── bin/             ← shell 包装脚本（自动定位包）
├── tests/                       ← 测试套件（132 用例）
```

---

## 团队协作

| 文件 | Git 策略 | 说明 |
|------|---------|------|
| `openspec/changes/<feature>/proposal.md` | ✅ 提交 | brief（设计决策摘要），团队可见 |
| `openspec/changes/<feature>/specs/<capability>/spec.md` | ✅ 提交 | spec（场景 + 验收条件），团队可见 |
| `openspec/changes/<feature>/tasks.md` | ✅ 提交 | tasks（可执行任务列表），团队可见 |
| `.specpowers/constitution.md` | ✅ 提交 | 项目原则全员一致 |
| `.specpowers/baseline.json` | ✅ 提交 | 团队共享结构基线 |
| `.specpowers/state.json` | 🚫 gitignore | 每人流水线独立 |
| `.specpowers/.lock` | 🚫 gitignore | 仅本机有效 |

---

## 许可

MIT
