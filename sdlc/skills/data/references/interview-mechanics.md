# Interview mechanics

How to actually run the Phase 6 interview: AskUserQuestion batch format,
EXIT semantics, and the three importance-tier flows (`med | high | critical`).

Read this when you enter Phase 6. Read it whenever the next question's
`importance` is `high` or `critical`.

## AskUserQuestion batch format

The tool's hard limit is 4 questions per call. Default to 2–3 so the user
isn't overwhelmed.

For each `med` question, build one option block:

```
{
  "question": "<verbatim from data-questions.yaml>",
  "header": "<≤12-char chip label>",
  "multiSelect": false,
  "options": [
    {"label": "<pre-filled candidate>",  "description": "..."},  # ⚠ inferred or ✓ found — position 1
    {"label": "<option 2>",              "description": "..."},
    {"label": "<option 3>",              "description": "..."},
  ]
}
```

Rules:

- The `⚠ inferred` candidate is **always** at position 1, labelled
  `"(Recommended) <value>"`. The user must explicitly pick it — never
  auto-accept.
- If `free_text_allowed: true`, the runtime appends an "Other" free-text
  option automatically. Do not include it manually.
- `header` is a 12-char chip for screen-readers; pick something punchy like
  "Primary DB", "PII fields", "ID scheme".
