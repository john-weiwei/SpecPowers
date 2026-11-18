# 状态机推导化 v3.0（第二步：校验依据切换 + state.json 退役）设计文档

> 日期：2026-11-17
> 状态：待确认
> 推荐方案：方案A 第二步（用户裁决：v2.12 已实施，继续实施 v3.0）

## 决策摘要

**目标**：在 v2.12（第一步：推导层 + 读后对账 + meta 自包含 + `facade reconcile`，已在工作区落地未提交）基础上完成第二步——`state.json` 从「可重建缓存」进一步退役：dispatcher 校验依据从状态缓存换成工件形态判定，删除 features 映射与全部 stage 缓存，活跃性 / 阶段 / 轮次 / 前台 / 归档基准全部工件推导。

**方案选择**：增量切换（非重写）——`derive_stage()` 正式化（v2.12 reconcile 内已有三件套判定雏形）→ `VALID_TRANSITIONS` 矩阵退役 → `facade iterate` / `_enter_new_round` 退役（轮次推导式，写侧 max+1）→ reset 语义重定义（删 change 目录）→ 前台改 meta touch → `fallback_count`/`last_archive_ref` 迁 `.specpowers/runtime.json` → 旧 state 自动迁移后改名 `.bak`。

**边界与约束**：`.lock` 锁机制、`auto_base/<slug>.json` 分片（含 auto 三分判定 / rounds 记录）、openspec CLI 归档链路、结构门禁 / 修改范围门禁语义零改动；v2.12 既有对账语义（explore/ready 豁免、propose 窗口保护、损坏自愈）随 state 退役转化为 reconcile 命令与 derive 入口校验的职责；「explore 进行中（未收口）」仍不可探测（v2.12 已接受）；本版含破坏性变更（reset 删目录、iterate 删除），须出 v3.0.0 升级须知。

## 方案对比

| 维度 | A 第一步（v2.12，已落地） | 本步：A 第二步（v3.0，已选） | 一步到位（已否决） |
|------|------|------|------|
| 核心思路 | 推导层 + 对账 + reconcile，state 降为可重建缓存 | 校验依据换工件、state 文件退役 | 单版同时做两步 |
| state 角色 | 缓存（读侧已推导对齐） | 退役（迁移 → .bak） | 直接删除 |
| 复杂度 | 已完成 | 中（增量切换，~150 用例改写） | 高（当时无地基） |
| 兼容性 | 旧项目无感 | 自动迁移 + 升级须知 | 破坏性集中 |
| 推荐度 | ⭐⭐⭐（已兑现） | ⭐⭐⭐（承接兑现） | ⭐ |

探索期推荐方案A，用户裁决采纳并指示两步连续实施。第二步无新的方案分叉——第一步已把可推导项推导化，本步只剩「切换校验依据 + 退役收尾」，风险面比探索期评估的一次到位方案显著收窄。

## 相关既有模式

- `modules/state_derivation.py`（v2.12 新增）：`change_dir_of` / `is_active_change` / `iteration_count_of` / `read_meta` / `write_meta` / `design_doc_of` / `reconcile_feature`——本步的地基，`derive_stage` 在其上新增
- `facade._cmd_reconcile` 的工件侧重建：已含 stage 推导雏形（三件套齐→propose、仅 meta→explore），本步提升为 `derive_stage()` 单一实现，reconcile 改为消费它
- `core/fs_state.py` 的 `atomic_write_json` / `_atomic_replace`：meta / runtime.json 写盘复用
- `_migrate_schema1` 的「读出即迁移」范式：本步 state 退役迁移沿用同语义（首次命令触发、幂等）

## 详细设计（v3.0 增量）

### 架构

```
facade 子命令入口
   └─ dispatcher.route()（锁内；首次命令先 migrate_legacy_state）
        ├─ state_derivation.derive_stage(change_dir)   ← 唯一 stage 权威（新）
        ├─ 入口校验：VALID_TRANSITIONS / _validate_transition 删除，各 handler 换推导判定
        ├─ 活跃权威：active_slugs(root) 扫目录（features 映射 API 删除）
        ├─ meta 读写（last_touched / mode / execution_mode / design_doc；原子写、锁内）
        ├─ runtime.json（.specpowers/runtime.json：fallback_count + last_archive_ref）
        └─ state.json 退役：migrate_legacy_state 迁移后改名 state.json.bak
```

