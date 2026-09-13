# Entity discovery heuristics

How to derive the *draft* entity list in Phase 3 from PRD + UX + repo
signals. This phase is the most hallucination-prone in the whole skill,
because entities are nouns and nouns appear in every requirement
description. Read this before Phase 3.

**Paradigm-independent.** Entity discovery (and the scope-completeness sweep)
runs the same way regardless of the storage paradigm chosen in Phase 4 — the
*domain model* is the same set of nouns whether they end up as SQL tables,
documents, graph nodes, vector collections, or serialized Pydantic models. Only
the per-entity *field shape* (filled in Phase 6) and the surrounding structural
themes differ by paradigm. So discover the same entity list either way; just
note that downstream you may call them "nodes" (graph) or "collections"
(vector/document) when talking to the user, to match their mental model.

## Source priority

1. **`PRD.data_model.key_entities`** — the user already named these. Each
   entry is shaped `"ENT-NNN: <Name>"` or `"ENT-NNN: <Name> — <description>"`
   per the PRD convention. Strip the `ENT-NNN: ` prefix and split on
   the first ` — ` (em-dash or `--`) to extract the PascalCase
   `<Name>`. Treat verbatim. Tag `✓ found`. Persist the original
   `ENT-NNN` id alongside the name in `state.defined_entities[].ent_id`
   so the sweep (below) can detect missing PRD ENT ids.
2. **Schema files on disk** (`schema.prisma`, `*.sql`, `models/`,
   `entities/`, Django `models.py`, SQLAlchemy `declarative_base`
   subclasses) — authoritative if present. Tag `✓ found`.
