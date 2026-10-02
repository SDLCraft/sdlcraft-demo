#!/usr/bin/env python3
"""Commit an sdlc skill run's own files when the project opted in (CLAUDE.md 20).

/sdlc:setup asks once whether every skill run should commit its own files at
close and stores the answer in .claude/sdlc/sdlc-plugin.json under
`auto_commit` (seeded `off`; a re-run never resets it). Every skill's Phase 1
runs `begin` before its first write, and its close phase runs `commit` as its
last action before the close card:

    python .claude/sdlc/autocommit.py begin --skill data
    ...
    python .claude/sdlc/autocommit.py commit --skill data \\
        --invocation "/sdlc:data --reconcile" \\
        --summary "DATA-MODEL 2.3 reconciled against PRD 1.4"

`begin` snapshots `git status` under the project root (the run baseline,
stored in the git dir, never in the tree). `commit`, when the mode is `on`,
stages the files that skill owns (its artifact and shards, docs/INDEX.yaml, its
state file, the findings/lessons queues, the statusboard files, the marker;
`code` adds the source files its ledger and manifest say it wrote, plus the
file pins of the units it recorded failed and the files an interrupted unit's
breadcrumb recorded) PLUS the run delta - every file under the project root
that changed after `begin`, wherever the run wrote it - and commits them as

    <invocation> → <summary>

The separator is U+2192 with a space on each side: the invocation carries its
own colon, and no human types an arrow into a subject, so
`git log --grep='→'` lists exactly the commits this helper made.

What it never does: `git add -A`, push, amend, rebase, `--no-verify`, an empty
commit, or any commit while the mode is off. A file that was already changed
when the run began and that the run did not touch stays where it is; anything
the user had staged outside the set stays staged and uncommitted (the commit
names its paths). Hooks run and may refuse. A failure here is never a run
failure: every reason not to commit is one printed line, and the exit code is 0.

Subcommands:
    mode [--set on|off]        read or set the stored answer (setup owns the
                               marker; this never creates one)
    begin --skill S            record the run baseline; silent, keeps an
                               existing one (a resumed run keeps its origin)
    commit --skill S --invocation "..." --summary "..."
           [--checkpoint] [--paths P ...] [--trailer "Key: value" ...] [--dry-run]
                               --checkpoint keeps the baseline (code's
                               container boundaries); otherwise it is consumed

Environment: SDLC_AUTO_COMMIT=on|off overrides the stored mode for one
session or a CI job.

Exit codes:
    0 — committed, nothing to commit, mode off, or not committed for an
        environmental reason (not a repository, git missing or too old,
        identity unset, a hook refused) — the printed line says which.
    1 — `mode --set` refused (unknown value, or no marker: run /sdlc:setup).
    2 — usage error.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    pass

HELPER_VERSION = "4"
MARKER_REL = Path(".claude/sdlc/sdlc-plugin.json")
ENV_OVERRIDE = "SDLC_AUTO_COMMIT"
MODES = ("off", "on")
# `also` (IMP-209) is retired: the run baseline commits every file a run
# writes. A stored list is left in the marker untouched and never read.
DEFAULTS = {"mode": "off", "decided_on": None}
SEPARATOR = " → "
MIN_GIT = (2, 25)  # --pathspec-from-file on `git add` and `git commit`
MODE_CMD = "python .claude/sdlc/autocommit.py mode"

STATE = ".claude/skills-state"
# Every artifact skill's close touches these (record-run may stamp the marker).
COMMON = (
    "docs/INDEX.yaml",
    STATE + "/sdlc-findings.yaml",
    STATE + "/sdlc-lessons.yaml",
    ".claude/rules/sdlc-statusboard.md",
    ".claude/sdlc/STATUS.md",
    ".claude/sdlc/sdlc-plugin.json",
)
# The artifact (and shards) each skill writes, as git pathspecs relative to the
# project root. A hand edit to ANOTHER artifact is never swept into this run's
# commit: the set is what the skill owns, not what changed under docs/.
OWN = {
    "prd": ("docs/PRD.yaml",),
    "ux": ("docs/UX.yaml", "docs/UX__*.yaml"),
    "design": ("docs/DESIGN.yaml", "docs/DESIGN__*.yaml"),
    "data": ("docs/DATA-MODEL.yaml",),
    "api": ("docs/API.yaml", "docs/API__*.yaml"),
    "arch": ("docs/ARCH.yaml", "docs/ARCH__*.yaml",
             STATE + "/sdlc-arch.derivation-report-*.yaml"),
    "test": ("docs/TEST-STRATEGY.yaml", "docs/TEST-STRATEGY__*.yaml"),
    "task": ("docs/TASKS.json", "docs/TASKS__*.json"),
    # `packets/` and `stack/` are regenerable caches - never committed, and
    # never counted as someone else's edit (CACHE_DIRS).
    "code": ("docs/CODE-MANIFEST.json", STATE + "/sdlc-code/inflight",
             STATE + "/sdlc-code/stuck"),
    # repair edits whichever artifact holds the defect and re-slices the task
    # shards, so without a baseline its set is every artifact (BROAD); never
    # code's ledger. Its run tree holds the workers' reports and breadcrumbs.
    "repair": ("docs", STATE + "/sdlc-repair.doctor.json", STATE + "/sdlc-repair"),
}
# Owned entries that stand in for a baseline the run did not record: with one,
# the run delta names exactly the artifacts the run edited, so the broad sweep
# (which would also take a hand edit to an artifact the run never touched) is
# dropped.
BROAD = {"repair": ("docs",)}
# The run's own regenerable caches under code's state dir: ignored, not staged.
CACHE_DIRS = ("packets", "stack")
_GLOB_CHARS = "*?["
CODE_DIR = STATE + "/sdlc-code"
# Skills whose set is EXACTLY this - no COMMON, no `sdlc-<skill>.state.yaml`.
# `lesson` is model-invocable in an ambient session, so it must never sweep a
# hand edit to docs/; `setup` installs, it does not write an artifact.
EXACT = {
    "lesson": (STATE + "/sdlc-lessons.yaml", ".claude/sdlc/sdlc-plugin.json"),
    "setup": (".claude/sdlc", ".claude/rules/sdlc-*.md", "docs/INDEX.yaml",
              STATE + "/sdlc-lessons.yaml", "CLAUDE.md", ".claude/settings.json"),
}


# ---------------------------------------------------------------------------
# the setting
# ---------------------------------------------------------------------------

def _iso_today() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")


def read_marker(root: Path) -> dict:
    try:
        data = json.loads((root / MARKER_REL).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def auto_commit_config(root: Path) -> dict:
    """Effective setting: defaults, then the marker, then $SDLC_AUTO_COMMIT.

    The environment is a hard override so a CI job can switch commits off
    without editing a file in the repo. Anything invalid collapses to `off`.
    """
    cfg = dict(DEFAULTS)
    stored = read_marker(root).get("auto_commit")
    if isinstance(stored, dict):
        cfg.update({k: v for k, v in stored.items() if k in DEFAULTS})
    env = os.environ.get(ENV_OVERRIDE)
    if env in MODES:
        cfg["mode"] = env
    if cfg.get("mode") not in MODES:
        cfg["mode"] = "off"
    return cfg


def write_auto_commit(root: Path, updates: dict) -> bool:
    """Merge into the marker's auto_commit block.

    False when the marker is absent (the project never ran /sdlc:setup) - the
    marker belongs to setup, and this helper never creates one behind its back.
    """
    marker = read_marker(root)
    if not marker:
        return False
    block = dict(DEFAULTS)
    stored = marker.get("auto_commit")
    if isinstance(stored, dict):
        block.update(stored)
    block.update(updates)
    marker["auto_commit"] = block
    try:
        # newline="\n": the marker is generated wholesale by the plugin, so it
        # is LF on every host - the same rule lessons.py follows for consent.
        (root / MARKER_REL).write_text(
            json.dumps(marker, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    except OSError:
        return False
    return True


# ---------------------------------------------------------------------------
# git plumbing - every call tolerant, every exit code read explicitly
# ---------------------------------------------------------------------------

def _git(cwd, *args: str, stdin: "str | None" = None):
    """A CompletedProcess, or None when git itself cannot be started."""
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None, input=stdin,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError:
        return None


def git_version() -> "tuple[int, int] | None":
    p = _git(None, "--version")
    if p is None or p.returncode != 0:
        return None
    m = re.search(r"(\d+)\.(\d+)", p.stdout)
    return (int(m.group(1)), int(m.group(2))) if m else None


def git_toplevel(root: Path) -> "Path | None":
    p = _git(root, "rev-parse", "--show-toplevel")
    if p is None or p.returncode != 0 or not p.stdout.strip():
        return None
    return Path(p.stdout.strip())


def repo_status_line(root: Path) -> str:
    """The `git:` line `mode` prints - what setup reads before asking."""
    if git_version() is None:
        return "git: not installed (nothing can be committed)"
    top = git_toplevel(root)
    return f"git: repository at {top.as_posix()}" if top else "git: not a repository"


def _prefix(root: Path, toplevel: Path) -> str:
    """The project root's path below the repository root ('' when equal)."""
    try:
        rel = root.resolve().relative_to(toplevel.resolve())
    except ValueError:
        return ""
    return "" if str(rel) == "." else rel.as_posix() + "/"


