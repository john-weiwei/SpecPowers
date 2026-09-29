"""根级 pytest 共享配置。

1. autouse 复位进程级全局（信号处理标志 / openspec 探测缓存 / git 路径缓存 /
   锁持有注册表）——这些模块级全局一旦被某用例触发，会跨用例存活并污染
   后续 mock 场景。
2. autouse 清理 SPECPOWERS_* 环境变量——开发者机器导出的 SPECPOWERS_CI=1
   会让 init 冲突检查静默放行、SCAN_DEPTH 会静音告警，行为悄然改变。
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_process_globals(monkeypatch):
    """每个用例前后保持进程级全局与环境变量干净。"""
    from specpowers_cli.bridge import dispatcher
    monkeypatch.setattr(dispatcher, "_signal_registered", False)
    monkeypatch.setattr(dispatcher, "_current_root", None)

    from specpowers_cli.bridge.adapters import openspec
    monkeypatch.setattr(openspec, "_OPENSPEC_CMD", None)

    from specpowers_cli.bridge.core import git_util
    monkeypatch.setattr(git_util, "_GIT_PATH", None)

    from specpowers_cli.bridge.core import lock
    lock._held_lock_fds.clear()

    for var in ("SPECPOWERS_CI", "SPECPOWERS_VERBOSE", "SPECPOWERS_SCAN_DEPTH"):
        monkeypatch.delenv(var, raising=False)
