"""Tests for dep_manifest — 单一依赖清单数据源。

验证 dep_manifest 作为 baseline_scanner 与 structure_gate 共享的数据源：
- DEPENDENCY_REGISTRY 完整性（含 dotnet/composer/cabal/stack 等历史遗漏项）
- FILENAME_TO_TYPE 反查表正确性（固定文件名项，glob 项排除）
- guess_dep_type 行为（匹配/不匹配/glob 模式不匹配）
"""

from specpowers_cli.bridge.modules.dep_manifest import (
    DEPENDENCY_REGISTRY,
    FILENAME_TO_TYPE,
    guess_dep_type,
)


def test_registry_is_dict_and_complete():
    """依赖注册表应是 dict 且含历史遗漏的依赖类型。"""
    assert isinstance(DEPENDENCY_REGISTRY, dict)
    # 历史上 structure_gate 漏了这些，验证已合并到单一数据源
    assert "dotnet" in DEPENDENCY_REGISTRY
    assert "composer" in DEPENDENCY_REGISTRY
    assert "cabal" in DEPENDENCY_REGISTRY
    assert "stack" in DEPENDENCY_REGISTRY
    assert "ruby" in DEPENDENCY_REGISTRY  # structure_gate 旧版有、baseline 旧版没有


def test_registry_filename_mapping():
    """dep_type → 文件名映射正确。"""
    assert DEPENDENCY_REGISTRY["npm"] == "package.json"
    assert DEPENDENCY_REGISTRY["maven"] == "pom.xml"
    assert DEPENDENCY_REGISTRY["pip"] == "requirements.txt"
    assert DEPENDENCY_REGISTRY["pip_pyproject"] == "pyproject.toml"


def test_filename_to_type_excludes_glob():
    """反查表不含 glob 模式项（文件名动态，无法固定反查）。"""
    # glob 项（dotnet *.csproj, cabal *.cabal）不应出现在反查表
    assert "*.csproj" not in FILENAME_TO_TYPE
    assert "*.cabal" not in FILENAME_TO_TYPE
    # 固定文件名项应在
    assert FILENAME_TO_TYPE["package.json"] == "npm"
    assert FILENAME_TO_TYPE["Gemfile"] == "ruby"


def test_guess_dep_type_known():
    """guess_dep_type 能识别已知依赖文件。"""
    assert guess_dep_type("package.json") == "npm"
    assert guess_dep_type("pom.xml") == "maven"
    assert guess_dep_type("build.gradle") == "gradle"
    # build.gradle.kts 在 registry 中单独列为 gradle_kts（区分 groovy/kotlin）
    assert guess_dep_type("build.gradle.kts") == "gradle_kts"
    assert guess_dep_type("requirements.txt") == "pip"
    assert guess_dep_type("go.mod") == "go"
    assert guess_dep_type("Cargo.toml") == "rust"


def test_guess_dep_type_unknown():
    """未知文件名返回 None。"""
    assert guess_dep_type("random.txt") is None
    assert guess_dep_type("README.md") is None
    assert guess_dep_type("") is None


def test_guess_dep_type_not_glob():
    """guess_dep_type 不匹配 glob 模式（只匹配固定文件名）。

    例如 dotnet 的 *.csproj 是 glob，传入具体 MyProject.csproj
    不应被 guess_dep_type 识别（gate 层需单独处理 glob）。
    """
    # 具体的 csproj 文件名不在反查表
    assert guess_dep_type("MyProject.csproj") is None
    assert guess_dep_type("foo.cabal") is None


def test_filename_to_type_consistency():
    """FILENAME_TO_TYPE 与 DEPENDENCY_REGISTRY 一致（固定项的逆映射）。"""
    for dep_type, filename in DEPENDENCY_REGISTRY.items():
        if "*" not in filename:
            # 固定文件名项的反查必须指向原 dep_type
            assert FILENAME_TO_TYPE[filename] == dep_type, \
                f"{filename} 反查应为 {dep_type}"
