---
name: repair
description: >
  Explicitly invoked DIAGNOSTIC + REPAIR skill for the SDLC artifact chain.
  Runs a doctor sweep (every skill validator + the cross-artifact linter + the
  docs-index dangling-reference gate + provenance drift), merges it with the
  FND-NNN findings any stage raised (codegen, an interview skill, the user),
  then BACK-PROPAGATES every open finding to the earliest artifact whose
  content is actually wrong, fixes it there, and forward-propagates along the
  computed blast radius — surgically (edit + bump + re-slice, scripted), or by
  handing the user the exact downstream re-invocation sequence (each stage's
  --reconcile form; the walk's reasoning is left on the finding as handoff
  notes, and the chain routes itself). The session orchestrates: opus workers
  localize every finding in parallel, one plan gate orders the whole queue
  upstream-first, workers fix per artifact aggregate. Forms: /sdlc:repair
  (full flow), /sdlc:repair --check [--no-emit] [--provenance] (sweep only,
  edits no docs/ artifact), /sdlc:repair FND-003 FND-005 (named findings),
  /sdlc:repair --flag "<reason>" [--stage <stage>] [--path <id|schema_path>]
  (record a defect you noticed, then localize it). Hands back to /sdlc:code
  automatically: edited task artifacts change their fingerprints, so affected
  tasks show up as `stale` at the next codegen plan gate.
  Trigger only on /sdlc:repair or a direct natural-language request to
  diagnose/repair the sdlc artifact chain — never auto-trigger from a generic
  request to fix a bug or a failing test.
user-invocable: true
disable-model-invocation: true
model: opus
effort: xhigh
allowed-tools: Read Write Edit Bash Bash(ls *) Glob Grep Agent AskUserQuestion
---

# sdlc-repair

The pipeline's repair stage. Every other sdlc skill *writes forward*: it
consumes upstream artifacts and produces one more. This skill is the only one
that **walks backward** — from a defect that surfaced late (usually during
`/sdlc:code`, which is where under-specification finally becomes visible, but
just as legitimately from an interview skill reading its inputs, from the
doctor sweep, or from the user) to the stage that actually caused it — and then
carries the fix forward again.

It exists because the alternative is worse. Left to itself, an agent that hits
an underdetermined contract will patch what it can reach: the task embed, or
the generated code. Both re-diverge the next time anything regenerates, and
the real defect stays in ARCH or PRD, invisible, waiting.

**Outputs:**

