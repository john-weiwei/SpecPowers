"""清单一致性测试 —— 9 份清单 + 包版本 + pyproject 版本同步校验。

覆盖发布时需人工同步的全部版本源：
  - 4 份宿主 plugin.json（zcode / claude / codex / codebuddy）
  - 1 份 portable 根清单（plugins/specpowers/plugin.json，
    agent-plugins.org 开放标准，Codex 新格式首选；顶层 additionalProperties
    为 false，自定义字段只能下沉 extensions 命名空间）
  - 4 份市场 marketplace.json（仓库根 / .claude-plugin / .agents/plugins / .codebuddy-plugin）
  - specpowers_cli.__version__
  - pyproject.toml 的 project.version

版本单源化策略（v2.2.0 起）：
  - 新增两份市场清单（.claude-plugin / .agents/plugins）不写 version
    （Claude 官方明确总以插件内 plugin.json 的 version 为准，双写易漂移且不告警）
  - 旧市场清单（仓库根 / .codebuddy-plugin）保留 version，写了就必须与 plugin.json 一致

另锁定各市场/宿主规范必需字段：
  - Claude 市场：顶层必须带 owner，source 为 ./ 开头的相对路径（Claude 市场规范）
  - Codex 市场：插件条目必须带 policy.installation / policy.authentication / category，
    source.path 为 ./ 开头、相对市场根（Codex 市场规范）
  - WorkBuddy（codebuddy）首版清单策略：
    - 市场清单必须带 owner（WorkBuddy 市场规范必需字段）
    - plugin.json 不注册 hooks（hooks.json 使用 ${CLAUDE_PLUGIN_ROOT}，
      WorkBuddy 官方变量为 ${CODEBUDDY_PLUGIN_ROOT}，兼容性实测前不启用）
  - Codex 宿主清单注册 hooks（Codex 已支持插件 hooks，与 Claude 同一事件 schema，
    hook 命令收到兼容的 ${CLAUDE_PLUGIN_ROOT} 变量；需用户信任审核后运行）

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

# 4 份市场清单（仓库级；各平台只识别自己约定路径）
MARKETPLACE_MANIFESTS = [
    "marketplace.json",
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
    ".codebuddy-plugin/marketplace.json",
]

# 版本单源化的新市场清单（不写 version，以插件内 plugin.json 为准）
VERSIONLESS_MARKETPLACE_MANIFESTS = [
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
]


# portable 根清单（agent-plugins.org 标准；Codex 检测到它后忽略 .codex-plugin/ 兼容回退）
PORTABLE_MANIFEST = "plugins/specpowers/plugin.json"

# portable 清单顶层允许的字段（schema 顶层 additionalProperties: false）
PORTABLE_ALLOWED_FIELDS = {
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
}


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
    """9 份清单文件必须全部存在。"""
    for rel in PLUGIN_MANIFESTS + MARKETPLACE_MANIFESTS + [PORTABLE_MANIFEST]:
        assert (REPO_ROOT / rel).is_file(), f"清单缺失：{rel}"


def test_plugin_manifests_consistent():
    """4 份宿主 plugin.json + portable 根清单的 name/version 必须一致。"""
    pairs = [(rel, _load_json(rel)) for rel in PLUGIN_MANIFESTS + [PORTABLE_MANIFEST]]
    first_name = pairs[0][1]["name"]
    first_version = pairs[0][1]["version"]
    for rel, manifest in pairs:
        assert manifest["name"] == first_name, f"{rel} 的 name 与其他清单不一致"
        assert manifest["version"] == first_version, f"{rel} 的 version 与其他清单不一致"


def test_marketplace_manifests_consistent():
    """4 份市场清单的插件条目 name 必须与 plugin.json 一致；写了 version 则必须一致。"""
    plugin_manifest = _load_json(PLUGIN_MANIFESTS[0])
    for rel in MARKETPLACE_MANIFESTS:
        marketplace = _load_json(rel)
        entry = marketplace["plugins"][0]
        assert entry["name"] == plugin_manifest["name"], f"{rel} 插件名与 plugin.json 不一致"
        if "version" in entry:
            assert entry["version"] == plugin_manifest["version"], (
                f"{rel} 插件版本与 plugin.json 不一致"
            )


def test_versionless_marketplace_manifests():
    """版本单源化：新市场清单（.claude-plugin / .agents/plugins）不写 version。"""
    for rel in VERSIONLESS_MARKETPLACE_MANIFESTS:
        entry = _load_json(rel)["plugins"][0]
        assert "version" not in entry, (
            f"{rel} 不应写 version——各平台均以插件内 plugin.json 的 version 为准"
        )


def test_claude_marketplace_has_owner():
    """Claude 市场规范要求 marketplace.json 顶层必须带 owner 字段。"""
    marketplace = _load_json(".claude-plugin/marketplace.json")
    owner = marketplace.get("owner")
    assert isinstance(owner, dict) and owner.get("name"), (
        "Claude 市场清单缺少必需的 owner 字段（owner.name）"
    )


def test_claude_marketplace_source_relative():
    """Claude 市场规范：source 必须为 ./ 开头、相对市场根的相对路径。"""
    entry = _load_json(".claude-plugin/marketplace.json")["plugins"][0]
    source = entry["source"]
    assert isinstance(source, str) and source.startswith("./"), (
        "Claude 市场清单 source 必须是 ./ 开头的相对路径字符串"
    )
    assert ".." not in source, "Claude 市场清单 source 不允许包含 ../"


def test_codex_marketplace_policy():
    """Codex 市场规范：插件条目必带 policy.installation/policy.authentication/category。"""
    entry = _load_json(".agents/plugins/marketplace.json")["plugins"][0]
    policy = entry.get("policy", {})
    assert policy.get("installation") in {
        "AVAILABLE",
        "INSTALLED_BY_DEFAULT",
        "NOT_AVAILABLE",
    }, "Codex 市场清单缺少合法的 policy.installation"
    assert policy.get("authentication") in {"ON_INSTALL", "ON_FIRST_USE"}, (
        "Codex 市场清单缺少合法的 policy.authentication"
    )
    assert isinstance(entry.get("category"), str) and entry["category"], (
        "Codex 市场清单缺少必需的 category"
    )


def test_codex_marketplace_source_path():
    """Codex 市场规范：source.path 必须为 ./ 开头、相对市场根（而非 .agents/plugins/）。"""
    entry = _load_json(".agents/plugins/marketplace.json")["plugins"][0]
    source = entry["source"]
    assert isinstance(source, dict), "Codex 市场清单 source 应为对象（source/path）"
    path = source.get("path", "")
    assert path.startswith("./"), "Codex 市场清单 source.path 必须以 ./ 开头"
    assert ".." not in path, "Codex 市场清单 source.path 不允许逃出市场根"
    assert (REPO_ROOT / path).is_dir(), f"Codex 市场清单 source.path 指向的目录不存在：{path}"


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


def test_portable_manifest_schema_fields():
    """portable 清单顶层字段必须落在 schema 允许集合内（additionalProperties: false）。"""
    manifest = _load_json(PORTABLE_MANIFEST)
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", (
        "portable 清单 $schema 必须指向 agent-plugins.org 1.0.0 官方 schema"
    )
    extra = set(manifest) - PORTABLE_ALLOWED_FIELDS
    assert not extra, f"portable 清单出现 schema 外顶层字段（会被拒载）：{sorted(extra)}"


def test_portable_manifest_openai_extension():
    """portable 清单的 OpenAI 扩展：interface 展示元数据 + requirements 依赖声明。"""
    extension = _load_json(PORTABLE_MANIFEST)["extensions"]["com.openai"]
    interface = extension.get("interface", {})
    assert interface.get("displayName"), "com.openai 扩展缺少 interface.displayName"
    assert interface.get("shortDescription"), "com.openai 扩展缺少 interface.shortDescription"
    assert interface.get("category"), "com.openai 扩展缺少 interface.category"
    assert "requirements" in extension, (
        "根清单含 inline extensions.com.openai 时 Codex 会整体忽略 .codex-plugin/ 回退，"
        "依赖声明必须随迁至扩展内"
    )


def test_codex_plugin_has_hooks():
    """Codex 已支持插件 hooks：宿主清单注册 ./hooks/hooks.json（信任审核后生效）。"""
    manifest = _load_json("plugins/specpowers/.codex-plugin/plugin.json")
    assert manifest.get("hooks") == "./hooks/hooks.json", (
        "Codex 清单应注册 hooks（./hooks/hooks.json）——Codex 兼容 ${CLAUDE_PLUGIN_ROOT}，"
        "未信任时自动跳过，注册无副作用"
    )


def test_package_version_matches_manifests():
    """包版本号（__version__ / pyproject）必须与清单 version 一致。"""
    plugin_manifest = _load_json(PLUGIN_MANIFESTS[0])
    expected = plugin_manifest["version"]
    assert __version__ == expected, "specpowers_cli.__version__ 与 plugin.json version 不一致"
    assert _pyproject_version() == expected, "pyproject.toml version 与 plugin.json version 不一致"
