#!/usr/bin/env python3
"""Pipeline health sweep for the SDLC docs/ chain — the `doctor` behind
/sdlc:repair --check and behind /sdlc:code's component-boundary check.

Every sdlc-* skill validates its OWN artifact at write time, and
crosscheck_artifacts.py validates references ACROSS artifacts. Neither runs
unless someone invokes the owning skill, so a chain can rot quietly between
stages — a hand-edited ARCH, a PRD requirement renamed after TEST-STRATEGY
copied it, a task graph whose embeds no longer match their source. This script
runs the whole set in one pass, reports each check's CAPTURED NUMERIC EXIT CODE,
and can turn every failure into an FND-NNN finding for /sdlc:repair to triage
(through findings.py — the queue's only writer — so every entry is validated
before it lands).

Two depths:

  --artifact FILE  ONE artifact's validator, with the accepted-deviance registry
            applied - the depth a skill's upstream gate needs (repeatable; a
            shard names its family's system file, a TASKS shard itself)
  --quick   only the cross-artifact linter (crosscheck_artifacts.py). Cheap
            enough to run at every component boundary during codegen, which is
            exactly what /sdlc:code does with it. Catches the desyncs that
            appear WHILE a long run is in flight (a mid-run hand-edit, a repair
            pass that landed between components).
  (default) the full sweep: every skill validator against its canonical
            artifact, every TASKS__*.json shard, the cross-artifact linter, and
            the docs-index dangling-reference gate (the installed
            .claude/sdlc/docs_index.py, or the plugin's own copy - READ-ONLY,
            --check - when none is installed; the label says which and why).

What a check's output means here:
  * Only lines under a BLOCKING section header (MUST FIX / BROKEN REFERENCES /
    WHAT FAILED / TO FINISH IT) are defects. Lines under WARNINGS or
    "Not checked yet" are never turned into findings by default.
  * Each check also reports how many WARNINGS it printed (exit-neutral).
    --warnings-as-findings records the cross-artifact subset of those as
    findings: task [check 20] (a task embed no longer matches its source) and
    [check 23] (a task built while its test is deferred), and ux/arch warnings
    that name another artifact.
  * Accepted deviance: a wontfix finding whose summary carries
    `expected_count: N` for a check + artifact turns that check's failure into
    "accepted (N, unchanged)" while the blocking-line count stays N. The moment
    the count moves, the check fails again. The artifact is matched by file
    NAME, so the finding is honoured whether the sweep runs with
    `--docs-dir docs` or an absolute path, and every finding this script
    mints carries the repo-relative POSIX path whatever form it ran with.
  * Awaiting re-invocation: an open|triaged re-invoke finding still owes the
    commands in its downstream_rerun, and every propagation hop without a
    verified_at. A failing check on an artifact those name is labelled
    "awaiting re-invocation per FND-NNN (<command>)" - it stays red (the
    artifact is not consumable) but is never recorded again, and when every
    failure is owed the NEXT line names the owed command instead of repair.
  * --provenance compares every artifact's metadata.upstream_provenance hashes
    with the current upstream files and prints one [stale] line per drift
    (a warning — staleness is a known state, not a defect), plus a hint for
    each triaged re-invoke finding whose downstream artifacts have all been
    rebuilt since the fix.

Every check runs BARE and its exit code is captured directly — never read an
exit status after a pipe (CLAUDE.md section 11: an upstream validator once ran
false-green for a full fix-plan cycle behind `cmd | tail -5`, masking 294 real
errors). A pass/fail paraphrase is never recorded in place of the number.

Usage:
    python doctor.py [--docs-dir docs] [--quick | --artifact FILE ...] [--json] [--provenance]
    python doctor.py --emit-findings                      # append FND-NNN entries to the
                                                          # queue of the project that holds
                                                          # --docs-dir (never the cwd's)
    python doctor.py --emit-findings .claude/skills-state/sdlc-findings.yaml
    python doctor.py --emit-findings --warnings-as-findings

Exit codes:
    0 — every check that ran passed (checks skipped for a missing artifact
        count as passed; this script must be runnable at any pipeline stage).
        Warnings, accepted deviance and provenance drift never change this.
    1 — at least one check failed.
    2 — could not read the docs dir, a required tool is missing from the
        skill tree, or the findings queue could not be read/written.
    3 — required dependency missing (pyyaml).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
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
    the class in one sentence, then a capped sample. The headline always
    carries the full count, so a capped list never hides how much there is."""
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
    print("[doctor] missing dependency: pyyaml (pip install pyyaml)", file=sys.stderr)
    sys.exit(3)

HERE = Path(__file__).resolve().parent
SKILLS_DIR = HERE.parent  # sdlc/skills/
sys.path.insert(0, str(HERE))
import findings as fq  # noqa: E402  - the queue's only writer

DEFAULT_FINDINGS = Path(".claude/skills-state/sdlc-findings.yaml")
MAX_EVIDENCE = fq.MAX_EVIDENCE
MAX_EVIDENCE_LEN = fq.MAX_EVIDENCE_LEN

# Statuses the sweep deduplicates against. Wider than findings.py's default
# (open + triaged): the same checks run every sweep, so a defect a person
# already dismissed (wontfix / deferred / duplicate) must not be re-minted.
DEDUPE_STATUSES = ("open", "triaged", "wontfix", "deferred", "duplicate")

# skill folder -> its canonical artifact under docs/. A skill whose artifact is
# absent is SKIPPED, not failed: the sweep must be usable halfway through the
# pipeline, when the later artifacts legitimately do not exist yet.
CANONICAL: List[Tuple[str, str]] = [
    ("prd", "PRD.yaml"),
    ("ux", "UX.yaml"),
    ("design", "DESIGN.yaml"),
    ("data", "DATA-MODEL.yaml"),
    ("api", "API.yaml"),
    ("arch", "ARCH.yaml"),
    ("test", "TEST-STRATEGY.yaml"),
    ("task", "TASKS.json"),
    ("code", "CODE-MANIFEST.json"),
]

