# fast_mode.md — 优化模式契约

## 触发

当用户调用 `/specpowers-fast "<需求>"` 时加载本契约。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade fast "<需求>" --root .
```

- 入口校验 = 工件形态判定（目录推导）：新需求（无 change 目录）或 fast 态重入（meta.mode=fast，补填清单/重确认）放行；该需求已在 full 流水线推进中（目录存在且非 fast 态）→ 确定性层拒绝并指引走对应阶段命令
- 命令成功 = 确定性层已建 `openspec/changes/<feature>/` change 目录 + `.specpowers-meta.json`（mode=fast）+ `checklist.md` 验收清单骨架（fast 自包含，见第三步）
- constitution.md + baseline.json 存在（未初始化时由薄入口第 0 步自动补跑 specpowers-init，确定性层兜底拒绝）

## 优化模式流水线

```
/specpowers-fast "<需求>" → 判小+确认 → 填充 checklist.md → 用户编码 → /specpowers-apply → /specpowers-archive
```

**跳过**：explore（探索）→ propose（提案三件套）；v3.0 起 fast 自包含——入口即建 change 目录（meta mode=fast + checklist.md 骨架），目录推导阶段即 `fast`

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
  2. run_explore — 升级为完整流程（走 explore→propose→apply）
━━━━━━━━━━━━━━━━━━
```

### 第三步：填充验收清单（checklist.md）

`/specpowers-fast` 入口命令已由确定性层落 `openspec/changes/<feature>/checklist.md` 骨架（fast 自包含，v3.0 起验收清单的唯一落点）。Agent（认知层）基于需求+对话生成 **3-5 条验收清单**并填充该文件（已有内容时增量修订，不整份重写）：

**文件路径**：`openspec/changes/<feature>/checklist.md`

**格式**（确定性层骨架已定结构，**全部中文**）：

```markdown
# 验收清单（fast 模式）

- [ ] <验收项 1：真实触发条件 + 可验证的预期结果>
- [ ] <验收项 2>
- [ ] <验收项 3>
```

边界校验：
- `< 3` 条验收项 → 拒绝，需要更多验收条件
- `> 5` 条验收项 → 提示回退，"建议升级为完整流程"（走回退机制，见下）
- 每条验收项写成 WHEN/THEN 心智格式（触发条件 + 预期结果），供第五步逐条验证

### 第四步：用户编码

用户自行完成代码编写。

### 第五步：运行 /specpowers-apply

用户编码完成后调用 `/specpowers-apply`：
- 目录推导阶段 = `fast`（meta.mode=fast）
- 验证代码变更存在
- 运行结构门禁信号提取
- 逐条验证 checklist.md 验收项（触发条件 + 预期结果）

### 第六步：/specpowers-archive

fast 模式 archive **与 full 一致**：
- 调用 `openspec archive <feature> --yes --json`
- change 快照移到 `openspec/changes/archive/YYYY-MM-DD-<feature>/`
- 区别仅在于：fast 自包含（v3.0）——验收清单是 `checklist.md`，OpenSpec 对其无感知，主规格合并为「无 delta 需合并」（无 proposal.md 与 specs/ delta；OpenSpec archive 对 proposal 本就是 informative only，不阻塞）

## 回退机制

在 apply/fast 阶段，如果用户发现优化模式不适用（重入 `/specpowers-propose` 或自然语言表达"升级为完整流程"）：
- 确定性层自动执行 fast→full 回退：目录推导阶段回到 `propose`，mode 归 `full`
- `.specpowers/runtime.json` 的 `fallback_count` += 1
- **整个生命周期最多 1 次回退**（计次在 runtime.json，归档/reset 均不清）

## 约束

- 仅允许 TDD 作为可选能力，禁止 worktree/subagent
- 验收清单 3-5 条（checklist.md），archive/apply 检查全勾选
- 判小误判 → 抽样审计检测，不阻断当前流程
