# archive.md — 归档收尾契约

## 触发

当用户调用 `/specpowers.archive [--force-merge-check]` 时加载本契约。

## 前置校验

```bash
python bridge/facade.py archive [--force-merge-check] --root .
```

Dispatcher 自动校验：
- 合法 from_stage：`build`
- 重复归档检查：该 feature 已有 archive commit → 拒绝 + 提示 `git pull && /specpowers.reset`
- 代码变更存在（`git diff --stat HEAD` 有输出或已有 commit）
- 实时门禁已通过

## 四职责收尾

### 职责一：清账（转人工挂起项）

- 检查 build 阶段记录的所有"转人工"项（audit.log 中 gate.result == "escalate"）
- 有未决项 → **拒绝归档**，提示先处理挂起的结构问题
- 已处理 → 记录到 archive 记录中

### 职责二：constitution 原则证据核查

轻量检查（只查证据是否存在，不做深度审计）：
- `constitution.md` 中的质量/测试/UX/性能原则是否在本次变更中有对应证据
- 缺证据 → 提示但不阻断

### 职责三：收尾产物

- 标记 `plan.md` 任务全部完成
- 生成 archive 记录（包含：feature、模式、时间、改动范围）

### 职责四：合体后校验

**常规模式**（`mode=full`）：
- 自动判断是否需要合体后校验：
  ```
  git log <last_archive_ref>..HEAD --merges  # 非空 → 多分支
  git log <last_archive_ref>..HEAD --format=%an | sort -u | wc -l  # >1 → 多作者
  ```
- 任一命中 → **开**合体后校验（多分支结构一致性检查）
- 都不命中 → **关**（单分支，跳过）
- `--force-merge-check` → **强制开**（rebase/squash 流兜底）

**优化模式**（`mode=fast`）：
- **退化**：跳过 delta 合并 + 合体后校验
- 执行步骤：
  1. `git add .`
  2. `git commit -m "specpowers(fast): <normalized_feature> — <改动范围摘要 1 句>"`
  3. 写 OpenSpec stub（模式标记 + hash + 改动范围说明）
  4. 原则核查

## 常规模式执行

### 第一步：收集改动范围

```bash
git diff --stat <baseline_ref>..HEAD
```

agent 基于 diff --stat 生成 3-5 句自然语言改动说明。

### 第二步：运行 OpenSpec delta 合并

```bash
npx openspec archive --delta
```

- 成功 → 继续
- 合并冲突 → 暂停，提示用户手动解决后重试 archive

### 第三步：合体后校验（如需）

- 比对当前结构与 baseline.json
- 检查无未预期的结构变更
- 有问题 → **转人工**（不打回）

### 第四步：刷新 last_archive_ref

```python
state["last_archive_ref"] = git_ref_of(root)
state["stage"] = "ready"
state["feature"] = ""
state["mode"] = "full"
```

## 归档原则

- **只转人工、不打回**（archive 是收尾，不打回重做）
- 重复归档检测：防止同一 feature 被多人重复归档
- 完成后 stage 跃迁到 `ready`，feature 清空

## 通知用户

```
Archive 完成。Feature <name> 已归档。
准备下一轮开发：/specpowers.brainstorm | .specify | .fast
```
