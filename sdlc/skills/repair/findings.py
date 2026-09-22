#!/usr/bin/env python3
"""findings.py — the one writer of .claude/skills-state/sdlc-findings.yaml,
the cross-skill FND-NNN queue (CLAUDE.md section 13).

Any sdlc stage that NOTICES a defect in this project's docs/ records it here
and moves on; /sdlc:repair localizes it to the artifact that is actually
wrong and fixes it there. Nothing else writes the queue: not a skill by hand,
not a heredoc, not the doctor sweep (which imports this module). Every entry
is validated against validate_findings.py's models BEFORE it is appended, so a
row that would fail the validator never reaches the file.

Skills call it as   python "${CLAUDE_SKILL_DIR}/../repair/findings.py" ...
Ambient sessions    python .claude/sdlc/findings.py ...   (installed by setup)

Usage:
    findings.py add --raised-by sdlc-arch --kind contract_contradiction \
        --summary "<one line>" --evidence "<line>" [--evidence "<line>" ...] \
        [--suspected-stage arch] [--suspected-source docs/ARCH__x.yaml] \
        [--symbol <sym>] [--qualified-task <cid>/TSK-NNN] [--file docs/X.yaml] \
        [--field-path <dotted>] [--detected-by <check-or-phase>] \
        [--related FND-NNN ...] [--session-id <id>] [--allow-duplicate]
    findings.py list [--open] [--status s ...] [--stage s] [--raised-by r] [--json]
    findings.py list --owed-by docs/<artifact> [--json]
                        # the re-invoke findings waiting on that file + the
                        # handoff notes left for it (read by every --reconcile)
    findings.py plan [--from <dir of localize reports>] [--doctor-json <snapshot>]
                     [--close-first FND-NNN ...] [--json]
                        # the open set grouped into aggregates (write sets that
                        # share an artifact) and ordered into stage-waves,
                        # upstream first - the table /sdlc:repair's plan gate
                        # shows; provisional from queue fields alone, exact
                        # once wave 1's reports are in
    findings.py reopen FND-NNN
                        # a resolved/wontfix/deferred finding whose owed work
                        # turned out incomplete (doctor.py --provenance's
                        # "should be reopened" hint names the command).
                        # Mode-aware: mode=re-invoke -> triaged, resolution
                        # KEPT (downstream_rerun replayed unconditionally -
                        # this script never asks which stage still needs it,
                        # the repair session that reopened it decides); any
                        # other mode -> open, resolution stripped, its
                        # artifacts_touched folded into a new evidence line
                        # so the walk record is not simply discarded.
    findings.py validate [--upgrade]
                        # --upgrade: when every gated check already passes
                        # with ZERO warnings, raise findings_file_version to
                        # the current floor (NEW_FILE_VERSION) and write it;
                        # a no-op if already there, refused while any warning
                        # remains. The one sanctioned writer of this field
                        # besides a fresh empty queue.
    findings.py stats
  Global: [--project-root <dir>] [--path <queue path>] (before or after the verb)

`add` mints the next id (max(last_ids.FND, highest present) + 1), refuses to
record a second copy of a still-open defect (same detected_by + summary) unless
--allow-duplicate, and stamps recurrence_of / recurrence when a resolved or
wontfix finding already named the same symbol or task with the same kind.

Exit codes:
    0 — recorded (or deliberately not recorded: a duplicate), listed, valid,
        or reopened.
    1 — the entry was rejected: it would not validate, or a flag value is not
        in the schema's enum. Nothing was written. `reopen` on an id that is
        not in the queue, or whose status is not resolved/wontfix/deferred,
        is the same rejection.
    2 — the queue could not be read or parsed, or could not be written. A
        queue that merely FAILS VALIDATION does not block an append: the entry
        lands and the run warns, because a producer must never lose a finding
        to a row somebody else wrote (ledger IMP-124).
    3 — required dependency missing (pyyaml, pydantic v2, or
        validate_findings.py not reachable from this script).
"""

from __future__ import annotations

import argparse
import glob
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: pyyaml is required.\nInstall with:  pip install pyyaml", file=sys.stderr)
    sys.exit(3)

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"
QUEUE_REL = Path(".claude/skills-state/sdlc-findings.yaml")
STATE_REL_TMPL = ".claude/skills-state/sdlc-{skill}.state.yaml"
FND_RE = re.compile(r"^FND-\d{3,}$")
RAISED_BY_RE = re.compile(r"^(sdlc-[a-z0-9-]+|user)$")
MAX_EVIDENCE = 5
MAX_EVIDENCE_LEN = 300
# IMP-196: the floor a fresh queue starts at, and the target `validate
# --upgrade` raises an existing queue to once every gated check on it passes
# with ZERO warnings. Was "2"; raised to "3" alongside validate_findings.py's
# ARTIFACTS_TOUCHED_GATED_VERSION / SITES_CONSIDERED_GATED_VERSION so a fresh
# queue is born past both floors and `--upgrade` has somewhere to raise an
# older one TO.
NEW_FILE_VERSION = "3"

# Statuses a fresh `add` deduplicates against: a defect nobody has closed yet.
# The doctor sweep widens this (see doctor.py) because it re-runs the same
# checks every time and must not re-mint what a person already dismissed.
OPEN_STATUSES = ("open", "triaged")
CLOSED_STATUSES = ("resolved", "wontfix")

# /sdlc:<skill> [<cid>]  ->  the artifact that invocation rewrites. One map for
# every reader of "what does this finding still owe": doctor.py (the awaiting
# label, the --provenance hints), validate_findings.py (whether a handoff note
# lands where anyone reads it) and `list --owed-by` (the reconcile run the
# finding is waiting on, reading why).
SKILL_ARTIFACT = {
    "prd": ("PRD", "yaml"), "ux": ("UX", "yaml"), "design": ("DESIGN", "yaml"),
    "data": ("DATA-MODEL", "yaml"), "api": ("API", "yaml"), "arch": ("ARCH", "yaml"),
    "test": ("TEST-STRATEGY", "yaml"), "task": ("TASKS", "json"),
}
SHARDED_SKILLS = ("arch", "test", "task")
RERUN_RE = re.compile(r"/sdlc:([a-z]+)(?:\s+([A-Za-z0-9][\w-]*))?")
ARTIFACT_RE = re.compile(r"\b([A-Z][A-Z0-9-]*(?:__[a-z0-9-]+)?\.(?:yaml|json))\b")
# A re-invoke finding owes its downstream artifacts for as long as it is open.
AWAITING_STATUSES = OPEN_STATUSES


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_project_root(arg: Optional[str]) -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd()


# =============================================================================
# The validator. findings.py never re-implements the schema: it imports the
# models from validate_findings.py — beside this file in the plugin, and
# beside the installed copy under .claude/sdlc/ (setup installs both).
# =============================================================================

def _validator_candidates() -> List[Path]:
    here = Path(__file__).resolve().parent
    cands = [here / "validate_findings.py"]
    skill_dir = os.environ.get("CLAUDE_SKILL_DIR")
    if skill_dir:
        cands.append(Path(skill_dir).resolve().parent / "repair" / "validate_findings.py")
    home = Path.home()
    for pat in (
        str(home / ".claude" / "plugins" / "**" / "sdlc" / "skills" / "repair" / "validate_findings.py"),
    ):
        cands += [Path(p) for p in sorted(glob.glob(pat, recursive=True))]
    return cands


_VALIDATOR = None


def validator_module():
    """Import validate_findings once. Exit 3 when it cannot be found: a queue
    written without validation is exactly what this helper exists to prevent."""
    global _VALIDATOR
    if _VALIDATOR is not None:
        return _VALIDATOR
    for cand in _validator_candidates():
        if cand.is_file():
            spec = importlib.util.spec_from_file_location("validate_findings", cand)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            # Registered BEFORE exec: the validator's models use postponed
            # annotations, which pydantic resolves through sys.modules.
            sys.modules["validate_findings"] = mod
            try:
                spec.loader.exec_module(mod)
            except SystemExit as e:  # pydantic/pyyaml missing inside the validator
                sys.exit(int(e.code or 3))
            _VALIDATOR = mod
            return mod
    print("ERROR: validate_findings.py is not reachable from findings.py - it must sit "
          "beside this script (the plugin's repair/ folder, or .claude/sdlc/ after "
          "/sdlc:setup). Nothing was written.", file=sys.stderr)
    sys.exit(3)


# =============================================================================
# Queue I/O
# =============================================================================

