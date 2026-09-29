"""Tests for facade — 全局选项解析与子命令分发。

回归覆盖：
- --root <path> 与 --root=<path> 两种形式都能被正确解析
- --root 必须从 requirement 中移除，不能被 " ".join(args) 拼进 feature 名
  （原 bug：explore "需求" --root . 导致 state.feature 变成
  「洗护到家黄牛充值限制---root」一类的脏数据）

作者：005819 | 协作：GLM-5.2
"""

import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.facade import _extract_global_options, main
from specpowers_cli.bridge.core.fs_state import load_state


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库（会话级模板复制，约 10ms）。"""
    from tests._gitrepo import create_git_repo

    return create_git_repo(tmp_path / "facade-repo")


def _seed_ready_state(root: Path) -> None:
    """把 state 推进到 ready 并补齐 explore 前置产物，使 explore 合法。"""
    from specpowers_cli.bridge.core.fs_state import save_state, DEFAULT_STATE
    state = dict(DEFAULT_STATE)
    state["stage"] = "ready"
    save_state(root, state)
    # explore 前置检查要求 constitution.md 存在
    (root / ".specpowers" / "constitution.md").write_text("# Constitution", encoding="utf-8")


# ---------- _extract_global_options 单元测试 ----------

def test_extract_root_space_form_removes_both_tokens():
    """--root <path> 形式：root 与 path 都从剩余参数移除。"""
    root_arg, remaining = _extract_global_options(["需求", "--root", "."])
    assert root_arg == "."
    assert remaining == ["需求"]


def test_extract_root_equals_form():
    """--root=<path> 形式：等号后作为值。"""
    root_arg, remaining = _extract_global_options(["需求", "--root=./repo"])
    assert root_arg == "./repo"
    assert remaining == ["需求"]


def test_extract_no_root_returns_none_and_unchanged():
    """没有 --root 时，root_arg 为 None 且剩余参数不变。"""
    root_arg, remaining = _extract_global_options(["需求", "更多", "描述"])
    assert root_arg is None
    assert remaining == ["需求", "更多", "描述"]


def test_extract_root_without_value_rejected(capsys):
    """--root 出现在末尾无值时：直接报错退出，不得把 "--root" 拼进 requirement。"""
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        _extract_global_options(["需求", "--root"])
    assert exc_info.value.code == 2
    assert "--root requires a path value" in capsys.readouterr().err


def test_extract_root_value_cannot_be_next_option(capsys):
    """--root 后紧跟另一选项时视为缺值：报错退出而非吞参。"""
    import pytest

    with pytest.raises(SystemExit) as exc_info:
        _extract_global_options(["--root", "--force", "需求"])
    assert exc_info.value.code == 2
    assert "--root requires a path value" in capsys.readouterr().err


# ---------- 通过 main() 的回归测试 ----------

def test_explore_root_not_merged_into_feature(tmp_path: Path):
    """回归：explore 带正确参数时 --root 不得污染 feature 名。"""
    root = _create_temp_git_repo(tmp_path)
    _seed_ready_state(root)

    rc = main(["explore", "洗护到家黄牛充值限制", "--root", str(root)])
    assert rc == 0

    feature = load_state(root)["feature"]
    # feature 应等于纯需求 normalize 结果，绝不含 root/--root/路径字符
    assert feature == "洗护到家黄牛充值限制"
    assert "--root" not in feature
    assert "root" not in feature.lower()
    assert "." not in feature


def test_explore_root_equals_form_not_merged_into_feature(tmp_path: Path):
    """回归：--root=<path> 形式同样不得污染 feature 名。"""
    root = _create_temp_git_repo(tmp_path)
    _seed_ready_state(root)

    rc = main(["explore", "--root=" + str(root), "登录模块重构"])
    assert rc == 0

    feature = load_state(root)["feature"]
    assert feature == "登录模块重构"
    assert "--root" not in feature
    assert "root" not in feature.lower()


# ---- gate --base 参数注入拒绝（安全修复回归）----

def test_gate_rejects_option_like_base(tmp_path, capsys):
    """--base 值以 '-' 开头（git 选项注入，如 --output=）必须被拒绝。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["gate", "--root", str(root), "--base", "--output=/tmp/evil"])
    assert rc == 2
    assert "invalid --base value" in capsys.readouterr().err


