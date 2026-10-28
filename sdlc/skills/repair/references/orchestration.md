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

Workers exist first for **context isolation** — the same reason the full
edition's `code` skill dispatches one worker per work unit — and only the
localize wave also buys speed, by running N of them at once ("Choosing N"
below). A walk's reads,
a fix's validator output and a heal transcript stay in the worker; what comes
back is a small report on disk. The session keeps what only it can do:
the sweep, the plan, the one gate, the queue, the verification between waves,
the handoffs and the card.

Two waves rather than one because the human gate sits between localizing and
fixing. Workers never ask the user, so every walk has to finish before one
plan gate can show the whole table — and only then is the fix dispatched.

## Choosing N (localize only)

N is how many **localize** workers may be in flight. It is resolved **flag >
gate answer > remembered value > 6**: `--parallel N` (clamped to 1–8 with a
one-line note, never an error), else the answer to the dispatch question, else
`run_defaults.parallel` from the state file, else 6. The effective value is
`min(N, clusters)` — the clusters `findings.py cluster` forms over the findings
to localize ("Wave 1"); report both, so an N of 6 over two clusters reads as the
scheduler working, not the setting being ignored.

**Why the localize wave may run wide.** A localizer is read-only against a
corpus nothing writes until the plan gate has been answered, and it writes one
file of its own. Two localizers cannot disturb each other, whatever they walk;
two that walk to the same defect meet afterwards in `findings.py plan` (a
report's own `duplicate_of` folds; a shared write set → one aggregate). The
independence is known in advance, by construction, so the default is wide (6).
What N costs: under a per-window token cap, N opus walks finish no sooner per
window than one — they spend the budget N times faster — and an interrupted
wave loses up to N unfinished walks (a cluster worker writes each member's
report as that walk ends, so the reports already on disk survive, and a resume
dispatches only the missing ones).

**Why the fix wave never runs wide.** A fix aggregate's *write* boundary is
disjoint from every other aggregate's by construction, but its *reads* are not:

- its verification is family- and corpus-wide — a validator is passed the
  system file and globs every `__<slug>` sibling, and `crosscheck`,
  `docs_index.py --check` and `doctor.py --provenance` read the whole corpus —
  so a second fixer's half-finished sequence would read as this fixer's red;
- every `docs/` edit fires the project's index hook, which rewrites
  `docs/INDEX.yaml` and the statusboard whole, so two fixers would race on
  shared files neither owns;
- two additive fixes in sibling shards can mint the same id in one numbering
  family, each green alone;
- a provenance pair diff cannot tell a sibling's in-flight stale pair from one
  this fixer caused.

None of that can be settled before the fixes run, so fixes run **one aggregate
at a time, in plan order**. The plan still records `max_wave_width` — the most
disjoint aggregates any one stage-wave holds — and the run copies it into
`metrics`, so how much a wider fix wave could ever have bought is measured, not
guessed.

**The dispatch question** (Phase 2, before wave 1). Options, one
`AskUserQuestion`: position 1 the resolved N labelled with its source — *"6 —
remembered from your last run"*, *"6 — the default, never chosen"* — then the
other rungs of `6` / `3` / `1`, deduplicated against position 1; "Other" takes
any N. Label each by its consequence, not its rationale: *6 — fastest; an
interruption loses up to 6 unfinished walks*, *1 — slowest; an interruption
loses one walk*. The `preview` is the provisional plan table. Skipped when
`--parallel N` answered it, when the findings to localize form at most one
cluster, and without the Agent tool (then say, in one line, that a remembered N
above 1 cannot be honoured this run).

**The scope questions** ride in the same call — full flow only (a named finding
is worked as named) — and are asked even when the N question is skipped:

- *Cosmetic findings.* When the `severity:` count line of `findings.py list
  --open` shows `cosmetic` above zero (an unstamped finding reads as
  `behavioural`): *defer the N cosmetic findings without a walk* at position 1,
  *walk them too*; the `preview` lists them one line each. The deferral is
  written in the resolution write as `status: deferred`, mode `none`, with a
  reason; the finding's severity already says why, so no `park_reason` is set,
  and `findings.py reopen` brings one back.
- *Parked latent findings.* When `findings.py list --status deferred` shows
  findings whose `park_reason` is `latent` (the statusboard prints their
  count): *leave them parked* at position 1, *work the N parked latent findings
  too* — each is reopened and joins this wave 1.

**Memory.** `run_defaults: {parallel, parallel_set_at}` lives in
`sdlc-repair.state.yaml` and is **sticky**: every new, restarted or discarded
state file carries it forward. Only a decision writes it — the flag or an
answer; a skipped question, `EXIT` at the question, and a run with nothing to
localize leave it untouched. A value that is missing, non-integer or outside
1–8 is clamped when it can be, otherwise read as never chosen (6), said in one
line; a preference never fails a run. `concurrency: {requested, source,
effective}` records what this run used.

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
resolution; `localize/` and `reports/` stay for the run as its audit trail,
are committed with it, and are pruned by the next run's Phase 1. Workers write
only their own file under these folders and the artifacts inside their write
boundary — never the queue, never the state file, never `docs/INDEX.yaml` bare.
A helper script or probe (the session's or a worker's) goes in the system temp
dir: every file a run leaves inside the project is committed with the run
(`setup/references/auto-commit.md`).

## Wave 1 — localize

**Who gets a worker:** one worker per cluster. The findings to localize are
the open set's findings that have no `resolution.located_stage` yet — a
`triaged` re-invoke already carries its walk (closable now, Phase 2 "Close
first", or already handed off) and a `deferred` finding is not in the open set
at all. `python "${CLAUDE_SKILL_DIR}/findings.py" cluster --json` groups
exactly those findings:

```
{"cap": <n>, "clusters": [{"id": "C1", "members": ["FND-004", "FND-009"], "shared_tokens": ["listItems"]}]}
```

(without `--json`, one line per cluster: `C1 (2): FND-004 FND-009  shared: listItems`).
It seeds a cluster with the finding that shares the most identifier tokens
with the others and grows it by token overlap with that seed, never past
`cap` members; a finding that shares nothing is a cluster of one. A cluster is
a reading convenience: its members are likely to walk the same slices, so one
worker reads them once instead of each paying a cold read. It is never a
duplicate claim — every member keeps its own walk, its own report and its own
located source, and only a member's own evidence sets `duplicate_of`. The helper
only groups; the plan still groups by write sets. Severity is display only
here: `findings.py list` prints each row's severity (an unstamped finding prints
`behavioural*`) and it never splits a cluster or an aggregate.

**Dispatch:** the Agent tool, `model: "opus"` (the walk is the cross-artifact
reasoning this skill's model policy reserves opus for), `run_in_background:
true`. Keep N clusters in flight ("Choosing N") and dispatch the next the
moment one returns — rolling, not batched; at N = 1 it is still a worker. A
worker is **read-only**: it edits nothing, asks nothing, and writes one report per
member.

**The brief carries paths, never bodies.** Every byte typed into a brief is a
session output token, and the worker reads the file anyway:

```
Localize the repair findings of ONE cluster. Read-only: never edit docs/, the queue
or any state file; never ask the user; never run another skill.
CLUSTER:   FND-004, FND-009 (C1; shared: listItems) - walk each member in turn, reading the
           shared slices once. Membership is a reading convenience, never a duplicate claim.
FINDINGS:  each in <abs path>/.claude/skills-state/sdlc-findings.yaml
           (python <abs path to findings.py> list --id FND-NNN --json prints it)
PRIOR:     (a finding minted mid-run only) <abs path>/localize/FND-NNN.yaml - the report of the
           finding that minted it; most of the walk is already there
RULES:     <abs path>/references/back-propagation.md   - read it whole; Step 3½ is the write set
INDEX:     <abs path>/docs/INDEX.yaml; docs_index.py at <the copy helper-resolution.md picked>
           (--show <symbol>, --refs <symbol>; read artifacts by slice, never whole)
SNAPSHOT:  <abs path>/.claude/skills-state/sdlc-repair.doctor.json
           (provenance.stale = pairs already owed before this run; you hold them, you never claim them)
WRITE:     <abs path>/.claude/skills-state/sdlc-repair/localize/FND-NNN.yaml - ONE file per member,
           written the moment that member's walk ends (shape in orchestration.md)
SURFACE, NEVER HUNT: a defect you meet while reading what a finding needs goes in that report's
           `beside:` (summary, site, read_for: that FND); a finding already in the queue goes in
           `resighted:`. Never read further to find more; never propose a fix for one.
PRICE:     none - read-only: run no topo_order.py or reslice_embeds.py and copy no docs; the
           fixer prices the edit ("Pricing").
EJECT:     a member whose walk leaves the cluster's ground gets NO report; name it on EJECTED.
REPORT in exactly the capped block below, once per member, then the EJECTED line, nothing else:
  FND: <id>  LOCATED: <stage> <artifact>#<symbol>  MODE: <proposed>
  DECISION: <one line, or none>  WRITE_SET: <n> file(s)  STATUS: ok | blocked
  EJECTED: <ids, or none>
```

**The localize report** is the contract `findings.py plan --from` reads:

```yaml
fnd_id: FND-004
located_stage: arch
located:                        # one or more; quote a field_path - `[0]` is not
  - artifact: docs/ARCH__demo-api.yaml   #   valid YAML inside a flow mapping
    symbol: items-controller/listItems
    field_path: "components[0].work_units[1]"   # the defective field INSIDE the symbol,
                                #   never the symbol's own entry
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
decide_with: []                 # FND ids whose decision or edit is the SAME as this one's; [] when none
beside:                         # defects met while reading what THIS finding needs; [] when none
  - {summary: "listItems orders by 'ascending numeric id'", site: "docs/ARCH__demo-api.yaml#items-controller/listItems", read_for: FND-004}
resighted: []                   # FND ids already in the queue (open or parked) this walk met again
report: |                       # <= 12 lines, what the plan table shows the user
  ...
```

`decide_with` is set before the gate and names a finding only when deciding or
editing it is the same act as this finding's — never for proximity, a shared
symbol or a shared cluster. `beside:` is a surfacing slot, not a finding: the
entry names where the defect is and which finding's reading met it, nothing
about a fix. The session tests it ("Convergence"). A member the worker ejects
has no report; the drain re-clusters report-less findings once, and a second
ejection goes solo ("Between waves").

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
artifact — that, not relatedness, decides a group. `plan` never infers a
duplicate from a name: only a localizer's own `duplicate_of` folds a finding
away. Two findings on one symbol and kind stay in their aggregate, listed in
its `possible_duplicates` (`{fnd, of, why}`, kept in the state file's `plan:`
block), fixed in id order; the later finding's brief carries a `CHECK FIRST`
line, and its worker reports `duplicate` when the earlier fix removed the
defect, else fixes it (`edge-cases.md`, "Two findings localize to the same
symbol"). An aggregate is **capped at five findings**; a larger one is
split by located stage first, then by overlap of the located symbols, and the
parts run serially. A possible-duplicate pair always stays in one part, earlier
id first; so do the findings a localizer links with `decide_with`, which may
run to six together — a larger link set is split and the plan lists the refused
links as unhonored. A link groups, it never folds.

**Order.** Stage-waves, upstream first: the rank of an aggregate is the
pipeline position of its located artifact (`prd → ux → design → data → api →
arch → test → task`), and an aggregate whose located artifact is downstream of
another aggregate's write set runs in a later wave even when the two are
disjoint — a downstream stamp or re-slice must see the final upstream bytes.
Inside a wave, aggregates run one after another in id order ("Choosing N");
`related`, `recurrence_of` and same-symbol findings sit in one aggregate. A
mutual wait — two aggregates whose located lists each reach below the other's
write set — runs upstream-first. When the later aggregate moves something
under the earlier one's downstream artifact, that artifact is re-stamped if
`--stale` marks it re-stamp-only, and otherwise joins the handoff chain; the
plan stays silent about it. The close-first findings close before wave 1.

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
  option. The decisions of the findings one `decide_with` unit links are asked
  as ONE question, and its answer is written under every linked id. A fifth
  decision goes in a second call before wave 2 — never a second extent
  question.

Record every answer in `gate/answers.yaml` and the state file's `plan:`
before the first dispatch. A finding whose decision was taken here is
authored in this run (`additive`, the decided field copied verbatim from the
answer); one whose decision was declined is a handoff, and the run carries on
with the next aggregate.

## Wave 2 — fix

One worker per aggregate, `model: "opus"`, `run_in_background: true`, **one
aggregate at a time, in plan order** — never two side by side, however
disjoint ("Choosing N"). The brief:

```
Fix one repair aggregate. Non-interactive: never ask the user - a decision the
gate did not take is STATUS: blocked with the question, not a guess.
FINDINGS:       FND-002, FND-003, FND-004 - work them SERIALLY in this order; the next
                starts after the previous one's verification, never interleaved.
CHECK FIRST:    (only when the plan lists a possible duplicate) FND-003 may be FND-002 - after
                FND-002's fix, report FND-003 duplicate (duplicate_of FND-002) if its defect is gone.
LOCALIZE:       <abs path>/localize/FND-002.yaml, FND-003.yaml, FND-004.yaml
GATE ANSWERS:   <abs path>/gate/answers.yaml   (a decided field is authored from here, never re-decided)
RULES:          <abs path>/references/forward-propagation.md - read it whole;
                back-propagation.md only if a walk proves wrong
SNAPSHOT:       <abs path>/.claude/skills-state/sdlc-repair.doctor.json
                (pairs listed there are held, never stamped, unless answers.yaml marks one re-stamped)
WRITE BOUNDARY: docs/ARCH__demo-api.yaml, docs/TEST-STRATEGY__demo-api.yaml, docs/TASKS__demo-api.json.
                Nothing else. Ever. A walk that locates outside it -> STATUS: relocated, edit nothing.
                A token-sweep hit outside it is never edited, never `unaffected`: report it in
                out_of_boundary, and list every key you grepped in swept_tokens.
                A helper script goes in the system temp dir - anything left in the project is committed.
BREADCRUMB:     <abs path>/inflight/<FND>.json - shape and phases: orchestration.md, "Breadcrumb" (read it).
                Create it, `baseline` filled, before your first write; update it after every phase.
RESUME FROM:    <breadcrumb path> (a resumed aggregate only) - keep its `baseline` verbatim and only
                append; classify each touched file by role (orchestration.md, "Resume").
BESIDE:         SURFACE, NEVER HUNT - a defect met beside a finding's fix goes in that report's
                `beside:` (summary, site, read_for); never fixed here, never looked for.
REPORT:         <abs path>/reports/<FND>.report.yaml per finding (shape in orchestration.md) + the capped block.
DO NOT: write the queue or the state file; run docs_index.py bare; run another skill;
        print a --reconcile chain (record owed commands in the report instead);
        run a git command that writes the tree or index (stash, checkout, switch, restore,
        reset, clean, rm, add, commit, apply, pull, worktree) - git is read-only for you
        (status, diff, show, log); the tree holds the user's uncommitted docs, the queue
        and the state file, and those commands belong to the session.
REPORT in exactly this block per finding, nothing else:
  FND: <id>  MODE: <mode>  TOUCHED: <n> file(s)  HOPS: <verified>/<total>  STATUS: ok | blocked | relocated | duplicate
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
 "baseline": [{"path": "docs/ARCH__demo-api.yaml", "hash": "<16 hex>"}],
 "files_written": [{"path": "docs/ARCH__demo-api.yaml", "hash": "<16 hex>"}],
 "stamps": ["docs/ARCH__demo-api.yaml <- docs/PRD.yaml"], "failure_tail": null}
```

`phase` is one of the listed words, nothing else. `baseline` holds every WRITE
BOUNDARY file that exists, hashed before the finding's first write; it is
written once, by the first worker on the finding, and a RESUME FROM worker
keeps it verbatim and only appends. Each file enters `files_written` in the
same breadcrumb write as the phase that wrote it. Both lists use the hash
`python .claude/sdlc/docs_index.py --hash <file>` prints (stable across a CRLF
checkout), never a raw sha256 of the bytes. Findings run serially, so a
finding's baseline already contains the earlier findings' landed edits.

**The fix report** (`reports/<FND>.report.yaml`) is what the session writes
the resolution from:

```yaml
fnd_id: FND-002
status: ok | blocked | relocated | duplicate
duplicate_of: null              # FND-X, when status is duplicate
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
swept_tokens: []                # every key grepped: the token, its sibling/parent keys, the old-shape words
out_of_boundary: []             # {artifact, token, hits}: sweep hits outside the write boundary that restate a swept token
relocated_to: null              # {stage, artifact} when status is relocated
blocked_on: null                # the question, when status is blocked
summary: "one line for resolution.summary"
lesson: null                    # a skill defect met on the way, one line (the session routes it)
beside: []                      # as in the localize report: defects met while fixing, {summary, site, read_for}
resighted: []                   # FND ids already in the queue this fix met again
```

`blocked`, `relocated` and `duplicate` reports carry no `propagation` and
touch no file: the worker stops before its first edit on that finding and
continues with the next one in its aggregate. A `duplicate` is the CHECK FIRST
outcome only; the queue stays untouched until the session's Phase-6 write sets
`status: duplicate` and `duplicate_of` from the report ("The resolution write"
in `forward-propagation.md`) — a worker never writes the queue.

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
   changed, so its "review" is empty and the stamp's claim is true — but the
   row is never itself diffed against the snapshot for pre-existence: a row
   is pre-existing only when EVERY (artifact, upstream) pair it names is
   already in `provenance_drift` (the Phase 2 `doctor.py --provenance --json`
   pairs, re-run and diffed pair by pair — never the `--stale` row count),
   stamped right after the plan gate; a row naming even one pair the
   snapshot lacks is wave-caused, stamped at that wave's drain instead — with
   `--upstream <the moved file>` and `--hold-upstream` for every other
   upstream the artifact records, then reads the `re-stamped …` printout
   exactly as surgical step 5 prescribes. This is the ONE case where a pair
   in the Phase-2 snapshot is stamped. A row with real item drift inside a
   pending aggregate's boundary belongs to that worker; outside every
   boundary it joins the handoff chain;
4. re-read the queue (`findings.py list --open`) and test every report's
   `beside:` entries ("Convergence"): the admitted ones are minted and join the
   next wave, the latent ones are minted and parked. ONE `python
   "${CLAUDE_SKILL_DIR}/findings.py" cluster --json` pass then groups everything
   still lacking a `located_stage` — the admitted mints (each cluster brief
   carrying `PRIOR:` the minting finding's report), any finding opened since the
   plan, and each finding a cluster worker ejected, re-clustered once, then
   solo. An admitted mint whose localize report names `decide_with` a finding
   of an aggregate not yet dispatched joins that aggregate (up to the six a
   linked unit may hold); any other mint forms its own;
5. a `blocked` report → its question goes to the user now, batched with the
   others of this drain (four per call), and the finding is re-dispatched with
   the answer in `gate/answers.yaml`; a `relocated` report → re-plan the
   finding into a later aggregate (its new write set) when that stage-wave has
   not run yet, else it goes on the card's `Remaining:` row with the reason;
6. re-grep each report's `swept_tokens` across `docs/` (changelog lines
   excepted) and compare the hits to THAT worker's own write boundary, not
   the wave's edited files. Route every hit outside it — listed in the
   report's `out_of_boundary` or found only by the re-grep — by the rule of
   step 3: inside a pending aggregate's boundary, an owed-site line appended
   to that aggregate's brief; outside every boundary, the handoff chain or
   `Remaining:`. The finding stays `open` with the progress on one evidence
   line until the hit is closed; never re-dispatch the whole finding;
7. settle: the resolution write (Phase 6) for every finding this drain
   settled — from the reports, never from memory, with the cosmetic and latent
   deferrals — so the queue and the tree agree. Phase 6 writes only what is
   still unwritten;
8. checkpoint. One checkpoint per located stage: at the drain of a wave whose
   next wave has a different `stage`, or that ends the plan; every other drain
   skips this step. It runs only after step 7's write succeeded: re-run
   `doctor.py --quick` and `validate_findings.py` bare after that write, and
   commit only when both exit 0 AND `findings.py list --open` names none of
   the findings this drain settled - validate_findings exits 0 while findings
   are open, so its exit code alone is not green. A failed resolution write or
   a settled id still open is a red tree. The commit is its own call, never
   chained after the write: `python
   .claude/sdlc/autocommit.py commit --skill repair --checkpoint --invocation
   "<as typed>" --summary "<FND ids fixed at <stage>>"`. A stage planned as
   many one-aggregate waves is still one commit. It keeps the run baseline for
   the close commit, and it is never a blocker and never a stop trigger: a red
   tree is never committed (one `Attention:` line says the checkpoint was
   skipped), and a helper that is absent or refuses is a skipped step. Rolling
   one fixer back stays possible from its report's file list. At the last
   drain of a round, print the round card ("The round card") and, when the
   round parked latent findings, ask its question ("Convergence").

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
breadcrumb without a report → find the finding's touched files by hashing
every `baseline` entry again, then re-dispatch the aggregate with
`RESUME FROM: <breadcrumb path>` in the brief; nothing at all → dispatch
fresh. A file whose hash differs from its `baseline` is touched, whatever
`files_written` says (the worker may have died before recording it) — and
never ask `git diff`, which also holds the user's uncommitted docs. Classify
each touched file by its role in the finding's sequence: a **bump target**
(the source, each site edit) whose newest changelog line names the finding is
landed, otherwise it was edited and not bumped — bump it, never re-edit; a
**reslice target** (a TASKS shard) is re-run with `reslice_embeds.py --check`,
silent = landed, else the same selector again (idempotent); a **stamp target**
is re-checked with `docs_index.py --drift`. Resume never bumps a reslice or
stamp target. A breadcrumb with no `baseline` (written under an older brief)
falls back to re-reading each `files_written` file against the localize
report's fields. A finding that became `open`
after `plan.planned_at` joins the next drain's cluster pass. Phase 1's existing rule
holds throughout: re-verify every artifact a partial record names against
disk before touching it. A resumed wave 1 keeps the recorded `concurrency`,
clusters again (`findings.py cluster` considers only the findings with no
localize report) and dispatches those clusters; the dispatch question is not
asked again.

## Without the Agent tool

When the Agent tool is unavailable, run both waves inline, one finding at a
time, in plan order — the same walks, the same per-mode sequences, the same
gate — and say so on the card's `Attention:` row. The plan, the order and the
card rules do not change; only the context isolation is lost. Each inline pass
counts as one worker on the round card.

## What the session never delegates

The doctor sweep and its snapshot; `findings.py add | cluster | plan | reopen |
validate`; the Phase-6 resolution write (from reports, never from memory);
`doctor.py --quick` and `validate_findings.py` at every drain; the bare
`docs_index.py` regenerate through the project's copy; the re-stamp-only
stamps; the consolidated chain; `lessons.py record-run`; `autocommit.py`; the
card. Workers report, the session records.

## Convergence

**Scope.** A run works the findings a build or an interview skill surfaced —
about a dozen is the designed scale — plus the defects its own fixes expose
beside them. It is not a corpus audit: a worker reads what its finding needs
and no more, and no brief asks it to look further.

**A round is one wave-1 pass over the findings open at its start plus the fix
waves that drain it** — one iteration of the loop SKILL.md Phase 1 describes.
The round card and the drain's cluster pass cite this definition and do not
restate it.

**Admission.** A defect a worker meets beside the finding it is working goes in
its report's `beside:` list as `{summary, site, read_for: FND-NNN}`: surface,
never hunt. The session checks the entry against the `located` list of the
finding `read_for` names. A `site` that lies in the work_unit or component blocks
of that located slice is inside what the fix had to READ: it is **admitted** —
minted (`findings.py add … --related FND-NNN --raised-by sdlc-repair --severity
<integrity|behavioural|cosmetic>`), it joins the next wave, and its gate question
offers *decide it now* at position 1. Anything reached by looking further, a
`read_for` that names no located slice, or a case the session cannot place is
**latent**: minted the same way and parked — `status: deferred`, mode `none`, a
reason, and `resolution.park_reason: latent`, written in the resolution write. When `add`
prints `not recorded - duplicate of FND-NNN` or `parked as FND-NNN` it wrote
nothing, and the entry is a **re-sighting**; so is a `resighted:` entry. The
statusboard prints one count line for the parked latent findings.

**The ledger.** At each round's end the session appends to the state file's
`rounds:` one entry, from the reports it already holds:

```yaml
rounds:
  - {n: 1, worked: 14, closed: 12, fix_induced: 2, latent: 9, resighted: 4, localize_workers: 5, fix_workers: 4, built: 28, stale: 71}
```

`fix_induced` counts the admitted mints; `built` and `stale` are the round's
one build measurement ("Pricing"). The rates, per round: fix-induced rate
= `fix_induced / worked`; latent rate = `latent / worked`; re-sighting share =
`resighted / (resighted + latent)` — the drain signal, because a share that
rises means the latent pool is finite.

**The round question** is asked only when the round parked latent findings, and
carries the round card as its recommended option's `preview`; otherwise the card
prints with no question. Its options follow the latent rate:

- latent rate at or below 1 — *work the latent findings now* at position 1 (each is
  reopened with `findings.py reopen` and starts the next round), then *park them*;
- latent rate above 1 — *park them* at position 1, then *work them now*;
- two consecutive rounds above 1 — the **structural route** at position 1: stop
  the run here, because the defects are in the specs and not in this queue.
  "Batching" in `forward-propagation.md` is that loop: re-invoke the owning
  stage, or `/sdlc:code <cid>` in a NEW session so the build surfaces what
  matters. `Next:` names it; then *park them*, then *work them now*.

## The round card

Printed at the end of each round. A field whose source is missing prints `not
reported` — never zero, never invented.

```
Round 2 - 14 worked, 12 closed · minted 11 (2 fix-induced, 9 latent) · re-sighted 4
Rates:   latent 0.6 per finding worked (round 1: 0.9) · re-sighting share 31%
Workers: 5 localize + 4 fix = 0.75 workers per closed finding
Context: worker context as the host reports it - not cost: localize 1.1M, fix 1.8M (or: not reported)
Build:   28 built, 82 stale (was 28 built, 71 stale)
Open:    severity: integrity 1, behavioural 4, cosmetic 3
```

- **Workers per closed finding** is the primary figure: localize plus fix
  workers over findings closed this round. The line always prints
  `Workers: <L> localize + <F> fix = <x> workers per closed finding`, never
  without the figure. An inline pass (a run without the Agent tool) is one
  worker for this arithmetic, and the line then ends `(inline)`.
- **Context** is the host's subagent token count from each worker's completion
  result. Record it per task id, **last value wins** (a resumed worker reports
  a running total), then sum it into `metrics.worker_context_tokens_localize`
  and `metrics.worker_context_tokens_fix`. It is context size, not cost, and
  the card says so; a host that reports none leaves the keys out.
- **Build** is the `done` and `stale` counts of the one unscoped `topo_order.py`
  run at the round's last drain ("Pricing"); `(was …)` reads the previous
  `rounds[]` entry, and a project with no price prints `not reported`.
- **Open** is the `severity:` count line of `findings.py list --open`.

Walks and fixes stay opus: a cheaper tier for either needs this record first,
so the card only records.

## Pricing

What a fix costs is the built tasks it moves, and it is measured in one place:
the fixer, in place, with the `topo_order.py` call of Phase 4 step 8. A localize
worker prices nothing: it is read-only, no edit exists to price, so it runs
neither `topo_order.py` nor `reslice_embeds.py` and copies no docs.

- **The delta.** The fixer runs `topo_order.py --scope <cid>` once before its
  first edit and once at step 8, both on the real tree, read-only, with no docs
  copy. `resolution.stale_tasks` gets only the tasks newly stale in the second
  run, each with the reason `topo_order.py` prints. A hand join of `--refs`
  against the ledger is not a price: it undercounts.
- **The round.** At a round's last drain the session runs `topo_order.py` once,
  unscoped (all containers). Its `done` and `stale` counts feed the round
  card's Build line, and the session records them as `built` and `stale` in that
  round's `rounds[]` entry.
- **No price.** No code skill (demo edition) or no code ledger = no price;
  `stale_tasks: []`, and the card prints `not reported` for Build.

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
chain is printed once, above the card. `Parked:` prints only when this run
parked latent findings: how many, which, and that the next run offers them.
`Workers:` says what was dispatched on which model — the localize workers, the
findings they covered, N with its source and its effective value — and how many
fixers relocated or blocked (or `inline - the Agent tool was unavailable`).

```
── /sdlc:repair — what changed ────────────────────────────
Findings:  3 fixed and closed (FND-001, FND-002, FND-006) · 1 fixed at its source, still owes 2 re-runs (FND-004) · 1 same defect as FND-002 (FND-007)
Located:   FND-001 → prd (suspected: test)  ·  FND-002 → arch (suspected: arch)  ·  FND-004 → arch (suspected: task)
Edited:    docs/PRD.yaml, docs/ARCH__demo-api.yaml, docs/TASKS__demo-api.json (2 embeds re-sliced) · 1 re-stamp (docs/TEST-STRATEGY__demo-api.yaml vs docs/PRD.yaml)
Verified:  arch exit 0 · test exit 0 · task exit 0 · reslice --check exit 0 · crosscheck exit 0 · index exit 0 · stale exit 0
Stale:     demo-api/TSK-003, demo-api/TSK-004 will be offered for regeneration
Remaining: 1 open, not worked this run — FND-005 (outside the chosen extent: first wave)
Parked:    2 latent findings parked (FND-008, FND-009) - the next /sdlc:repair run offers to work them
Handoffs:  2 re-runs owed for FND-004 — first: /sdlc:test demo-api --reconcile (each prints the next; the last routes back here)
Workers:   6 localize workers over 14 findings (N 6 remembered, effective 6), 3 fixers one at a time (opus) - 1 relocated, 0 blocked
Commit:    a1b2c3d  /sdlc:repair → 3 findings closed at prd/arch, 1 handed off
Status:    not finished - 1 open finding remains (FND-005)
Next:      /sdlc:repair FND-005   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this transcript.
```
