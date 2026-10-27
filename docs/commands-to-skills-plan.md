# SpecPowers 命令转技能调整方案（定稿）

> **状态**：已评审定稿，待实施（目标版本 v2.4.0）。
> **决策记录**（2026-10-27）：第三节撞名问题采用**方案 C**——探索引擎细则并入 `prompts/explore.md` 契约、引擎技能目录删除，阶段技能占用 `specpowers-explore` 原名（同日二次评审推翻首评的方案 A「引擎改名 explore-engine」：内部引擎以技能身份暴露会误导用户，且否决理由复核后不成立，决策演变见第三节留痕）。
> 本文档为实施依据，实施会话按第十节步骤清单执行，无需重新调研。
> **2026-10-27 补充**：第十一节新增后续演进 backlog（借鉴同名独立项目 `SAXEM1997/specpowers` 的四点设计），**不属于本次 v2.4.0 实施范围**，不影响第十节步骤清单。

## 1. 背景与动机

| 现状问题 | 说明 |
|---------|------|
| **Codex 端没有命令入口** | 四端清单里 `.zcode-plugin/` / `.claude-plugin/` / `.codebuddy-plugin/` 三份都是 `commands` + `skills` 双注册，唯独 `.codex-plugin/plugin.json` 只注册了 `skills`（README 亦自述「Codex 无自定义 slash 命令，skill 自动激活」）。9 条阶段命令在 Codex 端没有任何显式入口 |
| **命令只有用户能触发** | 命令是纯用户入口，模型无法自主调用。auto 模式编排表（`prompts/auto.md` 阶段编排表第 2–7 步全是 `/specpowers-*`）只能靠模型「模拟执行」各阶段契约；SessionStart resume 探测提示续跑命令后也须用户手敲。转技能后模型可经 Skill 工具直接调用 |
| **两套入口重复维护** | 命令文件是薄入口（「加载 SKILL.md + 跟随 prompts/\<阶段\>.md」），与主技能 SKILL.md 的「命令参考」表语义重复 |

## 2. 总体设计

**9 条命令 → 9 个「阶段技能」，slash 调用名完全不变，`prompts/` 分层契约零改动。**

```
plugins/specpowers/skills/       （3 个 → 11 个）
├── specpowers/                  主技能不动（路由层 + prompts/ + templates/）
├── specpowers-init/SKILL.md     ← commands/specpowers-init.md
├── specpowers-explore/SKILL.md  ← commands/specpowers-explore.md（引擎处理见第 3 节）
├── specpowers-propose/SKILL.md  ← commands/specpowers-propose.md
├── specpowers-apply/SKILL.md    ← commands/specpowers-apply.md
├── specpowers-auto/SKILL.md     ← commands/specpowers-auto.md
├── specpowers-fast/SKILL.md     ← commands/specpowers-fast.md
├── specpowers-archive/SKILL.md  ← commands/specpowers-archive.md
├── specpowers-baseline/SKILL.md ← commands/specpowers-baseline.md
├── specpowers-reset/SKILL.md    ← commands/specpowers-reset.md
└── specpowers-review/           不动
```

11 个技能**全部是用户可用入口**，无内部执行单元以技能身份暴露。

三条关键不变量：

1. **技能名 = 现命令名** → 用户敲 `/specpowers-init` 的习惯零破坏（ZCode/Claude 技能均可短名斜杠调用，与现在命令的两形态 `/specpowers:specpowers-init` / `/specpowers-init` 一致）；
2. **`prompts/<stage>.md` 契约零改动** → v2.3.1 的分层按需加载结构原样保留，阶段技能仍是薄入口；
3. **确定性层（facade/dispatcher/bridge）零改动** → 状态机、门禁、探测全部不受影响。

已排除的备选：「合并为主技能 + args 路由」（`/specpowers init`）——入口从 9 个变 1 个，菜单可发现性和描述粒度全丢，UX 回退明显。

