# Merge, validate, and closing out

Detailed rules for Phase 7 (write & validate) and Phase 8 (refresh & close). Read this when entering Phase 7.

## What Phase 7 writes

Phase 7 always writes **at least one file** — `docs/API.yaml`. For
non-`none` APIs it also writes one
`docs/API__<resource_id>.yaml` per confirmed resource in
`state.defined_resources`.

If a resource's status is still `draft` at write time (the user
EXIT'd mid-deep-dive or explicitly chose "Skip for now"), do NOT
write that resource yaml. The inventory entry stays in `API.yaml`
with `status: draft`, the coverage checks will surface any PRD
feature / UX surface it was supposed to cover, and
`API.yaml.metadata.status` is forced to `draft`.

## Merging into an existing API.yaml + resource files

If `docs/API.yaml` already exists:

- Load it as the baseline.
- Merge the session's confirmed answers on top:
  - **Keys present in both** — overwrite *only* if the user changed
    the value during this session. Otherwise keep the existing value.
  - **New keys** — add them.
  - **Keys the session would remove** — ask the user to confirm
    before deleting.

If `docs/API__<resource_id>.yaml` already exists:

- Load it as the resource baseline.
- Merge the session's confirmed per-resource answers on top with the
  same overwrite/add/remove logic.

If the session's `resource_inventory` would **remove a resource** that
previously existed:

> "I'm about to remove resource `<resource_id>` from the inventory.
> This will delete `docs/API__<resource_id>.yaml`. Proceed?"

Wait for explicit confirmation before deleting the file.

If the user manually edited an artifact between sessions and the state
file disagrees on a specific key, surface the conflict — do NOT
silently pick:

> "Conflict on `API.yaml.<key>`:
>   API.yaml has: `<a>`
>   Interview state has: `<b>` (set at <timestamp>)
> Which should I keep?"

Always preserve **unrelated keys** in the existing YAML files even if
you don't recognise them. The validator's `extra="allow"` config means
custom keys are tolerated.

## Writing the files

For `API.yaml`:

- Inline YAML comments on each top-level key (use `API.schema.yaml` as
  a template).
- Updated `metadata.last_updated` (ISO-8601 UTC) and
  `metadata.session_id`.
- `metadata.api_version`: new writes stamp `"2.0"` (CLAUDE.md §10). An
  update-flow merge on an older file keeps the file's existing version —
  do not silently bump a legacy artifact's floor out from under it.
- `metadata.status`:
  - Set to `"complete"` only when:
    1. all required fields are filled,
    2. the validator passes with `[OK]`,
    3. feature coverage passes (every PRD FR-NNN traced or deferred
       via the top-level `deferrals: [{id, reason}]` list — a bare
       `non_api_features` entry covers below `api_version` 2.0 only),
    4. surface coverage passes (matched by SCR-NNN id; traced or
       deferred),
    5. entity-link check passes,
    6. every ID-prefix format check passes (WRN/FR/SCR/WKF/OPR)
       (or the validator skipped coverage/entity-link because
       `api_kind: none`),
    7. every `external_dependencies` entry names an
       `integration_ref: INT-NNN` that resolves in PRD.yaml (from
       `api_version` 2.0; not skipped at `api_kind: none`).
  - Set to `"draft"` on early EXIT, when any required field is null,
    OR when any check fails.
- `metadata.changelog` (append-only, most-recent first): on a fresh
  write, omit the field or initialize with a single
  `"<version> (<YYYY-MM-DD>): initial."` entry. On an update-flow
  merge, prepend ONE new entry summarising what materially changed.
  Validator type-checks `Optional[list[string]]` only; format is
  convention, not enforced.
- `api_warnings`: every entry MUST be `"WRN-NNN: <message>"`. The
  WRN counter lives in `state.last_ids.WRN`; increment-then-write per
  appended item. Counter drift is covered by the canonical resume recipe
  (`${CLAUDE_SKILL_DIR}/../prd/references/edge-cases.md` → "Resume with
  stale state"; AUTHORING §5's `max(state counter, highest id present on
  disk)`), not restated here. Used for uncovered PRD features, uncovered
  UX surfaces, unresolved primary_entity references, low-confidence
  answers, merge conflicts, dropped optional themes (the now/skip/todo
  gates), sweep deferrals.

For each `API__<resource_id>.yaml`:

- Inline comments on top-level keys.
- Updated metadata (`last_updated`, `session_id`); optional
  `metadata.changelog` follows the same rules as `API.yaml`.
- `metadata.status: complete` only when all required resource fields
  are filled (`resource_id`, `base_path`, `traces_prd_features` with
  FR-NNN format, `traces_ux_surfaces` with SCR-NNN format, `endpoints`
  — each endpoint with `id` (OPR-NNN), `operation_id`, `method`,
  `path`, `summary`, `responses`) AND the user explicitly approved in
  theme 10 step e.

## Running the validator

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/API.yaml
```