def test_gate_rejects_metachar_base(tmp_path, capsys):
    """--base 值含空格等非法字符时被拒绝。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["gate", "--root", str(root), "--base", "HEAD; rm -rf /"])
    assert rc == 2


def test_gate_accepts_normal_ref_base(tmp_path):
    """--base 正常 git ref（如 HEAD~1）照常放行。"""
    root = _create_temp_git_repo(tmp_path)
    # HEAD~1 需要仓库至少 2 个提交，补一个
    (root / "CHANGE.md").write_text("# Change", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "second"],
        cwd=str(root), capture_output=True, check=True,
    )
    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0


# ---- gate scope 修改范围比对 + resume-probe 子命令（v2.3.0）----

def _seed_propose_state(root: Path, feature: str) -> None:
    """把 state 推到 propose 并锁定 feature（gate scope 比对的前置）。"""
    from specpowers_cli.bridge.core.fs_state import DEFAULT_STATE, save_state
    state = dict(DEFAULT_STATE)
    state["stage"] = "propose"
    state["feature"] = feature
    save_state(root, state)


def _seed_tasks_with_scope(root: Path, feature: str, scope_decl: str | None) -> None:
    """构造 change 目录与 tasks.md（scope_decl=None 表示不写声明行）。"""
    change_dir = root / "openspec" / "changes" / feature
    change_dir.mkdir(parents=True)
    comment = "<!--\n推荐：conductor\n修改范围：%s\n-->" % scope_decl if scope_decl else "<!--\n推荐：conductor\n-->"
    (change_dir / "tasks.md").write_text(comment, encoding="utf-8")


def test_gate_scope_out_of_scope(tmp_path, capsys):
    """声明 README.md 而实际改动含 placeholder → scope=out_of_scope 列出越界文件。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_propose_state(root, "demo")
    _seed_tasks_with_scope(root, "demo", "README.md")
    (root / "placeholder_0.md").write_text("out of scope change", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"]["status"] == "out_of_scope"
    assert "placeholder_0.md" in out["scope"]["out_of_scope"]
    assert out["scope"]["declared"] == ["README.md"]


def test_gate_scope_pass(tmp_path, capsys):
    """改动全部落在声明范围内 → scope=pass。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_propose_state(root, "demo")
    _seed_tasks_with_scope(root, "demo", "placeholder_0.md, openspec/, .specpowers/")
    (root / "placeholder_0.md").write_text("in scope change", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"]["status"] == "pass"


def test_gate_scope_undeclared(tmp_path, capsys):
    """tasks.md 存在但缺修改范围声明 → scope=undeclared（旧产物兼容）。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_propose_state(root, "demo")
    _seed_tasks_with_scope(root, "demo", None)
    (root / "placeholder_0.md").write_text("changed", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"]["status"] == "undeclared"
    assert out["scope"]["out_of_scope"] == []


def test_gate_scope_omitted_without_tasks_md(tmp_path, capsys):
    """无 tasks.md（fast/CI 场景）→ 输出 JSON 不带 scope 键（旧消费者兼容）。"""
    import json

    root = _create_temp_git_repo(tmp_path)
    _seed_propose_state(root, "demo")
    (root / "CHANGE.md").write_text("# x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "second"],
        cwd=str(root), capture_output=True, check=True,
    )

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "scope" not in out


def test_resume_probe_subcommand_silent_on_fresh(tmp_path, capsys):
    """resume-probe 在无活跃状态的项目 exit 0 且输出空（零噪音）。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["resume-probe", "--root", str(root)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_resume_probe_subcommand_reports_active_pipeline(tmp_path, capsys):
    """resume-probe 在活跃流水线输出续跑提示（hook 注入的内容源）。"""
    _seed_propose_state(tmp_path, "demo")
    (tmp_path / "openspec" / "changes" / "demo").mkdir(parents=True)
    (tmp_path / "openspec" / "changes" / "demo" / "tasks.md").write_text("# t", encoding="utf-8")

    rc = main(["resume-probe", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "demo" in out
    assert "/specpowers-propose" in out


def test_resume_probe_survives_corrupt_state(tmp_path, capsys):
    """state.json 损坏时 resume-probe 仍 exit 0（探测绝不阻断）。"""
    root = _create_temp_git_repo(tmp_path)
    (root / ".specpowers").mkdir()
    (root / ".specpowers" / "state.json").write_text("{broken", encoding="utf-8")
    rc = main(["resume-probe", "--root", str(root)])
    assert rc == 0
