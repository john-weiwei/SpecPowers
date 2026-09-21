#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gather_review_context.py

复刻 Codex 审查模式的 git 上下文收集（operationSource="review_model"）。

Codex 不会把被截断的补丁直接交给模型：基分支审查时解析合并基点后取完整差异；
未提交审查时收集已暂存 / 未暂存 / 未跟踪文件。本脚本执行同样的确定性 git 操作，
使审查者看到完整且权威的变更集。

模式
----
  * base-branch  : HEAD 相对基准分支。v3 起默认对比 `合并基点..HEAD`（仅已提交改动），
                   `--include-worktree` 时对比 `合并基点..工作区`（含未提交改动）。
  * uncommitted  : 工作区改动（已暂存 + 未暂存 + 未跟踪）。
  * method       : 单方法（--method "Class#method"），导出定义候选 / 完整方法体 /
                   同文件兄弟方法 / 一层调用方清单，供调用链穿透（指南 §7）使用。

v3 增强
------
  * 方法体提取按 diff 对应版本取内容（基分支取 HEAD、staged 取 index、unstaged 取
    工作区），已删除文件跳过提取并在上下文包注明；
  * 方法边界识别改用"成员表"算法（花括号深度跳变 + 容器排除），深层嵌套与
    大括号换行（Allman）风格均稳健，修复 v2 嵌套块内变更静默提取失败的问题；
  * 支持 Java / TS / JS / TSX / JSX（花括号成员表）、Python（缩进 def）、
    Mapper XML（完整 SQL 语句块）；
  * 统一按文件粒度截断：未提交模式同样受 --max-bytes 约束，超预算文件列入
    "未包含文件清单"，提示审查者用 Read 工具补读；
  * git 输出统一按 utf-8 解码（errors=replace）并关闭 core.quotepath，
    修复 Windows 下中文提交信息 / 中文路径乱码问题。

作者: 张威威(005819) / GLM
日期: 2026-09-14
"""
import argparse
import json
import os
import re
import subprocess
import sys

MAX_FILE_BYTES = 200_000       # 未跟踪单文件写入上下文包的大小上限
METHOD_SECTION_LIMIT = 60_000  # "变更方法完整上下文"章节的总大小上限

# 花括号语言中不作为成员起始的控制流关键字（按行首第一个标识符判断）
_CONTROL_KEYWORDS = {
    "if", "else", "for", "while", "switch", "try", "do", "catch",
    "finally", "synchronized", "using", "return",
}
# 容器声明关键字：命中则该块是类 / 接口等容器而非方法，不作为成员输出
_CONTAINER_RE = re.compile(
    r"\b(class|interface|enum|record|namespace|struct|impl|trait)\b"
)
# diff 头路径解析（兜底用；优先取 chunk 内 `+++ b/` 行，支持含空格路径）
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*) b/(.*)$")


def run_git(repo, args, check=True):
    """执行 git 命令并返回 CompletedProcess。

    统一 utf-8 解码并关闭 core.quotepath：Windows 默认按 cp936 解码会把中文
    提交信息 / 中文路径变成乱码，quotepath=true 会把非 ASCII 路径转义成八进制。
    """
    cmd = ["git", "-C", repo, "-c", "core.quotepath=false"] + args
    res = subprocess.run(cmd, capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        raise RuntimeError("git %s 执行失败: %s" % (" ".join(args), res.stderr.strip()))
    return res


def git_root(repo):
    """返回仓库根目录；非 git 仓库时抛错。"""
    res = run_git(repo, ["rev-parse", "--show-toplevel"], check=False)
    if res.returncode != 0:
        raise RuntimeError("不是 git 仓库: %s" % repo)
    return res.stdout.strip()


def read_file(path, cap=MAX_FILE_BYTES):
    """读取工作区文件，返回 (内容, 字节数, 状态)。超限截断。"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None, 0, "缺失"
    if size > cap:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read(cap)
        return data, size, "截断@%d" % cap
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), size, "正常"
    except Exception as e:  # noqa: BLE001
        return None, size, "不可读:%s" % e


# ——— 成员表：方法边界识别（花括号语言） ———