### 入口数量权衡（2026-10-27 二次评审补充）

曾质疑「11 个技能对用户是否太多」，结论：**数量维持，把结构亮出来**。

真实学习成本不是 11 条，是一个决策点——按触发方式分层：

| 分层 | 技能 | 用户负担 |
|------|------|---------|
| 一次性 | init | 每项目敲一次 |
| **启动入口（唯一决策点）** | explore / propose / fast / auto | 按需求形态四选一，README 已有选择表 |
| 流转 | apply / archive | **无需记忆**——resume 探测与 handoffs 会主动提示下一步命令 |
| 救急 / 维护 | reset / baseline | 出错时确定性层报错文案直接给出（见下） |
| 独立能力 | review | 可选，不进流水线也能用 |
| 容器 | specpowers（主技能） | prompts/templates 宿主，非用户目标入口 |

不做减法的理由：

- **reset 不可收**：被 9 处 bridge 确定性文案锚定（`dispatcher.py`×2 / `lock.py`×3 / `fs_state.py`×2 / `resume_probe.py`×1 / 契约×1，锁死与状态损坏时的救急指令）——收进主技能 args 须改全部文案，破「确定性层零改动」不变量；且救急场景下独立、显式的命令比「主技能+args」更可靠；
- **baseline 收拢收益仅 1 个技能位**：仅 2 处文案锚定、语义是 init 子集，技术上可并入 init（重跑即刷新），但要改 bridge 文案 + 损失「只刷基线不动 constitution」的独立语义，性价比不足；
- **args 路由彻底收敛（9→1）更糟**：9 个既有命令名全变（学习成本反增）、模型路由精度降（一条 description 覆盖九阶段语义）、bridge 探测提示命令名全改——把「多」的问题换成「全变」的问题。

降理解成本的三个动作（随本方案落地）：

1. **description 语义分层**（见第 4 节转换规则）：首词动词开头，生命周期语义（初始化/探索/提案/执行/归档/审查/重置/刷新）在菜单扫描与模型选择两个视角都立即可见；
2. **README 快速开始强化四入口引导**：显式告诉新用户「只需理解一个决策点——四个启动入口怎么选，后续阶段探测会提示你敲什么」；
3. **技能化本身的隐性缓解**：命令不进系统提示（模型看不见，只能靠 rules 记忆），技能列表常驻后模型可主动导航——用户说「我想做个小改动」，模型能看到 fast 的 description 主动建议；说「流水线卡了」会建议 reset。这是命令时代没有的反向减负。

## 3. 撞名决策（已定：方案 C——引擎并入契约）

阶段命令 `specpowers-explore` 要占用技能名，但内置探索引擎技能现在就叫 `specpowers-explore`——一个名字不能两个技能用。

**采用方案 C**：取消引擎的独立技能身份——其执行细则（四步流程、必须做/禁止做规则表、方案对比/设计文档/探索结论三模板）**并入 `prompts/explore.md` 第一步**，删除 `skills/specpowers-explore/` 目录，阶段技能占用 `specpowers-explore` 名。技能总数 3 → 11，全部为用户可用入口。

### 决策演变留痕

