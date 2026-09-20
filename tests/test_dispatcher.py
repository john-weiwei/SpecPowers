"""Tests for dispatcher — stage routing / state machine / fast mode.

回归覆盖：
- fast 命令的 transition 校验（原 bug：_validate_transition(stage, "fast") 因
  VALID_TRANSITIONS 无 "fast" 键而拒绝所有合法调用，导致 /specpowers.fast 不可用）
- reset 保留 fallback_count
- normalize_feature 中文/英文/边界

作者：005819 | 协作：GLM-5.2
"""

import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.dispatcher import (
    normalize_feature, _validate_transition, VALID_TRANSITIONS,
)
from specpowers_cli.bridge.core.errors import StateError
from specpowers_cli.bridge.core.git_util import is_detached_head


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库。

    tmp_path 由 pytest 自动管理，测试结束自动清理，无需手动删除。
    """
    root = tmp_path / "dispatcher-repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(root), capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(root), capture_output=True, check=True,
    )
    (root / "README.md").write_text("# Test", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "initial"],
        cwd=str(root), capture_output=True, check=True,
    )
    return root


# ---- fast 命令 transition 回归 ----

def test_fast_not_in_valid_transitions_keys():
    """VALID_TRANSITIONS 不应把 'fast' 作为目标 stage key。

    fast 不是状态机的真实目标（它把状态设为 ready+mode=fast），若误加为 key
    会掩盖 _handle_fast 的真实入口校验。此测试固化设计意图。
    """
    assert "fast" not in VALID_TRANSITIONS


def test_validate_transition_ready_to_fast_would_raise():
    """回归：原实现 _validate_transition('ready', 'fast') 会抛 StateError。

    因为 VALID_TRANSITIONS['fast'] 不存在 → 返回 [] → ready 不在空列表里 → 抛错。
    这导致 /specpowers.fast 从 ready 状态根本无法启动。
    修复后 _handle_fast 不再调 _validate_transition(..., 'fast')，而是显式校验
    stage in ['ready']。此测试确认旧的错误调用方式确实会抛错，证明 bug 存在性。
    """
    with pytest.raises(StateError):
        _validate_transition("ready", "fast")


def test_handle_fast_from_ready_succeeds(tmp_path):
    """fast 命令从 ready 状态启动应成功（核心回归）。

    原 bug：_handle_fast 调 _validate_transition(state['stage'], 'fast')，
    因 'fast' 不在 VALID_TRANSITIONS 表而抛 StateError，导致优化模式入口不可用。
    修复后：_handle_fast 显式校验 stage in ['ready']，不再走通用 transition 表。
    """
    from specpowers_cli.bridge.dispatcher import _handle_fast
    from specpowers_cli.bridge.core.fs_state import init_state

    root = _create_temp_git_repo(tmp_path)
    # 构造 ready 状态 + baseline 存在（fast 的硬门禁）
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(exist_ok=True)
    (specpowers_dir / "baseline.json").write_text(
        '{"git_ref":"","top_dirs":[],"deps":{},"src_patterns":[]}',
        encoding="utf-8",
    )
    state = init_state(root)
    state["stage"] = "ready"
    from specpowers_cli.bridge.core.fs_state import save_state
    save_state(root, state)

    # 从 ready 启动 fast 应成功（返回 0），不应抛 StateError
    exit_code = _handle_fast(root, {"requirement": "fix typo"})
    assert exit_code == 0


def test_handle_fast_from_apply_rejected(tmp_path):
    """fast 命令不允许从 apply 阶段启动（应抛 StateError）。"""
    from specpowers_cli.bridge.dispatcher import _handle_fast
    from specpowers_cli.bridge.core.fs_state import init_state, save_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "baseline.json").write_text("{}", encoding="utf-8")
    state = init_state(root)
    state["stage"] = "apply"
    save_state(root, state)

    # 从 apply 启动 fast 应被拒绝
    with pytest.raises(StateError):
        _handle_fast(root, {"requirement": "fix typo"})


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


# ---- proposal 数据流契约校验回归（v2.0.0：校验点从 specify 入口迁到 apply 入口，防探索结论被架空）----

def _setup_apply_prereqs(root: Path, feature: str, proposal_content: str):
    """构造进入 apply 所需的全部前置：state(propose) + constitution/baseline + 三件套。

    Args:
        root: 临时仓库根。
        feature: feature slug。
        proposal_content: proposal.md 内容（由调用方控制是否含数据流契约）。
    """
    from specpowers_cli.bridge.core.fs_state import init_state, save_state

    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(exist_ok=True)
    (specpowers_dir / "baseline.json").write_text(
        '{"git_ref":"","top_dirs":[],"deps":{},"src_patterns":[]}',
        encoding="utf-8",
    )
    state = init_state(root)
    state["stage"] = "propose"
    state["feature"] = feature
    save_state(root, state)
    (specpowers_dir / "constitution.md").write_text("# 项目原则", encoding="utf-8")
    change_dir = root / "openspec" / "changes" / feature
    spec_dir = change_dir / "specs" / feature
    spec_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "proposal.md").write_text(proposal_content, encoding="utf-8")
    (spec_dir / "spec.md").write_text("## ADDED Requirements\n", encoding="utf-8")
    (change_dir / "tasks.md").write_text("### Task 1: 示例\n", encoding="utf-8")


def test_apply_rejects_proposal_without_data_flow_contract(tmp_path):
    """proposal 缺「数据流契约」小节时，apply 前置校验应拒收。

    防止探索结论被架空：agent 若跳过 explore/propose 直写 proposal，
    proposal 不会含数据流契约，_check_proposal_data_flow_contract 将其拦在
    apply 之外，强制回 propose 补全（propose 必须承接 explore 设计文档结论）。
    """
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError

    root = _create_temp_git_repo(tmp_path)
    # proposal 不含数据流契约段头，也不含「无跨链路字段」声明
    _setup_apply_prereqs(root, "login", "## Why\n需要登录\n## What Changes\n加登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError):
        _run_pre_stage_checks(root, "apply", "full", "login")


def test_apply_accepts_proposal_with_data_flow_contract(tmp_path):
    """proposal 含「数据流契约」段头时，apply 前置校验应通过。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks

    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(
        root, "login",
        "## Why\n需要登录\n## 数据流契约\n| 字段 | 来源 |\n|---|---|\n## Impact\n无",
    )

    # 不应抛异常
    _run_pre_stage_checks(root, "apply", "full", "login")


