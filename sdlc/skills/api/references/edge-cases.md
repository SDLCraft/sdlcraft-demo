# Edge cases — sdlc-api

Read this whenever the agent hits an unusual situation that doesn't fit
the happy path.

## Input-side edge cases

### `docs/PRD.yaml`, `docs/UX.yaml`, or `docs/DATA-MODEL.yaml` missing

Do NOT proceed. Print a clear warning naming the missing file and the
upstream skill that owns it:

> "Cannot start the API interview — `docs/<file>.yaml` is missing.
> Run `/sdlc:<skill>` first."

### Upstream input has `metadata.status: draft`

Same flow as `sdlc:ux` for a draft PRD. Offer three choices via
`AskUserQuestion`:

- "Stop and finish `<file>` first" (recommended).
- "Proceed anyway and record draft status in `api_warnings`" — only
  use this when the user explicitly accepts the risk. `API.yaml`
  will be forced to `status: draft` regardless of completeness.
- "The upstream is wrong — record a finding for `/sdlc:repair`" —
  when the draft status reflects a real defect in the upstream
  artifact, not just unfinished work. Append the observation to
  `state.finding_notes` (never stop mid-run to record; Phase 8 drains
  the list through `findings.py`) and then apply one of the two
  choices above.

### Upstream validator exits non-zero (1, 2, or 3)

Do NOT proceed. Print the upstream validator's error output verbatim
and ask the user to fix it first.

### The upstream itself is wrong (findings, CLAUDE.md §13)

When the interview exposes a defect in PRD/UX/DATA-MODEL content — a
schema-REQUIRED field null in a `complete` upstream, two upstreams
contradicting each other, a stale reference the user confirms is an
upstream mistake — the durable channel is a **finding**, never a WRN
note about another artifact and never a silent workaround:

- **Mid-run, never stop to record.** Append
  `{noted_at, kind_guess, file, summary, evidence}` to
  `state.finding_notes` in the next state write (same cadence as
  answers) and continue the interrupted step.
- **Phase 8 drains the list** through
  `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add
  --raised-by sdlc-api ...` (skip silently when the script is
  absent). Cap 3 findings per run unless one is blocking.
- The user-facing option reads "the upstream is wrong — record a
  finding for `/sdlc:repair`" and appears only at prompts that have
  room (≤3 options today); where a prompt already has 4 options,
  fold it into the free-text guidance.

## Resource-inventory edge cases

### PRD feature with no obvious resource

A `features` entry the agent can't imagine any single
resource owning — e.g. "Send a weekly digest email" or
"Theme switcher (light/dark)". Behaviour:

- If the feature is genuinely non-API (UI-only theming, internal cron
  job, batch process): record it in the top-level `deferrals` list as
  `{id: FR-NNN, reason: <why no endpoint>}`. The feature-coverage
  gate counts it as covered. (A bare id in `non_api_features` still
  passes for one more version but is reported as unauditable — new
  writes use `deferrals`.)
- If the feature spans multiple resources but doesn't fit any one:
  propose a cross-cutting resource (`/v1/digest`, `/v1/admin`, …)
  and let the user decide.
- If the user can't decide: leave the feature uncovered and add an
  `api_warnings` entry. Force `status: draft`.

### Same resource implements many features

Fine. List every matching FR-NNN in `traces_prd_features`. The
coverage check is satisfied as long as each FR-NNN appears in at least
one resource's traces; one resource can carry several features.

### Resource has no primary entity

