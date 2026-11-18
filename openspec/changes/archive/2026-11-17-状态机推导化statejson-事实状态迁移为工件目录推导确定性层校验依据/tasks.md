## 推荐执行方式

<!--
推荐：conductor
worktree：不推荐
subagent：不推荐
TDD：推荐
修改范围：plugins/specpowers/scripts/specpowers_cli/, plugins/specpowers/skills/, tests/, README.md, docs/GETTING-STARTED.md, pyproject.toml
-->

### Task 1: TDD 新增 state_derivation 推导纯函数模块

- [x] 实现内容：先写 `tests/test_state_derivation.py`（红）——覆盖 iteration_count_of（design-round-N 最大值 / tasks.md Round 小节最大值 / 空目录返回 0）、is_active_change（proposal / specs / tasks / .specpowers-meta.json 任一存在）、design_doc_of（meta 读取 / 损坏降级 None）、reconcile_feature（僵尸清理 / explore-fast 豁免 / 推导回写）；再实现 `bridge/modules/state_derivation.py`（绿）——无副作用纯函数集，meta 读写复用 `fs_state.atomic_write_json` 范式
- 场景引用：迭代轮次从工件推导（WHEN change 目录内存在 design-round-3.md 且 tasks.md 含「## Round 5」小节 THEN 推导值为 5）；meta 损坏降级不阻断（WHEN meta JSON 非法 THEN 返回 None 并警告不中断）；活跃判定扩展 meta 文件
- 验收标准：`pytest tests/test_state_derivation.py` 全绿；模块无文件系统副作用（推导函数只读，写动作仅在 reconcile 回调）
- 依赖：无
- 并行：否（后续全部任务的地基）
- 检查点：完成验证：pytest tests/test_state_derivation.py 全绿

### Task 2: fs_state 读路径内嵌读后对账

- [x] 实现内容：`load_feature` / `list_features` 读出后调用 `state_derivation.reconcile_feature`（route 锁内读路径天然互斥）；清理动作复用 `delete_feature`；警告行聚合进返回值；explore/fast 豁免判定落在 reconcile_feature 内并保持纯函数可测
- 场景引用：僵尸条目自动清理（WHEN features 映射存在条目而 change 目录已消失且非 explore/fast 态 THEN 读取路径自动清理并输出警告行）；explore 与 fast 态豁免对账
- 验收标准：test_fs_state 补僵尸清理 / 豁免两态用例全绿；既有 6 用例不回归
- 依赖：Task 1
- 并行：是，可与 Task 3/5 并行
- 检查点：无

### Task 3: dispatcher 读侧切推导值 + record-design-doc 落 meta

- [x] 实现内容：`_describe_active` / `auto_status` / `_enter_new_round` 等读侧的 iteration_count / design_doc 换推导值（state 值降级为缓存，不一致时回写）；`_handle_record_design_doc` 确保 `openspec/changes/<slug>/` 存在并写 `.specpowers-meta.json`（design_doc 相对路径 + created_at，原子写）
- 场景引用：设计文档指针自包含落盘（WHEN explore 收口执行 record-design-doc THEN change 目录被确保创建并落 meta，state 损坏后可据此重建）；推导值与缓存不一致以推导为准
- 验收标准：test_dispatcher 补登记落 meta 用例；auto_status 轮次显示来自推导值；既有 record-design-doc 5 用例不回归
- 依赖：Task 1
- 并行：是，可与 Task 2/5 并行
- 检查点：无

### Task 4: facade reconcile 子命令（对账 + 重建）

- [x] 实现内容：`_cmd_reconcile` 提前分发 + 持锁；双向对账——features 映射 vs changes/ 目录（僵尸清理 + 缺失条目重建：meta + 三件套形态推导 stage/mode）；输出对账报告 JSON（清理行 / 重建行 / 差异行 / 无法重建行四类）
- 场景引用：reconcile 从工件重建状态（WHEN state.json 损坏而 change 目录含 meta 与三件套 THEN reconcile 重建条目并输出报告；无 meta 无三件套报告「无法重建，需重走入口」）
- 验收标准：test_facade 补 reconcile 三态用例（完整重建 / 无法重建 / 报告 JSON 结构）
- 依赖：Task 1、Task 2
- 并行：否
- 检查点：完成验证：端到端冒烟——构造损坏 state + 完整 change 目录，reconcile 后 `facade status` 恢复该需求条目

### Task 5: resume_probe 活跃判定扩展 + 僵尸提示

- [ ] 实现内容：`active_changes` 判定条件加入 `.specpowers-meta.json`；`probe_resume` 对已被对账清理的条目输出提示行（state 有目录无 → 已清理提示，替代静默）
- 场景引用：活跃判定扩展 meta 文件（WHEN 目录仅含 .specpowers-meta.json THEN active_changes 视为活跃 change）
- 验收标准：test_resume_probe 补 meta-only 目录判定 + 清理提示用例；既有 20 用例不回归
- 依赖：Task 1
- 并行：是，可与 Task 2/3 并行
- 检查点：无

### Task 6: 契约文案同步 + 防回潮锚点

- [ ] 实现内容：explore.md 收口契约改为「record-design-doc 建 change 目录 + 落 meta」（解除 v2.0.0「explore 不建 changes/ 目录」定位表述）；SKILL.md 补 state=缓存语义 + reconcile 入口（技能参考表 maintain 行附近）；propose.md / auto.md 涉及 state.json 的措辞同步（读侧推导语义）；test_builtin_skills 补防回潮锚点（meta 登记锚点存在 + 旧「本阶段不创建 changes/ 目录」表述不得回潮）
- 场景引用：设计文档指针自包含落盘（契约层落点）
- 验收标准：契约锚点用例全绿；test_builtin_skills 既有锚点不回归
- 依赖：Task 3、Task 4
- 并行：否
- 检查点：无

### Task 7: 文档与版本号同步

- [ ] 实现内容：README（对账与 reconcile 说明小节 + 用例数）、docs/GETTING-STARTED.md 同步；版本号八清单 + pyproject + `__version__` + SKILL.md frontmatter → 2.12.0
- 场景引用：无（工程收尾，不对应 delta 场景）
- 验收标准：test_manifest_consistency 用例数计数器与版本一致性用例通过
- 依赖：Task 6
- 并行：否
- 检查点：无

### Task 8: 全量回归 + 端到端冒烟

- [x] 实现内容：跑全量 pytest（tests/ + review 内置自测）；两项冒烟——① 模拟 state.json 损坏 → `facade reconcile` → `facade status` 恢复需求条目；② 模拟手动删除 change 目录 → 任一读命令 → 输出僵尸清理警告行
- 场景引用：reconcile 从工件重建状态（端到端）；僵尸条目自动清理（端到端）
- 验收标准：全量用例通过（新增用例数同步进 README 用例数行）；两项冒烟输出符合预期
- 依赖：Task 1、Task 2、Task 3、Task 4、Task 5、Task 6、Task 7
- 并行：否
- 检查点：完成验证：全量测试绿色 + 两项冒烟通过

## 依赖与并行说明

- **关键路径**：Task 1 → Task 2 → Task 4 → Task 6 → Task 7 → Task 8
- **可并行组**：[Task 2, Task 3, Task 5]（Task 1 完成后三者互不触碰同一文件：fs_state.py / dispatcher.py+facade.py / resume_probe.py）
- **检查点序列**：Task 1（纯函数测试绿）→ Task 4（reconcile 端到端恢复）→ Task 8（全量回归 + 冒烟）
