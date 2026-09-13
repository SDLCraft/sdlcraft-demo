# Edge derivation — how API + DATA + UX seed the typed edge graph

The typed edge graph is the unique value `sdlc-arch` adds over the
upstream skills. Edges are **derived from upstream artifacts**, not
enumerated by the user. The user confirms or edits a derived list.

This file is read at three points:

1. Phase 6 of system mode, theme `cross_container_edges`.
2. Phase 6 of container mode, theme `internal_and_external_edges`.
3. Every `-d` / `--dependencies` invocation (Phase 7-D).

## The seven edge types

| Type            | When to emit it                                                                              |
|-----------------|----------------------------------------------------------------------------------------------|
| `depends_on`    | Hard start-up / build-time dependency (e.g. service needs config from another at boot).      |
| `calls`         | Synchronous request (HTTP / RPC / function). The default for API-resource consumption.       |
| `reads`         | Read access to a data store / cache / blob / index.                                          |
| `writes`        | Write access to a data store / cache / blob / index.                                         |
| `publishes`     | Emits events to a bus / queue / channel.                                                     |
| `subscribes_to` | Consumes events from a bus / queue / channel.                                                |
| `implements`    | Realizes an abstract contract / interface defined elsewhere (rare — used for plugin archs).  |

`reads` and `writes` may both apply — emit two edges in that case
(don't invent a `read_write` type).

Hierarchical relationships (`contains`, `owns`) are NOT edges — they
live in the document structure (`containers[].components[]`).

## Edges vs imports — keep the call graph layering-legal

Once components carry `code_location` (see
`references/component-discovery.md`), an internal edge and a source-level
*import* are two different graphs, and the downstream codegen agent will
write real imports from them. Be explicit about how each edge type is
**realized** so codegen doesn't write an illegal import:

| Edge type                       | How codegen realizes it                              |
|---------------------------------|------------------------------------------------------|
| `depends_on`, `implements`      | A real **build-time import** — must respect the project's import layering (dependency direction). |
| `calls`, `reads`, `writes`      | A **runtime call**. Often a direct import (controller → service), but between *peer* components it is frequently wired at a composition root / router rather than a direct import. |
| `publishes`, `subscribes_to`    | **Runtime, indirected** through a bus/queue — never a direct import between the two components. |

The trap: a `calls` (or `reads`/`writes`) edge between two components in
the **same layer** (e.g. `service → service`, or two pipeline nodes that
"call" each other) implies a *sideways import*, which many layered
architectures forbid ("never import sideways or upward"). In reality such
peer-to-peer runtime edges are composed by a higher-layer component (a
router, an orchestrator, a graph/composition module), not by one peer
importing its sibling.

When you derive an internal `calls`/`reads`/`writes` edge whose endpoints
share a layer in their `code_location` (or whose archetypes are siblings,
e.g. two `service`s, two `event_handler`s), do **one** of:

1. **Retarget** the edge through the composing component if one exists
   (the router/orchestrator/graph module that wires them), so the edge —
   and the import codegen derives from it — points downward, not sideways.
2. Keep the runtime edge but add an **`arch_warning` (WRN-NNN)** stating
   that it is a runtime wiring edge realized at the composition root, NOT
   a direct import, so the codegen agent does not emit a sideways import.

`depends_on` is the only type that should ever denote a hard import between
peers — and even then it must respect the layer order. This is what lets
you mechanically check every internal edge against the import layering once
`code_location` is set.

## Edge `via_*` pre-fill (REQUIRED practice)

Every derived edge has OPTIONAL `via_*` fields that ground it in an
upstream artifact. These are not optional in spirit — the downstream
`test` and `task` agents lean on them heavily. **Always pre-fill them
when the evidence is unambiguous.**

| Edge type        | Required `via_*` pre-fills (when evidence exists)                |
|------------------|------------------------------------------------------------------|
| `calls` (internal) | `via_unit` (the callee `work_units[].name` on the `to` component) + `via_resource_id` when the callee traces a resource |
| `calls` (external, callee exposes an API) | `via_resource_id` (the API resource being called) + `via_operation_id` (the specific API endpoint on the called container). Mirror the resource into this container's `api_consumers[]` (cross-check #26). |
| `calls` (external, callee is an internal SIBLING with no API between them) | `via_unit` (the callee `work_units[].name` on the `<container_id>/<component_id>` target — requires that `to` form). The cross-container analogue of the internal via_unit. |
| `calls` (external, SUBPROCESS/CLI seam — callee invoked as a process) | `via_unit` → the callee's **`entrypoint`** work_unit; `invocation` → this caller's mode selector + resolved args/params. See the subprocess-seam rule below. |
| `reads`/`writes` | `via_entity` (the DATA entity primarily accessed)                |
| `publishes`      | `via_channel_id` (the API.events channel)                        |
| `subscribes_to`  | `via_channel_id` (the API.events channel)                        |
| `depends_on`     | None — pure topology.                                            |
| `implements`     | None — contract is the edge's only payload.                      |

If derivation produces an edge but no upstream evidence exists for the
`via_*` field, leave it null and add a note in `note:` explaining the
ambiguity. The validator does NOT require `via_*` to be set, but it
DOES validate any value that is set — typos in `via_*` are blocking
errors.

**Backfill passes sweep ALL `calls` edges — internal AND external.** When a
later pass backfills `via_unit` (e.g. after work_units were added to a
container), the sweep scope is *every* `calls` edge whose callee now declares
work_units: the intra-container `internal_edges`, **and the `external_edges`
whose target is a sibling container** (`<container>/<component>` form). The
historical failure mode is exactly a backfill that covered all N internal
edges and skipped the one cross-container call to an internal sibling —
enumerate the edge list from the files, don't enumerate from memory of "the
edges I was just editing".

**Subprocess / CLI seam — pin the INPUT contract on a shared seam, not just the
return.** When container A invokes container B as a **process** (a CLI/shell it
shells out to, no API between them), the contract has two directions and both
must be pinned **on one shared seam** — otherwise the caller authors the return
shape `(exit_code, stdout, stderr)` on its own side and the callee re-derives the
call shape independently. The seam is the callee's **`entrypoint`** work_unit:

- The **callee** exposes one `entrypoint` work_unit whose contract pins **both**
  directions: `inputs` = the argv/mode-selector + parameterization it accepts;
  `output` = the process result it returns (exit code, and stdout/stderr shape
  when structured); `raises` = the failure exit conditions.
- The **caller**'s external `calls` edge sets `via_unit` → that `entrypoint`
  unit, and records **its own** binding (which mode + which resolved args it
  invokes with) in the edge's `invocation`. The caller must **not** re-author the
  return shape on its side — the entrypoint unit is the single source of truth.

A cross-container `calls` edge with none of `via_operation_id` / `via_resource_id`
/ `via_unit` set has an **unpinned** invocation seam — cross-check #27 warns, and
downstream codegen has to guess the mode selector + parameterization. The
tightened arm of the same check: an edge whose `via_unit` resolves to an
`entrypoint` unit but that records **no `invocation`** also warns — the callee
pins both directions of the contract, yet nothing says how THIS caller binds
them. Derivation and `-d` backfill passes therefore fill `invocation` in the
same pass that points `via_unit` at an entrypoint.

## System-level derivation rules

Scope: edges between containers in `docs/ARCH.yaml`.

### Rule S1 — API consumption (`calls`)

For every resource `R` in `API.yaml.resource_inventory[]`:

- Find the producer container `P` such that `R.resource_id ∈ P.owns_api_resources`.
- For every consumer container `C` such that `C != P` AND
  any of `C`'s `owns_ux_surfaces` calls `R` (per `UX__<surface>.yaml.interactions`
  with `effect: call_api` pointing at `R`):
  emit `{ from: C, to: P, type: calls, via_resource_id: <R>, note: "consumes <R>" }`.
