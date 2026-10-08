# safe-project-cleanup

**Let Codex inspect project storage first, then clean the exact approved items.**

[中文](README.md) · [Getting started](docs/getting-started.md) · [MIT license](LICENSE)

A Windows-first Codex skill for growing development projects: bounded read-only inventory,
evidence-based cache review, old-version retirement, exact approval receipts, and verified
archive/restore workflows. The skill instructions are in Chinese. The Python helper uses
only the standard library and does not require a memory plugin.

## Install

Ask Codex:

```text
Use $skill-installer to install this version:
https://github.com/eastpeak001/safe-project-cleanup/tree/v0.1.0/skills/safe-project-cleanup
```

Or download the release ZIP, verify `SHA256SUMS.txt`, and place its `safe-project-cleanup`
folder in your user-level `.agents/skills` directory. The bundled installer may use
`.codex/skills`; use the actual installed path. Inspect an existing installation before
updating it. If Codex does not discover the skill automatically, restart it.

Requirements: Windows local drives and Python 3.11+. Installed Git is needed for Git
repository evidence. No Python runtime dependencies.

## Start with inventory

```text
Use $safe-project-cleanup to inventory the confirmed current project read-only.
Confirm a separate report workspace, preferably on a non-system drive.
Limit scanning to 40 seconds, 60000 entries and depth 10. Report major usage,
protected material, truncation and unknowns. Produce candidates only; do not delete,
archive or rebuild real resources in this run.
```

Every helper command requires `--workspace-root <absolute-directory>` before the
subcommand. Reports must be inside that workspace; the workspace cannot be cleaned.
No drive letter or personal project layout is assumed.

| Capability | Behavior |
| --- | --- |
| Inventory | Explicit limits, declared exclusions, continuation roots, logical byte totals |
| Cache cleanup | Rebuild evidence; dependency version, source and local-change review |
| Old versions | Numeric sorting; current plus verified rollback by default |
| Authorization | Exact plan digest and items; real authority must be checked by the agent |
| Archive/restore | Content hashes, restore rehearsal, new destinations only |
| Results | Distinguish deleted logical bytes, archive storage and measured volume free space |

## Limits

Dry-run is the default. An apply flag or self-written receipt is not human authorization.
Sources, secrets, logs, unique releases, PCB/data and repository history stay protected.
Mutations reject reparse points, hardlinks, compressed/sparse/encrypted/offline files and
alternate data streams. File identity and locking checks reduce race exposure; they do
not prove project inactivity or eliminate every hostile/concurrent-writer race.

Deletion is irreversible. ZIP verification is separate from restore rehearsal. Restore
does not reproduce ACLs, ADS or every timestamp. The helper does not run rebuild commands,
download dependencies, validate hardware, or establish real-project acceptance.

Windows CI covers 34 behavioral scenarios and distribution/CLI integration. All tests
operate on isolated simulated projects. See [the protocol](skills/safe-project-cleanup/references/workflow.md)
and [contribution guide](CONTRIBUTING.md) for details.