- **方案 A**（引擎改名 `specpowers-explore-engine`）：2026-10-27 首评采用，同日二次评审**推翻**。推翻理由：转技能后全部技能进入用户 `/` 菜单与模型技能列表，「内部引擎」以技能身份暴露是设计缺陷——曾提出 description 硬声明 + 误触发兜底转交两道防线，但那是**概率性补丁**（依赖模型遵守措辞），不是根治；且改名波及 6 处引用。正确的根治是让内部单元不以技能身份存在。
- **方案 B**（阶段技能改名 `specpowers-stage-explore`、引擎保留原名）：已否决——破坏 `/specpowers-explore` 用户习惯 + 全部文档引用。
- **方案 C 首评被否决的三条理由，二次评审逐条复核后均不成立**：
  1. 「auto 路径污染」——**事实性错误**：auto 模式本就经 explore 契约间接执行（`prompts/auto.md` 编排第 3 步），契约已是双模式共享（explore.md「迭代轮」小节明示「auto 与人工模式通用」）；引擎四步流程（静默探索/方案对比/设计文档落盘/自查）模式无关、零用户交互（交互决策全在契约层），并入后 auto 路径零变化；
  2. 「allowed-tools 收窄损失」——收窄列表含 Bash/Edit/Write，本就挡不住任何实际越界，是象征性声明；真实约束是「禁止做」规则表（不写流水线产物、不进提问循环），属提示词约束，并入契约后原样有效；
  3. 「与 review 对称性」——**伪需求**：review 用户直调无害且有用（自含三模式判定、不依赖登记门禁），应暴露；引擎直调有害（缺 `record-design-doc` 登记，propose 的 HARD-GATE 卡死），本就不该对称。引擎的正确形态是契约执行细则，不是技能。

### 方案 C 的额外收益

- 技能列表 11 个全是「可用入口」，无一个「勿用」项，零误导成本（Codex 端同样受益——它只有 skills 注册，列表更干净）；
- **token 不增反降**：explore 契约 + 引擎技能本就在同一执行路径上全部进上下文，合并省去技能包装开销（frontmatter/触发方式表/输入契约表约 30 行）；
- HARD-GATE 从「必须调用某技能」（隔一层、可被模型模拟执行）变为「必须完整执行契约第一步的探索引擎细则」（顺序阅读执行，更直接）；
- 引擎细则对 explore 是**必经主路径**（每次执行都跑），内联主契约符合 v2.3.1 分层哲学（refs 只装低频细则，必经内容不拆）。

### 引擎并入的接线点（实施时逐一处理）

| 文件 | 动作 |
|------|------|
| `skills/specpowers/prompts/explore.md` | 第一步 HARD-GATE 从「必须调用内置 specpowers-explore 技能」改为「必须完整执行下述探索引擎细则」；并入引擎四步流程、必须做/禁止做表、三模板；第 115 行「specpowers-explore 技能已把设计文档落盘」等技能指称表述同步改写 |
| `skills/specpowers-explore/` | 整目录删除 |
| `skills/specpowers/prompts/auto.md` | 编排第 3 步及正文「经 explore 契约（含探索引擎细则）执行」表述微调 |
| `skills/specpowers/SKILL.md` | 「内置技能（随插件分发）」段更新为仅 review；版本号 |
| `README.md` | 依赖表 explore 行（「explore 引擎内置于 explore 契约，无需外部依赖」）、触发词表、版本徽章与安装命令 |
| `tests/test_builtin_skills.py` | `BUILTIN_SKILL_DIRS` 删引擎条目（3 → 2：specpowers、specpowers-review，另加 9 个阶段技能目录） |

## 4. 单条命令 → 技能的转换规则（9 份统一适用）

**frontmatter**：

- `description` 保留但**统一精简到 ≤25 词**（现命令 description 有多条超长，explore 最长 60+ 词；技能 description 常驻系统提示，见第 8 节）；**首词动词开头**，让生命周期语义（初始化/探索/提案/执行/归档/审查/重置/刷新）在用户菜单扫描与模型技能选择两个视角都立即可见（入口数量权衡见第 2 节）；
- `handoffs` 删除（技能无此约定）→ 正文已有 "Tell user: next step is /specpowers-xxx" 承接，显式补一句「完成后建议用户调用技能 xxx；auto 模式下直接经 Skill 工具调用」；
- 新增 `name: specpowers-<stage>`（与目录名一致）；
- **不设 `allowed-tools`**：阶段技能是编排单元，需要 Bash 跑 facade + 调用 superpowers 技能，应继承全部工具；内置 specpowers-review 是叶子执行单元才收窄工具列表（探索引擎已并入 explore 契约，不适用——见第 3 节）。

