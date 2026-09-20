# SpecPowers auto 模式需求澄清方案

> **⚠️ v2.0.0 阶段名变更注记**：本文档为 v1.x 定稿方案，文中阶段名 constitution/brainstorm/specify/plan/build 已于 v2.0.0 重命名为 init/explore/propose(合并 specify+plan)/apply，语义不变；ceiling 值 `brainstorm` 相应改为 `explore`。本文按原文保留作历史依据，不再回改。

> 背景：auto 模式（`docs/auto-iteration-plan.md`，v1.2.0）fresh 流程为「第 0 步三分判定 + 八要素解析落盘 → 直接进入 constitution→brainstorm→specify→plan→build→review→archive」。八要素解析不到仅标注 `null` + 原因即继续，设计文档的质量问题（要素缺失、自相矛盾、场景不可测、范围与边界冲突）没有入口检查，被推迟到下游各阶段由「裁决规则表」零散兜底——**垃圾进垃圾出**：文档若核心要素缺失，要到 build/review 阶段才暴露，前序阶段全部白跑。本方案在流水线最前面补一个显式的**需求澄清步骤**，作为实现依据。

## 1. 定位与核心语义

**需求澄清 = 推进深度调度器**：对设计文档做入口质量检查，结论不是「跑 / 不跑」的二值门禁，而是**本轮推进上限（stage ceiling）**——文档能支撑到哪一步，auto 就自动推进到哪一步；支撑不了的深度不零步硬停，而是停在能力边界并产出**有效的中间产物**等待补充。

- 位置：第 0 步（三分判定 + 八要素解析落盘）之后、constitution 之前，重排为显式**第 1 步**（原阶段编排表 1–7 顺延为 2–8）
- **零门槛原则**：不新增任何用户参数（无 `--force` 之类逃生门）、不要求用户预判文档质量、不要求两段式操作。用户体验 = 「auto 总是尽量往前跑，跑到该停的地方停，补完即续」
- **与裁决规则表的关系**：裁决规则表是**各阶段零散交互点**的兜底；澄清步骤是**入口处系统性**的质量检查，把下游可能踩到的坑前置发现、前置裁决、集中留痕
- **三层防御哲学与 brainstorm 数据流契约一致**：确定性层校验形式（澄清结论已登记），认知层契约保证检查实质质量，汇总报告供人工回看

## 2. 澄清检查清单（五维）

对八要素解析结果（`parsed`）与设计文档原文执行以下检查，逐项产出结论（通过 / 已裁决 / 遗留 / 深度受限）+ 依据。按 1→5 顺序执行：

| # | 维度 | 检查内容 | 处置 |
|---|------|----------|------|
| 1 | 完整性 | 八要素逐项非空检查。**功能名**：null → 按参数错误（文档连标题级描述都没有，不属于合格设计文档，见 3.4）；**已定方案**：null → 深度受限至 brainstorm；**必测场景清单**：null → 不限深度，specify 按方案推导场景 + 遗留标注；其余五要素为次要要素，null → 按默认策略继续（见 3.5）+ 遗留记录 |
| 2 | 自洽性 | 文档内部结论冲突检测：同一需求点在两处描述不一致（如概述与详设的方案、场景清单与详述的边界） | 能判定权威章节（详设 > 概述、专门章节 > 顺带提及、后文 > 前文）→ 采信 + 记录出处；涉及关键要素且不可判定 → 深度受限至 brainstorm（草案双方向并列，见 3.2） |
| 3 | 可测性 | 「必测场景清单」逐条能否转化为 WHEN/THEN。**不可测的判定口径收紧为「连触发条件（WHEN）都无法从文档导出」**；预期结果写得笼统（如「友好提示」）不算不可测，按保守改写 + 留痕处理 | 不可测条目按口径统计：占比 ≤ 1/2 → 保守改写 + 留痕，不限深度；占比 > 1/2 → 说明方案粒度不足以定义行为，深度受限至 brainstorm |
| 4 | 明确性 | 歧义点识别：存在多种合理理解的需求描述 | 按现有裁决规则：回文档找依据；无依据 → 选「不改变现有行为」的理解 + 记录歧义点与采信依据，不限深度 |
| 5 | 边界一致性 | 「修改范围表」与「硬性边界」交叉核对：范围中的文件 / 动作是否触碰红线（如边界写「不改表结构」而范围含 DDL） | 可裁剪（越界项明显多余）→ 裁剪范围 + 记录；冲突不可裁（核心目标必须越界才能达成）→ 文档方案层矛盾，深度受限至 brainstorm |

