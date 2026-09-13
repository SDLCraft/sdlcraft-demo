# prd — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.12 (2026-09-11) — `reporting-to-the-user.md` rule 6 covers the demo (free) edition: a successor that does not ship in this build is named, never printed as a command, with the full edition's `homepage` as the pointer

The never-route rule now checks `${CLAUDE_SKILL_DIR}/../<name>/SKILL.md` - the
installed layout, not the repo path - and names that check as the way a skill
detects the free edition.

## 1.11 (2026-09-11) — `reporting-to-the-user.md`: a new `Next:` rule routes a reconcile chain through `docs_index.py --stale`; rule 2 no longer sends a run back to repair for a finding waiting on it; plain-string acceptance criteria / open questions warn below `prd_version` 2.0 instead of failing every legacy PRD

**Legacy-shape floor.** The ACR-NNN prefix and the typed QUE mapping had
blocked since July with no version gate, so a PRD stamped complete before then
failed (CLAUDE.md §10). `validate_schema.py` now routes a plain-string
acceptance criterion or open question into one grouped warning below
`prd_version` 2.0 and blocks from 2.0; a malformed TYPED entry (bad or
duplicate QUE id, resolved without a resolution) blocks at every version. The
floor clears the corpus because `prd_version` is an edit counter — repair's
bump took an eval fixture to 1.1 — so a reachable floor would turn a legacy PRD
red on its first repair. Regression: `_smoke/18_legacy_plain_acr_que.yaml`
(1.0, exit 0) and `19_plain_acr_que_at_floor.yaml` (2.0, exit 1); `08` still
fails, through its typed-entry errors.

New rule 3: a `--reconcile` run (or one whose write left a downstream file
stale) names the first `docs_index.py --stale` row; nothing stale and a
finding owed to the run → `/sdlc:repair FND-NNN`. Rule 2 excludes re-invoke
findings still waiting on this run's output or a file downstream of it — they
are the chain in progress. Later rules renumber (4 sharded, 5 successor, 6 not
implemented). No change to SKILL.md itself.

## 1.10 (2026-09-10) — Resume across a skill_version bump migrates the state file additively instead of offering restart

`references/edge-cases.md` "Resume with stale state" is now the canonical
recipe every skill's edge-cases point at: bump `skill_version`, add the
missing baseline keys with empty defaults, reconcile the theme lists,
record a `migrations` entry, touch no answer — then offer resume at position
1; only a downgrade still defaults to restart. Phase 1 and the state schema
name it; CLAUDE.md's State file contract carries the convention. Ledger
IMP-033 (seva-servant LSN-007); eval case 13.

## 1.9 (2026-09-10) — The idea prompt keys its telemetry as `idea_text`; template-answer questions declare `free_text_expected`; a forbidden free-text reply is mapped, read back and kept as rationale

Three telemetry-driven fixes from five seva-servant prd runs. Phase 3 names
the inventory id its idea prompt answers to (`idea_text`), so the counter no
longer lands under an improvised `idea_check` nobody can act on (IMP-067).
`performance_targets` and `acceptance_criteria` carry the new inventory key
`free_text_expected: true` - their suggestions are templates, and the
maintainer's digest (`collect_lessons.py`) now classifies such questions
by_design instead of flagging the designed answer (IMP-068). For a
`free_text_allowed: false` question, interview-mechanics.md says what an
"Other" reply becomes: the closest enum value, read back, with the text kept
in `_rationale`; `data_ownership` gains `capture_rationale: true` so the
nuance users kept typing has a designed home (IMP-037). Regression:
`lesson/_smoke/collect_selftest.py` classification cases.

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

## 1.6 (2026-09-01) — Findings capture + the QUE gate + the sweep-drop record

Findings capture + the QUE gate + the sweep-drop record: the validator warns
when an `open_questions[].blocks` entry does not resolve to an emitted
FR/NFR/WKF/ACR id (warn-level, never blocks; regression
`_smoke/15_que_blocks_dangling.yaml`); Phase 7 offers an acceptance-criteria
backfill for the features its warnings name; the new `state.finding_notes`
scratch list (fed only by the a-2 free-text fold in
`references/importance-flows.md` — prd consumes no upstream artifact, so
nothing auto-raises) is drained at Phase 8 via `findings.py add --raised-by
sdlc-prd` on every exit path, and the close card gains a `Findings:` row + a
`/sdlc:repair` Next rule; the scope sweep's "Wrap up" arm records declined
candidates under `state.dropped_candidates` and step e stops re-surfacing them;
`required_if` gets its canonical activation-vs-promotion definition in
`references/interview-mechanics.md`; close card says "can run it"; the leftover
literal Next card is gone; the Phase-7 validator call and merge-validate.md's
pre-plugin path both fixed to portable forms.

## 1.5 (2026-09-01) — PRD schema 1.1 (adopted from the AICF meta-corpus PRD)

PRD schema 1.1 (adopted from the AICF meta-corpus PRD): `runtime_platform` is a
LIST; enum widenings (tui/service/library/voice, local/cloud_managed/
mobile_app_store, not_applicable_cli, phi/pci, bsl/sspl/dual, mtls); seven
optional context blocks (glossary, user_stories/USR-NNN, internationalization,
competitive_landscape, legal_and_terms, analytics_and_telemetry,
support_model); `risks_assumptions.dependencies` deprecated. Regressions:
_smoke/11-14. Also: `set_claude_md_pointer.py` keeps the consumer CLAUDE.md's
own line endings (LF or CRLF) on every write — it used to rewrite the whole
file in the host's newline on a timestamp-only update (ledger IMP-006,
aicf/LSN-002; regression sdlc/skills/task/_smoke/pointer_selftest.py runs every
skill's copy).

## 1.4 (2026-09-01) — Never-interrupt capture + the channel rule (ledger IMP-002/IMP-003)

never-interrupt capture + the channel rule (ledger IMP-002/IMP-003): mid-run
observations go to the state file's `lesson_notes` and are drained by the Phase
8 self-review (never an interrupted interview); the EXIT path drains them too;
approval drafts ride INSIDE the AskUserQuestion call (option preview / question
text — see references/importance-flows.md → "The channel rule"), never only as
same-turn chat markdown; Phase 8's self-review pointer de-drifted (the
canonical questions live in lessons-capture.md). Regressions: evals/evals.json
case 12, lesson/evals cases 9-11.

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