**正文**：

- `## User Input` 里的 `$ARGUMENTS` 占位符改为「用户输入经技能 args 参数传入（用户直接 / 调用时为原文，模型经 Skill 工具调用时为编排参数）」；
- Outline 部分原样保留（本来就是「加载主技能上下文 + 跟随 `prompts/<stage>.md`」的薄入口）。

**示例**（`specpowers-init` 转换后骨架）：

```markdown
---
name: specpowers-init
description: 生成项目 constitution（质量/测试/UX/性能原则）并扫描结构基线，每项目执行一次
---

# specpowers-init — 项目初始化

用户输入经技能 args 参数传入（`--force` 时先删除既有 constitution.md 与 baseline.json 再重新生成）。

## Outline

（原 commands/specpowers-init.md 的 Outline 原样保留：加载主技能上下文 → 跟随 prompts/init.md → 四步流程）

完成后：提示用户提交 `.specpowers/constitution.md` 与 `.specpowers/baseline.json`；下一步建议调用技能 specpowers-explore / specpowers-propose / specpowers-fast（按需求形态三选一）。
```

## 5. 目录与清单接线

| 目标 | 动作 |
|------|------|
| `plugins/specpowers/commands/` | 删除（9 份文件） |
| `.zcode-plugin/plugin.json` | 删 `"commands": "commands"` 键 |
| `.claude-plugin/plugin.json` | 删 `"commands": "commands"` 键 |
| `.codebuddy-plugin/plugin.json` | 删 `"commands": "./commands"` 键 |
| `.codex-plugin/plugin.json` | **零改动**——本来只有 skills，是本次最大受益端（Codex 直接获得 9 个显式阶段入口） |
| 根 portable `plugin.json` | 零改动（skills 目录自动发现） |
| 4 份 `marketplace.json` | 零改动（已确认无「命令」字样） |

## 6. 引用面盘点

**不用改**（slash 名不变兜底，转技能后继续有效）：

- `skills/specpowers/prompts/` 内 96 处 `specpowers-*` 引用（阶段语义与斜杠调用名均不变）；
- `bridge/modules/resume_probe.py` 9 处提示文案（`/specpowers-apply` 等）；
- `hooks/check-deps` 2 处提示文案；
- bridge 其余 7 个 py 文件（lock/baseline_scanner/dispatcher/fs_state/facade/main/openspec_adapter）的提示文本；
- README / GETTING-STARTED 里 30+ 处 `/specpowers-xxx` 调用示例。

**要改**：

| 文件 | 改动 |
|------|------|
| `skills/specpowers/SKILL.md` | 「命令参考」表 → 「技能参考」（表头与措辞）；「内置技能」段更新为仅 review；版本号 |
| `skills/specpowers/prompts/explore.md` | 第一步并入探索引擎细则（HARD-GATE 措辞改为「必须完整执行」，见第 3 节接线表） |
| `skills/specpowers/prompts/auto.md` | 编排第 3 步改为「经 explore 契约（含探索引擎细则）执行」 |
| `README.md` | 支持平台表 Codex 行「skill 自动激活（Codex 无自定义 slash 命令）」→「`/specpowers-xxx` 技能直调（四端统一）」；「9 个 slash 命令 + SessionStart 依赖检测」等表述；依赖表 explore 行；「阶段命令详解」表头；快速开始强化四入口引导（见第 2 节降理解成本动作 2）；版本徽章与安装命令 |
| `docs/GETTING-STARTED.md` | 与 README 同步（命令表述 → 技能表述） |

## 7. 测试调整

