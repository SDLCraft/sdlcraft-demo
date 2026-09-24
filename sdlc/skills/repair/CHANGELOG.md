# repair — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.24 (2026-09-24) — The helper-resolution clause covers every `.claude/sdlc/<helper>.py` the file runs, not `docs_index.py` alone

- `SKILL.md` (ledger IMP-218): the Phase-2 helper bullet reads "every `python .claude/sdlc/<helper>.py …` in this file (`docs_index.py` and the close-phase helpers alike) runs the copy `helper-resolution.md` picks once per run", so a lagging install runs the plugin's `statusboard.py`, `lessons.py` and `autocommit.py` at the close too - a run on a 0.9.16 install had drawn the old statusboard and would have stamped no verdicts. Pinned by `setup/_smoke/helper_resolution_selftest.py` arm 4.

## 1.23 (2026-09-22) — No shipped repair file cites a Pro-only skill by path, every guarded call is marked on its own line, and the edition boundary is a release gate

- `references/orchestration.md` (new in 1.22) and `references/forward-propagation.md` each named a `code` skill reference by path as a "why" citation. In the demo edition no `code` skill exists, so `release_build.py` refused the free build - after every gate had passed and both editions were built. Both citations now name the mechanism in words: a citation nothing executes carries no path (AUTHORING 17).
- Every command that reaches into `test`, `task` or `code` (SKILL.md Phase 4 steps 6 and 8 and the Phase 5 block; `forward-propagation.md` steps 6 and 8 and its verify block; `doctor.py`'s task-validator and crosscheck lookups) carries `edition-ok: <where the skip lives>` on its own line. The per-FILE `GUARDED` allowlist in `release_build.py` is gone: a new Pro-only reference in one of those files is refused unless the line itself is guarded, and a bare marker with nothing after the colon does not count.
- The check is a gate. The new repo-root `lint_editions.py` runs `release_build.edition_reference_problems` (one shared function, every spelling: `${CLAUDE_SKILL_DIR}/../`, bare `../` and `../../`, `SKILLS_DIR / "<skill>"`) on the source tree, listed in `GATES` and CLAUDE.md's Commands block, pinned by `lint_selftest.py`.

## 1.22 (2026-09-22) — A run works EVERY open finding: opus workers localize them in parallel, one plan gate orders the whole queue upstream-first into artifact aggregates, workers fix per aggregate, handoffs print once at close, and the card names what it did not reach

- The open set (every `open` + every `triaged` finding) is asserted in Phase 2 with `findings.py list --open` and re-asserted at every stage-wave drain; a run ends when nothing in it can still be worked, never at the first re-invoke handoff ("stop and print the exact downstream command sequence" is gone - a re-invoke records its commands in the worker's report and the session prints ONE consolidated chain at close). Already-rebuilt re-invoke findings (the doctor's `can be marked resolved` hints) close first.
- Two waves of workers (frontmatter gains `Agent`; both `model: "opus"`, five in flight, rolling, briefs carry paths): wave 1 localizes every finding read-only into `.claude/skills-state/sdlc-repair/localize/<FND>.yaml` (walk, mode, the four-part criterion, the ONE missing decision, the write set); wave 2 fixes per **aggregate** - the write sets that share an artifact, union-find, directory-aware, capped at five - inside a write boundary, serially per finding (the stamp discipline holds; `never interleave` is scoped inside an aggregate), with breadcrumbs (`inflight/`) and reports (`reports/`). Relocation and blocked protocols; inline fallback without the Agent tool. Mechanics in the new `references/orchestration.md`.
- Phase 3 is ONE plan gate: `findings.py plan --from <localize dir> --doctor-json <snapshot> --json` (new subcommand; provisional from queue fields without `--from`) builds aggregates and stage-waves ordered by the pipeline stage of the located artifact, upstream first, an aggregate downstream of another's write set waiting even when disjoint; the AskUserQuestion carries the whole table in the recommended option's preview with an extent ladder (all / first wave / first aggregate) and one question per missing decision, so a would-be re-invoke whose only gap is a decision this run can take is authored additively.
- Phase 5 gains the drain: per stage-wave, `doctor.py --quick` + `validate_findings.py`, and the session re-stamps every `re-stamp only` row (with holds) - a re-stamp-only hop is repair's, never a reconcile's.
- Phase 6 writes resolutions from the reports, never from memory; the card gains `Remaining:` (open findings not worked, with why), `Handoffs:` (count + first command of the consolidated chain) and `Workers:`; `Status:` rule 2 is "open findings were left unworked -> not finished", rule 4 requires every OPEN finding (not every finding WORKED) closed, parked or handed off; `Next:` routes an unworked open finding to `/sdlc:repair FND-…` BEFORE any owed re-run command.
- SKILL.md 847 -> 825 lines (ceiling lowered): the blast-radius checklist, token sweep and symbol-class table moved to `back-propagation.md` Step 3½ with the "At a glance" table; the resolution-write rules, the re-invoke chain example and the measured/inferred registers to `forward-propagation.md`; the sweep's labels and the regenerate rule to `edge-cases.md`.
- Pinned by `_smoke/orchestration_selftest.py` (registered), `_smoke/findings_selftest.py` (plan arms) and `evals/evals.json` case 16 (`evals/fixtures/case16_full_queue`).

## 1.21 (2026-09-20) — Phase 6 records the run before the card and commits the run when the project opted in (auto-commit, CLAUDE.md 20)

- `Record the run` and `status: complete` now precede `Close with the report` (the card's `Lessons:` row used to be printed before the lessons were recorded), followed by the new close step `python .claude/sdlc/autocommit.py commit --skill repair …` (mechanics in `setup/references/auto-commit.md`) and a `Commit:` row on the card; `--check` runs commit only what they emitted. Pinned by `setup/_smoke/autocommit_lockstep_selftest.py`.

## 1.20 (2026-09-19) — The doctor sets the child's UTF-8 env and never mints a tool crash as a finding, the reopen hint checks the finding's own touched family, and re-invoke resolutions gate artifacts_touched at findings_file_version 3

- `doctor.py` `run_bare` sets `PYTHONUTF8`/`PYTHONIOENCODING` in the CHILD's env (a validator printing a non-cp1252 character crashed instead of finishing); a check whose output carries a raw Python traceback is a tool crash - no finding minted, the check stays FAILED (exit 1, `--quick` red) and prints its own detail line under WHAT FAILED; `fallback_lines` no longer stays in the WARNINGS section forever after one WARNINGS header. Pinned by `_smoke/doctor_selftest.py` (ledger IMP-190).
- `doctor.py` `--provenance`'s "should be reopened" hint fires only when the drifted upstream's FAMILY (a shard and its system file count as one) is named in the resolved finding's own `resolution.artifacts_touched`; an empty `artifacts_touched` (legacy) keeps today's unfiltered hint silently. Unrelated drift no longer held under a closed finding mints its own finding on `--emit-findings` (`DEDUPE_STATUSES` excludes `resolved` on purpose). `validate_findings.py` gains a higher-floored check (`findings_file_version` 3): a re-invoke resolution with an empty `artifacts_touched` warns below the floor and errors at it - fixtures 21/22 (ledger IMP-195).
- `references/forward-propagation.md`'s surgical command list names `reslice_embeds.py --component <cid>/<component>` for a component-scoped test task (ledger IMP-197).

- `resolution.handoff[]` gains an optional `retired: [<token>, ...]` - the literal token(s) a fix removed or renamed, instead of an authored guess at which downstream items carry it; `validate_findings.py` warns on a malformed value and on a handoff note that enumerates two or more foreign TST-/TSK- ids with retirement wording and no `retired` list; `findings.py list --owed-by` carries it in text and `--json`; the writer rule sits in `forward-propagation.md` and Phase 6 (ledger IMP-193).
- `resolution.sites_considered` (one entry per artifact the forward-propagation checklist named: `{artifact, disposition: edited|resliced|unaffected|deferred, reason, how}`) persists the checklist; REQUIRED non-empty at `findings_file_version` 3 whenever `symbols_changed` is non-empty or `mode` is `re-invoke` (a surgical fix touching no symbol is exempt). The Token sweep fires on an ADDED field too. New `findings.py validate --upgrade` raises an existing queue to the current file version only when every gated check passes with zero warnings, and Phase 6 runs it - until now the floor was per file and nothing ever raised one. Fixtures 23/24 + `findings_selftest.py` (ledger IMP-196).

- Every cross-skill reference pointer in SKILL.md and references/ now uses the consumer-safe `${CLAUDE_SKILL_DIR}/../<skill>/references/<file>.md` form instead of a bare `sdlc/skills/...` path that resolves only in the plugin repository; `lint_skill_paths.py` holds it (ledger IMP-206).

- No shipped runtime file (SKILL.md, references/, assets/) carries a ledger-id citation any more: bare `(IMP-NNN)` / `(LSN-NNN)` parentheticals are gone, history sentences keep their rule and their reason without the ticket, close-card examples show the `LSN-NNN` placeholder; `lint_context_budget.py` counts IMP- and LSN- ids with a ceiling of 0 per skill (ledger IMP-182).

## 1.19 (2026-09-17) — A resolved finding can be reopened when its downstream never rebuilt, and a wontfix code-defect closure names the task to rebuild

Ledger IMP-158: `findings.py reopen FND-NNN` — mode-aware: a re-invoke finding returns to `triaged` with its resolution and recorded `downstream_rerun` kept; a surgical or additive one returns to `open` with the resolution stripped and `artifacts_touched` folded into an evidence line; the write is validated first. `doctor.py --provenance` gains a "should be reopened" hint (JSON key `reopenable`) for a RESOLVED re-invoke finding whose owed artifact is stale by the existing `docs_index --stale` comparison — worded as staleness, never as a cause — and merges that resolved-but-stale set into `emit_findings`' owed registry before its loop, so the failing check is HELD and the reopen hint is the only channel (it would otherwise have minted a second finding with no handoff). Regressions: `doctor_selftest.py` `resolved_reopen_tests` (a sharded reconcile command) and a `findings_selftest.py` reopen section, red at 1.18.

Ledger IMP-063 (repair half; code's `stale_task_findings()` join is in code 0.24): `resolution.located_stage: code` is ALLOWED on `status: wontfix` only — the closure where that value is honest — and a wontfix with `located_stage: code` and an empty `stale_tasks` WARNS (the closer forgot the task). back-propagation.md's "never localize to code" absolute gained its qualifier (walk the owner table first; only when every upstream contract states the fact correctly and the code alone diverges is the finding mis-raised) and SKILL.md Phases 2/3 say to name the owning task in `stale_tasks` — the channel code's plan gate reads. Fixtures `_smoke/19_wontfix_code_stale_tasks.yaml` (validates) and `20_wontfix_code_missing_stale_tasks.yaml` (warns). A status-agnostic join was rejected: an OPEN finding's stale_tasks is a plan for a spec nobody fixed yet.

## 1.18 (2026-09-17) — Localizing a lone dangling reference to a retired id now names both outcomes and the durable retired-id channel `--check` offers

Ledger IMP-177 (split from IMP-160's dossier). back-propagation.md's Step 3 said a single dangling reference to a legitimately retired id always means the referencing artifact holds a stale copy, while docs_index.py keeps a durable channel — `docs/INDEX.allow.yaml` `retired_ids` or the PRD's `metadata.retired_ids` — for a citation that is deliberate and is listed as "cited without a definition on purpose". The paragraph now names both outcomes, says the retiring changelog entry decides between them, and points at the channel. Pinned by a prose arm in `_smoke/doctor_selftest.py` (the two literal tokens, red at 1.17).

## 1.17 (2026-09-16) — Phase 6 stops prescribing closes this skill's own queue validator rejects, and the doctor blames the file the defect is actually in

Ledger IMP-131 and IMP-130, plus the doctor half of IMP-118.

**The section headed "write it right the first time" was the source of the rejected writes.** Phase 6 told the agent to park a surgical fix with an unverifiable hop as `triaged` with a resolution block — which the queue validator appends to `errors`, so it blocks at every queue version — and to leave a re-invoke `triaged` with an empty downstream list, which v2 refuses. A finding in that state now stays `open`, and partial surgical progress goes in `evidence`, the queue's bounded slot that `doctor.py`, the statusboard and the owed-by listing already read; the earlier design put it in a state-file key that no script in this repository parses. Phase 1's resume rule moved in the same pass and is asserted as a PAIR with Phase 6's status word, because those two drifting apart is what produced this item. Also: a v2-gated rule is described as blocking rather than warning, citing the validator's own gate note; a hard-coded rule count is gone (AUTHORING section 8); Phase 4 names the brief exception; and the Phase 3 gate states its precedence, with the additive criterion winning when it holds, because this skill's own text calls the recurrence default "never a refusal of the in-run modes, just a changed default".

**The doctor blamed the wrong file.** Accepted deviance and minted findings keyed on the crosscheck's target rather than the file the defect is located in, a per-line hold matched only extension-bearing names so a shard row was attributed to the system PRD, and a relative docs directory resolved against the working directory. All four are fixed at the reader. The fallback to the old key is **gated on the finding's own raised date**, not left permanent: an unconditional either-key match would have let a wontfix on the system file silence genuinely new shard defects, which is the accept-direction twin of the bug being fixed.

The installer's own-toolchain predicate had a second copy here that would have disagreed with it for exactly the projects that item is about; it now mirrors both installer signals and an arm pins the agreement.

**Additive mode owes a provenance stamp** (IMP-107). Its mechanics prescribed none, yet the canonical additive fix edits an upstream that a downstream shard is stamped against, so the Phase 5 staleness check exited 1 on a row the same block calls a missed stamp and routed to a reconcile that additive's own close says is not owed. An additive run AUTHORED the whole delta, so the stamp claim is true for it: additive's rule was the wrong side and is what moved. The stamp is prescribed under surgical step 5's existing rules, fresh pairs only, holding every other recorded upstream and reading the printout, upstream-first because other additive shapes stamp a chain. A bare instruction here would have re-opened the two items that exist precisely because an unqualified stamp forges a review. The verification prose also gained the re-stamp-only vocabulary its own verdicts already print.

**The doctor now asks the installer instead of keeping its own copy.** The follow-up pass on IMP-118 found the two predicates differed FOUR ways, not one: the doctor's copy lacked the read-only narrowing, so a strict check script was a generator to one side and a mere check to the other; it never read the local settings file, and called an entry point that accepts none, so the LIVE path missed a fork's hook too; the two produced different reason text, which is the label a consumer reads; and one did not strip a byte-order mark. The old agreement arm was green on that tree, comparing only truthiness across seven cases, none of which distinguished them. A green pin over a real disagreement is worse than no pin. The doctor now imports the installer's two-signal API through a cached never-raising loader, keeping a mirror only for the unreachable-installer path, and 15 cases compare each signal as an exact list.

Regressions: the new `_smoke/validator_contract_selftest.py` (11 assertions, red on HEAD) and `_smoke/additive_stamp_selftest.py` (6, with both guard assertions green before and after so the fix cannot pass by moving the wrong side), both registered in `_smoke/expected.yaml` and `run_smoke.py`; three cases in `_smoke/findings_selftest.py`; twelve in `_smoke/doctor_selftest.py`. Two stale descriptions of the old state in `references/edge-cases.md` were corrected in the same release, and the reconcile chain in `references/forward-propagation.md` now names the system file's own spelling rather than the bare form (IMP-145), alongside one site corrected for IMP-113.

## 1.16 (2026-09-16) — `bump_artifact.py` reads the whole changelog, `findings.py add` never drops a producer's finding, and `migrate_warnings.py` credits the skill that ran it

Ledger IMP-140, IMP-124. The bump refused any artifact whose FIRST changelog line was older than its version - which is also what an oldest-first list looks like, so a PRD carrying every line including the current one could not be repaired without `--force`. It now refuses only when no line names the version (a bump that never got its line) and reports an out-of-order list while prepending. `findings.py add` appends onto a queue that was already invalid (reporting the queue's own problem) while the doctor sweep keeps refusing it, lists every bad flag in one rejection, and enumerates `--kind` in `--help`. `migrate_warnings.py` derives `--by` from `$CLAUDE_SKILL_DIR` and then leaves the caller's own version bump alone. Regressions: `_smoke/bump_selftest.py`, `_smoke/findings_selftest.py`, `_smoke/migrate_selftest.py`.

## 1.15 (2026-09-15) — The close card has a Status: row saying whether repair's edits are done, what each finding still owes and who runs it; the Findings: row translates queue states instead of printing `triaged` / `downstream_rerun`, and Next: prints the first owed command with its position and terminus

Ledger IMP-154 (aicf LSN-087). The card counted findings in the queue's own
words ("1 triaged (awaiting re-invocation)", "1 re-invoke awaiting
downstream_rerun") and was one of three cards without a Status: row, so a run
that fixed every finding at its source read as unfinished beside a Next:
naming another skill. Phase 6 now holds one table from queue state to the
Findings: phrase (closed / still owes N re-runs / not closable / not verified /
parked), a first-match Status: procedure, and a Next: bullet per state that
keeps exactly one command on the row. Phase 2 (the IMP-077 label) and the
IMP-054 bullet point at the table instead of restating a literal. doctor.py's
"awaiting re-invocation per FND-NNN (<command>)" label is unchanged: it names
the command and is the shared owed-work label.

Paths: `SKILL.md` Phase 2 (doctor labels), Phase 6 (the IMP-054 bullet, the
card, "The `Findings:` and `Status:` rows", the Next: bullets). Pinned by
`lint_output_style.py` `lint_cards()` (a card template must carry Status: and
neither queue word, and so must a prose line that tells the agent what to
print on the card) - red on the pre-fix tree with 7 violations; behaviour
check `evals/evals.json` case 4, one added assertion.

## 1.14 (2026-09-15) — A defect the walk surfaces beside the one being fixed, whose decision this run can obtain, is minted and worked in THIS run: it joins the queue, Phase 1 re-reads the queue after each finding closes, and its gate offers *decide it now* at position 1; a later-run sibling only when the decision is not this run's to take

Ledger IMP-153 (aicf LSN-086). Phase 4's split clause sent the modelling
half of a finding - and any adjacent defect the walk surfaced - to a sibling
finding for a later run, against the same phase's "FIX IT in this run" rule,
while Phase 3 had no way back for a defect found after its gate; one project
overrode the agent at the gate. Criterion 2 is unchanged (a gate answer is
recorded in the new finding's `resolution.summary`, not in the additive
criterion), and there is no re-entry mid-Phase 4: a second fix between the
first's steps 1-4 and 5-8 would move bytes the first's stamp then claims as
reviewed (IMP-099/106), so the minted finding is worked after the current
one's Phase 5 by the existing per-finding loop. IMP-107 (additive never
stamps the downstream shard) sits in the adjacent sentence and is untouched.

Paths: `SKILL.md` Phase 1 ("The queue is re-read after every finding
closes"), Phase 4 (the split clause). Pinned by `evals/evals.json` case 15
with `evals/fixtures/case15_adjacent_defect/` (an ARCH shard with one staged
content finding and a planted, askable contradiction twelve lines below it;
the run must mint and resolve the second finding in the same run) - red on
the pre-fix skill.

## 1.13 (2026-09-15) — `references/accepted-deviance.md` is the one statement of the accepted-deviance rule; `doctor --artifact` warns when a wontfix `expected_count` finding was not applied; surgical step 5 holds every recorded upstream it did not review

Ledger IMP-104, IMP-106, IMP-108 (2026-09-15 retro).
- New `references/accepted-deviance.md`; arch/test/task point at it instead of three diverging copies. `doctor.py --artifact` lists a wontfix `expected_count` finding whose `detected_by` names no check it runs (in WARNINGS and as `unapplied_deviance` in `--json`); the registry key stays `(detected_by, file)`. `findings.py add` and `validate_findings.py` warn on `expected_count` without `detected_by`. Pinned: `_smoke/deviance_clause_selftest.py` (new, swept), doctor_selftest and findings_selftest arms.
- Surgical step 5 and `references/forward-propagation.md` pass `--hold-upstream` for every recorded upstream the run did not review, read the stamp's `re-stamped ...` lines before closing, and run the stamp through the helper resolver.

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
