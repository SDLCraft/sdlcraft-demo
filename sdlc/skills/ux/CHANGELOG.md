# ux — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.21 (2026-09-17) — The re-run delta review's consolidated summary rides inside the decision question, and the REFINE row scopes a re-run before the merge

Ledger IMP-137 (AUTHORING §18). upstream-reconciliation.md's Step 4 presented the consolidated summary and asked for the decision in the same turn — the seven skills that delegate their delta review here inherited it. The summary now rides in the decision question's text and option descriptions (or the turn ends with it and takes a typed reply), and the reference cites §18. Pinned by prd's `_smoke/channel_rule_selftest.py`.

Ledger IMP-016 / IMP-112 / IMP-173 / IMP-174: the REFINE row of upstream-reconciliation.md's three-meanings table pointed at the merge mechanics alone; it now links a "Refine scoping" section — open only the themes or shard the user names, the §7 delta items and the non-confirmed set (open QUE entries, schema-added `null` fields, finding-named buckets, legacy plain-string ids through the skill's id-migration helper), confirm the rest in one summary — and every interview skill's Phase-1 update branch points here before Phase 7. Phase 1 itself is the shared five-line trigger (four states — the ABSENT-artifact case offers restart-from-partial_answers or discard, never resume — plus the older-`skill_version` line pointing at prd's edge-cases.md recipe, which reconciles the theme lists and the `last_ids` counters before offering resume); edge-cases.md's stale-state restatement is a pointer to that recipe. Pinned by prd's `_smoke/resume_recipe_lockstep_selftest.py`.

## 1.20 (2026-09-17) — The CLI contract is typed and version-gated at a floor new writes actually stamp, and the shard inventory is reconciled with the files on disk

Ledger IMP-009: `layout.cli_args` and the new once-declared `cli.global_flags` are checked as `{name, kind, type, required, description}` mappings, and a cli_command surface's `exit_conditions` entries are typed `{code, when}` with each code cross-checked against `cli.exit_codes` — one writer of the fact, no third field. All blocking from `ux_version` 3.0, warnings below. Two red-team findings shaped it: the skill had NO write-time stamp rule (schema example "1.1", corpus at 1.21), so the existing 2.0 floor was already dead code — merge-validate.md now says new writes stamp 3.0 (or higher) and the schema example does; and a `global_flags` key nobody asks for is a zero-producer field, so ux-questions.yaml gains the producer question. task's second hand-kept CLI field tuple became the imported `CLI_FIELDS` (one copy). Regression: `_smoke/24_typed_cli_contract/` (exit 1) / `25_…_below_floor/` (exit 0). The exit-code existence sub-check is verified by hand but not smoke-pinned: a typed entry failed pydantic at HEAD, so no fixture can flip on it. The consumer of `global_flags` (joined live into worker packets) is IMP-172.

Ledger IMP-171: `surface_inventory` and the on-disk `UX__*.yaml` set are two writers of one set and are now reconciled, mirroring arch's `check_file_path_integrity` and its resolution order — a ghost inventory `file_path` and an orphan shard both block at 3.0, warn below, and the check is vacuous on an empty inventory or a `not_applicable` artifact. Regression: `_smoke/26_inventory_shard_mismatch/` (exit 1) / `27_…_below_floor/` (exit 0).

## 1.19 (2026-09-16) — An FR naming a command is examined whether it is deferred or traced, so a trace from an unrelated surface no longer silences the clause

Ledger IMP-136.

`check_deferred_fr_names_command` skipped every FR already in the covered set before it read the requirement text, so an FR whose text names `<root> <verb>` was examined only while it was deferred. A trace from a surface that is not that command, or from a bare `cli.exit_codes` entry that carries no invocation at all, silenced the clause and nothing downstream built the command. Both halves were reported separately; they are one predicate, and shipping two exemptions would have let them drift.

The check is now `check_fr_names_unbuilt_command` — the old name asserted the defect — and it examines every such FR, traced or deferred, exempting it only when a lookalike surface **also traces that FR**. The slug match stays containment rather than equality, deliberately: the eval grader accepts any surface id containing the verb, so an exact match would let a graded-pass run trip the very warning the same grader asserts is absent. The trace is the strict half; the slug shape never was the signal. The deferred sentence is byte-identical, so the existing fixture's pins are untouched, and the new traced sentence names its tracers.

The three prose sites that stated the deferral-only rule moved in the same pass, or the canonical reconciliation step would now contradict the validator.

Regression: `_smoke/23_traced_fr_names_command/` with new sections in `_smoke/deferral_selftest.py` that assert the remedy **wording**, not merely that a row appears — a section added to a selftest whose assertions all pass can otherwise silently no-op if the predicate is wired wrong.

## 1.18 (2026-09-16) — A stale upstream routes NEXT to `/sdlc:ux --reconcile`, and the Phase 8 pointer-write prose is gone

