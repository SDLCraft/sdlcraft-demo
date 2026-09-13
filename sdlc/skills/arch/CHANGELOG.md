# arch — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.16 (2026-09-12) — Phase 2 honours an accepted upstream deviance (the IMP-052 clause, consulted through `doctor.py --artifact`) instead of stopping on any non-zero upstream validator

Ledger IMP-081 (aicf LSN-062, a blocker): `arch` never received the clause
IMP-052 gave `test` and `task`, so a project with one permanently accepted
DATA-MODEL error (a `wontfix` finding carrying `expected_count: N`) could not run
`/sdlc:arch` at all - and the next command in an open finding chain was exactly
that. The required-upstream gate now stops on a non-zero validator only when the
project has not accepted that exact deviance, consulted through `doctor.py
--artifact docs/<file>` (never `--quick`, which runs no per-artifact validator).
Eval case 6 (phase-2-accepted-deviance) pins it.

## 1.15 (2026-09-11) — Demo edition: with no `test` skill installed, the validator's NEXT line and the close card point to the full edition instead of `/sdlc:test`

The public free build (the "demo edition") ships setup through arch and leaves
test, task and code out. `validate_schema.py` checks `../test/SKILL.md` - the
same existence check `reporting-to-the-user.md` rule 6 gives the agent:
present, `NEXT: /sdlc:test` as before; absent, "this is where the demo edition
ends" plus the `homepage`
from the plugin's `plugin.json`. Dispatch rule 5's abort message and the close
card's successor arm say the same. Regression: `_smoke/edition_selftest.py`
runs the validator from throwaway plugin trees with and without `skills/test/`.

## 1.14 (2026-09-11) — `/sdlc:arch [--system | <container>] --reconcile` (bare: every stale ARCH file); auto-advance resolves a stale stamp to it instead of a full re-run

Dispatch rule 5 is the reconcile form, following the canonical form in
`ux/references/upstream-reconciliation.md`; an added item that needs a new
container is structural and names `/sdlc:arch --system`. The auto-advance
resolver's stale-provenance arm (IMP-049) now resolves to the file's
reconcile form. The system sub-session carries `reconcile_queue` for the bare
walk. The input-adequacy gate leaves out findings owed to the ARCH file this
run writes.

## 1.13 (2026-09-10) — Cross-check 32 warns on a work_unit nothing reaches

The mirror of the entity-with-no-unit arm: a function that is not `kind:
entrypoint`, is the target of no `via_unit` edge (internal or external, any
container), routes to no API operation, and is named in no sibling function's
contract is reported, warn-level, with the three remedies (wire a caller, mark
it entrypoint, defer it). Units in framework-invoked components (controller,
event_handler, scheduler, background_worker, …), non-callable deliverables
(module / content / tooling) and deferred ids are exempt, and the check runs
only in a container that pins at least one caller — where no call structure
was modelled at all, absence says nothing. Ledger IMP-062 (aicf LSN-026);
fixture 38 + `_smoke/seam_and_path_selftest.py`.

## 1.12 (2026-09-10) — Cross-check 28(a) reads an input's type from the `name: Type` shorthand only, never from prose

A warning-level false reject seen on a corpus that writes inputs as prose
contracts (IMP-075, aicf LSN-055; `_smoke/seam_and_path_selftest.py`,
fixture 37). The check used to tokenize every capitalized word of the whole
inputs string, so emphasis words (PURE, ASSIGNED), env-var names
(LLM_BASE_URL), proper nouns (GitHub, SQL) and plurals of real entities
(StageCostRecords) each became a row — 85 of 85 rows noise there, burying the
one real 28(d) row. An entry now declares a type only when its left side is an
identifier and its right side, minus a trailing `(note)` / ` - note`, is a type
expression; ALL-CAPS tokens never count; a note naming the caller marks the
value caller-supplied (the remedy text always suggested that, and it now
works); an entity's plural resolves to the entity; a module-qualified library
type (`click.Context`) is an import, pinned to its origin. Prose declares
nothing — an accepted false negative on an advisory check.

## 1.11 (2026-09-10) — Cross-check 25 spares paths under `output_locations`; cross-check 27 spares external callees

Two warning-level false rejects seen on a generator project (IMP-070/071,
aicf LSN-048/049; `_smoke/seam_and_path_selftest.py`, fixtures 35 + 36).
ARCH.yaml gains an optional `output_locations: [{path, written_by?, note?}]`
list naming the roots the RUNNING system writes; check 25 no longer reports
a requirement's path under one of them as a deliverable no component owns,
and its remedy names the field. Check 27 receives the system ARCH and skips a
`calls` edge whose callee is `external: true` or an `external-service` -
such a container has no work_units, so the `via_unit` it demanded could never
exist; its seam is the callee's `external_contract` or an API resource.

