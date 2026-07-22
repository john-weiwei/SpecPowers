# specify.md — 场景定义契约

## 触发

当用户调用 `/specpowers.specify "<需求>"` 时加载本契约。

## 前置校验

```bash
python bridge/facade.py specify "<需求>" --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`brainstorm` / `ready`（跳过探索）/ `build`（fallback 回退）
- **从 brainstorm 进入时**：`brief.md` 必须存在
- constitution.md 必须存在

## 执行步骤

### 第一步：读取上下文

1. 读取 `constitution.md` — 了解项目原则
2. 如果从 `brainstorm` 进入 — **必然读取 `brief.md`**
3. 如果从 `ready` 进入（跳过探索）— 仅读取 constitution.md

### 第二步：生成 OpenSpec 场景

使用 OpenSpec 场景格式生成 `spec.md`：

```markdown
# Scenario

## Description
[需求描述]

## Context (from brief.md)
[若有 brief.md，引用其决策摘要]

## Acceptance Criteria
- [ ] 验收条件 1
- [ ] 验收条件 2
...

## Technical Notes
- 技术要点
```

### 第三步：落盘 spec.md

将场景内容写入 `spec.md`（项目根目录）。

### 第四步：通知用户

```
spec.md 已生成。下一步：/specpowers.plan
```

## 约束

- 场景格式遵循 OpenSpec 规范
- 验收条件必须可测试、可验证
- 若 brief.md 存在，必须在 Context 中引用

## 回退场景（fallback）

当从 `build` 回退到 `specify` 时：
- stage 从 `build` → `specify`
- mode 重置为 `full`
- fallback_count += 1
- 原因：用户认为优化模式不适用，升级为完整流程

## 后续步骤

完成后 stage 跃迁到 `specify`，下一步：`/specpowers.plan`。
