## 推荐执行方式

<!--
推荐：conductor（顺序执行，默认）
worktree：不推荐（同批模块连续重构，隔离收益为零）
subagent：不推荐（任务间共享模块上下文强，零上下文子代理回读成本高于收益）
TDD：可选（361 既有用例是行为保护网，红绿循环收益有限；改造以测试同步改写为主）
修改范围：plugins/specpowers/scripts/specpowers_cli/, plugins/specpowers/skills/, plugins/specpowers/plugin.json, plugins/specpowers/.zcode-plugin/, plugins/specpowers/.claude-plugin/, plugins/specpowers/.codex-plugin/, plugins/specpowers/.codebuddy-plugin/, tests/, README.md, docs/GETTING-STARTED.md, pyproject.toml, marketplace.json, .zcode-plugin/, .claude-plugin/, .codex-plugin/, .codebuddy-plugin/
-->

### Task 1: state_derivation 扩展——derive_stage 成为唯一 stage 权威

- [x] 实现内容：在 `modules/state_derivation.py` 新增 `derive_stage(change_dir)`（按设计文档 stage 判定表：仅 meta→explore / proposal 缺 specs 或 tasks→propose / 三件套齐无勾选→propose / 有勾选→apply / meta.mode=fast→fast / archive/ 下→archived，目录不存在返回 explore）、`active_slugs(root)`、`foreground_slug(root)`、`derive_round`（= iteration_count_of 语义改名）；`reconcile_feature` 移除 state 条目参数改为纯工件一致性核对（meta 缺失清单 + 形态异常警告）；tasks 勾选解析复用 apply 侧既有勾选判定逻辑避免两套口径
- 场景引用：「stage 工件推导判定」WHEN change 目录三件套齐且 tasks.md 存在部分勾选任务 THEN 返回 apply，tasks 全勾时可进入 archive
- 验收标准：新函数单测覆盖判定表全部六行 + 目录不存在边界；`tests/test_state_derivation.py` 新用例绿色
- 依赖：无
- 并行：否
- 检查点：完成验证——`pytest tests/test_state_derivation.py` 绿色 + 全量测试无新增失败

### Task 2: fs_state 收缩——schema/映射/前台 API 删除，runtime.json 落位

- [x] 实现内容：`core/fs_state.py` 删除 schema 字段 / `_is_legacy_schema` / `_migrate_schema1` / features 映射 API（list_features/load_feature/foreground_feature/touch_feature/delete_feature/clear_features/features_snapshot/reset_state/init_state 的 state 部分）；新增 `load_runtime`/`save_runtime`（`.specpowers/runtime.json`：fallback_count + last_archive_ref，原子写）；`atomic_write_json` 保留为 meta/runtime 共用；drain_reconcile_warnings 等对账残留 API 随映射一并移除
- 场景引用：「旧 state 自动迁移退役」THEN fallback_count/last_archive_ref 写入 .specpowers/runtime.json（本任务承接存储端）
- 验收标准：`tests/test_fs_state.py` 改写后绿色；全库 grep 无已删 API 的调用残留（dispatcher/facade 的调用点在 Task 3/5 同步改写，本任务先保留临时 import 兼容或按依赖顺序先行改调用方——以 Task 3 不阻塞为准）
- 依赖：Task 1
- 并行：否
- 检查点：完成验证——`pytest tests/test_fs_state.py` 绿色

### Task 3: dispatcher 校验依据切换——矩阵退役，路由权威换目录

- [x] 实现内容：删除 `VALID_TRANSITIONS` 与 `_validate_transition`；`_handle_propose`/`_handle_apply`/`_handle_archive` 入口校验换 `derive_stage` 判定（映射：propose 可入自 explore/propose 续作/apply 回退、apply 可入自 propose 三件套齐或 fast、archive 可入自 apply）；`_resolve_target_feature`/`_resolve_entry_feature`/`_check_init_conflict`/`_describe_active` 等全部换 `active_slugs`/`foreground_slug`/`derive_stage`；多活跃未指名拒绝逻辑保留（清单与 stage 从推导拼装）；apply 回退的 `fallback_count` 拦截改读 `runtime.json`；propose 窗口保护语义保留（跃迁与落盘间目录暂缺不误判）
- 场景引用：「活跃清单目录推导防僵尸」WHEN 用户手动删除或归档某个 change 目录后执行任意推进类 facade 命令 THEN 该需求不再出现在活跃清单，多活跃路由保护按目录推导拒绝未指名命令
- 验收标准：`tests/test_dispatcher.py` 改写后绿色；手动删目录后推进命令路由拒绝用例通过
- 依赖：Task 1、Task 2
- 并行：否
- 检查点：完成验证——`pytest tests/test_dispatcher.py tests/test_multi_feature.py` 绿色