def test_apply_accepts_proposal_with_no_crosslink_decl(tmp_path):
    """proposal 含「本特性无跨链路字段」声明时，apply 前置校验应通过。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks

    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(
        root, "login",
        "## Why\n需要登录\n## 数据流契约\n本特性无跨链路字段\n## Impact\n无",
    )

    # 不应抛异常
    _run_pre_stage_checks(root, "apply", "full", "login")


def test_fast_mode_skips_proposal_contract_check(tmp_path):
    """fast 模式不触发 proposal 数据流契约校验（fast 跳过 explore/propose，无 proposal）。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.fs_state import init_state, save_state

    root = _create_temp_git_repo(tmp_path)
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(exist_ok=True)
    (specpowers_dir / "baseline.json").write_text("{}", encoding="utf-8")
    (specpowers_dir / "constitution.md").write_text("# 项目原则", encoding="utf-8")
    state = init_state(root)
    save_state(root, state)
    # fast 语义：用户已完成编码（修改已跟踪文件留未提交变更，供代码变更检查通过）
    (root / "README.md").write_text("# Test + fix", encoding="utf-8")

    # fast 模式 apply：无 proposal 也不应因数据流契约校验失败
    # （fast 模式下 proposal required=False）
    _run_pre_stage_checks(root, "apply", "fast", "login")


# ---- apply 入口数据流契约语境提示回归 ----

def test_apply_contract_hint_from_propose_path(tmp_path):
    """从 propose 刚进入 apply 时，缺数据流契约的提示应含回 propose 补全语境。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError

    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(root, "login", "## Why\n需要登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError) as exc_info:
        _run_pre_stage_checks(root, "apply", "full", "login", from_stage="propose")

    # 错误提示应包含回 propose 补全的语境引导
    err_msg = str(exc_info.value)
    assert "从 propose 刚进入 apply" in err_msg or "回 /specpowers.propose" in err_msg


def test_apply_contract_hint_absent_without_context(tmp_path):
    """不带 from_stage 调用时，缺数据流契约的提示不应含 fallback 语境。

    确认 from_stage 区分：只有 propose 来源才给语境提示，无来源不给。
    """
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError

    root = _create_temp_git_repo(tmp_path)
    _setup_apply_prereqs(root, "login", "## Why\n需要登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError) as exc_info:
        _run_pre_stage_checks(root, "apply", "full", "login")

    err_msg = str(exc_info.value)
    assert "从 propose 刚进入 apply" not in err_msg


# ---- propose 设计文档登记校验回归（v2.0.0 方案 A：防 explore 被架空）----

def _setup_explore_state(root: Path, feature: str):
    """构造 stage=explore 的 state（propose from explore 校验的起点）。"""
    from specpowers_cli.bridge.core.fs_state import init_state, save_state

    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(exist_ok=True)
    (specpowers_dir / "baseline.json").write_text(
        '{"git_ref":"","top_dirs":[],"deps":{},"src_patterns":[]}',
        encoding="utf-8",
    )
    (specpowers_dir / "constitution.md").write_text("# 项目原则", encoding="utf-8")
    state = init_state(root)
    state["stage"] = "explore"
    state["feature"] = feature
    save_state(root, state)


def test_propose_from_explore_rejects_unregistered_design_doc(tmp_path):
    """从 explore 进入 propose 时，设计文档未登记应被拒收（防 explore 被架空）。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError

    root = _create_temp_git_repo(tmp_path)
    _setup_explore_state(root, "login")

    with pytest.raises(ArtifactMissingError) as exc_info:
        _run_pre_stage_checks(root, "propose", "full", "login", from_stage="explore")

    assert "设计文档未登记" in str(exc_info.value)


