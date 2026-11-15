# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the requirements files you point it at, and it never rewrites a file and never changes anything. It writes nothing except the report on standard output (and usage errors on standard error). It never fetches a URL: a remote address named in an include is checked against the local disk, not opened.

It only checks that an include target exists on disk. It never installs a package, never runs pip, and never follows an include into another file.

If you find a case where the tool rewrites a file, installs anything, or reports a pass for a requirements file with a missing include, please open an issue describing the exact commands and input. Do not include any real secret in the report.
