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


def test_handle_fast_from_build_rejected(tmp_path):
    """fast 命令不允许从 build 阶段启动（应抛 StateError）。"""
    from specpowers_cli.bridge.dispatcher import _handle_fast
    from specpowers_cli.bridge.core.fs_state import init_state, save_state

    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir(exist_ok=True)
    (root / ".specpowers" / "baseline.json").write_text("{}", encoding="utf-8")
    state = init_state(root)
    state["stage"] = "build"
    save_state(root, state)

    # 从 build 启动 fast 应被拒绝
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


# ---- proposal 数据流契约校验回归（防止 brainstorming 被架空）----

def _setup_specify_prereqs(root: Path, feature: str, proposal_content: str):
    """构造进入 specify 所需的全部前置：state + constitution + proposal。

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
    state["stage"] = "brainstorm"
    state["feature"] = feature
    save_state(root, state)
    (specpowers_dir / "constitution.md").write_text("# 项目原则", encoding="utf-8")
    change_dir = root / "openspec" / "changes" / feature
    change_dir.mkdir(parents=True, exist_ok=True)
    (change_dir / "proposal.md").write_text(proposal_content, encoding="utf-8")


def test_specify_rejects_proposal_without_data_flow_contract(tmp_path):
    """proposal 缺「数据流契约」小节时，specify 前置校验应拒收。

    防止 brainstorming 被架空：agent 若跳过探索，proposal 不会含数据流契约，
    _check_proposal_data_flow_contract 将其拦在 specify 之外，强制回 brainstorm 补全。
    """
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError

    root = _create_temp_git_repo(tmp_path)
    # proposal 不含数据流契约段头，也不含「无跨链路字段」声明
    _setup_specify_prereqs(root, "login", "## Why\n需要登录\n## What Changes\n加登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError):
        _run_pre_stage_checks(root, "specify", "full", "login")


def test_specify_accepts_proposal_with_data_flow_contract(tmp_path):
    """proposal 含「数据流契约」段头时，specify 前置校验应通过。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks

    root = _create_temp_git_repo(tmp_path)
    _setup_specify_prereqs(
        root, "login",
        "## Why\n需要登录\n## 数据流契约\n| 字段 | 来源 |\n|---|---|\n## Impact\n无",
    )

    # 不应抛异常
    _run_pre_stage_checks(root, "specify", "full", "login")


def test_specify_accepts_proposal_with_no_crosslink_decl(tmp_path):
    """proposal 含「本特性无跨链路字段」声明时，specify 前置校验应通过。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks

    root = _create_temp_git_repo(tmp_path)
    _setup_specify_prereqs(
        root, "login",
        "## Why\n需要登录\n## 数据流契约\n本特性无跨链路字段\n## Impact\n无",
    )

    # 不应抛异常
    _run_pre_stage_checks(root, "specify", "full", "login")


def test_fast_mode_skips_proposal_contract_check(tmp_path):
    """fast 模式不触发 proposal 数据流契约校验（fast 跳过 brainstorm/specify）。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.fs_state import init_state, save_state

    root = _create_temp_git_repo(tmp_path)
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(exist_ok=True)
    (specpowers_dir / "baseline.json").write_text("{}", encoding="utf-8")
    (specpowers_dir / "constitution.md").write_text("# 项目原则", encoding="utf-8")
    state = init_state(root)
    save_state(root, state)

    # fast 模式 plan：无 proposal，也不应因数据流契约校验失败
    # （plan 不消费 proposal，且 fast 模式下 proposal required=False）
    _run_pre_stage_checks(root, "plan", "fast", "login")


# ---- build→specify fallback 路径回归 ----

def test_specify_fallback_from_build_with_contract_succeeds(tmp_path):
    """从 build 回退到 specify 时，proposal 含数据流契约应通过。

    VALID_TRANSITIONS["specify"] 含 "build"，是 fast 用户「升级完整流程」的合法回退路径。
    回退时 mode 被重置为 full，proposal 成为硬必需。本测试确认有合格 proposal 时通过。
    """
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks

    root = _create_temp_git_repo(tmp_path)
    _setup_specify_prereqs(
        root, "login",
        "## Why\n需要登录\n## 数据流契约\n| 字段 | 来源 |\n|---|---|\n## Impact\n无",
    )

    # 模拟从 build fallback，from_stage="build"
    _run_pre_stage_checks(root, "specify", "full", "login", from_stage="build")


