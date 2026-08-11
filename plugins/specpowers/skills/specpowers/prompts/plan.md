# plan.md — 实现计划契约

## 触发

当用户调用 `/specpowers-plan` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 来自 state.json 的 feature 字段（brainstorm/fast 阶段确定并锁定，同一流程不变）。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade plan --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`specify`
- `openspec/changes/<feature>/specs/` 下 delta spec 必须存在（缺则拒绝）

## 执行步骤

### 交互决策原则（AskUserQuestion 使用指引）

plan 阶段**默认按 delta spec 自主拆分任务并给出推荐**，不强制打断用户。但当出现以下情况时，**必须主动用 AskUserQuestion 让用户决策**：

| 触发场景 | 处理方式 |
|---------|---------|
| 任务拆分有歧义（同一需求可多种拆法） | 列出拆分方案 + 各自粒度/风险，让用户选 |
| 执行方式选择不确定（特性特征不明显） | 列出 conductor/worktree/subagent/TDD 各自适用性 + 推荐 |
| 任务间依赖关系不清晰（循环依赖/顺序难定） | 列出可能的依赖排列，让用户确认 |
| 涉及大粒度决策（如是否拆分独立模块、是否引入新依赖） | 列出选项 + 影响，让用户拍板 |
| **跨链路入参数据来源不明**（回调/接口/MQ 报文中的关键字段无法从 spec 追溯到上游产生方与传递链路） | 列出存疑入参 + 字段名假设 + 可能来源环节，让用户确认真实字段名与产生方 |

**AskUserQuestion 格式要求**（与 brainstorm 一致）：
- 每个选项给清晰 label（1-5 词）+ description（影响/取舍）
- 推荐项放第一，label 末尾加「（推荐）」
- 仅在真正需要用户判断时问

### 第一步：读取 delta spec

加载 `openspec/changes/<feature>/specs/<capability>/spec.md`（delta spec）作为任务拆分的输入。
读取其中的 `### Requirement` 和 `#### Scenario`，将每个 Scenario 映射为可执行任务。

### 第二步：瘦身 writing-plans + 生成 tasks.md

调用 superpowers 的 `writing-plans` 技能，但进行瘦身：

**产物归并**：所有任务合并到单一 `openspec/changes/<feature>/tasks.md`。

**内容语言**：**全部使用中文**。

**任务格式**（对齐 superpowers writing-plans 技能的 `Task N` 标题结构 + specpowers 固定字段）：

> **重要**：任务标题必须用 `### Task N: [描述]` 格式（英文 Task + 编号），
> 这是 subagent-driven-development 的 `task-brief` 脚本切分任务的依据
> （脚本按 `^#+ Task N` 匹配，awk 整段透传，不解析字段名）。内容用中文，但标题结构不可改。
> 新增字段只要写在 `### Task N` 标题之后、下一个 Task 标题之前，就会原样进入 task-brief，
> conductor 与 subagent 两种执行模式都能消费。

**字段档位**：先按第三步判定本特性的推荐执行方式，再套对应档位的字段模板。
推荐=conductor（或 fast 模式）用「conductor 档」；推荐=subagent 用「subagent 档」。
用户在 build 阶段仍可改执行方式，但 tasks.md 字段已按档位定稿，改模式可能需重跑 plan。

**conductor 档**（推荐=conductor，或 fast 模式）——轻量字段 + 场景原文：

```markdown
## 推荐执行方式

<!-- 顶部注释块标注推荐方式，build 阶段读 -->
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
- 测试先行：<是/否>

### Task 2: [任务描述]

- [ ] 实现内容：<具体步骤>
- 场景引用：<Scenario 名 + WHEN-THEN 原文摘录>
- 验收标准：<本任务验收标准>
- 依赖：Task 1
- 并行：<是/否 + 可并行的兄弟任务号；否则写 否>
- 检查点：<本任务完成后是否需独立验证，或写 无>
- 测试先行：<是/否>
```

