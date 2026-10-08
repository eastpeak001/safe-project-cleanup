#!/usr/bin/env python3
"""Windows-only, standard-library project inventory and approved-plan operations.

JSON is data. This program never runs rebuild commands or authenticates a human.
See ../references/workflow.md for the authorization boundary and supported paths.
"""
import argparse
import contextlib
import ctypes
from ctypes import wintypes as W
import hashlib
import io
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid
import zipfile
from collections import deque

BASE = None  # Configured explicitly by the CLI; library callers set this before operations.
HOME = Path(os.environ.get("USERPROFILE", str(Path.home())))
BUILTIN_PROTECTED = [HOME / ".codex" / p for p in
                     ("skills", "sessions", "memories", "worktrees", "attachments")]
BUILTIN_PROTECTED += [HOME / ".agents" / "skills", Path(__file__).resolve().parent.parent]
REPARSE = 0x400
SPECIAL = 0x200 | 0x800 | 0x1000 | 0x4000  # sparse, compressed, offline, encrypted
SOURCE_EXT = {".c", ".h", ".cpp", ".hpp", ".s", ".py", ".js", ".ts", ".tsx",
              ".jsx", ".rs", ".go", ".java", ".kt", ".cs", ".sh", ".ps1", ".bat",
              ".cmd", ".cmake", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
              ".md", ".txt", ".xml", ".gradle", ".properties"}
MATERIAL_EXT = {".bin", ".elf", ".map", ".apk", ".aab", ".hex", ".uf2", ".csv",
                ".tsv", ".log", ".jsonl", ".db", ".sqlite", ".png", ".jpg", ".jpeg",
                ".svg", ".webp", ".gif", ".mp4", ".wav", ".mp3", ".pdf", ".zip",
                ".7z", ".kicad_pcb", ".kicad_sch", ".sch", ".pcb", ".step", ".stl",
                ".onnx", ".pt", ".pth", ".gguf", ".safetensors", ".npy", ".npz"}
