# Merge, validate, close — sdlc-arch

Read this on entering Phase 7 of either mode and at the end of Phase 7-D
(`-d` mode).

## Merge behaviour (Phase 7)

### System mode → `docs/ARCH.yaml`

If the file already exists (update flow):

1. Load it as a baseline.
2. For every confirmed answer in the active session: overwrite the
   corresponding key in the baseline.
3. For new keys (new containers / new edges added in this session):
   append.
4. For keys the session would *remove* (e.g. a dropped container or
   edge): ask the user to confirm before deleting. Default: keep.
5. **Preserve unrelated top-level keys** the agent doesn't recognize.
   `arch_warnings` is the only key the agent freely rewrites.
6. Surface conflicts (user-edited yaml vs. state file) — never
   auto-resolve. Ask which to keep.

Container mode is forbidden from touching `docs/ARCH.yaml` *except*:

- May set `containers[<id>].file_path` to point at the new
  `docs/ARCH__<container>.yaml` if the file was just created.
- May update top-level `metadata.last_updated`.
- May **append** system edges that this container's `external_edges` imply
  and `ARCH.yaml.edges` lacks (roll-up rule S6 — presented as a
  confirmation diff first; required, because cross-check #24 blocks
  `complete` while a container-sourced edge has no system row). Append
  only — never edit or remove existing edges.

No other field in `ARCH.yaml` may be modified by container mode.

### Derived-count refresh (every write, every mode)

Structured data is the source of truth; prose that *restates* it goes
stale silently. The historical failure: propagation passes updated
`containers[]`/`edges`/`work_units` across several version bumps while
header comments and `overview`/`notes` sentences kept saying "12
containers", "43 edges", "15 commands" from three versions ago —
self-describing text that now lies to every downstream reader.

Two rules, applied on **every** write (interview merge, `-d` edge write,
backfill/propagation passes):

1. **Don't write derived counts into prose.** New `overview` / `purpose` /
   `notes` text and YAML header comments must not restate counts of
   structured collections ("N containers", "N edges", "N tests"). Say
   *what*, not *how many* — the reader can count, and the validator's
   summary line already reports totals.
2. **Refresh what you touch.** When updating a file that already carries
   such counts, re-derive each one from the structured data in the same
   write — or delete the sentence. Sweep the file's prose fields and
   comment headers for numerals adjacent to collection nouns; a
   propagation pass that changes a collection but not the prose
   describing it is an incomplete pass.

### Container mode → `docs/ARCH__<container>.yaml`

Same merge rules as above:

- Existing answers preserved unless the session changed them.
- New keys appended.
- Removals require user confirmation.
- Unrelated keys preserved.

### Derive component traces from unit touches (every container write)

