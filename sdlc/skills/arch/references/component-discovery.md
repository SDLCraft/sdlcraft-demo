# Component discovery — container mode Phase 3

This file describes how to seed the **component inventory** for one
`docs/ARCH__<container>.yaml` from the upstream artifacts plus the
container's archetype (read from the parent `ARCH.yaml`). Read this on
entering Phase 3 of container mode.

## Source priority

### Pass 1 — Archetype-driven scaffold

Load the container's `archetype` from
`ARCH.yaml.containers[id].archetype`, then look up the archetype's
`suggested_components` in `container-taxonomy.yaml`. These are the
"plumbing" components most containers of this archetype have.

For example, `backend-api` typically gets:

- `routing` (`controller` archetype)
- `auth-middleware` (`middleware`)
- `repository-layer` (`repository`)
- `use-cases` (`service`)
- `validators` (`validator`)
- `serializers` (`serializer`)

These are `⚠ inferred` and need user confirmation in Phase 3.

### Pass 2 — One component per API resource

For each `resource_id` in `ARCH.yaml.containers[id].owns_api_resources`,
propose **one or two** components:

- **Default (single)**: `<resource_id>` component — `service` archetype.
  The component traces back to `API__<resource_id>.yaml`.
- **Split (controller + service + repository)**: three components per
  resource, named `<resource>-controller`, `<resource>-service`,
  `<resource>-repository`. Use this split only when the user explicitly
  prefers a layered style (Phase 3 prompt asks).

Each component's `traces_api_resources` is set to the resource_id.

### Pass 3 — One component per UX surface (frontend only)

For each `surface_id` in `ARCH.yaml.containers[id].owns_ux_surfaces`,
propose one component named `<surface_id>-view` with archetype `view`.
Trace back to `UX__<surface_id>.yaml` via `traces_ux_surfaces`.

For multi-surface flows (`UX.navigation_model.top_level_nodes` groups
surfaces under a parent), propose an additional `<top-level>-router`
component with archetype `controller`.

### Pass 3b — Integration clients (from PRD INT ids)

For each `INT-NNN` in the container's `realizes_integrations` (or an
INT the container's FRs clearly depend on), propose an `api_client`
component owning the provider adapter, with `int_refs: [INT-NNN]`.
Component-level `int_refs` and container-level `realizes_integrations`
together satisfy the INT coverage gate (trace-or-defer, blocking at
arch_version >= 2.0). The provider itself is an `external: true`
container carrying `external_contract` (see container-discovery.md).

### Pass 4 — Persistence bindings → client components

For each store_id in `ARCH.yaml.containers[id].persistence`, propose
a client component:

| Store kind                | Component name           | Archetype     |
|---------------------------|--------------------------|---------------|
| primary database          | `<store>-client`         | `repository`  |
| cache / redis             | `<store>-client`         | `cache_client`|
| blob store / S3           | `<store>-client`         | `blob_client` |
| search index              | `<store>-client`         | `repository`  |
| message bus (publisher)   | `<bus>-publisher`        | `service`     |
| message bus (subscriber)  | `<event-id>-handler`     | `event_handler`|

The publish vs subscribe split comes from the system-level
`cross_container_edges`: if the container has a `publishes` edge to
the bus, add a publisher; if it has a `subscribes_to` edge, add a
handler per event channel.

### Pass 5 — Cross-cutting components

Always-on candidates regardless of archetype:

- `config-loader` (`service`) — every non-trivial container needs config
  parsing. Propose, but allow user to skip if config is trivial.
- `observability-bootstrap` (`service`) — OTel / metrics / logging init.
  Only propose if `observability.metrics` or `traces` is non-null in the
  Phase 6 deployment theme.
- `error-handler` (`middleware`) — for backend / web-frontend archetypes.

These are `⚠ inferred` — user confirms.

### Pass 6 — Build-time & shipped deliverables

Passes 1–5 only see **runtime callables** — API resources, UX surfaces,
store bindings, edges. A whole deliverable class is invisible to them:
things the project *ships or builds* but never *executes as a service* —
and an FR that names one still needs a component, or downstream `task`
can never schedule building it. Sweep for them explicitly:

1. **Scan the FR texts** of every requirement in this container's
   `implements_requirements` (plus `PRD.conventions` and
   `technical_constraints`) for concrete repo paths and deliverable nouns:
   `tools/…`, `templates/…`, schema/model layers, shipped validators,
   prompt packs, question inventories, migration scripts, generated docs.
