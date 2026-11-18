"""Tests for dispatcher — 工件推导入口判定 / runtime 计数 / fast 模式（v3.0.0）。

回归覆盖（v3.0 状态机推导化改写，state.json 退役）：
- derive_stage 入口判定取代 VALID_TRANSITIONS：propose 自环/explore 续作放行、
  explore 拒 apply（三件套未齐）、archive 仅 apply/fast（"Valid from stages" 文案）、
  fast 仅新需求或 fast 态重入
- fallback 回退计数迁 runtime.json：apply/fast→propose 生命周期 1 次额度、
  计次 +1 落 runtime + meta mode 归 full、超限拒绝
- reset 语义重定义：删 change 目录 + auto_base 分片、--force 破坏性确认、
  多活跃未指名拒绝、runtime 项目级字段保留
- init 幂等/冲突按 active_slugs 口径（无活跃 + baseline 存在 = 幂等跳过；
  --force 删除全部活跃 change 目录）
- record-design-doc：显式 --feature 不查活跃（登记即建目录）、meta 相对路径登记、
  advisory 段头警告
- 未初始化兜底（v2.5.0 承接）：route 入口五阶段统一拦截给 init 指引、
  init/baseline/reset 放行；git 前置（非 git 仓库）拦截保留

已知生产 bug 隔离（生产侧修复后本 fixture 自动 no-op，可保留不删）：
artifact_registry.MANIFEST 仍含已退役的 .specpowers/state.json 条目
（consumers=["*"], required=True —— v3.0 重构遗漏该文件适配），导致所有走
_run_pre_stage_checks 的阶段（explore/propose/apply/archive）一律抛
ArtifactMissingError: Required artifact '.specpowers/state.json' not found。
本文件用 autouse fixture 过滤该条目，其余产物校验（constitution/baseline/
proposal/spec/tasks）全部保持真实逻辑。

作者：005819 | 协作：GLM-5.3
"""

import shutil
from pathlib import Path

import pytest

from specpowers_cli.bridge.dispatcher import (
    _handle_record_design_doc,
    _run_pre_stage_checks,
    normalize_feature,
    route,
)
from specpowers_cli.bridge.core.errors import (
    ArtifactMissingError,
    FatalError,
    StateError,
)
from specpowers_cli.bridge.core.fs_state import load_runtime
from specpowers_cli.bridge.core.git_util import git_ref_of
from specpowers_cli.bridge.modules.state_derivation import (
    active_slugs,
    change_dir_of,
    derive_stage,
    design_doc_of,
)
from tests.helpers_v3 import (
    make_change,
    make_triple,
    read_meta_of,
    write_runtime,
)

# explore 收口形态的 meta（仅登记无三件套 → derive_stage = explore）
_EXPLORE_META = {"created_at": "2026-01-01T00:00:00+00:00"}

# apply 态 tasks（有勾选 = 执行进度 → derive_stage = apply）
_APPLY_TASKS = "### Task 1: x\n\n- [x] done\n- [ ] todo\n"




