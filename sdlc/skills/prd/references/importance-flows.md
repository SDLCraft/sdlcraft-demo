# Importance flows — running the interview by tier

Every question in `prd-questions.yaml` carries an `importance` field:
`med | high | critical | nested_freeform`. The tier dictates how the
agent runs the question — single batch entry, dedicated draft-approval
loop, full per-item drill-down, or per-bucket free-form drafting. Read
this file when entering Phase 6 alongside `interview-mechanics.md`.

The classification was made deliberately:

- **`critical`** is reserved for fields that define the functional scope and
  the cross-cutting NFR set — currently
  `functional_requirements.features` (one flat FR-NNN list; D2 retired the
  must/nice split) and
  `non_functional_requirements.other`. These warrant the most expensive
  interaction because every downstream agent will read them and treat
  them as scope-of-record. The flow is the per-item state machine plus
  a **dynamic scope-completeness sweep** before the list is closed
  (described below) so categories of items that are typical for *this
  specific project* but missing from the draft surface as concrete
  candidate items.
- **`high`** covers foundational narrative fields (e.g. `problem_statement`)
  and required list[string] fields (e.g. `core_workflows`, `primary_users`).
  Answers are expected to be longer than a single picked option, so the
  agent drafts the entry and the user approves or iterates.
- **`med`** is everything else — short strings, enums, bools, and well-
  bounded list[string] fields whose option menu covers most cases. These
  run inside ordinary 2–4-question `AskUserQuestion` batches per
  `interview-mechanics.md`.
- **`nested_freeform`** is for a single `Dict[str, Any]` field whose
  *shape* is project-defined — currently only `conventions`. The agent
  proposes named buckets inferred from prior answers and, for each
  bucket, drafts a free-form nested YAML body the user approves or
  iterates on. See "The nested_freeform flow" section below.

A question's `importance` does NOT change its `required` semantics —
required `med` fields are still required; optional `high`/`critical`/
`nested_freeform` fields are still skippable via the now/skip/todo gate.

## ID conventions across families

Several list[string] fields in `PRD.yaml` prefix each item with a stable
`<PREFIX>-NNN` identifier so that downstream SDLC artifacts (UX,
DATA-MODEL, API, ARCH, TEST-STRATEGY, TASKS) can cross-reference items
by ID. The agent assigns IDs in the order items are collected — never
mid-flow placeholders, never gaps.

### Family map

| Prefix | Field(s) — siblings share one continuous counter |
|---|---|
| `FR`  | `functional_requirements.features` (legacy: `must_have_features` + `nice_to_have_features`) |
| `OOS` | `functional_requirements.out_of_scope` |
| `INT` | `functional_requirements.integrations_required` |
| `AIF` | `functional_requirements.ai_features` |
| `NFR` | `non_functional_requirements.performance_targets`, `other` |
| `WRN` | `prd_warnings` (top level — populated by the writer, not interviewed) |
| `PER` | `users_personas.primary_users`, `secondary_users` |
| `GOL` | `users_personas.user_goals` |
| `PAN` | `users_personas.user_frustrations` |
| `WKF` | `use_cases.core_workflows` |
| `JTB` | `use_cases.primary_jobs_to_be_done`, `secondary_jobs` |
| `EDG` | `use_cases.edge_cases` |
| `ENT` | `data_model.key_entities` |

### Rules (apply to every family)

- Format: `"<PREFIX>-NNN: <content>"` — three-digit zero-padded integers
  (`FR-001`, `FR-002`, …, `FR-010`, `FR-011`, …).
- IDs are unique within a family + scope. Sibling fields that share a
  counter (the "+" rows above) draw from one sequence: e.g. if
  `primary_users` ends at `PER-003`, `secondary_users` starts at `PER-004`.
- IDs are stable. Once written they never change. Moving an item
  between sibling lists that share a counter (secondary → primary)
  means moving the string verbatim, not renumbering.
- In monorepo mode, each product carries its own independent ID space
  per family. Two products may each have `FR-001`; references are
  disambiguated by the `products.<slug>` path.

### State counters

The per-family counters live in `state.last_ids` (single-product) or
`state.last_ids_by_product` (monorepo). Persist them after each item is
written so EXIT/resume preserves gapless numbering. See `SKILL.md`'s
"Session state file" section for the schema.

### When the ID is assigned

The trigger differs by tier:

- **`med` (batched)**: when the agent serializes the user's batch response
  into the YAML list, it assigns IDs in collection order. The user
  doesn't see IDs during the question; they appear in the written file.
- **`high` (per-item draft-approval)**: at step 3 (*Add item*), the agent
  picks the next ID from the family counter, displays it back to the
  user as part of the appended item, and persists the counter.
