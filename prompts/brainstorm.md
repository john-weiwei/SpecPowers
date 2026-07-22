# brainstorm.md — 特性探索契约

## 触发

当用户调用 `/specpowers.brainstorm "<需求>"` 时加载本契约。

## 前置校验

```bash
python bridge/facade.py brainstorm "<需求>" --root .
```

- 确认 stage 处于 `ready`
- feature 名已规范化并写入 state.json
- 检查 constitution.md 存在（缺则拒绝）

## 执行步骤

### 第一步：探索项目上下文

1. 阅读 `constitution.md` 了解项目原则
2. 阅读 `baseline.json`（`.specpowers/baseline.json`）了解项目结构
3. 调用 `/brainstorming`（superpowers）进行需求探索
4. 与用户交互，提出澄清问题

### 第二步：收口 — 生成结构化决策摘要

探索结束后，**必须**产生以下结构化摘要：

```markdown
## 决策摘要

**目标**：[一句话描述本特性要达成的核心目标]

**方案选择**：[选定的技术方案 / 实现路径]

**替代方案**：
- 方案A：[描述] — [不选的原因]
- 方案B：[描述] — [不选的原因]

**边界与约束**：[明确不在本次范围内的内容和已知限制]
```

### 第三步：落盘 brief.md

将上述摘要**必然**写入 `brief.md`（项目根目录）：

```bash
python bridge/adapters/superpowers.py persist_brief  # 通过 facade 间接调用
```

或直接写入文件 `brief.md`。

### 第四步：通知用户

```
brief.md 已生成（决策摘要）。下一步：/specpowers.specify "<需求>"
```

## 判小信号映射（参考）

当 agent 在此阶段或后续阶段做"小/非小"判定时，参考以下信号：

| 信号 | 含义 | 典型场景 |
|------|------|---------|
| `bugfix` | 修复缺陷 | 修 bug、补边界条件 |
| `单文件` | 仅涉及 1 个文件 | 小改动 |
| `无新场景` | 不新增业务场景 | 重构、优化 |
| `纯配置` | 仅配置修改 | 改 yaml/json/env |
| `纯文案` | 仅文案修改 | 改 copy、i18n |
| `纯重构` | 不改行为 | 重命名、提取方法 |

## 后续步骤

完成后 stage 跃迁到 `brainstorm`，下一步：`/specpowers.specify "<需求>"`。
