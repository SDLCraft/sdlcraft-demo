---
name: api
description: >
  Explicitly invoked skill. Creates or updates docs/API.yaml plus one
  docs/API__<resource>.yaml per API resource, consumed by downstream
  coding agents (arch → test → task → deploy). A maintenance form,
  /sdlc:api --reconcile, reviews only what moved in PRD/UX/DATA since the
  file was written, without the interview. Trigger only on /sdlc:api
  or a direct natural-language request to start the API skill — never
  auto-trigger from generic API chatter.
user-invocable: true
disable-model-invocation: true
model: opus
effort: xhigh
allowed-tools: Read Write(docs/API.yaml) Write(docs/API__*.yaml) Write(.claude/skills-state/sdlc-api.state.yaml) Bash Bash(ls *) Glob Grep AskUserQuestion
---

# sdlc-api

Guides the user through a structured interview that produces a validated
`docs/API.yaml` (global API contract) plus one
`docs/API__<resource>.yaml` per API resource, so downstream coding agents
have an unambiguous machine-readable description of every endpoint, DTO,
auth scheme, error envelope, and event channel they need to implement.

## What this skill does (at a glance)

1. **Resume check** → load existing state if any.
2. **Scan inputs** → read `docs/PRD.yaml`, `docs/UX.yaml` (+ all
   `UX__*.yaml`), and `docs/DATA-MODEL.yaml`. Run each upstream skill's
   validator. Exit early if any input is missing, invalid, or not
   `metadata.status: complete`. On a re-run, check upstream drift
   (`docs_index.py --drift`); list open findings + blocking PRD open
   questions and ask once whether to continue (input-adequacy gate).
3. **Structural questions** → confirm `api_kind`
   (`rest | graphql | grpc | mixed | none`) and `transport_styles`. If
   the user picks `none`, skip the rest of the interview and write a
   minimal API.yaml.
4. **Pre-fill confirmation** → theme by theme, each `⚠ inferred`
   confirmed individually.
5. **Theme interview** → required themes always run; optional themes
   gated now/skip/todo. Theme 8 (`resource_inventory`) and theme 10
   (`per_resource_deepdive`) run as `critical` `synthesis: true`
   per-item drill-downs — every resource is examined, confirmed, and
   traced back to PRD features (FR-NNN) + UX surfaces (SCR-NNN) +
   optionally PRD workflows (WKF-NNN) + a DATA entity (by name).
   After theme 8's per-item loop closes, the agent runs a dynamic
   **scope-completeness sweep** drawing on every upstream ID family;
   see `references/resource-discovery.md`.
6. **Write & validate** → merge into `docs/API.yaml` and write all
   `docs/API__<resource>.yaml` (every endpoint carries a stable
   `id: OPR-NNN` assigned by the writer), then run `validate_schema.py`
   (Pydantic + ID-prefix format checks (WRN/FR/SCR/WKF/OPR) +
   feature/surface coverage — both gates honour the structural
   `deferrals: [{id, reason}]` list — + entity-link checks + a
   warn-level provenance-freshness check).
7. **Refresh & close** → refresh `docs/INDEX.yaml` and the
   statusboard, mark state `complete`. This skill does not touch
   `CLAUDE.md`.

State is persisted **after every confirmed batch and after every
per-resource deep-dive**, so the user can `EXIT` at any time without
losing progress.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — the workflow itself. |
| `api-questions.yaml` | Full question inventory grouped by theme. |
| `API.schema.yaml` | Human-readable canonical schema for `docs/API.yaml`. |
| `API__RESOURCE.schema.yaml` | Human-readable canonical schema for `docs/API__<resource>.yaml`. |
| `validate_schema.py` | Pydantic v2 validator (API.yaml + every API__*.yaml + coverage + entity-link checks). |
| `references/interview-mechanics.md` | AskUserQuestion batch format, EXIT handling, conditional promotions. Read on entering Phase 6. |
| `references/resource-discovery.md` | How to enumerate resources from DATA entities + PRD features + UX surfaces; per-resource state machine. Read whenever theme 8 or 10 is active. |
| `references/openapi-embedding.md` | OpenAPI 3.1 subset supported, forbidden keywords, cross-file `$ref` rule, DTO-vs-entity discipline. Read whenever theme 10 is active. |
| `references/async-and-events.md` | When to populate the `events` block, payload conventions, delivery guarantees. Read whenever theme 9 is active. |
| `references/merge-validate.md` | Merge logic for `API.yaml` and per-resource yamls, the three coverage checks, and the rule that this skill never writes CLAUDE.md. Read on entering Phase 7. |
| `references/edge-cases.md` | Unusual situations and how to handle them. |

Runtime files (NOT inside this skill directory):

| File | Purpose |
|---|---|
| `docs/API.yaml` (project root) | Global API contract consumed by downstream agents. |
| `docs/API__<resource>.yaml` (project root) | One file per API resource. `<resource>` is kebab-case. |
| `.claude/skills-state/sdlc-api.state.yaml` | Session state for resumability. |
| `CLAUDE.md` (project root) | Pointer bullet injected on completion. |