def _status_entries(toplevel: Path, pathspecs: "list[str]") -> "list[tuple[str, str]] | None":
    """(two-letter status, path) for every changed or untracked file under the
    pathspecs, toplevel-relative.

    Ignored files never appear here, so a gitignored state directory is never
    force-added. Renames are disabled so every entry is one path.
    """
    if not pathspecs:
        return []
    p = _git(toplevel, "status", "--porcelain=v1", "-z", "--untracked-files=all",
             "--no-renames", "--", *pathspecs)
    if p is None or p.returncode != 0:
        return None
    out: "list[tuple[str, str]]" = []
    for entry in p.stdout.split("\0"):
        if len(entry) < 4 or entry[:2] == "!!":
            continue
        out.append((entry[:2], entry[3:]))
    return out


def _status_paths(toplevel: Path, pathspecs: "list[str]") -> "list[str] | None":
    """The paths of _status_entries."""
    entries = _status_entries(toplevel, pathspecs)
    return None if entries is None else [path for _code, path in entries]


# ---------------------------------------------------------------------------
# the owned set
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _paths_from_ledger(text: str) -> "list[str]":
    """Every `files_written[].path` and `derived_files[].path` (a scaffold's
    package-manager lockfile) in code's ledger: the parsed shape when
    PyYAML is importable, else the `path:` keys by regex (over-inclusion is
    harmless - git status keeps only what changed)."""
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(text)
        found: "list[str]" = []
        for task in (doc.get("tasks") or {}).values() if isinstance(doc, dict) else []:
            for key in ("files_written", "derived_files"):
                for entry in (task.get(key) or []) if isinstance(task, dict) else []:
                    p = entry.get("path") if isinstance(entry, dict) else None
                    if isinstance(p, str) and p.strip():
                        found.append(p.strip())
        return found
    except Exception:
        return [m.strip() for m in re.findall(r'(?:^|[\s{,])path:\s*"?([^"\s,}]+)', text)]


