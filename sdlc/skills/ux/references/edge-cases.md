# Edge cases — sdlc-ux

Read this whenever the agent hits an unusual situation that doesn't fit
the happy path.

## Input-side edge cases (PRD-related)

- **`docs/PRD.yaml` missing**: do NOT proceed. Print a clear warning:

  > "Cannot start the UX interview — `docs/PRD.yaml` is missing. Run
  > `/sdlc:prd` first."

  Exit cleanly without writing anything.

- **`docs/PRD.yaml` present but `metadata.status: draft`**: do NOT
  proceed. The PRD is the source of truth for surface family, runtime
  platform, accessibility baseline, and core workflows — a draft PRD
  makes UX decisions speculative.

  Offer three choices via `AskUserQuestion`:

  - "Stop and finish the PRD first" (recommended).
  - "Proceed anyway and record draft status in `ux_warnings`" — only
    use this when the user explicitly accepts the risk. The UX yaml
    will be forced to `status: draft` regardless of completeness.
  - "The upstream is wrong — record a finding for `/sdlc:repair`" — the
    PRD is not merely unfinished but defective (stamped draft by
    mistake, or contradicts itself). Append the observation to
    `state.finding_notes` and continue with one of the first two paths;
    the run never stops to record (CLAUDE.md §13).

- **`docs/PRD.yaml` fails PRD validator (exit code 1, 2, or 3)**: do
  NOT proceed. Print the validator's error output verbatim and ask the
  user to fix the PRD first.

- **PRD has no `use_cases.core_workflows`**: surface a `ux_warnings`
  entry and proceed. The coverage check will pass trivially (no flows
  to cover), but the UX skill becomes a thin shell — every surface is
  user-defined from scratch. Recommend the user re-run `/sdlc:prd` to
  fill in the missing flows.

- **PRD `runtime_platform` (a list as of PRD 1.1) contains `server`,
  `embedded`, `browser_extension`, `other` or `undecided`**: ask the user
  which family that platform presents. Servers often expose a CLI admin
  tool plus a web admin panel — `mixed` is the common answer. `service`
  and `library` need no question: they are headless families, taken as-is.
- **The list maps to two or more families** (e.g. `[web, cli]`): that is
  `mixed` by definition — confirm the members, don't re-ask the family.

## ID-family edge cases

- **Surface implied by ENT-### but no WKF-### mentions it.** This is the
  canonical "missed surface" pattern. Don't try to special-case it in
  the per-item flow — let the **scope-completeness sweep** (theme 4
  step e, `surface-discovery.md`) catch it. The sweep reflects on
  every ENT-### description and surfaces concrete candidates like
  *"⚠ cmd-list — implied by ENT-032 ProjectRegistry"*. If the user
  accepts, the candidate enters the per-item flow at step a and gets
  the next `SCR-NNN`.

- **`SCR-NNN` collision after merge.** When merging into an existing
  UX.yaml, you may find two surfaces with the same `SCR-NNN` (e.g.
  the user manually edited the file and renumbered, then the skill
  re-ran). Behaviour: surface the conflict via the standard merge-
  conflict prompt (see `merge-validate.md`); do NOT silently
  renumber. SCR-NNN ids are stable by contract — preserving the user's
  manual edits beats automated renumbering.

