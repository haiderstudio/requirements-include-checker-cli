# requirements-include-checker-cli

Check `-r` / `--requirement` and `-c` / `--constraint` includes in requirements files point at files that actually exist — fail CI when one does not.

[![CI](https://github.com/haiderstudio/requirements-include-checker-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/requirements-include-checker-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`requirements_include_checker` reads a requirements
file, finds every `-r` / `--requirement` and `-c` /
`--constraint` include, resolves it relative to that
file's own directory, and reports each one that points
at a file that does not exist, with the file and the
line number. It exits 1 when any include is missing,
so it can fail a CI run. A file whose includes all
exist exits 0.

- An include pointing at a file that was moved,
  renamed, or never committed breaks `pip install -r`
  at the worst moment — on a fresh machine, in CI, at
  deploy time. This names the exact line before that
  happens, and the fix is one line per reference.
- Every include form is checked: `-r file.txt`,
  `--requirement file.txt`, `--requirement=file.txt`,
  `-c file.txt`, `--constraint file.txt`,
  `--constraint=file.txt`, and the attached forms
  `-rfile.txt` and `-cfile.txt`. A bare `-r` or `-c`
  with no file after it is reported too — pip would
  fail on that as well.
- Includes are resolved relative to the requirements
  file's own directory, so a file in `requirements/`
  that says `-r ../base.txt` is checked against the
  folder above it, not against wherever you ran the
  tool from. An absolute path is checked as written.
- A file given directly on the command line is always
  checked, whatever its name. A folder is walked for
  files named `requirements*.txt` only, recursively by
  default (`--no-recursive` stops at the top level).
  `.git` folders are never walked, and directory links
  are never followed.
- `--json` prints the result as JSON, and `--stdin`
  checks one requirements document read from standard
  input (includes resolve against the working folder
  there).
- Comment lines are never checked, blank lines are
  skipped, and an inline ` # comment` after an
  include is stripped before the check. Package lines,
  `-e` editable installs, `--index-url`, and every
  other option are left alone.
- Only the includes in the files you point at are
  checked. Included files are not followed: a missing
  include inside an included file is that file's own
  problem when it is checked itself.

## Who it is for

Anyone with a Python project whose requirements are
split across files — a base file, a dev file, a
constraints file. One renamed file and the install
breaks on the machine that matters most, the one you
did not test on. This is the gate that stops it at
the pull request.

## What it does NOT do

- It does not check whether a package is pinned, a
  duplicate, or sorted. That is repo #28,
  requirements-pin-checker-cli, repo #55,
  requirements-duplicate-checker-cli, and repo #90,
  requirements-sort-checker-cli — pins, duplicates,
  and order are different checks on the same files.
- It does not check whether an included file's own
  contents are valid, and it does not follow includes
  into included files. Each file is checked on its
  own, against its own directory.
- It does not check package names, versions, or
  whether a package exists on PyPI. A line that is
  not an include is not this tool's job.
- It never rewrites a file, and it never touches the
  network.

## How this differs

- A fresh search of GitHub on Nov 14, 2026 found 0
  results for `"requirements-include-checker-cli"`
  and 13 results for `requirements include checker`,
  all noise — pages that merely contain the words:
  - bayleyEddy/bash_password_checker, 0 stars (a
    password-strength checker)
  - hassanalawie/SYDE-Options-Checker, 0 stars (a
    course-requirements checker for students)
  - evancuczhughes5660/scam-message-checker-tool,
    0 stars (a browser tool that checks messages
    for scams)
  - Usman15021/password-strength-checker, 0 stars
    (a password-strength checker)
  - yashika547/password-checker, 0 stars (a
    password-strength checker)
- None of them checks requirements includes. No
  rival checks `-r` / `-c` targets in local files.

## Install

```sh
git clone https://github.com/haiderstudio/requirements-include-checker-cli.git
cd requirements-include-checker-cli
```

There is nothing else to install: Python 3.10 or newer,
standard library only, no dependencies.

## Usage

Check one requirements file:

```sh
python3 src/requirements_include_checker.py requirements.txt
```

A file whose includes all exist passes:

```sh
$ python3 src/requirements_include_checker.py examples/requirements.txt
OK — 1 file(s) checked, every include points at a file that exists.
```

A file with includes pointing nowhere fails, with the
file and line for each one:

```sh
$ python3 src/requirements_include_checker.py examples/requirements-flagged.txt
FAIL examples/requirements-flagged.txt: line 2 -r 'missing-base.txt' points at a file that does not exist
FAIL examples/requirements-flagged.txt: line 3 -c 'missing-constraints.txt' points at a file that does not exist
Checked 1 file(s), 2 missing include(s) in 1 file(s).
```

Check a whole folder (`requirements*.txt` files only):

```sh
$ python3 src/requirements_include_checker.py examples/
FAIL examples/requirements-flagged.txt: line 2 -r 'missing-base.txt' points at a file that does not exist
FAIL examples/requirements-flagged.txt: line 3 -c 'missing-constraints.txt' points at a file that does not exist
Checked 4 file(s), 2 missing include(s) in 1 file(s).
```

Check one document from standard input:

```sh
$ printf -- '-r missing.txt\n' | python3 src/requirements_include_checker.py --stdin
FAIL <stdin>: line 1 -r 'missing.txt' points at a file that does not exist
Checked 1 file(s), 1 missing include(s) in 1 file(s).
```

Machine-readable output:

```sh
$ python3 src/requirements_include_checker.py --json examples/requirements-flagged.txt
{
  "files": [
    {
      "path": "examples/requirements-flagged.txt",
      "findings": [
        {
          "line": 2,
          "directive": "-r",
          "target": "missing-base.txt",
          "reason": "points at a file that does not exist"
        },
        {
          "line": 3,
          "directive": "-c",
          "target": "missing-constraints.txt",
          "reason": "points at a file that does not exist"
        }
      ],
      "error": null
    }
  ],
  "checked": 1,
  "findings": 2
}
```

Exit codes: 0 when every include points at a file
that exists, 1 when any include is missing or a file
cannot be read, 2 for a usage error (a missing path,
a bad flag, or no requirements files found).

## Examples

A requirements file in a subfolder resolves its
includes against its own folder, not the folder you
ran the tool from — `sub/requirements.txt` saying
`-r ../base.txt` passes when `base.txt` sits next to
`sub/`, and `-r ../gone.txt` fails:

```sh
$ python3 src/requirements_include_checker.py /tmp/reqtest/sub/requirements.txt
FAIL /tmp/reqtest/sub/requirements.txt: line 2 -r '../gone.txt' points at a file that does not exist
Checked 1 file(s), 1 missing include(s) in 1 file(s).
```

Comments, attached forms, `=` forms, and options
that are not includes are handled —
`examples/requirements-edge.txt` has all of them,
and it passes:

```sh
$ python3 src/requirements_include_checker.py examples/requirements-edge.txt
OK — 1 file(s) checked, every include points at a file that exists.
```

A plain package file with no includes at all passes
too — there is nothing to break:

```sh
$ python3 src/requirements_include_checker.py /tmp/reqtest/plain.txt
OK — 1 file(s) checked, every include points at a file that exists.
```

Run every bundled example at once with `sh
examples/run-example.sh` — the output is saved in
[examples/sample-output.md](examples/sample-output.md).

## How it is tested

```sh
python3 tests/test_requirements_include_checker.py
```

The tests cover include parsing (`-r`, `--requirement`,
`--requirement=`, `-c`, `--constraint`,
`--constraint=`, attached `-rfile` / `-cfile`, a bare
`-r` / `-c` with no file after it, several includes on
one file in document order, an empty document), path
resolution (relative to the file's own directory, a
subfolder include with `..`, an absolute path that
exists and one that does not, a directory named like a
file failing, an existing include passing), skipping
(comment lines, a comment naming a missing file,
blank lines, package lines, `-e` editable installs,
`--index-url` and other options, inline comments
stripped, CRLF endings), the CLI (exit 0/1/2, folder
walking for several requirements files, nested
folders, `--no-recursive`, `--exclude`, `.git`
skipped, a direct file checked whatever its name,
duplicate paths checked once, `--json` output,
`--stdin`, bad flags, missing paths, empty folders,
`--version`, a non-UTF-8 file reported, input files
left unchanged, the tool run from another folder and
under a changed HOME), the bundled examples (sample
output compared byte-for-byte against a fresh run,
and the README-quoted outputs checked against it),
and hygiene checks (no placeholder text, no absolute
paths, no real secrets outside the tests and
examples, stdlib imports only, no network use in the
source, `.env` first in `.gitignore`, CI file runs
the test file, README names the neighbouring repos).

## Contributing

Small, focused improvements are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

This tool was written from scratch for this repo. The
idea of checking requirements includes is not new, and
the include forms follow pip's own documented
`-r` / `-c` options — but no existing tool does this
one job, checking that each include target exists on
disk, as a tested command-line gate with a CI exit
code, as the search above shows — and every line of
code here is original, built on nothing but Python's
standard library.