- **`critical` (full per-item state machine)**: at step c (*Finalize*),
  the agent assigns the next ID at the moment of approval — see the
  `critical` section below for the exact moment.

The `validate_schema.py` script enforces format on every list item in
every registered family. Items without the prefix are warnings in
`status: draft` and errors in `status: complete`.

### `prd_warnings` (writer-populated, never interviewed)

The writer prepends `WRN-NNN:` to each warning when serializing the
list. Use a monotonic counter `state.last_ids.WRN`; persist after every
warning append.

## How batching changes with tier

`med` questions batch together (2–4 per `AskUserQuestion` call) inside
their theme. `high`, `critical`, and `nested_freeform` questions are
**never batched with others** — they each run as their own mini-section,
because their flow is multi-turn and cannot share a call with sibling
questions.

Inside a theme, run all `med` questions first (in 2–4-question batches),
then run each `high`/`critical`/`nested_freeform` question as its own
mini-section in the order they appear in `prd-questions.yaml`. Write
state after each mini-section completes, exactly like after a normal
batch.

## The channel rule — content rides inside the question

A hard rendering constraint shapes every flow in this file: **markdown printed
to the chat in the same turn as a tool call may not be rendered to the user.**
Therefore:

- **Any content a question depends on travels INSIDE the `AskUserQuestion`
  call** — in the question text, an option's `description`, or an option's
  `preview` (a monospace markdown box, available on single-select questions —
  the right vehicle for YAML/draft snippets, attached to the recommended
  option). A user cannot approve what the call does not show.
- **Chat markdown in a turn that also calls a tool is never load-bearing.** It
  may duplicate what the call carries, never substitute for it.
- **Markdown followed by a TYPED reply is fine only when the turn ends with
  the markdown** (no same-turn tool call after it) — SKILL.md's Phase 3 idea
  summary and Phase 5 pre-fill blocks work exactly this way.
- When `preview` is unavailable (a multi-select question, or a harness
  without it), fold a compact draft into the question text and keep the full
  text in the option description.

The scope-completeness sweep below has always done this correctly —
candidates ride in option labels/descriptions. Downstream skills reference
this section instead of restating it.

## The `med` flow (default)

Unchanged from prior behavior. Each `med` question goes into an
`AskUserQuestion` batch alongside up to 3 sibling `med` questions from
the same theme. The `⚠ inferred` candidate (if any) is the position-1
option; the user picks an option, types free text into "Other", or
types `EXIT`. Set `<field>_confidence: confirmed` (explicit pick or
typed answer) or `inferred` (accepted as-is).

## The `high` flow

### Scalar `high` fields (string)

These are: `problem_opportunity.problem_statement`, `product_vision` (the MVP
narrative folded here after D2 retired `milestones`).

1. **Propose.** Compose a 2–4-sentence draft from prior context.
2. **Ask for approval — the draft rides in the call** (channel rule above).
   One `AskUserQuestion`: the question text carries a one-line provenance
   comment naming what you drew on, and the recommended option carries the
   full draft in its `preview` (no preview support: fold the draft into the
   question text). Never print the draft to chat and follow with a
   content-free approval in the same turn.

   ```
   header: "Approve?"
   question: "Based on the README excerpt and your users_personas answers — approve this <field> as drafted (full text in the first option), or iterate?"
   options:
     - { label: "Approve as-is", description: "Write this to PRD.yaml and continue.", preview: "<the full draft>" }
     - { label: "Iterate — type changes", description: "Use the text field to describe what to change, add, or remove." }
   ```

3. **On approve.** Write the answer with `<field>_confidence: confirmed`.
4. **On iterate.** Re-draft using the user's free-text guidance. Repeat
   steps 1–3 with the new draft.
5. **Iteration cap.** After 3 iterations on a single field, write the
   current draft, append a one-line `prd_warnings` entry naming the
   field, and move on. The user can always re-run the skill in update
   mode to keep tweaking.

### List[string] `high` fields

These are: `users_personas.primary_users` (PER), `use_cases.core_workflows`
(WKF), `use_cases.primary_jobs_to_be_done` (JTB),
`functional_requirements.out_of_scope` (OOS),
`functional_requirements.integrations_required` (INT),
`functional_requirements.ai_features` (AIF),
`non_functional_requirements.other` (NFR),
`data_model.key_entities` (ENT),
`risks_assumptions.top_risks` (no ID family).

Each item gets a lighter version of the per-item flow:

