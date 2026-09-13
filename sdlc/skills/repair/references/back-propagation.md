# Back-propagation — finding to source stage (sdlc-repair)

Read this on entering Phase 2. It answers one question per finding: **which
artifact's content is actually wrong?**

The question matters because the artifact a defect *surfaces in* is almost never
the artifact that *caused* it. A codegen worker cannot see PRD; it sees a task
embed, so every defect looks like a task defect from there. Fixing what you can
see is how a pipeline develops a permanent limp: the same defect returns the
next time anything regenerates.

---

## The rule

> Walk **backwards** along the pipeline from where the finding surfaced, and
> stop at the **earliest artifact whose content is wrong** — the first stage
> where the missing or contradictory fact *should have been recorded and was
> not*.

```
prd ─► ux ─► design ─► data ─► api ─► arch ─► test ─► task ─► code
 ▲                                                              │
 └──────────────── walk back from the surfacing site ───────────┘
```

Who raised the finding tells you where to *start* the walk, not where it ends:

| `raised_by` | Where it surfaced | Where to start looking |
|---|---|---|
| `sdlc-code` | a task embed, a red ring, a worker's blocked report | the artifact the embed was copied from (never the embed) |
| `sdlc-repair` (doctor) | the artifact a validator or the linter named | that artifact — unless the error is a coverage / trace failure naming an upstream id |
| `sdlc-<interview skill>` (`sdlc-ux` … `sdlc-task`) | the raiser's Phase 2/3 pre-fill, a stale-ref prompt, a delta-review, an `upstream_incomplete` auto-raise at close | **one stage upstream of the raiser** — the raiser read its inputs and found them wanting; it did not write the defect. Its `suspected_stage` is usually its immediate upstream; check that one first, then keep walking |
| `user` (`--flag`) | wherever the user was looking | the `--stage` / `--path` given, then the owner table below; the user's guess is a hint, not a verdict |

Three absolutes:

- **Never localize to the plugin's own files.** When the walk says the defect
  lives in a SKILL — its validator, schema, questions, or instructions —
  rather than in any artifact, that is a *lesson*, not a repair (CLAUDE.md 15;
  `repair/SKILL.md` Phase 2 Step 0): record it via `lessons.py add … --related
  FND-NNN` and close the finding `wontfix`. A validator is never bent to fit
  one project.
- **Never localize to `code`.** Generated code is an output, never a source. A
  defect *in* generated code is a `failed` task for `/sdlc:code` to heal, not a
  finding. If a finding localizes to `code`, it was mis-raised — close it
  `wontfix` with that reason.
- **Never localize to an embed.** A task's `interface_contract`, `test_spec`,
  `operation_contract`, `entity_slice`, `design_spec` and `config_keys` are
  *write-time copies* of upstream slices. Per CLAUDE.md §9 an embed is never the
  source; the artifact it was copied from is. See "Embed vs source" below.

## Step 1 — Embed vs source

When a finding names a task embed, read the upstream slice it was copied from
and compare. There are only two outcomes, and they localize differently:

| Comparison | What happened | Source |
|---|---|---|
| the source says the **same wrong thing** | the defect was authored upstream and faithfully copied | the **upstream artifact** — fix there, then re-slice |
| the source says **something different** | the embed is **stale**; upstream moved after the slice was taken | the **embed is out of date**, upstream is fine — the fix is a re-slice, not an edit to either |

