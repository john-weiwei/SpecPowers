# apply.md — 构建执行契约

## 触发

当用户调用 `/specpowers-apply` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 由阶段命令的 `--feature` 参数或前台推导确定（v2.8.0 多活跃需求：前台 = 各 change 目录 `.specpowers-meta.json` 中 last_touched 最大者，目录推导；多活跃时命令必须显式 `--feature <slug>`）。同一需求的流程内锁定不变（slug 即身份）。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade apply --root .
```

Dispatcher 自动校验：
- 入口校验 = 工件形态判定（目录推导）：可入自 `propose`（三件套齐）/ `apply`（续跑）/ `fast`（meta.mode=fast）；`explore`（三件套未齐）拒绝
- - Full 模式：`openspec/changes/<feature>/proposal.md` 必须存在**且含「## 数据流契约」小节**（确定性层校验段头，倒逼 propose 必须承接 explore 探索结论）
- Full 模式：`openspec/changes/<feature>/tasks.md` 必须存在
- Fast 模式：代码变更必须存在（`git diff --stat HEAD` 有输出）
- constitution.md + baseline.json 必须存在

> 认知层自查（Dispatcher 不校验）：Fast 模式 `checklist.md` 应含 3-5 条验收项（场景边界见 fast_mode.md）。

## 执行步骤

### 第一步：读上下文

1. 读取 `.specpowers/constitution.md` — 项目原则
2. Full 模式：**骨架读取** `openspec/changes/<feature>/tasks.md`（v3.1.0）——Grep 模式串 `^## 推荐执行方式|^修改范围：|^### Task|^- \[[ x]\]|^- 依赖：|^- 并行：|^- 检查点：` 拿到执行方式推荐 + 任务清单结构（第二步展示与派发规划所需）；任务执行明细**按第二步确认的执行方式分流读取**（见下方分流规则）；骨架命中数与文件规模明显不符（如非空文件 0 命中）→ 回退全文读取
3. Full 模式：读取 `openspec/changes/<feature>/specs/<capability>/spec.md` — delta spec 的 Scenario（验证用，全量读取）；Fast 模式：读取 `openspec/changes/<feature>/checklist.md` — 验收清单（验证用）

> **baseline.json 不再读取（v3.1.0）**：结构基线是防越界参考，真正的越界检测由第三步 gate 确定性比对（脚本自行读取 baseline.json，不占上下文）。认知层只守纪律：不新建顶层目录、不新增依赖类型——越界由 gate 兜底转人工。

**tasks.md 读取分流规则（v3.1.0，按「谁执行」分流）**：

| 执行方式 | tasks.md 读取 | 理由 |
|---------|--------------|------|
| conductor / worktree / TDD | 确认执行方式后**全文读取**（补读骨架未命中的任务明细） | 主会话亲自执行，执行清单漏读代价不对称（漏执行/执行错任务） |
| subagent | **保持骨架读取**，任务明细不进主会话 | 主会话只派发与校验；执行明细由 task_brief 脚本直出给 subagent（见第五步），漏读风险由 subagent 侧 brief 承载 |

### 第二步：选择执行方式

向用户展示 tasks.md 顶部注释块的推荐，让用户确认或更改执行方式：

```
apply 阶段 — 选择执行方式
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
- 用户选择后**必须调用确定性层记录**到目标需求 change 目录 `.specpowers-meta.json`（`execution_mode` 字段）：
  ```bash
  python -m specpowers_cli.bridge.facade record-execution-mode <conductor|worktree|subagent|tdd> --root .
  ```
  - 确定性层会校验：执行方式合法 + fast 模式 worktree/subagent 禁用兜底
  - 校验失败（如 fast 选了 subagent）会非 0 退出并给出原因，须据此让用户重选

### 第三步：结构门禁（三态判定：结构基线 + 修改范围）

运行确定性层提取信号（v2.3.0 起输出附 `scope` 修改范围比对结果）：

```bash
python -m specpowers_cli.bridge.facade gate --base HEAD~1 --root .
```

输出示例：

```json
{"signals": [], "base": "HEAD~1", "diff_lines": 42,
 "scope": {"declared": ["src/order", "tests/order"], "out_of_scope": ["src/payment/x.java"], "status": "out_of_scope"}}