- **`modules/state_derivation.py`**（扩展）：新增 `derive_stage(change_dir) -> str`（值域 `{explore, propose, apply, fast, archived}`）与 `active_slugs(root)`、`foreground_slug(root)`；`reconcile_feature` 中 state 条目参数随映射删除而移除，保留工件侧一致性核对（meta 缺失清单、形态异常警告）
- **`core/fs_state.py`**（收缩）：删除 schema/迁移/features 映射/前台/touch 全部 API；新增 `load_runtime`/`save_runtime`；`atomic_write_json` 保留为 meta/runtime 共用
- **`dispatcher.py`**（重构）：三个 `_validate_transition` 调用点换 derive 判定；`_resolve_target_feature`/`_resolve_entry_feature`/`_check_init_conflict` 等换 `active_slugs`；`_handle_iterate` 与 `_enter_new_round` 删除；`_handle_reset` 重写（删目录）；`_handle_archive` 的 `last_archive_ref` 写 runtime.json；apply 回退语义并入「propose 续作」（`fallback_count` 从 runtime.json 读，拦截逻辑不变）
- **`facade.py`**（子命令面）：`iterate` 删除；`switch` 保留（touch meta `last_touched`）；`record-design-doc` / `record-execution-mode` 写 meta（后者补 `mode: fast` 时同步建目录+meta）；`reconcile` 语义升级（不再修 state，改修 meta/报告推导不一致）；`status` 全推导拼装
- **`modules/resume_probe.py`**（改写）：probe / sticky_note 活跃判定换 `active_slugs` + `derive_stage` + `derive_round`，不再读 state
- **`modules/mode_controller.py`**（小改）：execution_mode 写 meta

### stage 判定表（derive_stage 唯一权威）

| 工件形态 | derive_stage | 可进入 |
|---------|-------------|--------|
| 目录不存在或仅含 meta（无三件套） | explore | propose |
| proposal.md 存在、specs/ 或 tasks.md 缺 | propose | propose 续作 |
| 三件套齐、tasks 无勾选 | propose | apply |
| 三件套齐、tasks 有勾选（含全勾） | apply | apply 续跑 / archive |
| meta.mode=fast（checklist.md 在 change 目录） | fast | apply（fast 门禁：git diff 非空） |
| 目录位于 `changes/archive/` | archived | 拒绝推进 |

入口校验映射：explore 可入自「目录不存在或无 meta」（slug 命中活跃目录 → 拒绝给续作指引，与旧「slug 命中即拒绝」同构）；propose 可入自 explore/propose 续作/apply 回退（`fallback_count` 拦截不变）；apply 可入自 propose（三件套齐，`artifact_registry` 校验保留）或 fast；archive 可入自 apply（tasks 全勾或用户确认）。多活跃路由保护不变：`active_slugs() > 1` 时推进类命令未指名拒绝并列出活跃清单与推导 stage。

### 三大难题裁定（v3.0 落地）

1. **reset 负事实** → `reset --feature` = 删 `openspec/changes/<slug>/` + `auto_base/<slug>.json`（破坏性确认必出，`--force` 显式跳过）；单活跃全清 = 删全部活跃目录；`runtime.json` 的 `fallback_count` **保留**（跨需求生命周期额度）。放弃即删工件，需留存走 archive——孤儿目录漂移根源消灭
2. **前台** → 前台 = `active_slugs` 中 meta `last_touched` 最大者（推导式）；`facade switch <slug>` = touch 目标 meta；多会话各写各 meta 无争抢；跨机同步后按 mtime 重排（前台本就是本机参考，可接受）
3. **fast/explore 态目录** → fast 入口即建 change 目录 + meta(mode=fast) + `checklist.md`（验收清单落目录，fast 自包含，`_is_exempt` 的 ready 豁免随之删除）；explore 收口建目录+meta（v2.12 已实现）；「进行中未收口」仍推导为无活跃（接受）

### 数据流

本特性无跨链路字段（纯本地 CLI 逻辑，无运行时注入源）。

**退役迁移数据流**（首次任意 facade 命令触发，幂等）：探测 `state.json` 存在 → 对每个 features 条目：有 change 目录者确保 meta 齐全（design_doc/mode/execution_mode/created_at 迁入，iteration_count 与推导值交叉核对留差异警告）；无目录且非豁免态者记录警告丢弃 → `fallback_count`/`last_archive_ref` 写 `runtime.json` → `state.json` 改名 `state.json.bak`（升级须知注明可删）→ 后续零 state。写路径锁语义不变（互斥对象 = meta / runtime.json / auto_base 的小文件原子写）。