# /sdlc:<skill> [<cid>]  ->  the artifact the re-invocation rewrites. Defined in
# findings.py, which every reader of "what a finding still owes" shares.
SKILL_ARTIFACT = fq.SKILL_ARTIFACT


class Check:
    """One executed check and the number it returned."""

    def __init__(self, name: str, target: str) -> None:
        self.name = name
        self.target = target
        self.exit: Optional[int] = None   # None => skipped
        self.summary: str = ""
        self.output: str = ""
        self.blocking: List[str] = []     # lines under a blocking section
        self.warning_lines: List[str] = []
        self.warnings: int = 0            # the validator's own WARNINGS (N)
        self.accepted: Optional[str] = None   # "accepted (N, unchanged) per FND-007"
        self.accepted_by: Optional[str] = None
        self.located: Optional[str] = None    # the docs/ file the first defect line
                                              # names, when it is not `target` - the
                                              # row is labelled with the path the
                                              # check RAN ON (ledger IMP-069)
        self.awaiting: Optional[str] = None   # "awaiting re-invocation per FND-080
                                              # (/sdlc:task x --reconcile)": the artifact
                                              # is one an open re-invoke finding still
                                              # owes - red, known, never re-minted
                                              # (ledger IMP-077)
        self.awaiting_by: Optional[str] = None
        self.awaiting_cmds: List[str] = []

    @property
    def skipped(self) -> bool:
        return self.exit is None

    @property
    def failed(self) -> bool:
        return self.exit is not None and self.exit != 0 and self.accepted is None

    def line(self) -> str:
        if self.skipped:
            return f"  [skip] {self.name:<28} {self.target}  ({self.summary})"
        tag = "[FAIL]" if self.failed else "[OK]  "
        extra = f", {self.warnings} warning(s)" if self.warnings else ""
        acc = f" - {self.accepted}" if self.accepted else ""
        wait = f" - {self.awaiting}" if self.awaiting else ""
        loc = f"  (first defect is in {self.located})" if self.located else ""
        return f"  {tag} {self.name:<28} {self.target}  exit {self.exit}{extra}{acc}{wait}{loc}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "target": self.target, "exit": self.exit,
            "summary": self.summary, "warnings": self.warnings,
            "blocking": len(self.blocking), "accepted": self.accepted,
            "located": self.located, "awaiting": self.awaiting,
        }


def run_bare(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str]:
    """Run a command with NO pipe and return (captured exit code, output).

    subprocess gives us the child's real returncode, which is the whole point:
    the shell idiom this replaces (`cmd | tail`) reports the LAST pipeline
    stage's status and silently hides a red validator.
    """
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=str(cwd) if cwd else None)
    except OSError as e:
        return 2, f"could not execute: {e}"
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


# --------------------------------------------------------------------------
# Output parsing — by SECTION, never by keyword
# --------------------------------------------------------------------------

HEADER_RE = re.compile(r"^([A-Z][A-Za-z '\-]{3,}?)\s*\((\d+)\)")
BLOCKING_HEADERS = ("MUST FIX", "BROKEN REFERENCES", "WHAT FAILED", "TO FINISH IT")
ITEM_RE = re.compile(r"^\s*-\s+(.*)$")
DETAIL_RE = re.compile(r"^\s*\*\s+(.*)$")
VERDICT_RE = re.compile(r"^\[(OK|DRAFT|FAIL)\]")


def parse_sections(text: str) -> Tuple[List[str], List[str], int]:
    """(blocking items, warning items, warnings count from the header).

    Validators and the linter all print the same two sections (CLAUDE.md 14).
    A defect is a `- ` item under a blocking header — or directly under a
    [FAIL] verdict line, which is how a schema (pydantic) failure prints;
    everything under WARNINGS, "Not checked yet:" or NEXT: is not one. Grouped
    items keep their `* ` detail lines, appended after the head so evidence
    still reads.
    """
    blocking: List[str] = []
    warnings: List[str] = []
    warn_count = 0
    section: Optional[str] = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("NEXT:"):
            section = "next"
            continue
        if line.startswith("Not checked yet"):
            section = "notes"
            continue
        m = HEADER_RE.match(line)
        if m:
            name = m.group(1).strip()
            if name.startswith("WARNINGS"):
                section = "warnings"
                warn_count = int(m.group(2))
            elif any(name.startswith(h) for h in BLOCKING_HEADERS):
                section = "blocking"
            else:
                section = None
            continue
        v = VERDICT_RE.match(line)
        if v:
            section = "blocking" if v.group(1) == "FAIL" else None
            continue
        if section == "blocking":
            im = ITEM_RE.match(line)
            dm = DETAIL_RE.match(line)
            if im:
                blocking.append(im.group(1).strip())
            elif dm and blocking:
                blocking.append(dm.group(1).strip())
        elif section == "warnings":
            im = ITEM_RE.match(line)
            dm = DETAIL_RE.match(line)
            if im:
                warnings.append(im.group(1).strip())
            elif dm and warnings:
                warnings.append(dm.group(1).strip())
    if warnings and not warn_count:
        warn_count = len(warnings)
    return blocking, warnings, warn_count


def top_level_count(items: List[str]) -> int:
    """Blocking items minus the '(+N more of the same)' continuation lines."""
    return sum(1 for i in items if not i.startswith("(+"))


