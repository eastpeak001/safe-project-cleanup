# Contributing

Open an issue with Windows/Python versions, the command, expected behavior and a minimal
simulated reproduction. Remove usernames, project names, secrets and private report content.
Do not upload real logs or cleanup plans without reviewing their paths and metadata.

Keep pull requests focused. Explain what triggered the problem, how behavior changes,
and what verification passed or failed. Preserve existing approval and protection checks.
Changes affecting deletion, archive or restore need a meaningful isolated behavior test.

Run the commands in [AGENTS.md](AGENTS.md) on Windows. Tests require Git, and use newly
created directories. Never point a test at a real project. Generated outputs belong in
ignored `temp/`; release packages belong in ignored `release/`.

This is a Windows skill. Do not claim cross-platform mutation support without implementing
and validating the appropriate native file-identity and safety behavior.
