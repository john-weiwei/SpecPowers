# build.md — 构建执行契约

## 触发

当用户调用 `/specpowers.build` 时加载本契约。

## 前置校验

```bash
python bridge/facade.py build --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`plan`（full 模式）/ `ready`（fast 模式）
- Full 模式：`plan.md` 必须存在
- Fast 模式：代码变更必须存在（`git diff --stat HEAD` 有输出）
- constitution.md + baseline.json 必须存在
- **Fast 模式额外**：最小验收清单 3-5 条

## 执行步骤

### 第一步：读上下文

1. 读取 `constitution.md` — 项目原则
2. 读取 `baseline.json` — 结构基线
3. Full 模式：读取 `plan.md` — 能力声明 + 任务列表
4. Fast 模式：读取先前生成的验收清单

### 第二步：实时结构门禁（三态判定）

运行确定性层提取信号：

```bash
python bridge/facade.py gate --base HEAD~1 --root .
```

获得信号列表后，agent 进行**三态判定**：

| 判定 | 条件 | 行为 |
|------|------|------|
| ✅ **通过** | 无信号 / 信号可解释 | 继续执行 |
| ⚠️ **转人工** | 有信号但不确定是否需要关注 | 记录到 audit.log（"escalate"），继续执行，archive 时清理 |
| ❌ **打回** | 明显结构违规 | 拒绝继续，要求修复后重试 |

**判定消息格式**：
```
[门禁：<通过/转人工/打回>] 信号：[<信号列表>] 证据：[<git diff 变更说明>]
```

### 第三步：能力池调度

根据 `plan.md` 中的能力声明调度执行：

| 声明 | 能力 | 说明 |
|------|------|------|
| conductor | `executing-plans` | 默认：顺序执行所有任务 |
| worktree | `using-git-worktrees` | 在独立 worktree 中执行 |
| subagent | `subagent-driven-development` | 每个任务一个子代理 |
| TDD | `test-driven-development` | 红-绿-重构循环 |

- **Fast 模式限制**：仅允许 TDD，禁止 worktree/subagent

### 第四步：执行任务

按 plan.md 任务列表顺序执行：
1. 每个任务：读取任务描述 → 执行 → 验证 → 标记完成
2. 遇到失败：记录原因 → 转人工或修复重试
3. 全部完成：进入验证阶段

### 第五步：验证

- Full 模式：逐条验证 spec.md 中的验收条件
- Fast 模式：逐条验证验收清单（3-5 条）
- 未全通过 → 转人工

### 第六步：通知用户

```
Build 完成。下一步：/specpowers.archive
```

## Fast 模式特殊规则

- 用户已**预先完成编码**（`/specpowers.fast` 声明后）
- 不执行 plan.md 中的任务（没有 plan.md）
- 直接运行结构门禁 + 验收清单验证
- 中途可通过自然语言"升级为完整流程"回退到 specify（仅一次）

## 后续步骤

完成后 stage 跃迁到 `build`，下一步：`/specpowers.archive [--force-merge-check]`
