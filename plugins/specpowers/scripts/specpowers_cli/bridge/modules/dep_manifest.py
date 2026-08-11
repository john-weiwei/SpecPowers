"""依赖清单单一数据源。

baseline_scanner 与 structure_gate 共享此清单，避免三处各维护一份导致不一致。

数据结构说明：
- DEPENDENCY_REGISTRY: dep_type → 文件名（可能是固定文件名或 glob 模式）
  baseline_scanner 按此扫描磁盘上的依赖文件。
- FILENAME_TO_TYPE: 固定文件名 → dep_type 的反查表（不含 glob 项，因为 glob
  文件名是动态的，需在扫描时单独匹配）。
  structure_gate 按此判断 git diff 中是否出现了依赖文件变更。

新增依赖类型时只需在 DEPENDENCY_REGISTRY 增加一项，并视情况在 FILENAME_TO_TYPE
补上固定文件名映射（若是 glob 模式则不需要也无法加入反查表）。
"""

# dep_type → 文件名或 glob 模式（用于磁盘扫描）
DEPENDENCY_REGISTRY: dict[str, str] = {
    "npm": "package.json",
    "maven": "pom.xml",
    "gradle": "build.gradle",
    "gradle_kts": "build.gradle.kts",
    "pip": "requirements.txt",
    "pip_setup": "setup.py",
    "pip_pyproject": "pyproject.toml",
    "go": "go.mod",
    "rust": "Cargo.toml",
    "dotnet": "*.csproj",
    "composer": "composer.json",
    "sbt": "build.sbt",
    "cabal": "*.cabal",
    "stack": "stack.yaml",
    "ruby": "Gemfile",
}

# 固定文件名 → dep_type 反查表（glob 模式项不纳入，因文件名动态）
FILENAME_TO_TYPE: dict[str, str] = {
    filename: dep_type
    for dep_type, filename in DEPENDENCY_REGISTRY.items()
    if "*" not in filename
}


def guess_dep_type(filename: str) -> str | None:
    """根据文件名反查依赖类型。

    仅匹配固定文件名（不支持 glob）。返回 None 表示非已知依赖文件或为 glob 模式。
    """
    return FILENAME_TO_TYPE.get(filename)
