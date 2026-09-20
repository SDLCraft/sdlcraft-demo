#!/usr/bin/env python3
"""Pydantic v2 validator for .claude/skills-state/sdlc-findings.yaml — the
cross-skill FND-NNN queue every sdlc stage may append to (through findings.py)
and /sdlc:repair resolves.

Canonical schema (with the rationale behind each field): FINDINGS.schema.yaml
in this directory. This module enforces it. findings.py imports the models
below and validates every entry BEFORE it is appended, so a hand-shaped row
can never reach the queue through the helper.

Beyond field types it checks the invariants that keep the queue trustworthy:

  * FND ids are unique, well-formed, and never above last_ids.FND (a counter
    that has fallen behind is how two skills reissue the same id).
  * A resolved / wontfix / deferred finding carries a resolution block; an
    open one does not; a triaged one may carry one ONLY while a re-invoke is
    in progress (mode re-invoke) — partial progress is recorded, nothing else.
  * duplicate_of is present exactly when status == duplicate, and points at a
    different finding that exists in this file.
  * evidence is a non-empty, bounded LIST — a finding nobody can judge without
    re-running the failing command is not evidence, it is a rumour.
  * Version-gated (CLAUDE.md section 10) — files stamped
    findings_file_version >= 2 get an ERROR, older files a WARNING, for:
    located_stage: code on anything but a wontfix closure (generated code is
    never the source of a spec defect; a wontfix may name it as a mis-raised
    closure, with stale_tasks naming the task(s) code's own plan gate
    schedules for regeneration), a re-invoke with no downstream_rerun, an
    artifacts_touched entry outside docs/, a resolved finding whose
    propagation hops are not all verified, a recurrence_of that names no
    finding in this file. A wontfix with located_stage: code and no
    stale_tasks is WARNED (never blocked): the closer named the cause but
    forgot the task id code needs to schedule the rebuild.
  * Version-gated on its own, higher floor (findings_file_version >= 3 —
    above the version-2 corpus this check must not retroactively block,
    CLAUDE.md section 10): a re-invoke resolution with an empty
    artifacts_touched, below findings_file_version 3 a WARNING only —
    doctor.py's "should be reopened" hint narrows to the upstream this
    field names, so an empty list falls back to its old unfiltered hint.
  * Same higher floor, same reason (findings_file_version >= 3, one floor -
    not a second one): a RESOLVED finding whose fix changed a named symbol
    (symbols_changed non-empty) or whose mode is re-invoke, carrying an empty
    resolution.sites_considered - the forward-propagation checklist persisted
    as a record instead of only printed (ledger IMP-196). A `deferred` entry
    with no `reason`, or an `unaffected` entry with no `how`, is gated the
    same way.
  * `findings.py validate --upgrade` is the only writer that ever raises an
    existing queue's findings_file_version - it does so only when every gated
    check above already passes with ZERO warnings (not merely zero errors).
  * Legacy stage spellings ('data-model' -> data, 'test-strategy' -> test)
    are read as their canonical form with a WARNING, never rejected.
  * resolution.handoff (the notes a re-invoke leaves for the reconcile runs it
    owes) is checked as WARNINGS only - its shape, a non-re-invoke mode, a
    note addressed to a file the finding does not owe, a malformed `retired`
    token list, and a note that enumerates two or more foreign TST-/TSK- ids
    with retirement wording and no `retired` list (the FND-104 shape, ledger
    IMP-193).
  * A finding that pins `expected_count` with no detected_by is WARNED, never
    rejected: doctor.py accepts a pinned count only from a finding that names
    its check (references/accepted-deviance.md).

Run from the project root:

    python validate_findings.py
    python validate_findings.py --path .claude/skills-state/sdlc-findings.yaml
    python validate_findings.py --stats        # counts + suspected->located matrix

Exit codes:
    0 — schema valid; the queue is internally consistent (warnings allowed).
    1 — schema invalid (pydantic error) or an invariant is violated.
    2 — could not read or parse the file (missing, bad YAML, etc.).
    3 — required dependency missing (pydantic v2 or pyyaml).
"""

from __future__ import annotations

import argparse
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# User-facing output (CLAUDE.md 14). Three verdict tags, two finding sections,
# one NEXT block - identical across every SDLC script, because the person
# reading them knows only "there is a pipeline and I run it in order".
# Canonical guidance: sdlc/skills/prd/references/reporting-to-the-user.md
# =============================================================================

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"