Before writing a container file, set **every** component's
`traces_data_entities` to
`sorted(existing entries ∪ union of its work_units' touches_entities)`.
The curated list may EXCEED the union (entities the component reads
without a unit naming them) but must never lag it. **The subset law
(`touches_entities ⊆ traces_data_entities`, cross-check #21) is maintained
by derivation, not by hand** — twice now (ARCH v1.15, PLAN4) a
touches-completion pass broke it corpus-wide because the component lists
were being hand-maintained. A component whose units touch entities while
its `traces_data_entities` is missing/empty draws an advisory (the subset
check has no base to fire against there — the derive step was skipped).

After writing, refresh the generated files (Phase 8):
`python .claude/sdlc/docs_index.py` and `python .claude/sdlc/statusboard.py`.
Neither mode writes `CLAUDE.md` — see "CLAUDE.md is not this skill's to write".

## Version stamp (new writes)

`metadata.arch_version` (system file) and `metadata.arch_container_version`
(container files) each stamp `"2.0"` (or higher) on a new write — the
version-gated blocking checks (cross-checks #21-#24, the reason-less
`non_container_features` escape — CLAUDE.md section 10) arm
only at/above 2.0; an older stamp silently degrades every one of them to a
warning instead of dead code nothing ever reaches. The update flow on an
existing artifact bumps the version's minor number and never crosses a
floor by itself.

## Validation (Phase 7)

Run:

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/ARCH.yaml
```

This validates:

1. `docs/ARCH.yaml` against the Arch model.
2. Every sibling `docs/ARCH__*.yaml` against the ArchContainer model.
3. Required-field gates (status: complete cannot land if anything's
   missing). `edges` is REQUIRED as a key but an empty list `[]` is
   valid for single-container CLIs / pure libraries with no persistence.
4. External-container exemption: ARCH__*.yaml files whose parent
   container has `external: true` get a much-reduced required-field
   check (only `overview`) AND emit a warning recommending deletion.
5. Coverage cross-checks (always enabled in both modes; failure forces
   `metadata.status: draft`):

   - **API-resource coverage** — every resource in `docs/API__*.yaml`
     appears in some container's `owns_api_resources`.
   - **UX-surface coverage** — every data-bearing surface in
     `docs/UX__*.yaml` appears in some container's `owns_ux_surfaces`.
     ("Data-bearing" surface_types: screen, page, tab, modal, dialog,
     drawer, panel, cli_command, flow_step, other. Excluded:
     empty_state, toast, overlay.)
   - **DATA-store coverage** — every store in
     `DATA-MODEL.yaml.persistence.*` appears in some container's
     `persistence`.
   - **PRD feature coverage** — every PRD `features` FR-NNN
     appears in some container's `implements_requirements`, OR in the
     top-level `deferrals` list with a reason, OR — **below
     `arch_version` 2.0 only** — in the reason-less legacy
     `ARCH.yaml.non_container_features` list (at/above the floor
     that bare escape no longer counts as coverage and blocks like any
     other uncovered FR; below it, it still warns `[deferral hygiene]`,
     "honoured one more schema version"). Skipped when `docs/PRD.yaml` is
     absent. This catches operational features (scheduler/worker work
     with no API resource) that would otherwise be untraceable.
   - **PRD integration coverage (cross-check #31)** — every PRD
     `integrations_required` INT-NNN appears in some container's
     `realizes_integrations`, some component's `int_refs`, or
     `deferrals`. Blocks at `arch_version >= 2.0`, warns below
     (CLAUDE.md §10). Format + existence of INT refs always block when
     the fields are present. An external container realizing an INT
     without an `external_contract` draws a warning.

   **Structural deferrals (CLAUDE.md §6).** Every coverage gate above
   (FR / INT / API resource / UX surface / DATA store) reads the
   artifact's top-level `deferrals: [{id, reason}]` list FIRST (alias:
   `deferred_requirements`). Authoring rule for Phase 7: when the user
   decides an uncovered id is intentionally out of scope, write a
   `deferrals` entry with a real reason — never a bare mention. An entry
   with no reason defers nothing (the validator reports it), and an FR
   escaping only via the reason-less `non_container_features` list is
   reported for migration.
   - **Edge endpoint integrity** — every `edges[].from / to` (system)
     and `internal_edges[].from / to` / `external_edges[].from / to`
     (container) resolves to an existing node.

6. Edge `via_*` resolution (always enabled; failure forces draft):

   - `via_resource_id` (when set) resolves to a resource_id in some
     `API__*.yaml`.
   - `via_unit` (internal edges, when set) resolves to a `work_units[].name`
     on the edge's `to` component.
   - `via_operation_id` (external edges, when set) resolves to an
     `operation_id` under `API__*.yaml.endpoints[].operation_id`.
   - `via_channel_id` (when set) resolves to a `channel_id` in
     `API.yaml.events.channels[]`.
   - `via_entity` (when set) resolves to an entity name in
     `DATA-MODEL.yaml.entities`.

7. Deployment compatibility — `deployment.shape` in each container
   artifact is compatible with the parent container's
   `deployment_unit` (per the map in `ARCH__CONTAINER.schema.yaml`).

8. Container `file_path` integrity:

   - Every `containers[].file_path` that is set points to a file that
     exists on disk.
   - Every sibling `docs/ARCH__*.yaml` is referenced by some
     `containers[].file_path`.

9. Component trace integrity (REQUIRED per component when traces are set):

   - `traces_api_resources`   ⊆ resource_ids in `API__*.yaml`
   - `traces_api_resources`   ⊆ parent container's `owns_api_resources`
   - `traces_api_operations`  ⊆ operation_ids in `API__*.yaml`
   - `traces_ux_surfaces`     ⊆ surface_ids in `UX__*.yaml`
   - `traces_ux_surfaces`     ⊆ parent container's `owns_ux_surfaces`
   - `traces_data_entities`   ⊆ entity names in `DATA-MODEL.yaml`

10. Three container-vs-system consistency checks:

    - `api_surface` resource_ids ⊆ parent `owns_api_resources`.
    - `ux_surface` surface_ids ⊆ parent `owns_ux_surfaces`.
    - `persistence_bindings` store_ids ⊆ parent `persistence`.

11. ID-prefix formats (cross-skill conventions; failure forces draft):

    - `WRN-NNN` on every `arch_warnings` entry (system + each container),
      matching `^WRN-\d{3,}:\s+.+`.
    - `FR-NNN` on every `implements_requirements` entry (containers +
      components) and on `non_container_features`.
    - `WKF-NNN` on every `traces_prd_workflows` entry.

12. PRD trace integrity (failure forces draft; skipped when PRD declares
    no such family):

    - every `implements_requirements` (FR-NNN) resolves to a PRD FR id;
    - every `traces_prd_workflows` (WKF-NNN) resolves to a PRD WKF id;
    - a component's `implements_requirements` ⊆ its parent container's
      `implements_requirements`.

13. Upstream-status awareness (warning only, never blocks): the
    validator peeks at `metadata.status` of each upstream artifact
    (PRD, UX, DATA-MODEL, API) and prints a warning if any is not
    `complete`. This catches the case where someone hand-edits
    ARCH.yaml against a half-finished upstream chain.

14. Component `work_units` integrity + coverage (block `complete`):

    - **#21 per-unit integrity** — each `work_units[].name` is non-empty and
      unique within its component; `summary` non-empty; `traces_api_operation`,
      `implements_requirements` (⊆ the component's), `touches_entities` resolve
      (⊆ the component's `traces_data_entities` — the error's fix is the derive
      rule above: complete the component list to the union of unit touches).
      Advisory: a component whose units touch entities while its
      `traces_data_entities` is missing/empty (subset check has no base).
    - **#21 blocking upgrade** — a NON-TRIVIAL component (non-plumbing archetype
      carrying `implements_requirements` or a traced contract) that declares no
      `work_units` and no `work_units_waiver` blocks `complete`. Counts come from
      a real YAML parse (block- AND flow-style entries), never a line-grep.
    - **#22 FR → work_unit coverage** — for each component with work_units, every
      FR-NNN in its `implements_requirements` must appear in some
      `work_units[].implements_requirements`. Waivable per component via
      `work_units_waiver`. A per-container advisory roll-up lists FRs unreachable
      through any work_unit.

    These are the checks that make "drilled" mean *internally complete*. A
    `docs/ARCH__<cid>.yaml` that is on-disk `complete` but fails #21/#22 is
    **drilled but incomplete**; plain `/sdlc:arch` routes back to resume it and
    it does not count toward "all containers specified" (SKILL.md → Invocation
    dispatch).

15. Work_unit DEFER-OR-DECLARE contract (#23 — block `complete`):

    - A work_unit with **no** `traces_api_operation` (no schema-bearing traced
      contract) must declare ALL of `inputs`, `output`, `raises` — explicit
      empties count (`inputs: []`, `raises: []`, `output: "None"`); absence
      fails. A unit WITH `traces_api_operation` may defer to the API schema.
    - Waiver-aware: the component's `work_units_waiver` downgrades its units'
      contract gaps to warnings.
    - This closes the emitter divergence where units carried only trace
      fields (`implements_requirements`/`touches_entities`/
      `satisfies_acceptance`) and every downstream atomic task had to
      re-guess the interface.

16. Container→system edge roll-up (#24 — block `complete`):

    - Every container file's `external_edges[]` entry must have a
      corresponding `ARCH.yaml.edges` row ({from: that container, to: the
      target container, same type}). The system edge table is the roll-up of
      the per-container tables. Fix by confirming the appended rows at
      container-mode Phase 7 or running `/sdlc:arch -d`.
    - Also part of #15's via_* suite: an external edge's `via_unit` resolves
      to a `work_units[].name` on its `<container>/<component>` target
      (sibling-container calls with no API between them).

17. Warnings (never block): **#25** — a concrete repo path named as inline code
    (backticks) in a claimed FR's text outside every component's `code_location`
    (a build-time deliverable `task` could never schedule; bare prose slashes
    are ignored; a path under ARCH.yaml `output_locations` is runtime output
    and never reported); **#26** — an external `calls` edge with `via_resource_id` not
    mirrored in `api_consumers[]`; **#27** (tightened) — an unpinned
    cross-container `calls` seam into a container this system BUILDS (an
    `external: true` / `external-service` callee has no work_units to pin and
    is exempt), and a `via_unit` that resolves to an
    `entrypoint` unit while the edge records no `invocation`; **#28** —
    contract seams (an input type no sibling produces and no entity defines; an
    error contract decided nowhere on a pinned call seam; sibling
    `code_location` overlap); **#29** — a callable claimed by two units'
    `owns_callables`; **#30** — configuration consistency (duplicate keys,
    unknown `consumed_by`); store-id resolution (`realizes_store` /
    `persistence` / `persistence_bindings` vs the DATA store-id set — a stated
    no-op when the DATA persistence paradigm is `none`); the untraced-entity
    check (a DATA entity no component reads or writes, reported once every
    buildable container is drilled); and provenance staleness (a recorded
    `upstream_provenance` hash that no longer matches the upstream — "built
    against an older docs/X"). **#32** — a work_unit nothing reaches: an
    internal/external edge's `via_unit`, an `entrypoint`-kind unit, a
    framework-invoked component archetype, a non-callable kind (module /
    content / tooling), a sibling unit's contract text naming it, or a
    top-level `deferrals` entry all count as reached — as does a
    via_unit-less `calls` edge into a component with exactly one callable
    unit (unambiguous); into a component with two or more it collapses to
    ONE grouped advisory naming the component, never one row per unit. A
    via_unit-less `depends_on` edge never counts as reached (it proves an
    import, not an invocation — the same rule Gap-1's own `imported` set
    already applies).

18. **Version gating (CLAUDE.md §10).** Checks **#21–#24** and the
    component-containment gate ERROR at schema version >= 2.0
    (`arch_version` for #24's system half, `arch_container_version` per
    container file) and WARN below it; the INT coverage gate (#31) errors at
    `arch_version >= 2.0`; the reason-less `non_container_features` escape
    errors at the same floor instead of warning. An artifact
    stamped complete by an older skill version never flips red on upgrade —
    the findings print under WARNINGS with a note naming the floor.

**Numbering.** Two disjoint sequences share this file: `#1`-`#15` above are
this document's own system-mode list (never printed with a bracket tag by
the validator); `#21`-`#32` are the container/suite checks the validator
prints verbatim as `[cross-check N]` — this section is their one canonical
table. `SKILL.md`, `ARCH.schema.yaml` and `ARCH__CONTAINER.schema.yaml`
point here rather than keep their own copy.

