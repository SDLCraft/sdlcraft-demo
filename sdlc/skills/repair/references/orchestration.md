# Orchestration — the whole queue, in two waves of workers (sdlc-repair)

Read this on entering Phase 2 of a run that has more than nothing to work. It
carries the mechanics SKILL.md only names: how the session dispatches the
localize wave and the fix wave, what a worker reads and writes, how findings
are grouped into aggregates and ordered, and what the session never hands off.

---

## Why two waves, and why workers at all

A repair session used to do every localization walk itself. Each walk holds
several artifacts' slices in view, and every one of them lands in the same
context window the session still needs for the next finding — so a run that
started with twelve open findings worked one to four, printed the first
handoff it met, and stopped. The findings it never reached were not refused;
they were never seen again.

Workers exist for **context isolation, not speed** — the same reason the full
edition's `code` skill dispatches one worker per work unit. A walk's reads,
a fix's validator output and a heal transcript stay in the worker; what comes
back is a small report on disk. The session keeps what only it can do:
the sweep, the plan, the one gate, the queue, the verification between waves,
the handoffs and the card.

Two waves rather than one because the human gate sits between localizing and
fixing. Workers never ask the user, so every walk has to finish before one
plan gate can show the whole table — and only then is the fix dispatched.

## Layout on disk

```
.claude/skills-state/sdlc-repair.state.yaml        # the run: plan:, handoffs:, dispatch:
.claude/skills-state/sdlc-repair.doctor.json       # Phase 2 snapshot (unchanged)
.claude/skills-state/sdlc-repair/
  localize/<FND>.yaml       # wave 1 output, one per finding (the plan's input)
  gate/answers.yaml         # the plan gate's answers, as the wave-2 brief reads them
  inflight/<FND>.json       # wave 2 breadcrumb, one per finding, deleted when ledgered
  reports/<FND>.report.yaml # wave 2 output, one per finding (the resolution's input)
```

The session deletes an `inflight/` file the moment it writes that finding's
resolution; `localize/` and `reports/` stay for the run as its audit trail and
are pruned by the next run's Phase 1. Workers write only their own file under
these folders and the artifacts inside their write boundary — never the queue,
never the state file, never `docs/INDEX.yaml` bare.

## Wave 1 — localize

**Who gets a worker:** every finding in the open set that has no
`resolution.located_stage` yet. A `triaged` re-invoke already carries its
walk; it is either closable now (Phase 2, "Close first") or already handed
off, and needs no second walk.

