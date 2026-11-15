#!/usr/bin/env python3
"""Tests for requirements_include_checker — stdlib unittest only.

Every file path in this file is a temporary file made up
for testing. No real secret appears anywhere in this file.
"""

import ast
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import requirements_include_checker as checker

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src/requirements_include_checker.py"


def run_cli(argv):
    """Run main(argv), capture stdout/stderr, return (code, out, err)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = checker.main(argv)
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def write(tmp, name, text, encoding="utf-8"):
    path = Path(tmp) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding=encoding)
    return str(path)


def findings_of(text, base_dir):
    return checker.check_text(text, base_dir)


class TestParseIncludes(unittest.TestCase):
    def test_r_flag_missing(self):
        self.assertEqual(
            checker.parse_includes("-r missing.txt"),
            [("-r", "missing.txt")])

    def test_require_long_flag_missing(self):
        self.assertEqual(
            checker.parse_includes("--requirement missing.txt"),
            [("-r", "missing.txt")])

    def test_require_equals_missing(self):
        self.assertEqual(
            checker.parse_includes("--requirement=missing.txt"),
            [("-r", "missing.txt")])

    def test_c_flag_missing(self):
        self.assertEqual(
            checker.parse_includes("-c missing.txt"),
            [("-c", "missing.txt")])

    def test_constraint_long_missing(self):
        self.assertEqual(
            checker.parse_includes("--constraint missing.txt"),
            [("-c", "missing.txt")])

    def test_constraint_equals_missing(self):
        self.assertEqual(
            checker.parse_includes("--constraint=missing.txt"),
            [("-c", "missing.txt")])

    def test_attached_r_missing(self):
        self.assertEqual(
            checker.parse_includes("-rmissing.txt"),
            [("-r", "missing.txt")])

    def test_attached_c_missing(self):
        self.assertEqual(
            checker.parse_includes("-cmissing.txt"),
            [("-c", "missing.txt")])

    def test_bare_r_reported(self):
        self.assertEqual(
            checker.parse_includes("-r"),
            [("-r", None)])

    def test_bare_c_reported(self):
        self.assertEqual(
            checker.parse_includes("-c"),
            [("-c", None)])

    def test_bare_long_require_reported(self):
        self.assertEqual(
            checker.parse_includes("--requirement"),
            [("-r", None)])

    def test_comment_line_skipped(self):
        self.assertEqual(
            checker.parse_includes("# -r missing.txt"), [])

    def test_blank_line_skipped(self):
        self.assertEqual(checker.parse_includes("   "), [])

    def test_package_line_skipped(self):
        self.assertEqual(
            checker.parse_includes("requests==2.31.0"), [])

    def test_editable_skipped(self):
        self.assertEqual(checker.parse_includes("-e ."), [])

    def test_index_url_skipped(self):
        self.assertEqual(
            checker.parse_includes(
                "--index-url https://pypi.org/simple"), [])

    def test_inline_comment_stripped(self):
        self.assertEqual(
            checker.parse_includes(
                "-r base.txt  # the shared base file"),
            [("-r", "base.txt")])

    def test_multiple_includes_one_line(self):
        self.assertEqual(
            checker.parse_includes("-r a.txt -c b.txt"),
            [("-r", "a.txt"), ("-c", "b.txt")])

    def test_include_after_option(self):
        self.assertEqual(
            checker.parse_includes(
                "--index-url https://pypi.org/simple -r a.txt"),
            [("-r", "a.txt")])


class TestCheckText(unittest.TestCase):
    def test_existing_include_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "base.txt", "django==4.2.7\n")
            self.assertEqual(
                findings_of("-r base.txt\n", tmp), [])

    def test_missing_include_flagged_with_line_directive_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of("-r missing.txt\n", tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["line"], 1)
            self.assertEqual(bad[0]["directive"], "-r")
            self.assertEqual(bad[0]["target"], "missing.txt")
            self.assertEqual(
                bad[0]["reason"],
                "points at a file that does not exist")

    def test_findings_in_document_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = ("-r one.txt\nrequests==2.31.0\n"
                    "-c two.txt\n--requirement three.txt\n")
            bad = findings_of(text, tmp)
            self.assertEqual([f["line"] for f in bad], [1, 3, 4])
            self.assertEqual(
                [f["directive"] for f in bad], ["-r", "-c", "-r"])

    def test_relative_resolved_to_files_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "sub/base.txt", "django==4.2.7\n")
            path = write(tmp, "sub/requirements.txt",
                         "-r base.txt\n-r gone.txt\n")
            bad, error = checker.check_file(path)
            self.assertIsNone(error)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["target"], "gone.txt")

    def test_parent_dir_include(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "base.txt", "django==4.2.7\n")
            path = write(tmp, "sub/requirements.txt",
                         "-r ../base.txt\n-r ../gone.txt\n")
            bad, error = checker.check_file(path)
            self.assertIsNone(error)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["target"], "../gone.txt")

    def test_absolute_existing_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = write(tmp, "base.txt", "django==4.2.7\n")
            self.assertEqual(
                findings_of("-r %s\n" % target, tmp), [])

    def test_absolute_missing_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "gone.txt")
            bad = findings_of("-r %s\n" % target, tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["target"], target)

    def test_directory_named_like_file_flagged(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "base.txt").mkdir()
            bad = findings_of("-r base.txt\n", tmp)
            self.assertEqual(len(bad), 1)

    def test_bare_r_finding_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of("-r\n", tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["reason"],
                             "-r has no file after it")

    def test_empty_document_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(findings_of("", tmp), [])

    def test_crlf_line_endings(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = findings_of("-r missing.txt\r\n", tmp)
            self.assertEqual(len(bad), 1)
            self.assertEqual(bad[0]["target"], "missing.txt")

    def test_comment_naming_missing_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                findings_of("# -r missing.txt\n", tmp), [])


class TestCLI(unittest.TestCase):
    def test_clean_file_exit_0(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "base.txt", "django==4.2.7\n")
            path = write(tmp, "requirements.txt",
                         "-r base.txt\nrequests==2.31.0\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 0)
            self.assertIn("every include points at a file that exists",
                          out)
            self.assertEqual(err, "")

    def test_flagged_file_exit_1_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "requirements.txt",
                         "-r missing.txt\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("line 1", out)
            self.assertIn("missing.txt", out)
            self.assertIn(path, out)

    def test_folder_walk_finds_requirements_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "requirements.txt", "requests==2.31.0\n")
            write(tmp, "requirements-dev.txt", "-r gone.txt\n")
            write(tmp, "notes.txt", "-r gone.txt\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)
            self.assertIn("requirements-dev.txt", out)
            self.assertNotIn("notes.txt", out)

    def test_folder_walk_skips_nested_with_no_recursive(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "requirements.txt", "requests==2.31.0\n")
            write(tmp, "sub/requirements.txt", "-r gone.txt\n")
            code, out, err = run_cli([tmp, "--no-recursive"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 1)
            self.assertIn("Checked 2 file(s)", out)

    def test_exclude_skips_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "requirements.txt", "requests==2.31.0\n")
            write(tmp, "requirements-dev.txt", "-r gone.txt\n")
            code, out, err = run_cli([tmp, "--exclude", "*dev*"])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_git_folder_skipped_in_walk(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "requirements.txt", "requests==2.31.0\n")
            write(tmp, ".git/requirements.txt", "-r gone.txt\n")
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_direct_file_checked_whatever_its_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "mydeps.txt", "-r gone.txt\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("mydeps.txt", out)

    def test_duplicate_paths_checked_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "requirements.txt",
                         "requests==2.31.0\n")
            code, out, err = run_cli([path, path])
            self.assertEqual(code, 0)
            self.assertIn("1 file(s) checked", out)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "requirements.txt",
                         "-r gone.txt\n")
            code, out, err = run_cli(["--json", path])
            self.assertEqual(code, 1)
            data = json.loads(out)
            self.assertEqual(data["checked"], 1)
            self.assertEqual(data["findings"], 1)
            self.assertEqual(data["files"][0]["path"], path)
            self.assertEqual(
                data["files"][0]["findings"][0]["target"], "gone.txt")
            self.assertIsNone(data["files"][0]["error"])

    def test_stdin_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input="requests==2.31.0\n", cwd=tmp,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every include points at a file that exists",
                          result.stdout)

    def test_stdin_dirty(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SRC), "--stdin"],
                input="-r missing.txt\n", cwd=tmp,
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("FAIL <stdin>: line 1", result.stdout)
            self.assertIn("missing.txt", result.stdout)

    def test_stdin_with_paths_is_usage_error(self):
        code, out, err = run_cli(["--stdin", "requirements.txt"])
        self.assertEqual(code, 2)

    def test_no_paths_is_usage_error(self):
        code, out, err = run_cli([])
        self.assertEqual(code, 2)

    def test_missing_path_exit_2(self):
        code, out, err = run_cli(["/nonexistent/path/xyz"])
        self.assertEqual(code, 2)
        self.assertIn("no such file or folder", err)

    def test_empty_folder_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli([tmp])
            self.assertEqual(code, 2)
            self.assertIn("no requirements files found", err)

    def test_bad_flag_exit_2(self):
        code, out, err = run_cli(["--nope"])
        self.assertEqual(code, 2)

    def test_version(self):
        code, out, err = run_cli(["--version"])
        self.assertEqual(code, 0)
        self.assertIn("requirements_include_checker 1.0.0", out)

    def test_non_utf8_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "requirements.txt",
                         b"\xff\xfe-r missing.txt\n")
            code, out, err = run_cli([path])
            self.assertEqual(code, 1)
            self.assertIn("not valid UTF-8", out)

    def test_input_files_left_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "requirements.txt",
                         "-r gone.txt\nrequests==2.31.0\n")
            before = Path(path).read_text()
            run_cli([path])
            self.assertEqual(Path(path).read_text(), before)

    def test_cli_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "base.txt", "django==4.2.7\n")
            write(tmp, "requirements.txt", "-r base.txt\n")
            result = subprocess.run(
                [sys.executable, str(SRC), "requirements.txt"],
                cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            self.assertIn("every include points at a file that exists",
                          result.stdout)

    def test_cli_runs_under_fake_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "base.txt", "django==4.2.7\n")
            path = write(tmp, "requirements.txt", "-r base.txt\n")
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = tmp
            try:
                code, out, err = run_cli([path])
            finally:
                if old_home is None:
                    del os.environ["HOME"]
                else:
                    os.environ["HOME"] = old_home
            self.assertEqual(code, 0)


class TestExamples(unittest.TestCase):
    def test_run_example_output_matches_sample(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        expected = (REPO / "examples/sample-output.md").read_text()
        self.assertEqual(result.stdout, expected)

    def test_readme_quotes_match_real_runs(self):
        readme = (REPO / "README.md").read_text()
        clean = subprocess.run(
            [sys.executable, "src/requirements_include_checker.py",
             "examples/requirements.txt"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(clean.returncode, 0)
        self.assertIn(clean.stdout.strip(), readme)
        flagged = subprocess.run(
            [sys.executable, "src/requirements_include_checker.py",
             "examples/requirements-flagged.txt"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(flagged.returncode, 1)
        self.assertIn(flagged.stdout.strip(), readme)
        folder = subprocess.run(
            [sys.executable, "src/requirements_include_checker.py",
             "examples/"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(folder.returncode, 1)
        self.assertIn("Checked 4 file(s), 2 missing include(s) in 1 "
                      "file(s).", folder.stdout)
        self.assertIn("Checked 4 file(s), 2 missing include(s) in 1 "
                      "file(s).", readme)
        edge = subprocess.run(
            [sys.executable, "src/requirements_include_checker.py",
             "examples/requirements-edge.txt"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(edge.returncode, 0)
        self.assertIn(edge.stdout.strip(), readme)
        js = subprocess.run(
            [sys.executable, "src/requirements_include_checker.py",
             "--json", "examples/requirements-flagged.txt"],
            cwd=REPO, capture_output=True, text=True)
        self.assertEqual(js.returncode, 1)
        self.assertIn(js.stdout.strip(), readme)


class TestHygiene(unittest.TestCase):
    def _repo_files(self, skip_tests=True, skip_examples=True):
        for root, dirs, files in os.walk(REPO):
            dirs[:] = [d for d in dirs
                       if d not in (".git", "__pycache__")
                       and not (skip_tests and d == "tests")
                       and not (skip_examples and d == "examples")]
            for name in files:
                if name.endswith(".pyc"):
                    continue
                yield Path(root) / name

    def test_no_placeholder_text(self):
        banned = ["TODO", "coming soon", "lorem", "FIXME", "XXX"]
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for word in banned:
                if word in text:
                    hits.append("%s: %s" % (path.name, word))
        self.assertEqual(hits, [])

    def test_no_absolute_paths(self):
        hits = []
        for path in self._repo_files(skip_tests=True,
                                     skip_examples=False):
            text = path.read_text(errors="ignore")
            for marker in ("/home/", "/Users/", "C:\\"):
                if marker in text:
                    hits.append("%s: %s" % (path.name, marker))
        self.assertEqual(hits, [])

    def test_no_real_secrets_outside_tests_and_examples(self):
        # The source holds no key values at all; the tests
        # and examples hold fake values only, so they are
        # excluded from this scan.
        patterns = [
            re.compile(r"AKIA[0-9A-Z]{16}"),
            re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
            re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
            re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
            re.compile(r"AIza[0-9A-Za-z_-]{35}"),
            re.compile(r"[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"),
            re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
            re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ"),
        ]
        hits = []
        for path in self._repo_files():
            text = path.read_text(errors="ignore")
            for pattern in patterns:
                if pattern.search(text):
                    hits.append("%s: %s" % (path.name, pattern.pattern))
        self.assertEqual(hits, [])

    def test_stdlib_imports_only(self):
        stdlib = set(sys.stdlib_module_names)
        for target in (REPO / "src/requirements_include_checker.py",
                       REPO / "tests/test_requirements_include_checker.py"):
            tree = ast.parse(target.read_text())
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0]
                                    for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            self.assertFalse(
                imported - stdlib - {"requirements_include_checker"},
                (target.name, imported))
            self.assertNotIn("yaml", imported)

    def test_no_network_use_in_src(self):
        src = (REPO / "src/requirements_include_checker.py").read_text()
        for marker in ("urllib.request", "requests", "socket",
                       "http.client", "urlopen", "urlretrieve"):
            self.assertNotIn(marker, src, marker)

    def test_gitignore_lists_env_first(self):
        lines = (REPO / ".gitignore").read_text().splitlines()
        self.assertEqual(lines[0], ".env")

    def test_ci_runs_this_test_file(self):
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        self.assertIn("tests/test_requirements_include_checker.py", ci)
        self.assertIn("ubuntu-latest", ci)
        self.assertIn("3.12", ci)
        self.assertIn("actions/checkout", ci)
        self.assertIn("setup-python", ci)
        self.assertIn("push", ci)
        self.assertIn("pull_request", ci)

    def test_readme_names_the_neighbouring_repos(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("requirements-pin-checker-cli", readme)
        self.assertIn("requirements-duplicate-checker-cli", readme)
        self.assertIn("requirements-sort-checker-cli", readme)


if __name__ == "__main__":
    unittest.main()
