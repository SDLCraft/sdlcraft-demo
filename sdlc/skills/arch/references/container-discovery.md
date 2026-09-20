# Container discovery — system mode Phase 3

This file describes how to seed the **container inventory** for
`docs/ARCH.yaml` from the upstream artifacts (`PRD.yaml`,
`UX.yaml` + `UX__*.yaml`, `DATA-MODEL.yaml`, `API.yaml` +
`API__*.yaml`). Read this on entering Phase 3 of system mode.

The goal: present a draft container list **before** any per-container
drill-down begins, so the user can correct course early. Hallucinated
containers are the most expensive error this skill can make — every
downstream skill (test, task, deploy) propagates them.

## Source priority

Run the following passes in order. Each pass adds candidates; later
passes can refine but never silently drop earlier candidates.

### Pass 1 — Frontend containers (from `UX.yaml`)

`UX.yaml.surface_family` decides the frontend shape:

| surface_family    | Default container(s)                          |
|-------------------|-----------------------------------------------|
| `web`             | `web-frontend`                                |
| `mobile`          | `mobile-frontend`                             |
| `desktop`         | `desktop-frontend`                            |
| `cli`             | `cli`                                         |
| `tui`             | `tui` (terminal app — treat like `cli`)       |
| `voice`           | `voice-frontend` (conversational adapter)     |
| `service`         | none — the product IS the backend service (Pass 2+) |
| `library`         | none — the product IS the package (Pass 2+)   |
| `mixed`           | one container per actual surface_type cluster |
| `none`            | no frontend container                         |

All surfaces from `UX__*.yaml` go into one frontend container *by default*.
Split into multiple frontend containers only when:

- Different surfaces target different platforms (e.g. web + mobile).
- A surface explicitly belongs to a different audience (admin panel vs.
  end-user app) AND the PRD has separate personas.
- The user opts to split (Phase 3 confirmation).

Tag all surfaces from a frontend container's `owns_ux_surfaces`.

### Pass 2 — Backend containers (from `API.yaml`)

If `API.yaml.api_kind != none`, propose at least one backend container.

Splitting rules:

- If `API.yaml` defines `tags` or `bounded_context` on resources, group
  resources by tag/context — each group → one backend container.
- If the architecture pattern (Phase 4 question) is `microservices` or
  `event_driven`, propose one backend container per resource group at
  the bounded-context level.
- Otherwise default to one backend container holding *all* API resources.
  Confirm with the user.

Backend containers' `owns_api_resources` are the resources from their group.

### Pass 3 — Data stores (from `DATA-MODEL.yaml`)

Every entry in `DATA-MODEL.persistence.*` becomes a container with
`external: true` unless explicitly self-hosted:

- `primary_store`: `postgres` / `mysql` / `sqlite` / `mongodb` / ... →
  one `primary-database` container.
- `secondary_stores[].kind ∈ {cache, redis, memcached}` → `cache` container.
- `secondary_stores[].kind ∈ {blob, s3, gcs}` → `blob-store` container.
- `secondary_stores[].kind ∈ {search, elastic, opensearch}` →
  `search-index` container.
- `secondary_stores[].kind ∈ {queue, kafka, sqs, pubsub}` → `message-bus`
  container.

Each data-store container has empty `owns_api_resources` and
`owns_ux_surfaces`; its `persistence` list contains *itself* (the
store_id), and its `realizes_store` names the **stable DATA store id**
it realizes: `"primary"` for the primary store, else the secondary's
`store_id` (B8). That id — not the container_id — is what migration and
integration tasks key on; the validator resolves `realizes_store` and
every persistence reference against the DATA store-id set (warning-only,
legacy names accepted as aliases). When `DATA-MODEL.persistence.paradigm`
is `"none"` (a stateless project), this pass proposes no containers and
the store checks are a stated no-op.

### Pass 4 — Operational containers (from PRD)

Walk `PRD.functional_requirements.features` and look for
keywords that imply non-API operational work:

| Keyword cluster                          | Candidate container         |
|------------------------------------------|------------------------------|
| "scheduled", "nightly", "weekly", "cron" | `scheduler`                  |
| "batch", "import", "ETL", "ingestion"    | `worker` (batch_job)         |
| "real-time", "stream", "event"           | `stream-processor`           |
| "notification", "email", "SMS"           | `worker` (notifications) OR external |
| "AI agent", "LLM", "inference"           | `ml-inference`               |
| "webhook receiver"                       | `gateway` or merge into backend |
| "static landing page"                    | `static-site`                |

