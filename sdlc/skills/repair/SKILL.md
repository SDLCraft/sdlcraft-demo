---
name: repair
description: >
  Explicitly invoked DIAGNOSTIC + REPAIR skill for the SDLC artifact chain.
  Runs a doctor sweep (every skill validator + the cross-artifact linter + the
  docs-index dangling-reference gate + provenance drift), merges it with the
  FND-NNN findings any stage raised (codegen, an interview skill, the user),
  then BACK-PROPAGATES each finding to the earliest artifact whose content is
  actually wrong, fixes it there, and forward-propagates along the computed
  blast radius — surgically (edit + bump + re-slice, scripted), or by handing
  the user the exact downstream re-invocation sequence (each stage's
  --reconcile form; the walk's reasoning is left on the finding as handoff
  notes, and the chain routes itself). Forms: /sdlc:repair
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
allowed-tools: Read Write Edit Bash Bash(ls *) Glob Grep AskUserQuestion
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
  every task embed copied from a changed symbol re-sliced (via
  `../task/reslice_embeds.py`).
- `.claude/skills-state/sdlc-findings.yaml` — the `FND-NNN` queue, with a
  `resolution` block per finding it closed (schema: `FINDINGS.schema.yaml`).
  Written only through `findings.py` and the Phase-6 resolution write.
- `.claude/skills-state/sdlc-repair.state.yaml` — session state, for resume.
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
| `findings.py` | The queue's ONLY writer: `add \| list \| validate \| stats`. Every stage calls it as `python "${CLAUDE_SKILL_DIR}/../repair/findings.py"`; `setup` installs a copy at `.claude/sdlc/findings.py` for ambient sessions. Validates before it appends, dedupes, stamps recurrence. |
| `doctor.py` | The sweep runner. `--quick` = cross-artifact linter only (what `/sdlc:code` runs at component boundaries); default = the full sweep; `--provenance` = upstream-hash drift; `--emit-findings [--warnings-as-findings]` records failures through `findings.py`. |
| `bump_artifact.py` | Bumps `metadata.<name>_version` and prepends the changelog line as one text-level edit (comments preserved); refuses an out-of-order changelog unless `--force`. Installed by `setup` at `.claude/sdlc/bump_artifact.py`. |
| `references/back-propagation.md` | Finding → source stage. The localization rules. Read in Phase 2. |
| `references/forward-propagation.md` | Blast-radius checklist, surgical vs re-invoke, the scripted surgical sequence, verification, handback. Read in Phase 4. |
| `references/edge-cases.md` | Unusual situations. |
| `../prd/references/reporting-to-the-user.md` | How to report results to the user: the three verdict tags, translated (never pasted) findings, and the Phase-8 close card. Shared by every skill; read before Phase 6. |
| `../lesson/references/lessons-capture.md` | When a walk ends at the SKILL rather than an artifact (Phase 2 Step 0): the lessons routing table and raising conditions. |
| `_smoke/` | Validator fixtures (pinned by `expected.yaml`) + `bump_selftest.py`, `findings_selftest.py`, `doctor_selftest.py`. |
| `evals/` | Eval prompts; `evals/fixtures/<case>/` holds pre-edited copies of the demo docs for cases 3 and 4. |

## Invocation dispatch

Classify `$ARGUMENTS`:

1. **No arguments** → **full flow**: sweep, merge with open findings, localize,
   confirm, fix, verify, hand back. Phases 1–6 below.
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

The state file's schema (written on first gate, updated after every finding
worked, kept as audit trail):

```yaml
session_id: <uuid4>
skill_version: <the skill_version at the end of this file>
started_at: <iso8601>
last_updated: <iso8601>
status: in_progress          # in_progress | complete | aborted
findings_worked: []          # FND ids resolved/triaged/wontfixed/deferred this session
current_finding: null
baseline_checks: {}          # Phase 2: {"<check name> <target>": <exit>} copied from
                             #   doctor.py --json, so Phase 5 can say "red before, red after"
provenance_drift: []         # Phase 2: the [stale] lines doctor.py --provenance printed
metrics: {}                  # run telemetry (CLAUDE.md 15): validator_runs,
                             # validator_failures, resumes
lesson_notes: []             # mid-run lesson scratch (CLAUDE.md 15): noted, never
                             # acted on mid-run; drained by the Phase-6 self-review
```

On resume, reconcile before continuing. An interrupted run leaves one of two
shapes, and both name the artifacts it had already edited: a `triaged`
re-invoke carries them in its resolution block's `artifacts_touched`, and a
surgical fix whose verification never ran leaves the finding `open` with one
evidence line naming them (Phase 6 — an `open` finding carries no resolution
block at all, and a `triaged` one only while a re-invoke is in progress).
Re-verify every artifact so named against disk before touching it. The common
failure mode here is re-applying an edit that already landed.

**The queue is re-read after every finding closes.** A finding minted mid-run
(`--raised-by sdlc-repair`, Phase 4: a defect the walk surfaced beside the one
being fixed, whose decision this run can obtain) is `open` in the queue this
run owns, so the loop picks it up next — its Phase 2 walk is short (the
finding that minted it is the localization), its Phase 3 gate offers *decide
it now* at position 1, and it lands in `findings_worked` like any other. A run
invoked with named findings (`/sdlc:repair FND-003`) works the ones it minted
too; they are not "other findings" (ledger IMP-153).