def _scan_brace_depths(lines):
    """逐行扫描源码，返回每行结束时的花括号深度（下标 0 起始，depths[i] 为第 i 行后深度）。

    忽略行注释、块注释与字符串 / 字符 / 模板字面量中的花括号，避免字面量干扰
    成员边界识别。启发式实现：跨行模板字符串中的 ${} 表达式不展开。
    """
    depths = [0] * (len(lines) + 1)
    depth = 0
    in_block_comment = False
    in_string = ""
    for i, line in enumerate(lines, 1):
        j = 0
        n = len(line)
        while j < n:
            c = line[j]
            if in_block_comment:
                if line.startswith("*/", j):
                    in_block_comment = False
                    j += 2
                    continue
                j += 1
                continue
            if in_string:
                if c == "\\":
                    j += 2
                    continue
                if c == in_string:
                    in_string = ""
                j += 1
                continue
            if line.startswith("//", j):
                break
            if line.startswith("/*", j):
                in_block_comment = True
                j += 2
                continue
            if c in ("'", '"', "`"):
                in_string = c
                j += 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth = max(0, depth - 1)
            j += 1
        depths[i] = depth
    return depths


def _member_header_start(lines, brace_line):
    """从 '{' 所在行向上回溯，收编多行签名与 @注解 行，返回成员起始行号。"""
    start = brace_line
    k = brace_line - 1
    while k >= 1:
        t = lines[k - 1].strip()
        if not t:
            break
        if t.startswith("@"):
            start = k
            k -= 1
            continue
        if t.startswith("//") or t.endswith("*/"):
            break
        # 上一行以 ; } { 收尾，说明是完整语句，不属于当前成员头
        if t.endswith((";", "}", "{")):
            break
        start = k
        k -= 1
    return start


def _member_name(lines, header_start, brace_line):
    """尽力提取成员名：优先 header 中最后一个 `标识符(` 或 `标识符<...>(`（泛型）。"""
    header = "".join(lines[header_start - 1:brace_line])
    matches = re.findall(r"(\w+)\s*(?:<[^(){}]*>)?\s*\(", header)
    if matches:
        return matches[-1]
    m = re.search(r"(\w+)\s*=[^=]", header)
    if m:
        return m.group(1)
    first = lines[header_start - 1].strip().lstrip("@")
    tok = re.split(r"[\s({\[<>=:;,!]", first, maxsplit=1)[0]
    return tok or ""


def _find_members_braced(lines):
    """花括号语言（Java/TS/JS）成员表：返回 [(start, end, name), ...]（行号 1 起，闭区间）。

    识别依据：花括号深度从 0/1 跳深的行（类体直接成员或模块级函数的块起始行）。
    用深度跳变而非签名正则，因此嵌套在 if/for 内的变更也能反查所属方法；
    同时排除控制流关键字行与 class/interface 等容器声明行。
    """
    depths = _scan_brace_depths(lines)
    n = len(lines)
    members = []
    for i in range(1, n + 1):
        prev, cur = depths[i - 1], depths[i]
        if not (cur > prev and prev in (0, 1)):
            continue
        first = lines[i - 1].lstrip()
        # 仅排除 } 等收尾标点开头的行（如 `} else {`）；保留 `)` 开头的行——
        # 多行签名以右括号收尾后接 '{' 是合法成员起点
        if not first or first[0] in "}];,":
            continue
        first_word = re.split(r"[\s({\[<>=:;,!@]", first, maxsplit=1)[0].lstrip("@")
        if first_word in _CONTROL_KEYWORDS:
            continue
        # 从该行向后找深度回落到 prev 的行作为成员终点
        end = n
        for j in range(i + 1, n + 1):
            if depths[j] <= prev:
                end = j
                break
        start = _member_header_start(lines, i)
        header = "".join(lines[start - 1:i])
        if _CONTAINER_RE.search(header):
            continue
        members.append((start, end, _member_name(lines, start, i)))
    return members


# ——— 成员表：Python（缩进）与 Mapper XML（SQL 语句块） ———

def _find_members_python(lines):
    """Python 成员表：按缩进识别顶层函数 / 类方法（def / async def），回溯装饰器。"""
    header = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)")
    members = []
    for i, line in enumerate(lines, 1):
        m = header.match(line)
        if not m:
            continue
        indent = len(m.group(1).expandtabs(4))
        start = i
        k = i - 1
        while k >= 1 and lines[k - 1].strip().startswith("@"):
            start = k
            k -= 1
        end = i
        for j in range(i + 1, len(lines) + 1):
            l = lines[j - 1]
            if not l.strip():
                continue
            cur_indent = len(l[:len(l) - len(l.lstrip())].expandtabs(4))
            if cur_indent <= indent:
                break
            end = j
        members.append((start, end, m.group(2)))
    return members