## Reserved EXIT command

At any prompt, the user can type `EXIT` (case-insensitive) into the
free-text field of any `AskUserQuestion` call to abort. State is saved
after every confirmed batch and after every per-resource deep-dive, so
progress is never lost — `EXIT` marks the session `status: aborted`,
drains `lesson_notes` and `finding_notes` (see Phase 8), and stops.

There is no `SAVE` command — saving is implicit.

## Invocation dispatch

Classify `$ARGUMENTS`:

1. **Empty** → the full flow below (Phases 1–8). On a re-run it still runs the
   upstream-drift check in Phase 2 before the interview.
2. **`--reconcile`** → the **reconcile form**: the upstream-change review of
   `docs/API.yaml` and nothing else — no theme interview, no structural
   questions. Follow `sdlc/skills/ux/references/upstream-reconciliation.md` →
   "The `--reconcile` form" (steps 1–8, and this skill's row in its specifics
   table), then Phases 7–8 below. A resource the review adds is authored
   through the per-resource drill (theme 10) into its own
   `API__<resource>.yaml`; a change of `api_kind` or transport style is
   structural — stop and name plain `/sdlc:api`. It needs a `complete`
   `docs/API.yaml` — without one, name plain `/sdlc:api` and abort.
3. **Anything else** → print the two forms above and abort.

## The 8-phase flow

### Phase 1 — Resume check

Before doing anything else, check for
`.claude/skills-state/sdlc-api.state.yaml`:

- If it exists with `status: in_progress`, ask:
  > "I found an unfinished API session from `<last_updated>`. Would you
  > like to **resume**, **restart** (discard previous answers), or
  > **discard** (delete state and exit)?"
- If `status: complete` or `status: aborted` and `docs/API.yaml`
  exists, treat this as an update flow — see
  `references/merge-validate.md`.
- If no state file, continue to Phase 2.

### Phase 2 — Scan inputs

`sdlc:api` does NOT re-interview anything that already lives in
`docs/PRD.yaml`, `docs/UX.yaml`, or `docs/DATA-MODEL.yaml`. Read these
files at startup and validate each via its upstream skill.

**Slice, don't slurp.** When `docs/INDEX.yaml` exists (the project ran
`/sdlc:setup`), read the large upstreams **by line range via the index**:
look the needed section/symbol up in `INDEX.yaml` (`sections` /
`symbols`, or `python .claude/sdlc/docs_index.py --show <symbol>`) and
`Read` only that slice — the extraction lists below name exactly which
blocks each upstream contributes. Fall back to a whole-file read only
when `INDEX.yaml` is absent or the doc is genuinely small. See
`.claude/rules/sdlc-docs-access.md`.

1. **`docs/PRD.yaml`** — required.

   ```bash
   python "${CLAUDE_SKILL_DIR}/../prd/validate_schema.py" --path docs/PRD.yaml
   ```

   - If exit code ≠ 0 or `metadata.status != "complete"` → stop. Print
     a clear warning telling the user to complete the PRD first
     (`/sdlc:prd`).
   - Extract the fields the API skill needs:
     - `security_compliance.auth_model` → preliminary `auth.schemes`
     - `users_personas.primary_users` + `secondary_users` →
       preliminary `auth.roles`
     - `functional_requirements.features` (FR-NNN list) →
       feature-coverage source of truth
     - `functional_requirements.integrations_required` →
       preliminary `external_dependencies`
     - `technical_constraints.runtime_platform` (a LIST as of PRD 1.1; a
       bare scalar is the legacy one-element form) → narrows `api_kind`
       (e.g. only `cli` / `library` → strong default `api_kind: none`)
     - `security_compliance.auth_model: mtls` (PRD 1.1) →
       `auth.schemes: [mtls]` (the scheme enum already has it)
     - `internationalization.enabled` (PRD 1.1) → `errors.localisation`
       (`✓ found`)
     - `glossary.terms` (PRD 1.1) → resource names and `operation_id`s reuse
       the glossary term, never a synonym (`✓ found`)
     - `non_functional_requirements.scalability ∈ {large, hyperscale}`
       → strong hint for `pagination.strategy: cursor` and stricter
       `rate_limiting` defaults (per_user + per_ip together).
     - `non_functional_requirements.performance_targets` → verbatim
       rationale for `rate_limiting.burst` / `sustained` values.
     - `non_functional_requirements.reliability: mission_critical` →
       hint for `errors.retry_semantics` (5xx + 429 with Retry-After).
     - `metadata.monorepo` + `products: <slug>:` → if true, the API
       skill runs the interview **per product** and writes one
       `API.yaml` per product slug. (See `references/edge-cases.md`.)