def _strip_dot_slash(p: str) -> str:
    """Drop leading `./` segments only - never the dot of `.github/`."""
    p = Path(p).as_posix()
    while p.startswith("./"):
        p = p[2:]
    return p


def _failed_task_ids(text: str) -> "list[str]":
    """Qualified ids (`<cid>/TSK-NNN`) of every ledger entry whose status is
    `failed`: a failed unit records no files_written, so its pins come from the
    TASKS shard instead. `skipped` and `blocked` units never ran and wrote
    nothing, so they stay out."""
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(text)
        tasks = (doc.get("tasks") or {}) if isinstance(doc, dict) else {}
        return [str(q) for q, e in tasks.items()
                if isinstance(e, dict) and e.get("status") == "failed"]
    except Exception:
        out: "list[str]" = []
        current = None
        for line in text.splitlines():
            m = re.match(r'^  "?([^"\s:]+/TSK-\d+)"?:\s*$', line)
            if m:
                current = m.group(1)
            elif current and re.match(r'^    status:\s*"?failed"?\s*$', line):
                out.append(current)
        return out


def _failed_unit_files(root: Path, ledger_text: str) -> "list[str]":
    """File-valued `target_files` of the units the ledger records `failed`,
    joined from docs/TASKS__<cid>.json (docs/TASKS.json for `TASKS/...`). A
    directory pin or a glob is skipped: staging a tree is the sweep this helper
    never makes. A missing or unreadable shard contributes nothing."""
    out: "list[str]" = []
    shards: "dict[str, object]" = {}
    for q in _failed_task_ids(ledger_text):
        cid, _, tid = q.partition("/")
        if cid not in shards:
            shard = root / "docs" / ("TASKS.json" if cid == "TASKS" else f"TASKS__{cid}.json")
            try:
                shards[cid] = json.loads(_read(shard) or "null")
            except ValueError:
                shards[cid] = None
        doc = shards[cid]
        for task in (doc.get("tasks") or []) if isinstance(doc, dict) else []:
            if not isinstance(task, dict) or task.get("tsk_id") != tid:
                continue
            for pin in task.get("target_files") or []:
                if not isinstance(pin, str) or not pin.strip():
                    continue
                pin = _strip_dot_slash(pin.strip().replace("\\", "/"))
                if (pin.endswith("/") or any(c in pin for c in _GLOB_CHARS)
                        or (root / pin).is_dir()):
                    continue
                out.append(pin)
    return out