- **A surface's `traces_workflows`, `implements_requirements`, or
  `references_entities` references an id that no longer exists in PRD.**
  Happens when PRD was edited between sessions to remove an item.
  Behaviour on resume: detect the stale ref during Phase 2 scan; ask
  the user *"Surface `<SCR-NNN>/<surface_id>` references `<WKF-NNN |
  FR-NNN | ENT-NNN>` which no longer exists in PRD. Remove the ref,
  re-route to a different id, leave + record a ux_warnings entry, or is
  the upstream wrong — record a finding for `/sdlc:repair`?"* The
  fourth pick means the PRD deletion itself is the defect: append the
  observation to `state.finding_notes` and continue — the run never
  stops to record (CLAUDE.md §13). Do not silently delete refs.

- **Changelog entry was deleted or reordered manually.** The changelog
  is append-only by contract, but the validator does NOT enforce
  append-only on disk (it only checks the type is `list[string]`).
  Behaviour: trust the on-disk file as the source of truth. If you
  notice obvious tampering (e.g. the version numbers don't increase
  monotonically), surface a one-time warning to the user but proceed
  without rejecting.

- **`WRN-NNN` / `SCR-NNN` counter drift.** Covered by the canonical resume
  recipe (`${CLAUDE_SKILL_DIR}/../prd/references/edge-cases.md` → "Resume
  with stale state"; AUTHORING §5's `max(state counter, highest id present
  on disk)`), not restated here.

## Surface-inventory edge cases

- **Surfaceless PRD flow**: a `core_workflow` for which the agent can't
  imagine any UI surface — e.g. "Send a weekly digest email". Behavior:
  - The agent should propose a `flow_step` surface (`surface_type:
    flow_step`) named after the workflow, even if it has no UI per se,
    so the trace exists. The `layout` for these flow steps is the
    backend trigger description (cron + payload).
  - Alternative: keep the flow uncovered and write a `ux_warnings`
    entry. Force `status: draft`.

- **Same surface participates in many flows**: fine. List every
  matching flow in `traces_prd_flows`. The coverage check is satisfied
  as long as each flow appears in at least one surface's traces, but
  one surface can carry several flows.

- **Two surfaces have a circular trace dependency** (rare, e.g. a flow
  routes through two surfaces back-and-forth): list the flow in both
  surfaces' `traces_prd_flows`. No special handling needed.

- **Surface candidate has no obvious trace** (e.g. `/about` page, error
  surfaces): allow it. Record `traces_prd_flows: []` and add a
  `ux_warnings` entry `"surface '<id>' has no PRD trace"`. The
  validator does NOT require every surface to trace — it only requires
  every PRD flow to be covered by at least one surface.

## Mid-interview platform change

The user said `web` in theme 1, answered themes 2–5, then says
"actually we also need a CLI companion → make it `mixed`".

Behavior:

- Update `state.surface_family = mixed`, prompt for
  `surface_family_members`.
- Re-evaluate `required_if` rules at next theme boundary — the
  `cli_specifics` theme is now required.
- Existing surfaces stay; the user can add CLI surfaces during
  theme 4 (extension of inventory). Existing per-surface yamls don't
  need to change.
- Do NOT silently delete the user's earlier answers — surface family
  changes augment, not invalidate.

If the user goes from `web` → `cli` (changing, not adding), warn:

> "Switching surface_family from `web` to `cli` will invalidate
> existing surface deep-dives (region trees won't apply to CLI
> commands). Continue and re-do the surfaces, or keep both as
> `mixed`?"

## Conflicting design decisions across surfaces

The user picks `state_patterns.error: "Inline error + retry"` globally
but later, during a per-surface deep-dive, picks `surface.states.error:
"Full-screen error page"` for a specific surface.

Behavior: respected — the per-surface override wins. Surface that
override in `ux_warnings` only if it appears unintentional (e.g.
several surfaces silently override the same default; ask the user
whether they want to update the global pattern instead).

## Deleted PRD workflows / entities / features mid-session

The user is mid-interview, switches to another shell, edits
`docs/PRD.yaml` to remove a WKF-/FR-/ENT- entry, then resumes. The
agent's in-memory inventory still references the old id.

Behavior on resume:

1. Re-read `docs/PRD.yaml` and re-derive the ID inventories (WKF-### in
   `use_cases.core_workflows`, FR-### in `functional_requirements.must_
   have_features` + `nice_to_have_features`, ENT-### in
   `data_model.key_entities`).
2. Diff against `state.defined_surfaces[*].{traces_workflows,
   implements_requirements, references_entities}`.
3. If any id was removed but is still referenced, prompt per stale ref:

   > "PRD no longer contains `<WKF-NNN | FR-NNN | ENT-NNN>`. Surface
   > `<SCR-NNN>/<surface_id>` still references it. Remove the ref,
   > re-route to a different id, keep + record a ux_warnings entry, or
   > is the upstream wrong — record a finding for `/sdlc:repair`?"

   The fourth pick (the PRD removal was the mistake) appends the
   observation to `state.finding_notes` and continues — never stop the
   run to record (CLAUDE.md §13).

4. Update the ref list based on the user's answer.

If new ids were added (a new WKF/FR/ENT in PRD), also offer to extend
the inventory: re-run theme 4 step a only for the new ids, then re-run
the scope-completeness sweep over the union.

## Upstream changes between sessions (re-invocation, §7)

The section above handles an upstream edited *mid-session* (the resume path).
When the user instead re-invokes `/sdlc:ux` in a *new* session after
`docs/UX.yaml` already exists, Phase 2 runs **upstream-change detection**
against `metadata.upstream_provenance`: it compares the recorded `sha256` of
`docs/PRD.yaml` to its current hash and, if PRD moved, runs the consolidated
delta-review (added / removed / modified PRD ids) *before* the interview. This
is the cross-skill §7 contract; the stale-ref prompt above is the "removed"
branch of it, and the "added" offer is the "added" branch. A content hash also
catches hand-edits that no `session_id` check would. Full mechanics:
`${CLAUDE_SKILL_DIR}/../ux/references/upstream-reconciliation.md`.

## Validation failures

Same flow as `sdlc:prd`. Show field-level errors verbatim, list
affected paths, offer via `AskUserQuestion`: "Fill in now, or accept
draft status?" Re-run validation after re-entry.

Common failure modes specific to UX:

- **Surface yaml claims `status: complete` but `traces_workflows` is
  unset (None)**: validator fails. Either set it to `[]` (explicit
  non-flow surface; record a WRN-NNN entry so downstream knows it's
  intentional) or add WKF-NNN id(s).
- **`traces_workflows: []` is allowed** (non-flow / chrome / diagnostic
  surfaces) — the validator only enforces that the field is filled in
  (non-None), not non-empty. The coverage check separately verifies
  that *every PRD WKF-NNN* is referenced by *some* surface; a single
  surface with an empty list is fine as long as another surface
  picks up the slack for its WKF-NNN(s).
- **An ID value in a ref field has the wrong family prefix** (e.g. an
  `FR-NNN` mistakenly listed in `traces_workflows`): validator
  surfaces it as an ID-prefix format violation. In `status: complete`
  this is an error; in `draft` it's a warning. Resolution: move the
  id to its correct family field.
- **`UX.yaml.surface_inventory[i].file_path` points to a non-existent
  file**: validator does NOT explicitly check this (the discovery scans
  the docs/ folder). Recommend the agent verify file existence before
  declaring Phase 8 complete and surface a warning if a file is missing.

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

If the user tries to batch-accept `⚠ inferred` surfaces or per-surface
fields with shortcuts like "ok" or "all good", refuse and re-prompt.
Each `⚠` item needs an explicit confirmation or correction. This
applies to:

- Phase 5 pre-fill confirmation.
- Phase 6 theme 4 (`surface_inventory`).
- Phase 6 theme 11 (`per_surface_deepdive`).

## Monorepo mode

When `PRD.metadata.monorepo == true`:

- `UX.yaml` itself is monorepo-shaped (themes under
  `products.<slug>.<theme>`).
- Surface yamls are named
  `docs/UX__<product-slug>__<surface-slug>.yaml` to avoid collisions
  between products that have surfaces with the same id.
- The interview runs **per product**: theme 4 enumerates each
  product's surfaces separately; theme 11 deep-dives the union.
- The coverage check is per-product: every product's
  `use_cases.core_workflows` must be covered by at least one surface
  from that product.

If the PRD is monorepo but the user wants the UX skill to treat the
products as if they were one shared UX (e.g. a unified design system),
offer:

> "Treat all products as one unified UX (single UX.yaml), or run
> per-product UX interviews (one UX.yaml per product slug)?"

Default to per-product; only switch to unified when the user explicitly
asks.

## Very large surface inventories

If the user accepts the hard cap of 20 surfaces (per
`surface-discovery.md`) and wants more, refuse politely and suggest:

- Splitting the product into multiple products (and converting the
  PRD to monorepo mode).
- Pushing some surfaces to a later phase (drop from MVP inventory,
  note in `ux_warnings: "phase-2 surface: <id>"`).

## CLI surface family with no PRD CLI flows

If `surface_family in ['cli', 'mixed']` but the PRD doesn't mention
any CLI-style workflows, surface a `ux_warnings` entry and continue.
The user may be designing the CLI alongside the PRD; the per-surface
deep-dives will surface this.

## User skips a required theme

The skill cannot mark a required theme `todo` — that's a hard error.
If the user tries, refuse politely:

> "`<theme>` is required for downstream agents to consume the UX
> spec. Either answer it now, or type `EXIT` to save progress as
> `aborted`."
