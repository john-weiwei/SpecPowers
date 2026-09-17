# build.md — 构建执行契约

## 触发

当用户调用 `/specpowers-build` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 来自 state.json 的 feature 字段（brainstorm/fast 阶段确定并锁定，同一流程不变）。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade build --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`plan`（full 模式）/ `ready`（fast 模式）
- Full 模式：`openspec/changes/<feature>/tasks.md` 必须存在
- Fast 模式：代码变更必须存在（`git diff --stat HEAD` 有输出）
- constitution.md + baseline.json 必须存在
- **Fast 模式额外**：delta spec 含 3-5 条 Scenario

## 执行步骤

### 第一步：读上下文

1. 读取 `.specpowers/constitution.md` — 项目原则
2. 读取 `.specpowers/baseline.json` — 结构基线
3. Full 模式：读取 `openspec/changes/<feature>/tasks.md` — 执行方式推荐（顶部注释块） + 任务列表
4. Full/Fast 模式：读取 `openspec/changes/<feature>/specs/<capability>/spec.md` — delta spec 的 Scenario（验证用）

### 第二步：选择执行方式

向用户展示 tasks.md 顶部注释块的推荐，让用户确认或更改执行方式：

```
build 阶段 — 选择执行方式
━━━━━━━━━━━━━━━━━━━━━━━
tasks.md 推荐：conductor（顺序执行）
━━━━━━━━━━━━━━━━━━━━━━━
可选：
  1. conductor — executing-plans（顺序执行，默认）
  2. worktree  — using-git-worktrees（隔离工作区并行）
  3. subagent  — subagent-driven-development（每任务一个子代理）
  4. TDD       — test-driven-development（红-绿-重构）

你的选择：[1-4，回车选推荐]
━━━━━━━━━━━━━━━━━━━━━━━
```

- fast 模式：仅可选 conductor / TDD，禁止 worktree / subagent
- 用户选择后**必须调用确定性层记录**到 state.json（`execution_mode` 字段）：
  ```bash
  python -m specpowers_cli.bridge.facade record-execution-mode <conductor|worktree|subagent|tdd> --root .
  ```
  - 确定性层会校验：执行方式合法 + fast 模式 worktree/subagent 禁用兜底
  - 校验失败（如 fast 选了 subagent）会非 0 退出并给出原因，须据此让用户重选

### 第三步：结构门禁（三态判定）

运行确定性层提取信号：

```bash
python -m specpowers_cli.bridge.facade gate --base HEAD~1 --root .
```

获得信号列表后，agent 进行**三态判定**：

| 判定 | 条件 | 行为 |
|------|------|------|
| ✅ **通过** | 无信号 / 信号可解释 | 继续执行 |
| ⚠️ **转人工** | 有信号但不确定是否需要关注 | 提示用户处理挂起的结构问题，继续执行 |
| ❌ **打回** | 明显结构违规 | 拒绝继续，要求修复后重试 |

**判定消息格式**：
```
[门禁：<通过/转人工/打回>] 信号：[<信号列表>] 证据：[<git diff 变更说明>]
```

### 第四步：能力池调度

根据用户选择的执行方式，调用对应的 superpowers 技能：

| 执行方式 | superpowers 技能 | 说明 |
|---------|-----------------|------|
| conductor | `executing-plans` | 顺序执行所有任务 |
| worktree | `using-git-worktrees` | 在独立 worktree 中执行 |
| subagent | `subagent-driven-development` | 每个任务一个子代理 |
| TDD | `test-driven-development` | 红-绿-重构循环 |

- **Fast 模式限制**：仅允许 conductor / TDD，禁止 worktree / subagent（已在第二步由确定性层 `record-execution-mode` 硬校验兜底，无需在第四步重复判断）

### 第五步：执行任务

