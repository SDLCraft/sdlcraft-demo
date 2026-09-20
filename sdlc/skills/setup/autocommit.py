#!/usr/bin/env python3
"""Commit an sdlc skill run's own files when the project opted in (CLAUDE.md 20).

/sdlc:setup asks once whether every skill run should commit its own files at
close and stores the answer in .claude/sdlc/sdlc-plugin.json under
`auto_commit` (seeded `off`; a re-run never resets it). Every skill's close
phase then runs this helper as its last action before the close card:

    python .claude/sdlc/autocommit.py commit --skill data \\
        --invocation "/sdlc:data --reconcile" \\
        --summary "DATA-MODEL 2.3 reconciled against PRD 1.4"

which, when the mode is `on`, stages ONLY the files that skill owns (its
artifact and shards, docs/INDEX.yaml, its state file, the findings/lessons
queues, the statusboard files, the marker; `code` adds the source files its
ledger and manifest say it wrote) and commits them as

    <invocation> → <summary>

The separator is U+2192 with a space on each side: the invocation carries its
own colon, and no human types an arrow into a subject, so
`git log --grep='→'` lists exactly the commits this helper made.

What it never does: `git add -A`, push, amend, rebase, `--no-verify`, an empty
commit, or any commit while the mode is off. Anything the user had staged
outside the owned set stays staged and uncommitted (the commit names its
paths). Hooks run and may refuse. A failure here is never a run failure:
every reason not to commit is one printed line, and the exit code is 0.

Subcommands:
    mode [--set on|off]        read or set the stored answer (setup owns the
                               marker; this never creates one)
    commit --skill S --invocation "..." --summary "..."
           [--paths P ...] [--trailer "Key: value" ...] [--dry-run]

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

HELPER_VERSION = "1"
MARKER_REL = Path(".claude/sdlc/sdlc-plugin.json")
ENV_OVERRIDE = "SDLC_AUTO_COMMIT"
MODES = ("off", "on")
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
    # `packets/` and `stack/` are regenerable caches - never committed.
    "code": ("docs/CODE-MANIFEST.json", STATE + "/sdlc-code/inflight",
             STATE + "/sdlc-code/stuck"),
    # repair edits whichever artifact holds the defect and re-slices the task
    # shards, so its set is every artifact; never code's ledger.
    "repair": ("docs", STATE + "/sdlc-repair.doctor.json"),
}
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

def _git(cwd, *args: str):
    """A CompletedProcess, or None when git itself cannot be started."""
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd) if cwd else None,
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


def _status_paths(toplevel: Path, pathspecs: "list[str]") -> "list[str] | None":
    """Changed or untracked files under the pathspecs, toplevel-relative.

    Ignored files never appear here, so a gitignored state directory is never
    force-added. Renames are disabled so every entry is one path.
    """
    if not pathspecs:
        return []
    p = _git(toplevel, "status", "--porcelain=v1", "-z", "--untracked-files=all",
             "--no-renames", "--", *pathspecs)
    if p is None or p.returncode != 0:
        return None
    out: "list[str]" = []
    for entry in p.stdout.split("\0"):
        if len(entry) < 4 or entry[:2] == "!!":
            continue
        out.append(entry[3:])
    return out


# ---------------------------------------------------------------------------
# the owned set
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _paths_from_ledger(text: str) -> "list[str]":
    """Every `files_written[].path` in code's ledger: the parsed shape when
    PyYAML is importable, else the `path:` keys by regex (over-inclusion is
    harmless - git status keeps only what changed)."""
    try:
        import yaml  # type: ignore
        doc = yaml.safe_load(text)
        found: "list[str]" = []
        for task in (doc.get("tasks") or {}).values() if isinstance(doc, dict) else []:
            for entry in (task.get("files_written") or []) if isinstance(task, dict) else []:
                p = entry.get("path") if isinstance(entry, dict) else None
                if isinstance(p, str) and p.strip():
                    found.append(p.strip())
        return found
    except Exception:
        return [m.strip() for m in re.findall(r'(?:^|[\s{,])path:\s*"?([^"\s,}]+)', text)]


def code_generated_files(root: Path) -> "list[str]":
    found = _paths_from_ledger(_read(root / STATE / "sdlc-code.state.yaml"))
    try:
        manifest = json.loads(_read(root / "docs" / "CODE-MANIFEST.json") or "null")
    except ValueError:
        manifest = None
    if isinstance(manifest, dict):
        for entry in manifest.get("files") or []:
            p = entry.get("path") if isinstance(entry, dict) else entry
            if isinstance(p, str) and p.strip():
                found.append(p.strip())
    clean: "list[str]" = []
    for p in found:
        p = Path(p).as_posix().lstrip("./")
        if p and not p.startswith("..") and not Path(p).is_absolute() and p not in clean:
            clean.append(p)
    return clean


def owned_pathspecs(skill: str, root: Path, extra: "list[str]") -> "list[str]":
    if skill in EXACT:
        specs = list(EXACT[skill])
    else:
        specs = list(COMMON) + [STATE + f"/sdlc-{skill}.state.yaml"] + list(OWN.get(skill, ()))
        if skill == "code":
            specs += code_generated_files(root)
    specs += [Path(p).as_posix() for p in extra]
    seen: "list[str]" = []
    for s in specs:
        if s not in seen:
            seen.append(s)
    return seen


# ---------------------------------------------------------------------------
# commit
# ---------------------------------------------------------------------------

def _pathspec_file(paths: "list[str]") -> str:
    f = tempfile.NamedTemporaryFile("wb", suffix=".pathspec", delete=False)
    with f:
        f.write("\0".join(paths).encode("utf-8"))
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


def cmd_commit(args) -> int:
    root = Path(args.project_root).resolve()
    invocation = " ".join(args.invocation.split())
    summary = " ".join(args.summary.split())
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
    specs = [prefix + s for s in owned_pathspecs(args.skill, root, args.paths or [])]
    files = _status_paths(toplevel, specs)
    if files is None:
        print("[DRAFT] not committed - git status failed. Nothing is lost: the files are on disk.")
        return 0
    if not files:
        print(f"[OK] nothing to commit - {invocation} changed no file the pipeline owns")
        return 0

    if args.dry_run:
        print(f"[DRY-RUN] would commit: {subject}")
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
    line = f"[OK] committed {short} - {subject} ({len(files)} file{'s' if len(files) != 1 else ''})"
    left = _status_paths(toplevel, [prefix + "docs", prefix + ".claude"])
    if left:
        line += f" · {len(left)} other pipeline file(s) changed by something else, left uncommitted"
    print(line)
    return 0


# ---------------------------------------------------------------------------
# mode
# ---------------------------------------------------------------------------

def cmd_mode(args) -> int:
    root = Path(args.project_root).resolve()
    cfg = auto_commit_config(root)

    if not args.set:
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
    if args.set == "on":
        print("[OK] auto-commit is on. Every /sdlc:* run now commits its own files when it closes.")
    else:
        print("[OK] auto-commit is off. Nothing is committed on its own.")
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
    p.add_argument("--project-root", default=".", help="Project root (default: cwd).")
    p.set_defaults(func=cmd_mode)

    p = sub.add_parser("commit", help="Commit this run's own files, if the project opted in.")
    p.add_argument("--skill", required=True, help="The running skill: prd, ux, ..., code, repair, lesson, setup.")
    p.add_argument("--invocation", required=True, help='The command as typed, e.g. "/sdlc:data --reconcile".')
    p.add_argument("--summary", required=True, help="One line: what changed, in the user's words.")
    p.add_argument("--paths", nargs="*", action="extend", default=[], metavar="PATH",
                   help="Extra files or directories this run wrote outside the skill's own set.")
    p.add_argument("--trailer", action="append", default=[], metavar="'Key: value'",
                   help="A trailer line for the message (repeatable), e.g. an attribution line.")
    p.add_argument("--dry-run", action="store_true", help="Print what would be committed; write nothing.")
    p.add_argument("--project-root", default=".", help="Project root (default: cwd).")
    p.set_defaults(func=cmd_commit)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