1. **Propose first item.** Suggest a candidate item (title + ≤ 1
   sentence description) drawn from prior context. Use
   `AskUserQuestion`:

   ```
   header: "Item 1"
   question: "First <field-singular> — does this look right?"
   options:
     - { label: "<inferred title>", description: "<one-sentence description>. Confirm to add as-is." }
     - { label: "Alternative 1",    description: "<other candidate>." }
     - { label: "Alternative 2",    description: "<other candidate>." }
     - { label: "Other / type",     description: "Type your own item in the text field." }
   ```

2. **One clarifying round (only if user typed free text or you flagged
   risk).** If the user typed a free-text item or you see a meaningful
   gap (e.g. ambiguous scope, missing constraint), ask one targeted
   clarifying `AskUserQuestion`. If the user picked a suggested option
   as-is, skip this step.

3. **Add item.** Look up the field's ID family in the table above. If the
   field has one, increment `state.last_ids.<PREFIX>` (or
   `state.last_ids_by_product[<slug>].<PREFIX>` in monorepo mode), format
   the new ID as `<PREFIX>-{:03d}`, and prepend it to the item so the
   stored string is `"<PREFIX>-NNN: <title — description>"`. Append to
   the running list and state-write (item + counter together). Fields
   that have no ID family (e.g. `success_metrics.primary_kpis`) are appended
   as plain strings.

4. **Next item or end.** Either suggest the next likely item (steps 1–3
   again, with item index incremented) or — if you've run out of
   suggestions — ask:

   ```
   header: "Add more?"
   question: "Add another <field-singular>, or wrap up <field>?"
   options:
     - { label: "Add another (I'll suggest)", description: "I'll propose a candidate next." }
     - { label: "Add my own",                  description: "Type the title in the text field." }
     - { label: "Done — wrap up <field>",      description: "Move on to the next question." }
   ```

5. **Cap.** Stop after the user picks "Done" or after 8 items
   (whichever first). For `core_workflows` the natural cap is 7 per
   schema; for others use 8 as a soft cap, then prompt the user
   explicitly if they want more.

After all items are collected, the list is the answer — no final
approval step is needed because every item was confirmed individually.

## The `critical` flow

Applies to:

- `functional_requirements.features` (FR-NNN family; D2 retired the
  must/nice split — one flat list)
- `non_functional_requirements.other` (NFR-NNN family)

This is the full per-item state machine. Every item is challenged
before it's accepted, drafted with structured detail slots, and the
*list as a whole* is reflected on with a dynamic scope-completeness
sweep before it closes.

The shape of the per-item flow is identical across both fields.
Only the **detail slots** (step b) and the **scope-sweep heuristics**
(step e) differ between FR-style lists and NFR-style lists — see those
sections below.

### Item IDs — assigned in step c

The relevant family per field:

| Field | Counter | Notes |
|---|---|---|
| `functional_requirements.features` | `state.last_ids.FR` | One flat list; FR-NNN in collection order. |
| `non_functional_requirements.other` | `state.last_ids.NFR` | Continues from `performance_targets`. |
| `user_stories.stories` | `state.last_ids.USR` | Typed mappings `{id, story, owning_personas}` (PRD 1.1) — never `"USR-NNN: text"` strings. |

The assignment moment is **step c (Finalize)**, not earlier — proposals
and detail drafts shown in steps a/b don't carry an ID yet. See "ID
conventions across families" above for the format rules and stability
guarantees that apply to all families.

In monorepo mode, replace `state.last_ids.<PREFIX>` with
`state.last_ids_by_product[<slug>].<PREFIX>` throughout.

### Per-item state machine

For each item in the list:

#### Step a — propose or accept a candidate

`AskUserQuestion` with the inferred candidate as position-1, 2–3
alternatives the agent considers plausible, and "Other / type your own"
as the last option. The item at this stage is *title + ≤ 1 sentence
description only* — detail comes later.

```
header: "<Family> N"      # e.g. "Feature N", "NFR N"
question: "<Field-singular> #N — pick one or type your own."
options:
  - { label: "⚠ <inferred title>",   description: "⚠ <one-sentence description>. Drawn from <prior-answer source>." }
  - { label: "<alt candidate 1>",    description: "<one-sentence description>." }
  - { label: "<alt candidate 2>",    description: "<one-sentence description>." }
  - { label: "Other — type your own", description: "Use the text field. The agent will challenge it before accepting." }
```

If the user picks a suggested option → go to **step b** (skip a-2).
If the user types free text → go to **step a-2** (challenge it first).

#### Step a-2 — challenge (free-text only)

Look at the user's typed item against everything answered so far. If
you see a meaningful risk — scope ambiguity, dependency conflict,
contradiction with `out_of_scope` / `users_personas` / earlier NFRs,
technical infeasibility under the chosen stack — surface it in **one**
`AskUserQuestion`:

