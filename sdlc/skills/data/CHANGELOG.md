# data — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.22 (2026-09-24) — The helper-resolution clause covers every `.claude/sdlc/<helper>.py` the file runs, not `docs_index.py` alone

- `SKILL.md` (ledger IMP-218): the Phase-2 clause reads "every `python .claude/sdlc/<helper>.py …` in this file (`docs_index.py` and the close-phase helpers alike) runs the copy `helper-resolution.md` picks once per run", so a lagging install runs the plugin's `statusboard.py`, `lessons.py` and `autocommit.py` at the close too - a run on a 0.9.16 install had drawn the old statusboard and would have stamped no verdicts. Pinned by `setup/_smoke/helper_resolution_selftest.py` arm 4.

## 1.21 (2026-09-22) — Phase 8 row-omission footer is one line pointing at reporting-to-the-user.md

- Phase 8's row-omission footer (two paragraphs) became one line pointing at `reporting-to-the-user.md`, which states the rules in full (ledger IMP-181, AUTHORING §19); SKILL_LINE_CEILINGS lowered in `lint_context_budget.py`.

## 1.20 (2026-09-20) — Phase 8 commits the run when the project opted in (auto-commit, CLAUDE.md 20)

- New close step after `record-run`, before the card: `python .claude/sdlc/autocommit.py commit --skill data --invocation "<as typed>" --summary "<one line>"` (mechanics in `setup/references/auto-commit.md`), its one printed line as the card's new `Commit:` row; runs on every exit path, never a blocker. The restated self-review paragraph is now a pointer at `lessons-capture.md`, paying for the lines (AUTHORING §19 ceilings unchanged). Pinned by `setup/_smoke/autocommit_lockstep_selftest.py`.

## 1.19 (2026-09-19) — Phase 8's index refresh distinguishes own-toolchain from never-ran-setup

- Phase 8's index refresh distinguishes own-toolchain (marker present, no `docs_index` helper: run the project's own docs-hook command from `.claude/settings.json` and name it) from never-ran-setup (no marker: the only genuine no-op), per setup's helper-resolution.md; the statusboard sentence is unchanged. Pinned by setup's `_smoke/index_refresh_lockstep_selftest.py` (ledger IMP-200).

- The `Phase 3 (first step) — Repo evidence` block keeps only its skill-specific lines and a consumer-safe pointer (`${CLAUDE_SKILL_DIR}/../setup/references/repo-evidence.md`); the fifteen lines setup's canonical file already states are gone (14 lines shorter; the lint_context_budget ceiling follows). `lint_skill_paths.py` now flags a bare `sdlc/skills/<x>/references/<y>.md` path in shipped markdown (ledger IMP-181).

- Every cross-skill reference pointer in SKILL.md and references/ now uses the consumer-safe `${CLAUDE_SKILL_DIR}/../<skill>/references/<file>.md` form instead of a bare `sdlc/skills/...` path that resolves only in the plugin repository; `lint_skill_paths.py` holds it (ledger IMP-206).

- No shipped runtime file (SKILL.md, references/, assets/) carries a ledger-id citation any more: bare `(IMP-NNN)` / `(LSN-NNN)` parentheticals are gone, history sentences keep their rule and their reason without the ticket, close-card examples show the `LSN-NNN` placeholder; `lint_context_budget.py` counts IMP- and LSN- ids with a ceiling of 0 per skill (ledger IMP-182).

## 1.18 (2026-09-17) — The schema template stamps the version the validator's floors need, and Phase 1 is the shared four-state trigger

Ledger IMP-178 (the fourth instance of a floor nothing reached, found by the new repo lint). DATA-MODEL.schema.yaml's example stamped `data_model_version: "1.1"` against `_PARADIGM_GATE_VERSION` (3.0) while merge-validate.md already said new writes stamp 3.0 — the example is now "3.0". `lint_version_floors.py` holds every skill's template and stamp sentence at or above its own floors from here on.

Ledger IMP-112 / IMP-173 / IMP-174 / IMP-016: Phase 1 had no stale-state trigger at all; it is now the five-line shape every interview skill shares — `in_progress`; artifact present → scope the update per ux's upstream-reconciliation.md REFINE row, then merge; artifact ABSENT → restart-from-partial_answers or discard, never resume; no state file; an older `skill_version` → prd's edge-cases.md recipe, which reconciles the theme lists and the `last_ids` counters (max of the state counter and the highest id on disk, shards included) before offering resume. merge-validate.md's counter restatement is a pointer to that recipe. Pinned by prd's `_smoke/resume_recipe_lockstep_selftest.py`.

## 1.17 (2026-09-17) — The critical-tier entity card rides inside the approval question