def fallback_lines(text: str) -> List[str]:
    """When a failing check printed no blocking section (a crash, an exit-2
    'cannot read', a bare pydantic dump): the verdict line plus a short tail,
    never anything under WARNINGS / NEXT."""
    out: List[str] = []
    section: Optional[str] = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = HEADER_RE.match(line)
        if m:
            section = "warnings" if m.group(1).strip().startswith("WARNINGS") else "other"
            continue
        if line.startswith("NEXT:") or line.startswith("What these labels mean"):
            section = "next"
            continue
        if section in ("warnings", "next"):
            continue
        out.append(line[:MAX_EVIDENCE_LEN])
    verdict = [ln for ln in out if ln.startswith("[FAIL]")]
    rest = [ln for ln in out if not ln.startswith("[FAIL]")]
    return (verdict[:1] + rest[-3:]) or ["(no output)"]


COUNT_RE = re.compile(r"(?<![\w.\-/])\d+(?=\s+[A-Za-z][\w'\-]*(?:\(s\))?)")


def count_stripped(line: str) -> str:
    """'3 reference(s) point at' -> 'N reference(s) point at', so a defect
    whose count moved is still the same defect for dedupe. Ids (FR-012,
    tasks[4], 1.3) are untouched: the digit must stand alone before a word."""
    return COUNT_RE.sub("N", line)


ARTIFACT_RE = fq.ARTIFACT_RE
FAMILY_RE = re.compile(r"\b(PRD|UX|DESIGN|DATA-MODEL|API|ARCH|TEST-STRATEGY|TASKS|CODE-MANIFEST)\b")


def artifact_in(line: str, docs: Path, default: str) -> str:
    """The docs/ path of the artifact a defect line names, else the default.
    A validator run on ARCH.yaml reports its sibling shards by name; the
    finding should point at the shard, not at the file the sweep happened to
    pass on the command line."""
    m = ARTIFACT_RE.search(line)
    if not m:
        return default
    cand = docs / m.group(1)
    if cand.is_file():
        return cand.as_posix()
    return default


# --------------------------------------------------------------------------
# The sweep
# --------------------------------------------------------------------------

def _finish(c: Check, docs: Path) -> None:
    c.blocking, c.warning_lines, c.warnings = parse_sections(c.output)
    if c.exit == 0:
        c.summary = "valid" if "/" in c.name else c.summary or "ok"
        return
    lines = c.blocking or fallback_lines(c.output)
    c.summary = lines[0][:200] if lines else "(no output)"
    if "/" in c.name:
        # The shard the failure is about: named in the first defect line, or
        # failing that in the [FAIL] headline ("TEST-STRATEGY__x.yaml does not
        # match the schema"). It is recorded NEXT TO the target, never in its
        # place: a validator that sweeps every sibling shard reports one shared
        # error from every invocation, and relabelling each row with that file
        # printed the same shard failing three times while the shards that
        # actually ran vanished from the report (ledger IMP-069, aicf LSN-047).
        headline = next((ln for ln in c.output.splitlines() if ln.startswith("[FAIL]")), "")
        where = artifact_in(c.blocking[0], docs, "") if c.blocking else ""
        where = where or artifact_in(headline, docs, "")
        if where and where != c.target:
            c.located = where


def family_of(name: str) -> Optional[Tuple[str, str]]:
    """(skill, canonical artifact) for an artifact FILE NAME. A shard
    (ARCH__x.yaml, TEST-STRATEGY__x.yaml) resolves to its family's system file,
    which is what every validator accepts (it globs its own siblings); a TASKS
    shard is validated on its own path, as the sweep already does."""
    base = name.split("__", 1)[0]
    suffix = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    for skill, artifact in CANONICAL:
        if artifact == name or artifact == base + suffix:
            return skill, artifact
    return None


def sweep_artifacts(docs: Path, only: List[str]) -> List[Check]:
    """The `--artifact` depth: one validator per named file, nothing else. The
    accepted-deviance registry is applied by the caller exactly as for a full
    sweep, so a skill's upstream gate gets the one answer it needs - accepted
    (N, unchanged) or red - which `--quick` could never give it: that depth runs
    only the cross-artifact linter (ledger IMP-081, aicf LSN-062 / LSN-063)."""
    checks: List[Check] = []
    for raw in only:
        name = artifact_key(raw)
        fam = family_of(name)
        if fam is None:
            raise ValueError(name)
        skill, artifact = fam
        target = docs / (name if name.startswith("TASKS__") else artifact)
        validator = SKILLS_DIR / skill / "validate_schema.py"
        c = Check(f"{skill}/validate_schema", target.as_posix())
        if not validator.is_file():
            c.summary = "validator not present in this skill tree"
        elif not target.is_file():
            c.summary = "artifact absent - stage not reached"
        else:
            c.exit, c.output = run_bare([sys.executable, str(validator), "--path", str(target)])
            _finish(c, docs)
        checks.append(c)
    return checks