def empty_queue() -> Dict[str, Any]:
    return {
        "findings_file_version": NEW_FILE_VERSION,
        "last_updated": None,
        "last_ids": {"FND": 0},
        "findings": [],
    }


def load_findings(path: Path) -> Dict[str, Any]:
    """Load the queue, defaulting an absent file to an empty version-2 queue.
    Raises OSError / yaml.YAMLError / ValueError on an unreadable file."""
    if not path.is_file():
        return empty_queue()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return empty_queue()
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    raw.setdefault("findings_file_version", "1")
    raw["findings_file_version"] = str(raw["findings_file_version"])
    if not isinstance(raw.get("last_ids"), dict):
        raw["last_ids"] = {}
    raw["last_ids"].setdefault("FND", 0)
    if not isinstance(raw.get("findings"), list):
        raw["findings"] = []
    return raw


def dump_findings(data: Dict[str, Any], path: Path) -> None:
    data["last_updated"] = _iso_utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def next_fnd(data: Dict[str, Any]) -> int:
    """Counter reconciliation (CLAUDE.md section 2): the on-disk maximum wins
    over a stale counter, so an EXIT/resume can never reissue an id."""
    highest = 0
    for f in data.get("findings") or []:
        if isinstance(f, dict):
            m = FND_RE.match(str(f.get("fnd_id", "")))
            if m:
                highest = max(highest, int(str(f["fnd_id"]).split("-")[1]))
    try:
        counter = int(data.get("last_ids", {}).get("FND") or 0)
    except (TypeError, ValueError):
        counter = 0
    return max(counter, highest) + 1


# =============================================================================
# What an open re-invoke finding still owes
# =============================================================================

def _artifact_name(path: Any) -> str:
    """'docs/TASKS__x.json#TSK-001.test_spec' -> 'TASKS__x.json'."""
    return str(path or "").split("#", 1)[0].replace("\\", "/").rsplit("/", 1)[-1]


def _join_ids(ids, limit: int = 12) -> str:
    ids = [str(i) for i in ids]
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown} (+{len(ids) - limit} more)"


def rerun_artifacts(commands) -> List[str]:
    """'/sdlc:test demo-api --reconcile' -> 'TEST-STRATEGY__demo-api.yaml';
    '/sdlc:arch --system --reconcile' and '/sdlc:arch' -> 'ARCH.yaml'. A bare
    sharded form ('/sdlc:test --reconcile') maps to the system file only, so
    repair names the container whenever it knows one."""
    out: List[str] = []
    for cmd in commands or []:
        for m in RERUN_RE.finditer(str(cmd)):
            skill, arg = m.group(1), m.group(2)
            if skill not in SKILL_ARTIFACT:
                continue
            base, ext = SKILL_ARTIFACT[skill]
            if arg and not arg.startswith("-") and skill in SHARDED_SKILLS:
                out.append(f"{base}__{arg}.{ext}")
            else:
                out.append(f"{base}.{ext}")
    return out


def owed_artifacts(res: Any) -> List[str]:
    """The artifact file names a re-invoke resolution still owes: the files its
    downstream_rerun commands rewrite, plus the targets of propagation hops
    with no verified_at. A verified hop, a code hop and any other mode owe
    nothing."""
    if not isinstance(res, dict) or res.get("mode") != "re-invoke":
        return []
    names = rerun_artifacts([str(x) for x in (res.get("downstream_rerun") or []) if x])
    for h in res.get("propagation") or []:
        if not isinstance(h, dict) or str(h.get("verified_at") or "").strip():
            continue
        name = _artifact_name(h.get("target"))
        if ARTIFACT_RE.fullmatch(name):
            names.append(name)
    out: List[str] = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


def awaiting_registry(data: Dict[str, Any]) -> Dict[str, Tuple[str, str, List[str]]]:
    """artifact file name -> (fnd_id, label, owed commands) for every artifact
    an open re-invoke finding still owes (see owed_artifacts).

    Such an artifact is red on every sweep until the user runs the owed
    command, and its first defect line moves as the chain advances (a ux hop
    surfaces 'SCR-017 has no task', the arch hop five work_unit names) - so
    the summary-keyed dedupe never matched and every sweep minted the known
    failure again (ledger IMP-077, aicf LSN-058: FND-080 -> FND-085)."""
    reg: Dict[str, Tuple[str, str, List[str]]] = {}
    for f in data.get("findings") or []:
        if not isinstance(f, dict) or f.get("status") not in AWAITING_STATUSES:
            continue
        res = f.get("resolution") if isinstance(f.get("resolution"), dict) else None
        names = owed_artifacts(res)
        if not names:
            continue
        fnd_id = str(f.get("fnd_id"))
        cmds = [str(x) for x in (res.get("downstream_rerun") or []) if x]
        label = f"awaiting re-invocation per {fnd_id}" + (f" ({_join_ids(cmds, 2)})" if cmds else "")
        for name in names:
            reg.setdefault(name, (fnd_id, label, cmds))
    return reg


def owed_findings(data: Dict[str, Any], artifact: str) -> List[Dict[str, Any]]:
    """The open re-invoke findings that owe ``artifact`` (a docs/ path or a bare
    file name), each as the compact record a reconcile run reads: what was
    wrong, what repair changed, the commands still owed, and the handoff notes
    repair left for THIS file - the reason for the change, carried on disk so
    a fresh session does not need the one that made it."""
    name = _artifact_name(artifact)
    out: List[Dict[str, Any]] = []
    for f in data.get("findings") or []:
        if not isinstance(f, dict) or f.get("status") not in AWAITING_STATUSES:
            continue
        res = f.get("resolution") if isinstance(f.get("resolution"), dict) else None
        if name not in owed_artifacts(res):
            continue
        handoff = res.get("handoff") if isinstance(res.get("handoff"), list) else []
        notes = [{"key": h.get("key"), "note": str(h.get("note")).strip(),
                  "basis": str(h.get("basis") or "unstated"),
                  "retired": [str(t) for t in (h.get("retired") or []) if str(t).strip()]}
                 for h in handoff
                 if isinstance(h, dict) and _artifact_name(h.get("artifact")) == name
                 and str(h.get("note") or "").strip()]
        out.append({
            "fnd_id": f.get("fnd_id"),
            "summary": f.get("summary"),
            "located_stage": res.get("located_stage"),
            "fix": res.get("summary"),
            "downstream_rerun": [str(x) for x in (res.get("downstream_rerun") or []) if x],
            "handoff": notes,
        })
    return out


# =============================================================================
# Reopen — the sanctioned pen back into scope for a closed finding whose owed
# work turned out incomplete (ledger IMP-158)
# =============================================================================

REOPENABLE_STATUSES = ("resolved", "wontfix", "deferred")