## 3. 处置策略：推进深度上限（分级停靠）

### 3.1 深度上限表

| 澄清结论 | ceiling | 行为 |
|----------|---------|------|
| 五维全部通过，或仅有：次要要素缺失 / 场景需推导 / 可保守裁决的歧义与笼统 | `full` | 直通全流程至归档（现状行为 + 留痕），场景推导、保守改写、默认策略全部记录进澄清报告 |
| 已定方案 null / 关键矛盾不可判 / 边界冲突不可裁 / 不可测场景占比 > 1/2 | `brainstorm` | 推进 constitution → brainstorm，产出**未收敛 proposal 草案**后**自然停靠**（见 3.2），不进入 specify 及以后 |
| 功能名 null（文档无法解析出标题级功能描述） | 入口 | 按现有硬阻断类「参数错误」处理（文档不合格），输出澄清问题清单 |

**设计原则**：方案没定 → 永远不会走到 specify / plan / build（杜绝垃圾进 build）；但 constitution（提取仓库编码约束，与文档缺陷无关）与 brainstorm 探索（代码事实核对）不受文档缺陷影响，照常执行——**每段跑过的产物都有效，零浪费**。

### 3.2 brainstorm 停靠：未收敛草案

ceiling=brainstorm 时，brainstorm 阶段按其契约的**未收敛语义**落盘（现有机制复用，不新增状态）：

- 探索代码事实照常执行（核对核心调用链等）
- proposal.md 的 Why 段标题标注 `[未收敛]`，按缺陷类型组织草案内容：
  - 方案未定 → 列出 2–3 个候选方向 + 各自 trade-off + 推荐（对齐 brainstorming 技能标准流程），**不做方案取舍**
  - 关键矛盾 / 边界冲突 → 并列文档内冲突结论 + 代码事实，标注「待用户裁决」
  - 场景大面积不可测 → 列出不可导出 WHEN 的场景清单，标注「方案粒度不足」
- 「## 数据流契约」小节照常产出（能确定多少写多少，`未确认项` 列出缺口），保证后续 specify 前置校验语义不变

**停靠输出四要素**（对齐硬阻断输出格式，语义为「等待输入」而非「异常」）：① 停靠原因 + 待用户裁决问题清单；② 已完成阶段（constitution / brainstorm）；③ 产物位置（未收敛 proposal + 澄清报告）；④ 恢复方式：**带方案结论重入 `/specpowers-auto --instruction "<结论摘要>"`，或补充设计文档后重入**。

### 3.3 停靠后的重入路径（零参数扩展）

停靠发生在 brainstorm 完成之后，**feature 已锁定、change 目录已建立**，因此重入必然命中现有 `iterate` 分支，恢复路径完全复用现有机制：

- 用户带 `--instruction "<方案结论>"`（**现有参数，迭代轮形态天然可用，零语义扩展**）或带补充后的设计文档重入
- `auto-status` 判 `iterate` → `auto new-round` 开轮 → 迭代深度判定命中「已定方案变了（从无到有）→ 全量」→ brainstorm 在草案基础上收敛，proposal 去掉 `[未收敛]` 标注 → specify → … 全流程
- **轮次语义**：首轮停靠后的重入计为 Round 1（「方案定稿轮」），`iteration_count` 0→1；汇总报告注明「Round 0 为未收敛草案轮」。草案 + 定稿合起来视为需求的早期迭代，与「迭代不设上限、归档收口」模型自洽
- **resume 保护**：无新输入重入（既无指令也无文档变更）且 `clarification.ceiling = brainstorm` → `auto-status` 输出 `pending_input` 状态，契约层**不得**从 brainstorm 断点盲目续跑 specify，提示用户带结论重入（见 3.1 表与第 6 节）

### 3.4 硬阻断定义（不变，仅一类与澄清相关）

沿用现有四类硬阻断（外部强依赖不可用且无降级 / 状态机不一致无法自愈 / 参数错误 / 输出恢复方式）。澄清相关的仅一条入列：**功能名 null 按参数错误**（文档无法解析出标题级功能描述 = 不是合格的设计文档输入）。原方案中「文档自相矛盾不可判」从硬阻断移出，降为 brainstorm 停靠（3.2）。

### 3.5 次要要素默认策略（full 路径继续的依据）