def test_propose_from_explore_rejects_missing_design_doc_file(tmp_path):
    """登记的设计文档文件不存在时，propose 应拒收。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError
    from specpowers_cli.bridge.core.fs_state import load_state, save_state

    root = _create_temp_git_repo(tmp_path)
    _setup_explore_state(root, "login")
    state = load_state(root)
    state["design_doc"] = str(root / "docs" / "specpowers" / "design" / "ghost.md")
    save_state(root, state)

    with pytest.raises(ArtifactMissingError):
        _run_pre_stage_checks(root, "propose", "full", "login", from_stage="explore")


def test_propose_from_explore_accepts_registered_design_doc(tmp_path):
    """登记且存在的设计文档通过 propose 前置校验。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.fs_state import load_state, save_state

    root = _create_temp_git_repo(tmp_path)
    _setup_explore_state(root, "login")
    design_doc = root / "docs" / "specpowers" / "design" / "2026-01-01-login-design.md"
    design_doc.parent.mkdir(parents=True, exist_ok=True)
    design_doc.write_text("# login 设计文档\n## 数据流\n本特性无跨链路字段\n", encoding="utf-8")
    state = load_state(root)
    state["design_doc"] = str(design_doc)
    save_state(root, state)

    # 不应抛异常
    _run_pre_stage_checks(root, "propose", "full", "login", from_stage="explore")