### Task 4: dispatcher 命令行为改造——iterate 退役 / reset 删目录 / fast 自包含 / 迁移钩子

- [x] 实现内容：删除 `_handle_iterate` 与 `_enter_new_round`（auto-new-round 保留 auto_base.rounds 记录、去 state 写点）；`_handle_reset` 重写为删 `openspec/changes/<slug>/` + auto_base 分片（确认提示逻辑 + `--force` 跳过），单活跃全清删全部活跃目录，`fallback_count` 保留；`_handle_archive` 的 last_archive_ref 写 `runtime.json`；`_handle_fast` 建目录 + meta(mode=fast) + `checklist.md`；`route()` 前置 `migrate_legacy_state`（首次命令探测 state.json → meta 齐全化 + runtime 迁移 + 改名 `.bak`，幂等）；`_handle_auto_status` 三分判定的活跃权威换 `active_slugs` + `derive_stage`
- 场景引用：「迭代轮目录推导识别」THEN facade iterate 子命令不存在；「reset 删除工件目录」WHEN 执行 facade reset --feature <slug> 并确认 THEN openspec/changes/<slug>/ 与 auto_base 分片被删除且 fallback_count 保留；「fast 态目录自包含」WHEN 经 /specpowers-fast 开工 THEN 立即建立 change 目录含 meta(mode=fast) 与 checklist.md；「旧 state 自动迁移退役」WHEN 旧项目首次执行任意 facade 命令 THEN 迁移三步完成且幂等
- 验收标准：`tests/test_auto_iteration.py`、`tests/test_execution_mode.py` 改写后绿色；迁移幂等用例（重复执行跳过）通过
- 依赖：Task 3
- 并行：否
- 检查点：完成验证——`pytest tests/test_auto_iteration.py tests/test_execution_mode.py` 绿色；手工冒烟：构造 schema 2 state 的临时仓库跑一次 status 确认迁移三步生效

### Task 5: facade 子命令面调整——switch/record 写 meta，reconcile 升级，status 全推导

- [x] 实现内容：`facade.py` 删除 `iterate` 子命令与 usage 行；`_cmd_switch` 改 touch 目标 meta `last_touched`；`_cmd_record_design_doc`/`_cmd_record_execution_mode` 写 meta（后者 fast 场景补建目录+meta）；`_cmd_reconcile` 升级——移除 state 损坏自愈与 state 重建职责，改为 meta 补齐 + 推导不一致报告（JSON 输出字段同步）；`_cmd_status` 全推导拼装（stage/前台/活跃清单零 state）；报错文案同步（活跃需求选择指引从映射改目录推导口径）
- 场景引用：「前台 meta 推导与切换」WHEN 多活跃需求中执行 facade switch <slug> THEN 目标需求 meta last_touched 更新为最大，前台推导切换；「探索收口自包含登记」THEN 仅 meta 无三件套的目录推导为 explore 态，meta 缺失的旧目录推导不受阻断
- 验收标准：`tests/test_facade.py` 改写后绿色；status 输出与旧版字段兼容（stage/前台/活跃清单语义不变）
- 依赖：Task 4
- 并行：是，可与 Task 6 并行
- 检查点：完成验证——`pytest tests/test_facade.py` 绿色

### Task 6: resume_probe / mode_controller 全推导改写

- [x] 实现内容：`modules/resume_probe.py` 的 `probe_resume`/`sticky_note`/`active_changes` 活跃判定换 `active_slugs` + `derive_stage` + `derive_round`（锚点行 stage/Round/fast 态全部推导拼装，capability 与修改范围仍读工件）；`modules/mode_controller.py` 的 execution_mode 写 meta；hook bash 层零改动验证（sticky-note/resume-probe 子命令名不变）
- 场景引用：「迭代轮目录推导识别」WHEN 未归档需求重入 THEN 由 derive_stage 与目录存在性识别为同需求迭代轮（锚点行 Round 推导展示）
- 验收标准：`tests/test_resume_probe.py` 改写后绿色；构造目录工件（无 state.json）probe 输出正确
- 依赖：Task 3、Task 4
- 并行：是，可与 Task 5 并行
- 检查点：完成验证——`pytest tests/test_resume_probe.py` 绿色

