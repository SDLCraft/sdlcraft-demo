# Merge, validate, and closing out

Detailed rules for Phase 7 (write & validate) and Phase 8 (refresh & close). Read this when entering Phase 7.

## What Phase 7 writes

Phase 7 always writes **at least two files** for a non-trivial product:

1. `docs/UX.yaml` — the global UX contract.
2. One `docs/UX__<surface_id>.yaml` per confirmed surface in
   `state.defined_surfaces`.

If a surface's status is still `draft` at write time (the user
EXIT'd mid-deep-dive or explicitly chose "Skip for now"), do NOT write
that surface yaml. The inventory entry stays in `UX.yaml` with
`status: draft`, the coverage check will surface any PRD flow it was
supposed to cover, and `UX.yaml.metadata.status` is forced to `draft`.

## Merging into an existing UX.yaml + surface files

If `docs/UX.yaml` already exists:

- Load it as the baseline.
- Merge the session's confirmed answers on top:
  - **Keys present in both** — overwrite *only* if the user changed
    the value during this session. Otherwise keep the existing value.
  - **New keys** — add them.
  - **Keys the session would remove** — ask the user to confirm
    before deleting.

If `docs/UX__<surface_id>.yaml` already exists:

- Load it as the surface baseline.
- Merge the session's confirmed per-surface answers on top with the
  same overwrite/add/remove logic.

If the session's `surface_inventory` would **remove a surface** that
previously existed:

> "I'm about to remove surface `<surface_id>` from the inventory.
> This will delete `docs/UX__<surface_id>.yaml`. Proceed?"

Wait for explicit confirmation before deleting the file.

If the user manually edited an artifact between sessions and state
file disagrees on a specific key, surface the conflict — do NOT
silently pick:

> "Conflict on `UX.yaml.<key>`:
>   UX.yaml has: `<a>`
>   Interview state has: `<b>` (set at <timestamp>)
> Which should I keep?"

Always preserve **unrelated keys** in the existing YAML files even if
you don't recognise them. The validator's `extra="allow"` config means
custom keys are tolerated.

**Surface-status maturity.** Before merging, run the downstream-claim
reconciliation from SKILL.md Phase 2: any surface claimed by
`ARCH.yaml.containers[].owns_ux_surfaces` whose inventory `status` is not
`confirmed` gets a consolidated prompt — confirm the surface, note the
premature ARCH claim to `state.finding_notes` for `/sdlc:repair` (never a
`WRN` about another artifact, CLAUDE.md §13), or drop the claim note. A
surface that ARCH builds and TEST tests must not linger as `proposed` in the
UX inventory — the validator prints a standing warning for exactly this
mismatch, and this merge step is where it gets resolved.

## Writing the files

For `UX.yaml`:

- Inline YAML comments on each top-level key (use `UX.schema.yaml` as a
  template).
- `metadata.ux_version`: stamp `"3.0"` (or higher) on a new write — the
  version-gated blocking checks (CLI-contract typing, inventory-shard
  integrity — CLAUDE.md section 10) arm only
  at/after 3.0, the same as the existing 2.0 provenance gate; an older
  stamp silently degrades every one of them to a warning instead of dead
  code nothing ever reaches. The update flow on an existing artifact bumps
  the version's minor number and never crosses a floor by itself — moving
  2.x → 3.0 (or 3.x → 4.0) needs an explicit reason, not an automatic edit.
- Updated `metadata.last_updated` (ISO-8601 UTC) and
  `metadata.session_id`.
- `metadata.status`:
  - Set to `"complete"` only when:
    1. all required fields are filled,
    2. the validator passes with `[OK]` (schema + ID-prefix format),
    3. every WKF-NNN parsed from `PRD.use_cases.core_workflows` is
       referenced by at least one surface's `traces_workflows`.
  - Set to `"draft"` on early EXIT, when any required field is null,
    OR when any PRD WKF-NNN is uncovered.
- `metadata.changelog`: append-only. When running in update mode (an
  existing UX.yaml is on disk), prepend ONE entry summarizing this
  session's material changes in the format
  `"<ux_version> (<YYYY-MM-DD>): <one-line summary>"`. Never rewrite
  earlier entries; never reorder; never delete. On a brand-new write
  (no existing UX.yaml), the changelog may be omitted entirely or
  initialized with a single `"<ux_version> (<YYYY-MM-DD>): initial."`
  entry — both are valid.
- `ux_warnings`: informational notes, each prefixed with a writer-
  managed `WRN-NNN:`. Used for uncovered PRD WKF-NNN, low-confidence
  answers, merge conflicts, dropped optional themes (the now/skip/todo
  gates), sweep candidates the user deferred, and any other note
  downstream agents should see. The counter lives in
  `state.last_ids.WRN` (or `state.last_ids_by_product[<slug>].WRN`
  in monorepo mode).

For each `UX__<surface_id>.yaml`:

