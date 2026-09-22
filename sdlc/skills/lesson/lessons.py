#!/usr/bin/env python3
"""sdlc lessons helper — the ONLY writer of .claude/skills-state/sdlc-lessons.yaml,
the cross-skill queue where skill runs record themselves and skill DEFECTS
(instruction gaps, validator false rejects, bad questions, script bugs — never
project-artifact defects, those are FND findings) are captured for the plugin
maintainer. Canonical schema with rationale: LESSONS.schema.yaml next to this
file. Raising doctrine: references/lessons-capture.md.

Subcommands:

    record-run  append/update one run record. Metrics are derived from the
                skill's state file (flat interview state, sharded `sessions:`
                map, or the code ledger's `session:`) — never invented.
                The calling skill may pass extra facts with repeatable
                --metric key=value (the only metrics channel for state-less
                skills like setup).
    add         append one LSN-NNN lesson about a skill. Prints a `Check:`
                line after [OK] when the entry looks improper (file not in
                the skill folder, kind/file mismatch, placeholder text, a
                blocker that did not stop anything) - hints, never rejects.
                --dry-run validates and prints the checks, writes nothing.
    list        print lessons (all, --open, --status X, --skill X), each with
                the maintainer's verdict when one has reached this project:
                [triaged IMP-041], [resolved 0.9.8], [resolved 0.9.17 - not
                installed], [wontfix IMP-039], [dismissed], and [open again
                after 0.9.8] for a lesson that recurred after its fix.
    reconcile   stamp the maintainer's verdicts onto this project's lessons
                from the installed plugin's skills/lesson/VERDICTS.yaml (rows
                keyed by this project's opaque id; --plugin-root names the
                plugin outside a skill run). record-run does this at every
                close, so it is rarely typed by hand.
    export      sanitized report for the skillset owner (--format md|json,
                --out FILE to write it, --send to mail it now).
    consent     read or set this project's telemetry mode (off|ask|auto).
    validate    check the queue against the schema invariants.

Delivery (opt-in, chosen once at /sdlc:setup):

    Nothing leaves the machine unless the marker's telemetry.mode says so.
    When it does, a `blocker` lesson mails at the next skill close and
    everything else rides a weekly batch, redacted and stamped `sent_at` so
    nothing is ever sent twice. $SDLC_LESSONS_TELEMETRY=off overrides
    everything. See the "Telemetry" section below for the whole contract.

Resolution chains:

    project root    --project-root, then $CLAUDE_PROJECT_DIR, then cwd.
    state file      --state, else <root>/.claude/skills-state/sdlc-<skill>.state.yaml.
    plugin version  --plugin-version (source `flag`), else
                    <--plugin-root>/.claude-plugin/plugin.json (source `manifest`),
                    else $CLAUDE_SKILL_DIR/../../.claude-plugin/plugin.json
                    (source `manifest`), else the
                    <root>/.claude/sdlc/sdlc-plugin.json marker written by
                    /sdlc:setup (source `marker`), else unrecorded.

This helper is BEST-EFFORT infrastructure: a non-zero exit must never block a
skill run — the calling skill notes it in one Attention: clause and moves on.

Exit codes:
    0 — success / queue valid.
    1 — queue invalid, or a rejected add/record (bad enum, unsanitized where,
        evidence out of bounds).
    2 — could not read or parse a file.
    3 — required dependency missing (pyyaml; reading YAML needs it).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import uuid
from pathlib import Path

# =============================================================================
# User-facing output (CLAUDE.md 14). Three verdict tags, two finding sections,
# one NEXT block - identical across every SDLC script, because the person
# reading them knows only "there is a pipeline and I run it in order".
# Canonical guidance: sdlc/skills/prd/references/reporting-to-the-user.md
# =============================================================================

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"

# Where an exported report should be sent.
FEEDBACK_CONTACT = "sdlc@agentmail.to"


def print_findings(blocking, warnings, blocking_header="MUST FIX BEFORE 'complete'"):
    """The two canonical sections. A WARNING never blocks, and says so."""
    if blocking:
        print(f"\n{blocking_header} ({len(blocking)}):")
        for b in blocking:
            print(f"  - {b}")
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}) - none of these block the next skill:")
        for w in warnings:
            print(f"  - {w}")


def print_next(*lines, show_glossary=False):
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


QUEUE_REL = Path(".claude/skills-state/sdlc-lessons.yaml")
MARKER_REL = Path(".claude/sdlc/sdlc-plugin.json")
STATE_REL_TMPL = ".claude/skills-state/sdlc-{skill}.state.yaml"

LSN_RE = re.compile(r"^LSN-\d{3,}$")
FND_RE = re.compile(r"^FND-\d{3,}$")
IMP_RE = re.compile(r"^IMP-\d{3,}$")
SKILL_RE = re.compile(r"^[a-z][a-z0-9-]*$")
# The maintainer's verdict manifest, shipped inside the plugin (relative to
# the plugin root): one row per lesson the ledger has dealt with, keyed by the
# opaque project id. `reconcile` reads it; /improve's close writes it.
VERDICTS_REL = Path("skills/lesson/VERDICTS.yaml")

KINDS = (
    "instruction_gap",
    "instruction_conflict",
    "validator_false_reject",
    "validator_false_accept",
    "question_quality",
    "schema_gap",
    "script_bug",
    "terminal_output",
    "drift",
    "process",
    "other",
)
SEVERITIES = ("blocker", "degraded", "cosmetic")
OUTCOMES = ("complete", "draft", "aborted", "failed")
AGENT_ACTIONS = ("improvised", "asked_user", "stopped", "worked_around")
GENERALIZES = ("yes", "unsure", "project_specific")
# `open` is this project's word; everything after it is the maintainer's,
# stamped by `reconcile` (from the installed plugin's VERDICTS.yaml) or by the
# maintainer's collector on a registered repo. `collected` only says the
# collector has the lesson; the four VERDICT_STATUSES say what became of it.
LESSON_STATUSES = ("open", "collected", "triaged", "resolved", "wontfix", "dismissed")
VERDICT_STATUSES = ("triaged", "resolved", "wontfix", "dismissed")
# A recurrence of a lesson in one of these reopens it (status back to `open`,
# the verdict fields kept): the fix regressed, or the call was wrong.
CLOSED_STATUSES = ("resolved", "wontfix", "dismissed")
MAX_EVIDENCE = 5
MAX_EVIDENCE_LEN = 200

# Field order for the emitter — mirrors LESSONS.schema.yaml.
RUN_KEYS = (
    "session_id",
    "skill",
    "skill_version",
    "state_skill_version",
    "skill_version_at_start",
    "plugin_version",
    "plugin_version_source",
    "installed_version",
    "started_at",
    "finished_at",
    "outcome",
    "resumes",
    "mode",
    "container_id",
    "metrics",
    "sent_at",
)
LESSON_KEYS = (
    "lsn_id",
    "raised_by",
    "raised_at",
    "session_id",
    "skill",
    "skill_version",
    "state_skill_version",
    "plugin_version",
    "installed_version",
    "kind",
    "severity",
    "where",
    "summary",
    "evidence",
    "agent_action",
    "suggested_fix",
    "generalizes",
    "related_findings",
    "occurrences",
    "first_seen_at",
    "last_seen_at",
    "status",
    "imp_id",
    "fixed_in",
    "verdict_at",
    "sent_at",
)


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def _iso_utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(value):
    if not isinstance(value, str):
        return None
    try:
        return _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def resolve_project_root(arg: "str | None") -> Path:
    if arg:
        return Path(arg).resolve()
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path.cwd()


# =============================================================================
# Queue I/O. Reading uses pyyaml; writing uses a deterministic emitter so the
# file is diff-stable and round-trips through any YAML reader. All strings are
# emitted double-quoted (JSON escaping is valid YAML), which sidesteps the
# yes/no/null scalar traps entirely.
# =============================================================================


def _empty_queue() -> dict:
    return {
        "lessons_file_version": "1",
        "last_updated": None,
        "last_ids": {"LSN": 0},
        "runs": [],
        "lessons": [],
    }


def _norm_generalizes(value):
    # YAML 1.1 readers load a bare `yes` as True; normalize back.
    if value is True:
        return "yes"
    return value


def load_queue(path: Path) -> dict:
    if not path.is_file():
        return _empty_queue()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return _empty_queue()
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    doc = _empty_queue()
    doc.update(raw)
    doc.setdefault("last_ids", {"LSN": 0})
    if not isinstance(doc.get("runs"), list):
        doc["runs"] = []
    if not isinstance(doc.get("lessons"), list):
        doc["lessons"] = []
    for lesson in doc["lessons"]:
        if isinstance(lesson, dict) and "generalizes" in lesson:
            lesson["generalizes"] = _norm_generalizes(lesson["generalizes"])
    return doc


def _emit_scalar(value) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return repr(value)
    return json.dumps(str(value), ensure_ascii=False)


def _emit(value, indent: int, lines: "list[str]", key_order=None) -> None:
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            lines[-1] += " {}"
            return
        keys = [k for k in (key_order or []) if k in value]
        keys += [k for k in value if k not in keys]
        for k in keys:
            v = value[k]
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}{k}:")
                _emit(v, indent + 1, lines)
            else:
                lines.append(f"{pad}{k}:")
                _emit(v, indent, lines)
    elif isinstance(value, list):
        if not value:
            lines[-1] += " []"
            return
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{pad}-")
                # Re-render the "-" line to carry the first key inline is
                # avoidable complexity; block style below every dash is valid.
                _emit(item, indent + 1, lines)
            else:
                lines.append(f"{pad}- {_emit_scalar(item)}")
    else:
        lines[-1] += f" {_emit_scalar(value)}"


def dump_queue(doc: dict, path: Path) -> None:
    lines: "list[str]" = [
        "# GENERATED by lessons.py - never hand-edit.",
        "# Schema: sdlc/skills/lesson/LESSONS.schema.yaml (in the sdlc plugin).",
    ]
    lines.append("lessons_file_version:")
    _emit(doc.get("lessons_file_version", "1"), 0, lines)
    lines.append("last_updated:")
    _emit(doc.get("last_updated"), 0, lines)
    lines.append("last_ids:")
    _emit(doc.get("last_ids", {"LSN": 0}), 1, lines)
    lines.append("runs:")
    runs = [_ordered(r, RUN_KEYS) for r in doc.get("runs", [])]
    _emit(runs, 1, lines) if runs else lines.append("runs: []") or lines.pop(-2)
    lines.append("lessons:")
    lessons = [_ordered(l, LESSON_KEYS) for l in doc.get("lessons", [])]
    _emit(lessons, 1, lines) if lessons else lines.append("lessons: []") or lines.pop(-2)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def _ordered(mapping: dict, key_order) -> dict:
    out = {k: mapping[k] for k in key_order if k in mapping}
    out.update({k: v for k, v in mapping.items() if k not in out})
    return out


# =============================================================================
# State-file parsing (record-run's input). Three shapes exist in the wild:
#   flat     top-level session_id (prd/ux/design/data/api, repair)
#   sharded  a `sessions:` map keyed "system" / "container|<cid>" (arch/test/task)
#   ledger   a `session:` mapping (the code skill's execution ledger)
# =============================================================================


def parse_state(path: Path, session_key: "str | None"):
    """Return (doc, session_record, shape) or (None, None, None)."""
    if not path.is_file():
        return None, None, None
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None, None, None
    if isinstance(raw.get("sessions"), dict) and raw["sessions"]:
        sessions = raw["sessions"]
        if session_key:
            record = sessions.get(session_key)
            if record is None:
                raise KeyError(session_key)
        else:

            def _lu(item):
                return item[1].get("last_updated") or "" if isinstance(item[1], dict) else ""

            record = max(sessions.items(), key=_lu)[1]
        return raw, record if isinstance(record, dict) else None, "sharded"
    if isinstance(raw.get("session"), dict):
        return raw, raw["session"], "ledger"
    if raw.get("session_id"):
        return raw, raw, "flat"
    return raw, None, None


def _derive_metrics(doc: dict, record: dict, shape: str, finished_at: str) -> dict:
    metrics: dict = {}
    stated = record.get("metrics")
    if isinstance(stated, dict):
        metrics.update(stated)

    started = _parse_iso(record.get("started_at"))
    finished = _parse_iso(finished_at)
    if started and finished and "duration_s" not in metrics:
        metrics["duration_s"] = max(0, int((finished - started).total_seconds()))

    for key, name in (
        ("completed_themes", "themes_completed"),
        ("skipped_themes", "themes_skipped"),
        ("todo_themes", "themes_todo"),
    ):
        value = record.get(key)
        if isinstance(value, list) and name not in metrics:
            metrics[name] = len(value)

    minted = 0
    seen_counter = False
    for source in (record.get("last_ids"), record.get("last_ids_global")):
        if isinstance(source, dict):
            seen_counter = True
            minted += sum(v for v in source.values() if isinstance(v, int))
    by_product = record.get("last_ids_by_product")
    if isinstance(by_product, dict):
        for fam in by_product.values():
            if isinstance(fam, dict):
                seen_counter = True
                minted += sum(v for v in fam.values() if isinstance(v, int))
    if seen_counter and "ids_minted" not in metrics:
        metrics["ids_minted"] = minted

    if shape == "ledger":
        budget = record.get("budget")
        if isinstance(budget, dict) and isinstance(budget.get("units_done"), int):
            metrics.setdefault("units_done", budget["units_done"])
        tasks = doc.get("tasks")
        if isinstance(tasks, dict) and tasks:
            heals = sum(
                t.get("heal_attempts", 0)
                for t in tasks.values()
                if isinstance(t, dict) and isinstance(t.get("heal_attempts"), int)
            )
            metrics.setdefault("heals", heals)
            metrics.setdefault(
                "escalations",
                sum(
                    1
                    for t in tasks.values()
                    if isinstance(t, dict) and t.get("escalated") is True
                ),
            )
            metrics.setdefault(
                "failed",
                sum(
                    1
                    for t in tasks.values()
                    if isinstance(t, dict) and t.get("status") == "failed"
                ),
            )
        components = doc.get("components_done")
        if isinstance(components, dict):
            findings: "set[str]" = set()
            for comp in components.values():
                if isinstance(comp, dict) and isinstance(comp.get("findings"), list):
                    findings.update(str(f) for f in comp["findings"])
            metrics.setdefault("findings_raised", len(findings))
    return metrics


def resolve_plugin_version(args, project_root: Path):
    if getattr(args, "plugin_version", None):
        return args.plugin_version, "flag"
    candidates = []
    if getattr(args, "plugin_root", None):
        candidates.append(Path(args.plugin_root) / ".claude-plugin" / "plugin.json")
    skill_dir = os.environ.get("CLAUDE_SKILL_DIR")
    if skill_dir:
        candidates.append(Path(skill_dir).parent.parent / ".claude-plugin" / "plugin.json")
    for manifest in candidates:
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("version"):
                return str(data["version"]), "manifest"
        except (OSError, ValueError):
            continue
    marker = project_root / MARKER_REL
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
        if data.get("plugin_version"):
            return str(data["plugin_version"]), "marker"
    except (OSError, ValueError):
        pass
    return None, None


def resolve_plugin_root(args) -> "Path | None":
    """The installed plugin's root - the folder holding `.claude-plugin/` and
    `skills/` - or None when nothing names one.

    Same chain as `resolve_plugin_version` minus the marker: `--plugin-root`,
    then `$CLAUDE_SKILL_DIR/../..`. Only a folder that actually carries a
    `skills/` directory counts; an ambient session (no skill dir) gets None,
    and every check that needs the root is skipped rather than guessed.
    """
    candidates = []
    if getattr(args, "plugin_root", None):
        candidates.append(Path(args.plugin_root))
    skill_dir = os.environ.get("CLAUDE_SKILL_DIR")
    if skill_dir:
        candidates.append(Path(skill_dir).parent.parent)
    for root in candidates:
        try:
            if (root / "skills").is_dir():
                return root
        except OSError:
            continue
    return None


# The footer every SKILL.md ends with. Phase 8 passes the same number to
# record-run, and the skills repo's lint_skill_versions.py keeps it equal to
# the newest changelog entry. Re-declared here rather than imported: this file
# is copied standalone into consumer projects.
SKILL_VERSION_RE = re.compile(r'^skill_version:\s*"(\d+\.\d+)"\s*$', re.M)


def skill_version_from_plugin(plugin_root, skill: str) -> "str | None":
    """The installed plugin's `skills/<skill>/SKILL.md` footer, or None.

    The fallback for a lesson about a skill with no state file in this project
    (setup keeps none; an ambient `/sdlc:lesson` may be about a skill that never
    ran here). Without it 8 of the first 23 collected lessons carried no
    skill_version at all, and the maintainer could not date them.
    """
    if not plugin_root or not skill:
        return None
    try:
        text = (Path(plugin_root) / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None
    found = SKILL_VERSION_RE.findall(text)
    return found[-1] if found else None


def running_skill() -> "str | None":
    """The skill whose SKILL.md is executing - `$CLAUDE_SKILL_DIR`'s folder
    name - or None in an ambient session."""
    skill_dir = os.environ.get("CLAUDE_SKILL_DIR")
    return Path(skill_dir).name if skill_dir else None


def date_from_footer(skill: str, state_version, footer) -> "tuple[str | None, str | None]":
    """(skill_version to record, hint) once a run is known to be INSIDE `skill`.

    The SKILL.md footer is the version executing right now; a state file that
    says otherwise was never re-stamped - the code ledger records the version
    that CREATED it and nothing bumps it. Twelve consumer lessons and four run
    records were dated to code 0.3 while the skill was at 0.14, so `--delta`
    could date none of them (ledger IMP-095). An interview state IS re-stamped
    by its resume migration, but a run that spans an upgrade then has two
    truthful numbers and nothing recording which; the footer is the one that
    just ran. The state's number is kept beside it as `state_skill_version`,
    so nothing is lost - only the date is right."""
    if footer and state_version and str(footer) != str(state_version):
        return str(footer), (
            f"the state file for /sdlc:{skill} says skill_version {state_version} but the "
            f"SKILL.md running now is {footer} - dated from {footer}, the state file's number "
            f"kept as state_skill_version (a ledger records the version that CREATED it, and "
            f"a run that spanned an upgrade has two truthful numbers; the footer is the one "
            f"that just ran)"
        )
    return (str(footer) if footer else (str(state_version) if state_version else None)), None


def ambient_ledger_footer_note(skill: str, state_version, footer) -> "tuple[str | None, str | None]":
    """(footer_skill_version, hint) for an AMBIENT lesson about ANOTHER
    skill's ledger-shaped state, when it disagrees with that skill's
    installed footer.

    Unlike `date_from_footer`, this is never "a run known to be inside
    `skill`" - the caller is a different skill, or no skill at all, so the
    footer is NOT "the SKILL.md running now" (that phrase would be a lie
    here). A ledger (code today) records only the version that CREATED it
    and nothing bumps it between runs, so the state's number is what
    actually wrote what this ambient observation is about - `skill_version`
    stays it, unchanged. The footer is kept beside it as
    `footer_skill_version` so a human reads the skew at triage, and
    `--delta` - which dates a lesson from the OLDER of the two numbers it
    finds - can date it from the newer fix that landed since, instead of
    silently trusting a ledger nothing has re-stamped."""
    if not (footer and state_version and str(footer) != str(state_version)):
        return None, None
    return str(footer), (
        f"the {skill} ledger says skill_version {state_version} but the installed "
        f"SKILL.md footer is {footer} (not currently running - skill_version stays "
        f"{state_version}, the version that wrote what was observed) - footer kept "
        f"as footer_skill_version {footer}"
    )


def installed_plugin_version(project_root: Path) -> "str | None":
    """What /sdlc:setup last copied into `.claude/sdlc/` - the marker's number.

    It can lag the plugin cache that `claude plugin update` moves, and a lesson
    about an INSTALLED helper (docs_index.py, findings.py, this file) is about
    this number, not the manifest's. Recorded next to plugin_version whenever
    the two differ, so the maintainer dates the defect from the older one.
    """
    version = read_marker(project_root).get("plugin_version")
    return str(version) if version else None


_CAPABILITY_RE = re.compile(r"^CAPABILITY_VERSION\s*=\s*[\"']?(\d+)", re.M)


def _version_older(installed, running) -> bool:
    """True when `installed` is older than `running`. Dotted numbers compare
    part by part as integers (0.10.0 is newer than 0.9.14); anything that does
    not parse counts as older when the two differ."""
    try:
        return tuple(int(p) for p in str(installed).split(".")) < \
            tuple(int(p) for p in str(running).split("."))
    except ValueError:
        return str(installed) != str(running)


def setup_lag(project_root: Path, plugin_version, plugin_root) -> "str | None":
    """One plain sentence when /sdlc:setup's install lags the running plugin.

    record-run already stored installed_version when the marker and the plugin
    differed, and printed only [OK]; skills then ran an old docs_index.py that
    rejected --stale/--stamp with exit 2, and nothing asked for a /sdlc:setup
    re-run (ledger IMP-108). `plugin_version` is the RUNNING plugin's (None when
    only the marker named one); `plugin_root` enables the docs_index capability
    compare, which catches a lag the version numbers do not show.
    """
    marker = read_marker(project_root)
    if not marker:
        return None
    reasons = []
    installed = marker.get("plugin_version")
    if plugin_version and installed and _version_older(installed, plugin_version):
        reasons.append(f"installed by plugin {installed}, plugin {plugin_version} is running")
    installed_cap = (marker.get("helpers") or {}).get("docs_index")
    if plugin_root and installed_cap is not None:
        try:
            text = (Path(plugin_root) / "skills" / "setup" / "docs_index.py").read_text(
                encoding="utf-8")
        except OSError:
            text = ""
        match = _CAPABILITY_RE.search(text)
        if match and _version_older(installed_cap, match.group(1)):
            reasons.append(f"docs_index.py there is capability {installed_cap}, "
                           f"the plugin's is {match.group(1)}")
    if not reasons:
        return None
    return ("the helper scripts in .claude/sdlc/ are older than this plugin ("
            + "; ".join(reasons) + ") - run /sdlc:setup once to update them; until "
            "then skills run the plugin's own copies")


# =============================================================================
# Lesson tokenizer + recurrence matching.
#
# Two callers share this code and MUST agree, or the loop contradicts itself:
# `add` uses it to notice that a lesson already in this project's queue is the
# same defect being reported again, and the maintainer's
# lessons/cluster_lessons.py uses it to notice the same defect arriving from a
# DIFFERENT project. One is a bump, the other is one IMP grouping two lessons;
# both answer "are these the same defect?" and would rot separately. This file
# is copied verbatim into every consumer project, so keeping the code here -
# rather than in a module only the maintainer's repo has - is what makes the
# two sides provably the same code rather than two implementations that agree
# today.
#
# What the matching keys on, and why NOT `kind`:
#
#   Measured on the collected corpus, `kind` disagreed on 3 out of 3 pairs that
#   were genuinely the same defect (instruction_conflict vs drift;
#   validator_false_reject vs terminal_output; process vs instruction_gap).
#   Two people describing one defect pick different labels for it, so keying on
#   the label hides exactly the duplicates worth finding. `skill` and
#   `where.file` are the stable half - they name the thing that is broken
#   rather than an opinion about it - so they block, and the free text decides.
#
# Splitting identifiers into atoms is the whole trick. `DataDeferralIndex.defer
# / deprecation_warning` and `DataDeferralIndex.deprecation_warning / defer`
# describe one defect and share zero whole-string tokens; split on dots,
# underscores and CamelCase humps they are the same four atoms.
# =============================================================================

_TOKEN_STOPWORDS = frozenset("""
the a an and or of to in on is are it its for with that this so not but be as
by from at every any no all one two own only still while which what when where
who how than then there their they them has have had was were will would can
could should may might must does did done none non per via out into over under
before after same other another each both few more most some such too very just
now the sdlc claude
""".split())

_TOKEN_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_./\\-]*|\d{3,5}")
_TOKEN_SPLIT_RE = re.compile(r"[._/\\-]+")
_TOKEN_HUMP_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z][a-z]+|[a-z]+|\d+")


def _atoms(word: str) -> "set[str]":
    """One raw word -> its atoms. `run_index.py` -> {run, index}."""
    out = set()
    for piece in _TOKEN_SPLIT_RE.split(word):
        for atom in _TOKEN_HUMP_RE.findall(piece):
            low = atom.lower()
            if len(low) > 2 and low not in _TOKEN_STOPWORDS:
                out.add(low)
    return out


def tokenize(text) -> "set[str]":
    """Free text -> the atom set two descriptions of one defect should share.

    Bare 3-5 digit runs survive as their own token: a line number quoted in two
    projects' evidence ("validate_schema.py:2367") is strong agreement.
    """
    out: "set[str]" = set()
    for word in _TOKEN_WORD_RE.findall(str(text or "")):
        out |= _atoms(word)
    return out


def _jaccard(a: "set[str]", b: "set[str]") -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def lesson_tokens(lesson: dict) -> "dict[str, set[str]]":
    """The three token sets a lesson is compared on."""
    where = lesson.get("where") or {}
    evidence = lesson.get("evidence")
    detail = " ".join([
        str(where.get("anchor") or ""),
        str(lesson.get("suggested_fix") or ""),
        " ".join(str(e) for e in evidence) if isinstance(evidence, list) else "",
    ])
    return {
        "anchor": tokenize(where.get("anchor")),
        "detail": tokenize(detail),
        "summary": tokenize(lesson.get("summary")),
    }


# Weights: the anchor names the symbol, so it leads; the detail (anchor + fix +
# evidence) carries quoted code and line numbers; the summary is prose and
# varies most between two authors, so it decides least.
SIM_WEIGHTS = {"anchor": 0.45, "detail": 0.30, "summary": 0.25}

# Propose at 0.25 and call it strong at 0.45. On the corpus these thresholds
# were derived from, the three true pairs scored 0.58 / 0.50 / 0.31 and the
# next-best unrelated pair scored 0.15, so 0.25 sits in open space rather than
# on a boundary. They are deliberately not tight: this proposes candidates for
# a human to confirm, and a missed duplicate costs more than a rejected one.
SIM_PROPOSE = 0.25
SIM_STRONG = 0.45


def strip_skill_prefix(skill, where_file) -> str:
    """`where.file` is relative to the skill's folder, but authors keep writing
    it with that folder in front (`code/SKILL.md`, `repair/doctor.py`) - seven
    of one collect's 34 lessons did. The file exists either way, so every
    reader normalizes instead of calling it missing (ledger IMP-041)."""
    f = str(where_file or "").replace("\\", "/")
    s = str(skill or "")
    if not s:
        return f
    for prefix in (f"sdlc/skills/{s}/", f"skills/{s}/", f"{s}/"):
        if f.startswith(prefix) and len(f) > len(prefix):
            return f[len(prefix):]
    return f


def find_prefix_skill(plugin_root, skill, where_file):
    """The OTHER real skill folder `where_file`'s leading segment names, when
    the remainder actually exists there - (skill_name, remainder) or None.

    `strip_skill_prefix` only ever tries the lesson's OWN `skill` as a
    candidate prefix; a where.file legitimately prefixed with a DIFFERENT
    real skill folder (`arch/validate_schema.py` filed under `--skill test`)
    fell through every reader to a basename-only search. A cross-skill
    prefix counts only when `sdlc/skills/<name>/<rest>` EXISTS on disk - a
    repo's own `test/` directory is not the `test` skill folder, and a
    same-named subfolder that happens to exist under the WRONG skill must
    not be mistaken for the real owner (ledger IMP-143).
    """
    if not plugin_root:
        return None
    f = str(where_file or "").replace("\\", "/")
    own = str(skill or "")
    skills_dir = Path(plugin_root) / "skills"
    try:
        names = sorted(p.name for p in skills_dir.iterdir() if p.is_dir())
    except OSError:
        return None
    for name in names:
        if name == own:
            continue
        for prefix in (f"sdlc/skills/{name}/", f"skills/{name}/", f"{name}/"):
            if f.startswith(prefix) and len(f) > len(prefix):
                rest = f[len(prefix):]
                if (skills_dir / name / rest).exists():
                    return name, rest
    return None


def resolve_subject(lesson: dict, plugin_root=None) -> "tuple[str, str]":
    """(owner_skill, resolved_file) - the file this lesson is REALLY about.

    Own-skill `strip_skill_prefix` first; when that left `where.file`
    unchanged (no prefix matching the lesson's OWN skill), fall back to
    `find_prefix_skill` so a where.file legitimately prefixed with a
    DIFFERENT real skill folder resolves to that folder's owner, not the
    filed skill. Mirrors `lesson_hints`'s existing two-step resolution
    (ledger IMP-179). `plugin_root=None` (no skill folder set known) skips
    the fallback and returns the filed skill unchanged - no hidden default
    root, so a caller that never passes one keeps today's own-skill-only
    behaviour.
    """
    skill = str(lesson.get("skill") or "")
    where_file = (lesson.get("where") or {}).get("file")
    resolved = strip_skill_prefix(skill, where_file)
    raw = str(where_file or "").replace("\\", "/")
    if plugin_root and resolved == raw:
        hit = find_prefix_skill(plugin_root, skill, where_file)
        if hit:
            return hit
    return skill, resolved


def same_subject(a: dict, b: dict, plugin_root=None) -> bool:
    """The blocking keys: the same OWNER skill and the same file, or no
    comparison.

    Cheap to check and it is what makes an all-pairs sweep affordable as the
    inbox grows. Resolved via `resolve_subject` so a where.file prefixed
    with a DIFFERENT real skill folder lines up with a lesson filed
    directly under that folder's own skill, not just a same-filed-skill
    pair (ledger IMP-179; `plugin_root` is required for the cross-skill
    fallback - `None` keeps the own-skill-only comparison).
    """
    skill_a, fa = resolve_subject(a, plugin_root)
    skill_b, fb = resolve_subject(b, plugin_root)
    if skill_a != skill_b:
        return False
    return bool(fa) and fa == fb


def similarity(a: dict, b: dict, a_tokens=None, b_tokens=None, plugin_root=None) -> float:
    """0..1 that two lessons report the same defect. 0 when subjects differ."""
    if not same_subject(a, b, plugin_root=plugin_root):
        return 0.0
    ta = a_tokens if a_tokens is not None else lesson_tokens(a)
    tb = b_tokens if b_tokens is not None else lesson_tokens(b)
    return sum(weight * _jaccard(ta[part], tb[part])
               for part, weight in SIM_WEIGHTS.items())


def shared_tokens(a: dict, b: dict) -> "list[str]":
    """The atoms two lessons agree on - the evidence FOR a proposed match.

    A score with no visible reason is not reviewable, and this proposes to a
    human who has to be able to disagree with it.
    """
    ta, tb = lesson_tokens(a), lesson_tokens(b)
    return sorted((ta["anchor"] | ta["detail"]) & (tb["anchor"] | tb["detail"]))


def _occurrences(lesson: dict) -> int:
    """How many times this defect has been reported. Absent means once."""
    n = lesson.get("occurrences")
    return n if isinstance(n, int) and n > 0 else 1


def stamp_recurrence(prior: dict, fresh: dict) -> dict:
    """Fold a repeat report into the lesson already in the queue.

    Three things happen. The count goes up, because how often a defect bites is
    what ranks it for the maintainer. Evidence the repeat brought that the
    original lacked is appended (within the schema's cap) - the second sighting
    usually knows something the first did not. And `sent_at` is cleared, so the
    updated entry rides the next batch instead of sitting at a stale count on
    the relay forever; the maintainer's merge is keyed on lsn_id, so it updates
    in place rather than arriving twice.
    """
    prior["occurrences"] = _occurrences(prior) + 1
    prior.setdefault("first_seen_at", prior.get("raised_at"))
    prior["last_seen_at"] = fresh.get("raised_at") or _iso_utc_now()
    prior.pop("sent_at", None)

    have = {str(line).strip() for line in (prior.get("evidence") or [])}
    room = MAX_EVIDENCE - len(prior.get("evidence") or [])
    for line in (fresh.get("evidence") or []):
        if room <= 0:
            break
        if str(line).strip() not in have:
            prior.setdefault("evidence", []).append(line)
            have.add(str(line).strip())
            room -= 1

    # A repeat that is worse than the original raises the severity: delivery
    # latency keys on it, and a defect that escalated to blocker should not
    # wait for the weekly batch because its first sighting was cosmetic.
    if SEVERITIES.index(str(fresh.get("severity"))) < SEVERITIES.index(str(prior.get("severity"))):
        prior["severity"] = fresh["severity"]
    if not prior.get("suggested_fix") and fresh.get("suggested_fix"):
        prior["suggested_fix"] = fresh["suggested_fix"]
    # A repeat of a lesson the maintainer had CLOSED is the reopen signal: the
    # fix regressed, or the wontfix/dismissed call was wrong. Status goes back
    # to open; imp_id / fixed_in / verdict_at stay, so `list` can say "open
    # again after 0.9.8", the next reconcile can tell this stale verdict from
    # a newer one, and the maintainer's digest lists it as a REOPEN candidate.
    # A triaged lesson stays triaged: its item is open already, and the bumped
    # count is what has to travel.
    if prior.get("status") in CLOSED_STATUSES:
        prior["status"] = "open"
    return prior


# =============================================================================
# Verdicts - the maintainer's word on a lesson, coming back to the project.
#
# A lesson leaves as `open`. The maintainer groups it into a ledger item, fixes
# the skill, ships a version - and until this section existed, nothing told the
# project. One consumer carried 55 fixed defects as live traps for months and
# re-filed two of them as new lessons. Two channels close that loop, and both
# go through `apply_verdict` so they obey one rule:
#
#   * the installed plugin ships skills/lesson/VERDICTS.yaml, rows keyed by the
#     opaque project id; `reconcile` (run by every record-run) stamps the rows
#     that name THIS project;
#   * the maintainer's collector stamps a registered repo directly (`--mark`).
#
# The one rule that is not obvious: a lesson that RECURRED after its verdict
# (stamp_recurrence set it back to `open`, keeping the verdict fields) is left
# alone by the very verdict it recurred after - re-closing it would erase the
# only signal the maintainer has that the fix regressed. A newer fix, or a
# reopened item, still stamps.
# =============================================================================


def _reopened_from(lesson: dict):
    """The verdict a reopened lesson carried before its recurrence, as the
    (status, imp_id, fixed_in) triple apply_verdict compares against - or None
    when the lesson was never closed. Only resolved / wontfix / dismissed
    reopen (stamp_recurrence), so the fields left behind say which it was."""
    if lesson.get("status") != "open" or not lesson.get("verdict_at"):
        return None
    if lesson.get("fixed_in"):
        return ("resolved", str(lesson.get("imp_id") or "") or None, str(lesson["fixed_in"]))
    if lesson.get("imp_id"):
        return ("wontfix", str(lesson["imp_id"]), None)
    return ("dismissed", None, None)


def apply_verdict(lesson: dict, verdict: dict, today: "str | None" = None) -> "str | None":
    """Stamp one maintainer verdict onto one lesson.

    Returns the status written, "reopened" when a reopened lesson was left
    alone because this is the verdict it recurred after, or None when the
    lesson already carried it (so a second pass changes nothing).
    """
    status = str(verdict.get("status") or "")
    if status not in VERDICT_STATUSES:
        return None
    imp_id = str(verdict["imp_id"]) if verdict.get("imp_id") else None
    fixed_in = str(verdict["fixed_in"]) if verdict.get("fixed_in") else None
    target = (status, imp_id, fixed_in)
    prior = _reopened_from(lesson)
    if prior is not None and prior == target:
        return "reopened"
    current = (str(lesson.get("status") or ""),
               str(lesson["imp_id"]) if lesson.get("imp_id") else None,
               str(lesson["fixed_in"]) if lesson.get("fixed_in") else None)
    if current == target:
        return None
    lesson["status"] = status
    for key, value in (("imp_id", imp_id), ("fixed_in", fixed_in)):
        if value:
            lesson[key] = value
        else:
            lesson.pop(key, None)
    lesson["verdict_at"] = today or _iso_utc_now()[:10]
    return status


def project_ids(root: Path) -> "set[str]":
    """Every id this project may be known by in a verdict manifest: the
    marker's project_uuid and project_id, plus the legacy path hash (a report
    delivered before the uuid existed was keyed by it)."""
    ids = {project_id_for(root)}
    stored = read_marker(root).get("telemetry")
    if isinstance(stored, dict):
        for key in ("project_uuid", "project_id"):
            if stored.get(key):
                ids.add(str(stored[key]))
    return ids


def load_verdicts(path: Path) -> "list[dict]":
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = raw.get("rows") if isinstance(raw, dict) else None
    return [r for r in (rows or [])
            if isinstance(r, dict) and r.get("project") and r.get("lsn_id")]


def reconcile(root: Path, plugin_root, today: "str | None" = None) -> dict:
    """Apply the installed plugin's verdict manifest to this project's queue.

    Returns {status: no-manifest | unreadable | no-rows | ok, path, queue,
    stamped: {status: n}, reopened: n, written: bool, problem}. Never raises
    for a missing or unreadable manifest - a close must not fail on it.
    """
    out = {"status": "no-manifest", "path": None, "queue": Path(root) / QUEUE_REL,
           "stamped": {}, "reopened": 0, "written": False, "problem": None}
    if not plugin_root:
        return out
    path = Path(plugin_root) / VERDICTS_REL
    if not path.is_file():
        return out
    out["path"] = path
    try:
        rows = load_verdicts(path)
    except (OSError, yaml.YAMLError) as e:
        out.update(status="unreadable", problem=str(e))
        return out
    ids = project_ids(root)
    mine = {str(r["lsn_id"]): r for r in rows if str(r["project"]) in ids}
    try:
        queue = load_queue(out["queue"])
    except (OSError, yaml.YAMLError, ValueError) as e:
        out.update(status="unreadable", problem=str(e))
        return out
    named = [l for l in queue["lessons"] if isinstance(l, dict) and str(l.get("lsn_id")) in mine]
    if not named:
        out["status"] = "no-rows"
        return out
    out["status"] = "ok"
    stamped: "dict[str, int]" = {}
    for lesson in named:
        result = apply_verdict(lesson, mine[str(lesson["lsn_id"])], today)
        if result == "reopened":
            out["reopened"] += 1
        elif result:
            stamped[result] = stamped.get(result, 0) + 1
    out["stamped"] = stamped
    if stamped:
        queue["last_updated"] = _iso_utc_now()
        try:
            dump_queue(queue, out["queue"])
        except OSError as e:
            out.update(status="unreadable", problem=str(e))
            return out
        out["written"] = True
    return out


def verdict_summary(summary: dict) -> str:
    """One line for the terminal, from reconcile()'s result (status ok)."""
    stamped = summary["stamped"]
    n = sum(stamped.values())
    if not n and not summary["reopened"]:
        return (f"verdicts from {summary['path']}: nothing new - every lesson it names "
                f"already carries its verdict.")
    parts = ", ".join(f"{stamped[k]} {k}" for k in VERDICT_STATUSES if stamped.get(k))
    text = f"verdicts from {summary['path']}: {n} lesson(s) stamped"
    if parts:
        text += f" ({parts})"
    if summary["reopened"]:
        text += (f", {summary['reopened']} left open - recurred after the verdict the "
                 f"manifest records, which the maintainer reads as a reopen")
    return text + f" -> {summary['queue']}"


def verdict_tag(lesson: dict, installed: "str | None") -> str:
    """What `list` prints in the brackets: the status, with the verdict's
    facts beside it, and `- not installed` when the fix is newer than what
    /sdlc:setup last copied here."""
    prior = _reopened_from(lesson)
    if prior is not None:
        if prior[0] == "resolved":
            return f"open again after {prior[2]}"
        if prior[0] == "wontfix":
            return f"open again - {prior[1]} was wontfix"
        return "open again - was dismissed"
    status = str(lesson.get("status") or "open")
    if status == "resolved":
        fixed_in = lesson.get("fixed_in")
        tag = f"resolved {fixed_in}" if fixed_in else "resolved"
        if fixed_in and installed and _version_older(installed, fixed_in):
            tag += " - not installed"
        return tag
    if status in ("triaged", "wontfix") and lesson.get("imp_id"):
        return f"{status} {lesson['imp_id']}"
    return status


def find_recurrence(queue: dict, lesson: dict, threshold: float = SIM_STRONG,
                     plugin_root=None):
    """The open lesson in `queue` this one is a repeat of, or None.

    Mirrors findings.py's find_recurrence: same question, same answer shape.
    The threshold is SIM_STRONG rather than SIM_PROPOSE because this one acts
    on its own - a wrong bump silently merges two real defects, where a wrong
    cluster proposal is just rejected by the maintainer. `plugin_root`
    (ledger IMP-179) lets a same-project resend filed under a cross-skill
    where.file prefix still be caught here, not only by the clusterer.
    """
    best, best_score = None, 0.0
    tokens = lesson_tokens(lesson)
    for existing in queue.get("lessons", []):
        if not isinstance(existing, dict) or existing is lesson:
            continue
        score = similarity(lesson, existing, a_tokens=tokens, plugin_root=plugin_root)
        if score >= threshold and score > best_score:
            best, best_score = existing, score
    return (best, best_score) if best else (None, 0.0)


# =============================================================================
# Lesson hints - what a proper lesson looks like, checked mechanically.
#
# These are HINTS, never rejects. A reject at a skill's close phase would lose
# the lesson (the self-review calls `add` once and moves on); the installed
# helpers can be older than the plugin the check runs against; and an ambient
# call has no plugin root to check against at all, so the same command would
# pass or fail depending on who typed it. A wrong path in the queue costs the
# maintainer seconds at triage; a lesson refused at the source is gone.
# `add` prints them after [OK]; the maintainer's collector prints the same
# ones as triage flags.
# =============================================================================

_PLACEHOLDER_RE = re.compile(
    r"^\s*(?:test|testing|todo|tbd|ignore|x+|asdf|foo|bar|baz|dummy|placeholder|"
    r"lorem ipsum|n/?a)(?:\s*[-:,.]*\s*(?:test|ignore|me|this|todo|entry|lesson))*"
    r"\s*[.!]?\s*$",
    re.I,
)
_STOPPED_RE = re.compile(
    r"abort|could not|couldn.t|cannot|can.t|stopp?ed|blocked|crash|died|"
    r"did not finish|unfinished|exit(?:ed)? [1-9]|traceback|hung",
    re.I,
)

# kind -> (does where.file look right?, what it usually names). A miss is a
# hint because this is a heuristic: drift, terminal_output and
# instruction_conflict defects can live in any file, so they are absent.
_KIND_FILE_EXPECTATIONS = {
    "validator_false_reject": (
        lambda f: "validate" in f or f.startswith("_smoke/"),
        "the validator (validate_schema.py) or the fixture that reproduces it"),
    "validator_false_accept": (
        lambda f: "validate" in f or f.startswith("_smoke/"),
        "the validator (validate_schema.py) or the fixture that reproduces it"),
    "question_quality": (
        lambda f: f.endswith("-questions.yaml"),
        "the <skill>-questions.yaml inventory, with the question id in --where-anchor"),
    "schema_gap": (
        lambda f: f.endswith(".schema.yaml"),
        "the <NAME>.schema.yaml that lacks the field"),
    "script_bug": (
        lambda f: f.endswith((".py", ".mjs", ".js", ".sh", ".ps1")),
        "the script that misbehaved"),
    "instruction_gap": (
        lambda f: f.endswith(".md"),
        "SKILL.md or the references/ file that should carry the instruction"),
    "process": (
        lambda f: f.endswith(".md"),
        "SKILL.md or the references/ file that states the flow"),
}


def _list_skill_folder(folder: Path) -> str:
    top = sorted(p.name for p in folder.iterdir() if p.is_file())
    refs = folder / "references"
    if refs.is_dir():
        top += sorted(f"references/{p.name}" for p in refs.iterdir() if p.is_file())
    return ", ".join(top[:12]) + (" ..." if len(top) > 12 else "")


def lesson_hints(lesson: dict, plugin_root=None, installed_version=None) -> "list[str]":
    """Reasons a maintainer would send this lesson back. Pure; never raises.

    `plugin_root` enables the existence checks (skill folder, where.file)
    against the plugin the caller can see; None skips them. `installed_version`
    (the marker's, when it differs from the plugin's) only changes the wording
    of a missing-file hint: a file the newer plugin dropped is not a typo.
    """
    hints: "list[str]" = []
    skill = str(lesson.get("skill") or "")
    where = lesson.get("where") or {}
    where_file = str(where.get("file") or "").replace("\\", "/")
    kind = lesson.get("kind")
    summary = str(lesson.get("summary") or "")
    evidence = [str(e) for e in (lesson.get("evidence") or []) if e is not None]
    plugin_version = lesson.get("plugin_version")

    # 1. does the plugin the caller can see have this skill and this file?
    if plugin_root and skill and where_file:
        skills_dir = Path(plugin_root) / "skills"
        folder = skills_dir / skill
        try:
            if not folder.is_dir():
                have = ", ".join(sorted(p.name for p in skills_dir.iterdir() if p.is_dir()))
                hints.append(f"no skill folder {skill}/ in the plugin"
                             + (f" (it has: {have})" if have else "")
                             + " - is --skill right?")
            elif (not (folder / where_file).exists()
                  and strip_skill_prefix(skill, where_file) != where_file
                  and (folder / strip_skill_prefix(skill, where_file)).exists()):
                stripped = strip_skill_prefix(skill, where_file)
                hints.append(
                    f"{where_file} carries the skill folder as a prefix - where.file is "
                    f"relative to {skill}/, so this lesson is about {stripped}; drop the "
                    f"leading {where_file[:len(where_file) - len(stripped)]}")
            elif not (folder / where_file).exists():
                msg = f"{where_file} is not in {skill}/"
                if plugin_version:
                    msg += f" at plugin {plugin_version}"
                msg += f" (it has: {_list_skill_folder(folder)})"
                prefix_hit = find_prefix_skill(plugin_root, skill, where_file)
                if prefix_hit:
                    prefix_skill, rest = prefix_hit
                    msg += (f"; {where_file} is {rest} with the {prefix_skill}/ folder "
                            f"as prefix - did you mean --skill {prefix_skill}?")
                else:
                    base = where_file.rsplit("/", 1)[-1]
                    elsewhere = [other.name for other in sorted(skills_dir.iterdir())
                                 if other.is_dir() and other.name != skill
                                 and (other / base).exists()]
                    if elsewhere:
                        msg += (f"; {base} lives in {'/'.join(elsewhere)}/ - did you mean "
                                f"--skill {elsewhere[0]}?")
                if (installed_version and plugin_version
                        and str(installed_version) != str(plugin_version)):
                    msg += (f"; the helpers installed here are from {installed_version}, "
                            f"so if the file was removed since, say so in the evidence")
                hints.append(msg)
        except OSError:
            pass

    # 2. does the kind fit the file?
    expectation = _KIND_FILE_EXPECTATIONS.get(kind)
    if expectation and where_file and not expectation[0](where_file):
        hints.append(f"kind {kind} usually names {expectation[1]}, not {where_file}")

    # 3. is there anything to judge?
    if kind == "other":
        hints.append("kind other is the one nobody can act on - pick the kind that fits")
    placeholder = (
        len(summary.strip()) < 15
        or bool(_PLACEHOLDER_RE.match(summary))
        or (bool(evidence) and all(_PLACEHOLDER_RE.match(e) for e in evidence))
        or (bool(evidence) and all(e.strip() == summary.strip() for e in evidence))
    )
    if placeholder:
        hints.append("summary/evidence read like a placeholder - the maintainer will "
                     "dismiss it")

    # 4. does blocker mean what it says?
    if (lesson.get("severity") == "blocker" and lesson.get("agent_action") != "stopped"
            and not any(_STOPPED_RE.search(t) for t in [summary] + evidence)):
        hints.append("blocker means the run could not finish, and it sends at the next "
                     "close - nothing here says the run stopped")
    return hints


def _print_hints(hints: "list[str]", written: bool) -> None:
    if not hints:
        return
    print(f"Check: {hints[0]}")
    for hint in hints[1:]:
        print(f"       {hint}")
    if written:
        print("       (recorded as is - the maintainer sees the same checks at triage)")
    else:
        print("       (nothing written - fix the flags, then run add without --dry-run)")


# =============================================================================
# Telemetry: redaction, batching, delivery (CLAUDE.md 15).
#
# A lesson is about the PLUGIN, so the report that travels carries skill file
# locations, id families and counts. Three mechanisms keep it that way once the
# report starts leaving the machine on its own:
#
#   redaction  strips absolute paths and e-mail addresses out of free text, and
#              replaces the project's directory name with an opaque project_id.
#   batching   a `blocker` mails at the next close; everything else rides a
#              weekly batch, so a consenting project costs a few mails a year.
#   delivery   one POST to the maintainer's own relay, which holds the mail
#              provider's key server-side. This file is copied verbatim into
#              every consumer project, so it carries a URL and a public tag and
#              never a credential. Relay source: lessons/relay/ in the skills
#              repo.
#
# Sending happens only at a skill CLOSE (record-run, /sdlc:lesson) or on an
# explicit `export --send`, never mid-run, and never at all unless the project
# opted in at /sdlc:setup. Every failure is swallowed into a [DRAFT] line: this
# is the plugin's only network call, and it must never fail a skill run.
# =============================================================================

# The maintainer's relay. It holds the mail provider's secret server-side, so
# this file - which /sdlc:setup copies verbatim into every consumer project -
# never carries a credential. Source and deploy notes: lessons/relay/ in the
# skills repo. An unconfigured endpoint disables delivery cleanly.
RELAY_ENDPOINT = "https://lessons.sdlc.workers.dev"  # $SDLC_LESSONS_ENDPOINT

# A PUBLIC tag, deliberately not a credential: this file is open source, so
# anyone can read the value. It only lets the relay drop scanner noise; real
# abuse control lives in the relay. Never put a real secret here.
RELAY_TOKEN = "sdlc-lessons-v1"  # $SDLC_LESSONS_TOKEN

# An explicit, honest client name. REQUIRED, not cosmetic: Cloudflare's default
# bot rules answer 403 (error 1010) to the "Python-urllib/x.y" User-Agent that
# urllib sends when nothing sets one, so leaving it unset breaks every delivery
# on a workers.dev relay. This identifies the client truthfully - it is not a
# browser string, and must never become one.
USER_AGENT = "sdlc-lessons/1.0 (+https://github.com/anthropics/claude-code)"

MAX_PAYLOAD_BYTES = 90_000  # the free relay tier carries no attachments

TELEMETRY_MODES = ("off", "ask", "auto")
TELEMETRY_DEFAULTS = {
    "mode": "off",
    "consented_on": None,
    "project_id": None,
    "project_uuid": None,  # minted once; see project_uuid_for
    "batch_days": 7,
    "batch_max": 10,
    "runs_only_days": 30,
    "retry_after_hours": 6,
    "last_sent_at": None,
    "last_attempt_at": None,  # set on FAILURE only; its presence means the
    # last attempt failed and is cooling down.
    "last_sent_count": 0,
}

# Which run metrics may travel. `metrics` is an open mapping each skill fills
# from its own state file, so unfiltered it is an unbounded channel out of the
# user's project - that is what has to be closed.
#
# A fixed allowlist closed it, but only by naming the keys that existed when it
# was written: skills went on to emit `own_toolchain`, `scripts_written` and
# `idempotence_proved`, all harmless counts, and the maintainer never saw one
# of them or any sign that they had been dropped. Silence is the wrong failure
# mode for a list that has to be maintained in a different repo from the code
# that grows it.
#
# So the rule is about the SHAPE of a value rather than a roster of names. A
# number or a flag says how much or whether - it cannot carry a path, a name or
# a sentence out of the project no matter what a skill puts in it. Strings,
# lists and mappings can, so they stay out, with `free_text_by_question`
# (question ids -> counts, never answers) the one audited exception. The key
# name is a channel too, so it must look like an identifier, and the count is
# capped: this travels for the maintainer's telemetry, not as free storage.
METRIC_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
MAX_METRIC_KEYS = 32

_FILE_URL_RE = re.compile(r"file://[^\s\"',;]*")
_ABS_WIN_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"',;]*")
_ABS_POSIX_RE = re.compile(r"/(?:home|Users|root|var|opt|mnt|srv|tmp)/[^\s\"',;]*")
_EMAIL_RE = re.compile(r"[^\s\"',;<>()]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def project_id_for(root: Path) -> str:
    """The legacy project id: a hash of the project's absolute path.

    Still computed, because reports already delivered under it must keep
    reconciling to the same project. Two things are wrong with it and neither
    is fixable in place: moving or renaming the directory mints a new identity
    for a project that did not change, and a hash of a guessable string is not
    opaque - common layouts can simply be enumerated until one matches. Prefer
    project_uuid_for.
    """
    from hashlib import sha256

    return sha256(str(Path(root).resolve()).encode("utf-8")).hexdigest()[:12]


def project_uuid_for(root: Path) -> "str | None":
    """A stable, opaque id for one project - minted once, then remembered.

    Random rather than derived, so it survives a move and has no preimage to
    guess. It lives in the marker's telemetry block, which is where the
    project's consent already lives: a project that never opted in never mints
    one, and one that opted out keeps whatever it had.

    None when the project has no marker (it never ran /sdlc:setup, so it is not
    delivering anything anyway) or the marker cannot be written - callers fall
    back to project_id_for, which always answers.
    """
    stored = read_marker(root).get("telemetry")
    if isinstance(stored, dict) and stored.get("project_uuid"):
        return str(stored["project_uuid"])
    import uuid

    minted = str(uuid.uuid4())
    return minted if write_telemetry(root, {"project_uuid": minted}) else None


def environment() -> dict:
    """The machine facts a maintainer needs to reproduce a defect.

    Deliberately two coarse values. Several live lessons are about behaviour
    only Windows shows - CRLF line endings, an unset $TMPDIR - and arrived with
    no way to tell which platform raised them, so the maintainer could not tell
    a universal defect from a local one. `sys.platform` and the Python
    major.minor answer that; anything finer would start describing the user's
    machine rather than the defect's conditions.
    """
    return {
        "os": sys.platform,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _redact(value):
    """Strip absolute paths and e-mail addresses from one free-text field.

    Skill-relative paths (`sdlc/skills/prd/SKILL.md`) survive untouched - they
    are the whole point of a lesson.
    """
    if not isinstance(value, str):
        return value
    text = _FILE_URL_RE.sub("<path>", value)
    text = _ABS_WIN_RE.sub("<path>", text)
    text = _ABS_POSIX_RE.sub("<path>", text)
    return _EMAIL_RE.sub("<email>", text)


def _redact_lesson(lesson: dict) -> dict:
    out = dict(lesson)
    out["summary"] = _redact(out.get("summary"))
    if out.get("suggested_fix"):
        out["suggested_fix"] = _redact(out["suggested_fix"])
    if isinstance(out.get("evidence"), list):
        out["evidence"] = [_redact(line) for line in out["evidence"]]
    if isinstance(out.get("where"), dict):
        where = dict(out["where"])
        if where.get("anchor"):
            where["anchor"] = _redact(where["anchor"])
        out["where"] = where
    return out


def _metric_may_travel(key, value) -> bool:
    """One metric survives export when it can only be a measurement.

    Numbers and flags answer "how much" or "whether", which is all telemetry
    needs and all it can leak. Anything that could hold a path, an identifier
    or a sentence stays home.
    """
    if not isinstance(key, str) or not METRIC_KEY_RE.match(key):
        return False
    return isinstance(value, bool) or (isinstance(value, (int, float))
                                       and not isinstance(value, bool))


def _redact_run(run: dict) -> dict:
    # container_id is the project's own vocabulary (its container names) and
    # buys the maintainer nothing, so it does not travel.
    out = {k: v for k, v in run.items() if k != "container_id"}
    metrics = out.get("metrics")
    if isinstance(metrics, dict):
        kept = {k: v for k, v in metrics.items() if _metric_may_travel(k, v)}
        if len(kept) > MAX_METRIC_KEYS:
            kept = dict(sorted(kept.items())[:MAX_METRIC_KEYS])
        by_question = metrics.get("free_text_by_question")
        if isinstance(by_question, dict):
            # Question IDS only - the ratio is the signal, the answers never are.
            kept["free_text_by_question"] = {
                str(k): v for k, v in by_question.items() if isinstance(v, int)
            }
        if kept:
            out["metrics"] = kept
        else:
            out.pop("metrics", None)
    return out


def build_report(root: Path, runs, lessons, truncate: bool = True) -> dict:
    """The document that travels: redacted, project-anonymous, size-capped.

    This report is the maintainer's ONLY copy. Nobody triaging a published
    plugin's lessons has the consumer's checkout to look things up in, so
    anything missing here is not recoverable later - which is why identity,
    environment and the runs lessons point at are all resolved before the size
    cap gets a say.
    """
    report = {
        "exported_at": _iso_utc_now(),
        "project_id": project_id_for(root),
        "runs": [_redact_run(r) for r in runs if isinstance(r, dict)],
        "lessons": [_redact_lesson(l) for l in lessons if isinstance(l, dict)],
        "environment": environment(),
    }
    # Both ids travel: the uuid is the durable one, the path hash is how every
    # report delivered before it was named, and the maintainer needs to see
    # they are the same project rather than guess.
    uuid_ = project_uuid_for(root)
    if uuid_:
        report["project_uuid"] = uuid_
    version = read_marker(root).get("plugin_version")
    if version:
        report["plugin_version"] = str(version)
    if not truncate:
        return report

    # The free relay tier carries no attachments, so the report travels inside a
    # message body. Lessons never go - one names a defect, a metrics row only
    # counts one - so runs absorb the cap.
    #
    # WHICH runs go first matters more than it looks. A lesson carries the
    # session_id of the run it came from, and that link is how the maintainer
    # sees what the run was doing when the defect bit: how long it took, how
    # many validator passes it burned, whether it finished at all. Dropping
    # oldest-first severs exactly those links first, because a lesson and its
    # run are the same age. So unreferenced runs go first, oldest among them,
    # and a run some travelling lesson points at is given up only when nothing
    # else is left.
    def _size() -> int:
        return len(json.dumps(report, ensure_ascii=False, default=str).encode("utf-8"))

    referenced = {str(l.get("session_id")) for l in report["lessons"]
                  if isinstance(l, dict) and l.get("session_id")}
    dropped = 0
    for keep_referenced in (True, False):
        while _size() > MAX_PAYLOAD_BYTES:
            expendable = [i for i, r in enumerate(report["runs"])
                          if not keep_referenced
                          or str(r.get("session_id")) not in referenced]
            if not expendable:
                break
            for i in reversed(expendable[: max(1, len(expendable) // 10)]):
                del report["runs"][i]
                dropped += 1
    if dropped:
        # Say what was lost. "truncated: true" told the maintainer something
        # went missing but not what, so a thin report and a complete one read
        # the same.
        report["truncated"] = {"runs_dropped": dropped,
                               "runs_kept": len(report["runs"])}
    return report


def read_marker(root: Path) -> dict:
    try:
        data = json.loads((Path(root) / MARKER_REL).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def telemetry_config(root: Path) -> dict:
    """Effective telemetry settings.

    $SDLC_LESSONS_TELEMETRY is a hard override, so a CI job or an employer can
    switch delivery off without editing a file in the repo.
    """
    cfg = dict(TELEMETRY_DEFAULTS)
    stored = read_marker(root).get("telemetry")
    if isinstance(stored, dict):
        cfg.update({k: v for k, v in stored.items() if k in TELEMETRY_DEFAULTS})
    env = os.environ.get("SDLC_LESSONS_TELEMETRY")
    if env in TELEMETRY_MODES:
        cfg["mode"] = env
    if cfg.get("mode") not in TELEMETRY_MODES:
        cfg["mode"] = "off"
    if not cfg.get("project_id"):
        cfg["project_id"] = project_id_for(root)
    return cfg


def write_telemetry(root: Path, updates: dict) -> bool:
    """Merge into the marker's telemetry block.

    False when the marker is absent (the project never ran /sdlc:setup) - the
    marker belongs to setup, and this helper never creates one behind its back.
    """
    marker = read_marker(root)
    if not marker:
        return False
    block = dict(TELEMETRY_DEFAULTS)
    stored = marker.get("telemetry")
    if isinstance(stored, dict):
        block.update(stored)
    block.update(updates)
    if not block.get("project_id"):
        block["project_id"] = project_id_for(root)
    marker["telemetry"] = block
    try:
        # newline="\n": the marker is generated wholesale by the plugin, so it
        # is LF on every host. Without it, every consent change rewrote the
        # whole file in CRLF on Windows - in a file the consumer commits
        # (ledger IMP-116).
        (Path(root) / MARKER_REL).write_text(
            json.dumps(marker, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
    except OSError:
        return False
    return True


def _unsent(queue: dict):
    runs = [r for r in queue.get("runs", []) if isinstance(r, dict) and not r.get("sent_at")]
    lessons = [
        l for l in queue.get("lessons", []) if isinstance(l, dict) and not l.get("sent_at")
    ]
    return runs, lessons


def _age_days(stamp, now):
    when = _parse_iso(stamp)
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    return (now - when).total_seconds() / 86400.0


def send_due(queue: dict, cfg: dict, now=None):
    """Is a batch due? Returns (due, reason). Pure - no I/O, no network.

    First match wins, and the order is the policy: a blocker never waits, a
    full batch goes early, an old batch goes on time, and run telemetry alone
    trickles out monthly rather than earning its own weekly mail.
    """
    now = now or _dt.datetime.now(tz=_dt.timezone.utc)
    runs, lessons = _unsent(queue)
    if not runs and not lessons:
        return False, "the maintainer already has everything recorded here"

    failed_ago = _age_days(cfg.get("last_attempt_at"), now)
    if failed_ago is not None and failed_ago * 24.0 < float(cfg.get("retry_after_hours") or 0):
        return False, "the last send failed and is still cooling down"

    for lesson in lessons:
        if lesson.get("severity") == "blocker":
            return True, f"{lesson.get('lsn_id')} is a blocker"

    batch_max = int(cfg.get("batch_max") or 0)
    if batch_max > 0 and len(lessons) >= batch_max:
        return True, f"{len(lessons)} lessons have accumulated"

    ages = [a for a in (_age_days(l.get("raised_at"), now) for l in lessons) if a is not None]
    if ages and max(ages) >= float(cfg.get("batch_days") or 0):
        return True, f"the oldest lesson is {int(max(ages))} day(s) old"

    if not lessons and runs:
        run_ages = [
            a for a in (_age_days(r.get("finished_at"), now) for r in runs) if a is not None
        ]
        if run_ages and max(run_ages) >= float(cfg.get("runs_only_days") or 0):
            return True, f"run telemetry is {int(max(run_ages))} day(s) old"

    return False, "they are waiting for the next batch"


def relay_endpoint() -> str:
    """The configured relay URL, or "" when this build has none.

    The shipped default is a placeholder, so a checkout nobody has pointed at
    a relay disables delivery rather than posting into the void.
    """
    endpoint = os.environ.get("SDLC_LESSONS_ENDPOINT") or RELAY_ENDPOINT
    return "" if "CHANGEME" in endpoint else endpoint


def deliver(report: dict, timeout: float = 10.0):
    """POST the report to the relay. Never raises; returns (ok, reason)."""
    import urllib.error
    import urllib.request

    endpoint = relay_endpoint()
    if not endpoint:
        return False, "this plugin build carries no delivery address"
    token = os.environ.get("SDLC_LESSONS_TOKEN") or RELAY_TOKEN

    body = json.dumps(
        {
            "token": token,
            "plugin_version": report.get("plugin_version"),
            "report": report,
        },
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")

    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json",
                 "Accept": "application/json",
                 "User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", None) or response.getcode()
            raw = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # The body is where a relay explains itself ("wrong key", "server-side
        # use needs a paid plan"). Dropping it turns every refusal into the same
        # unactionable number, which is exactly how long a broken transport can
        # hide.
        detail = ""
        try:
            said = json.loads(e.read().decode("utf-8", "replace"))
            if isinstance(said, dict) and said.get("message"):
                detail = f": {str(said['message'])[:200]}"
        except Exception:
            pass
        return False, f"the relay refused the report (HTTP {e.code}){detail}"
    except Exception as e:  # timeout, DNS, TLS, offline, proxy - all the same
        return False, f"could not reach the relay ({type(e).__name__})"

    if status != 200:
        return False, f"the relay answered HTTP {status}"
    # A relay that spam-filters a submission still answers 200, with its own
    # verdict in the body. Reading it is the difference between a delivery and
    # a report that vanished while looking like one.
    try:
        parsed = json.loads(raw)
    except ValueError:
        return True, "delivered"
    if isinstance(parsed, dict) and parsed.get("success") is False:
        return False, f"the relay rejected the report ({parsed.get('message')})"
    return True, "delivered"


def flush(root: Path, force: bool = False, timeout: float = 5.0, quiet: bool = False) -> bool:
    """Send the unsent batch when the policy says it is due.

    Called at a skill CLOSE and by `export --send` (which passes force=True and
    is the manual override). Silent and harmless when nothing is due; a
    telemetry failure must never look like - or become - a skill failure.
    """
    cfg = telemetry_config(root)
    if cfg["mode"] == "off" and not force:
        return False
    if not relay_endpoint():
        # A build with no delivery address configured. Say so on an explicit
        # --send, but never stamp a failure: there is nothing to retry, and a
        # cooldown here would look like a network problem for six hours.
        if not quiet:
            print(
                "[DRAFT] not sent - this plugin build carries no delivery "
                "address, so the report has to travel by hand."
            )
            print_next(
                f"python .claude/sdlc/lessons.py export --out "
                f"lessons-report.md, then email it to {FEEDBACK_CONTACT}."
            )
        return False

    queue_path = Path(root) / QUEUE_REL
    try:
        queue = load_queue(queue_path)
    except (OSError, ValueError, yaml.YAMLError):
        return False

    runs, lessons = _unsent(queue)
    if not runs and not lessons:
        if not quiet:
            print(
                "[OK] nothing new to send - the maintainer already has "
                "everything recorded here."
            )
        return False

    if not force:
        due, reason = send_due(queue, cfg)
        if not due:
            if not quiet:
                print(f"[OK] {len(lessons)} lesson(s) held for the next batch - " f"{reason}.")
            return False

    report = build_report(root, runs, lessons)
    ok, reason = deliver(report, timeout=timeout)
    stamp = _iso_utc_now()

    if ok:
        for entry in runs + lessons:
            entry["sent_at"] = stamp
        queue["last_updated"] = stamp
        try:
            dump_queue(queue, queue_path)
        except OSError:
            pass  # sent is sent; a re-send is deduped by the maintainer
        write_telemetry(
            root,
            {"last_sent_at": stamp, "last_attempt_at": None, "last_sent_count": len(lessons)},
        )
        if not quiet:
            print(
                f"[OK] sent {len(lessons)} lesson(s) and {len(runs)} run(s) "
                f"about the sdlc skills to their maintainer."
            )
        return True

    write_telemetry(root, {"last_attempt_at": stamp})
    if not quiet:
        print(
            f"[DRAFT] not sent - {reason}. Nothing is lost: the batch is kept "
            f"and retried at the next skill close."
        )
        print_next(
            f"nothing to run. To send it by hand instead: python "
            f".claude/sdlc/lessons.py export --out lessons-report.md, "
            f"then email that file to {FEEDBACK_CONTACT}."
        )
    return False


# =============================================================================
# Subcommands
# =============================================================================


def cmd_record_run(args) -> int:
    root = resolve_project_root(args.project_root)
    queue_path = root / QUEUE_REL
    state_path = (
        Path(args.state) if args.state else root / STATE_REL_TMPL.format(skill=args.skill)
    )

    try:
        doc, record, shape = parse_state(state_path, args.session)
    except KeyError as e:
        print(
            f"[FAIL] no sub-session named {e.args[0]!r} in {state_path} - "
            f"pass --session with a key that exists there."
        )
        return 1
    except (OSError, yaml.YAMLError) as e:
        print(f"[FAIL] cannot parse {state_path}: {e}", file=sys.stderr)
        return 2

    record = record or {}
    outcome = args.outcome
    if not outcome:
        status = record.get("status")
        outcome = {"complete": "complete", "aborted": "aborted", "in_progress": "draft"}.get(
            status
        )
    if not outcome:
        print(
            f"[FAIL] no run recorded - no state file at {state_path} and no "
            f"--outcome given. Pass --outcome complete|draft|aborted|failed."
        )
        return 1
    if outcome not in OUTCOMES:
        print(
            f"[FAIL] no run recorded - outcome {outcome!r} is not one of "
            f"{'|'.join(OUTCOMES)}."
        )
        return 1

    finished_at = _iso_utc_now()
    session_id = args.session_id or record.get("session_id") or str(uuid.uuid4())
    state_version = (doc or {}).get("skill_version") or record.get("skill_version")
    version_hint = None
    if args.skill_version:
        skill_version = args.skill_version
    else:
        # record-run runs at a skill's close, inside it: the footer is what ran.
        footer = skill_version_from_plugin(resolve_plugin_root(args), args.skill)
        skill_version, version_hint = date_from_footer(args.skill, state_version, footer)
    plugin_version, plugin_source = resolve_plugin_version(args, root)

    run = {
        "session_id": str(session_id),
        "skill": args.skill,
        "outcome": outcome,
        "finished_at": finished_at,
    }
    if skill_version:
        run["skill_version"] = str(skill_version)
    if state_version and skill_version and str(state_version) != str(skill_version):
        run["state_skill_version"] = str(state_version)
    # A migrated interview state names the version the run started under
    # (CLAUDE.md "State file contract": migrations[{from, to, at, ...}]) - but
    # only a migration that happened DURING this run: a state file reused
    # across sessions can carry a migration that already finished in an
    # earlier, unrelated run, which is not "the version this run started
    # under" (ledger IMP-144). When started_at itself is missing or
    # unparseable there is no way to score which migration is in-run, so the
    # earliest listed one is kept - the prior, unscored behaviour.
    migrations = record.get("migrations") or (doc or {}).get("migrations")
    if isinstance(migrations, list) and migrations:
        started_at_dt = _parse_iso(record.get("started_at"))
        candidate = None
        if started_at_dt is None:
            if isinstance(migrations[0], dict):
                candidate = migrations[0]
        else:
            for m in migrations:
                if not isinstance(m, dict):
                    continue
                at_dt = _parse_iso(m.get("at"))
                if at_dt is not None and at_dt >= started_at_dt:
                    candidate = m
                    break
        if candidate:
            started_under = candidate.get("from")
            if started_under and str(started_under) != str(skill_version or ""):
                run["skill_version_at_start"] = str(started_under)
    if plugin_version:
        run["plugin_version"] = plugin_version
        run["plugin_version_source"] = plugin_source
        installed = installed_plugin_version(root)
        if installed and installed != plugin_version:
            run["installed_version"] = installed
    if record.get("started_at"):
        run["started_at"] = record["started_at"]
    if record.get("mode"):
        run["mode"] = record["mode"]
    if record.get("container_id"):
        run["container_id"] = record["container_id"]
    metrics = _derive_metrics(doc or {}, record, shape or "flat", finished_at)
    for pair in args.metric or []:
        key, sep, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            print(f"[FAIL] no run recorded - --metric {pair!r} is not key=value.")
            return 1
        digits = value[1:] if value.startswith("-") else value
        metrics[key] = int(value) if digits.isdigit() else value
    if metrics:
        run["metrics"] = metrics

    try:
        queue = load_queue(queue_path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        print(f"[FAIL] cannot parse {queue_path}: {e}", file=sys.stderr)
        return 2

    # `resumes` semantics: the state file's metrics.resumes is authoritative
    # (the skill bumps it at every ACTUAL resume, including sessions killed
    # without a record). Only when the state carries none do we fall back to
    # counting re-records: prior + 1 on upsert, 0 on a first record.
    resumes = metrics.get("resumes") if isinstance(metrics.get("resumes"), int) else None
    existing = next(
        (
            r
            for r in queue["runs"]
            if isinstance(r, dict) and r.get("session_id") == run["session_id"]
        ),
        None,
    )
    if existing is not None:
        if resumes is not None:
            run["resumes"] = resumes
        else:
            prior = existing.get("resumes", 0)
            run["resumes"] = (prior if isinstance(prior, int) else 0) + 1
        existing.clear()
        existing.update(run)
        verb = "updated"
    else:
        run["resumes"] = resumes if resumes is not None else 0
        queue["runs"].append(run)
        verb = "recorded"

    queue["last_updated"] = finished_at
    try:
        dump_queue(queue, queue_path)
    except OSError as e:
        print(f"[FAIL] cannot write {queue_path}: {e}", file=sys.stderr)
        return 2
    print(
        f"[OK] {verb} run {run['session_id'][:8]} for /sdlc:{args.skill} "
        f"(outcome: {outcome}) -> {queue_path}"
    )
    if version_hint:
        _print_hints([version_hint], written=True)
    lag = setup_lag(root, plugin_version if plugin_source in ("manifest", "flag") else None,
                    resolve_plugin_root(args))
    if lag:
        print(f"Check: {lag}")
    # A close is also where the maintainer's verdicts arrive: the installed
    # plugin ships skills/lesson/VERDICTS.yaml, and a close is the one moment a
    # plugin root is reliably known. Silent unless something changed, and never
    # a failure - the run record above is what this command is for.
    try:
        verdicts = reconcile(root, resolve_plugin_root(args))
    except Exception:  # noqa: BLE001
        verdicts = None
    if verdicts and verdicts["status"] == "ok" and (verdicts["stamped"] or verdicts["reopened"]):
        print(f"Verdicts: {verdict_summary(verdicts)}")
    # A skill close is a flush point. The due-check is a local read that costs
    # nothing when nothing is due, so the network is touched at most once a week
    # per project - and never at all unless this project opted in.
    flush(root, quiet=True)
    return 0


def _reject_add(reason: str) -> int:
    print(f"[FAIL] lesson not recorded - {reason}")
    return 1


def cmd_add(args) -> int:
    root = resolve_project_root(args.project_root)
    queue_path = root / QUEUE_REL

    if not SKILL_RE.match(args.skill or ""):
        return _reject_add(f"--skill {args.skill!r} is not a skill slug (kebab-case).")

    # Every enum flag is checked before any is reported. The caller here is
    # usually an agent composing one long command, so failing on the first bad
    # value costs a round-trip per flag - three of them, in the episode that
    # prompted this (ledger IMP-026). The flags stay free-text rather than
    # argparse `choices=` so these messages, and the exit code 1 they carry,
    # remain the contract; argparse would exit 2 with its own wording.
    bad = []
    if args.kind not in KINDS:
        bad.append(f"--kind {args.kind!r} is not one of: {', '.join(KINDS)}.")
    if args.severity not in SEVERITIES:
        bad.append(f"--severity {args.severity!r} is not one of {'|'.join(SEVERITIES)}.")
    if args.agent_action and args.agent_action not in AGENT_ACTIONS:
        bad.append(
            f"--agent-action {args.agent_action!r} is not one of {'|'.join(AGENT_ACTIONS)}."
        )
    if args.generalizes and args.generalizes not in GENERALIZES:
        bad.append(
            f"--generalizes {args.generalizes!r} is not one of {'|'.join(GENERALIZES)}."
        )
    if bad:
        return _reject_add(" ".join(bad))

    where_file = (args.where_file or "").replace("\\", "/")
    problem = _where_problem(where_file)
    if problem:
        return _reject_add(problem)
    prefix_note = None
    stripped = strip_skill_prefix(args.skill, where_file)
    if stripped != where_file:
        # Recorded, not rejected: a reject at Phase 8 loses the lesson.
        prefix_note = (f"--where-file {where_file!r} carried the skill folder as a "
                       f"prefix - where.file is relative to {args.skill}/, so it was "
                       f"recorded as {stripped!r}")
        where_file = stripped

    evidence = args.evidence or []
    if not 1 <= len(evidence) <= MAX_EVIDENCE:
        return _reject_add(
            f"evidence must be 1..{MAX_EVIDENCE} lines (got {len(evidence)}) - "
            f"a lesson nobody can judge is a rumour; a wall of text is one too."
        )
    for line in evidence:
        if len(line) > MAX_EVIDENCE_LEN:
            return _reject_add(
                f"an evidence line exceeds {MAX_EVIDENCE_LEN} chars - "
                f"summarize; never paste project content."
            )
    for fnd in args.related or []:
        if not FND_RE.match(fnd):
            return _reject_add(f"--related {fnd!r} is not an FND-NNN id.")

    raised_by = args.raised_by
    if not raised_by:
        skill_dir = os.environ.get("CLAUDE_SKILL_DIR")
        raised_by = f"sdlc-{Path(skill_dir).name}" if skill_dir else "user"

    # Session/version context from the named skill's state, best-effort. The
    # state file says what actually RAN; the installed plugin's SKILL.md footer
    # is the fallback for skills that keep no state here (setup) or never ran.
    plugin_root = resolve_plugin_root(args)
    session_id = args.session_id
    skill_version = None
    shape = None
    try:
        doc, record, shape = parse_state(root / STATE_REL_TMPL.format(skill=args.skill), None)
        if record and not session_id:
            session_id = record.get("session_id")
        if doc:
            skill_version = doc.get("skill_version")
    except Exception:
        pass
    state_version = skill_version
    version_hint = None
    footer_skill_version = None
    footer = skill_version_from_plugin(plugin_root, args.skill)
    if running_skill() == args.skill:
        # About the skill executing right now: its footer is the version whose
        # behaviour was observed, whatever a never-re-stamped state file says.
        skill_version, version_hint = date_from_footer(args.skill, state_version, footer)
    elif shape == "ledger" and skill_version and footer and str(skill_version) != str(footer):
        # About another skill's LEDGER (code today): the ledger records the
        # version that CREATED it and nothing bumps it between runs, so it
        # still says what wrote what this run observed - skill_version stays
        # it. The footer is not "running now" here, so it rides the
        # ledger-specific note, never date_from_footer's wording.
        footer_skill_version, version_hint = ambient_ledger_footer_note(
            args.skill, state_version, footer)
    elif not skill_version:
        # About another skill: its state file says which version wrote what
        # this run observed; the footer is only the fallback when it never ran.
        skill_version = footer
    plugin_version, _source = resolve_plugin_version(args, root)
    installed = installed_plugin_version(root)

    try:
        queue = load_queue(queue_path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        print(f"[FAIL] cannot parse {queue_path}: {e}", file=sys.stderr)
        return 2

    highest = 0
    for lesson in queue["lessons"]:
        m = LSN_RE.match(str(lesson.get("lsn_id", "")))
        if m:
            highest = max(highest, int(lesson["lsn_id"].split("-")[1]))
    counter = max(int(queue["last_ids"].get("LSN", 0)), highest) + 1
    lsn_id = f"LSN-{counter:03d}"

    lesson = {
        "lsn_id": lsn_id,
        "raised_by": raised_by,
        "raised_at": _iso_utc_now(),
        "skill": args.skill,
        "kind": args.kind,
        "severity": args.severity,
        "where": {"file": where_file},
        "summary": args.summary,
        "evidence": list(evidence),
        "status": "open",
    }
    if args.where_anchor:
        lesson["where"]["anchor"] = args.where_anchor
    if session_id:
        lesson["session_id"] = str(session_id)
    if skill_version:
        lesson["skill_version"] = str(skill_version)
    if state_version and skill_version and str(state_version) != str(skill_version):
        lesson["state_skill_version"] = str(state_version)
    if footer_skill_version:
        lesson["footer_skill_version"] = str(footer_skill_version)
    if plugin_version:
        lesson["plugin_version"] = plugin_version
    if installed and plugin_version and installed != plugin_version:
        lesson["installed_version"] = installed
    if args.agent_action:
        lesson["agent_action"] = args.agent_action
    if args.suggested_fix:
        lesson["suggested_fix"] = args.suggested_fix
    if args.generalizes:
        lesson["generalizes"] = args.generalizes
    if args.related:
        lesson["related_findings"] = list(args.related)

    hints = lesson_hints(lesson, plugin_root=plugin_root, installed_version=installed)
    if version_hint:
        hints.append(version_hint)
    if prefix_note:
        hints.insert(0, prefix_note)

    # Is this the same defect this project already reported? A second write
    # would send the maintainer two entries to reconcile by hand, and the
    # number that actually matters - how often this bites - would read as two
    # separate ones rather than one that recurred. --allow-duplicate is the
    # escape hatch when the match is wrong.
    prior, score = (None, 0.0)
    if not getattr(args, "allow_duplicate", False):
        prior, score = find_recurrence(queue, lesson, plugin_root=plugin_root)

    if getattr(args, "dry_run", False):
        if prior is not None:
            print(
                f"[OK] dry run - would be recorded as a recurrence of "
                f"{prior.get('lsn_id')} (seen {_occurrences(prior) + 1}x); nothing written."
            )
        else:
            print(
                f"[OK] dry run - {lsn_id} would be recorded about /sdlc:{args.skill} "
                f"({args.kind}, {args.severity}); nothing written."
            )
        _print_hints(hints, written=False)
        return 0

    if prior is not None:
        stamp_recurrence(prior, lesson)
        queue["last_updated"] = lesson["raised_at"]
        try:
            dump_queue(queue, queue_path)
        except OSError as e:
            print(f"[FAIL] cannot write {queue_path}: {e}", file=sys.stderr)
            return 2
        print(
            f"[OK] recorded as a recurrence of {prior.get('lsn_id')} - "
            f"seen {_occurrences(prior)}x now, still one lesson -> {queue_path}"
        )
        print(f"       (same skill, same file, {int(score * 100)}% match on what it "
              f"names; use --allow-duplicate if it is a different defect)")
        _print_hints(hints, written=True)
        _refresh_statusboard()
        flush(root, quiet=True)
        return 0

    queue["lessons"].append(lesson)
    queue["last_ids"]["LSN"] = counter
    queue["last_updated"] = lesson["raised_at"]
    try:
        dump_queue(queue, queue_path)
    except OSError as e:
        print(f"[FAIL] cannot write {queue_path}: {e}", file=sys.stderr)
        return 2
    print(
        f"[OK] {lsn_id} recorded about /sdlc:{args.skill} "
        f"({args.kind}, {args.severity}) -> {queue_path}"
    )
    _print_hints(hints, written=True)
    _refresh_statusboard()
    # A blocker goes out now; anything else joins the batch. Quiet, because the
    # line above is the one the user asked for.
    flush(root, quiet=True)
    return 0


def _where_problem(where_file: str) -> "str | None":
    if not where_file:
        return "--where-file is required - name the plugin file the defect lives in."
    if where_file.startswith("/") or re.match(r"^[A-Za-z]:", where_file):
        return (
            f"--where-file {where_file!r} is absolute - use a path relative "
            f"to the skill's folder (e.g. SKILL.md, references/edge-cases.md)."
        )
    if ".." in where_file.split("/"):
        return f"--where-file {where_file!r} escapes the skill folder ('..')."
    if where_file.startswith("docs/") or "/docs/" in where_file:
        return (
            f"--where-file {where_file!r} points at a project artifact - "
            f"a defect in docs/ is a finding (FND) or a WRN in the owning "
            f"artifact, not a lesson."
        )
    return None


def _load_for_read(path: Path):
    if not path.is_file():
        print(f"[OK] no lessons queue at {path} - nothing recorded yet.")
        return None
    try:
        return load_queue(path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        print(f"[FAIL] cannot parse {path}: {e}", file=sys.stderr)
        return 2


def cmd_list(args) -> int:
    root = resolve_project_root(args.project_root)
    queue = _load_for_read(Path(args.path) if args.path else root / QUEUE_REL)
    if queue is None:
        return 0
    if queue == 2:
        return 2
    lessons = _filter_lessons(queue["lessons"], args)
    print(f"{len(lessons)} lesson(s), {len(queue['runs'])} run(s) recorded.")
    installed = installed_plugin_version(root)
    counts: "dict[str, int]" = {}
    for lesson in queue["lessons"]:
        if isinstance(lesson, dict):
            key = "open again" if _reopened_from(lesson) else str(lesson.get("status") or "open")
            counts[key] = counts.get(key, 0) + 1
    if any(k not in ("open", "collected") for k in counts):
        order = ("open", "open again", "collected") + VERDICT_STATUSES
        print("  by verdict: " + ", ".join(f"{counts[k]} {k}" for k in order if counts.get(k)))
    for lesson in lessons:
        where = lesson.get("where") or {}
        anchor = f"#{where.get('anchor')}" if where.get("anchor") else ""
        print(
            f"  {lesson.get('lsn_id')} [{verdict_tag(lesson, installed)}] "
            f"{lesson.get('skill')}/{lesson.get('kind')} ({lesson.get('severity')}) "
            f"{where.get('file')}{anchor} - {lesson.get('summary')}"
        )
    return 0


def _filter_lessons(lessons, args):
    out = []
    for lesson in lessons:
        if not isinstance(lesson, dict):
            continue
        if getattr(args, "open", False) and lesson.get("status") != "open":
            continue
        if getattr(args, "status", None) and lesson.get("status") != args.status:
            continue
        if getattr(args, "skill", None) and lesson.get("skill") != args.skill:
            continue
        if getattr(args, "since", None) and str(lesson.get("raised_at", "")) < args.since:
            continue
        out.append(lesson)
    return out


def cmd_export(args) -> int:
    root = resolve_project_root(args.project_root)
    queue = _load_for_read(Path(args.path) if args.path else root / QUEUE_REL)
    if queue is None:
        return 0
    if queue == 2:
        return 2
    lessons = _filter_lessons(queue["lessons"], args)
    runs = queue["runs"]

    # --send is the manual override: it ignores the batching policy and mails
    # whatever is unsent, whatever the filters say.
    if getattr(args, "send", False):
        cfg = telemetry_config(root)
        if cfg["mode"] == "off":
            print(
                "[DRAFT] not sent - this project has not opted in to sharing "
                "lessons with the plugin maintainer."
            )
            print_next(
                "turn it on with: python .claude/sdlc/lessons.py consent " "--set auto",
                f"or export the report and email it to {FEEDBACK_CONTACT} " f"yourself.",
            )
            return 0
        flush(root, force=True, timeout=10.0)
        return 0

    report = build_report(root, runs, lessons, truncate=False)
    if args.format == "json":
        text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
        return _emit_report(text, getattr(args, "out", None))

    lessons = report["lessons"]
    runs = report["runs"]
    out: "list[str]" = []
    out.append(f"# sdlc lessons report - {report['project_id']}, {_iso_utc_now()}")
    out.append(f"\n{len(lessons)} lesson(s), {len(runs)} run(s). Lessons describe the")
    out.append("sdlc SKILLS, not this project - locations are files inside the plugin.")
    by_skill: "dict[str, list]" = {}
    for lesson in lessons:
        by_skill.setdefault(str(lesson.get("skill")), []).append(lesson)
    for skill in sorted(by_skill):
        out.append(f"\n## /sdlc:{skill}")
        for lesson in by_skill[skill]:
            where = lesson.get("where") or {}
            anchor = f" # {where.get('anchor')}" if where.get("anchor") else ""
            out.append(
                f"\n### {lesson.get('lsn_id')} - {lesson.get('kind')} "
                f"({lesson.get('severity')}, {lesson.get('status')})"
            )
            versions = ", ".join(
                filter(
                    None,
                    [
                        (
                            f"skill {lesson['skill_version']}"
                            if lesson.get("skill_version")
                            else None
                        ),
                        (
                            f"plugin {lesson['plugin_version']}"
                            if lesson.get("plugin_version")
                            else None
                        ),
                    ],
                )
            )
            if versions:
                out.append(f"- raised against: {versions} (by {lesson.get('raised_by')})")
            out.append(f"- where: {where.get('file')}{anchor}")
            out.append(f"- summary: {lesson.get('summary')}")
            for line in lesson.get("evidence") or []:
                out.append(f"  - {line}")
            if lesson.get("suggested_fix"):
                out.append(f"- suggested fix: {lesson['suggested_fix']}")
            if lesson.get("related_findings"):
                out.append(
                    f"- related findings in this project: "
                    f"{', '.join(lesson['related_findings'])}"
                )
    if runs:
        out.append(f"\n## Run telemetry ({len(runs)} run(s))")
        for run in runs:
            metrics = run.get("metrics") or {}
            picked = ", ".join(
                f"{k}={metrics[k]}"
                for k in (
                    "questions_asked",
                    "free_text_answers",
                    "validator_failures",
                    "units_done",
                    "heals",
                    "duration_s",
                )
                if k in metrics
            )
            out.append(
                f"- /sdlc:{run.get('skill')} {run.get('outcome')} "
                f"(resumes: {run.get('resumes', 0)}"
                f"{', ' + picked if picked else ''})"
            )
    out.append(f"\n---\nTo report these, email this report to {FEEDBACK_CONTACT}.")
    out.append(
        "Absolute paths and e-mail addresses are stripped and this project " "appears only as"
    )
    out.append(
        f"{report['project_id']} - review it anyway before sending, as you "
        f"would any outbound text."
    )
    return _emit_report("\n".join(out), getattr(args, "out", None))


def _emit_report(text: str, out_path: "str | None") -> int:
    """Print the report, or write it where --out says and name the file."""
    if not out_path:
        print(text)
        return 0
    path = Path(out_path)
    try:
        if path.parent and not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")
    except OSError as e:
        print(f"[FAIL] cannot write {path}: {e}", file=sys.stderr)
        return 2
    print(f"[OK] wrote the report to {path}.")
    print_next(
        f"review it, then email it to {FEEDBACK_CONTACT}.",
        "To have this sent automatically in future: python "
        ".claude/sdlc/lessons.py consent --set auto",
    )
    return 0


def cmd_consent(args) -> int:
    """Read or set how this project shares lessons with the plugin maintainer."""
    root = resolve_project_root(args.project_root)
    cfg = telemetry_config(root)

    if not args.set:
        env = os.environ.get("SDLC_LESSONS_TELEMETRY")
        print(
            f"[OK] lesson sharing is {cfg['mode']!r} for this project "
            f"(id {cfg['project_id']})."
        )
        if env in TELEMETRY_MODES:
            print(
                f"      SDLC_LESSONS_TELEMETRY={env} in this environment is "
                f"overriding whatever the marker says."
            )
        if cfg["mode"] != "off":
            print(
                f"      A blocker is mailed at the next skill close; anything "
                f"else waits up to {cfg['batch_days']} day(s) or "
                f"{cfg['batch_max']} lessons."
            )
            print(f"      Last sent: {cfg['last_sent_at'] or 'never'}.")
        print_next("change it with: python .claude/sdlc/lessons.py consent " "--set off|ask|auto")
        return 0

    if args.set not in TELEMETRY_MODES:
        print(f"[FAIL] {args.set!r} is not one of {'|'.join(TELEMETRY_MODES)}.")
        return 1
    updates = {"mode": args.set}
    if args.set != "off":
        updates["consented_on"] = _iso_utc_now()[:10]
    if not write_telemetry(root, updates):
        print(
            f"[FAIL] no .claude/sdlc/sdlc-plugin.json in {root} - run "
            f"/sdlc:setup first; it owns that file."
        )
        return 1
    if args.set == "off":
        print("[OK] lesson sharing is off. Nothing will leave this machine.")
    else:
        print(
            f"[OK] lesson sharing is {args.set!r}. Reports about this "
            f"plugin's skills go to {FEEDBACK_CONTACT}; nothing about this "
            f"project's code or docs is ever included."
        )
    print_next("nothing to run - this takes effect at the next skill close.")
    return 0


# =============================================================================
# validate
# =============================================================================


def _check_queue(doc: dict) -> "list[str]":
    errors: "list[str]" = []
    if not isinstance(doc.get("lessons_file_version"), str):
        errors.append("lessons_file_version must be a string")
    if not isinstance(doc.get("last_ids"), dict):
        errors.append("last_ids must be a mapping")
        return errors

    session_ids = []
    for i, run in enumerate(doc.get("runs", [])):
        tag = f"runs[{i}]"
        if not isinstance(run, dict):
            errors.append(f"{tag}: must be a mapping")
            continue
        if not run.get("session_id"):
            errors.append(f"{tag}: session_id is required")
        else:
            session_ids.append(run["session_id"])
        if not run.get("skill"):
            errors.append(f"{tag}: skill is required")
        if run.get("outcome") not in OUTCOMES:
            errors.append(
                f"{tag}: outcome {run.get('outcome')!r} is not one of " f"{'|'.join(OUTCOMES)}"
            )
        if (
            "metrics" in run
            and run["metrics"] is not None
            and not isinstance(run["metrics"], dict)
        ):
            errors.append(f"{tag}: metrics must be a mapping")
    dupes = sorted({s for s in session_ids if session_ids.count(s) > 1})
    if dupes:
        errors.append(
            f"duplicate run session_id(s): {', '.join(str(d) for d in dupes)} - "
            f"record-run upserts by session_id; duplicates mean a "
            f"writer other than lessons.py touched the file"
        )

    ids = []
    counter = int(doc["last_ids"].get("LSN", 0) or 0)
    for i, lesson in enumerate(doc.get("lessons", [])):
        tag = f"lessons[{i}]"
        if not isinstance(lesson, dict):
            errors.append(f"{tag}: must be a mapping")
            continue
        lsn = str(lesson.get("lsn_id", ""))
        tag = lsn or tag
        if not LSN_RE.match(lsn):
            errors.append(f"{tag}: lsn_id {lsn!r} does not match LSN-NNN")
        else:
            ids.append(lsn)
            if int(lsn.split("-")[1]) > counter:
                errors.append(
                    f"{tag} exceeds last_ids.LSN={counter} - the counter "
                    f"has fallen behind; reconcile to max(counter, "
                    f"highest id) before appending"
                )
        for field in ("raised_by", "raised_at", "skill", "summary"):
            if not lesson.get(field):
                errors.append(f"{tag}: {field} is required")
        if lesson.get("kind") not in KINDS:
            errors.append(
                f"{tag}: kind {lesson.get('kind')!r} is not in the closed "
                f"set ({', '.join(KINDS)})"
            )
        if lesson.get("severity") not in SEVERITIES:
            errors.append(
                f"{tag}: severity {lesson.get('severity')!r} is not one of "
                f"{'|'.join(SEVERITIES)}"
            )
        if lesson.get("status") not in LESSON_STATUSES:
            errors.append(
                f"{tag}: status {lesson.get('status')!r} is not one of "
                f"{'|'.join(LESSON_STATUSES)}"
            )
        where = lesson.get("where")
        if not isinstance(where, dict) or not where.get("file"):
            errors.append(
                f"{tag}: where.file is required - a lesson that cannot "
                f"name the plugin file it is about is not a lesson yet"
            )
        else:
            problem = _where_problem(str(where["file"]).replace("\\", "/"))
            if problem:
                errors.append(f"{tag}: {problem}")
        evidence = lesson.get("evidence")
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= MAX_EVIDENCE:
            got = len(evidence) if isinstance(evidence, list) else "none"
            errors.append(f"{tag}: evidence must be 1..{MAX_EVIDENCE} lines (got {got})")
        else:
            for line in evidence:
                if len(str(line)) > MAX_EVIDENCE_LEN:
                    errors.append(f"{tag}: an evidence line exceeds {MAX_EVIDENCE_LEN} chars")
                    break
        if lesson.get("agent_action") not in (None,) + AGENT_ACTIONS:
            errors.append(
                f"{tag}: agent_action {lesson.get('agent_action')!r} is not "
                f"one of {'|'.join(AGENT_ACTIONS)}"
            )
        generalizes = _norm_generalizes(lesson.get("generalizes"))
        if generalizes not in (None,) + GENERALIZES:
            errors.append(
                f"{tag}: generalizes {lesson.get('generalizes')!r} is not "
                f"one of {'|'.join(GENERALIZES)}"
            )
        for fnd in lesson.get("related_findings") or []:
            if not FND_RE.match(str(fnd)):
                errors.append(f"{tag}: related_findings entry {fnd!r} is not FND-NNN")
        # The verdict fields: type checks only, and only when present - a
        # queue written before verdicts existed carries none and stays green.
        imp_id = lesson.get("imp_id")
        if imp_id is not None and not IMP_RE.match(str(imp_id)):
            errors.append(f"{tag}: imp_id {imp_id!r} does not match IMP-NNN - it names "
                          f"the maintainer's ledger item, and is written by lessons.py alone")
        for key in ("fixed_in", "verdict_at"):
            value = lesson.get(key)
            if value is not None and not isinstance(value, str):
                errors.append(f"{tag}: {key} must be a string (got {value!r})")
        # Type checks only. Absent means "reported once" and every queue
        # written before recurrence stamping existed is silent here, so an
        # older file cannot turn red on upgrade.
        occurrences = lesson.get("occurrences")
        if occurrences is not None and (not isinstance(occurrences, int)
                                        or isinstance(occurrences, bool)
                                        or occurrences < 1):
            errors.append(f"{tag}: occurrences must be a positive whole number "
                          f"(got {occurrences!r}) - it counts how often this was reported")

    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        errors.append(f"duplicate lsn_id(s): {', '.join(dupes)}")
    return errors


def cmd_validate(args) -> int:
    root = resolve_project_root(args.project_root)
    path = Path(args.path) if args.path else root / QUEUE_REL
    if not path.is_file():
        print(f"[OK] no lessons queue at {path} - nothing recorded yet, nothing to check.")
        return 0
    try:
        queue = load_queue(path)
    except (OSError, yaml.YAMLError, ValueError) as e:
        print(f"[FAIL] cannot parse {path}: {e}", file=sys.stderr)
        return 2
    errors = _check_queue(queue)
    if errors:
        print(
            f"[FAIL] {path} breaks its own schema in {len(errors)} place(s). "
            f"The maintainer's collector would refuse it:"
        )
        print_findings(errors, [], blocking_header="MUST FIX")
        print_next(
            "fix the entries above (the file is written by lessons.py - "
            "a hand edit is the usual cause), then re-run validate."
        )
        return 1
    open_count = sum(1 for l in queue["lessons"] if l.get("status") == "open")
    resolved = sum(1 for l in queue["lessons"] if l.get("status") == "resolved")
    print(
        f"[OK] {path} is valid - {len(queue['lessons'])} lesson(s) "
        f"({open_count} open" + (f", {resolved} resolved upstream" if resolved else "")
        + f"), {len(queue['runs'])} run(s)."
    )
    return 0


def cmd_reconcile(args) -> int:
    root = resolve_project_root(args.project_root)
    summary = reconcile(root, resolve_plugin_root(args))
    if summary["status"] == "no-manifest":
        print(
            "[OK] no verdict manifest reachable - run this inside a skill, or pass "
            "--plugin-root <the installed sdlc plugin's folder>; nothing to reconcile."
        )
        return 0
    if summary["status"] == "unreadable":
        print(f"[FAIL] cannot reconcile - {summary['problem']}", file=sys.stderr)
        return 2
    if summary["status"] == "no-rows":
        print(f"[OK] {summary['path']} names no lesson of this project - nothing to reconcile.")
        return 0
    print(f"[OK] {verdict_summary(summary)}")
    if summary["written"]:
        print_next("python .claude/sdlc/lessons.py list - the verdict now shows beside each id.")
        _refresh_statusboard(root)
    return 0


# =============================================================================
# CLI
# =============================================================================


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
        subprocess.call(
            [sys.executable, str(script), "--path", str(root)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def main(argv=None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(
        description="Record sdlc skill runs and skill-defect lessons "
        "(.claude/skills-state/sdlc-lessons.yaml)."
    )
    ap.add_argument(
        "--project-root",
        default=None,
        help="Consumer project root (default: $CLAUDE_PROJECT_DIR, then cwd).",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("record-run", help="Append/update one run record.")
    p.add_argument("--skill", required=True)
    p.add_argument("--state", default=None, help="State file path override.")
    p.add_argument(
        "--session", default=None, help="Sub-session key for sharded skills (default: newest)."
    )
    p.add_argument("--outcome", default=None, choices=OUTCOMES)
    p.add_argument("--skill-version", default=None,
                   help="Override the recorded skill_version (else: the running SKILL.md "
                        "footer when the plugin is visible, else the state file's).")
    p.add_argument("--session-id", default=None)
    p.add_argument("--plugin-root", default=None)
    p.add_argument("--plugin-version", default=None)
    p.add_argument(
        "--metric",
        action="append",
        default=None,
        metavar="KEY=VALUE",
        help="Repeatable extra fact for the run record's metrics "
        "(int if the value is int-shaped, else string); "
        "overrides a state-derived key of the same name. The "
        "only metrics channel for state-less skills (setup).",
    )
    p.set_defaults(func=cmd_record_run)

    p = sub.add_parser("add", help="Append one LSN-NNN lesson.")
    p.add_argument("--skill", required=True, help="The skill the lesson is ABOUT.")
    p.add_argument("--kind", required=True,
                   help="One of: " + ", ".join(KINDS) + ".")
    p.add_argument("--summary", required=True)
    p.add_argument(
        "--evidence",
        action="append",
        required=True,
        help="Repeatable, 1..5 lines, each <= 200 chars.",
    )
    p.add_argument(
        "--where-file",
        required=True,
        help="Path inside the skill folder (SKILL.md, references/x.md, ...).",
    )
    p.add_argument("--where-anchor", default=None)
    p.add_argument("--raised-by", default=None)
    p.add_argument("--severity", default="degraded",
                   help="One of: " + "|".join(SEVERITIES) + " (default: degraded).")
    p.add_argument("--agent-action", default=None,
                   help="One of: " + "|".join(AGENT_ACTIONS) + ".")
    p.add_argument("--suggested-fix", default=None)
    p.add_argument("--generalizes", default=None,
                   help="One of: " + "|".join(GENERALIZES) + ".")
    p.add_argument("--related", action="append", default=None, help="FND-NNN, repeatable.")
    p.add_argument("--session-id", default=None)
    p.add_argument("--plugin-root", default=None)
    p.add_argument("--plugin-version", default=None)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the entry and print its checks; write nothing.",
    )
    p.add_argument(
        "--allow-duplicate",
        action="store_true",
        help="Record a new lesson even if it looks like one already in the "
             "queue (by default a close match bumps that one instead).",
    )
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="Print recorded lessons, each with the maintainer's "
                                    "verdict when one has reached this project.")
    p.add_argument("--open", action="store_true")
    p.add_argument("--status", default=None,
                   help="One of: " + "|".join(LESSON_STATUSES) + ".")
    p.add_argument("--skill", default=None)
    p.add_argument("--since", default=None)
    p.add_argument("--path", default=None)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("reconcile", help="Stamp the maintainer's verdicts (from the installed "
                                         "plugin's VERDICTS.yaml) onto this project's lessons. "
                                         "record-run does this at every skill close.")
    p.add_argument("--plugin-root", default=None,
                   help="The installed plugin's folder (default: the skill running now).")
    p.set_defaults(func=cmd_reconcile)

    p = sub.add_parser("export", help="Sanitized report for the skillset owner.")
    p.add_argument("--format", default="md", choices=("md", "json"))
    p.add_argument("--open", action="store_true")
    p.add_argument("--skill", default=None)
    p.add_argument("--since", default=None)
    p.add_argument("--path", default=None)
    p.add_argument(
        "--out",
        default=None,
        metavar="FILE",
        help="Write the report here instead of printing it.",
    )
    p.add_argument(
        "--send",
        action="store_true",
        help="Mail everything unsent now, ignoring the batch "
        "schedule. Needs consent (see the consent subcommand).",
    )
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("consent", help="Read or set lesson sharing (off|ask|auto).")
    p.add_argument(
        "--set",
        default=None,
        metavar="MODE",
        help="off (never send), ask (offer at each close), " "auto (send batches on their own).",
    )
    p.set_defaults(func=cmd_consent)

    p = sub.add_parser("validate", help="Check the queue against the schema.")
    p.add_argument("--path", default=None)
    p.set_defaults(func=cmd_validate)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
