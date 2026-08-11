# archive.md — 归档收尾契约

## 触发

当用户调用 `/specpowers-archive [--force-merge-check]` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 来自 state.json 的 feature 字段（brainstorm/fast 阶段确定并锁定，同一流程不变）。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade archive [--force-merge-check] --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`build`
- 重复归档检查：该 feature 已有 archive commit → 拒绝 + 提示 `git pull && /specpowers-reset`
- 代码变更存在（`git diff --stat HEAD` 有输出或已有 commit）
- 实时门禁已通过

## 三职责收尾

### 职责一：constitution 原则证据核查

轻量检查（只查证据是否存在，不做深度审计）：
- `.specpowers/constitution.md` 中的质量/测试/UX/性能原则是否在本次变更中有对应证据
- 缺证据 → 提示但不阻断

### 职责二：收尾产物

- 标记 `openspec/changes/<feature>/tasks.md` 任务全部完成
- 归档由 dispatcher 调 `openspec archive` 确定性执行（产物收敛到 `openspec/specs/` 与 `openspec/changes/archive/`，详见职责三）

### 职责三：合体后校验

**常规模式**（`mode=full`）：
- 由 dispatcher 确定性执行：调 `openspec archive <feature> --yes --json`
  （内置 delta 合并到主规格 + change 移到 archive 快照）
- 产物（proposal/specs/tasks）由前面阶段增量生成，archive 零转换
- 自动判断是否需要合体后校验：
  ```
  git log <last_archive_ref>..HEAD --merges  # 非空 → 多分支
  git log <last_archive_ref>..HEAD --format=%an | sort -u | wc -l  # >1 → 多作者
  ```
- 任一命中 → **开**合体后校验（多分支结构一致性检查）
- 都不命中 → **关**（单分支，跳过）
- `--force-merge-check` → **强制开**（rebase/squash 流兜底）

**优化模式**（`mode=fast`）：
- 与 full 一致：调 `openspec archive <feature> --yes --json`
- delta spec（fast 阶段落盘的验收清单）合并到主规格
- 区别仅在于 fast 无 proposal.md（OpenSpec archive 对 proposal 是 informative only，不阻塞）

## 常规模式执行

> 归档由 dispatcher 确定性执行（调 openspec archive），
> agent 只需解读 facade 输出，无需手动跑 openspec 命令。

### 第一步：前置校验（dispatcher 自动完成）

dispatcher 自动校验：
- 合法 from_stage：`build`
- 重复归档检查：该 feature 已有 archive commit → 拒绝
- openspec CLI 可用性（Duty 5）：不可用 → **拒绝归档**（强依赖，不降级）
- delta spec 必须存在（`openspec/changes/<feature>/specs/` 下有 spec.md）

### 第二步：确定性归档（dispatcher 自动完成）

dispatcher 执行：
1. **确保 openspec 工作区**：`ensure_openspec_workspace` 创建 `openspec/{changes,specs}` 目录结构
2. **调 openspec archive**：`openspec archive <feature> --yes --json`
   - openspec 内置 delta 合并：把 change 的 delta 合并进主规格
     `openspec/specs/<capability>/spec.md`
   - openspec 把 change 移到 `openspec/changes/archive/YYYY-MM-DD-<feature>/`
3. **刷新 state**：`last_archive_ref` = 当前 HEAD，stage → `ready`，feature 清空

> 产物（proposal.md/specs/**/spec.md/tasks.md）由 brainstorm/specify/plan 阶段
> 增量写入 change 目录，archive 只负责归档，无转换。

### 第三步：合体后校验（如需）

dispatcher 已提示是否触发 merge check，agent 如需额外校验：
- 比对当前结构与 baseline.json
- 检查无未预期的结构变更
- 有问题 → **转人工**（不打回）

### 归档产物（最终只保留两样）

| 产物 | 路径 | 说明 |
|------|------|------|
| 合并后的主规格 | `openspec/specs/<capability>/spec.md` | openspec 把本次 delta 合并进来的主规格 |
| change 快照 | `openspec/changes/archive/YYYY-MM-DD-<feature>/` | openspec 移过去的完整 change 目录（含 proposal/specs/tasks） |

### 失败处理

- openspec archive 失败时，change 目录（`openspec/changes/<feature>/`）保留供排查
- state 不跃迁，用户可修后重试 `/specpowers-archive`
- 常见失败：delta 验证不通过（缺 SHALL/Scenario）

## 归档原则

- **只转人工、不打回**（archive 是收尾，不打回重做）
- 重复归档检测：防止同一 feature 被多人重复归档
- 完成后 stage 跃迁到 `ready`，feature 清空

## 通知用户

```
Archive 完成。Feature <name> 已归档。
准备下一轮开发：/specpowers-brainstorm | /specpowers-specify | /specpowers-fast
```
