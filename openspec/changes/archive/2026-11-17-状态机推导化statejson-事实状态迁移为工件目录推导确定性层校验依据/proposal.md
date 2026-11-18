## Why

state.json 与 openspec/changes/ 工件是双真相源：用户手动执行 `openspec archive` 或删除 change 目录后，state 的僵尸条目仍然存在，推进类命令会路由到已不存在的需求；state.json 一旦损坏只能 reset 全清——迭代轮次、设计文档指针、auto 断点全部丢失，而工件都还在盘上（指针链断裂）。SpecPowers 为 state 防御性维护付出了大量成本（损坏恢复引导、schema 1→2 迁移、锁残留清理）。借鉴 OpenSpec「目录即状态」哲学，把边界再往推导侧挪一格：能从工件证明的事实不依赖缓存。

## What Changes

**v2.12（本次实施）**：
1. 新增 `bridge/modules/state_derivation.py` 推导纯函数模块——活跃性 / 迭代轮次 / 设计文档指针从 change 目录推导
2. `fs_state` 读路径内嵌「读后对账」——僵尸条目自动清理 + 警告，explore/fast 态豁免
3. `record-design-doc` 收口时确保 change 目录存在并落 `.specpowers-meta.json`（change 目录自包含）
4. 消费点读侧（iteration_count / design_doc）切推导值，state 值降级为缓存回写
5. 新增 `facade reconcile` 子命令——从工件重建缺失条目，state.json 降级为「可删可重建缓存」

**v3.0（路线图，本次不实施）**：dispatcher 校验依据切换为工件形态校验、`facade iterate`/`switch` 退役、`fallback_count` 迁极简文件、reset 负事实重定义（删目录或墓碑）、删除 state.json。

## Capabilities

### New Capabilities

- `状态机推导化statejson-事实状态迁移为工件目录推导确定性层校验依据`: 需求级事实状态以 openspec/changes/ 工件目录推导为权威信源，state.json 仅作可重建缓存；提供对账（僵尸条目清理）与重建（reconcile）能力

## 数据流契约

本特性无跨链路字段（纯本地 CLI 逻辑：state.json + changes/ 目录 → dispatcher 校验 → stdout / hook 注入；无配置中心 / DB / MQ / 请求头注入源——依据设计文档「数据流」章节声明）。

## Impact

- **修改面**：确定性层 bridge 包（fs_state / dispatcher / facade / resume_probe + 新增 state_derivation）、契约文案（explore.md / SKILL.md / propose.md / auto.md）、测试（新增对账 / 推导 / rebuild 用例 + 防回潮锚点）、README / GETTING-STARTED、版本八清单同步 2.12.0
- **行为变更**：explore 收口将创建 change 目录并落 meta 文件（解除 v2.0.0「explore 不建 changes/ 目录」定位）；读路径发现僵尸条目会自动清理并警告（原行为：静默保留直至下游撞墙）
- **兼容性**：读出即对账幂等，旧项目无感；`.lock` 锁机制 / 结构门禁 / 修改范围门禁 / openspec CLI 归档链路零改动
- **风险**：`active_changes` 活跃判定扩展 meta 后，specpowers 视图与 `openspec list` 类外部视图的活跃口径存在差异（meta 对 openspec CLI 不可见，无实际影响，契约措辞中说明即可）