- If `UX` doesn't disambiguate which surface calls which resource (the
  default), fall back to: every frontend container `calls` every backend
  container whose resources its surfaces *could* be calling. Surface this
  as a single edge per (frontend, backend) pair — the agent confirms
  during the synthesis review. In the fallback case, leave `via_resource_id`
  null (ambiguous) and explain in `note`.

### Rule S2 — Persistence (`reads` / `writes`)

For every container `C` and every store_id `S` in `C.persistence`:

- `S` is a **stable DATA store id** (B8): `"primary"` for
  `DATA-MODEL.persistence.primary_store`, else a secondary's `store_id`
  (legacy names are accepted as aliases, but new writes use the ids —
  the validator warns on entries matching no DATA store).
- Find the store container `T` such that `T.container_id == S` OR
  `T.realizes_store == S` OR
  `T.archetype ∈ {primary-database, secondary-database, cache, blob-store, search-index}`
  AND `T.container_id == S`. Prefer matching on `realizes_store` — it is
  the explicit binding; the container_id match is the legacy heuristic.
- Inspect `C`'s expected access pattern:
  - Backend container with API resources → `reads` + `writes` (both edges).
  - Worker / scheduler / batch container → `writes` (and `reads` if the
    feature description implies it).
  - Cache client → `reads` + `writes`.
  - Read-only replica binding → `reads` only.
