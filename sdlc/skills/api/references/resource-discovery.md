# Resource discovery — how to enumerate, name, and deep-dive resources

Read this when entering **theme 8 (`resource_inventory`)** or **theme
10 (`per_resource_deepdive`)**. Both are `critical` per-item flows;
this file is the source of truth for how the agent drives them.

The core idea: **a resource is the smallest cohesive unit of the API
that operates on (typically) one DATA entity**. For a REST API that
usually means "all endpoints under a shared `base_path`". For GraphQL
it's the Query/Mutation root for one entity. For gRPC it's one
`service` definition.

A resource always has an `id`, a `base_path`, a `primary_entity`
(unless cross-cutting like `/search`), endpoints, and traces back to
PRD features + UX surfaces.

## Step 1 — Generate the candidate list

The candidate set is the union of three axes:

1. **DATA entities** (the primary axis). For each entity in
   `DATA-MODEL.yaml.entities`, propose one CRUD resource:
   - `User` entity → `users` resource at `/v1/users`
   - `Order` entity → `orders` resource at `/v1/orders`
   Entities listed in `enums_and_lookups.lookup_tables` are usually
   read-only — propose `list-<resource>` + `get-<resource>` only,
   skip Create/Update/Delete.
2. **PRD features that don't map 1:1 to an entity**. Cross-entity
   workflows often deserve their own endpoint group:
   - PRD feature "Bulk-import tasks from CSV" →
     `imports` resource at `/v1/imports` (no single primary entity)
   - PRD feature "Search across projects + tasks" →
     `search` resource at `/v1/search` (primary_entity: null)
3. **UX surfaces with data I/O** that imply endpoints the entity list
   misses:
   - UX surface `dashboard` that displays aggregated stats →
     `dashboard` resource at `/v1/dashboard` (read-only summary)
   - UX surface `notifications` panel →
     `notifications` resource at `/v1/notifications`

### Grouping by bounded context (when DATA.bounded_contexts is set)

If `DATA-MODEL.yaml.bounded_contexts` is non-null, use it as the
default grouping axis: propose one set of resources per context, and
prefix `base_path` with the context name where it would otherwise
collide (e.g. `auth/users` vs `billing/users`). Cross-context
relationships still go via `data-model://<EntityName>` `$ref`s — the
context grouping is purely organizational. Tag-group each resource by
its context so the synthesized OpenAPI document keeps the structure.

Don't try to be exhaustive — the user will add, remove, or rename
resources during the per-item drill-down. Aim for a starter inventory
that:

- Covers every DATA entity with at least one resource (or has the user
  consciously opt the entity out as "internal").
- Covers every UX surface with data I/O (or is in the planned
  `non_api_surfaces` opt-out, if any).
- Covers every PRD `FR-NNN` feature (or is in the planned
  `non_api_features` opt-out).

## Step 2 — Generate `resource_id`s and `base_path`s

`resource_id` is kebab-case, unique within the project, short
(≤ 32 chars). `base_path` typically starts with the version prefix
(`/v1/` if versioning is path-based) and continues with the resource
name in plural-noun form.

Rules:

- Derive `resource_id` from the dominant entity name in singular or
  plural — `users`, `orders`, `invoices`. Plural for REST conventions;
  singular when the resource fronts a single instance like
  `current-user` or `health`.
- For cross-cutting resources, use a single descriptive noun:
  `search`, `health`, `metrics`, `imports`.
- `base_path` should be lowercase and kebab-case where applicable
  (`/v1/saved-searches` not `/v1/savedSearches`).
- Renames during the interview are fine — update the
  `state.defined_resources` entry and the (unwritten) deep-dive
  partial in one move. If the resource yaml has already been written
  under the old id, ask the user before deleting it.

## Step 3 — Per-resource state machine (theme 8)

For each candidate resource, run one mini-section that confirms
identity (id, base_path, primary_entity, traces) but does NOT yet do
the endpoints/schemas deep-dive — that's theme 10.

### State machine

Each resource progresses through three states tracked in
`state.defined_resources[i].status`:

| state | meaning |
|---|---|
| `defined`   | id + base_path + primary_entity + traces known, no endpoints yet |
| `draft`     | deep-dive in progress (theme 10) |
| `confirmed` | deep-dive complete + user approved |

Theme 8 produces a list of `defined` resources. Theme 10 walks that
list and transitions each from `defined` → `draft` → `confirmed`.

### Per-item flow for theme 8

For each candidate resource from step 1:

#### a) Propose

