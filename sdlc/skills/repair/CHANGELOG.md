# repair — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.12 (2026-09-15) — Surgical step 5 stamps only a pair the Phase 2 snapshot showed fresh; a pre-existing stale pair is named on the close card and routed to its own reconcile, never stamped; `findings.py list --id` reads a finding a reconcile's delta cites

Ledger IMP-099 (aicf LSN-080): a stamp claims that every delta between the recorded upstream
and the current one was reviewed, and a repair reviews one finding's change. Step 5 (IMP-088)
said to stamp every hand-reconciled artifact and Phase 5 called a leftover `--stale` row a
missed stamp, so a pair that already owed an unreviewed reconcile was either forged or
mislabelled. Phase 2's `doctor.py --provenance --json` is now named the pre-run stale
snapshot; step 5 stamps only pairs absent from it and names a listed pair on the close card
with its owed reconcile in `Next:`; step 7 and the Phase 5 line read such a row as that
reconcile. `forward-propagation.md` states the principle once ("What a stamp claims").
Ledger IMP-101 (aicf LSN-082): `findings.py list --id FND-NNN` (repeatable) - what a
`--reconcile` run reads when an upstream changelog line cites a finding
(`_smoke/findings_selftest.py`). Regression for IMP-099: eval case 14
(`fixtures/case14_prestale_pair`).

## 1.11 (2026-09-12) — `doctor.py --artifact` runs one validator with the accepted-deviance registry applied; handoff notes carry `basis` (measured | inferred); the surgical sequence stamps hand-reconciled artifacts upstream-first BEFORE the re-slice and sweeps the corpus for a retired token

Ledger IMP-081 (aicf LSN-062 + LSN-063): the IMP-052 accepted-deviance clause
told test/task to consult `doctor.py --quick`, which runs only the cross-artifact
linter and reports nothing about a per-artifact validator; `--artifact FILE`
(repeatable) runs that one validator with the registry applied and answers
accepted-or-red (`_smoke/doctor_selftest.py`). IMP-082 (aicf LSN-064): a
`resolution.handoff` note was one string in one register, so a cold reconcile
took an analogical siting as a verified fact; every note now carries `basis:
measured | inferred` (warn-only when absent; `findings.py list --owed-by`
prints it; `_smoke/findings_selftest.py`). IMP-088 (aicf LSN-070 + LSN-073):
the surgical sequence never re-stamped the artifacts a run reconciled by hand,
and a stamp issued after the re-slice put the shard behind again for a
metadata-only write; steps 4-6 are now walk-by-hand, stamp upstream-first,
re-slice LAST, and `--stale` joins the verification block (eval case 12).
IMP-091 (aicf LSN-074): a fix that retires a named token had no sweep - the
reference graph cannot see sites that use a name that no longer exists; Phase 2
and step 4 grep the corpus for it and close every hit (eval case 13).

## 1.10 (2026-09-11) — Free edition: the surgical steps and Phase-5 lines that call `task`, `code` and `test` scripts are skipped, and said so, when those skills do not ship

The public free build ships setup through arch plus repair and lesson. A free
install has no task graph to re-slice or schedule, so surgical steps 3 and 7
(forward-propagation steps 4 and 7) and the test/task verification lines are
skipped with a note. A project still holding `docs/TASKS*.json` from an
earlier Pro install gets the owed re-slice named in `Attention:`, never a hand
edit. `doctor.py` already skipped the task linter when it was absent.

## 1.9 (2026-09-11) — A re-invoke leaves the walk's reasoning on disk (`resolution.handoff`) and prints every stage's `--reconcile`; the chain routes itself and returns to `/sdlc:repair FND-NNN` to close; `doctor.py` writes its default queue into the project that holds `--docs-dir`; a TASKS bump is a patch bump; a re-invoke's command sequence starts below the source

**A re-invoke starts below the source.** An eval run localized a missing
store-read unit to `ARCH__demo-api.yaml`, recorded only a warning there, and
routed the chain to `/sdlc:arch demo-api --reconcile` — copying Phase 4's
example, which began at arch. A reconcile reviews what moved upstream of its
artifact, so pointed at the file just localized it finds no delta and the
chain stalls at its first hop. Phase 4 now says the located artifact is always
edited in the run (a modelling choice inside it — which component owns a new
unit, its name — is a Phase 3 question), the printed sequence starts at the
first stage below the source, and the example names the file it is rooted in.

