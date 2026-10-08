"""Test a release installed from ZIP with isolated Windows CLI fixtures."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument('--package', type=Path, required=True)
parser.add_argument('--workspace', type=Path, required=True)
args = parser.parse_args()
if os.name != 'nt':
    raise SystemExit('Distribution tests require Windows.')
work = args.workspace
if not work.is_absolute() or work.exists():
    raise SystemExit('An absolute, new test workspace is required.')
work.mkdir(parents=True)
install = work / 'install'
with zipfile.ZipFile(args.package) as archive:
    names = archive.namelist()
    if any(not n.startswith('safe-project-cleanup/') or '..' in Path(n).parts or '\\' in n for n in names):
        raise SystemExit('Invalid package paths.')
    archive.extractall(install)
script = install / 'safe-project-cleanup' / 'scripts' / 'cleanup.py'
spec = importlib.util.spec_from_file_location('cleanup', script)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


class Distribution(unittest.TestCase):
    def setUp(self):
        self.case = work / self._testMethodName
        self.project = self.case / 'project'
        self.reports = self.case / 'reports'
        (self.project / 'src').mkdir(parents=True)
        (self.project / 'build').mkdir()
        self.source = self.project / 'src' / 'main.py'
        self.source.write_bytes(b'print("fixture")\n')
        self.object = self.project / 'build' / 'part.o'
        self.object.write_bytes(b'simulated build object')

    def cli(self, *arguments, workspace=None, ok=True):
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(script), '--workspace-root',
                                 str(workspace or self.reports), *map(str, arguments)], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def plan(self, action):
        path = self.case / 'spec.json'
        path.write_text(json.dumps({'roots': [str(self.project)], 'items': [{'path': str(self.object.parent),
            'action': action, 'purpose': 'derived', 'resource_class': 'A', 'basis': 'isolated generated fixture',
            'rebuild': 'regenerate the simulated byte string', 'inactive_evidence': 'fixture never started'}]}), encoding='utf-8')
        target = self.reports / 'plan.json'
        self.cli('plan', '--spec', path, '--out', target)
        plan = c.load(target)
        self.assertEqual(len(plan['items']), 1, plan)
        approval = self.case / 'approval.json'
        approval.write_text(json.dumps({'plan_id': plan['plan_id'], 'plan_sha256': c.digest(plan),
            'authorization_source': 'User-authorized isolated distribution test only', 'items': [{
                'path': str(self.object.parent), 'action': action, 'permanent_delete': True,
                'retire_entire_version': False, 'inactive_evidence': 'fixture never started'}]}), encoding='utf-8')
        return target, approval

    def test_package_members_and_checksum(self):
        repo = Path(__file__).resolve().parents[1]
        expected = {'safe-project-cleanup/' + p.relative_to(repo / 'skills' / 'safe-project-cleanup').as_posix()
                    for p in (repo / 'skills' / 'safe-project-cleanup').rglob('*') if p.is_file()}
        self.assertEqual(set(names), expected)
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(hashlib.sha256(args.package.read_bytes()).hexdigest(),
                         (args.package.parent / 'SHA256SUMS.txt').read_text().split()[0])
        with zipfile.ZipFile(args.package) as archive:
            for path in expected:
                content = archive.read(path)
                self.assertEqual(content, (repo / 'skills' / Path(path)).read_bytes())
                self.assertNotIn(str(Path.home()).encode('utf-8'), content)
        self.assertTrue((install / 'safe-project-cleanup' / 'LICENSE').is_file())

    def test_missing_workspace_is_refused(self):
        result = subprocess.run([sys.executable, '-B', str(script), 'scan', '--root', str(self.project),
                                 '--out', str(self.reports / 'inventory.json')], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.object.exists())
        self.assertFalse(self.reports.exists())

    def test_invalid_workspace_and_outside_report_refused(self):
        for base in (Path(self.project.anchor), c.HOME, script.parent.parent):
            self.cli('scan', '--root', self.project, '--out', self.reports / 'invalid.json', workspace=base, ok=False)
        self.cli('scan', '--root', self.project, '--out', self.case / 'outside.json', ok=False)
        self.assertTrue(self.object.exists())
        self.assertFalse((self.case / 'outside.json').exists())

    def test_installed_cli_scan_measures_involved_volume(self):
        report = self.reports / 'inventory.json'
        self.cli('scan', '--root', self.project, '--out', report, '--max-seconds', '3', '--max-entries', '100')
        data = c.load(report)
        self.assertGreater(data['entries_observed'], 0)
        self.assertEqual(set(data['volumes']), {self.project.anchor, self.reports.anchor})
        self.assertEqual(self.source.read_bytes(), b'print("fixture")\n')

    def test_installed_cli_dry_run_and_exact_delete(self):
        plan, approval = self.plan('delete')
        self.cli('execute', '--plan', plan, '--out', self.reports / 'preview.json')
        self.assertTrue(self.object.exists())
        self.cli('execute', '--plan', plan, '--approval', approval, '--apply', '--out', self.reports / 'execution.json')
        data = c.load(self.reports / 'execution.json')
        self.assertEqual(data['items'][0]['status'], 'DELETED', data)
        self.assertEqual(data['deleted_logical_bytes'], len(b'simulated build object'))
        self.assertFalse(self.object.parent.exists())
        self.assertEqual(self.source.read_bytes(), b'print("fixture")\n')

    def test_installed_cli_archive_verify_and_restore(self):
        plan, approval = self.plan('archive')
        self.cli('execute', '--plan', plan, '--approval', approval, '--apply', '--out', self.reports / 'archive.json')
        data = c.load(self.reports / 'archive.json')
        self.assertEqual(data['items'][0]['status'], 'ARCHIVED_SOURCE_RETAINED', data)
        archive = data['items'][0]['archive']['path']
        self.cli('verify-archive', '--archive', archive, '--out', self.reports / 'verify.json')
        dest = self.project / 'restored'
        self.cli('restore', '--archive', archive, '--root', self.project, '--dest', dest, '--out', self.reports / 'restore-preview.json')
        self.assertFalse(dest.exists())
        self.cli('restore', '--archive', archive, '--root', self.project, '--dest', dest, '--apply', '--out', self.reports / 'restore.json')
        self.assertEqual((dest / 'part.o').read_bytes(), self.object.read_bytes())
        self.assertTrue(self.object.exists())
        self.cli('restore', '--archive', archive, '--root', self.project, '--dest', dest, '--apply', '--out', self.reports / 'overwrite.json', ok=False)


result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Distribution))
(work / 'DISTRIBUTION_RESULTS.json').write_text(json.dumps({'tests_run': result.testsRun,
    'failed': len(result.failures) + len(result.errors), 'skipped': len(result.skipped)}, indent=2), encoding='utf-8')
sys.exit(0 if result.wasSuccessful() else 1)
