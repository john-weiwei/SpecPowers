---
name: specpowers
description: 桥接编排插件 — 在 OpenSpec + superpowers 之上叠加结构一致性门禁与实时卡转人工，五阶段流水线（init→explore→propose→apply→archive）+ 无人值守模式 + 优化模式
version: 2.0.1
---

# SpecPowers 桥接插件

> **定位**：薄桥接层（Facade + Adapter + Dispatcher），不重写任何框架引擎。只复用 OpenSpec + superpowers 原生能力，补上两条它们都没有的硬约束：**结构一致性门禁**、**实时卡转人工**。
> **v2.0.0 阶段重命名**：constitution→init、brainstorm→explore、build→apply；specify+plan 合并为 **propose**（一站式生成 proposal/spec/tasks 三件套，存储路径不变）。产物落盘路径与 v1.x 完全一致，旧项目 state.json 自动惰性迁移。

## ⚠️ 前置依赖（必装）

本插件是**桥接层**，编排以下外部能力。安装本插件前请先就绪：

| 依赖 | 类型 | 用在哪 | 安装方式 |
|------|------|--------|---------|
| **OpenSpec CLI** | 命令行工具 | archive 阶段归档（强依赖，不可用则拒绝归档） | `npm install -g @funneler/openspec` 或见 [openspec 官方](https://github.com/funneler/openspec) |
| **superpowers 插件** | agent skill 包 | propose(`writing-plans`)/apply(`executing-plans`、`using-git-worktrees`、`subagent-driven-development`、`test-driven-development`)。explore 阶段用**内置** `specpowers-explore` 技能（`skills/specpowers-explore/`，随插件分发） | `/plugin install superpowers`（ZCode/Claude 内置市场） |

**自动检测**：本插件内置 SessionStart hook，会话启动时（startup/clear/compact）自动检测上述依赖。若缺失，agent 会在首条回复中提示你安装方法——无需手动检查。

手动确认（可选）：
```bash
openspec --version          # OpenSpec CLI 可用性
```
superpowers 插件是否启用，在 agent 的插件管理界面查看。

> 若未安装 superpowers，propose/apply 阶段的规划、执行能力会降级为提示词引导（无原生 skill 加持）；explore 阶段用内置 `specpowers-explore` 技能，不受影响；若未安装 OpenSpec CLI，仅 archive 阶段会拒绝执行，其余阶段正常。

## 三个概念

| 概念 | 说明 |
|------|------|
| ① 项目原则 | `/specpowers-init` — 生成 constitution.md（质量/测试/UX/性能 四类原则）+ 扫描结构基线 |
| ② 特性流水线 | `/specpowers-explore` → `/specpowers-propose` → `/specpowers-apply` → `/specpowers-archive` 五阶段；归档前需要调整时，直接重入 `/specpowers-propose`（场景调整）或 `/specpowers-explore`（方案变更）——经确认自动开同一需求的新迭代轮（调整落在当前 spec 文件内），归档即新需求 |
| ③ 收尾 | `/specpowers-archive` — 常规/优化统一调 openspec archive 做 delta 合并；只归档，不提交代码 |

## 三个开关

| 开关 | 说明 |
|------|------|
| ① 无人值守模式 | `/specpowers-auto "<设计文档路径>"` — 以设计文档为唯一权威输入，五阶段直通 codex-review，**任何轮次默认都不归档**（`--archive` 或手动 `/specpowers-archive` 显式收口）；所有确认/门禁节点自动裁决，仅硬阻断才停；支持断点续跑。**多轮迭代**：归档前重入（新文档/原文档/口头指令）都是同一需求的新迭代轮，调整落在当前 spec 文件内；归档即新需求 |
| ② 优化模式 | `/specpowers-fast` — 判小跳 explore/propose，直进 apply |
| ③ 基线刷新 | `/specpowers-baseline` — 手动重扫结构基线 |

---

## 流水线总览

```
init ─▶ ready ─┬─(explore)───▶ explore ─▶ propose ─▶ apply ─▶ archive ─▶ ready
               ├─(propose)─────────────▶ propose ─▶ apply ─▶ archive ─▶ ready
               ├─(auto)───无人值守驱动上述阶段（含 codex-review，默认不归档）──▶ ready
               ├─(fast)──▶(用户编码)──▶ apply ─▶ archive ─▶ ready
               └─(迭代重入)──▶ 归档前任意阶段重入 /specpowers-propose 或 /specpowers-explore，
                              确认后受控回 propose，feature 锁定不变，
                              spec 增量修订 + tasks 分轮演进（多轮迭代）
```

**propose 一站式三件套**（v2.0.0 合并原 specify+plan，存储路径不变）：

| 产物 | 路径 | 来源 |
|------|------|------|
| proposal.md | `openspec/changes/<feature>/proposal.md` | 从 explore 设计文档提炼（含「## 数据流契约」） |
| spec.md | `openspec/changes/<feature>/specs/<capability>/spec.md` | OpenSpec delta 格式 |
| tasks.md | `openspec/changes/<feature>/tasks.md` | writing-plans 瘦身 |

---

## 命令参考

| 命令 | 参数 | 合法 from_stage | 说明 |
|------|------|----------------|------|
| `/specpowers-init` | `[--force]` | init / 任意(需确认) | 生成原则 + 扫基线 |
| `/specpowers-explore` | `"<需求>"` | ready；propose/apply 重入=迭代轮确认（方案变更路径） | 探索 + 设计文档落盘 + `record-design-doc` 登记；未归档重入经确认开同需求新迭代轮 |
| `/specpowers-propose` | `"<需求>"` | explore / ready / apply(fallback) / propose(迭代续作)；apply 重入=迭代轮确认（场景调整路径） | 一站式生成 proposal.md + spec.md + tasks.md；未归档重入经确认开同需求新迭代轮 |
| `/specpowers-auto` | `"<设计文档路径>" [--instruction "<调整描述>"] [--archive] [--new-round]` | fresh 首轮 ready；任意活跃状态可重入（三分判定 fresh/resume/iterate） | 全流程无人值守：init→…→apply→codex-review，**默认不归档**（`--archive` 显式收口，先过收口前置检查），确认/门禁节点自动裁决，仅硬阻断才停，重入续跑；归档前重入为同需求迭代轮（feature 锁定、spec 增量修订、tasks 分轮演进），归档即新需求 |
| `/specpowers-fast` | `"<需求>"` | ready | 声明优化模式 |
| `/specpowers-apply` | — | propose / ready(fast) | 执行构建 + 门禁 |
| `/specpowers-archive` | `[--force-merge-check]` | apply | 收尾归档（归档即宣告新需求，迭代计数清零） |
| `/specpowers-baseline` | — | 任意 | 手动刷新基线 |
| `/specpowers-reset` | — | 任意 | 重置 state+lock |

---

## 执行方式

所有阶段命令先调用确定性层获取状态/校验，再加载对应 `prompts/` 契约执行认知任务：

```bash
python -m specpowers_cli.bridge.facade <subcommand> [--root <path>] [options]
```

**插件内 bridge 包定位**：本插件把 `specpowers_cli` 包内嵌在 `${PLUGIN_ROOT}/scripts/` 下。若 `python -m specpowers_cli.bridge.facade` 直接执行失败（包未 pip 安装），改用插件内的包装脚本，它会自动设置 PYTHONPATH：

```bash
# Linux/macOS
${PLUGIN_ROOT}/scripts/specpowers_cli/bin/specpowers <subcommand> [--root <path>] [options]
# Windows
%PLUGIN_ROOT%\scripts\specpowers_cli\bin\specpowers.bat <subcommand> [--root <path>] [options]
```

> `PLUGIN_ROOT` 在 ZCode 为 `${ZCODE_PLUGIN_ROOT}`、Claude Code 为 `${CLAUDE_PLUGIN_ROOT}`、Codex 为 `${CODEX_PLUGIN_ROOT}`，按当前运行环境替换。

**自动读取契约强制**：每个阶段开始前，Dispatcher 自动校验本阶段必读上游产物是否存在。缺必读 → 拒绝开工。v2.0.0 防架空链：propose 从 explore 进入时校验设计文档已登记（`record-design-doc`）；apply 入口校验 proposal 含「## 数据流契约」段头。

---

## 契约文件

| 文件 | 职责 |
|------|------|
| `prompts/init.md` | 内联生成 constitution.md（4 类原则）；不调外部技能；不承载结构规则 |
| `templates/constitution-template.md` | constitution 生成模板（四类原则骨架，填入质量/测试/UX/性能 4 类原则） |
| `prompts/explore.md` | 收口契约：HARD-GATE 强制调用内置 specpowers-explore 技能探索（防架空）+ 运行时数据流溯源（结论写设计文档数据流章节）+ 设计文档落盘 + `record-design-doc` 登记；判小信号映射 |
| `skills/specpowers-explore/SKILL.md` | 内置需求探索技能（替代 superpowers `brainstorming`）：静默项目探索 → 2-3 方案统一维度对比 → 唯一推荐 → 设计文档落盘（`docs/specpowers/design/`，含架构/组件划分/数据流/接口定义/错误处理）→ 结构化探索结论交付（含跨链路字段线索）；不写流水线产物 |
| `prompts/propose.md` | 提案契约（合并原 specify+plan）：从设计文档提炼 proposal.md（含「## 数据流契约」）+ OpenSpec 场景格式 spec.md + writing-plans 瘦身 tasks.md（conductor/subagent 档字段），一次落盘三件套 |
| `prompts/apply.md` | 实时门禁三态 + 能力池调度 + 验收清单消费 |
| `prompts/archive.md` | 三职责收尾；合体后校验 |
| `prompts/fast_mode.md` | 判小 prompt / 确认交互 / 回退 / 清单 |
| `prompts/auto.md` | 无人值守契约：八要素文档解析 + 重入三分判定（fresh/resume/iterate，`facade auto-status` 确定性支撑）+ 迭代深度分级（full/light）+ 阶段编排 0–7（第 7 步仅 `--archive` 触发）+ 裁决规则表 + codex-review 编排（首轮基点跨轮累计审查/传基点/滤范围/控 2 轮迭代）+ 归档双通道收口（`facade auto new-round` 轮次切换）+ 硬阻断定义 + 断点续跑 |
| `templates/auto-summary-template.md` | auto 模式汇总报告模板（产物/文件清单/审查结论/编译测试/裁决日志/遗留风险） |

---

## 安全底线

- 所有用户输入参数化传递，禁止拼入 shell 命令字符串
- git 操作使用参数列表调用 subprocess（bridge/core/git_util.py）
- `.specpowers/state.json` 原子写（临时文件 + rename）
- `.specpowers/.lock` 防重入，含死锁检测

## 团队协作

- `baseline.json` → 提交 git（团队共享基线）
- `state.json` / `.lock` → `.gitignore`（个人本地）
