"""fs_state 模块测试 — v3.0 收缩后职责（runtime.json + 原子写原语 + auto_base 工具）。

state.json 状态机已退役（流水线状态由 modules/state_derivation.py 从工件推导），
fs_state 仅剩四件事，用例按职责一一对应：

1. runtime.json：.specpowers/runtime.json 的默认值 / save-load 往返 /
   损坏 FatalError（含 fallback_count 重置的恢复指引）/ 缺键与默认值合并
2. atomic_write_json：原子写原语（自动建父目录、内容完整落盘），
   meta / runtime / auto_base 状态文件共用
3. auto_base_path：auto 基点按需求分片的路径规则
4. cleanup_auto_base：keep 语义（活跃需求的基线保留，其余残留清理）

作者：005819 | 协作：GLM-5.3 | 日期：2026-11-17
"""

import json
from pathlib import Path

import pytest

from specpowers_cli.bridge.core.fs_state import (
    DEFAULT_RUNTIME,
    RUNTIME_FILENAME,
    atomic_write_json,
    auto_base_path,
    cleanup_auto_base,
    load_runtime,
    runtime_path,
    save_runtime,
)
from specpowers_cli.bridge.core.errors import FatalError
from tests.helpers_v3 import write_runtime


def test_load_runtime_default(tmp_path: Path):
    """runtime.json 缺失时返回默认副本（fallback_count=0 / last_archive_ref 空串）。

    同时验证返回的是副本：调用方就地修改读出值不得污染模块级 DEFAULT_RUNTIME，
    否则同一进程内的后续读取会被串改。
    """
    runtime = load_runtime(tmp_path)
    assert runtime["fallback_count"] == 0
    assert runtime["last_archive_ref"] == ""
    assert runtime == DEFAULT_RUNTIME
    # 副本语义：改读出值不影响默认模板
    runtime["fallback_count"] = 99
    assert DEFAULT_RUNTIME["fallback_count"] == 0
    assert load_runtime(tmp_path)["fallback_count"] == 0


def test_runtime_round_trip(tmp_path: Path):
    """save_runtime 后 load_runtime 应完整往返两个过程字段。

    fallback_count（人工回退计次）与 last_archive_ref（merge check 基准）
    是仅有的两个无法从工件推导的真全局过程状态。
    """
    save_runtime(tmp_path, {"fallback_count": 1, "last_archive_ref": "abc1234"})
    loaded = load_runtime(tmp_path)
    assert loaded["fallback_count"] == 1
    assert loaded["last_archive_ref"] == "abc1234"
    # 落盘路径即约定路径：.specpowers/runtime.json
    assert runtime_path(tmp_path) == tmp_path / ".specpowers" / RUNTIME_FILENAME
    assert (tmp_path / ".specpowers" / "runtime.json").is_file()


def test_load_runtime_corrupted_raises_fatal_error_with_guidance(tmp_path: Path):
    """runtime.json 损坏应抛 FatalError，指引文案含 fallback_count 重置说明。

    覆盖两类损坏：JSON 非法（截断/手改坏）与顶层非对象（数组/标量）。
    FatalError 属显式人工干预错误——用户需知道删除文件的代价
    （fallback 额度重置为 0）才能做出正确决定。
    """
    # 场景一：非法 JSON
    path = write_runtime(tmp_path)
    path.write_text("{fallback_count: ", encoding="utf-8")
    with pytest.raises(FatalError) as exc_info:
        load_runtime(tmp_path)
    message = str(exc_info.value)
    assert "runtime.json" in message
    assert "fallback_count" in message  # 恢复指引必须告知额度将重置
    assert "last_archive_ref" in message

    # 场景二：顶层非 JSON 对象（数组）
    path.write_text('[1, 2, 3]', encoding="utf-8")
    with pytest.raises(FatalError):
        load_runtime(tmp_path)


def test_load_runtime_merges_missing_keys(tmp_path: Path):
    """旧文件缺键时与默认值合并（容忍文件演进，不做硬性 schema 校验）。

    只含 fallback_count 的旧文件：last_archive_ref 补默认空串；
    空 dict：全字段落回默认值。
    """
    path = write_runtime(tmp_path)
    path.write_text(json.dumps({"fallback_count": 2}), encoding="utf-8")
    runtime = load_runtime(tmp_path)
    assert runtime["fallback_count"] == 2
    assert runtime["last_archive_ref"] == ""

    path.write_text(json.dumps({}), encoding="utf-8")
    assert load_runtime(tmp_path) == DEFAULT_RUNTIME


def test_atomic_write_json_creates_parent_dirs(tmp_path: Path):
    """atomic_write_json 应自动创建多级父目录并完整落盘。

    meta / runtime / auto_base 的写点依赖该原语自建目录（调用方无需
    预先 mkdir），中文等非 ASCII 内容经 ensure_ascii=False 原样保留。
    """
    target = tmp_path / "a" / "b" / "c" / "state.json"
    data = {"note": "中文内容", "count": 3}
    atomic_write_json(target, data)
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8")) == data
    # 目录内不残留临时文件（.state-*.json 前缀），原子替换干净收尾
    leftovers = [p.name for p in target.parent.iterdir() if p.name != "state.json"]
    assert leftovers == []


def test_auto_base_path_and_cleanup_keep_semantics(tmp_path: Path):
    """auto_base 按需求分片路径；cleanup_auto_base 只清 keep 之外的残留。

    auto 第 0 步由认知层直接写盘（不持锁），多需求并行必须物理隔离，
    因此路径形如 .specpowers/auto_base/<slug>.json；清理时活跃需求
    （keep 集合）的基线文件不受影响。
    """
    # 分片路径规则
    assert auto_base_path(tmp_path, "feat-a") == tmp_path / ".specpowers" / "auto_base" / "feat-a.json"
    assert auto_base_path(tmp_path, "feat-b") != auto_base_path(tmp_path, "feat-a")

    # keep 语义：保留 feat-a，清理其余残留（测试现场直接落盘，先建分片目录）
    base_dir = tmp_path / ".specpowers" / "auto_base"
    base_dir.mkdir(parents=True)
    for slug in ("feat-a", "feat-b", "stale"):
        auto_base_path(tmp_path, slug).write_text("{}", encoding="utf-8")
    removed = cleanup_auto_base(tmp_path, keep=["feat-a"])
    assert removed == 2
    assert auto_base_path(tmp_path, "feat-a").is_file()
    assert not auto_base_path(tmp_path, "feat-b").exists()
    assert not auto_base_path(tmp_path, "stale").exists()

    # 无活跃需求（keep 为空）→ 全清
    auto_base_path(tmp_path, "feat-a").write_text("{}", encoding="utf-8")
    assert cleanup_auto_base(tmp_path, keep=[]) == 1
    assert not auto_base_path(tmp_path, "feat-a").exists()

    # 目录不存在 → 幂等返回 0
    assert cleanup_auto_base(tmp_path, keep=[]) == 0