### 接口定义

```python
# modules/state_derivation.py（扩展）
def derive_stage(change_dir: Path) -> str          # 见 stage 判定表；目录不存在返回 "explore"
def active_slugs(root: Path) -> list[str]          # 非 archive、is_active_change 为真，按名排序
def foreground_slug(root: Path) -> str | None      # active_slugs 中 meta.last_touched 最大者
def derive_round(change_dir: Path) -> int          # = 既有 iteration_count_of 改名语义不变
def migrate_legacy_state(root: Path) -> dict       # state.json → meta 齐全化 + runtime.json + .bak；幂等

# core/fs_state.py（收缩后剩余全部）
def load_runtime(root: Path) -> dict
def save_runtime(root: Path, runtime: dict) -> None
def atomic_write_json(path: Path, data: dict) -> None

# facade 子命令面变化（v3.0.0）
facade switch <slug>        # 保留：实现改 touch meta.last_touched
facade reconcile            # 升级：不再修 state，输出 meta 补齐 + 推导不一致报告
facade iterate              # 删除：重入 propose/explore 由 derive_stage 识别迭代轮
其余子命令签名不变（内部实现换推导）
```

### 错误处理

- meta 缺失/损坏 → 按默认值推导不抛错（meta 非 stage 硬依赖）；`reconcile` 报告标注待补清单
- tasks 勾选不可辨（格式异常）→ derive_stage 保守取 propose + 警告行，不阻断
- `state.json.bak` 已存在 → 幂等跳过迁移（已退役过）
- runtime.json 损坏 → FatalError 给「删除后 fallback 额度重置」显式指引（字段单一，重建成本≈零）
- derive 出 archived / fast 与命令目标不符 → 拒绝并给对应入口指引（与旧 transition 报错同型，文案同步）
- reset 删目录前强确认（宪章：破坏性动作意图不明必问）

## 修改范围

| 操作 | 文件路径 | 说明 |
|------|---------|------|
| 扩展 | plugins/specpowers/scripts/specpowers_cli/bridge/modules/state_derivation.py | +derive_stage / active_slugs / foreground_slug / migrate_legacy_state；reconcile_feature 去 state 化 |
| 收缩 | plugins/specpowers/scripts/specpowers_cli/bridge/core/fs_state.py | 删 schema/映射/前台/touch API；+runtime 读写 |
| 重构 | plugins/specpowers/scripts/specpowers_cli/bridge/dispatcher.py | 校验表换推导、iterate/_enter_new_round 删除、reset 删目录、archive_ref 迁 runtime、路由权威换目录 |
| 修改 | plugins/specpowers/scripts/specpowers_cli/bridge/facade.py | -iterate、switch/record-* 改 meta、reconcile 升级、status 全推导 |
| 改写 | plugins/specpowers/scripts/specpowers_cli/bridge/modules/resume_probe.py | probe/sticky 全推导 |
| 修改 | plugins/specpowers/scripts/specpowers_cli/bridge/modules/mode_controller.py | execution_mode 写 meta |
| 修改 | plugins/specpowers/skills/specpowers/SKILL.md + prompts/explore.md、propose.md、apply.md、archive.md、fast_mode.md、auto.md、refs/auto-iteration.md | state.json/stage 跃迁/iterate 措辞清零换工件推导叙事；fast 建目录契约 |
| 修改 | plugins/specpowers/skills/specpowers-explore、-propose、-auto、-maintain 的 SKILL.md | iterate/state 引用同步 |
| 改写 | tests/test_fs_state.py、test_dispatcher.py、test_auto_iteration.py、test_multi_feature.py、test_execution_mode.py、test_resume_probe.py、test_state_derivation.py | 推导判定/迁移/reset 删目录/meta 前台/迭代轮识别新断言 + 防回潮锚点（VALID_TRANSITIONS、facade iterate、state.json 校验依据不得回潮） |
| 修改 | tests/test_facade.py、test_builtin_skills.py | 子命令面与契约锚点同步 |
| 修改 | README.md、docs/GETTING-STARTED.md | v3.0.0 破坏性变更须知（自动迁移 / reset 删目录 / iterate 退役）、多活跃与团队协作小节、用例数同步 |
| 修改 | pyproject.toml + 八清单 + `__version__` | 版本号 3.0.0 同步 |
