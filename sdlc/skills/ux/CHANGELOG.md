# ux — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

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
