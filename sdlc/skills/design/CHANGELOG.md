# design — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.12 (2026-09-17) — New writes stamp the version the validator's floors need, the false "arch reads DESIGN" claim is gone, and Phase 1 is the shared four-state trigger

Ledger IMP-019: DESIGN.schema.yaml's example stamped `design_version: "1.0"` against this validator's 2.0 prose-deferral floor and no reference said what a new write stamps, so a freshly authored artifact's "works for one more version" fallback never expired. The example is now "2.0" and merge-validate.md carries a "Version stamp (new writes)" section (data's shape). Pinned by `_smoke/14_prose_deferral_retired/` (exit 1 at 2.0; fixture 08 stays the below-floor twin) and a `deferral_selftest.py` block; `lint_version_floors.py` holds it from here on.

Ledger IMP-010: SKILL.md and merge-validate.md claimed arch consumes DESIGN.yaml — arch has no DESIGN reference; the two words are gone. DESIGN__TOKENS.schema.yaml keeps naming the multi-mode token ambiguity; a `mode_encoding` field is declined until a project reads it (zero consumers). The task-side arms (the design_spec.tokens drift arm, crosscheck X8, the asset-source filter) are in task 1.29.

Ledger IMP-112 / IMP-173 / IMP-174 / IMP-016: Phase 1 is the five-line trigger every interview skill shares — `in_progress`; artifact present → scope the update per ux's upstream-reconciliation.md REFINE row, then merge; artifact ABSENT → restart-from-partial_answers or discard, never resume; no state file; an older `skill_version` → prd's edge-cases.md recipe, which reconciles the theme lists and the `last_ids` counters (`DESIGN__*` shards included) before offering resume. edge-cases.md's stale-state restatement is a pointer to that recipe. Pinned by prd's `_smoke/resume_recipe_lockstep_selftest.py`.

## 1.11 (2026-09-16) — A stale upstream routes NEXT to `/sdlc:design --reconcile`, and the Phase 8 pointer-write prose is gone

Ledger IMP-127 and IMP-111 - the same two defects as ux, in this skill's validator and `merge-validate.md`. Regression: `_smoke/deferral_selftest.py` (fixture 11).

## 1.10 (2026-09-15) — Phase 2's UX and PRD validator stops honour accepted deviance (`doctor.py --artifact`); a typed deferral with a malformed WRN id warns; `docs_index.py` calls run the copy `helper-resolution.md` picks

Ledger IMP-104, IMP-108, IMP-109 (2026-09-15 retro).

## 1.9 (2026-09-15) — Phase 7 stamps provenance through `docs_index.py --stamp` over every file read, `UX__<surface>.yaml` shards included, instead of a hand-written sha-only snapshot for PRD and UX

Ledger IMP-102 (aicf LSN-083, the arch lesson's sibling sweep): the write bullet asked for a
hand-written `{file, session_id, last_updated, sha256}` snapshot - a sha-only stamp with no
items map, so every `--drift` on DESIGN.yaml fell back to git or the residue, and the UX__
shards this skill reads were never recorded. Same fix as arch 1.17.

## 1.8 (2026-09-11) — `/sdlc:design --reconcile`: the upstream-change review alone, no interview; a finding waiting on this run is context, not an input-adequacy question

New `Invocation dispatch` section (the skill took no arguments before).
`--reconcile` follows the canonical form in
`ux/references/upstream-reconciliation.md`; a change that would move
`functional_structure` or the aesthetic direction is structural and names the
plain form. The input-adequacy gate leaves out re-invoke findings that
`findings.py list --owed-by docs/DESIGN.yaml` returns — this run is the
re-invocation they owe.

## 1.7 (2026-09-04) — The typed-`WRN` note names `resolution` as REQUIRED once resolved

The typed-`WRN` note now lists `resolution` and says it is REQUIRED once
`status: resolved`. Without it `warning_item.py` forces the warning back to
`open`, so a warning the user believes they closed silently never leaves the
statusboard while the artifact still validates. Ledger IMP-027; regression
`lint_claude_md.py`.

## 1.6 (2026-09-02) — This skill no longer writes `CLAUDE.md`

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

## 1.5 (2026-09-01) — Findings + drift wiring (CLAUDE.md 13/7)

Findings + drift wiring (CLAUDE.md 13/7): Phase 2 gains the input-adequacy gate
(open findings + blocking PRD QUEs, one ask), `docs_index.py --drift` decides
refine-vs-reconcile, and the draft-upstream / stale-ref prompts gain "the
upstream is wrong - record a finding for /sdlc:repair" (noted to
`state.finding_notes`, never interrupting the run); Phase 8 drains the notes
through `findings.py add` and auto-raises `upstream_incomplete` for
REQUIRED-but-null PRD/UX fields. Validator: the asset-brief coverage gate reads
the structured `deferrals: [{id, reason}]` list of the OWNING scope first — per
product in monorepo mode, so one product's deferral no longer silences another
product's same-numbered AST (the pooled design_warnings prose mention is
deprecated - honoured one more version, reported) — plus a provenance-staleness
warning (built against an older upstream; complete with no snapshot at
design_version >= 2.0). State gains `finding_notes`, `input_adequacy`,
`delta_review`, `dropped_candidates`. Regressions:
`_smoke/09_structured_deferral_monorepo`, `_smoke/10_deferral_wrong_product`,
`_smoke/11_provenance_behind`, `_smoke/deferral_selftest.py`.

## 1.4 (2026-09-01) — `set_claude_md_pointer.py` keeps the consumer CLAUDE.md's own line endings

`set_claude_md_pointer.py` keeps the consumer CLAUDE.md's own line endings (LF
or CRLF) on every write — it used to rewrite the whole file in the host's
newline on a timestamp-only update (ledger IMP-006, aicf/LSN-002; regression
sdlc/skills/task/_smoke/pointer_selftest.py runs every skill's copy).

## 1.3 (2026-09-01) — Self-review pointer de-drifted

self-review pointer de-drifted (the canonical questions live in
lessons-capture.md, no longer counted here) + `lesson_notes` drain wired at
close (CLAUDE.md 15, ledger IMP-002).

## 1.2 (2026-08-31) — Lessons capture wired (CLAUDE.md 15)

Lessons capture wired (CLAUDE.md 15): the `metrics` telemetry block rides along
in every state write, Phase 8 runs the close self-review from
`sdlc/skills/lesson/references/lessons-capture.md` and records the run via
`.claude/sdlc/lessons.py` (best-effort — an absent helper or non-zero exit
never blocks), and EXIT records `--outcome aborted`.

## 1.1 (2026-08-27) — Terminal output rewritten for the person running the pipeline

Terminal output rewritten for the person running the pipeline (CLAUDE.md 14):
three verdict tags (`[OK]` / `[DRAFT]` / `[FAIL]`, never `[OK]` above blocking
errors), one `WARNINGS` section that states it does not block, same-class
findings grouped into one line, internal ids and check codes moved out of the
message subject, and a closing `NEXT:` block naming the exact command. Phase 8
now ends with a close card the agent fills in — translated, never pasted
validator output.