def test_specify_fallback_from_build_rejects_proposal_without_contract(tmp_path):
    """从 build 回退到 specify 时，proposal 缺数据流契约应被拦，且提示含 fallback 语境。"""
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError

    root = _create_temp_git_repo(tmp_path)
    _setup_specify_prereqs(root, "login", "## Why\n需要登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError) as exc_info:
        _run_pre_stage_checks(root, "specify", "full", "login", from_stage="build")

    # 错误提示应包含 fallback 语境引导
    err_msg = str(exc_info.value)
    assert "从 build 回退" in err_msg or "升级为完整流程" in err_msg


def test_specify_fallback_hint_absent_from_brainstorm_path(tmp_path):
    """从 brainstorm 正常进入 specify 时，缺数据流契约的提示不应含 fallback 语境。

    确认 from_stage 区分：只有 build 来源才给 fallback 提示，brainstorm 来源不给。
    """
    from specpowers_cli.bridge.dispatcher import _run_pre_stage_checks
    from specpowers_cli.bridge.core.errors import ArtifactMissingError

    root = _create_temp_git_repo(tmp_path)
    _setup_specify_prereqs(root, "login", "## Why\n需要登录\n## Impact\n无")

    with pytest.raises(ArtifactMissingError) as exc_info:
        _run_pre_stage_checks(root, "specify", "full", "login", from_stage="brainstorm")

    err_msg = str(exc_info.value)
    assert "从 build 回退" not in err_msg


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


# ---- fallback 回退计数与上限（安全修复回归：文档承诺落地确定性层）----

def _seed_build_stage(root: Path, feature: str = "fallback-feature") -> None:
    """把 state 推进到 build 并补齐 specify 前置产物（proposal 含数据流契约）。"""
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE

    state = dict(DEFAULT_STATE)
    state["stage"] = "build"
    state["mode"] = "fast"
    state["feature"] = feature
    save_state(root, state)
    # specify 前置：constitution.md + proposal.md（含数据流契约段头）
    (root / ".specpowers" / "constitution.md").write_text("# Constitution", encoding="utf-8")
    proposal = root / "openspec" / "changes" / feature / "proposal.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text("## 数据流契约\n\n本特性无跨链路字段\n", encoding="utf-8")


def test_fallback_from_build_increments_count(tmp_path):
    """首次 build→specify 回退：fallback_count +1 且放行。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state

    root = _create_temp_git_repo(tmp_path)
    _seed_build_stage(root)

    rc = route("specify", "full", root, extra={"requirement": "回退补规格"})
    assert rc == 0
    assert load_state(root)["fallback_count"] == 1
    assert load_state(root)["stage"] == "specify"
    assert load_state(root)["mode"] == "full"


def test_second_fallback_rejected(tmp_path):
    """第二次 build→specify 回退：按「生命周期最多 1 次」承诺拒绝。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state

    root = _create_temp_git_repo(tmp_path)
    _seed_build_stage(root)

    # 第一次回退成功
    assert route("specify", "full", root, extra={"requirement": "回退补规格"}) == 0
    # 推回 build 后再次回退 → 拒绝
    state = load_state(root)
    state["stage"] = "build"
    save_state(root, state)
    with pytest.raises(StateError):
        route("specify", "full", root, extra={"requirement": "再次回退"})


def test_specify_from_brainstorm_not_counted(tmp_path):
    """正常路径（brainstorm→specify）不计回退数。"""
    from specpowers_cli.bridge.dispatcher import route
    from specpowers_cli.bridge.core.fs_state import load_state, save_state, DEFAULT_STATE

    root = _create_temp_git_repo(tmp_path)
    state = dict(DEFAULT_STATE)
    state["stage"] = "brainstorm"
    state["feature"] = "normal-flow"
    save_state(root, state)
    (root / ".specpowers" / "constitution.md").write_text("# Constitution", encoding="utf-8")
    proposal = root / "openspec" / "changes" / "normal-flow" / "proposal.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text("## 数据流契约\n\n本特性无跨链路字段\n", encoding="utf-8")

    assert route("specify", "full", root, extra={"requirement": "正常流程"}) == 0
    assert load_state(root)["fallback_count"] == 0