Both are fixed by editing/regenerating from upstream. Neither is ever fixed by
hand-patching the embed to say what you wish it said — that re-diverges on the
next regeneration, and for most embeds it trips the task validator's drift
warning (cross-check #20) immediately. Note the exceptions, because they are
the *more* dangerous ones: `config_keys` is synthesized from ARCH + API + PRD,
and `fixture_briefs` is authored apart from its `fixture_strategy` key — so #20
has no source to diff those against and a hand-patch there is silent. The rule
is the same for all of them — fix upstream and re-slice — but for those nothing
will tell you when you didn't.

Note the asymmetry this creates in the resolution record: a same-wrong-thing
case has `located_stage` upstream; a stale-embed case has `located_stage: task`
with `mode: re-invoke` (or a surgical re-slice), because nothing upstream is
wrong.

## Step 2 — "Where should this fact live?"

For a finding of missing or underdetermined information, the source is the
stage that *owns* that class of fact. This table is the whole heuristic:

| The missing fact is… | Owner |
|---|---|
| a callable's inputs / output / raises | `arch` — the component's `work_units[]` entry |
| …unless the work unit `traces_api_operation` | `api` — the operation's request/response/error schemas |
| an HTTP route, status code, payload shape, CLI flag contract | `api` |
| a persisted field, relation, constraint, or index | `data` |
| a screen, CLI surface, field, state, or navigation step | `ux` |
| a design token, theme value, or asset brief | `design` |
| a behaviour rule, threshold, budget, or acceptance criterion | `prd` — an FR / NFR / ACR |
| a test's tier, directive, subject, or acceptance | `test` |
| a file path, dependency edge, or task decomposition | `task` |
| a container, component, boundary, or edge | `arch` |

Walk up the table until you find a stage where the fact **should** appear and
does not. If it appears at a stage and is simply *wrong*, that stage is the
source and you can stop walking.

## Step 3 — Per-kind localization

### `contract_underdetermined`

Start at the ARCH `work_unit`. Three sub-cases:

1. The work_unit declares the fact but ambiguously → **`arch`**.
2. The work_unit defers via `traces_api_operation` → follow it; the operation's
   schemas are the contract → **`api`**.
3. The work_unit is silent *because nothing upstream ever decided the
   behaviour* (the acceptance demands an outcome no requirement describes) →
   **`prd`**. This is the case teams most often mis-file as an ARCH gap; the
   tell is that filling it in ARCH requires inventing product behaviour.

### `test_contradicts_contract`

Two candidates — the TST and the contract — and exactly one adjudicator: trace
**both** to their PRD requirements.

- The FR/NFR/ACR supports the test → the **contract** is wrong (`arch` or
  `api`).
- The FR/NFR/ACR supports the contract → the **test** is wrong (`test`).
- The FR/NFR/ACR supports neither, or is ambiguous enough to support both →
  **`prd`** is the source. The disagreement downstream is a *symptom* of an
  under-specified requirement, and fixing either side alone leaves the other
  free to drift back.

Never resolve this by "the code passes, so the test is wrong". The contract, not
the implementation, is the arbiter.

### `missing_requirement`

A downstream artifact demands behaviour with no FR/NFR behind it. Two honest
readings, and the user picks:

- the behaviour is legitimate and PRD simply missed it → **`prd`**, add the
  requirement (and let coverage propagate);
- the behaviour is **scope the downstream stage invented** → the downstream
  artifact is the source; remove or defer it there.

Do not default to adding an FR. Silently promoting invented scope into the PRD
is how a spec grows features nobody asked for.

### `missing_operation` / `missing_entity`

A call site with no API operation → **`api`**. Persisted state with no
DATA-MODEL entity → **`data`**. But check the upstream direction first: if the
container legitimately should not be reaching for that operation or entity at
all, the source is **`arch`** (a wrong edge or a mis-assigned responsibility),
not a missing definition.

### `wrong_path` / `missing_dependency_edge` / `impossible_acceptance`

Task-graph defects → **`task`**. One exception worth checking: an
`impossible_acceptance` whose text was copied verbatim from an upstream ACR that
is itself unsatisfiable localizes to **`prd`**.

### `contract_contradiction`

Two upstream statements about one thing disagree (ARCH says the unit returns
`Item`, API says the operation responds 204; PRD names a flag UX does not
draw). The source is the **earlier** of the two stages unless PRD adjudicates
the other way: trace both statements to the requirement they realize; the one
the FR/NFR/ACR supports stands, the other is the source. PRD silent → **`prd`**.

### `unrealizable_item`

An item a downstream artifact must realize — a UX surface, an API operation,
an ARCH work_unit, a task — cannot be built from what upstream provides. Two
readings, decided by *what* is missing:

- the item's own definition is wrong or incomplete → the stage that **defined
  the item** (`ux` / `api` / `arch` / `task`);
- the item is fine but the inputs it needs were never specified (an entity
  with no fields, a workflow step with no actor) → **one stage earlier**, at
  the owner of the missing input (the Step-2 table).

### `upstream_incomplete`

A schema-REQUIRED section or field is null or empty in an upstream stamped
`complete`. This one is a **fact, not a judgement** — the raiser's pre-fill
map exposed it — so the walk is short: the source is the **named upstream,
exactly** (`surfaced_at.file` + `field_path`). Fill the field there (a
`surgical` edit, or a re-invoke of the owning skill when filling it needs an
interview). Never patch around it in the downstream artifact: the next
consumer would hit the same hole.

### `stale_downstream_claim`

A downstream artifact claims something about an upstream item that is no
longer true — ARCH owns a surface UX still marks `proposed`; a task is built
while its test was deferred; a container traces an FR that PRD parked. The
claim is stale, not the upstream item, so the source is usually the
**downstream claimer**, and the fix is its `--reconcile` re-invoke (the
claimer's own delta-review reconciles the lifecycle). The one exception:
the upstream item was removed or downgraded *by mistake* — then the upstream
is the source and the claim was right all along. Ask when the artifacts do
not say which.

### Findings raised by an interview skill or the user

Whatever the kind: the raiser read its inputs and found them wanting. Start
one stage upstream of the raiser (its `suspected_stage` is usually that), and
keep walking with the Step-2 table until the fact's owner is found. A raiser
never localizes to itself — if the walk ends at the raiser's own artifact, the
finding was mis-raised (the raiser should have fixed its own output) and
closes `wontfix` with that note.

### `validator_error`

The validator names the artifact and the field. That artifact is the source
*unless* the error is a coverage/trace failure pointing at an upstream id — then
walk to the artifact that owns the id.

### `crosscheck_broken_ref` / `dangling_reference`

A reference no longer resolves. Which side is stale? Use the reference graph
rather than guessing:

```bash
python .claude/sdlc/docs_index.py --refs <symbol>
```

- The id is referenced from **many** places but is absent from its definer →
  the definer lost it (a bad edit or a rename that didn't propagate). Source is
  the **defining artifact**.
- **One** dangling reference against an id that was legitimately renamed or
  retired upstream → source is the **referencing artifact**; it holds a stale
  copy.

This is also the cheapest localization in the set — run it before reasoning.

## Step 4 — Confidence, and when to ask

Localization is a judgement, and the queue records a `suspected_stage` from the
raiser that is explicitly **not** authoritative. Present your conclusion to the
user with the walk that produced it (surfacing site → stages examined →
chosen source → why), not just the verdict. A user who disagrees usually knows
something the artifacts do not record.

Ask — do not decide alone — whenever:

- the finding is `missing_requirement` (scope questions are always the user's);
- two stages are equally defensible and the artifacts do not adjudicate;
- the fix would change product behaviour rather than clarify a description;
- the walk terminates at `prd` (a PRD edit ripples through everything
  downstream and deserves an explicit decision).

Proceed without asking when the walk is mechanical and the fix is a
clarification: a stale embed re-slice, a dangling ref whose owner is obvious
from `--refs`, a validator error naming one field, an `upstream_incomplete`
whose owner can simply fill the field.

## Step 5 — Recurrence: "repaired before as FND-NNN"

`findings.py` stamps `recurrence_of` / `recurrence` when a resolved or wontfix
finding already named the same task-or-symbol with the same kind. A recurrence
means the earlier repair's propagation stopped short, or the earlier
localization was wrong. Read the earlier finding's resolution before walking:
its `located_stage`, `artifacts_touched` and `propagation` hops say which hop
was never verified (the FND-016 → FND-023 → FND-034 shape). At the gate, say
**"repaired before as FND-NNN (came back Nx)"**, put **`re-invoke` in
position 1** — the owning skill's delta-review reconciles what a surgical edit
missed last time — and **never refuse `surgical`**: when the earlier resolution
shows exactly which hop was skipped, a scripted surgical pass that closes that
hop is the right fix, and the user may pick it.
