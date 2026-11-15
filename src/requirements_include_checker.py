#!/usr/bin/env python3
"""Check -r / --requirement and -c / --constraint includes in
requirements files point at files that actually exist.

Run: python3 src/requirements_include_checker.py requirements.txt
     python3 src/requirements_include_checker.py project/
     python3 src/requirements_include_checker.py --stdin < requirements.txt

An include that points at a file that was moved, renamed,
or never committed breaks "pip install -r" at the worst
moment — on a fresh machine, in CI, at deploy time. This
tool reads each requirements file, finds every -r /
--requirement and -c / --constraint include, resolves it
relative to the requirements file's own directory, and
reports each one that points at a file that does not
exist, with the file and the line number. It exits 1 when
any include is missing, so it can fail a CI run. A file
whose includes all exist exits 0.

An include written as "-r file.txt", "--requirement
file.txt", "--requirement=file.txt", "-c file.txt",
"--constraint file.txt", or "--constraint=file.txt" is
checked, and so is the attached form "-rfile.txt" /
"-cfile.txt". A bare "-r" or "-c" with no file after it
is reported too — pip would fail on it as well.

Only the includes in the files you point at are checked.
Included files are not followed: a missing include inside
an included file is that file's own problem when it is
checked itself. Package lines, "-e" editable installs,
"--index-url" and every other option are left alone.

It never rewrites a file, never touches the network, and
reads only the files and folders you point it at.
"""

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

__version__ = "1.0.0"

REQUIREMENTS_NAME = re.compile(r"^requirements.*\.txt$", re.IGNORECASE)


def _strip_comment(line):
    """Drop a trailing " # comment" from one requirements line."""
    if " #" in line:
        return line.split(" #", 1)[0].rstrip()
    return line


def parse_includes(line):
    """Return the include targets named on one line.

    Each result is (directive, target) where directive is
    "-r" or "-c" as written, or ("-r", None) / ("-c", None)
    for a bare flag with no file after it. Comment lines,
    blank lines, package lines, and other options give [].
    """
    stripped = line.strip()
    if stripped == "" or stripped.startswith("#"):
        return []
    stripped = _strip_comment(line).strip()
    if stripped == "" or stripped.startswith("#"):
        return []
    tokens = stripped.split()
    found = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in ("-r", "--requirement"):
            if index + 1 < len(tokens):
                found.append(("-r", tokens[index + 1]))
                index += 2
            else:
                found.append(("-r", None))
                index += 1
        elif token in ("-c", "--constraint"):
            if index + 1 < len(tokens):
                found.append(("-c", tokens[index + 1]))
                index += 2
            else:
                found.append(("-c", None))
                index += 1
        elif token.startswith("--requirement="):
            found.append(("-r", token[len("--requirement="):]))
            index += 1
        elif token.startswith("--constraint="):
            found.append(("-c", token[len("--constraint="):]))
            index += 1
        elif token.startswith("-r") and len(token) > 2:
            found.append(("-r", token[2:]))
            index += 1
        elif token.startswith("-c") and len(token) > 2:
            found.append(("-c", token[2:]))
            index += 1
        else:
            index += 1
    return found


def check_text(text, base_dir):
    """Check one document's text.

    base_dir is the folder includes are resolved against —
    the requirements file's own directory, or the working
    folder for standard input. Returns a list of findings,
    each {"line": int, "directive": str, "target": str,
    "reason": str}, in document order.
    """
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        for directive, target in parse_includes(line):
            if target is None or target == "":
                findings.append({
                    "line": number,
                    "directive": directive,
                    "target": "",
                    "reason": "%s has no file after it" % directive,
                })
                continue
            candidate = Path(target)
            if not candidate.is_absolute():
                candidate = Path(base_dir) / target
            if not candidate.is_file():
                findings.append({
                    "line": number,
                    "directive": directive,
                    "target": target,
                    "reason": "points at a file that does not exist",
                })
    return findings