def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库（会话级模板复制，约 10ms）。"""
    from tests._gitrepo import create_git_repo

    return create_git_repo(tmp_path / "dispatcher-repo")


def _init_project(root: Path) -> None:
    """初始化项目产物（constitution + baseline），模拟已执行 /specpowers-init。"""
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(parents=True, exist_ok=True)
    (specpowers_dir / "constitution.md").write_text("# 项目原则", encoding="utf-8")
    (specpowers_dir / "baseline.json").write_text(
        '{"git_ref":"","top_dirs":[],"deps":{},"src_patterns":[]}', encoding="utf-8",
    )


def _write_design_doc(root: Path, slug: str) -> str:
    """落盘探索设计文档，返回相对 root 的 posix 路径（meta 登记值形态）。"""
    rel = f"docs/specpowers/design/2026-01-01-{slug}-design.md"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# 设计\n## 方案对比\n略\n## 详细设计\n略\n", encoding="utf-8")
    return rel


def _write_auto_base(root: Path, slug: str) -> Path:
    """写入需求的 auto_base 分片（reset/archive 清理语义的测试现场）。"""
    base = root / ".specpowers" / "auto_base" / f"{slug}.json"
    base.parent.mkdir(parents=True, exist_ok=True)
    base.write_text("{}", encoding="utf-8")
    return base


def _mock_openspec_archive(monkeypatch):
    """屏蔽真实 openspec CLI：按真实契约模拟归档（change 目录移入 archive/ 快照）。"""
    import specpowers_cli.bridge.modules.archive_auditor as archive_auditor

    def _fake_prepare(root, feature, state, skip_validation=False):
        src = root / "openspec" / "changes" / feature
        dst = root / "openspec" / "changes" / "archive" / feature
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.move(str(src), str(dst))
        return {"archivedAs": feature, "specsUpdated": False}

    monkeypatch.setattr(archive_auditor, "prepare_openspec_archive", _fake_prepare)


def _setup_apply_prereqs(root: Path, feature: str, proposal_content: str) -> None:
    """构造 apply 前置校验现场：constitution/baseline + 三件套（proposal 内容可定制）。

    Args:
        root: 临时仓库根。
        feature: feature slug。
        proposal_content: proposal.md 内容（由调用方控制是否含数据流契约）。
    """
    _init_project(root)
    make_triple(root, feature)
    (change_dir_of(root, feature) / "proposal.md").write_text(
        proposal_content, encoding="utf-8",
    )


# ---- derive_stage 入口判定（取代 VALID_TRANSITIONS，v3.0） ----

def test_propose_reenters_from_explore_stage_allowed(tmp_path, monkeypatch):
    """explore 态（仅 meta）propose 续作放行，且正常路径不计回退数。

    explore 收口（record-design-doc 登记）后进入 propose 是唯一正规入口：
    工件判定按 derive_stage 放行（explore/propose 自环均合法），设计文档登记
    校验以已登记且存在的文档通过。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    rel = _write_design_doc(root, "login")
    make_change(root, "login", meta={"design_doc": rel})
    # facade 以项目根为 cwd 运行（meta design_doc 为相对路径，按 cwd 解析）
    monkeypatch.chdir(root)

    assert route("propose", root, {"requirement": "login"}) == 0
    # explore→propose 正常路径：不触发 fast/apply 回退计次
    assert load_runtime(root)["fallback_count"] == 0
    # 操作即前台：meta touch（design_doc 登记保留）
    meta = read_meta_of(root, "login")
    assert meta["design_doc"] == rel
    assert meta["last_touched"]


def test_propose_self_loop_at_propose_stage_allowed(tmp_path):
    """propose 态自环（续作/迭代轮重入）放行，不抛 StateError 不计回退。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "login")  # 三件套齐无勾选 = propose 态

    assert route("propose", root, {"requirement": "login"}) == 0
    assert derive_stage(change_dir_of(root, "login")) == "propose"
    assert load_runtime(root)["fallback_count"] == 0


def test_propose_new_requirement_creates_change_dir(tmp_path):
    """无活跃需求时 propose 新需求：建 change 目录 + meta(mode=full)。

    v3.0 起 propose 入口本身有写点（touch meta，新需求借此建目录），
    「propose 进行中」的目录形态 = 仅 meta → derive_stage=explore，重入自洽。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)

    assert route("propose", root, {"requirement": "brand new thing"}) == 0

    assert active_slugs(root) == ["brand-new-thing"]
    assert read_meta_of(root, "brand-new-thing")["mode"] == "full"
    assert derive_stage(change_dir_of(root, "brand-new-thing")) == "explore"


def test_apply_rejected_from_explore_stage(tmp_path):
    """explore 态（三件套未齐）拒入 apply，报错点名「三件套未齐」并给 propose 指引。

    取代旧 VALID_TRANSITIONS 的 apply 入口校验：derive_stage=explore 即拒绝。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "login", meta=dict(_EXPLORE_META))  # 仅 meta = explore 态

    with pytest.raises(StateError, match="三件套未齐"):
        route("apply", root, {"feature": "login"})


def test_apply_multi_active_requires_named_feature(tmp_path):
    """多活跃需求 apply 未指名 → 拒绝并列出活跃清单（--feature 防错路由）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "feat-a", _APPLY_TASKS)
    make_triple(root, "feat-b", _APPLY_TASKS)

    with pytest.raises(StateError, match="--feature") as exc_info:
        route("apply", root, {})
    # 报错必须把活跃清单递给模型（带名重试的依据）
    assert "feat-a" in str(exc_info.value)
    assert "feat-b" in str(exc_info.value)


