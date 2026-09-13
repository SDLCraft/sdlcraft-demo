# Pre-fill sources — PRD/UX → DATA-MODEL field map

A deterministic table the agent follows in Phase 3 and Phase 5. Each row
says: "this PRD/UX field maps to this DATA-MODEL field, with confidence
`✓ found` or `⚠ inferred`."

Read this in Phase 3 (when building the pre-fill map) and again in
Phase 5 (when presenting pre-fills for confirmation).

## Top-level mappings

| PRD / UX source                                                        | DATA-MODEL target                                  | Confidence tag |
|------------------------------------------------------------------------|----------------------------------------------------|----------------|
| `PRD.metadata.monorepo`                                                | `metadata.monorepo`                                | ✓ found        |
| `PRD.data_model.key_entities[*]` — "ENT-NNN: <Name>"                   | `entities` keys (strip ENT prefix, keep PascalCase `<Name>`) | ⚠ inferred (the user already named the entity, but agent must confirm fields and traces) |
| `PRD.data_model.key_entities[*]` — keep the ENT-NNN id                 | `state.defined_entities[].ent_id` (for the sweep)   | ✓ found        |
| `PRD.data_model.storage_preferences[0]`                                | `persistence.primary_store`                        | ✓ found        |
| `PRD.data_model.storage_preferences[1+]`                               | `persistence.secondary_stores` (and `polyglot: true`) | ✓ found     |
| `PRD.data_model.storage_preferences` mentions "S3"/"GCS"/"Azure Blob"  | `persistence.file_blob_store`                      | ⚠ inferred     |
| `PRD.data_model.storage_preferences_rationale`                         | `persistence.primary_store_rationale`              | ✓ found        |
| `PRD.data_model.data_ownership`                                        | `data_warnings` note (downstream visibility — `"WRN-NNN: data_ownership: <value>"`) | ✓ found        |
| `PRD.data_model.data_volume_estimate`                                  | gates `scale_and_retention` promotion              | ✓ found        |
| `PRD.functional_requirements.features[*]` (FR-NNN id)         | candidate `entities.*.traces_prd_features` (verbatim FR-NNN, no description text) | ⚠ inferred     |
| `PRD.use_cases.core_workflows[*]` (WKF-NNN id)                         | candidate `entities.*.traces_prd_workflows` (verbatim WKF-NNN); sweep seed | ⚠ inferred |
| `PRD.functional_requirements.integrations_required`                    | `external_data_sources[*].name`                    | ✓ found        |
| `PRD.security_compliance.data_sensitivity`                             | `data_classification.regulated_fields` heuristic   | ⚠ inferred     |
| `PRD.security_compliance.regulatory_requirements: [gdpr, ccpa]`        | `data_classification.pii_fields` default scope     | ⚠ inferred     |
| `PRD.security_compliance.regulatory_requirements: [hipaa]`             | `data_classification.regulated_fields` (PHI scope) | ⚠ inferred     |
| `PRD.security_compliance.regulatory_requirements: [pci_dss]`           | `data_classification.regulated_fields` (PCI scope) | ⚠ inferred     |
| `PRD.security_compliance.data_sensitivity: phi` (PRD 1.1)              | `data_classification.regulated_fields` (PHI scope); promotes the question | ⚠ inferred |
| `PRD.security_compliance.data_sensitivity: pci` (PRD 1.1)              | `data_classification.regulated_fields` (PCI scope); promotes the question | ⚠ inferred |
| `PRD.internationalization.enabled: true` (PRD 1.1)                     | `data_classification.localized_fields` — promotes the question; candidates = every user-visible text field | ⚠ inferred |
| `PRD.glossary.terms[*].term` (PRD 1.1)                                 | entity / field naming candidates (the synonyms are the names to avoid) | ⚠ inferred |
| `PRD.security_compliance.encryption_at_rest: true`                     | encourages `data_classification.encrypted_at_rest` non-empty | ✓ found |
| `PRD.security_compliance.audit_logging: true`                          | promotes `audit_and_lifecycle` theme to "now"      | ✓ found        |
| `PRD.non_functional_requirements.scalability ∈ [large, hyperscale]`    | promotes `scale_and_retention` to "now"            | ✓ found        |
| `PRD.technical_constraints.primary_language: python` + `pyproject.toml` has `alembic` dep | `migrations_and_evolution.tool: alembic` | ⚠ inferred |
| `PRD.technical_constraints.primary_language: typescript` + `prisma` dep | `migrations_and_evolution.tool: prisma_migrate`   | ⚠ inferred     |
| `UX.surface_inventory[].id` (SCR-NNN) + `references_entities`          | reverse-trace: write the SCR-NNN to the entity's `traces_ux_surfaces` | ⚠ inferred |
| `UX__<surface>.layout` form fields                                     | candidate entity fields (names + types)            | ⚠ inferred     |
| `UX__<surface>.validation_rules[].field` + `.rules`                    | entity field constraints (nullable, unique, regex) | ⚠ inferred     |
| `UX__<surface>.components.content_slots` (label, placeholder)          | candidate entity field name + comment              | ⚠ inferred     |
| `UX__<surface>.interactions.effects` matching `create/update/delete X` | trace surface (SCR-NNN) → entity                   | ⚠ inferred     |