Ledger IMP-127 and IMP-111. The validator warned "built against an older docs/PRD.yaml - run /sdlc:ux to review the delta" and printed `NEXT: /sdlc:design` in the same run, so an agent following the NEXT line skipped the review and design built on a stale UX. NEXT now names the reconcile form with the successor on the second line. `merge-validate.md` no longer says a draft still injects a pointer or that the close waits on a CLAUDE.md write. Regression: `_smoke/deferral_selftest.py` (fixture 14).

## 1.17 (2026-09-15) — `upstream-reconciliation.md` step 4 takes `--drift`'s `[referenced here]` / `[cited in prose xN]` marks as the "only items this file traces or covers" filter, and step 6 covers the `re-stamp only` verdict

Ledger IMP-147 (aicf LSN-084): the canonical step 4 prescribed a filter the
helper never computed, so every consumer re-derived it by hand and a prose
cite was invisible to it. Path: `references/upstream-reconciliation.md`
(steps 4 and 6). Pinned by setup's `_smoke/index_selftest.py` section 12d.

## 1.16 (2026-09-15) — Phase 2's validator stop honours accepted deviance (`doctor.py --artifact`); a typed deferral with a malformed WRN id warns; `docs_index.py` calls run the copy `helper-resolution.md` picks

Ledger IMP-104, IMP-108, IMP-109 (2026-09-15 retro). The `metadata.status` stop stays unconditional.

## 1.15 (2026-09-15) — `upstream-reconciliation.md`: a delegating upstream item goes through the discovery step and a void delegation becomes a finding, never "the upstream is wrong"; a resolved finding the delta cites leads its card as the decision; Phase 7 stamps through the helper

Ledger IMP-100 (aicf LSN-081): Step 4 read a changed-in-body item as a contradiction or an
assignment; an item that delegates a decision here ("until DATA-MODEL describes it") was
carded as an assignment, the element presumed necessary, "the upstream is wrong" offered
beside define/remove. A delegation now routes like an added item - the skill's discovery step
first - and when it names no candidate the delegation is void: a finding for repair
(`finding_notes`), nothing authored; the state enum gains `delegation_void`. Ledger IMP-101
(aicf LSN-082): step 3 also collects the `FND-NNN` ids the `--drift` `why` lines and changed
items cite, reads them with `findings.py list --id`, and a resolved finding's resolution leads
the card as position 1 with basis measured - never re-offering "record a finding" for an item
a finding decided. Ledger IMP-102: Phase 7 stamps `UX.yaml` through `docs_index.py --stamp`
instead of a hand-written sha-only entry. Regressions: eval cases 4 (reconcile-delegated-item)
and 5 (reconcile-decided-finding).

## 1.14 (2026-09-12) — `upstream-reconciliation.md`: the no-items fallback tries git first, and a handoff note quantifying over an enumeration is verified against that enumeration whatever its basis

Ledger IMP-083 (aicf LSN-065): the helper-absent bullet and the name-addressed
backlog rule now say `--drift` diffs a sha-only stamp against the committed revision
whose text hash matches ("recovered from git") and that only an uncommitted stamp
leaves the residue; the ban on recovering from git is gone (the helper does it).

Ledger IMP-085 (aicf LSN-067): step 5 - a note or arm that quantifies over an
upstream enumeration is seeded by reading that enumeration from the artifact it
names, whatever the note's `basis`, and the close card prints seeded-vs-enumerated.

## 1.13 (2026-09-12) — `upstream-reconciliation.md`: a handoff note's `basis` (measured | inferred) decides whether the reconcile card offers it as read or verifies it against the cited artifact first

Ledger IMP-082 (aicf LSN-064): a repair handoff note carried no register, so a
cold reconcile offered an analogical siting recommendation as a verified fact -
it was wrong against the very artifacts the note cited. The canonical step 3 now
reads the note's `basis`: `measured` is offered as read, `inferred` (or unstated)
is verified against the cited artifact first, and the card says what was checked.

## 1.12 (2026-09-11) — `/sdlc:ux --reconcile` runs the upstream-change review alone, and `upstream-reconciliation.md` holds the canonical reconcile form every consumer skill shares

Until now only `test` and `task` had a `--reconcile` flag, so a repair that
changed the PRD, UX, DATA-MODEL, API or ARCH had no scoped command to hand
out: the plain re-run ran the same §7 review and then fell into the full
interview. `references/upstream-reconciliation.md` gains "The `--reconcile`
form" — capture the `--drift` delta before any write (the IMP-051 rule,
generalized), read what repair handed off (`findings.py list --owed-by`: the
finding's `fix` and `handoff` notes, quoted up front; a note keyed to a delta
item becomes its position-1 proposal), one card per class of change, a scoped
per-item drill for what is incorporated, and a `Next:` taken from
`docs_index.py --stale`, so the chain after a repair walks itself — plus a
per-skill specifics table. SKILL.md gains an `Invocation dispatch` section (it
had none), and the input-adequacy gate stops asking about a finding that is
waiting on this very run (it used to send the reconcile back to repair).

