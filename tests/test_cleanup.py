"""Observable Windows behavior tests. All fixture mutations stay in a new sandbox.
Run with: py -3.11 -B -X utf8 test_cleanup.py --script <cleanup.py> --workspace <new-dir>
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import uuid
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("--script", required=True)
parser.add_argument("--workspace", required=True)
args = parser.parse_args()
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("cleanup", args.script)
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
WORK = c.checked(args.workspace, False)
if WORK.exists():
    raise SystemExit("tests require a new independent workspace; no existing directory is accepted")
WORK.mkdir(parents=True)
c.BASE = WORK / "control"


class Cases(unittest.TestCase):
    def setUp(self):
        self.root = WORK / self._testMethodName
        self.root.mkdir()
        self.reports = WORK / (self._testMethodName + "-reports")
        self.reports.mkdir()

    def out(self, label):
        return self.reports / (label + "-" + uuid.uuid4().hex[:8] + ".json")

    def file(self, rel, data=b"derived fixture"):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def plan(self, paths, action="delete", more=None, item_more=None):
        body = {"roots": [str(self.root)], "protected_paths": [], "items": [
            {"path": str(p), "action": action, "purpose": "derived", "resource_class": "A",
             "basis": "fixture generated object with known generator", "rebuild": "regenerate simulated object",
             "inactive_evidence": "fixture has no task/build/service"} for p in paths]}
        if more:
            body.update(more)
        if item_more:
            for item in body["items"]:
                item.update(item_more)
        return c.make_plan(body, self.out("plan"))

    def approval(self, plan):
        return {"plan_id": plan["plan_id"], "plan_sha256": c.digest(plan),
                "authorization_source": "user-authorized simulation only, independent test workspace",
                "items": [{"path": i["path"], "action": i["action"], "permanent_delete": True,
                           "retire_entire_version": i["purpose"] == "old-version",
                           "inactive_evidence": "fresh fixture inactivity verification"} for i in plan["items"]]}

    def run_plan(self, plan, approval=None):
        return c.execute(plan, self.out("execution"), True, approval or self.approval(plan))

    def versions(self):
        group = {"project": "fixture", "line": "main", "hardware": "virtual"}
        rows = []
        for n in (1, 2, 3, 4, 10):
            p = self.root / ("project_v" + str(n))
            p.mkdir()
            (p / "run.py").write_text("print('stable-fixture-ok')\n", encoding="utf-8")
            rows.append({"path": str(p), "identity": group, "current": n == 4,
                         "stable_evidence": "synthetic runnable fixture verified" if n == 3 else None,
                         "active": n == 10, "obsolete_implementation_authorized": True,
                         "inactive_evidence": "unused synthetic version", "local_history_reviewed": True,
                         "independent_retained_evidence": "retained run.py has no external imports"})
        return {"mode": "current-and-rollback", "identity": group,
                "reference_roots": [rows[2]["path"], rows[3]["path"]],
                "reference_scope_confirmed": True, "versions": rows}

    def git(self, p, *arguments):
        env = dict(os.environ, GIT_AUTHOR_NAME="Simulation", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                   GIT_COMMITTER_NAME="Simulation", GIT_COMMITTER_EMAIL="fixture@example.invalid",
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="NUL", GIT_OPTIONAL_LOCKS="0")
        return subprocess.run(["git", "-C", str(p), "-c", "core.hooksPath=NUL", *arguments],
                              env=env, check=True, capture_output=True).stdout.decode().strip()

    def synthetic_history(self, p):
        self.git(p, "init", "-b", "main")
        self.git(p, "add", ".")
        tree = self.git(p, "write-tree")
        commit = self.git(p, "commit-tree", tree, "-m", "isolated synthetic fixture")
        self.git(p, "update-ref", "refs/heads/main", commit)

    def test_dry_run_unchanged_and_approved_delete(self):
        self.file("source.py", b"print('preserved')")
        target = self.file("build/part.o").parent
        before = c.bounded_tree(self.root, hashes=True)
        plan = self.plan([target])
        self.assertEqual(len(plan["items"]), 1)
        preview = c.execute(plan, self.out("preview"))
        self.assertEqual(preview["items"][0]["status"], "DRY_RUN")
        self.assertEqual(c.bounded_tree(self.root, hashes=True)["digest"], before["digest"])
        result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "DELETED", result)
        self.assertFalse(target.exists())
        self.assertEqual((self.root / "source.py").read_bytes(), b"print('preserved')")
        self.assertIn("irreversible", result["reversibility"])

    def test_build_firmware_elf_source_and_logs_protected(self):
        for name in ("unique.bin", "firmware.elf", "code.c", "raw.log"):
            d = self.file("build-" + name.replace(".", "-") + "/" + name).parent
            plan = self.plan([d])
            self.assertFalse(plan["items"], name)
            self.assertTrue(plan["rejected"])
            self.assertTrue((d / name).exists())

    def test_secret_not_hashed_and_not_deleted(self):
        p = self.file("build/.env", b"dummy simulation content")
        snap = c.bounded_tree(p, hashes=True)
        self.assertNotIn("sha256", snap["entries"]["."])
        self.assertFalse(self.plan([p.parent])["items"])

    def test_untracked_ignored_and_uncommitted_git(self):
        self.file("main.py", b"print('base')\n")
        self.file(".gitignore", b"build/\n")
        self.synthetic_history(self.root)
        target = self.file("build/part.o").parent
        self.file("unknown.txt", b"untracked user notes")
        self.file("main.py", b"print('uncommitted')\n")
        plan = self.plan([target])
        self.assertEqual(len(plan["items"]), 1, plan)
        result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "DELETED", result)
        self.assertEqual((self.root / "main.py").read_bytes(), b"print('uncommitted')\n")
        self.assertTrue((self.root / "unknown.txt").exists())
        self.assertFalse(self.plan([self.root / "unknown.txt"])["items"])

    def test_ignored_protected_file_and_tracked_object(self):
        self.file("main.py")
        self.synthetic_history(self.root)
        tracked = self.file("tracked.o")
        self.git(self.root, "add", "tracked.o")
        self.assertFalse(self.plan([tracked])["items"])
        hidden = self.file("build/raw.log").parent
        self.assertFalse(self.plan([hidden])["items"])

    def test_nested_empty_repository_marker_is_protected(self):
        target = self.file("build/part.o").parent
        (target / ".git").mkdir()
        self.assertFalse(self.plan([target])["items"])

    def test_non_git_spaces_and_chinese(self):
        p = self.file("中文 工程/build objects/part.o").parent
        self.assertEqual(self.run_plan(self.plan([p]))["items"][0]["status"], "DELETED")

    def test_dependency_unknown_local_changes_or_offline_unique_preserved(self):
        p = self.file("dependency-cache/part.cache").parent
        self.assertFalse(self.plan([p], item_more={"resource_class": "B"})["items"])
        manifest = self.file("requirements.lock", b"fixture==1.0")
        evidence = {"manifests": [str(manifest)], "versions": "fixture 1.0 synthetic provider",
                    "download": "simulated generator available", "reference_scope": [str(self.root)],
                    "local_modifications": "none_verified", "offline_unique": True}
        self.assertFalse(self.plan([p], item_more={"resource_class": "B", "dependencies": evidence})["items"])
        evidence["offline_unique"] = False
        evidence["local_modifications"] = "unknown"
        self.assertFalse(self.plan([p], item_more={"resource_class": "B", "dependencies": evidence})["items"])
        evidence["local_modifications"] = "none_verified"
        plan = self.plan([p], item_more={"resource_class": "B", "dependencies": evidence})
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(self.run_plan(plan)["items"][0]["status"], "DELETED")
        self.assertTrue(manifest.exists())

    def test_active_or_unknown_not_plannable(self):
        p = self.file("build/part.o").parent
        plan = self.plan([p])
        body = {"roots": [str(self.root)], "items": [{**plan["items"][0], "inactive_evidence": None}]}
        self.assertFalse(c.make_plan(body, self.out("unknown"))["items"])

    def test_locked_target_skip(self):
        p = self.file("build/part.o")
        plan = self.plan([p.parent])
        h = c.NativeHandle(p)
        try:
            result = self.run_plan(plan)
            self.assertEqual(result["items"][0]["status"], "SKIPPED", result)
            self.assertTrue(p.exists())
        finally:
            h.close()

    def test_concurrent_cleanup_refused(self):
        p = self.file("build/part.o").parent
        plan = self.plan([p])
        held, done = threading.Event(), threading.Event()
        def holder():
            lock = c.ExecutionLock()
            held.set()
            done.wait(15)
            lock.close()
        thread = threading.Thread(target=holder)
        thread.start()
        self.assertTrue(held.wait(5))
        try:
            with self.assertRaises(c.Refused):
                self.run_plan(plan)
            self.assertTrue(p.exists())
        finally:
            done.set()
            thread.join(5)

    def test_traversal_prefix_roots_and_devices_refused(self):
        other = Path(str(self.root) + "-similar")
        other.mkdir()
        (other / "part.o").write_bytes(b"protected outside")
        self.assertFalse(self.plan([other])["items"])
        for p in (str(self.root) + r"\..\escape", "D:\\", r"\\server\share\x", r"\\?\D:\x",
                  str(self.root) + r"\NUL", str(self.root) + r"\part.o:stream"):
            with self.assertRaises(c.Refused, msg=p):
                c.checked(p, False)

    def test_real_junction_and_new_link_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "precious.log").write_bytes(b"keep")
        link = self.root / "junction"
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
        if r.returncode:
            self.skipTest("junction creation unavailable on this platform")
        report = c.scan([self.root], self.out("scan"), seconds=3, entries=100)
        self.assertTrue(any(x["path"] == str(link) and "reparse" in x["reason"] for x in report["skipped"]))
        self.assertFalse(self.plan([link])["items"])
        target = self.file("build/part.o").parent
        plan = self.plan([target])
        (target / "part.o").unlink()
        target.rmdir()
        subprocess.run(["cmd", "/c", "mklink", "/J", str(target), str(outside)], check=True, capture_output=True)
        with self.assertRaises(c.Refused):
            self.run_plan(plan)
        self.assertEqual((outside / "precious.log").read_bytes(), b"keep")

    def test_changed_target_and_new_protected_material_skip(self):
        p = self.file("build/part.o").parent
        plan = self.plan([p])
        self.file("build/new.log", b"preserve new evidence")
        result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "SKIPPED")
        self.assertTrue((p / "part.o").exists())
        self.assertTrue((p / "new.log").exists())

    def test_duplicate_and_nested_not_executed_twice(self):
        p = self.file("build/sub/part.o").parents[1]
        plan = self.plan([p, p, p / "sub"])
        self.assertEqual(len(plan["items"]), 1)
        self.assertEqual(len(plan["rejected"]), 2)
        self.assertEqual(self.run_plan(plan)["deleted_logical_bytes"], len(b"derived fixture"))

    def test_report_install_and_retained_parent_protected(self):
        self.file("build/part.o")
        plan = self.plan([self.root / "build"], more={"protected_paths": [str(self.root / "build" / "retained")]})
        self.assertFalse(plan["items"])
        with self.assertRaises(c.Refused):
            c.scan([self.root], self.root / "report.json")
        self.assertFalse(self.plan([Path(args.script).parent])["items"])

    def test_approval_not_plan_flag_or_apply_switch(self):
        p = self.file("build/part.o").parent
        plan = self.plan([p])
        plan["approved"] = True
        with self.assertRaises(c.Refused):
            c.execute(plan, self.out("no-approval"), True)
        receipt = self.approval(plan)
        receipt["items"][0]["permanent_delete"] = False
        with self.assertRaises(c.Refused):
            self.run_plan(plan, receipt)
        changed = copy.deepcopy(plan)
        changed["items"][0]["basis"] += " edited"
        with self.assertRaises(c.Refused):
            self.run_plan(changed, self.approval(plan))
        self.assertTrue(p.exists())

    def test_numeric_versions_default_keep_and_stable_runtime(self):
        manifest = self.versions()
        review = c.version_review(manifest)
        self.assertEqual([x["number"] for x in review["versions"]], [1, 2, 3, 4, 10])
        self.assertEqual([x["number"] for x in review["versions"] if x["disposition"] == "RETIRE_CANDIDATE"], [1, 2])
        self.file("project_v4/history/failure.log", b"old FAIL remains")
        keep = self.root / "project_v4"
        before = subprocess.run([sys.executable, "-B", str(keep / "run.py")], capture_output=True, check=True).stdout
        body = {"roots": [str(self.root)], "version_set": manifest,
                "items": [{"path": str(self.root / "project_v1"), "action": "delete", "purpose": "old-version",
                           "resource_class": "C", "basis": "same virtual project, obsolete duplicate implementation",
                           "inactive_evidence": "synthetic v1 inactive"}]}
        plan = c.make_plan(body, self.out("version-plan"))
        self.assertEqual(len(plan["items"]), 1, plan)
        result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "DELETED", result)
        after = subprocess.run([sys.executable, "-B", str(keep / "run.py")], capture_output=True, check=True).stdout
        self.assertEqual(before, after)
        self.assertEqual((keep / "history" / "failure.log").read_bytes(), b"old FAIL remains")

    def test_latest_unverified_and_missing_fallback(self):
        m = self.versions()
        m["versions"][2]["stable_evidence"] = None
        self.assertFalse(c.version_review(m)["stable_policy_valid"])
        m["mode"] = "latest-stable-only"
        m["single_version_authorized"] = True
        self.assertTrue(all(r["disposition"] == "KEEP" for r in c.version_review(m)["versions"]))

    def test_latest_stable_only_explicit_and_other_hardware_kept(self):
        m = self.versions()
        m["mode"] = "latest-stable-only"
        m["versions"][3]["stable_evidence"] = "simulated stable current verified"
        self.assertFalse(c.version_review(m)["stable_policy_valid"])
        m["single_version_authorized"] = True
        m["versions"][4]["identity"] = {**m["identity"], "hardware": "another-board"}
        r = c.version_review(m)
        self.assertEqual([x["number"] for x in r["versions"] if x["disposition"] == "RETIRE_CANDIDATE"], [1, 2, 3])
        self.assertEqual(r["versions"][-1]["disposition"], "KEEP")

    def test_unique_material_and_retained_reference_block_versions(self):
        m = self.versions()
        self.file("project_v1/raw.log", b"unique old FAIL")
        self.file("project_v4/ref.txt", b"../project_v2/run.py")
        r = c.version_review(m)
        self.assertEqual(r["versions"][0]["disposition"], "SKIP")
        self.assertEqual(r["versions"][1]["disposition"], "SKIP")
        saved = self.file("saved/raw.log", b"unique old FAIL")
        m["versions"][0]["preserved_files"] = {"raw.log": str(saved)}
        self.assertEqual(c.version_review(m)["versions"][0]["disposition"], "RETIRE_CANDIDATE")

    def test_unique_git_history_blocks_retirement(self):
        m = self.versions()
        self.synthetic_history(self.root / "project_v1")
        r = c.version_review(m)
        self.assertEqual(r["versions"][0]["disposition"], "SKIP")
        self.assertFalse(r["versions"][0]["git_history"]["retained"])

    def test_cache_approval_cannot_retire_entire_version(self):
        m = self.versions()
        body = {"roots": [str(self.root)], "version_set": m,
                "items": [{"path": str(self.root / "project_v1"), "action": "delete", "purpose": "old-version",
                           "resource_class": "C", "basis": "obsolete simulation", "inactive_evidence": "fixture unused"}]}
        plan = c.make_plan(body, self.out("version-plan"))
        receipt = self.approval(plan)
        receipt["items"][0]["retire_entire_version"] = False
        with self.assertRaises(c.Refused):
            self.run_plan(plan, receipt)

    def test_archive_verified_restore_no_overwrite(self):
        target = self.file("build/sub/part.o", b"deterministic archive bytes").parents[1]
        plan = self.plan([target], action="archive")
        result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "ARCHIVED_SOURCE_RETAINED", result)
        self.assertEqual(result["deleted_logical_bytes"], 0)
        self.assertGreater(result["retained_archive_bytes"], 0)
        archive = result["items"][0]["archive"]["path"]
        dest = self.root / "restored"
        restored = c.restore(archive, self.root, dest, self.out("restore"), True)
        self.assertEqual(restored["status"], "RESTORED_HASH_VERIFIED")
        self.assertEqual((dest / "sub" / "part.o").read_bytes(), b"deterministic archive bytes")
        with self.assertRaises(c.Refused):
            c.restore(archive, self.root, dest, self.out("again"), True)
        self.assertTrue(target.exists())

    def test_archive_no_space_or_verification_failure_keeps_original(self):
        target = self.file("build/part.o").parent
        plan = self.plan([target], action="archive-delete")
        self.assertFalse(plan["items"])
        plan = self.plan([target], action="archive")
        with patch.object(c, "verify_archive", side_effect=c.Refused("simulated verification failure")):
            result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "SKIPPED")
        self.assertTrue((target / "part.o").exists())
        plan = self.plan([target], action="archive")
        actual = shutil.disk_usage(self.root)
        with patch.object(c.shutil, "disk_usage", return_value=type(actual)(actual.total, actual.total, 0)):
            result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "SKIPPED")
        self.assertTrue((target / "part.o").exists())

    def test_archive_delete_requires_and_uses_restore_rehearsal(self):
        target = self.file("build/sub/part.o").parents[1]
        archive_result = self.run_plan(self.plan([target], action="archive"))
        archive = archive_result["items"][0]["archive"]["path"]
        proof_path = self.out("rehearsal")
        c.restore(archive, self.root, self.root / "rehearsed", proof_path, True)
        plan = self.plan([target], action="archive-delete", item_more={"restore_rehearsal": str(proof_path)})
        self.assertEqual(len(plan["items"]), 1, plan)
        result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "ARCHIVED_AND_DELETED", result)
        self.assertFalse(target.exists())
        self.assertTrue((self.root / "rehearsed" / "sub" / "part.o").exists())

    def test_same_bytes_and_time_replacement_is_refused(self):
        target = self.file("build/part.o")
        plan = self.plan([target.parent])
        stamp = target.stat().st_mtime_ns
        target.rename(self.root / "original-kept.o")
        target.write_bytes(b"derived fixture")
        os.utime(target, ns=(stamp, stamp))
        result = self.run_plan(plan)
        self.assertEqual(result["items"][0]["status"], "SKIPPED")
        self.assertTrue(target.exists())

    def test_duplicate_git_history_supported_unknown_untracked_still_kept(self):
        m = self.versions()
        old = self.root / "project_v1"
        self.synthetic_history(old)
        shutil.copytree(old / ".git", self.root / "project_v3" / ".git")
        r = c.version_review(m)
        self.assertEqual(r["versions"][0]["disposition"], "RETIRE_CANDIDATE", r)
        (old / "unfinished.py").write_text("print('unique unfinished work')", encoding="utf-8")
        self.assertEqual(c.version_review(m)["versions"][0]["disposition"], "SKIP")

    def test_git_filter_command_is_not_executed(self):
        self.file("main.py", b"print('base')\n")
        self.file(".gitattributes", b"main.py filter=probe\n")
        self.synthetic_history(self.root)
        marker = self.root / "unexpected-filter-ran.txt"
        command = '"' + sys.executable + '" -c "open(\'' + str(marker).replace("\\", "/") + '\',\'w\').write(\'unexpected\')"'
        self.git(self.root, "config", "filter.probe.clean", command)
        self.file("main.py", b"print('modified')\n")
        self.assertEqual(c.git_state(self.root)["state"], "checked_read_only")
        self.assertFalse(marker.exists())

    def test_corrupt_or_traversal_archive_not_restored(self):
        target = self.file("build/part.o").parent
        archive = self.run_plan(self.plan([target], action="archive"))["items"][0]["archive"]["path"]
        with zipfile.ZipFile(archive, "a") as z:
            z.writestr("data/../escape", b"unsafe")
        with self.assertRaises(c.Refused):
            c.restore(archive, self.root, self.root / "restored", self.out("restore"), True)
        self.assertFalse((self.root / "restored").exists())
        self.assertTrue(target.exists())

    def test_hardlink_and_ads_refused_for_mutation(self):
        target = self.file("build/part.o")
        os.link(target, self.root / "second.o")
        self.assertFalse(self.plan([target.parent])["items"])
        target = self.file("another/part.o")
        plan = self.plan([target.parent])
        with open(str(target) + ":hidden", "wb") as f:
            f.write(b"hidden data")
        self.assertEqual(self.run_plan(plan)["items"][0]["status"], "SKIPPED")
        self.assertTrue(target.exists())

    def test_bounded_scan_and_unique_candidate_totals(self):
        self.file("build/sub/part.o")
        r = c.scan([self.root, self.root / "build"], self.out("scan"), entries=100, seconds=3, depth=5)
        self.assertEqual(r["logical_bytes_observed"], len(b"derived fixture"))
        self.assertEqual(r["nonnested_candidate_logical_bytes"], len(b"derived fixture"))
        cut = c.scan([self.root], self.out("cut"), entries=1, seconds=3)
        self.assertFalse(cut["complete_within_declared_exclusions"])
        self.assertTrue(cut["continuation_roots"])

    def test_cli_scans_explicit_fixture_inside_delivery_base(self):
        self.file("build/part.o")
        output = self.out("cli-scan")
        subprocess.run([sys.executable, "-B", "-X", "utf8", args.script, "--workspace-root", str(WORK), "scan", "--root", str(self.root),
                        "--out", str(output), "--max-seconds", "3", "--max-entries", "100"], check=True, capture_output=True)
        report = c.load(output)
        self.assertGreater(report["entries_observed"], 0)
        self.assertEqual(report["logical_bytes_observed"], len(b"derived fixture"))

    def test_policy_scope_budget_and_revocation(self):
        target = self.file("build/part.o").parent
        plan = self.plan([target])
        policy = {"policy_id": "simulation", "status": "ACTIVE", "authorization_source": "user authorized test",
                  "roots": [str(self.root)], "resource_classes": ["A"], "purposes": ["derived"],
                  "actions": ["delete"], "permanent_delete": True, "max_bytes": 1000,
                  "idle_rule": "fixture never started", "revocation": "set REVOKED"}
        policy["status"] = "REVOKED"
        with self.assertRaises(c.Refused):
            c.execute(plan, self.out("revoked"), True, policy=policy)
        policy["status"] = "ACTIVE"
        policy["max_bytes"] = 1
        with self.assertRaises(c.Refused):
            c.execute(plan, self.out("budget"), True, policy=policy)
        policy["max_bytes"] = 1000
        self.assertEqual(c.execute(plan, self.out("policy"), True, policy=policy)["items"][0]["status"], "DELETED")


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.records = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.records.append({"test": test.id(), "status": "PASS"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.records.append({"test": test.id(), "status": "FAIL", "evidence": self._exc_info_to_string(err, test)})

    def addError(self, test, err):
        super().addError(test, err)
        self.records.append({"test": test.id(), "status": "ERROR", "evidence": self._exc_info_to_string(err, test)})

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.records.append({"test": test.id(), "status": "NOT_TESTED", "reason": reason})


started = time.monotonic()
suite = unittest.defaultTestLoader.loadTestsFromTestCase(Cases)
result = unittest.TextTestRunner(verbosity=2, resultclass=RecordedResult).run(suite)
c.write_new(WORK / "TEST_RESULTS.json", {"workspace": str(WORK), "script": str(Path(args.script)),
            "script_sha256": hashlib.sha256(Path(args.script).read_bytes()).hexdigest(), "platform": sys.platform,
            "tests_run": result.testsRun, "passed": sum(x["status"] == "PASS" for x in result.records),
            "failed": len(result.failures) + len(result.errors), "skipped": len(result.skipped),
            "elapsed_seconds": time.monotonic() - started, "cases": result.records,
            "not_tested": ["kernel/hostile concurrent writer races", "UNC/ReFS/FAT restore support (unsupported)",
                           "actual hardware/build/release acceptance", "official cache tool live cleaning"]})
print("REPORT=" + str(WORK / "TEST_RESULTS.json"))
sys.exit(0 if result.wasSuccessful() else 1)
