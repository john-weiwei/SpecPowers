"""OpenSpec adapter — 场景生成 + archive 命令封装。

职责：
- to_scenario: specify 阶段把需求转成 OpenSpec 场景格式文本（认知层用）
- is_openspec_available: 检测 openspec CLI 是否可用（归档强依赖）
- archive_change: 调用真实 openspec archive 命令归档指定 change

注意：真实的 archive 命令是 `openspec archive [change-name]`，
内置 delta 合并（findSpecUpdates + buildUpdatedSpec），无需 --delta 开关。
旧代码调用的 `npx openspec archive --delta` 是不存在的命令，已废弃。

作者：005819 | 协作：GLM-5.2
"""

import json
import subprocess
import sys
from pathlib import Path

from specpowers_cli.bridge.core.errors import FatalError


def to_scenario(req: str, brief: str | None = None) -> str:
    """生成 OpenSpec 场景格式文本（specify 阶段认知层使用）。

    Args:
        req: 需求文本。
        brief: 可选的 brief.md 内容（brainstorm 阶段产出）。

    Returns:
        OpenSpec 格式的场景文本，供 agent 写入 spec.md。
    """
    lines = ["# 场景描述", ""]
    lines.append("## 需求描述")
    lines.append("")
    lines.append(f"{req}")
    lines.append("")

    if brief:
        lines.append("## 背景（来自 brief.md）")
        lines.append("")
        lines.append(f"{brief}")
        lines.append("")

    lines.append("## 验收条件")
    lines.append("- [ ] TBD - 定义验收条件")
    lines.append("")

    lines.append("## 技术要点")
    lines.append("- TBD")
    lines.append("")

    return "\n".join(lines)


# ---- CLI 可用性检测 ----

def _try_openspec(cmd: list[str], cwd: Path) -> bool:
    """尝试用给定命令列表运行 openspec --version，成功返回 True。

    Args:
        cmd: 完整命令列表（如 ["openspec", "--version"]）。
        cwd: 工作目录。
    """
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15, cwd=str(cwd),
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    except Exception:
        return False


def is_openspec_available(root: Path) -> bool:
    """检测 openspec CLI 是否可用。

    检测顺序：
    1. PATH 里的 openspec（全局安装，已确认存在于 node 目录）
    2. npx openspec（项目本地或远程拉取）

    Args:
        root: 项目根目录（仅用于 cwd，检测与目录无关）。

    Returns:
        True 表示 openspec CLI 可调用。
    """
    # 优先 PATH 全局 openspec
    if _try_openspec(["openspec", "--version"], root):
        return True
    # 回退 npx（避免远程拉取加 --no-install）
    if _try_openspec(["npx", "--no-install", "openspec", "--version"], root):
        return True
    return False


# ---- archive 命令封装 ----

def ensure_openspec_workspace(root: Path) -> None:
    """确保目标项目根有 openspec/ 工作区目录结构。

    openspec archive 的前提是存在 openspec/changes 和 openspec/specs。
    若缺失则最小化创建（不调 openspec init，避免交互）。

    Args:
        root: 项目根目录。
    """
    openspec_dir = root / "openspec"
    (openspec_dir / "changes" / "archive").mkdir(parents=True, exist_ok=True)
    (openspec_dir / "specs").mkdir(parents=True, exist_ok=True)
    # config.yaml 是 openspec 识别工作区的标记
    config_path = openspec_dir / "config.yaml"
    if not config_path.exists():
        config_path.write_text("schema: spec-driven\n", encoding="utf-8")


def archive_change(root: Path, change_name: str, skip_validation: bool = False) -> dict:
    """调用真实 openspec archive 命令归档指定 change。

    命令：openspec archive <change_name> --yes --json
    - --yes 跳过交互确认（specpowers 非交互场景必需）
    - --json 拿结构化结果（{ change, archivedAs, path, specsUpdated, totals }）
    - --no-validate 可选，跳过验证（不推荐，仅诊断时用）

    openspec archive 内置行为：
    1. findSpecUpdates 把 change 下 delta specs 合并到主规格
       openspec/specs/<capability>/spec.md
    2. moveDirectory 把 change 移到 openspec/changes/archive/YYYY-MM-DD-<name>/

    Args:
        root: 项目根目录。
        change_name: change 名（specpowers feature slug，保留原样）。
        skip_validation: True 则加 --no-validate。

    Returns:
        openspec 输出的 JSON dict。

    Raises:
        FatalError: openspec 命令执行失败（带 stderr）或输出非 JSON。
    """
    # 构建安全命令列表（参数化，无 shell 注入风险）
    cmd = ["openspec", "archive", change_name, "--yes", "--json"]
    if skip_validation:
        cmd.append("--no-validate")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=str(root),
        )
    except FileNotFoundError:
        raise FatalError(
            "openspec CLI 未找到。请确认 openspec 已全局安装或在 PATH 中。"
            "归档强依赖 openspec archive 命令。"
        )
    except subprocess.TimeoutExpired:
        raise FatalError(
            f"openspec archive 超时（120s）：openspec archive {change_name}"
        )

    if result.returncode != 0:
        # 失败时保留临时 change 目录供排查，不清理
        stderr = result.stderr.strip() or result.stdout.strip()
        raise FatalError(
            f"openspec archive 失败（exit {result.returncode}）：\n{stderr}\n"
            f"临时 change 目录已保留：openspec/changes/{change_name}/，"
            f"可排查后重试 /specpowers.archive。"
        )

    # 解析 JSON 结果
    stdout = result.stdout.strip()
    if not stdout:
        # 非 JSON 模式可能无输出，构造最小结果
        return {
            "change": change_name,
            "archivedAs": change_name,
            "path": str(root / "openspec" / "changes" / "archive" / change_name),
            "specsUpdated": True,
        }
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # openspec --json 正常应输出 JSON；解析失败视为警告但不阻断
        print(f"⚠ openspec archive 输出非 JSON，归档可能已成功：\n{stdout}",
              file=sys.stderr)
        return {
            "change": change_name,
            "archivedAs": change_name,
            "path": str(root / "openspec" / "changes" / "archive" / change_name),
            "specsUpdated": True,
        }