### About `PRD.conventions`

`PRD.conventions` is a project-defined `Dict[str, Any]` — its bucket
names and sub-shapes are not fixed. Do NOT assume specific bucket names
(e.g. `artifact_ids` or `nfr_propagation`) exist. If the PRD does
carry an `nfr_propagation`-style bucket that names "Data Model" or
"FR-007" as a consumer of certain PRD fields, treat that as a
verbatim directive (read those PRD fields and pre-fill the DATA-MODEL
sections it points at). When unsure, surface the bucket name to the
user and ask whether it applies.

## Repo signals (Phase 2 scan)

If the consumer project's repo already contains schema artifacts, the
data skill **respects them as authoritative** (`✓ found`):

| Repo signal                                            | DATA-MODEL target                          |
|--------------------------------------------------------|--------------------------------------------|
| `schema.prisma` model blocks                            | `entities.<Name>` with full fields         |
| `alembic.ini` + `migrations/`                          | `migrations_and_evolution.tool: alembic`   |
| `db/migrate/*.rb` (Rails)                              | `migrations_and_evolution.tool: activerecord` |
| `prisma/migrations/`                                   | `migrations_and_evolution.tool: prisma_migrate` |
| `models/` with SQLAlchemy `Base` subclasses            | `entities.<Name>` candidates               |
| `db/seeds.rb` / `prisma/seed.ts` / `fixtures/`         | `seed_and_fixtures.seed_strategy`, `dev_fixtures_path` |
| `redis` in `requirements.txt` / `package.json`         | `caching_layer.layer: redis`, `polyglot: true` |
| `elasticsearch` / `opensearch-py` in deps              | `search_and_analytics.fulltext_engine`     |
| Docker compose with `postgres:` service                | `persistence.primary_store: postgres`      |
| `.env.example` with `DATABASE_URL=postgres://`         | `persistence.primary_store: postgres`     |
| `.env.example` with `KMS_KEY=` or `KMS_ARN=`           | `data_classification.encryption_kms_ref`   |

## Inferred entities — quick rules

When deriving entities from `features`, follow the heuristics
in `entity-discovery.md`. The key rule for pre-fill: **every entity from
the PRD-key_entities list is `✓ found`; every entity derived from
features or UX is `⚠ inferred`**. The user must confirm the latter
individually in Phase 3, not as a batch.

## Confidence semantics

When writing pre-filled values to `DATA-MODEL.yaml`:

- User explicitly confirmed a `⚠ inferred` candidate →
  `<field>_confidence: confirmed`.
- User accepted a `⚠ inferred` candidate without correction (e.g.
  pressed Enter on the recommended option) → `<field>_confidence: inferred`.
- User left an inferred value as-is via batch-accept shortcut → **NOT
  ALLOWED** for `⚠ inferred` items. Force individual confirmation.
- User confirmed a `✓ found` candidate → `<field>_confidence: confirmed`.
- User batch-accepted a `✓ found` candidate (via "ok") → omit the
  confidence field or set `confirmed` (both are acceptable).

This split lets downstream agents see which choices were thought through
vs accepted on autopilot. Important: if a downstream `arch` or `api`
skill sees a stack of `inferred` confidence tags, it should challenge them
before designing on top.

## When pre-fill maps don't apply

Skip a row if:

- The source field is empty/null in PRD or UX.
- The source field's value doesn't unambiguously map (e.g.
  `storage_preferences: ["No preference — recommend"]`).
- The user already has a `docs/DATA-MODEL.yaml` and the existing value
  conflicts. In that case, surface the conflict for human resolution
  rather than silently overriding.