2. **Propose one component per deliverable class**, using the build-time
   archetypes:

   | Deliverable class                                  | Archetype       | work_units are …                          |
   |----------------------------------------------------|-----------------|--------------------------------------------|
   | typed schema / domain-model layer shipped as code  | `schema_model`  | the model classes / load-dump callables    |
   | repo tools: validators, generators, migrations     | `dev_tool`      | each tool's entry point (a real callable)  |
   | shipped content: templates, prompts, question packs, archetype packs | `content_asset` | AUTHORING units — name = the authoring action or pack, `output` = the shipped path(s) |

3. **Give each a `code_location` that covers every FR-named path** — the
   validator's advisory cross-check #25 flags any path named in a claimed
   FR that no component's `code_location` covers. #25 keys on **backticked
   tokens with path shape** (a trailing `/` or a file extension): it scans
   inline code like `` `tools/validate.py` `` or `` `templates/` `` and ignores
   bare prose slashes AND backticked non-paths (`and/or`, `PyPI/npm`, ID-lists
   like `FR-046/047`, enum listings like `pass/fail`). When your discovery
   sweep here turns up a genuine deliverable path that the FR left as bare
   prose, write it back into the FR text as inline code so #25 can verify its
   coverage (see prd's FR-authoring note). The converse case is a path the
   running system WRITES (a packaged bundle under `dist/`, sidecars under
   `assets/`, a scaffolded app under an output root): no component owns it
   because nothing ships it. `output_locations` is a **system-mode field —
   container mode may not write it** (`references/merge-validate.md`'s mode
   boundary). Leave the advisory standing; the next `/sdlc:arch --system` or
   `--reconcile` run is where it gets asked and recorded (SKILL.md → "system
   mode's update flow, #25 rows"). There is no interview question for it
   today — hand-editing `docs/ARCH.yaml` also works, but never from here.
4. **Content assets need authoring units.** A `content_asset` component's
   work_units are not code callables; they are the authoring deliverables
   (`author_review_prompt_pack`, `write_cli_question_inventory`), each with
   `output:` naming the shipped path(s). If the container instead derives
   its content mechanically, declare that rule in `work_units_waiver`
   (e.g. "one authoring task per template file under templates/ — derived
   by task, not enumerated here") so the derivation rule is explicit
   rather than absent. Word the rule precisely: downstream `task` **expands
   it** into concrete per-file authoring tasks (it is a promise, not a
   waiver of the work — see task's `references/coverage-and-defer.md`), so
   the rule must name the directory/tree the files live in.

These are `⚠ inferred` — user confirms. Tag `source: deliverable-sweep`.

## Inferred vs found

- `✓ found` — direct evidence (API resource, UX surface, persistence
  binding).
- `⚠ inferred` — derived from archetype's `suggested_components` (Pass 1)
  or cross-cutting heuristics (Pass 5).

The hallucination guard applies: each `⚠ inferred` component is
confirmed individually.

## Presentation

```
Drafted from upstream + archetype (backend-api):

  ✓ users-controller      (controller)  traces: users
  ✓ users-service         (service)     traces: users
  ✓ users-repository      (repository)  traces: users, primary-postgres
  ✓ projects-controller   (controller)  traces: projects
  ✓ projects-service      (service)     traces: projects
  ✓ projects-repository   (repository)  traces: projects, primary-postgres
  ⚠ auth-middleware       (middleware)  — from backend-api archetype
  ⚠ error-handler         (middleware)  — from backend-api archetype
  ⚠ config-loader         (service)     — cross-cutting
  ⚠ notification-publisher (service)    — from publishes edge in ARCH.yaml

Add, rename, drop, or collapse anything? (e.g. "collapse users-controller +
users-service + users-repository into one `users` component")
```

The user controls layering depth (controller-service-repository vs flat).
Default to the upstream-suggested style, but always offer a one-line
"collapse" shortcut.

## Persisting

Persist the confirmed list to
`state.sessions[container|<id>].defined_components`:

```yaml
- component_id: <kebab>
  archetype: <enum>
  status: proposed | draft | confirmed | dropped
  source: api-resource | ux-surface | archetype-scaffold | persistence-binding | cross-cutting | user-added
  traces_api_resources: [...]
  traces_ux_surfaces: [...]
  traces_data_entities: [...]
```

After Phase 3 confirmation, Phase 6's `component_inventory` and
`per_component_deepdive` themes walk the confirmed list per-item
(critical state machines). During `per_component_deepdive`, set each
component's `implements_requirements` to the FR-NNN it realizes — this
MUST be a subset of the parent container's `implements_requirements`
(the validator enforces containment), so draw only from the features the
container itself claims.

## Deriving code_location

`code_location` is the **component → code-module seam**: the repo-relative
directory(ies) (and optionally an illustrative file) where this component's
source lives. It is filled during `per_component_deepdive` (an `importance:
high` mini-section — the agent drafts, the user approves). It is the single
highest-leverage field for autonomous downstream work: the `task` skill grounds
every task's `target_files` in the owning component's `code_location`, so if it's
vague or absent the codegen agent has to *invent* each file's placement — the
most common way a generated repo drifts from its architecture.

**Draft it from archetype + the container's source layout.** The container's
`tech_stack` (language + framework) and its conventional import layering tell you
where each archetype's code belongs. Map the component's archetype to a directory
in that layout:

| Archetype (component)                | Typical home (layered backend)     | Notes |
|--------------------------------------|------------------------------------|-------|
| `controller`                         | `src/<area>/` or `controllers/`    | one per API resource the controller owns |
| `service` / `use_case`               | `services/` / `core/`              | the bulk of behaviour |
| `repository`                         | `repositories/` / `data/`          | one per entity/store |
| `middleware` / `error_handler`       | `middleware/`                      | |
| `view`                               | `src/views/` / `app/<route>/`      | frontend; map to the surface's route |
| `api_client`                         | `clients/` / `api/`                | the SDK for a called container |
| `event_handler` / `background_worker`| `workers/` / `handlers/`           | |
| `cache_client` / `blob_client`       | `clients/`                         | |
| `config_loader` / `serializer`       | `config/` / `serialization/`       | plumbing — code_location optional |

These are *heuristics keyed to the conventional layout for the chosen stack* —
not a fixed list. Read the project's own layering signal first (a `README`, an
`architecture.*` doc, an existing `src/` tree, or a `CLAUDE.md` layering rule the
project ships) and prefer it over the table. Honour the **directory-firm,
file-illustrative** rule: a directory entry is a contract the executor must
respect; a file path is a hint it may rename.

**A component may span layers** — e.g. a runtime component that owns both its
node module and the schema it emits lists both dirs. List each directory rather
than picking one. **Reconcile with edges:** a component's `code_location` plus
the internal-edge graph is what makes every edge mechanically checkable against
the project's import layering — see `references/edge-derivation.md` → "Edges vs
imports".

**Bind the concrete MVP variant of a parameterized placement.** If a placement
is templated over a project-defined choice — `.../<stack>/...`, `.../<lang>/...` —
do **not** leave the placeholder in `code_location`: it is resolvable from prose
but forces codegen to re-derive the binding. List the **resolved MVP-variant
path** (the concrete path for the chosen MVP stack) and model any further
variants as their own components/work_units, or defer them with a `WRN-NNN`
note. The arch validator warns (#20) on a `<...>` token in a `code_location`
entry.

When you persist a drafted component's placement to state, carry it on the
`defined_components` entry (`code_location: [...]`) so resume doesn't re-draft it.

## Deriving work_units

`work_units` is the **component → code seam**: the named method/function-level
**callables** the component exposes (C4 interface level). It is filled during
`per_component_deepdive` (an `importance: high` mini-section — the agent drafts the
full list, the user approves or edits). It is the single field that makes
**atomic, method-level task breakdown** possible downstream: the `task` skill
slices **exactly one implementation task per work_unit** (its `target_symbol` =
the work_unit `name`), so a component that declares no work_units yields no atomic
implementation task. The arch validator emits a non-blocking WARNING for a
non-trivial component with traces but no work_units (cross-check #21).

**Enumerate the contract surface, not every private helper.** A work_unit is a
PUBLIC / contract-bearing callable — one that realizes a traced contract (an API
operation, an entity's persistence, a surface's render) or sits on an
internal/external edge (something another component calls). A private helper that
no contract or edge names is an implementation detail *of* some work_unit, not a
work_unit of its own. This keeps the list at the right altitude: one codegen task
per callable another part of the system depends on.

**Never ask cold — draft from the component's archetype + its traces, then let
the user trim:**

| Component archetype | Draft one work_unit per … | Pre-fill |
|---|---|---|
| `controller` / `bff` | owned API operation | `traces_api_operation` = the `operation_id`; `implements_requirements` from the endpoint's feature; `name` = the handler (e.g. `createTask`) |
| `repository` / `cache_client` / `blob_client` | CRUD verb × traced entity (create/get/list/update/delete) | `touches_entities` = the entity |
| `service` / `use_case` / `background_worker` | behaviour implied by a responsibility, an `acceptance_criterion`, or an FR it implements | `implements_requirements` ⊆ the component's; `satisfies_acceptance` = the criterion |
| `view` | user interaction / render path | — |
| `api_client` | called remote operation | `traces_api_operation` |
| `validator` / `serializer` | the one transform it performs (often a single unit, or skip) | — |
| `middleware` / `scheduler` / `event_handler` | the wrap / tick / handle entry point | — |
| `schema_model` | model class / load-dump callable per shipped schema | `touches_entities` = the entities it types |
| `dev_tool` | tool entry point (each shipped validator/generator/migration) | `implements_requirements` from the FR that names it |
| `command-dispatcher` / single-file CLI/shell | the dispatch root (`kind: entrypoint`) + one unit per run-mode branch | `inputs` = argv/env; `output` = exit code / dispatched result; `raises` = usage/exit conditions |
| `content_asset` | authoring unit per shipped pack/asset (`output:` = the shipped path) | `implements_requirements`; or a task-derivation rule in `work_units_waiver` |
| `config_loader` / `observability_bootstrap` / `error_handler` | usually **none** (plumbing) | — |

Each work_unit carries:

- `name` — the callable (method / function / `Class.method`), **unique within its
  owning component**. work_units are addressed as `(component, name)` — there is
  no id family. This name is the stable handle `task` references as a
  `target_symbol`; it IS the callable, so renaming the callable renames it.
- `summary` (one line) — required.
- `kind` (optional; default `callable`) — the **deliverable class**, for
  components whose units aren't runtime callables (demo FR-013 v1.30):
  - `callable` — the normal case; omit the field.
  - `module` — a source module whose **definition set is the interface** (e.g. a
    Pydantic schemas file the rest of the code imports). `name` names the module
    deliverable; one unit per shipped module.
  - `content` — a shipped content file (prompt pack, question inventory,
    template). Typical for `content_asset` components.
  - `tooling` — a repo tool/validator/migration script. Typical for `dev_tool`
    components.
  - `entrypoint` — the **composition/dispatch root** of a single-file or
    multi-run-mode deliverable (a CLI/shell entrypoint, a `main`): it owns
    arg/mode parsing, step-sequencing, setup/teardown and exit semantics. It is
    **callable-dialect** (argv/env in, exit code out), so #23 DECLARE applies:
    `inputs` = argv/env, `output` = the exit code or dispatched result, `raises`
    = usage/exit conditions.
  The same 1:1 unit→task rule applies to every kind (downstream `task` copies it
  onto the task's `unit_kind`; codegen switches its rendering mode on it).
  Non-callable kinds (`module`/`content`/`tooling`) deliver a **file**, so the
  #23 interface-contract check below does not apply to them — their contract is
  the deliverable itself.

**Single-file, multi-branch deliverable → emit one `entrypoint` unit.** When a
component's `code_location` is **one executable file** with more than one
run-mode branch (a shell/CLI entrypoint that dispatches on a mode selector),
decompose the per-mode behaviours into their own work_units **AND** emit one
`entrypoint` unit that owns the top-level dispatch + step-sequencing + setup —
never leave the file's control flow unowned. Without it, the 1:1 unit→task rule
produces one task per mode and *no* task whose deliverable is the orchestrator,
so the generated file has no owner for its `main`/arg-parse/dispatch scaffold.
The arch validator warns (#21) on a single-file component with ≥2 units and no
`entrypoint` — but only in an **executable-deliverable container** (archetype
`cli` / `other`) whose units aren't API-routed. A framework-routed
service/controller with several handlers in one file is *not* flagged: its web
framework owns dispatch, so it needs no `entrypoint` unit.

**A work_unit must have code to emit — an externally-enforced policy is not
one.** If a "responsibility" is a constraint honored **externally** (enforced by
the platform, runtime, or deployment — not by code in this component) with
nothing to build, do **not** model it as a work_unit: a unit with `output:
"None"`, no `inputs`, and no `raises` becomes a downstream codegen task with
nothing to emit. Record it instead as a container/component `security_concern`
(with a `mitigation`) and/or an `acceptance_criterion`, and let `test` cover it.
The arch validator warns (#23) on the empty-callable shape.
- Optional traces: `traces_api_operation` (⊆ API operation_ids),
  `implements_requirements` (FR/NFR ⊆ the owning component's),
  `touches_entities` (⊆ the component's `traces_data_entities`),
  `satisfies_acceptance` (the component criterion it fulfils).
- Optional `owns_callables` — additional symbols this unit's build task owns
  beyond `name` (private helpers it also writes). Downstream `task` copies the
  list onto the task's `owns_symbols`, so it widens the codegen ownership
  boundary. Keep each symbol in exactly ONE unit's list — a callable claimed
  by two units in one container draws a warning (#29): two build tasks would
  both own the same function.
- The **interface contract**, DEFER-OR-DECLARE (`inputs`, `output`, `raises`, and
  an optional concrete `signature`) — **enforced by cross-check #23**:
  - **DEFER** is allowed only when the unit sets `traces_api_operation` — the
    API operation's request/response schema in `API__*.yaml` *is* the frozen
    interface, so `inputs`/`output`/`raises` may be omitted.
  - **DECLARE** applies to every other unit (service/use_case methods,
    repository CRUD, authoring units): draft **all three** of `inputs`,
    `output`, `raises` **at drafting time**, in the same pass that fills the
    trace fields. **Pin where each input type comes from**: an input naming a
    type that no sibling unit produces and that is not a DATA entity leaves
    codegen to invent it — the contract-seam warning (#28) flags exactly that.
    Either reference an entity/enum, a sibling's output type, or say
    "caller-supplied" in the input text. The same seam discipline applies to
    `raises` on a called unit: when a family contract covers a unit's
    inputs/output but declares no `raises`, a caller edge pinned to that unit
    has no error contract on either side (#28 warns). Do not emit trace-only units (`implements_requirements` /
    `touches_entities` / `satisfies_acceptance` filled, contract empty) — that
    is exactly the divergence that leaves every downstream atomic task
    re-guessing the signature. Explicit empties are legitimate declarations:
    `inputs: []` (no args), `raises: []` (nothing beyond language defaults),
    `output: "None"` (no return). Draft `inputs`/`output` from the entity
    types the unit touches and the responsibility text; draft `raises` from
    the component's failure_modes and validation rules.
  - Fill `signature` only when the signature itself is the contract (a public
    library API); otherwise codegen renders it from `inputs`/`output` + the
    tech stack.
  - **FAMILY** (opt-in for ANY project with uniform unit families; the
    meta-corpus dialect merely required it first) — declare a container-level
    `work_unit_family_contracts` list: one shared `inputs`/`output`/`raises`
    contract per uniform unit family (gate units, stage-node bodies, CLI verb
    handlers, sub-agent runners), keyed by `member_components` /
    `member_name_globs` / `member_archetypes`. A terse family member inherits
    its family's contract and may omit its own; a member OVERRIDES by declaring
    its own. Cross-check #23 recognizes this only when the block is present — a
    container that declares no such block keeps the strict per-unit DECLARE
    rule above.

**When to fold units into a family.** When **≥ 3 units share one contract
shape** (per-stage bodies, per-clause gates, per-command handlers, per-schema
loaders), declare ONE `work_unit_family_contracts` entry — family name, member
selector, shared inputs/output/raises — instead of N copies. Scale proof: the
meta-corpus put 112 of its 214 units on 16 families. Do NOT instead stamp
trivial empty contracts across the members to satisfy #23 — a component where
≥ 3 callable units are ≥ 80% all-empty (`inputs: []`, `output: "None"`,
`raises: []`) trips the emptiness advisory; the family mechanism is the honest
way to say "one decided shape, many members".

**Aggregator/dispatcher contract pattern (PLAN2-D3).** A unit that dispatches
over sibling units — a `run_stage_quality_gate` fanning out to per-clause
gates, a command router, the `entrypoint` unit dispatching run-mode branches
(the entrypoint IS the typical dispatcher) — declares its **dispatch inventory
in its contract `inputs`** (the list of callees it fans out to) and NEVER
takes graph self-edges to them. The inventory is the contract; the edges stay
lean (the task skill's granularity invariant (b) forbids absorber-style edge
fan-in for the same reason).

**Work_unit-completeness check (before closing the component).** Reflect on the
drafted units against the component's own signals: does every owned API
`operation_id` map to a work_unit? every `acceptance_criterion`? every entity the
component reads/writes (a CRUD unit)? **every FR-NNN in the component's
`implements_requirements`?** Cross-check #22 holds you to the last one: each FR
the component claims must appear in at least one of its `work_units[].
implements_requirements`, or `task` gets no atomic task that actually builds the
feature. Add the missing ones. Honour the anti-padding rule — a `validator` with
one transform has one work_unit, not five, and a private helper is not a
work_unit.

**Contract lint (also before closing the component).** Walk the drafted units
once more, contract-only: every unit without `traces_api_operation` must have
`inputs`, `output`, AND `raises` present (explicit empties fine). A DECLARE-case
unit with an empty contract is a blocker (#23), not a style choice — fix it in
the deep-dive while the component's context is loaded, not later from the
validator's error list.

**Emit block-style; normalize flow-style on update.** Write each work_unit
block-style — one field per line under a `- name:` entry — NOT as a flow-style
one-liner mapping (`- {name: x, summary: y}`). Both parse identically, but
block-style is diff-reviewable and robust to any line-oriented tooling. On an
update flow, rewrite any existing flow-style entries you touch as block-style.
(Downstream `task` counts work_units with a real YAML parse via
`count_work_units.py`, never a grep — so the style never changes the count; the
rule is purely about reviewability.)

**Non-trivial components block `complete` without work_units — or a waiver.** A
component whose archetype is outside the plumbing set (`config_loader` /
`serializer` / `observability_bootstrap` / `error_handler`) AND which carries
`implements_requirements` or a traced contract must declare `work_units`. If it
genuinely exposes no standalone callable (its behaviour is realized purely by
wiring — a decorator, a composition root), record `work_units: []` plus a
`work_units_waiver: <one-sentence reason>`. The waiver also waives #22 for that
component (use it when a specific FR is realized by wiring, not a callable).
Without units and without a waiver, cross-check #21 blocks `complete`: this is
the guard that stopped a container being "complete" while a third of its
components seeded no downstream implementation task.

Persist the confirmed units to the `defined_components` entry
(`work_units: [...]`) so resume doesn't re-draft them. (No id counter — work_units
are name-addressed.)

## Scope-completeness sweep (synthesis theme)

`component_inventory` is a `critical synthesis: true` theme. After the
per-item loop closes, run a dynamic scope-completeness sweep (canonical
spec: `${CLAUDE_SKILL_DIR}/../prd/references/importance-flows.md`). Reflect on:

1. **The draft component list** — are layers missing (controller without
   a service, repository without a client)? Is one component doing two
   jobs?
2. **Every upstream signal the container owns**:
   - **owned API resources / operations** — does every owned
     `resource_id` (and key `operation_id`) have a component that
     implements it?
   - **owned UX surfaces** — does every owned `surface_id` have a view
     component?
   - **persistence bindings** — does every store the container binds to
     have a client/repository component?
   - **the container's `implements_requirements` (FR-NNN)** — is every
     feature the container claims realized by at least one component?
     An FR with no component is a missing component.
   - **the container's `subscribes_to` / `publishes` edges** (from
     `ARCH.yaml`) — each needs an event-handler / publisher component.
3. **Archetype heuristics** — cross-cutting plumbing (config-loader,
   error-handler, observability-bootstrap) that's easy to forget.
4. **Build-time deliverables (Pass 6 signals)** — re-scan the claimed FR
   texts for concrete paths and shipped-artifact nouns (schema layer,
   `tools/`, `templates/`, prompt/question/archetype packs): does every
   FR-named path fall inside some component's `code_location`? Does every
   content deliverable have authoring work_units or an explicit
   task-derivation rule? Runtime-only sweeps miss this class entirely —
   it is the reason cross-check #25 exists. (Your discovery reads all prose;
   #25 only auto-flags paths written as inline code — backtick a genuine
   deliverable path in the FR text so the validator can enforce its coverage.)

Surface concrete missed **candidate components** via **one multi-select
`AskUserQuestion`**. Caps: at most **2 sweep passes**; defer leftovers
to a `WRN-NNN` `arch_warnings` entry; honour the **anti-padding rule**.

## Edge cases

- **External containers** (`external: true` in ARCH.yaml) — these never
  enter container mode. If invoked on an external container, abort with
  a message: "External container `<id>`. We model the API surface in
  ARCH.yaml but don't author internal components for external services."
- **Data-store containers** (e.g. `primary-postgres`) — these are also
  external in practice. Same abort message.
- **No upstream evidence** — if `owns_api_resources`, `owns_ux_surfaces`,
  and `persistence` are all empty for this container, fall back to the
  archetype scaffold only. Warn the user that the container is
  under-specified.