**Dispatch:** the Agent tool, `model: "opus"` (the walk is the cross-artifact
reasoning this skill's model policy reserves opus for), `run_in_background:
true`, the whole wave in ONE turn. Keep at most five in flight and dispatch the
next the moment one returns — rolling, not batched. A worker is **read-only**:
it edits nothing, asks nothing, and writes one file.

**The brief carries paths, never bodies.** Every byte typed into a brief is a
session output token, and the worker reads the file anyway:

```
Localize one repair finding. Read-only: never edit docs/, the queue or any
state file; never ask the user; never run another skill.
FINDING:   FND-NNN in <abs path>/.claude/skills-state/sdlc-findings.yaml
           (python <abs path to findings.py> list --id FND-NNN --json prints it)
RULES:     <abs path>/references/back-propagation.md   - read it whole; Step 3½ is the write set
INDEX:     <abs path>/docs/INDEX.yaml; docs_index.py at <the copy helper-resolution.md picked>
           (--show <symbol>, --refs <symbol>; read artifacts by slice, never whole)
SNAPSHOT:  <abs path>/.claude/skills-state/sdlc-repair.doctor.json
           (provenance.stale = pairs already owed before this run; you hold them, you never claim them)
WRITE:     <abs path>/.claude/skills-state/sdlc-repair/localize/FND-NNN.yaml   (shape in orchestration.md)
REPORT in exactly the capped block below, nothing else:
  FND: <id>  LOCATED: <stage> <artifact>#<symbol>  MODE: <proposed>
  DECISION: <one line, or none>  WRITE_SET: <n> file(s)  STATUS: ok | blocked
```

**The localize report** is the contract `findings.py plan --from` reads:

```yaml
fnd_id: FND-004
located_stage: arch
located:                        # one or more; quote a field_path - `[0]` is not
  - artifact: docs/ARCH__demo-api.yaml   #   valid YAML inside a flow mapping
    symbol: items-controller/listItems
    field_path: "components[0].work_units[1]"
walk:                           # <= 6 lines: surfacing site, stages examined, chosen source, why
  - "surfaced in demo-api/TSK-004 (a codegen worker's blocked report)"
  - "TASKS embed matches ARCH byte for byte -> the embed is not the source"
  - "ARCH listItems names a store read no work_unit provides; PRD FR-002 requires it"
  - "arch is the earliest artifact whose content is wrong"
proposed_mode: surgical | additive | re-invoke | wontfix | duplicate | lesson
criterion:                      # the four-part additive test, answered even for surgical
  additive: true
  determined: false
  provable: true
  chain_closes: true
missing_decision:               # null unless proposed_mode would be re-invoke for want of ONE decision
  question: "which component owns the store-read unit, and what is it called?"
  proposal: "items-controller/readItems - listItems is its only caller"
  basis: measured               # measured = read off the artifacts named; inferred = an analogy
write_set:                      # the blast radius: the located artifact + every artifact the
  - docs/ARCH__demo-api.yaml    # forward checklist will edit, stamp or re-slice
  - docs/TEST-STRATEGY__demo-api.yaml
  - docs/TASKS__demo-api.json
sites_considered_draft:
  - {artifact: docs/TASKS__demo-api.json, disposition_guess: resliced, how: "--refs: TSK-004 embeds the unit"}
restamp_only_rows: []           # `docs_index.py --stale` rows marked re-stamp only that touch the write set
recurrence_of: null
duplicate_of: null              # another OPEN finding on the same located symbol
report: |                       # <= 12 lines, what the plan table shows the user
  ...
```

A worker that cannot settle the located artifact or the mode writes
`proposed_mode: re-invoke` with the unsettled question as `missing_decision`
and `STATUS: blocked` — it never guesses, and the gate takes the question.

## The plan gate

**The table** comes from the helper, never from the session's memory:

```bash
python "${CLAUDE_SKILL_DIR}/findings.py" plan \
  --from .claude/skills-state/sdlc-repair/localize \
  --doctor-json .claude/skills-state/sdlc-repair.doctor.json [--json]
```

It reads every localize report, folds the doctor's `can be marked resolved`
hints into a close-first list, and prints the aggregates in stage-wave order
(`--json` is the same plan as the state file's `plan:` block).

**Aggregates.** An aggregate is the unit of a wave-2 worker: the findings
whose write sets share at least one artifact, joined transitively
(union-find). Overlap is **directory-aware**: a `docs/` entry contains every
path beneath it, so a finding whose write set names a directory joins
everything under it and runs alone. Two workers must never hold the same
artifact — that, not relatedness, decides a group. Two findings that
localize to the same symbol with the same kind are one defect: the later id
closes as `duplicate` of the earlier (`edge-cases.md`, "Two findings localize
to the same symbol"); two kinds on one symbol are two defects in one
aggregate, fixed in id order. An aggregate is **capped at five findings**; a larger one is
split by located stage first, then by id, and the parts run serially.

**Order.** Stage-waves, upstream first: the rank of an aggregate is the
pipeline position of its located artifact (`prd → ux → design → data → api →
arch → test → task`), and an aggregate whose located artifact is downstream of
another aggregate's write set runs in a later wave even when the two are
disjoint — a downstream stamp or re-slice must see the final upstream bytes.
Inside a wave, disjoint aggregates run in parallel; `related`, `recurrence_of`
and same-symbol findings sit in one aggregate. The close-first findings close
before wave 1.

**One `AskUserQuestion`**, with the whole table inside it (AUTHORING's
channel rule: content a decision depends on rides inside the call, in the
recommended option's `preview`, never in chat markdown the same turn):

- Q1, the extent ladder, single-select — position 1 **all N aggregates, in
  wave order** with the full table as its `preview`; then *the first
  stage-wave only*; then *the first aggregate only*. The auto-added "Other"
  carries the per-finding dispositions: `all except FND-…`, `defer FND-…:
  <reason>`, `wontfix FND-…`, `accept-as-is FND-… (expected_count N)`,
  `it's the skill FND-…`, `it's the generated code FND-…` (the Quick
  reference vocabulary, unchanged).
- Q2–Q4, one per `missing_decision`, single-select, the worker's proposal at
  position 1 with its `basis` in the description, *hand it off* as the last
  option. A fifth decision goes in a second call before wave 2 — never a
  second extent question.

Record every answer in `gate/answers.yaml` and the state file's `plan:`
before the first dispatch. A finding whose decision was taken here is
authored in this run (`additive`, the decided field copied verbatim from the
answer); one whose decision was declined is a handoff, and the run carries on
with the next aggregate.

## Wave 2 — fix

One worker per aggregate, `model: "opus"`, dispatched the same way as wave 1
(one turn per stage-wave, five in flight, rolling). The brief:

```
Fix one repair aggregate. Non-interactive: never ask the user - a decision the
gate did not take is STATUS: blocked with the question, not a guess.
FINDINGS:       FND-002, FND-003, FND-004 - work them SERIALLY in this order; the next
                starts after the previous one's verification, never interleaved.
LOCALIZE:       <abs path>/localize/FND-002.yaml, FND-003.yaml, FND-004.yaml
GATE ANSWERS:   <abs path>/gate/answers.yaml   (a decided field is authored from here, never re-decided)
RULES:          <abs path>/references/forward-propagation.md - read it whole;
                back-propagation.md only if a walk proves wrong
SNAPSHOT:       <abs path>/.claude/skills-state/sdlc-repair.doctor.json
                (pairs listed there are held, never stamped, unless answers.yaml marks one re-stamped)
WRITE BOUNDARY: docs/ARCH__demo-api.yaml, docs/TEST-STRATEGY__demo-api.yaml, docs/TASKS__demo-api.json.
                Nothing else. Ever. A walk that locates outside it -> STATUS: relocated, edit nothing.
BREADCRUMB:     <abs path>/inflight/<FND>.json - create before your first write, update after every phase.
REPORT:         <abs path>/reports/<FND>.report.yaml per finding (shape in orchestration.md) + the capped block.
DO NOT: write the queue or the state file; run docs_index.py bare; run another skill;
        print a --reconcile chain (record owed commands in the report instead).
REPORT in exactly this block per finding, nothing else:
  FND: <id>  MODE: <mode>  TOUCHED: <n> file(s)  HOPS: <verified>/<total>  STATUS: ok | blocked | relocated
```

Inside the aggregate the worker runs each finding's Phase-4 sequence exactly
as forward-propagation.md scripts it — the surgical steps, the additive
authoring, or the source-only part of a re-invoke — then its Phase-5
verification, before the next finding starts. That is what keeps the stamp
discipline: every provenance stamp claims only what its own sequence reviewed,
and no other worker can move a file in this boundary meanwhile.

**Breadcrumb** (`inflight/<FND>.json`), written before the first edit and
after every phase:

```json
{"fnd_id": "FND-002", "aggregate": "A2", "started_at": "<iso>",
 "phase": "located | source_edited | bumped | sites_walked | stamped | resliced | verified | reported",
 "files_written": [{"path": "docs/ARCH__demo-api.yaml", "sha256": "<16 hex>"}],
 "stamps": ["docs/ARCH__demo-api.yaml <- docs/PRD.yaml"], "failure_tail": null}
```

**The fix report** (`reports/<FND>.report.yaml`) is what the session writes
the resolution from:

```yaml
fnd_id: FND-002
status: ok | blocked | relocated
mode: surgical
located_stage: arch
artifacts_touched: [docs/ARCH__demo-api.yaml, docs/TASKS__demo-api.json]   # edit order
symbols_changed: [items-controller/createItem]
fields_changed: [components[0].work_units[0].raises]
propagation:
  - {hop: source, target: docs/ARCH__demo-api.yaml, verified_at: <iso>, how: "arch/validate_schema exit 0"}
  - {hop: embed, target: "docs/TASKS__demo-api.json#TSK-003.interface_contract", verified_at: <iso>, how: "reslice_embeds.py --check exit 0"}
sites_considered:
  - {artifact: docs/TASKS__demo-api.json, disposition: resliced, how: "reslice_embeds.py --symbol"}
stale_tasks: [demo-api/TSK-003]
validators: {arch: 0, test: 0, task: 0, reslice_check: 0, crosscheck: 0, index_check: 0, stale: 0}
held_pairs: []                  # snapshot pairs this worker held (never stamped)
handoff_commands: []            # re-invoke only: the owed commands, pipeline order, test before task
handoff_notes: []               # re-invoke only: {artifact, key, note, basis, retired}
relocated_to: null              # {stage, artifact} when status is relocated
blocked_on: null                # the question, when status is blocked
summary: "one line for resolution.summary"
lesson: null                    # a skill defect met on the way, one line (the session routes it)
```

`blocked` and `relocated` reports carry no `propagation` and touch no file:
the worker stops before its first edit on that finding and continues with
the next one in its aggregate.

## Between waves — drain, verify, re-stamp

A stage-wave is drained when every worker in it has reported. Then, in the
session, before the next wave is dispatched:

1. read each report's captured exit codes and compare them to
   `baseline_checks` (a check red before the run is pre-existing, never
   claimed either way);
2. `python "${CLAUDE_SKILL_DIR}/doctor.py" --docs-dir docs --quick` and
   `python "${CLAUDE_SKILL_DIR}/validate_findings.py"`, bare, exit codes
   captured;
3. re-stamp the **re-stamp-only rows**: `docs_index.py --stale` marks a row
   `re-stamp only` when nothing the downstream artifact references or cites
   changed, so its "review" is empty and the stamp's claim is true. The
   session stamps such rows — pre-existing ones right after the plan gate,
   ones a wave caused at that wave's drain — with `--upstream <the moved
   file>` and `--hold-upstream` for every other upstream the artifact
   records, then reads the `re-stamped …` printout exactly as surgical step 5
   prescribes. This is the ONE case where a pair in the Phase-2 snapshot is
   stamped. A row with real item drift inside a pending aggregate's boundary
   belongs to that worker; outside every boundary it joins the handoff chain;
4. re-read the queue (`findings.py list --open`): a finding minted by a
   worker's report (`lesson`, or a defect it surfaced beside its own) joins
   the next wave's plan through wave 1 for it alone;
5. a `blocked` report → its question goes to the user now, batched with the
   others of this drain (four per call), and the finding is re-dispatched with
   the answer in `gate/answers.yaml`; a `relocated` report → re-plan the
   finding into a later aggregate (its new write set) when that stage-wave has
   not run yet, else it goes on the card's `Remaining:` row with the reason.

Only then the next wave. A downstream wave that started before an upstream
drain would stamp its shard against upstream bytes still moving.

## The consolidated handoff chain

Nothing prints a `--reconcile` command mid-run. At Phase 6 the session builds
ONE chain from every report's `handoff_commands` plus every already-`triaged`
finding's `downstream_rerun`: deduplicated, ordered by the pipeline position
of the artifact each command rewrites, `/sdlc:test <cid>` before `/sdlc:task
<cid>` where a work_unit was minted, container-scoped forms, the full
interview form as one fallback line. It is printed once above the card, the
card's `Handoffs:` row carries the count and the FIRST command, and each
finding keeps its own sub-sequence in `downstream_rerun`. The chain still
walks itself: each reconcile's `Next:` is the next stale file, and the last
routes back to `/sdlc:repair FND-…` to close.

## Relocation

A wave-2 worker whose fix, once started, proves the walk wrong — the source
is in an artifact outside its boundary — edits nothing and reports
`relocated` with `relocated_to`. The session never localizes it inline (that
would pull the archaeology back into the window this design keeps clear): it
re-plans the finding into a later aggregate, or lists it under `Remaining:`
as *relocated to <stage> after that wave closed*, with `/sdlc:repair FND-…`
as the way back.

## Resume

The state file's `plan:` block plus the breadcrumbs and reports decide, per
aggregate, where an interrupted run stands: a report `ok` with the resolution
written → done; a report `ok` without a resolution → Phase 6 for it; a
breadcrumb without a report → re-verify every `files_written` hash against
disk, then re-dispatch the aggregate with `RESUME FROM: <breadcrumb path>`
in the brief; nothing at all → dispatch fresh. A finding that became `open`
after `plan.planned_at` gets wave 1 for itself alone. Phase 1's existing rule
holds throughout: re-verify every artifact a partial record names against
disk before touching it.

## Without the Agent tool

When the Agent tool is unavailable, run both waves inline, one finding at a
time, in plan order — the same walks, the same per-mode sequences, the same
gate — and say so on the card's `Attention:` row. The plan, the order and the
card rules do not change; only the context isolation is lost.

## What the session never delegates

The doctor sweep and its snapshot; `findings.py add | plan | reopen |
validate`; the Phase-6 resolution write (from reports, never from memory);
`doctor.py --quick` and `validate_findings.py` at every drain; the bare
`docs_index.py` regenerate through the project's copy; the re-stamp-only
stamps; the consolidated chain; `lessons.py record-run`; `autocommit.py`; the
card. Workers report, the session records.

## The close card

The `Findings:` row translates queue states into what is done and what is
still owed; the queue's state names and field names are input to the row,
never its text:

| The finding in the queue | What the row says |
|---|---|
| `resolved` | `fixed and closed` |
| a re-invoke in progress with commands recorded | `fixed at its source, still owes N re-run(s)` — N is the length of its recorded sequence; the same owed work the doctor labels `awaiting re-invocation per FND-NNN` |
| a re-invoke in progress with no commands recorded | `not closable - its re-runs were never recorded` |
| `open`, a surgical fix whose hop this run could not verify | `fixed, not verified - <the check that could not run>` |
| `deferred` / `wontfix` / `duplicate` | `parked (<reason>)` / `left as is (accepted)` / `same defect as FND-NNN` |

Collapse same-state findings into one phrase listing their ids. Keep "closed"
and "still owes" apart.

`Remaining:` names every finding that was open when the run started and was
not worked: *outside the chosen extent* / *relocated to <stage> after that
wave closed* / *its worker stopped on a question the run could not answer*.
It is the row that makes a narrowed run honest. `Handoffs:` names how many
re-runs are owed across how many findings and the first command; the full
chain is printed once, above the card.

```
── /sdlc:repair — what changed ────────────────────────────
Findings:  3 fixed and closed (FND-001, FND-002, FND-006) · 1 fixed at its source, still owes 2 re-runs (FND-004) · 1 same defect as FND-002 (FND-007)
Located:   FND-001 → prd (suspected: test)  ·  FND-002 → arch (suspected: arch)  ·  FND-004 → arch (suspected: task)
Edited:    docs/PRD.yaml, docs/ARCH__demo-api.yaml, docs/TASKS__demo-api.json (2 embeds re-sliced) · 1 re-stamp (docs/TEST-STRATEGY__demo-api.yaml vs docs/PRD.yaml)
Verified:  arch exit 0 · test exit 0 · task exit 0 · reslice --check exit 0 · crosscheck exit 0 · index exit 0 · stale exit 0
Stale:     demo-api/TSK-003, demo-api/TSK-004 will be offered for regeneration
Remaining: 1 open, not worked this run — FND-005 (outside the chosen extent: first wave)
Handoffs:  2 re-runs owed for FND-004 — first: /sdlc:test demo-api --reconcile (each prints the next; the last routes back here)
Workers:   6 localizers, 3 fixers (opus) - 1 relocated, 0 blocked
Commit:    a1b2c3d  /sdlc:repair → 3 findings closed at prd/arch, 1 handed off
Status:    not finished - 1 open finding remains (FND-005)
Next:      /sdlc:repair FND-005   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this transcript.
```