def test_archive_rejected_outside_apply_fast_stages(tmp_path):
    """propose/explore 态拒入 archive，文案固定为 "Valid from stages: apply, fast"。

    archive 入口工件判定：仅 apply（tasks 有执行进度）与 fast（验收清单路径）
    合法；propose（无进度）与 explore（三件套未齐）拒绝。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "feat-a")  # 无勾选 = propose 态
    make_change(root, "feat-b", meta=dict(_EXPLORE_META))  # 仅 meta = explore 态

    for slug in ("feat-a", "feat-b"):
        with pytest.raises(StateError, match=r"Valid from stages: apply, fast"):
            route("archive", root, {"feature": slug})


@pytest.mark.parametrize("mode", ["apply", "fast"])
def test_archive_acceptance_from_valid_stages(tmp_path, monkeypatch, mode):
    """apply/fast 态归档放行：runtime 刷新 last_archive_ref + auto_base 分片清理。

    归档的「需求终结」由工件承载（目录移入 archive/ 后 active_slugs 即时更新），
    全部状态写点只有 runtime.json 与 auto_base 清理两处。
    """
    _mock_openspec_archive(monkeypatch)
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    if mode == "apply":
        make_triple(root, "feat-a", _APPLY_TASKS)
    else:
        make_change(root, "feat-a", meta={"mode": "fast"})
    _write_auto_base(root, "feat-a")

    assert route("archive", root, {"feature": "feat-a"}) == 0

    # merge check 基准刷新为当前 HEAD（项目级，落 runtime.json）
    assert load_runtime(root)["last_archive_ref"] == git_ref_of(root)
    # 归档即该需求生命周期终结：auto_base 分片清理
    assert not (root / ".specpowers" / "auto_base" / "feat-a.json").exists()
    # 需求终结由工件承载：快照落 archive/，活跃清单即时更新
    assert (root / "openspec" / "changes" / "archive" / "feat-a").is_dir()
    assert "feat-a" not in active_slugs(root)


# ---- fast 入口（原 transition 回归场景的 v3.0 形态） ----

def test_fast_new_requirement_creates_meta_and_checklist(tmp_path):
    """fast 对新需求启动成功（核心回归传承）：建 change 目录 + meta(mode=fast) + checklist 骨架。

    原 bug 语境：_validate_transition('ready', 'fast') 因 VALID_TRANSITIONS 无
    'fast' 键而拒绝一切合法 fast 启动。v3.0 起入口按工件判定（新需求无目录即放行），
    并自包含落 meta + checklist 骨架保证 apply 门禁可校验。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)

    assert route("fast", root, {"requirement": "fix typo"}) == 0

    meta = read_meta_of(root, "fix-typo")
    assert meta["mode"] == "fast"
    assert meta["created_at"]
    checklist = change_dir_of(root, "fix-typo") / "checklist.md"
    assert checklist.is_file()
    assert "- [ ]" in checklist.read_text(encoding="utf-8")
    assert active_slugs(root) == ["fix-typo"]
    assert derive_stage(change_dir_of(root, "fix-typo")) == "fast"


def test_fast_reentry_at_fast_stage_allowed(tmp_path):
    """fast 态重入 fast（补填清单/重确认）放行，已有验收清单不被覆盖。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "fix-typo", meta={"mode": "fast"})
    checklist = change_dir_of(root, "fix-typo") / "checklist.md"
    checklist.write_text("# 验收清单（fast 模式）\n\n- [x] 已有验收项\n", encoding="utf-8")

    assert route("fast", root, {"requirement": "fix typo", "feature": "fix-typo"}) == 0

    # meta 保持 fast（重入合法）；骨架只在缺失时创建，已有清单保留
    assert read_meta_of(root, "fix-typo")["mode"] == "fast"
    assert "- [x] 已有验收项" in checklist.read_text(encoding="utf-8")


def test_fast_rejected_for_active_non_fast_feature(tmp_path):
    """fast 不允许对非 fast 态的活跃需求启动（slug 命中续作校验，抛 StateError）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "fix-typo", _APPLY_TASKS)  # apply 态活跃需求

    # requirement normalize 后命中活跃需求 → 非 fast 态 → 拒绝
    with pytest.raises(StateError, match="Cannot start fast mode"):
        route("fast", root, {"requirement": "fix typo"})


