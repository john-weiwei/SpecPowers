# archive.md — 归档收尾契约

## 触发

当用户调用 `/specpowers-archive [--force-merge-check]` 时加载本契约。

> **feature 说明**：以下路径中的 <feature> 由阶段命令的 `--feature` 参数或前台推导确定（v2.8.0 多活跃需求：前台 = 各 change 目录 `.specpowers-meta.json` 中 last_touched 最大者，目录推导；多活跃时命令必须显式 `--feature <slug>`）。同一需求的流程内锁定不变（slug 即身份）。

## 前置校验

```bash
python -m specpowers_cli.bridge.facade archive [--force-merge-check] --root .
```

Dispatcher 自动校验：
- 入口校验 = 工件形态判定（目录推导）：可入自 `apply`（tasks 已有执行进度）/ `fast`
- 重复归档检查：该 feature 已有 archive commit → 拒绝 + 提示 `git pull && /specpowers-maintain reset`

> 认知层自查（Dispatcher 不复查）：代码变更确实存在（`git diff --stat HEAD` 有输出或已有 commit）、实时门禁三态已通过。

## 三职责收尾

### 职责一：constitution 原则证据核查

轻量检查（只查证据是否存在，不做深度审计；v3.1.0 起不整份读取 constitution.md）：
- Grep `.specpowers/constitution.md` 的原则段标题（`^### `，如质量/测试/UX/性能）拿到原则清单，逐项在本次变更中核对对应证据（测试文件、日志规范落地等）——只需段标题与关键条目，无需读全文
- 缺证据 → 提示但不阻断

### 职责二：收尾产物

- 标记 `openspec/changes/<feature>/tasks.md` 任务全部完成（**跳过「## 已作废」小节**——作废任务不等价于待办，多轮迭代产物见 propose.md 迭代轮小节）
- 归档由 dispatcher 调 `openspec archive` 确定性执行（产物收敛到 `openspec/specs/` 与 `openspec/changes/archive/`，详见职责三）

### 职责三：合体后校验

**常规模式**（`mode=full`）：
- 由 dispatcher 确定性执行：调 `openspec archive <feature> --yes --json`
  （内置 delta 合并到主规格 + change 移到 archive 快照）
- 产物（proposal/specs/tasks）由 propose 阶段一次性生成，archive 零转换
- 自动判断是否需要合体后校验：
  ```
  git log <last_archive_ref>..HEAD --merges  # 非空 → 多分支
  git log <last_archive_ref>..HEAD --format=%an | sort -u | wc -l  # >1 → 多作者
  ```
- 任一命中 → **开**合体后校验（多分支结构一致性检查）
- 都不命中 → **关**（单分支，跳过）
- `--force-merge-check` → **强制开**（rebase/squash 流兜底）

**优化模式**（`mode=fast`）：
- 与 full 一致：调 `openspec archive <feature> --yes --json`，change 快照移入 archive/
- fast 自包含（v3.0）：验收清单是 change 目录 `checklist.md`（OpenSpec 对其无感知），主规格合并为「无 delta 需合并」
- 区别仅在于 fast 无 proposal.md 与 specs/ delta（OpenSpec archive 对 proposal 是 informative only，不阻塞）

## 常规模式执行

> 归档由 dispatcher 确定性执行（调 openspec archive），
> agent 只需解读 facade 输出，无需手动跑 openspec 命令。

### 第一步：前置校验（dispatcher 自动完成）

dispatcher 自动校验：
- 入口校验 = 工件形态判定（目录推导）：可入自 `apply` / `fast`
- 重复归档检查：该 feature 已有 archive commit → 拒绝
- openspec CLI 可用性（Duty 5）：不可用 → **拒绝归档**（强依赖，不降级）
- delta spec 必须存在（`openspec/changes/<feature>/specs/` 下有 spec.md）
- **场景覆盖核查**（v2.3.0，确定性，提示不阻断）：delta spec 的每个 `#### Scenario:` 应至少被 tasks.md 一个任务的「场景引用」字段覆盖（规范即验收标尺——OpenSpec 第三原则的归档前兜底）。存在未覆盖场景时输出 `⚠` 与未覆盖清单，agent 应提示用户：回 `/specpowers-propose` 补任务，或确认场景已作废；用户坚持归档则放行（archive 只转人工不打回）。fast 自包含无 delta spec（验收清单在 checklist.md），核查自动跳过