def _breadcrumb_files(root: Path) -> "list[str]":
    """`files_written[].path` of every in-flight breadcrumb: the files an
    interrupted unit already wrote, whose hashes the committed breadcrumb names."""
    out: "list[str]" = []
    for crumb in sorted((root / CODE_DIR / "inflight").glob("*.json")):
        try:
            doc = json.loads(_read(crumb) or "null")
        except ValueError:
            continue
        for entry in (doc.get("files_written") or []) if isinstance(doc, dict) else []:
            p = entry.get("path") if isinstance(entry, dict) else None
            if isinstance(p, str) and p.strip():
                out.append(p.strip())
    return out


def code_generated_files(root: Path) -> "list[str]":
    ledger_text = _read(root / STATE / "sdlc-code.state.yaml")
    found = _paths_from_ledger(ledger_text)
    try:
        manifest = json.loads(_read(root / "docs" / "CODE-MANIFEST.json") or "null")
    except ValueError:
        manifest = None
    if isinstance(manifest, dict):
        for entry in manifest.get("files") or []:
            p = entry.get("path") if isinstance(entry, dict) else entry
            if isinstance(p, str) and p.strip():
                found.append(p.strip())
    found += _failed_unit_files(root, ledger_text)
    found += _breadcrumb_files(root)
    clean: "list[str]" = []
    for p in found:
        p = _strip_dot_slash(p)
        if p and not p.startswith("..") and not Path(p).is_absolute() and p not in clean:
            clean.append(p)
    return clean


def owned_pathspecs(skill: str, root: Path, extra: "list[str]", has_baseline: bool = False) -> "list[str]":
    if skill in EXACT:
        specs = list(EXACT[skill])
    else:
        drop = BROAD.get(skill, ()) if has_baseline else ()
        specs = (list(COMMON) + [STATE + f"/sdlc-{skill}.state.yaml"]
                 + [s for s in OWN.get(skill, ()) if s not in drop])
        if skill == "code":
            specs += code_generated_files(root)
    specs += [Path(p).as_posix() for p in extra]
    seen: "list[str]" = []
    for s in specs:
        if s not in seen:
            seen.append(s)
    return seen


# ---------------------------------------------------------------------------
# the run baseline - every file the run touched, wherever it wrote it
# ---------------------------------------------------------------------------

# Hashing is one `git hash-object --stdin-paths` call; past the cap a dirty
# path is recorded unhashed and read as "untouched" (left out) - a project
# with that many dirty files has a tree no run should sweep.
BASELINE_CAP = 20000


def _root_spec(prefix: str) -> str:
    """The project root as ONE literal pathspec - a `[` in a directory name is
    never read as a glob class matching sibling directories."""
    return f":(literal){prefix.rstrip('/')}" if prefix else "."