### Exit-code recovery

| Exit | Meaning                                  | Action                                                     |
|------|------------------------------------------|------------------------------------------------------------|
| 0    | `[OK]` valid + complete, OR `[DRAFT]`.   | Proceed to Phase 8.                                        |
| 1    | Schema invalid, OR claims complete but   | Show errors. Offer per-error AskUserQuestion to fix, then  |
|      | required fields missing / checks failed. | re-run validator. If user prefers draft: set status: draft.|
| 2    | File missing or unparseable.             | Abort. Tell user the path that failed.                     |
| 3    | pydantic/pyyaml not installed.           | Tell user to `pip install pydantic pyyaml`. Skip validator.|

## `metadata.status` rules

- `complete` — set only when:
  - all required fields filled;
  - validator returns `[OK]`;
  - all coverage checks pass (API / UX / DATA-store / PRD-feature — zero
    uncovered);
  - all edge + trace integrity checks pass (zero unresolved edges, all
    component traces resolve, all PRD traces resolve);
  - all container-vs-system consistency checks pass;
  - all ID-prefix formats are valid (WRN/FR/WKF);
  - (container mode) component `work_units` integrity + FR coverage
    (#21/#22) pass — every non-trivial component has work_units or a
    `work_units_waiver`, and every component FR is realized by a work_unit
    or waived;
  - (container mode) every DECLARE-case work_unit carries its interface
    contract (#23), and every external edge has its system roll-up row
    (#24).
- `draft` — set on early EXIT, on any missing required field, or on
  any failing check. A container that is on-disk `complete` but fails
  #21/#22/#23 is "drilled but incomplete" — resume its deep-dive.

If the user is about to set `complete` but the validator flags
problems, surface them via AskUserQuestion and let the user choose:

1. Fix now (re-enter the missing fields inline, re-validate).
2. Save as draft (set status: draft, keep going).
3. EXIT (save state, stop).

**Warnings the user leaves standing become durable WRN entries (Phase 7
rule).** The validator never writes `arch_warnings` — the agent does. For
every validator WARNING the user chooses not to fix now, append ONE grouped
`WRN-NNN` entry per warning class to the affected file's `arch_warnings`
(e.g. `"WRN-004: 3 cross-container calls have no pinned invocation seam
(check 27) - accepted for now"`), using the writer-managed counter
(`state.last_ids.WRN`). Without this, the decision to accept a warning
evaporates with the session and every later run re-litigates it. Do not
duplicate an entry that already records the same class; refresh its count
instead.

## CLAUDE.md is not this skill's to write (Phase 8)

**This skill never writes `CLAUDE.md`.** The project-root `CLAUDE.md` is owned by
`/sdlc:setup`, which writes one static `## SDLC Documents` block — no per-skill
bullets, no timestamps, byte-identical on every run. Never add a section, a
bullet, a note, an id, a status, a caveat or a resolution there.

Those have homes that a machine reads and that nothing has to remember to
update:

| What you noticed | Where it goes |
|---|---|
| A caveat about this artifact | a typed `WRN-NNN` entry in the artifact itself |
| A defect in an upstream spec | `FND-NNN`, via `.claude/sdlc/findings.py` |
| A defect in an sdlc SKILL | `LSN-NNN`, via `/sdlc:lesson` |
| Something the user should see now | the close card's `Attention:` row |

All of them surface, generated and never stale, in
`.claude/rules/sdlc-statusboard.md` (loaded into every session) and
`.claude/sdlc/STATUS.md` (the full text). Refresh both at the end of Phase 8:

```bash
python .claude/sdlc/docs_index.py     # the navigation index
python .claude/sdlc/statusboard.py    # the statusboard
```

Both are harmless no-ops when the project has not run `/sdlc:setup`.

## Downstream-agent rejection rule

Document this so test/task/deploy can enforce it:

> **Downstream skills MUST reject `docs/ARCH.yaml` if
> `metadata.status != "complete"` OR if `validate_schema.py` exits
> non-zero.** The one exception is to the exit code, never to the status: a
> failure every check of which `doctor.py --artifact docs/ARCH.yaml` reports as
> accepted deviance does not reject
> (`${CLAUDE_SKILL_DIR}/../repair/references/accepted-deviance.md`).

The same applies to each `docs/ARCH__<container>.yaml`. A draft container
file means that container has not been confirmed and is not safe to
generate code from.

> **Field-level errors are the one thing you show verbatim** — the field path
> *is* the fix, so paraphrasing it costs the user the answer. Everything else
> the validator prints gets translated, not pasted: coverage gaps, warnings and
> cross-check findings become one plain sentence each (what happened, why it
> matters, what to do). See CLAUDE.md section 14 and
> `${CLAUDE_SKILL_DIR}/../prd/references/reporting-to-the-user.md`.