- Emit one edge per access mode, both `from: C` `to: T`. Set
  `via_entity: <PascalCaseEntityName>` to the primary entity being accessed
  when DATA-MODEL.access_patterns lets you identify it; otherwise leave
  null and note the ambiguity.

### Rule S3 — Identity (`calls`)

For every backend container `C` with `auth.schemes` mentioning JWT /
OIDC / SAML AND the system has an `identity-provider` container `IDP`:

- Emit `{ from: C, to: IDP, type: calls, note: "validates tokens" }`.
  No `via_resource_id` (the IDP isn't modelled as an API resource in the
  consumer project).

If the IDP is external (e.g. Auth0, Cognito), use
`type: calls` with `note: "external"` and ensure `IDP.external: true`.

### Rule S4 — Eventing (`publishes` / `subscribes_to`)

For every channel `CH` in `API.yaml.events.channels`:

- Find the bus container `BUS` whose archetype is `message-bus`.
- If `CH.direction == out` (server publishes): for every container `P`
  with `CH.payload_schema_ref` mentioned in its `purpose` /
  feature-coverage: emit
  `{ from: P, to: BUS, type: publishes, via_channel_id: CH.channel_id }`.
- If `CH.direction == in` (server subscribes): for every container `S`
  whose archetype is `worker` / `stream-processor` AND whose features
  imply consuming `CH`: emit
  `{ from: S, to: BUS, type: subscribes_to, via_channel_id: CH.channel_id }`.

When `CH` has no payload_schema_ref, infer the producer/consumer from
the channel name (e.g. `users.created` → producer is the users-owning
backend; consumer is anyone with a `worker` archetype mentioning
"notifications" or "user lifecycle").

### Rule S5 — Pattern-driven scaffolding

- `architecture_pattern.pattern == event_driven` → every backend
  container has at least one `publishes` edge to the bus (else surface
  a warning).
- `architecture_pattern.pattern == microservices` AND no gateway →
  every consumer→producer edge is `calls`. Add no implicit gateway
  unless the user confirmed one in container_inventory.

### Rule S6 — Container-file roll-up (`all types`)

For every drilled `docs/ARCH__<A>.yaml` and every entry in its
`external_edges` targeting container `B` (or `B/<component>`): ensure a
system edge `{ from: A, to: B, type: <same> }` exists in
`ARCH.yaml.edges`. Derive the system edge's `via_*` from the container
edge's (via_resource_id / via_channel_id / via_entity carry over;
via_operation_id and via_unit stay container-level detail).

