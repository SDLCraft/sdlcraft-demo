# Paradigm: relational (SQL)

Postgres, MySQL, SQLite, SQL Server, Oracle. The default paradigm — and the
fallback when no other paradigm's signal dominates. A normalized schema of
tables with typed columns, foreign keys, and a query planner that serves
ad-hoc multi-field queries.

## When to recommend

Recommend `relational` when the PRD shows any of:

- **Ad-hoc, multi-field queries** — reports, filters, joins across several
  entities. A planner earns its keep here.
- **Transactional integrity matters** — money, inventory, bookings; anything
  where a half-applied multi-row change is unacceptable.
- **Moderate, interconnected entity set** with clear foreign-key relationships
  (orders→line_items→products) but not so deeply traversal-centric that a
  graph wins.
- **No dominant signal for another paradigm.** Relational is the safe, boring,
  correct default. Prefer it unless a non-relational signal is strong and
  specific. Most CRUD web apps and SaaS backends land here.

Lean **away** from relational when: the product is a single-user CLI with no
server (→ file_native), the core query is semantic similarity (→ vector),
the data is overwhelmingly about traversal/relationships (→ graph), or access
is exclusively single-key lookups at very high scale (→ key_value).

`storage_preferences` in the PRD naming Postgres/MySQL/etc. is a strong `✓ found`
signal — honor it.

## Entity-field shape

Standard SQL columns. For each field:

```yaml
fields:
  id:
    type: uuid            # uuid|string|text|int|bigint|decimal|float|bool|
                          # date|time|timestamp|timestamptz|json|jsonb|enum|
                          # binary|blob|array|other
    nullable: false
    primary_key: true
    unique: true
    default: "now()"      # codegen/SQL default expression
    references: User.id   # FK target "Entity.field"
    on_delete: cascade    # cascade|restrict|set_null|no_action
    check: "amount > 0"   # column check constraint
    comment: "…"
```

`primary_key` is **required** per entity (single field name or list for a
composite key).

## Themes to run (Phase 6)

This paradigm uses the `data-questions.yaml` themes directly — no analogue
themes from this file. The applicable themes are:

- Universal: `persistence`, `entities`, `enums_and_lookups`,
  `data_classification`, `seed_and_fixtures`, `external_data_sources`,
  `audit_and_lifecycle`, `versioning_and_history`, `caching_layer`,
  `search_and_analytics`.
- Relational structural: `id_strategy`, `relationships`,
  `indexes_and_queries`, `integrity_and_constraints`, `scale_and_retention`,
  `migrations_and_evolution`, `transactions_and_consistency`.

## Validator notes

Required (status: complete): `id_strategy.scheme`, `relationships` (key present,
empty OK), `indexes_and_queries.access_patterns` (present, empty OK),
`integrity_and_constraints.default_on_delete`. Cross-checks: relationship
integrity (from/to/join_table resolve; N:M needs a join_table entity), field
references resolve, volume-vs-scale gate when PRD volume is TB/PB.
