# Interview mechanics — sdlc-arch

This file specifies the *how* of running the architecture interview:
AskUserQuestion batches, EXIT semantics, importance tiers, and the per-item
state machines for `critical` themes. Read this on entering Phase 6 of either
mode.

## AskUserQuestion batch format

The hard tool limit is **4 questions per call**. Aim for 2–4 so each batch is
short enough to answer without scrolling.

For each question:

- **Title in the UI**: the `question` field from `arch-questions.yaml`.
- **Options**: the `suggested_answers` list, with the inferred recommendation
  *at position 1* prefixed `(Recommended) `.
- **Hint** (passed as the question description): the `hint` field, kept
  short. If the question carries a `_confidence` sibling, mention "Pick
  'Other' to provide a custom value (confidence: confirmed); pick the
  recommendation to accept the inferred value (confidence: inferred)."
- **Free text**: enabled iff `free_text_allowed: true` in the inventory.
  The user can type a custom answer OR a reserved command (`EXIT`,
  `confirm`, `ok`, `confirm all`, etc.) in this field.

Number questions within a batch consecutively (1., 2., 3., 4.) so the user
can refer back to them. Renumber after skipping any.

## EXIT semantics

At any prompt, the user can type `EXIT` (case-insensitive) into the free-text
field of any AskUserQuestion call.

On detection:

1. Set the *active* sub-session's `status: aborted` in the state file.
2. Write the current `partial_answers` and any per-item snapshot
   (`current_container` / `current_component`).
3. Confirm to the user that state was saved and stop.

Saving is implicit after every confirmed batch — there is no `SAVE` command.
The user never loses progress.

## Importance tiers

Each question has an `importance` field. Three flows:

### `med` — batched

Up to 3 sibling `med` questions from the same theme go into one
AskUserQuestion call. `⚠ inferred` candidates appear at position 1.

### `high` — own mini-section

`high` questions run as their own mini-section. Two sub-flows:

- **Scalar fields** (e.g. `architecture_pattern.pattern`):
  1. Agent drafts a full answer, including a one-sentence rationale.
  2. Show the draft to the user — and END the turn with it (the typed
     `ok`/`confirm` reply is the approval channel), or carry the draft
     inside an `AskUserQuestion` option's `preview`; chat markdown sharing
     a turn with a tool call may not render (the channel rule: AUTHORING
     §18, `../../prd/references/importance-flows.md`).
  3. User approves (`ok` / `confirm`) or iterates ("change pattern to
     microservices because we have 5 teams").
  4. Cap at 3 iteration rounds. After the cap, default to the last
     proposal and surface a warning.
- **List[string] fields** (e.g. `tech_stack.key_libraries`):
  1. Agent drafts the list.
  2. One AskUserQuestion call per item with options "keep" /
     "rephrase" / "drop" / "Other (replace)".

### `critical` — per-item state machine

Used by `container_inventory`, `cross_container_edges`,
`component_inventory`, `per_component_deepdive`, and
`internal_and_external_edges`. The state machine has 4 sub-phases per item:

1. **propose** — the agent presents the item's pre-filled fields
   (`archetype`, `purpose`, `owns_*`, etc.) sourced from the upstream
   artifacts. Each `⚠ inferred` field has the inferred value at option 1.
2. **challenge** — for any field the agent is uncertain about, it raises
   a one-question challenge ("Are you sure `users` should own
   `payments` too?").
3. **detail** — fill the remaining required fields for the item.
4. **approve** — single confirmation question ("Confirm `backend-api` as
   a `backend-api` container owning `users`, `projects`, persisting to
   `primary-postgres`?"). On confirm: set the item's
   `status: confirmed` and persist before moving on.

State writes happen after **every approved item** — not at the end of the
list. If the user EXITs mid-list, the items already approved are kept; the
in-progress item is restored on resume.

## Synthesis themes

Two distinct kinds of synthesis theme exist in arch:

1. **Scope-defining inventories** — `container_inventory` (system) and
   `component_inventory` (container) carry `synthesis: true` in
   `arch-questions.yaml`. They run the full `critical` per-item state
   machine AND, after the per-item loop closes, a **scope-completeness
   sweep** that draws on every upstream ID family to catch missed
   items. See `references/container-discovery.md` /
   `references/component-discovery.md` for the per-theme sweep spec, and
   `sdlc/skills/prd/references/importance-flows.md` for the canonical
   procedure (anti-padding rule, 2-pass cap, defer-to-`WRN-NNN`).
2. **Edge derivation** — `cross_container_edges` and
   `internal_and_external_edges` generate a candidate edge list,
   present it as a diff, and the user confirms or edits. These do NOT
   run the scope sweep (edges are derived from the already-finalized
   node set, not a scope decision).

### Edge derivation

The presentation format is:

```
I derived these edges for `<scope>`:

  KEEP   1. calls           → backend-api
  KEEP   2. writes          → primary-postgres
  ADD    3. publishes       → notification-bus
  RETYPE 4. depends_on → calls  → auth-provider
  REMOVE 5. depends_on      → legacy-batch-runner

Confirm all, or edit:
  - "confirm all"
  - "remove 5, keep 4 as depends_on"
  - "add: subscribes_to billing-events"
  - "retype 3 as publishes"
```

`KEEP` rows are already in the artifact and survived re-derivation.
`ADD`, `REMOVE`, `RETYPE` are the diff against the current state.

Accept user free-text edits in the AskUserQuestion's "Other" field; parse
deterministically and apply only the requested changes.

## Conditional promotion

Some questions are promoted to required by `required_if`. The agent
re-evaluates `required_if` expressions at the start of each new theme
batch. If a question becomes required mid-theme, surface it before
advancing to the next theme.

## Pre-fill confidence rules

Two values for `<field>_confidence`:

- `confirmed` — user explicitly picked the value (custom or recommended).
- `inferred` — user accepted the position-1 recommendation as-is, OR
  the value was pre-filled directly from an upstream artifact without
  needing user touch.

The third value, `assumption`, is reserved for fields where no upstream
evidence exists and the agent had to guess; should be rare in arch
because PRD/UX/DATA/API cover most upstream territory.

## Hallucination guards

Three non-negotiable rules in every interview phase:

1. `⚠ inferred` candidates surface as the **position-1 recommended option**
   in their AskUserQuestion call. They cannot be silently accepted —
   the user must explicitly pick or correct.
2. State is written after **every confirmed batch, mini-section, and
   per-item step** — not at theme boundaries.
3. The agent NEVER fabricates a `container_id`, `component_id`,
   `resource_id`, `surface_id`, or `entity name` that has no upstream
   evidence. If a candidate isn't in PRD/UX/DATA/API, the agent
   surfaces it as a *new addition the user proposed*, not as inferred.