# ---- 未初始化兜底（v2.5.0 承接） ----

def test_route_uninitialized_rejected_with_init_hint(tmp_path):
    """未初始化项目跑流水线阶段命令应被 route 入口拒绝并给出 init 指引。

    兜底在锁与工件校验之前：报错语义是「未初始化」而非「产物缺失」，
    指引含 /specpowers-init（模型读到后自动转执行初始化再重试原命令）。
    """
    root = _create_temp_git_repo(tmp_path)
    with pytest.raises(FatalError) as exc_info:
        route("explore", root, {"requirement": "新需求"})
    message = str(exc_info.value)
    assert "not initialized" in message
    assert "/specpowers-init" in message
    assert "constitution.md" in message and "baseline.json" in message


def test_route_uninitialized_applies_to_all_pipeline_stages(tmp_path):
    """五个流水线阶段统一兜底；init/baseline/reset 不拦（维护或初始化动作）。"""
    root = _create_temp_git_repo(tmp_path)
    with_args = {"explore", "propose", "fast"}
    for stage in ("explore", "propose", "fast", "apply", "archive"):
        extra = {"requirement": "新需求"} if stage in with_args else {"feature": "any"}
        with pytest.raises(FatalError, match="not initialized"):
            route(stage, root, extra)

    assert route("init", root, {}) == 0
    assert route("baseline", root, {}) == 0
    assert route("reset", root, {}) == 0