def sweep(docs: Path, quick: bool, only: Optional[List[str]] = None) -> List[Check]:
    if only:
        return sweep_artifacts(docs, only)
    checks: List[Check] = []

    if not quick:
        for skill, artifact in CANONICAL:
            validator = SKILLS_DIR / skill / "validate_schema.py"
            target = docs / artifact
            c = Check(f"{skill}/validate_schema", target.as_posix())
            if not validator.is_file():
                c.summary = "validator not present in this skill tree"
                checks.append(c)
                continue
            if not target.is_file():
                c.summary = "artifact absent - stage not reached"
                checks.append(c)
                continue
            c.exit, c.output = run_bare([sys.executable, str(validator), "--path", str(target)])
            _finish(c, docs)
            checks.append(c)

        # Container task shards: the bulk of a real graph lives here, not in
        # TASKS.json, so a sweep that only validated the system file would miss
        # almost everything.
        task_validator = SKILLS_DIR / "task" / "validate_schema.py"
        if task_validator.is_file():
            for shard in sorted(docs.glob("TASKS__*.json")):
                c = Check("task/validate_schema", shard.as_posix())
                c.exit, c.output = run_bare([sys.executable, str(task_validator), "--path", str(shard)])
                _finish(c, docs)
                checks.append(c)

    # Cross-artifact linter — the only check --quick runs, because it is the one
    # that catches drift BETWEEN artifacts, which is what moves during a run.
    crosscheck = SKILLS_DIR / "task" / "crosscheck_artifacts.py"
    c = Check("crosscheck_artifacts", docs.as_posix())
    if not crosscheck.is_file():
        c.summary = "linter not present in this skill tree"
    else:
        c.exit, c.output = run_bare([sys.executable, str(crosscheck), "--docs-dir", str(docs)])
        _finish(c, docs)
        if c.exit == 0:
            c.summary = "all cross-artifact refs resolve"
    checks.append(c)

    if not quick:
        gen = installed_index_generator(docs)
        if gen is not None:
            c = Check("docs_index --check", gen.as_posix())
        else:
            gen = SKILLS_DIR / "setup" / "docs_index.py"
            c = Check("docs_index --check", f"{gen.as_posix()} ({index_fallback_label(docs)})")
        if not gen.is_file():
            c.summary = "index generator not present in this skill tree"
        else:
            c.exit, c.output = run_bare([sys.executable, str(gen), "--docs-dir", str(docs), "--check"])
            _finish(c, docs)
            if c.exit == 0:
                c.summary = "no dangling id references"
        checks.append(c)

    return checks


_SETUP_HELPERS = ("findings.py", "lessons.py", "statusboard.py", "repo_scan.py",
                  "bump_artifact.py", "validate_findings.py")


def _project_roots(docs: Path) -> List[Path]:
    return [docs.resolve().parent, Path.cwd()]


def own_index_generator_reasons(docs: Path) -> List[str]:
    """Why this project regenerates docs/INDEX.yaml with its OWN tool - the
    same two signals /sdlc:setup's installer refuses to clobber (its
    wire_setup.detect_foreign_wiring): a docs/INDEX.yaml header naming another
    generator, or a hook that regenerates the index with another command.
    Empty when the index looks stock or is absent."""
    index_text: Optional[str] = None
    try:
        p = docs / "INDEX.yaml"
        index_text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None
    except OSError:
        index_text = None
    settings: Dict[str, Any] = {}
    for root in _project_roots(docs):
        sp = root / ".claude" / "settings.json"
        if sp.is_file():
            try:
                settings = json.loads(sp.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                settings = {}
            break
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_wire_setup_for_doctor", SKILLS_DIR / "setup" / "wire_setup.py")
        ws = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ws)  # type: ignore[union-attr]
        return list(ws.detect_foreign_wiring(index_text, settings))
    except Exception:  # the installer is optional here - fall back to the header check
        if index_text:
            first = next((ln.strip() for ln in index_text.splitlines() if ln.strip()), "")
            if "GENERATED" in first.upper() and ".claude/sdlc/docs_index.py" not in first:
                return [f"docs/INDEX.yaml says it is generated by another tool: {first.lstrip('#').strip()}"]
        return []


def setup_helpers_present(docs: Path) -> bool:
    """Did /sdlc:setup install anything here (other than the index generator)?"""
    return any((root / ".claude" / "sdlc" / name).is_file()
               for root in _project_roots(docs) for name in _SETUP_HELPERS)


def index_fallback_label(docs: Path) -> str:
    """Why the plugin's own docs_index.py runs the dangling gate, and that it
    runs READ-ONLY. The only label used to be "project never ran /sdlc:setup",
    which was false for a project whose .claude/sdlc/ holds every other setup
    helper but ships its own index generator - and it sent an agent to run the
    plugin copy bare, which overwrote the project-owned docs/INDEX.yaml with a
    stock-format one (ledger IMP-043). The write side is never delegated: a
    generator the project owns regenerates the project's index."""
    reasons = own_index_generator_reasons(docs)
    if reasons:
        return (f"plugin copy, --check only; the project owns its index - "
                f"{reasons[0]} - so nothing here regenerates docs/INDEX.yaml")
    if setup_helpers_present(docs):
        return ("plugin copy, --check only; /sdlc:setup ran here but installed no "
                "docs_index.py, so nothing here regenerates docs/INDEX.yaml")
    return "plugin copy, --check only; project never ran /sdlc:setup"


def installed_index_generator(docs: Path) -> Optional[Path]:
    """The consumer project's own .claude/sdlc/docs_index.py, if setup ran —
    looked up beside the docs dir first, then under the cwd."""
    for root in (docs.resolve().parent, Path.cwd()):
        cand = root / ".claude" / "sdlc" / "docs_index.py"
        if cand.is_file():
            return cand
    return None


# --------------------------------------------------------------------------
# Accepted deviance (wontfix findings that pin an expected count)
# --------------------------------------------------------------------------

EXPECTED_COUNT_RE = re.compile(r"expected_count:\s*(\d+)")


def artifact_key(path: Any) -> str:
    """The file name a registry keys on - never the path as written.
    `--docs-dir docs` and an absolute --docs-dir name the same artifact, and
    a finding's surfaced_at.file carries whichever form the run that minted
    it was invoked with; keyed verbatim, one wontfix finding was honoured
    under the relative form and ignored under the absolute one, and a
    finding minted under the absolute form could never be accepted by a
    relative run (ledger IMP-078, aicf LSN-059). Artifact names are unique
    within a docs dir, so the name is the whole identity."""
    raw = str(path or "").replace("\\", "/").rstrip("/")
    return raw.rsplit("/", 1)[-1] if raw else ""