```
header: "Risk check"
question: "Before adding '<user's text>', one concern: <risk>. How do you want to handle it?"
options:
  - { label: "<proposed resolution 1>", description: "<one-sentence explanation>." }
  - { label: "<proposed resolution 2>", description: "<one-sentence explanation>." }
  - { label: "Keep as-is anyway",       description: "Accept the item without changing it. A note will be added to prd_warnings." }
  - { label: "Reword — type",           description: "Type a revised title/description in the text field." }
```

If you don't see a concrete risk, skip this step. Don't manufacture
risks — challenge is for adding signal, not for forcing iteration.

**The free-text fold — "the input is wrong."** This prompt already sits at
the 4-option cap, so the findings route rides in free text instead of a
fifth option: when the user's typed reply says an **existing `docs/`
artifact** is wrong (a stale PRD on disk from an earlier run, a defective
sibling spec the idea text quoted) rather than the item under discussion, do
NOT stop to record it — append
`{noted_at, kind_guess, file, summary, evidence}` to the state file's
`finding_notes` list in the next state write (same cadence as answers) and
continue the step. Phase 8 drains the list through
`python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add --raised-by
sdlc-prd …` on every exit path (cap 3 per run unless one is blocking; helper
absent → skip silently). `prd` consumes no upstream artifact, so this fold
is its ONLY findings route — there is no automatic close-time raise.

#### Step b — detail with structured slots

Now expand the item from title → full entry. The goal is a *verbose*
stored string (typically 2–6 sentences, longer when warranted) that
downstream agents can read once and understand the full intent without
re-reading the interview transcript. Draft the detail by mentally
filling **structured slots** before writing the prose; you don't need
to label slots in the stored string, but every slot that *applies*
should be reflected in the prose.

**Slots for FR-style items** (`features`):