This is the rule the validator's cross-check #24 enforces: the system
edge table is the *roll-up* of the per-container tables. Container mode
discovers edges the system interview never saw (a sandbox writing an
artifact filesystem, a test agent calling a sibling's callable) — without
S6 they stay buried in one container file and `test`/`deploy`, which read
`ARCH.yaml.edges`, under-see the topology. S6 runs in system `-d` mode
AND at container-mode Phase 7 (see "Roll-up at container-mode write"
below).

## Container-level derivation rules

Scope: `internal_edges` (component ↔ component inside one container)
and `external_edges` (component → container or component → component
in another container) in `docs/ARCH__<container>.yaml`.

### Rule C1 — Controller → service (`calls`)

For every `controller` component `K` with `traces_api_resources: [R]`:
emit `{ from: K, to: <R>-service, type: calls }` if a service
component for `R` exists.

### Rule C2 — Service → repository (`calls`)

For every `service` component `S` with `traces_data_entities: [E]`:
emit `{ from: S, to: <E>-repository, type: calls }` if a repository
component exists.

### Rule C3 — Service → cache / blob clients (`reads` / `writes`)

If a `service` component traces an entity AND the container binds a
cache / blob store: emit edges from the service to the appropriate
`*-client` component for the access mode.

### Rule C4 — Service → publisher (`calls` internally, `publishes` externally)

If the service implements an API resource that has a corresponding
event channel (per Rule S4), emit:

- internal: `{ from: <r>-service, to: notification-publisher, type: calls }`.
- external: `{ from: notification-publisher, to: <bus-container>, type: publishes }`.

### Rule C5 — Subscriber components

For every `event_handler` component:

- internal: emit `{ from: <handler>, to: <service-it-delegates-to>, type: calls }`
  if such a service exists.
- external: emit `{ from: <handler>, to: <bus-container>, type: subscribes_to }`.

### Rule C6 — Middleware → next handler (`depends_on`)

`middleware` components in backend / web-frontend archetypes
typically form a chain (logger → auth → rate-limiter → router). Emit
`{ from: <upstream>, to: <downstream>, type: depends_on }` for each
adjacent pair. Confirm chain order with the user.

### Rule C7 — Frontend view → api_client (`calls`)

For every `view` component with `traces_ux_surfaces: [SF]` AND `SF`'s
surface has `interactions[].effect: call_api`:

- internal: `{ from: <surface>-view, to: api-client, type: calls }`.
- external: `{ from: api-client, to: <backend-container>/<resource>-controller, type: calls }`
  (or just `<backend-container>` if no controller component is defined).

## Endpoint resolution

Every derived edge must resolve to an **existing graph node**:

- System-level edges' endpoints are `container_id`s.
- Container-level internal_edges' endpoints are `component_id`s
  within this container.
- Container-level external_edges' `to` is `<container_id>` or
  `<container_id>/<component_id>`. The latter is preferred whenever
  the target container has been drilled-down via container mode.

If a derivation rule would produce an edge to a non-existent node, do
**one** of three things, in priority:

1. If the target node clearly *should* exist (e.g. you've inferred
   `users-service` but the user collapsed to flat components), retarget
   to the closest existing node (`users`).
2. If the target node is missing but its container is known, target
   the container (`<container_id>` with no slash).
3. Otherwise, **drop the edge** and add a warning to `arch_warnings`.

Never invent a node to support an edge.

## Presentation as a diff

The user sees the derived edges as a numbered diff (see
`interview-mechanics.md` — Synthesis themes). They can:

- `confirm all` — accept the whole derivation.
- `remove N` — drop a specific row.
- `retype N as <type>` — change the type.
- `add: <type> <to>` — add a row not derived.
- `EXIT` — save state and stop.

## Roll-up at container-mode write (Phase 7)

When container mode writes `docs/ARCH__<A>.yaml` with external_edges that
have no corresponding `ARCH.yaml.edges` row (Rule S6), it must not leave
them un-rolled-up — the validator blocks `complete` on that (#24). Present
the missing system edges as one confirmation diff ("These container edges
imply system edges ARCH.yaml doesn't have yet: …") and, on confirm, append
them to `ARCH.yaml.edges` and bump `ARCH.yaml.metadata.last_updated`. This
is one of the only mutations container mode may make to `ARCH.yaml`
(alongside `containers[<id>].file_path`) — appending derived system edges,
never editing or removing existing ones. If the user declines, drop or
retarget the container edge instead; do not write a file that fails #24.

## `-d` (re-derivation) mode

In `-d` mode the agent **skips the interview entirely** and runs only
edge derivation. The diff is built against the *currently stored*
edges in the target file. System-scope `-d` includes Rule S6: read every
drilled container file's `external_edges` and propose the missing system
rows as ADDs.

Three differences vs. interview-mode derivation:

1. No `KEEP` rows that haven't changed — show only ADD / REMOVE / RETYPE.
2. After the user's confirm, write a derivation report at
   `.claude/skills-state/sdlc-arch.derivation-report-<ISO8601>.yaml`:

   ```yaml
   generated_at: <iso>
   scope: system | container/<id>
   added:
     - { from: ..., to: ..., type: ..., evidence: "..." }
   removed:
     - { from: ..., to: ..., type: ... }
   retyped:
     - { from: ..., to: ..., old_type: ..., new_type: ..., evidence: "..." }
   skipped_no_evidence:
     - { from: ..., to: ..., type: ..., reason: "no upstream signal" }
   ```

3. Edge-only writes never change `metadata.status` — they only update
   `edges`/`internal_edges`/`external_edges` and `last_updated`.

## Common pitfalls

- **Over-eager `depends_on`** — most agents reach for `depends_on` when
  unsure. Prefer the more specific verb. Only emit `depends_on` for
  hard boot-time dependencies (config service, secrets manager, IDP
  before serving traffic).
- **Symmetric `reads` + `writes`** — emit two edges, not a fictitious
  `accesses` type.
- **Edges to/from external containers** — fine. External containers
  participate in the graph but lack `ARCH__<id>.yaml` files.
- **Cycles** — allowed. Cyclic dependencies are common (services that
  call each other for cross-cutting concerns). The validator does not
  reject cycles; only surfacing them in `arch_warnings` is appropriate
  when they look unintentional.
