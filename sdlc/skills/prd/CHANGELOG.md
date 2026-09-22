# prd — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.22 (2026-09-22) — Phase 8 footer is one line, and the close card's Findings: row follows the canonical rule

- Phase 8's row-omission footer (two paragraphs) became one line pointing at `reporting-to-the-user.md`, which states the rules in full (ledger IMP-181, AUTHORING §19); SKILL_LINE_CEILINGS lowered in `lint_context_budget.py`. The narrower `Findings:` rule this skill restated is dropped, so the canonical rule ("or open findings name an artifact this skill consumed") now governs its close card too - a behaviour widening, not only a text move.

## 1.21 (2026-09-20) — Phase 8 commits the run when the project opted in (auto-commit, CLAUDE.md 20)

- New close step after `record-run`, before the card: `python .claude/sdlc/autocommit.py commit --skill prd --invocation "<as typed>" --summary "<one line>"` (mechanics in `setup/references/auto-commit.md`), its one printed line as the card's new `Commit:` row; runs on every exit path, never a blocker. The restated self-review paragraph is now a pointer at `lessons-capture.md`, paying for the lines (AUTHORING §19 ceilings unchanged). Pinned by `setup/_smoke/autocommit_lockstep_selftest.py`.

## 1.20 (2026-09-19) — Phase 8's index refresh distinguishes own-toolchain from never-ran-setup

- Phase 8's index refresh distinguishes own-toolchain (marker present, no `docs_index` helper: run the project's own docs-hook command from `.claude/settings.json` and name it) from never-ran-setup (no marker: the only genuine no-op), per setup's helper-resolution.md; the statusboard sentence is unchanged. Pinned by setup's `_smoke/index_refresh_lockstep_selftest.py` (ledger IMP-200).

- Every cross-skill reference pointer in SKILL.md and references/ now uses the consumer-safe `${CLAUDE_SKILL_DIR}/../<skill>/references/<file>.md` form instead of a bare `sdlc/skills/...` path that resolves only in the plugin repository; `lint_skill_paths.py` holds it (ledger IMP-206).

- No shipped runtime file (SKILL.md, references/, assets/) carries a ledger-id citation any more: bare `(IMP-NNN)` / `(LSN-NNN)` parentheticals are gone, history sentences keep their rule and their reason without the ticket, close-card examples show the `LSN-NNN` placeholder; `lint_context_budget.py` counts IMP- and LSN- ids with a ceiling of 0 per skill (ledger IMP-182).

## 1.19 (2026-09-17) — The channel rule is AUTHORING §18, Phase 7's fill-or-draft decision carries its errors inside the question, the resume recipe has four states and reconciles the counters, and `--set` edits one field without an interview

Ledger IMP-137: the print-then-ask channel rule (content a question depends on rides INSIDE the `AskUserQuestion` call — question text, an option's `description`, or an option's `preview` — because same-turn chat markdown may not render; markdown then a typed reply only when the turn ends with the markdown) lived only in this skill's importance-flows.md, where four other skills cited it by path and three never found it. It is now AUTHORING §18; importance-flows.md keeps the mechanics with a back-pointer, interview-mechanics.md's restatement collapsed to a citation, and the Phase-7 "fill or draft" prompt (merge-validate.md, SKILL.md, edge-cases.md) carries the field-level errors in the question or option descriptions instead of showing them and then asking. Pinned by `_smoke/channel_rule_selftest.py`: per site a positive token (`preview` / "inside the `AskUserQuestion`" / the turn ends) and a negative (no show-then-ask shape), plus §18 cited in every interview skill's references — red at 1.18 on all three sites and 8 of 8 skills. The retro's shorthand for the rule had inverted it; the red team caught the inversion before it shipped.

Ledger IMP-135 (row B05): `questions_inventory_selftest.py` arm (d) pins idea_text's empty `suggested_answers` and the three SKILL.md sentences IMP-067's fix depends on — prose that was correct and unpinned.