### Task 7: 契约文案同步——state/iterate 措辞清零

- [x] 实现内容：主技能 SKILL.md（流水线总览/多活跃/粘滞/技能参考/安全底线小节）+ `prompts/explore.md`/`propose.md`/`apply.md`/`archive.md`/`fast_mode.md`/`auto.md`/`refs/auto-iteration.md` + `specpowers-explore`/`-propose`/`-auto`/`-maintain` 的 SKILL.md：`state.json`/`stage 跃迁`/`facade iterate`/`iteration_count` 措辞全部改工件推导叙事（重入识别改目录推导口径、迭代轮确认流程去 iterate 命令、reset 文案改删目录语义、fast 建目录契约）；`templates/auto-summary-template.md` 同步
- 场景引用：「迭代轮目录推导识别」WHEN 未归档需求重入 /specpowers-propose 或 /specpowers-explore THEN 识别为同需求迭代轮且 facade iterate 子命令不存在
- 验收标准：`pytest tests/test_builtin_skills.py` 改写锚点后绿色；全库 grep `facade iterate` 与 `state.json` 在 skills/ 下零残留（升级须知历史段落除外）
- 依赖：Task 5、Task 6
- 并行：否
- 检查点：完成验证——`pytest tests/test_builtin_skills.py` 绿色

### Task 8: 迁移与兼容全链路验证

- [x] 实现内容：端到端迁移用例补全——schema 2 旧 state（含多活跃条目/explore 豁免态/propose 窗口态/fallback_count>0/last_archive_ref 非空）→ 首条命令迁移 → meta/runtime/.bak 三产物断言 → 二次命令幂等 → 损坏 state.json 走 reconcile 留底重建路径适配（v2.12 损坏自愈语义迁入迁移钩子）；跨机接管场景（仅目录工件无 state）probe/sticky/多活跃路由全推导验证
- 场景引用：「旧 state 自动迁移退役」WHEN 旧项目（schema 2 state.json 存在）首次执行任意 facade 命令 THEN 三步迁移完成、迁移幂等、此后零 state 读写
- 验收标准：`tests/test_multi_feature.py` 迁移相关用例绿色；临时仓库端到端冒烟（init→explore→propose→apply→archive 全流程零 state.json）
- 依赖：Task 5、Task 6、Task 7
- 并行：否
- 检查点：完成验证——全量 `pytest tests/` 绿色（本任务是回归收口点）

### Task 9: 文档与版本——v3.0.0 升级须知与八清单同步

- [x] 实现内容：README「升级」新增 v3.0.0 破坏性变更须知（state 自动迁移可删 .bak / reset 删目录 / iterate 退役对照表 / fast 与 explore 建目录行为变化）、流水线/多活跃/省 token 小节的 state 措辞清理、版本徽章与安装命令 3.0.0；GETTING-STARTED 架构章节（确定性层=工件推导）与项目结构小节同步；版本号八清单（各 plugin.json/marketplace.json）+ pyproject + `__version__` + 主技能 SKILL.md 同步 3.0.0；用例数全库同步
- 场景引用：「reset 删除工件目录」「迭代轮目录推导识别」（升级须知内容与两裁定一致）
- 验收标准：`pytest tests/test_manifest_consistency.py` 绿色（版本号/用例数一致性由测试校验）；README 徽章显示 3.0.0
- 依赖：Task 8
- 并行：否
- 检查点：完成验证——全量测试（tests/ + review 自测）绿色，提交前 review

## 依赖与并行说明

- **主链**：Task 1 → 2 → 3 → 4 → {5, 6 可并行} → 7 → 8 → 9，严格顺序执行（conductor）
- **并行点**：仅 Task 5 与 Task 6（二者文件集不相交，均依赖 Task 4）；其余任务共享 dispatcher/fs_state 上下文，并行收益为负
- **风险集中点**：Task 3（校验切换，行为面最宽）与 Task 8（迁移回归收口）各设检查点；Task 2 删除 API 时注意 Task 3/5 的调用方同步，避免中间态 import 断裂