- Edits to the artifact(s) under `docs/` that actually hold the defect, with
  `metadata` version bumps and changelog entries (via `bump_artifact.py`) and
  every task embed copied from a changed symbol re-sliced (via the `task`
  skill's `reslice_embeds.py`, full edition only).
- `.claude/skills-state/sdlc-findings.yaml` — the `FND-NNN` queue, with a
  `resolution` block per finding it closed (schema: `FINDINGS.schema.yaml`).
  Written only through `findings.py` and the Phase-6 resolution write.
- `.claude/skills-state/sdlc-repair.state.yaml` — session state, for resume;
  `.claude/skills-state/sdlc-repair/{localize,gate,inflight,reports}/` — the
  workers' reports and breadcrumbs (`references/orchestration.md`).
- A close report naming the stale tasks `/sdlc:code` will offer to rebuild.

It owns no `docs/` artifact of its own.

**This skill never writes `CLAUDE.md`.** That file belongs to `/sdlc:setup`, which
writes one static `## SDLC Documents` block. Never add a section, a bullet, a
note, an id, a status, a caveat or a resolution there — a caveat is a typed
`WRN-NNN` in the artifact it is about, a spec defect is an `FND-NNN`, a skill
defect is an `LSN-NNN`, and all of them surface, generated, in
`.claude/rules/sdlc-statusboard.md`.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — dispatch, the six phases, the gates. |
| `FINDINGS.schema.yaml` | Canonical schema for `.claude/skills-state/sdlc-findings.yaml` (version 2). |
| `validate_findings.py` | Pydantic v2 validator for the queue (+ id/resolution/propagation integrity, version-gated). `--stats` prints the suspected-vs-located matrix. |
| `findings.py` | The queue's ONLY writer: `add \| list \| plan \| reopen \| validate \| stats`. Every stage calls it as `python "${CLAUDE_SKILL_DIR}/../repair/findings.py"`; `setup` installs a copy at `.claude/sdlc/findings.py` for ambient sessions. Validates before it appends, dedupes, stamps recurrence; `plan` orders the open set into aggregates and stage-waves. |
| `doctor.py` | The sweep runner. `--quick` = cross-artifact linter only (what `/sdlc:code` runs at component boundaries); default = the full sweep; `--provenance` = upstream-hash drift; `--emit-findings [--warnings-as-findings]` records failures through `findings.py`. |
| `bump_artifact.py` | Bumps `metadata.<name>_version` and prepends the changelog line as one text-level edit (comments preserved); refuses an out-of-order changelog unless `--force`. Installed by `setup` at `.claude/sdlc/bump_artifact.py`. |
| `references/orchestration.md` | The two worker waves: briefs, report shapes, breadcrumbs, aggregates and their order, the plan gate, the drain between waves, the consolidated handoffs, the close card rows. Read by the session in Phase 2. |
| `references/back-propagation.md` | Finding → source stage, and the write set (Step 3½). Read by every localize worker; by the session when it walks inline. |
| `references/forward-propagation.md` | Surgical / additive / re-invoke, the scripted sequences, verification, the resolution write, handback. Read by every fix worker; by the session when it fixes inline. |
| `references/edge-cases.md` | Unusual situations, the sweep's labels, verification caveats. |
| `../prd/references/reporting-to-the-user.md` | How to report results to the user: the three verdict tags, translated (never pasted) findings, and the Phase-8 close card. Shared by every skill; read before Phase 6. |
| `../lesson/references/lessons-capture.md` | When a walk ends at the SKILL rather than an artifact (Phase 2 Step 0): the lessons routing table and raising conditions. |
| `_smoke/` | Validator fixtures (pinned by `expected.yaml`) + `bump_selftest.py`, `findings_selftest.py`, `doctor_selftest.py`, `orchestration_selftest.py` and the other prose pins. |
| `evals/` | Eval prompts; `evals/fixtures/<case>/` holds pre-edited copies of the demo docs. |

## Invocation dispatch

Classify `$ARGUMENTS`:

1. **No arguments** → **full flow**: sweep, merge with open findings, localize
   every one of them, plan, confirm once, fix, verify, hand back. Phases 1–6
   below. The run works EVERY open finding the extent answer covers, and it
   never stops at a handoff.
2. **`--check`** → **sweep only**: run the full doctor, print the report, stop.
   **Edits no artifact under `docs/`** — but it *does* append one finding per
   failed check to the queue (deduplicated), which is what makes the next
   `/sdlc:repair` pick them up. Add **`--no-emit`** for the CI / pre-flight
   form that records nothing (`doctor.py` without `--emit-findings`). Add
   **`--provenance`** to also list every artifact built against an upstream
   whose content has since changed (a warning, never a finding).
3. **One or more `FND-NNN` arguments** → work only those findings (they must
   exist in the queue and be `open` or `triaged`). Skips the sweep; everything
   else is identical. A `triaged` re-invoke finding named here is usually the
   end of its own chain — the last reconcile routes back with exactly this
   form — so check that first: `python "${CLAUDE_SKILL_DIR}/doctor.py"
   --docs-dir docs --provenance` prints `FND-NNN can be marked resolved` once
   every file it owed was rebuilt after the fix. Then verify the hops (Phase
   5) and close it (Phase 6) without localizing it again.
4. **`--flag "<reason>" [--stage <stage>] [--path <id|schema_path>]`** →
   **user intake**: the user noticed a defect. Mint the finding first —

   ```bash
   python "${CLAUDE_SKILL_DIR}/findings.py" add --raised-by user --detected-by "user/--flag" \
     --kind <best fit, default other> --summary "<reason, one line>" --evidence "<reason>" \
     [--suspected-stage <stage>] [--symbol <id>] [--field-path <schema_path>] [--file docs/<ARTIFACT>]
   ```

   (`--path` maps to `--symbol` when it is an id like `FR-012` / `TST-004` /
   `Entity`, to `--field-path` when it is a dotted schema path; use the
   artifact that owns that path as `--file`). Then enter Phase 2 **for that
   finding only** — no sweep — and continue through Phase 6. A duplicate of an
   open finding is reported, not re-minted; work the existing one.
5. Anything else → print the forms above and abort.

## Preconditions (a CLOSED set — do not invent gates)

- `docs/` exists and holds at least one artifact. Otherwise there is nothing to
  diagnose — point at `/sdlc:prd`.
- If `.claude/skills-state/sdlc-findings.yaml` exists, it must pass
  `python "${CLAUDE_SKILL_DIR}/validate_findings.py"` (warnings are fine; a
  version-1 file only warns on the version-2 checks). A corrupted queue is
  repaired first (that edit is in scope); no artifact is touched until it
  validates.
- Nothing else. Missing artifacts are *skipped checks*, not errors — this skill
  must be runnable at any pipeline stage, including halfway through. Draft
  status, dirty git trees, and incomplete stages are observations for the
  report, never grounds for refusal.

## The flow

### Phase 1 — Session & queue

Read `.claude/skills-state/sdlc-repair.state.yaml` if present. `in_progress`
→ offer resume / restart / discard. Load and validate the findings queue.
Prune `.claude/skills-state/sdlc-repair/localize/` and `reports/` left by an
earlier run that is `complete` or `aborted` (they are that run's audit trail,
not this one's input).

The state file's schema (written at the plan gate, updated after every
finding worked and every drain, kept as audit trail):

```yaml
session_id: <uuid4>
skill_version: <the skill_version at the end of this file>
started_at: <iso8601>
last_updated: <iso8601>
status: in_progress          # in_progress | complete | aborted
findings_worked: []          # FND ids resolved/triaged/wontfixed/deferred this session
current_finding: null
dispatch: agent              # agent | inline (the Agent tool was unavailable)
plan: {}                     # Phase 3: `findings.py plan --json` + extent, decisions,
                             #   per-aggregate status (planned | dispatched | done | relocated)
handoffs: []                 # Phase 6: the consolidated command chain, printed once
baseline_checks: {}          # Phase 2: {"<check name> <target>": <exit>} copied from
                             #   doctor.py --json, so Phase 5 can say "red before, red after"
provenance_drift: []         # Phase 2: the [stale] lines doctor.py --provenance printed
metrics: {}                  # run telemetry (CLAUDE.md 15): validator_runs,
                             # validator_failures, resumes, workers_dispatched
lesson_notes: []             # mid-run lesson scratch (CLAUDE.md 15): noted, never
                             # acted on mid-run; drained by the Phase-6 self-review
```

On resume, reconcile before continuing. An interrupted run leaves one of two
shapes on a finding, and both name the artifacts it had already edited: a
`triaged` re-invoke carries them in its resolution block's `artifacts_touched`,
and a surgical fix whose verification never ran leaves the finding `open` with
one evidence line naming them (Phase 6 — an `open` finding carries no
resolution block at all, and a `triaged` one only while a re-invoke is in
progress). Re-verify every artifact so named against disk before touching it.
The common failure mode here is re-applying an edit that already landed. The
`plan:` block, the breadcrumbs under `sdlc-repair/inflight/` and the reports
under `sdlc-repair/reports/` say where each aggregate stands
(`references/orchestration.md`, "Resume"): an aggregate with a report and a
written resolution is done, one with a breadcrumb is re-dispatched from its
last phase after its `files_written` hashes are re-verified, one with nothing
is dispatched fresh.

**The queue is re-read after every finding closes and after every stage-wave
drains.** A finding minted mid-run (`--raised-by sdlc-repair`: a defect a
worker surfaced beside the one it was fixing, whose decision this run can
obtain) is `open` in the queue this run owns, so the loop picks it up next —
it joins the next stage-wave's plan through a localize pass of its own (short:
the finding that minted it is most of the walk), its gate question offers
*decide it now* at position 1, and it lands in `findings_worked` like any
other. A run invoked with named findings (`/sdlc:repair FND-003`) works the
ones it minted too; they are not "other findings".

