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
    findings.py validate
    findings.py stats
  Global: [--project-root <dir>] [--path <queue path>] (before or after the verb)

`add` mints the next id (max(last_ids.FND, highest present) + 1), refuses to
record a second copy of a still-open defect (same detected_by + summary) unless
--allow-duplicate, and stamps recurrence_of / recurrence when a resolved or
wontfix finding already named the same symbol or task with the same kind.

Exit codes:
    0 — recorded (or deliberately not recorded: a duplicate), listed, or valid.
    1 — the entry was rejected: it would not validate, or a flag value is not
        in the schema's enum. Nothing was written.
    2 — the queue could not be read or parsed (or fails validation before the
        append — repair it first), or could not be written.
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
NEW_FILE_VERSION = "2"

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
                  "basis": str(h.get("basis") or "unstated")}
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
                    stamp_recurrence: bool = True):
    """Validate-then-append. Returns (added, skipped):
    added   = [(fnd_id, entry)] in the order they were written
    skipped = [(entry, duplicate_of_id)] for entries a still-open twin covers

    The whole candidate queue (existing rows + every new entry) is validated
    before the file is touched. An invalid EXISTING queue raises QueueError
    (repair it first); an invalid NEW entry raises EntryRejected and nothing
    is written — not even the entries that were fine.
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
    _doc, errors, _warns = vf.validate_raw(data, str(path))
    if errors:
        raise QueueError(
            f"{path} already fails validation ({len(errors)} problem(s)); nothing appended - "
            f"run validate_findings.py and repair the queue first. First problem: {errors[0]}"
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
        return added, skipped

    _doc, errors, _warns = vf.validate_raw(data, str(path))
    if errors:
        raise EntryRejected(errors)
    try:
        dump_findings(data, path)
    except OSError as e:
        raise QueueError(f"cannot write {path}: {e}")
    return added, skipped


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

    raised_by = args.raised_by or _derive_raised_by()
    if not RAISED_BY_RE.match(raised_by):
        return _reject(f"--raised-by {raised_by!r} must be 'sdlc-<skill>' or 'user'.")
    kinds = [k.value for k in vf.Kind]
    if args.kind not in kinds:
        return _reject(f"--kind {args.kind!r} is not one of: {', '.join(kinds)}.")
    stages = [s.value for s in vf.Stage]
    stage = args.suspected_stage
    if stage is not None:
        if stage in vf.LEGACY_STAGE_ALIASES:
            print(f"  note: --suspected-stage '{stage}' is an old spelling; recording "
                  f"'{vf.LEGACY_STAGE_ALIASES[stage]}'.")
            stage = vf.LEGACY_STAGE_ALIASES[stage]
        if stage not in stages:
            return _reject(f"--suspected-stage {stage!r} is not one of: {', '.join(stages)}.")
    summary = (args.summary or "").strip()
    if not summary:
        return _reject("--summary must not be empty.")
    evidence = [str(e) for e in (args.evidence or [])]
    if not 1 <= len(evidence) <= MAX_EVIDENCE:
        return _reject(f"evidence must be 1..{MAX_EVIDENCE} lines (got {len(evidence)}) - "
                       f"a finding nobody can judge is a rumour; a wall of text is one too.")
    for line in evidence:
        if len(line) > MAX_EVIDENCE_LEN:
            return _reject(f"an evidence line exceeds {MAX_EVIDENCE_LEN} chars - summarize, "
                           f"never paste whole artifacts.")
    for rel in args.related or []:
        if not FND_RE.match(rel):
            return _reject(f"--related {rel!r} is not an FND-NNN id.")

    surfaced: Dict[str, Any] = {}
    if args.qualified_task:
        surfaced["qualified_task"] = args.qualified_task
    if args.file:
        surfaced["file"] = args.file.replace("\\", "/")
    if args.symbol:
        surfaced["symbol"] = args.symbol
    if args.field_path:
        surfaced["field_path"] = args.field_path

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
        added, skipped = append_findings(path, [entry], allow_duplicate=args.allow_duplicate)
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


def cmd_validate(args) -> int:
    path = _queue_path(args)
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
    p.add_argument("--kind", required=True)
    p.add_argument("--summary", required=True, help="One line: what is wrong.")
    p.add_argument("--evidence", action="append", default=None,
                   help=f"Repeatable, 1..{MAX_EVIDENCE} lines, each <= {MAX_EVIDENCE_LEN} chars.")
    p.add_argument("--suspected-stage", default=None,
                   help="Your GUESS at the owning stage (prd|ux|design|data|api|arch|test|task|code).")
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
    p.add_argument("--json", action="store_true", dest="as_json")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("validate", help="Run validate_findings.py on the queue.")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("stats", help="Counts + suspected-vs-located matrix per raiser.")
    _add_global_opts(p, sub=True)
    p.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