def baseline_path(toplevel: Path, skill: str) -> "Path | None":
    """Inside the git dir (`.git/sdlc/baseline-<skill>.json`): never tracked,
    never in `git status`, per worktree, no .gitignore needed."""
    p = _git(toplevel, "rev-parse", "--git-path", f"sdlc/baseline-{skill}.json")
    if p is None or p.returncode != 0 or not p.stdout.strip():
        return None
    rel = Path(p.stdout.strip())
    return rel if rel.is_absolute() else toplevel / rel


def _hashes(toplevel: Path, paths: "list[str]") -> "dict[str, str | None]":
    """path -> blob hash, "deleted" when absent, None when not hashed."""
    out: "dict[str, str | None]" = {}
    present: "list[str]" = []
    for p in paths:
        f = toplevel / p
        if not f.exists():
            out[p] = "deleted"
        elif f.is_file() and len(present) < BASELINE_CAP:
            present.append(p)
        else:
            out[p] = None
    if present:
        r = _git(toplevel, "hash-object", "--no-filters", "--stdin-paths", stdin="\n".join(present) + "\n")
        got = r.stdout.split() if r is not None and r.returncode == 0 else []
        for p, h in zip(present, got if len(got) == len(present) else [None] * len(present)):
            out[p] = h
    return out


def _is_cache(path: str, prefix: str) -> bool:
    return any(path.startswith(f"{prefix}{CODE_DIR}/{d}/") for d in CACHE_DIRS)


def record_baseline(root: Path, skill: str) -> None:
    """`begin`: snapshot every changed or untracked file under the project root.
    An existing baseline is kept - one only survives a run that died before its
    close commit, so a resumed run keeps the snapshot it started from."""
    if auto_commit_config(root)["mode"] != "on":
        return
    ver = git_version()
    if ver is None or ver < MIN_GIT:
        return
    toplevel = git_toplevel(root)
    if toplevel is None:
        return
    bp = baseline_path(toplevel, skill)
    if bp is None or bp.exists():
        return
    prefix = _prefix(root, toplevel)
    entries = _status_entries(toplevel, [_root_spec(prefix)])
    if entries is None:
        return
    paths = [path for _code, path in entries]
    snap = {"skill": skill, "helper_version": HELPER_VERSION, "prefix": prefix,
            "paths": _hashes(toplevel, paths)}
    try:
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_text(json.dumps(snap, indent=1) + "\n", encoding="utf-8", newline="\n")
    except OSError:
        pass


