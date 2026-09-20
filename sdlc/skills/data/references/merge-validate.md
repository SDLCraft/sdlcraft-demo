# Merging, validating, and closing out

Detailed rules for Phase 7 (write & validate) and Phase 8 (refresh & close). Read this when entering Phase 7.

## Merging into an existing DATA-MODEL.yaml

If `docs/DATA-MODEL.yaml` already exists at the project root:

- Load it as the baseline.
- Merge the session's confirmed answers on top:
  - **Keys present in both** — overwrite *only* if the user changed the
    value during this session. Otherwise keep the existing value.
  - **New keys** — add them.
  - **Keys the session would remove** (rare; only if the user explicitly
    cleared a value) — ask the user to confirm before deleting.

If the user manually edited `docs/DATA-MODEL.yaml` between sessions and
the state file disagrees on a specific key, surface the conflict — do
NOT silently pick one:

> "Conflict on `entities.User.fields.email.unique`:
>   DATA-MODEL.yaml has: `true`
>   Interview state has: `false` (set at <timestamp>)
> Which should I keep?"

Always preserve **unrelated keys** in `DATA-MODEL.yaml` even if you don't
recognize them. The validator's `extra="allow"` config means custom keys
are tolerated.

## Entity rename / removal — the dangerous merge cases

These are where DATA-MODEL merge differs from PRD merge. Entities are
referenced from many places (relationships, data_classification,
bounded_contexts, indexes_and_queries, search_and_analytics,
caching_layer, external_data_sources.maps_to_entity — PLUS, by paradigm,
edges, composition, cross_references, graph_config.node_labels, and
key_value_design.key_patterns). When the user **renames** or **removes** an
entity in this session, the merge must either propagate the change or warn
loudly.

**Rename `X → Y`**:

1. Rewrite `entities.X` → `entities.Y` (key change).
2. Walk every other block:
   - `relationships[*].from_entity / to_entity / join_table`: replace `X` with `Y`.
   - `data_classification.{pii_fields, regulated_fields, encrypted_at_rest}`:
     replace `X.<field>` with `Y.<field>`.
   - `bounded_contexts.*.entities`: replace `X` with `Y`.
   - `enums_and_lookups.lookup_tables`: replace `X` with `Y`.
   - `indexes_and_queries.{access_patterns, expected_indexes}[*].entity`:
     replace.
   - `integrity_and_constraints.{unique_constraints, check_constraints}[*].entity`:
     replace.
   - `audit_and_lifecycle.applies_to`, `versioning_and_history.applies_to`:
     replace.
   - `scale_and_retention.retention_policies[*].entity`: replace.
   - `caching_layer.cached_entities[*].entity`: replace.
   - `search_and_analytics.indexed_entities[*].entity`: replace.
   - `external_data_sources[*].maps_to_entity`: replace.
   - `entities.*.fields.*.references` strings containing `X.<...>`:
     rewrite to `Y.<...>`.
   - Paradigm blocks: `edges[*].from_entity / to_entity` and
     `graph_config.node_labels` (graph); `composition[*].parent / child`
     and `cross_references[*].from_entity / to_entity` (document/file_native);
     `key_value_design.key_patterns[*].entity` (key_value);
     `entities.X.node_label` (graph). Replace `X` with `Y`.
3. Show the user a summary of the rewrites before saving.

**Remove entity `X`**:

1. Confirm with the user explicitly: *"Removing `X` will affect N other
   blocks. Continue?"*
2. Walk the same blocks above. For each reference to `X`:
   - In `relationships`: drop the entire relationship row.
   - In `data_classification.*`: drop the entry.
   - In `bounded_contexts.*.entities`: drop from the list (and warn if
     it leaves a context empty).
   - In `entities.*.fields.*.references`: set to `null` and warn the user
     that the FK is now dangling.
3. Append a `data_warnings` entry: *"Entity X removed at <timestamp>; N
   downstream references were also removed."*

If the user is uncertain, the safer move is **soft-removal**: keep `X`
in `entities` with a `description: "DEPRECATED — to be removed in next
session"` and let downstream agents see the deprecation marker.

## Writing the file

Write `docs/DATA-MODEL.yaml` with:

- Inline YAML comments on each top-level key (use `DATA-MODEL.schema.yaml`
  as the template).
- `metadata.data_model_version`: stamp `"3.0"` (or higher) on new writes —
  the version-gated blocking checks (paradigm declared, store ids) arm only
  at/after 3.0; an older stamp silently degrades them to warnings.
- Updated `metadata.last_updated` (ISO-8601 UTC) and `metadata.session_id`.
- `deferrals` (top-level): the structured DEFER half of trace-or-defer
  (CLAUDE.md §6) — one `{id, reason}` entry per PRD requirement
  intentionally out of the data scope. An entry with no reason defers
  nothing. A `WRN-NNN` note may accompany an entry as the human-readable
  companion, never as the machine channel.
- `persistence.secondary_stores[].store_id`: a stable kebab-case id per
  secondary store (unique; `primary` reserved). `entities.<E>.stored_in`
  values must resolve to `primary` or a declared store_id.
- `metadata.status`:
  - Set to `"complete"` only when **all required fields are filled**,
    **every cross-check passes**, and the validator exits with `[OK]`.
  - Set to `"draft"` on early EXIT, when any required field is still null,
    or when a soft cross-check (feature coverage, volume-vs-scale gate)
    reports issues.