**`EXIT`** (any free-text field, any phase): persist the state file with
`status: aborted`, confirm which artifacts were already edited, run
`python .claude/sdlc/lessons.py record-run --skill repair --outcome aborted`
(skip silently if absent) after draining `lesson_notes` into `lessons.py add`
calls, and stop.

### Phase 2 — Sweep & localize (wave 1)

Run the doctor (bare; capture the numeric exit code — never read an exit status
after a pipe, CLAUDE.md §11). Two invocations, both cheap:

```bash
python "${CLAUDE_SKILL_DIR}/doctor.py" --docs-dir docs --emit-findings
python "${CLAUDE_SKILL_DIR}/doctor.py" --docs-dir docs --provenance --json > .claude/skills-state/sdlc-repair.doctor.json
```

The second is the **pre-run stale snapshot**: its `provenance.stale` lists
every artifact/upstream pair that already owed a reconcile before this run
wrote anything. Surgical step 5 stamps only pairs absent from it, and Phase 5
reads a leftover `--stale` row that is in it as that owed reconcile, not as a
missed stamp.

The first runs every skill validator against its canonical artifact, every
`TASKS__*.json` shard, `crosscheck_artifacts.py`, and the docs-index dangling
gate (the project's `.claude/sdlc/docs_index.py`, or the plugin's own copy —
read-only `--check`, never a regenerate — when none is installed, with a label
saying why); appends one finding per failed check, deduplicated, and reports
each check's captured exit code plus its `WARNINGS (N)` count. What each label
means — accepted deviance, `awaiting re-invocation per FND-NNN`, skipped —
is in `references/edge-cases.md`, "The sweep's labels"; a row labelled
awaiting is work a finding still owes and is never localized again.

Copy the second run's per-check exits into the state file's `baseline_checks`
and its `[stale]` lines into `provenance_drift`. A `[stale]` line is *not* a
finding — an artifact built against an older upstream is a known state whose
channel is the owning skill's §7 delta-review — but it is a fact Phase 4 needs
(see "hand-edits" in `references/edge-cases.md`).

**The open set** is every `open` finding plus every `triaged` one — the
sweep's new findings merged with the queue's existing ones, all raisers
(`sdlc-code`, any `sdlc-<skill>`, `sdlc-repair`, `user`). Assert it here with
`python "${CLAUDE_SKILL_DIR}/findings.py" list --open`, and it is re-asserted
at every stage-wave drain: a run ends when nothing in that set can still be
worked, never because the first handoff was printed. A run invoked with named
findings uses those instead.

