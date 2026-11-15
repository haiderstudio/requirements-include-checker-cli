== examples/requirements.txt ==
OK — 1 file(s) checked, every include points at a file that exists.

== examples/requirements-flagged.txt ==
FAIL examples/requirements-flagged.txt: line 2 -r 'missing-base.txt' points at a file that does not exist
FAIL examples/requirements-flagged.txt: line 3 -c 'missing-constraints.txt' points at a file that does not exist
Checked 1 file(s), 2 missing include(s) in 1 file(s).

== examples/requirements-edge.txt ==
OK — 1 file(s) checked, every include points at a file that exists.

== examples/ : the whole folder ==
FAIL examples/requirements-flagged.txt: line 2 -r 'missing-base.txt' points at a file that does not exist
FAIL examples/requirements-flagged.txt: line 3 -c 'missing-constraints.txt' points at a file that does not exist
Checked 4 file(s), 2 missing include(s) in 1 file(s).