def read_baseline(bp: "Path | None") -> "dict[str, str | None] | None":
    if bp is None:
        return None
    try:
        data = json.loads(bp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    paths = data.get("paths") if isinstance(data, dict) else None
    return paths if isinstance(paths, dict) else None


def run_delta(toplevel: Path, prefix: str, baseline: "dict[str, str | None]") -> "list[str] | None":
    """Every file under the project root the run touched: changed now and
    clean when the run began, or changed when it began and changed again since
    (its content differs from the snapshot). Gitignored files never appear;
    code's regenerable caches are skipped even without their .gitignore."""
    entries = _status_entries(toplevel, [_root_spec(prefix)])
    if entries is None:
        return None
    fresh = [p for _c, p in entries if not _is_cache(p, prefix)]
    again = [p for p in fresh if p in baseline and baseline[p] is not None]
    now = _hashes(toplevel, again)
    return [p for p in fresh if p not in baseline or (p in now and now[p] is not None and now[p] != baseline[p])]


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

def _pathspec_file(paths: "list[str]") -> str:
    """`paths` are already-resolved real repo-relative file paths straight out
    of `git status` (never a user-typed pattern), so every line is written
    `:(literal)`-prefixed - otherwise `git add`/`git commit
    --pathspec-from-file` would re-parse a filename that itself contains a
    pathspec-magic character (`*`, `?`, `[`; possible via a bracketed
    subdirectory, or a delta file whose OWN name is clean but whose
    project-root prefix is not) as a glob, matching sibling files it must
    not touch."""
    f = tempfile.NamedTemporaryFile("wb", suffix=".pathspec", delete=False)
    with f:
        f.write("\0".join(f":(literal){p}" for p in paths).encode("utf-8"))
    return f.name


def _message(subject: str, trailers: "list[str]") -> str:
    lines = [subject]
    if trailers:
        lines += [""] + [t.strip() for t in trailers if t.strip()]
    return "\n".join(lines) + "\n"


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return "git reported no reason"


REPAIR_SUFFIX = " · invocation prefixed with /sdlc:{skill}"


def _normalize_invocation(invocation: str, skill: str) -> "tuple[str, bool, str | None]":
    """Shape-check `--invocation` against `--skill` (the one fact the caller
    always has right, even when the collapsed $ARGUMENTS half under-substitutes
    the documented `/sdlc:<skill> ` prefix).

    Returns `(invocation, repaired, refused_reason)`:
    - already `/sdlc:<skill> ...` — unchanged: `(invocation, False, None)`.
    - `/sdlc:<other> ...` — a real dispatch mismatch, never silently repaired:
      `(invocation, False, "<reason>")`.
    - leading token spells `/<skill>` or `sdlc:<skill>` (no full prefix), or
      the prefix is missing entirely (the lesson's `--system --reconcile`, or
      an empty string) — repaired: `(fixed, True, None)`. No skill name list:
      the only comparison is against `--skill` itself.
    """
    parts = invocation.split(maxsplit=1)
    first = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if first.startswith("/sdlc:"):
        x = first[len("/sdlc:"):]
        if x == skill:
            return invocation, False, None
        return invocation, False, f"--invocation names /sdlc:{x} but --skill is {skill}"

    for lead in ("/", "sdlc:"):
        if first.startswith(lead) and first[len(lead):] == skill:
            fixed = f"/sdlc:{skill}" + (f" {rest}" if rest else "")
            return fixed, True, None

    fixed = f"/sdlc:{skill}" + (f" {invocation}" if invocation else "")
    return fixed, True, None


def _left_entries(toplevel: Path, prefix: str) -> "tuple[list[str], list[str]]":
    """(files changed by something else, tracked cache files that changed).

    code's own regenerable caches are not someone else's edit: an UNTRACKED
    file under packets/ or stack/ is not counted at all, and a TRACKED changed
    one (a project that committed them once) is counted apart so the line can
    name the one command that ends it. The second list holds the cache dir of
    each such file."""
    entries = _status_entries(toplevel, [prefix + "docs", prefix + ".claude"]) or []
    left: "list[str]" = []
    tracked: "list[str]" = []
    for code, path in entries:
        rel = path[len(prefix):] if prefix and path.startswith(prefix) else path
        hit = next((d for d in CACHE_DIRS if rel.startswith(f"{CODE_DIR}/{d}/")), None)
        if hit is None:
            left.append(path)
        elif code != "??":
            tracked.append(hit)
    return left, tracked


def _cache_remedy(tracked: "list[str]") -> str:
    dirs = [d for d in CACHE_DIRS if d in tracked]
    label = "{" + ",".join(dirs) + "}" if len(dirs) > 1 else dirs[0]
    cmd = " ".join(f"{CODE_DIR}/{d}" for d in dirs)
    return (f"{len(tracked)} tracked cache file(s) under {CODE_DIR}/{label} - "
            f"untrack once: git rm -r --cached {cmd}")


def cmd_begin(args) -> int:
    record_baseline(Path(args.project_root).resolve(), args.skill)
    return 0


def cmd_commit(args) -> int:
    """Commit, then consume the run baseline - the run closed, whatever the
    outcome - unless this is a mid-run `--checkpoint` or a `--dry-run`."""
    root = Path(args.project_root).resolve()
    try:
        return _commit(args, root)
    finally:
        if not (args.checkpoint or args.dry_run):
            top = git_toplevel(root) if git_version() is not None else None
            bp = baseline_path(top, args.skill) if top is not None else None
            if bp is not None:
                try:
                    bp.unlink()
                except OSError:
                    pass


def _commit(args, root: Path) -> int:
    invocation = " ".join(args.invocation.split())
    summary = " ".join(args.summary.split())

    invocation, repaired, refused = _normalize_invocation(invocation, args.skill)
    if refused:
        print(f"[DRAFT] not committed - {refused}. Nothing is lost: the files are on disk.")
        return 0
    note = REPAIR_SUFFIX.format(skill=args.skill) if repaired else ""

    subject = f"{invocation}{SEPARATOR}{summary}"

    cfg = auto_commit_config(root)
    if cfg["mode"] != "on":
        print(f"[OK] auto-commit is off - nothing committed (turn it on: {MODE_CMD} --set on)")
        return 0

    ver = git_version()
    if ver is None:
        print("[DRAFT] not committed - git is not installed. Nothing is lost: the files are on disk.")
        return 0
    if ver < MIN_GIT:
        print(f"[DRAFT] not committed - git {MIN_GIT[0]}.{MIN_GIT[1]} or newer is needed "
              f"(this is {ver[0]}.{ver[1]}). Nothing is lost: the files are on disk.")
        return 0
    toplevel = git_toplevel(root)
    if toplevel is None:
        print("[DRAFT] not committed - this project is not a git repository. "
              "Nothing is lost: the files are on disk.")
        return 0

    prefix = _prefix(root, toplevel)
    baseline = read_baseline(baseline_path(toplevel, args.skill))
    specs = [prefix + s for s in owned_pathspecs(args.skill, root, args.paths or [],
                                                  has_baseline=baseline is not None)]
    files = _status_paths(toplevel, specs)
    delta = run_delta(toplevel, prefix, baseline) if baseline is not None else []
    if files is None or delta is None:
        print("[DRAFT] not committed - git status failed. Nothing is lost: the files are on disk.")
        return 0
    pipeline_dirs = (prefix + "docs/", prefix + ".claude/")
    elsewhere = [p for p in delta if p not in files and not p.startswith(pipeline_dirs)]
    files += [p for p in delta if p not in files]
    if elsewhere:
        note = f" · {len(elsewhere)} file(s) outside docs/ and .claude/" + note
    if not files:
        print(f"[OK] nothing to commit - {invocation} changed no file the pipeline owns{note}")
        return 0

    if args.dry_run:
        print(f"[DRY-RUN] would commit: {subject}{note}")
        for p in files:
            print(f"          {p}")
        return 0

    spec_file = _pathspec_file(files)
    msg_file = tempfile.NamedTemporaryFile("w", suffix=".msg", delete=False, encoding="utf-8", newline="\n")
    with msg_file:
        msg_file.write(_message(subject, args.trailer or []))
    try:
        added = _git(toplevel, "add", "--pathspec-from-file=" + spec_file, "--pathspec-file-nul")
        if added is None or added.returncode != 0:
            print(f"[DRAFT] not committed - git add failed: "
                  f"{_first_line(added.stderr if added else '')}. Nothing is lost: the files are on disk.")
            return 0
        committed = _git(toplevel, "commit", "--quiet", "--only",
                         "--pathspec-from-file=" + spec_file, "--pathspec-file-nul",
                         "-F", msg_file.name)
    finally:
        for name in (spec_file, msg_file.name):
            try:
                os.unlink(name)
            except OSError:
                pass

    if committed is None or committed.returncode != 0:
        reason = _first_line((committed.stderr + "\n" + committed.stdout) if committed else "")
        print(f"[DRAFT] not committed - {reason}. Nothing is lost: {len(files)} file(s) are "
              f"staged; commit them by hand with: git commit -m \"{subject}\"")
        return 0

    sha = _git(toplevel, "rev-parse", "--short", "HEAD")
    short = sha.stdout.strip() if sha is not None and sha.returncode == 0 else "HEAD"
    line = f"[OK] committed {short} - {subject} ({len(files)} file{'s' if len(files) != 1 else ''}){note}"
    left, cached = _left_entries(toplevel, prefix)
    if left:
        line += f" · {len(left)} other pipeline file(s) changed by something else, left uncommitted"
    if cached:
        line += " · " + _cache_remedy(cached)
    print(line)
    return 0


# ---------------------------------------------------------------------------
# mode
# ---------------------------------------------------------------------------

def cmd_mode(args) -> int:
    root = Path(args.project_root).resolve()
    cfg = auto_commit_config(root)

    if args.also is not None:
        print("[OK] auto_commit.also is retired - every file a run writes is now committed by "
              "the run baseline. Nothing written.")
        if args.set is None:
            return 0

    # No --set: read-only, print the mode.
    if args.set is None:
        decided = f" (decided {cfg['decided_on']})" if cfg.get("decided_on") else ""
        print(f"[OK] auto-commit is {cfg['mode']!r} for this project{decided}.")
        env = os.environ.get(ENV_OVERRIDE)
        if env in MODES:
            print(f"      {ENV_OVERRIDE}={env} in this environment is overriding whatever the marker says.")
        print(f"      {repo_status_line(root)}")
        print(f"\nNEXT: change it with: {MODE_CMD} --set on|off")
        return 0

    if args.set not in MODES:
        print(f"[FAIL] {args.set!r} is not one of {'|'.join(MODES)}.")
        return 1
    if not write_auto_commit(root, {"mode": args.set, "decided_on": _iso_today()}):
        print(f"[FAIL] no .claude/sdlc/sdlc-plugin.json in {root} - run /sdlc:setup first; "
              f"it owns that file.")
        return 1
    print("[OK] " + ("auto-commit is on. Every /sdlc:* run now commits its own files when it closes."
                     if args.set == "on" else "auto-commit is off. Nothing is committed on its own."))
    print("\nNEXT: nothing to run - this takes effect at the next skill close.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="autocommit.py",
        description="Commit an sdlc skill run's own files when the project opted in.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("mode", help="Read or set auto-commit (on|off).")
    p.add_argument("--set", default=None, metavar="MODE", help="on (commit at every skill close) or off.")
    p.add_argument("--also", nargs="*", action="extend", default=None, metavar="PATH",
                   help=argparse.SUPPRESS)  # retired; answered with one line
    p.add_argument("--project-root", default=".", help="Project root (default: cwd).")
    p.set_defaults(func=cmd_mode)

    p = sub.add_parser("begin", help="Record the run baseline (Phase 1, before the run's first write).")
    p.add_argument("--skill", required=True, help="The running skill: prd, ux, ..., code, repair, lesson, setup.")
    p.add_argument("--project-root", default=".", help="Project root (default: cwd).")
    p.set_defaults(func=cmd_begin)

    p = sub.add_parser("commit", help="Commit this run's own files, if the project opted in.")
    p.add_argument("--skill", required=True, help="The running skill: prd, ux, ..., code, repair, lesson, setup.")
    p.add_argument("--invocation", required=True, help='The command as typed, e.g. "/sdlc:data --reconcile".')
    p.add_argument("--summary", required=True, help="One line: what changed, in the user's words.")
    p.add_argument("--paths", nargs="*", action="extend", default=[], metavar="PATH",
                   help="Extra files or directories this run wrote outside the skill's own set.")
    p.add_argument("--trailer", action="append", default=[], metavar="'Key: value'",
                   help="A trailer line for the message (repeatable), e.g. an attribution line.")
    p.add_argument("--checkpoint", action="store_true",
                   help="A mid-run commit (code's container boundary): keep the run baseline.")
    p.add_argument("--dry-run", action="store_true", help="Print what would be committed; write nothing.")
    p.add_argument("--project-root", default=".", help="Project root (default: cwd).")
    p.set_defaults(func=cmd_commit)
    return ap


def _merge_flag_values(argv: "list[str]") -> "list[str]":
    """Rewrite an adjacent `--invocation X` / `--summary X` pair to
    `--invocation=X` / `--summary=X` before `parse_args` sees them.

    Both values can legitimately start with `-` (an under-substituted
    `--invocation` is exactly `$ARGUMENTS`, e.g. `-d` or `--reconcile`; a
    `-`-led one-word `--summary` is the same shape). Passed as two argv
    tokens, argparse's own next-token-looks-like-an-option heuristic refuses
    them (`error: argument --invocation: expected one argument`, exit 2) -
    the caller's malformed call would not even reach `cmd_commit`'s repair.
    The `--flag=value` form sidesteps that heuristic entirely.
    """
    out: "list[str]" = []
    i, n = 0, len(argv)
    while i < n:
        tok = argv[i]
        if tok in ("--invocation", "--summary") and i + 1 < n:
            out.append(f"{tok}={argv[i + 1]}")
            i += 2
            continue
        out.append(tok)
        i += 1
    return out


def main(argv=None) -> int:
    argv = _merge_flag_values(list(argv if argv is not None else sys.argv[1:]))
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