def reopen_finding(data: Dict[str, Any], fnd_id: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Flip a closed finding back into scope, mode-aware — a blind status
    overwrite would itself write the class of invalid row 1.17 just rejected
    (an open finding still carrying a resolution block, or a triaged one
    carrying a non-re-invoke mode):

      - mode re-invoke -> triaged, resolution KEPT as-is (SKILL.md: a triaged
        finding may carry exactly this partial-progress block). Its
        downstream_rerun is replayed unconditionally; deciding which stage
        still needs the reconcile is the repair session's call, not this
        script's — it stays non-interactive.
      - anything else (surgical / additive / none / no mode) -> open,
        resolution stripped (SKILL.md: an open finding carries no resolution
        block at all). The walk is not simply discarded: its
        artifacts_touched is folded into one new evidence line, so a fresh
        session still knows what was touched before, even though the finding
        starts over.

    Returns (the mutated finding, []) on success, or (None, [problem, ...])
    without touching `data` when it cannot be reopened.
    """
    target = None
    for f in data.get("findings") or []:
        if isinstance(f, dict) and str(f.get("fnd_id")) == fnd_id:
            target = f
            break
    if target is None:
        return None, [f"{fnd_id} is not in this queue."]
    status = target.get("status")
    if status not in REOPENABLE_STATUSES:
        return None, [f"{fnd_id} is status={status!r} - reopen only applies to "
                      f"{'/'.join(REOPENABLE_STATUSES)}."]
    res = target.get("resolution") if isinstance(target.get("resolution"), dict) else {}
    if (res or {}).get("mode") == "re-invoke":
        target["status"] = "triaged"
        # resolution is kept exactly as recorded: SKILL.md's triaged +
        # re-invoke shape, the same partial-progress block a run in progress
        # already carries.
    else:
        touched = [str(a) for a in (res or {}).get("artifacts_touched") or []]
        note = (f"reopened {_iso_utc_now()}: previously touched {_join_ids(touched, 6)} "
                f"(resolution stripped on reopen)" if touched else
                f"reopened {_iso_utc_now()} (resolution stripped on reopen)")
        evidence = list(target.get("evidence") or [])
        evidence.append(note[:MAX_EVIDENCE_LEN])
        if len(evidence) > MAX_EVIDENCE:
            evidence = evidence[-MAX_EVIDENCE:]
        target["evidence"] = evidence
        target["status"] = "open"
        target["resolution"] = None
    return target, []


# =============================================================================
# Dedupe + recurrence
# =============================================================================

def dedupe_key(entry: Dict[str, Any]) -> Tuple[Optional[str], str]:
    return (entry.get("detected_by"), str(entry.get("summary") or "")[:200])


def find_duplicate(data: Dict[str, Any], entry: Dict[str, Any],
                   statuses=OPEN_STATUSES) -> Optional[str]:
    """The id of a still-open finding with the same (detected_by, summary)."""
    key = dedupe_key(entry)
    for f in data.get("findings") or []:
        if isinstance(f, dict) and f.get("status") in statuses and dedupe_key(f) == key:
            return str(f.get("fnd_id"))
    return None


def _anchor(entry: Dict[str, Any]) -> Optional[str]:
    sa = entry.get("surfaced_at") or {}
    if not isinstance(sa, dict):
        return None
    return sa.get("qualified_task") or sa.get("symbol") or None


def find_recurrence(data: Dict[str, Any], entry: Dict[str, Any]) -> Optional[Tuple[str, int]]:
    """(earlier id, recurrence count) when a resolved/wontfix finding already
    named the same task-or-symbol with the same kind. The count is how many
    times the defect has come back: the earlier finding's count + 1."""
    anchor = _anchor(entry)
    if not anchor:
        return None
    kind = entry.get("kind")
    best: Optional[Tuple[str, int]] = None
    for f in data.get("findings") or []:
        if not isinstance(f, dict) or f.get("status") not in CLOSED_STATUSES:
            continue
        if f.get("kind") != kind:
            continue
        sa = f.get("surfaced_at") or {}
        if not isinstance(sa, dict):
            continue
        if anchor in (sa.get("qualified_task"), sa.get("symbol")):
            prior = f.get("recurrence")
            prior_n = int(prior) if isinstance(prior, int) else 0
            best = (str(f.get("fnd_id")), prior_n + 1)   # later entries win
    return best


# =============================================================================
# Append (the only write path)
# =============================================================================

class QueueError(Exception):
    """The queue on disk cannot be used (unreadable, or already invalid)."""


class EntryRejected(Exception):
    """The candidate entry would not validate; nothing was written."""

    def __init__(self, problems: List[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def append_findings(path: Path, entries: List[Dict[str, Any]], *,
                    dedupe_statuses=OPEN_STATUSES, allow_duplicate: bool = False,
                    stamp_recurrence: bool = True, tolerate_existing: bool = False):
    """Validate-then-append. Returns (added, skipped, pre_existing_errors):
    added    = [(fnd_id, entry)] in the order they were written
    skipped  = [(entry, duplicate_of_id)] for entries a still-open twin covers
    pre_existing_errors = problems the queue ALREADY had when this was called

    The whole candidate queue (existing rows + every new entry) is validated
    before the file is touched. An invalid NEW entry raises EntryRejected and
    nothing is written — not even the entries that were fine.

    `tolerate_existing` decides what an already-invalid queue means. Refusing
    it (the default, and what the doctor sweep wants) protects a queue nobody
    has repaired. For a PRODUCER — code's raising conditions, every skill's
    close-phase drain — refusing it threw away a finding because of a row
    written by someone else, at the one moment the finding had nowhere else
    to go, so `cmd_add` passes True and reports the queue's own problem
    instead (ledger IMP-124).
    """
    vf = validator_module()
    try:
        data = load_findings(path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        raise QueueError(f"cannot read {path}: {e}")

    # Counter reconciliation (CLAUDE.md section 2) happens BEFORE the queue is
    # judged: a counter that fell behind the ids on disk is exactly the state
    # this helper exists to recover from, not a reason to refuse the append.
    data["last_ids"]["FND"] = next_fnd(data) - 1
    _doc, pre_errors, _warns = vf.validate_raw(data, str(path))
    if pre_errors and not tolerate_existing:
        raise QueueError(
            f"{path} already fails validation ({len(pre_errors)} problem(s)); nothing appended - "
            f"run validate_findings.py and repair the queue first. First problem: {pre_errors[0]}"
        )

    counter = next_fnd(data)
    added: List[Tuple[str, Dict[str, Any]]] = []
    skipped: List[Tuple[Dict[str, Any], str]] = []
    now = _iso_utc_now()
    for raw_entry in entries:
        entry = dict(raw_entry)
        if not allow_duplicate:
            dup = find_duplicate(data, entry, dedupe_statuses)
            if dup:
                skipped.append((entry, dup))
                continue
        entry["fnd_id"] = f"FND-{counter:03d}"
        entry.setdefault("raised_at", now)
        entry.setdefault("status", "open")
        entry.setdefault("resolution", None)
        if stamp_recurrence and not entry.get("recurrence_of"):
            rec = find_recurrence(data, entry)
            if rec:
                entry["recurrence_of"], entry["recurrence"] = rec
        # Field-level check on the entry alone first: the message then names
        # the entry's own field, not "findings -> 37 -> evidence".
        try:
            vf.Finding.model_validate(entry)
        except vf.ValidationError as e:
            problems = [f"{' -> '.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
            raise EntryRejected(problems)
        data["findings"].append(entry)
        data["last_ids"]["FND"] = counter
        added.append((entry["fnd_id"], entry))
        counter += 1

    if not added:
        return added, skipped, pre_errors

    _doc, errors, _warns = vf.validate_raw(data, str(path))
    # Only what THIS call introduced can reject it; a problem the queue
    # already had is reported, not blamed on the new entry.
    new_errors = [e for e in errors if e not in pre_errors]
    if new_errors:
        raise EntryRejected(new_errors)
    try:
        dump_findings(data, path)
    except OSError as e:
        raise QueueError(f"cannot write {path}: {e}")
    return added, skipped, pre_errors


# =============================================================================
# CLI
# =============================================================================

def _queue_path(args) -> Path:
    if getattr(args, "path", None):
        return Path(args.path)
    return resolve_project_root(getattr(args, "project_root", None)) / QUEUE_REL


def _reject(reason: str) -> int:
    print(f"[FAIL] not recorded - {reason}", file=sys.stderr)
    return 1


def _reject_all(problems: List[str]) -> int:
    """Every bad flag at once, so one more run records the finding."""
    if len(problems) == 1:
        return _reject(problems[0])
    print(f"[FAIL] not recorded - {len(problems)} flag(s) are wrong:", file=sys.stderr)
    for p in problems:
        print(f"  - {p}", file=sys.stderr)
    return 1


def kind_help(argv: "Optional[List[str]]") -> str:
    """The --kind enum, spelled out - but only when the call is an `add`.

    Reading the enum means importing the validator, which needs pydantic and
    exits 3 without it. `list`, `stats` and `--owed-by` need neither, and a
    --reconcile run reads the queue through `list`, so the import stays on the
    path that already required it.
    """
    generic = "One of the FINDINGS.schema.yaml kinds (`add --help` lists them)."
    if "add" not in (argv if argv is not None else sys.argv[1:]):
        return generic
    try:
        return "One of: " + ", ".join(k.value for k in validator_module().Kind) + "."
    except BaseException:
        return generic


def stage_help(argv: "Optional[List[str]]") -> str:
    """The --suspected-stage enum, spelled out - but only when the call is an
    `add` (kind_help says why the import stays on that path).

    Read from vf.Stage, never hand-typed: the literal here listed nine stages
    and went on listing nine after the enum gained `brief`, so the one flag
    that could record a walk ending outside the pipeline looked invalid to
    every agent composing the call from --help (ledger IMP-031; IMP-124 is the
    same fix for --kind).
    """
    generic = "Your GUESS at the owning stage (FINDINGS.schema.yaml lists them)."
    if "add" not in (argv if argv is not None else sys.argv[1:]):
        return generic
    try:
        stages = "|".join(s.value for s in validator_module().Stage)
        return f"Your GUESS at the owning stage ({stages})."
    except BaseException:
        return generic


def _derive_raised_by() -> str:
    skill_dir = os.environ.get("CLAUDE_SKILL_DIR")
    return f"sdlc-{Path(skill_dir).name}" if skill_dir else "user"


def _session_id_for(root: Path, raised_by: str) -> Optional[str]:
    """Best-effort: the RAISER's own state file carries the session id."""
    if not raised_by.startswith("sdlc-"):
        return None
    skill = raised_by[len("sdlc-"):]
    state = root / STATE_REL_TMPL.format(skill=skill)
    if not state.is_file():
        return None
    try:
        doc = yaml.safe_load(state.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if isinstance(doc, dict) and doc.get("session_id"):
        return str(doc["session_id"])
    return None


def cmd_add(args) -> int:
    vf = validator_module()
    root = resolve_project_root(args.project_root)
    path = _queue_path(args)

    # Every bad flag in ONE rejection. Reporting them one per run cost a
    # round-trip each, on a call an agent composes from a SKILL.md template
    # that enumerates none of the enums (ledger IMP-124; IMP-026 is the same
    # fix in lessons.py).
    problems: List[str] = []
    raised_by = args.raised_by or _derive_raised_by()
    if not RAISED_BY_RE.match(raised_by):
        problems.append(f"--raised-by {raised_by!r} must be 'sdlc-<skill>' or 'user'.")
    kinds = [k.value for k in vf.Kind]
    if args.kind not in kinds:
        problems.append(f"--kind {args.kind!r} is not one of: {', '.join(kinds)}.")
    stages = [s.value for s in vf.Stage]
    stage = args.suspected_stage
    if stage is not None:
        if stage in vf.LEGACY_STAGE_ALIASES:
            print(f"  note: --suspected-stage '{stage}' is an old spelling; recording "
                  f"'{vf.LEGACY_STAGE_ALIASES[stage]}'.")
            stage = vf.LEGACY_STAGE_ALIASES[stage]
        if stage not in stages:
            problems.append(f"--suspected-stage {stage!r} is not one of: {', '.join(stages)}.")
    summary = (args.summary or "").strip()
    if not summary:
        problems.append("--summary must not be empty.")
    evidence = [str(e) for e in (args.evidence or [])]
    if not 1 <= len(evidence) <= MAX_EVIDENCE:
        problems.append(f"evidence must be 1..{MAX_EVIDENCE} lines (got {len(evidence)}) - "
                        f"a finding nobody can judge is a rumour; a wall of text is one too.")
    for line in evidence:
        if len(line) > MAX_EVIDENCE_LEN:
            problems.append(f"an evidence line exceeds {MAX_EVIDENCE_LEN} chars - summarize, "
                            f"never paste whole artifacts.")
    for rel in args.related or []:
        if not FND_RE.match(rel):
            problems.append(f"--related {rel!r} is not an FND-NNN id.")
    if problems:
        return _reject_all(problems)

    surfaced: Dict[str, Any] = {}
    if args.qualified_task:
        surfaced["qualified_task"] = args.qualified_task
    if args.file:
        surfaced["file"] = args.file.replace("\\", "/")
    if args.symbol:
        surfaced["symbol"] = args.symbol
    if args.field_path:
        surfaced["field_path"] = args.field_path

    if not args.detected_by and vf.EXPECTED_COUNT_RE.search(summary):
        # Ledger IMP-104: the health check accepts a pinned count only from a
        # finding that names its check. Never blocks - the entry still records.
        print("  note: the summary pins expected_count but --detected-by is not set - the health "
              "check accepts a pinned count only from a finding that names its check "
              "(e.g. --detected-by data/validate_schema).")

    entry: Dict[str, Any] = {
        "fnd_id": None,   # minted by append_findings
        "raised_by": raised_by,
        "raised_at": _iso_utc_now(),
    }
    if args.detected_by:
        entry["detected_by"] = args.detected_by
    session_id = args.session_id or _session_id_for(root, raised_by)
    if session_id:
        entry["session_id"] = session_id
    if surfaced:
        entry["surfaced_at"] = surfaced
    entry["kind"] = args.kind
    entry["summary"] = summary
    entry["evidence"] = evidence
    entry["suspected_stage"] = stage
    entry["suspected_source"] = args.suspected_source.replace("\\", "/") if args.suspected_source else None
    if args.related:
        entry["related"] = list(args.related)
    entry["status"] = "open"
    entry["resolution"] = None

    try:
        added, skipped, pre_errors = append_findings(
            path, [entry], allow_duplicate=args.allow_duplicate, tolerate_existing=True)
    except QueueError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 2
    except EntryRejected as e:
        print("[FAIL] not recorded - the entry would not validate against "
              "FINDINGS.schema.yaml:", file=sys.stderr)
        for p in e.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    if skipped:
        _entry, dup = skipped[0]
        print(f"[OK] not recorded - duplicate of {dup} (same detected_by and summary, still open). "
              f"Pass --allow-duplicate if it really is a second defect.")
        return 0
    fnd_id, written = added[0]
    if pre_errors:
        print(f"WARNINGS (1) - the queue was already broken before this entry:")
        print(f"  - {path} fails its own validator ({len(pre_errors)} problem(s)), which "
              f"nothing here wrote. The finding above was recorded anyway; run "
              f"validate_findings.py and repair the queue, or /sdlc:repair cannot work "
              f"from it. First problem: {pre_errors[0]}")
    line = f"[OK] recorded {fnd_id} ({written['kind']}) - /sdlc:repair will localize it"
    if written.get("recurrence_of"):
        line += (f"  [repaired before as {written['recurrence_of']}; came back "
                 f"{written['recurrence']}x - re-invoke is the safer mode]")
    print(line)
    # Redraw the board of the project that owns this queue, not the cwd's: a
    # --path into another project would otherwise redraw the wrong board.
    qp = Path(path).resolve()
    owner = qp.parents[2] if qp.parent.name == "skills-state" and qp.parent.parent.name == ".claude" else root
    _refresh_statusboard(owner)
    return 0


def _load_for_read(path: Path):
    if not path.is_file():
        print(f"[OK] no findings queue at {path} - nothing recorded yet.")
        return None
    try:
        return load_findings(path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        print(f"[FAIL] cannot parse {path}: {e}", file=sys.stderr)
        return 2


def _filter(findings: List[Dict[str, Any]], args) -> List[Dict[str, Any]]:
    out = []
    statuses = set(args.status or [])
    if args.open:
        statuses |= set(OPEN_STATUSES)
    for f in findings:
        if not isinstance(f, dict):
            continue
        if statuses and f.get("status") not in statuses:
            continue
        if args.stage:
            res = f.get("resolution") or {}
            located = res.get("located_stage") if isinstance(res, dict) else None
            if args.stage not in (f.get("suspected_stage"), located):
                continue
        if args.raised_by and f.get("raised_by") != args.raised_by:
            continue
        out.append(f)
    return out


def _print_owed(data: Dict[str, Any], artifact: str, as_json: bool) -> int:
    rows = owed_findings(data, artifact)
    label = f"docs/{_artifact_name(artifact)}"
    if as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        return 0
    if not rows:
        print(f"[OK] no finding is waiting on {label} - nothing was handed off to this run.")
        return 0
    print(f"{len(rows)} finding(s) are waiting on {label} - this run is the re-invocation "
          f"they owe. Read them as the reason for the change, not as a reason to stop:")
    for r in rows:
        print(f"  {str(r['fnd_id']):<8} located={r.get('located_stage') or '-'}  "
              f"{str(r.get('summary') or '')[:110]}")
        if r.get("fix"):
            print(f"           fix: {str(r['fix'])[:160]}")
        for h in r["handoff"]:
            # basis: measured = read from the artifacts it names; inferred (or
            # unstated) = verify against the cited artifact before offering it.
            print(f"           handoff {h.get('key') or '(whole file)'} [{h.get('basis') or 'unstated'}]: "
                  f"{h['note'][:220]}")
            if h.get("retired"):
                # The literal token(s), not an authored consumer list (IMP-193) -
                # the reconcile sweeps its own artifact family for these itself.
                print(f"                    retired: {', '.join(h['retired'])}")
    return 0


def cmd_list(args) -> int:
    path = _queue_path(args)
    if args.as_json and not path.is_file():
        print("[]")   # machine readers get JSON even when nothing was recorded yet
        return 0
    data = _load_for_read(path)
    if data is None:
        return 0
    if data == 2:
        return 2
    if args.owed_by:
        return _print_owed(data, args.owed_by, args.as_json)
    rows = _filter(data.get("findings") or [], args)
    wanted = {str(i).strip().upper() for i in (getattr(args, "ids", None) or [])}
    if wanted:
        rows = [r for r in rows if str(r.get("fnd_id") or "").upper() in wanted]
    if args.as_json:
        print(json.dumps(rows, indent=2, ensure_ascii=False, default=str))
        return 0
    if not rows:
        print(f"[OK] {path}: no finding matches the filter "
              f"({len(data.get('findings') or [])} recorded).")
        return 0
    print(f"{len(rows)} finding(s) in {path}:")
    for f in rows:
        sa = f.get("surfaced_at") or {}
        where = ""
        if isinstance(sa, dict):
            where = sa.get("qualified_task") or sa.get("symbol") or sa.get("file") or ""
        res = f.get("resolution") or {}
        located = res.get("located_stage") if isinstance(res, dict) else None
        stage = f"suspected={f.get('suspected_stage') or '-'}"
        if located:
            stage += f" located={located}"
        rec = f" (came back: {f.get('recurrence_of')})" if f.get("recurrence_of") else ""
        print(f"  {f.get('fnd_id'):<8} {str(f.get('status')):<9} {str(f.get('kind')):<26} "
              f"{str(f.get('raised_by')):<12} {stage:<28} {where}")
        print(f"           {str(f.get('summary') or '')[:110]}{rec}")
    return 0


# =============================================================================
# plan - the open set, grouped into aggregates and ordered into stage-waves.
#
# A repair run used to assert its open set once and then work whatever its
# context window still held: one consumer project's runs went from twelve
# findings to one while twenty waited. The plan is the table the session's
# ONE gate shows, and the order its fix workers run in. Two inputs:
#   * the queue alone (provisional): clusters by the fields a finding already
#     carries - the same surfaced symbol, `related`, `recurrence_of`, the same
#     surfaced file - ordered by the stage the finding suspects (or, for a
#     triaged one, the stage its walk located);
#   * --from <dir> of localize reports (exact): the aggregates are the write
#     sets that share an artifact, joined transitively and directory-aware,
#     ordered by the pipeline stage of the located artifact, upstream first.
# =============================================================================

# Copied from setup/docs_index.py (_PIPELINE / _STAGE_OF): this script cannot
# import setup's module from a consumer install, the way the validators copy
# the WRN block rather than import it. Keep the two in step by hand.
PIPELINE = ("prd", "ux", "design", "data", "api", "arch", "test", "task", "code")
STAGE_OF_STEM = {"PRD": "prd", "UX": "ux", "DESIGN": "design", "DATA-MODEL": "data",
                 "API": "api", "ARCH": "arch", "TEST-STRATEGY": "test", "TASKS": "task",
                 "CODE-MANIFEST": "code"}
PLAN_CAP = 5   # findings per aggregate: a worker's context, not a policy


def artifact_stage(path: Any) -> Optional[str]:
    """'docs/ARCH__x.yaml' -> 'arch'; None for a path no stage owns."""
    name = _artifact_name(path)
    stem = name.split(".", 1)[0].split("__", 1)[0]
    return STAGE_OF_STEM.get(stem)


def stage_rank(stage_or_path: Any) -> int:
    """Pipeline position: `brief` (a hand-written upstream) is 0, an unknown
    stage sorts last, a docs/ path ranks as its owning stage."""
    s = str(stage_or_path or "")
    if s == "brief":
        return 0
    if s in PIPELINE:
        return PIPELINE.index(s) + 1
    stage = artifact_stage(s)
    return PIPELINE.index(stage) + 1 if stage else len(PIPELINE) + 1


def finding_stage(f: Dict[str, Any]) -> Optional[str]:
    res = f.get("resolution") or {}
    if isinstance(res, dict) and res.get("located_stage"):
        return str(res["located_stage"])
    return str(f["suspected_stage"]) if f.get("suspected_stage") else None


def _norm_docs(path: Any) -> Tuple[str, bool]:
    """('docs/<name>', is_directory) - a trailing slash or a bare directory
    name is a directory entry, which contains every path beneath it."""
    raw = str(path or "").replace("\\", "/").strip()
    is_dir = raw.endswith("/") or raw in ("docs", ".")
    raw = raw.rstrip("/")
    if raw in ("docs", "."):
        return "docs", True
    if "/" in raw:
        raw = raw.rsplit("/", 1)[1] if raw.startswith("docs/") and raw.count("/") == 1 else raw
    return (raw if raw.startswith("docs/") else f"docs/{raw}"), is_dir


def _overlap(a: Tuple[str, bool], b: Tuple[str, bool]) -> bool:
    if a[0] == b[0]:
        return True
    if a[1] and b[0].startswith(a[0] + "/"):
        return True
    if b[1] and a[0].startswith(b[0] + "/"):
        return True
    return False


def union_find(items: List[str], edges: List[Tuple[str, str, str]]) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """(parent map, {root: [why, ...]}) over `items`; an edge is (a, b, why)."""
    parent = {i: i for i in items}
    why: Dict[str, List[str]] = {i: [] for i in items}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b, reason in edges:
        if a not in parent or b not in parent:
            continue
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        keep, drop = sorted((ra, rb), key=_fnd_num)
        parent[drop] = keep
        why[keep] = why[keep] + why[drop] + [reason]
        why[drop] = []
    roots = {i: find(i) for i in items}
    return roots, {r: why[r] for r in set(roots.values())}


def _fnd_num(fnd_id: Any) -> int:
    try:
        return int(str(fnd_id).split("-")[1])
    except (IndexError, ValueError):
        return 10 ** 9


def _closable_from_doctor(path: Optional[str]) -> List[str]:
    """The ids the doctor's --provenance JSON says can be marked resolved."""
    if not path:
        return []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    hints = ((data.get("provenance") or {}).get("resolvable")) if isinstance(data, dict) else None
    out = []
    for h in hints or []:
        m = re.match(r"\s*(FND-\d{3,})", str(h))
        if m:
            out.append(m.group(1))
    return out


def provisional_plan(data: Dict[str, Any], closable: List[str]) -> Dict[str, Any]:
    """The plan from queue fields alone - exact after wave 1 (`--from`)."""
    open_set = [f for f in (data.get("findings") or [])
                if isinstance(f, dict) and f.get("status") in OPEN_STATUSES]
    by_id = {str(f.get("fnd_id")): f for f in open_set}
    ids = sorted(by_id, key=_fnd_num)
    owed, candidates = [], []
    for fid in ids:
        f = by_id[fid]
        res = f.get("resolution") or {}
        if f.get("status") == "triaged" and isinstance(res, dict) and res.get("mode") == "re-invoke":
            if fid not in closable:
                owed.append({"fnd": fid, "downstream_rerun": list(res.get("downstream_rerun") or [])})
            continue
        candidates.append(fid)
    edges: List[Tuple[str, str, str]] = []
    anchors: Dict[str, List[str]] = {}
    files: Dict[str, List[str]] = {}
    for fid in candidates:
        f = by_id[fid]
        a = _anchor(f)
        if a:
            anchors.setdefault(a, []).append(fid)
        sa = f.get("surfaced_at") or {}
        if isinstance(sa, dict) and sa.get("file"):
            files.setdefault(_norm_docs(sa["file"])[0], []).append(fid)
        for rel in f.get("related") or []:
            if str(rel) in by_id and str(rel) in candidates:
                edges.append((fid, str(rel), f"{fid} is related to {rel}"))
        rec = f.get("recurrence_of")
        if rec and str(rec) in candidates:
            edges.append((fid, str(rec), f"{fid} recurs {rec}"))
    for a, group in anchors.items():
        for other in group[1:]:
            edges.append((group[0], other, f"same symbol {a}"))
    for path, group in files.items():
        for other in group[1:]:
            edges.append((group[0], other, f"surfaced in {path}"))
    roots, why = union_find(candidates, edges)
    groups: Dict[str, List[str]] = {}
    for fid in candidates:
        groups.setdefault(roots[fid], []).append(fid)
    aggregates = []
    for root, members in groups.items():
        members = sorted(members, key=_fnd_num)
        stages = [finding_stage(by_id[m]) for m in members]
        rank = min((stage_rank(s) for s in stages if s), default=len(PIPELINE) + 1)
        aggregates.append({"findings": members, "located": [], "write_set": [],
                           "modes": {m: "?" for m in members}, "decisions": [],
                           "rank": rank, "stage": _stage_name(rank),
                           "merged_because": why.get(root, [])})
    return _assemble("queue", closable, [], owed, aggregates, [])


def load_localize_reports(directory: Path) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    reports: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as e:
            problems.append(f"{path.name}: unreadable ({e})")
            continue
        if not isinstance(doc, dict) or not FND_RE.match(str(doc.get("fnd_id") or "")):
            problems.append(f"{path.name}: no fnd_id - not a localize report")
            continue
        if not doc.get("located_stage") and not doc.get("located"):
            problems.append(f"{path.name}: names no located stage or artifact")
            continue
        reports[str(doc["fnd_id"])] = doc
    return reports, problems


def write_set(report: Dict[str, Any]) -> List[Tuple[str, bool]]:
    out: List[Tuple[str, bool]] = []
    for loc in report.get("located") or []:
        if isinstance(loc, dict) and loc.get("artifact"):
            out.append(_norm_docs(loc["artifact"]))
    for p in report.get("write_set") or []:
        out.append(_norm_docs(p))
    seen: set = set()
    uniq = []
    for item in out:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def _located_paths(report: Dict[str, Any]) -> List[str]:
    return [_norm_docs(loc["artifact"])[0] for loc in (report.get("located") or [])
            if isinstance(loc, dict) and loc.get("artifact")]


def _stage_name(rank: int) -> str:
    if rank == 0:
        return "brief"
    if 1 <= rank <= len(PIPELINE):
        return PIPELINE[rank - 1]
    return "unknown"


def aggregates_from_reports(reports: Dict[str, Dict[str, Any]], closable: List[str],
                            kinds: Optional[Dict[str, str]] = None) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
    """(aggregates, duplicates): union-find over write sets; two reports on
    one located symbol WITH THE SAME KIND fold into one (the later id is the
    duplicate - the recurrence rule's key, since two kinds on one symbol are
    two defects); an aggregate over PLAN_CAP is split by located stage, then
    by id."""
    kinds = kinds or {}
    ids = sorted((i for i in reports if i not in closable), key=_fnd_num)
    duplicates: List[Dict[str, str]] = []
    by_symbol: Dict[str, str] = {}
    kept: List[str] = []
    for fid in ids:
        rep = reports[fid]
        dup = rep.get("duplicate_of")
        if dup and str(dup) in reports and str(dup) != fid:
            duplicates.append({"fnd": fid, "of": str(dup), "why": "the worker found the same defect"})
            continue
        key = None
        for loc in rep.get("located") or []:
            if isinstance(loc, dict) and loc.get("symbol"):
                key = f"{_norm_docs(loc.get('artifact'))[0]}#{loc['symbol']}#{kinds.get(fid) or rep.get('kind') or ''}"
                break
        if key and key in by_symbol:
            duplicates.append({"fnd": fid, "of": by_symbol[key],
                               "why": f"same symbol {key.split('#')[1]}, same kind"})
            continue
        if key:
            by_symbol[key] = fid
        kept.append(fid)
    sets = {fid: write_set(reports[fid]) for fid in kept}
    edges: List[Tuple[str, str, str]] = []
    for i, a in enumerate(kept):
        for b in kept[i + 1:]:
            shared = [x[0] for x in sets[a] for y in sets[b] if _overlap(x, y)]
            if shared:
                edges.append((a, b, f"{a} and {b} both write {shared[0]}"))
    roots, why = union_find(kept, edges)
    groups: Dict[str, List[str]] = {}
    for fid in kept:
        groups.setdefault(roots[fid], []).append(fid)
    aggregates: List[Dict[str, Any]] = []
    for root, members in groups.items():
        members = sorted(members, key=_fnd_num)
        parts = _split(members, reports)
        for index, part in enumerate(parts):
            located = sorted({p for m in part for p in _located_paths(reports[m])})
            ws = sorted({p[0] for m in part for p in sets[m]})
            rank = min((stage_rank(reports[m].get("located_stage") or (located[0] if located else None))
                        for m in part), default=len(PIPELINE) + 1)
            decisions = [{"fnd": m, **{k: v for k, v in (reports[m].get("missing_decision") or {}).items()
                                       if k in ("question", "proposal", "basis")}}
                         for m in part if isinstance(reports[m].get("missing_decision"), dict)
                         and reports[m]["missing_decision"].get("question")]
            aggregates.append({"findings": part, "located": located, "write_set": ws,
                               "modes": {m: str(reports[m].get("proposed_mode") or "?") for m in part},
                               "decisions": decisions, "rank": rank, "stage": _stage_name(rank),
                               "merged_because": why.get(root, []) if len(parts) == 1 else
                               [w for w in why.get(root, []) if any(m in w for m in part)],
                               # the parts of one split group hold the same artifacts, so
                               # they run one after another - never side by side
                               "chain": root if len(parts) > 1 else None, "chain_index": index})
    return aggregates, duplicates


def _split(members: List[str], reports: Dict[str, Dict[str, Any]]) -> List[List[str]]:
    if len(members) <= PLAN_CAP:
        return [members]
    by_stage: Dict[int, List[str]] = {}
    for m in members:
        by_stage.setdefault(stage_rank(reports[m].get("located_stage")), []).append(m)
    parts: List[List[str]] = []
    for rank in sorted(by_stage):
        chunk = by_stage[rank]
        for i in range(0, len(chunk), PLAN_CAP):
            parts.append(chunk[i:i + PLAN_CAP])
    return parts


def order_waves(aggregates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Waves of equal effective rank, upstream first. An aggregate whose located
    artifact is downstream of another aggregate's write set waits for it even
    when the two are disjoint - a downstream stamp must see final upstream
    bytes. Stable tie-break: the lowest finding id."""
    aggs = sorted(aggregates, key=lambda a: (a["rank"], _fnd_num(a["findings"][0])))
    effective = {id(a): a["rank"] for a in aggs}
    changed = True
    while changed:
        changed = False
        for a in aggs:
            for b in aggs:
                if a is b:
                    continue
                if any(stage_rank(la) > stage_rank(wb) for la in a["located"] for wb in b["write_set"]) \
                        and effective[id(a)] <= effective[id(b)]:
                    effective[id(a)] = effective[id(b)] + 1
                    changed = True
                # the parts of one split group share artifacts: part k+1 waits for part k
                if a.get("chain") and a.get("chain") == b.get("chain") \
                        and a.get("chain_index", 0) > b.get("chain_index", 0) \
                        and effective[id(a)] <= effective[id(b)]:
                    effective[id(a)] = effective[id(b)] + 1
                    changed = True
    waves: Dict[int, List[Dict[str, Any]]] = {}
    for a in aggs:
        waves.setdefault(effective[id(a)], []).append(a)
    out = []
    for n, rank in enumerate(sorted(waves), start=1):
        members = sorted(waves[rank], key=lambda a: (a["rank"], _fnd_num(a["findings"][0])))
        for k, a in enumerate(members):
            a["id"] = f"A{sum(len(waves[r]) for r in sorted(waves) if r < rank) + k + 1}"
        out.append({"wave": n, "stage": _stage_name(min(a["rank"] for a in members)),
                    "aggregates": members})
    return out


def _assemble(source: str, closable: List[str], duplicates: List[Dict[str, str]],
              owed: List[Dict[str, Any]], aggregates: List[Dict[str, Any]],
              unplaced: List[Dict[str, str]]) -> Dict[str, Any]:
    return {"source": source, "planned_at": _iso_utc_now(), "close_first": sorted(closable, key=_fnd_num),
            "duplicates": duplicates, "owed": owed, "waves": order_waves(aggregates),
            "unplaced": unplaced}


def render_plan(plan: Dict[str, Any]) -> str:
    n_agg = sum(len(w["aggregates"]) for w in plan["waves"])
    n_open = (len(plan["close_first"]) + len(plan["duplicates"]) + len(plan["owed"])
              + len(plan["unplaced"]) + sum(len(a["findings"]) for w in plan["waves"] for a in w["aggregates"]))
    tag = "from: localize reports" if plan["source"] == "localize" else \
        "provisional: from queue fields - exact after wave 1"
    lines = [f"Repair plan - {n_open} open finding(s): {len(plan['close_first'])} close first, "
             f"{n_agg} aggregate(s) in {len(plan['waves'])} stage-wave(s), "
             f"{len(plan['duplicates'])} duplicate(s)  [{tag}]"]
    for fid in plan["close_first"]:
        lines.append(f"CLOSE FIRST  {fid}  every artifact its re-runs rewrite was rebuilt after the fix")
    for w in plan["waves"]:
        lines.append(f"WAVE {w['wave']} - {w['stage']}")
        for a in w["aggregates"]:
            where = ", ".join(a["located"]) if a["located"] else "(located after wave 1)"
            extra = len(a["write_set"]) - len(a["located"])
            if extra > 0:
                where += f" + {extra} downstream"
            modes = ", ".join(a["modes"][m] + ("*" if any(d["fnd"] == m for d in a["decisions"]) else "")
                              for m in a["findings"])
            lines.append(f"  {a['id']:<4} {', '.join(a['findings']):<34} {where:<48} {modes}")
            for d in a["decisions"]:
                lines.append(f"       * {d['fnd']} needs one decision: {d.get('question')} - proposal: {d.get('proposal')}")
            for why in a["merged_because"]:
                lines.append(f"       ({why})")
    for d in plan["duplicates"]:
        lines.append(f"DUPLICATE  {d['fnd']} = {d['of']} ({d['why']})")
    if plan["owed"]:
        for o in plan["owed"]:
            first = o["downstream_rerun"][0] if o["downstream_rerun"] else "(no command recorded)"
            lines.append(f"Handed off already  {o['fnd']}  first: {first}")
    else:
        lines.append("Handed off already: none")
    for u in plan["unplaced"]:
        lines.append(f"UNPLACED  {u['fnd']}  {u['why']}")
    if plan["waves"]:
        lines.append("NEXT: answer the plan gate; each stage-wave starts after the previous one drains.")
    elif n_open:
        lines.append("NEXT: nothing to dispatch - close the close-first findings and record the owed ones.")
    else:
        lines.append("NEXT: nothing open - the queue is clean.")
    return "\n".join(lines)


def cmd_plan(args) -> int:
    path = _queue_path(args)
    data = _load_for_read(path)
    if data is None:
        data = empty_queue()
    if data == 2:
        return 2
    closable = list(args.close_first or []) + _closable_from_doctor(args.doctor_json)
    if args.from_dir:
        directory = Path(args.from_dir)
        if not directory.is_dir():
            print(f"[FAIL] cannot plan - {directory} is not a directory of localize reports.",
                  file=sys.stderr)
            return 2
        reports, problems = load_localize_reports(directory)
        if problems:
            print(f"[FAIL] {len(problems)} localize report(s) cannot be read - re-dispatch those "
                  f"findings before planning:")
            for p in problems:
                print(f"  - {p}")
            return 1
        open_ids = [str(f.get("fnd_id")) for f in (data.get("findings") or [])
                    if isinstance(f, dict) and f.get("status") in OPEN_STATUSES]
        owed = []
        unplaced = []
        for fid in sorted(open_ids, key=_fnd_num):
            f = next(x for x in data["findings"] if str(x.get("fnd_id")) == fid)
            res = f.get("resolution") or {}
            if fid in reports or fid in closable:
                continue
            if f.get("status") == "triaged" and isinstance(res, dict) and res.get("mode") == "re-invoke":
                owed.append({"fnd": fid, "downstream_rerun": list(res.get("downstream_rerun") or [])})
            else:
                unplaced.append({"fnd": fid, "why": "no localize report"})
        kinds = {str(f.get("fnd_id")): str(f.get("kind") or "") for f in (data.get("findings") or [])
                 if isinstance(f, dict)}
        aggregates, duplicates = aggregates_from_reports(reports, closable, kinds)
        plan = _assemble("localize", [c for c in closable if c in open_ids or c in reports],
                         duplicates, owed, aggregates, unplaced)
    else:
        plan = provisional_plan(data, closable)
    if args.as_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False, default=str))
    else:
        print(render_plan(plan))
    return 0


def cmd_reopen(args) -> int:
    vf = validator_module()
    path = _queue_path(args)
    fnd_id = str(args.fnd_id).strip().upper()
    if not FND_RE.match(fnd_id):
        return _reject(f"{fnd_id!r} is not an FND-NNN id.")
    try:
        data = load_findings(path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        print(f"[FAIL] cannot read {path}: {e}", file=sys.stderr)
        return 2
    # The candidate write is judged against what the queue ALREADY has wrong,
    # same rule as append_findings: only what THIS call introduces can reject
    # it (line 477).
    _doc, pre_errors, _warns = vf.validate_raw(data, str(path))
    updated, problems = reopen_finding(data, fnd_id)
    if problems:
        return _reject_all(problems)
    _doc, errors, _warns = vf.validate_raw(data, str(path))
    new_errors = [e for e in errors if e not in pre_errors]
    if new_errors:
        print(f"[FAIL] not reopened - the result would not validate against "
              f"FINDINGS.schema.yaml:", file=sys.stderr)
        for e in new_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    try:
        dump_findings(data, path)
    except OSError as e:
        print(f"[FAIL] cannot write {path}: {e}", file=sys.stderr)
        return 2
    if updated.get("resolution"):
        detail = f"resolution kept (mode={updated['resolution'].get('mode')})"
    else:
        detail = "resolution stripped, walk recorded as a new evidence line"
    print(f"[OK] {fnd_id} reopened -> status={updated['status']} ({detail})")
    root = resolve_project_root(getattr(args, "project_root", None))
    qp = Path(path).resolve()
    owner = qp.parents[2] if qp.parent.name == "skills-state" and qp.parent.parent.name == ".claude" else root
    _refresh_statusboard(owner)
    return 0


def cmd_validate_upgrade(path: Path) -> int:
    """Raise this queue's OWN findings_file_version to NEW_FILE_VERSION - but
    only when it already validates with ZERO errors AND zero warnings, gated
    or not (ledger IMP-196: "the floor gets a way up"). Today nothing ever
    raises an existing queue: a fresh queue is born at NEW_FILE_VERSION, but
    an older project's queue sits below it forever, so every gated check on
    it stays a warning nobody has to fix. This is the one sanctioned writer of
    findings_file_version besides a fresh `empty_queue()` - never a partial
    raise, never on a queue that still owes a fix."""
    vf = validator_module()
    try:
        data = load_findings(path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        print(f"[FAIL] cannot read {path}: {e}", file=sys.stderr)
        return 2
    doc, errors, warnings = vf.validate_raw(data, str(path))
    current = str(data.get("findings_file_version") or "1")
    if doc is None or errors:
        print(f"[FAIL] not upgraded - {path} does not pass validation yet "
              f"({len(errors)} problem(s)); run `findings.py validate` for the detail, fix them, "
              f"then retry --upgrade.", file=sys.stderr)
        return 1
    if warnings:
        print(f"[FAIL] not upgraded - {path} validates but still carries {len(warnings)} warning(s); "
              f"raising findings_file_version from {current!r} to {NEW_FILE_VERSION!r} needs ZERO, "
              f"not just no errors - every gated check must actually be clean, not merely "
              f"not-yet-blocking. First: {warnings[0]}", file=sys.stderr)
        return 1
    if vf.file_version_major({"findings_file_version": current}) >= \
            vf.file_version_major({"findings_file_version": NEW_FILE_VERSION}):
        print(f"[OK] {path} is already at findings_file_version {current!r} "
              f"(>= {NEW_FILE_VERSION!r}) - nothing to raise.")
        return 0
    data["findings_file_version"] = NEW_FILE_VERSION
    try:
        dump_findings(data, path)
    except OSError as e:
        print(f"[FAIL] cannot write {path}: {e}", file=sys.stderr)
        return 2
    print(f"[OK] {path} raised from findings_file_version {current!r} to {NEW_FILE_VERSION!r} - "
          f"every gated check passed with zero warnings.")
    return 0


def cmd_validate(args) -> int:
    path = _queue_path(args)
    if getattr(args, "upgrade", False):
        return cmd_validate_upgrade(path)
    validator = None
    for cand in _validator_candidates():
        if cand.is_file():
            validator = cand
            break
    if validator is None:
        print("ERROR: validate_findings.py is not reachable from findings.py.", file=sys.stderr)
        return 3
    r = subprocess.run([sys.executable, str(validator), "--path", str(path)],
                       env={**os.environ, "PYTHONUTF8": "1"})
    return r.returncode


def _bump(table: Dict[str, int], key: Any) -> None:
    k = str(key) if key is not None else "-"
    table[k] = table.get(k, 0) + 1


def print_stats(data: Dict[str, Any]) -> None:
    """Counts by status / kind / mode / raiser, then the suspected-stage vs
    located-stage matrix per raiser. Counts only - this travels in
    `lessons.py export` reports, and a count never leaks project content."""
    findings = [f for f in (data.get("findings") or []) if isinstance(f, dict)]
    by_status: Dict[str, int] = {}
    by_kind: Dict[str, int] = {}
    by_mode: Dict[str, int] = {}
    by_raiser: Dict[str, int] = {}
    matrix: Dict[str, Dict[Tuple[str, str], int]] = {}
    recurrences = 0
    for f in findings:
        _bump(by_status, f.get("status"))
        _bump(by_kind, f.get("kind"))
        _bump(by_raiser, f.get("raised_by"))
        res = f.get("resolution") if isinstance(f.get("resolution"), dict) else None
        if res:
            _bump(by_mode, res.get("mode"))
            located = res.get("located_stage")
            if located:
                raiser = str(f.get("raised_by") or "-")
                cell = (str(f.get("suspected_stage") or "-"), str(located))
                matrix.setdefault(raiser, {})
                matrix[raiser][cell] = matrix[raiser].get(cell, 0) + 1
        if f.get("recurrence_of"):
            recurrences += 1

    def _fmt(table: Dict[str, int]) -> str:
        return ", ".join(f"{k}={v}" for k, v in sorted(table.items(), key=lambda kv: (-kv[1], kv[0]))) or "none"

    print(f"Findings: {len(findings)} recorded, {recurrences} of them a defect that came back.")
    print(f"  by status:    {_fmt(by_status)}")
    print(f"  by kind:      {_fmt(by_kind)}")
    print(f"  by fix mode:  {_fmt(by_mode)}")
    print(f"  by raiser:    {_fmt(by_raiser)}")
    if not matrix:
        print("  suspected vs located: no resolved finding names a located_stage yet.")
        return
    print("  suspected stage -> located stage (resolved findings; a cell off the "
          "diagonal is a raiser whose guess was wrong):")
    for raiser, cells in sorted(matrix.items()):
        total = sum(cells.values())
        right = sum(n for (s, l), n in cells.items() if s == l)
        print(f"    {raiser}: {right} of {total} guesses matched the located stage")
        for (s, l), n in sorted(cells.items(), key=lambda kv: (-kv[1], kv[0])):
            mark = "  " if s == l else "->"
            print(f"      {s:<8} {mark} {l:<8} {n}")


def cmd_stats(args) -> int:
    path = _queue_path(args)
    data = _load_for_read(path)
    if data is None:
        return 0
    if data == 2:
        return 2
    print_stats(data)
    return 0


def _add_global_opts(p: argparse.ArgumentParser, *, sub: bool = False) -> None:
    # On a subparser the default is SUPPRESSED so `findings.py --path X add ...`
    # and `findings.py add ... --path X` both work: a subparser default would
    # otherwise overwrite the value the top-level parser already parsed.
    default = argparse.SUPPRESS if sub else None
    p.add_argument("--project-root", default=default,
                   help="Consumer project root (default: $CLAUDE_PROJECT_DIR, then cwd).")
    p.add_argument("--path", default=default,
                   help=f"Queue path override (default: <root>/{QUEUE_REL.as_posix()}).")


def _refresh_statusboard(project_root=None) -> None:
    """Best-effort: keep the generated statusboard in step with this queue.

    An entry recorded here is one of the things the ambient board carries
    verbatim, so a board drawn before the append stays wrong until the next
    docs/ edit happens to trigger the index hook. Silent and never fatal - the
    board is a convenience, and failing to draw it must not fail a capture.
    """
    import subprocess
    from pathlib import Path as _Path

    root = _Path(project_root) if project_root else _Path.cwd()
    script = root / ".claude" / "sdlc" / "statusboard.py"
    if not script.is_file():
        return
    try:
        subprocess.call([sys.executable, str(script), "--path", str(root)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(
        description="Record and inspect FND-NNN findings (.claude/skills-state/sdlc-findings.yaml).")
    _add_global_opts(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="Record one finding (validated before it lands).")
    p.add_argument("--raised-by", default=None,
                   help="sdlc-<skill> or user (default: derived from $CLAUDE_SKILL_DIR, else user).")
    p.add_argument("--kind", required=True, help=kind_help(argv))
    p.add_argument("--summary", required=True, help="One line: what is wrong.")
    p.add_argument("--evidence", action="append", default=None,
                   help=f"Repeatable, 1..{MAX_EVIDENCE} lines, each <= {MAX_EVIDENCE_LEN} chars.")
    p.add_argument("--suspected-stage", default=None, help=stage_help(argv))
    p.add_argument("--suspected-source", default=None, help="docs/ path you suspect.")
    p.add_argument("--symbol", default=None, help="The smallest thing implicated (work_unit, TST, entity).")
    p.add_argument("--qualified-task", default=None, help="<cid>/TSK-NNN that hit it, if any.")
    p.add_argument("--file", default=None, help="docs/ file where it became visible.")
    p.add_argument("--field-path", default=None, help="Dotted path inside that file.")
    p.add_argument("--detected-by", default=None,
                   help="Check or phase that saw it (e.g. arch/validate_schema, ux/phase-2). Used to dedupe.")
    p.add_argument("--related", action="append", default=None, help="FND-NNN, repeatable.")
    p.add_argument("--session-id", default=None,
                   help="Raiser's session id (default: read from the raiser's state file).")
    p.add_argument("--allow-duplicate", action="store_true",
                   help="Record even when an open finding has the same detected_by + summary.")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="Print findings.")
    p.add_argument("--open", action="store_true", help="Only open + triaged.")
    p.add_argument("--status", action="append", default=None, help="Repeatable status filter.")
    p.add_argument("--stage", default=None, help="Suspected OR located stage.")
    p.add_argument("--raised-by", default=None)
    p.add_argument("--owed-by", default=None, metavar="ARTIFACT",
                   help="Only the open re-invoke findings that still owe this docs/ file, with the "
                        "handoff notes repair left for it - what a --reconcile run reads. "
                        "Ignores the other filters.")
    p.add_argument("--id", action="append", default=None, metavar="FND-NNN", dest="ids",
                   help="Only these finding ids (repeatable) - what a --reconcile run reads when "
                        "an upstream changelog line the delta quotes cites a finding: a resolved "
                        "finding's resolution is that item's decision, offered first (IMP-101). "
                        "Combines with the other filters.")
    p.add_argument("--json", action="store_true", dest="as_json")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("plan", help="The open set grouped into aggregates and ordered into "
                                    "stage-waves, upstream first - the table /sdlc:repair's "
                                    "plan gate shows. Provisional from the queue alone; exact "
                                    "with --from <dir of localize reports>.")
    p.add_argument("--from", dest="from_dir", default=None, metavar="DIR",
                   help="Directory of wave-1 localize reports (<FND>.yaml); the aggregates are "
                        "then the write sets that share an artifact.")
    p.add_argument("--doctor-json", default=None, metavar="PATH",
                   help="The doctor's provenance snapshot (its --provenance --json output, written "
                        "at Phase 2); its resolvable hints become the close-first list.")
    p.add_argument("--close-first", action="extend", nargs="+", default=None, metavar="FND-NNN",
                   help="Ids to close before any wave (adds to the doctor's hints).")
    p.add_argument("--json", action="store_true", dest="as_json")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("reopen", help="Flip a resolved/wontfix/deferred finding back into "
                                      "scope, mode-aware (the doctor sweep's --provenance report "
                                      "names the id when one is owed a reopen).")
    p.add_argument("fnd_id", metavar="FND-NNN")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_reopen)

    p = sub.add_parser("validate", help="Run validate_findings.py on the queue.")
    p.add_argument("--upgrade", action="store_true",
                   help="Instead of just reporting, raise findings_file_version to the current "
                        "floor (NEW_FILE_VERSION) when the queue already passes every gated check "
                        "with ZERO warnings; a no-op if already there, refused (exit 1) while any "
                        "warning remains.")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("stats", help="Counts + suspected-vs-located matrix per raiser.")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_stats)

    parsed = ap.parse_args(argv)
    return parsed.func(parsed)


if __name__ == "__main__":
    sys.exit(main())
