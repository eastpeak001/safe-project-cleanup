# safe-project-cleanup

Windows-first Codex skill for bounded project inventory and explicitly authorized cleanup.
Runtime: Windows, Python 3.11+, standard library; optional installed Git for repository evidence.
No hardware, flashing, network downloads, or rebuilds are performed by the cleanup helper.

Keep changes narrow. Preserve approval binding, protected materials, canonical path checks,
Win32 file-identity checks, archive verification, and restore rehearsal requirements.
Reports and tests must use new isolated directories. Never test deletion on real user projects.
Do not add private cleanup reports, machine paths, credentials, or generated test outputs to Git.
The installed personal skill is separate from this publication copy.

Verification from the repository root (PowerShell):

```powershell
$testRoot = Join-Path $PWD ('temp\behavior-' + [guid]::NewGuid().ToString('N'))
python -B -X utf8 tests/test_cleanup.py --script skills/safe-project-cleanup/scripts/cleanup.py --workspace $testRoot
$packageRoot = Join-Path $PWD ('temp\package-' + [guid]::NewGuid().ToString('N'))
python -B -X utf8 tools/package_release.py --out $packageRoot
$installRoot = Join-Path $PWD ('temp\distribution-' + [guid]::NewGuid().ToString('N'))
python -B -X utf8 tests/test_distribution.py --package (Join-Path $packageRoot 'safe-project-cleanup-v0.1.0.zip') --workspace $installRoot
```

Known limits: Windows local drives only; no UNC, hardlink/sparse/compressed/ADS mutation,
no ACL restoration, no general malicious-writer race guarantee, no automatic human-authority validation.
First release: v0.1.0. Record meaningful changes and rerun relevant verification before the next release.