2. **`docs/UX.yaml`** + all `docs/UX__<surface>.yaml` — required **unless UX
   does not apply to this project**. Resolve that first, per the three-step
   rule in `sdlc/skills/prd/references/optional-stages.md`:

   ```bash
   python "${CLAUDE_SKILL_DIR}/../ux/validate_schema.py" --path docs/UX.yaml
   ```

   - **Present** → same `status: complete` and exit-code-0 gate as PRD. A
     valid file with `metadata.applicability: not_applicable` counts as absent
     (below), and is not an error.
   - **Absent and `PRD.pipeline_scope.ux.applicable` is `false`** → continue
     without UX. Skip every UX-sourced pre-fill and the surface-coverage gate
     (it is vacuous with no surfaces), and note the skip once in `api_warnings`
     (WRN-NNN). Ask nothing. A project with no user-facing surface can still
     have an API — a headless service is the standard case — so this does NOT
     imply `api_kind: none`; derive that from `runtime_platform` as usual.
   - **Absent with no scope entry** → one `AskUserQuestion` (wording in
     optional-stages.md), record under `state.ux_present`, and add the "record
     it permanently with `/sdlc:prd`" line to the close card.

   With UX present and applicable, extract:
     - `surface_family` → hint for `api_kind` (cli → likely `none`)
     - Every surface's `surface_id`, `surface_type`, `interactions`,
       `validation_rules` → surface-coverage source of truth; agent
       infers candidate resources from surfaces with data I/O
     - `navigation_model.top_level_nodes` → hints for base_path
       grouping (e.g. `/dashboard` → `dashboard` resource)

3. **`docs/DATA-MODEL.yaml`** — required.

   ```bash
   python "${CLAUDE_SKILL_DIR}/../data/validate_schema.py" --path docs/DATA-MODEL.yaml
   ```

   - Same `status: complete` and exit-code-0 gate as PRD/UX. If the file
     is absent → stop. Print:
     > "Cannot start the API interview — `docs/DATA-MODEL.yaml` is
     > missing. Run `/sdlc:data` first."
   - Extract the fields the API skill needs:
     - `entities` keys (PascalCase) → candidate axis for
       `resource_inventory` (one resource per primary entity by default).
     - `entities` keys → pool of valid `primary_entity` references
       (the entity-link check fails any reference that's not in this set).
     - `entities` keys → source of truth for
       `$ref: data-model://<EntityName>` in per-resource schemas. See
       `references/openapi-embedding.md`.
     - `id_strategy.scheme` → path-parameter `format` for `{id}` segments
       (`uuid_v4|uuid_v7|ulid` → `format: uuid`; `serial_int|bigserial`
       → `type: integer`; `nanoid|natural_key` → `type: string`).
     - `data_classification.pii_fields` + `regulated_fields` +
       `encrypted_at_rest` → authoritative "omit from public DTOs"
       list. DTOs MUST omit these fields by default; the user can opt
       a field back in per resource with an explicit confirmation.
     - `data_classification.localized_fields` → per-locale text: a DTO
       serves these in the locale negotiated via `Accept-Language` (see
       `errors.localisation`), never as one fixed string.
     - `audit_and_lifecycle.soft_delete: true` → DELETE endpoints
       become soft-delete (status 204 + the row stays). Default is
       hard-delete.
     - `enums_and_lookups.enums` → pre-fill DTO `enum:` constraints
       wherever a DTO field maps to one of these enums.
     - `bounded_contexts` (when present) → propose grouping resources
       by context (one tag group per context). Cross-context references
       still go via `data-model://` $refs.
     - `indexes_and_queries.access_patterns` → pre-fill list endpoints
       (one per pattern) and the `pagination.stable_sort_field` hint
       when the pattern's `fields` list ends in a monotonic column.

4. Existing `docs/API.yaml` and `docs/API__*.yaml` — if present, treat
   as the merge baseline (Phase 7).

5. Optional context files at project root: `README*`, any existing
   `openapi.yaml`/`openapi.json`, `*.openapi.*`. Quote findings in
   pre-fill rationale.

Build the pre-fill map exactly as `sdlc:prd` and `sdlc:ux` do,
classifying each candidate as `✓ found` (direct quote from PRD/UX/DATA
or local file) or `⚠ inferred` (derived). While building it, record
every schema-REQUIRED upstream field found null or empty in a
`complete` upstream — Phase 8 auto-raises each as an
`upstream_incomplete` finding (CLAUDE.md §13); do not stop for it now.

**Upstream-drift check (re-runs, CLAUDE.md §7).** If `docs/API.yaml` already
exists, decide refine-vs-reconcile BEFORE the interview:

```bash
python .claude/sdlc/docs_index.py --drift docs/API.yaml
```

Exit 1 (drift) → run the consolidated **delta-review pass before the theme
interview** per `sdlc/skills/ux/references/upstream-reconciliation.md`: for
each changed upstream classify the delta (added / removed / modified ids),
and persist progress in `state.delta_review` (`{upstreams, decisions,
unresolved}`) so a resume continues instead of restarting. The per-item
options include "the upstream is wrong — record a finding for
`/sdlc:repair`" (noted to `state.finding_notes`, drained at Phase 8).
Exit 0 → every upstream is unchanged: proceed to the merge flow without a
delta-review. Helper absent (the project never ran `/sdlc:setup`) → fall
back to comparing each recorded `metadata.upstream_provenance.sha256` to the
upstream's current hash (`docs/INDEX.yaml.generated_from[<file>].sha256`
when present, else sha256 over the file's utf-8 text, first 16 hex —
identical to `docs_index.py --hash`). Fresh runs (no prior `docs/API.yaml`)
skip this step.

