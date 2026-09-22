# arch — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.24 (2026-09-22) — Cross-check 21 reports an entity no work_unit touches; cross-check 32 stops counting a mention or a file name as a call; Phase 8 footer is one line

- Cross-check 21 advisory: an entity a non-repository component traces that no work_unit in the container touches is named with every component tracing it (no worker packet carries its slice); repository components are exempt; ungated. `merge-validate.md`'s unconditional "may EXCEED the union" allowance is replaced by that rule (ledger IMP-208, pinned by `_smoke/trace_excess_selftest.py` + fixture 46).
- Cross-check 32: a name followed by a file extension is a file reference, not a call; a qualified `component.unit` mention still counts with no verb; a bare-name mention counts only in a sentence of the same contract field that carries a call-verb stem - a heuristic, since no typed call field exists (ledger IMP-202, pinned by `_smoke/seam_and_path_selftest.py` + fixture 47). The demo corpus moves 42 -> 63 "called by nothing" units: 15 file-mention-only stage modules, 6 verb-less mentions.
- Phase 8's row-omission footer (two paragraphs) became one line pointing at `reporting-to-the-user.md`, which states the rules in full (ledger IMP-181, AUTHORING §19); SKILL_LINE_CEILINGS lowered in `lint_context_budget.py`.

## 1.23 (2026-09-20) — Phase 8 commits the run when the project opted in (auto-commit, CLAUDE.md 20)

- New close step after `record-run`, before the card: `python .claude/sdlc/autocommit.py commit --skill arch --invocation "<as typed>" --summary "<one line>"` (mechanics in `setup/references/auto-commit.md`), its one printed line as the card's new `Commit:` row; runs on every exit path, never a blocker. The restated self-review paragraph is now a pointer at `lessons-capture.md`, paying for the lines (AUTHORING §19 ceilings unchanged). Pinned by `setup/_smoke/autocommit_lockstep_selftest.py`.

## 1.22 (2026-09-19) — Cross-check 32 accepts a callee named in its own component's qualified form, `--path` on an ARCH__<cid>.yaml shard validates the family, and Phase 8 distinguishes own-toolchain

- `check_unreachable_work_units` (cross-check 32) also accepts a callee named in its OWN component's qualified form `<component_id>.<unit>`; a same-name mention under a different component's prefix still does not count as a call. Pinned by fixture `38_unreachable_unit` + `seam_and_path_selftest.py` (ledger IMP-189).
- `validate_all()` no longer applies the system Arch model to an `ARCH__<cid>.yaml` shard given to `--path`: a shard path redirects to its `ARCH.yaml` sibling and validates the whole family, mirroring test/task; a shard whose system file is missing gets a named exit-2 message; `[OK]` prints the system path. Pinned by the `39_shard_provenance/ARCH__backend-api.yaml` row (ledger IMP-199).
- Phase 8's index refresh distinguishes own-toolchain (marker present, no `docs_index` helper: run the project's own docs-hook command from `.claude/settings.json` and name it) from never-ran-setup (no marker: the only genuine no-op), per setup's helper-resolution.md; the statusboard sentence is unchanged. Pinned by setup's `_smoke/index_refresh_lockstep_selftest.py` (ledger IMP-200).

- The `Phase 3 (first step) — Repo evidence` block keeps only its skill-specific lines and a consumer-safe pointer (`${CLAUDE_SKILL_DIR}/../setup/references/repo-evidence.md`); the fifteen lines setup's canonical file already states are gone (14 lines shorter; the lint_context_budget ceiling follows). `lint_skill_paths.py` now flags a bare `sdlc/skills/<x>/references/<y>.md` path in shipped markdown (ledger IMP-181).

- Every cross-skill reference pointer in SKILL.md and references/ now uses the consumer-safe `${CLAUDE_SKILL_DIR}/../<skill>/references/<file>.md` form instead of a bare `sdlc/skills/...` path that resolves only in the plugin repository; `lint_skill_paths.py` holds it (ledger IMP-206).

- No shipped runtime file (SKILL.md, references/, assets/) carries a ledger-id citation any more: bare `(IMP-NNN)` / `(LSN-NNN)` parentheticals are gone, history sentences keep their rule and their reason without the ticket, close-card examples show the `LSN-NNN` placeholder; `lint_context_budget.py` counts IMP- and LSN- ids with a ceiling of 0 per skill (ledger IMP-182).

## 1.21 (2026-09-17) — The write-time stamp is written down, the shared provenance helper declares the version fields it gates, and Phase 1 is the shared four-state trigger

Ledger IMP-178. merge-validate.md gains the one-sentence stamp rule (new writes stamp `arch_version` "2.0" — the schema already did, the reference never said so), and `check_provenance_staleness`'s def line carries `# version-floor-fields: arch_version, arch_container_version`, the declared mapping `lint_version_floors.py` reads for a helper whose bare `version` parameter serves both the system file and every container — declared, never guessed; a floor with neither a traceable field nor an annotation stays red in that lint.

