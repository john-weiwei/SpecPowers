# fast_mode.md — 优化模式契约

## 触发

当用户调用 `/specpowers-fast "<需求>"` 时加载本契约。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade fast "<需求>" --root .
```

- 确认 stage 处于 `ready`
- constitution.md + baseline.json 存在（硬门禁，缺则拒绝）

## 优化模式流水线

```
/specpowers-fast "<需求>" → 判小+确认 → 用户编码 → /specpowers-build → /specpowers-archive
```

**跳过**：brainstorm（探索）→ specify（场景）→ plan（计划）

## 执行步骤

### 第一步：判小（agent 判定）

分析用户需求，对照判小信号集：

| 信号 | 含义 |
|------|------|
| `bugfix` | 修复缺陷 |
| `单文件` | 仅涉及 1 个文件 |
| `无新场景` | 不新增业务场景 |
| `纯配置` | 仅配置修改 |
| `纯文案` | 仅文案修改 |
| `纯重构` | 不改行为，仅重构 |

判定输出格式：
```
[理由：<命中信号 1>/<信号 2>/...，置信度：<高/中/低>]
```

**只判"小/非小"二值**。非小 → 默认走完整流程。

### 第二步：确认交互

向用户展示结构化确认：

```
📋 优化模式确认
━━━━━━━━━━━━━━━━━━
需求：[用户输入的需求]
判定：[小特性] — [理由：<信号>/...，置信度：<高/中/低>]
━━━━━━━━━━━━━━━━━━
能力声明：
  • 执行方式：conductor（默认）
  • Worktree：❌ 禁用
  • Subagent：❌ 禁用
  • TDD：[可选，用户声明]
━━━━━━━━━━━━━━━━━━
选项：
  1. go_fast — 确认优化模式，开始编码
  2. run_brainstorm — 升级为完整流程（走 brainstorm→specify→plan→build）
━━━━━━━━━━━━━━━━━━
```

### 第三步：生成验收清单（落盘为 delta spec）

Dispatcher 基于需求+对话生成 **3-5 条验收清单**，并落盘为 OpenSpec delta spec：

**文件路径**：`openspec/changes/<feature>/specs/<feature>/spec.md`

（fast 模式 capability = feature slug，独立能力；不读 proposal.md，故无 capability frontmatter）

**格式**（OpenSpec delta，**全部中文**）：

```markdown
## ADDED Requirements

### Requirement: <feature>
The system SHALL <一句话描述本特性的核心能力>。

#### Scenario: 验收点1
- **WHEN** <真实触发条件>
- **THEN** <验收项 1 的预期结果>

#### Scenario: 验收点2
- **WHEN** <触发条件>
- **THEN** <验收项 2 的预期结果>

#### Scenario: 验收点3
- **WHEN** <触发条件>
- **THEN** <验收项 3 的预期结果>
```

边界校验：
- `< 3` 条 Scenario → 拒绝，需要更多验收条件
- `> 5` 条 Scenario → 提示回退，"建议升级为完整流程"

### 第四步：用户编码

用户自行完成代码编写。

### 第五步：运行 /specpowers-build

用户编码完成后调用 `/specpowers-build`：
- 检测到 `stage=ready, mode=fast`
- 验证代码变更存在
- 运行结构门禁信号提取
- 逐条验证 delta spec 中的 Scenario（THEN 条目）

### 第六步：/specpowers-archive

fast 模式 archive **与 full 一致**：
- 调用 `openspec archive <feature> --yes --json`
- delta spec 合并到主规格 `openspec/specs/<feature>/spec.md`
- change 快照移到 `openspec/changes/archive/YYYY-MM-DD-<feature>/`
- 区别仅在于：fast 无 proposal.md（OpenSpec archive 对 proposal 内容是 informative only，不阻塞）

## 回退机制

在 build 阶段，如果用户发现优化模式不适用：
- 自然语言表达"升级为完整流程"
- stage 从 `build` → `specify`
- mode 改为 `full`
- fallback_count += 1
- **整个 state 生命周期最多 1 次回退**（reset 不清除计次）

## 约束

- 仅允许 TDD 作为可选能力，禁止 worktree/subagent
- 验收清单 3-5 条，archive 检查全勾选
- 判小误判 → 抽样审计检测，不阻断当前流程