These are `⚠ inferred` candidates — surface them with the FR-NNN
evidence inline ("FR-014 mentions 'nightly cleanup' → `scheduler`
container?").

### Pass 5 — Identity provider (from PRD + API)

The edge-derivation rules (`edge-derivation.md` Rule S3) emit a `calls`
edge from every authenticated backend container to the identity
provider. For those edges to resolve, the IDP MUST exist as a node in
`containers[]`. Therefore:

- If `PRD.security_compliance.auth_model ∈ {oauth2, sso, openid_connect,
  oidc, saml, jwt, passkeys}` OR `API.auth.schemes` contains anything
  other than `[none]`: **always auto-propose an `identity-provider`
  container.**
  - Default `external: true` (most projects use Auth0 / Cognito / Okta /
    Clerk / etc.).
  - Set `external: false` only if the user has explicitly stated they're
    building their own IDP.
  - Empty `owns_api_resources`, empty `owns_ux_surfaces`, empty
    `persistence`.
- If `auth_model == none` AND every entry in `API.auth.schemes` is
  `none`: no identity container.

This is `⚠ inferred` but the user has to actively *remove* it to abort
auto-add — the default is to keep it. Otherwise downstream edge
derivation will drop the `calls → identity-provider` edges (Rule S3)
and the system loses traceability of token validation.

### Pass 5b — External integrations (from PRD INT ids)

Walk `PRD.functional_requirements.integrations_required` (INT-NNN). For
each integration, propose the container that is its **seam**:

- Usually an `external-service` container (`external: true`) for the
  provider itself, carrying `realizes_integrations: [INT-NNN]` and an
  `external_contract` block (protocol, auth_scheme,
  credential_config_keys, client_library, failure_semantics, rate_limits,
  sandbox_available) — without it the build stage guesses the provider
  contract.
- Occasionally an internal worker/gateway that owns the client side
  (webhook receiver, sync worker) — then that container records the
  INT id and the client component records `int_refs` in container mode.

Every PRD INT-NNN must end up in some container's
`realizes_integrations`, some component's `int_refs`, or `deferrals`
with a reason — the INT coverage check enforces trace-or-defer
(blocking at arch_version >= 2.0). These are `⚠ inferred` candidates
with the INT id quoted inline.

### Pass 6 — Gateway / BFF (from pattern + container count)

- If `architecture_pattern.pattern == microservices` AND more than 2
  backend containers exist: propose `gateway` (`api-gateway` /
  reverse proxy / ingress).
- If frontend ≥ 1 AND backend containers ≥ 2 AND the pattern hint
  suggests per-client APIs: propose `bff` (one per frontend).

These are `⚠ inferred` — never auto-add.

## Inferred vs found

Each candidate is tagged for the user:

- `✓ found` — direct evidence (UX surface, API resource, DATA store).
- `⚠ inferred` — derived from keywords/heuristics (Pass 4, 5, 6).

`⚠ inferred` candidates **must** be confirmed individually (the
hallucination guard from `interview-mechanics.md`). Bulk acceptance is
allowed only for `✓ found` items, with a per-item escape hatch.

## Presentation

The Phase 3 presentation is a numbered list plus an "Add, remove, or
rename anything?" prompt:

```
Drafted from upstream artifacts:

  ✓ web-frontend     (web-frontend)    owns: dashboard, login, settings
  ✓ backend-api      (backend-api)     owns: users, projects, files
  ✓ primary-postgres (primary-database) — DATA primary_store
  ✓ redis-cache      (cache)           — DATA secondary_store
  ⚠ scheduler        (scheduler)       — inferred from FR-014 "nightly cleanup"
  ⚠ identity-provider (external)       — inferred from PRD oauth2

Add, remove, or rename anything before we go deep on each one?
```

The user can:

- `ok` → accept all `✓ found` items, then walk through `⚠ inferred`
  one-by-one.
- `drop scheduler` / `rename web-frontend to admin-ui` / `add: cdn`.
- `EXIT` → save state and stop.

Persist the confirmed list to
`state.sessions[system].defined_containers`. Each entry:

```yaml
- container_id: <kebab>
  archetype: <enum>
  status: proposed | draft | confirmed | dropped
  source: ux | api | data | prd-feature | prd-auth | pattern | user-added
```

After Phase 3 confirmation, Phase 6's `container_inventory` theme walks
the *confirmed* list per-item (critical state machine). During that
per-item drill-down, record the FR-NNN that seeded the container (Pass 4)
into the container's `implements_requirements` — this is what makes an
operational container (scheduler/worker, no API resource) traceable.

## Scope-completeness sweep (synthesis theme)

`container_inventory` is a `critical synthesis: true` theme. The
container list is the single most consequential scope decision in the
whole architecture — a missed container cascades into every downstream
skill. So **after the per-item loop closes, before the inventory is
finalized, run a dynamic scope-completeness sweep** (canonical spec:
`${CLAUDE_SKILL_DIR}/../prd/references/importance-flows.md` →
"The `critical` flow → Step e — dynamic scope-completeness sweep").

Reflect, in order, on:

1. **The draft container list itself** — are two candidates really one
   container? Is one candidate secretly two (e.g. a "backend" that both
   serves an API and runs a nightly job)?
2. **Every upstream ID family**, not just the most direct one:
   - **PRD `FR-NNN` features** — is every feature
     implemented by some container in the list? An FR with no home is
     the loudest signal of a missing container (esp. operational ones).
     This is the same set the Phase 7 feature-coverage check enforces —
     surfacing it here is cheaper than failing validation later.
   - **PRD `WKF-NNN` workflows** — does any workflow span a step that no
     container performs (e.g. an async "send digest email" step)?
   - **PRD `ENT-NNN` / DATA entities + `persistence.*` stores** — is
     every store bound to a container? A store with no owner is a
     missing data-store container.
   - **API resources + `events.channels`** — every resource needs a
     backend owner; every event channel needs at least one publisher and
     one subscriber container.
   - **PRD `INT-NNN` integrations** — every integration needs a seam
     container (the external provider, or the internal owner of the
     client side); an INT with no home fails the INT coverage check at
     Phase 7 unless deferred with a reason.
   - **UX `SCR-NNN` surfaces** — every data-bearing surface needs a
     frontend owner.
3. **Project-type heuristics** — CLI tool, SaaS web app, library, data
   pipeline, browser extension: each implies a characteristic container
   set (e.g. a pipeline implies ingest + transform + sink stages).
4. **Build-time deliverables** — scan the FR texts for concrete
   repo paths and shipped-artifact nouns (a schema/model layer, repo-root
   `tools/` validators, `templates/`, prompt/question/archetype packs,
   generated docs). Every such path must fall inside the scope of SOME
   container in the list — usually as components of an existing container
   (see `component-discovery.md` → Pass 6), occasionally as a dedicated
   tooling/content container. Runtime-driven seeding (Passes 1–5) never
   proposes these, and a deliverable with no owning container means the
   downstream `task` stage can never schedule building it. (The validator's
   advisory #25 only auto-flags paths written as inline code in FR text; your
   sweep reads all prose, so backtick a genuine deliverable path in the FR so
   #25 can enforce its coverage.)

Surface the concrete missed **candidate containers** — not category
labels — via **one multi-select `AskUserQuestion`** ("I may have missed
these — which are real containers?"). Caps: at most **2 sweep passes**;
defer anything still unresolved to an `arch_warnings` `WRN-NNN` entry;
honour the **anti-padding rule** — surface zero candidates rather than
manufacture filler. Accepted candidates re-enter the per-item state
machine before the list is finalized.

**Skip the sweep at your peril** — it's the main defence against the
synthesis-stage gap where an FR-NNN literally naming an operational
verb ("nightly cleanup", "send invoices") never became a container
because Phase 3 only seeded from the most-direct upstream signal.

## Edge cases

- **Zero containers** — happens for pure-docs projects or if the user
  drops every candidate. Surface a warning and offer to EXIT.
- **Duplicate names** — the agent never silently dedupes. Surface the
  conflict and ask which to keep.
- **Container archetype mismatch** — if the user changes a container's
  archetype mid-session, recompute `suggested_components` for the
  container-mode interview on resume.