- Inline comments on top-level keys.
- Updated metadata (`last_updated`, `session_id`).
- `metadata.changelog`: same append-only rule as UX.yaml.
- `metadata.status: complete` only when all required surface fields
  are filled (`id` = SCR-NNN, `surface_id`, `surface_type`, `layout`,
  `traces_workflows` — may be `[]` for non-flow surfaces) AND the user
  explicitly approved in theme 11 step e. The validator additionally
  enforces SCR-NNN format on `id` and WKF/FR/ENT format on each ref
  list.

## Running the validator

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/UX.yaml
```

The validator does six things in one pass:

1. Schema-validates `docs/UX.yaml`.
2. Schema-validates every `docs/UX__*.yaml` sibling.
3. ID-prefix format checks: `SCR-NNN` on every surface id (in both
   `surface_inventory[].id` and per-surface top-level `id`); `WRN-NNN:
   <message>` on every `ux_warnings` entry; `WKF-NNN` on values in
   `traces_workflows`; `FR-NNN` on values in `implements_requirements`
   and in `cli.exit_codes[<code>].implements_requirements`; `ENT-NNN`
   on values in `references_entities`. Violations are warnings when
   `status: draft`, errors when `status: complete`.
4. Coverage check: every WKF-NNN id parsed from
   `PRD.use_cases.core_workflows` (read from `docs/PRD.yaml` directly,
   not from state) must be referenced by at least one surface yaml's
   `traces_workflows`. Matching is by id only — verbatim text in PRD
   may change freely without breaking the coverage. Uncovered ids are
   surfaced in the output.
5. CLI-contract typing (blocking at `ux_version >= 3.0`, a warning below
   — CLAUDE.md section 10): a `layout.cli_args` or
   `cli.global_flags` entry that is not a mapping, or a `cli_command`
   surface's `exit_conditions` entry that is a plain string or names a
   code absent from `cli.exit_codes`.
6. Inventory-shard integrity (same floor): a
   `surface_inventory` `file_path` that names no file on disk, or a
   `UX__*.yaml` on disk that no `surface_inventory` entry names —
   mirrors `arch`'s `check_file_path_integrity`.

Exit codes:

| Code | Meaning | What the agent does |
|---|---|---|
| 0 (`[OK]`) | UX.yaml is complete, all surfaces valid, every PRD flow covered | ✓ Proceed to Phase 8. |
| 0 (`[DRAFT]`) | Draft — schema valid, possibly missing required fields or coverage | Inform user; proceed to Phase 8. |
| 1 (`[FAIL]`) | Schema invalid, OR `status: complete` but required fields missing, OR `status: complete` but coverage incomplete | Show field-level errors verbatim. Offer via `AskUserQuestion`: fix now, or accept `status: draft`. Re-run validation after re-entry. |
| 2 | Cannot read/parse one of the files | Surface to user (missing file, bad YAML, permission error). Do not retry silently. |
| 3 | Missing dependency | Validator prints `pip install` instructions. Ask the user to install and re-run; do NOT auto-install. |

**Downstream-agent contract**: downstream skills/agents MUST reject the
UX artifacts if `UX.yaml.metadata.status != "complete"` OR if the
validator exits non-zero. The one exception is to the exit code, never to the
status: a failure every check of which `doctor.py --artifact docs/UX.yaml`
reports as accepted deviance does not reject
(`${CLAUDE_SKILL_DIR}/../repair/references/accepted-deviance.md`).

## Coverage-check details

The coverage check reads `docs/PRD.yaml` and extracts the WKF-NNN id
prefix from each entry in `use_cases.core_workflows` (or, in monorepo
mode, the union across products). PRD entries are of the form
`"WKF-NNN: <description>"`; the leading id is extracted via regex. A
WKF-NNN id is **covered** when it appears verbatim in at least one
surface yaml's `traces_workflows` list. Matching is on the id only —
the description text in PRD may change freely without breaking the
trace.

If `docs/PRD.yaml` is missing, the validator continues without the
coverage check and its headline says the PRD was not found and coverage
was NOT checked — it never claims "all 0 PRD workflow(s) covered".

Any uncovered WKF-NNN:

1. Appears in the validator's output ("PRD WKF-NNN(s) with no surface
   trace").
2. Must be written to `UX.yaml.ux_warnings` by the agent during Phase 7
   *before* validation runs, as a `WRN-NNN:` entry, e.g.
   `"WRN-007: coverage: WKF-008 has no surface trace"`. The WRN-NNN is
   assigned from `state.last_ids.WRN` (writer-managed counter).
3. Forces `UX.yaml.metadata.status: draft`.

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

## Closing the session

Once Phase 8's refresh has run:

- Set `status: complete` in the state file.
- Keep the state file as an audit trail — do **not** delete it.
- Tell the user the workflow finished and where the artifacts live (the
  close card, SKILL.md Phase 8).

> **Field-level errors are the one thing you show verbatim** — the field path
> *is* the fix, so paraphrasing it costs the user the answer. Everything else
> the validator prints gets translated, not pasted: coverage gaps, warnings and
> cross-check findings become one plain sentence each (what happened, why it
> matters, what to do). See CLAUDE.md section 14 and
> `${CLAUDE_SKILL_DIR}/../prd/references/reporting-to-the-user.md`.