def test_route_initialized_project_passes_init_check(tmp_path):
    """已初始化项目（两产物齐）不触发兜底；explore 对新需求无任何写点。

    v3.0：route 不再创建 state.json；explore 仅入口校验 + 指引打印，
    需求登记要等 record-design-doc（meta 落点）才有写点。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)

    # 已初始化 + 无活跃需求：explore 新需求正常进入（不抛任何错误）
    assert route("explore", root, {"requirement": "新需求"}) == 0
    # explore 无任何写点：不建 change 目录、不建 state.json
    assert active_slugs(root) == []
    assert not (root / ".specpowers" / "state.json").exists()
    # 再次 explore 开另一新需求同样合法（多活跃并存是常态，无「ready 拒绝」语义）
    assert route("explore", root, {"requirement": "另一需求"}) == 0
    assert active_slugs(root) == []


# ---- git 前置 ----

def test_route_rejected_in_non_git_repo(tmp_path):
    """非 git 仓库的目录跑流水线命令 → git 前置拦截（FatalError）。"""
    root = tmp_path / "plain-dir"  # 非 git 目录
    _init_project(root)  # 绕过初始化兜底，专测 git 前置

    with pytest.raises(FatalError, match="is not a git repository"):
        route("fast", root, {"requirement": "some fix"})


# ---- normalize_feature 边界回归 ----

def test_normalize_feature_pure_english():
    """纯英文：空格转连字符，转小写。"""
    assert normalize_feature("Fix Login Button") == "fix-login-button"


def test_normalize_feature_special_chars_removed():
    """特殊字符被移除，仅保留字母数字/空格/连字符。"""
    result = normalize_feature("fix bug @#$% in login")
    # 特殊字符移除后，空格转连字符
    assert "@" not in result and "#" not in result
    assert result == "fix-bug-in-login"


def test_normalize_feature_truncate_at_40():
    """超过 40 字符的需求被截断（首 40 字符）。"""
    result = normalize_feature("a" * 100)
    # 截断后 + 连字符处理，长度不应超过 40 + 少量连字符
    assert len(result) <= 45


def test_normalize_feature_archive_reserved():
    """保留字 archive 与 OpenSpec 归档目录冲突：追加后缀消歧。"""
    assert normalize_feature("archive") == "archive-feature"


def test_normalize_feature_windows_device_names_reserved():
    """Windows 保留设备名（con/nul/com1 等）追加后缀消歧。"""
    assert normalize_feature("con") == "con-feature"
    assert normalize_feature("NUL") == "nul-feature"
    assert normalize_feature("COM1") == "com1-feature"


def test_normalize_feature_normal_slug_untouched():
    """普通 slug 不受保留字消歧影响（幂等）。"""
    assert normalize_feature("user-login") == "user-login"
    assert normalize_feature("fix bug in login") == "fix-bug-in-login"


# ---- proposal 数据流契约校验（apply 前置，防探索结论被架空）----

def test_apply_rejects_proposal_without_data_flow_contract(tmp_path):
    """proposal 缺「数据流契约」小节时，apply 前置校验应拒收。

    防止探索结论被架空：agent 若跳过 explore/propose 直写 proposal，
    proposal 不会含数据流契约，_check_proposal_data_flow_contract 将其拦在
    apply 之外，强制回 propose 补全（propose 必须承接 explore 设计文档结论）。
    """
    root = _create_temp_git_repo(tmp_path)
    # proposal 不含数据流契约段头，也不含「无跨链路字段」声明
    _setup_apply_prereqs(root, "login", "## Why\n需要登录\n## What Changes\n加登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError):
        _run_pre_stage_checks(root, "apply", "full", "login")


def test_apply_accepts_proposal_with_data_flow_contract(tmp_path):
    """proposal 含「数据流契约」段头时，apply 前置校验应通过。"""
    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(
        root, "login",
        "## Why\n需要登录\n## 数据流契约\n| 字段 | 来源 |\n|---|---|\n## Impact\n无",
    )

    # 不应抛异常
    _run_pre_stage_checks(root, "apply", "full", "login")


def test_apply_accepts_proposal_with_no_crosslink_decl(tmp_path):
    """proposal 含「本特性无跨链路字段」声明时，apply 前置校验应通过。"""
    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(
        root, "login",
        "## Why\n需要登录\n## 数据流契约\n本特性无跨链路字段\n## Impact\n无",
    )

    # 不应抛异常
    _run_pre_stage_checks(root, "apply", "full", "login")


def test_fast_mode_skips_proposal_contract_check(tmp_path):
    """fast 模式 apply 不触发 proposal 数据流契约校验（fast 无 proposal，验收看代码变更）。

    fast 语义：用户已完成编码（修改已跟踪文件留未提交变更，供代码变更检查通过）；
    需求工件仅为 meta(mode=fast) + checklist，required_for 在 fast 模式下不要求
    proposal/spec/tasks。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "login", meta={"mode": "fast"})
    # 用户已完成编码：修改模板仓库已跟踪的 README.md 留未提交变更
    (root / "README.md").write_text("# Test + fix", encoding="utf-8")

    # 无 proposal 也不因数据流契约校验失败（fast 模式 proposal required=False）
    assert route("apply", root, {"feature": "login"}) == 0
    assert read_meta_of(root, "login")["mode"] == "fast"