The validator does seven things in one pass:

1. Schema-validates `docs/API.yaml`.
2. Schema-validates every `docs/API__*.yaml` sibling.
3. **Feature coverage**: every entry in
   `PRD.functional_requirements.features` (parsed as `FR-NNN`)
   appears in at least one resource's `traces_prd_features`, OR is
   deferred via the top-level `deferrals: [{id, reason}]` list
   (consulted FIRST), OR — DEPRECATED, covers below `api_version` 2.0
   only, always reported — sits bare in `API.yaml.non_api_features`.
   At/above 2.0 a bare `non_api_features` entry no longer covers
   anything: the FR is reported as uncovered like any other untraced id.
4. **Surface coverage**: every data-bearing UX surface appears in at
   least one resource's `traces_ux_surfaces` OR is deferred via the
   same `deferrals` list. A surface is
   "data-bearing" if its `surface_type` is in
   `{screen, page, tab, modal, dialog, drawer, panel, cli_command,
   flow_step, other}` (types like `toast`, `empty_state`, `overlay`
   are display-only and ignored).
5. **Entity-link check**: every `primary_entity` value (whether on
   a resource_inventory item or in a per-resource yaml) exists in
   `DATA-MODEL.yaml.entities`. Skipped (with a printed warning) if
   `DATA-MODEL.yaml` is absent.
6. **Integration contracts** (NOT skipped at `api_kind: none`): every
   `external_dependencies` entry names an `integration_ref: INT-NNN`
   that resolves in `PRD.functional_requirements.integrations_required`
   — never minted here (CLAUDE.md §4). A missing or dangling
   `integration_ref` blocks from `api_version` 2.0; below 2.0 it only
   warns. Vacuous on an empty/null `external_dependencies` list.
7. **Provenance freshness** (warn-level, never blocks): each
   `metadata.upstream_provenance` sha256 is compared to the
   upstream's current hash; a mismatch warns "built against an older
   docs/X - run /sdlc:api to review the delta". `status: complete`
   with no provenance at all warns from `api_version >= 2.0`.

Checks 3-5 are skipped when `api_kind: none`; check 6 is NOT — an
integration-only CLI/library still needs typed provider contracts.

