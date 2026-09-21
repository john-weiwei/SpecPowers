# -*- coding: utf-8 -*-
"""gather_review_context.py 的单元与集成测试。

运行方式（在本技能根目录下）：
    python -m unittest discover -s scripts/tests -v

集成测试会在系统临时目录创建真实 git 仓库，需要本机可用 git。
作者: 张威威(005819) / GLM
日期: 2026-09-14
"""
import os
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS_DIR = os.path.dirname(_HERE)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import gather_review_context as g  # noqa: E402


# ——— 单元测试：成员表算法 ———

JAVA_NESTED = """\
public class OrderService {
    private ConfigCache cache;

    public ConfigDTO matchConfig(java.util.List<ConfigDTO> configs, String areaNo) {
        if (areaNo == null) {
            return null;
        }
        for (ConfigDTO config : configs) {
            if (config.getAreaSet().contains(areaNo)) {
                if (config.getLevel() == 1) {
                    if (cache != null) {
                        return decorate(config);
                    }
                }
            }
        }
        return null;
    }
}
"""


class MemberTableTest(unittest.TestCase):
    """阶段一回归：成员表算法对嵌套 / 换行风格 / 字面量的稳健性。"""

    def test_deep_nested_change_extracts_full_method(self):
        """回归：变更落在 4 层嵌套块内，仍能提取完整方法体（v2 会静默失败）。"""
        lines = JAVA_NESTED.split("\n")
        change_line = lines.index("                        return decorate(config);") + 1
        blocks = g._extract_methods(lines, [(change_line, change_line)], lang="braced")
        self.assertEqual(len(blocks), 1)
        start, end, name = blocks[0]
        self.assertEqual(name, "matchConfig")
        snippet = "".join(lines[start - 1:end])
        self.assertIn("public ConfigDTO matchConfig", snippet)
        self.assertIn("return decorate(config);", snippet)
        self.assertIn("return null;", snippet)

    def test_allman_style(self):
        """大括号换行（Allman）风格：签名行与 '{' 分离时仍能回溯出完整签名。"""
        code = "\n".join([
            "public class A",
            "{",
            "    public int bar()",
            "    {",
            "        return 1;",
            "    }",
            "}",
            "",
        ])
        lines = code.split("\n")
        blocks = g._extract_methods(lines, [(5, 5)], lang="braced")
        self.assertEqual(len(blocks), 1)
        start, end, name = blocks[0]
        self.assertEqual(name, "bar")
        snippet = "".join(lines[start - 1:end])
        self.assertIn("public int bar()", snippet)
        self.assertIn("return 1;", snippet)

    def test_braces_in_strings_ignored(self):
        """字符串字面量中的 '{' 不参与深度计算，否则后续方法识别会错位。"""
        code = "\n".join([
            "public class A {",
            "    private String brace = \"{\";",
            "",
            "    public int bar(int x) {",
            "        if (x > 0) {",
            "            return 1;",
            "        }",
            "        return 0;",
            "    }",
            "}",
            "",
        ])
        lines = code.split("\n")
        blocks = g._extract_methods(lines, [(6, 6)], lang="braced")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][2], "bar")

    def test_multiline_signature_and_annotations(self):
        """多行签名 + 注解行：成员起点回溯应包含注解与签名续行。"""
        code = "\n".join([
            "public class A {",
            "    @Override",
            "    @SuppressWarnings(\"unused\")",
            "    public void foo(",
            "        int a,",
            "        int b) {",
            "        if (a > b) {",
            "            return;",
            "        }",
            "    }",
            "}",
            "",
        ])
        lines = code.split("\n")
        blocks = g._extract_methods(lines, [(8, 8)], lang="braced")
        self.assertEqual(len(blocks), 1)
        start, end, name = blocks[0]
        self.assertEqual(name, "foo")
        snippet = "".join(lines[start - 1:end])
        self.assertIn("@Override", snippet)
        self.assertIn("int b) {", snippet)

    def test_control_keywords_not_members(self):
        """控制流关键字行不构成成员；模块级函数（TS）正常识别。"""
        code = "\n".join([
            "const flag = true;",
            "if (flag) {",
            "    console.log(\"hi\");",
            "}",
            "export function foo(x) {",
            "    return x;",
            "}",
            "",
        ])
        lines = code.split("\n")
        blocks = g._extract_methods(lines, [(6, 6)], lang="braced")
        names = [b[2] for b in blocks]
        self.assertEqual(names, ["foo"])

    def test_select_members_prefers_outermost(self):
        """Python 嵌套函数：变更落在 inner 内时保留外层（控制流上下文更完整）。"""
        code = "\n".join([
            "def outer():",
            "    def inner():",
            "        return 1",
            "    return inner()",
            "",
        ])
        lines = code.split("\n")
        members = g._find_members_python(lines)
        selected = g._select_members(members, [(3, 3)])
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][2], "outer")