def test_apply_contract_hint_from_propose_path(tmp_path):
    """从 propose 刚进入 apply 时，缺数据流契约的提示应含回 propose 补全语境。"""
    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(root, "login", "## Why\n需要登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError) as exc_info:
        _run_pre_stage_checks(root, "apply", "full", "login", from_stage="propose")

    # 错误提示应包含回 propose 补全的语境引导
    err_msg = str(exc_info.value)
    assert "从 propose 刚进入 apply" in err_msg or "回 /specpowers-propose" in err_msg


def test_apply_contract_hint_absent_without_context(tmp_path):
    """不带 from_stage 调用时，缺数据流契约的提示不应含 fallback 语境。

    确认 from_stage 区分：只有 propose 来源才给语境提示，无来源不给。
    """
    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(root, "login", "## Why\n需要登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError) as exc_info:
        _run_pre_stage_checks(root, "apply", "full", "login")

    err_msg = str(exc_info.value)
    assert "从 propose 刚进入 apply" not in err_msg


# ---- propose 设计文档登记校验（防 explore 被架空）----

def test_propose_from_explore_accepts_unregistered_design_doc(tmp_path):
    """meta 未登记 design_doc 时放行（跳过探索路径的中断重入不再误拦）。

    v3.0 目录形态「仅 meta」无法区分 explore 未收口与 ready 直入 propose
    两个来源——登记为空时放行（防探索架空由 explore 契约 HARD-GATE 承担）；
    已登记但文件缺失仍拒收（见 test_propose_from_explore_rejects_missing_design_doc_file）。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "login", meta=dict(_EXPLORE_META))  # explore 态，未登记文档

    # 不应抛异常（审查修复：旧版在此处 ArtifactMissingError「设计文档未登记」）
    _run_pre_stage_checks(root, "propose", "full", "login", from_stage="explore")


def test_propose_from_explore_rejects_missing_design_doc_file(tmp_path, monkeypatch):
    """登记的设计文档文件不存在时，propose 应拒收（防登记空指针）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "login", meta={"design_doc": "docs/specpowers/design/ghost.md"})
    monkeypatch.chdir(root)  # 相对登记按项目根 cwd 解析（facade 调用契约）

    with pytest.raises(ArtifactMissingError):
        _run_pre_stage_checks(root, "propose", "full", "login", from_stage="explore")


def test_propose_from_explore_accepts_registered_design_doc(tmp_path, monkeypatch):
    """登记且存在的设计文档通过 propose 前置校验（meta 相对路径按 cwd=root 解析）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    rel = _write_design_doc(root, "login")
    make_change(root, "login", meta={"design_doc": rel})
    monkeypatch.chdir(root)

    # 不应抛异常
    _run_pre_stage_checks(root, "propose", "full", "login", from_stage="explore")
    assert design_doc_of(root, "login") == rel


def test_propose_from_ready_skips_design_doc_check(tmp_path):
    """从 ready 进入 propose（跳过探索路径）不做设计文档校验。

    仅 from_stage=explore 触发登记校验；ready 路径（清晰需求直入）、
    apply 回退路径、propose 自环均不要求。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)  # 无任何 change 目录

    # 无 meta 无设计文档也不应触发校验
    _run_pre_stage_checks(root, "propose", "full", "login", from_stage="ready")


# ---- record-design-doc 登记原语 ----

def test_handle_record_design_doc_registers_path(tmp_path):
    """登记成功：design_doc 相对路径写入 change 目录 meta（显式 --feature 不查活跃）。

    v3.0 唯一登记处是 meta（state.design_doc 已退役）。显式 --feature 直接采用、
    不校验活跃清单——登记本身即建目录动作，登记前目录尚不存在、无从校验活跃
    （本用例无任何活跃需求仍成功，即「不查活跃」的证明）。
    """
    root = _create_temp_git_repo(tmp_path)
    design_doc = root / "docs" / "specpowers" / "design" / "d.md"
    design_doc.parent.mkdir(parents=True, exist_ok=True)
    design_doc.write_text("# 设计", encoding="utf-8")

    rc = _handle_record_design_doc(
        root, {"design_doc": str(design_doc), "feature": "demo-feat"},
    )
    assert rc == 0
    # 绝对路径登记 → meta 归一为相对 root 的 posix 路径（自包含跨机友好）
    assert read_meta_of(root, "demo-feat")["design_doc"] == "docs/specpowers/design/d.md"
    # 设计文档指针推导（propose 前置校验的读取路径）与 meta 一致
    assert design_doc_of(root, "demo-feat") == "docs/specpowers/design/d.md"
    # 登记即建目录：需求即时进入活跃清单
    assert active_slugs(root) == ["demo-feat"]


def test_handle_record_design_doc_rejects_missing_file(tmp_path):
    """登记失败：文件不存在时拒绝（防登记空指针）。"""
    root = _create_temp_git_repo(tmp_path)

    with pytest.raises(FatalError):
        _handle_record_design_doc(
            root, {"design_doc": str(root / "ghost.md"), "feature": "demo-feat"},
        )


def test_handle_record_design_doc_rejects_empty_path(tmp_path):
    """登记失败：空路径参数拒绝。"""
    root = _create_temp_git_repo(tmp_path)

    with pytest.raises(FatalError):
        _handle_record_design_doc(root, {"design_doc": ""})