按 tasks.md 的 `### Task N` 任务顺序执行，参考末尾「## 依赖与并行说明」规划执行顺序：
1. 每个任务：读取任务描述 → 执行 → 按该 task「检查点」字段自验 → 在 tasks.md 勾选 `- [x]`。检查点未通过的 task 不得勾选，须修复后重验。
2. subagent 模式：用 `scripts/task-brief <tasks.md> N` 提取任务 brief 交给子代理。
   - **并行派发**：参考每个 task 的「并行」字段与「依赖与并行说明」的可并行组，将无依赖冲突的 task 并行派发给多个 subagent（注意：并行任务不得修改同一文件）。有依赖的 task 须等前置完成后再派发。
   - **检查点放行**：subagent 返回后，controller 先按该 task「检查点」字段快速校验，通过再进入 spec-reviewer 审查；不通过则原 subagent 修复重试。
   - **Context 拼装（关键）**：subagent 是隔离上下文，不继承主会话的项目规则（实测确认 subagent 看不到工作区 AGENTS.md/CLAUDE.md/constitution.md），controller 必须把以下内容随每个 task 的 Context 一并注入：
     - **constitution.md 全部原则**（质量/测试/UX/性能 + 编码规范）——从 `.specpowers/constitution.md` 摘录。这是 subagent 遵守项目级约束（禁止行尾注释、方法≤60行、日志格式、测试策略、性能要求等）的唯一途径，缺则 subagent 完全无视。
     - **跨任务背景**：该 task 在 tasks.md「前置产出契约/代码锚点/数据来源」之外、但实现所需的架构位置与共享约定。
   Context 拼装时按 task 相关性裁剪：与该 task 无关的原则可省略，但编码规范对每个 task 都必带。
3. 遇到失败：记录原因 → 转人工或修复重试
4. 全部完成：进入验证阶段

### 第六步：验证

- Full 模式：逐条验证 delta spec（`specs/<capability>/spec.md`）中的 `#### Scenario` 的 **THEN** 条目
- Fast 模式：逐条验证 delta spec 的 Scenario（3-5 条）
- **跨链路字段核对**：涉及跨链路字段的 THEN，对照 `openspec/changes/<feature>/proposal.md` 的「数据流契约」核对字段来源/值域是否与实现一致；不一致（如实现取了错误的注入点、值域不符）记为未通过
- 未全通过 → 转人工

### 第七步：通知用户

```
Build 完成。下一步：/specpowers-archive
```

## Fast 模式特殊规则

- 用户已**预先完成编码**（`/specpowers-fast` 声明后）
- 不执行 tasks.md 中的任务（fast 无 tasks.md，只有 delta spec）
- 直接运行结构门禁 + delta spec Scenario 验证
- 中途可通过自然语言"升级为完整流程"回退到 specify（仅一次）

## 迭代轮：只执行未完成且未作废的任务（多轮迭代，auto 与人工模式通用）

当本轮是迭代轮（`state.json` 的 `iteration_count` ≥ 1——入口可以是 `/specpowers-specify`、`/specpowers-brainstorm` 重入识别确认（人工模式）或 `/specpowers-auto`（无人值守））时，tasks.md 已按 plan 契约完成分轮差异同步，build 执行范围收敛为：

- **只执行未勾选（`[ ]`）且不在「## 已作废」小节的任务**；跨轮保留的 `[x]` 任务视为已交付，跳过
- 执行前先核对：任务引用的 spec 场景在当前 delta spec 中仍存在（plan 同步与 spec 修订之间若出现漂移，以 spec 为准并记录裁决）
- 本轮新增任务的执行方式仍按第二步确认（新轮 `execution_mode` 已被确定性层清空，按 tasks.md 顶部推荐或默认 conductor 重新确认并 `record-execution-mode` 记录）
- 验证阶段（第六步）按**当前 delta spec 全量 Scenario** 验证（含历史轮场景回归），确保迭代未破坏既有行为

## 后续步骤

完成后 stage 跃迁到 `build`，下一步：`/specpowers-archive [--force-merge-check]`
