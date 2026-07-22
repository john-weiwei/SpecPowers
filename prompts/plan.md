# plan.md — 实现计划契约

## 触发

当用户调用 `/specpowers.plan` 时加载本契约。

## 前置校验

```bash
python bridge/facade.py plan --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`specify`
- `spec.md` 必须存在（缺则拒绝）

## 执行步骤

### 第一步：读取 spec.md

加载已生成的 `spec.md` 作为任务拆分的输入。

### 第二步：瘦身 writing-plans + 合并 spec-kit tasks

调用 superpowers 的 `writing-plans` 技能，但进行瘦身：

**产物归并**：不产生多个 plan 文件，所有内容合并到单一 `plan.md`。

**任务单元固定字段**：

每个任务必须包含以下字段：

```markdown
### Task N: [任务描述]

- **Scenario Pointer**: [关联 spec.md 中的场景/验收条件]
- **Acceptance Criteria**: [本任务的验收标准]
- **Dependencies**: [依赖的前置任务，无则写 none]
- **Test-First**: [yes/no — 是否要求测试先行]
- **Capability**: [conductor | worktree | subagent | TDD — 执行能力声明]
```

### 第三步：能力声明

在 plan.md 开头声明本特性的执行能力需求：

```markdown
## Capability Declaration

- **Executor**: conductor（默认）
- **Worktree**: [required / optional / none]
- **Subagent**: [required / optional / none]
- **TDD**: [enabled / disabled]
```

- 优化模式（fast）：**禁止 worktree 和 subagent**
- 常规模式：默认 conductor，其余由任务声明驱动

### 第四步：自审核

生成 plan.md 后进行自我审核：
- 每个任务是否覆盖 spec.md 中的验收条件
- 依赖关系是否合理
- 能力声明是否与任务匹配

### 第五步：落盘 plan.md

写入 `plan.md`（项目根目录）。

### 第六步：通知用户

```
plan.md 已生成（含能力声明 + N 个任务）。下一步：/specpowers.build
```

## 瘦身原则

- 只有一个 plan.md 文件
- 不生成 research.md / data-model.md / contracts.md / quickstart.md
- tasks 由 spec-kit 分解，合并进 plan.md（不单独生成 tasks.md）
- 任务格式固定，禁止自由发散

## 后续步骤

完成后 stage 跃迁到 `plan`，下一步：`/specpowers.build`。