def project_relative(where: str, docs: Path) -> str:
    """A minted finding's path, repo-relative and POSIX whatever --docs-dir
    the sweep was invoked with. An absolute form written into the queue is
    invocation-specific noise: the statusboard prints it, and a registry
    keyed on it (before artifact_key) never matched a relative run."""
    raw = str(where or "").replace("\\", "/")
    if not raw:
        return raw
    p = Path(raw)
    if not p.is_absolute():
        return p.as_posix()
    for root in (Path.cwd(), docs.resolve().parent):
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except (ValueError, OSError):
            continue
    return raw


def accepted_registry(data: Dict[str, Any]) -> Dict[Tuple[str, str], Tuple[str, int]]:
    """(detected_by, artifact file name) -> (fnd_id, expected N) from wontfix
    findings. The name, not the path: see artifact_key."""
    reg: Dict[Tuple[str, str], Tuple[str, int]] = {}
    for f in data.get("findings") or []:
        if not isinstance(f, dict) or f.get("status") != "wontfix":
            continue
        res = f.get("resolution") if isinstance(f.get("resolution"), dict) else {}
        text = " ".join(str(x or "") for x in (f.get("summary"), res.get("reason"), res.get("summary")))
        m = EXPECTED_COUNT_RE.search(text)
        if not m:
            continue
        sa = f.get("surfaced_at") if isinstance(f.get("surfaced_at"), dict) else {}
        where = artifact_key(sa.get("file") or f.get("suspected_source"))
        det = str(f.get("detected_by") or "")
        if det and where:
            reg[(det, where)] = (str(f.get("fnd_id")), int(m.group(1)))
    return reg


def apply_accepted(checks: List[Check], data: Dict[str, Any]) -> None:
    reg = accepted_registry(data)
    if not reg:
        return
    for c in checks:
        if c.skipped or c.exit == 0:
            continue
        hit = reg.get((c.name, artifact_key(c.target)))
        if not hit:
            continue
        fnd_id, expected = hit
        n = top_level_count(c.blocking)
        if n == expected:
            c.accepted = f"accepted ({expected}, unchanged) per {fnd_id}"
            c.accepted_by = fnd_id
        else:
            c.summary = (f"{fnd_id} accepted {expected} problem line(s) here, now {n} - "
                         f"the accepted deviance moved; {c.summary}")


# artifact file name -> (fnd_id, label, owed commands) for every artifact an
# open re-invoke finding still owes (ledger IMP-077). Lives in findings.py so
# the --reconcile runs read the same answer through `list --owed-by`.
AWAITING_STATUSES = fq.AWAITING_STATUSES
awaiting_registry = fq.awaiting_registry


def apply_awaiting(checks: List[Check], data: Dict[str, Any]) -> None:
    """Label every failing check whose target - or the file its first defect
    names - is an artifact an open re-invoke finding still owes. The check
    stays failed: the artifact is not consumable and the exit code says so;
    the label says the failure is known and scheduled, and emit_findings
    records nothing for it."""
    reg = awaiting_registry(data)
    if not reg:
        return
    for c in checks:
        if c.skipped or c.exit == 0 or c.accepted:
            continue
        for path in (c.target, c.located):
            hit = reg.get(artifact_key(path)) if path else None
            if hit:
                c.awaiting_by, c.awaiting, c.awaiting_cmds = hit
                break


# --------------------------------------------------------------------------
# Findings emission
# --------------------------------------------------------------------------

def kind_for(check: Check) -> str:
    if check.name.startswith("crosscheck"):
        return "crosscheck_broken_ref"
    if check.name.startswith("docs_index"):
        return "dangling_reference"
    return "validator_error"


def stage_for(check: Check) -> Optional[str]:
    """The pipeline stage a check belongs to, or None when it spans several.

    A skill validator localizes to its own stage. The cross-artifact linter and
    the index gate do NOT — they compare two artifacts, and guessing a stage
    here would seed the finding with a suspicion the raiser has no basis for.
    None is the honest answer; /sdlc:repair localizes properly.
    """
    if "/" in check.name:
        return check.name.split("/", 1)[0]
    return None


# Checks whose output lists INDEPENDENT defects, one per line: each may localize
# to a different stage, so each earns its own finding. A skill validator's
# errors, by contrast, are all about one artifact and travel together.
PER_LINE_CHECKS = ("crosscheck_artifacts", "docs_index --check")
MAX_PER_CHECK = 20


def _entry(c: Check, summary: str, where: str, evidence: List[str], *,
           kind: Optional[str] = None, stage: Optional[str] = "auto",
           detected_by: Optional[str] = None, docs: Optional[Path] = None) -> Dict[str, Any]:
    if docs is not None:
        where = project_relative(where, docs)
    return {
        "fnd_id": None,
        "raised_by": "sdlc-repair",
        "detected_by": detected_by or c.name,
        "surfaced_at": {"file": where},
        "kind": kind or kind_for(c),
        "summary": summary[:400],
        "evidence": [e[:MAX_EVIDENCE_LEN] for e in (evidence or [f"exit {c.exit}"])][:MAX_EVIDENCE],
        "suspected_stage": stage_for(c) if stage == "auto" else stage,
        "suspected_source": where,
        "status": "open",
        "resolution": None,
    }


def failure_entries(c: Check, docs: Path) -> List[Dict[str, Any]]:
    lines = c.blocking or fallback_lines(c.output)
    out: List[Dict[str, Any]] = []
    if c.name in PER_LINE_CHECKS:
        items = [ln for ln in lines if not ln.startswith("(+")]
        for ln in items[:MAX_PER_CHECK]:
            where = artifact_in(ln, docs, c.target)
            out.append(_entry(c, f"{c.name} exit {c.exit}: {ln}", where, [ln], docs=docs))
        if len(items) > MAX_PER_CHECK:
            out.append(_entry(
                c, f"{c.name} exit {c.exit}: {len(items) - MAX_PER_CHECK} further defect line(s) not itemized",
                c.target, [f"exit {c.exit}", f"{len(items)} defect lines in total"], docs=docs,
            ))
    else:
        out.append(_entry(c, f"{c.name} exit {c.exit}: {c.summary}", c.target, lines[:MAX_EVIDENCE], docs=docs))
    return out