Cross-cutting resources (`/search`, `/health`, `/metrics`, `/auth`)
genuinely don't front a single DATA entity. Set `primary_entity:
null` — the entity-link check skips null values.

### DATA entity with no resource (entity coverage)

The skill does NOT enforce "every DATA entity must have a resource".
Some entities are internal-only (e.g. `AuditLog`, `IdempotencyKey`,
`SessionToken`). The agent SHOULD flag this in `api_warnings` as a
soft note (*"entity 'User' has no resource — confirm internal-only?"*)
but does not fail validation on it.

### UX surface with no obvious resource

A surface whose interactions imply data I/O but no resource clearly
serves it (e.g. a dashboard that aggregates many entities). Two
options:

- Create a cross-cutting resource that serves the aggregated view
  (e.g. `dashboard` resource with read-only endpoints).
- Trace the surface from multiple existing resources (e.g. `dashboard`
  surface is served by both `tasks` and `projects` resources — list
  it in both `traces_ux_surfaces`).

Either pattern satisfies the surface coverage check.

## Mid-interview transport-style change

The user said `[rest]` in Phase 4, answered themes 2–8, then says
"actually we also need WebSocket for live updates → add `websocket`".

Behaviour:

- Update `state.transport_styles`.
- Re-evaluate `required_if` rules at next theme boundary — the
  `events_async` theme is now required.
- Existing resources stay; the user can add events during theme 9.
  Existing per-resource yamls don't need to change.
- Do NOT silently delete the user's earlier answers — transport
  changes augment, not invalidate.

If the user goes from `rest` to `none` mid-interview (rare):

> "Switching `api_kind` from `rest` to `none` will discard all
> answered themes and resource inventory. Are you sure? (Type `EXIT`
> to abort the change.)"

On confirm: drop everything, write a minimal `API.yaml` with
`api_kind: none` + rationale.

## Conflicting auth decisions across resources

The user picks `auth.schemes: [bearer_jwt]` globally but later, during
a per-resource deep-dive, sets `endpoints[0].auth_override:
"api_key"` for a specific endpoint.

Behaviour: respected — the per-endpoint override wins. Surface a note
in `api_warnings` only if the override is suspicious (e.g. several
endpoints in different resources independently override to the same
scheme; ask the user whether they want to update the global
`auth.schemes` instead).

## DATA-MODEL changed mid-session

The user is mid-interview, re-runs `/sdlc:data` (or hand-edits
`docs/DATA-MODEL.yaml`) to add, rename, or remove an entity, then
resumes. The agent's in-memory inventory still references the old
entity set.

Behaviour on resume:

1. Re-validate `docs/DATA-MODEL.yaml` with
   `python "${CLAUDE_SKILL_DIR}/../data/validate_schema.py" --path docs/DATA-MODEL.yaml`.
   If it now fails or has `status: draft`, stop and ask the user to
   finish `sdlc:data` before continuing.
2. Compare `DATA-MODEL.metadata.session_id` and `last_updated` against
   what the api state file recorded on first scan. If they differ,
   announce it: *"DATA-MODEL was updated since you started this
   session — re-checking entity references."*
3. Diff the entities the api state file knows about vs. the entities
   currently in DATA.
4. If any entity was removed but is still referenced in
   `state.defined_resources[*].primary_entity` or in a `$ref:
   data-model://<Name>`, prompt:

   > "DATA-MODEL no longer has entity `<name>`. Resource `<id>` still
   > references it. Update primary_entity, drop the resource, or
   > leave the broken link (will fail validation)? If DATA-MODEL is
   > wrong to have dropped it, say so — I'll record a finding for
   > `/sdlc:repair`."

   The finding pick appends to `state.finding_notes` (drained at
   Phase 8); the resource keeps its reference in the meantime.

5. If any entity was renamed (detectable when the user kept the
   `traces_prd_features` / `traces_ux_surfaces` constant but the
   entity name moved), offer to rewrite `primary_entity` and any
   `data-model://<Old>` $refs in one move.
6. If new entities were added, offer to add candidate resources for
   them (re-running theme 8 step a only for the new entities).

## Upstream changes between sessions (re-invocation, §7)

The section above handles an upstream edited *mid-session* (the resume path).
When the user re-invokes `/sdlc:api` in a *new* session after `docs/API.yaml`
already exists, Phase 2 runs **upstream-change detection** against
`metadata.upstream_provenance`: it compares the recorded `sha256` of each
upstream (`PRD`, `UX`, `DATA-MODEL`) to its current hash and, for any that
moved, runs the consolidated delta-review (added / removed / modified ids)
*before* the interview. This is the cross-skill §7 contract and **generalizes
the `session_id`/`last_updated` comparison used above** — a content hash also
catches hand-edits, which `session_id` does not. Full mechanics:
`sdlc/skills/ux/references/upstream-reconciliation.md`.

## Validation failures

Same flow as `sdlc:prd` and `sdlc:ux`. Show field-level errors
verbatim, list affected paths, offer via `AskUserQuestion`: "Fill in
now, or accept draft status?" Re-run validation after re-entry.

