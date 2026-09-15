# data — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

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
