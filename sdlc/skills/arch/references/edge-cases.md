# Edge cases — sdlc-arch

Read this when the happy path doesn't fit.

## Missing or draft upstream artifacts

The four upstream artifacts (`PRD.yaml`, `UX.yaml`, `DATA-MODEL.yaml`,
`API.yaml`) MUST all exist with `metadata.status: complete` before the
skill runs. Behaviour:

- **Any missing** → stop and print which file is missing + which skill
  to run.
- **Any with `status: draft`** → stop and print
  "Run `/sdlc:<skill>` to complete the artifact before invoking arch."
- **Any failing its own validator** → stop. Print the validator's
  stderr verbatim so the user sees the field-level errors — **unless** the
  project accepted that exact deviance:
  `python "${CLAUDE_SKILL_DIR}/../repair/doctor.py" --docs-dir docs --artifact docs/<that file>`
  reports every failing check as `accepted (N, unchanged)`; then proceed
  (never `--quick`; rule: `sdlc/skills/repair/references/accepted-deviance.md`).

The skill never partially-runs against a partially-validated upstream
chain (an accepted deviance is not partial validation: its count is pinned
and re-checked on every run). The risk of polluting a downstream artifact
with stale assumptions is too high.

## When an upstream changes after ARCH exists (re-invocation, §7)

The user re-invokes `/sdlc:arch` (or `/sdlc:arch <container>`) after the output
already exists, because `docs/PRD.yaml`, `docs/UX.yaml`,
`docs/DATA-MODEL.yaml`, or `docs/API.yaml` changed in between. Phase 2's
**upstream-change detection** drives the reconciliation per the cross-skill §7
contract (`sdlc/skills/ux/references/upstream-reconciliation.md`):

1. Read the active output's `metadata.upstream_provenance`. System mode reads
   `ARCH.yaml`'s; container mode reads the specific `ARCH__<container>.yaml`'s —
   a container drilled long ago carries its own, older baseline, so it
   reconciles against exactly what *it* was built on.
2. For each upstream, compare the recorded `sha256` to its current hash (from
   `docs/INDEX.yaml.generated_from[<file>]`, else the `docs_index.py --hash` text-level hash (sha256 of the file read as UTF-8 text, first 16 hex — never raw bytes)).
3. For every changed upstream, classify added / removed / modified ids and run
   the **consolidated delta-review before the theme interview**. Concretely:
   new API resources / UX surfaces / DATA stores / PRD FRs surface as
   coverage-driven additions (a new container, or new `owns_*` /
   `implements_requirements` on an existing one); removed ids are the stale-ref
   branch (never silently dropped); modified bodies trigger a re-review of the
   traces that point at them.
4. Refresh `upstream_provenance` on write and add a `changelog` line naming
   what moved.

This is distinct from `-d` (edge re-derivation) mode: `-d` re-derives the typed
edge graph from current upstream without an interview, and is the right tool
when *only* the edge-bearing relationships changed. A full re-invocation
delta-review is for added / removed / modified upstream *items*.

## Invalid `<container>` argument in container mode

User typed `/sdlc:arch backennd-api`. The agent:

1. Lists all valid `container_id`s from `ARCH.yaml.containers[]`.
2. If exactly one is a Levenshtein distance ≤ 2 from the typed string,
   offer it as a "did you mean?" suggestion.
3. Otherwise abort.

Do NOT silently create the container. Container creation happens in
system mode only.

## Container in `ARCH.yaml` but no `ARCH__<container>.yaml`

This is the normal state right after system-mode completion: the user
has defined the inventory but not drilled down. Validator does not flag
it — `file_path` is optional in `ARCH.yaml.containers[]`. Downstream
test/task/deploy skills will refuse to operate on a container without
its yaml.

The guided way to work through these is plain `/sdlc:arch`, which resolves to
the next undrilled drillable container (skipping external / storage-only ones),
confirms the target, and runs its container interview — repeat until it reports
all containers specified. See SKILL.md → "Invocation dispatch" → the
auto-advance resolver.

## External / data-store containers (cannot be drilled-down)

If the user invokes `/sdlc:arch <id>` where `id` is an external
container (`external: true`) or a data-store archetype
(`primary-database`, `cache`, `blob-store`, etc.), abort with:

> "Container `<id>` is `<archetype>` (`external: true` / data store).
> We model its API surface in ARCH.yaml but don't author internal
> components for external or storage-only containers. If this is wrong,
> set `external: false` in ARCH.yaml.containers[id] first."

## Conflicting scan signals

Examples:

- `UX.surface_family: web` but the team has no web container in
  PRD.technical_constraints.
- `PRD.technical_constraints.runtime_platform` holds only `cli` but `API.api_kind:
  rest` (rare).
- Two pre-fill sources disagree on a value.

For all of these: surface the conflict to the user with both sources
quoted; **never auto-resolve**. Use the literal phrasing:

> "Conflicting signals for `<field>`:
>   - `<source_a>` says `<value_a>`
>   - `<source_b>` says `<value_b>`
> Which should win?"

Options: `<value_a>` / `<value_b>` / **"An upstream is wrong — record a
finding for /sdlc:repair"**. The third option is the CLAUDE.md §13 route:
two upstream artifacts contradicting each other is a spec defect the arch
stage cannot fix. On that pick, still ask which value to *proceed* with,
then append `{noted_at, kind_guess: contract_contradiction, file, summary,
evidence}` to the state file's `finding_notes: []` in the next state write
and continue the interview — **never stop mid-run to record**; Phase 8
drains the list through
`python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add` (skip silently
when the helper is absent).