**Close first.** The snapshot's `provenance.resolvable` hints (`FND-NNN can be
marked resolved`) name the `triaged` re-invoke findings whose downstream
artifacts have all been rebuilt since the fix: verify their hops (Phase 5) and
close them (Phase 6) before any wave — they need no walk.

**Wave 1 — localize.** Load `references/orchestration.md` now. Every finding
in the open set that carries no `resolution.located_stage` gets ONE read-only
worker (the Agent tool, `model: "opus"`, `run_in_background: true`, the whole
wave in one turn, five in flight, rolling) whose brief carries paths only —
the finding id and queue path, `references/back-propagation.md`, the index,
the snapshot, and the report path
`.claude/skills-state/sdlc-repair/localize/<FND>.yaml`. The worker walks,
computes the write set (Step 3½) and writes that one file; it edits nothing
and asks nothing. Without the Agent tool, walk them yourself, one at a time,
and say so on the card. While the wave runs,
`python "${CLAUDE_SKILL_DIR}/findings.py" plan` (no `--from`) prints the
provisional table from the queue's own fields; the exact one comes after the
wave. The shape of every walk, whoever runs it:

- walk **backwards** from where the finding surfaced to the earliest artifact
  whose content is wrong; a finding raised by an interview skill usually
  surfaced one stage *downstream* of its source (the raiser read the wrong
  thing, it did not write it);
- never localize to `code` UNLESS the owner table (`back-propagation.md` Step
  2) shows every upstream contract already states the fact correctly and the
  generated code alone diverges — then it is mis-raised: close `wontfix` with
  `located_stage: code` (the validator rejects that value at queue version 2
  on every OTHER status) and name the owning task(s) in `stale_tasks`, which
  `/sdlc:code`'s own plan gate reads to schedule the rebuild; never localize
  to a task **embed** (CLAUDE.md §9 — the artifact it was copied from is the
  source);
- read the upstream slice an embed was copied from and compare: same wrong thing
  → upstream is the source; different → the embed is merely stale;
- a finding stamped `recurrence_of: FND-NNN` was **repaired before**: say so at
  the gate, put `re-invoke` in position 1, and never refuse `surgical`;
- compute the blast radius — the write set — with `docs_index.py --refs` plus
  the token sweep (`back-propagation.md`, Step 3½), never by guessing; every
  `python .claude/sdlc/docs_index.py …` in this file runs the copy
  `${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks once
  per run, and the bare regenerate in Phase 5 is the exception that file names.

**Step 0 — is it the skill?** (CLAUDE.md 15). Sometimes the walk ends not at
a wrong artifact but at the *plugin itself*: a validator check the user
confirms is wrong (`validator_false_reject`), or an upstream output schema
with no field for what downstream needs (`schema_gap`). The fix then does NOT
live in this project — record a lesson
(`python .claude/sdlc/lessons.py add --skill <owning-skill> --kind …
--related FND-NNN`; skip silently if the helper is absent) and close the
finding `wontfix` with that reason. A worker reports it as `lesson`; the
session records it. Never bend a validator to accept an artifact, and never
patch any plugin file from inside a consumer project. Mid-run observations
that are not yet lessons go to `lesson_notes`, never to a detour.

**Read by slice, not by slurp.** The upstream artifacts are large; use
`docs/INDEX.yaml` line ranges (`.claude/rules/sdlc-docs-access.md`) to read only
the symbol under suspicion and its inbound sites.

### Phase 3 — Plan gate

When the wave has drained, build the table — never from memory:

```bash
python "${CLAUDE_SKILL_DIR}/findings.py" plan --from .claude/skills-state/sdlc-repair/localize \
  --doctor-json .claude/skills-state/sdlc-repair.doctor.json --json
```

It groups the findings into **aggregates** (write sets that share an
artifact, joined transitively, directory-aware, capped at five; two findings
on one located symbol become one, the later a `duplicate`) and orders them
into **stage-waves** by the pipeline stage of the located artifact, upstream
first (`prd → ux → design → data → api → arch → test → task`): an aggregate
downstream of another aggregate's write set waits for it even when the two
are disjoint, `related` and `recurrence_of` findings sit together, and the
close-first findings are already closed. That order is the dependency order
of the whole queue, and it is stated here once (`references/orchestration.md`
holds the mechanics).

Then ONE `AskUserQuestion`, with the whole table inside it (AUTHORING's channel
rule: what a decision depends on rides in the call, in the recommended
option's `preview`, never in chat markdown the same turn):

- the **extent** ladder, single-select — *all N aggregates, in wave order*
  at position 1 with the full table as its `preview`; *the first stage-wave
  only*; *the first aggregate only*. "Other" carries the per-finding
  dispositions in the Quick-reference vocabulary (`all except FND-…`,
  `defer FND-…: <reason>`, `wontfix FND-…`, `accept-as-is FND-…
  (expected_count N)`, `it's the skill FND-…`, `it's the generated code
  FND-…`);
- one question per **missing decision** — a finding whose walk would route
  to `re-invoke` for want of ONE decision this run can take (which component
  owns a new unit, what it is called, which of two contradictory values is
  right): the worker's proposal at position 1 with its `basis`, *hand it off*
  last. Answered, the finding is authored in this run (`additive`); declined,
  it is a handoff and the run carries on. Four per call; a fifth goes in a
  second call before wave 2.

Per finding the table shows the **walk** (surfacing site → stages examined →
chosen source → why), the proposed mode (`surgical` / `additive` /
`re-invoke`), the write set, and `repaired before as FND-NNN` when it applies.
Position 1 of a mode is *re-invoke* for a recurrence, *fix fully — author the
new item(s) here* whenever the fix changes the downstream SET and the
four-part additive criterion in Phase 4 holds (offered, never argued for).

**When both rules claim position 1** — the finding is a recurrence *and* its fix
meets the four-part additive criterion — *fix fully* takes position 1. The
recurrence default changes which mode leads, never which modes are offered
(`references/forward-propagation.md` says exactly that: "never a refusal of the
in-run modes, just a changed default"), while the additive rule rests on a
measured cost — routing a fully-determined item to `re-invoke` costs the user
two interviews and discards the walk.

`references/back-propagation.md` names when to **ask rather than decide**:
`missing_requirement` findings, two equally defensible stages, any fix that
changes product behaviour rather than clarifying a description, and any walk
that terminates at PRD — those are the missing-decision questions above, never
silent choices. Record every answer in
`.claude/skills-state/sdlc-repair/gate/answers.yaml` and the state file's
`plan:` before the first dispatch.

`EXIT` in any free-text field stops the run (Phase 1 rules).

### Phase 4 — Fix at the source (wave 2)

Three modes, chosen by two questions: does the fix change the **set** of
downstream items, or only their **content**? And when the set — is the change
**purely additive and fully determined** by the walk just performed?

**Once a finding is localized and the fix is expressible in the artifacts,
FIX IT in this run.** The localization table is a map of where the *source*
is, not a routing table for who fixes it. Hand a fix downstream (`re-invoke`)
only when it needs a decision this run cannot get — and a modelling choice
inside the located artifact itself (which component owns a new work_unit,
what it is called) is one this run CAN get: ask it at Phase 3, then write it.
A new finding is cheap to write and expensive to redeem: the next skill re-derives the cross-artifact
walk cold, with no guarantee of the same reading.

**Wave 2 — fix.** One worker per aggregate (`model: "opus"`, one turn per
stage-wave, five in flight, rolling), briefed with paths: the aggregate's
localize reports, `gate/answers.yaml`, `references/forward-propagation.md`,
the snapshot, and a **write boundary** = the aggregate's write set — nothing
else, ever. Inside the aggregate the worker runs each finding's sequence
below SERIALLY, each one's verification (Phase 5) before the next starts —
never interleave two findings' sequences, so each stamp claims only what its
own sequence reviewed — and writes a breadcrumb after every phase and a
report per finding (`.claude/skills-state/sdlc-repair/reports/<FND>.report.yaml`).
Disjoint aggregates of one stage-wave run in parallel; the next stage-wave
starts only after the previous one drained (Phase 5). A worker never asks: a
decision the gate did not take is reported `blocked` with the question, and
a walk that proves wrong mid-fix is reported `relocated` with the artifact it
points at, nothing edited — the session re-plans it or names it on the card.
**The reconcile chain is never printed here**; a re-invoke records its owed
commands in the report and the session prints the consolidated chain once, at
close. Without the Agent tool, run the sequences yourself in plan order.

- **`surgical`** (content) — scripted, in this order, no hand edits to any
  task JSON:
  1. edit the source slice (`Edit`, by `INDEX.yaml` line range);
  2. `python "${CLAUDE_SKILL_DIR}/bump_artifact.py" --file docs/<SOURCE> --summary "<what changed>" --by sdlc-repair`
     (version bump + changelog line in one write; it refuses an out-of-order
     changelog — fix the changelog, do not `--force` blindly). A TASKS source
     takes `--patch`: its minor version gates task checks, and a minor bump
     would switch them on for tasks this fix never touched. A `brief` source
     — the walk ended outside the pipeline, at a hand-written document no
     skill owns — carries no `metadata` block, so this step **does not
     apply**: edit the brief, then propagate into every artifact that reads it
     and name each one in `artifacts_touched`;
  3. re-derive any prose the change invalidated (CLAUDE.md §8);
  4. walk the rest of the checklist by hand — every inbound site that is not a
     task embed is edited (with its own bump), unaffected (`how`), or
     deferred (`reason`) — each a `sites_considered` entry. When the fix
     retires, renames, or ADDS a named token, sweep the corpus for it first
     (`grep -rn <token> docs/` — a text search, never the index's symbol-only
     `--find`) and add every hit: the sibling test or prose restatement in
     the file just edited is the typical miss (`back-propagation.md`, "Token
     sweep");
  5. `python .claude/sdlc/docs_index.py --stamp docs/<artifact> --upstream docs/<reviewed-upstream> --hold-upstream docs/<other-recorded-upstream>`
     (one flag per file; each flag takes exactly one) for every artifact
     reconciled by hand, upstream-first — a stamp moves the stamped file's own
     hash, and it must land BEFORE the re-slice, which stamps the shard
     against the upstream bytes it sees. Run it through the copy
     `${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks:
     `--hold-upstream` needs `docs_index.py` capability 6, and an older
     install rejects it with exit 2 (the plugin's form is
     `"${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs`).
     **`--upstream` only for a pair that was fresh before this run's first
     write.** A stamp claims that EVERY delta between the recorded upstream
     and the current one was reviewed, and this sequence reviewed one
     finding's change. It also re-hashes EVERY upstream the artifact already
     records, so every other entry in its `metadata.upstream_provenance`
     takes `--hold-upstream`, which leaves that entry byte-identical: an
     upstream this run did not review, and a pair the Phase 2 snapshot
     (`sdlc-repair.doctor.json`, `provenance.stale`) already listed — such a
     pair owes an older, unreviewed delta to `/sdlc:<skill> … --reconcile`,
     and stamping it now would forge that review (the session's re-stamp of
     a `re-stamp only` row between waves is the one exception, and it holds
     every other upstream the same way). An artifact with no fresh reviewed
     pair is not stamped at all; a held pair goes in the report's
     `held_pairs`. **Then read what the stamp printed:** a `re-stamped
     <upstream>: … since the last stamp - reviewed by this run?` line names
     an upstream it re-hashed that had moved. For an upstream this sequence
     reviewed that is expected; for any other a hold is missing, so restore
     the artifact's old record of that upstream from git (`git diff
     docs/<artifact>` shows the old lines), confirm `--drift docs/<artifact>`
     names that upstream again, and stamp again with the hold. The printout
     catches a missing hold after the fact; the holds are what prevent the
     forgery (`forward-propagation.md`, "What a stamp claims");
  6. `python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --symbol <cid>/<component>/<work_unit>` (edition-ok: demo edition skips it — see below)
     (or `--tst TST-NNN` / `--entity <Name>` / `--operation <operation_id>`)
     — LAST, so the shard is stamped against the final upstream bytes; it
     re-slices every embed copied from the changed symbol, bumps the shard,
     refreshes its `upstream_provenance` and prints the moved task ids.
     **Add `--hold-stamp docs/<upstream>` for every pair the Phase 2 snapshot
     listed**: the embed still moves (a mechanical copy, not a review), but
     the shard's stamp for that upstream stays, so the owed `--reconcile`
     still sees the whole delta. A pre-existing embed drift on such a pair is
     a baseline failure for Phase 5, not this run's to clear;
  7. verify (Phase 5), exit codes captured into the report;
  8. `python "${CLAUDE_SKILL_DIR}/../code/topo_order.py" --scope <cid> --state .claude/skills-state/sdlc-code.state.yaml` (edition-ok: demo edition skips it — see below)
     plus `--affected <FR-NNN…>` for a PRD change → `stale_tasks` in the
     report (stale + affected, with the reason recorded).

  Steps 6 and 8 call the `task` and `code` skills. In the **demo edition**
  (`${CLAUDE_SKILL_DIR}/../task/SKILL.md` absent) there is nothing to re-slice
  or schedule: skip both and say so. A project that still has
  `docs/TASKS*.json` from an earlier full-edition install owes that re-slice —
  name it in the close card's `Attention:` row; never edit a task file by hand
  instead.
- **`additive`** (set, fully determined) — the fix **adds** downstream items
  and nothing else, and the walk already determined every field they need.
  All four must hold, or the mode is `re-invoke`:
  1. **purely additive** — no item is removed, renamed or re-scoped;
  2. **fully determined** — every field the new item's schema requires follows
     from facts in hand (the source slice, its siblings, the walk, a decision
     the plan gate took); no interview question is left. A field you would
     have to *decide* (a tier the strategy never uses, a behaviour the PRD
     never stated, a name nobody chose) fails this — unless the gate decided
     it, in which case the answer is copied verbatim, never re-decided;
  3. **validator-provable** — after the write, each touched artifact's
     `validate_schema.py`, `reslice_embeds.py --check` and `doctor.py --quick`
     are green, bare, with captured exit codes (Phase 5);
  4. **the obligation chain closes in this run** — a new TST obliges its
     realizing `kind: test` task, wired per checks 27/28; a new work_unit
     obliges its impl task AND a test naming it in `targets_work_units` (or a
     structured deferral); a new entity obliges its traces. Every link must
     itself pass 2 — one undetermined link makes the whole fix `re-invoke`.

  Mechanics (`forward-propagation.md`, "Additive mode"): steps 1–2 of
  `surgical` on the source; then author each new item directly in its own
  artifact — a new task's embed is *copied* from the source slice and proven
  byte-identical by `reslice_embeds.py --check`; `bump_artifact.py` every
  touched artifact; then **stamp, exactly as `surgical` step 5 prescribes** —
  `docs_index.py --stamp` each artifact this mode authored into, against the
  upstream it authored from, upstream-first, `--hold-upstream` for every other
  recorded upstream, then read the `re-stamped …` printout; a pair the Phase 2
  snapshot listed stays held. Verify (Phase 5). Close `resolved` with `mode:
  additive`, `artifacts_touched` naming every file, one `source` hop and one
  `downstream` hop per authored item, and `downstream_rerun: []` — nothing is
  owed downstream; if something is, the mode was `re-invoke`.

  A finding that splits into a **mechanical half and a modelling half** is
  fixed in one run when the modelling half passes 1–4: `surgical` on the
  first, `additive` on the second, one resolution block naming both. When the
  modelling half fails 2 only for want of a decision this run CAN obtain (a
  choice inside the located artifact — which of two contradictory values is
  right, which component owns a unit, what it is called), it does not leave
  this run: the gate asked it (Phase 3), or the worker reports it `blocked`
  and the session asks it at the drain. A defect the worker surfaces BESIDE
  the one being fixed is minted (`findings.py add … --related FND-NNN
  --raised-by sdlc-repair`, by the session, from the report's `lesson`-like
  line) so the audit trail has it, and it joins THIS run's queue — Phase 1
  re-reads the queue after each finding closes and after each drain, and
  works it through the same gate, *decide it now* at position 1. Only a half
  whose decision is not this run's to take (`references/back-propagation.md`,
  "ask — do not decide alone": a `missing_requirement`, a product-behaviour
  change, a walk ending at PRD) becomes a handoff, and the card says so.
- **`re-invoke`** (set, not determined) — changes to the *set* of downstream
  items that fail the additive criterion: a removed/renamed component,
  work_unit, entity, operation, surface, TST or task; a restructured boundary;
  a new item whose content needs an interview the gate declined to settle.
  Fix the source (steps 1–2) — the located artifact is always edited HERE,
  never handed to its own `--reconcile`: a reconcile reviews what moved
  upstream of its artifact, so pointed at the file just localized it finds no
  delta and the handoff note has no card to land on. Then record — never
  print — the downstream command sequence, starting at the first stage BELOW
  the source, every consumer stage's `--reconcile` form, container-scoped on
  arch/test/task, the full interview only as the fallback, and
  **`/sdlc:test <cid>` before `/sdlc:task <cid>` whenever work_units were
  minted** (`forward-propagation.md`, "Re-invoke mode"). Leave the walk's
  reasoning on disk as `resolution.handoff` — one entry per downstream item
  you already have a view on: `{artifact: docs/<a file an owed command
  rewrites>, key: <the item as docs_index.py --drift prints it, or null for
  the whole file>, note: <why it moved and what you propose>, basis:
  measured | inferred}`, `retired: [<token>…]` when a token goes; each
  reconcile reads its notes (`findings.py list --owed-by`) and offers them as
  its card's position-1 proposal. **Always** record the sequence in
  `resolution.downstream_rerun` (the queue validator requires it for
  `re-invoke`), record `artifacts_touched` so far, and leave the finding
  `triaged` — a triaged finding may carry exactly this partial resolution
  block — until the user reports the re-invocations done (or `doctor.py
  --provenance` says they were). This skill never runs those skills: they
  are interviews and the user owns them; the chain routes itself and the
  last reconcile returns to `/sdlc:repair FND-NNN` to close.

When in doubt between `surgical` and the set modes, prefer a set mode: a
surgical edit that should have changed the set leaves a downstream artifact
internally consistent but missing an item, and no coverage gate catches an
item that was never created. Between `additive` and `re-invoke`, "in doubt"
means a criterion actually fails — not that the change feels big. Routing a
fully-determined item to `re-invoke` costs the user two interviews and
discards the only cross-artifact context the pipeline builds.

### Phase 5 — Verify, per finding and per stage-wave

Every fix worker re-runs these **bare**, capturing every numeric exit code
into its report, after each finding. Pass the **system file** of each touched
family — the validators glob their own `__<slug>` siblings, and a shard path
is refused:

```bash
python "${CLAUDE_SKILL_DIR}/../arch/validate_schema.py" --path docs/ARCH.yaml
python "${CLAUDE_SKILL_DIR}/../test/validate_schema.py" --path docs/TEST-STRATEGY.yaml                  # edition-ok: demo edition skips this line, and says so (Phase 4)
python "${CLAUDE_SKILL_DIR}/../task/validate_schema.py" --path docs/TASKS.json                           # edition-ok: demo edition skips this line, and says so (Phase 4)
python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --container <cid> --all --check   # edition-ok: demo edition skips this line, and says so (Phase 4)
python "${CLAUDE_SKILL_DIR}/../task/crosscheck_artifacts.py" --docs-dir docs                             # edition-ok: demo edition skips this line, and says so (Phase 4)
python .claude/sdlc/docs_index.py                 # regenerate the index - the PROJECT's copy only
python .claude/sdlc/docs_index.py --check         # dangling-reference gate
python .claude/sdlc/docs_index.py --stale         # must list nothing this run reconciled - a row here is a missed stamp,
                                                  # the `re-stamp only` rows included (nothing the shard cites changed, so
                                                  # the review is cheap - but the stamp is still owed), unless the Phase 2
                                                  # snapshot already held it (a pre-existing pair, owed to its own
                                                  # --reconcile: name it on the close card, never stamp it)
```

The `test` and `task` lines run only where those skills ship; in the demo
edition skip them and say so. The regenerate line runs only through the
project's installed copy — absent, skip it and say so; never the plugin's
copy bare (`references/edge-cases.md`, "Verification").

**The drain.** When every worker of a stage-wave has reported, the session —
before dispatching the next wave (`references/orchestration.md`, "Between
waves"): reads each report's exit codes against `baseline_checks`; runs
`python "${CLAUDE_SKILL_DIR}/doctor.py" --docs-dir docs --quick` and
`python "${CLAUDE_SKILL_DIR}/validate_findings.py"` bare; re-stamps every
row `docs_index.py --stale` marks `re-stamp only` that no pending aggregate
holds — the session does this, with `--hold-upstream` for every other
recorded upstream, because such a row's review is empty and the claim true —
pre-existing ones right after the gate, wave-caused ones now; re-reads the
queue; and asks the user each `blocked` report's question (four per call),
re-dispatching that finding with the answer, while a `relocated` report is
re-planned into a later aggregate or listed on the card's `Remaining:` row.
A downstream wave dispatched before an upstream drain would stamp its shard
against upstream bytes still moving.

Validate **every artifact touched**, not just the source. Compare each exit
against `baseline_checks`: a check that was already red before this repair, for
an unrelated reason, is reported with its before/after exit codes and called
out as pre-existing. Never let an unrelated red read as caused by the repair,
and never claim a repair fixed something it did not touch.

If verification cannot run at all, nothing is marked `resolved`.

### Phase 6 — Close & hand back

**Resolutions are written from the reports, never from memory.** For each
finding, copy `.claude/skills-state/sdlc-repair/reports/<FND>.report.yaml`
into its `resolution` block (`by`, `at`, `located_stage`, `mode`,
`artifacts_touched`, `downstream_rerun`, `stale_tasks`, `fields_changed` /
`symbols_changed` when known, `sites_considered` when required, `summary`)
**and its `propagation` hops** — one per place the fix had to land, each
with `verified_at` and `how`:

```yaml
propagation:
  - {hop: source, target: docs/ARCH__demo-api.yaml, verified_at: <now>, how: "arch/validate_schema exit 0"}
  - {hop: embed,  target: "docs/TASKS__demo-api.json#TSK-004.interface_contract", verified_at: <now>, how: "reslice_embeds.py --check exit 0"}
```

`resolved` requires every listed hop verified (queue version 2). A hop the
worker could not verify means the finding does not close, and where it waits
depends on the mode: a `re-invoke` keeps its block and stays `triaged`, while a
`surgical` fix leaves the finding `open` with no resolution block at all —
only a re-invoke in progress may record partial progress on a triaged finding,
and `validate_findings.py` makes that an error at *every* queue version, so
parking a surgical fix there is a rejected write, not a park. Record what did
land as one evidence line on the finding itself (`evidence` holds at most five
lines — fold it into the last one when the list is full): the artifacts already
edited, and the check that could not run. That line is what the next run
re-verifies against disk (Phase 1) and what the statusboard prints under the
still-open finding. Set the queue's `last_updated` and re-validate it with
`validate_findings.py`; delete the finding's breadcrumb once its resolution
is written.

**Write it right the first time** — the rules the validator enforces beyond
the example (the `hop` enum, `duplicate_of`, the `handoff` shape,
`sites_considered`, `validate --upgrade`) are in
`references/forward-propagation.md`, "The resolution write". Two of them
decide where a finding waits:

- `mode: additive` carries `downstream_rerun: []`, at least one
  `hop: downstream` (the item it authored), and every artifact it wrote into
  in `artifacts_touched`. An additive resolution that owes a re-run, or that
  records no downstream hop, is refused from `findings_file_version: "2"`;
  below that version the validator states the gate in its own note ("it blocks
  from findings_file_version 2") rather than failing the file.
- `mode: re-invoke` names its command sequence in `downstream_rerun`; empty
  means the propagation never happened, which is not a resolution. **This
  skill never closes a re-invoke finding `resolved` with an empty
  `downstream_rerun`, at any queue version.** The validator blocks it only
  from `findings_file_version: "2"` (CLAUDE.md §10 keeps a legacy queue from
  turning red on upgrade), so on a version-1 queue the warning scrolls past
  unread — one project closed ten such findings and four of them hid real
  unpropagated defects, one for three weeks. So take the sequence from the
  report and fill `downstream_rerun` in this same write, then keep the finding
  `triaged` until the user reports those runs done. A re-invoke whose sequence
  the worker could not compute carries no resolution block at all — an empty
  one is the state that hid those defects.

**The consolidated handoffs.** Build the command chain once, from every
report's owed commands plus every already-`triaged` finding's recorded
sequence — deduplicated, in pipeline order, test before task, container-scoped
(`references/orchestration.md`, "The consolidated handoff chain") — write it
to the state file's `handoffs:`, print it once above the card, and put the
count and the FIRST command on the card's `Handoffs:` row. Nothing prints a
reconcile command anywhere else in the run.

Then compute the handback. There is no bespoke mechanism and there should not
be: editing a task artifact changes each affected task's fingerprints, which
`/sdlc:code` already classifies as `stale`, `ring_recheck` or `refreshed` and
gates at its plan approval; `topo_order.py`'s `stale` and `--affected`
sections are already in `resolution.stale_tasks` from the reports.

**Record the run** (CLAUDE.md 15): drain `lesson_notes` (one `lessons.py add` per surviving
note, at most 2 unless one is a blocker), then `python .claude/sdlc/lessons.py record-run --skill repair --plugin-root "${CLAUDE_SKILL_DIR}/../.."`
(best-effort: a non-zero exit is one line in the report; helper absent — skip silently). A `Lessons:`
row only when one was recorded — never "no lessons". Then set the state file `status: complete`.

**Commit the run** (CLAUDE.md 20; the message rules and what is staged:
`${CLAUDE_SKILL_DIR}/../setup/references/auto-commit.md`) — the last action before the card, on every exit path, never a blocker:
`python .claude/sdlc/autocommit.py commit --skill repair --invocation "<the form the dispatch resolved, as typed>" --summary "<one line: what changed, in the user's words>"`
Its one printed line is the card's `Commit:` row; off, or helper absent → no row.

Close with the report:

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
Commit:    {a1b2c3d  /sdlc:repair → <summary> | nothing to commit — only when auto-commit is on}
Status:    {computed - e.g. not finished - 1 open finding remains (FND-005)}
Next:      {the computed next invocation}   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript.
```

**The `Findings:` row** translates each finding's queue state into what is
done and what is still owed — the table is in `references/orchestration.md`,
"The close card"; the queue's own state and field names are input to the row,
never its text (`prd/references/reporting-to-the-user.md`, "translates; it
never pastes"). Collapse same-state findings into one phrase listing their
ids, and keep "closed" and "still owes" apart. **`Remaining:`** names every
finding that was open when the run started and was not worked, each with its
reason (*outside the chosen extent* / *relocated to <stage> after that wave
closed* / *its worker stopped on a question the run could not answer*) — it
prints only when non-empty, and it is what makes a narrowed run honest.
**`Handoffs:`** prints only when re-runs are owed: the count, the findings, the
first command. `Workers:` says what was dispatched, on which model, and how
many relocated or blocked (or `inline - the Agent tool was unavailable`).

`Status:` — first match wins, always printed:

1. **A finding is not closable or not verified** → `not finished - <FND-NNN>
   <what is missing>`; `Next:` re-invokes this skill naming it (the shared
   procedure's rule 1).
2. **Open findings were left unworked** (the `Remaining:` row is non-empty) →
   `not finished - N open finding(s) remain (<ids>)`.
3. **A finding still owes re-runs** → `repair's edits are done; N re-run(s)
   owed across M finding(s) - you run them, one per new session, starting
   with Next:`. This skill never runs them (Phase 4).
4. **Every OPEN finding is closed, parked or handed off** → `done - <the stage
   that was blocked> can run` (or `done - nothing is blocked` when no stage
   was).
5. **`--check`** → `health check only - nothing under docs/ was edited`.

**Compute the `Next:` row; never copy the example literals.** Procedure and
successor map: `${CLAUDE_SKILL_DIR}/../prd/references/reporting-to-the-user.md`
(CLAUDE.md 14). `repair` walks backwards, so its `Next:` is an **in-run
position** (the located stage) while work remains, and the pipeline position
once the run is done — print both as they apply, first match wins:

- **A finding is not closable or not verified** → `/sdlc:repair FND-NNN`, after
  saying what it lacks.
- **An open finding was left unworked** → `/sdlc:repair FND-…` naming the
  `Remaining:` ids (the shared procedure's rule 2: open findings name
  artifacts this run consumed). This bullet ranks BEFORE the re-run one — a
  reconcile is never recommended while a finding waits unworked.
- **A finding still owes re-runs** → the FIRST command of the consolidated
  chain, with its position and the terminus in words — one command on the
  row, never the chain, e.g.
  `/sdlc:test demo-api --reconcile   (1 of 2 owed for FND-004 - each prints the next; the last routes back here to close it)`.
- **All open findings resolved** → `/sdlc:code <container>`, the stage that was
  blocked; add the one-line consequence (`2 tasks are now stale and will be
  offered for regeneration`).
- **Nothing was fixed** (`--check`, or every finding `wontfix`/`deferred`) →
  say the docs are clean (or what stays parked) and name no command.

**The recommended loop**, for the user who asks "what do I run next time", is
in `references/forward-propagation.md`, "Batching": pre-flight `--check
--no-emit`, codegen to a component boundary, ONE `/sdlc:repair` over the whole
batch, the printed chain only when printed, codegen again in a new session.

Every target must have a `sdlc/skills/<name>/SKILL.md`; never route to
`/sdlc:deploy`, which is planned and not yet implemented.

## Hard boundaries

- **Never writes source code** and never touches the generated tree. Code
  defects are `/sdlc:code`'s heal loop, not findings.
- **Never runs another skill.** `re-invoke` records a command sequence and
  leaves its reasoning in `resolution.handoff`; the session prints the chain
  once at close, and it routes itself through each reconcile's `Next:`.
- **Never edits `.claude/skills-state/sdlc-code.state.yaml`.** The `stale`
  handback works precisely because that ledger is left alone.
- **Never patches a task embed.** Embeds move only through
  `reslice_embeds.py`, from a corrected source (CLAUDE.md §9). A NEW task's
  embed (`additive` mode) is written as a copy of the source slice and proven
  identical by `reslice_embeds.py --check` before the finding closes.
- **Never writes the findings queue except through `findings.py` and the
  Phase-6 resolution write**, and never marks a finding `resolved` without a
  verified resolution block — the queue validator enforces both.
- **Never deletes an artifact item implicitly.** Deletion changes the downstream
  item set, so it is a `re-invoke` case requiring explicit approval that names
  what disappears and what references it.
- **A worker never edits outside its write boundary**, never asks the user,
  and never writes the queue, the state file or `docs/INDEX.yaml`; only the
  session does (`references/orchestration.md`, "What the session never
  delegates").

## Model policy

**opus / xhigh** (frontmatter), and deliberately so. This is the one skill whose
core operation is cross-artifact archaeology: holding eight artifacts' semantics
in view at once and deciding which of them is *actually* wrong. It is the
opposite regime from `/sdlc:code`'s manager (sonnet/high bookkeeping), which is
exactly why the two are separate skills rather than one — running this reasoning
inside the codegen manager would both mis-model the work and consume the very
context that codegen is trying to conserve. The workers are opus for the same
reason, and they exist for context isolation, not speed: every walk and every
fix transcript stays in its worker, so the session's window holds the plan of
the whole queue instead of the first four findings' archaeology.

## Quick reference: user inputs at gates

| Input | Effect |
|---|---|
| `EXIT` | Stop; state persisted as `aborted`, edits so far confirmed and named, run recorded. |
| *all N aggregates, in wave order* | The whole open set, upstream first (position 1). |
| *the first stage-wave only* / *the first aggregate only* | A prefix of that order; the rest is named on `Remaining:` with `/sdlc:repair FND-…` as `Next:`. |
| *fix as proposed* | Apply the localization and fix shown. |
| *fix fully* | `additive` mode: author the new downstream item(s) in this run (criterion in Phase 4); the finding closes `resolved` with `mode: additive`. |
| *fix differently* | Free text — your localization or fix overrides the proposal. |
| *hand it off* | The missing decision stays with the owning skill's interview; the finding is a re-invoke and joins the consolidated chain. |
| *defer* | Finding → `deferred` (mode none + reason); TASKS items go in the artifact's `deferrals` list. |
| *accept as-is* | Finding → `wontfix` with `expected_count: N`; the doctor reports the check as accepted until the count moves. |
| *wontfix* | Close with the reason; no artifact is touched. |
| *it's the skill* | Record a lesson (`--related FND-NNN`); finding → `wontfix`. |
| *it's the generated code* | Every upstream contract is right and only the code diverges: `wontfix` with `located_stage: code`, the owning tasks in `stale_tasks`. |

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.23"
