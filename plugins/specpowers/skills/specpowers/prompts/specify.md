# specify.md — 场景定义契约

## 触发

当用户调用 `/specpowers-specify "<需求>"` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 来自 state.json 的 feature 字段（brainstorm/fast 阶段确定并锁定，同一流程不变）。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade specify "<需求>" --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`brainstorm` / `ready`（跳过探索）/ `build`（fallback 回退）
- **从 brainstorm 进入时**：`openspec/changes/<feature>/proposal.md` 必须存在**且含「## 数据流契约」小节**（确定性层校验段头，倒逼 brainstorm 必须完成探索）
- `.specpowers/constitution.md` 必须存在

## 执行步骤

### 第一步：读取上下文

1. 读取 `.specpowers/constitution.md` — 了解项目原则
2. 如果从 `brainstorm` 进入 — **必然读取 `openspec/changes/<feature>/proposal.md`**，并**重点读取其中的「## 数据流契约」小节**（字段来源/值域是 Scenario WHEN/THEN 的输入依据）
3. 如果从 `ready` 进入（跳过探索）— 仅读取 constitution.md

### 第二步：解析 capability

从 proposal.md 顶部 YAML frontmatter 解析 capability：
- 有 `capability: <名称>` → 共享已有能力（迭代场景），delta 写到 `specs/<capability>/spec.md`
- 无 frontmatter → capability = feature slug（独立能力），delta 写到 `specs/<feature>/spec.md`

### 第三步：生成 OpenSpec delta spec

使用 **OpenSpec delta 格式**生成 spec.md，**全部使用中文**。

> 这是 change 的核心规范文件，build 阶段验证、archive 阶段合并主规格都依赖它。
> **WHEN/THEN 必须从需求真实提取**，不要填空模板（如"用户执行相关操作"这种无意义内容）。

格式：

```markdown
## ADDED Requirements

### Requirement: <feature>
<本 requirement 描述 feature 要满足的核心能力，含 SHALL 关键字>
The system SHALL <一句话描述 feature 的核心能力>。

#### Scenario: <场景名 1>
- **WHEN** <真实的触发条件，从需求提取>
- **THEN** <真实的预期结果，可测试可验证>

#### Scenario: <场景名 2>
- **WHEN** <触发条件>
- **THEN** <预期结果>
```

**要求**（OpenSpec validator 硬约束）：
- 必须含 `## ADDED Requirements` 段头
- 段内至少一条 `### Requirement: <name>`，name 用 feature slug
- requirement body 必须含 `SHALL` 或 `MUST`
- 每个 requirement 至少一个 `#### Scenario:`
- 每个 Scenario 必须含 `**WHEN**` 和 `**THEN**`

**requirement 名固定用 feature slug**（迭代标识，保证跨次归档不重名冲突）。

**Scenario 与数据流契约的关系**：涉及跨链路字段的 Scenario，其 WHEN/THEN 必须能从 proposal 的「数据流契约」字段来源/值域导出，**不得引入数据流契约之外的未知字段来源**。若发现 Scenario 需要某字段但数据流契约未覆盖，说明 brainstorm 探索有缺口，应回退到 `/specpowers-brainstorm` 补全，而非在 specify 凭空假设。

### 第四步：落盘 delta spec

将内容写入 `openspec/changes/<feature>/specs/<capability>/spec.md`（capability 来自第二步）。

### 第五步：通知用户

```
✅ openspec/changes/<feature>/specs/<capability>/spec.md 已生成。
下一步：/specpowers-plan
```

## 约束

- delta 格式严格遵循 OpenSpec 规范（validator 会校验）
- Scenario 的 WHEN/THEN 必须真实、可测试、可验证，禁止填空
- 若 proposal.md 存在，capability 必须从其 frontmatter 解析
- 迭代场景（capability ≠ feature）：requirement 名用 feature slug，与主规格已有 requirement 累积不冲突

## 回退场景（fallback）

当从 `build` 回退到 `specify` 时：
- stage 从 `build` → `specify`
- mode 重置为 `full`
- fallback_count += 1
- 原因：用户认为优化模式不适用，升级为完整流程

## 后续步骤

完成后 stage 跃迁到 `specify`，下一步：`/specpowers-plan`。