```

`scope` 字段说明（来自 tasks.md 顶部注释块「修改范围：」声明，propose 生成；仅 full 模式有效——fast 模式或无 feature 时输出 JSON 不带 scope 键，不做范围比对）：

| scope.status | 含义 | 处理 |
|--------------|------|------|
| `pass` | 实际改动全部落在声明范围内 | 无需处理 |
| `out_of_scope` | 存在越界改动（`out_of_scope` 列出越界文件） | **转人工**：列出越界文件请用户裁决（放行改动并建议 propose 更新声明 / 回退越界改动） |
| `undeclared` | tasks.md 缺「修改范围：」声明（v2.2 旧产物兼容） | 提示用户可重入 /specpowers-propose 补声明，本轮跳过范围比对 |

> - 越界判定是确定性路径前缀比对，但"越界是否可接受"由人裁决——agent 不得以"顺手改了相关代码"为由静默放行越界文件
> - 流水线工件（`openspec/`、`.specpowers/`、`docs/specpowers/`）已由确定性层豁免，不判越界
> - **列表截断（v3.1.0）**：`signals` / `out_of_scope` / `declared` 超过 20 条时输出截取前 20 条并附 `*_total` 计数与 `truncated: true`——转人工时以计数说明规模，完整明细按下方 report 句柄回查
> - **判定留痕**：输出存在结构信号或越界改动时，完整判定 JSON 会落盘到 `.specpowers/reports/gate-<时间戳>.json`，输出 JSON 附 `report` 句柄路径——转人工/打回说明中给用户句柄路径即可，人机按路径回查完整明细，不必把全部明细塞进消息（该目录属个人本机留痕，已在 init 生成的 .gitignore 中排除，无需提交）

获得信号列表后，agent 进行**三态判定**：

| 判定 | 条件 | 行为 |
|------|------|------|
| ✅ **通过** | 无结构信号（或信号可解释）且 scope 无越界 | 继续执行 |
| ⚠️ **转人工** | scope=out_of_scope / scope=undeclared / 结构信号不确定 | 提示用户处理挂起的结构或范围问题，继续执行 |
| ❌ **打回** | 明显结构违规 | 拒绝继续，要求修复后重试 |

**判定消息格式**：
```
[门禁：<通过/转人工/打回>] 信号：[<信号列表>] 范围：[<scope 结论：pass / 越界文件清单 / 未声明>] 证据：[<git diff 变更说明>]
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
2. subagent 模式：brief 由确定性脚本直出，**禁止手工转写**（v3.1.0——转写 = 主会话读全文 + 重输出一遍，双向浪费且可能失真）：

   ```bash
   python scripts/task_brief.py openspec/changes/<feature>/tasks.md <N> --spec openspec/changes/<feature>/specs/<capability>/spec.md
   ```

   脚本输出该 task 整段 brief + 顶部「推荐执行方式」注释块 + 从 delta spec 确定性抽取的「关联场景原文」（tasks.md 场景引用只存名字，原文由脚本附上）；输出整体作为 subagent Context 的任务部分。场景原文未命中时脚本末尾有降级提示，此时才由 controller 从 spec 手工补充。
   - **并行派发**：参考每个 task 的「并行」字段与「依赖与并行说明」的可并行组，将无依赖冲突的 task 并行派发给多个 subagent（注意：并行任务不得修改同一文件）。有依赖的 task 须等前置完成后再派发。
   - **检查点放行**：subagent 返回后，controller 先按该 task「检查点」字段快速校验，通过再进入 spec-reviewer 审查；不通过则原 subagent 修复重试。
   - **Context 拼装（关键）**：subagent 是隔离上下文，不继承主会话的项目规则（实测确认 subagent 看不到工作区 AGENTS.md/CLAUDE.md/constitution.md），controller 必须把以下内容随每个 task 的 Context 一并注入：
     - **constitution.md 相关原则**——从 `.specpowers/constitution.md` 按 task 相关性摘录（质量/测试/UX/性能中与本任务相关的条目），**编码规范对每个 task 都必带**。这是 subagent 遵守项目级约束（禁止行尾注释、方法≤60行、日志格式、测试策略、性能要求等）的唯一途径，缺则 subagent 完全无视。
     - **跨任务背景**：该 task 在 tasks.md「前置产出契约/代码锚点/数据来源」之外、但实现所需的架构位置与共享约定。
   Context 拼装时按 task 相关性裁剪：与该 task 无关的原则可省略，但编码规范对每个 task 都必带。