| Slot | What to capture |
|---|---|
| Input(s)        | What the feature consumes — upstream artifact, user gesture, event. Reference upstream IDs (ENT-###, FR-###, SCR-###, etc.) where known. |
| Output(s)       | What the feature produces — artifact, response, side effect. |
| Dependencies    | Other FR-### / INT-### / NFR-### this feature relies on or composes with. |
| Edge cases / special modes | No-op behavior, fallback paths, multi-mode behavior (e.g. headless vs GUI), failure handling. |
| Why this matters | The downstream reason this is non-deferrable — what would break or be lost without it. |

**Slots for NFR-style items** (`non_functional_requirements.other`):

| Slot | What to capture |
|---|---|
| Scope           | Which CNT-### / CMP-### / FR-### / artifact-type this NFR applies to (the *boundary* of the constraint). |
| Threshold or criterion | The concrete bar — value, predicate, invariant. Avoid hand-wavy "good enough"; state the actual rule. |
| Measurement     | How conformance is verified — gate check, test category, manual review, structural property. |
| Downstream impact | Which downstream stage(s) must consult this — Architecture, Test Strategy, Deployment, etc. (Mirrors the role of `conventions.nfr_propagation` if that bucket exists.) |
| Why this matters | What breaks if the constraint isn't honored — determinism leak, audit failure, resumability loss, etc. |

Slot guidance is *internal* to the agent: surface 2–3 detail candidates
that each cover the applicable slots, plus the free-text option. Don't
ask the user "fill in these slots" — just make sure the candidate
drafts you propose *do* cover them.

**Deliverable-path markup.** When an Input/Output slot names a concrete
repo path this product builds / writes / ships (a schema layer, a
`tools/` validator, a `templates/` dir, a generated sidecar file), write
that path as **inline code** (backticks) in the stored FR string. Leave
bare: prose slashes (`and/or`), external product names (`PyPI/npm`),
reference-ID lists (`FR-046/047`), and paths mentioned only as
analogies. Downstream `sdlc-arch` cross-check #25 keys on the backticked
paths to verify each build-time deliverable has an owning component +
`code_location`; bare prose slashes are (correctly) ignored, so
back-ticking is what makes a real deliverable path machine-checkable.

**Don't only flatten the slots — also mint the linked instances.** Two
slots have their own ID families, and burying them solely in the FR's
prose makes them machine-unreachable for downstream coverage gates:

- an **Edge cases** slot answer that names concrete cases → ALSO mint one
  `EDG-NNN` per case under `use_cases.edge_cases`, naming the owning FR id
  inside the string ("EDG-004: FR-002 — comment body over 10k chars is
  rejected with a clear error");
- a done-condition the detail implies → ALSO mint an `ACR-NNN` under
  `success_metrics.acceptance_criteria`, naming the FR id ("ACR-012:
  FR-003 — marking a task done persists across a read"). The validator
  advises (never blocks) on every FR no ACR names — this is
  where those entries come from.

The FR prose still summarizes both (it must read standalone); the minted
EDG/ACR entries are the typed, per-requirement instances `test` and
`task` consume.

```
header: "Detail"
question: "Detail for '<title>' — pick the framing or write your own."
options:
  - { label: "⚠ <detailed candidate 1>", description: "⚠ <2–6 sentence detailed spec covering applicable slots>." }
  - { label: "<detailed candidate 2>",    description: "<alternative framing — different slot emphasis>." }
  - { label: "<detailed candidate 3>",    description: "<alternative framing — narrower or broader scope>." }
  - { label: "Other — type the full detail", description: "Use the text field." }
```

If the user picks a suggested option → go to **step c** (skip b-2).
If the user types free text → go to **step b-2**.

#### Step b-2 — second-pass clarification (free-text only)

If the user's free-text detail leaves a meaningful gap (a slot that
*should* apply is missing, contradicts something earlier, or is
ambiguous), ask **one** more `AskUserQuestion` to pin down the missing
slot. Otherwise proceed to step c. Do not loop here — at most one b-2
round.

Skip this step if the user's free text already covers the applicable
slots — slot completeness is the bar, not slot labeling.

#### Step c — finalize

Show the drafted entry as a YAML snippet **inside the approval question**
(channel rule above): the "Approve — add it" option's `preview` carries the
exact stored string. **Assign the next ID now** (increment the
relevant counter — see the table at the top of this section — and
format as `<PREFIX>-{:03d}`). The stored format merges title and detail
into one string:

```yaml
# Item about to be added (<PREFIX>-NNN assigned on approval):
- "FR-003: OAuth2 login — users authenticate via Google or GitHub. Input:
   user click on a provider button (SCR-002). Output: a session cookie
   (ENT-007) plus a short-lived access token with refresh-token rotation.
   Dependencies: INT-002 (OAuth provider), NFR-004 (session timeout).
   Edge: when the provider returns no email scope, fall back to manual
   email entry. Why: removing password storage cuts our attack surface
   and matches user expectation for B2B SaaS."
```

Then ask:

```
header: "Approve <PREFIX>-NNN?"
question: "Add <PREFIX>-NNN: <title> to <field>? (full entry in the option preview)"
options:
  - { label: "Approve — add it",         description: "Append <PREFIX>-NNN to the list and move on.", preview: "<the YAML snippet above>" }
  - { label: "Iterate — type changes",   description: "Use the text field to describe what to change. The agent will re-draft." }
```

On approve: write `"<PREFIX>-NNN: <merged title + detail>"` to the list
and persist the counter.
On iterate: re-enter step b with the user's revision as new context; the
ID is tentatively held but not written until the next approval.
**Iteration cap**: after 3 c-iterations on a single item, write the
current draft with the assigned ID, add a `prd_warnings` entry naming
the item, and proceed to step d.

#### Step d — next item or end

Once an item is approved (or capped):

- If you can think of another likely item from the user's prior
  answers, propose it directly via step a again (with the next item
  index).
- If you've exhausted your suggestions, ask:

  ```
  header: "Add more?"
  question: "Add another <field-singular>, or are we done with this list?"
  options:
    - { label: "Add another (I'll suggest)", description: "I'll propose a candidate next." }
    - { label: "Add my own",                  description: "Type the title; we'll work through it from step a-2." }
    - { label: "Done — wrap up the list",     description: "Trigger the scope-completeness sweep, then move on." }
  ```

When the user picks "Done", do **not** close the list yet — run step e
first.

#### Step e — dynamic scope-completeness sweep

This is the gate that catches items the user (and the agent so far)
forgot. It is **dynamic and project-specific**: don't use any canned
checklist. Instead, take a reflective pass over:

1. **The draft list itself** (what's been added so far) — what kinds of
   items dominate? What kinds are conspicuously absent given the
   prior answers?
2. **All upstream answers** (`problem_opportunity`, `users_personas`,
   `use_cases`, `technical_constraints`, earlier critical lists,
   structural questions from Phase 4) — what do they imply about
   features/NFRs that haven't surfaced yet?
3. **The project type** — a CLI tool, a SaaS app, a mobile-first
   product, a library, an internal data pipeline, and an
   AI-orchestration framework each have very different "things people
   forget" surfaces. Let the project's own profile drive your
   suggestions.

**Skip what was already declined.** Before surfacing candidates, read
`state.dropped_candidates[<schema_path>]` (written by the "Wrap up" arm
below). A candidate recorded there is NOT re-surfaced — on this pass, a
later pass, or a later update run — with one exception: when the answer or
id it was seeded from (`seeded_from`) has changed since the drop, the ground
under the decision moved, and the candidate may be surfaced once more.
(Downstream skills apply the same rule inside their upstream delta review.)

The sweep produces **concrete candidate items**, not category labels.
"You might be missing audit logging" beats "have you considered
observability"; "cross-branch session isolation" beats "have you
considered concurrency". The user is going to read these and decide
in one click each, so name the thing.

Format the sweep as **one** `AskUserQuestion` call surfacing the agent's
top 2–4 candidate items. Add 1–2 sentences of preamble in the question
text explaining what you noticed.

```
header: "Scope sweep"
question: "Looking at your N <field-singular>s alongside <one-line
  reflection of what you drew on>, a few candidates look notable that
  aren't on the list yet. Add any of these, or wrap up?"
options:
  - { label: "⚠ <candidate item 1 — short title>", description: "⚠ <one-sentence why-it-might-belong>. Pick to draft it through steps a-2 → c." }
  - { label: "⚠ <candidate item 2 — short title>", description: "⚠ <one-sentence why-it-might-belong>." }
  - { label: "⚠ <candidate item 3 — short title>", description: "⚠ <one-sentence why-it-might-belong>." }
  - { label: "Wrap up — list is complete",         description: "Skip these. The list closes as-is." }
```

(Multi-select if your `AskUserQuestion` call supports it for this
question, so the user can pick more than one candidate at once.)

For each picked candidate: re-enter the state machine at **step a-2**
(treat the candidate as user-typed free text that the agent already
flagged; you may skip the risk-check if the candidate is self-evidently
clean) → b → c. Then return to step e for a second pass.

**Record the drops.** When the user picks "Wrap up — skip these" (or leaves
surfaced candidates unpicked), record each declined candidate under
`state.dropped_candidates[<schema_path>]` as
`{candidate, seeded_from, reason: "declined at sweep", at: <iso8601>}` in
the same state write that closes the pass — `seeded_from` names the answer
or upstream id the candidate was derived from. This record is what keeps a
declined candidate from nagging on every later pass or update run (see
"Skip what was already declined" above).

**Caps for the sweep:**

- At most **2 sweep passes** per list. After two passes, even if you
  still see candidates, defer them to a `prd_warnings` entry:
  `"<field>: sweep suggested but not added — <candidate>, <candidate>"`
  and close the list. The user can re-run the skill in update mode if
  they want more.
- **No sweep at all** if the user added 0 items in step a/b/c (an
  empty critical list is its own signal — don't push). Surface a
  single `prd_warnings` note instead: `"<field>: empty list — no items
  collected"`.
- For very short lists (1–2 items), still run one sweep pass — short
  lists are exactly when forgotten items are most likely.

**Anti-padding rule:** if you don't see *concrete* candidates after
honest reflection, surface 0 — close the list without a sweep question.
Don't manufacture candidates to look thorough.

#### Confidence after step e

Items added during the sweep get `confidence: inferred` (the agent
proposed them; the user accepted but didn't originate them). If the
user edited the sweep candidate in step b's free-text path, promote to
`confirmed` as usual.

### Caps (per-list)

- **Soft cap**: 10 items per critical list (the `features` list runs
  3–10 for a focused product). The sweep can take a list past 10 if the
  user keeps picking candidates; that's intentional — a real product has
  as many FRs as it has, and there is no post-MVP list to spill into.
- **Hard cap**: 20. After that, refuse politely and suggest routing
  lower-priority ideas to `open_questions.parking_lot` (for FR) or
  splitting the NFR list into more focused buckets.

### State-write timing

Write state after:

- each item's step c approval (single-item granularity), and
- each completed sweep pass (so partial sweeps survive EXIT).

This keeps `EXIT` cheap.

### Confidence (list-level)

Items added via step a (user picked a suggestion as-is) get
`confidence: inferred`. Items that went through any free-text
iteration get `confidence: confirmed`. The whole list inherits the
*lowest* confidence of its items if you record list-level confidence.

## The `nested_freeform` flow

Currently applies only to the `conventions` field. The output is a
`Dict[str, Any]` whose shape is project-defined — named buckets where
each bucket's sub-structure is *not* fixed by the schema. The
validator only type-checks the top-level mapping; everything inside is
up to the project.

This tier exists because the existing `critical` flow assumes "title
plus detail merges into one string item with an assigned `<PREFIX>-NNN`
ID". That shape is wrong for conventions, where each bucket has its
own free-form nested body (scalars, lists, maps — whatever the project
needs) and has no ID.

### Run as the LAST mini-section of its theme — a synthesis pass

`conventions` lives in its own theme at the end of `prd-questions.yaml`,
after `open_questions`. By the time this question runs, the agent has
seen every other answer and can spot cross-cutting patterns that
downstream stages must honor verbatim. Treat it as a **synthesis pass**,
not a single fill-in question: it is the conventions analogue of the
`critical` scope-completeness sweep, and it is where the most manual
rework lands when done thinly.

**Before step a, read `references/conventions-catalog.md`.** It carries
~12 project-agnostic bucket archetypes (artifact_ids, schema_versioning,
nfr_propagation, code_style, testing_policy, severity rubrics,
dependency/supply-chain policy, directory_layout, data_conventions,
api_conventions, observability, domain_glossary, stage_contracts), each
with a "propose when" trigger and a skeletal body. It is the menu you
reason *from* — not a checklist to fill.

### Per-bucket state machine

#### Step a — reflect, then propose convention bucket names

First do the **structured reflection** (same discipline as the `critical`
sweep), across three lenses:

1. **The answers themselves** — an ID/naming scheme spanning lists, a term
   recurring with a precise meaning, NFRs naming downstream stages, a
   code-style/testing rule that kept surfacing.
2. **Every upstream ID family** (FR/NFR/ENT/WKF/INT/AIF) — a rule about how
   a family is referenced by later stages is a convention, not a feature.
3. **The project type** — CLI tool, SaaS app, library/SDK, data pipeline,
   AI-orchestration framework, regulated app: each carries different
   "rules everyone forgets to write down". Match the catalogue archetypes
   against this project's profile.

Then surface the candidate bucket names you actually see via one
`AskUserQuestion` (multi-select) — typically 2–4 per pass, drawn from the
catalogue plus anything project-specific. Always include "Done — no
conventions / no more conventions" as an explicit option:

```
header: "Conventions"
question: "Any binding cross-cutting conventions downstream stages must
  honor? Pick any candidates you want to define, or wrap up."
options:
  - { label: "⚠ artifact_ids",      description: "⚠ The cross-stage ID rules you've mentioned (FR-###, ENT-###, …). Pick to draft the bucket body next." }
  - { label: "⚠ schema_versioning", description: "⚠ Per-artifact versioning policy and migration rules." }
  - { label: "⚠ nfr_propagation",   description: "⚠ Map of which NFR/PRD fields each downstream stage must read." }
  - { label: "Done — wrap up",      description: "No (more) conventions to define. Close the conventions block." }
```

The user can also type a bucket name in the free-text field that the
agent didn't propose. For each accepted bucket name → step b. After
all buckets are drafted, return here for another pass (max 2 passes
total — see "Caps" below).

**Anti-padding rule:** if you genuinely don't see any cross-cutting
convention worth surfacing (small CLI, single-script utility, etc.),
ask **one** `AskUserQuestion` with options `["Define conventions
manually — type bucket name", "Skip conventions — none apply"]` and let
the user opt in.

#### Step b — draft the bucket body

For each accepted bucket name, draft a free-form nested YAML body that
captures the rule. The body shape is *project-defined* — it can be a
scalar, a list, a flat map, a nested map, or any combination. The agent
picks the shape that best expresses the rule, drawing on prior answers.

Show the draft **inside the approval question** (channel rule above): the
question text carries the one-line provenance comment, and the "Approve
as-is" option's `preview` carries the bucket's YAML body:

```
"Based on the FR-### and ENT-### references in your features list
and your earlier mention of stable IDs, here's a draft for the
`artifact_ids` bucket:"

```yaml
conventions:
  artifact_ids:
    binding: true
    description: "Canonical 3-letter cross-stage IDs..."
    scope:
      - "Every stage artifact that emits or references one of the id_types"
    id_types:
      FR: "Functional Requirement — ..."
      ENT: "Data Entity — ..."
```

Then ask via `AskUserQuestion`:

```
header: "Approve?"
question: "Approve this `<bucket>` body, or iterate?"
options:
  - { label: "Approve as-is",           description: "Write to conventions.<bucket> and move on.", preview: "<the YAML body above>" }
  - { label: "Iterate — type changes",  description: "Use the text field to describe what to change, add, or remove. The agent will re-draft." }
```

On approve → write `conventions.<bucket>` with the drafted body.
On iterate → re-draft with the user's free-text guidance. Repeat
steps b–approve up to 3 times.

**Iteration cap**: after 3 b-iterations on a single bucket, write the
current draft, append a one-line `prd_warnings` entry naming the bucket,
and move on to the next bucket (or step c).

#### Step c — loop or close

After each bucket completes, loop back to step a with the buckets
already written excluded from the candidate list. The user can keep
adding buckets until they pick "Done — wrap up" or until the caps
trigger.

### Caps (per `conventions` block)

- **Sweep-pass cap**: 3 passes through step a maximum. After three passes
  even if you still see candidates, defer them to `prd_warnings`:
  `"conventions: sweep suggested but not added — <bucket>, <bucket>"`
  and close the block. (Raised from 2: conventions-rich projects surface
  buckets in waves as the agent works through the catalogue lenses.)
- **Bucket count cap**: soft cap 15 buckets. A conventions-rich project
  (a multi-stage pipeline, a regulated app, a framework) legitimately
  needs a dozen-plus buckets — do NOT let the cap force you to drop a
  real cross-cutting rule (the demo PRD this skill was tuned against
  carries 13). Only past 15 should you pause and ask the user whether to
  collapse related buckets or accept the remainder as `prd_warnings`.
- **Empty conventions**: writing `conventions: null` (or omitting the
  key entirely) is fine — most simple projects have no binding
  cross-cutting rules. Don't push.

### State-write timing

Write state after **each bucket's approval in step b**, not at the end
of the whole block. This keeps `EXIT` cheap. The on-disk shape of the
state's `partial_answers.conventions` mirrors the output YAML.

### Validation

The validator (`validate_schema.py`) only checks that `conventions` is
either `null` or a `Dict[str, Any]`. It does not enforce sub-keys,
value types, or nesting depth — those are deliberately project-defined.

The ID-family check skips `conventions` entirely. Items inside
conventions are *not* expected to carry `<PREFIX>-NNN` prefixes — they
are addressed by bucket name and sub-path.

## product_identity — the synthesis batch

`product_identity` is asked LAST among required themes so the agent has
rich context by the time it runs. All `product_identity` fields are
`med` (the heavy lifting was already done by `product_identity.idea_text`,
captured verbatim in Phase 3). They run as a single `AskUserQuestion`
batch where every candidate option is `⚠ inferred` from prior answers.

Example:

```
AskUserQuestion(questions=[
  {
    header: "Identity",
    question: "What is the product's name? (Synthesized from your prior answers.)",
    options: [
      { label: "⚠ flowcraft", description: "⚠ Inferred from your assembly metaphor. Pick to confirm or use text field to correct." },
      { label: "⚠ mosaic",    description: "⚠ Pieces composing into a whole." },
      { label: "⚠ loom",      description: "⚠ Weaving workflows together." },
      { label: "Custom name", description: "Type your preferred name in the text field." }
    ]
  },
  {
    header: "Identity",
    question: "Preferred URL/package slug? (kebab-case)",
    options: [
      { label: "⚠ flowcraft", description: "⚠ Auto-derived from inferred name. Confirm or correct." },
      { label: "Custom slug", description: "Type a kebab-case slug in the text field." }
    ]
  },
  {
    header: "Identity",
    question: "Describe the product in one sentence (≤ 140 chars).",
    options: [
      { label: "⚠ Inferred one-liner", description: "⚠ \"Compose AI workflows visually, run them anywhere — even offline.\" Confirm or correct." },
      { label: "Custom one-liner", description: "Type your own in the text field." }
    ]
  }
])
```

**Hallucination guard**: all `⚠`-marked options require explicit
pick-or-correct from the user. Accepting one counts as confirmation;
the user can also use the "Other" field to correct. Never treat a
non-answer as implicit acceptance.

Explicitly call out in the batch header that candidates were
synthesized from prior answers — don't present them as facts.

## When the user EXITs mid-flow

`EXIT` works at every `AskUserQuestion` call regardless of tier. On
exit:

- For a `med` question: no special handling; state is written after the
  batch the question lived in, so the question's prior batch is saved.
- For a `high` mini-section: write whatever has been collected so far
  (e.g. the partial list for list[string] fields, or no value at all
  if no item was approved). Mark the field's `<field>_confidence` as
  `assumption` if any partial content was written.
- For a `critical` mini-section: write the partially-approved items
  to the list. The unfinished current item is dropped (not written
  partial). If EXIT arrives mid-sweep (step e), write the items
  collected so far; do not finalize the sweep pass. Set
  `<field>_confidence: assumption`. Add a `prd_warnings` entry:
  `"<field>: list incomplete — EXIT received mid-item N"` (or
  `"<field>: list incomplete — EXIT received mid-sweep pass M"`).
- For a `nested_freeform` mini-section: write the buckets that were
  fully approved (`conventions.<bucket-name>` complete). The
  unfinished current bucket is dropped (not written partial). Add a
  `prd_warnings` entry: `"conventions: incomplete — EXIT received
  while drafting bucket '<name>'"`.

Then proceed with the normal abort flow from `interview-mechanics.md`:
set `status: aborted`, save state, confirm to user, stop.