**`EXIT`** (any free-text field, any phase): persist the state file with
`status: aborted`, confirm which artifacts were already edited, run
`python .claude/sdlc/lessons.py record-run --skill repair --outcome aborted`
(skip silently if absent) after draining `lesson_notes` into `lessons.py add`
calls, and stop.

### Phase 2 — Sweep & localize

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
missed stamp (ledger IMP-099).

The first runs every skill validator against its canonical artifact, every
`TASKS__*.json` shard, `crosscheck_artifacts.py`, and the docs-index dangling
gate (the project's `.claude/sdlc/docs_index.py`, or the plugin's own copy -
read-only `--check`, never a regenerate - when none is installed, with a label
saying why); appends one finding per failed check (deduplicated
against every open, triaged, wontfix, deferred and duplicate finding, keyed on
the check and the count-stripped first defect line — so a re-sweep never piles
up copies and never re-mints something a person dismissed); and reports each
check's captured exit code plus its `WARNINGS (N)` count. Only lines under a
blocking section become findings; a validator's warnings never do unless you
pass `--warnings-as-findings` (the cross-artifact subset: task `[check 20]`
embed drift, `[check 23]` built-but-test-deferred, ux/arch warnings that name
another artifact). A `wontfix` finding whose summary carries
`expected_count: N` for a check is an **accepted deviance**: the check reports
`accepted (N, unchanged)` instead of failing until its count moves — matched
by the artifact's file name, so it holds whether `--docs-dir` was given as
`docs` or as an absolute path, and the doctor writes repo-relative paths into
every finding it mints whatever form it ran with. A check
labelled `awaiting re-invocation per FND-NNN (<command>)` is red on an
artifact that finding still **owes** — named by its `downstream_rerun` or by a
propagation hop with no `verified_at` — so the failure is that finding's
pending hop, not a new defect: the doctor keeps it red (the artifact is not
consumable) but records nothing for it, and when every failure is owed its
`NEXT:` names the owed command instead of this skill. Do not localize such a
row again; the close card counts it as work that finding still owes (Phase 6,
"The `Findings:` and `Status:` rows"). Before this label existed, every sweep between two hops
minted the same failure afresh, because its first defect line moved with each
hop while the cause did not (ledger IMP-077). Skipped checks (artifact absent,
tool absent) are reported as skipped and never become findings.

Copy the second run's per-check exits into the state file's `baseline_checks`
and its `[stale]` lines into `provenance_drift`. A `[stale]` line is *not* a
finding — an artifact built against an older upstream is a known state whose
channel is the owning skill's §7 delta-review — but it is a fact Phase 4 needs
(see "hand-edits" in `references/edge-cases.md`), and the doctor's
`can be marked resolved` hints name triaged re-invoke findings whose downstream
artifacts have all been rebuilt since the fix: confirm and close those first.

Merge the sweep's findings with the queue's existing open ones (all raisers:
`sdlc-code`, any `sdlc-<skill>`, `sdlc-repair`, `user`), then **localize each**.
Load `references/back-propagation.md` now — it holds the rules. The shape of
the work:

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
  the gate, put `re-invoke` in position 1, and never refuse `surgical`.

**Blast-radius checklist.** For every located symbol, compute — never guess —
the inbound sites, and print them **grouped by artifact** as a checklist the
Phase-4 fix must tick off (edited / re-sliced / unaffected):

```bash
python .claude/sdlc/docs_index.py --refs <symbol>
```