def _find_xml_blocks(lines):
    """Mapper XML 语句块表：<select|insert|update|delete id="..."> ... </...>。"""
    open_re = re.compile(r"<(select|insert|update|delete)\b[^>]*\bid\s*=\s*[\"']([^\"']+)")
    members = []
    current = None
    for i, line in enumerate(lines, 1):
        if current is None:
            m = open_re.search(line)
            if m:
                current = (i, m.group(1), m.group(2))
        else:
            if "</%s>" % current[1] in line:
                members.append((current[0], i, current[2]))
                current = None
    return members


def _members_for_lang(lines, lang):
    """按语言分发成员表构建。"""
    if lang == "python":
        return _find_members_python(lines)
    if lang == "xml":
        return _find_xml_blocks(lines)
    return _find_members_braced(lines)


def _select_members(members, changed_ranges):
    """选出覆盖任一变更区间的成员；嵌套重叠时保留最外层（控制流上下文更完整）。"""
    hits = []
    for (ms, me, name) in members:
        for (hs, he) in changed_ranges:
            if not (he < ms or hs > me):
                hits.append((ms, me, name))
                break
    hits.sort(key=lambda t: (t[0], -t[1]))
    selected = []
    for h in hits:
        if selected and h[0] >= selected[-1][0] and h[1] <= selected[-1][1]:
            continue
        selected.append(h)
    return selected


# ——— 语言判定与提取入口 ———

_BRACED_EXTS = (".java", ".ts", ".tsx", ".js", ".jsx")
_FENCE_OF = {".java": "java", ".ts": "ts", ".tsx": "tsx", ".js": "js",
             ".jsx": "jsx", ".py": "python", ".xml": "xml"}


def _lang_of(path):
    """按扩展名判定提取语言：braced / python / xml / None（不提取）。"""
    p = path.lower()
    if p.endswith(_BRACED_EXTS):
        return "braced"
    if p.endswith(".py"):
        return "python"
    if p.endswith(".xml"):
        return "xml"
    return None


def _extract_methods(lines, changed_ranges, lang="braced"):
    """对变更行区间查成员表，返回 [(start, end, name), ...]（行号 1 起，闭区间）。

    v3 起仅负责"查表 + 选成员"，Markdown 渲染交给 _method_section。
    """
    return _select_members(_members_for_lang(lines, lang), changed_ranges)


# ——— diff 解析 ———

def _split_diff_files(diff_text):
    """把 git diff 输出按文件拆分为 [(path, chunk_text), ...]，支持含空格路径。

    路径优先取 chunk 内 `+++ b/` 行（权威新文件路径），diff 头正则兜底。
    """
    chunks = []
    current = []
    for line in diff_text.split("\n"):
        if line.startswith("diff --git "):
            if current:
                chunks.append(current)
            current = [line]
        elif current:
            current.append(line)
    if current:
        chunks.append(current)
    result = []
    for cl in chunks:
        path = None
        for line in cl:
            if line.startswith("+++ b/"):
                path = line[len("+++ b/"):]
                break
        if path is None:
            m = _DIFF_HEADER_RE.match(cl[0]) if cl else None
            path = m.group(2) if m else None
        if path:
            result.append((path, "\n".join(cl)))
    return result


def _parse_hunks(chunk):
    """从单文件 diff 块解析新文件侧变更行区间 [(start, end), ...]（1 起闭区间）。"""
    ranges = []
    for line in chunk.split("\n"):
        if line.startswith("@@ "):
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                start = int(m.group(1))
                count = int(m.group(2)) if m.group(2) else 1
                if count > 0:
                    ranges.append((start, start + count - 1))
    return ranges


# ——— 按 diff 版本读取文件内容 ———

