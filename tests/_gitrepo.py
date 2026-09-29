"""共享的测试 git 仓库构造工具。

原 tests/ 下 8 份各写一份的 _create_temp_git_repo（且细节已漂移：-q、
encoding、提交次数不一）统一收敛到这里。每个用例仓库由会话级模板复制
生成（约 10ms），替代逐用例 git init + config + add + commit（Windows
进程创建开销下约 500-800ms）——这是测试套件 121 秒耗时的大头。
"""

import atexit
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), capture_output=True, check=True)


@lru_cache(maxsize=1)
def _template_dir() -> str:
    """构建会话级模板仓库（git init + config + 单次 README 提交），进程退出时清理。"""
    base = Path(tempfile.mkdtemp(prefix="specpowers-git-tpl-"))
    atexit.register(shutil.rmtree, str(base), ignore_errors=True)

    repo = base / "tpl"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test User"], repo)
    (repo / "README.md").write_text("# Test", encoding="utf-8")
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)
    return str(repo)


def create_git_repo(dest: Path, commits: int = 1) -> Path:
    """在 dest 创建临时 git 仓库（模板复制 + 按需追加占位提交）。

    Args:
        dest: 目标路径（通常 tmp_path / "<name>"），须不存在。
        commits: 需要的历史提交数（>1 时追加占位提交，供 HEAD~1 对比用例）。

    Returns:
        仓库根路径。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_template_dir(), dest)
    for i in range(commits - 1):
        (dest / f"placeholder_{i}.md").write_text(f"placeholder {i}", encoding="utf-8")
        commit_all(dest, f"commit {i + 2}")
    return dest


def commit_all(repo: Path, message: str) -> None:
    """在既有仓库中提交全部变更（测试辅助）。"""
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", message], repo)