def join_ids(ids, limit=12):
    """Render a grouped finding's id list. Capped, because a line nobody
    finishes reading has told the user nothing."""
    ids = [str(i) for i in ids]
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown} (+{len(ids) - limit} more)"



def _emit_finding(item, detail_cap=5):
    """One finding. A (headline, details) pair renders as a grouped finding:
    the class in one sentence, then a capped sample. A line nobody finishes
    reading has told the user nothing."""
    if isinstance(item, tuple):
        head, details = item
        print(f"  - {head}")
        for d in list(details)[:detail_cap]:
            print(f"      * {d}")
        if len(details) > detail_cap:
            print(f"      * (+{len(details) - detail_cap} more of the same)")
    else:
        print(f"  - {item}")


def print_findings(blocking, warnings, blocking_header="MUST FIX BEFORE 'complete'"):
    """The two canonical sections. A WARNING never blocks, and says so."""
    if blocking:
        print(f"\n{blocking_header} ({len(blocking)}):")
        for b in blocking:
            _emit_finding(b)
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}) - none of these block the next skill:")
        for w in warnings:
            _emit_finding(w)


def print_next(*lines, show_glossary=True):
    """Close with what to type next. The glossary pointer only appears when
    there was something to decode."""
    print(f"\nNEXT: {lines[0]}")
    for extra in lines[1:]:
        print(f"      {extra}")
    if show_glossary:
        print(f"      What these labels mean: {GLOSSARY_PATH}")


try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: pyyaml is required.\nInstall with:  pip install pyyaml", file=sys.stderr)
    sys.exit(3)

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
except ImportError:  # pragma: no cover
    print("ERROR: pydantic v2 is required.\nInstall with:  pip install 'pydantic>=2'", file=sys.stderr)
    sys.exit(3)

DEFAULT_PATH = Path(".claude/skills-state/sdlc-findings.yaml")
FND_RE = re.compile(r"^FND-\d{3,}$")
RAISED_BY_RE = re.compile(r"^(sdlc-[a-z0-9-]+|user)$")
MAX_EVIDENCE = 5
MAX_EVIDENCE_LEN = 300
# An accepted deviance pins its count in the summary (doctor.py reads the same
# pattern); it is applied only when detected_by names the check (ledger IMP-104).
EXPECTED_COUNT_RE = re.compile(r"expected_count:\s*(\d+)")

# The version at which the checks marked "v2" below turn from WARNING into
# ERROR (CLAUDE.md section 10). Files written before that version keep
# validating; they just hear about it.
GATED_VERSION = 2

# IMP-195: doctor.py's "should be reopened" hint narrows to the upstream a
# re-invoke resolution's artifacts_touched actually names; an empty list
# falls back to the old unfiltered hint, silently. This check is floored
# ABOVE GATED_VERSION on its own (CLAUDE.md section 10, "floor above the
# corpus"): the corpus already has resolved re-invoke findings stamped
# findings_file_version 2 with no artifacts_touched recorded (findings.py's
# NEW_FILE_VERSION has stamped "2" since before this check existed), and a
# floor equal to GATED_VERSION would retroactively block them the instant
# this check shipped.
ARTIFACTS_TOUCHED_GATED_VERSION = 3

# IMP-196: `resolution.sites_considered` (the forward-propagation checklist,
# persisted) reuses this SAME floor - one gated version for both fields, not
# a fourth constant, since both exist to keep a re-invoke resolution honest
# about what it actually touched vs. only looked at.
SITES_CONSIDERED_GATED_VERSION = ARTIFACTS_TOUCHED_GATED_VERSION

# IMP-193: an authored enumeration of "which items use this retired token" is
# unreliable in both directions (FND-104 named five tests without the token
# and missed five that had it; FND-107 repeated the pattern) - warn when a
# handoff note reads like one and carries no `retired` list instead. Warn-only,
# no version gate: a new, hand-written field, not a blocking rule.
RETIRE_VOCAB_RE = re.compile(r"\b(retired|retire|removed|renamed|no longer)\b", re.IGNORECASE)
FOREIGN_ID_RE = re.compile(r"\b(?:TST|TSK)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b")

# Spellings older writers used for two stages. Read as the canonical stage,
# reported as a warning, never rejected: the aicf queue carried them.
LEGACY_STAGE_ALIASES = {
    "data-model": "data",
    "test-strategy": "test",
}