Ledger IMP-112 / IMP-173 / IMP-174 / IMP-016: Phase 1 had no stale-state trigger at all; it is now the five-line shape every interview skill shares — `in_progress`; artifact present → scope the update per ux's upstream-reconciliation.md REFINE row, then merge; artifact ABSENT → restart-from-partial_answers or discard, never resume; no state file; an older `skill_version` → prd's edge-cases.md recipe, which reconciles the theme lists and the `last_ids` counters (`ARCH__*` shards included) before offering resume. Pinned by prd's `_smoke/resume_recipe_lockstep_selftest.py`.

## 1.20 (2026-09-17) — One cross-check table instead of four, reachability that agrees with Gap-1, an honest #25 remedy, and the reason-less non_container_features escape closed at the 2.0 floor

Ledger IMP-013: `references/merge-validate.md` is the one canonical cross-check table (it is what Phase 7 loads); SKILL.md and both schemas point at it instead of restating it, the validator docstring is a pointer too, #30's output gained its `[cross-check 30]` tag, #31/#32 are in the table, the two sequences (#1-#15 system, #21-#32 container/suite) are named, ARCH__CONTAINER.schema.yaml no longer calls #21's no-waiver path non-blocking, and SKILL.md's stale "the 4 cross-checks" is gone. Pinned by `_smoke/crosscheck_table_selftest.py` (the validator's tag set against the canonical section; red at 1.19 on eight counts). The red team dropped the planned generic root lint: only arch prints `[cross-check N]`. Observability siblings: wontfix, deploy's.

Ledger IMP-126: `check_unreachable_work_units` (#32) counts a via_unit-less `calls` edge into a single-callable-unit component as reached (never a `depends_on` edge, which proves an import) and collapses a multi-unit ambiguity into one grouped "pin via_unit" advisory; Gap-1 no longer says "nothing owns startup" when the container already has an entrypoint elsewhere; the deferral probe accepts `<cid>/<component>/<unit>`; the remedy stops telling a framework-invoked unit to become `kind: entrypoint`. Pinned by three new `seam_and_path_selftest.py` arms over fixtures 41-43.

Ledger IMP-128: the #25 remedy (validator string, SKILL.md, component-discovery.md) no longer tells container mode to write `output_locations` or claims an interview question asks for it; system mode's update/`--reconcile` flow gains one conditional ask, only when #25 rows are non-empty. Pinned by two `seam_and_path_selftest.py` assertions.

Ledger IMP-129 (arch half; api's is in api 1.13): `feature_legacy_fallback` is gated by the existing `GATE_FLOOR` — at/above `arch_version` 2.0 a bare `non_container_features` entry no longer counts as coverage and blocks like any uncovered FR; below it warns as before; `evals/grade.py` counts `deferrals[].id` as coverage. Regression: `_smoke/44_legacy_fallback_floor/` (exit 1) / `45_…_below/` (exit 0), built from the passing fixture 16. The task-side reader of the list is IMP-176.

## 1.19 (2026-09-16) — The validator's NEXT names the stale file's own reconcile form instead of `/sdlc:test`

Ledger IMP-127 (aicf LSN-028's other half). IMP-049 gave the auto-advance RESOLVER a provenance arm at 1.14 and left the validator printing `NEXT: /sdlc:test` underneath its own "run /sdlc:arch to review the delta" warning - the same loop, in the output the user reads. NEXT now names `--system --reconcile` or `<container> --reconcile` for whichever file is stale, and the warning tail names the reconcile form too. Regression: `_smoke/provenance_selftest.py` on fixture `31_provenance_stale`.

## 1.18 (2026-09-15) — `DeferralIndex` reads typed `kind: deferral` warnings' `defers` like every sibling; the accepted-deviance clause points at `repair/references/accepted-deviance.md` and edge-cases.md no longer orders an unconditional stop

Ledger IMP-104, IMP-108, IMP-109 (2026-09-15 retro). A typed deferral of an uncovered INT used to turn ARCH.yaml red while six sibling validators accepted it; `_smoke/40_typed_int_deferral` pins exit 0. A malformed-id typed deferral warns. `docs_index.py` calls run the copy `helper-resolution.md` picks.

## 1.17 (2026-09-15) — Phase 7 stamps every file read through `docs_index.py --stamp`, owned UX__/API__ shards included, and the validator warns on an owned shard the stamp omits

Ledger IMP-102 (aicf LSN-083): Phase 7 enumerated four canonical files for a hand-written
`{file, session_id, last_updated, sha256}` snapshot, so a container built from
`UX__<surface>.yaml` / `API__<resource>.yaml` shards recorded neither and a shard edit that
left `UX.yaml` byte-identical was invisible to `--drift`, `--stale` and `<container>
--reconcile` - five moved surface shards went unreported on one reconcile. Phase 7 now uses
the helper with one `--upstream` per file read (shards from `owns_ux_surfaces` /
`owns_api_resources`), which also records the items map a hand-written entry never had.
`check_shard_provenance` (warn-level, no floor) names a complete container shard that owns a
surface or resource whose shard file its provenance omits, with the stamp that records it.
Regression: `_smoke/provenance_selftest.py` on fixture `39_shard_provenance`.

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
