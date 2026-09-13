# Polyglot persistence

When the project uses more than one durable store (or the primary store
plus a cache, search engine, or queue), the data model has to make that
explicit. Read this when the user opts into `persistence.polyglot: true`
in Phase 4, or when PRD storage preferences imply multiple stores.

## Paradigm vs polyglot

`persistence.paradigm` describes the **primary** store's shape — the source of
truth that the `entities` block and the paradigm-analogue themes model. A
polyglot setup adds **secondary stores**, and a secondary may be a *different*
paradigm from the primary. The most common cross-paradigm case:

- **Primary relational/document/file + secondary vector** — the canonical RAG
  shape. The source of truth is rows/documents/files; a vector store is a
  derived semantic index, rebuilt from the primary. Pick the primary paradigm
  for `persistence.paradigm`, model entities there, and record the vector store
  under `secondary_stores` (`kind: vector`, role: `search` or `other`) with a
  one-line note on what gets embedded and how the index is rebuilt. Only choose
  `vector` as the *primary* paradigm when similarity search dominates and
  there's little other state (see `references/paradigms/vector.md`).
- **Primary relational + secondary key_value (cache)** or **+ graph (a
  recommendation/relationship sidecar)** follow the same rule: primary paradigm
  models the truth; the secondary is derived and noted, not modeled as a full
  second `entities` block.

Do NOT set `persistence.paradigm` to two values or run two full paradigm
interviews. One primary paradigm; secondaries are described, not re-modeled.

## Why split at all

Most "polyglot" setups are really one primary store plus auxiliary
infrastructure:

- **Primary durable store** — source of truth. Almost always exactly one.
- **Cache** — Redis, Memcached. Derived, evictable, ideally not the
  source of truth for anything.
- **Search index** — Elasticsearch, OpenSearch, Meilisearch. Derived
  from the primary; can be rebuilt.
- **Queue / event bus** — Kafka, RabbitMQ. Carries events; not where
  entities live.
- **Analytics warehouse** — BigQuery, Snowflake. Derived; populated via
  CDC from the primary.
- **Blob store** — S3, GCS, Azure Blob. Holds files referenced by ID from
  the primary.

True multi-source-of-truth (e.g. orders in Postgres + payments in a
separate ledger DB) is rare and should be flagged with explicit
rationale. Model the second authoritative store as a secondary store
with `role: source_of_truth` (and a `kind` family such as `relational`),
NOT `role: primary` — the single main store always belongs in
`primary_store` (or the per-product `primary_store` in monorepo mode).
`source_of_truth` makes the multi-SoT decision a typed signal downstream
consistency/transaction reviews can act on.

## What to capture in DATA-MODEL.yaml

```yaml
persistence:
  primary_store: postgres
  primary_store_rationale: "Strong transactional needs; team fluent."
  polyglot: true
  secondary_stores:
    - kind: redis
      role: cache
      rationale: "Cache hot reads on User and Project entities; ttl-driven invalidation."
    - kind: elasticsearch
      role: search
      rationale: "Postgres FTS scales to ~5M rows; we expect 50M+."
    - kind: kafka
      role: queue
      rationale: "Decouples event consumers; supports CDC outbox."
    - kind: vector            # family fallback — concrete engine in rationale
      role: search
      rationale: "Semantic search over Document embeddings; qdrant, rebuilt from Postgres."
  file_blob_store: s3
  file_blob_store_bucket: "acme-uploads"
```

Then make sure each secondary store has a downstream block that explains
*what* lives there:

- Redis → `caching_layer.cached_entities`
- Elasticsearch / OpenSearch / etc. → `search_and_analytics.fulltext_engine`
  + `indexed_entities`
- Kafka / RabbitMQ → typically captured in `search_and_analytics.cdc_strategy`
  (e.g. `outbox` or `debezium`)
- Blob store → field-level `references` or a dedicated `Attachment` entity
  with a `blob_url` field

## Interview script for secondary stores

When `persistence.polyglot: true` (Phase 6, `persistence` theme):

1. **List the stores** — for each, ask: kind, role, rationale.
2. **Map to downstream themes** — for each secondary store, automatically
   *promote* the relevant downstream theme to "now" (instead of letting
   the user skip it):
   - kind=redis or memcached → `caching_layer` theme runs.
   - kind ∈ {elasticsearch, opensearch, meilisearch, typesense} →
     `search_and_analytics.fulltext_engine` is pre-set; `search_and_analytics`
     theme runs.
   - kind ∈ {kafka, rabbitmq} → `search_and_analytics.cdc_strategy` is
     pre-set to `outbox`; `transactions_and_consistency` may need
     attention.
   - kind=clickhouse or duckdb → `search_and_analytics.analytics_target`
     pre-set.
3. **Surface coordination concerns** — write a `data_warnings` note
   for each secondary store reminding downstream agents:
   - `"Redis cache: invalidation strategy is per-entity (see caching_layer.cached_entities)."`
   - `"Elasticsearch search: full-text index is rebuilt from Postgres; downtime tolerable."`
   - `"Outbox CDC: every write to <entity> must publish an event in the same transaction."`

## Anti-patterns to challenge

If the user proposes:

- **Two primary stores for the same entity** ("Orders live in both
  Postgres and DynamoDB") — challenge: which is source of truth? If the
  answer is "both," that's eventual consistency hell. Suggest one
  primary + the other as a denormalised projection.
- **Cache as source of truth** ("just store sessions in Redis") — fine,
  but call it out. Mark the session entity as
  `persistence.primary_store: redis` for that specific entity (use a
  per-entity override; see `entities.<Name>.fields.*.references` patterns
  or a `_storage_hint` comment).
- **Queue as a store** ("we put events in Kafka and read them back") —
  Kafka is a transport, not a store. The events need a durable home
  (the primary or a dedicated event store).
- **No invalidation plan for a cache** — every cached entity must have
  an explicit invalidation strategy or a TTL. Otherwise users see stale
  data forever.

## Blob store specifics

When `persistence.file_blob_store` is non-`none`:

- Decide where the blob URL/ID lives. Two patterns:
  - Inline on the parent entity (e.g. `User.avatar_url: string`).
  - Dedicated `Attachment` entity with `parent_type`, `parent_id`,
    `blob_url`, `mime_type` — useful when many entities have attachments.
- Tag the URL/ID field with appropriate `data_classification` (often
  `regulated_fields` for uploaded documents in healthcare/finance).
- Plan deletion: if the parent row is soft-deleted, what happens to the
  blob? Record this in `audit_and_lifecycle.archive_strategy`.

## Single-store sanity check

Before letting the user commit to polyglot, ask once: "Can this be served
by a single Postgres / single store with extensions (Postgres FTS, JSONB,
pg_partman)?" Many "we need Redis" decisions evaporate when the actual
QPS is measured. Surface this in `data_warnings` if the user defers the
question.