class Kind(str, Enum):
    # ---- the contract or the spec does not determine the behaviour ---------
    contract_underdetermined = "contract_underdetermined"
    contract_contradiction = "contract_contradiction"
    test_contradicts_contract = "test_contradicts_contract"
    impossible_acceptance = "impossible_acceptance"
    unrealizable_item = "unrealizable_item"
    # ---- something a downstream artifact needs is not defined upstream -----
    missing_requirement = "missing_requirement"
    missing_operation = "missing_operation"
    missing_entity = "missing_entity"
    missing_dependency_edge = "missing_dependency_edge"
    upstream_incomplete = "upstream_incomplete"
    # ---- copies and claims that no longer match their source ---------------
    drifted_embed = "drifted_embed"
    stale_downstream_claim = "stale_downstream_claim"
    wrong_path = "wrong_path"
    # ---- raised by the doctor sweep ----------------------------------------
    validator_error = "validator_error"
    crosscheck_broken_ref = "crosscheck_broken_ref"
    dangling_reference = "dangling_reference"
    # ---- fallback ----------------------------------------------------------
    other = "other"


class Stage(str, Enum):
    prd = "prd"
    ux = "ux"
    design = "design"
    data = "data"
    api = "api"
    arch = "arch"
    test = "test"
    task = "task"
    code = "code"
    # Not a pipeline stage: a hand-written document that the pipeline CONSUMES.
    # PRD `conventions.upstream_briefs` makes these first-class (docs/architecture.md
    # and the like, written by a person before any skill runs, read by arch/api/data),
    # and a localization walk can legitimately end at one - the artifact that
    # consumed it is then correct about a source that was wrong. Without this
    # value such a finding had to be filed under the consuming stage, which
    # misreports where the defect lived and drops the second brief when two are
    # implicated (ledger IMP-031). Note that briefs carry no
    # `metadata.<name>_version`, so the surgical version bump does not apply to
    # them - see FINDINGS.schema.yaml.
    brief = "brief"


class Status(str, Enum):
    open = "open"
    triaged = "triaged"
    resolved = "resolved"
    wontfix = "wontfix"
    deferred = "deferred"
    duplicate = "duplicate"


class Mode(str, Enum):
    surgical = "surgical"
    additive = "additive"       # repair authored the new downstream item(s) itself
    re_invoke = "re-invoke"
    none = "none"


class Hop(str, Enum):
    source = "source"
    embed = "embed"
    code = "code"
    # An artifact the fix propagated INTO that is neither the source nor a
    # write-time copy of it - a TEST-STRATEGY acceptance, a DATA-MODEL trace,
    # a UX shard. Without it distinct hops flattened to `source` and the
    # audit trail leaned on prose (ledger IMP-047, aicf LSN-027).
    downstream = "downstream"


class SiteDisposition(str, Enum):
    edited = "edited"
    resliced = "resliced"
    unaffected = "unaffected"
    deferred = "deferred"


class SiteConsidered(BaseModel):
    """One artifact the forward-propagation checklist named, and what became
    of it (IMP-196). Distinct from PropagationHop: a hop records a place the
    fix DID land, verified; a site_considered entry records that an artifact
    was CHECKED, whatever the outcome - including "looked at, unaffected"."""
    model_config = ConfigDict(extra="allow")
    artifact: str
    disposition: SiteDisposition
    reason: Optional[str] = None
    how: Optional[str] = None


class SurfacedAt(BaseModel):
    model_config = ConfigDict(extra="allow")
    qualified_task: Optional[str] = None
    file: Optional[str] = None
    symbol: Optional[str] = None
    field_path: Optional[str] = None


class PropagationHop(BaseModel):
    model_config = ConfigDict(extra="allow")
    hop: Hop
    target: str
    verified_at: Optional[str] = None
    how: Optional[str] = None