**subagent 档**（推荐=subagent）——subagent 是零上下文执行单元，只看 brief、看不到 brainstorm/proposal/spec/代码库/前置任务实现，必须把以下硬数据显式写入每个 Task：

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
- 测试先行：<是/否；若是，附测试基类用法 + 注解组合 + 已有测试文件路径作模板 + mock 框架>
```

> subagent 档字段覆盖了 8 类缺口：第4类场景原文、第1类代码锚点、第2类 API 契约、第3类数据来源、第5类测试模板、第7类前置产出、第8类验证+升级路径。第6类项目编码规范及其余项目原则（质量/测试/UX/性能）走 constitution.md 统一管道——build 阶段 controller 从 `.specpowers/constitution.md` 摘录全部原则注入每个 task 的 Context（subagent 隔离上下文，看不到 AGENTS.md/CLAUDE.md/constitution.md，必须显式注入），不重复进 task。

#### 字段填充指引（各字段数据来源，避免凭空填写）

- **代码锚点 / 依赖 API**：查代码库（grep 类名/方法签名定位文件，摘录方法签名与唯一代码片段）。禁止写裸行号（前置任务改动会让行号漂移）。
- **数据来源**：从 `openspec/changes/<feature>/proposal.md` 的「## 数据流契约」字段卡片逐张抄入（每张卡片含 字段名/值域/运行时来源/注入点/空值处理 五个标签）。若数据流契约未覆盖本任务所需字段，**不得自行假设**——触发第四步「跨链路入参数据来源回溯」向用户澄清。
- **前置产出契约**：从已完成的前置 Task 小节的「实现内容」提取产出的符号（常量全名/方法签名/DTO 字段）。若前置 Task 尚未实现，契约即本 feature 对该产出的约定，后续前置 Task 实现时必须遵守。
- **场景原文**：从 `openspec/changes/<feature>/specs/<capability>/spec.md` 摘录 WHEN-THEN 原文，不要只写 Scenario 名。
- **验证命令**：查项目 build 工具（有 `pom.xml` → mvn；有 `package.json` → npm/yarn；有 `pyproject.toml` → pytest）。
- **测试模板**：查项目既有测试文件（如 `src/test/` 下同类测试），摘录其测试基类、注解组合、mock 用法作为模板引用。
- **并行**：判断本任务是否与兄弟任务无文件冲突、无数据依赖。可并行的典型场景：不同模块的同级任务、同模块内只读不同文件的任务。注意：并行任务不得修改同一文件。
- **检查点**：在关键集成点（如 foundational 任务完成、某 user story 闭环、跨模块对接前）设检查点。检查点内容须可独立验证（编译通过/测试绿色/接口对接成功）。

### 第三步：执行方式推荐

tasks.md 顶部「## 推荐执行方式」注释块（模板见第二步 conductor 档）给出本特性**推荐的**执行方式，build 阶段由用户最终选择。

> 这是推荐而非强制。build 阶段会提示用户，用户拥有最终选择权。
> 注释块统一用第二步 conductor 档模板里的格式，不要另造措辞。

- 优化模式（fast）：**禁止推荐 worktree 和 subagent**（fast 仅允许 TDD 作为可选能力）

- **worktree 推荐判定**（满足以下任一才推荐/可选 worktree，否则标 不推荐）：
  - **隔离工作区收益**：存在 ≥ 2 条互不依赖且各自较长的并行任务链（每条链需多次提交/验证），在独立 worktree 推进可避免主分支索引被来回切换污染、降低半成品互相覆盖风险。
  - **多人并行开发特性**：多个任务天然分属不同模块/不同责任人，各自在自己的 worktree 推进，主分支保持干净直到合并。
  - **需在隔离工作树验证**：改动涉及破坏性重构（如大范围重命名/删除/目录迁移），需在独立 worktree 先验证再合并，避免主分支长期处于不可编译状态。
  - **不推荐 worktree 的典型场景**：单链路线性特性、任务数 ≤ 5 的连续上下文特性、或无并行需求的单点改动——worktree 切换与合并开销高于隔离收益，直接 conductor 在主分支推进更划算。
  - **与 subagent 的区别**：worktree 隔离的是 git 工作区（仍由主 session 顺序执行），subagent 隔离的是执行上下文（每任务一个零上下文执行单元）。两者可叠加（如 subagent 在各自 worktree 跑），但默认按上方判定独立标注。
  - worktree 推荐与否只影响注释块 `worktree：` 一栏的标注，不影响第二步字段档位（worktree 仍用「conductor 档」字段）。

- **subagent 推荐判定**（满足以下任一才推荐 subagent，否则默认 conductor）：
  - 任务数 ≥ 15 且存在可并行的独立链路（如 A→B 与 C→D 互不依赖，可派给 subagent 并行）
  - 算法/状态机密集任务（适合独立 subagent 跑 TDD 红绿循环，避免污染主上下文）
  - 多模块跨团队特性（任务天然边界清晰，subagent 隔离收益高）
  - **不推荐 subagent 的典型场景**：9 任务以下的 CRUD 级连续上下文特性——subagent brief 准备成本（每个 task 扩 3-5 倍篇幅 + 数据流预先排查）高于并行收益，conductor 自执行更划算。
  - **中间区间（10-14 任务）**：默认 conductor；仅当存在明确的独立并行链路（至少 2 条互不依赖的任务链）时，才升级为 subagent，并在 tasks.md 注释块说明升级理由。
  - 本判定决定第二步套用「conductor 档」还是「subagent 档」字段模板。

- **TDD 推荐判定**（满足以下任一才推荐/可选 TDD，否则标 不推荐）：
  - **核心业务逻辑 / 算法 / 状态机**：有明确输入输出契约、可独立单元测试的逻辑单元（计费、折扣、风控规则、排序/匹配算法等）——红-绿-重构收益最高。
  - **回归风险高的逻辑改动**：改动位于被多处依赖的核心路径，需先用测试锁定既有行为再重构（特性开关、兼容性分支）。
  - **不推荐 TDD 的典型场景**：纯 UI/布局调整、配置改动、胶水接线（@Autowired 连线、controller 转调 service 的薄壳）、数据迁移/脚本类无清晰单元测试落点的改动——强行 TDD 反而徒增测试桩维护负担。
  - **与执行编排的关系**：TDD 是「能力」而非「编排」，可与 conductor / worktree / subagent 任一叠加（如「推荐 subagent + 可选 TDD」）。注释块 `TDD：` 一栏据此标注，字段档位仍由 worktree/subagent 判定决定。

### 第四步：自审核

生成 tasks.md 后进行自我审核：
- 每个任务是否覆盖 delta spec 中的 Scenario
- 依赖关系是否合理
- 推荐执行方式是否符合特性特征（如 TDD 适合核心逻辑、worktree 适合多人并行等）
- **跨链路入参数据来源回溯（第3类，最关键）**：对每个涉及「跨模块/跨系统/跨进程」入参的任务（典型如回调 handler、消息消费者、对外暴露接口的下游消费者），逐个追问入参字段的**运行时数据来源**——该值在调用方那头叫什么、由谁产生、经哪条链路传过来、payload 里是否有对应字段。任一入参无法从 proposal 数据流契约卡片追溯到明确产生方与传递链路时，**不得放过**：回到上方「交互决策原则」用 AskUserQuestion 向用户澄清真实字段名与来源，缺口补齐后再定稿 tasks.md。避免把数据来源缺口拖延到 build 阶段返工——conductor 模式下本类盲区会返工，subagent 模式下会直接卡死或瞎猜。
- **前置产出契约一致性（第7类）**：依赖前置任务的每个 Task，其「前置产出契约」列出的常量名/方法签名/DTO 字段，必须与前置 Task 的「实现内容」描述一致。若前置 Task 尚未实现（本 feature 内），契约即为本 feature 对该产出的约定，后续前置 Task 实现时必须遵守此契约——subagent 无上下文，契约不一致会导致它回读前置实现或直接失败。
- **subagent 档字段完整性（第1/2/3/8类）**：若推荐=subagent，逐个 Task 核对：代码锚点是否含文件路径+方法签名（非裸行号）、依赖 API 是否含完整签名+Bean 获取方式、数据来源是否覆盖该任务全部跨链路字段、验证命令是否可执行。任一缺失，补齐后再定稿。

### 第五步：落盘 tasks.md

写入 `openspec/changes/<feature>/tasks.md`。**末尾追加「## 依赖与并行说明」小节**（最后一个 Task 之后），汇总：
- **关键路径**：列出阻塞后续任务的前置链（如 Task 1→3→6 为关键路径）
- **可并行组**：列出可同时派发的任务组（如 [Task 2, Task 4, Task 5] 可并行）
- **检查点序列**：按执行顺序列出所有标注了检查点的 Task 及其验证内容

此小节不参与 task-brief 切分（awk 只切 `### Task N` 段落，末尾的 `##` 小节不会被误切），供 build 阶段 controller 规划执行顺序与并行派发。

**禁止自动 git commit**：只生成文件，不执行 `git add` / `git commit`。提交由用户在 archive 阶段手动完成。

### 第六步：通知用户

```
✅ openspec/changes/<feature>/tasks.md 已生成（推荐执行方式 + N 个任务）
下一步：/specpowers-build
```

## 瘦身原则

- 只有一个 tasks.md 文件
- 不生成 research.md / data-model.md / contracts.md / quickstart.md
- 任务格式固定（OpenSpec 复选框 + specpowers 固定字段），禁止自由发散
- tasks.md 结构：顶部「## 推荐执行方式」注释块 + 中部 `### Task N` 序列 + 末尾「## 依赖与并行说明」小节。禁止插入 Phase/Stage 标题（破坏 task-brief 锚点）

## 后续步骤

完成后 stage 跃迁到 `plan`，下一步：`/specpowers-build`。