- For `suggested_answers: []` questions, run them free-text-only: still
  build an AskUserQuestion call with one position-1 draft option (the
  agent's proposed answer) and let the user accept or type their own.

## EXIT (case-insensitive)

If the user types `EXIT` into any free-text field:

1. Set `state.status = "aborted"`.
2. Write current `partial_answers` to state.
3. Confirm to user: *"Saved progress to .claude/skills-state/sdlc-data.state.yaml.
   You can resume by running /sdlc:data again."*
4. Stop. Do not attempt validation or CLAUDE.md updates.

There is no SAVE — saving is implicit after every confirmed batch.

## Tier: `med` (default)

- Batch up to 3 sibling `med` questions from the same theme into one
  AskUserQuestion call.
- Pre-filled `⚠ inferred` candidate at position 1 with the
  `"(Recommended)"` prefix.
- After the user answers, write state immediately.
- Then move to the next batch.

Most questions in `data-questions.yaml` are `med`.

## Tier: `high` — mini-section with draft-approve loop

`high` questions run as their **own** AskUserQuestion call (never batched).

**For scalar answers** (e.g. `persistence.primary_store_rationale`):

1. Agent drafts a full answer from upstream context.
2. Show the draft + 3–4 alternative phrasings as options.
3. Loop up to 3 rounds: if the user picks "rewrite" or types a refinement,
   re-draft incorporating their notes.
4. On user approval, write state and move on.

**For list[string] answers** (e.g. `data_classification.pii_fields`,
`indexes_and_queries.access_patterns`, `external_data_sources`):

1. Agent drafts the full list from upstream context.
2. Show the list, ask: "approve as-is, edit specific items, add more, or
   remove some?"
3. Per-item: one clarifying challenge round each (e.g. "I see `User.ssn`
   in pii_fields — is this actually a US Social Security Number? If not,
   it shouldn't be regulated_fields.").
4. Approve the whole list when satisfied.

Iteration cap: 3 rounds. If round 3 still hasn't converged, ask the user
to write the answer in free text and accept it as-is.

`high` questions in this skill: `persistence.primary_store`,
`persistence.secondary_stores`, `relationships`, `access_patterns`,
`pii_fields`, `regulated_fields`, `external_data_sources`,
`scale_and_retention.partitioning_key` (when promoted).

## Tier: `critical` — per-entity state machine (the `entities` theme)

`entities` is the only `critical` theme in this skill. It runs a full
per-entity drill-down — propose → describe → fields → primary_key →
traces → approve → next entity. This is the data-model analogue of PRD's
`features` per-feature flow.

Because the theme is also marked `synthesis: true`, the per-entity
loop is followed by a **dynamic scope-completeness sweep** (drawing
on every upstream ID family: PRD `ENT-NNN`, `FR-NNN`, `WKF-NNN`,
`JTB-NNN`, and UX `SCR-NNN`) before the theme is allowed to close.
See `references/entity-discovery.md` "Scope-completeness sweep" for
the procedure, caps, and anti-padding rule.

**The field/key steps (d, e) are paradigm-dependent.** The set of
entities is the same across paradigms (the domain doesn't change), but the
per-field attributes and whether a primary key exists differ. Use the field
shape from `references/paradigms/<selected-paradigm>.md` — summarized in the
step (d)/(e) notes below.

### State machine per entity

For each entity in `state.defined_entities` (Phase 3 already drafted the
list), iterate through the following states:

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │                                                                     │
   │   (a) PROPOSE       Show pre-drafted entity card                    │
   │        │            (description + candidate fields drafted from    │
   │        │            UX forms, schema files, and PRD FR-NNN traces)   │
   │        ▼                                                            │
   │   (b) CHALLENGE     Ask one clarifying question if anything looks   │
   │        │            ambiguous (e.g. "I see `Order` and `Invoice`    │
   │        │            both — are these distinct entities or aliases?")│
   │        ▼                                                            │
   │   (c) DESCRIPTION   Confirm or rewrite the one-sentence purpose.    │
   │        │                                                            │
   │        ▼                                                            │
   │   (d) FIELDS        Per-field batch (2-4 fields per AskUserQuestion │
   │        │            call). Attributes are PARADIGM-DEPENDENT (see    │
   │        │            note below). Auto-add audit columns if           │
   │        │            audit_and_lifecycle.audit_columns enabled        │
   │        │            (relational/document only).                     │
   │        ▼                                                            │
   │   (e) KEY / IDENTITY Relational/document: confirm primary_key.       │
   │        │            file_native: SKIP (path-derived; captured in     │
   │        │            identity_conventions). graph/vector/key_value:   │
   │        │            SKIP (identity is store/key-design concern).     │
   │        ▼                                                            │
   │   (f) TRACES        Confirm traces_prd_features (FR-NNN list),      │
   │        │            traces_ux_surfaces (SCR-NNN list), and          │
   │        │            traces_prd_workflows (WKF-NNN list, optional).  │
   │        ▼                                                            │
   │   (g) FINAL APPROVAL Show the full entity card; user confirms or    │
   │        │             requests revisions (back to any earlier step). │
   │        ▼                                                            │
   │   (h) WRITE STATE    Persist this entity to state.partial_answers   │
   │        │             under entities.<EntityName>; set its status    │
   │        │             to confirmed.                                  │
   │        ▼                                                            │
   │   (i) NEXT or DONE   If more entities pending, loop to (a) for next.│
   │                      Else: theme complete.                          │
   │                                                                     │
   └─────────────────────────────────────────────────────────────────────┘
```

### Step (d) field attributes by paradigm

| paradigm    | per-field attributes to elicit                                          |
|-------------|-------------------------------------------------------------------------|
| relational  | `type` (enum), `nullable`, `unique`, `primary_key`, `default`, `references`, `on_delete`, `check` |
| document    | `type`, `nullable`, `unique`; embedded children via `composition`       |
| file_native | `pydantic_type` (literal Python type) + `description`; NO nullable/unique/pk |
| graph       | node properties: `type` (+ `nullable`); edges captured in the `edges` theme |
| vector      | payload fields (`type`); mark the embedding-source field `embedding: true`; list `payload_fields` |
| key_value   | `type` per attribute; the key itself is captured in `key_value_design`  |

### Schema-path rewriting

The questions tagged `theme: entities` in `data-questions.yaml` use a
`entity.<field>` prefix on `schema_path`. The agent rewrites this prefix
at runtime per entity:

- For entity `User`: `entity.fields` → `entities.User.fields`,
  `entity.description` → `entities.User.description`, etc.
- For entity `Order`: `entity.fields` → `entities.Order.fields`.

This pattern is borrowed from sdlc-ux's `surface.<field>` rewrite (see
ux/SKILL.md Phase 11). It lets one question definition serve every entity
without duplicating prompts.

### EXIT during per-entity drill-down

If the user types EXIT mid-entity:

- Write the current partial entity to `state.partial_answers.entities.<Name>`.
- Mark the entity's status as `draft` (not `confirmed`).
- Set `state.current_entity = <Name>` so resume jumps back to it.
- Then do the normal EXIT actions (status: aborted, save, stop).

### Auto-derived fields

`audit_and_lifecycle.audit_columns` is answered up-front in **Phase 4
(audit-columns preliminary)** — before the per-entity drill-down begins
— precisely so it can drive auto-add behavior here. If that preliminary
question has been answered (e.g. user picked
`[created_at, updated_at, deleted_at]`), the agent auto-adds those
columns to every entity's `fields` block during step (d) unless the
user opts out per-entity. This avoids 20× "yes add created_at" prompts.

If the user skipped or hadn't yet answered the Phase 4 preliminary
(possible on a partial resume), step (d) instead asks once at the start
of the FIRST entity: *"Add `created_at`/`updated_at` to every entity by
default?"* — and writes the answer back to
`state.partial_answers.audit_and_lifecycle.audit_columns` so subsequent
entities inherit it. The full `audit_and_lifecycle` theme later expands
the picture (soft delete, archive).

## Position-1 hallucination guard

Every `AskUserQuestion` call where the agent has a pre-filled candidate
must place that candidate at position 1 with the `"(Recommended) "`
prefix. The user has to explicitly select or correct it — there is no
silent accept.

This guard exists because pre-fills are derived from PRD/UX heuristics and
can be wrong. The single most common failure mode of an AI-driven data
modelling pipeline is "agent invented an entity from a passing reference,
user didn't notice, now downstream agents are designing endpoints for
something that shouldn't exist." Force the user to look.
