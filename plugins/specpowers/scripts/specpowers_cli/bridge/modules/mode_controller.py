"""Mode controller — fast mode judgment, confirmation, checklist management, execution mode enforcement."""

from pathlib import Path

SMALL_SIGNALS = ["bugfix", "单文件", "无新场景", "纯配置", "纯文案", "纯重构"]

# build 阶段可选的四种执行方式（对应 build.md 第二步选项）
# conductor  → superpowers executing-plans（顺序执行，默认）
# worktree   → superpowers using-git-worktrees（隔离工作区）
# subagent   → superpowers subagent-driven-development（每任务一个子代理）
# tdd        → superpowers test-driven-development（红-绿-重构）
VALID_EXECUTION_MODES = ("conductor", "worktree", "subagent", "tdd")

# fast 模式禁止的执行方式（fast_mode.md:132 / build.md:50 声明的约束）
# fast 模式仅允许 conductor / tdd，worktree / subagent 被禁用
FAST_FORBIDDEN_MODES = ("worktree", "subagent")


def validate_execution_mode(mode: str, current_mode: str = "full") -> tuple[bool, str]:
    """校验执行方式是否合法，并对 fast 模式做约束兜底。

    兑现 build.md 第二步「记录到 state.json（execution_mode 字段）」的承诺，
    同时把 fast_mode.md 声明的「fast 禁止 worktree/subagent」从纯 prompt 自律
    升级为确定性层硬校验，补上纵深防御（认知层约束被绕过时仍能拦截）。

    Args:
        mode: 用户选择的执行方式（conductor/worktree/subagent/tdd）。
        current_mode: 当前 state 的 mode（full/fast），决定是否触发 fast 约束。

    Returns:
        (ok, hint)：ok=False 时 hint 给出拒绝原因（含 fast 语境友好提示）。
    """
    # 输入规范化：去空白、转小写，容忍 agent 传入 "TDD"/" Conductor " 等大小写差异
    normalized = (mode or "").strip().lower()
    if normalized not in VALID_EXECUTION_MODES:
        return False, (
            f"未知的执行方式 '{mode}'。"
            f"合法值：{', '.join(VALID_EXECUTION_MODES)}。"
        )
    # fast 模式约束兜底：fast 禁止 worktree/subagent
    if current_mode == "fast" and normalized in FAST_FORBIDDEN_MODES:
        return False, (
            f"fast 模式禁止使用 '{normalized}' 执行方式。"
            f"fast 模式仅允许 conductor / tdd（worktree / subagent 已禁用）。"
            f"如需 worktree/subagent，请先升级为完整流程。"
        )
    return True, ""


def set_execution_mode(root: Path, state: dict, mode: str) -> dict:
    """把用户选择的执行方式记录到 state.json（execution_mode 字段）。

    落地 build.md 第二步的承诺：执行方式不仅停留在 agent 实时交互，
    也持久化到 state，供后续阶段（archive 审计等）追溯。

    Args:
        root: 项目根目录（save_state 内部拼 .specpowers/state.json）。
        state: 当前状态字典。
        mode: 用户选择的执行方式（conductor/worktree/subagent/tdd）。

    Returns:
        更新后的 state 字典。

    Raises:
        ValueError: 执行方式非法，或 fast 模式选了禁止的方式。
    """
    # 先按当前 mode 校验合法性（含 fast 约束兜底）
    ok, hint = validate_execution_mode(mode, state.get("mode", "full"))
    if not ok:
        raise ValueError(hint)
    state["execution_mode"] = mode.strip().lower()
    from specpowers_cli.bridge.core.fs_state import save_state
    save_state(root, state)
    return state


# 说明：fast 模式的判小确认 / checklist 边界 / 回退标记等交互逻辑，
# 全部由认知层（prompts/fast_mode.md）承担，确定性层不再重复实现。
# 历史的 build_confirm_prompt / parse_confirm / gen_checklist /
# validate_checklist / mark_fallback 已移除（无生产调用）。
# 确定性层仅保留 validate_execution_mode / set_execution_mode 两个硬校验入口。