Ledger IMP-112 / IMP-173 / IMP-174 (canonical for every interview skill): edge-cases.md's "Resume with stale state" states the FOUR states up front — `in_progress`; `complete`/`aborted` with the artifact present (scope the update, then merge); `complete`/`aborted` with the artifact ABSENT (only `partial_answers` survives: restart-from-partial_answers or discard, never resume); no state file — and the migration recipe no longer freezes the theme lists in the step that reconciles them: migrate additively, reconcile the theme lists against the current inventory, re-derive every `last_ids` counter (monorepo: `last_ids_by_product`) as max(state counter, highest id on disk — the canonical file and every one of its shards), then offer resume at position 1. Every interview skill's Phase 1 collapses to the same five one-line bullets, and the five local restatements (ux/design/api edge-cases, data/api/task merge-validate) are pointers. Pinned by `_smoke/resume_recipe_lockstep_selftest.py`: section-scoped tokens per Phase-1 slice (`scop`; `partial_answers` + `discard` + `ABSENT`; `reconcil` + `last_ids`), the recipe's `max(` and fourth branch, the REFINE row's scoping mechanism — red at 1.18 on 36 assertions (four skills had no stale-state trigger in Phase 1 at all).

Ledger IMP-016: the Phase-1 update branch scopes a re-run before Phase 7's merge instead of re-walking every theme or inventing a scoping question — the mechanism is ux's upstream-reconciliation.md "Refine scoping" section (the themes or shard the user names, the §7 delta items, the non-confirmed set: open QUE, schema-added `null` fields, finding-named buckets, legacy plain-string ids through `migrate_ids.py`), everything else confirmed in one summary. prd is exempt from `--reconcile`, not from the scoping step.

Ledger IMP-018: a new "Invocation dispatch" section (every sibling skill had one) adds the prd-only `--set <schema_path>=<value>` rung — one scalar leaf or whole list, no question, on a `complete` PRD: parse the value as YAML, validate an in-memory copy through `validate_schema.py` BEFORE the real file moves, then write, set the `<field>_confidence` sibling to `confirmed`, require `--rationale` where a `<field>_rationale` sibling exists, and let `bump_artifact.py` write the changelog line. A list-item id inside a list-valued path stays out of scope until an id→schema_path index exists. Pinned by the same selftest's dispatch arm (validate precedes write); an end-to-end eval is deferred.

## 1.18 (2026-09-17) — A parked idea is no longer shaped like a live decision, the prose stops naming fields and options the validator does not have, and every template answer carries a `<…>` placeholder

Ledger IMP-007: `check_open_questions` flags a parking_lot item left at `status: open` (explicit or defaulted) or carrying a non-empty `blocks` list — a deferred-scope idea was structurally identical to a live, build-gating decision, and the file's own retrofit text told the update flow to write `status: open` into both lists. Blocking from prd_version 2.0 (the shared LEGACY_SHAPE_FLOOR, not a new floor), warning below; the retrofit message and docstring now name the status per list. Regression: `_smoke/25_parking_lot_open_at_floor.yaml` (exit 1) / `26_parking_lot_open_below_floor.yaml` (exit 0). Declined from the same item: per-bucket conventions headers — no downstream reader consumes a header sub-field.

Ledger IMP-008: four doc-versus-validator disagreements. The `product_vision` phantom (prose now says `product_identity.vision`, plus a generic WARNING whenever the file carries a top-level key the model does not declare — pinned by `_smoke/unknown_keys_selftest.py`); the monorepo Phase-4 prompt no longer offers a "shared at the root" option the validator refuses; the top_risks hint shows the typed `{statement, disposition, mitigation_refs}` shape; the WRN counter is documented as never per-product. The Phase-1 gap for an aborted/complete state with the artifact absent is cross-skill (IMP-173); counters frozen on resume are IMP-174.