3. 遇到失败：记录原因 → 转人工或修复重试
4. 全部完成：进入验证阶段

### 第六步：验证

- Full 模式：逐条验证 delta spec（`specs/<capability>/spec.md`）中的 `#### Scenario` 的 **THEN** 条目
- Fast 模式：逐条验证 `checklist.md` 的验收项（3-5 条，触发条件 + 预期结果）
- **跨链路字段核对**：涉及跨链路字段的 THEN，对照 `openspec/changes/<feature>/proposal.md` 的「数据流契约」核对字段来源/值域是否与实现一致；不一致（如实现取了错误的注入点、值域不符）记为未通过
- 未全通过 → 转人工

### 第七步：通知用户

```
Build 完成。下一步：/specpowers-archive
```

## Fast 模式特殊规则

- 用户已**预先完成编码**（`/specpowers-fast` 声明后）
- 不执行 tasks.md 中的任务（fast 无 tasks.md，验收清单在 `checklist.md`）
- 直接运行结构门禁 + checklist.md 验收项逐条验证
- 中途可通过自然语言"升级为完整流程"回退到 propose（仅一次，计次在 `.specpowers/runtime.json`）

## 迭代轮：只执行未完成且未作废的任务（多轮迭代，auto 与人工模式通用）

当本轮是迭代轮（轮次 ≥ 1——v3.0 起轮次即工件推导值：design-round-N.md 与 tasks「## Round N」小节的最大值；入口可以是 `/specpowers-propose`、`/specpowers-explore` 重入识别（人工模式，目录推导自动识别）或 `/specpowers-auto`（无人值守））时，tasks.md 已按 propose 契约完成分轮差异同步，apply 执行范围收敛为：

- **只执行未勾选（`[ ]`）且不在「## 已作废」小节的任务**；跨轮保留的 `[x]` 任务视为已交付，跳过
- 执行前先核对：任务引用的 spec 场景在当前 delta spec 中仍存在（propose 同步与 spec 修订之间若出现漂移，以 spec 为准并记录裁决）
- 本轮新增任务的执行方式仍按第二步确认（新轮 `execution_mode` 已被确定性层清空，按 tasks.md 顶部推荐或默认 conductor 重新确认并 `record-execution-mode` 记录）
- 验证阶段（第六步）按**当前 delta spec 全量 Scenario** 验证（含历史轮场景回归），确保迭代未破坏既有行为

> **读取边界（v3.1.0 修订）**：propose 侧三件套修订已局部化（骨架两级读取 + Edit 化，见 propose.md 迭代轮小节）；apply 侧按「谁执行」分流——conductor/TDD/worktree 主会话亲自执行，tasks.md 全文与 delta spec 全量 Scenario（第六步含历史轮回归验证）是执行与验证的质量硬边界，禁止局部化裁剪；**subagent 模式主会话只派发与校验，tasks.md 保持骨架读取**（执行明细由 task_brief 脚本直出给 subagent，漏执行风险由 subagent 侧 brief 承载），但 delta spec 全量 Scenario 仍须全文读（第六步验证由 controller 执行）。

## 后续步骤

完成后目录推导阶段为 `apply`（tasks 已有执行进度），下一步：`/specpowers-archive [--force-merge-check]`