class Resolution(BaseModel):
    model_config = ConfigDict(extra="allow")
    by: str
    at: str
    located_stage: Optional[Stage] = None
    mode: Optional[Mode] = None
    reason: Optional[str] = None
    artifacts_touched: List[str] = Field(default_factory=list)
    downstream_rerun: List[str] = Field(default_factory=list)
    stale_tasks: List[str] = Field(default_factory=list)
    propagation: Optional[List[PropagationHop]] = None
    fields_changed: Optional[List[str]] = None
    symbols_changed: Optional[List[str]] = None
    sites_considered: Optional[List[SiteConsidered]] = None
    summary: Optional[str] = None
    # What the localization walk concluded each owed re-invocation should do,
    # per downstream item: [{artifact: docs/<file>, key: <item key | null>,
    # note: <why it moved + the proposed disposition>}]. The stage's
    # --reconcile reads it through `findings.py list --owed-by` - the reason for
    # the change, carried on disk to a fresh session. Typed loosely on purpose:
    # repair writes this block by hand, and one malformed note must not stop
    # every producer's append; the shape is checked in cross_checks, as warnings.
    handoff: Optional[Any] = None


class Finding(BaseModel):
    model_config = ConfigDict(extra="allow")

    fnd_id: str
    raised_by: str
    raised_at: str
    detected_by: Optional[str] = None
    session_id: Optional[str] = None
    surfaced_at: Optional[SurfacedAt] = None
    kind: Kind
    summary: str
    evidence: List[str]
    suspected_stage: Optional[Stage] = None
    suspected_source: Optional[str] = None
    related: Optional[List[str]] = None
    recurrence_of: Optional[str] = None
    recurrence: Optional[int] = None
    status: Status
    duplicate_of: Optional[str] = None
    resolution: Optional[Resolution] = None

    @field_validator("fnd_id")
    @classmethod
    def _id_format(cls, v: str) -> str:
        if not FND_RE.match(v):
            raise ValueError(f"{v!r} must match FND-NNN (>=3 digits)")
        return v

    @field_validator("raised_by")
    @classmethod
    def _raised_by_format(cls, v: str) -> str:
        if not RAISED_BY_RE.match(v or ""):
            raise ValueError(
                f"{v!r} must be 'sdlc-<skill>' (the stage that noticed it) or 'user'"
            )
        return v

    @field_validator("summary")
    @classmethod
    def _summary_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("summary must not be empty")
        return v

    @field_validator("evidence")
    @classmethod
    def _evidence_bounded(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError(
                "evidence must have at least one line - a finding nobody can judge "
                "without re-running the failing command is not actionable"
            )
        if len(v) > MAX_EVIDENCE:
            raise ValueError(f"evidence has {len(v)} lines; keep it to at most {MAX_EVIDENCE}")
        # Per-line LENGTH is checked in cross_checks, version-gated (CLAUDE.md
        # section 10): a field-level error here would hard-fail legacy queues
        # whose lines predate the cap. findings.py enforces it on every new add.
        return v

    @field_validator("recurrence")
    @classmethod
    def _recurrence_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 1:
            raise ValueError("recurrence counts how many times this defect came back; it starts at 1")
        return v


class FindingsFile(BaseModel):
    model_config = ConfigDict(extra="allow")

    findings_file_version: str
    last_updated: Optional[str] = None
    last_ids: Dict[str, int]
    findings: List[Finding]

    @field_validator("findings_file_version", mode="before")
    @classmethod
    def _version_as_str(cls, v: Any) -> str:
        # A hand-typed `2` loads as an int; the schema says string.
        return str(v)

    @field_validator("last_ids")
    @classmethod
    def _has_fnd_counter(cls, v: Dict[str, int]) -> Dict[str, int]:
        if "FND" not in v:
            raise ValueError("last_ids must carry an FND counter")
        return v


# --------------------------------------------------------------------------
# Version + legacy handling
# --------------------------------------------------------------------------

def file_version_major(raw: Any) -> int:
    """The major of findings_file_version, defaulting to 1 for anything odd."""
    if not isinstance(raw, dict):
        return 1
    v = raw.get("findings_file_version", "1")
    m = re.match(r"^\s*(\d+)", str(v))
    return int(m.group(1)) if m else 1


def normalize_legacy(raw: Any) -> List[str]:
    """Rewrite legacy stage spellings IN PLACE on the raw mapping and return
    one warning per rewrite. Runs before pydantic so the enum never sees them."""
    warnings: List[str] = []
    if not isinstance(raw, dict):
        return warnings
    for f in raw.get("findings") or []:
        if not isinstance(f, dict):
            continue
        fid = f.get("fnd_id", "?")
        v = f.get("suspected_stage")
        if isinstance(v, str) and v in LEGACY_STAGE_ALIASES:
            f["suspected_stage"] = LEGACY_STAGE_ALIASES[v]
            warnings.append(
                f"{fid}: suspected_stage '{v}' is an old spelling; read as "
                f"'{LEGACY_STAGE_ALIASES[v]}' - write the stage name next time"
            )
        res = f.get("resolution")
        if isinstance(res, dict):
            v = res.get("located_stage")
            if isinstance(v, str) and v in LEGACY_STAGE_ALIASES:
                res["located_stage"] = LEGACY_STAGE_ALIASES[v]
                warnings.append(
                    f"{fid}: resolution.located_stage '{v}' is an old spelling; read as "
                    f"'{LEGACY_STAGE_ALIASES[v]}' - write the stage name next time"
                )
    return warnings


# --------------------------------------------------------------------------
# Cross-checks
# --------------------------------------------------------------------------

def cross_checks(doc: FindingsFile, version: int) -> Tuple[List[str], List[str]]:
    """Invariants pydantic cannot express field-by-field.

    Returns (errors, warnings). A check marked gated fires as an error when
    the file is stamped at or above GATED_VERSION and as a warning below it.
    """
    errors: List[str] = []
    warnings: List[str] = []
    gated = errors if version >= GATED_VERSION else warnings
    gate_note = "" if version >= GATED_VERSION else (
        f" (not blocking: this file is version {version}; it blocks from "
        f"findings_file_version {GATED_VERSION})"
    )
    touched_gated = errors if version >= ARTIFACTS_TOUCHED_GATED_VERSION else warnings
    touched_gate_note = "" if version >= ARTIFACTS_TOUCHED_GATED_VERSION else (
        f" (not blocking: this file is version {version}; it blocks from "
        f"findings_file_version {ARTIFACTS_TOUCHED_GATED_VERSION})"
    )
    ids = [f.fnd_id for f in doc.findings]

    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate fnd_id(s): {', '.join(dupes)}")

    counter = int(doc.last_ids.get("FND", 0))
    for f in doc.findings:
        n = int(f.fnd_id.split("-")[1])
        if n > counter:
            errors.append(
                f"{f.fnd_id} exceeds last_ids.FND={counter} - the counter has fallen "
                f"behind; reconcile to max(counter, highest id) before appending"
            )

    known = set(ids)
    for f in doc.findings:
        fid = f.fnd_id
        res = f.resolution
        closed = f.status in (Status.resolved, Status.wontfix, Status.deferred)

        # ---- status <-> resolution ------------------------------------------
        if closed and res is None:
            errors.append(
                f"{fid}: status={f.status.value} but resolution is null - "
                f"record what changed (or why not), or set status back to open/triaged"
            )
        if f.status is Status.open and res is not None:
            errors.append(f"{fid}: status=open but a resolution block is present")
        if f.status is Status.triaged and res is not None and res.mode is not Mode.re_invoke:
            errors.append(
                f"{fid}: status=triaged carries a resolution block with mode="
                f"{res.mode.value if res.mode else 'null'} - only a re-invoke in progress "
                f"may record partial progress on a triaged finding; finish it (resolved) "
                f"or drop the block"
            )
        if f.status is Status.duplicate and res is not None:
            errors.append(f"{fid}: status=duplicate but a resolution block is present")
        if f.status is Status.deferred and res is not None:
            if res.mode is not Mode.none:
                errors.append(
                    f"{fid}: status=deferred requires resolution.mode: none "
                    f"(got {res.mode.value if res.mode else 'null'}) - a deferral changes no artifact"
                )
            if not (res.reason or "").strip():
                errors.append(
                    f"{fid}: status=deferred requires resolution.reason - say why the "
                    f"defect stays unfixed, so the next reader does not re-triage it"
                )

        # ---- duplicates -----------------------------------------------------
        if f.status is Status.duplicate and not f.duplicate_of:
            errors.append(f"{fid}: status=duplicate requires duplicate_of")
        if f.duplicate_of:
            if f.status is not Status.duplicate:
                errors.append(f"{fid}: duplicate_of is set but status is {f.status.value}")
            if f.duplicate_of == fid:
                errors.append(f"{fid}: duplicate_of points at itself")
            elif f.duplicate_of not in known:
                errors.append(f"{fid}: duplicate_of {f.duplicate_of} is not in this file")

        # ---- evidence line length (gated: legacy queues predate the cap) ----
        long_lines = [i for i, line in enumerate(f.evidence) if len(str(line)) > MAX_EVIDENCE_LEN]
        if long_lines:
            gated.append(
                f"{fid}: evidence line(s) {join_ids(long_lines, 3)} exceed {MAX_EVIDENCE_LEN} chars - "
                f"summarize, never paste whole artifacts{gate_note}"
            )

        # ---- recurrence + related links ------------------------------------
        if f.recurrence_of:
            if f.recurrence_of == fid:
                errors.append(f"{fid}: recurrence_of points at itself")
            elif f.recurrence_of not in known:
                gated.append(
                    f"{fid}: recurrence_of {f.recurrence_of} is not in this file - "
                    f"name the earlier finding this one repeats, or drop the key{gate_note}"
                )
        for rel in f.related or []:
            if rel not in known:
                warnings.append(f"{fid}: related {rel} is not in this file")

        # ---- a pinned count needs its check named (warning only, IMP-104) ---
        pinned = " ".join(str(x or "") for x in (f.summary, res.reason if res else None,
                                                  res.summary if res else None))
        if EXPECTED_COUNT_RE.search(pinned) and not (f.detected_by or "").strip():
            warnings.append(
                f"{fid}: summary pins expected_count but detected_by is empty - the health check "
                f"accepts a pinned count only from a finding that names its check "
                f"(e.g. detected_by: data/validate_schema)"
            )

        if res is None:
            continue

        # ---- resolution content (gated) -------------------------------------
        # Allowed on a wontfix closure only: a mis-raised finding whose walk
        # found every upstream contract already correct and generated code
        # alone diverging. Every other status still refuses it - repair never
        # patches code, so located_stage: code cannot be a fix's destination.
        if res.located_stage is Stage.code and f.status is not Status.wontfix:
            gated.append(
                f"{fid}: resolution.located_stage is 'code' - generated code is never the "
                f"source of a spec defect; localize to the artifact it was built from, or "
                f"close the finding wontfix as mis-raised{gate_note}"
            )
        if (res.located_stage is Stage.code and f.status is Status.wontfix
                and not res.stale_tasks):
            warnings.append(
                f"{fid}: resolution.located_stage is 'code' on a wontfix with no stale_tasks - "
                f"name the owning qualified task id(s) so code's own plan gate can schedule the "
                f"rebuild (resolution.stale_tasks), or the mis-raised closure is invisible to "
                f"/sdlc:code"
            )
        if res.mode is Mode.re_invoke and not res.downstream_rerun:
            gated.append(
                f"{fid}: mode=re-invoke but downstream_rerun is empty - a re-invoke that "
                f"names no command sequence leaves the user guessing which skills to re-run; "
                f"list them in pipeline order{gate_note}"
            )
        if res.mode is Mode.re_invoke and not res.artifacts_touched:
            touched_gated.append(
                f"{fid}: mode=re-invoke but artifacts_touched is empty - doctor.py's "
                f"'should be reopened' hint narrows to the upstream this resolution actually "
                f"touched; an empty list falls back to today's unfiltered hint{touched_gate_note}"
            )

        # ---- sites_considered (IMP-196; reuses the artifacts_touched floor,
        # never a fourth version) ---------------------------------------------
        trigger = None
        if f.status is Status.resolved and res.mode is Mode.re_invoke:
            trigger = "mode=re-invoke"
        elif f.status is Status.resolved and (res.symbols_changed or []):
            trigger = "symbols_changed is non-empty"
        if trigger and not res.sites_considered:
            touched_gated.append(
                f"{fid}: resolution.sites_considered is empty but {trigger} - every artifact the "
                f"forward-propagation checklist named must be recorded edited | resliced | "
                f"unaffected | deferred before the finding closes{touched_gate_note}"
            )
        for i, sc in enumerate(res.sites_considered or []):
            if sc.disposition is SiteDisposition.deferred and not (sc.reason or "").strip():
                touched_gated.append(
                    f"{fid}: resolution.sites_considered[{i}] ({sc.artifact}) is deferred with no "
                    f"reason - say why it stays untouched on purpose{touched_gate_note}"
                )
            if sc.disposition is SiteDisposition.unaffected and not (sc.how or "").strip():
                touched_gated.append(
                    f"{fid}: resolution.sites_considered[{i}] ({sc.artifact}) is unaffected with no "
                    f"how - a sweep count stands for the reason (e.g. \"sweep <token>: 0 hits\"){touched_gate_note}"
                )
        if res.mode is Mode.additive:
            # Additive means repair authored every new downstream item itself,
            # so nothing is owed to a re-invocation (ledger IMP-060).
            if res.downstream_rerun:
                gated.append(
                    f"{fid}: mode=additive but downstream_rerun names "
                    f"{len(res.downstream_rerun)} command(s) - additive means nothing is "
                    f"owed downstream; if a re-run is owed, the mode is re-invoke{gate_note}"
                )
            if f.status is Status.resolved and not any(
                    h.hop == "downstream" for h in (res.propagation or [])):
                gated.append(
                    f"{fid}: mode=additive resolved with no hop: downstream - an additive "
                    f"fix authored at least one downstream item; record each as a "
                    f"propagation hop of kind downstream{gate_note}"
                )
        bad_paths = [a for a in res.artifacts_touched if not str(a).replace("\\", "/").startswith("docs/")]
        if bad_paths:
            gated.append(
                f"{fid}: artifacts_touched names {len(bad_paths)} path(s) outside docs/ "
                f"({join_ids(bad_paths, 3)}) - repair edits only the artifact chain; scripts "
                f"and scratch files are not artifacts{gate_note}"
            )
        if f.status is Status.resolved and res.propagation:
            unverified = [h.target for h in res.propagation if not (h.verified_at or "").strip()]
            if unverified:
                gated.append(
                    f"{fid}: status=resolved but {len(unverified)} propagation hop(s) have no "
                    f"verified_at ({join_ids(unverified, 3)}) - a fix that was not confirmed on "
                    f"disk at every hop is still triaged{gate_note}"
                )

        # ---- handoff notes (warnings only: a new field, written by hand) ----
        if res.handoff is not None:
            warnings.extend(handoff_problems(fid, res))
    return errors, warnings


def _owed_by(res: Resolution) -> Optional[set]:
    """The file names this resolution still owes, computed by findings.py -
    beside this validator in the plugin and in .claude/sdlc/ alike. None when
    it cannot be imported: the check is then skipped, never guessed."""
    try:
        here = str(Path(__file__).resolve().parent)
        if here not in sys.path:
            sys.path.insert(0, here)
        import findings as _findings  # noqa: WPS433 - one implementation, lazily
    except ImportError:
        return None
    return set(_findings.owed_artifacts(res.model_dump(mode="json")))


HANDOFF_BASES = ("measured", "inferred")


def handoff_problems(fid: str, res: Resolution) -> List[str]:
    """Why a handoff note would never reach the reconcile run it is meant for."""
    if not isinstance(res.handoff, list):
        return [f"{fid}: resolution.handoff should be a list of {{artifact, key, note}} entries - "
                f"as written, no reconcile run can read it"]
    if res.mode is not Mode.re_invoke:
        mode = res.mode.value if res.mode else "mode-less"
        return [f"{fid}: resolution.handoff is set on a {mode} fix - only a re-invoke owes a "
                f"downstream run, so no reconcile will read these notes; move the reasoning into "
                f"resolution.summary"]
    out: List[str] = []
    owed = _owed_by(res)
    for i, h in enumerate(res.handoff):
        artifact = str(h.get("artifact") or "").replace("\\", "/") if isinstance(h, dict) else ""
        if not artifact.startswith("docs/") or not str(h.get("note") or "").strip():
            out.append(f"{fid}: resolution.handoff[{i}] needs artifact: docs/<file> and a non-empty "
                       f"note - the reconcile run finds its notes by that file name")
            continue
        name = artifact.split("#", 1)[0].rsplit("/", 1)[-1]
        if owed is not None and name not in owed:
            out.append(f"{fid}: resolution.handoff[{i}] is addressed to {artifact}, which this finding "
                       f"does not owe (no downstream_rerun command rewrites it, no unverified hop "
                       f"names it) - no reconcile will read it; address the file an owed command rewrites")
        # A note is one string in one register: without a basis a cold reconcile
        # cannot tell a fact read from the artifacts from an analogy the walk never
        # checked, and one such siting was wrong against the files the same note
        # cited (ledger IMP-082, aicf LSN-064). Warn-only: hand-written field.
        basis = h.get("basis")
        if basis is None or str(basis).strip() == "":
            out.append(f"{fid}: resolution.handoff[{i}] has no basis - say measured (read from the "
                       f"artifacts the note names) or inferred (an analogy the reconcile run must "
                       f"verify before it writes), so a cold session knows which notes to check first")
        elif str(basis) not in HANDOFF_BASES:
            out.append(f"{fid}: resolution.handoff[{i}] basis {basis!r} is not measured | inferred")

        # ---- retired: the literal token, not an authored consumer list (IMP-193) --
        note_text = str(h.get("note") or "")
        retired = h.get("retired")
        if retired is not None:
            if not (isinstance(retired, list) and retired
                    and all(isinstance(t, str) and t.strip() for t in retired)):
                out.append(f"{fid}: resolution.handoff[{i}].retired should be a list of one or more "
                           f"non-empty token strings - as written, no reconcile sweep can read it")
        else:
            ids = {m.group(0) for m in FOREIGN_ID_RE.finditer(note_text)}
            ids.discard(str(h.get("key") or ""))
            if len(ids) >= 2 and RETIRE_VOCAB_RE.search(note_text):
                out.append(
                    f"{fid}: resolution.handoff[{i}] note names {len(ids)} other TST-/TSK- id(s) "
                    f"({join_ids(sorted(ids), 5)}) and reads like a retirement, but carries no "
                    f"retired list - naming specific consumers here is the FND-104 shape (wrong in "
                    f"both directions); put the retired token(s) in handoff[{i}].retired and let the "
                    f"reconcile's own sweep find the real consumers"
                )
    return out


def validate_raw(raw: Any, label: str) -> Tuple[Optional[FindingsFile], List[str], List[str]]:
    """Validate an already-loaded mapping. Returns (doc | None, errors, warnings).

    findings.py calls this on the queue it is about to write, so an entry that
    would fail here never lands on disk. Legacy stage spellings are normalized
    in place (a warning each).
    """
    if not isinstance(raw, dict):
        return None, [f"{label}: top level must be a mapping"], []
    warnings = normalize_legacy(raw)
    try:
        doc = FindingsFile.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " -> ".join(str(x) for x in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return None, errors, warnings
    errs, warns = cross_checks(doc, file_version_major(raw))
    return doc, errs, warnings + warns


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="Validate the sdlc findings queue.")
    ap.add_argument("--path", default=str(DEFAULT_PATH), help=f"Path to the queue (default: {DEFAULT_PATH}).")
    ap.add_argument("--stats", action="store_true",
                    help="After validating, print counts by status/kind/mode/raiser and the "
                         "suspected-stage vs located-stage matrix (same as findings.py stats).")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"[FAIL] cannot read {path}: file not found", file=sys.stderr)
        return 2
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        print(f"[FAIL] cannot parse {path}: {e}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print(f"[FAIL] {path}: top level must be a mapping", file=sys.stderr)
        return 2

    doc, errors, warnings = validate_raw(raw, str(path))
    if doc is None:
        print(f"[FAIL] {path} does not match the findings schema. /sdlc:repair "
              f"cannot read it until these fields are fixed:")
        print_findings(errors, warnings, blocking_header="MUST FIX BEFORE 'complete'")
        print_next("fix the fields above by hand (findings.py never writes a row that "
                   "fails this check), then re-run this validator.")
        return 1
    if errors:
        print(f"[FAIL] {path} contradicts itself in {len(errors)} place(s):")
        print_findings(errors, warnings, blocking_header="MUST FIX BEFORE 'complete'")
        print_next("fix the entries above, then re-run this validator.")
        return 1

    by_status: Dict[str, int] = {}
    for f in doc.findings:
        by_status[f.status.value] = by_status.get(f.status.value, 0) + 1
    tally = ", ".join(f"{k}={v}" for k, v in sorted(by_status.items())) or "empty"
    print(f"[OK] {path} is valid - {len(doc.findings)} recorded problem(s) "
          f"({tally})")
    print_findings([], warnings)
    if args.stats:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import findings as _findings  # noqa: WPS433 - one implementation, lazily
            print()
            _findings.print_stats(raw)
        except ImportError:
            print("\n(stats unavailable: findings.py is not beside this validator)")
    open_now = [f.fnd_id for f in doc.findings if f.status in (Status.open, Status.triaged)]
    if open_now:
        print_next(f"/sdlc:repair  ({len(open_now)} still open: "
                   f"{join_ids(open_now)})", show_glossary=bool(warnings))
    else:
        print_next("nothing required - no finding is open.", show_glossary=bool(warnings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
