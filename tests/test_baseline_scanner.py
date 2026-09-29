"""Tests for baseline_scanner module — uses temp git repos."""

import tempfile
from pathlib import Path

# package installed via pip - no sys.path needed


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带结构的临时 git 仓库（模板复制 + 一次结构提交）。

    tmp_path 由 pytest 自动管理，测试结束自动清理。
    """
    from tests._gitrepo import create_git_repo, commit_all

    root = create_git_repo(tmp_path / "baseline-repo")

    # Create some structure
    (root / "src" / "controller").mkdir(parents=True)
    (root / "src" / "controller" / "__init__.py").write_text("", encoding="utf-8")
    (root / "src" / "service").mkdir()
    (root / "src" / "service" / "__init__.py").write_text("", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs" / "readme.md").write_text("docs", encoding="utf-8")
    (root / "package.json").write_text('{"name":"test"}', encoding="utf-8")
    commit_all(root, "initial structure")

    return root


def test_load_baseline_empty():
    """Loading baseline from non-existent path returns empty dict."""
    from specpowers_cli.bridge.modules.baseline_scanner import load_baseline
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        result = load_baseline(root)
        assert result == {}


def test_constitution_changed_no_baseline():
    """If no baseline exists, constitution is 'changed'."""
    from specpowers_cli.bridge.modules.baseline_scanner import constitution_changed
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        result = constitution_changed(root)
        assert result is True


def test_constants():
    """Test dependency registry constant is defined (单一数据源 dep_manifest)。"""
    from specpowers_cli.bridge.modules.dep_manifest import DEPENDENCY_REGISTRY, FILENAME_TO_TYPE
    assert isinstance(DEPENDENCY_REGISTRY, dict)
    assert "npm" in DEPENDENCY_REGISTRY
    assert DEPENDENCY_REGISTRY["npm"] == "package.json"
    # 反查表应包含固定文件名项
    assert FILENAME_TO_TYPE.get("package.json") == "npm"
    # glob 模式项不应出现在反查表中
    assert "*.csproj" not in FILENAME_TO_TYPE


def test_baseline_json_structure(tmp_path):
    """Test that scan produces correct structure."""
    from specpowers_cli.bridge.modules.baseline_scanner import scan
    root = _create_temp_git_repo(tmp_path)

    baseline = scan(root)

    assert "git_ref" in baseline
    assert "scanned_at" in baseline
    assert "top_dirs" in baseline
    assert "deps" in baseline
    assert "src_patterns" in baseline
    assert "constitution_hash" in baseline

    assert isinstance(baseline["top_dirs"], list)
    assert "src" in baseline["top_dirs"]


def test_src_patterns_depth_contract(tmp_path):
    """回归：src_patterns 必须收集 src/ 的一级子目录名（与 structure_gate 对齐）。

    原实现错误地收集二级目录名，structure_gate 用 diff 路径的 parts[1]
    （src 下一级）比对时，平铺/嵌套布局下每次 src 变更都误报 new_src_pattern。
    本测试同时锁定扫描器与门禁的端到端契约。
    """
    from specpowers_cli.bridge.modules.baseline_scanner import scan
    from specpowers_cli.bridge.modules.structure_gate import extract_signals
    root = _create_temp_git_repo(tmp_path)

    baseline = scan(root)

    # fixture 中 src/ 的一级子目录是 controller/service（无更深子目录），
    # 旧实现此处返回 []（收集的是二级名），新实现返回一级名
    assert baseline["src_patterns"] == ["controller", "service"]

    # 端到端：baseline 内已有的架构层变更不报信号，新架构层才报
    known = extract_signals("src/controller/user.py | 5 +\n", baseline)
    assert known == []
    fresh = extract_signals("src/repository/user.py | 5 +\n", baseline)
    assert fresh == ["new_src_pattern:repository"]


def test_load_baseline_corrupted_raises_fatal(tmp_path):
    """回归：baseline.json 损坏时显式报 FatalError 并指引重建，而非裸 traceback。"""
    from specpowers_cli.bridge.modules.baseline_scanner import load_baseline
    from specpowers_cli.bridge.core.errors import FatalError
    root = tmp_path / "corrupt-repo"
    (root / ".specpowers").mkdir(parents=True)
    (root / ".specpowers" / "baseline.json").write_text("{not valid json", encoding="utf-8")

    try:
        load_baseline(root)
        raise AssertionError("应抛出 FatalError")
    except FatalError as e:
        assert "corrupted" in str(e)
        assert "baseline" in str(e).lower()


def test_baseline_persistence(tmp_path):
    """Test that scan persists to disk."""
    from specpowers_cli.bridge.modules.baseline_scanner import scan, load_baseline
    root = _create_temp_git_repo(tmp_path)

    baseline = scan(root)
    loaded = load_baseline(root)

    assert loaded["git_ref"] == baseline["git_ref"]


def test_scan_large_repo_branch(tmp_path, monkeypatch):
    """回归测试：大仓库分支不得因 os 作用域问题崩溃。

    scan() 曾在函数中部 import os，使 os 编译为整个函数的局部变量，
    导致大仓库分支（_check_large_repo 为 True 且未设置 shallow 深度）里
    os.environ.get 在 import 语句之前执行，抛 UnboundLocalError。
    """
    from specpowers_cli.bridge.modules import baseline_scanner
    root = _create_temp_git_repo(tmp_path)

    # 强制走大仓库分支，并确保未设置 shallow 深度（否则跳过 os.environ.get）
    monkeypatch.setattr(baseline_scanner, "_check_large_repo", lambda _root: True)
    monkeypatch.delenv("SPECPOWERS_SCAN_DEPTH", raising=False)

    baseline = baseline_scanner.scan(root)

    assert baseline["git_ref"]
    assert "src" in baseline["top_dirs"]
