"""Local runtime state & atomic JSON writes（v3.0.0 状态机推导化收缩版）。

v3.0.0 起 state.json 退役（工件推导，见 modules/state_derivation.py），本模块
收缩为两件事：

1. 原子写原语：atomic_write_json / _atomic_replace（meta、runtime、auto_base
   等状态文件共用；Windows PermissionError 短暂重试）
2. runtime.json：仅存两个无法从工件推导的真全局过程状态——
   .specpowers/runtime.json
   {
       "fallback_count": int,    # 人工回退限额计次（跨需求刻意保留，归档/reset 不清）
       "last_archive_ref": str   # 最近一次归档时的 HEAD（merge check 基准）
   }

auto_base 仍按需求分片（.specpowers/auto_base/<slug>.json）：认知层（agent）
在 auto 第 0 步直接写盘、不持锁，多需求并行必须物理隔离防串扰——该文件不在
本模块职责内，本模块仅提供路径与残留清理工具。

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path


def _atomic_replace(src: str, dst: str, retries: int = 5, delay: float = 0.05) -> None:
    """跨平台原子替换，Windows 下对 PermissionError 短暂重试。

    Windows 上 os.replace 目标文件若被杀毒软件/索引器短暂打开，会抛
    [WinError 5] PermissionError。这是高频 IO 场景（如测试连续创建临时仓库）
    的已知痛点。重试几次即可通过，避免在真实工作流中误报。
    作者：005819 | 协作：GLM-5.2
    """
    for attempt in range(retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            # 仅 Windows 下 PermissionError 值得重试（文件被外部短暂占用）
            if sys.platform != "win32" or attempt == retries - 1:
                raise
            time.sleep(delay)


def atomic_write_json(path: Path, data: dict) -> None:
    """原子写 JSON 文件（临时文件 + rename），meta/runtime/auto_base 状态文件共用。

    Prevents half-written corruption on crash.

    作者：005819 | 协作：GLM-5.3
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (ensures same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json",
        prefix=".state-",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # 原子替换：Windows 下对 PermissionError 重试（见 _atomic_replace）
        _atomic_replace(tmp_path, str(path))
    except Exception:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


# ---- runtime.json（真全局过程状态的唯一落点） ----

RUNTIME_FILENAME = "runtime.json"

DEFAULT_RUNTIME = {
    # 人工回退限额计次：整个项目生命周期最多 1 次 apply→propose 回退，
    # 归档/reset 均不清除（跨需求刻意保留，防 reset 刷额度）
    "fallback_count": 0,
    # 最近一次归档时的 HEAD（merge check 基准）
    "last_archive_ref": "",
}


def runtime_path(root: Path) -> Path:
    """runtime.json 路径（.specpowers/runtime.json，本地私有 gitignore）。"""
    return root / ".specpowers" / RUNTIME_FILENAME


def load_runtime(root: Path) -> dict:
    """读取 runtime 状态（缺失返回默认副本；损坏 FatalError 给显式恢复指引）。

    Returns:
        runtime dict（与默认值合并，容忍旧文件缺键）。

    Raises:
        FatalError: runtime.json 损坏（JSON 非法或顶层非对象）。
    """
    from specpowers_cli.bridge.core.errors import FatalError
    path = runtime_path(root)
    if not path.is_file():
        return dict(DEFAULT_RUNTIME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"top level must be a JSON object, got {type(data).__name__}")
    except (json.JSONDecodeError, ValueError, OSError) as e:
        raise FatalError(
            f"runtime.json is corrupted: {e}. "
            f"修复：删除 .specpowers/runtime.json 后重试（fallback_count 额度将重置为 0，"
            f"last_archive_ref 将在下一次归档时重建）。"
        )
    result = dict(DEFAULT_RUNTIME)
    result.update(data)
    return result


def save_runtime(root: Path, runtime: dict) -> None:
    """原子写 runtime 状态（调用方持锁；merge check 基准与 fallback 计次写点）。"""
    atomic_write_json(runtime_path(root), runtime)


# ---- auto_base（按需求分片，路径与残留清理工具） ----

def _auto_base_dir(root: Path) -> Path:
    """auto 基点目录：.specpowers/auto_base/（每需求一个 <slug>.json）。"""
    return root / ".specpowers" / "auto_base"


def auto_base_path(root: Path, feature: str) -> Path:
    """auto 基点文件路径（v2.8.0 起按 feature 隔离）。

    auto_base 由认知层第 0 步直接写盘（不持锁），多需求并行时必须
    物理隔离，是唯一按需求拆分的状态文件。

    Args:
        root: 项目根目录。
        feature: feature slug（auto_base 所属需求）。

    Returns:
        .specpowers/auto_base/<feature>.json 路径。
    """
    return _auto_base_dir(root) / f"{feature}.json"


def cleanup_auto_base(root: Path, keep: list[str]) -> int:
    """清理 auto_base 目录中不属于 keep 集合的残留文件，返回清理数。

    fresh 判定（无活跃需求 → keep 为空即全清）与归档后兜底共用；
    keep 内的 slug 文件（活跃需求的基线）不受影响。

    Args:
        root: 项目根目录。
        keep: 保留的 feature slug 集合。
    """
    base_dir = _auto_base_dir(root)
    if not base_dir.is_dir():
        return 0
    removed = 0
    keep_set = {f"{slug}.json" for slug in keep}
    for entry in base_dir.glob("*.json"):
        if entry.name not in keep_set:
            entry.unlink(missing_ok=True)
            removed += 1
    return removed