Common failure modes specific to API:

- **Endpoint missing `responses`**: validator fails. Every endpoint
  must declare at least one status code response — usually `200` or
  `201` for success.
- **`primary_entity: <Name>` not in DATA-MODEL**: entity-link check
  fails. The user must either fix the name, set it to `null`
  (cross-cutting), or add the entity to DATA-MODEL.
- **DTO schema references a DATA entity that doesn't exist**: same.
  The `data-model://<Name>` URI is checked lazily during downstream
  OpenAPI synthesis; the api validator only checks `primary_entity`.
- **Per-resource yaml claims `status: complete` but some endpoint is
  missing required keys**: validator surfaces the path. Fix the
  endpoint or accept the resource staying `draft`.

## Write-permission errors

Report the path and OS error verbatim. Do not retry silently. Common
causes: `docs/` directory doesn't exist (offer to create it),
filesystem read-only (offer to write to a different path),
`CLAUDE.md` is open in another editor (suggest the user close it).

## Resume with stale state

SKILL.md's Phase 1 carries the inline trigger (all four states, plus the
older-`skill_version` line). The canonical recipe — the additive migration,
and the theme-list / `last_ids` reconciliation — lives in
`${CLAUDE_SKILL_DIR}/../prd/references/edge-cases.md` → "Resume with stale
state". Nothing to add here.

## Hallucination-guard violation

If the user tries to batch-accept `⚠ inferred` resources or
per-resource fields with shortcuts like "ok" or "all good", refuse
and re-prompt. Each `⚠` item needs an explicit confirmation or
correction. This applies to:

- Phase 5 pre-fill confirmation.
- Phase 6 theme 8 (`resource_inventory`).
- Phase 6 theme 10 (`per_resource_deepdive`).

## Monorepo mode

When `PRD.metadata.monorepo == true`:

- `API.yaml` itself is monorepo-shaped (themes under
  `products.<slug>.<theme>`).
- Resource yamls are named
  `docs/API__<product-slug>__<resource-slug>.yaml` to avoid
  collisions between products that have resources with the same id
  (e.g. both products having a `users` resource).
- The interview runs **per product**: theme 8 enumerates each
  product's resources separately; theme 10 deep-dives the union.
- Coverage checks run per-product: every product's `features`
  must be covered by at least one resource from that product (or
  listed in that product's `non_api_features`); every product's UX
  surfaces must be covered by a resource from that product.
- Entity-link check is global (entities cross product boundaries
  unless the data model is partitioned).

If the PRD is monorepo but the user wants the API skill to treat the
products as if they shared one API (e.g. a unified BFF layer), offer:

> "Treat all products as one unified API (single API.yaml without
> products: namespacing), or run per-product API interviews?"

Default to per-product; only switch to unified when the user
explicitly asks.

## Very large APIs

If the user accepts the hard cap of 25 resources (per
`resource-discovery.md`) and wants more, refuse politely and suggest:

- Splitting the product into multiple products (and converting the
  PRD to monorepo mode).
- Pushing some resources to a later phase (drop from MVP inventory,
  note in `api_warnings: "phase-2 resource: <id>"`).
- Grouping fine-grained CRUD into a single "admin" resource and
  exposing it via sub-paths (`/v1/admin/users`, `/v1/admin/orders`).

## `api_kind: none` but the user changes their mind

The user picks `api_kind: none` in Phase 4, the skill writes a
minimal `API.yaml`, marks complete. Later, the user re-runs `/sdlc:api`
intending to add an actual API.

Behaviour: on resume, detect that `api_kind: none` is set in the
existing API.yaml. Ask:

> "The existing API.yaml says `api_kind: none`. Are we switching to
> an actual API now? If yes, I'll re-open Phase 4 and re-ask the
> structural questions."

On confirm: clear `api_kind`, `rationale`, restart at Phase 4. The
state file is updated; the existing API.yaml is the merge baseline
(but everything is empty so the merge is trivial).

## User skips a required theme

The skill cannot mark a required theme `todo` — that's a hard error.
If the user tries, refuse politely:

> "`<theme>` is required for downstream agents to consume the API
> spec. Either answer it now, or type `EXIT` to save progress as
> `aborted`."