Ledger IMP-139: `data_ownership` gains its `data_ownership_rationale` sibling in the schema and the validator (the lone outlier against seven correct capture_rationale fields); acceptance_criteria's suggested answers gain a template-marked `ACR-NNN: <FR-NNN> — <observable outcome>` option and performance_targets' template answers are normalised to the `<N>` placeholder — ONE convention, stated in CLAUDE.md's interview contract; interview-mechanics.md's Other-mapping rule and Why? follow-up now cross-reference each other so the two writers of `<field>_rationale` never race. Regression: `_smoke/questions_inventory_selftest.py` (arms a/b red at HEAD; arm c is a green-at-HEAD enum-membership guard).

## 1.17 (2026-09-16) — How a requirement item is SPELLED is part of the contract at last: checked on the writer side, and repairable on files already written

Ledger IMP-159, split out of IMP-007 and raised to blocker.

**A PRD could validate `complete` and still ship empty requirement text into every codegen worker packet.** Four consumers read requirement items, three of them off raw lines, and they disagreed about the physical spelling — while this schema declared only the *value* shape, so a wrapped, single-quoted or comment-tailed item parsed to the identical string and passed every check here. Measured on a fixture: of four items, the packet builder resolved **one**. The missing statements were then hashed as nothing into the context fingerprint, so the tasks built without them could never restale.

`check_item_line_shape()` is the writer-side half: a raw-line pass over the text `validate_file()` already reads, covering FR/NFR/WKF/ACR, skipping the `metadata`/`changelog` audit trail (a changelog legitimately quotes an item beside the requirement it used to belong to), and anchored on the `- ` opener so a retired-id entry and a `blocks:` reference are not mistaken for items. It shares `LEGACY_SHAPE_FLOOR` rather than adding a third number, and the version this schema stamps moves to **2.0** so that floor is actually reachable — a floor nothing reaches makes the blocking half dead code, which is most of why this went unseen. Every PRD already on disk carries a 1.x edit counter that `bump_artifact.py` moves 1.9 → 1.10, so none of them can cross it by being edited; they warn.