def _read_lines(file_path):
    """读取工作区文件全部行；失败返回空列表。"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except Exception:  # noqa: BLE001
        return []


def _git_version_reader(repo, ref, label=None):
    """构造"按 git 版本读文件"的函数：返回 (行列表, 状态说明)。

    ref 传 "HEAD" 取提交版本；传 "" 取 index（暂存区，即 `git show :path`）。
    读取失败视为文件已删除 / 不存在。
    """
    label = label or ref or "指定版本"

    def read(path):
        res = run_git(repo, ["show", "%s:%s" % (ref, path)], check=False)
        if res.returncode != 0:
            return None, "文件已删除或不在 %s 中" % label
        # 保留换行符，保证后续按行 join 时方法体不挤成一行
        lines = [l + "\n" for l in res.stdout.split("\n")]
        if lines and lines[-1] == "\n":
            lines.pop()
        return lines, "正常"

    return read


def _worktree_reader(root):
    """构造"按工作区读文件"的函数。"""

    def read(path):
        lines = _read_lines(os.path.join(root, path))
        if not lines:
            return None, "文件已删除或不可读"
        return lines, "正常"

    return read


# ——— "变更方法完整上下文"章节渲染 ———

def _method_section(title, entries):
    """生成"变更方法完整上下文"章节（Markdown）。

    entries: [(path, chunk, lines, state)]；lines 为该 diff 对应版本的文件内容，
    None 表示已删除 / 不可读（跳过提取并注明）。章节总大小受 METHOD_SECTION_LIMIT 约束。
    """
    out = ["", "## " + title, ""]
    out.append("> 以下为每个修改方法 / SQL 语句在对应 diff 版本中的完整内容，用于审查")
    out.append("> diff 片段无法直接体现的控制流问题（早期返回阻断、条件覆盖、兜底路径等）。")
    out.append("> 提取基于花括号 / 缩进 / 标签边界的启发式解析；若目标方法缺失，请手动 Read 源文件。")
    out.append("")
    body = []
    total = 0
    for (path, chunk, lines, state) in entries:
        lang = _lang_of(path)
        if lang is None:
            continue
        # 已删除 / 不可读：先于区间检查注明，纯删除 hunk（+0,0）解析不出行区间
        if lines is None:
            body.append("### %s" % path)
            body.append("")
            body.append("> %s，跳过方法体提取（diff 中已含对应删除内容）。" % state)
            body.append("")
            continue
        ranges = _parse_hunks(chunk)
        if not ranges:
            continue
        selected = _extract_methods(lines, ranges, lang=lang)
        if not selected:
            continue
        body.append("### %s" % path)
        body.append("")
        fence = _FENCE_OF.get(os.path.splitext(path)[1].lower(), "")
        for (s, e, name) in selected:
            # XML 语句块按块原样输出，扩展上下文会把下一条语句的开头带进来
            if lang == "xml":
                cs, ce = s, e
            else:
                cs = max(1, s - 3)
                ce = min(len(lines), e + 5)
            snippet = "".join(lines[cs - 1:ce])
            size = len(snippet.encode("utf-8"))
            if total + size > METHOD_SECTION_LIMIT:
                body.append("> （超出方法体章节上限 %d 字节，其余方法请手动 Read 源文件。）"
                            % METHOD_SECTION_LIMIT)
                break
            total += size
            label = name or "(匿名块)"
            body.append("#### %s — 行 %d-%d" % (label, cs, ce))
            body.append("")
            body.append("```" + fence)
            body.append(snippet.rstrip())
            body.append("```")
            body.append("")
    if not body:
        return ""
    return "\n".join(out + body) + "\n"


# ——— 按文件粒度的字节预算 ———

class _Budget(object):
    """按文件粒度的字节预算：放得下则计入，放不下记入未包含清单（不做字节级砍断）。"""

    def __init__(self, max_bytes):
        self.remaining = max_bytes
        self.excluded = []  # (path, size)

    def take(self, path, text):
        """尝试纳入一段内容；失败时记录到未包含清单并返回 False。"""
        size = len(text.encode("utf-8"))
        if size <= self.remaining:
            self.remaining -= size
            return True
        self.excluded.append((path, size))
        return False

    def excluded_section(self, max_bytes):
        """渲染"未包含文件清单"章节；无截断时返回空串。"""
        if not self.excluded:
            return ""
        out = ["", "## 未包含文件清单（超出 --max-bytes=%d 预算）" % max_bytes, ""]
        out.append("| 文件 | 字节 |")
        out.append("| --- | --- |")
        for (p, sz) in self.excluded:
            out.append("| %s | %d |" % (p, sz))
        out.append("")
        out.append("> 以上文件未纳入上下文包。请使用 Read 工具按需读取这些文件的完整内容")
        out.append("> 后再审查，不得仅基于截断片段下结论。")
        out.append("")
        return "\n".join(out) + "\n"


# ——— 模式一：基分支对比 ———

def gather_base_branch(repo, base, hide_whitespace, max_bytes, extract_methods,
                       include_worktree=False):
    """基分支模式：收集 HEAD（或工作区）相对基准分支的完整差异与方法体上下文。"""
    root = git_root(repo)
    mb = run_git(repo, ["merge-base", "HEAD", base], check=False)
    if mb.returncode != 0 or not mb.stdout.strip():
        raise RuntimeError("无法在 HEAD 与 %s 之间解析出合并基点。" % base)
    merge_base = mb.stdout.strip()

    # v3：默认只对比已提交改动（合并基点..HEAD），符合审 PR 心智；旧行为经开关保留
    tail = []
    if hide_whitespace:
        tail.append("--ignore-all-space")
    if include_worktree:
        tail.append(merge_base)
        scope_note = "合并基点..工作区（含未提交改动）"
        range_label = merge_base
    else:
        tail.extend([merge_base, "HEAD"])
        scope_note = "合并基点..HEAD（仅已提交改动；加 --include-worktree 可含工作区）"
        range_label = "%s HEAD" % merge_base
    full_diff = run_git(repo, ["diff"] + tail, check=False).stdout
    stat = run_git(repo, ["diff", "--stat"] + tail, check=False).stdout
    commits = run_git(repo, ["log", "%s..HEAD" % merge_base, "--oneline"],
                      check=False).stdout

    budget = _Budget(max_bytes)
    included = []
    out = []
    out.append("# 审查上下文")
    out.append("")
    out.append("模式: 基分支对比")
    out.append("基准分支: %s" % base)
    out.append("合并基点 SHA: %s" % merge_base)
    out.append("对比范围: %s" % scope_note)
    out.append("")
    out.append("## 差异统计")
    out.append("")
    out.append("```")
    out.append(stat.strip() or "(无改动)")
    out.append("```")
    out.append("")
    out.append("## 本分支提交 (合并基点..HEAD)")
    out.append("")
    out.append("```")
    out.append(commits.strip() or "(无)")
    out.append("```")
    out.append("")
    out.append("## 完整差异 (`git diff %s`)" % range_label)
    out.append("")
    out.append("```diff")
    for (path, chunk) in _split_diff_files(full_diff):
        if budget.take(path, chunk):
            included.append((path, chunk))
            out.append(chunk.rstrip())
    if not included:
        out.append("(无改动)")
    out.append("```")
    out.append("")

    if extract_methods:
        # 按 diff 对应版本提取：默认 HEAD；--include-worktree 时为工作区
        reader = (_worktree_reader(root) if include_worktree
                  else _git_version_reader(repo, "HEAD"))
        entries = []
        for (path, chunk) in included:
            lines, state = reader(path)
            entries.append((path, chunk, lines, state))
        out.append(_method_section("变更方法完整上下文（控制流审查辅助）", entries))

    excluded_md = budget.excluded_section(max_bytes)
    if excluded_md:
        out.append(excluded_md)

    bundle = "\n".join(out) + "\n"
    meta = {
        "mode": "base-branch",
        "repo_root": root,
        "base_branch": base,
        "merge_base": merge_base,
        "include_worktree": include_worktree,
        "diff_bytes": len(bundle.encode("utf-8")),
        "truncated": bool(budget.excluded),
        "excluded_files": [{"path": p, "bytes": s} for (p, s) in budget.excluded],
    }
    return bundle, meta


# ——— 模式二：未提交改动 ———

def gather_uncommitted(repo, hide_whitespace, max_bytes, extract_methods):
    """未提交模式：收集已暂存 + 未暂存 + 未跟踪文件，统一按文件粒度截断。

    预算消耗顺序（优先级）：已暂存差异 → 未暂存差异 → 未跟踪文件。
    方法体提取按 diff 对应版本：staged 取 index，unstaged 取工作区。
    """
    root = git_root(repo)
    ws = ["--ignore-all-space"] if hide_whitespace else []
    staged_diff = run_git(repo, ["diff", "--cached"] + ws, check=False).stdout
    unstaged_diff = run_git(repo, ["diff"] + ws, check=False).stdout
    status = run_git(repo, ["status", "--short"], check=False).stdout
    untracked_raw = run_git(repo, ["ls-files", "--others", "--exclude-standard"],
                            check=False).stdout
    untracked = [p for p in untracked_raw.splitlines() if p.strip()]

    budget = _Budget(max_bytes)
    staged_chunks = []
    unstaged_chunks = []

    out = []
    out.append("# 审查上下文")
    out.append("")
    out.append("模式: 未提交（已暂存 + 未暂存 + 未跟踪）")
    out.append("截断策略: 按文件粒度，超出 --max-bytes=%d 的文件列入文末清单" % max_bytes)
    out.append("")
    out.append("## Git 状态")
    out.append("")
    out.append("```")
    out.append(status.strip() or "(干净)")
    out.append("```")
    out.append("")

    out.append("## 已暂存差异 (`git diff --cached`)")
    out.append("")
    out.append("```diff")
    wrote = False
    for (path, chunk) in _split_diff_files(staged_diff):
        if budget.take(path, chunk):
            staged_chunks.append((path, chunk))
            out.append(chunk.rstrip())
            wrote = True
    if not wrote:
        out.append("(无)")
    out.append("```")
    out.append("")

    out.append("## 未暂存差异 (`git diff`)")
    out.append("")
    out.append("```diff")
    wrote = False
    for (path, chunk) in _split_diff_files(unstaged_diff):
        if budget.take(path, chunk):
            unstaged_chunks.append((path, chunk))
            out.append(chunk.rstrip())
            wrote = True
    if not wrote:
        out.append("(无)")
    out.append("```")
    out.append("")

    out.append("## 未跟踪文件（完整内容）")
    out.append("")
    if not untracked:
        out.append("(无)")
        out.append("")
    for rel in untracked:
        abspath = os.path.join(root, rel)
        content, size, state = read_file(abspath)
        out.append("### %s  (%s, %d 字节)" % (rel, state, size))
        out.append("")
        if content is None:
            out.append("_(不可读)_")
        elif not budget.take(rel, content):
            out.append("_(超出预算，未纳入；请使用 Read 工具读取)_")
        else:
            out.append("```")
            out.append(content.rstrip())
            out.append("```")
        out.append("")

    if extract_methods:
        index_reader = _git_version_reader(repo, "", label="index（暂存区）")
        worktree_reader = _worktree_reader(root)
        if staged_chunks:
            entries = []
            for (path, chunk) in staged_chunks:
                lines, state = index_reader(path)
                entries.append((path, chunk, lines, state))
            out.append(_method_section("变更方法完整上下文（已暂存，基于 index 版本）", entries))
        if unstaged_chunks:
            entries = []
            for (path, chunk) in unstaged_chunks:
                lines, state = worktree_reader(path)
                entries.append((path, chunk, lines, state))
            out.append(_method_section("变更方法完整上下文（未暂存，基于工作区版本）", entries))

    excluded_md = budget.excluded_section(max_bytes)
    if excluded_md:
        out.append(excluded_md)

    bundle = "\n".join(out) + "\n"
    meta = {
        "mode": "uncommitted",
        "repo_root": root,
        "untracked_count": len(untracked),
        "diff_bytes": len(bundle.encode("utf-8")),
        "truncated": bool(budget.excluded),
        "excluded_files": [{"path": p, "bytes": s} for (p, s) in budget.excluded],
    }
    return bundle, meta


# ——— 模式三：单方法（调用链穿透的确定性材料收集） ———

# 定义行启发式提示词：命中其一才视为方法定义行
_DEF_HINT_RE = re.compile(
    r"(?:^|[^\w.])(?:async\s+def|async|def|function|func|public|private|protected|static|"
    r"final|abstract|synchronized|override|suspend)\s"
)


def _looks_like_definition(text, meth):
    """粗判一行是否为方法定义行（启发式）：区分定义与调用，供 --method 模式使用。

    同时兼容泛型形式（`meth<...>(`，TS / Java 泛型方法）。
    """
    t = text.strip()
    if not t:
        return False
    for sep in (".", "->", "::"):
        if (sep + meth + "(") in t or (sep + meth + "<") in t:
            return False
    m = re.search(r"(?:^|[^\w.])" + re.escape(meth) + r"(\s*[<(])", t)
    if not m:
        return False
    # TS 方法签名可直接以方法名开头：以 '{' 或 '(' 收尾视为定义，';' 收尾视为调用
    if t.startswith(meth) and t[len(meth):len(meth) + 1] in "(<":
        return t.endswith(("{", "("))
    # 赋值调用形态（cache = meth(...)）不算定义
    if "=" in t[:m.start()]:
        return False
    return bool(_DEF_HINT_RE.search(t))


def _is_test_path(path):
    """判断路径是否属于测试代码（候选排序时降权）。"""
    low = path.lower()
    return "test" in low or "spec" in low or "__tests__" in low


def gather_method(repo, spec, max_bytes):
    """单方法模式：导出定义候选 / 完整方法体 / 同文件兄弟方法 / 一层调用方清单。

    spec 形如 "Class#method" 或 "method"。调用图的递归展开仍由审查者按指南 §7 执行，
    本函数只把机械性、易超时的 grep 定位工作确定性化。
    """
    root = git_root(repo)
    spec = spec.strip()
    if "#" in spec:
        cls_part, meth_part = (s.strip() for s in spec.split("#", 1))
    else:
        cls_part, meth_part = "", spec
    meth_part = meth_part or spec

    out = []
    out.append("# 审查上下文")
    out.append("")
    out.append("模式: 单方法（无 diff；调用链穿透需按指南 §7 继续执行）")
    out.append("目标: %s" % spec)
    out.append("")

    # 正则匹配 `meth(` 与 `meth<`（TS / Java 泛型方法）；前缀仅排除字母数字下划线，
    # 允许 `obj.meth(` / `this.meth(` 这类调用点进入 hits，定义与调用的区分交给
    # _looks_like_definition 判定
    pattern = r"(^|[^A-Za-z0-9_])" + re.escape(meth_part) + r"[[:space:]]*[<(]"
    res = run_git(repo, ["grep", "-n", "-I", "-E", "-e", pattern,
                         "--", "*.java", "*.ts", "*.tsx", "*.js", "*.jsx", "*.py"],
                  check=False)
    hits = []
    for line in res.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[1].isdigit():
            hits.append((parts[0], int(parts[1]), parts[2]))
    defs = [h for h in hits if _looks_like_definition(h[2], meth_part)]
    callers = [h for h in hits if h not in defs]

    # 候选排序：声明目标类的文件 > 非测试路径 > 路径 / 行号
    preferred = set()
    if cls_part:
        cres = run_git(repo, ["grep", "-l", "-E", "-e",
                              r"(class|interface|struct)\s+" + re.escape(cls_part) + r"\b",
                              "--", "*.java", "*.ts", "*.tsx", "*.js", "*.jsx", "*.py"],
                       check=False)
        preferred = set(p for p in cres.stdout.splitlines() if p.strip())

    def _rank(hit):
        fp, ln, _ = hit
        return (0 if fp in preferred else 1,
                1 if _is_test_path(fp) else 0,
                fp, ln)

    defs.sort(key=_rank)

    out.append("## 定义候选（git grep + 启发式判定）")
    out.append("")
    if defs:
        for (fp, ln, text) in defs:
            out.append("- `%s:%d` %s" % (fp, ln, text.strip()))
    else:
        out.append("（未找到定义候选；请人工确认方法名或放宽 grep 条件）")
    out.append("")

    out.append("## 入口方法完整方法体")
    out.append("")
    sibling_lines = []
    if defs:
        fp, ln, _ = defs[0]
        lines = _read_lines(os.path.join(root, fp))
        if lines:
            lang = _lang_of(fp)
            members = _members_for_lang(lines, lang) if lang in ("braced", "python") else []
            target = next(((s, e, n) for (s, e, n) in members if s <= ln <= e), None)
            if target:
                cs = max(1, target[0] - 3)
                ce = min(len(lines), target[1] + 5)
                out.append("### %s" % fp)
                out.append("")
                out.append("#### %s — 行 %d-%d" % (target[2] or "(匿名块)", cs, ce))
                out.append("")
                out.append("```" + _FENCE_OF.get(os.path.splitext(fp)[1].lower(), ""))
                out.append("".join(lines[cs - 1:ce]).rstrip())
                out.append("```")
                out.append("")
                cap = 30
                for (s, e, n) in members:
                    if (s, e, n) == target:
                        continue
                    if len(sibling_lines) >= cap:
                        sibling_lines.append("- （其余兄弟方法已省略）")
                        break
                    sibling_lines.append("- 行 %d-%d  %s" % (s, e, n or "(匿名块)"))
            else:
                out.append("> 未能定位方法边界，以下为其上下文 ±40 行：")
                out.append("")
                out.append("```" + _FENCE_OF.get(os.path.splitext(fp)[1].lower(), ""))
                out.append("".join(lines[max(0, ln - 41):ln + 39]).rstrip())
                out.append("```")
                out.append("")
    if sibling_lines:
        out.append("## 同文件兄弟方法清单（对比用，见指南 §5.2）")
        out.append("")
        out.extend(sibling_lines)
        out.append("")

    out.append("## 调用方清单（一层，供调用方回溯）")
    out.append("")
    if not callers:
        out.append("（无调用方命中；可能是入口方法 / 反射调用，请人工确认）")
        out.append("")
    else:
        used = 0
        budget = max_bytes // 2
        omitted = 0
        for (fp, ln, text) in callers:
            line_md = "- `%s:%d` %s" % (fp, ln, text.strip())
            cost = len(line_md.encode("utf-8"))
            if used + cost > budget:
                omitted = len(callers) - callers.index((fp, ln, text))
                break
            out.append(line_md)
            used += cost
        if omitted:
            out.append("- （其余 %d 条调用方超出预算省略，可用 `git grep \"%s(\"` 继续）"
                       % (omitted, meth_part))
        out.append("")

    out.append("> 以上为确定性收集材料。请继续按 review-guidelines.md §7 构建调用图，")
    out.append("> 对触达缓存 / DB 的节点 Read 完整方法体并穿透到 SQL / 缓存实现；")
    out.append("> 默认穿透深度上限 3 层，超出需在报告中说明理由。")
    out.append("")

    bundle = "\n".join(out) + "\n"
    meta = {
        "mode": "method",
        "repo_root": root,
        "target": spec,
        "def_candidates": len(defs),
        "caller_hits": len(callers),
    }
    return bundle, meta


def main():
    """命令行入口：按 --method / --base / 默认 分派到三种收集模式。"""
    ap = argparse.ArgumentParser(description="收集 Codex 风格的审查 git 上下文。")
    ap.add_argument("--repo", default=".", help="仓库路径（默认：当前目录）")
    ap.add_argument("--base", default=None,
                    help="基分支模式的基准分支（如 main、develop）。省略则为未提交模式。")
    ap.add_argument("--hide-whitespace", action="store_true",
                    help="忽略仅空白的改动（对应 Codex 的 hideWhitespace）。")
    ap.add_argument("--max-bytes", type=int, default=MAX_FILE_BYTES,
                    help="上下文包内容预算（默认 200000），按文件粒度截断，"
                         "超预算文件列入'未包含文件清单'。")
    ap.add_argument("--extract-methods", action="store_true",
                    help="提取每个修改方法 / SQL 语句的完整内容（按 diff 对应版本）。")
    ap.add_argument("--include-worktree", action="store_true",
                    help="基分支模式：把工作区未提交改动并入对比（默认仅对比 HEAD）。")
    ap.add_argument("--method", default=None,
                    help="单方法模式：目标形如 Class#method 或 method。与 --base 互斥。")
    ap.add_argument("--out", default=None, help="将上下文包写入此文件而非 stdout。")
    ap.add_argument("--json", default=None, help="将 JSON 元数据写入此文件。")
    args = ap.parse_args()

    try:
        if args.method:
            if args.base:
                raise RuntimeError("--method 与 --base 互斥：单方法模式无 diff，不使用基准分支。")
            bundle, meta = gather_method(args.repo, args.method, args.max_bytes)
        elif args.base:
            bundle, meta = gather_base_branch(args.repo, args.base, args.hide_whitespace,
                                              args.max_bytes, args.extract_methods,
                                              args.include_worktree)
        else:
            bundle, meta = gather_uncommitted(args.repo, args.hide_whitespace,
                                              args.max_bytes, args.extract_methods)
        meta["extract_methods"] = args.extract_methods
    except RuntimeError as e:
        sys.stderr.write("错误: %s\n" % e)
        sys.exit(1)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(bundle)
        print("已将上下文包写入 %s" % args.out, file=sys.stderr)
    else:
        sys.stdout.write(bundle)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        print("已将元数据写入 %s" % args.json, file=sys.stderr)


if __name__ == "__main__":
    main()