def check_file(path):
    """Check one file. Returns (findings, error)."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], "not valid UTF-8"
    except OSError as exc:
        return [], str(exc)
    base_dir = str(Path(path).parent)
    return check_text(text, base_dir), None


def _is_requirements_file(path):
    return bool(REQUIREMENTS_NAME.match(Path(path).name))


def collect_files(paths, recursive=True, exclude=None):
    """Expand CLI paths into a sorted list of requirements files.

    A file given directly is always checked, whatever its
    name. A folder is walked for files named
    requirements*.txt only. .git folders are never walked,
    and directory links are never followed.
    """
    exclude = exclude or []
    found = []
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            found.append(str(path))
        elif path.is_dir():
            for dirpath, dirs, files in os.walk(path, followlinks=False):
                dirs[:] = [
                    d for d in dirs
                    if d != ".git"
                    and not any(fnmatch.fnmatch(d, pat) for pat in exclude)
                ]
                for name in files:
                    candidate = Path(dirpath) / name
                    if not _is_requirements_file(candidate):
                        continue
                    if any(
                        fnmatch.fnmatch(str(candidate), pat)
                        or fnmatch.fnmatch(name, pat)
                        for pat in exclude
                    ):
                        continue
                    found.append(str(candidate))
                if not recursive:
                    break
        else:
            raise FileNotFoundError("no such file or folder: %s" % raw)
    seen = set()
    unique = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return sorted(unique)


def format_finding(path, finding):
    """One human-readable line for one missing include."""
    if finding["target"] == "":
        return ("FAIL %s: line %d %s %s"
                % (path, finding["line"], finding["directive"],
                   finding["reason"]))
    return ("FAIL %s: line %d %s '%s' %s"
            % (path, finding["line"], finding["directive"],
               finding["target"], finding["reason"]))


def run(paths, recursive=True, exclude=None, as_json=False):
    """Check paths, print the report, return the exit code."""
    try:
        files = collect_files(paths, recursive=recursive, exclude=exclude)
    except FileNotFoundError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    if not files:
        print("error: no requirements files found", file=sys.stderr)
        return 2
    results = []
    findings = 0
    files_with_findings = 0
    for path in files:
        bad, error = check_file(path)
        count = len(bad) + (1 if error else 0)
        if count:
            findings += count
            files_with_findings += 1
        results.append({"path": path, "findings": bad, "error": error})
    if as_json:
        print(json.dumps(
            {"files": results, "checked": len(files),
             "findings": findings},
            indent=2))
    else:
        for result in results:
            if result["error"]:
                print("FAIL %s: %s" % (result["path"], result["error"]))
            for finding in result["findings"]:
                print(format_finding(result["path"], finding))
        if findings:
            print("Checked %d file(s), %d missing include(s) in %d "
                  "file(s)." % (len(files), findings,
                                files_with_findings))
        else:
            print("OK — %d file(s) checked, every include points at "
                  "a file that exists." % len(files))
    return 1 if findings else 0


def run_stdin(as_json=False):
    """Check one requirements document read from standard input."""
    text = sys.stdin.read()
    bad = check_text(text, os.getcwd())
    findings = len(bad)
    if as_json:
        print(json.dumps(
            {"files": [{"path": "<stdin>", "findings": bad,
                        "error": None}],
             "checked": 1, "findings": findings},
            indent=2))
    else:
        for finding in bad:
            print(format_finding("<stdin>", finding))
        if findings:
            print("Checked 1 file(s), %d missing include(s) in 1 "
                  "file(s)." % findings)
        else:
            print("OK — 1 file(s) checked, every include points at "
                  "a file that exists.")
    return 1 if findings else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="requirements_include_checker",
        description="Check -r / --requirement and -c / "
                    "--constraint includes in requirements files "
                    "point at files that actually exist, fail CI "
                    "when one does not.")
    parser.add_argument("paths", nargs="*",
                        help="requirements files or folders to walk")
    parser.add_argument("--no-recursive", action="store_true",
                        help="do not walk into subfolders")
    parser.add_argument("--exclude", action="append", default=[],
                        help="skip files or folders matching this pattern "
                             "(repeatable)")
    parser.add_argument("--json", action="store_true",
                        help="print the result as JSON")
    parser.add_argument("--stdin", action="store_true",
                        help="check one requirements document from "
                             "standard input")
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    if args.stdin:
        if args.paths:
            parser.error("--stdin takes no file or folder arguments")
        return run_stdin(as_json=args.json)
    if not args.paths:
        parser.error("give at least one requirements file or folder")
    return run(args.paths, recursive=not args.no_recursive,
               exclude=args.exclude, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
