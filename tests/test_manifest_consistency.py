"""清单一致性测试 —— 6 份清单 + 包版本 + pyproject 版本同步校验。

覆盖发布时需人工同步的全部版本源：
  - 4 份宿主 plugin.json（zcode / claude / codex / codebuddy）
  - 2 份市场 marketplace.json（仓库根 / .codebuddy-plugin）
  - specpowers_cli.__version__
  - pyproject.toml 的 project.version

另锁定 WorkBuddy（codebuddy）首版清单策略：
  - 市场清单必须带 owner（WorkBuddy 市场规范必需字段）
  - plugin.json 不注册 hooks（hooks.json 使用 ${CLAUDE_PLUGIN_ROOT}，
    WorkBuddy 官方变量为 ${CODEBUDDY_PLUGIN_ROOT}，兼容性实测前不启用，
    与 Codex 版无 hooks 的先例一致）

作者：SpecPowers Team 2026-09-20（ZCode / GLM-5.3）
"""

import json
import re
from pathlib import Path

from specpowers_cli import __version__

REPO_ROOT = Path(__file__).resolve().parent.parent

# 4 份宿主清单（插件目录内）
PLUGIN_MANIFESTS = [
    "plugins/specpowers/.zcode-plugin/plugin.json",
    "plugins/specpowers/.claude-plugin/plugin.json",
    "plugins/specpowers/.codex-plugin/plugin.json",
    "plugins/specpowers/.codebuddy-plugin/plugin.json",
]

# 2 份市场清单（仓库级）
MARKETPLACE_MANIFESTS = [
    "marketplace.json",
    ".codebuddy-plugin/marketplace.json",
]


def _load_json(rel_path):
    """读取仓库内 JSON 文件并解析为 dict。"""
    return json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))


def _pyproject_version():
    """从 pyproject.toml 提取 project.version。"""
    content = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    assert match, "pyproject.toml 中未找到 version 字段"
    return match.group(1)


def test_all_manifests_exist():
    """6 份清单文件必须全部存在。"""
    for rel in PLUGIN_MANIFESTS + MARKETPLACE_MANIFESTS:
        assert (REPO_ROOT / rel).is_file(), f"清单缺失：{rel}"


def test_plugin_manifests_consistent():
    """4 份宿主 plugin.json 的 name/version 必须一致。"""
    pairs = [(rel, _load_json(rel)) for rel in PLUGIN_MANIFESTS]
    first_name = pairs[0][1]["name"]
    first_version = pairs[0][1]["version"]
    for rel, manifest in pairs:
        assert manifest["name"] == first_name, f"{rel} 的 name 与其他清单不一致"
        assert manifest["version"] == first_version, f"{rel} 的 version 与其他清单不一致"


def test_marketplace_manifests_consistent():
    """2 份市场清单的插件条目必须与 plugin.json 的 name/version 一致。"""
    plugin_manifest = _load_json(PLUGIN_MANIFESTS[0])
    for rel in MARKETPLACE_MANIFESTS:
        marketplace = _load_json(rel)
        entry = marketplace["plugins"][0]
        assert entry["name"] == plugin_manifest["name"], f"{rel} 插件名与 plugin.json 不一致"
        assert entry["version"] == plugin_manifest["version"], f"{rel} 插件版本与 plugin.json 不一致"


def test_codebuddy_marketplace_has_owner():
    """WorkBuddy 市场规范要求 marketplace.json 必须带 owner 字段。"""
    marketplace = _load_json(".codebuddy-plugin/marketplace.json")
    assert "owner" in marketplace and marketplace["owner"], "WorkBuddy 市场清单缺少必需的 owner 字段"


def test_codebuddy_plugin_has_no_hooks():
    """WorkBuddy 首版策略：plugin.json 不注册 hooks（变量兼容性实测前不启用）。"""
    manifest = _load_json("plugins/specpowers/.codebuddy-plugin/plugin.json")
    assert "hooks" not in manifest, (
        "WorkBuddy 清单注册了 hooks——若 ${CLAUDE_PLUGIN_ROOT} 兼容性已实测通过，"
        "可移除本用例并补充 hooks 字段（./hooks/hooks.json）"
    )


def test_package_version_matches_manifests():
    """包版本号（__version__ / pyproject）必须与清单 version 一致。"""
    plugin_manifest = _load_json(PLUGIN_MANIFESTS[0])
    expected = plugin_manifest["version"]
    assert __version__ == expected, "specpowers_cli.__version__ 与 plugin.json version 不一致"
    assert _pyproject_version() == expected, "pyproject.toml version 与 plugin.json version 不一致"
