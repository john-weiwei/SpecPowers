"""OpenSpec adapter — 场景生成 + archive 命令封装。

职责：
- to_scenario: propose 阶段把需求转成 OpenSpec 场景格式文本（认知层用）
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
from specpowers_cli.bridge.core.platform import _safe_which


def to_scenario(req: str, brief: str | None = None) -> str:
    """生成 OpenSpec 场景格式文本（propose 阶段认知层使用）。

    Args:
        req: 需求文本。
        brief: 可选的 brief.md 内容（explore 阶段产出）。

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
        cmd: 完整命令列表（如 ["/abs/openspec", "--version"]）。
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


# 已解析的 openspec 调用方式缓存（None 表示尚未解析）。
# 检测与执行共用同一结果，避免「npx 检测通过、裸 openspec 执行失败」的不一致。
_OPENSPEC_CMD: list[str] | None = None


def _resolve_openspec_cmd(root: Path) -> list[str] | None:
    """解析 openspec CLI 的实际调用命令（绝对路径优先，npx 回退），进程内缓存。

    解析结果同时供 is_openspec_available 与 archive_change 使用，
    保证「检测到的」与「执行的」是同一条命令。
    经 _safe_which 解析为绝对路径，不搜索当前目录（Windows 劫持防护）。

    Args:
        root: 项目根目录（作为探测命令的 cwd）。

    Returns:
        完整命令前缀列表（如 ["/usr/bin/openspec"] 或
        ["/usr/bin/npx", "--no-install", "openspec"]）；不可用返回 None。
    """
    global _OPENSPEC_CMD
    if _OPENSPEC_CMD is not None:
        return _OPENSPEC_CMD

    # 优先 PATH 全局 openspec（绝对路径）
    exe = _safe_which("openspec")
    if exe and _try_openspec([exe, "--version"], root):
        _OPENSPEC_CMD = [exe]
        return _OPENSPEC_CMD
    # 回退项目本地 npx 安装（--no-install 避免远程拉取）
    npx = _safe_which("npx")
    if npx and _try_openspec([npx, "--no-install", "openspec", "--version"], root):
        _OPENSPEC_CMD = [npx, "--no-install", "openspec"]
        return _OPENSPEC_CMD
    return None


def is_openspec_available(root: Path) -> bool:
    """检测 openspec CLI 是否可用（与 archive_change 共用同一命令解析）。

    Args:
        root: 项目根目录（仅用于 cwd，检测与目录无关）。

    Returns:
        True 表示 openspec CLI 可调用。
    """
    return _resolve_openspec_cmd(root) is not None


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


def _verify_archived(root: Path, change_name: str) -> dict | None:
    """扫描归档目录确认 change 确实已归档，返回结果 dict；未找到返回 None。

    作为 openspec 输出不可解析（非 JSON / 空输出）时的实证兜底：
    归档目录里存在 YYYY-MM-DD-<change_name> 目录才算成功，
    避免「假定成功」掩盖真实失败。

    Args:
        root: 项目根目录。
        change_name: change 名。

    Returns:
        含 archivedAs 的最小结果 dict；未找到返回 None。
    """
    archive_dir = root / "openspec" / "changes" / "archive"
    if not archive_dir.is_dir():
        return None
    for entry in archive_dir.iterdir():
        # 归档目录命名约定：YYYY-MM-DD-<change_name>（日期前缀固定 11 字符）。
        # 去前缀后精确比对，避免 "sso-login" 被 endswith("-login") 误匹配给 "login"
        if entry.is_dir() and len(entry.name) > 11 and entry.name[11:] == change_name:
            return {
                "change": change_name,
                "archivedAs": entry.name,
                "path": str(entry),
                # specsUpdated 无法从目录判定，保守取 False（仅影响提示文案）
                "specsUpdated": False,
            }
    return None


def archive_change(root: Path, change_name: str, skip_validation: bool = False) -> dict:
    """调用真实 openspec archive 命令归档指定 change。

    命令：<resolved-cmd> archive <change_name> --yes --json
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
        FatalError: openspec 命令执行失败（带 stderr）、CLI 不可用、
                    或输出不可解析且归档目录中找不到产物（无法确认成功）。
    """
    # 复用与 is_openspec_available 相同的命令解析（绝对路径，防当前目录劫持）
    cmd_prefix = _resolve_openspec_cmd(root)
    if cmd_prefix is None:
        raise FatalError(
            "openspec CLI 不可用。归档强依赖 openspec archive 命令，"
            "请确认 openspec 已全局安装（pip/node）并在 PATH 中。"
        )
    cmd = cmd_prefix + ["archive", change_name, "--yes", "--json"]
    if skip_validation:
        cmd.append("--no-validate")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, cwd=str(root),
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
    if stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # JSON 解析失败：不假定成功，改用归档目录实证校验
            verified = _verify_archived(root, change_name)
            if verified is None:
                print(f"⚠ openspec archive 输出非 JSON：\n{stdout}", file=sys.stderr)
                raise FatalError(
                    f"openspec archive 输出无法解析，且归档目录中未找到 "
                    f"'{change_name}' 的产物，无法确认归档成功。"
                    f"临时 change 目录已保留：openspec/changes/{change_name}/，"
                    f"请人工排查后重试。"
                )
            return verified

    # stdout 为空：同样以归档目录实证为准
    verified = _verify_archived(root, change_name)
    if verified is None:
        raise FatalError(
            f"openspec archive 无输出且归档目录中未找到 '{change_name}' 的产物，"
            f"无法确认归档成功。请人工排查 openspec/changes/{change_name}/。"
        )
    return verified