def test_propose_from_ready_skips_design_doc_check(tmp_path):
    """从 ready 进入 propose（跳过探索路径）不做设计文档校验。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.fs_state import init_state, save_state

    root = _create_temp_git_repo(tmp_path)
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(exist_ok=True)
    (specpowers_dir / "baseline.json").write_text("{}", encoding="utf-8")
    (specpowers_dir / "constitution.md").write_text("# 项目原则", encoding="utf-8")
    state = init_state(root)
    state["stage"] = "ready"
    save_state(root, state)

    # design_doc 为空也不应触发校验
    _run_pre_stage_checks(root, "propose", "full", "login", from_stage="ready")


# ---- record-design-doc 登记原语回归 ----

def test_handle_record_design_doc_registers_path(tmp_path):
    """登记成功：state.design_doc 写入路径。"""
    from specpowers_cli.bridge.dispatcher import _handle_record_design_doc
    from specpowers_cli.bridge.core.fs_state import init_state, load_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    init_state(root)
    design_doc = root / "docs" / "specpowers" / "design" / "d.md"
    design_doc.parent.mkdir(parents=True, exist_ok=True)
    design_doc.write_text("# 设计", encoding="utf-8")

    rc = _handle_record_design_doc(root, {"design_doc": str(design_doc)})
    assert rc == 0
    assert load_state(root)["design_doc"] == str(design_doc)


def test_handle_record_design_doc_rejects_missing_file(tmp_path):
    """登记失败：文件不存在时拒绝（防登记空指针）。"""
    from specpowers_cli.bridge.dispatcher import _handle_record_design_doc
    from specpowers_cli.bridge.core.errors import FatalError
    from specpowers_cli.bridge.core.fs_state import init_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    init_state(root)

    with pytest.raises(FatalError):
        _handle_record_design_doc(root, {"design_doc": str(root / "ghost.md")})


def test_handle_record_design_doc_rejects_empty_path(tmp_path):
    """登记失败：空路径参数拒绝。"""
    from specpowers_cli.bridge.dispatcher import _handle_record_design_doc
    from specpowers_cli.bridge.core.errors import FatalError
    from specpowers_cli.bridge.core.fs_state import init_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    init_state(root)

    with pytest.raises(FatalError):
        _handle_record_design_doc(root, {"design_doc": ""})


# ---- reset 委托 reset_state 回归 ----

def test_handle_reset_state_matches_default_structure(tmp_path):
    """reset 后 state 应与 DEFAULT_STATE 结构一致（含全部 key）。

    回归：原 _handle_reset 硬编码 state 字典，与 DEFAULT_STATE 脱钩。若 DEFAULT_STATE
    新增 key，reset 后会缺该 key。改委托 reset_state 后保证结构同步。
    """
    from specpowers_cli.bridge.dispatcher import _handle_reset
    from specpowers_cli.bridge.core.fs_state import load_state, DEFAULT_STATE, init_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    init_state(root)

    _handle_reset(root, {})

    state = load_state(root)
    # reset 后应包含 DEFAULT_STATE 的全部 key，且 stage=ready
    assert set(state.keys()) >= set(DEFAULT_STATE.keys())
    assert state["stage"] == "ready"


def test_handle_reset_preserves_fallback_count(tmp_path):
    """reset 应保留 fallback_count（与 reset_state 行为一致）。"""
    from specpowers_cli.bridge.dispatcher import _handle_reset
    from specpowers_cli.bridge.core.fs_state import load_state, init_state, save_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    state = init_state(root)
    state["fallback_count"] = 3
    save_state(root, state)

    _handle_reset(root, {})

    assert load_state(root)["fallback_count"] == 3


def test_handle_reset_clears_residual_lock_file(tmp_path):
    """reset 应清理残留的锁文件（reset 跳过 acquire_lock，需主动 force_unlock）。"""
    from specpowers_cli.bridge.dispatcher import _handle_reset
    from specpowers_cli.bridge.core.fs_state import init_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    init_state(root)
    # 模拟残留锁文件
    (root / ".specpowers" / ".lock").write_text("999999", encoding="utf-8")

    _handle_reset(root, {})

    assert not (root / ".specpowers" / ".lock").exists()


# ---- feature slug 保留字消歧（安全修复回归）----

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


# ---- fallback 回退计数与上限（安全修复回归：文档承诺落地确定性层，v2.0.0：apply→propose）----

def _seed_apply_stage(root: Path, feature: str = "fallback-feature") -> None:
    """把 state 推进到 apply（fast 升级完整流程的回退起点），补齐 propose 前置产物。"""
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    state = dict(DEFAULT_STATE)
    state["stage"] = "apply"
    state["mode"] = "fast"
    state["feature"] = feature
    save_state(root, state)
    # propose from apply 前置：constitution.md（设计文档校验仅 from explore 时触发）
    (root / ".specpowers" / "constitution.md").write_text("# Constitution", encoding="utf-8")


def test_fallback_from_apply_increments_count(tmp_path):
    """首次 apply→propose 回退：fallback_count +1 且放行。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state

    root = _create_temp_git_repo(tmp_path)
    _seed_apply_stage(root)

    rc = route("propose", "full", root, extra={"requirement": "回退补规格"})
    assert rc == 0
    assert load_state(root)["fallback_count"] == 1
    assert load_state(root)["stage"] == "propose"
    assert load_state(root)["mode"] == "full"


def test_second_fallback_rejected(tmp_path):
    """第二次 apply→propose 回退：按「生命周期最多 1 次」承诺拒绝。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state

    root = _create_temp_git_repo(tmp_path)
    _seed_apply_stage(root)

    # 第一次回退成功
    assert route("propose", "full", root, extra={"requirement": "回退补规格"}) == 0
    # 推回 apply 后再次回退 → 拒绝
    state = load_state(root)
    state["stage"] = "apply"
    save_state(root, state)
    with pytest.raises(StateError):
        route("propose", "full", root, extra={"requirement": "再次回退"})


def test_propose_from_explore_not_counted(tmp_path):
    """正常路径（explore→propose）不计回退数。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "explore"
    state["feature"] = "normal-flow"
    save_state(root, state)
    (root / ".specpowers" / "constitution.md").write_text("# Constitution", encoding="utf-8")
    design_doc = root / "docs" / "specpowers" / "design" / "2026-01-01-normal-design.md"
    design_doc.parent.mkdir(parents=True, exist_ok=True)
    design_doc.write_text("# 设计\n## 数据流\n本特性无跨链路字段\n", encoding="utf-8")
    state["design_doc"] = str(design_doc)
    save_state(root, state)

    assert route("propose", "full", root, extra={"requirement": "正常流程"}) == 0
    assert load_state(root)["fallback_count"] == 0
