## Why

`state.json` 与 `openspec/changes/` 工件是双真相源：手动归档/删除 change 目录后 state 残留僵尸条目（推进类命令仍可路由）；state 损坏时 FatalError 引导 reset，迭代计数与设计文档指针全丢；schema 迁移与防御代码是持续性维护成本。v2.12（已落地）已将推导层、读后对账、`facade reconcile`、meta 自包含就位，`state.json` 降级为可重建缓存。本 change 完成第二步：把校验依据也切换为工件推导，让 `state.json` 彻底退役——目录即状态，工件是唯一权威。

## What Changes

- **校验依据切换**：`VALID_TRANSITIONS` 矩阵与 `_validate_transition` 退役，新增 `derive_stage(change_dir)` 工件判定（值域 explore/propose/apply/fast/archived）成为唯一 stage 权威；`facade iterate` 与 `_enter_new_round` 退役（迭代轮由目录推导识别，轮次 = design-round-N 与 tasks Round 小节推导，写侧 max+1 维护）
- **state 退役**：features 映射 / 前台 last_touched / iteration_count / design_doc / mode / execution_mode 全部删除或迁入 change 目录 meta；`fallback_count` / `last_archive_ref` 迁 `.specpowers/runtime.json`；旧 `state.json` 首次命令自动迁移后改名 `.bak`
- **语义重定义（破坏性）**：reset `--feature` 改为删除 change 目录 + auto_base 分片（确认提示，`fallback_count` 保留）；`facade switch` 实现改为 touch meta `last_touched`（前台推导式）；fast 入口建 change 目录 + meta(mode=fast) + `checklist.md`
- **配套**：resume_probe / sticky_note 全推导改写；契约文案 state/iterate 措辞清零；测试 ~150 用例改写 + 防回潮锚点；版本 3.0.0 + 升级须知

## Capabilities

### New Capabilities

- `状态机推导化v3`: 流水线状态工件推导化——stage/轮次/活跃清单/前台/归档基准全部从 `openspec/changes/` 目录形态与 change 目录 meta 推导，确定性层校验依据为工件形态，`state.json` 退役

## 数据流契约

本特性无跨链路字段（纯本地 CLI 逻辑：`openspec/changes/` 目录 + `.specpowers-meta.json` + `.specpowers/runtime.json` → `state_derivation` 推导 → dispatcher 校验 → stdout / hook 注入；无配置中心 / DB / MQ / 请求头注入源）。

## Impact

**受影响**：`bridge/modules/state_derivation.py`（扩展 derive_stage/active_slugs/foreground_slug/migrate_legacy_state）、`bridge/core/fs_state.py`（收缩为 runtime 读写 + atomic_write_json）、`bridge/dispatcher.py`（校验表/路由权威/iterate/_enter_new_round/reset/archive_ref）、`bridge/facade.py`（子命令面）、`bridge/modules/resume_probe.py`、`mode_controller.py`；契约 11 个 SKILL.md/prompts；测试 7 个文件约 150 用例；README / GETTING-STARTED / 版本八清单。

**边界与约束**：`.lock` 锁机制、`auto_base/<slug>.json` 分片（auto 三分判定 / rounds 记录）、openspec CLI 归档链路、结构门禁 / 修改范围门禁语义零改动；v2.12 对账语义（propose 窗口保护、损坏自愈）转化为 reconcile 命令与 derive 入口校验职责；「explore 进行中（未收口）」仍不可探测（接受）。破坏性变更（reset 删目录、iterate 删除、state 自动迁移）由 v3.0.0 升级须知承载。