Ledger IMP-137 (AUTHORING §18). The entity state machine's PROPOSE, list-approve and FINAL-APPROVAL steps showed the drafted card in chat and then asked, in the same turn, for approval — the IMP-003 defect, since same-turn chat markdown may not render. The card now rides in the recommended option's `preview` (a worked example, the shape api's step-e already had), and the reference cites §18. Pinned by prd's `_smoke/channel_rule_selftest.py`. The earlier ledger claim that this skill's restatement was compliant was wrong: it had none.

## 1.16 (2026-09-17) — The five entity-bearing blocks that never resolved their `entity:` name now do (error at data_model_version 3.0, warning below), and an entity nothing is connected to draws an orphan warning

Ledger IMP-012. `check_entity_ref_fields` resolves `id_strategy.natural_keys`, `indexes_and_queries.access_patterns` / `expected_indexes` and `integrity_and_constraints.unique_constraints` / `check_constraints` against `entities` — a typo'd name used to validate clean. `check_orphan_entities` warns on an entity that is CONNECTED to nothing: named by no other block AND owning no `one_of` / `composes` of its own (inbound-only would have flagged every union root — 5 of 21 valid fixtures); guarded by entities ≥ 2 and a non-empty reference-bearing block, else one vacuous-pass line. Regression: `_smoke/40_entity_ref_unresolved_at_floor.yaml` (exit 1) / `41_…_below_floor.yaml` (exit 0) and `_smoke/orphan_selftest.py` (0 of 21 valid fixtures gain the warning). Declined from the same item: the tenancy/SaaS fields and the geometry/abstract/enum_meta taxonomy — zero consumers, no reporting project.

## 1.15 (2026-09-16) — An entity whose fields come entirely from a composed mixin is no longer refused: `check_required`'s own-`fields` gate resolves through the composes-aware helper `check_union_integrity` already used

Ledger IMP-163 (IMP-138's named residual). Regression: `_smoke/38_composes_only_fields.yaml` flipped from `expect: 1` to `expect: 0` - the fixture that pinned the residual now pins the fix. An unresolvable or empty composes chain still resolves to no fields, so nothing is over-relaxed. The task-side half (`embed_sources.py` reads an entity's own fields with no composes resolution) is IMP-170.

## 1.14 (2026-09-16) — A stale upstream routes NEXT to `/sdlc:data --reconcile`, and the Phase 8 pointer-write prose is gone

Ledger IMP-127 and IMP-111. Regression: `_smoke/deferral_selftest.py`, which now also runs fixture `30_provenance_behind` and pins its NEXT line.

## 1.13 (2026-09-15) — The downstream-rejection rule names the accepted-deviance exception; a typed deferral with a malformed WRN id warns; `docs_index.py` calls run the copy `helper-resolution.md` picks

Ledger IMP-104, IMP-108, IMP-109 (2026-09-15 retro).

## 1.12 (2026-09-15) — Phase 7 stamps provenance through `docs_index.py --stamp` over every file read, `UX__<surface>.yaml` shards included, instead of a hand-written sha-only entry for the two canonicals

Ledger IMP-102 (aicf LSN-083, the arch lesson's sibling sweep): the write paragraph told the
agent to hand-write `{file, session_id, last_updated, sha256}` for `PRD.yaml` and `UX.yaml`
- a sha-only stamp with no items map, so every `--drift` on DATA-MODEL fell back to git or the
residue, and the UX__ shards this skill reads were never recorded. Same fix as arch 1.17;
`--stale` now warns about the sha-only entries a project still carries.

## 1.11 (2026-09-12) — DATA-MODEL entities gain `one_of` + `discriminator` (a discriminated union): a union parent is exempt from `fields`/`primary_key`, every variant must exist and carry the discriminator (blocking from 3.0), and one interview question makes it reachable

Ledger IMP-080 (aicf LSN-061): `fields` was required on every entity in every
paradigm and no construct expressed "an instance is exactly one of these", so a
union parent could only be flattened or smuggled in as a private extension that
failed the required-field check forever (the consumer's FND-011, accepted with
expected_count 1, which then blocked arch). `Entity.one_of: [Variant, ...]` +
`discriminator: <field>`; `check_required` skips `fields` / `primary_key` for a
union parent; new `check_union_integrity` (discriminator named, every variant
declared and not the parent itself, every variant carries the discriminator field)
errors at `data_model_version >= 3.0` and warns below (CLAUDE.md section 10).
`data-questions.yaml` gains `entity-one-of`; SKILL.md Phase 6 and
`submodel-and-context-sweep.md` name the construct. Follow-up (not this run):
task's `entity_slice` v2 should copy `one_of`/`discriminator` beside invariants.
Regression: `_smoke/34_union_one_of.yaml` (0), `35_union_missing_variant.yaml` (1),
`36_union_legacy_below_floor.yaml` (0).

## 1.10 (2026-09-11) — `/sdlc:data --reconcile`: the upstream-change review alone, no interview; a finding waiting on this run is context, not an input-adequacy question

New `Invocation dispatch` section (the skill took no arguments before).
`--reconcile` follows the canonical form in
`ux/references/upstream-reconciliation.md`: a new entity gets the per-entity
drill and its own sub-model sweep only; another storage paradigm or bounded-
context split is structural and names the plain form. The input-adequacy gate
leaves out re-invoke findings that `findings.py list --owed-by
docs/DATA-MODEL.yaml` returns.

## 1.9 (2026-09-09) — The `[deferral hygiene]` report names only ids whose prose deferral is load-bearing

`DataDeferralIndex.defer(ids, covered=...)`: a prose-matched id an entity
already traces still defers as before but is no longer reported, so the
count can reach zero and the remedy never tells the author to declare
traced behaviour out of scope. Ledger IMP-042 (aicf LSN-021/029);
regression `_smoke/deferral_selftest.py` + fixture 33.

## 1.8 (2026-09-04) — The typed-`WRN` note names `resolution` as REQUIRED once resolved

The typed-`WRN` note now lists `resolution` and says it is REQUIRED once
`status: resolved`. Without it `warning_item.py` forces the warning back to
`open`, so a warning the user believes they closed silently never leaves the
statusboard while the artifact still validates. Ledger IMP-027; regression
`lint_claude_md.py`.

## 1.7 (2026-09-02) — This skill no longer writes `CLAUDE.md`

This skill no longer writes `CLAUDE.md`. `set_claude_md_pointer.py` is deleted
and the `Write(CLAUDE.md)` grant is gone: `/sdlc:setup` owns that file and
writes one static `## SDLC Documents` block, so the per-skill bullet and its
`Last updated by … on <timestamp>` tail — rewritten on every run, read back by
nothing — are retired. Phase 8 now refreshes `docs/INDEX.yaml` **and**
`.claude/rules/sdlc-statusboard.md` instead. Warnings may be written in the
typed `WRN` form (`{id, text, kind, status, impact, refs?, defers?,
resolution?, resolved_on?}`, CLAUDE.md 2). `resolution` is REQUIRED once
`status: resolved` - without it `warning_item.py` forces the warning back to
`open`, so it silently never leaves the statusboard while the artifact still
validates. Legacy `"WRN-NNN: <text>"` strings stay valid forever and read as
`{kind: note, status: open, impact: local}`.

## 1.6 (2026-09-01) — Pipeline-loop pass: `persistence.paradigm` admits `none`

pipeline-loop pass: `persistence.paradigm` admits `none` (a stateless project
completes with empty entities; the coverage check is skipped and says so);
structured trace-or-defer via a top-level `deferrals: [{id, reason}]` list
(prose WRN mentions honoured one more version, reported);
`secondary_stores[].store_id` + `entities.stored_in` (store binding ARCH
resolves); `entities.invariants` + lifecycle cross-checks (field exists,
terminal states, enum containment); provenance-staleness warning; Phase 2 gains
the `docs_index.py --drift` check and the input-adequacy gate; Phase 8 drains
`state.finding_notes` into `/sdlc:repair`'s queue (auto `upstream_incomplete`);
state gains
`finding_notes`/`delta_review`/`input_adequacy`/`dropped_candidates`.
Regressions: _smoke/26_paradigm_none.yaml, 27_structured_deferral,
28_deferral_missing_reason, 29_stored_in_unknown.yaml, 30_provenance_behind,
31_deferral_prose_fallback.

## 1.5 (2026-09-01) — PRD 1.1 propagation: new `data_classification.localized_fields`

PRD 1.1 propagation: new `data_classification.localized_fields` (same integrity
check as pii_fields; asked when PRD.internationalization.enabled); `phi`/`pci`
promote `regulated_fields`; glossary + i18n pre-fill rows. Regressions:
_smoke/24-25. Also: `set_claude_md_pointer.py` keeps the consumer CLAUDE.md's
own line endings (LF or CRLF) on every write — it used to rewrite the whole
file in the host's newline on a timestamp-only update (ledger IMP-006,
aicf/LSN-002; regression sdlc/skills/task/_smoke/pointer_selftest.py runs every
skill's copy).

## 1.4 (2026-09-01) — Self-review pointer de-drifted

self-review pointer de-drifted (the canonical questions live in
lessons-capture.md, no longer counted here) + `lesson_notes` drain wired at
close (CLAUDE.md 15, ledger IMP-002).

## 1.3 (2026-08-31) — Lessons capture wired (CLAUDE.md 15)

Lessons capture wired (CLAUDE.md 15): the `metrics` telemetry block rides along
in every state write, Phase 8 runs the close self-review from
`sdlc/skills/lesson/references/lessons-capture.md` and records the run via
`.claude/sdlc/lessons.py` (best-effort — an absent helper or non-zero exit
never blocks), and EXIT records `--outcome aborted`.

## 1.2 (2026-08-27) — Terminal output rewritten for the person running the pipeline

Terminal output rewritten for the person running the pipeline (CLAUDE.md 14):
three verdict tags (`[OK]` / `[DRAFT]` / `[FAIL]`, never `[OK]` above blocking
errors), one `WARNINGS` section that states it does not block, same-class
findings grouped into one line, internal ids and check codes moved out of the
message subject, and a closing `NEXT:` block naming the exact command. Phase 8
now ends with a close card the agent fills in — translated, never pasted
validator output.