def test_handle_record_design_doc_warns_on_missing_sections(tmp_path, capsys):
    """advisory 段头检查：缺「方案对比/详细设计」段头警告但不阻断登记。

    项目自有设计文档约定可能不含模板章节，故 advisory 只警告不拒收——
    警告为空壳/占位文档留下可追溯信号。
    """
    root = _create_temp_git_repo(tmp_path)
    design_doc = root / "docs" / "specpowers" / "design" / "d.md"
    design_doc.parent.mkdir(parents=True, exist_ok=True)
    design_doc.write_text("# 只有标题的空壳文档\n", encoding="utf-8")

    rc = _handle_record_design_doc(
        root, {"design_doc": str(design_doc), "feature": "demo-feat"},
    )

    assert rc == 0
    assert read_meta_of(root, "demo-feat")["design_doc"] == "docs/specpowers/design/d.md"
    out = capsys.readouterr().out
    assert "advisory" in out, "缺模板段头应输出 advisory 警告"
    assert "方案对比" in out and "详细设计" in out, "警告应点名缺失章节"


def test_handle_record_design_doc_no_warning_on_complete_doc(tmp_path, capsys):
    """advisory 段头检查：模板段头齐全时登记无警告。"""
    root = _create_temp_git_repo(tmp_path)
    design_doc = root / "docs" / "specpowers" / "design" / "d.md"
    design_doc.parent.mkdir(parents=True, exist_ok=True)
    design_doc.write_text(
        "# login 设计文档\n\n## 方案对比\nA vs B\n\n## 详细设计\n略\n",
        encoding="utf-8",
    )

    rc = _handle_record_design_doc(
        root, {"design_doc": str(design_doc), "feature": "demo-feat"},
    )

    assert rc == 0
    out = capsys.readouterr().out
    assert "advisory" not in out, "段头齐全不应触发 advisory 警告"


# ---- reset 删目录语义（v3.0：放弃即删工件） ----

def test_reset_feature_deletes_change_dir_and_auto_base(tmp_path):
    """reset --feature：删目标需求 change 目录 + auto_base 分片，其余活跃不受影响。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "feat-a", meta=dict(_EXPLORE_META))
    make_triple(root, "feat-b", meta=dict(_EXPLORE_META))
    auto_base = _write_auto_base(root, "feat-b")

    assert route("reset", root, {"feature": "feat-b", "force": True}) == 0

    assert not change_dir_of(root, "feat-b").exists()
    assert not auto_base.exists()
    assert active_slugs(root) == ["feat-a"]
    assert change_dir_of(root, "feat-a").is_dir()


def test_reset_feature_requires_force(tmp_path):
    """非 CI 模式 reset --feature 无 --force → StateError 要求确认，不删任何工件。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "feat-a", _APPLY_TASKS)

    with pytest.raises(StateError, match="--force"):
        route("reset", root, {"feature": "feat-a"})

    assert change_dir_of(root, "feat-a").is_dir()


def test_reset_multi_active_requires_named_feature(tmp_path):
    """多活跃 + reset 未指名 → StateError 要求显式 --feature（防误删全部）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "feat-a", meta=dict(_EXPLORE_META))
    make_change(root, "feat-b", meta=dict(_EXPLORE_META))

    with pytest.raises(StateError, match="--feature"):
        route("reset", root, {})


def test_reset_force_clears_all_active_and_preserves_runtime(tmp_path):
    """reset --force 全清：删除全部活跃 change 目录，runtime 项目级字段保留。

    v3.0 放弃语义 = 删工件；fallback_count/last_archive_ref 是跨需求生命周期的
    项目级字段（防 reset 刷回退额度），刻意不清。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "feat-a", _APPLY_TASKS)
    write_runtime(root, fallback_count=3, last_archive_ref="abc1234")

    assert route("reset", root, {"force": True}) == 0

    assert active_slugs(root) == []
    assert not change_dir_of(root, "feat-a").exists()
    runtime = load_runtime(root)
    assert runtime["fallback_count"] == 3
    assert runtime["last_archive_ref"] == "abc1234"


