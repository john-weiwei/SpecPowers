"""v3.0 测试基建：工件构造工厂（替代旧 save_state 现场）。

状态机推导化后，测试现场 = openspec/changes/ 目录工件 + meta + runtime.json，
不再有 state.json 可写。本模块提供构造/断言两用的小工厂，供各测试文件共用。

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

import json
from pathlib import Path

from specpowers_cli.bridge.modules.state_derivation import META_FILENAME
from specpowers_cli.bridge.core.fs_state import RUNTIME_FILENAME


def make_change(root: Path, slug: str, files: list[str] | None = None,
                meta: dict | None = None) -> Path:
    """构造 change 目录工件。

    Args:
        root: 项目根（openspec/changes/ 的父目录）。
        slug: 需求 slug（目录名）。
        files: 相对 change 目录的文件/目录列表，"dir/" 形式建目录。
        meta: 合并写入 .specpowers-meta.json 的字段（None 不写 meta）。

    Returns:
        change 目录路径。
    """
    change = root / "openspec" / "changes" / slug
    change.mkdir(parents=True, exist_ok=True)
    for rel in files or []:
        target = change / rel
        if rel.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x", encoding="utf-8")
    if meta:
        meta_path = change / META_FILENAME
        existing = {}
        if meta_path.exists():
            existing = json.loads(meta_path.read_text(encoding="utf-8"))
        meta_path.write_text(json.dumps({**existing, **meta}, ensure_ascii=False),
                             encoding="utf-8")
    return change


def make_triple(root: Path, slug: str, tasks_text: str = "### Task 1: x\n\n- [ ] a\n",
                meta: dict | None = None) -> Path:
    """构造三件套齐全的 change 目录（tasks 文本可自定义勾选状态）。"""
    change = make_change(root, slug, ["proposal.md", "specs/", "tasks.md"], meta)
    (change / "tasks.md").write_text(tasks_text, encoding="utf-8")
    return change


def write_runtime(root: Path, fallback_count: int = 0, last_archive_ref: str = "") -> Path:
    """构造 runtime.json（fallback 额度 / merge check 基准的测试现场）。"""
    path = root / ".specpowers" / RUNTIME_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "fallback_count": fallback_count,
        "last_archive_ref": last_archive_ref,
    }), encoding="utf-8")
    return path


def read_meta_of(root: Path, slug: str) -> dict:
    """读取需求 meta（断言用；缺失返回空 dict）。"""
    path = root / "openspec" / "changes" / slug / META_FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