SECRET_EXT = {".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".crt", ".cer"}
HINTS = {"build": "A", "dist": "A", "__pycache__": "A", ".pytest_cache": "A",
         "temp": "A", "tmp": "A", "node_modules": "B", ".venv": "B", "venv": "B",
         ".gradle": "B", ".npm": "B", "pip": "B", "downloads": "B",
         "backup": "C", "archive": "C", "release": "C", "models": "C", "sdk": "C"}


class Refused(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def load(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def inside(path, root):
    return path == root or root in path.parents


def overlap(a, b):
    return inside(a, b) or inside(b, a)


def checked(path, exists=True):
    """Reject ambiguous Windows names and inspect every existing ancestor, no resolve-follow."""
    raw = str(path).replace("/", "\\")
    drive, tail = ntpath.splitdrive(raw)
    if not re.fullmatch(r"[A-Za-z]:", drive) or not tail.startswith("\\"):
        raise Refused("only absolute local drive paths are supported")
    parts = tail.split("\\")[1:]
    if any(p in (".", "..") or any(c in p for c in '*?:<>|"') or
           p.endswith((" ", ".")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", p)
           for p in parts if p):
        raise Refused("ambiguous, wildcard, device or traversal path")
    p = Path(ntpath.normpath(raw))
    if p == Path(p.anchor):
        raise Refused("drive roots are not operation targets")
    for node in reversed([p, *p.parents]):
        if os.path.lexists(node):
            s = os.lstat(node)
            if getattr(s, "st_file_attributes", 0) & REPARSE or stat.S_ISLNK(s.st_mode):
                raise Refused("reparse boundary: " + str(node))
            # Reject 8.3 aliases rather than granting a second spelling of a protected path.
            if ntpath.normcase(os.path.realpath(node)) != ntpath.normcase(str(node)):
                raise Refused("noncanonical path alias: " + str(node))
    if exists and not os.path.lexists(p):
        raise Refused("missing target: " + str(p))
    return p


def protected_file(rel):
    p = Path(rel)
    name = p.name.lower()
    if name == ".env" or name.startswith(".env.") or p.suffix.lower() in SECRET_EXT:
        return "secret"
    if any(x.lower() in (".git", ".svn", ".hg") for x in p.parts):
        return "git"
    if p.suffix.lower() in MATERIAL_EXT or any(x.lower() in
            ("data", "logs", "evidence", "hardware", "pcb", "assets", "freeze", "frozen") for x in p.parts):
        return "material"
    if (p.suffix.lower() in SOURCE_EXT or name in
            {"agents.md", "makefile", "cmakelists.txt", "sdkconfig", ".gitignore", ".gitmodules"} or
            name.endswith(".lock")):
        return "source/config"
    return None


def meta(s):
    return {"id": [s.st_dev, s.st_ino], "size": s.st_size if stat.S_ISREG(s.st_mode) else 0,
            "mtime_ns": s.st_mtime_ns, "directory": stat.S_ISDIR(s.st_mode),
            "attributes": getattr(s, "st_file_attributes", 0), "links": s.st_nlink}


def volumes(paths=()):
    """Measure only volumes used by the selected operation and report workspace."""
    anchors = {Path(p).anchor for p in paths if Path(p).anchor}
    if BASE is not None:
        anchors.add(BASE.anchor)
    result = {}
    for d in sorted(anchors):
        try:
            u = shutil.disk_usage(d)
            result[d] = {"total": u.total, "used": u.used, "free": u.free}
        except OSError as e:
            result[d] = {"error": type(e).__name__}
    return result


def write_new(path, obj):
    p = checked(path, False)
    p.parent.mkdir(parents=True, exist_ok=True)
    checked(p.parent)
    with open(p, "x", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def outside_output(out, roots, exclusions=()):
    p = checked(out, False)
    if any(inside(p, r) and not any(inside(p, e) for e in exclusions) for r in roots):
        raise Refused("report must be outside inventoried projects, or inside an explicitly excluded report tree")
    if p.exists():
        raise Refused("output already exists")
    return p


def bounded_tree(root, seconds=20, entries=10000, hashes=False, max_bytes=4 * 1024**3):
    root = checked(root)
    start = time.monotonic()
    queue = deque([root])
    records = {}
    total = 0
    while queue:
        if time.monotonic() - start > seconds or len(records) >= entries:
            raise Refused("snapshot limit reached; narrow the target")
        p = queue.popleft()
        s = os.lstat(p)
        m = meta(s)
        if m["attributes"] & (REPARSE | SPECIAL) or stat.S_ISLNK(s.st_mode):
            raise Refused("unsupported reparse/sparse/compressed/offline/encrypted entry")
        rel = str(p.relative_to(root)) if p != root else "."
        if not m["directory"]:
            if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
                raise Refused("nonregular file or hardlink is not supported for mutation")
            total += s.st_size
            if total > max_bytes:
                raise Refused("snapshot byte budget reached; narrow or explicitly raise the bound")
            if hashes and protected_file(rel if rel != "." else p.name) != "secret":
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    while chunk := f.read(1024 * 1024):
                        h.update(chunk)
                        if time.monotonic() - start > seconds:
                            raise Refused("snapshot time budget reached")
                if meta(os.lstat(p)) != m:
                    raise Refused("file changed during snapshot")
                m["sha256"] = h.hexdigest()
        else:
            with os.scandir(p) as it:
                for e in it:
                    queue.append(Path(e.path))
                    if len(records) + len(queue) > entries:
                        raise Refused("snapshot entry budget reached")
        records[rel] = m
    return {"entries": records, "logical_bytes": total, "digest": digest(records)}


def git_read(repo, args, timeout=5, deadline=None):
    if deadline is not None:
        timeout = min(timeout, deadline - time.monotonic())
        if timeout <= 0:
            raise Refused("Git time budget exhausted")
    began = time.monotonic()
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0",
               GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="NUL")
    base = ["git", "--no-pager", "--no-optional-locks", "-C", str(repo),
            "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "-c", "core.hooksPath=NUL", "-c", "submodule.recurse=false", "-c", "diff.external="]
    # Status may run clean filters. Discover names without invoking filters and override them.
    conf = subprocess.run(base + ["config", "--includes", "--name-only", "--get-regexp", r"^filter\..*\.(clean|smudge|process|required)$"],
                          env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=timeout)
    if conf.returncode not in (0, 1) or len(conf.stdout) > 131072:
        raise Refused("cannot safely inspect Git filter configuration")
    for key in conf.stdout.decode("utf-8", "replace").splitlines():
        base += ["-c", key + ("=false" if key.endswith(".required") else "=")]
    remaining = timeout - (time.monotonic() - began)
    if remaining <= 0:
        raise Refused("Git time budget exhausted")
    r = subprocess.run(base + args, env=env, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, timeout=remaining)
    if r.returncode or len(r.stdout) > 2 * 1024**2:
        raise Refused("Git check failed or exceeded output budget")
    return r.stdout.decode("utf-8", "replace")


def git_state(repo, deadline=None):
    deadline = deadline or time.monotonic() + 10
    try:
        status_text = git_read(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=normal", "--ignore-submodules=all"], deadline=deadline)
        tracked = git_read(repo, ["status", "--porcelain=v1", "-z", "--untracked-files=no", "--ignore-submodules=all"], deadline=deadline)
        wt = git_read(repo, ["worktree", "list", "--porcelain"], deadline=deadline)
        return {"state": "checked_read_only", "tracked_dirty": bool(tracked),
                "tracked_status_digest": digest(tracked), "status_digest": digest(status_text),
                "unknown_untracked": sum(x.startswith("??") for x in status_text.split("\0")),
                "worktrees": wt.splitlines(), "submodules_present": (repo / ".gitmodules").exists()}
    except (OSError, Refused, subprocess.TimeoutExpired) as e:
        return {"state": "unknown", "reason": type(e).__name__}


def project_for(p, roots):
    for parent in [p, *p.parents]:
        if any(inside(parent, r) for r in roots) and any((parent / x).exists() for x in
                (".git", "AGENTS.md", "package.json", "pyproject.toml", "CMakeLists.txt")):
            return parent
    return next((r for r in roots if inside(p, r)), p.parent)


def scan(roots, out, exclusions=(), seconds=40, entries=60000, depth=10, git_limit=8):
    roots = [checked(x) for x in roots]
    if any(not p.is_dir() for p in roots):
        raise Refused("scan roots must be directories")
    # Broad inventories exclude our delivery tree. A specifically requested test
    # project inside it must still be scannable; its report remains outside that project.
    delivery_exclusion = [] if any(inside(r, BASE) for r in roots) else [BASE]
    exclusions = [checked(x, False) for x in [*exclusions, *delivery_exclusion,
                  *BUILTIN_PROTECTED[:3], HOME / ".agents" / "skills", Path(__file__).resolve().parent.parent]]
    out = outside_output(out, roots, exclusions)
    roots = sorted(set(roots), key=lambda p: len(p.parts))
    roots = [p for i, p in enumerate(roots) if not any(inside(p, q) for q in roots[:i])]
    queue = deque((r, 0) for r in roots)
    start = time.monotonic()
    records, dirs, candidates, skipped, errors, frontier, repos = {}, {}, {}, [], [], [], set()
    count = 0
    unique_ids, duplicate_bytes, special_files = set(), 0, 0
    while queue and count < entries and time.monotonic() - start < seconds:
        p, level = queue.popleft()
        if any(inside(p, e) for e in exclusions) or "sources" in [s.lower() for s in p.parts]:
            skipped.append({"path": str(p), "reason": "explicit/default read-only exclusion"})
            continue
        try:
            s = os.lstat(p)
            count += 1
            m = meta(s)
            if m["attributes"] & REPARSE or stat.S_ISLNK(s.st_mode):
                skipped.append({"path": str(p), "reason": "reparse point; not followed"})
                continue
            if m["directory"]:
                dirs[p] = 0
                if (p / ".git").exists():
                    repos.add(p)
                hint = HINTS.get(p.name.lower())
                match = re.search(r"(?i)(?:^|[_-])v(\d+)(?:$|[_-])", p.name)
                if hint or match:
                    candidates[p] = {"path": str(p), "project": str(project_for(p, roots)),
                                     "class_hint": hint or "C", "resource": p.name,
                                     "version_number": int(match.group(1)) if match else None,
                                     "activity": "unknown", "state": "NEEDS_EVIDENCE",
                                     "protected_kinds": set(), "logical_bytes_observed": 0,
                                     "recovery": "unverified; identify reproducible rebuild/download or retained materials"}
                if level >= depth:
                    frontier.append(str(p))
                else:
                    with os.scandir(p) as it:
                        for e in it:
                            if count + len(queue) >= entries or time.monotonic() - start >= seconds:
                                frontier.append(str(p))  # restart this directory, do not sum overlapping passes
                                break
                            queue.append((Path(e.path), level + 1))
            elif stat.S_ISREG(s.st_mode):
                records[p] = m
                if m["attributes"] & SPECIAL:
                    special_files += 1
                key = tuple(m["id"])
                if key in unique_ids:
                    duplicate_bytes += m["size"]
                unique_ids.add(key)
        except OSError as e:
            errors.append({"path": str(p), "error": type(e).__name__})
    frontier += [str(p) for p, _ in queue]
    for p, m in records.items():
        for parent in p.parents:
            if parent in dirs:
                dirs[parent] += m["size"]
            if parent in candidates:
                candidates[parent]["logical_bytes_observed"] += m["size"]
                kind = protected_file(str(p.relative_to(parent)))
                if kind:
                    candidates[parent]["protected_kinds"].add(kind)
    complete = not frontier and not errors
    for p, c in candidates.items():
        c["protected_kinds"] = sorted(c["protected_kinds"])
        c["coverage_complete"] = complete and not any(inside(Path(x["path"]), p) for x in skipped)
        if c["protected_kinds"]:
            c["state"] = "PROTECTED_CONTENT_REVIEW_REQUIRED"
        c["basis"] = "name is a discovery hint only; reproducibility, ownership and inactivity not established"
        c["unknowns"] = ["source/recovery evidence", "current usage", "external references"]
    top = sorted(dirs.items(), key=lambda x: x[1], reverse=True)[:50]
    ordered = sorted(candidates.values(), key=lambda x: x["logical_bytes_observed"], reverse=True)
    antichain = []
    for c in sorted(ordered, key=lambda x: len(Path(x["path"]).parts)):
        if not any(inside(Path(c["path"]), Path(a["path"])) for a in antichain):
            antichain.append(c)
    git_reports = []
    for p in sorted(repos)[:git_limit]:
        if time.monotonic() >= start + seconds:
            break
        git_reports.append({"path": str(p), **git_state(p, deadline=start + seconds)})
    report = {"schema": 1, "mode": "read-only inventory", "roots": list(map(str, roots)),
              "exclusions": list(map(str, exclusions)), "limits": {"seconds": seconds, "entries": entries, "depth": depth},
              "elapsed_seconds": round(time.monotonic() - start, 3), "entries_observed": count,
              "complete_within_declared_exclusions": complete, "skipped": skipped, "errors": errors,
              "continuation_roots": sorted(set(frontier))[:200], "continuation_count": len(set(frontier)),
              "top_directories": [{"path": str(p), "logical_bytes_observed": n} for p, n in top],
              "candidates": ordered, "nonnested_candidate_logical_bytes": sum(x["logical_bytes_observed"] for x in antichain),
              "logical_bytes_observed": sum(x["size"] for x in records.values()),
              "hardlink_duplicate_logical_bytes": duplicate_bytes, "special_files_observed": special_files,
              "git": git_reports, "git_not_checked": list(map(str, sorted(repos)[len(git_reports):])),
              "mutation_ready_bytes": 0, "volumes": volumes(roots),
              "space_note": "logical size is not released disk space; truncated sizes are lower bounds; no data was deleted"}
    write_new(out, report)
    return report


def reference_check(target, roots, max_entries=5000, seconds=15):
    hits, skips = [], []
    count = 0
    start = time.monotonic()
    needles = {str(target).lower().replace("\\", "/"), target.name.lower()}
    for raw in roots:
        root = checked(raw)
        queue = deque([root])
        while queue:
            p = queue.popleft()
            count += 1
            if count > max_entries or time.monotonic() - start > seconds:
                return {"hits": hits, "complete": False, "scope": roots, "skipped": skips, "reason": "bounded search truncated"}
            try:
                s = os.lstat(p)
                if getattr(s, "st_file_attributes", 0) & REPARSE:
                    skips.append(str(p))
                elif p.is_dir():
                    if p.name in (".git", "node_modules", ".venv", "sources"):
                        continue
                    queue.extend(Path(e.path) for e in os.scandir(p))
                elif protected_file(p.name) != "secret" and p.suffix.lower() in SOURCE_EXT:
                    if s.st_size > 1024**2:
                        skips.append(str(p))
                        continue
                    text = p.read_text(encoding="utf-8", errors="replace").lower().replace("\\", "/")
                    # Record locations, never matching text (which might contain private configuration).
                    for i, line in enumerate(text.splitlines(), 1):
                        if any(n in line for n in needles):
                            hits.append({"file": str(p), "line": i})
            except OSError:
                skips.append(str(p))
    return {"hits": hits, "complete": not skips, "scope": roots, "skipped": skips,
            "uncovered": "binary/generated references and any directories outside the declared scope"}


def histories_retained(old, kept):
    if not (old / ".git").exists():
        return True, "non-Git copy"
    if not (old / ".git").is_dir() or (old / ".gitmodules").exists():
        return False, "shared Git metadata/submodules require native management"
    state = git_state(old)
    if state.get("state") != "checked_read_only" or state.get("tracked_dirty"):
        return False, "Git state unknown or uncommitted tracked work"
    try:
        common = Path(git_read(old, ["rev-parse", "--path-format=absolute", "--git-common-dir"]).strip())
        if common != old / ".git" or len(state["worktrees"]) > 4:
            return False, "shared Git history/worktrees"
        refs = set(git_read(old, ["for-each-ref", "--format=%(refname) %(objectname)"]).splitlines())
        commits = set(git_read(old, ["rev-list", "--all", "--reflog"]).splitlines())
        # Detached HEAD must be represented in the retained graph too.
        commits.add(git_read(old, ["rev-parse", "HEAD"]).strip())
        saved_refs, saved_commits = set(), set()
        for k in kept:
            if (k / ".git").exists():
                saved_refs.update(git_read(k, ["for-each-ref", "--format=%(refname) %(objectname)"]).splitlines())
                saved_commits.update(git_read(k, ["rev-list", "--all", "--reflog"]).splitlines())
                saved_commits.add(git_read(k, ["rev-parse", "HEAD"]).strip())
        return refs <= saved_refs and commits <= saved_commits, "all refs and reachable/reflog commits compared with retained repositories; dangling objects not proven disposable"
    except (OSError, Refused, subprocess.TimeoutExpired):
        return False, "Git history comparison incomplete"


def version_review(manifest):
    mode = manifest.get("mode", "current-and-rollback")
    if mode not in ("current-and-rollback", "latest-stable-only"):
        raise Refused("unknown version mode")
    rows = manifest["versions"]
    if len({str(checked(r["path"])) for r in rows}) != len(rows):
        raise Refused("duplicate version path")
    for r in rows:
        r["path"] = str(checked(r["path"]))
        match = re.search(r"(?i)(?:^|[_-])v(\d+)(?:$|[_-])", Path(r["path"]).name)
        if not match:
            raise Refused("numeric version identity missing")
        r["number"] = int(match.group(1))
    rows.sort(key=lambda r: r["number"])
    group = manifest["identity"]
    main = [r for r in rows if r.get("identity") == group]
    current = [r for r in main if r.get("current")]
    stable = [r for r in main if r.get("stable_evidence")]
    keep = {r["path"] for r in rows if r.get("active") or r.get("frozen") or r.get("keep") or r.get("identity") != group}
    valid = len(current) == 1
    if mode == "current-and-rollback":
        fallback = [r for r in stable if not r.get("current")]
        valid &= bool(fallback)
        if current:
            keep.add(current[0]["path"])
        if fallback:
            keep.add(max(fallback, key=lambda r: r["number"])["path"])
    else:
        valid &= bool(manifest.get("single_version_authorized")) and bool(stable)
        if stable:
            latest = max(stable, key=lambda r: r["number"])
            keep.add(latest["path"])
            valid &= bool(current) and latest["path"] == current[0]["path"]
        if current:
            keep.add(current[0]["path"])
    if not valid:
        keep.update(r["path"] for r in rows)
    kept_snapshots = {k: bounded_tree(k, hashes=True) for k in keep}
    reviewed = []
    for row in rows:
        p = Path(row["path"])
        result = {**row, "disposition": "KEEP", "blockers": [], "references": None,
                  "difference_categories": {}, "recovery": "retained copy or irreversible retirement; choose explicitly"}
        snap = bounded_tree(p, hashes=True)
        result["logical_bytes"] = snap["logical_bytes"]
        if str(p) not in keep and valid:
            blockers = result["blockers"]
            if any(Path(rel).name.lower() in (".hg", ".svn") for rel in snap["entries"]):
                blockers.append("non-Git repository history requires its native manager")
            if not row.get("inactive_evidence") or not row.get("independent_retained_evidence"):
                blockers.append("usage/retained-version independence not verified")
            ref = reference_check(p, manifest.get("reference_roots", []))
            result["references"] = ref
            if ref["hits"] or not ref["complete"] or not manifest.get("reference_scope_confirmed") or not ref["scope"]:
                blockers.append("references present or declared scope not confirmed/complete")
            untracked = set()
            if (p / ".git").exists():
                try:
                    untracked = set(git_read(p, ["ls-files", "--others", "--exclude-standard", "-z"]).split("\0"))
                except (OSError, Refused, subprocess.TimeoutExpired):
                    blockers.append("untracked Git contents not checked")
            for rel, m in snap["entries"].items():
                if m["directory"] or protected_file(rel) == "git":
                    continue
                kind = protected_file(rel) or "unknown file"
                result["difference_categories"][kind] = result["difference_categories"].get(kind, 0) + 1
                if kind == "secret":
                    blockers.append("secret/signing material requires separate manual retention")
                    continue
                copies = [s["entries"].get(rel, {}) for s in kept_snapshots.values()]
                preserved = row.get("preserved_files", {}).get(rel)
                if preserved:
                    pp = checked(preserved)
                    if inside(pp, p):
                        blockers.append("retention location is inside retired version")
                    else:
                        copies.append(bounded_tree(pp, hashes=True)["entries"]["."])
                if not any(c.get("sha256") == m.get("sha256") and c.get("sha256") for c in copies):
                    if rel.replace("\\", "/") in untracked or kind != "source/config" or not row.get("obsolete_implementation_authorized"):
                        blockers.append("unique material not retained: " + rel)
            nested = [r for r in snap["entries"] if Path(r).name == ".git" and r != ".git"]
            history_ok, reason = histories_retained(p, [Path(k) for k in keep])
            result["git_history"] = {"retained": history_ok, "basis": reason}
            # An explicit local-history review is required: rev-list cannot prove dangling objects unimportant.
            if not history_ok or nested or ((p / ".git").exists() and not row.get("local_history_reviewed")):
                blockers.append("unique/unknown/nested/shared Git history")
            result["disposition"] = "RETIRE_CANDIDATE" if not blockers else "SKIP"
        elif not valid:
            result["blockers"].append("stable fallback/latest-stable-only authorization insufficient")
        reviewed.append(result)
    return {"mode": mode, "identity": group, "keep_paths": sorted(keep), "versions": reviewed,
            "stable_policy_valid": bool(valid), "scope_note": "declared reference scope only; no whole-machine dependency claim"}


def guard_target(p, roots, protections):
    p = checked(p)
    if p == HOME or inside(HOME, p) or not any(p != r and inside(p, r) for r in roots):
        raise Refused("target is not a strict child of an allowed root, or contains the user home")
    if any(overlap(p, q) for q in protections):
        raise Refused("target overlaps a protected/retained/installation/report path")
    if any(x.lower() == "sources" for x in p.parts) or inside(p, HOME / ".codex"):
        raise Refused("synchronized sources or Codex-managed data require their native manager")
    return p


def dependency_evidence(item):
    if item.get("resource_class") != "B":
        return
    e = item.get("dependencies", {})
    if not e.get("manifests") or not e.get("versions") or not e.get("download") or not e.get("reference_scope") or (
            e.get("local_modifications") != "none_verified" or e.get("offline_unique") is not False):
        raise Refused("dependency cache provenance, versions, download, local changes, references or offline uniqueness not verified")
    for path in e["manifests"]:
        p = checked(path)
        if not p.is_file() or protected_file(p.name) == "secret":
            raise Refused("invalid dependency manifest")


def make_plan(spec, out):
    roots = [checked(p) for p in spec["roots"]]
    protections = [checked(p, False) for p in [*spec.get("protected_paths", []), *BUILTIN_PROTECTED]]
    out = outside_output(out, roots, protections)
    protections.append(out.parent)
    vr = version_review(spec["version_set"]) if spec.get("version_set") else None
    if vr:
        protections.extend(Path(p) for p in vr["keep_paths"])
        for row in spec["version_set"]["versions"]:
            protections.extend(checked(p) for p in row.get("preserved_files", {}).values())
    plan = {"schema": 1, "plan_id": uuid.uuid4().hex, "roots": list(map(str, roots)),
            "protected_paths": list(map(str, protections)), "items": [], "rejected": [],
            "version_review": vr, "version_manifest": spec.get("version_set"),
            "authorization": "NONE; creating a plan or setting approved is not human authorization",
            "volumes_before": volumes(roots), "max_bytes": spec.get("max_bytes", 4 * 1024**3)}
    paths = []
    for raw in spec.get("items", []):
        try:
            p = guard_target(Path(raw["path"]), roots, protections)
            if any(overlap(p, q) for q in paths):
                raise Refused("duplicate or nested candidate")
            if raw.get("action") not in ("delete", "archive", "archive-delete") or raw.get("resource_class") not in ("A", "B", "C"):
                raise Refused("unknown action/class")
            if not raw.get("basis") or not raw.get("inactive_evidence"):
                raise Refused("basis and observed inactivity evidence are required")
            if raw.get("exclusions"):
                raise Refused("select separate leaf targets; a whole-tree operation cannot contain excluded materials")
            purpose = raw.get("purpose")
            dependency_evidence(raw)
            if purpose == "old-version":
                if not vr or not any(r["path"] == str(p) and r["disposition"] == "RETIRE_CANDIDATE" for r in vr["versions"]):
                    raise Refused("version retirement evidence insufficient")
            elif purpose != "derived" or raw["resource_class"] == "C" or not raw.get("rebuild"):
                raise Refused("derived resources require a specific reproducible rebuild/download method")
            snap = bounded_tree(p, hashes=True, max_bytes=plan["max_bytes"])
            if raw["action"] == "archive-delete":
                rehearsal = checked(raw.get("restore_rehearsal", ""))
                verify_rehearsal(rehearsal, snap)
                proof = load(rehearsal)
                protections.extend([rehearsal, checked(proof["verified_archive"]), checked(proof["destination"])])
            for rel, m in snap["entries"].items():
                if Path(rel).name.lower() in (".git", ".hg", ".svn") and purpose != "old-version":
                    raise Refused("nested repository metadata is not a build cache")
                if m["directory"]:
                    continue
                kind = protected_file(rel if rel != "." else p.name)
                if kind == "secret" or (kind and purpose != "old-version" and rel not in raw.get("rebuildable_files", [])):
                    raise Refused("protected file inside target: " + rel)
                if kind == "git" and purpose != "old-version":
                    raise Refused("Git metadata cannot be treated as a build cache")
            project = project_for(p.parent, roots)
            baseline = git_state(project) if (project / ".git").exists() else {"state": "non-Git"}
            if baseline["state"] == "unknown":
                raise Refused("unknown Git state")
            if purpose != "old-version" and (project / ".git").exists():
                if git_read(project, ["ls-files", "--", str(p)]).strip():
                    raise Refused("tracked content is not eligible for derived-tree deletion")
            plan["items"].append({**raw, "path": str(p), "project": str(project), "snapshot": snap,
                                  "git_baseline": baseline,
                                  "recovery": raw.get("rebuild") if purpose == "derived" else "irreversible unless an archive is verified"})
            paths.append(p)
        except (OSError, Refused, subprocess.TimeoutExpired, KeyError) as e:
            plan["rejected"].append({"path": raw.get("path"), "reason": str(e) if isinstance(e, Refused) else type(e).__name__})
    if sum(i["snapshot"]["logical_bytes"] for i in plan["items"]) > plan["max_bytes"]:
        raise Refused("aggregate plan byte budget exceeded")
    write_new(out, plan)
    return plan


# Win32 handles pin ancestors and selected objects against replacement. Files deny
# sharing; directories deny deletion. Directory children may still be added by an
# unrelated process; they are never traversed for deletion and cause a recorded failure.
if os.name == "nt":
    K = ctypes.WinDLL("kernel32", use_last_error=True)
    K.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, W.LPVOID, W.DWORD, W.DWORD, W.HANDLE]
    K.CreateFileW.restype = W.HANDLE
    K.CloseHandle.argtypes = [W.HANDLE]
    K.SetFileInformationByHandle.argtypes = [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD]
    K.GetFileInformationByHandle.argtypes = [W.HANDLE, W.LPVOID]
    K.DuplicateHandle.argtypes = [W.HANDLE, W.HANDLE, W.HANDLE, ctypes.POINTER(W.HANDLE), W.DWORD, W.BOOL, W.DWORD]
    K.GetCurrentProcess.restype = W.HANDLE

    class FileInfo(ctypes.Structure):
        _fields_ = [("attrs", W.DWORD), ("creation", W.FILETIME), ("access", W.FILETIME),
                    ("write", W.FILETIME), ("volume", W.DWORD), ("size_high", W.DWORD),
                    ("size_low", W.DWORD), ("links", W.DWORD), ("id_high", W.DWORD), ("id_low", W.DWORD)]

    class StreamInfo(ctypes.Structure):
        _fields_ = [("size", ctypes.c_longlong), ("name", W.WCHAR * 296)]

    K.FindFirstStreamW.argtypes = [W.LPCWSTR, ctypes.c_int, W.LPVOID, W.DWORD]
    K.FindFirstStreamW.restype = W.HANDLE
    K.FindNextStreamW.argtypes = [W.HANDLE, W.LPVOID]
    K.FindClose.argtypes = [W.HANDLE]
    K.CreateMutexW.argtypes = [W.LPVOID, W.BOOL, W.LPCWSTR]
    K.CreateMutexW.restype = W.HANDLE
    K.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    K.ReleaseMutex.argtypes = [W.HANDLE]


class ExecutionLock:
    """No filesystem side effects. Coordinate this helper in the current Windows session."""
    def __init__(self):
        self.h = K.CreateMutexW(None, False, "Local\\CodexSafeProjectCleanup-v1")
        if not self.h:
            raise Refused("cannot create cleanup mutex")
        result = K.WaitForSingleObject(self.h, 0)
        if result != 0:
            if result == 0x80:
                K.ReleaseMutex(self.h)
            K.CloseHandle(self.h)
            self.h = None
            raise Refused("concurrent or abandoned cleanup lock; inspect, do not force retry")

    def close(self):
        if self.h is not None:
            K.ReleaseMutex(self.h)
            K.CloseHandle(self.h)
            self.h = None


class NativeHandle:
    def __init__(self, path, directory=False, delete=False):
        if os.name != "nt":
            raise Refused("mutations require Windows/Win32 handles")
        checked(path)
        access = 0x80 if directory else 0x80000000
        if delete:
            access |= 0x10000
        self.h = K.CreateFileW(str(path), access, 3 if directory else 0, None, 3, 0x02200000, None)
        if self.h == ctypes.c_void_p(-1).value:
            raise Refused("locked or inaccessible object: " + str(path))
        self.path, self.directory = Path(path), directory
        try:
            info = self.info()
            if info.attrs & (REPARSE | SPECIAL):
                raise Refused("new reparse/unsupported entry")
            if not directory:
                stream = StreamInfo()
                handle = K.FindFirstStreamW(str(path), 0, ctypes.byref(stream), 0)
                if handle == ctypes.c_void_p(-1).value:
                    raise Refused("cannot inspect NTFS stream information")
                try:
                    while True:
                        if stream.name != "::$DATA":
                            raise Refused("alternate data stream is not supported")
                        if not K.FindNextStreamW(handle, ctypes.byref(stream)):
                            if ctypes.get_last_error() != 38:
                                raise Refused("stream enumeration incomplete")
                            break
                finally:
                    K.FindClose(handle)
        except Exception:
            self.close()
            raise

    def info(self):
        i = FileInfo()
        if not K.GetFileInformationByHandle(self.h, ctypes.byref(i)):
            raise ctypes.WinError(ctypes.get_last_error())
        return i

    def reader(self):
        import msvcrt
        dup = W.HANDLE()
        proc = K.GetCurrentProcess()
        if not K.DuplicateHandle(proc, self.h, proc, ctypes.byref(dup), 0, False, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        fd = msvcrt.open_osfhandle(dup.value, os.O_RDONLY | os.O_BINARY)
        f = os.fdopen(fd, "rb")
        f.seek(0)
        return f

    def verify(self, m):
        i = self.info()
        ino = (i.id_high << 32) | i.id_low
        ns = (((i.write.dwHighDateTime << 32) | i.write.dwLowDateTime) - 116444736000000000) * 100
        if ino != m["id"][1] or i.attrs != m["attributes"] or bool(i.attrs & 16) != m["directory"]:
            raise Refused("object identity/type/attributes changed")
        if not self.directory:
            if i.links != 1 or ns != m["mtime_ns"] or ((i.size_high << 32) | i.size_low) != m["size"]:
                raise Refused("file identity changed")
            with self.reader() as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != m.get("sha256"):
                    raise Refused("file content changed")

    def delete(self):
        flag = W.BOOL(True)
        if not K.SetFileInformationByHandle(self.h, 4, ctypes.byref(flag), ctypes.sizeof(flag)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.h is not None:
            K.CloseHandle(self.h)
            self.h = None


@contextlib.contextmanager
def pin_ancestors(path):
    handles = []
    try:
        for p in reversed(path.parents):
            if p == Path(p.anchor):
                continue
            handles.append(NativeHandle(p, directory=True))
        yield
    finally:
        for h in reversed(handles):
            h.close()


@contextlib.contextmanager
def pinned_tree(path, snapshot, delete=False):
    handles = {}
    with pin_ancestors(path):
        try:
            for rel, m in snapshot["entries"].items():
                p = path if rel == "." else path / rel
                handles[rel] = NativeHandle(p, m["directory"], delete)
                handles[rel].verify(m)
            # Enumerate names only, through pinned directories; new entries are not eligible.
            for rel, m in snapshot["entries"].items():
                if m["directory"]:
                    p = path if rel == "." else path / rel
                    expected = {Path(r).name for r in snapshot["entries"] if r != "." and
                                (str(Path(r).parent) if str(Path(r).parent) != "." else ".") == rel}
                    actual = {e.name for e in os.scandir(p)}
                    if actual != expected:
                        raise Refused("directory membership changed")
            yield handles
        finally:
            for h in reversed(list(handles.values())):
                h.close()


def archive_tree(path, snap, handles, dest):
    dest = checked(dest, False)
    if shutil.disk_usage(dest.parent).free < snap["logical_bytes"] + 1024**2:
        raise Refused("insufficient archive space; original retained")
    manifest = {"schema": 1, "source": str(path), "entries": snap["entries"],
                "logical_bytes": snap["logical_bytes"], "restore": "verified backup restore to a new path"}
    with zipfile.ZipFile(dest, "x", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("cleanup-manifest.json", json.dumps(manifest, ensure_ascii=False))
        for rel, m in snap["entries"].items():
            name = "data/" + (path.name if rel == "." else rel.replace("\\", "/"))
            if m["directory"]:
                if rel != ".":
                    z.writestr(name + "/", b"")
            else:
                with handles[rel].reader() as f, z.open(name, "w", force_zip64=True) as w:
                    shutil.copyfileobj(f, w, 1024**2)
    check = verify_archive(dest)
    if check["logical_bytes"] != snap["logical_bytes"]:
        raise Refused("archive verification failed; original retained")
    return {"path": str(dest), "retained_bytes": dest.stat().st_size,
            "verified": True, "restore_method": "restore --archive ... --root ... --dest new-path"}


def inspect_archive(z):
    names = z.namelist()
    if len(names) != len(set(n.lower() for n in names)) or len(names) > 10001:
        raise Refused("archive has duplicate names or exceeds entry budget")
    if z.getinfo("cleanup-manifest.json").file_size > 16 * 1024**2:
        raise Refused("archive manifest exceeds size bound")
    manifest = json.loads(z.read("cleanup-manifest.json"))
    if manifest.get("schema") != 1 or not isinstance(manifest.get("entries"), dict) or len(manifest["entries"]) > 10000:
        raise Refused("unsupported archive manifest")
    expected = {"cleanup-manifest.json"}
    total = 0
    for rel, m in manifest["entries"].items():
        if rel == "." and m["directory"]:
            continue
        parts = rel.replace("\\", "/").split("/")
        if rel != "." and any(p in ("", ".", "..") or ":" in p for p in parts):
            raise Refused("archive path traversal")
        name = "data/" + (Path(manifest["source"]).name if rel == "." else "/".join(parts))
        if m["directory"]:
            expected.add(name + "/")
            continue
        expected.add(name)
        zi = z.getinfo(name)
        if (zi.external_attr >> 16) & 0o170000 == 0o120000 or zi.file_size != m["size"]:
            raise Refused("archive symlink/size mismatch")
        total += zi.file_size
        if total > 4 * 1024**3:
            raise Refused("restore byte budget exceeded")
        with z.open(name) as f:
            if hashlib.file_digest(f, "sha256").hexdigest() != m.get("sha256"):
                raise Refused("archive content hash mismatch")
    if set(names) != expected or total != manifest["logical_bytes"]:
        raise Refused("archive contains unmanifested data")
    return manifest


def verify_archive(path):
    h = NativeHandle(checked(path))
    try:
        with h.reader() as f, zipfile.ZipFile(f) as z:
            return inspect_archive(z)
    finally:
        h.close()


def restore(archive, root, dest, out, apply=False):
    root, dest = checked(root), checked(dest, False)
    guard_target_for_restore = not inside(dest, root) or dest == root or any(overlap(dest, p) for p in BUILTIN_PROTECTED if p != BASE)
    if guard_target_for_restore or os.path.lexists(dest):
        raise Refused("restore destination must be a new allowed child; existing destinations never overwritten")
    out = outside_output(out, [root], [BASE])
    original = verify_archive(archive)
    report = {"mode": "restore", "apply": apply, "destination": str(dest), "verified_archive": str(archive),
              "logical_bytes": original["logical_bytes"], "volumes_before": volumes([root, dest, archive]), "status": "DRY_RUN"}
    report["source_snapshot_digest"] = digest(original["entries"])
    if apply:
        if not original["entries"]["."]["directory"]:
            raise Refused("single-file archives can be verified but this helper restores directory trees only")
        if shutil.disk_usage(root).free < original["logical_bytes"] + 1024**2:
            raise Refused("insufficient restore space")
        # A fresh private directory, held against replacement, with exclusive file creation.
        stage = dest.parent / (dest.name + ".restore-" + uuid.uuid4().hex)
        with pin_ancestors(stage):
            stage.mkdir()
            holders = [NativeHandle(stage, directory=True)]
            try:
                h = NativeHandle(checked(archive))
                try:
                    with h.reader() as f, zipfile.ZipFile(f) as z:
                        manifest = inspect_archive(z)
                        if digest(manifest) != digest(original):
                            raise Refused("archive changed between checks")
                        for rel, m in sorted(manifest["entries"].items(), key=lambda x: len(Path(x[0]).parts)):
                            if rel == ".":
                                continue
                            p = checked(stage / rel, False)
                            if not inside(p, stage):
                                raise Refused("restore escaped staging path")
                            if m["directory"]:
                                p.mkdir()
                                holders.append(NativeHandle(p, directory=True))
                            else:
                                with z.open("data/" + rel.replace("\\", "/")) as r, open(p, "xb") as w:
                                    shutil.copyfileobj(r, w, 1024**2)
                        recovered = bounded_tree(stage, hashes=True)
                        if {r: m.get("sha256") for r, m in recovered["entries"].items() if not m["directory"]} != {
                                r: m.get("sha256") for r, m in manifest["entries"].items() if not m["directory"]}:
                            raise Refused("restore verification failed")
                finally:
                    h.close()
            finally:
                for h in reversed(holders):
                    h.close()
            checked(stage)
            checked(dest, False)
            if os.path.lexists(dest):
                raise Refused("restore destination appeared; stage retained")
            os.rename(stage, dest)  # Windows rename does not replace an existing directory.
        report["status"] = "RESTORED_HASH_VERIFIED"
    report["volumes_after"] = volumes([root, dest, archive])
    write_new(out, report)
    return report


def verify_rehearsal(path, snapshot):
    proof = load(path)
    if proof.get("status") != "RESTORED_HASH_VERIFIED" or proof.get("source_snapshot_digest") != snapshot["digest"]:
        raise Refused("archive-delete requires a matching successful restore rehearsal")
    original = verify_archive(checked(proof["verified_archive"]))
    if digest(original["entries"]) != snapshot["digest"]:
        raise Refused("rehearsal archive no longer matches source")
    recovered = bounded_tree(checked(proof["destination"]), hashes=True)
    expected = {r: m.get("sha256") for r, m in snapshot["entries"].items() if not m["directory"]}
    actual = {r: m.get("sha256") for r, m in recovered["entries"].items() if not m["directory"]}
    if expected != actual:
        raise Refused("rehearsal restored data no longer matches")


def authorize(plan, approval, policy=None):
    if policy:
        if policy.get("status") != "ACTIVE" or not policy.get("authorization_source") or not policy.get("revocation"):
            raise Refused("active policy needs a real authorization source and revocation method")
        if not policy.get("idle_rule") or not policy.get("policy_id"):
            raise Refused("policy lacks inactivity rule or identity")
        roots = [checked(r) for r in policy["roots"]]
        selected = []
        for i in plan["items"]:
            if not any(inside(Path(i["path"]), r) and Path(i["path"]) != r for r in roots):
                raise Refused("policy root mismatch")
            if i["resource_class"] not in policy["resource_classes"] or i["purpose"] not in policy["purposes"] or i["action"] not in policy["actions"]:
                raise Refused("policy resource/purpose/action mismatch")
            if i["action"] in ("delete", "archive-delete") and not policy.get("permanent_delete"):
                raise Refused("permanent deletion was not authorized")
            if i["purpose"] == "old-version" and policy.get("version_mode") != plan["version_review"]["mode"]:
                raise Refused("version retirement policy mismatch")
            if any(overlap(Path(i["path"]), checked(p, False)) for p in policy.get("protected_paths", [])):
                raise Refused("policy protects target")
            selected.append(i)
        if sum(i["snapshot"]["logical_bytes"] for i in selected) > policy["max_bytes"]:
            raise Refused("policy budget exceeded")
        return selected
    if not approval or not approval.get("authorization_source") or approval.get("plan_id") != plan["plan_id"] or approval.get("plan_sha256") != digest(plan):
        raise Refused("separate human approval receipt bound to this exact plan is required")
    selected = []
    for entry in approval["items"]:
        found = [i for i in plan["items"] if i["path"] == entry.get("path") and i["action"] == entry.get("action")]
        if len(found) != 1 or not entry.get("inactive_evidence"):
            raise Refused("approved path/action or fresh inactivity evidence mismatch")
        i = found[0]
        if i["purpose"] == "old-version" and not entry.get("retire_entire_version"):
            raise Refused("cache authorization does not authorize version retirement")
        if i["action"] in ("delete", "archive-delete") and not entry.get("permanent_delete"):
            raise Refused("permanent deletion requires explicit approval")
        if i in selected:
            raise Refused("duplicate approved target")
        selected.append(i)
    return selected


def execute(plan, out, apply=False, approval=None, policy=None):
    roots = [checked(p) for p in plan["roots"]]
    protections = [checked(p, False) for p in [*plan["protected_paths"], *BUILTIN_PROTECTED]]
    out = outside_output(out, roots, protections)
    out.parent.mkdir(parents=True, exist_ok=True)
    checked(out.parent)
    selected = authorize(plan, approval, policy) if apply else plan["items"]
    protections.append(out.parent)
    checked_paths = [guard_target(Path(i["path"]), roots, protections) for i in selected]
    if any(overlap(p, q) for n, p in enumerate(checked_paths) for q in checked_paths[n + 1:]):
        raise Refused("nested/duplicate targets")
    report = {"mode": "execute", "plan_id": plan["plan_id"], "plan_sha256": digest(plan), "apply": apply,
              "volumes_before": volumes(roots), "items": [], "logical_processed_bytes": 0,
              "deleted_logical_bytes": 0, "retained_archive_bytes": 0,
              "project_integrity": "not established; run reviewed project-specific minimal checks separately",
              "reversibility": "permanent delete is irreversible; archive restore/rebuild are distinct"}
    execution_lock = None
    try:
        if apply:
            execution_lock = ExecutionLock()
        for i, path in zip(selected, checked_paths):
            row = {"path": str(path), "action": i["action"], "status": "DRY_RUN", "deleted_bytes": 0}
            report["items"].append(row)
            try:
                now = bounded_tree(path, hashes=True, max_bytes=plan["max_bytes"])
                if now["digest"] != i["snapshot"]["digest"]:
                    raise Refused("snapshot changed; replan and obtain updated approval")
                if i.get("purpose") not in ("derived", "old-version") or not i.get("inactive_evidence") or not i.get("basis"):
                    raise Refused("incomplete item evidence")
                if i.get("purpose") == "derived" and not i.get("rebuild"):
                    raise Refused("rebuild evidence missing")
                dependency_evidence(i)
                if i.get("resource_class") == "C" and i.get("purpose") != "old-version":
                    raise Refused("models/SDKs/toolchains/unknown C resources require separate reviewed native operations")
                for rel, m in now["entries"].items():
                    if Path(rel).name.lower() in (".git", ".hg", ".svn") and i["purpose"] != "old-version":
                        raise Refused("nested repository metadata is protected")
                    if m["directory"]:
                        continue
                    kind = protected_file(rel if rel != "." else path.name)
                    if kind == "secret" or (kind == "git" and i["purpose"] != "old-version") or (
                            kind and i["purpose"] != "old-version" and rel not in i.get("rebuildable_files", [])):
                        raise Refused("protected material cannot be deleted by a modified plan")
                if i["action"] == "archive-delete":
                    verify_rehearsal(checked(i.get("restore_rehearsal", "")), now)
                if i["purpose"] == "old-version":
                    current = version_review(plan["version_manifest"])
                    if digest(current) != digest(plan["version_review"]):
                        raise Refused("version evidence/references/retained state changed")
                    if not any(r["path"] == str(path) and r["disposition"] == "RETIRE_CANDIDATE" for r in current["versions"]):
                        raise Refused("target is not an eligible version")
                project = Path(i["project"])
                if (project / ".git").exists() and git_state(project) != i["git_baseline"]:
                    raise Refused("project Git baseline changed")
                if not apply:
                    continue
                with pinned_tree(path, i["snapshot"], i["action"] != "archive") as handles:
                    if i["action"] in ("archive", "archive-delete"):
                        dest = out.parent / (plan["plan_id"] + "-" + digest(str(path))[:12] + ".zip")
                        row["archive_attempt_path"] = str(dest)
                        row["archive"] = archive_tree(path, i["snapshot"], handles, dest)
                        report["retained_archive_bytes"] += row["archive"]["retained_bytes"]
                    if i["action"] in ("delete", "archive-delete"):
                        for rel in sorted(handles, key=lambda r: len(Path(r).parts) if r != "." else 0, reverse=True):
                            h = handles[rel]
                            h.delete()
                            h.close()
                            if not i["snapshot"]["entries"][rel]["directory"]:
                                row["deleted_bytes"] += i["snapshot"]["entries"][rel]["size"]
                        row["status"] = "DELETED" if i["action"] == "delete" else "ARCHIVED_AND_DELETED"
                    else:
                        row["status"] = "ARCHIVED_SOURCE_RETAINED"
                    report["logical_processed_bytes"] += i["snapshot"]["logical_bytes"]
            except (OSError, Refused, zipfile.BadZipFile, KeyError) as e:
                row["status"] = "PARTIAL_FAILURE" if row["deleted_bytes"] else "SKIPPED"
                row["reason"] = str(e) if isinstance(e, Refused) else type(e).__name__
            finally:
                report["deleted_logical_bytes"] += row["deleted_bytes"]
                if row.get("archive_attempt_path") and not row.get("archive"):
                    failed_zip = Path(row["archive_attempt_path"])
                    if failed_zip.exists():
                        row["retained_failed_archive_bytes"] = failed_zip.stat().st_size
                        report["retained_archive_bytes"] += row["retained_failed_archive_bytes"]
    finally:
        if execution_lock is not None:
            execution_lock.close()
        report["volumes_after"] = volumes(roots)
        report["free_delta_bytes"] = {d: report["volumes_after"][d]["free"] - v["free"]
                                     for d, v in report["volumes_before"].items() if "free" in v and "free" in report["volumes_after"][d]}
        report["space_note"] = "measured per-volume changes include other activity; archive-only does not release source space; logical bytes are not a promise"
        write_new(out, report)
    return report


def main():
    global BASE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", required=True, help="dedicated report/control directory; never a drive or user root")
    sub = parser.add_subparsers(dest="mode", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--root", action="append", required=True)
    s.add_argument("--exclude", action="append", default=[])
    s.add_argument("--out", required=True)
    s.add_argument("--max-seconds", type=float, default=40)
    s.add_argument("--max-entries", type=int, default=60000)
    s.add_argument("--max-depth", type=int, default=10)
    s.add_argument("--git-limit", type=int, default=8)
    p = sub.add_parser("plan")
    p.add_argument("--spec", required=True)
    p.add_argument("--out", required=True)
    v = sub.add_parser("versions")
    v.add_argument("--manifest", required=True)
    v.add_argument("--out", required=True)
    x = sub.add_parser("execute")
    x.add_argument("--plan", required=True)
    x.add_argument("--approval")
    x.add_argument("--policy")
    x.add_argument("--out", required=True)
    x.add_argument("--apply", action="store_true")
    a = sub.add_parser("verify-archive")
    a.add_argument("--archive", required=True)
    a.add_argument("--out", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--archive", required=True)
    r.add_argument("--root", required=True)
    r.add_argument("--dest", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("this helper targets Windows local drives only")
    try:
        BASE = checked(args.workspace_root, False)
        if BASE == HOME or any(overlap(BASE, p) for p in BUILTIN_PROTECTED):
            raise Refused("workspace overlaps a protected installation or user root")
        if BASE.exists() and not BASE.is_dir():
            raise Refused("workspace must be a directory")
        if not inside(checked(args.out, False), BASE):
            raise Refused("report must be inside --workspace-root")
        BUILTIN_PROTECTED.append(BASE)
        if args.mode == "scan":
            result = scan(args.root, args.out, args.exclude, args.max_seconds, args.max_entries, args.max_depth, args.git_limit)
        elif args.mode == "plan":
            result = make_plan(load(args.spec), args.out)
        elif args.mode == "versions":
            manifest = load(args.manifest)
            outside_output(args.out, [checked(r["path"]) for r in manifest["versions"]], [BASE])
            result = version_review(manifest)
            write_new(args.out, result)
        elif args.mode == "execute":
            if args.approval and args.policy:
                raise Refused("choose an approval receipt or a policy")
            result = execute(load(args.plan), args.out, args.apply, load(args.approval) if args.approval else None,
                             load(args.policy) if args.policy else None)
        elif args.mode == "verify-archive":
            result = verify_archive(args.archive)
            write_new(args.out, {"verified": True, "logical_bytes": result["logical_bytes"], "recovery": "hash-verified archive, restore rehearsal still separate"})
        else:
            result = restore(args.archive, args.root, args.dest, args.out, args.apply)
        print(json.dumps({"status": "completed", "mode": args.mode, "report": args.out,
                          "items": len(result.get("items", result.get("candidates", [])))}, ensure_ascii=False))
    except (OSError, Refused, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as e:
        print(json.dumps({"status": "REFUSED", "reason": str(e) if isinstance(e, Refused) else type(e).__name__}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