### 第二步：确定性归档（dispatcher 自动完成）

dispatcher 执行：
1. **确保 openspec 工作区**：`ensure_openspec_workspace` 创建 `openspec/{changes,specs}` 目录结构
2. **调 openspec archive**：`openspec archive <feature> --yes --json`
   - openspec 内置 delta 合并：把 change 的 delta 合并进主规格
     `openspec/specs/<capability>/spec.md`
   - openspec 把 change 移到 `openspec/changes/archive/YYYY-MM-DD-<feature>/`
3. **刷新项目级凭据**：`.specpowers/runtime.json` 的 `last_archive_ref` = 当前 HEAD（merge check 基准，归档/reset 均不清的项目级字段）；change 目录已被移入 archive 快照，该需求即从活跃清单消失（工件推导，无需任何状态删除——迭代计数等需求级事实随目录终结）；若仍有其他活跃需求，前台自动切到剩余 meta last_touched 最大者

> 产物（proposal.md/specs/**/spec.md/tasks.md）由 propose 阶段一次性写入 change 目录
> （承接 explore 设计文档结论），archive 只负责归档，无转换。

### 第三步：合体后校验（如需）

dispatcher 已提示是否触发 merge check，agent 如需额外校验：
- 以 apply 阶段 gate 门禁结论为准（结构信号与修改范围比对已覆盖）；额外核对用 `git diff --stat <last_archive_ref>..HEAD` 看有无未预期的顶层结构变更，不读 baseline.json 全文
- 有问题 → **转人工**（不打回）

### 归档产物（最终只保留两样）

| 产物 | 路径 | 说明 |
|------|------|------|
| 合并后的主规格 | `openspec/specs/<capability>/spec.md` | openspec 把本次 delta 合并进来的主规格 |
| change 快照 | `openspec/changes/archive/YYYY-MM-DD-<feature>/` | openspec 移过去的完整 change 目录（含 proposal/specs/tasks） |

### 失败处理

- openspec archive 失败时，change 目录（`openspec/changes/<feature>/`）保留供排查
- 工件形态不变（目录推导阶段仍为 apply/fast），用户可修后重试 `/specpowers-archive`
- 常见失败：delta 验证不通过（缺 SHALL/Scenario）

## 归档原则

- **只转人工、不打回**（archive 是收尾，不打回重做）
- **不提交代码**：archive 只做归档动作（openspec archive + change 目录移入 archive 快照 + runtime.json 刷新），不执行 `git add` / `git commit`，代码与产物的提交由用户自行完成
- 重复归档检测：防止同一 feature 被多人重复归档。**注意**：检测依据是 git log 中含 `specpowers.*<feature>` 的 commit——归档完成后请用户提交时在 commit message 中包含 feature 名（推荐格式 `specpowers: <feature>`），否则重复归档检测对该 feature 不生效
- **归档即该需求终结**（auto 多轮迭代语义，per-feature）：归档成功后确定性层自动清理该需求的 `.specpowers/auto_base/<feature>.json`（v2.8.0 起按 slug 隔离），change 目录移入 archive 快照后轮次推导事实源随之归档终结——该需求的下一轮 `/specpowers-auto` 必然判定为 fresh，不被残留基线误判为续跑；其余活跃需求各自的 auto_base 不受影响；裁决历史 `.specpowers/auto_decisions/<feature>.md` 保留作审计
- 完成后该需求不再出现在活跃清单（无剩余活跃需求时项目回到无活跃空转态）

## 通知用户

```
Archive 完成。Feature <name> 已归档。
提交本次改动时建议 commit message 包含 "specpowers: <feature>"（重复归档检测依据）。
准备下一轮开发：/specpowers-explore | /specpowers-propose | /specpowers-fast
```
