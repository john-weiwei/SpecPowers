"""Tests for baseline_scanner module — uses temp git repos."""

import tempfile
import subprocess
from pathlib import Path

# package installed via pip - no sys.path needed


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带结构的临时 git 仓库。

    tmp_path 由 pytest 自动管理，测试结束自动清理。
    """
    root = tmp_path / "baseline-repo"
    root.mkdir()

    subprocess.run(["git", "init"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(root), capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(root), capture_output=True
    )

    # Create some files
    (root / "README.md").write_text("# Test")
    (root / "src").mkdir(exist_ok=True)
    (root / "src" / "controller").mkdir(exist_ok=True)
    (root / "src" / "controller" / "__init__.py").write_text("")
    (root / "src" / "service").mkdir(exist_ok=True)
    (root / "src" / "service" / "__init__.py").write_text("")
    (root / "docs").mkdir(exist_ok=True)
    (root / "docs" / "readme.md").write_text("docs")
    (root / "package.json").write_text('{"name":"test"}')

    subprocess.run(["git", "add", "-A"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial structure"],
        cwd=str(root), capture_output=True, check=True
    )

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