class PythonXmlExtractionTest(unittest.TestCase):
    """阶段二：Python 缩进提取与 Mapper XML SQL 语句块提取。"""

    def test_python_def_with_decorator(self):
        code = "\n".join([
            "import os",
            "",
            "",
            "@decorator",
            "async def fetch_items(client, limit=10):",
            "    items = []",
            "    for page in range(limit):",
            "        if page % 2 == 0:",
            "            items.append(page)",
            "    return items",
            "",
            "",
            "def other():",
            "    return 1",
            "",
        ])
        lines = code.split("\n")
        change_line = lines.index("            items.append(page)") + 1
        blocks = g._extract_methods(lines, [(change_line, change_line)], lang="python")
        self.assertEqual(len(blocks), 1)
        start, end, name = blocks[0]
        self.assertEqual(name, "fetch_items")
        snippet = "".join(lines[start - 1:end])
        self.assertIn("@decorator", snippet)
        self.assertIn("return items", snippet)
        self.assertNotIn("def other", snippet)

    def test_xml_blocks(self):
        code = "\n".join([
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<mapper namespace="com.x.OrderMapper">',
            '    <select id="queryOrder" resultType="map">',
            "        SELECT * FROM t_order",
            "        WHERE status = 1",
            "    </select>",
            '    <select id="queryNew" resultType="map">',
            "        SELECT * FROM t_order WHERE status = 2",
            "    </select>",
            "</mapper>",
            "",
        ])
        lines = code.split("\n")
        blocks = g._extract_methods(lines, [(5, 5)], lang="xml")
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0][2], "queryOrder")
        snippet = "".join(lines[blocks[0][0] - 1:blocks[0][1]])
        self.assertIn('<select id="queryOrder"', snippet)
        self.assertIn("</select>", snippet)
        self.assertNotIn("queryNew", snippet)


class DiffParseTest(unittest.TestCase):
    """阶段一：diff 头解析健壮性。"""

    def test_split_diff_path_with_spaces(self):
        diff = "\n".join([
            "diff --git a/dir with space/My File.java b/dir with space/My File.java",
            "index 1111111..2222222 100644",
            "--- a/dir with space/My File.java",
            "+++ b/dir with space/My File.java",
            "@@ -1,3 +1,3 @@",
            " old",
            "-int a() {",
            "+int b() {",
            " end",
            "",
        ])
        files = g._split_diff_files(diff)
        self.assertEqual(len(files), 1)
        path, chunk = files[0]
        self.assertEqual(path, "dir with space/My File.java")
        self.assertEqual(g._parse_hunks(chunk), [(1, 3)])

    def test_parse_hunks_edge_cases(self):
        self.assertEqual(g._parse_hunks("@@ -1,5 +2,6 @@ x"), [(2, 7)])
        self.assertEqual(g._parse_hunks("@@ -0,0 +1,3 @@"), [(1, 3)])
        self.assertEqual(g._parse_hunks("@@ -5 +5 @@ x"), [(5, 5)])
        self.assertEqual(g._parse_hunks("@@ -1,0 +0,0 @@ x"), [])

    def test_looks_like_definition(self):
        self.assertTrue(g._looks_like_definition(
            "    public String greet(String name) {", "greet"))
        self.assertTrue(g._looks_like_definition("def greet(name):", "greet"))
        # TS 风格：async 修饰的方法定义 / 方法名直接开头的签名
        self.assertTrue(g._looks_like_definition(
            "  async request(method: string, path: string) {", "request"))
        self.assertTrue(g._looks_like_definition(
            "  request(method: string) {", "request"))
        # 泛型形式：meth<...>(
        self.assertTrue(g._looks_like_definition(
            "    async request<T extends ApiResponse = ApiResponse>(", "request"))
        self.assertFalse(g._looks_like_definition(
            "        return this.request<T>('GET', path, { query });", "request"))
        self.assertFalse(g._looks_like_definition(
            "        return s.greet(\"bob\");", "greet"))
        self.assertFalse(g._looks_like_definition(
            "        String s = greet(name);", "greet"))
        self.assertFalse(g._looks_like_definition(
            "        return greet(name);", "greet"))
        self.assertFalse(g._looks_like_definition(
            "        request('GET', path);", "request"))


