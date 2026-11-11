---
name: specpowers
description: 桥接编排插件 — 在 OpenSpec + superpowers 之上叠加结构一致性门禁与实时卡转人工，五阶段流水线（init→explore→propose→apply→archive）+ 无人值守模式 + 优化模式
version: 2.7.0
---

# SpecPowers 桥接插件

> **定位**：薄桥接层（Facade + Adapter + Dispatcher），不重写任何框架引擎。只复用 OpenSpec + superpowers 原生能力，补上两条它们都没有的硬约束：**结构一致性门禁**、**实时卡转人工**。
> **v2.0.0 阶段重命名**：constitution→init、brainstorm→explore、build→apply；specify+plan 合并为 **propose**（一站式三件套，存储路径不变）。旧项目 state.json 自动惰性迁移。

## ⚠️ 前置依赖（必装）

| 依赖 | 用在哪 | 安装方式 |
|------|--------|---------|
| **OpenSpec CLI** | archive 归档（强依赖，不可用则拒绝归档） | `npm install -g @funneler/openspec` |
| **superpowers 插件** | propose（`writing-plans`）/ apply（`executing-plans`、`using-git-worktrees`、`subagent-driven-development`、`test-driven-development`） | `/plugin install superpowers`（ZCode/Claude 内置市场） |

explore 探索引擎内置于 `prompts/explore.md` 契约（第一步 HARD-GATE 强制完整执行，无需预装）、review 审查用**内置** `specpowers-review` 技能（`skills/` 下随插件分发）。SessionStart hook 会在会话启动时（startup/clear/compact）自动检测上述依赖并在首条回复中提示安装方法。降级语义：未装 superpowers → propose/apply 降级为提示词引导（explore/review 不受影响）；未装 OpenSpec CLI → 仅 archive 拒绝执行。

## 流水线总览

```
init ─▶ ready ─┬─(explore)───▶ explore ─▶ propose ─▶ apply ─▶ archive ─▶ ready
               ├─(propose)─────────────▶ propose ─▶ apply ─▶ archive ─▶ ready
               ├─(auto)───无人值守驱动上述阶段（含 review，默认不归档）──▶ ready
               ├─(fast)──▶(用户编码)──▶ apply ─▶ archive ─▶ ready
               └─(迭代重入)──▶ 归档前重入 /specpowers-propose（场景调整）或
                              /specpowers-explore（方案变更）= 同需求新迭代轮，
                              feature 锁定，方案变更轮新落 design-round-<N>
                              简易设计文档（基线冻结不动），spec 增量修订 + tasks 分轮演进
```

propose 一站式生成三件套到 `openspec/changes/<feature>/`：proposal.md（含「## 数据流契约」，apply 硬依赖）+ `specs/<capability>/spec.md`（OpenSpec delta 格式）+ tasks.md（writing-plans 瘦身，顶部含执行方式推荐与「修改范围：」声明）。

> **省 token 建议**：各阶段产物全部落盘（state.json + openspec/changes/），阶段间不依赖对话记忆。人工模式推荐**每阶段完成即开新会话**再触发下一条命令——长会话上下文逐轮累积是 token 消耗主因，新会话只加载当阶段契约；会话启动探测（v2.3.0）会自动提示续跑命令，跨机接管同样支持。`/specpowers-auto` 例外（单会话直通是其设计）。宿主支持 prompt 缓存时，固定的指令前缀可按缓存价计费，避免频繁切换模型。

## 会话粘滞（v2.7.0）

本对话加载过任一 specpowers 技能且项目有活跃需求（`state.json` 的 stage ∈ explore/propose/apply/archive 且 feature 非空，或 fast 模式进行中）时，**后续每条用户消息默认先做相关性判定**，把对话保持在流程语境内（软粘滞，不阻塞正常使用）：

| 消息判定 | 处理 |
|---------|------|
| ① 相关 | 按当前阶段技能/契约处理（未归档调整 = 同需求迭代轮，走重入识别） |
| ② 无关（闲聊/其他任务） | 照常回答，回复**末尾加一行提醒**：当前有活跃需求 \<feature\>（\<stage\>），脱离流程前建议 `/specpowers-archive` 或 `/specpowers-reset` |
| ③ 要开新需求 | 提示先归档（`/specpowers-archive`）或与用户明确并存后再开工 |

**相关性六级判定**（按优先级短路）：

