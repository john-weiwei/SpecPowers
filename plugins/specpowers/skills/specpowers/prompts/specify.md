# specify.md — 场景定义契约

## 触发

当用户调用 `/specpowers-specify "<需求>"` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 来自 state.json 的 feature 字段（brainstorm/fast 阶段确定并锁定，同一流程不变）。

## 重入识别（人工模式迭代轮入口）

执行前置校验**之前**，先读 `.specpowers/state.json` 判断本次调用是否为迭代重入：

- **触发条件**：`stage` ∈ {`plan`, `build`} 且 `feature` 非空（活跃未归档——归档后 stage 已回 `ready`，不在此列）。这表明用户要在**同一个未归档需求**上做调整，需求身份由归档状态唯一决定，调整必须落在当前 change 目录的当前 spec 文件内。
- **交互确认**（必须，禁止静默切换轮次）：

  ```
  检测到未归档需求 <feature>（stage=<stage>，当前 Round <iteration_count>）。本次重入意图是？
  1. 开启 Round <iteration_count+1> 迭代轮 —— 调整/优化需求，调整记录进当前 spec 文件
  2. 取消 —— 继续现有流程（/specpowers-build 或 /specpowers-archive）
  ```

  - `stage=build` 且 `mode=fast` 时追加选项：`3. fast→full 流程回退（原 fallback 语义：消耗整个生命周期唯一 1 次回退额度，放弃 fast 产物重新完整生成 spec）`
  - 用户给出调整描述（命令参数）时在选项 1 中原样带入，作为本轮修订依据
- **确认开启迭代轮**：调 `facade iterate [--instruction "<调整描述>"] --root .`（确定性层完成：stage → `specify`、feature 锁定不变、`iteration_count += 1`、不占 fallback 额度）。成功后**不要再调 `facade specify`**（状态已就位），直接按下方「迭代轮」小节增量修订 spec.md
- **选择取消**：不改任何状态，向用户说明当前可选步骤后结束
- **未触发**（stage 为 `ready`/`brainstorm`/`specify`）：走正常流程——stage=`specify` 的重跑属迭代轮**续作**（`iteration_count ≥ 1` 时按迭代轮小节执行，轮次不变），其余按前置校验常规进入

## 前置校验

```bash
python -m specpowers_cli.bridge.facade specify "<需求>" --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`brainstorm` / `ready`（跳过探索）/ `build`（fallback 回退）/ `specify`（迭代轮续作，自环幂等）
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

## 迭代轮：spec.md 增量修订（多轮迭代，auto 与人工模式通用）

当本轮是迭代轮（`state.json` 的 `iteration_count` ≥ 1——入口可以是 `/specpowers-specify`、`/specpowers-brainstorm` 重入识别确认（人工模式，见「重入识别」小节）或 `/specpowers-auto`（无人值守））时，specify 不做盲目重写，改为**对照本轮有效场景清单增量修订**现有 delta spec（`openspec/changes/<feature>/specs/<capability>/spec.md`）。场景清单来源：auto 迭代轮取八要素「必测场景清单」；人工迭代轮取用户本轮调整描述与现有 spec 的合并结果：

| 现有场景 vs 本轮清单 | 处理 |
|----------------------|------|
| 场景仍存在但描述有变 | 按本轮清单更新 WHEN/THEN（保持 Scenario 名稳定，便于 plan/build 追踪） |
| 场景仍存在且无变化 | 原样保留 |
| 场景已从清单删除 | 从 delta 中移除该 Scenario（归档前 delta 只在 change 内，移除安全） |
| 清单新增场景 | 按 OpenSpec delta 格式追加 |

- 修订完成后在 spec.md 末尾追加一行 HTML 注释记录轮次痕迹：`<!-- Round <N> 修订：+<新增数> / ~<更新数> / -<删除数> -->`
- **硬底线**：无论多小的迭代，本轮调整必须反映到 spec.md（这是「归档前所有调整记录在当前 spec 文件内」的落点），轻量迭代也不例外
- 首轮（`iteration_count` = 0）行为不变：按上方执行步骤全新生成

## 回退场景（fallback）

当从 `build` 回退到 `specify` 时：
- stage 从 `build` → `specify`
- mode 重置为 `full`
- fallback_count += 1
- 原因：用户认为优化模式不适用，升级为完整流程

## 后续步骤

完成后 stage 跃迁到 `specify`，下一步：`/specpowers-plan`。