**Input-adequacy gate (ask, never block).** After reading the inputs, list
what is already known to be unsettled:

- open or triaged findings:
  `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" list --open` (or read
  `.claude/skills-state/sdlc-findings.yaml` directly; skip silently when
  neither exists), and
- PRD `open_questions` entries with `status: open` whose `blocks:` names an
  id this skill consumes (FR/WKF/SCR ids, an entity name).

When the combined list is non-empty, ask ONE `AskUserQuestion`: continue
anyway, or stop and run `/sdlc:repair` (findings) / `/sdlc:prd` (open
questions) first. Record the decision in the state file under
`input_adequacy: {checked_at, open_ids, decision}` so a resume does not
re-ask.

**Findings owed to this run are not gate items.** A triaged re-invoke finding
that `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" list --owed-by
docs/API.yaml` returns is waiting on this very run — its owed re-run is what
you are doing. Leave it out of the question and read it as the reason for the
change: its `fix` and `handoff` notes (canonical:
`sdlc/skills/ux/references/upstream-reconciliation.md` → "The `--reconcile`
form", step 3).

**Before dropping or renaming an emitted id** (an OPR endpoint id, a
resource slug), check its inbound references with
`python .claude/sdlc/docs_index.py --refs <id>` (skip when the helper is
absent) — downstream ARCH/TEST/TASKS artifacts may already cite it.

### Phase 3 (first step) — Repo evidence

Before seeding anything, look at what the project already has. On a greenfield
project this finds nothing and costs one command; on a **brownfield** one it is
the best evidence available, and this skill used to ignore it entirely.

```bash
python .claude/sdlc/repo_scan.py --domain api --json
```

Helper absent (the project never ran `/sdlc:setup`) → skip silently and seed
from the upstream artifacts alone. Never block the run on it.

It returns OpenAPI/Swagger documents, `.proto` files, GraphQL SDL, route decorators and `urls.py` — each hit a `path`, `line`
and one-line `excerpt`. Fold them into the pre-fill map below as **`⚠ inferred`
candidates**, never as answers: cite `<path>:<line>` in the `_rationale` sibling
of whatever field the evidence fed, confirm each one individually (the canonical
flow forbids batch-accepting inferred values), and pass on `truncated` /
`capped_signals` as "this is a sample of a large repo, not an inventory".

An existing OpenAPI document is the single best pre-fill this skill can get —
read it for the resource inventory and operations rather than re-deriving them
from surfaces. Finding route decorators but no spec means the API exists and is
undocumented, which is worth saying out loud.

Full rules, including what to do when the repo contradicts an upstream
artifact: `sdlc/skills/setup/references/repo-evidence.md`.

### Phase 3 — Idea capture (lightweight)

Unlike `sdlc:prd`, this skill does NOT need to capture a free-text idea
brief — PRD, UX, and DATA together fully describe the product. Quote it
back briefly:

> "Working from `docs/PRD.yaml`, `docs/UX.yaml`, and
> `docs/DATA-MODEL.yaml`. Product: `<name>` — `<one_liner>`. Surface
> family: `<surface_family>`. `<N>` PRD features, `<M>` UX surfaces,
> `<K>` DATA entities. Starting the API interview. Type anything to add
> framing context, or `ok` to proceed."

If the user types extra context, store it verbatim in `state.idea_text`.

### Phase 4 — Structural questions

These determine the *shape* of the API output:

1. **`api_kind`** — `rest | graphql | grpc | mixed | none`.
   - Derived from `PRD.technical_constraints.runtime_platform` (a LIST as
     of PRD 1.1 — read it as "contains") and `UX.surface_family`:
     - the list holds only `cli` and/or `library` AND
       `surface_family: cli | library` → strongly recommend `none`
     - it contains any of `web | mobile_ios | mobile_android | desktop |
       voice | tui` (or `surface_family: web | mobile | mixed`) → strongly
       recommend `rest`
     - it contains `service` → `rest` or `grpc`; ask the user
     - `server` / `browser_extension` / `embedded` / `other`, or a desktop
       app with a backend → ask the user
   - Always surface the recommendation as `⚠ inferred` position-1
     option; user must confirm or pick another.

2. **(only if `api_kind == none`)** Capture `rationale` (one sentence)
   and **skip to Phase 7**. Write a minimal `API.yaml` with
   `api_kind: none`, `rationale`, empty `resource_inventory`, no
   `API__*.yaml` files. Coverage + entity-link checks are skipped.

   **Also stamp the uniform marker**: `metadata.applicability:
   not_applicable`, `metadata.applicability_rationale` (the same sentence)
   and `metadata.applicability_confidence`. `api_kind: none` is this
   artifact's own vocabulary; `metadata.applicability` is what every other
   skill reads, and it is what lets `arch` skip the API without an `ls` and
   without asking the user. The validator errors when the two disagree, and
   warns when a legacy `api_kind: none` file carries no marker. Mechanics:
   `sdlc/skills/prd/references/optional-stages.md`.

3. **`transport_styles`** — multi-select from `rest, graphql, grpc,
   websocket, server_sent_events, webhooks_out`. Pre-fill: `[rest]` is
   the default when `api_kind: rest`; offer `websocket` or
   `server_sent_events` if any UX surface mentions real-time updates.

4. **(only if `transport_styles` includes `websocket`,
   `server_sent_events`, or `webhooks_out`)** Promote theme
   `events_async` to required.

Persist these to state under `api_kind:`, `rationale:`,
`transport_styles:` before proceeding.

### Phase 5 — Pre-fill confirmation

Present the pre-fill map **theme by theme**. Same rules as `sdlc:prd`
and `sdlc:ux`:

- `✓ found` items can be batch-accepted with `ok`.
- `⚠ inferred` items must be confirmed or corrected one by one. No
  batch-acceptance. **This is the hallucination guard.**

Write confirmed values to state with the right `_confidence` value:
`confirmed` (explicit pick or typed answer) or `inferred` (`⚠`
accepted as-is).

### Phase 6 — Theme interview

Walk the themes in this order (canonical order from
`api-questions.yaml`):

1. `api_kind_and_styles` — required (asked in Phase 4 above).
2. `versioning` — required.
3. `auth` — required.
4. `errors` — required.
5. `pagination` — required.
6. `idempotency` — required.
7. `rate_limiting` — required.
8. **`resource_inventory`** — required, `synthesis: true`. CRITICAL tier.
   Per-item drill-down (see `references/resource-discovery.md`). Build
   the inventory of resources and trace each to PRD features + UX
   surfaces + a DATA entity.
9. **`events_async`** — `required_if: transport_styles includes
   websocket | server_sent_events | webhooks_out`.
10. **`per_resource_deepdive`** — required, `synthesis: true`.
    CRITICAL tier. For each resource defined in theme 8, run a
    per-resource mini-interview that fills out the per-resource yaml
    (endpoints, DTO schemas, primary_entity, traces).
11. `external_dependencies` — optional (now/skip/todo gate).
12. `sdk_and_clients` — optional (now/skip/todo gate).

Required questions can never be `todo`'d. They must be answered, set to
`null` (writing a note to `api_warnings`), or the user must `EXIT`.

After all themes are addressed, set `suggestion_phase_done: true` in
state.

#### Within a theme: tiered question flow

Same tier mechanics as `sdlc:prd` and `sdlc:ux` — see
`references/interview-mechanics.md` for batch format and
`references/resource-discovery.md` for the `critical` per-resource
state machine.

Tier assignments (set in `api-questions.yaml`):

- Theme 8 (`resource_inventory`) → `critical` per item — every
  resource is examined, named, given a base_path, and traced back to
  PRD features + UX surfaces + a DATA entity.
- Theme 10 (`per_resource_deepdive`) → `critical` per resource — for
  each resource, run the full per-resource mini-interview (endpoints
  / schemas / primary_entity / traces).
- Themes 3, 4, 5, 6 → `high` (agent drafts; user iterates).
- Remainder → `med` (batched 2–4 per `AskUserQuestion` call).

**Read `references/resource-discovery.md` before running theme 8 or 10.**
**Read `references/openapi-embedding.md` before running theme 10.**
**Read `references/async-and-events.md` before running theme 9.**

The two non-negotiable rules in this phase:

1. `⚠ inferred` candidates surface as the **position-1 recommended
   option** in their `AskUserQuestion` call. They cannot be silently
   accepted — the user must explicitly pick or correct.
2. State is written after **every confirmed batch, every mini-section,
   and every per-resource deep-dive completion**.

#### Conditional promotions (`required_if`)

Some questions in `api-questions.yaml` are conditionally required:

| Question / theme | Becomes required when |
|---|---|
| `api_kind_and_styles.rationale_for_none` | `api_kind == 'none'` |
| `api_kind_and_styles.transport_styles` | `api_kind != 'none'` |
| `events_async` (whole theme) | `transport_styles` includes `websocket`, `server_sent_events`, or `webhooks_out` |
| `pagination.default_page_size`, `max_page_size` | `pagination.strategy != 'none'` |
| `pagination.stable_sort_field` | `pagination.strategy == 'cursor'` |

Re-evaluate at the start of each new theme batch.

### Phase 7 — Write & validate

Write or merge `docs/API.yaml` and write every
`docs/API__<resource>.yaml` in one consistent batch (so that the
resource inventory and the per-resource files always agree).

When writing, (re)write `metadata.upstream_provenance`: one entry per upstream
artifact consumed this run (`docs/PRD.yaml`, `docs/UX.yaml`,
`docs/DATA-MODEL.yaml`), each `{file, session_id, last_updated, sha256}` with
`sha256` from `docs/INDEX.yaml.generated_from[<file>]`, else
`python .claude/sdlc/docs_index.py --hash <file>`, else sha256 over the
file's utf-8 text (first 16 hex — the same value `--hash` prints).
Replace-on-write (not append-only). See CLAUDE.md §7.

Deferrals the user explicitly chose (a PRD FR that needs no endpoint, a UX
screen no endpoint serves) are written to the top-level
`deferrals: [{id, reason}]` list — never as a bare id in `non_api_features`
(deprecated: still passes for one more version, but every id that relies on
it is reported) and never as prose in `api_warnings` alone (the WRN note
stays the human-readable companion, not the machine channel). Internal-only
resources (health, metrics, ops) set `internal: true` instead of inventing
traces.

Then run:

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/API.yaml
```

The validator also walks `docs/API__*.yaml` siblings and runs three
checks (all skipped when `api_kind: none`):

1. **Feature coverage**: every PRD `features` `FR-NNN` must
   appear in some resource's `traces_prd_features` OR be deferred via
   the top-level `deferrals: [{id, reason}]` list (a bare id in
   `non_api_features` still passes for one more version and is
   reported). Uncovered features are appended to `api_warnings` and
   force `status: draft`.
2. **Surface coverage**: every data-bearing UX surface (see
   `references/merge-validate.md` for the type list) must appear in
   some resource's `traces_ux_surfaces` or be deferred the same way.
   Uncovered surfaces force `status: draft`.
3. **Entity-link check**: every `primary_entity` value must exist in
   `DATA-MODEL.yaml.entities`. Unresolved entities force
   `status: draft`. Skipped if `DATA-MODEL.yaml` is absent (with a
   warning).

For full merge logic and the exit-code recovery flow, see
`references/merge-validate.md`.

When writing files: inline YAML comments on top-level keys, updated
`metadata.last_updated` and `metadata.session_id`.

Set `metadata.status`:
- `"complete"` — only when all required fields are filled, the validator
  passes with `[OK]`, AND all three checks pass (or are skipped due to
  `api_kind: none`).
- `"draft"` — on early EXIT, when any required field is null, or when
  any check fails.

### Phase 8 — Refresh & complete

**This skill does not write `CLAUDE.md`.** That file is owned by `/sdlc:setup`,
which writes one static `## SDLC Documents` block. A caveat belongs in this
artifact's own `WRN-NNN` list, a spec defect in the findings queue, a skill
defect in the lessons queue — never as a note, a bullet or a "resolved" section
in `CLAUDE.md`. See `references/merge-validate.md`.

Then: set `status: complete` in the state
file (keep the file — audit trail), then **refresh the navigation
index** (`python .claude/sdlc/docs_index.py`; no-op if the project never
ran `/sdlc:setup` — the freshly-installed hook isn't active until the
next session, so the explicit refresh keeps `INDEX.yaml` current now).
Optionally confirm the write introduced no dangling id references:
`python .claude/sdlc/docs_index.py --check` (skip when the helper is
absent).

**Refresh the statusboard.** Run `python .claude/sdlc/statusboard.py` in the
same breath. It regenerates `.claude/rules/sdlc-statusboard.md` (loaded into
every session) and `.claude/sdlc/STATUS.md` from the artifacts, so this run's
new warnings, deferrals and open questions are visible to the next agent
without anyone writing them down by hand. Harmless no-op if it is not installed.

**Drain findings (CLAUDE.md 13).** Before the lessons self-review:

1. Drain `state.finding_notes` — each mid-run observation becomes one

   ```bash
   python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add --raised-by sdlc-api \
     --kind <kind_guess> --summary "<what is wrong>" --file <docs file> \
     --field-path <dotted.path> --evidence "<quote>"
   ```

   Skip silently when the script is absent; a non-zero exit becomes one
   `Attention:` clause, never a blocker.
2. Auto-raise `upstream_incomplete` for every schema-REQUIRED upstream
   field the Phase-2/3 pre-fill found null or empty in a `complete`
   upstream. The summary MUST start `<upstream file> <field path>:` and
   `--detected-by` is `sdlc-api`, so the (detected_by, summary) dedupe in
   `findings.py` lands each defect once across runs, not once per run.
3. Cap: at most 3 findings per run, unless one is blocking.

Close by telling the user where the artifacts live and what comes next:

**Self-review & record the run** (CLAUDE.md 15; doctrine:
`sdlc/skills/lesson/references/lessons-capture.md`). First drain `state.lesson_notes` (mid-run observations — that file →
"Mid-run: note now, record at close"), then answer the self-review questions
from that file for this run. Each yes that matches a raising condition
becomes one `lessons.py add` (at most 2 per run unless one is a `blocker`;
drained notes count toward the cap). Then record the run:

```bash
python .claude/sdlc/lessons.py record-run --skill api --plugin-root "${CLAUDE_SKILL_DIR}/../.."
```

Best-effort: a non-zero exit becomes one `Attention:` clause in the card;
helper absent (project never ran `/sdlc:setup`) — skip silently.

**Close with the card** (CLAUDE.md 14; canonical shape:
`sdlc/skills/prd/references/reporting-to-the-user.md`). The user reading this
knows only "there is a pipeline and I run it in order", so answer their three
questions and nothing else: did it work, can I run the next skill, what do I
type next.

```
-- /sdlc:api - what you have now ---------------------
Wrote:     docs/API.yaml + docs/API__*.yaml ({the one count that matters})
Status:    complete - /sdlc:arch can run it
Attention: {what needs a decision, in the user's words}
Findings:  {N recorded (FND-NNN, ...) -> /sdlc:repair}
Next:      {the computed next invocation}   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript.
```

**Compute the `Next:` row; never copy the example** — the card above is a
shape, and its `Next:` literal is an example, never a value to print
through. Procedure and successor map:
`sdlc/skills/prd/references/reporting-to-the-user.md`
(CLAUDE.md 14). For `/sdlc:api` it resolves to, first match wins:

- **`docs/` artifact is `draft`, the user typed `EXIT`, or the validator is not
  green** → `Next:` is `/sdlc:api` again, and `Status:` says what finishing
  means. Never hand off an unfinished artifact.
- **This run recorded findings, or open findings name an artifact this skill
  consumed** — except a re-invoke finding still waiting on `docs/API.yaml` or
  on a file downstream of it (`findings.py list --owed-by`): that is a
  reconcile chain in progress → `Next:` is `/sdlc:repair` (name the ids)
  before any successor.
- **This run was a `--reconcile`, or `docs_index.py --stale` lists a file
  downstream of `docs/API.yaml`** → the first `--stale` row's command.
  Nothing stale any more and a finding was owed to this run →
  `/sdlc:repair FND-NNN`, which closes it.
- **Complete and green** → `/sdlc:arch` is the pipeline successor and always the successor here — `api` is not sharded.


Rules: omit any row with nothing to say (never write "no warnings"). Add a
`Lessons:` row only when this run recorded at least one — e.g. `Lessons: 1
recorded (LSN-004) - about this skill, for its maintainer; nothing for you to
do` — and never print "no lessons". Add the `Findings:` row only when this
run recorded findings or open findings name an artifact this skill consumed —
e.g. `Findings: 2 recorded (FND-011, FND-012) -> /sdlc:repair` — and never
print "no findings".
**`Attention:` is translated, never pasted validator output** - turn each
finding into what happened, why it matters, and what to do. If the validator
printed nothing worth acting on, drop the row.

## Session state file

Path: `.claude/skills-state/sdlc-api.state.yaml`

Schema (extends the baseline state schema from CLAUDE.md):

```yaml
session_id: <uuid4 string>
skill_version: <the skill_version at the end of this file>
started_at: <iso8601>
last_updated: <iso8601>
status: in_progress  # in_progress | complete | aborted

# Phase 4 — structural answers (mirror API.yaml top-level)
api_kind: null              # rest | graphql | grpc | mixed | none
rationale: null             # populated only when api_kind == "none"
transport_styles: []        # populated only when api_kind != "none"

idea_text: null             # optional extra context user typed in Phase 3
pre_fill_confirmed: false
suggestion_phase_done: false
completed_themes: []
skipped_themes: []
todo_themes: []
pending_themes: []
current_theme: null
current_resource: null      # which resource_id is mid-deepdive (theme 10)

# Per-family ID counters (single-product mode). Each entry is the
# last-assigned integer for that family — increment, format as
# <PREFIX>-{:03d}, then persist. This skill emits two families:
#   WRN — api_warnings entries.
#   OPR — per-endpoint stable id (lives on each endpoint as `id`).
last_ids: {}                # e.g. {WRN: 3, OPR: 17}

# Per-product ID counters (monorepo mode only). Same shape as last_ids,
# keyed by product slug. Each product carries an independent WRN/OPR id space.
last_ids_by_product: {}     # e.g. {billing: {WRN: 1, OPR: 8}, notifications: {WRN: 0, OPR: 3}}

# Resource registry — one entry per defined resource
defined_resources:          # extension over the baseline state schema
  - resource_id: <kebab>
    base_path: </v1/...>
    status: defined          # defined | draft | confirmed
    file_path: docs/API__<slug>.yaml
    primary_entity: null     # PascalCase DATA entity NAME; set during theme 8
    traces_prd_features: []  # FR-NNN ids; set during theme 8
    traces_ux_surfaces: []   # SCR-NNN ids; set during theme 8
    traces_prd_workflows: [] # WKF-NNN ids; optional; set during theme 8

dropped_candidates: {}            # {<schema_path>: [{candidate, seeded_from,
                                  #   reason, at}]} — resource_inventory
                                  # candidates the user dropped or skipped at
                                  # the sweep, so resume doesn't re-propose.
                                  # Entries in the legacy list
                                  # `dropped_resource_candidates` are read as
                                  # the resource_inventory bucket.

input_adequacy: null              # Phase 2 gate: {checked_at, open_ids,
                                  # decision} — recorded once per run so a
                                  # resume does not re-ask.

delta_review:                     # section-7 reconcile progress (re-runs only)
  upstreams: []                   # [{file, recorded_sha, current_sha}]
  decisions: []                   # per-item picks already confirmed
  unresolved: []                  # items still to review on resume

lesson_notes: []                  # mid-run lesson scratch (CLAUDE.md 15):
                                  # {noted_at, about, kind_guess, note} —
                                  # drained by the Phase 8 self-review; the
                                  # run is never interrupted to record.

finding_notes: []                 # mid-run finding scratch (CLAUDE.md 13):
                                  # {noted_at, kind_guess, file, summary,
                                  # evidence} — drained at Phase 8 through
                                  # findings.py; the run is never interrupted
                                  # to record.

# Run telemetry (CLAUDE.md 15) — updated in the same write as everything
# else; consumed only by `lessons.py record-run` at close.
metrics: {}                 # questions_asked, free_text_answers,
                            # free_text_by_question{<question-id>: n},
                            # validator_runs, validator_failures, resumes

partial_answers: {}         # mirrors API.yaml structure incrementally
partial_resources: {}       # mirrors per-resource yamls incrementally,
                            # keyed by resource_id
```

Rules:

- Generate `session_id` as a UUID4 on first creation.
- Update `last_updated` on every write.
- Write the file **after every confirmed batch** and **after every
  per-resource deep-dive completion**.
- The `metrics` counters (schema above) update in the same write: a batch
  bumps `questions_asked`; an Other/free-text answer bumps `free_text_answers`
  and `free_text_by_question[<question-id>]`; a resume bumps `resumes`
  (Phase 1); Phase 7 counts `validator_runs`/`validator_failures`.
- On user `EXIT`: set `status: aborted`, write current
  `partial_answers` and `partial_resources`, drain `lesson_notes` (the
  close self-review, CLAUDE.md 15) AND `finding_notes` (through
  `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add`; skip silently
  if the script is absent), run
  `python .claude/sdlc/lessons.py record-run --skill api --outcome aborted`
  (skip silently if the helper is absent), confirm to user, stop.
- On Phase 8 completion: set `status: complete`, keep the file.
- The validator ignores this file — it validates only `docs/API.yaml`
  and the resource yamls.

**Source of truth on resume:**

- `docs/API.yaml` + the existing `docs/API__*.yaml` files (if present)
  are the on-disk source of truth for *answers*.
- The state file is the source of truth for *interview progress*.
- On resume: load the on-disk yamls first as the baseline, then layer
  `partial_answers` and `partial_resources` on top.
- If they conflict on the same key, ask the user which to keep —
  never silently overwrite.

## Edge cases

For unusual situations (PRD/UX/DATA missing or in draft, surface with
no obvious resource, DATA entity deleted mid-session, conflicting auth
across resources, mid-interview transport_style change, validation
failures, write-permission errors, very large APIs, monorepo mode) →
`references/edge-cases.md`.

## Style of conversation

The interview can be long, especially for products with many resources.
Keep it humane:

- Use the user's terminology as soon as they introduce it.
- Keep `AskUserQuestion` batches to 2–4 questions; never more than 4.
- Acknowledge progress at each theme boundary
  (*"Auth done — next: errors. RFC 7807 envelope strongly recommended."*).
- For theme 10 (per-resource deep-dive), announce each resource before
  diving in (*"Now: `users` resource (5 endpoints expected, primary
  entity User)."*).
- Always make multiple-choice the path of least resistance.
- For the `resource_inventory` and `per_resource_deepdive` themes,
  explicitly call out that candidates were synthesized from DATA + PRD
  + UX — don't pretend they came from nowhere.
- After all themes are done, congratulate the user briefly and move to
  write/validate. Do not repeat everything back at them.
  (This is about the INTERVIEW. The Phase-8 close report is separate and
  is NOT optional — see the card in Phase 8.)

## Quick reference: commands the user can type

| User input | Effect |
|---|---|
| `EXIT` | Abort: type into the free-text field of any AskUserQuestion call. |
| `confirm` | Accept a single inferred pre-fill (Phase 5). |
| `ok` | Batch-accept all `✓ found` pre-fills in the current theme, OR accept the Phase 3 framing summary. |
| `now` | Run the proposed optional theme (gate question). |
| `skip` | Skip the proposed optional theme (gate question). |
| `todo` | Defer the proposed optional theme; logs it to `api_warnings`. |

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.9"
