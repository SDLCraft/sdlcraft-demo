# Paradigm: file_native (Pydantic models → YAML/JSON on disk)

No database server. The domain model is a set of Pydantic models serialized as
human-readable YAML/JSON files on the filesystem. Identity is derived from the
on-disk path, not a generated key. This is the paradigm the project's own
`docs/DATA-MODEL.yaml` was hand-overhauled into — it is the reference example.

`persistence.primary_store: filesystem`, `persistence.serialization_format:
yaml|json`.

## When to recommend

Recommend `file_native` when the PRD shows:

- **Single-user / single-process tool**, especially a CLI — no concurrent
  writers, so no need for a DB's locking/transactions.
- **Git-friendly, diffable artifacts** are a stated value — users want to read,
  edit, and version the data by hand.
- **Small, bounded data volume** — hundreds or low thousands of records, not
  millions. (TB/PB → never file_native.)
- **Pipeline / artifact-chain shape** — each stage emits a structured document
  consumed by the next (the AICF/SDLC factory itself is the canonical case).
- **No ad-hoc query requirement** — access is "load this artifact by its known
  path," not "find all X where Y."

Lean away when: there are concurrent writers, ad-hoc queries across records,
or volume beyond what fits comfortably in memory/files.

## Entity-field shape

Fields carry a **literal Python type expression** + a description — NOT a SQL
`type` enum, NO `nullable`/`unique`/`primary_key`. Optionality is encoded in
the type itself (`Optional[...]`).

```yaml
entities:
  ProductRequirements:
    description: "Stage 02 output — the master requirements artifact."
    category: stage_artifact        # free-string discriminator (your taxonomy)
    composes: [ArtifactBase]        # Pydantic mixins this model extends
    serialization:
      scope: per_stage              # per_stage|per_project|nested_in:<E>|runtime_only
      filename_pattern: "02_product_requirements.yaml"
    fields:
      product_name:
        pydantic_type: str
        description: "Human-readable product name."
      must_have_features:
        pydantic_type: list[FeatureSpec]
        description: "FR-NNN entries; ID-anchored for downstream stages."
    traces_prd_features: [FR-001]
    traces_ux_surfaces: []
```

Promote nested sub-models (e.g. `FeatureSpec`) to first-class entries with
`category: sub_model` and `serialization.scope: nested_in:<Parent>` — they are
never serialized standalone.

**No `primary_key`** — the validator does not require it for file_native.

## Analogue themes to run (Phase 6)

Replace the relational structural themes with these:

1. **identity_conventions** (REQUIRED) — state how identity is derived without
   keys. Ask: "How is each entity identified on disk?" Capture a `rules` list,
   e.g. *"stage_artifact: identity is the path (stage_ref + project); no id
   field"*, *"sub_model: carries its domain ID string (FR-NNN); no UUIDs"*.

2. **composition** — parent→child containment. For each containment:
   `{parent, child, kind: embeds|contains|references, comment}`. Drives how
   codegen nests Pydantic models.

3. **cross_references** — string-ID references between models (the input
   contract for referential-integrity gates). Each: `{from_entity, field,
   to_entity OR references_family, gate?}`. Use `references_family` (FR, ENT,
   …) when the reference points at an upstream PRD/UX ID family rather than a
   local entity.

   **Gate-clause sweep (run before closing this theme).** If the catalogue
   presents itself as the edge-table schema that referential/coverage gates
   consume, it must actually contain a row for every field those gates query
   — an incomplete edge table makes each missing gate clause mechanically
   unenforceable while the artifact still *looks* authoritative. Before
   closing:

   a. **Enumerate the gate clauses.** Collect every referential / coverage /
      lint clause named anywhere upstream: PRD FRs that describe validation
      gates ("every X.field must resolve to…", per-clause lint requirements),
      `PRD.conventions` buckets that mandate ID resolution, and any `gate:`
      names already used in this table.
   b. **Extract the queried fields.** For each clause, list the concrete
      `Entity.field` pairs it reads (e.g. a gate that checks
      `Component.api_refs` / `Component.implements_requirements` queries
      those two fields).
   c. **Demand a row or a carve-out for each.** Every queried field gets
      EITHER a `cross_references` row (`from_entity` + `field` +
      `to_entity`/`references_family`, with `gate:` naming the clause) OR an
      explicit carve-out: a `data_warnings` `WRN-NNN` entry naming the field,
      why no id-family row fits, and where its read-model home is.
   d. **Non-id-family relations get a declared home too.** A reference that
      travels as something other than a single ID string — a composite tuple
      (e.g. a `(component, name)` address), a path, a content hash — cannot
      be a normal row, but silence is not an option either: add a row with a
      `comment` describing the tuple resolution rule, or the `WRN-NNN`
      carve-out from (c). Downstream gate-writers must find every relation's
      contract *somewhere*.

   The sweep is cheap (one reflective pass over clauses you have already
   read) and it is the difference between "exclusive edge-table schema" being
   a property and being a caption.

4. **serialization_conventions** — where artifacts live so the tree is
   human-readable. `{root_path, format, entries: [{entity, filename_pattern,
   scope}]}`. (Per-entity placement may also live inline on
   `entities.<E>.serialization`.)

Skip-instead: `id_strategy`, `relationships`, `indexes_and_queries`,
`integrity_and_constraints`, `scale_and_retention`, `transactions_and_
consistency`, `migrations_and_evolution` (file_native handles evolution via
`metadata.schema_version` + forward-migration scripts; mention this in a
`data_warnings` note rather than running the SQL migration theme).

## Validator notes

Required (status: complete): `identity_conventions` (with a non-empty `rules`
list). Cross-checks: composition parent/child resolve to entities;
cross_references' `from_entity`/`to_entity` resolve (or `references_family` is
set). No relationship/index/constraint/volume checks run.