Every `python .claude/sdlc/docs_index.py …` in this file runs the copy
`${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks once per
run: an installed copy older than the plugin's counts as absent. The bare
regenerate in Phase 5 is the exception that file names.

**Retired-token sweep.** A fix that REMOVES or RENAMES a named token (an input
parameter, a CLI flag, a field, an enum member, a literal) has sites `--refs`
cannot see: nothing references a name that no longer exists. Sweep the corpus
for the old name with a plain text search — `grep -rn <token> docs/` (or the
Grep tool over `docs/`); the index's `--find` matches symbols, not prose, so
it cannot do this sweep — and add every hit to the checklist, changelog lines
excepted. The typical miss is a
sibling test in the very file you are about to edit (aicf LSN-074: five
artifacts reconciled, one test in the edited strategy file still passing the
removed parameter). The close card names the token, the hit count and each
hit's disposition (ledger IMP-091).

Until shards and named symbols are indexed, `--refs` resolves **corpus ids
only** (`FR-`, `WKF-`, `ENT-`, `SCR-`, `TST-`, `TSK-`, … families defined in
the canonical files). For a *named* symbol fall back to a grep over `docs/`,
by symbol class, and say in the resolution that the radius came from grep:

| Symbol class | Grep for the name in | Fields that carry it |
|---|---|---|
| DATA-MODEL entity | `docs/ARCH__*.yaml docs/TEST-STRATEGY__*.yaml docs/TASKS__*.json` (+ `docs/API__*.yaml`) | `traces_data_entities`, `touches_entities`, `via_entity`, `entity_slice.entity`, `primary_entity`, `to_entity` |
| ARCH work_unit | `docs/TEST-STRATEGY__<cid>.yaml docs/TASKS__<cid>.json docs/ARCH__<cid>.yaml` | `target_symbol`, `targets_work_units`, `via_unit` |
| TST-NNN | `docs/TASKS__<cid>.json` | `implements_tests` (+ `test_spec` is its embed) |
| API operation | `docs/ARCH__*.yaml docs/TASKS__*.json` | `traces_api_operation`, `touches_operations`, `operation_contract` |

**Step 0 — is it the skill?** (CLAUDE.md 15). Sometimes the walk ends not at
a wrong artifact but at the *plugin itself*: a validator check the user
confirms is wrong (`validator_false_reject`), or an upstream output schema
with no field for what downstream needs (`schema_gap`). The fix then does NOT
live in this project — record a lesson
(`python .claude/sdlc/lessons.py add --skill <owning-skill> --kind …
--related FND-NNN`; skip silently if the helper is absent) and close the
finding `wontfix` with that reason. Never bend a validator to accept an
artifact, and never patch any plugin file from inside a consumer project.
Mid-run observations that are not yet lessons go to `lesson_notes`, never to a
detour.

**Read by slice, not by slurp.** The upstream artifacts are large; use
`docs/INDEX.yaml` line ranges (`.claude/rules/sdlc-docs-access.md`) to read only
the symbol under suspicion and its inbound sites.

### Phase 3 — Confirm

One `AskUserQuestion` per finding (batch 2–4 when several are mechanical and
low-stakes). Present, per finding: the **walk** (surfacing site → stages
examined → chosen source → why), the proposed fix, the blast-radius checklist,
the mode (`surgical` / `re-invoke`) and, when it applies, `repaired before as
FND-NNN`.

Options: *fix as proposed* (position 1; position 1 is *re-invoke* for a
recurrence) / *fix fully — author the new item(s) here* (offered, and at
position 1, whenever the fix changes the downstream SET and the four-part
additive criterion in Phase 4 holds; it is never argued for, it is offered)
/ *fix differently* (free text) / *defer* (status `deferred`,
`resolution.mode: none` + `reason`; on a TASKS artifact also declare the task
in its top-level `deferrals: [{id, reason}]` list — never a `WRN` prose note) /
*accept as-is* (status `wontfix` with `expected_count: N` in the summary when
the finding is a validator count the project lives with) / *wontfix* / *it's
the skill, not the doc* (record the lesson per Phase 2 Step 0, cross-linked
`--related FND-NNN`, and close the finding `wontfix`) / *it's the generated
code, not the spec* (`back-propagation.md`'s Step 2 owner table showed every
upstream contract already correct; close `wontfix` with
`resolution.located_stage: code` and name the owning qualified task id(s) in
`resolution.stale_tasks` — `/sdlc:code`'s own plan gate reads that field
regardless of status and schedules the rebuild; repair still never edits
code itself).

**When both rules claim position 1** — the finding is a recurrence *and* its fix
meets the four-part additive criterion — *fix fully* takes position 1. The
recurrence default changes which mode leads, never which modes are offered
(`references/forward-propagation.md` says exactly that: "never a refusal of the
in-run modes, just a changed default"), while the additive rule rests on a
measured cost — routing a fully-determined item to `re-invoke` costs the user
two interviews and discards the walk (aicf LSN-019 / LSN-040).

`references/back-propagation.md` names when to **ask rather than decide**:
`missing_requirement` findings, two equally defensible stages, any fix that
changes product behaviour rather than clarifying a description, and any walk
that terminates at PRD. Mechanical cases (a stale embed re-slice, a dangling ref
whose owner `--refs` makes obvious, an `upstream_incomplete` whose field the
owner can simply fill) can be batched.

`EXIT` in any free-text field stops the run (Phase 1 rules).

### Phase 4 — Fix at the source

Load `references/forward-propagation.md`. Three modes, chosen by two
questions: does the fix change the **set** of downstream items, or only their
**content**? And when the set — is the change **purely additive and fully
determined** by the walk just performed?

**Once a finding is localized and the fix is expressible in the artifacts,
FIX IT in this run.** The localization table is a map of where the *source*
is, not a routing table for who fixes it. Hand a fix downstream (`re-invoke`)
only when it needs a decision this run cannot get — and a modelling choice
inside the located artifact itself (which component owns a new work_unit,
what it is called) is one this run CAN get: ask it at Phase 3, then write it.
A new finding is cheap to write and expensive to redeem: the next skill re-derives the cross-artifact
walk cold, with no guarantee of the same reading (aicf LSN-019 / LSN-040).

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
     task embed is edited (with its own bump) or explicitly marked unaffected.
     When the fix retires or renames a named token, sweep the corpus for it
     first (`grep -rn <token> docs/` - a text search, never the index's
     symbol-only `--find`) and add every hit: the sibling test in the file you
     just edited is the
     typical miss (Phase 2, "Retired-token sweep");
  5. `python .claude/sdlc/docs_index.py --stamp docs/<artifact> --upstream docs/<reviewed-upstream> --hold-upstream docs/<other-recorded-upstream>`
     (one flag per file; each flag takes exactly one) for every artifact
     reconciled by hand, upstream-first — a stamp moves the stamped file's own
     hash, and it must land BEFORE the re-slice, which stamps the shard
     against the upstream bytes it sees. Run it through the copy
     `${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks:
     `--hold-upstream` needs `docs_index.py` capability 6, and an older
     install rejects it with exit 2 (the plugin's form is
     `"${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs`; ledger
     IMP-088, IMP-108). **`--upstream` only for a pair that was fresh before
     this run's first write.** A stamp claims that EVERY delta between the
     recorded upstream and the current one was reviewed, and this run
     reviewed one finding's change. It also re-hashes EVERY upstream the
     artifact already records, not only the ones named, so every other entry
     in its `metadata.upstream_provenance` takes `--hold-upstream`, which
     leaves that entry byte-identical: an upstream this run did not review,
     and a pair the Phase 2 snapshot (`sdlc-repair.doctor.json`,
     `provenance.stale`) already listed. Such a pair owes an older, unreviewed
     delta to `/sdlc:<skill> … --reconcile`, and stamping it now would forge
     that review. An artifact with no fresh reviewed pair is not stamped at
     all. Name each held pre-existing pair on the close card's `Attention:`
     row and route the owed reconcile in `Next:` (ledger IMP-099, IMP-106,
     aicf LSN-080). **Then read what the stamp printed:** a `re-stamped
     <upstream>: … since the last stamp - reviewed by this run?` line names
     an upstream it re-hashed that had moved. For an upstream this run
     reviewed that is expected; for any other a hold is missing, so restore
     the artifact's old record of that upstream from git (`git diff
     docs/<artifact>` shows the old lines), confirm `--drift docs/<artifact>`
     names that upstream again, and stamp again with the hold. The printout
     catches a missing hold after the fact; the holds are what prevent the
     forgery (`forward-propagation.md`, "What a stamp claims");
  6. `python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --symbol <cid>/<component>/<work_unit>`
     (or `--tst TST-NNN` / `--entity <Name>` / `--operation <operation_id>`)
     — LAST, so the shard is stamped against the final upstream bytes;
     re-slices every embed copied from the changed symbol, bumps the shard,
     refreshes its `upstream_provenance`, prints the moved task ids with their
     before/after fingerprints. **Add `--hold-stamp docs/<upstream>` for every
     pair the Phase 2 snapshot listed**: the embed still moves (a mechanical
     copy, not a review), but the shard's stamp for that upstream stays, so
     the owed `--reconcile` still sees the whole delta — the re-slice's own
     stamp refresh would otherwise forge it exactly as a hand `--stamp` would
     (IMP-099). A pre-existing embed drift on such a pair is a baseline
     failure for Phase 5, not this run's to clear;
  7. verify (Phase 5) — `reslice_embeds.py --check` green, the validators
     bare, and `docs_index.py --stale` listing nothing this run reconciled —
     a row the Phase 2 snapshot already held is the owed reconcile step 5
     left alone, not a missed stamp;
  8. `python "${CLAUDE_SKILL_DIR}/../code/topo_order.py" --scope <cid> --state .claude/skills-state/sdlc-code.state.yaml`
     plus `--affected <FR-NNN…>` for a PRD change → `resolution.stale_tasks`
     (stale + affected, with the reason recorded).

  Steps 6 and 8 call the `task` and `code` skills. In the **demo edition**
  (`${CLAUDE_SKILL_DIR}/../task/SKILL.md` absent) there is nothing to re-slice
  or schedule: skip both and say so. A project that still has
  `docs/TASKS*.json` from an earlier full-edition install owes that re-slice — name it in
  the close card's `Attention:` row; never edit a task file by hand instead.
- **`additive`** (set, fully determined) — the fix **adds** downstream items
  and nothing else, and the walk already determined every field they need.
  All four must hold, or the mode is `re-invoke`:
  1. **purely additive** — no item is removed, renamed or re-scoped;
  2. **fully determined** — every field the new item's schema requires follows
     from facts in hand (the source slice, its siblings, the walk); no
     interview question is left. A field you would have to *decide* (a tier
     the strategy never uses, a behaviour the PRD never stated, a name nobody
     chose) fails this;
  3. **validator-provable** — after the write, each touched artifact's
     `validate_schema.py`, `reslice_embeds.py --check` and `doctor.py --quick`
     are green, bare, with captured exit codes (Phase 5);
  4. **the obligation chain closes in this run** — a new TST obliges its
     realizing `kind: test` task, wired per checks 27/28; a new work_unit
     obliges its impl task AND a test naming it in `targets_work_units` (or a
     structured deferral); a new entity obliges its traces. Every link must
     itself pass 2 — one undetermined link makes the whole fix `re-invoke`.

  Mechanics: steps 1–2 of `surgical` on the source; then author each new item
  directly in its own artifact. A new task's embed (`test_spec`,
  `interface_contract`) is *copied* from the source slice and proven
  byte-identical by `reslice_embeds.py --check` — the hard boundary on
  embeds forbids *patching* a copy to a third value, not copying a corrected
  source. `bump_artifact.py` every touched artifact; then **stamp, exactly as
  `surgical` step 5 prescribes** — `docs_index.py --stamp` each artifact this mode
  authored into, against the upstream it authored from, upstream-first (the
  source before the shard that copies it; other additive shapes stamp a whole
  chain), `--hold-upstream` for every other recorded upstream, then read the
  `re-stamped …` printout. This mode may claim that pair because it WROTE the
  whole delta between the recorded upstream and the current one — but step 5's
  other rules still bind: a pair the Phase 2 snapshot already listed owed an
  older, unreviewed delta, so it stays held and named on the close card, never
  stamped. Then refresh the index; verify
  (Phase 5). The new task is simply `pending` to `topo_order.py` — no ledger
  edit. Close `resolved` with `mode: additive`, `artifacts_touched` naming
  every file, one `source` hop and one `downstream` hop per authored item,
  and `downstream_rerun: []` — nothing is owed downstream (a stamp records a
  review, it is not a re-run); if something is, the mode was `re-invoke`.

  A finding that splits into a **mechanical half and a modelling half** is
  fixed in one run when the modelling half passes 1–4: `surgical` on the
  first, `additive` on the second, one resolution block naming both. When the
  modelling half fails 2 only for want of a decision this run CAN obtain (a
  choice inside the located artifact — which of two contradictory values is
  right, which component owns a unit, what it is called), it does not leave
  this run: mint it (`findings.py add … --related FND-NNN --raised-by
  sdlc-repair`) so the audit trail has it, and it joins THIS run's queue —
  Phase 1 re-reads the queue after each finding closes and works it through
  the same Phase 3 gate, *decide it now* at position 1, the answer recorded
  in that finding's `resolution.summary`. Only a half whose decision is not
  this run's to take (`references/back-propagation.md`, "ask — do not decide
  alone": a `missing_requirement`, a product-behaviour change, a walk ending
  at PRD) becomes a sibling finding for a later run, and the close card says
  so. The same holds for any defect the walk surfaces BESIDE the one being
  fixed (ledger IMP-153, aicf LSN-086: an adjacent contradiction was routed to
  "file a new finding" with the walk loaded and the user at the gate). Never
  under-deliver silently, and never interleave two findings' surgical
  sequences: the second starts after the first's Phase 5, so each stamp
  claims only what its own run reviewed.
- **`re-invoke`** (set, not determined) — changes to the *set* of downstream
  items that fail the additive criterion: a removed/renamed component,
  work_unit, entity, operation, surface, TST or task; a restructured boundary;
  a new item whose content needs an interview. Fix the source (steps 1–2) —
  the located artifact is always edited HERE, never handed to its own
  `--reconcile`: a reconcile reviews what moved upstream of its artifact, so
  pointed at the file you just localized it finds no delta and the handoff
  note has no card to land on. Then **stop and print the exact downstream
  command sequence**, starting at the first stage BELOW the source — every
  consumer stage has a `--reconcile` form (`/sdlc:ux --reconcile`,
  `/sdlc:data --reconcile`, `/sdlc:arch <cid> --reconcile`, …): print those,
  container-scoped on arch/test/task, the full interview only as the fallback
  — and **`/sdlc:test <cid>` before `/sdlc:task <cid>` whenever work_units
  were minted** (the test has to name the new subject before task can wire a
  test task to it):

  ```
  # rooted in docs/API__tasks.yaml; a fix rooted in ARCH__demo-api.yaml starts at /sdlc:test demo-api --reconcile
  /sdlc:arch demo-api --reconcile   then   /sdlc:test demo-api --reconcile   then   /sdlc:task demo-api --reconcile
  (fallback when a reconcile stops at a structural question: the same skills without --reconcile)
  ```

  **Leave the walk's reasoning on disk: `resolution.handoff`.** The fresh
  session that runs each reconcile never saw this walk, so write down what it
  concluded — one entry per downstream item you already have a view on:
  `{artifact: docs/<a file an owed command rewrites>, key: <the item as
  docs_index.py --drift prints it, or null for the whole file>, note: <why it
  moved and what you propose>, basis: measured | inferred}` (e.g. `key: demo-api/api/archive-task`,
  `note: "now raises NotFound for an unknown id; that branch needs a unit TST
  covering FR-014"`). Each reconcile reads its own notes (`findings.py list
  --owed-by`) and offers them as the matching card's position-1 proposal.
  **Say how each note was reached.** `basis: measured` means you read it off
  the artifacts the note names (a call site checked against the caller's
  declared order, a field read from the entity); `basis: inferred` means an
  analogy or a precedent you did not verify there. A cold reconcile offers a
  measured note as read and VERIFIES an inferred one against the cited
  artifact before writing - one siting recommendation written by analogy was
  wrong against the very files its note cited, and nothing marked it as a
  guess (ledger IMP-082). Never mix the two registers in one note. The
  `bump_artifact.py --summary` line is the other half — every reconcile's
  `--drift` quotes it as the upstream's "why" — so write that summary for the
  reader who lacks this session.

  This skill never runs another skill: those are interviews and the user owns
  them. Nor does it walk the chain for them: each reconcile's `Next:` is the
  next stale file (`docs_index.py --stale`), and the last one routes back to
  `/sdlc:repair FND-NNN` to close this finding. **Always** record the sequence in `resolution.downstream_rerun` (the queue
  validator requires it for `re-invoke`), record `artifacts_touched` so far,
  and leave the finding `triaged` — a triaged finding may carry exactly this
  partial resolution block — until the user reports the re-invocations done
  (or `doctor.py --provenance` says they were).

When in doubt between `surgical` and the set modes, prefer a set mode: a
surgical edit that should have changed the set leaves a downstream artifact
internally consistent but missing an item, and no coverage gate catches an
item that was never created. Between `additive` and `re-invoke`, "in doubt"
means a criterion actually fails — not that the change feels big. Routing a
fully-determined item to `re-invoke` costs the user two interviews and
discards the only cross-artifact context the pipeline builds.

### Phase 5 — Verify

Re-run, **bare**, capturing every numeric exit code. Pass the **system file**
of each touched family — the validators glob their own `__<slug>` siblings, and
a shard path is refused:

```bash
python "${CLAUDE_SKILL_DIR}/../arch/validate_schema.py" --path docs/ARCH.yaml
python "${CLAUDE_SKILL_DIR}/../test/validate_schema.py" --path docs/TEST-STRATEGY.yaml
python "${CLAUDE_SKILL_DIR}/../task/validate_schema.py" --path docs/TASKS.json
python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --container <cid> --all --check
python "${CLAUDE_SKILL_DIR}/../task/crosscheck_artifacts.py" --docs-dir docs
python .claude/sdlc/docs_index.py                 # regenerate the index - the PROJECT's copy only
python .claude/sdlc/docs_index.py --check         # dangling-reference gate
python .claude/sdlc/docs_index.py --stale         # must list nothing this run reconciled - a row here is a missed stamp,
                                                  # the `re-stamp only` rows included (nothing the shard cites changed, so
                                                  # the review is cheap - but the stamp is still owed), unless the Phase 2
                                                  # snapshot already held it (a pre-existing pair, owed to its own
                                                  # --reconcile: name it on the close card, never stamp it)
```

The `test` and `task` lines run only where those skills ship; in the demo
edition skip them and say so.

**The regenerate line runs only through the project's installed copy.** When
`.claude/sdlc/docs_index.py` is absent, skip that line and say so in the close
report: either the project never ran `/sdlc:setup`, or it ships its own index
generator (its `docs/INDEX.yaml` header names it, and the doctor's gate label
reads `plugin copy, --check only` with the reason). In both cases
`docs/INDEX.yaml` is not this skill's to rewrite. Never run the plugin's own
`setup/docs_index.py` bare against a consumer project: it writes a stock-format
index over whatever the project generates, and one project lost its
project-owned index that way. Only the read-only `--check` may fall back to
the plugin copy, exactly as the doctor does.

Validate **every artifact touched**, not just the source. Compare each exit
against `baseline_checks`: a check that was already red before this repair, for
an unrelated reason, is reported with its before/after exit codes and called
out as pre-existing. Never let an unrelated red read as caused by the repair,
and never claim a repair fixed something it did not touch.

If verification cannot run at all, nothing is marked `resolved`.

### Phase 6 — Close & hand back

Write each finding's `resolution` block (`by`, `at`, `located_stage`, `mode`,
`artifacts_touched`, `downstream_rerun`, `stale_tasks`, `fields_changed` /
`symbols_changed` when known, `summary`) **and its `propagation` hops** — one
per place the fix had to land, each with `verified_at` and `how`:

```yaml
propagation:
  - {hop: source, target: docs/ARCH__demo-api.yaml, verified_at: <now>, how: "arch/validate_schema exit 0"}
  - {hop: embed,  target: "docs/TASKS__demo-api.json#TSK-004.interface_contract", verified_at: <now>, how: "reslice_embeds.py --check exit 0"}
```

`resolved` requires every listed hop verified (queue version 2). A hop you
could not verify means the finding does not close, and where it waits depends
on the mode: a `re-invoke` keeps its block and stays `triaged`, while a
`surgical` fix leaves the finding `open` with no resolution block at all —
only a re-invoke in progress may record partial progress on a triaged finding,
and `validate_findings.py` makes that an error at *every* queue version, so
parking a surgical fix there is a rejected write, not a park. Record what did
land as one evidence line on the finding itself (`evidence` holds at most five
lines — fold it into the last one when the list is full): the artifacts already
edited, and the check that could not run. That line is what the next run
re-verifies against disk (Phase 1) and what the statusboard prints under the
still-open finding. Set the queue's `last_updated` and re-validate it with
`validate_findings.py`.

**Write it right the first time** — the queue's validator enforces rules
the example above does not show, and each one costs a rejected round-trip
when learned by trial (canonical: `FINDINGS.schema.yaml`):

- `hop` is one of `source` (the artifact whose content was wrong), `embed` (a
  write-time copy re-sliced from it), `downstream` (any other artifact the fix
  propagated into — a TST acceptance, an entity trace, a UX shard) or `code`
  (generated source the build re-made). Nothing else — an index refresh is
  not a hop.
- `duplicate_of` is present exactly when `status: duplicate`, and a duplicate
  carries NO `resolution` block. A `wontfix` never carries `duplicate_of`;
  say which finding it repeats in `resolution.summary` instead.
- `resolved`, `wontfix` and `deferred` all carry a `resolution` block
  (`deferred` with a `reason`).
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
  unpropagated defects, one for three weeks. So compute the sequence in Phase
  4 and fill `downstream_rerun` in this same write, then keep the finding
  `triaged` until the user reports those runs done. A re-invoke whose sequence
  you cannot compute carries no resolution block at all — an empty one is the
  state that hid those defects. What is still owed is reported by the row
  table below (ledger IMP-054).
- `handoff` (re-invoke only) is a list of `{artifact: docs/<file>, key, note,
  basis}`,
  and `artifact` must be a file an owed `downstream_rerun` command rewrites —
  container-scoped on arch/test/task, since a bare `--reconcile` maps to the
  system file only. The validator merely warns on a misplaced note, and a
  misplaced note is one no reconcile ever reads: address it right.
- **Upgrade a version-1 queue when it is clean.** When every finding in a
  `findings_file_version: "1"` queue passes the version-2 checks (run
  `validate_findings.py` and read the gated warnings — zero means clean), set
  `findings_file_version: "2"` in the same close write, then re-validate. The
  gate exists for queues this skill does not touch, not for the one it keeps
  writing.

Then compute the handback. There is no bespoke mechanism and there should not
be: editing a task artifact changes each affected task's fingerprints, which
`/sdlc:code` already classifies as `stale` (build-relevant content moved),
`ring_recheck` (a provider's contract moved) or `refreshed` (nothing that
matters moved) and gates at its plan approval. `topo_order.py`'s `stale` and
`--affected` sections are the answer; they are already in
`resolution.stale_tasks` from Phase 4.

Close with the report:

```
── /sdlc:repair — what changed ────────────────────────────
Findings:  2 fixed and closed (FND-001, FND-002) · 1 fixed at its source, still owes 2 re-runs (FND-004) · 1 parked (FND-005)
Located:   FND-001 → arch (suspected: task)  ·  FND-002 → api (suspected: test)
Edited:    docs/ARCH__demo-api.yaml, docs/TASKS__demo-api.json (2 embeds re-sliced)
Verified:  arch exit 0 · task exit 0 · reslice --check exit 0 · crosscheck exit 0 · index exit 0
Stale:     demo-api/TSK-004, demo-api/TSK-006 will be offered for regeneration
Status:    {computed - e.g. repair's edits are done; FND-004 closes when its 2 re-runs finish, and you run them, one per new session}
Next:      {the computed next invocation}   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript.
```

**The `Findings:` and `Status:` rows** answer "is repair done, what is still
owed, and who runs it" — the question a user asked when a card printed the
queue's own words beside a `Next:` naming another skill (ledger IMP-154). The
queue's state names and field names are input to these rows, never their text
(`prd/references/reporting-to-the-user.md`, "translates; it never pastes"):

| The finding in the queue | What the `Findings:` row says |
|---|---|
| `resolved` | `fixed and closed` |
| `triaged`, `mode: re-invoke`, commands recorded | `fixed at its source, still owes N re-run(s)` — N is the length of its `resolution.downstream_rerun`; the same owed work `doctor.py` labels `awaiting re-invocation per FND-NNN` |
| `triaged`, `mode: re-invoke`, no commands recorded (IMP-054) | `not closable - its re-runs were never recorded` |
| `open`, a surgical fix whose hop this run could not verify | `fixed, not verified - <the check that could not run>` |
| `deferred` / `wontfix` / `duplicate` | `parked (<reason>)` / `left as is (accepted)` / `same defect as FND-NNN` |

Collapse same-state findings into one phrase listing their ids. Keep "closed"
and "still owes" apart: a finding whose source is fixed but whose copies are
not has not closed, and saying "fixed" alone is how a card reads as done when
it is not — or as unfinished when it is.

`Status:` — first match wins, always printed:

1. **A finding is not closable or not verified** → `not finished - <FND-NNN>
   <what is missing>`; `Next:` re-invokes this skill naming it (the shared
   procedure's rule 1).
2. **A finding still owes re-runs** → `repair's edits are done; <FND-NNN>
   closes when its N re-run(s) finish - you run them, one per new session,
   starting with Next:`. This skill never runs them (Phase 4).
3. **Every finding worked is closed or parked** → `done - <the stage that was
   blocked> can run` (or `done - nothing is blocked` when no stage was).
4. **`--check`** → `health check only - nothing under docs/ was edited`.

**Compute the `Next:` row; never copy the example literals.** Procedure and
successor map: `sdlc/skills/prd/references/reporting-to-the-user.md`
(CLAUDE.md 14). `repair` walks backwards, so its `Next:` is an **in-run
position** (the located stage) while work remains, and the pipeline position
once the run is done — print both as they apply:

- **A finding is not closable or not verified** → `/sdlc:repair FND-NNN`, after
  saying what it lacks.
- **A finding still owes re-runs** → the FIRST command of its sequence, with
  its position and the terminus in words — one command on the row, never the
  chain, e.g.
  `/sdlc:test demo-api --reconcile   (1 of 2 owed for FND-004 - each prints the next; the last routes back here to close it)`.
- **All findings resolved** → `/sdlc:code <container>`, the stage that was
  blocked; add the one-line consequence (`2 tasks are now stale and will be
  offered for regeneration`).
- **Nothing was fixed** (`--check`, or every finding `wontfix`/`deferred`) →
  say the docs are clean (or what stays parked) and name no command.

**The recommended loop**, for the user who asks "what do I run next time":
`/sdlc:repair --check --no-emit` as pre-flight → `/sdlc:code <cid>` to a
component boundary → findings batch there (continue to the container boundary
while the blocked cascade stays inside the component; stop when a finding
blocks later components or two findings name one symbol) → ONE `/sdlc:repair`
over the batch → the printed `--reconcile` chain, only when printed (run the
first; each names the next; the last routes back to `/sdlc:repair FND-NNN`)
→ `/sdlc:code <cid>` in a NEW session. Never repair mid-component. There is no
`--propagate` chain walker: propagation is `reslice_embeds.py` + refreshed
provenance + the residual re-invoke list with its `handoff` notes, and that
list routes itself.

Every target must have a `sdlc/skills/<name>/SKILL.md`; never route to
`/sdlc:deploy`, which is planned and not yet implemented.

**Record the run** (CLAUDE.md 15): drain `lesson_notes` (one `lessons.py add`
per note that survives the self-review, at most 2 unless one is a blocker),
then `python .claude/sdlc/lessons.py record-run --skill repair --plugin-root
"${CLAUDE_SKILL_DIR}/../.."`. Best-effort: a non-zero exit becomes one line in
the close report; helper absent — skip silently. Add a `Lessons:` row to the
card only when this run recorded at least one; never print "no lessons".

Set the state file `status: complete`.

## Localization at a glance

Full rules: `references/back-propagation.md`. The one-line version of each:

| Finding kind | Usual source | The check that decides |
|---|---|---|
| `contract_underdetermined` | `arch` work_unit | …unless it `traces_api_operation` (→ `api`), or filling it in would require inventing behaviour (→ `prd`) |
| `contract_contradiction` | the *earlier* of the two stages | whichever statement PRD supports stands; PRD silent → `prd` |
| `test_contradicts_contract` | `arch`/`api` **or** `test` | trace both to PRD; whichever the FR/NFR/ACR supports is right. Supports neither → `prd` |
| `missing_requirement` | `prd` **or** the downstream stage | is the behaviour legitimate, or invented scope? Always the user's call |
| `missing_operation` / `missing_entity` | `api` / `data` | …unless the container should not reach for it at all (→ `arch`) |
| `unrealizable_item` | the stage that *defined* the item | the item's owner (UX surface → `ux`, operation → `api`, work_unit → `arch`) unless its inputs are what is missing (→ one stage earlier) |
| `upstream_incomplete` | the named upstream, exactly | the fact is the finding: fill the null REQUIRED field there; never patch around it downstream |
| `stale_downstream_claim` | usually the **downstream** artifact | the claim is stale, not the upstream item: reconcile the claimer (a `--reconcile` re-invoke) unless the upstream item was removed by mistake |
| `drifted_embed` | upstream, or a stale slice | compare embed to source: same wrong thing → upstream; different → re-slice |
| `wrong_path`, `missing_dependency_edge`, `impossible_acceptance` | `task` | …unless the acceptance was copied from an unsatisfiable ACR (→ `prd`) |
| `validator_error` | the named artifact | …unless it is a coverage failure naming an upstream id |
| `crosscheck_broken_ref`, `dangling_reference` | whichever side is stale | `docs_index.py --refs`: many inbound refs + absent definer → the definer; one dangling ref → the referencer |
| any kind raised by an **interview skill** or the **user** | one stage *upstream* of the raiser | the raiser read its inputs and found them wanting; the `suspected_stage` it gives is usually its immediate upstream — check that one first, then keep walking |

## Hard boundaries

- **Never writes source code** and never touches the generated tree. Code
  defects are `/sdlc:code`'s heal loop, not findings.
- **Never runs another skill.** `re-invoke` prints a command sequence and
  leaves its reasoning in `resolution.handoff`; the sequence routes itself
  through each reconcile's `Next:`.
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

## Model policy

**opus / xhigh** (frontmatter), and deliberately so. This is the one skill whose
core operation is cross-artifact archaeology: holding eight artifacts' semantics
in view at once and deciding which of them is *actually* wrong. It is the
opposite regime from `/sdlc:code`'s manager (sonnet/high bookkeeping), which is
exactly why the two are separate skills rather than one — running this reasoning
inside the codegen manager would both mis-model the work and consume the very
context that codegen is trying to conserve.

## Quick reference: user inputs at gates

| Input | Effect |
|---|---|
| `EXIT` | Stop; state persisted as `aborted`, edits so far confirmed and named, run recorded. |
| *fix as proposed* | Apply the localization and fix shown. |
| *fix fully* | `additive` mode: author the new downstream item(s) in this run (criterion in Phase 4); the finding closes `resolved` with `mode: additive`. |
| *fix differently* | Free text — your localization or fix overrides the proposal. |
| *defer* | Finding → `deferred` (mode none + reason); TASKS items go in the artifact's `deferrals` list. |
| *accept as-is* | Finding → `wontfix` with `expected_count: N`; the doctor reports the check as accepted until the count moves. |
| *wontfix* | Close with the reason; no artifact is touched. |
| *it's the skill* | Record a lesson (`--related FND-NNN`); finding → `wontfix`. |

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.19"