CHECK_TAG_RE = re.compile(r"\[check (\d+)\]")


def warning_entries(c: Check, docs: Path) -> List[Dict[str, Any]]:
    """The cross-artifact subset of a check's WARNINGS, as findings. Off by
    default (--warnings-as-findings): a warning is exit-neutral for a reason."""
    out: List[Dict[str, Any]] = []
    if c.skipped:
        return out
    own_family = None
    if "/" in c.name:
        skill = c.name.split("/", 1)[0]
        own_family = next((a.split(".")[0] for s, a in CANONICAL if s == skill), None)
    for ln in c.warning_lines:
        if ln.startswith("(+"):
            continue
        tag = CHECK_TAG_RE.search(ln)
        if c.name == "task/validate_schema" and tag and tag.group(1) in ("20", "23"):
            n = tag.group(1)
            kind = "drifted_embed" if n == "20" else "stale_downstream_claim"
            where = artifact_in(ln, docs, c.target)
            out.append(_entry(c, f"{c.name} [check {n}]: {ln}", where, [ln],
                              kind=kind, stage="task", detected_by=f"{c.name} [check {n}]", docs=docs))
        elif c.name in ("ux/validate_schema", "arch/validate_schema"):
            named = {m.group(1).split("__")[0].split(".")[0] for m in ARTIFACT_RE.finditer(ln)}
            named |= set(FAMILY_RE.findall(ln))
            named.discard(own_family or "")
            if not named:
                continue
            where = artifact_in(ln, docs, c.target)
            out.append(_entry(c, f"{c.name} warning: {ln}", where, [ln],
                              kind="stale_downstream_claim", stage=None,
                              detected_by=f"{c.name} warning", docs=docs))
    return out