- `metadata.changelog` (append-only, most-recent first): on a fresh
  write, omit the field or initialize with a single
  `"<version> (<YYYY-MM-DD>): initial."` entry. On an update-flow
  merge, prepend ONE new entry summarising what materially changed in
  this session (e.g. *"1.1 (2026-05-25): Added BranchSession entity
  per WKF-004 sweep; rewired SCR traces."*). The validator only
  type-checks `Optional[list[string]]`; format is convention, not
  enforced — over-validating here would discourage manual edits, which
  are explicitly allowed.
- `data_warnings`: every entry MUST be `"WRN-NNN: <message>"`. The
  WRN counter lives in `state.last_ids.WRN`; increment-then-write per
  appended item. Counter drift is covered by the canonical resume recipe
  (`${CLAUDE_SKILL_DIR}/../prd/references/edge-cases.md` → "Resume with
  stale state"; AUTHORING §5's `max(state counter, highest id present on
  disk)`), not restated here. Used for low-confidence answers, merge
  conflicts, deferred themes, classification orphans flagged in error
  recovery, deferred sweep candidates, etc. — not for required-field
  acknowledgement.

## Running the validator

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/DATA-MODEL.yaml
```

Exit codes:

| Code | Meaning | What the agent does |
|---|---|---|
| 0 (`[OK]`) | Complete and valid; all cross-checks pass | ✓ Proceed to Phase 8. |
| 0 (`[DRAFT]`) | Draft — structurally valid, possibly missing required fields or with soft-check warnings | Inform user and proceed to Phase 8. |
| 1 (`[FAIL]`) | Schema invalid, OR `status: complete` but required fields missing, OR `status: complete` but a hard cross-check failed (relationship integrity, paradigm structural integrity, classification integrity, bounded-context partition) | Show field-level errors verbatim. If required fields are missing, offer via `AskUserQuestion`: fill them in now, or accept `status: draft`. If a cross-check failed, walk the user through the offending block (e.g. show the relationship that references a nonexistent entity). Re-run validation after re-entry. |
| 2 | Cannot read/parse the file | Surface to user (missing file, bad YAML, permission error). Do not retry silently. |
| 3 | Missing dependency | Validator prints `pip install` instructions. Do **not** auto-install — ask the user to install and re-run. |

**Downstream-agent contract**: downstream agents (api, arch, test) MUST
reject the DATA-MODEL if `metadata.status != "complete"` OR if
`validate_schema.py` exits non-zero. The one exception is to the exit code,
never to the status: a failure every check of which
`doctor.py --artifact docs/DATA-MODEL.yaml` reports as accepted deviance does
not reject (`${CLAUDE_SKILL_DIR}/../repair/references/accepted-deviance.md`).

## Cross-check recovery flows

The validator reports the following check categories. Each has a
different recovery path:

| Cross-check                       | If hard-fail at status:complete   | Recovery |
|-----------------------------------|-----------------------------------|----------|
| Required fields missing           | FAIL                              | Re-enter via AskUserQuestion |
| `data_warnings` WRN-NNN format    | FAIL                              | The writer is at fault: re-prefix any bare entry with the next `state.last_ids.WRN` id |
| Entity trace ID-format (FR / SCR / WKF) | FAIL                          | Show the offending field; if a kebab slug snuck into `traces_ux_surfaces`, replace with the matching `UX.surface_inventory[].id` (SCR-NNN) |
| Relationship integrity (relational) | FAIL                            | Show the relationship, ask user to fix from_entity / to_entity / join_table |
| Field references                  | FAIL                              | Show entity.field.references, ask user to correct |
| Paradigm structural integrity     | FAIL                              | Paradigm-specific: graph→edge endpoint resolves to a node; document/file_native→composition parent/child + cross_reference from/to resolve; vector→vector_config has embedding_model+dimensions+distance_metric; file_native→identity_conventions.rules non-empty; key_value→key_value_design.key_patterns non-empty + entity resolves. Show the offending block, re-enter. |
| Classification integrity          | FAIL                              | Show offending Entity.field in pii_fields/regulated_fields/encrypted_at_rest |
| Bounded-context partition         | FAIL                              | Show unassigned/duplicate entities, ask to reassign |
| Feature coverage                  | Soft — force draft, warn          | Walk uncovered FR-NNN list, ask to assign each to ≥1 entity OR defer it structurally: append `{id, reason}` to the top-level `deferrals` list. An entry with no reason defers nothing. A `WRN-NNN` prose mention still counts for one more version but is reported as prose-only — never write a new one as the deferral channel |
| Volume-vs-scale gate              | Soft — force draft, warn          | Prompt user to fill scale_and_retention partitioning/sharding/retention |
| Mode mismatch                     | FAIL (pydantic)                   | Refuse to write; ask user to fix the structural state in Phase 4 |

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
- Tell the user where the artifacts live and which downstream skills
  can now run: *"Done. `docs/DATA-MODEL.yaml` is valid and complete. You
  can now run `/sdlc:api` to define the API contract that fronts these
  entities."*

> **Field-level errors are the one thing you show verbatim** — the field path
> *is* the fix, so paraphrasing it costs the user the answer. Everything else
> the validator prints gets translated, not pasted: coverage gaps, warnings and
> cross-check findings become one plain sentence each (what happened, why it
> matters, what to do). See CLAUDE.md section 14 and
> `${CLAUDE_SKILL_DIR}/../prd/references/reporting-to-the-user.md`.