1. 明确流程指令（继续/下一步/验收/归档/重置/迭代/Round N/specpowers-* 入口名）→ 相关
2. 结构化锚点命中：feature 名、capability/Requirement/Scenario 名、Task 编号/标题、「修改范围：」路径前缀、数据流契约的数据源/接口、design-round-\<N\> 章节 → 相关
3. 语义重叠：消息目标改动与当前需求修改范围/场景语义重叠 → 相关
4. 明显新需求（新能力目标、与当前 feature 无重叠）→ 按③
5. 都不中 → 无关，按②
6. **拿不准 → 一律按相关①**（代价不对称：多一句确认 ≪ 绕过流程）

配套约束：**判定零额外读取**——用上下文已加载的锚点（或 hook 注入的锚点行）匹配即可，禁止为判定重读三件套；**每条消息独立判定**——话题漂移后重新走规则表，不整段对话二分。误判不伤流程：确定性层状态机仍是最终防线（阶段跃迁/产物门禁/修改范围比对照常拦截），粘滞只是路由引导。

**解除条件**：需求归档或 reset（stage 回 ready、feature 清空）——「对话结束」宿主侧不可观测，以磁盘状态为界；对话结束后新会话由 SessionStart resume-probe 提示续跑，跨会话衔接不丢。逐轮锚点行由 UserPromptSubmit hook 注入（ZCode/Claude/Codex，约 80 token/轮，`facade sticky-note` 供模型直接调用；WorkBuddy/pip 形态无 hook 机制，仅靠本小节条款）。粘滞与上方「每阶段开新会话省 token」不冲突：粘滞是**对话内不跑偏**，跨阶段换会话建议不变。

## 技能参考

v2.4.0 起 9 条阶段命令全部转为**阶段技能**（`skills/specpowers-<stage>/`）：slash 调用名完全不变（`/specpowers-init` 两形态照旧），用户可直接 `/` 调用，模型可经 Skill 工具自主调度（auto 编排、resume 探测提示后直接续跑）；各技能均为薄入口——加载本主技能上下文 + 跟随 `prompts/<stage>.md` 契约。

| 技能（slash 名不变） | 参数 | 说明 |
|------|------|------|
| `/specpowers-init` | `[--force]` | 生成 constitution（质量/测试/UX/性能原则 + 可选实现倾向段，从 AGENTS.md 提取编码约束）+ 扫结构基线 |
| `/specpowers-explore` | `"<需求>"` | 探索 + 设计文档落盘（`docs/specpowers/design/`）+ `record-design-doc` 登记；未归档重入=迭代轮确认（方案变更路径，v2.7.0 起新落 `design-round-<N>.md` 简易设计文档，基线不动不重登记） |
| `/specpowers-propose` | `"<需求>"` | 一站式生成三件套；未归档重入=迭代轮确认（场景调整路径） |
| `/specpowers-auto` | `"<设计文档路径>" [--instruction "<描述>"] [--archive] [--new-round]` | 无人值守全流程至 review，**默认不归档**（`--archive` 显式收口）；重入三分判定 fresh/resume/iterate；所有确认/门禁节点自动裁决，仅硬阻断才停；归档前重入=同需求迭代轮 |
| `/specpowers-fast` | `"<需求>"` | 判小跳 explore/propose，用户编码后直进 apply（fast→full 回退消耗生命周期唯一 1 次额度） |
| `/specpowers-apply` | — | 执行构建 + 实时门禁三态（结构基线 + 修改范围比对）+ 能力池调度 + Scenario 验证 |
| `/specpowers-archive` | `[--force-merge-check]` | 收尾归档（openspec delta 合并 + 场景覆盖核查）；归档即新需求，迭代计数清零 |
| `/specpowers-baseline` | — | 手动刷新结构基线 |
| `/specpowers-reset` | — | 重置 state + lock |

合法 from_stage 由 facade 确定性校验（如 apply 仅 propose / ready(fast) 可入），详见各阶段契约。

## 执行方式

所有阶段技能先调确定性层获取状态/校验，再加载对应 `prompts/` 契约执行认知任务：

```bash
python -m specpowers_cli.bridge.facade <subcommand> [--root <path>] [options]
```

插件内 `specpowers_cli` 包内嵌在 `${PLUGIN_ROOT}/scripts/` 下；`python -m` 直接执行失败（包未 pip 安装）时，改用插件内包装脚本（自动设置 PYTHONPATH）：