```
header: "Resource N"
question: "Resource #N — confirm or revise?"
options:
  - { label: "⚠ <inferred id> at <base_path> (entity: <primary_entity>)", description: "⚠ <one-sentence purpose>. Traces PRD F-IDs: <ids>. Serves UX surfaces: <ids>. Confirm or correct in text field." }
  - { label: "Rename / change base_path",  description: "Type a different resource_id (kebab-case) or base_path in the text field." }
  - { label: "Change primary_entity",      description: "Type the DATA entity name this resource fronts, or 'null' for cross-cutting." }
  - { label: "Drop this candidate",        description: "Remove it from the inventory — no resource will be created." }
```

On accept → record `{ resource_id, base_path, primary_entity,
status: defined, file_path: docs/API__<resource_id>.yaml,
traces_prd_features: [<F-IDs>], traces_ux_surfaces: [<surface_ids>] }`
in `state.defined_resources`, persist state.

On rename / base_path change → re-run step a with the new values.

On drop → record `{candidate, seeded_from, reason, at}` under
`state.dropped_candidates.resource_inventory` (so the agent knows not
to re-propose on resume; entries in the legacy
`state.dropped_resource_candidates` list are read as the same
bucket). Don't write the file.

#### b) Confirm traces

If the proposed traces miss a PRD feature you'd expect, or if the user
is likely to add resources beyond what the agent inferred, ask one or
two targeted clarifying `AskUserQuestion` calls — one for features,
one for surfaces (both `multiSelect: true`):

```
header: "Features?"
question: "Which PRD FR-NNN features does '<resource_id>' implement?"
options:
  - { label: "<FR-001: description>",          description: "<verbatim PRD features entry>" }
  - { label: "<FR-003: description>",          description: "<verbatim PRD features entry>" }
  - { label: "Other (type)",                  description: "Type the FR-NNN id(s) verbatim from PRD.functional_requirements.features." }
  - { label: "None — internal-only resource", description: "This resource doesn't implement any PRD FR-NNN. (Will be flagged in api_warnings unless an explicit reason is captured.)" }
multiSelect: true
```

```
header: "Surfaces?"
question: "Which UX surfaces (SCR-NNN ids) does '<resource_id>' serve?"
options:
  - { label: "<SCR-NNN-1> (<surface_id slug>)", description: "<surface_type>; <one-line description>" }
  - { label: "<SCR-NNN-2> (<surface_id slug>)", description: "<surface_type>; <one-line description>" }
  - { label: "Other (type)",                  description: "Type a UX SCR-NNN id verbatim — never the kebab slug." }
  - { label: "None — internal-only resource", description: "Surface coverage will not credit this resource for any UX surface; a WRN-NNN note is added to api_warnings." }
multiSelect: true
```

The user picks SCR-NNN ids; the slug (`surface_id`) is shown only as
context. The stored `traces_ux_surfaces` list MUST contain SCR-NNN
ids — never slugs.

#### c) Next or end

When the candidate list is exhausted, ask:

```
header: "More?"
question: "Add another resource, or wrap up the inventory?"
options:
  - { label: "Add another (I'll suggest)",   description: "I'll propose a candidate from any uncovered DATA entity / PRD feature / UX surface." }
  - { label: "Add my own",                   description: "Type a resource_id + base_path + primary_entity in the text field." }
  - { label: "Done — wrap up inventory",     description: "Move on to per-resource deep-dive." }
```

**Caps**: soft 15 resources, hard 25. Above the hard cap, refuse
politely and suggest splitting the product into multiple products
(monorepo mode) or pushing some resources to a later phase.

### Scope-completeness sweep at end of theme 8