**doctor's queue path.** `--emit-findings` without a PATH resolved
`.claude/skills-state/sdlc-findings.yaml` against the working directory, so an
absolute `--docs-dir` run from anywhere else wrote the queue there — two eval
runners put one into the plugin tree. The default now resolves against the
parent of `--docs-dir`; an explicit PATH keeps its command-line meaning, and
the "written to" line names the project-relative path. `findings.py add`
redraws the statusboard of the queue's project, not the cwd's. Regression:
`doctor_selftest.py` sweeps from a foreign cwd.

**TASKS bumps are patch bumps.** Surgical step 2 and forward-propagation step
2 pass `bump_artifact.py --patch` for a TASKS file: its minor version gates
task checks (check 18 from 1.4), and a minor bump turned a green 1.3 graph red
in the 0.9.10 eval. The case4 eval fixture's PRD, ARCH.yaml and TEST-STRATEGY
files now validate, so a sweep over it reports only the planted defect.

Decided with the user 2026-09-11: repair keeps its boundary and never runs
another skill. Running the downstream reconciles inline was weighed and
rejected — those skills are not model-invocable, their state files and run
records would lose attribution, and a PRD-rooted chain can fan out past one
context window. What a fresh session lacked was the walk's reasoning, so that
now travels on disk: `resolution.handoff: [{artifact, key, note}]`
(FINDINGS.schema.yaml; validate_findings.py warns — never blocks — on a
non-re-invoke mode, a malformed entry, or a note addressed to a file nothing
owes). `findings.py` owns `SKILL_ARTIFACT` / `rerun_artifacts` /
`owed_artifacts` / `awaiting_registry` (moved from doctor.py, which aliases
them) and gains `list --owed-by docs/<file>`, which every `--reconcile` reads.
Re-invoke prints each stage's `--reconcile`, container-scoped; `Next:` is the
first command; the `FND-NNN` form closes a chain-end finding through
`doctor.py --provenance`'s `can be marked resolved` hint. Regression:
`_smoke/18_handoff.yaml`, `findings_selftest.py` (`--owed-by`, handoff
warnings).

## 1.8 (2026-09-10) — `doctor.py` matches accepted deviance by artifact file name and mints repo-relative paths, so a wontfix finding is honoured under `--docs-dir docs` and an absolute `--docs-dir` alike

The accepted-deviance registry keyed on `(detected_by, surfaced_at.file)` as
written and looked up `(check, target)` as invoked, so one wontfix
`expected_count` finding was honoured under `--docs-dir docs` and ignored
under an absolute path in the same session; findings the doctor minted under
the absolute form carried absolute `surfaced_at.file` / `suspected_source`
values a relative run could never accept. Both registries (accepted and
awaiting) now key on `artifact_key()` — the file name, unique within a docs
dir — and every minted entry's path goes through `project_relative()`
(repo-relative POSIX, resolved against the cwd then the docs dir's parent).
Regression: `_smoke/doctor_selftest.py` — a finding recorded as
`docs/PRD.yaml` is honoured for a check on an absolute, backslashed or
`../` target and vice versa; an absolute `--docs-dir` sweep reports the same
`failed` count as the relative one and mints only relative paths (ledger
IMP-078, aicf LSN-059).

## 1.7 (2026-09-10) — `doctor.py` labels a failure on an artifact an open re-invoke finding still owes as `awaiting re-invocation per FND-NNN` and never records it again

A re-invoke finding whose `downstream_rerun` has not run yet leaves its
downstream artifact red on every sweep in between, with a first defect line
that moves as the chain advances — so the summary-keyed dedupe never matched
and each sweep minted the known failure afresh (aicf FND-080 -> FND-085). The
doctor now reads the open|triaged re-invoke findings' owed artifacts (the
files their `downstream_rerun` commands rewrite, plus the targets of
propagation hops with no `verified_at`), labels a failing check on one of
them with the finding and its owed command, keeps the check red, records
nothing for it (`findings_awaiting` in `--json`), and when every failure is
owed prints the owed command as `NEXT:` instead of `/sdlc:repair`. Phase 2
says what to do with such a row. Ledger IMP-077 (aicf LSN-058);
`_smoke/doctor_selftest.py` (both channels, the verified-hop negative, the
text report).