| 次要要素 | 缺失时的默认策略 |
|----------|------------------|
| 核心调用链 | brainstorm 阶段探索代码事实自行核对（现有语义本就如此） |
| 修改范围表 | plan 阶段基于 spec 自行拆分，澄清报告标注「范围以 plan 结论为准」 |
| 编码约束 | 取仓库 AGENTS.md（constitution 阶段本就从此提取） |
| 外部依赖降级策略 | 通用降级：Remote 不可达 → 返回空 + warn 日志 + 完整异常堆栈 |
| 硬性边界 | 按通用红线（不改表结构 / 不新增第三方依赖 / 修复不扩范围），标注「文档未声明边界」 |

## 4. 产物设计

### 4.1 澄清报告（人读，审计留痕）

路径：`.specpowers/auto_clarifications/<feature>.md`（feature 取八要素功能名 slug；与 `auto_decisions/<feature>.md` 对称命名，归档后保留作审计历史）。

结构（新增 `templates/clarification-template.md`）：

```markdown
# 需求澄清报告：<功能名>（Round <N>）

- 澄清时间 / 输入形态 / 设计文档路径 + hash
- 结论：ceiling = full / brainstorm（+ 遗留 <N> 项）

## 五维检查结果

| 维度 | 结论 | 说明（含文档出处章节） |
|------|------|------------------------|

## 裁决记录

| # | 问题 | 裁决 | 依据（文档章节 / 默认策略 / 保守原则） |
|---|------|------|----------------------------------------|

## 遗留问题（场景推导 / 保守改写 / 次要要素默认策略）

| # | 问题 | 影响 | 建议补充方式 |
|---|------|------|--------------|

## 待用户裁决问题清单（ceiling=brainstorm 时非空，同步进未收敛 proposal）
```

迭代轮为**追加式**：文末按 `### Round <N>` 续写本轮澄清记录（对齐 proposal「迭代历史」模式），不覆盖历史轮。

### 4.2 状态登记（机器可读，断点续跑凭据）

`auto_base.json` 新增 `clarification` 字段：

```json
{
  "clarification": {
    "ceiling": "full | brainstorm",
    "report_path": ".specpowers/auto_clarifications/<feature>.md",
    "checked_at": "<ISO8601>"
  }
}
```

- 功能名 null（入口参数错误）不登记
- resume / 重入时凭此字段判定是否重做澄清与是否允许续跑（见第 5、6 节）

## 5. 各分支行为

| 分支 | 澄清行为 |
|------|----------|
| `fresh` | **全量五维澄清**（本方案主体），产出 ceiling 并按 3.1 推进 |
| `resume` | 不重做（`clarification` 字段为凭据，迭代轮同理）；**例外**：`ceiling=brainstorm` 且本轮无新输入 → 输出 `pending_input`，提示带结论重入，不盲目续跑。字段缺失（旧格式 auto_base.json / 人工流程接管）→ 补做全量澄清后按结论推进 |
| `iterate`（有新文档） | **增量澄清**：新 `parsed` 与上一轮对比——① 冲突点自洽性；② 调整是否触碰硬性边界（维度 5）；③ 新增/变更场景可测性（维度 3）。结论仅可能维持或**上调** ceiling（brainstorm → full），不下调（上一轮已跑过的深度不因澄清回退）；「已定方案」变更 → 升级为全量五维 |
| `iterate`（仅指令） | **指令澄清**：① 指令能否无歧义映射到现有 scenario 增/删/改（对齐迭代深度判定的轻量条件）；② 是否触碰硬性边界。若上一轮停靠在 brainstorm（方案待定），指令即方案结论 → ceiling 上调 full，走方案变更全量路径收敛草案 |

迭代轮澄清结论同样落报告（追加）并刷新 `clarification` 字段。

## 6. 确定性层改动（最小侵入）

| 改动 | 内容 | 目的 |
|------|------|------|
| `facade auto-status` 输出扩展 | 响应 JSON 增加 `clarification` 字段（从 `auto_base.json` 读取：`ceiling` + `pending_input` 布尔：ceiling=brainstorm 且本次无新输入） | resume 判定保护（3.3）与契约层可见性 |
| 新增 `facade auto clarify` 子命令 | `auto clarify --ceiling <full|brainstorm> [--report <路径>]`：写入 / 刷新 `auto_base.json` 的 `clarification` 字段（要求 auto_base.json 存在，即第 0 步已完成） | 防「声称澄清但未登记」（形式校验兜底，对齐 brainstorm 数据流契约段头校验哲学） |
| `auto_status` 现有 fresh 分支 | 不改（残留清理已覆盖入口阻断重入） | — |