def emit_findings(path: Path, checks: List[Check], docs: Path,
                  warnings_as_findings: bool) -> Tuple[int, int, Optional[str]]:
    """Append one open finding per failed check (per defect line for the
    per-line checks). Returns (how many were added, how many failures were
    held back as awaiting an owed re-invocation, error text or None).

    Deduplicates on (detected_by, count-stripped summary) against every
    finding that is open, triaged, wontfix, deferred or duplicate — so
    repeated sweeps never pile up copies of one defect, and never re-mint a
    defect a person already dismissed. A check labelled awaiting (its artifact
    is one an open re-invoke finding still owes) is never recorded, and
    neither is a per-line defect naming such an artifact: the finding that
    owes the re-run already tracks it, and its first defect line moves with
    every hop, which is why the summary key alone never caught it.
    """
    try:
        data = fq.load_findings(path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        return 0, 0, f"cannot read {path}: {e}"
    seen = {
        (f.get("detected_by"), count_stripped(str(f.get("summary") or ""))[:200])
        for f in data.get("findings") or []
        if isinstance(f, dict) and f.get("status") in DEDUPE_STATUSES
    }
    owed = awaiting_registry(data)
    entries: List[Dict[str, Any]] = []
    held = 0
    for c in checks:
        if c.awaiting:
            held += 1
            continue
        cands: List[Dict[str, Any]] = []
        if c.failed:
            cands += failure_entries(c, docs)
        if warnings_as_findings:
            cands += warning_entries(c, docs)
        for e in cands:
            where = str((e.get("surfaced_at") or {}).get("file") or "")
            if owed and artifact_key(where) in owed:
                held += 1
                continue
            key = (e["detected_by"], count_stripped(e["summary"])[:200])
            if key in seen:
                continue
            seen.add(key)
            entries.append(e)
    if not entries:
        return 0, held, None
    try:
        added, _skipped = fq.append_findings(path, entries, allow_duplicate=True)
    except fq.QueueError as e:
        return 0, held, str(e)
    except fq.EntryRejected as e:
        return 0, held, "a sweep finding would not validate: " + "; ".join(e.problems[:3])
    return len(added), held, None


# --------------------------------------------------------------------------
# Provenance drift
# --------------------------------------------------------------------------

def sha16(path: Path) -> Optional[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Hasher:
    """docs_index.py --hash when the installed copy supports it (the generator
    owns the hash definition), inline sha16 otherwise — the two are identical
    by contract: sha256 of the file's text, first 16 hex."""

    def __init__(self, docs: Path) -> None:
        self.gen = installed_index_generator(docs)
        self.use_gen = self.gen is not None
        self.cache: Dict[str, Optional[str]] = {}

    def __call__(self, path: Path) -> Optional[str]:
        key = path.as_posix()
        if key in self.cache:
            return self.cache[key]
        val: Optional[str] = None
        if self.use_gen and self.gen is not None:
            code, out = run_bare([sys.executable, str(self.gen), "--hash", str(path)])
            m = re.search(r"\b[0-9a-f]{16}\b", out) if code == 0 else None
            if m:
                val = m.group(0)
            else:
                self.use_gen = False   # an older installed copy: fall back for the rest
        if val is None:
            val = sha16(path)
        self.cache[key] = val
        return val


def load_artifact(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (OSError, ValueError, yaml.YAMLError):
        return None
    return raw if isinstance(raw, dict) else None


def provenance_entries(meta: Dict[str, Any]) -> List[Dict[str, Any]]:
    prov = meta.get("upstream_provenance")
    out: List[Dict[str, Any]] = []
    if isinstance(prov, list):
        out = [p for p in prov if isinstance(p, dict) and p.get("file")]
    elif isinstance(prov, dict):
        for fname, p in prov.items():
            if isinstance(p, dict):
                out.append({"file": fname, **p})
    return out


def artifact_provenance(docs: Path, path: Path, hasher: Hasher):
    """[(upstream file, recorded sha, current sha | None)] for one artifact,
    or None when it records no provenance at all."""
    raw = load_artifact(path)
    if raw is None:
        return None
    meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    entries = provenance_entries(meta)
    if not entries:
        return None
    rows = []
    for p in entries:
        up = docs / Path(str(p["file"]).replace("\\", "/")).name
        recorded = str(p.get("sha256") or "")[:16]
        current = hasher(up) if up.is_file() else None
        rows.append((up.name, recorded, current))
    return rows


def provenance_report(docs: Path, findings_path: Optional[Path]) -> Tuple[List[str], List[str]]:
    """([stale] lines, 'can be marked resolved' hints)."""
    hasher = Hasher(docs)
    stale: List[str] = []
    fresh_artifacts: Dict[str, bool] = {}
    last_updated: Dict[str, str] = {}
    for path in sorted(list(docs.glob("*.yaml")) + list(docs.glob("*.json"))):
        if path.name == "INDEX.yaml":
            continue
        rows = artifact_provenance(docs, path, hasher)
        if rows is None:
            continue
        raw = load_artifact(path) or {}
        meta = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        last_updated[path.name] = str(meta.get("last_updated") or "")
        fresh = True
        for up, recorded, current in rows:
            if current is None:
                stale.append(f"[stale] docs/{path.name} was built against docs/{up}, which is no longer in docs/")
                fresh = False
            elif recorded and current[:len(recorded)] != recorded[:len(current)]:
                stale.append(f"[stale] docs/{path.name} was built against docs/{up}@{recorded}, now @{current}")
                fresh = False
        fresh_artifacts[path.name] = fresh

    hints: List[str] = []
    if findings_path and findings_path.is_file():
        try:
            data = fq.load_findings(findings_path)
        except (OSError, yaml.YAMLError, ValueError):
            data = {"findings": []}
        for f in data.get("findings") or []:
            if not isinstance(f, dict) or f.get("status") != "triaged":
                continue
            res = f.get("resolution") if isinstance(f.get("resolution"), dict) else None
            if not res or res.get("mode") != "re-invoke" or not res.get("downstream_rerun"):
                continue
            targets = rerun_artifacts(res["downstream_rerun"])
            if not targets:
                continue
            fixed_at = str(res.get("at") or "")
            ok = True
            for name in targets:
                if name not in fresh_artifacts or not fresh_artifacts[name]:
                    ok = False
                    break
                if fixed_at and last_updated.get(name) and last_updated[name] < fixed_at:
                    ok = False
                    break
            if ok:
                hints.append(f"{f.get('fnd_id')} can be marked resolved: every artifact its re-invocations "
                             f"rewrite ({join_ids(targets, 4)}) was rebuilt after the fix and reads fresh upstream hashes")
    return stale, hints


# '/sdlc:test demo-api --reconcile' -> 'TEST-STRATEGY__demo-api.yaml'. Shared
# with findings.py (see awaiting_registry above).
RERUN_RE = fq.RERUN_RE
rerun_artifacts = fq.rerun_artifacts


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="SDLC pipeline health sweep.")
    ap.add_argument("--docs-dir", default="docs", help="Directory holding the artifacts (default: docs).")
    ap.add_argument(
        "--quick",
        action="store_true",
        help="Cross-artifact linter only - the depth /sdlc:code runs at component boundaries.",
    )
    ap.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="FILE",
        help="Run only this artifact's validator (repeatable), with the accepted-deviance "
             "registry applied - the depth a skill's upstream gate needs. A shard resolves to "
             "its family's system file; a TASKS shard runs on itself. Not with --quick.",
    )
    ap.add_argument(
        "--emit-findings",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help=f"Append an FND-NNN entry per failed check (default: {DEFAULT_FINDINGS} under the "
             f"project that holds --docs-dir, whatever the working directory).",
    )
    ap.add_argument(
        "--warnings-as-findings",
        action="store_true",
        help="With --emit-findings: also record the cross-artifact WARNINGS (task [check 20] / "
             "[check 23], ux/arch warnings naming another artifact). Off by default.",
    )
    ap.add_argument(
        "--findings",
        default=None,
        metavar="PATH",
        help=f"Queue to read for accepted deviance and --provenance hints (default: the "
             f"--emit-findings path, else {DEFAULT_FINDINGS} under the project that holds --docs-dir).",
    )
    ap.add_argument(
        "--provenance",
        action="store_true",
        help="Compare every artifact's recorded upstream hashes with the files as they are now.",
    )
    ap.add_argument("--json", action="store_true", dest="as_json", help="Machine-readable report on stdout.")
    args = ap.parse_args()

    docs = Path(args.docs_dir)
    if not docs.is_dir():
        print(f"[doctor] docs dir not found: {docs}", file=sys.stderr)
        return 2

    # The default queue belongs to the project whose docs are swept - the
    # parent of --docs-dir - never to the working directory. Resolved against
    # the cwd, an absolute --docs-dir run from anywhere else wrote the queue
    # there: into the plugin tree, the day two eval runners inherited that
    # cwd. An explicit PATH keeps its ordinary command-line meaning.
    default_queue = docs.resolve().parent / DEFAULT_FINDINGS
    emit_path: Optional[Path] = None
    if args.emit_findings is not None:
        emit_path = Path(args.emit_findings) if args.emit_findings else default_queue
    findings_path = Path(args.findings) if args.findings else (emit_path or default_queue)
    queue_data: Dict[str, Any] = {"findings": []}
    queue_error: Optional[str] = None
    if findings_path.is_file():
        try:
            queue_data = fq.load_findings(findings_path)
        except (OSError, yaml.YAMLError, ValueError) as e:
            queue_error = f"cannot read {findings_path}: {e}"

    if args.artifact and args.quick:
        print("[FAIL] --artifact and --quick name different depths - pass one of them.", file=sys.stderr)
        return 2
    unknown = [a for a in args.artifact if family_of(artifact_key(a)) is None]
    if unknown:
        print(f"[FAIL] no validator for {', '.join(unknown)} - name a canonical artifact or one of "
              f"its shards ({', '.join(a for _, a in CANONICAL)}; ARCH__<cid>.yaml, "
              f"TASKS__<cid>.json ...).", file=sys.stderr)
        return 2
    checks = sweep(docs, args.quick, args.artifact)
    apply_accepted(checks, queue_data)
    apply_awaiting(checks, queue_data)
    failed = [c for c in checks if c.failed]
    accepted = [c for c in checks if c.accepted]
    awaiting = [c for c in checks if c.awaiting]
    warn_total = sum(c.warnings for c in checks)

    added = 0
    held = 0
    if emit_path is not None and queue_error is None:
        added, held, queue_error = emit_findings(emit_path, checks, docs, args.warnings_as_findings)

    stale: List[str] = []
    hints: List[str] = []
    if args.provenance:
        stale, hints = provenance_report(docs, findings_path)

    if args.as_json:
        print(json.dumps(
            {
                "docs_dir": docs.as_posix(),
                "depth": "quick" if args.quick else ("artifact" if args.artifact else "full"),
                "checks": [c.as_dict() for c in checks],
                "failed": len(failed),
                "accepted": [c.accepted for c in accepted],
                "awaiting": [c.awaiting for c in awaiting],
                "warnings_total": warn_total,
                "findings_added": added,
                "findings_awaiting": held,
                "queue_error": queue_error,
                "provenance": {"stale": stale, "resolvable": hints} if args.provenance else None,
            },
            indent=2,
        ))
        return 2 if queue_error else (1 if failed else 0)

    depth = "quick" if args.quick else ("artifact" if args.artifact else "full")
    print(f"Health check ({depth}) over {docs.as_posix()} - one line per "
          f"document, one line per cross-document check.")
    for c in checks:
        print(c.line())
    ran = [c for c in checks if not c.skipped]
    skipped = len(checks) - len(ran)

    print()
    tail_note = f"; {skipped} skipped (nothing to check yet)" if skipped else ""
    if failed:
        print(f"[FAIL] {len(failed)} of {len(ran)} check(s) failed{tail_note}.")
        print_findings(
            [(f"{c.name} on {c.target} exited {c.exit} with "
              f"{top_level_count(c.blocking) if c.blocking else 'no'} problem line(s)"
              + (f" - the first names {c.located}" if c.located else "")
              + (f" - {c.awaiting}; known and scheduled, not recorded again" if c.awaiting else "")
              + ". What it printed:",
              c.blocking or fallback_lines(c.output))
             for c in failed],
            [],
            blocking_header="WHAT FAILED",
        )
    else:
        print(f"[OK] all {len(ran)} check(s) passed{tail_note}.")

    warnings: List[Any] = []
    for c in checks:
        if c.warnings:
            warnings.append((f"{c.name} on {c.target} printed {c.warnings} warning(s) - none block; "
                             f"the cross-document ones become findings only with --warnings-as-findings:",
                             [ln for ln in c.warning_lines if not ln.startswith("(+")]))
    for c in accepted:
        warnings.append(f"{c.name} on {c.target} exited {c.exit} but is {c.accepted} - "
                        f"a known, accepted deviance; it fails again the moment its count moves")
    owed_by: Dict[str, List[Check]] = {}
    for c in awaiting:
        owed_by.setdefault(c.awaiting_by or "", []).append(c)
    for fnd_id, rows in owed_by.items():
        cmds = rows[0].awaiting_cmds
        warnings.append(f"{fnd_id} still owes {join_ids(cmds, 3) if cmds else 'its re-invocation'} - "
                        f"{len(rows)} red check(s) wait on it ({join_ids([r.target for r in rows], 3)}); "
                        f"they turn green when that runs and are not recorded again until then")
    warnings += stale
    if queue_error:
        warnings.append(f"findings queue: {queue_error} - run validate_findings.py and repair it before "
                        f"the next /sdlc:repair")
    print_findings([], warnings)

    if hints:
        print()
        for h in hints:
            print(f"  {h}")

    if emit_path is not None:
        held_note = (f"; {held} failure(s) wait on a re-invocation an open finding already owes "
                     f"and were not recorded again" if held else "")
        print(f"\n{added} problem(s) were written to {project_relative(str(emit_path), docs)} for "
              f"/sdlc:repair to work through{held_note}.")

    if failed and all(c.awaiting for c in failed):
        owed_cmds: List[str] = []
        for c in failed:
            owed_cmds += [x for x in c.awaiting_cmds if x not in owed_cmds]
        print_next(f"{'  then  '.join(owed_cmds) if owed_cmds else 'the re-invocation the finding owes'}  "
                   f"(every failure waits on {join_ids(sorted(owed_by), 3)}; run the owed command(s) in a "
                   f"NEW session, then sweep again)")
    elif failed:
        print_next("/sdlc:repair  (walks each failure back to the document that is actually wrong)")
    elif stale:
        print_next("nothing is broken; the [stale] lines above mean an upstream moved after a "
                   "downstream was built - re-run the downstream skill to review the delta.",
                   show_glossary=True)
    else:
        print_next("nothing required - the document chain is healthy.", show_glossary=bool(warnings))
    return 2 if queue_error else (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