## 1.10 (2026-09-09) — The entry-point advisory spares imported libraries and groups per container; rule 5 has a stale-provenance arm

The "single file with N functions but no entry point" nudge skips any
component a sibling imports (the `to` side of an internal edge) and prints
one grouped line per container when several candidates remain (IMP-050,
aicf LSN-032; `_smoke/gap1_selftest.py`). The auto-advance resolver's rule
5 runs the provenance drift check before declaring the architecture fully
specified and resolves a stale stamp to that file's delta review, naming
`/sdlc:arch --system` as what clears the warning (IMP-049, LSN-028; evals
case 4).

## 1.9 (2026-09-02) — This skill no longer writes `CLAUDE.md` - `/sdlc:setup` owns it

This skill no longer writes CLAUDE.md - set_claude_md_pointer.py is deleted and
/sdlc:setup owns that file (one static section, no timestamps). Phase 8
refreshes docs/INDEX.yaml AND the statusboard. Warnings may use the typed WRN
form; legacy strings stay valid.

## 1.8 (2026-09-01) — Schema 2.0: INT binding, per-container configuration and stable store ids

Schema 2.0 pass. INT binding (realizes_integrations / int_refs /
external_contract; trace-or-defer coverage), per-container configuration block,
work_units owns_callables, stable store ids (realizes_store), structural
top-level deferrals (CLAUDE.md 6), provenance-staleness + untraced-entity +
contract-seam warnings, and the CLAUDE.md 10 version gate on checks #21-#24
(ERROR >= 2.0, WARN below). Phase 2 gains the input-adequacy gate + docs_index
--drift; Phase 8 drains finding_notes into findings.py and auto-raises
upstream_incomplete. Regression: _smoke/26-33 + re-pinned expected.yaml.

## 1.7 (2026-09-01) — PRD 1.1 propagation: the surface/container table gains tui, voice, service and library

PRD 1.1 propagation: surface->container table gains tui/voice/service/ library
(browser_extension dropped - never a ux value); tech-stack pre-fill reads the
runtime_platform LIST; observability seeds candidate business metrics from
PRD.analytics_and_telemetry.product_events. Also set_claude_md_pointer.py keeps
CLAUDE.md's own line endings (ledger IMP-006).

## 1.6 (2026-09-01) — Close self-review pointer de-drifted + lesson_notes drain wired

Close self-review pointer de-drifted + lesson_notes drain wired at close
(CLAUDE.md 15, ledger IMP-002); high-tier draft display gains the channel-rule
caveat in references/interview-mechanics.md (ledger IMP-005).

## 1.5 (2026-08-31) — Lessons capture wired (CLAUDE.md 15) — per-sub-session metrics

Lessons capture wired (CLAUDE.md 15) — per-sub-session metrics telemetry rides
along in every state write; Phase 8 runs the close self-review from
lesson/references/lessons-capture.md and records the run via
.claude/sdlc/lessons.py (best-effort — absent helper or non-zero exit never
blocks); EXIT records --outcome aborted.

## 1.4 (2026-08-27) — Terminal output rewritten for the person running the pipeline

Terminal output rewritten for the person running the pipeline (CLAUDE.md 14):
three verdict tags ([OK]/[DRAFT]/[FAIL], never [OK] over blocking errors), one
WARNINGS section that states it does not block, same-class findings grouped,
internal ids and check codes moved out of the message subject, and a closing
NEXT block naming the exact command. Phase 8 now ends with a close card the
agent fills in (translated, never pasted validator output).

## 1.3 (2026-07-19) — SPLAN3 contract quality — SK-21 emptiness roll-up advisory

SPLAN3 contract quality — SK-21 emptiness roll-up advisory (>=3 callable units
>=80% all-empty); SK-22 derive rule (component traces_data_entities = curated
UNION unit touches, Phase 7) + subset fix-hint + missing-key advisory; family
contracts reframed as opt-in for any project (fold >=3 same-shape units);
aggregator/ dispatcher contract pattern documented (PLAN2-D3).

## 1.2 (2026-07-03) — work_units cross-check #21 upgraded to BLOCKING for non-trivial

work_units cross-check #21 upgraded to BLOCKING for non-trivial components
(waivable via work_units_waiver); new #22 FR->work_unit coverage cross-check;
work_units emit block-style; "drilled" now means internally complete (#21/#22),
so auto-advance resumes drilled-but-incomplete containers instead of counting
them as specified.

## 1.1 — Per-component work_units (#21), code_location (#20), upstream provenance

per-component work_units (#21), code_location (#20), upstream provenance.