Persist the user's choice with `confidence: confirmed`.

## Container rename mid-session

User decides `backend-api` should be called `core-api`. Behavior:

1. Pause the active sub-session.
2. Rename the entry in `defined_containers`.
3. Update `containers[<id>].container_id` and `file_path` if set.
4. If `docs/ARCH__backend-api.yaml` already exists: rename to
   `docs/ARCH__core-api.yaml` (atomic move, fall back to copy+delete if
   atomic fails).
5. Rewrite every edge in `ARCH.yaml` whose `from` / `to` was the old
   name.
6. Walk every existing `docs/ARCH__*.yaml` and rewrite
   `external_edges[].to` mentions of the old name.
7. Update the state file's `sessions` map key
   (`"container|backend-api"` → `"container|core-api"`).
8. Continue the session.

Surface a confirmation summary before doing steps 4–7. The user gets
one "are you sure?" to back out.

## Component split across containers

User says: "Actually, the `notification-publisher` should live in the
`worker` container, not `backend-api`." Behaviour:

1. Pause the active sub-session.
2. If the worker container's yaml doesn't yet exist, just add a note
   to the system-level state and continue. The user will create the
   worker yaml in a future `/sdlc:arch worker` invocation.
3. If the worker yaml exists, write the component there in the next
   `/sdlc:arch worker` invocation. Don't auto-cross-write — container
   mode never writes to another container's file.

In both cases, remove the component from the active container's
`components[]` and rewrite affected `internal_edges` /
`external_edges`.

## Edge to a non-existent node

Two cases:

1. **Target node clearly should exist** (e.g. the user collapsed
   `users-service` into `users` but the edge still says
   `to: users-service`): retarget to the closest existing node and
   warn.
2. **Target node has no upstream evidence**: drop the edge, append a
   warning to `arch_warnings`:
   `"Dropped edge from <a> to <b> (<type>): target not in graph"`.

Never invent a node to support an edge.

## Mid-interview abort with partial state

User types `EXIT` mid-theme. Behaviour:

1. Set the sub-session's `status: aborted`.
2. Write `partial_answers` to state.
3. Write `docs/ARCH.yaml` or `docs/ARCH__<container>.yaml` if the
   theme being aborted had committed answers — keep their values, do
   NOT roll back. Set top-level `metadata.status: draft`.
4. Confirm to user: "Saved at `<file>`. Resume with `/sdlc:arch
   <args>` later."

## Mid-interview transport / pattern change

User decides mid-session that the architecture pattern should change.
Behaviour:

1. Acknowledge the change.
2. Revisit any pattern-dependent answers (e.g. `cross_container_edges`
   re-derivation). Pre-fill the new derivation; ask the user to
   re-confirm.
3. Update `pattern_confidence: confirmed`.
4. Continue.

## Write-permission errors

If a write to `docs/ARCH.yaml` / `docs/ARCH__*.yaml` / state file
fails:

1. Capture the error.
2. Report which file failed and the OS error.
3. Save the in-memory partial state to a fallback location in `/tmp`
   if possible, and tell the user where.
4. Stop. Do not retry without user input.

## Very large systems

Defined as ≥ 12 containers or ≥ 25 components in any single container.

- For very large container counts: split the system-mode container
  inventory into chunks of 6 per `AskUserQuestion` batch. Confirm chunk
  by chunk, then proceed to per-container drill-downs.
- For very large component counts inside one container: prompt the
  user to split the container before proceeding. Suggest splitting
  along bounded contexts.

## Monorepo mode — DEFERRED to a future major version

The upstream `prd`/`ux`/`data`/`api` skills support multi-product
(monorepo) mode via `metadata.monorepo: true` + a `products:` shape.
`sdlc-arch` does NOT yet implement that shape — the schemas, validator,
and interview all assume single-product.

**On invocation against a monorepo PRD** (`PRD.metadata.monorepo: true`),
the skill:

1. Stops at Phase 2 (input scan).
2. Prints a warning:

   > "sdlc-arch v1.0 does not support multi-product (monorepo) mode.
   > Author one `docs/ARCH.yaml` (and one set of
   > `docs/ARCH__<container>.yaml`) per product manually, or wait for
   > sdlc-arch v2.0. See sdlc/skills/arch/references/edge-cases.md."

3. Asks the user whether they want to proceed *anyway* against the
   monorepo PRD (treating one product as "the" product) or abort.

If the user proceeds, document in `arch_warnings`:

```yaml
arch_warnings:
  - "Authored against monorepo PRD (PRD.metadata.monorepo: true) in
     single-product mode — multi-product support arrives in v2.0."
```

**Planned v2.0 shape (informational, not implemented):**

- `docs/ARCH.yaml` would carry a top-level `products:` sub-mapping
  mirroring upstream skills, with each product holding its own
  `containers` / `architecture_pattern` / `edges`.
- Per-container files would be named
  `docs/ARCH__<product>__<container>.yaml`.
- Validator would gain a multi-product path.

Do not author content against that shape until the schemas and
validator are updated — current validation will reject it.

## Validator missing dependencies

If the validator exits 3 (pydantic/pyyaml not installed):

1. Surface the install hint to the user.
2. Offer to skip validation for this run only (treat as `[DRAFT]`).
3. Refuse to set `metadata.status: complete` without validation.