## 1.11 (2026-09-10) — an ADDED FR goes through surface-discovery 1b before its delta-review decision, and a deferred FR whose text names a command is reported

`upstream-reconciliation.md` Step 4 now states the rule every consumer skill
inherits: an added item is run through the skill's own discovery step before
the incorporate / ignore / defer prompt, the candidate it yields is position
1, and a whole-item deferral of an item whose text names a command needs a
reason naming that command. `surface-discovery.md` 1b says it re-runs on
re-runs and that an FR is read whole (content clause + command clause).
`validate_schema.py` adds the warn-only `[FR names a command]` check: a
deferred FR whose PRD text names `<cli.root_command> <verb>` in backticks is
reported with the surface that already looks like it, when one exists. SKILL.md's
helper-absent branch runs the plugin's copy of `docs_index.py` instead of a
hand hash. Ledger IMP-076 (aicf LSN-056); regression fixture 22 +
`_smoke/deferral_selftest.py` + eval case 2.

## 1.10 (2026-09-10) — `upstream-reconciliation.md`: provenance is stamped with per-item hashes, and an artifact's references are not a snapshot

The canonical reconciliation reference (which every consumer skill cites)
now has Step 1 write `metadata.upstream_provenance` through `docs_index.py
--stamp`, which records an `items` map (every upstream item → body hash)
beside the sha256; Step 2/3 take `--drift`'s item-by-item added / removed /
changed-in-body lists as the delta; and the name-addressed section retracts
"the artifact's own references are the old snapshot" - that shortcut is
exact only where a blocking trace-or-defer gate holds, and elsewhere the
residue mixes new-since-last-write with never-covered and must be printed as
a backlog line, never as the delta (IMP-073, aicf LSN-051/053). A project
with its own index generator runs the plugin's copy of the helper; git
recovery of an old upstream is ruled out. No `ux` behaviour changed.

## 1.9 (2026-09-09) — FR coverage counts `cli.exit_codes[].implements_requirements`

`check_fr_coverage` unions the exit-code traces from the root and every
product scope, as UX.schema.yaml always said it did - for a CLI an exit
code is how a gate requirement reaches the user. Ledger IMP-046 (aicf
LSN-020); regression fixture 21 + `_smoke/deferral_selftest.py`.

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

## 1.6 (2026-09-01) — Findings + drift wiring (CLAUDE.md 13/7)

Findings + drift wiring (CLAUDE.md 13/7): Phase 2 gains the input-adequacy gate
(open findings + blocking PRD QUEs, one ask), `docs_index.py --drift` decides
refine-vs-reconcile, and the stale-ref / downstream-claim prompts gain "the
upstream is wrong - record a finding for /sdlc:repair" (noted to
`state.finding_notes`, never interrupting the run); Phase 8 drains the notes
through `findings.py add` and auto-raises `upstream_incomplete` for
REQUIRED-but-null PRD fields. Validator: the FR-coverage warning reads the
structured top-level `deferrals: [{id, reason}]` first (ux_warnings prose
mention deprecated - honoured one more version, reported), a
provenance-staleness warning (built against an older upstream; complete with no
snapshot at ux_version >= 2.0), and an absent PRD is named instead of boasting
"all 0 workflow(s) covered". State gains `finding_notes`, `input_adequacy`,
`delta_review`, `dropped_candidates`. Regressions:
`_smoke/13_structured_deferral`, `_smoke/14_provenance_behind`,
`_smoke/deferral_selftest.py`.

## 1.5 (2026-09-01) — PRD 1.1 propagation: surface family derived list-aware over all nine platforms

PRD 1.1 propagation: surface family derived list-aware over all nine families
(two or more → mixed); `localisation.*` pre-filled from
PRD.internationalization; `glossary.terms` read for labels/copy. Also:
`set_claude_md_pointer.py` keeps the consumer CLAUDE.md's own line endings (LF
or CRLF) on every write — it used to rewrite the whole file in the host's
newline on a timestamp-only update (ledger IMP-006, aicf/LSN-002; regression
sdlc/skills/task/_smoke/pointer_selftest.py runs every skill's copy).

## 1.4 (2026-09-01) — Self-review pointer de-drifted

self-review pointer de-drifted (the canonical questions live in
lessons-capture.md, no longer counted here) + `lesson_notes` drain wired at
close (CLAUDE.md 15, ledger IMP-002); the per-surface announce recap is no
longer a same-turn banner (channel rule, ledger IMP-005).

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
