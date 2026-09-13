# Paradigm: key_value

DynamoDB, Redis-as-primary, etcd. Access-pattern-FIRST design: you enumerate
the exact lookups the app makes, then design partition/sort keys (and secondary
indexes) so every lookup is a direct key hit. There is no query planner and no
ad-hoc querying — if an access pattern wasn't designed for, it isn't cheap.

## When to recommend

Recommend `key_value` when the PRD shows:

- **A small, fixed set of access patterns**, each a lookup by a known key
  ("get session by id", "list a user's events newest-first").
- **Very high scale / throughput** with predictable latency requirements —
  key-value stores stay flat where relational degrades.
- **No ad-hoc reporting / analytics on the operational store** (those go to a
  secondary analytics target).
- Session stores, event logs, feature flags, caches-as-source-of-truth,
  high-write telemetry.

Lean away when the PRD wants flexible queries, joins, or reporting on the live
data (→ relational/document). If key_value is the operational store but
analytics are needed, that's polyglot: key_value primary + an analytics
secondary (see `polyglot-persistence.md`).

## Entity-field shape

Plain typed fields (reuse the relational `type`/`nullable` attributes). There
is **no `primary_key`** at the entity level — identity is expressed through the
key templates in `key_value_design`. List every attribute the item carries.

## Analogue themes to run (Phase 6)

1. **key_value_design** (REQUIRED) — the core of this paradigm. Walk the PRD's
   access patterns and, for each entity, capture:

   ```yaml
   key_value_design:
     key_patterns:
       - entity: Session
         key_template: "user#{user_id}#session#{session_id}"
         partition_key: user_id
         sort_key: session_id
     secondary_indexes:        # e.g. DynamoDB GSIs — one per extra access pattern
       - name: GSI1-by-session
         partition_key: session_id
         projection: ALL
   ```

   Challenge each access pattern: which key serves it? If an access pattern has
   no key/index that serves it, that's a design gap — surface it (a GSI, a
   denormalized copy, or a rethink).

Skip-instead: `id_strategy`, `relationships`, `indexes_and_queries` (replaced
by key_value_design), `integrity_and_constraints`,
`transactions_and_consistency`, `migrations_and_evolution`.

## Validator notes

Required (status: complete): `key_value_design` with a non-empty `key_patterns`
list; each pattern's `entity` must resolve to an entity. Volume-vs-scale gate
applies (key_value is a high-scale paradigm).