## 1.6 (2026-09-10) — Third fix mode `additive`: a fully-determined new downstream item is authored in-run, never routed to re-invoke

Phase 3 offers *fix fully — author the new item(s) here* at position 1 when
the four-part criterion holds (purely additive, fully determined by the walk,
validator-provable, obligation chain closed in this run); Phase 4 states the
criterion and mechanics (`bump_artifact.py` every touched artifact, a new
task's embed copied from the source and proven by `reslice_embeds.py
--check`, `downstream_rerun: []`); a split finding is fixed half by half. The
findings schema and `validate_findings.py` gain `mode: additive` (v2: an
additive resolution that owes a re-run or records no downstream hop is
refused). Ledger IMP-060 (aicf LSN-019 + LSN-040); fixtures 16/17 + eval 11.

## 1.5 (2026-09-10) — `doctor.py` labels a FAIL row with the path the check ran on; the defect's file is a separate field

A validator that sweeps every sibling shard reports one shared error from
every invocation; relabelling each row with the file that error named printed
the same shard failing three times while the shards that actually ran
vanished. The row keeps its target, `located` (also in `--json`) names the
first defect's file, and the WHAT FAILED summary says both. Ledger IMP-069
(aicf LSN-047); `_smoke/doctor_selftest.py`.

## 1.4 (2026-09-09) — Phase 5 never regenerates a project-owned index; the doctor's fallback label says why; `hop: downstream`; Phase 6 states the queue's rules

Phase 5's regenerate line runs only through the project's installed
`docs_index.py` - absent means skip and say so, never the plugin's copy
(one project lost a 3000-line project-owned index); `doctor.py` derives the
read-only fallback's label from what is installed and names a
project-owned generator (IMP-043, aicf LSN-022/033/044; doctor_selftest +
evals case 8). FINDINGS `propagation.hop` gains `downstream` (IMP-047,
LSN-027; fixture 15). Phase 6 states the hop enum and the
duplicate_of/resolution compatibility rules (IMP-032, LSN-012; evals case
9) and never closes a re-invoke finding `resolved` with an empty
`downstream_rerun` at any queue version, counting it on the close card and
bumping a clean version-1 queue to 2 (IMP-054, LSN-045; evals case 10).

## 1.3 (2026-09-04) — `migrate_warnings.py` takes `--by <skill>`

`migrate_warnings.py` takes `--by <skill>`, so a conversion run by another
skill no longer credits `sdlc-repair` in that artifact's changelog; pair it
with `--no-bump` when the caller writes its own line. `located_stage` accepts
`brief` for a defect that lived in a hand-written upstream brief rather than in
any skill-authored artifact. Ledger IMP-030/IMP-031; regression
`_smoke/migrate_selftest.py` + `_smoke/14_brief_stage.yaml`.

## 1.2 (2026-09-02) — Never writes `CLAUDE.md` (it belongs to `/sdlc:setup`)

Never writes `CLAUDE.md` (it belongs to `/sdlc:setup`); ships `warning_item.py`
(the canonical typed-`WRN` parser every validator embeds) and
`migrate_warnings.py` (opt-in conversion of legacy warning strings); a `kind:
deferral` warning's `defers:` is now a structured coverage channel, and the
prose word-match is off at artifact version >= 2.0 (DATA-MODEL >= 3.0).

## 1.1 (2026-09-01) — Findings from every stage, plus a scripted surgical mode

Findings from every stage (`findings.py`, queue version 2, `--flag` intake);
scripted surgical mode (`bump_artifact.py` + `reslice_embeds.py`); blast-radius
checklist; doctor warning channel, accepted deviance and `--provenance`;
`--check --no-emit`; propagation hops; test-before-task re-invoke order; state
gains `baseline_checks` / `provenance_drift` / `lesson_notes`; EXIT records the
run.

## 1.0 — Initial

Initial.