- `tests/test_builtin_skills.py`：技能目录表 3 → 11；新增「阶段技能完整性」断言——SKILL.md 存在、frontmatter `name` = 目录名、正文引用 `prompts/<stage>.md` 不断链、无 `$ARGUMENTS` / `handoffs` 残留；
- 新增防回潮断言：`commands/` 目录不存在、三端清单（zcode/claude/codebuddy）无 `"commands"` 键；
- 引擎并入防断链：`skills/` 下不存在 `specpowers-explore-engine` 或其他以 `-engine` 结尾的目录；`prompts/explore.md` 含探索引擎细则章节与三模板锚点（防细则被误删）；全仓无「调用内置 specpowers-explore 技能」残留表述（changelog 历史记录除外）；
- `tests/test_manifest_consistency.py`：已确认只锁 requirements 声明（`commands`/`plugins` 键为依赖声明语义，非目录注册）与 version 一致性，不锁 commands 目录，预计只动 version 同步；
- README 用例数同步。

## 8. token 影响与对策（与 v2.3.1 省 token 目标对齐）

- **代价**：ZCode/Claude 的技能列表常驻系统提示，3 → 11 条 ≈ 每会话多 ~8 行 name+description（约 300 token）。对策是第 4 节的 description 精简（≤25 词）——命令 description 只进 UI 菜单，技能 description 要常驻上下文，这是转换的必修课；
- **收益**：模型可自主调度阶段（auto 编排、resume 探测提示后直接续跑）；技能 description 进入模型可见的技能列表后，模型能按描述语义自主选阶段——这是命令没有的能力；
- **可选后续**（不进本次 v2.4.0）：`prompts/auto.md` 编排表从「模型模拟执行契约」升级为「直接 Skill 调用阶段技能」，语义更确定。

## 9. 风险与开放问题

1. **handoffs 能力损失**：命令 frontmatter 的 `handoffs`（ZCode UI 的「下一步建议」按钮）在技能上没有对应约定，降级为正文文字指引。实施前实测一次 ZCode 技能 frontmatter 是否兼容该字段，兼容则原样保留；
2. **菜单分组变化**：插件入口从「命令 9」分组变为技能分组，菜单位置变化（直接敲 `/specpowers-init` 不受影响）；
3. **CodeBuddy 需实测**：删 `commands` 键后其技能斜杠调用是否可用（Codex 已验证 skills 可用，CodeBuddy 风格接近 Claude，风险低）；
4. ~~引擎命名决策~~ **已定**：方案 C——引擎并入 `prompts/explore.md` 契约、技能目录删除（2026-10-27 二次评审，演变留痕见第 3 节）。

## 10. 实施步骤清单（一次提交完成）

1. 新建 9 份阶段技能（按第 4 节转换规则，description 精简）+ 删除 `commands/` 9 份命令；
2. 引擎细则并入 `prompts/explore.md` 第一步（HARD-GATE 措辞改为「必须完整执行」）+ 删除 `skills/specpowers-explore/` 目录 + 第 3 节接线表逐一更新；
3. 三端清单（zcode/claude/codebuddy）删 `commands` 键；
4. 主 SKILL.md / README / GETTING-STARTED 措辞（第 6 节「要改」表）；
5. 测试扩展 + 防回潮断言（第 7 节），全量测试跑通；
6. 版本升级 v2.4.0（按项目惯例 16 处同步：8 份清单 version + pyproject + `__version__` + SKILL.md + README 徽章与安装命令），README 用例数同步；
7. 提交信息按仓库惯例：`feat: 命令转技能四端入口统一 + 探索引擎并入 explore 契约，版本升级 v2.4.0——…`（详述动机与变更，含全量用例数与耗时）。

规模估计：新增 9、删除 10（9 份命令 + 引擎技能目录）、小改约 8 个文件；确定性层（bridge/facade/dispatcher）零改动；用户 slash 习惯零破坏；技能列表无内部单元暴露。

## 11. 后续演进 backlog（2026-10-27 调研补充，不属于 v2.4.0）

