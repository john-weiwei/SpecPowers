---
name: specpowers-review
description: SpecPowers 内置代码审查技能：复刻 Codex 审查逻辑（git 上下文收集 + 完整方法体提取 + 多 Pass 审查 + P0-P3 分级），基分支/未提交/单方法三种模式。用户说"审查我的改动""review 这个 PR""代码审查""按 codex 规则审查"或 auto 模式 review 环节时调用，结论一律中文
allowed-tools:
  - Read
  - Glob
  - Grep
  - Bash
---

# specpowers-review — 代码审查技能（SpecPowers 内置）

> **定位**：复刻 Codex 的代码审查逻辑（提取自 `codex.app.asar`），输出 Codex 同款格式的审查结论，随插件内置分发（无需用户预装）。
> 流水线中承担 auto 模式 build 之后、archive 之前的 review 环节；也可被用户直接点名触发独立审查。
> 审查规则、严重度定义、pass 定义与自检清单的**唯一来源**是 `references/review-guidelines.md`，本文件只定义工作流骨架。**审查结论一律使用中文。**

## 触发方式

| 调用方 | 行为 |
|--------|------|
| `prompts/auto.md` 第 6 步 | auto 模式全流程编排的 review 环节（传基点、滤范围、控 2 轮修复迭代） |
| 用户点名 | 触发词：`/specpowers-review`、`审查我的改动`、`review 这个 PR`、`代码审查`、`按 codex 规则审查`、`Codex review` |

本技能**不产出 SpecPowers 流水线产物**（proposal.md / spec.md / tasks.md），审查结论以中文 Markdown 正文在对话上下文中交付调用方。

## 输入契约

| 输入 | 必需 | 说明 |
|------|------|------|
| 审查目标 | ✅ | 三选一：基准分支（默认仓库默认分支 `main`）/ 工作区未提交改动 / 具体方法（`Class#method`） |
| 基点 SHA | auto 模式传入 | `.specpowers/auto_base.json` 的 `base_commit`（首轮 HEAD，跨轮不变，累计审查） |
| 范围过滤清单 | auto 模式传入 | 本轮有效八要素「修改范围表」，用于过滤变更文件 |

## 工作流

### 第一步 — 确定模式

- **基分支模式**：用户提到 PR、分支或"相对 `BASE` 的改动"，或 auto 模式传入基点 SHA。基准默认取仓库默认分支（探测不到时回退 `main`）。
- **未提交模式**：审查工作区改动（已暂存 + 未暂存 + 未跟踪）。
- **单方法模式**：用户点名具体方法。**必须执行调用链穿透（指南 §七），严禁只审方法体。**

### 第二步 — 收集 git 上下文

```bash
# 基分支模式（--extract-methods 建议默认启用）
python scripts/gather_review_context.py --repo 仓库路径 --base 基准分支 --extract-methods --out 上下文.md

# 基分支模式 + 纳入工作区未提交改动（默认不含）
python scripts/gather_review_context.py --repo 仓库路径 --base 基准分支 --include-worktree --out 上下文.md

# 未提交模式
python scripts/gather_review_context.py --repo 仓库路径 --extract-methods --out 上下文.md

# 单方法模式：自动定位定义、导出方法体、列兄弟方法与一层调用方
python scripts/gather_review_context.py --repo 仓库路径 --method "Class#method" --out 上下文.md
```

> `scripts/` 与 `references/` 相对本 SKILL.md 所在技能目录（`${PLUGIN_ROOT}/skills/specpowers-review/`）解析；
> 流水线契约 `prompts/auto.md` 位于主编排技能目录（`${PLUGIN_ROOT}/skills/specpowers/prompts/`）。

- 支持提取：Java / TS / JS / TSX / JSX（方法体）、Python（函数体）、Mapper XML（完整 SQL 语句块）。
- 超出 `--max-bytes` 预算的文件列入"未包含文件清单"——**必须用 Read 工具补读后再审查**，
  不得只凭截断片段下结论。
- 不启用 `--extract-methods` 时，对嵌套 ≥ 3 层或 `return` ≥ 2 个的方法必须手动 `Read` 完整方法体。
- 上下文包 `--out` 输出到系统临时目录（如 `$TMPDIR/specpowers-review-context.md`），审查完成后可删除，避免在目标仓库落下杂物文件。
- 若调用方传入范围过滤清单（auto 模式八要素「修改范围表」），仅对清单内文件执行审查；
  清单外文件的变更在报告中注明「范围外，未审查」。

### 第三步 — 按指南执行多 pass 审查

将 `references/review-guidelines.md` 载入上下文，按其章节执行：

1. **比例原则**（指南 §四）：小改动走快速通道；大变更先分诊（跳过生成代码 / dist / target / lock 等）。
2. **Pass 1 模式匹配**（必须）→ **Pass 2 控制流追踪**（必须）→ **Pass 3 语义验证**（建议）→
   **Pass 4 跨文件数据流**（命中触发条件时必须）。
3. **单方法模式**：以 `--method` 输出为起点，按指南 §七构建调用图并穿透缓存 / DB 触达点；
   默认深度上限 3 层。
4. **自检清单**（指南 §5.5 / §6.4 / §7.5）必须随报告输出；快速通道可合并为一行"触发条件未命中"说明。

### 输出要求

- 普通 Markdown 中文正文；不要 JSON / XML / 结构化 findings。
- 严重度标签 `[P0]` / `[P1]` / `[P2]` / `[P3]`，定义见指南 §三。
- 应用六条判定标准（指南 §一）；**宁可"没有问题"，不给推测性或低价值反馈**。
- 正文点名文件 / 行 / 函数；无可操作问题时简要说明。

## 边界情况

- 截断：以"未包含文件清单"为准，用 Read 工具补读；必要时可重跑 `git diff {合并基点}`。
- 未跟踪文件以完整内容纳入上下文包（受预算约束，超预算列入清单）。
- 规则细节一律以 `references/review-guidelines.md` 为准；设计动机与历史漏检复盘见 `readme.md`。

## 与流水线的衔接

```
本技能（specpowers-review）
  输入：基点 SHA（auto_base.json）+ 范围过滤清单（八要素修改范围表）
  输出：中文审查正文（[P0]-[P3] 标签 + 各 Pass 发现 + 自检清单）
  衔接方式：返回调用方 prompts/auto.md 第 6 步
      ↓
auto.md 第 6 步编排
  职责：传基点（首轮 HEAD 跨轮累计）→ 滤范围（只审修改范围表内文件）
        → 控迭代（P1/P2 修复最多 2 轮复审）→ 收口前置检查（blocking P1/P2 未收敛不归档）
      ↓
/specpowers-archive（--archive 显式收口后才执行）
```

接口耦合面（调用方依赖的四处约定，本技能变更任一项需同步 `prompts/auto.md`）：
技能名 `specpowers-review`、脚本 `gather_review_context.py` 的 `--base`/`--extract-methods` 参数、
严重度标签 `[P1]`/`[P2]`、中文输出约定。

## 资源

- `scripts/gather_review_context.py` — git 上下文收集（基分支 / 未提交 / 单方法），
  按 diff 对应版本提取方法体，支持 Java / TS / JS / Python / Mapper XML
- `references/review-guidelines.md` — 审查规则唯一来源（判定标准 / pass 定义 / 自检清单 / 严重度 / 比例原则）
- `scripts/tests/` — 回归测试（`python -m unittest discover -s scripts/tests`，在技能目录下执行）
- `readme.md` — 使用说明与设计复盘