Theme 8 is marked `synthesis: true` in `api-questions.yaml`. After the
per-resource confirmation loop closes (the user picks "Done — wrap up
inventory"), the agent MUST run a dynamic scope-completeness sweep
before the inventory can close. This is the canonical sweep contract
from CLAUDE.md "Cross-skill conventions" — read it ONCE before doing
this for the first time.

#### What to reflect on (every pass)

1. **The draft inventory itself** — which resources are present? What
   axes (CRUD per entity / cross-cutting actions / domain workflows)
   dominate? What axes are conspicuously absent?
2. **Every upstream ID family**, not just the most-direct one:
   - `PRD.functional_requirements.features` (FR-NNN) — is
     every FR traced by a resource OR explicitly in
     `non_api_features`? Read each FR's description text; some
     features (e.g. "Bulk import CSV") imply resources the entity
     axis missed.
   - `PRD.use_cases.core_workflows` (WKF-NNN) — does any workflow
     imply an API entry point (e.g. "switch git branch" → a
     `sessions` or `projects` resource) the draft missed?
   - `PRD.use_cases.primary_jobs_to_be_done` / `secondary_jobs`
     (JTB-NNN) — similar implications.
   - `UX.surface_inventory[].id` (SCR-NNN) — every data-bearing
     surface should be traced by ≥1 resource. List the untraced
     ones.
   - `DATA-MODEL.yaml.entities` keys — every entity should be the
     `primary_entity` of some resource, OR explicitly flagged
     internal-only via a `WRN-NNN` warning (e.g. `AuditLog`,
     `IdempotencyKey`).
3. **Project-type heuristics** — a public SaaS API, an internal BFF,
   a GraphQL gateway, and a CLI-fronted local tool each have very
   different "things people forget":
   - Public SaaS: health, version, webhooks_in receive endpoints,
     admin DTOs gated behind a scope.
   - Internal BFF: session refresh, server-time, feature flags.
   - GraphQL: schema introspection, persisted queries.

#### Format of the sweep question

Format as **one** multi-select `AskUserQuestion` call surfacing the
agent's top 2–4 candidate resources — concrete names, not category
labels:

```
header: "Scope sweep"
question: "Looking at your N resources alongside upstream PRD FR/WKF +
  UX SCR + DATA entities, a few candidates look notable that aren't
  in the inventory yet. Add any of these, or wrap up?"
options:
  - { label: "⚠ <candidate-resource-1>", description: "⚠ Implied by <upstream ref, e.g. WKF-004 / FR-031 / SCR-008>. Pick to draft." }
  - { label: "⚠ <candidate-resource-2>", description: "⚠ Implied by <upstream ref>. Pick to draft." }
  - { label: "⚠ <candidate-resource-3>", description: "⚠ Implied by <upstream ref>. Pick to draft." }
  - { label: "Wrap up — inventory complete", description: "Skip these. The inventory closes as-is." }
multiSelect: true
```

For each picked candidate: re-enter the per-resource state machine at
**step a** (with the candidate pre-filled) → step b (traces) → record.
Then return to the sweep for a second pass.

Candidates the user skips at wrap-up are recorded under
`state.dropped_candidates.resource_inventory` with
`reason: "skipped at sweep"` (same `{candidate, seeded_from, reason,
at}` shape), so a resume or update run does not re-propose them.

#### Caps

- **Sweep-pass cap**: at most 2 passes per inventory. After two
  passes, defer remaining candidates to `api_warnings`:
  `"WRN-NNN: inventory sweep suggested but not added — <Candidate>,
  <Candidate>"`. Persist the WRN counter to `state.last_ids.WRN`.
- **Anti-padding rule**: if no concrete candidates surface after
  honest reflection, surface 0 — close the inventory without a
  sweep question. Don't manufacture candidates to look thorough.
- **Empty inventory**: if the user added 0 resources in the main
  loop AND `api_kind != "none"`, write a `WRN-NNN: inventory empty
  — no resources collected` note. (An empty inventory with
  `api_kind != "none"` will also fail the feature-coverage check.)

#### Fallback coverage gate

If the sweep closes but some FR-NNN / SCR-NNN are still uncovered,
offer the user a final-mile gate (this is the older "coverage hint"
narrative, now scoped to after-the-sweep cleanup):

```
header: "Coverage?"
question: "After the sweep, these items still aren't covered:\n - FR ids: <ids>\n - SCR surfaces: <ids>\nWhat to do?"
options:
  - { label: "Defer with a reason", description: "Add {id, reason} to API.yaml's top-level `deferrals` list — the auditable form (SKILL.md: never a bare id). A bare non_api_features entry covers below api_version 2.0 only, and is still reported even then." }
  - { label: "Leave gap — record in api_warnings (WRN-NNN)", description: "API.yaml will save as draft." }
  - { label: "Edit existing traces",         description: "Re-open an existing resource to add the missing trace(s)." }
```

This is the soft coverage check. The hard checks happen in
`validate_schema.py` (Phase 7).

## Step 4 — Per-resource deep-dive (theme 10)

For each resource in `state.defined_resources` (in order they were
defined), run the deep-dive. The deep-dive is the `critical` per-item
flow that writes the per-resource yaml.

### State transition

When the deep-dive starts for a resource, set its status to `draft`
and seed `state.partial_resources[<resource_id>]` with the known
identity (`resource_id`, `base_path`, `primary_entity`,
`traces_prd_features`, `traces_ux_surfaces`) plus empty values for the
rest.

When the deep-dive completes (after step e final approval), flip
status to `confirmed`, write the resource yaml to disk
(`docs/API__<resource_id>.yaml`), and move the contents from
`state.partial_resources` into a permanent slot.

### Per-resource mini-interview (5 steps)

For each resource:

#### a) Announce + identity recap

Open the resource with a one-line recap — "Now: `<resource_id>` at
`<base_path>` (primary entity: `<primary_entity>`); traces F-IDs `<F-IDs>`
and UX surfaces `<ids>`." Because chat markdown sharing a turn with a tool
call may not render (the channel rule: AUTHORING §18,
`../../prd/references/importance-flows.md`), either END the turn with the
recap or fold it into the first step-b question's text — never rely on a
banner printed in the same turn as an `AskUserQuestion` call.

#### b) Endpoints

Propose the canonical CRUD set adapted to the resource's verbs. Every
endpoint carries TWO ids:

- `id` — the stable `OPR-NNN` cross-stage reference (assigned by the
  writer in collection order; persisted via `state.last_ids.OPR`).
  Downstream test/task/arch agents reference this id.
- `operation_id` — the codegen-naming hook (kebab/snake string,
  unique within the file). Editable; OPR-NNN is the contract.

Canonical starter set:

- `list-<resource>` — `GET <base_path>` — returns paginated list
- `get-<resource>` — `GET <base_path>/{id}` — returns one
- `create-<resource>` — `POST <base_path>` — creates one
- `update-<resource>` — `PUT <base_path>/{id}` or `PATCH` — updates
- `delete-<resource>` — `DELETE <base_path>/{id}` — removes

Each picks the next OPR-NNN from `state.last_ids.OPR` when the user
approves it in step e.

Pre-fills from DATA-MODEL:

- **Path-param `{id}` format**: read `DATA-MODEL.id_strategy.scheme`
  and the entity's `primary_key` field to pick `format: uuid` /
  `format: int64` / a pattern — see
  `references/openapi-embedding.md` "Identifier formats" table.
  Composite primary keys split into multiple path segments.
- **DELETE semantics**: if
  `DATA-MODEL.audit_and_lifecycle.soft_delete: true`, mark
  `delete-<resource>` as soft-delete (`204 No Content`, no body) and
  add an `sdlc_note` in the endpoint description so downstream code
  generators wire the soft-delete column rather than a DROP.
- **List endpoints from `indexes_and_queries.access_patterns`**: walk
  every access pattern whose `entity` matches this resource's
  `primary_entity` AND `read_or_write` is `read` or `both`. Propose
  one query-parameter combo per pattern (e.g. an access pattern over
  `[owner_id, created_at]` becomes `GET /v1/projects?owner_id=...`
  with default sort by `created_at`). When a pattern's trailing field
  is monotonic (timestamp, ulid, serial), propose it as the
  `pagination.stable_sort_field` if cursor pagination is enabled.

Add custom actions for any PRD feature the canonical CRUD doesn't
cover (e.g. `POST /users/{id}/reset-password` for a "reset password"
feature). The agent proposes them per-feature.

Walk endpoints per-item (high tier), confirming method/path/summary/
request DTO ref / response DTO ref / status codes / auth. Each endpoint
becomes one entry in the resource yaml's `endpoints[]`. See
`references/openapi-embedding.md` for the OpenAPI 3.1 subset
supported and how to write request/response schemas.

#### c) DTO schemas

Propose schemas based on the primary DATA entity:

- `<Entity>` — full read DTO. **Omit by default** every field
  referenced as `<Entity>.<field>` in
  `DATA-MODEL.data_classification.regulated_fields`,
  `encrypted_at_rest`, and any password / token / secret hashes.
  Surface each `pii_fields` entry to the user for an explicit
  keep/omit decision per resource.
- `<Entity>Create` — POST payload. Additionally omit server-set
  fields (`id` when `id_strategy.scheme` is server-generated, any
  field with `default: now()`, audit columns).
- `<Entity>Update` — PATCH payload (all fields optional). PUT is rare
  but if present requires the same fields as Create.
- `<Entity>List` — paginated list wrapper (only when pagination is
  envelope-style rather than raw array; `projects_from: null`).
- `<Entity>Admin` (optional) — re-exposes regulated/encrypted fields
  behind an admin scope. Propose only when the user explicitly asks.
- `<Entity>Public` (optional) — cross-tenant read DTO that hides PII.

Embed `enum:` lists inline for any field whose DATA type is `enum` —
the values come from `DATA-MODEL.enums_and_lookups.enums.<EnumName>`.

Each object DTO carries `projects_from: <EntityName>` (required for
single-entity DTOs; `null` only for cross-entity wrappers like
`<Entity>List`). See `references/openapi-embedding.md` for the
DTO-vs-entity discipline and the data_classification-anchored rules.

#### d) Re-confirm traces

Re-show the `traces_prd_features` and `traces_ux_surfaces` lists from
theme 8 and ask one quick `AskUserQuestion` to adjust:

```
header: "Traces ok?"
question: "These traces are recorded for `<resource_id>`. Adjust before saving?"
options:
  - { label: "Looks good",            description: "Keep traces as recorded." }
  - { label: "Add an FR-NNN",         description: "Type the FR-NNN id to add (PRD must_have/nice_to_have)." }
  - { label: "Add a SCR-NNN",         description: "Type the UX SCR-NNN id to add (never a kebab slug)." }
  - { label: "Add a WKF-NNN",         description: "Type the PRD WKF-NNN workflow id to add (optional)." }
  - { label: "Remove a trace",        description: "Type the FR-NNN / SCR-NNN / WKF-NNN id to remove." }
```

#### e) Final approval

The drafted per-resource yaml (or a compact summary if it's long) rides
INSIDE the approval question — in the "Approve" option's `preview`, or the
question text when preview is unavailable (channel rule: AUTHORING §18,
`../../prd/references/importance-flows.md`) — never only as chat markdown
printed in the same turn as the call:

```
header: "Approve?"
question: "Approve `<resource_id>` as drafted? (full draft in the first option)"
options:
  - { label: "Approve — write to disk",       description: "Save docs/API__<resource_id>.yaml and continue.", preview: "<the drafted yaml or compact summary>" }
  - { label: "Iterate — type changes",        description: "Use the text field to describe what to change. The agent will re-draft." }
  - { label: "Skip for now — keep as draft",  description: "Move on to the next resource; this one stays status: draft and the file is NOT written." }
```

On approve: write the resource yaml, flip status to `confirmed`,
persist state.

On iterate: re-enter step b/c/d with the user's revision context.
After 3 iterations on a single resource, write the current draft and
add an `api_warnings` entry naming the resource.

On skip: leave status `draft`, do NOT write the file (the validator
won't see it, but the entry remains in `state.defined_resources` and
`state.partial_resources` so the user can resume later).

### State-write timing

Persist state after each per-resource step (b/c/d/e), not just at the
end. This keeps EXIT cheap mid-deep-dive — the partial resource stays
in `state.partial_resources` and resumes cleanly.

## When the user EXITs mid-flow

- Mid-theme 8: write all confirmed inventory entries to
  `state.defined_resources`, drop the current candidate (it wasn't
  approved). Set `status: aborted`.
- Mid-theme 10 deep-dive on resource N: write the partial yaml
  content to `state.partial_resources[<resource_id>]`. Do NOT write
  the resource file to disk (it's incomplete). Set `status: aborted`.
  The `state.defined_resources[N].status` stays `draft`.

On resume, the agent picks up at the partial resource — it explicitly
asks the user *"Resume mid-deep-dive of `<resource_id>`?"* before
re-entering theme 10.

## Naming and renaming resources mid-flow

If the user renames a resource during theme 10:

1. If no file has been written yet → just update the id everywhere
   (`state.defined_resources`, `state.partial_resources`,
   `state.current_resource`).
2. If the file already exists → ask the user:
   *"Rename `docs/API__<old>.yaml` → `docs/API__<new>.yaml`? This will
   delete the old file."* Wait for explicit confirmation before
   deleting.

Resource ids are immutable post-completion only by convention — the
user can always rename via an update interview, but each rename
forces a file move and a coverage-check re-validation. Before
renaming or dropping a resource whose endpoints already carry OPR
ids, check inbound references with
`python .claude/sdlc/docs_index.py --refs OPR-NNN` (skip when the
helper is absent) — downstream ARCH/TEST/TASKS artifacts may already
cite them.

## Soft-deletion of dropped candidates

When the user drops a candidate in theme 8 step a:

- Record `{ candidate: <resource_id>, seeded_from: <the upstream
  id(s) that implied it, e.g. "FR-031">, reason: "dropped by user",
  at: <timestamp> }` under
  `state.dropped_candidates.resource_inventory` (entries in the
  legacy `state.dropped_resource_candidates` list are read as the
  same bucket).
- Don't propose the same id again on resume. A later §7 delta review
  re-surfaces a dropped candidate only when its `seeded_from` id
  changed upstream.
- The dropped resource is NOT written to
  `API.yaml.resource_inventory`.