3. **`PRD.functional_requirements.features`** (FR-NNN list) —
   each entry is `"FR-NNN: <title> — <description>"`. Extract candidate
   entity nouns from BOTH the title and the description (the
   description often names the entity directly, e.g. "FR-031: End-to-end
   MVP demo: factory takes a one-paragraph idea (e.g. recipe manager,
   scheduling app) and produces a runnable repo with passing tests").
   Tag `⚠ inferred`.
4. **`UX__<surface>.yaml.layout` + `validation_rules` +
   `components.content_slots`** — forms imply entities; list items imply
   entities; filters imply entities. Tag `⚠ inferred`. Note: the surface
   reference for a confirmed entity is `SCR-NNN` (from
   `UX.surface_inventory[].id`), NOT the editable `surface_id` slug.
5. **`PRD.use_cases.core_workflows`** (WKF-NNN list) — workflows often
   imply state-bearing entities the FR list overlooks (e.g. a
   `BranchSession` entity from "switch git branch and continue work").
   Tag `⚠ inferred`. These are the primary signals the
   scope-completeness sweep (below) draws on.

Higher-priority sources override lower ones. If PRD names `User` and a
UX form has a field labelled "Account", treat them as the same entity
(prefer the PRD name) unless the user disambiguates.

## Heuristics for extracting entities from FR-NNN features

A typical PRD feature reads like: *"FR-001: Quick add a task with a
keyboard shortcut."* The candidate entity is the **direct object of the
main verb**, capitalized and singularized:

| Verb pattern              | Likely entity        |
|---------------------------|----------------------|
| `add/create/insert <X>`   | `<X>` (singularized) |
| `delete/remove <X>`       | `<X>`                |
| `update/edit/modify <X>`  | `<X>`                |
| `list/show/view <X>`      | `<X>` (plural form in UI implies entity exists) |
| `assign <X> to <Y>`       | `<X>` and `<Y>`; expect a relationship |
| `share <X> with <Y>`      | `<X>`, `<Y>`, and a join entity (e.g. `<X>Share`) |
| `notify <X> when <Y>`     | `<X>`, plus a `Notification` or `Event` entity |
| `import/export <X>`       | `<X>` plus possibly `Import`/`Export` job entities |
| `audit <X>` / `track <X>` | `<X>` plus an `AuditLog` entity |

Treat these as **candidates only**. Each must surface in Phase 3 with the
source FR-NNN ID quoted, so the user can correct.

## Heuristics for extracting entities from UX surfaces

Read each `docs/UX__*.yaml`. For each surface:

- **`layout.region_tree`** — region names like `task-list`, `user-card`,
  `order-summary` strongly imply the kebab-cased noun is an entity.
  Convert to PascalCase: `Task`, `User`, `Order`.
- **`components`** — a component with `type: list` or `type: table` whose
  rows are named (e.g. `row_template: TaskRow`) implies the entity.
- **`validation_rules`** — a rule like `field: "email"` implies a form
  field; the form's submission target is usually an entity.
- **`interactions.effects`** — strings like `"create task in store"`,
  `"update user profile"` are direct signals.
- **`cli_args`** (CLI surfaces) — positional args often map to entity IDs
  (e.g. `task-id`, `user-id`).

A surface that has no `validation_rules` and no list/table component is
probably *not* a data-bearing surface (e.g. a marketing splash page,
loading screen). Such surfaces do not contribute entity candidates.

## Heuristics for relationships at discovery time

While drafting candidates, also draft **probable relationships**. The
following imply edges:

- Two entities named together in one FR-NNN feature → likely related.
- A UX surface that displays one entity but filters/sorts/links by
  another → many-to-one foreign key.
- A "list of X within Y" pattern (e.g. "list tasks within a project") →
  `1:N` from Y to X.
- A "tag", "label", "category" suffix → typically `N:M` with a join
  table (e.g. `TaskTag`).

Surface these as proposals during Phase 6's `relationships` theme. Do not
quietly write them.

## What NOT to do

- **Don't invent abstract "Manager" or "Service" entities**. Those are
  application-layer concepts, not data entities. If you see `TaskManager`
  in the PRD, that's likely a service, not a row in a table.
- **Don't propose `Settings` or `Configuration` entities unless there's
  explicit evidence**. Most apps store config in env vars or
  filesystem files, not the DB.
- **Don't propose audit/log entities unless audit_logging is enabled
  in PRD**. If you do propose them, label clearly as `⚠ inferred from
  PRD.security_compliance.audit_logging`.
- **Don't fold two distinct nouns into one entity** to be "clever". If
  PRD names both `Order` and `LineItem`, keep them separate even if you
  could imagine modelling lines as a JSON column on Order.
- **Don't propose junction/join entities until the relationship theme**.
  Discovery is for first-class nouns. N:M join entities surface naturally
  when the user confirms a many-to-many relationship.

## Surfacing candidates to the user

Present the draft list as:

```
I found these entity candidates:

  ✓ User                  (from PRD.data_model.key_entities)
  ✓ Project               (from PRD.data_model.key_entities)
  ✓ Task                  (from schema.prisma model Task)
  ⚠ Tag                   (inferred from UX__dashboard form 'tags')
  ⚠ Comment               (inferred from FR-003 "Add a comment to a task")
  ⚠ Notification          (inferred from FR-007 "Notify users when …")

Add, remove, rename, or skip any of these before we go deep. Each ⚠
needs your explicit confirmation — type 'confirm Tag', 'rename Tag→Label',
'drop Notification', or describe what you'd rather have.
```

Persist the confirmed list to `state.defined_entities` as a list of
`{name, ent_id (if any), status: confirmed|dropped, source}`. Dropped
entries go to `state.dropped_entity_candidates` so they don't get
re-proposed on resume.

## Scope-completeness sweep (theme `entities`, after the per-entity loop)

The `entities` theme is marked `synthesis: true` in `data-questions.yaml`.
After the per-entity drill-down loop closes — i.e. after the user picks
"Done — wrap up the list" in the standard `critical` flow — the agent
MUST run a dynamic scope-completeness sweep before the theme is allowed
to close. This is the single most important defence against missing
entities the upstream artifacts imply but the draft list overlooks.

### What to reflect on (every pass)

1. **The draft entity list itself** — what kinds of entities dominate?
   What kinds are conspicuously absent given the upstream IDs?
2. **Every upstream ID family**, not just the most-direct one:
   - `PRD.data_model.key_entities` (ENT-NNN) — are all PRD ENT ids
     present in the draft? Any ENT-NNN whose name doesn't appear?
   - `PRD.functional_requirements.features` (FR-NNN) — every
     FR's description text. Does any feature description name a
     state-bearing noun (registry, log, session, queue, marker) that
     the draft doesn't have?
   - `PRD.use_cases.core_workflows` (WKF-NNN) — does any workflow imply
     a persistent entity (e.g. "switch branch" → `BranchSession`,
     "resume after exit" → `CheckpointRecord`) that the draft missed?
   - `PRD.use_cases.primary_jobs_to_be_done` / `secondary_jobs`
     (JTB-NNN) — similar implications.
   - `UX.surface_inventory[].references_entities` — every ENT-NNN that
     UX claims to display must have a matching entity in the draft.
   - `UX__<surface>.yaml` — every form field, list/table component,
     and filter implies an entity behind it.
3. **Project-type heuristics** — a CLI tool, a SaaS app, a library, and
   a pipeline each have different "things people forget":
   - SaaS app: tenant boundary, audit log, user session, password reset
     token, idempotency key.
   - CLI tool: project registry, branch session, cost record, run log.
   - Library: typically zero entities (it's not data-bearing).
   - Pipeline: stage state, checkpoint, retry record, dead-letter queue.

### Format of the sweep question

Format as **one** multi-select `AskUserQuestion` call surfacing the
agent's top 2–4 candidate entities — concrete names, not category
labels. "You might be missing `BranchSession` (implied by WKF-004 'switch
git branch')" beats "have you considered session entities".

```
header: "Scope sweep"
question: "Looking at your N entities alongside upstream PRD/UX ids, a
  few candidates look notable that aren't in the list yet. Add any
  of these, or wrap up?"
options:
  - { label: "⚠ <CandidateEntity1>", description: "⚠ Implied by <upstream ref, e.g. WKF-004 ...>. Pick to draft it through the per-entity state machine." }
  - { label: "⚠ <CandidateEntity2>", description: "⚠ Implied by <upstream ref>. Pick to draft." }
  - { label: "⚠ <CandidateEntity3>", description: "⚠ Implied by <upstream ref>. Pick to draft." }
  - { label: "Wrap up — list is complete", description: "Skip these. The list closes as-is." }
multiSelect: true
```

For each picked candidate: enter the per-entity state machine at
**step a-2** (challenge if free-text); confirm description → fields →
primary_key → traces → final approval. Then return to the sweep for a
second pass.

### Caps

- **Sweep-pass cap**: at most 2 passes per session. After two passes,
  even if you still see candidates, defer them to `data_warnings`:
  `"WRN-NNN: entities sweep suggested but not added — <Candidate>,
  <Candidate>"`. Persist the WRN counter to `state.last_ids.WRN`.
- **Anti-padding rule**: if you don't see *concrete* candidates after
  honest reflection, surface 0 — close the list without a sweep
  question. Don't manufacture candidates to look thorough.
- **Empty list**: if the user added 0 entities in the main loop,
  surface a single `data_warnings` note (`"WRN-NNN: entities: empty
  list — no entities collected"`) and don't push.

### State-write timing

Write state after each completed sweep pass (so a partial sweep
survives EXIT mid-pass). On EXIT mid-sweep, the items collected so far
stay in `state.partial_answers.entities`; an additional WRN-NNN entry
records `"entities: list incomplete — EXIT received mid-sweep pass M"`.

### Skip the sweep at your peril

The sweep is the single most important defence against synthesis-stage
gaps — the kind where an entity implied by a PRD workflow or by a UX
surface didn't make the draft because the agent only seeded from PRD
`data_model.key_entities`. Always run it unless the anti-padding rule
fires.