```bash
# 插件市场安装 —— Linux/macOS
${PLUGIN_ROOT}/scripts/specpowers_cli/bin/specpowers <subcommand> [options]
# 插件市场安装 —— Windows
%PLUGIN_ROOT%\scripts\specpowers_cli\bin\specpowers.bat <subcommand> [options]
# pip 安装（specpowers init --integration <agent>）—— 运行时包内置于主技能目录，Windows 示例
<skills_root>\specpowers\bin\specpowers.bat <subcommand> [options]
#   如 WorkBuddy：.workbuddy\skills\specpowers\bin\specpowers.bat
#      Claude：   .claude\skills\specpowers\bin\specpowers.bat
```

`PLUGIN_ROOT` 按运行环境替换：优先取宿主提供的任意插件根变量（`*_PLUGIN_ROOT` 形态——ZCode `${ZCODE_PLUGIN_ROOT}`、Claude Code `${CLAUDE_PLUGIN_ROOT}`、Codex `${PLUGIN_ROOT}`（兼容 `${CLAUDE_PLUGIN_ROOT}`）、WorkBuddy `${CODEBUDDY_PLUGIN_ROOT}` 等，新工具同理）；变量不可用时按插件安装目录定位。pip 安装形态（`specpowers init --integration <agent>` 或 `--skills-root <路径>`）包装脚本位于 `<skills_root>/specpowers/bin/`（如 WorkBuddy `.workbuddy\skills\specpowers\bin\specpowers.bat`）。

**自动读取契约强制**：Dispatcher 自动校验本阶段必读上游产物，缺必读 → 拒绝开工。如 propose 从 explore 进入时校验设计文档已登记；apply 入口校验 proposal 含「## 数据流契约」段头。

**初始化前置（v2.5.0）**：任何流水线阶段技能（explore/propose/fast/apply/archive）执行前，若 `.specpowers/constitution.md` 与 `.specpowers/baseline.json` 任一缺失（= 项目未初始化），先自动执行 specpowers-init（加载 `prompts/init.md` 完整流程，含提示用户提交两产物），再带着原输入继续目标技能——用户无需记忆「先 init」，直接开工即可。确定性层在 dispatcher 入口兜底：未初始化时阶段命令直接拒绝并给出 init 指引（防认知层跳过检查）。auto 编排本就内置 init 步骤、baseline/reset/init 不受此约束。

## 契约文件（按阶段加载，不预读）

| 文件 | 职责 |
|------|------|
| `prompts/init.md` | 生成 constitution.md（四类原则 + 可选实现倾向段），不调外部技能 |
| `prompts/explore.md` | HARD-GATE 强制完整执行内联探索引擎细则（静默探索/方案对比/设计文档落盘）+ 数据流溯源 + 设计文档落盘登记 + 判小信号映射 |
| `prompts/propose.md` | 提案契约：从设计文档提炼三件套（数据流契约 / 修改范围声明 / 执行方式推荐 / 迭代轮增量修订） |
| `prompts/apply.md` | 结构门禁三态 + 能力池调度 + 验收清单消费 + 迭代轮只跑未完成任务 |
| `prompts/archive.md` | 三职责收尾 + 合体后校验 |
| `prompts/fast_mode.md` | 判小 / 确认交互 / 回退 / 清单 |
| `prompts/auto.md` | 无人值守主契约（八要素解析落盘 + 需求澄清五维 + 阶段编排表 + 硬阻断）；**四类低频细则按需读 `prompts/refs/`**：迭代轮 `auto-iteration.md`、review 编排与归档收口 `auto-review.md`、完整裁决规则表 `auto-adjudication.md`、explore 停靠 `auto-explore-halt.md` |
| `templates/` | constitution / auto-summary / clarification 三份生成模板 |

技能组成（`skills/` 下共 11 个）：主技能 `specpowers`（本文件，路由层 + prompts/ + templates/）、9 个阶段技能 `specpowers-init/explore/propose/apply/archive/fast/auto/baseline/reset`（薄入口，见上方技能参考）、内置审查技能 `specpowers-review`（Codex 式审查；规则唯一来源 `references/review-guidelines.md`，Pass 4 / 单方法两份细则同样按需加载）。探索引擎已内联于 `prompts/explore.md` 第一步（v2.4.0 起不以技能形态暴露）。

## 安全底线

- 所有用户输入参数化传递，禁止拼入 shell 命令字符串
- git 操作使用参数列表调用 subprocess（bridge/core/git_util.py）
- `.specpowers/state.json` 原子写（临时文件 + rename）；`.specpowers/.lock` 防重入，含死锁检测

## 团队协作

- `baseline.json` → 提交 git（团队共享基线）；`state.json` / `.lock` → `.gitignore`（个人本地）