> **来源**：对同名独立项目 [SAXEM1997/specpowers](https://github.com/SAXEM1997/specpowers) 的对比调研——SDD+TDD 方法论的 DeepSeek Harness 插件 + Claude Code 技能组，同样融合 OpenSpec 与 Superpowers（与本项目思路同源、实现路线不同：纯 Markdown 技能组，无确定性 bridge，平台仅 Claude Code + DSH 双端）。
> 四点按落地成本从低到高排序，均与现有设计零冲突，可独立分版本实施。

### 11.1 审查核算「守恒等式 + 四口径 + 拒绝异常升级」（纯提示词，成本最低）

**机制**：审查过程强制维护四个精确口径——`p*_raw`（各审查 Agent 原始发现数）/ `p*_merged`（合并后清单数）/ `p*_rejected`（被拒绝未纳入数）/ `p*_supplement`（监督补充数）——并强制自检守恒等式 `Σsources + Σrejected == Σraw + Σsupplement`（精确算术、无容差），不成立即标 `[问题数存疑]`、禁止进入后续步骤。配套 `[拒绝异常]` 规则：拒绝必须逐条书面理由（禁模板化、禁批量），被拒 >3 条或 >30% 强制触发一轮独立复核。

**借鉴理由**：本项目 review 技能是多 Pass 审查 + P0-P3 输出，属**引导式**——规则告诉模型怎么审，但没有机制验证它有没有审完、有没有漏账；auto 模式「review 修复最多 2 轮」的收敛判定同样靠模型自觉，模型可以审 3 条报 3 条、悄悄吞掉 5 条后宣布通过。守恒等式把「审查是否偷懒/漏账」从不可验证的主观判断变成一行算术，每条原始发现必须有明确去向（进合并表 `sources` 或进未纳入清单），与本项目「确定性校验兜最低底线」哲学完全同构，只是尚未延伸到审查环节自身。口径分配亦有讲究：收敛判定用 merged（防重复计数白跑一轮），验证强度判定用 raw（保守值，防主 Agent 过度合并人为压低问题数逃逸监督）；拒绝异常堵的是「用大量低质量拒绝伪装严格或提前收敛」的另一类漏洞。

**作用**：① 反偷懒——少报/漏报/悄悄合并无法通过算术自检；② 反伪装——批量拒绝自动升级独立复核；③ 收敛可信——auto 的 2 轮上限建立在可信问题数之上而非模型自报「没大问题了」。

**落地建议**：写入 `skills/specpowers-review/references/review-guidelines.md`（审查规则唯一来源），SKILL.md 工作流骨架加对应步骤；auto 模式（`prompts/auto.md` review 编排）消费口径数字做收敛判定。

### 11.2 内网信息/凭据泄漏自检脚本（一个 Python 脚本）

**机制**：零依赖自检脚本，扫描已追踪文件内容（`git ls-files`）、**全部提交信息（`git log --all`）与作者/提交者姓名邮箱**，匹配 RFC1918 私网 IP、`.lan/.internal/.corp/.local` 内网域名、`glpat-`/`ghp_`/`github_pat_`/`AKIA`/`sk-` 等凭据前缀、PEM 私钥块、`scheme://user:pass@` 内嵌凭据；违规退出码 1，输出**全部打码**（只留首尾几字符），避免把敏感内容再次抄进日志。

**借鉴理由**：本项目是在公司环境（工号、企业邮箱）下维护公开 MIT 仓库，泄漏风险是现实配置而非假设；且 git 历史一旦推出，删文件解决不了历史里的泄漏。扫**作者邮箱**维度来自对方的真实事故：公司域名邮箱曾入库 139 个提交，重写历史修复后遗留的 `user.email` 又让新提交把邮箱带回——只扫文件内容的闸门对此完全失明。输出打码则是防自检脚本本身成为新泄漏源。

**作用**：① 推送前确定性拦截内网 IP/内部域名/令牌/私钥进入公开仓库；② 覆盖 git 元数据盲区（提交信息 + 作者身份）；③ 检测过程自身不二次泄漏。

**落地建议**：`scripts/verify_no_internal_refs.py`（Python 仅 stdlib，贴合仓库惯例），挂 pre-push hook 或纳入 CI（见 11.3）；项目专属 denylist（企业邮箱域名、内网域名）放 gitignored 的 `.internal-refs.txt`，缺失自动跳过该层。

### 11.3 GitHub Actions CI + Windows CRLF 专项复验（一个 workflow 文件）

**机制**：push/PR 触发，ubuntu + windows 双系统矩阵跑全量测试；另设专项 job：先把技能/提示词文件转 CRLF 行尾，**在转换后的副本上再复验一遍**（主动构造最恶劣行尾形态）。

**借鉴理由**：286 个用例目前只能在本地跑，质量保障依赖「记得提交前跑全量」——测试再全，没有 CI 强制执行就存在改坏未测即推送的窗口。CRLF 专项针对性强：本项目 Windows 主力开发、用户横跨三平台，`hooks/check-deps` 这类 bash 脚本遇 CRLF 直接报错；v2.2.2 刚修过一整轮 Windows 编码链路问题，说明此类风险在本项目反复真实出现。

**作用**：① 每次 push/PR 强制回归全部用例，契约漂移合入前拦截，不依赖个人自觉；② 跨平台兼容从事后修 bug 变成事前守门；③ 公开仓库的 CI 徽章是外部用户判断工程质量的第一信号。

**落地建议**：`.github/workflows/ci.yml`：矩阵 [ubuntu-latest, windows-latest] 跑 `pytest`；CRLF 专项 job 转换 `skills/`、`hooks/` 后复验（至少覆盖 hooks 的 shell 脚本解析类测试）。

### 11.4 技能行为评测套件（评测基建，可从 review 技能起步）

**机制**：每技能配 `evals/eval.yaml` + `evals/cases/*.yaml`（skill-up 声明式格式）：`input.prompt` 为**对抗样本**（模拟主 Agent 中间态、故意诱导模型犯错，如守恒等式用例给出「差 2 条但不到两成，大致相符」的合理化诱惑），`expect.must_contain` 断言关键标记，`judge.rule_based` 规则谓词判成败。用例 description 沉淀**失配原因**（该防护为何易被模型绕过）与踩坑记录（如不设 `must_not_contain`——正确答案的否定式表述会误命中）。

**借鉴理由**：现有 286 个用例全部是**契约一致性**断言（清单/版本/文件存在/文案防断链），验证「插件结构没被改坏」，但不验证「技能执行起来行为对不对」——提示词重构（如 v2.3.1 瘦身）后规则语义有没有被改丢、模型还能不能抵抗常见错误诱惑，现有测试测不出来，只能人肉过。行为评测是提示词规则的「负向测试」，与本项目的契约测试**互补成双层**（对方只有行为评测、无契约测试；本项目反之——完整形态是两者兼有）。

**作用**：① 把「提示词规则是否真的约束了模型行为」变成可回归验证的资产，改提示词后跑评测即可暴露行为退化；② 用例本身是规则的活文档，记录每条规则防的真实失误模式；③ 为持续提示词瘦身提供行为不回归的安全网。

**落地建议**：`tests/evals/`（或独立 `evals/` 目录）起步只做 review 技能 2-3 个对抗用例（正好承接 11.1 的守恒等式/拒绝异常规则），YAML 格式沿用 skill-up schema（`schema_version: v1alpha1` / judge.rule_based），配一个仅 stdlib 的 runner 脚本判定输出；验证有效后再铺开到其他技能。

### 11.5 实施顺序建议

11.1（纯提示词，半天）→ 11.2（一个脚本）→ 11.3（一个 workflow）→ 11.4（评测基建，依赖 11.1 的规则先行落地才能写对抗用例）。四点可分别随后续 patch/minor 版本实施；11.2 + 11.3 组合优先级最高（公司环境 + 公开仓库的暴露面是当下真实风险，其余是质量增益）。