`migrate_ids.py --normalize-shape` (off by default, because this module's contract is that a correct item keeps its own quote style) rewrites the items of a file already written the other way. An item carrying a trailing comment is left strictly alone and reported: ruamel keeps the comment attached, so re-wrapping would still emit an unreadable line, and deleting it would destroy content nobody asked this tool to touch.

Pinned by `_smoke/23_item_shape_wrapped.yaml` (at the floor, expect 1 — it exited 0 before the fix), its below-floor twin `24_item_shape_below_floor.yaml`, and `_smoke/item_shape_selftest.py`, which compares this validator's pattern byte-for-byte against the one `code/topo_order.py` enforces, so the rule and its subject cannot drift apart. The canonical authoring example in `references/importance-flows.md` was itself a wrapped item that the pattern matched zero times; it is one line now, and says why.

## 1.16 (2026-09-16) — An eval stops rewarding the one thing this skill must not do, `metadata.changelog` is declared at last, and duplicate requirement ids are refused

Ledger IMP-111 (reopened) and two rows of IMP-007.

**The eval was scoring the contract backwards.** Case 1's expected output still said this skill creates CLAUDE.md with the pointer block, and its grader asserted that file exists — in a project where the installer had never run, and under a contract that says only the installer may write it. An obedient run therefore scored 7 of 8, and the reward went to the behaviour the contract forbids. IMP-111 fixed exactly this defect in case 7's grader; its recorded siblings enumerated graders 7 and 4 and missed this one, which is why the item is reopened rather than re-minted. Nothing sweeps the eval files, so the pin is the selftest: `_smoke/grade7_selftest.py` now runs the same three synthetic projects through graders 1 AND 7, and pins case 1's expected output too.

`metadata.changelog` was required by the cross-skill convention and read by the repair helper, but this schema never declared it and the validator never mentioned it. It is now declared and type-checked, matching the shape the sibling skills use.

Duplicate requirement ids validated clean, although the equivalent check already existed for two other id families in the same file. `check_duplicate_ids()` covers the four requirement families per scope, gated on the existing legacy floor per AUTHORING section 10. A sweep of all 33 PRD files in this repo found no duplicates and no scalar changelogs, so nothing turns red on upgrade.

Regressions: `_smoke/grade7_selftest.py` (red on the pre-fix graders) and fixtures `20_metadata_changelog_bad_type` and `21_duplicate_fr_ids` at the floor, with the below-floor twin `22_duplicate_fr_ids_below_floor`.

One line of IMP-116 also lands here: `migrate_ids.py` rewrites a PRD the consumer authored, so it now detects that file's line endings from its bytes and writes them back unchanged, rather than silently normalising them. It ships pinned by nothing — this skill has no selftest covering that script — which is recorded in the ledger rather than glossed.

**IMP-058: the acceptance-criteria backfill now scales, and stops presuming one criterion per feature.** Phase 7 drafted one criterion per uncovered feature and confirmed them four per call as one yes/no each, which on a PRD with around a hundred uncovered features is 25-plus round trips of rubber-stamping. Past roughly twenty features the PACING changes rather than the scope, which is the rule this skill's own caps section already states and which this one bulk confirmation never received: the drafts go into the run's existing partial-answers slot, the list prints whole as an operand, and only the entries where a judgement was actually made are confirmed. Below the threshold the old flow is unchanged. The count of criteria is now the feature's to set — none, one, or several — because the validator and schema never believed the one-to-one rule anyway: the coverage check counts features that no criterion names, and a real corpus of 108 criteria over 96 features passes clean. Added with it: a criterion may state only what its own requirement states. This item's ledger note had deferred it behind the update-flow work; that deferral was a myth, and the fix shipped with no file overlap at all. Regression: `_smoke/acr_backfill_selftest.py`, 8 of 10 assertions red before the fix, and it pins the threshold in the two files that own it so they cannot drift apart.

## 1.15 (2026-09-16) — The features list has no numeric ceiling, and nothing in this skill instructs a CLAUDE.md write

Ledger IMP-156 and IMP-111 (2026-09-15 retro cards B19-R2, B05-R7/B14-R1/B14-R2). `references/importance-flows.md` used to cap a critical list at 20 and route the rest to `open_questions.parking_lot`, two lines after saying a real product has as many FRs as it has - on a 101-feature PRD that turns in-scope requirements into deferred questions no coverage gate sees. The cap is gone; past ~20 items the PACING changes, not the scope. Separately, the Files table and `merge-validate.md` still told the agent to inject a CLAUDE.md pointer block (retired at 0.9.0), and eval 7's grader rewarded exactly that write: prompt, expected output and grader now assert the contract. Regressions: `_smoke/caps_selftest.py`, `_smoke/grade7_selftest.py` and `lint_claude_md.py`.

## 1.14 (2026-09-15) — The downstream-rejection rule names the accepted-deviance exception; `docs_index.py` calls run the copy `helper-resolution.md` picks

Ledger IMP-104, IMP-108 (2026-09-15 retro).

## 1.13 (2026-09-15) — `reporting-to-the-user.md`: a capped sample is for a verdict a person skims; an operand list a later step consumes is printed whole

Ledger IMP-097 (aicf LSN-078): the canonical reporting block every script copies caps
grouped ids at 12 "because a line nobody finishes reading has told the user nothing", and
nothing said when that cap is wrong. It is wrong for an operand - the item delta
`docs_index.py --drift` prints for a reconcile, the residue the user picks from, the
candidates an ambiguous symbol is qualified against - and two ids hidden behind a
`(+2 more)` needed edits nobody made. The "Volume" section now states the distinction;
`setup` 1.14 applies it.

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
