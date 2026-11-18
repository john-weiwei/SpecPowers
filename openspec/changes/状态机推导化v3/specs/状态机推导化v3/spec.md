## ADDED Requirements

### Requirement: 状态机推导化v3

流水线状态完全从 `openspec/changes/` 工件推导：系统的流水线状态（阶段 / 轮次 / 活跃清单 / 前台 / 归档基准）SHALL 完全从 `openspec/changes/` 目录形态与 change 目录 meta 推导，`state.json` 退役，dispatcher 校验依据为工件形态判定而非状态缓存。

#### Scenario: stage 工件推导判定

- **WHEN** change 目录三件套齐且 tasks.md 存在部分勾选任务，调用 `derive_stage`
- **THEN** 返回 `apply`；propose 入口校验依据该推导值而非任何缓存字段，tasks 全勾时可进入 archive

#### Scenario: 活跃清单目录推导防僵尸

- **WHEN** 用户手动删除或归档某个 change 目录后执行任意推进类 facade 命令
- **THEN** 该需求不再出现在活跃清单（活跃权威 = 目录扫描），多活跃路由保护按目录推导拒绝未指名命令，无僵尸条目可被路由

#### Scenario: 旧 state 自动迁移退役

- **WHEN** 旧项目（schema 2 `state.json` 存在）首次执行任意 facade 命令
- **THEN** features 条目转换：有 change 目录者补齐 meta（design_doc/mode/execution_mode/created_at 迁入），`fallback_count`/`last_archive_ref` 写入 `.specpowers/runtime.json`，`state.json` 改名 `state.json.bak`；迁移幂等（重复执行跳过），此后所有命令零 state 读写

#### Scenario: 迭代轮目录推导识别

- **WHEN** 未归档需求（change 目录存在）重入 `/specpowers-propose` 或 `/specpowers-explore`
- **THEN** 由 `derive_stage` 与目录存在性识别为同需求迭代轮（Round = design-round-N 最大值与 tasks Round 小节推导 +1，写侧维护），`facade iterate` 子命令不存在；auto 模式 `auto-new-round` 保留并继续写 `auto_base.rounds`

#### Scenario: reset 删除工件目录

- **WHEN** 用户执行 `facade reset --feature <slug>` 并确认（或 `--force`）
- **THEN** `openspec/changes/<slug>/` 与 `.specpowers/auto_base/<slug>.json` 被删除；`.specpowers/runtime.json` 的 `fallback_count` 保留不清；单活跃全清 = 删除全部活跃目录

#### Scenario: 前台 meta 推导与切换

- **WHEN** 多活跃需求中执行 `facade switch <slug>`
- **THEN** 目标需求 meta 的 `last_touched` 更新为最大值，前台 = `active_slugs` 中 meta `last_touched` 最大者推导切换，无全局指针写点

#### Scenario: fast 态目录自包含

- **WHEN** 用户经 `/specpowers-fast` 开工新需求
- **THEN** 立即建立 `openspec/changes/<slug>/`，内含 `.specpowers-meta.json`（mode=fast）与 `checklist.md`（验收清单）；apply 门禁按 meta.mode=fast 走 fast 分支（git diff 非空校验）

#### Scenario: 探索收口自包含登记

- **WHEN** explore 收口执行 `facade record-design-doc`
- **THEN** change 目录建立并写入 meta（design_doc 路径/created_at）；仅 meta 无三件套的目录推导为 explore 态，meta 缺失的旧目录推导不受阻断（meta 非 stage 判定硬依赖）