> 确定性层不校验报告内容质量（无法机器判定「方案是否真的定了」），只兜「澄清结论已登记」这一形式底线；实质质量依赖契约层措辞 + 汇总报告人工回看，三层防御。

## 7. 契约层改动

| 文件 | 改动 |
|------|------|
| `prompts/auto.md` | ① fresh 分支插入「第 1 步：需求澄清」（五维检查 + 深度上限表 + 停靠输出四要素），阶段编排表 0–7 改 0–8，ceiling=brainstorm 时第 2 步标注「产出未收敛草案后停靠」；② 迭代轮编排增加「增量澄清」小节与 ceiling 上调规则；③ resume 保护：`pending_input` 时不得续跑 specify；④ 裁决规则表增补：「次要要素缺失 → 默认策略表」「澄清检查发现的歧义 → 前置裁决（引用澄清报告裁决记录）」；⑤ 硬阻断定义表增加：功能名 null 按参数错误；⑥ 汇总输出要求增加澄清结论 |
| `templates/clarification-template.md`（新增） | 4.1 的报告结构 |
| `templates/auto-summary-template.md` | 头部元信息增加「需求澄清：ceiling = full / brainstorm（遗留 <N> 项）」；「执行结果」增加「brainstorm 停靠（方案待定，等待输入）」形态；「遗留风险」增加澄清遗留项来源 |
| `commands/specpowers-auto.md` | Outline 插入澄清步骤描述（五维检查 → 深度上限 → 停靠等待输入，零新参数） |

**不改动**：`brainstorm.md` 未收敛语义（直接复用，仅在 auto.md 编排层引用）；`specify.md` / `plan.md` 等各阶段契约（澄清是 auto 编排层步骤，不是新流水线阶段，不新增 stage、不动状态机）；人工模式不做强制对齐（brainstorm 本就有 AskUserQuestion 澄清交互，澄清模板可被人工复用，属可选后续项）。

## 8. 改动落点清单

| 层 | 文件 | 改动 |
|----|------|------|
| 确定性层 | `bridge/facade.py` | 新增 `auto clarify` 子命令入口 |
| 确定性层 | `bridge/dispatcher.py` | 新增 clarify 登记处理器（写 `clarification` 字段）；`auto_status` 响应增加 `clarification`（ceiling + pending_input） |
| 契约层 | `skills/specpowers/prompts/auto.md` | 第 7 节所列六项 |
| 契约层 | `skills/specpowers/templates/clarification-template.md` | 新增 |
| 契约层 | `skills/specpowers/templates/auto-summary-template.md` | 澄清结论与停靠形态呈现 |
| 命令 | `commands/specpowers-auto.md` | Outline 补充 |
| 测试 | `tests/`（test_dispatcher.py / test_auto_iteration.py） | clarify 登记落盘、auto-status 携带 clarification / pending_input、ceiling=brainstorm 无新输入不续跑、旧格式无字段补做路径、停靠后带 instruction 重入判 iterate |
| 版本 | `plugin.json` × 3（.claude-plugin / .codex-plugin / .zcode-plugin）、marketplace.json | minor 升级 v1.3.0 |

## 9. 实现顺序

1. 确定性层：`dispatcher.py`（clarify 处理器 + auto_status 扩展）→ `facade.py`（子命令）+ 测试
2. 契约层：`clarification-template.md` → `auto.md`（第 1 步 + 深度上限 + 停靠 + 迭代增量澄清 + resume 保护 + 汇总）→ `auto-summary-template.md` → `commands/specpowers-auto.md`
3. 版本升级 + 全量回归：`python -m pytest tests/ -v`

## 10. 边界与不做的事

- 澄清**不替代**各阶段裁决规则表：澄清过后下游仍可能遇到新交互点，仍按裁决规则表处理
- 澄清不调外部模型 / 不做语义级「文档评分」，仅基于八要素 + 文档原文的结构化检查（可执行、可留痕）
- 不新增流水线 stage、不改状态机跃迁、**不加用户参数**（`auto clarify` 是 auto 契约内部编排原语，仅契约调用；停靠恢复复用现有 `--instruction` / 文档重入形态）
- ceiling=brainstorm 停靠会产生 change 目录与锁定的 feature：用户决定放弃该需求时走现有 `/specpowers-reset` 清理（汇总报告停靠输出中注明放弃路径）