# ——— 集成测试：临时 git 仓库 ———

def _git(repo, *args):
    subprocess.run(["git", "-C", repo] + list(args), check=True,
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace")


def _retry_git(repo, *args, attempts=3):
    """带重试的 git 调用：Windows 下临时目录可能被杀毒/索引服务短暂锁住。"""
    import time
    last = None
    for _ in range(attempts):
        proc = subprocess.run(["git", "-C", repo] + list(args), check=False,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        if proc.returncode == 0:
            return
        last = proc
        time.sleep(0.2)
    raise AssertionError("git %s 重试 %d 次仍失败: %s"
                         % (" ".join(args), attempts, last.stderr.strip()))


class RepoTestBase(unittest.TestCase):
    """集成测试基类：搭建带中文用户名的临时 git 仓库。"""

    def setUp(self):
        # ignore_cleanup_errors：Windows 下 git 进程可能短暂占用 .git/objects 内的临时文件
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.repo = self._tmp.name
        _git(self.repo, "init", "-q")
        for key, val in (("user.email", "test@example.com"),
                         ("user.name", "测试者"),
                         ("core.autocrlf", "false"),
                         ("commit.gpgsign", "false")):
            _retry_git(self.repo, "config", key, val)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, relpath, content):
        path = os.path.join(self.repo, relpath)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        return path

    def commit(self, relpath, content, message):
        self.write(relpath, content)
        _git(self.repo, "add", relpath)
        _git(self.repo, "commit", "-q", "-m", message)

    def base_sha(self):
        res = subprocess.run(["git", "-C", self.repo, "rev-parse", "HEAD"],
                             capture_output=True, text=True, encoding="utf-8",
                             check=True)
        return res.stdout.strip()


class BaseBranchModeTest(RepoTestBase):
    """阶段二：基分支模式默认只含已提交改动，提取基于 HEAD 版本。"""

    JAVA = "class A {\n    int old() {\n        return %d;\n    }\n}\n"

    def test_default_excludes_worktree_changes(self):
        self.commit("src/A.java", self.JAVA % 1, "基线提交")
        base = self.base_sha()
        self.commit("src/A.java", self.JAVA % 2, "分支提交")
        self.write("src/A.java", self.JAVA % 999)
        bundle, meta = g.gather_base_branch(self.repo, base, False, 200000, False, False)
        self.assertIn("仅已提交改动", bundle)
        self.assertNotIn("return 999", bundle)
        self.assertIn("return 2", bundle)
        self.assertFalse(meta["include_worktree"])

    def test_include_worktree_contains_uncommitted(self):
        self.commit("src/A.java", self.JAVA % 1, "基线提交")
        base = self.base_sha()
        self.write("src/A.java", self.JAVA % 999)
        bundle, meta = g.gather_base_branch(self.repo, base, False, 200000, False, True)
        self.assertIn("合并基点..工作区", bundle)
        self.assertIn("return 999", bundle)
        self.assertTrue(meta["include_worktree"])

    def test_chinese_commit_message_no_mojibake(self):
        """阶段一回归：Windows 下中文提交信息与中文 diff 内容不乱码。"""
        self.commit("a.txt", "你好世界\n", "基线")
        base = self.base_sha()
        self.commit("a.txt", "你好世界2\n", "修复中文乱码问题")
        bundle, _ = g.gather_base_branch(self.repo, base, False, 200000, False, False)
        self.assertIn("修复中文乱码问题", bundle)
        self.assertIn("你好世界2", bundle)

    def test_extraction_uses_head_version(self):
        """方法体提取基于 HEAD 而非工作区：工作区未提交的 555 不应出现。"""
        self.commit("src/B.java", self.JAVA % 1, "基线")
        base = self.base_sha()
        self.commit("src/B.java", self.JAVA % 42, "修改方法")
        self.write("src/B.java", self.JAVA % 555)
        bundle, _ = g.gather_base_branch(self.repo, base, False, 200000, True, False)
        self.assertIn("变更方法完整上下文", bundle)
        self.assertIn("return 42", bundle)
        self.assertNotIn("return 555", bundle)

    def test_path_with_spaces_and_chinese(self):
        """阶段一回归：含空格 + 中文名称的路径可正确解析（core.quotepath=false）。"""
        rel = "src with space/中文 文件.java"
        self.commit(rel, self.JAVA % 1, "基线")
        base = self.base_sha()
        self.commit(rel, self.JAVA % 77, "修改含空格路径文件")
        bundle, _ = g.gather_base_branch(self.repo, base, False, 200000, True, False)
        self.assertIn(rel, bundle)
        self.assertIn("return 77", bundle)


class UncommittedModeTest(RepoTestBase):
    """阶段二：未提交模式按 index / 工作区分别提取，预算按文件粒度截断。"""

    JAVA = "class B {\n    int m() {\n        return %d;\n    }\n}\n"

    def test_staged_extraction_uses_index(self):
        self.commit("src/B.java", self.JAVA % 1, "基线")
        self.write("src/B.java", self.JAVA % 42)
        _git(self.repo, "add", "src/B.java")
        self.write("src/B.java", self.JAVA % 99)
        bundle, _ = g.gather_uncommitted(self.repo, False, 200000, True)
        # 只取"已暂存提取"章节（其后才是未暂存提取章节；两个 diff 章节本身
        # 合法包含 42/99，不能作为断言范围）
        staged_extract = bundle.split("变更方法完整上下文（已暂存")[1]
        staged_extract = staged_extract.split("变更方法完整上下文（未暂存")[0]
        self.assertIn("return 42", staged_extract)
        self.assertNotIn("return 99", staged_extract)
        unstaged_extract = bundle.split("变更方法完整上下文（未暂存")[1]
        self.assertIn("return 99", unstaged_extract)
        self.assertNotIn("return 42", unstaged_extract)

    def test_deleted_file_skips_extraction_with_note(self):
        self.commit("src/D.java", self.JAVA % 1, "基线")
        os.remove(os.path.join(self.repo, "src", "D.java"))
        bundle, _ = g.gather_uncommitted(self.repo, False, 200000, True)
        self.assertIn("已删除", bundle)
        self.assertIn("跳过方法体提取", bundle)

    def test_budget_excludes_files_and_lists_them(self):
        """阶段二回归：未提交模式同样受 --max-bytes 约束，超预算文件入清单。"""
        self.commit("f1.txt", "", "基线1")
        self.commit("f2.txt", "", "基线2")
        self.commit("f3.txt", "", "基线3")
        big = "x" * 800 + "\n"
        for name in ("f1.txt", "f2.txt", "f3.txt"):
            self.write(name, big)
        bundle, meta = g.gather_uncommitted(self.repo, False, 1000, False)
        self.assertIn("未包含文件清单", bundle)
        self.assertTrue(meta["truncated"])
        excluded_names = [e["path"] for e in meta["excluded_files"]]
        self.assertTrue(set(excluded_names) <= {"f1.txt", "f2.txt", "f3.txt"})
        self.assertTrue(excluded_names)
        self.assertIn("x" * 50, bundle)

    def test_truncation_note_mentions_read_tool(self):
        self.commit("f1.txt", "", "基线")
        self.write("f1.txt", "y" * 2000)
        bundle, _ = g.gather_uncommitted(self.repo, False, 500, False)
        self.assertIn("Read 工具", bundle)


class XmlIntegrationTest(RepoTestBase):
    """阶段二：Mapper XML 的完整 SQL 语句块提取（基分支模式）。"""

    def test_mapper_sql_block_extracted(self):
        base_xml = "\n".join([
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<mapper namespace="com.x.OrderMapper">',
            '    <select id="queryOrder" resultType="map">',
            "        SELECT * FROM t_order",
            "    </select>",
            "",
            "",
            "",
            "",
            '    <select id="queryNew" resultType="map">',
            "        SELECT * FROM t_order WHERE status = 2",
            "    </select>",
            "</mapper>",
            "",
        ])
        self.commit("src/main/resources/mapper/OrderMapper.xml", base_xml, "基线 mapper")
        base = self.base_sha()
        new_xml = base_xml.replace(
            "SELECT * FROM t_order\n    </select>",
            "SELECT * FROM t_order\n        WHERE status = 1\n    </select>", 1)
        self.commit("src/main/resources/mapper/OrderMapper.xml", new_xml, "追加过滤条件")
        bundle, _ = g.gather_base_branch(self.repo, base, False, 200000, True, False)
        section = bundle.split("变更方法完整上下文")[-1]
        self.assertIn('<select id="queryOrder"', section)
        self.assertIn("WHERE status = 1", section)
        self.assertIn("</select>", section)
        self.assertNotIn("queryNew", section)


class MethodModeTest(RepoTestBase):
    """阶段三：--method 单方法模式。"""

    def test_method_mode_dumps_body_siblings_callers(self):
        service = "\n".join([
            "package svc;",
            "public class GreeterService {",
            "    public String greet(String name) {",
            "        if (name == null) {",
            "            return \"hi\";",
            "        }",
            "        return \"hello \" + name;",
            "    }",
            "",
            "    public String greetLoud(String name) {",
            "        return greet(name).toUpperCase();",
            "    }",
            "}",
            "",
        ])
        self.commit("src/svc/GreeterService.java", service, "基线服务")
        caller = "\n".join([
            "package app;",
            "import svc.GreeterService;",
            "public class App {",
            "    public String run(GreeterService s) {",
            "        return s.greet(\"bob\");",
            "    }",
            "}",
            "",
        ])
        self.commit("src/app/App.java", caller, "调用方")
        bundle, meta = g.gather_method(self.repo, "GreeterService#greet", 200000)
        self.assertEqual(meta["mode"], "method")
        self.assertIn("定义候选", bundle)
        self.assertIn("GreeterService.java", bundle)
        self.assertIn("return \"hello \" + name;", bundle)
        self.assertIn("greetLoud", bundle)
        self.assertIn("调用方清单", bundle)
        self.assertIn("App.java", bundle)

    def test_method_mode_without_hits(self):
        self.commit("a.txt", "content\n", "基线")
        bundle, meta = g.gather_method(self.repo, "NoSuch#method", 200000)
        self.assertEqual(meta["mode"], "method")
        self.assertIn("未找到定义候选", bundle)

    def test_method_base_mutually_exclusive(self):
        """--method 与 --base 互斥，同时给出应报错退出。"""
        self.commit("a.txt", "content\n", "基线")
        proc = subprocess.run(
            [sys.executable, os.path.join(_SCRIPTS_DIR, "gather_review_context.py"),
             "--repo", self.repo, "--method", "A#m", "--base", "main"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("互斥", proc.stderr)


if __name__ == "__main__":
    unittest.main()
