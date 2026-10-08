"""Build the small installable skill ZIP. Runtime outputs stay outside Git."""
import argparse
import hashlib
from pathlib import Path
import zipfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
skill = repo / 'skills' / 'safe-project-cleanup'
files = sorted(p for p in skill.rglob('*') if p.is_file())
if any(p.is_symlink() or any(part.startswith('.') or part == '__pycache__' for part in p.relative_to(skill).parts)
       or p.suffix in ('.pyc', '.pyo') for p in files):
    raise SystemExit('Unexpected generated/hidden file in skill; refusing package.')
if not (skill / 'SKILL.md').is_file() or (skill / 'LICENSE').read_bytes() != (repo / 'LICENSE').read_bytes():
    raise SystemExit('Missing entrypoint or inconsistent packaged license.')
args.out.mkdir(parents=True, exist_ok=True)
archive = args.out / 'safe-project-cleanup-v0.1.0.zip'
checksum = args.out / 'SHA256SUMS.txt'
if archive.exists() or checksum.exists():
    raise SystemExit('Release output exists; refusing overwrite.')
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as output:
    for path in files:
        info = zipfile.ZipInfo('safe-project-cleanup/' + path.relative_to(skill).as_posix(), (2026, 10, 8, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        output.writestr(info, path.read_bytes())
checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + '  ' + archive.name + '\n', encoding='ascii')
print('PACKAGE=' + str(archive))