def test_handle_reset_clears_residual_lock_file(tmp_path):
    """reset 应清理残留的锁文件（reset 跳过 acquire_lock，需主动 force_unlock）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    # 模拟残留锁文件
    (root / ".specpowers" / ".lock").write_text("999999", encoding="utf-8")

    assert route("reset", root, {}) == 0

    assert not (root / ".specpowers" / ".lock").exists()


# ---- fallback 回退计数（runtime.json，生命周期 1 次额度） ----

def test_fallback_from_apply_increments_count_and_switches_to_full(tmp_path):
    """首次 apply 态重入 propose（回退修订）：runtime fallback_count +1 且放行，
    meta mode 归 full（新轮执行方式在 apply 重新确认）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "fallback-feature", _APPLY_TASKS)  # apply 态

    assert route("propose", root, {"requirement": "fallback-feature"}) == 0

    assert load_runtime(root)["fallback_count"] == 1
    assert read_meta_of(root, "fallback-feature")["mode"] == "full"


def test_second_fallback_rejected_runtime_cap(tmp_path):
    """runtime fallback_count=1 后 apply 态重入 propose → 按「生命周期最多 1 次」拒绝。

    计次跨需求保留（归档/reset 均不清），拒绝时不计次、不改 meta。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    write_runtime(root, fallback_count=1)
    make_triple(root, "fallback-feature", _APPLY_TASKS)

    with pytest.raises(StateError, match="回退次数已达上限"):
        route("propose", root, {"requirement": "fallback-feature"})

    assert load_runtime(root)["fallback_count"] == 1


def test_fast_to_full_propose_reentry_counts_fallback(tmp_path):
    """fast 态重入 propose = fast→full 转换：同走唯一 1 次额度，meta mode 归 full。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "quick-fix", meta={"mode": "fast"})  # fast 态（无三件套）

    assert route("propose", root, {"requirement": "quick-fix"}) == 0

    assert load_runtime(root)["fallback_count"] == 1
    assert read_meta_of(root, "quick-fix")["mode"] == "full"


# ---- init 幂等/冲突（active_slugs 口径） ----

def test_init_idempotent_skips_when_no_active_and_baseline_exists(tmp_path):
    """无活跃需求且 baseline 已存在 → init 幂等跳过，不重建、不报错。

    auto 判定 fresh 的常见起点恰是「上一需求已归档的空转态」，
    无幂等语义时无人值守流程必然撞冲突拦截或被迫 --force 重建 constitution。
    """
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    baseline = root / ".specpowers" / "baseline.json"
    before = baseline.read_text(encoding="utf-8")

    assert route("init", root, extra={}) == 0

    # baseline 未被重建（幂等跳过，不触发 scan）
    assert baseline.read_text(encoding="utf-8") == before
    # 活跃清单保持空（v3.0 无 state 可验，空转即无活跃）
    assert active_slugs(root) == []


def test_init_conflict_with_active_feature_rejected(tmp_path):
    """存在活跃需求（异常残留）→ 幂等不适用，非 CI 无 --force 走冲突拦截。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_change(root, "leftover-feature", meta=dict(_EXPLORE_META))

    with pytest.raises(StateError, match="Active features in progress"):
        route("init", root, extra={})

    # 未确认不删任何工件
    assert change_dir_of(root, "leftover-feature").is_dir()


def test_init_fresh_scans_baseline(tmp_path):
    """全新仓库（无 baseline）→ 正常执行扫描，baseline 落盘，无活跃需求。"""
    root = _create_temp_git_repo(tmp_path)

    assert route("init", root, extra={}) == 0

    assert (root / ".specpowers" / "baseline.json").is_file()
    assert active_slugs(root) == []


def test_init_force_discards_all_active_features(tmp_path):
    """init --force：删除全部活跃 change 目录后重建基线（放弃语义 = 删工件）。"""
    root = _create_temp_git_repo(tmp_path)
    _init_project(root)
    make_triple(root, "feat-a", _APPLY_TASKS)
    make_change(root, "feat-b", meta=dict(_EXPLORE_META))

    assert route("init", root, extra={"force": True}) == 0

    assert active_slugs(root) == []
    assert not change_dir_of(root, "feat-a").exists()
    assert not change_dir_of(root, "feat-b").exists()