**Absent-upstream honesty**: when `docs/PRD.yaml`, the `docs/UX__*.yaml`
shards, or `docs/DATA-MODEL.yaml` are absent, the corresponding check
does not run and the summary SAYS SO ("requirement coverage was not
checked") — it never reports zeros as a pass, and a `complete` artifact
gets a warning listing what nothing vouched for.

Exit codes:

| Code | Meaning | What the agent does |
|---|---|---|
| 0 (`[OK]`) | API.yaml is complete, all resources valid, all enabled checks pass | ✓ Proceed to Phase 8. |
| 0 (`[DRAFT]`) | Draft — schema valid, possibly missing required fields or coverage | Inform user; proceed to Phase 8. |
| 1 (`[FAIL]`) | Schema invalid, OR `status: complete` but required fields missing, OR `status: complete` but a check failed | Show field-level errors verbatim. Offer via `AskUserQuestion`: fix now, or accept `status: draft`. Re-run validation after re-entry. |
| 2 | Cannot read/parse one of the files | Surface to user (missing file, bad YAML, permission error). Do not retry silently. |
| 3 | Missing dependency | Validator prints `pip install` instructions. Ask the user to install and re-run; do NOT auto-install. |

**Downstream-agent contract**: downstream skills/agents MUST reject
the API artifacts if `API.yaml.metadata.status != "complete"` OR if
the validator exits non-zero. The one exception is to the exit code, never to
the status: a failure every check of which `doctor.py --artifact docs/API.yaml`
reports as accepted deviance does not reject
(`sdlc/skills/repair/references/accepted-deviance.md`).

## Coverage-check details

### Structural deferrals (trace-or-defer, CLAUDE.md §6)

Both coverage gates read a top-level `deferrals` list (alias
`deferred_requirements`; also read under each `products.<slug>` in
monorepo mode) BEFORE any fallback:

```yaml
deferrals:
  - id: FR-012        # or SCR-NNN for a surface deferral
    reason: "Nightly cleanup job - no endpoint; realized in ARCH."
```

An entry needs BOTH an id and a reason — an entry with no reason
defers nothing and is reported (an unauditable deferral is not a
deferral). The writer records a deferral only after the user
explicitly chose it (a "defer" pick in theme 8, the sweep, or the
delta review); the matching human-readable `WRN-NNN` note in
`api_warnings` stays the companion, never the machine channel.

### Feature coverage

The validator reads `docs/PRD.yaml`, extracts every
`functional_requirements.features` entry, and parses out
the `FR-NNN` prefix (case-insensitive). A feature is **covered** when
at least one resource lists the `FR-NNN` (verbatim, ignoring
description text) in its `traces_prd_features` list, OR when the
FR-NNN is deferred via `deferrals` (read first), OR — DEPRECATED,
covers below `api_version` 2.0 only — when it sits bare in
`API.yaml.non_api_features`. Below the floor, every id that only the
bare `non_api_features` fallback saves is reported once in the
WARNINGS section (`[deferral hygiene]`); at/above 2.0 the fallback no
longer covers anything and the FR is reported as uncovered instead.
New writes always use `deferrals`.

If `docs/PRD.yaml` is missing, the validator continues without the
feature coverage check (prints a warning).

Uncovered features:

1. Appear in the validator's output ("PRD FR-NNN feature(s) with no
   resource trace").
2. Should be written to `API.yaml.api_warnings` by the agent during
   Phase 7 *before* validation runs
   (`"coverage: feature '<FR-NNN>' has no resource trace"`).
3. Force `API.yaml.metadata.status: draft`.

### Surface coverage

The validator walks `docs/UX__*.yaml` files. For each surface, it
checks `surface_type` and reads the surface's **stable `id` field
(SCR-NNN)** — never the editable `surface_id` slug:

- Data-bearing (covered by this check):
  `screen`, `page`, `tab`, `modal`, `dialog`, `drawer`, `panel`,
  `cli_command`, `flow_step`, `other`.
- Display-only (ignored by this check):
  `toast`, `empty_state`, `overlay`.

A data-bearing surface is **covered** when at least one resource
lists its `SCR-NNN` id in `traces_ux_surfaces`, or when the SCR-NNN
is deferred via the top-level `deferrals` list ({id, reason}).

A resource that serves no UX surface BY DESIGN (health, metrics,
ops) sets `internal: true` in its per-resource yaml (mirrored on the
inventory entry): the validator then accepts its empty trace lists at
`status: complete` and reports the waiver as a warning, so the choice
stays visible.

For backward compatibility, if a per-surface yaml predates the
SCR-NNN convention and has no `id` field, the validator falls back to
its `surface_id` slug — but new sessions should migrate the surface
file to carry an `id: SCR-NNN`.

Uncovered surfaces follow the same warnings + draft-forcing rules as
features. Soft notes are appended to `api_warnings` as
`"WRN-NNN: coverage: SCR-<N> has no endpoint trace"`.

### Entity-link check

For every resource (in the inventory and in each per-resource yaml),
the validator checks that `primary_entity` exists in
`DATA-MODEL.yaml.entities`. The check accepts two DATA shapes:

```yaml
# Shape A — map keyed by entity name
entities:
  User: { ... }
  Order: { ... }

# Shape B — list with `name` per item
entities:
  - name: User
  - name: Order
```

`primary_entity: null` is always valid (cross-cutting resources like
`/search` or `/health`).

If `DATA-MODEL.yaml` is missing, the entity-link check is skipped
with a printed warning. The agent should refuse to set
`metadata.status: complete` in that case unless the user has been
warned and explicitly accepts the gap.

### Integration contracts

NOT skipped at `api_kind: none` — an integration-only CLI/library still
calls outbound providers. For every `external_dependencies` entry (top
level, or under each `products.<slug>` in monorepo mode), the validator
reads `integration_ref` and requires it to be a well-formed `INT-NNN` id
that exists in `PRD.functional_requirements.integrations_required`:

- No `integration_ref` at all, or a malformed one: reported as a
  format/missing error.
- A well-formed `integration_ref` that does not resolve in `PRD.yaml`:
  reported as a dangling-reference error naming the PRD list to extend
  — never mint an INT-NNN here (CLAUDE.md §4).

Both cases block `status: complete` from `api_version` 2.0; below 2.0
they only warn (CLAUDE.md §10). The check is vacuous on an empty or
null `external_dependencies` list, so a `none`-kind file with no
outbound integrations is unaffected. `metadata.applicability:
not_applicable` is valid only when `api_kind: none` AND
`external_dependencies` is empty/null (SKILL.md Phase 4 step 2): a
`none`-kind file that DOES declare `external_dependencies` stamps
`applicable`, not `not_applicable`.

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
- Tell the user the workflow finished and where the artifacts live:
  *"API spec written: `docs/API.yaml` plus N resource files. CLAUDE.md
  pointer updated. The downstream `sdlc:arch` skill can now consume
  these artifacts."*

> **Field-level errors are the one thing you show verbatim** — the field path
> *is* the fix, so paraphrasing it costs the user the answer. Everything else
> the validator prints gets translated, not pasted: coverage gaps, warnings and
> cross-check findings become one plain sentence each (what happened, why it
> matters, what to do). See CLAUDE.md section 14 and
> `sdlc/skills/prd/references/reporting-to-the-user.md`.
