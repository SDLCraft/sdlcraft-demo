"""Validate DATA-MODEL.yaml against the canonical sdlc-data schema, and run
cross-checks against the upstream PRD.yaml (feature coverage) plus internal
consistency checks (relationship integrity, classification integrity,
bounded-context partition, volume-vs-scale gate, ID-prefix format).

Run from the project root:

    python sdlc/skills/data/validate_schema.py
    python sdlc/skills/data/validate_schema.py --path docs/DATA-MODEL.yaml

Persistence — two orthogonal axes:
    `persistence.paradigm` (relational | document | key_value | graph | vector |
    file_native | none) is the FAMILY axis — the data shape. It is the
    discriminator that decides which theme blocks are required and which
    cross-checks run. It defaults to `relational` when absent, so
    DATA-MODEL.yaml files written before paradigms existed validate unchanged.
    `none` declares a stateless project (nothing persisted): `entities` may be
    empty or absent, no store is required, and every check that assumes
    persisted state is skipped — the summary says so explicitly instead of
    claiming vacuous coverage.

    `persistence.topology` (local_embedded | networked_server | cloud_managed |
    serverless | in_memory | other) is the orthogonal TOPOLOGY axis — where/how
    the store runs. A single family spans several topologies (a relational
    family may run self-hosted, managed, or embedded), so the two are captured
    independently. `topology` is optional (back-compat) and is NOT a
    discriminator — it never changes the required set; the skill recommends it
    in Phase 4 alongside the paradigm.

Validates:
    1. docs/DATA-MODEL.yaml (or --path) — single-file data model.
    2. Cross-checks (hardness as marked):
       - Required fields present: paradigm-gated (required_paths_for +
         entity_required_paths_for). Failure -> hard error in status:complete.
         relational: id_strategy.scheme, relationships, indexes_and_queries,
         integrity_and_constraints; document: id_strategy + indexes; graph:
         edges; vector: vector_config; key_value: key_value_design; file_native:
         identity_conventions. `primary_key` is required per-entity only for
         relational/document.
       - Relationship integrity (relational): from_entity / to_entity /
         join_table exist in `entities`. Hard error in status:complete.
       - Field references: entities.<E>.fields.<f>.references resolves. Hard.
       - Paradigm structural integrity: edge endpoints (graph), composition
         parent/child, cross_reference from/to, vector_config completeness,
         identity_conventions.rules non-empty, key_value_design.key_patterns
         non-empty + entity resolution. Hard error in status:complete.
       - Classification integrity: every Entity.field in pii_fields /
         regulated_fields / encrypted_at_rest resolves. Failure -> hard error.
       - Bounded-context partition: when bounded_contexts present, every
         entity belongs to exactly one context. Failure -> hard error.
       - Mode-mismatch: monorepo: true requires products:; false forbids it.
         Failure -> hard error (raised by the pydantic model_validator).
       - ID-prefix format: WRN-NNN on every data_warnings entry; FR-NNN on
         every traces_prd_features entry; SCR-NNN on every traces_ux_surfaces
         entry; WKF-NNN on every traces_prd_workflows entry. Hard error in
         status:complete; warning (force draft) otherwise.
       - Feature coverage: every PRD FR-NNN (the flat `features` list, or the
         legacy must-have list) is either traced by some entity's
         traces_prd_features OR explicitly deferred (trace-or-defer,
         CLAUDE.md §6). The DEFER half reads the structured top-level
         `deferrals: [{id, reason}]` list FIRST (alias `deferred_requirements`;
         an entry with no reason defers nothing). An id named as a whole word
         in a data_warnings entry still counts for one more version, and every
         id that fell through to that prose fallback is reported as a warning.
         Skipped under paradigm `none` (nothing stores data) — the summary
         says so. Failure -> force draft (soft).
       - Union integrity: an entity declaring `one_of: [Variant, ...]` is a
         union parent (exempt from the per-entity `fields` / `primary_key`
         requirement - the variants carry them). It must name a
         `discriminator` field, every variant it names must exist in
         `entities`, and every variant must carry that field. Errors at
         data_model_version >= 3.0, warnings below (CLAUDE.md §10; ledger
         IMP-080, aicf LSN-061).
       - Store ids: when persistence.secondary_stores is present, every entry
         needs a unique kebab-case `store_id` ('primary' is reserved for the
         primary store). Missing/duplicate/reserved/malformed ids are errors
         at data_model_version >= 3.0, warnings below (CLAUDE.md §10).
         entities.<E>.stored_in must resolve to 'primary' or a declared
         store_id — unknown ids warn (never block).
       - Lifecycle wiring (warn-level): lifecycle.field exists on the entity;
         terminal states have no outgoing transition; the state set is listed
         in the field's validation.enum (or a declared enum) when one exists.
       - Provenance staleness (warn-level): each metadata.upstream_provenance
         sha256 is compared to the upstream's current hash (INDEX.yaml
         generated_from, else the same 16-hex text hash docs_index.py --hash
         prints). A mismatch warns "built against an older docs/<X>"; a
         `complete` artifact with no provenance at all warns from
         data_model_version >= 3.0.
       - Volume-vs-scale gate (relational/document/key_value): if PRD
         data_volume_estimate in {terabytes, petabytes}, scale_and_retention
         must be non-null. Failure -> force draft (soft).
       - PRD absent: the coverage check cannot run; the validator says so in a
         warning instead of claiming "all 0 requirements accounted for".

Exit codes:
    0 — schema valid; either status='complete' (with all required fields filled
        AND all enabled checks passing) or status='draft'.
    1 — schema invalid (pydantic error), OR status='complete' but required
        fields are missing, OR status='complete' but any cross-check failed.
    2 — could not read or parse the file (missing, bad YAML, etc.)
    3 — required dependency missing (pydantic v2 or pyyaml).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union


# =============================================================================
# User-facing output (CLAUDE.md 14). Three verdict tags, two finding sections,
# one NEXT block - identical across every SDLC script, because the person
# reading them knows only "there is a pipeline and I run it in order".
# Canonical guidance: sdlc/skills/prd/references/reporting-to-the-user.md
# =============================================================================

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"

def join_ids(ids, limit=12):
    """Render a grouped finding's id list. Capped, because a line nobody
    finishes reading has told the user nothing."""
    ids = [str(i) for i in ids]
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown} (+{len(ids) - limit} more)"



def _emit_finding(item, detail_cap=5):
    """One finding. A (headline, details) pair renders as a grouped finding:
    the class in one sentence, then a capped sample. A line nobody finishes
    reading has told the user nothing."""
    if isinstance(item, tuple):
        head, details = item
        print(f"  - {head}")
        for d in list(details)[:detail_cap]:
            print(f"      * {d}")
        if len(details) > detail_cap:
            print(f"      * (+{len(details) - detail_cap} more of the same)")
    else:
        print(f"  - {item}")


def print_findings(blocking, warnings, blocking_header="MUST FIX BEFORE 'complete'"):
    """The two canonical sections. A WARNING never blocks, and says so."""
    warnings = list(warnings or []) + drain_warning_shape_warnings()
    if blocking:
        print(f"\n{blocking_header} ({len(blocking)}):")
        for b in blocking:
            _emit_finding(b)
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}) - none of these block the next skill:")
        for w in warnings:
            _emit_finding(w)


def print_next(*lines, show_glossary=True):
    """Close with what to type next. The glossary pointer only appears when
    there was something to decode."""
    print(f"\nNEXT: {lines[0]}")
    for extra in lines[1:]:
        print(f"      {extra}")
    if show_glossary:
        print(f"      What these labels mean: {GLOSSARY_PATH}")


try:
    import yaml
except ImportError:
    print(
        "ERROR: pyyaml is required.\nInstall with:  pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(3)

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
except ImportError:
    print(
        "ERROR: pydantic v2 is required.\nInstall with:  pip install 'pydantic>=2'",
        file=sys.stderr,
    )
    sys.exit(3)


# =============================================================================
# Enums — kept in lockstep with DATA-MODEL.schema.yaml
# =============================================================================


class Confidence(str, Enum):
    confirmed = "confirmed"
    inferred = "inferred"
    assumption = "assumption"


class Paradigm(str, Enum):
    """Top-level storage paradigm — the *family* axis (the data shape). This is
    the discriminator that selects which theme blocks are required and which
    cross-checks run. Absence defaults to `relational` so pre-paradigm
    DATA-MODEL.yaml files validate unchanged.

    Persistence is modelled as two ORTHOGONAL axes: `paradigm` (family — the
    data shape, here) × `topology` (where/how the store runs — see
    PersistenceTopology). A `relational` family can run `networked_server`
    (self-hosted Postgres), `cloud_managed` (RDS), or `local_embedded`
    (SQLite); the same family spans several topologies, so the two are captured
    independently."""

    relational = "relational"
    document = "document"
    key_value = "key_value"
    graph = "graph"
    vector = "vector"
    file_native = "file_native"
    # A stateless project: nothing is persisted anywhere. `entities` may be
    # empty or absent, no primary store is required, and every check that
    # assumes persisted state (feature coverage, volume gate, per-entity
    # required fields) is skipped — with an explicit summary line, never a
    # vacuous "all covered" claim.
    none = "none"


class PersistenceTopology(str, Enum):
    """Where/how the primary store runs — the axis orthogonal to `paradigm`
    (the family). Concrete provider (RDS vs Cloud SQL vs self-managed) is
    finalized downstream at the deploy stage; this captures the deployment
    shape that the data model assumes. Optional + back-compat: absence means
    "not yet decided", and never changes a pre-topology file's required set."""

    local_embedded = "local_embedded"      # in-process store (SQLite, embedded KV, on-disk files)
    networked_server = "networked_server"  # self-hosted DB server (Postgres/MySQL/Mongo/Neo4j…)
    cloud_managed = "cloud_managed"         # managed DB service (RDS, Cloud SQL, Atlas, DynamoDB…)
    serverless = "serverless"               # serverless data tier (Aurora Serverless, D1, Upstash…)
    in_memory = "in_memory"                  # ephemeral, process-lifetime only (no durable store)
    other = "other"


class PrimaryStore(str, Enum):
    # relational
    postgres = "postgres"
    mysql = "mysql"
    sqlite = "sqlite"
    sqlserver = "sqlserver"
    oracle = "oracle"
    # document
    mongodb = "mongodb"
    firestore = "firestore"
    couchbase = "couchbase"
    # key-value (dynamodb straddles document/key-value)
    dynamodb = "dynamodb"
    redis = "redis"
    etcd = "etcd"
    # graph
    neo4j = "neo4j"
    arangodb = "arangodb"
    neptune = "neptune"
    janusgraph = "janusgraph"
    # vector
    pinecone = "pinecone"
    qdrant = "qdrant"
    weaviate = "weaviate"
    milvus = "milvus"
    chroma = "chroma"
    pgvector = "pgvector"
    lancedb = "lancedb"
    # file-native (Pydantic models serialized to disk)
    filesystem = "filesystem"
    other = "other"


class SecondaryStoreKind(str, Enum):
    # Paradigm families — use when a secondary store is a *different paradigm*
    # than the primary and the concrete engine is TBD / finalized at deploy.
    # A secondary legitimately spans paradigms (see references/polyglot-
    # persistence.md): the canonical RAG shape is primary relational +
    # secondary `vector`; a recommendation sidecar is a secondary `graph`; a
    # rare second source-of-truth ledger is a secondary `relational`. Pick the
    # family here and name the concrete engine in `rationale`. Mirrors the
    # Paradigm family vocabulary, so `relational` is valid as a secondary kind.
    relational = "relational"
    document = "document"
    key_value = "key_value"
    graph = "graph"
    vector = "vector"
    # Specific auxiliary technologies (characteristically deployed as secondary).
    redis = "redis"
    memcached = "memcached"
    elasticsearch = "elasticsearch"
    opensearch = "opensearch"
    meilisearch = "meilisearch"
    kafka = "kafka"
    rabbitmq = "rabbitmq"
    clickhouse = "clickhouse"
    duckdb = "duckdb"
    other = "other"


class SecondaryStoreRole(str, Enum):
    cache = "cache"
    search = "search"
    queue = "queue"
    analytics = "analytics"
    timeseries = "timeseries"
    # A secondary store that is itself authoritative for some subset of data —
    # the rare, deliberate multi-source-of-truth case (e.g. orders in the
    # primary + payments in a separate ledger DB; flag with rationale). This is
    # NOT the main store: that belongs in `primary_store` (or the per-product
    # `primary_store` in monorepo mode). There is deliberately no `primary`
    # role — a *secondary* store cannot be the primary by definition.
    source_of_truth = "source_of_truth"
    other = "other"


class FileBlobStore(str, Enum):
    none = "none"
    s3 = "s3"
    gcs = "gcs"
    azure_blob = "azure_blob"
    minio = "minio"
    local_fs = "local_fs"
    other = "other"


class IdScheme(str, Enum):
    uuid_v4 = "uuid_v4"
    uuid_v7 = "uuid_v7"
    ulid = "ulid"
    nanoid = "nanoid"
    serial_int = "serial_int"
    bigserial = "bigserial"
    natural_key = "natural_key"
    mixed = "mixed"


class FieldType(str, Enum):
    uuid = "uuid"
    string = "string"
    text = "text"
    int_ = "int"
    bigint = "bigint"
    decimal = "decimal"
    float_ = "float"
    bool_ = "bool"
    date = "date"
    time = "time"
    timestamp = "timestamp"
    timestamptz = "timestamptz"
    json_ = "json"
    jsonb = "jsonb"
    enum = "enum"
    binary = "binary"
    blob = "blob"
    array = "array"
    other = "other"

    @classmethod
    def _missing_(cls, value: object):
        # Tolerate Python-keyword clashes (int/float/bool/json) by re-mapping
        # the value strings back to the enum members.
        mapping = {
            "int": cls.int_,
            "float": cls.float_,
            "bool": cls.bool_,
            "json": cls.json_,
        }
        if isinstance(value, str) and value in mapping:
            return mapping[value]
        return None


class Cardinality(str, Enum):
    one_one = "1:1"
    one_many = "1:N"
    many_many = "N:M"


class OnDelete(str, Enum):
    cascade = "cascade"
    restrict = "restrict"
    set_null = "set_null"
    no_action = "no_action"


class PartitioningStrategy(str, Enum):
    range = "range"
    list_ = "list"
    hash = "hash"
    none = "none"

    @classmethod
    def _missing_(cls, value: object):
        if value == "list":
            return cls.list_
        return None


class RecordVersioning(str, Enum):
    none = "none"
    row_version = "row_version"
    temporal_table = "temporal_table"
    event_sourcing = "event_sourcing"


class IsolationLevel(str, Enum):
    read_committed = "read_committed"
    repeatable_read = "repeatable_read"
    serializable = "serializable"
    snapshot = "snapshot"


class CachingLayer(str, Enum):
    none = "none"
    in_process = "in_process"
    redis = "redis"
    memcached = "memcached"
    other = "other"


class FulltextEngine(str, Enum):
    none = "none"
    postgres_fts = "postgres_fts"
    elasticsearch = "elasticsearch"
    opensearch = "opensearch"
    meilisearch = "meilisearch"
    typesense = "typesense"


class AnalyticsTarget(str, Enum):
    none = "none"
    bigquery = "bigquery"
    snowflake = "snowflake"
    redshift = "redshift"
    duckdb = "duckdb"
    other = "other"


class CdcStrategy(str, Enum):
    none = "none"
    debezium = "debezium"
    outbox = "outbox"
    trigger = "trigger"
    other = "other"


class MigrationTool(str, Enum):
    alembic = "alembic"
    flyway = "flyway"
    liquibase = "liquibase"
    prisma_migrate = "prisma_migrate"
    drizzle_kit = "drizzle_kit"
    sqlx = "sqlx"
    knex = "knex"
    django_migrate = "django_migrate"
    activerecord = "activerecord"
    other = "other"


class IndexType(str, Enum):
    btree = "btree"
    hash = "hash"
    gin = "gin"
    gist = "gist"
    fulltext = "fulltext"
    composite = "composite"
    other = "other"


class SyncModel(str, Enum):
    pull = "pull"
    push = "push"
    webhook = "webhook"
    stream = "stream"


class RetentionPolicy(str, Enum):
    hard_delete = "hard_delete"
    archive = "archive"
    anonymize = "anonymize"


# --- paradigm-specific enums --------------------------------------------------


class SerializationFormat(str, Enum):
    yaml = "yaml"
    json = "json"
    toml = "toml"
    other = "other"


class CompositionKind(str, Enum):
    embeds = "embeds"  # child serialized inline within the parent (document/file)
    contains = "contains"  # parent owns child's lifecycle (1:N composition)
    references = "references"  # parent points at child by id (no containment)


class EdgeDirection(str, Enum):
    directed = "directed"
    undirected = "undirected"


class DistanceMetric(str, Enum):
    cosine = "cosine"
    euclidean = "euclidean"
    dot_product = "dot_product"
    manhattan = "manhattan"


class AnnIndexType(str, Enum):
    hnsw = "hnsw"
    ivf = "ivf"
    ivf_flat = "ivf_flat"
    ivf_pq = "ivf_pq"
    flat = "flat"
    diskann = "diskann"
    other = "other"


# =============================================================================
# Models — keep nested theme models permissive (extra="allow") so the file can
# carry forward-compat keys without breaking validation; reject enum values strictly.
# =============================================================================


_BASE_CONFIG = ConfigDict(extra="allow", str_strip_whitespace=True)


class _Permissive(BaseModel):
    model_config = _BASE_CONFIG


class FieldSpec(_Permissive):
    # relational / document attributes
    type: Optional[FieldType] = None
    nullable: Optional[bool] = None
    primary_key: Optional[bool] = None
    unique: Optional[bool] = None
    default: Optional[Any] = None
    references: Optional[str] = None  # "Entity.field"
    on_delete: Optional[OnDelete] = None
    check: Optional[str] = None
    # Structured app-level validation (codegen renders Pydantic/zod validators
    # from this, never from parsing `check` SQL). Keys: min / max / min_length /
    # max_length / regex / format / enum. Type-checked as a mapping only.
    validation: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None
    # file-native attribute — a literal Python type expression, e.g.
    # "Optional[list[FeatureSpec]]". Optionality is encoded in the type itself,
    # not a `nullable:` flag. Carried alongside `description` instead of `type`.
    pydantic_type: Optional[str] = None
    description: Optional[str] = None
    # vector attribute — marks a field as the source/holder of an embedding.
    embedding: Optional[bool] = None


class EntityLifecycleTransition(_Permissive):
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    trigger: Optional[str] = None
    guard: Optional[str] = None


class EntityLifecycle(_Permissive):
    """Per-entity state machine: the allowed-transition graph downstream
    `test` (state-transition cases) and `task`/`code` (guard logic) consume.
    Enums list the status VALUES; this block adds the legal moves."""

    field: Optional[str] = None       # the status-bearing field name
    initial: Optional[str] = None
    transitions: Optional[List[EntityLifecycleTransition]] = None
    terminal: Optional[List[str]] = None


class Entity(_Permissive):
    description: Optional[str] = None
    primary_key: Optional[Union[str, List[str]]] = None
    fields: Optional[Dict[str, FieldSpec]] = None
    lifecycle: Optional[EntityLifecycle] = None
    # Plain-language always-true statements about a valid instance (e.g.
    # "end_date >= start_date"). task's entity_slice copies invariants and
    # lifecycle verbatim; code renders model validators / CHECKs from them;
    # test seeds invariant-violation cases. Type-checked as list[str] only.
    invariants: Optional[List[str]] = None
    # Which store(s) hold this entity: "primary" (the default when absent) or
    # a secondary_stores[].store_id. Unknown ids warn (check_store_ids).
    stored_in: Optional[List[str]] = None
    traces_prd_features: Optional[List[str]] = None
    traces_ux_surfaces: Optional[List[str]] = None
    traces_prd_workflows: Optional[List[str]] = None
    # file-native: discriminator + Pydantic composition + on-disk serialization.
    category: Optional[str] = None
    composes: Optional[List[str]] = None
    serialization: Optional[Any] = None
    # graph: the node label (defaults to the entity key when omitted).
    node_label: Optional[str] = None
    # vector: which fields form the stored payload alongside the vector.
    payload_fields: Optional[List[str]] = None
    # Discriminated union (any paradigm): this entity IS one of the named
    # variants, told apart by `discriminator` - a field every variant carries.
    # A union parent may omit `fields` / `primary_key`; check_union_integrity
    # verifies the variants exist and carry the discriminator (IMP-080).
    one_of: Optional[List[str]] = None
    discriminator: Optional[str] = None


class SecondaryStore(_Permissive):
    # Stable kebab-case id (e.g. "redis-cache") that ARCH containers
    # (`realizes_store`) and entities.<E>.stored_in reference. "primary" is
    # reserved for the primary store. Uniqueness/format enforced by
    # check_store_ids (error >= 3.0, warning below).
    store_id: Optional[str] = None
    kind: Optional[SecondaryStoreKind] = None
    role: Optional[SecondaryStoreRole] = None
    rationale: Optional[str] = None


class Persistence(_Permissive):
    paradigm: Optional[Paradigm] = None  # absent ⇒ treated as relational (the FAMILY axis)
    paradigm_confidence: Optional[Confidence] = None
    paradigm_rationale: Optional[str] = None
    topology: Optional[PersistenceTopology] = None  # orthogonal axis: where/how it runs
    topology_confidence: Optional[Confidence] = None
    topology_rationale: Optional[str] = None
    primary_store: Optional[PrimaryStore] = None
    primary_store_confidence: Optional[Confidence] = None
    primary_store_rationale: Optional[str] = None
    serialization_format: Optional[SerializationFormat] = None  # file_native
    polyglot: Optional[bool] = None
    secondary_stores: Optional[List[SecondaryStore]] = None
    secondary_stores_confidence: Optional[Confidence] = None
    file_blob_store: Optional[FileBlobStore] = None
    file_blob_store_bucket: Optional[str] = None
    file_blob_store_rationale: Optional[str] = None


class NaturalKey(_Permissive):
    entity: Optional[str] = None
    fields: Optional[List[str]] = None
    reason: Optional[str] = None


class IdStrategy(_Permissive):
    scheme: Optional[IdScheme] = None
    scheme_confidence: Optional[Confidence] = None
    scheme_rationale: Optional[str] = None
    natural_keys: Optional[List[NaturalKey]] = None


class Relationship(_Permissive):
    from_entity: Optional[str] = None
    from_field: Optional[str] = None
    to_entity: Optional[str] = None
    to_field: Optional[str] = None
    cardinality: Optional[Cardinality] = None
    on_delete: Optional[OnDelete] = None
    on_update: Optional[OnDelete] = None
    join_table: Optional[str] = None
    comment: Optional[str] = None


class EnumsAndLookups(_Permissive):
    enums: Optional[Dict[str, List[str]]] = None
    lookup_tables: Optional[List[str]] = None


class AccessPattern(_Permissive):
    description: Optional[str] = None
    entity: Optional[str] = None
    fields: Optional[List[str]] = None
    expected_qps: Optional[float] = None
    latency_budget_ms: Optional[int] = None
    read_or_write: Optional[Literal["read", "write", "both"]] = None


class IndexSpec(_Permissive):
    entity: Optional[str] = None
    fields: Optional[List[str]] = None
    unique: Optional[bool] = None
    type: Optional[IndexType] = None
    name: Optional[str] = None


class IndexesAndQueries(_Permissive):
    access_patterns: Optional[List[AccessPattern]] = None
    expected_indexes: Optional[List[IndexSpec]] = None


class UniqueConstraint(_Permissive):
    entity: Optional[str] = None
    fields: Optional[List[str]] = None
    name: Optional[str] = None


class CheckConstraint(_Permissive):
    entity: Optional[str] = None
    expression: Optional[str] = None
    name: Optional[str] = None
    comment: Optional[str] = None


class IntegrityAndConstraints(_Permissive):
    default_on_delete: Optional[OnDelete] = None
    default_on_delete_rationale: Optional[str] = None
    unique_constraints: Optional[List[UniqueConstraint]] = None
    check_constraints: Optional[List[CheckConstraint]] = None


class DataClassification(_Permissive):
    pii_fields: Optional[List[str]] = None
    pii_fields_confidence: Optional[Confidence] = None
    regulated_fields: Optional[List[str]] = None
    regulated_fields_confidence: Optional[Confidence] = None
    localized_fields: Optional[List[str]] = None   # per-locale text (PRD 1.1 i18n)
    localized_fields_confidence: Optional[Confidence] = None
    encrypted_at_rest: Optional[List[str]] = None
    encryption_kms_ref: Optional[str] = None
    retention_policy_default: Optional[str] = None


class BoundedContext(_Permissive):
    description: Optional[str] = None
    entities: Optional[List[str]] = None


class AuditColumns(_Permissive):
    created_at: Optional[bool] = None
    updated_at: Optional[bool] = None
    created_by: Optional[bool] = None
    updated_by: Optional[bool] = None
    deleted_at: Optional[bool] = None


class AuditAndLifecycle(_Permissive):
    audit_columns: Optional[AuditColumns] = None
    soft_delete: Optional[bool] = None
    soft_delete_rationale: Optional[str] = None
    archive_strategy: Optional[str] = None
    applies_to: Optional[List[str]] = None


class VersioningAndHistory(_Permissive):
    record_versioning: Optional[RecordVersioning] = None
    record_versioning_rationale: Optional[str] = None
    history_retention: Optional[str] = None
    applies_to: Optional[List[str]] = None


class RetentionPolicyItem(_Permissive):
    entity: Optional[str] = None
    ttl: Optional[str] = None
    policy: Optional[RetentionPolicy] = None


class ScaleAndRetention(_Permissive):
    partitioning_key: Optional[str] = None
    partitioning_strategy: Optional[PartitioningStrategy] = None
    sharding_key: Optional[str] = None
    retention_policies: Optional[List[RetentionPolicyItem]] = None


class MigrationsAndEvolution(_Permissive):
    tool: Optional[MigrationTool] = None
    tool_confidence: Optional[Confidence] = None
    zero_downtime_strategy: Optional[str] = None
    rollback_policy: Optional[str] = None


class TransactionsAndConsistency(_Permissive):
    default_isolation: Optional[IsolationLevel] = None
    default_isolation_rationale: Optional[str] = None
    transaction_boundaries: Optional[List[str]] = None


class CachedEntity(_Permissive):
    entity: Optional[str] = None
    ttl: Optional[str] = None
    invalidation: Optional[str] = None


class CachingLayerBlock(_Permissive):
    layer: Optional[CachingLayer] = None
    layer_confidence: Optional[Confidence] = None
    cached_entities: Optional[List[CachedEntity]] = None


class IndexedEntity(_Permissive):
    entity: Optional[str] = None
    fields: Optional[List[str]] = None


class SearchAndAnalytics(_Permissive):
    fulltext_engine: Optional[FulltextEngine] = None
    fulltext_engine_confidence: Optional[Confidence] = None
    fulltext_engine_rationale: Optional[str] = None
    indexed_entities: Optional[List[IndexedEntity]] = None
    analytics_target: Optional[AnalyticsTarget] = None
    cdc_strategy: Optional[CdcStrategy] = None


class SeedAndFixtures(_Permissive):
    seed_strategy: Optional[str] = None
    dev_fixtures_path: Optional[str] = None
    # Concrete reference rows keyed by entity name (lookup/enum-backed tables
    # only). Type-checked loosely; each row is a field: value mapping.
    seed_data: Optional[Dict[str, List[Dict[str, Any]]]] = None


class ExternalDataSource(_Permissive):
    name: Optional[str] = None
    sync_model: Optional[SyncModel] = None
    conflict_resolution: Optional[str] = None
    refresh_interval: Optional[str] = None
    maps_to_entity: Optional[str] = None


# -----------------------------------------------------------------------------
# Paradigm-specific blocks. All optional at the model level; the per-paradigm
# required-path table (REQUIRED_PATHS_BY_PARADIGM) decides which are mandatory.
# -----------------------------------------------------------------------------


class IdentityConventions(_Permissive):
    """file_native (and any non-surrogate-key paradigm): how entity identity is
    derived when there is no generated primary key. Replaces id_strategy."""

    rules: Optional[List[str]] = None


class CompositionItem(_Permissive):
    parent: Optional[str] = None
    child: Optional[str] = None
    kind: Optional[CompositionKind] = None
    comment: Optional[str] = None


class CrossReference(_Permissive):
    """file_native / document: a string-ID reference relation (e.g.
    TestSpec.covers → FR-NNN), the input contract for referential-integrity
    gates. `from_entity` must exist in `entities`; `to_entity` (when given)
    must too. `references_family` names an upstream ID family (FR/ENT/…) when
    the reference points outside the local entity set."""

    from_entity: Optional[str] = None
    field: Optional[str] = None
    to_entity: Optional[str] = None
    references_family: Optional[str] = None
    gate: Optional[str] = None
    comment: Optional[str] = None


class SerializationEntry(_Permissive):
    entity: Optional[str] = None
    filename_pattern: Optional[str] = None
    scope: Optional[str] = None  # per_stage | per_project | nested_in:<E> | runtime_only


class SerializationConventions(_Permissive):
    """file_native: where artifacts live on disk so the tree is human-readable."""

    root_path: Optional[str] = None
    format: Optional[SerializationFormat] = None
    entries: Optional[List[SerializationEntry]] = None


class Edge(_Permissive):
    """graph: a first-class relationship. Unlike relational `relationships`,
    edges carry their own properties and have no join table."""

    type: Optional[str] = None
    from_entity: Optional[str] = None
    to_entity: Optional[str] = None
    cardinality: Optional[Cardinality] = None
    direction: Optional[EdgeDirection] = None
    properties: Optional[Dict[str, Any]] = None
    comment: Optional[str] = None


class TraversalPattern(_Permissive):
    description: Optional[str] = None
    start_label: Optional[str] = None
    pattern: Optional[str] = None  # e.g. "(:User)-[:FOLLOWS*1..3]->(:User)"


class GraphConfig(_Permissive):
    node_labels: Optional[List[str]] = None
    traversal_patterns: Optional[List[TraversalPattern]] = None


class VectorConfig(_Permissive):
    """vector: the embedding + ANN-index configuration for the collection(s)."""

    embedding_model: Optional[str] = None
    dimensions: Optional[int] = None
    distance_metric: Optional[DistanceMetric] = None
    ann_index: Optional[AnnIndexType] = None
    index_params: Optional[Dict[str, Any]] = None


class KeyPattern(_Permissive):
    entity: Optional[str] = None
    key_template: Optional[str] = None  # e.g. "user#{user_id}#order#{order_id}"
    partition_key: Optional[str] = None
    sort_key: Optional[str] = None


class SecondaryKeyIndex(_Permissive):
    name: Optional[str] = None
    partition_key: Optional[str] = None
    sort_key: Optional[str] = None
    projection: Optional[str] = None


class KeyValueDesign(_Permissive):
    """key_value: access-pattern-first key design (partition/sort keys, GSIs)."""

    key_patterns: Optional[List[KeyPattern]] = None
    secondary_indexes: Optional[List[SecondaryKeyIndex]] = None


# -----------------------------------------------------------------------------
# Top-level
# -----------------------------------------------------------------------------


class Metadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    data_model_version: str
    last_updated: str
    generated_by: str = "sdlc-data"
    session_id: str
    monorepo: bool = False
    status: Literal["draft", "complete"] = "draft"
    changelog: Optional[List[str]] = None
    # One entry per upstream artifact consumed, each a mapping
    # {file, session_id, last_updated, sha256}. Type-checked as a list of
    # mappings only — see CLAUDE.md §7 "Upstream-change re-invocation".
    upstream_provenance: Optional[List[Dict[str, Any]]] = None


class DataModelProduct(_Permissive):
    """One product's data model in monorepo mode."""

    # The structured DEFER half of trace-or-defer (see DataDeferralIndex).
    # Loosely typed; a malformed entry defers nothing (the coverage gate
    # stays armed) and is reported as a warning, never a schema failure.
    deferrals: Optional[List[Dict[str, Any]]] = None
    deferred_requirements: Optional[List[Dict[str, Any]]] = None   # alias
    persistence: Optional[Persistence] = None
    id_strategy: Optional[IdStrategy] = None
    entities: Optional[Dict[str, Entity]] = None
    relationships: Optional[List[Relationship]] = None
    enums_and_lookups: Optional[EnumsAndLookups] = None
    indexes_and_queries: Optional[IndexesAndQueries] = None
    integrity_and_constraints: Optional[IntegrityAndConstraints] = None
    data_classification: Optional[DataClassification] = None
    bounded_contexts: Optional[Dict[str, BoundedContext]] = None
    audit_and_lifecycle: Optional[AuditAndLifecycle] = None
    versioning_and_history: Optional[VersioningAndHistory] = None
    scale_and_retention: Optional[ScaleAndRetention] = None
    migrations_and_evolution: Optional[MigrationsAndEvolution] = None
    transactions_and_consistency: Optional[TransactionsAndConsistency] = None
    caching_layer: Optional[CachingLayerBlock] = None
    search_and_analytics: Optional[SearchAndAnalytics] = None
    seed_and_fixtures: Optional[SeedAndFixtures] = None
    external_data_sources: Optional[List[ExternalDataSource]] = None
    # paradigm-specific blocks
    identity_conventions: Optional[IdentityConventions] = None
    composition: Optional[List[CompositionItem]] = None
    cross_references: Optional[List[CrossReference]] = None
    serialization_conventions: Optional[SerializationConventions] = None
    edges: Optional[List[Edge]] = None
    graph_config: Optional[GraphConfig] = None
    vector_config: Optional[VectorConfig] = None
    key_value_design: Optional[KeyValueDesign] = None


class DataModel(BaseModel):
    """Top-level docs/DATA-MODEL.yaml document."""

    model_config = ConfigDict(extra="allow")

    metadata: Metadata
    data_warnings: List[Any] = Field(default_factory=list)  # str | typed WarningItem mapping

    # The structured DEFER half of trace-or-defer (see DataDeferralIndex).
    # In monorepo mode this top-level list applies to every product, and each
    # product may carry its own beside it. Not a theme block — legal in both
    # modes.
    deferrals: Optional[List[Dict[str, Any]]] = None
    deferred_requirements: Optional[List[Dict[str, Any]]] = None   # alias

    # Single-product theme blocks (in interview order)
    persistence: Optional[Persistence] = None
    id_strategy: Optional[IdStrategy] = None
    entities: Optional[Dict[str, Entity]] = None
    relationships: Optional[List[Relationship]] = None
    enums_and_lookups: Optional[EnumsAndLookups] = None
    indexes_and_queries: Optional[IndexesAndQueries] = None
    integrity_and_constraints: Optional[IntegrityAndConstraints] = None
    data_classification: Optional[DataClassification] = None
    bounded_contexts: Optional[Dict[str, BoundedContext]] = None
    audit_and_lifecycle: Optional[AuditAndLifecycle] = None
    versioning_and_history: Optional[VersioningAndHistory] = None
    scale_and_retention: Optional[ScaleAndRetention] = None
    migrations_and_evolution: Optional[MigrationsAndEvolution] = None
    transactions_and_consistency: Optional[TransactionsAndConsistency] = None
    caching_layer: Optional[CachingLayerBlock] = None
    search_and_analytics: Optional[SearchAndAnalytics] = None
    seed_and_fixtures: Optional[SeedAndFixtures] = None
    external_data_sources: Optional[List[ExternalDataSource]] = None
    # paradigm-specific blocks
    identity_conventions: Optional[IdentityConventions] = None
    composition: Optional[List[CompositionItem]] = None
    cross_references: Optional[List[CrossReference]] = None
    serialization_conventions: Optional[SerializationConventions] = None
    edges: Optional[List[Edge]] = None
    graph_config: Optional[GraphConfig] = None
    vector_config: Optional[VectorConfig] = None
    key_value_design: Optional[KeyValueDesign] = None

    # Multi-product mode
    products: Optional[Dict[str, DataModelProduct]] = None

    @model_validator(mode="after")
    def _check_mode(self) -> "DataModel":
        single_themes = [
            self.persistence,
            self.id_strategy,
            self.entities,
            self.relationships,
            self.enums_and_lookups,
            self.indexes_and_queries,
            self.integrity_and_constraints,
            self.data_classification,
            self.bounded_contexts,
            self.audit_and_lifecycle,
            self.versioning_and_history,
            self.scale_and_retention,
            self.migrations_and_evolution,
            self.transactions_and_consistency,
            self.caching_layer,
            self.search_and_analytics,
            self.seed_and_fixtures,
            self.external_data_sources,
            self.identity_conventions,
            self.composition,
            self.cross_references,
            self.serialization_conventions,
            self.edges,
            self.graph_config,
            self.vector_config,
            self.key_value_design,
        ]
        any_single = any(t is not None for t in single_themes)

        if self.metadata.monorepo:
            if not self.products:
                raise ValueError("metadata.monorepo is true but `products` is missing or empty")
            if any_single:
                raise ValueError(
                    "monorepo mode set but top-level theme blocks are present; "
                    "in monorepo mode every theme must live under `products.<slug>`"
                )
        else:
            if self.products:
                raise ValueError(
                    "`products` is set but metadata.monorepo is false; "
                    "either set monorepo: true or move themes to top level"
                )
        return self


# =============================================================================
# Required-field check — only enforced when metadata.status == "complete"
# =============================================================================

# Required fields are paradigm-gated. COMMON_REQUIRED_PATHS hold for every
# paradigm; PARADIGM_REQUIRED_PATHS add the blocks that only make sense for one
# storage shape. A DATA-MODEL.yaml with no `persistence.paradigm` defaults to
# `relational`, so pre-paradigm files keep exactly their old required set.
COMMON_REQUIRED_PATHS: List[str] = [
    "persistence.primary_store",
    "entities",
    "data_classification.pii_fields",
]

PARADIGM_REQUIRED_PATHS: Dict[Paradigm, List[str]] = {
    Paradigm.relational: [
        "id_strategy.scheme",
        "relationships",
        "indexes_and_queries.access_patterns",
        "integrity_and_constraints.default_on_delete",
    ],
    Paradigm.document: [
        "id_strategy.scheme",
        "indexes_and_queries.access_patterns",
    ],
    Paradigm.key_value: [
        "key_value_design",
    ],
    Paradigm.graph: [
        "edges",
    ],
    Paradigm.vector: [
        "vector_config",
    ],
    Paradigm.file_native: [
        "identity_conventions",
    ],
    # Stateless: nothing is persisted, so nothing is required — not even the
    # COMMON set (no store, no entities, no classification lists).
    Paradigm.none: [],
}


def required_paths_for(paradigm: Paradigm) -> List[str]:
    if paradigm == Paradigm.none:
        return []
    return COMMON_REQUIRED_PATHS + PARADIGM_REQUIRED_PATHS.get(paradigm, [])


# Paths where the key must be PRESENT (not None) but an empty list is allowed:
# the agent has to explicitly answer ("no edges / no PII / no listed patterns"),
# but an empty answer is valid. Feature-coverage is the real scope guard.
PRESENT_ONLY_PATHS: set = {
    "relationships",
    "edges",
    "data_classification.pii_fields",
    "indexes_and_queries.access_patterns",
}


def entity_required_paths_for(paradigm: Paradigm) -> List[str]:
    """Per-entity required fields. `primary_key` is meaningful only where the
    paradigm has surrogate keys (relational, document); file_native derives
    identity from path, graph/vector/key_value from their own key design."""
    base = ["description", "fields", "traces_prd_features"]
    if paradigm in (Paradigm.relational, Paradigm.document):
        base.insert(2, "primary_key")
    return base


# Per-entity path where the key must be present (not None) but empty list is OK.
ENTITY_PRESENT_ONLY_PATHS: set = {"traces_prd_features"}


def _get_dotted(obj: object, path: str) -> object:
    cur: object = obj
    for part in path.split("."):
        if cur is None:
            return None
        # Models use attribute access; dicts use key access.
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
    return cur


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        # entities {} is empty — required; relationships [] is allowed (key present
        # but no edges). We handle this differentiation in the caller.
        return True
    return False


def _paradigm_of(root: object) -> Paradigm:
    """Read persistence.paradigm for a scope, defaulting to relational when
    absent (so pre-paradigm files behave exactly as before)."""
    persistence = _get_dotted(root, "persistence")
    if persistence is None:
        return Paradigm.relational
    p = getattr(persistence, "paradigm", None)
    if p is None:
        return Paradigm.relational
    if isinstance(p, Paradigm):
        return p
    try:
        return Paradigm(p)
    except ValueError:
        return Paradigm.relational


# ⚠D (D2): the silent relational default hides a forgotten paradigm on a
# file-native/CLI project (the exact trap the original AICF DATA-MODEL v1 was
# hand-rewritten to escape). From this artifact version on, an undeclared
# paradigm is an ERROR at status:complete; older artifacts keep the silent
# default + a warning. The floor CLEARS the meta-corpus's self-stamped 2.25
# (CLAUDE.md §10 — a new blocking check must not hard-fail legacy artifacts).
_PARADIGM_GATE_VERSION: "tuple[int, ...]" = (3, 0)


def _version_tuple(version: str) -> "tuple[int, ...]":
    """Parse ``"2.25"`` -> ``(2, 25)`` for a major.minor comparison; ``(0,)`` when
    unparseable."""
    parts = re.findall(r"\d+", str(version))
    return tuple(int(x) for x in parts[:2]) if parts else (0,)

def _prose_deferrals_allowed(obj, _fields=('data_model_version',), _floor=3):
    """Is the DEPRECATED prose word-match still read on this artifact?

    Only below `<name>_version` 3.0. From there up, a deferral is
    declared structurally - the top-level `deferrals` list, or a typed warning
    with `kind: deferral` and `defers: [...]` - and a note that merely mentions
    an id no longer silences that id's gate. Version-gated because an artifact
    an older skill version stamped complete must not turn red on upgrade
    (CLAUDE.md section 10). When no version is reachable the answer is yes, so
    the gate can only ever get looser, never stricter, by accident.
    """
    md = getattr(obj, "metadata", None)
    for name in _fields:
        v = getattr(md, name, None)
        if v:
            return tuple(_version_tuple(v)[:2]) < (_floor, 0)
    return True


def check_paradigm_declared(dm: "DataModel") -> List[str]:
    """Return scope-labelled ``persistence.paradigm`` paths not explicitly
    declared (⚠D). The caller decides error-vs-warning by artifact version."""
    gaps: List[str] = []

    def _scope(label: str, root: object) -> None:
        persistence = _get_dotted(root, "persistence")
        declared = persistence is not None and getattr(persistence, "paradigm", None) is not None
        if not declared:
            gaps.append(f"{label}persistence.paradigm")

    if dm.metadata.monorepo and dm.products:
        for slug, product in dm.products.items():
            _scope(f"products.{slug}.", product)
    else:
        _scope("", dm)
    return gaps


def check_required(dm: DataModel) -> List[str]:
    """Return a flat list of missing required field paths.

    The required set is paradigm-gated (see required_paths_for). `entities` must
    be a non-empty dict for every paradigm. List-typed scope fields in
    PRESENT_ONLY_PATHS (relationships, edges, pii_fields, access_patterns) only
    require the key to be present — an explicit empty answer is valid. The
    feature-coverage cross-check is the real "did you think about scope" guard.
    """
    missing: List[str] = []

    def _check(scope_label: str, root: object) -> None:
        paradigm = _paradigm_of(root)
        for path in required_paths_for(paradigm):
            val = _get_dotted(root, path)
            if path == "entities":
                if not isinstance(val, dict) or len(val) == 0:
                    missing.append(f"{scope_label}{path}")
                continue
            if path in PRESENT_ONLY_PATHS:
                if val is None:
                    missing.append(f"{scope_label}{path}")
                continue
            if _is_empty(val):
                missing.append(f"{scope_label}{path}")

        # Per-entity required fields (paradigm-gated). A union parent (one_of)
        # carries no fields of its own - its variants do - so `fields` and
        # `primary_key` are not required of it (check_union_integrity holds
        # the variants to that instead).
        entities = _get_dotted(root, "entities")
        if isinstance(entities, dict):
            entity_required = entity_required_paths_for(paradigm)
            for ename, entity in entities.items():
                is_union = _is_union_parent(entity)
                for ep in entity_required:
                    if is_union and ep in ("fields", "primary_key"):
                        continue
                    val = _get_dotted(entity, ep)
                    if ep == "fields":
                        if not isinstance(val, dict) or len(val) == 0:
                            missing.append(f"{scope_label}entities.{ename}.{ep}")
                    elif ep in ENTITY_PRESENT_ONLY_PATHS:
                        if val is None:
                            missing.append(f"{scope_label}entities.{ename}.{ep}")
                    elif _is_empty(val):
                        missing.append(f"{scope_label}entities.{ename}.{ep}")

    if dm.metadata.monorepo and dm.products:
        for slug, product in dm.products.items():
            _check(f"products.{slug}.", product)
    else:
        _check("", dm)
    return missing


# =============================================================================
# Cross-checks
# =============================================================================

_FEATURE_ID_RE = re.compile(r"^FR-\d+", re.IGNORECASE)
_WRN_RE = re.compile(r"^WRN-\d{3,}:\s+.+")
_FR_PREFIX_RE = re.compile(r"^FR-\d{3,}$", re.IGNORECASE)
_SCR_PREFIX_RE = re.compile(r"^SCR-\d{3,}$", re.IGNORECASE)
_WKF_PREFIX_RE = re.compile(r"^WKF-\d{3,}$", re.IGNORECASE)


# --- BEGIN canonical WRN block (CLAUDE.md section 2) — byte-identical everywhere
# A `*_warnings` entry is EITHER the legacy string "WRN-NNN: <text>" OR a
# mapping {id, text, kind, status, impact, refs?, defers?, resolution?,
# resolved_on?}. Legacy strings stay valid forever and read as an open,
# local-impact note. A malformed MAPPING never fails the file: it is reported
# and the entry is dropped or downgraded, exactly as a malformed `deferrals`
# entry is (it defers nothing). A malformed STRING stays the error it has
# always been.

WRN_KINDS = ("deferral", "limitation", "decision", "exception", "scope_change", "note")
WRN_STATUSES = ("open", "resolved")
WRN_IMPACTS = ("none", "local", "downstream", "risk")

_WRN_ENTRY_RE = re.compile(r"^WRN-\d{3,}:\s+.+", re.DOTALL)
_WRN_ID_RE = re.compile(r"^WRN-\d{3,}$")


class WarningItem:
    """One normalized `*_warnings` entry.

    `typed` records which form it was written in, so a writer can tell an
    untouched legacy corpus from one that has been migrated.
    """

    __slots__ = ("id", "text", "kind", "status", "impact", "refs", "defers",
                 "resolution", "resolved_on", "typed", "where")

    def __init__(self, wid, text, kind="note", status="open", impact="local",
                 refs=None, defers=None, resolution=None, resolved_on=None,
                 typed=False, where=""):
        self.id = wid
        self.text = text
        self.kind = kind
        self.status = status
        self.impact = impact
        self.refs = [str(r).strip() for r in (refs or []) if str(r).strip()]
        self.defers = [str(d).strip() for d in (defers or []) if str(d).strip()]
        self.resolution = resolution
        self.resolved_on = resolved_on
        self.typed = typed
        self.where = where

    def __str__(self):
        return "%s: %s" % (self.id, self.text)


def parse_warnings(raw, label):
    """Normalize one `*_warnings` list.

    Returns `(items, errors, shape_warnings)`:
      items          - WarningItem per usable entry, in file order.
      errors         - BLOCKING. A string entry that is not "WRN-NNN: <text>",
                       or an entry that is neither a string nor a mapping.
                       Unchanged from the pre-typed behaviour.
      shape_warnings - NON-BLOCKING. A mapping whose fields are wrong. Never
                       promoted to an error: an artifact stamped complete by an
                       older skill version must not start failing (section 10).
    """
    items: List["WarningItem"] = []
    errors: List[str] = []
    shape: List[str] = []
    for i, w in enumerate(raw or []):
        where = "%s[%d]" % (label, i)
        if isinstance(w, str):
            s = w.strip()
            if not _WRN_ENTRY_RE.match(s):
                errors.append(
                    "%s: '%s' must start with 'WRN-NNN: ' "
                    "(zero-padded 3-digit number)" % (where, w)
                )
                continue
            wid, _, text = s.partition(":")
            items.append(WarningItem(wid.strip(), text.strip(), where=where))
            continue
        if not isinstance(w, dict):
            errors.append(
                "%s: '%s' must start with 'WRN-NNN: ' "
                "(zero-padded 3-digit number)" % (where, w)
            )
            continue
        wid = str(w.get("id") or "").strip()
        text = str(w.get("text") or "").strip()
        if not _WRN_ID_RE.match(wid):
            shape.append(
                "%s declares id '%s' - a warning needs an id of the form "
                "'WRN-NNN' to be referenced; this entry is ignored"
                % (where, w.get("id"))
            )
            continue
        if not text:
            shape.append(
                "%s (%s) has no 'text' - a warning with no message says "
                "nothing; this entry is ignored" % (where, wid)
            )
            continue
        kind = str(w.get("kind") or "note").strip()
        status = str(w.get("status") or "open").strip()
        impact = str(w.get("impact") or "local").strip()
        if kind not in WRN_KINDS:
            shape.append(
                "%s (%s): kind '%s' is not one of %s - read as 'note'"
                % (where, wid, kind, ", ".join(WRN_KINDS))
            )
            kind = "note"
        if status not in WRN_STATUSES:
            shape.append(
                "%s (%s): status '%s' is not 'open' or 'resolved' - read as "
                "'open'" % (where, wid, status)
            )
            status = "open"
        if impact not in WRN_IMPACTS:
            shape.append(
                "%s (%s): impact '%s' is not one of %s - read as 'local'"
                % (where, wid, impact, ", ".join(WRN_IMPACTS))
            )
            impact = "local"
        resolution = w.get("resolution")
        if status == "resolved" and not str(resolution or "").strip():
            shape.append(
                "%s (%s) is marked resolved but records no resolution - a "
                "resolution nobody can read is not one; read as still open"
                % (where, wid)
            )
            status = "open"
        defers = [str(d).strip() for d in (w.get("defers") or []) if str(d).strip()]
        if defers and kind != "deferral":
            shape.append(
                "%s (%s) lists 'defers' but its kind is '%s' - only a "
                "'deferral' defers anything, so these ids are ignored"
                % (where, wid, kind)
            )
            defers = []
        items.append(WarningItem(
            wid, text, kind, status, impact, w.get("refs"), defers,
            resolution, w.get("resolved_on"), typed=True, where=where,
        ))
    return items, errors, shape


_WRN_SHAPE_SEEN = []


def check_warning_ids(warnings, label="warnings"):
    """The blocking half of `parse_warnings`.

    The non-blocking half is collected in `_WRN_SHAPE_SEEN` and drained once,
    where the report is printed, so a caller that only wants the errors cannot
    accidentally swallow a malformed mapping.
    """
    _items, errors, shape = parse_warnings(warnings, label)
    _WRN_SHAPE_SEEN.extend(shape)
    return errors


def drain_warning_shape_warnings():
    """Every malformed typed-warning report seen so far, each once."""
    out = list(dict.fromkeys(_WRN_SHAPE_SEEN))
    del _WRN_SHAPE_SEEN[:]
    return out


def warning_text(entry):
    """The message of one raw entry, whichever form it is written in."""
    if isinstance(entry, dict):
        return str(entry.get("text") or "")
    s = str(entry or "").strip()
    return s.partition(":")[2].strip() if ":" in s else s
# --- END canonical WRN block




def _check_id_prefix(values: object, regex: "re.Pattern[str]", path_label: str) -> List[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        return [f"{path_label}: expected a list, got {type(values).__name__}"]
    errs: List[str] = []
    for i, v in enumerate(values):
        if not isinstance(v, str) or not regex.match(v.strip()):
            errs.append(f"{path_label}[{i}]: '{v}' does not match expected ID format")
    return errs


def check_trace_id_formats(root: object) -> List[str]:
    """Enforce <PREFIX>-NNN format on every per-entity trace list."""
    errs: List[str] = []
    entities = _get_dotted(root, "entities")
    if not isinstance(entities, dict):
        return errs
    for ename, entity in entities.items():
        errs.extend(
            _check_id_prefix(
                getattr(entity, "traces_prd_features", None),
                _FR_PREFIX_RE,
                f"entities.{ename}.traces_prd_features (expected FR-NNN)",
            )
        )
        errs.extend(
            _check_id_prefix(
                getattr(entity, "traces_ux_surfaces", None),
                _SCR_PREFIX_RE,
                f"entities.{ename}.traces_ux_surfaces (expected SCR-NNN)",
            )
        )
        errs.extend(
            _check_id_prefix(
                getattr(entity, "traces_prd_workflows", None),
                _WKF_PREFIX_RE,
                f"entities.{ename}.traces_prd_workflows (expected WKF-NNN)",
            )
        )
    return errs


def _entity_names(root: object) -> List[str]:
    entities = _get_dotted(root, "entities")
    if isinstance(entities, dict):
        return list(entities.keys())
    return []


def _entity_field_names(root: object, entity_name: str) -> List[str]:
    entity = (_get_dotted(root, "entities") or {}).get(entity_name)
    if entity is None:
        return []
    fields = getattr(entity, "fields", None)
    if isinstance(fields, dict):
        return list(fields.keys())
    return []


def check_relationship_integrity(root: object) -> List[str]:
    """Every relationship's from_entity, to_entity, and (for N:M) join_table
    must exist as a key in `entities`. Field names referenced must exist on
    the corresponding entity."""
    errs: List[str] = []
    rels = _get_dotted(root, "relationships")
    if not isinstance(rels, list):
        return errs
    enames = set(_entity_names(root))
    for i, rel in enumerate(rels):
        # rel is a Relationship model
        fe = getattr(rel, "from_entity", None)
        te = getattr(rel, "to_entity", None)
        ff = getattr(rel, "from_field", None)
        tf = getattr(rel, "to_field", None)
        card = getattr(rel, "cardinality", None)
        jt = getattr(rel, "join_table", None)

        if fe and fe not in enames:
            errs.append(f"relationships[{i}].from_entity: '{fe}' not in entities")
        if te and te not in enames:
            errs.append(f"relationships[{i}].to_entity: '{te}' not in entities")
        if fe in enames and ff and ff not in _entity_field_names(root, fe):
            errs.append(f"relationships[{i}].from_field: '{ff}' not a field on '{fe}'")
        if te in enames and tf and tf not in _entity_field_names(root, te):
            errs.append(f"relationships[{i}].to_field: '{tf}' not a field on '{te}'")
        if card == Cardinality.many_many:
            if not jt:
                errs.append(f"relationships[{i}].join_table: required when cardinality == 'N:M'")
            elif jt not in enames:
                errs.append(f"relationships[{i}].join_table: '{jt}' not in entities")
    return errs


def check_field_references(root: object) -> List[str]:
    """Every entity field with a `references: Entity.field` must resolve."""
    errs: List[str] = []
    entities = _get_dotted(root, "entities")
    if not isinstance(entities, dict):
        return errs
    enames = set(entities.keys())
    for ename, entity in entities.items():
        fields = getattr(entity, "fields", None) or {}
        if not isinstance(fields, dict):
            continue
        for fname, field in fields.items():
            ref = getattr(field, "references", None)
            if not ref:
                continue
            if "." not in ref:
                errs.append(
                    f"entities.{ename}.fields.{fname}.references: '{ref}' "
                    f"must be 'Entity.field' format"
                )
                continue
            ref_entity, _, ref_field = ref.partition(".")
            if ref_entity not in enames:
                errs.append(
                    f"entities.{ename}.fields.{fname}.references: "
                    f"'{ref_entity}' not in entities"
                )
                continue
            if ref_field not in _entity_field_names(root, ref_entity):
                errs.append(
                    f"entities.{ename}.fields.{fname}.references: "
                    f"'{ref_field}' not a field on '{ref_entity}'"
                )
    return errs


def check_classification_integrity(root: object) -> List[str]:
    """Every Entity.field listed in pii_fields, regulated_fields,
    localized_fields, encrypted_at_rest must resolve to a real field on a real
    entity."""
    errs: List[str] = []
    dc = _get_dotted(root, "data_classification")
    if dc is None:
        return errs
    entities = _get_dotted(root, "entities") or {}
    if not isinstance(entities, dict):
        return errs

    for list_name in ("pii_fields", "regulated_fields", "localized_fields", "encrypted_at_rest"):
        items = getattr(dc, list_name, None) or []
        for i, ref in enumerate(items):
            if not isinstance(ref, str):
                errs.append(
                    f"data_classification.{list_name}[{i}]: must be a string "
                    f"in 'Entity.field' format, got {type(ref).__name__}"
                )
                continue
            if "." not in ref:
                errs.append(
                    f"data_classification.{list_name}[{i}]: '{ref}' "
                    f"must be 'Entity.field' format"
                )
                continue
            ent, _, fld = ref.partition(".")
            if ent not in entities:
                errs.append(f"data_classification.{list_name}[{i}]: entity " f"'{ent}' not found")
                continue
            if fld not in _entity_field_names(root, ent):
                errs.append(
                    f"data_classification.{list_name}[{i}]: field "
                    f"'{fld}' not on entity '{ent}'"
                )
    return errs


def check_bounded_context_partition(root: object) -> List[str]:
    """When bounded_contexts is present, every entity in `entities` must be
    assigned to exactly one context (no orphans, no duplicates)."""
    errs: List[str] = []
    bcs = _get_dotted(root, "bounded_contexts")
    if not isinstance(bcs, dict) or len(bcs) == 0:
        return errs
    enames = set(_entity_names(root))

    assignments: Dict[str, List[str]] = {e: [] for e in enames}
    for ctx_name, ctx in bcs.items():
        ctx_ents = getattr(ctx, "entities", None) or []
        for ent in ctx_ents:
            if ent not in enames:
                errs.append(f"bounded_contexts.{ctx_name}.entities: '{ent}' not in entities")
                continue
            assignments[ent].append(ctx_name)

    for ent, ctxs in assignments.items():
        if len(ctxs) == 0:
            errs.append(f"bounded_contexts: entity '{ent}' is not assigned to any context")
        elif len(ctxs) > 1:
            errs.append(
                f"bounded_contexts: entity '{ent}' is assigned to multiple " f"contexts: {ctxs}"
            )
    return errs


def check_edge_integrity(root: object) -> List[str]:
    """graph: every edge's from_entity and to_entity must exist in `entities`
    (matched against the entity key or its node_label)."""
    errs: List[str] = []
    edges = _get_dotted(root, "edges")
    if not isinstance(edges, list):
        return errs
    enames = set(_entity_names(root))
    labels = set()
    for ename in enames:
        entity = (_get_dotted(root, "entities") or {}).get(ename)
        labels.add(ename)
        nl = getattr(entity, "node_label", None)
        if nl:
            labels.add(nl)
    for i, edge in enumerate(edges):
        fe = getattr(edge, "from_entity", None)
        te = getattr(edge, "to_entity", None)
        if fe and fe not in labels:
            errs.append(f"edges[{i}].from_entity: '{fe}' not in entities/node_labels")
        if te and te not in labels:
            errs.append(f"edges[{i}].to_entity: '{te}' not in entities/node_labels")
    return errs


def check_composition_integrity(root: object) -> List[str]:
    """document / file_native / graph: every composition parent and child must
    exist as a key in `entities`."""
    errs: List[str] = []
    comp = _get_dotted(root, "composition")
    if not isinstance(comp, list):
        return errs
    enames = set(_entity_names(root))
    for i, item in enumerate(comp):
        parent = getattr(item, "parent", None)
        child = getattr(item, "child", None)
        if parent and parent not in enames:
            errs.append(f"composition[{i}].parent: '{parent}' not in entities")
        if child and child not in enames:
            errs.append(f"composition[{i}].child: '{child}' not in entities")
    return errs


def _is_union_parent(entity: object) -> bool:
    one_of = getattr(entity, "one_of", None)
    return isinstance(one_of, list) and len(one_of) > 0


def check_union_integrity(root: object) -> List[str]:
    """Discriminated unions (any paradigm) - version-gated by the caller
    (error at data_model_version >= 3.0, warning below): an entity with
    `one_of` names a `discriminator`, every variant it names exists in
    `entities` (and is not the parent itself), and every variant carries the
    discriminator field. Without these a union cannot be resolved by codegen
    or seeded per variant by test (ledger IMP-080, aicf LSN-061)."""
    errs: List[str] = []
    entities = _get_dotted(root, "entities")
    if not isinstance(entities, dict):
        return errs
    for ename, entity in entities.items():
        if not _is_union_parent(entity):
            continue
        where = f"entities.{ename}"
        disc = getattr(entity, "discriminator", None)
        disc = str(disc).strip() if disc else ""
        if not disc:
            errs.append(f"{where}.discriminator: missing - a union needs the field whose "
                        f"value selects the variant (present on every variant)")
        for v in entity.one_of:
            vname = str(v)
            if vname == ename:
                errs.append(f"{where}.one_of: names itself ('{vname}') - a variant is another entity")
                continue
            variant = entities.get(vname)
            if variant is None:
                errs.append(f"{where}.one_of: '{vname}' not in entities - declare the variant "
                            f"as its own entity")
                continue
            if disc:
                vfields = getattr(variant, "fields", None)
                if not isinstance(vfields, dict) or disc not in vfields:
                    errs.append(f"entities.{vname}.fields: no '{disc}' field, but {ename}.one_of "
                                f"names it as a variant told apart by '{disc}'")
    return errs


def check_cross_reference_integrity(root: object) -> List[str]:
    """file_native / document: every cross_reference's from_entity must exist.
    `to_entity` (intra-model reference) must exist too; a reference that points
    at an upstream ID family instead uses `references_family` and is exempt
    from the entity-existence check."""
    errs: List[str] = []
    xrefs = _get_dotted(root, "cross_references")
    if not isinstance(xrefs, list):
        return errs
    enames = set(_entity_names(root))
    for i, xr in enumerate(xrefs):
        fe = getattr(xr, "from_entity", None)
        te = getattr(xr, "to_entity", None)
        fam = getattr(xr, "references_family", None)
        if fe and fe not in enames:
            errs.append(f"cross_references[{i}].from_entity: '{fe}' not in entities")
        if te and te not in enames:
            errs.append(f"cross_references[{i}].to_entity: '{te}' not in entities")
        if not te and not fam:
            errs.append(
                f"cross_references[{i}]: needs either `to_entity` (intra-model) "
                f"or `references_family` (upstream ID family)"
            )
    return errs


def check_vector_config(root: object) -> List[str]:
    """vector: vector_config must specify at least an embedding model, a
    dimension count, and a distance metric — codegen cannot wire up an index
    without all three."""
    errs: List[str] = []
    vc = _get_dotted(root, "vector_config")
    if vc is None:
        return errs  # presence is enforced by the required-path check
    for attr, label in (
        ("embedding_model", "embedding_model"),
        ("dimensions", "dimensions"),
        ("distance_metric", "distance_metric"),
    ):
        if getattr(vc, attr, None) is None:
            errs.append(f"vector_config.{label}: required for the vector paradigm")
    return errs


def check_identity_conventions(root: object) -> List[str]:
    """file_native: identity_conventions.rules must be a non-empty list — the
    whole point of the block is to state how identity is derived without keys."""
    errs: List[str] = []
    ic = _get_dotted(root, "identity_conventions")
    if ic is None:
        return errs  # presence enforced by the required-path check
    rules = getattr(ic, "rules", None)
    if not isinstance(rules, list) or len(rules) == 0:
        errs.append("identity_conventions.rules: must list at least one identity rule")
    return errs


def check_key_value_design(root: object) -> List[str]:
    """key_value: key_value_design.key_patterns must be non-empty, and each
    pattern's entity must resolve."""
    errs: List[str] = []
    kvd = _get_dotted(root, "key_value_design")
    if kvd is None:
        return errs  # presence enforced by the required-path check
    patterns = getattr(kvd, "key_patterns", None)
    if not isinstance(patterns, list) or len(patterns) == 0:
        errs.append("key_value_design.key_patterns: must define at least one key pattern")
        return errs
    enames = set(_entity_names(root))
    for i, kp in enumerate(patterns):
        ent = getattr(kp, "entity", None)
        if ent and ent not in enames:
            errs.append(f"key_value_design.key_patterns[{i}].entity: '{ent}' not in entities")
    return errs


def load_prd_features(
    prd_path: Path,
) -> Dict[Optional[str], List[str]]:
    """Return the PRD's gating FR-NNN IDs, scoped correctly. D2 gating subset
    (FR_GATE semantics, CLAUDE.md §10 / task precedent): the flat `features`
    list when present, else the legacy `must_have_features` ONLY. A legacy PRD's
    `nice_to_have_features` is post-MVP backlog the pre-D2 coverage gate never
    required, so it stays ungated — widening it would hard-fail legacy artifacts.

    Single-product mode: returns ``{None: [FR-001, ...]}``.
    Monorepo mode: returns ``{"<slug>": [FR-001, ...], ...}`` — one entry per
    product. Each product's features stay scoped to that product so the
    feature-coverage cross-check can compare each product's entities against
    only that product's features (rather than the union across all products,
    which would force every product to trace every other product's features).
    """
    if not prd_path.exists():
        return {None: []}
    try:
        raw = yaml.safe_load(prd_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {None: []}
    if not isinstance(raw, dict):
        return {None: []}

    monorepo = bool((raw.get("metadata") or {}).get("monorepo"))

    def _pull(node: dict) -> List[str]:
        out: List[str] = []
        fr = node.get("functional_requirements") or {}
        if not isinstance(fr, dict):
            return out
        feats = fr.get("features")
        if not feats:  # legacy: gate on must_have only (nice_to_have stays ungated)
            feats = fr.get("must_have_features") or []
        if isinstance(feats, list):
            for item in feats:
                s = str(item).strip()
                m = _FEATURE_ID_RE.match(s)
                if m:
                    out.append(m.group(0).upper())
        return out

    if monorepo:
        result: Dict[Optional[str], List[str]] = {}
        products = raw.get("products") or {}
        if isinstance(products, dict):
            for slug, prod in products.items():
                if isinstance(prod, dict):
                    result[slug] = _pull(prod)
        return result
    return {None: _pull(raw)}


def load_prd_data_volume(prd_path: Path) -> Optional[str]:
    """Return PRD.data_model.data_volume_estimate (or first product's), or None."""
    if not prd_path.exists():
        return None
    try:
        raw = yaml.safe_load(prd_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(raw, dict):
        return None

    monorepo = bool((raw.get("metadata") or {}).get("monorepo"))

    def _pull(node: dict) -> Optional[str]:
        dm = node.get("data_model") or {}
        if isinstance(dm, dict):
            v = dm.get("data_volume_estimate")
            if isinstance(v, str):
                return v
        return None

    if monorepo:
        for prod in (raw.get("products") or {}).values():
            if isinstance(prod, dict):
                v = _pull(prod)
                if v:
                    return v
    else:
        return _pull(raw)
    return None


def collect_traced_features(root: object) -> List[str]:
    """Aggregate traces_prd_features across all entities."""
    feats: List[str] = []
    entities = _get_dotted(root, "entities") or {}
    if not isinstance(entities, dict):
        return feats
    for entity in entities.values():
        tf = getattr(entity, "traces_prd_features", None)
        if isinstance(tf, list):
            for f in tf:
                m = _FEATURE_ID_RE.match(str(f).strip())
                if m:
                    feats.append(m.group(0).upper())
    return feats


class DataDeferralIndex:
    """The DEFER half of trace-or-defer (CLAUDE.md §6), for one scope.

    Canonical channel: the scope's `deferrals` list of {id, reason} (alias:
    `deferred_requirements`). Explicit, auditable, impossible to trigger by
    accident. In monorepo mode a product's coverage consults its own index
    AND the top-level one.

    DEPRECATED channel: the id appearing as a whole word in a data_warnings
    entry. Any note that happens to mention an FR silences its coverage gate,
    and nobody chooses that on purpose. Still honoured for one more version
    (no artifact flips red on upgrade); every prose-only hit is collected and
    reported once by `deprecation_warning()`.

    Malformed structured entries never defer anything: an entry without an
    id, or with an id but no reason, is reported and the gate stays armed.
    Replicates the task validator's DeferralIndex (do not import across
    skills — each plugin skill ships self-contained)."""

    def __init__(self, model: Any, label: str) -> None:
        self.label = label
        self.warnings: List[str] = [
            warning_text(w) for w in (getattr(model, "data_warnings", None) or [])
        ]
        self.declared: Dict[str, str] = {}
        self.shape_warnings: List[str] = []
        self.prose_only: set = set()
        self.prose_ok = _prose_deferrals_allowed(model)

        field = "deferrals"
        raw = getattr(model, "deferrals", None)
        if raw is None:
            raw = getattr(model, "deferred_requirements", None)
            field = "deferred_requirements"
        for i, entry in enumerate(raw or []):
            where = f"{label}{field}[{i}]"
            if not isinstance(entry, dict):
                self.shape_warnings.append(
                    f"{where} is not a mapping - expected {{id, reason}}; it defers nothing"
                )
                continue
            eid = str(entry.get("id") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            if not eid:
                self.shape_warnings.append(f"{where} declares no id - it defers nothing")
                continue
            if not reason:
                self.shape_warnings.append(
                    f"{where} defers '{eid}' with no reason - an unauditable deferral "
                    f"defers nothing; the coverage gate for '{eid}' stays armed"
                )
                continue
            self.declared[eid.upper()] = reason

        # A typed WRN entry with `kind: deferral` and `defers: [...]` declares
        # exactly what a `deferrals` entry declares, written where the author
        # already writes it. Reading it here is what lets the prose word-match
        # below be retired (CLAUDE.md sections 2 and 6).
        for _w in (getattr(model, "data_warnings", None) or []):
            if not isinstance(_w, dict):
                continue
            if str(_w.get("kind") or "").strip() != "deferral":
                continue
            _reason = str(_w.get("text") or "").strip()
            if not _reason:
                continue
            for _eid in (_w.get("defers") or []):
                _eid = str(_eid).strip()
                if _eid:
                    self.declared.setdefault(_eid.upper(), _reason)

    def defer(self, ids: Any, covered: Any = None) -> set:
        """The subset of `ids` this scope has deferred (structured first,
        prose fallback second). Returns the ids as given so call sites keep
        their own casing.

        `covered`: ids the calling gate already counts as traced/covered. A
        prose mention of one of those silences nothing, so it is deferred as
        before but NOT reported as a load-bearing prose deferral - the report
        used to name every mentioned id, and its remedy would have told the
        author to declare covered behaviour as intentionally out of scope
        (ledger IMP-042).
        """
        covered_up = {str(c).strip().upper() for c in (covered or []) if str(c).strip()}
        out: set = set()
        for i in ids or []:
            s = str(i).strip()
            if not s:
                continue
            if s.upper() in self.declared:
                out.add(i)
                continue
            pat = re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE)
            if self.prose_ok and any(pat.search(w) for w in self.warnings):
                out.add(i)
                if s.upper() not in covered_up:
                    self.prose_only.add(s.upper())
        return out

    def deprecation_warning(self) -> Optional[str]:
        if not self.prose_only:
            return None
        scope = self.label or ""
        return (
            f"{scope}{len(self.prose_only)} requirement(s) count as intentionally "
            f"out of scope only because a data_warnings note happens to mention "
            f"them: {join_ids(sorted(self.prose_only))}. That is fragile - any "
            f"note naming an id silences its coverage check. Declare each one "
            f"you meant in the top-level `deferrals` list as {{id, reason}}. "
            f"Notes still work for one more version. [deferral hygiene]"
        )


_STORE_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


def check_store_ids(root: object) -> "tuple[List[str], List[str]]":
    """Store-id integrity. Returns (gaps, warns):

    gaps — version-gated (error at data_model_version >= 3.0, warning below):
      every persistence.secondary_stores[] entry needs a `store_id` that is
      kebab-case, unique within the scope, and not the reserved word
      'primary'. ARCH containers (`realizes_store`) and entities.stored_in
      key on these ids.
    warns — always warning-level: entities.<E>.stored_in values must be
      'primary' or a declared store_id."""
    gaps: List[str] = []
    warns: List[str] = []
    persistence = _get_dotted(root, "persistence")
    stores = getattr(persistence, "secondary_stores", None) if persistence is not None else None
    declared: set = set()
    if isinstance(stores, list):
        for i, s in enumerate(stores):
            where = f"persistence.secondary_stores[{i}].store_id"
            sid = getattr(s, "store_id", None)
            if not sid or not str(sid).strip():
                gaps.append(
                    f"{where}: missing - every secondary store needs a stable "
                    f"kebab-case id (e.g. 'redis-cache') so /sdlc:arch containers "
                    f"and entities.stored_in can reference it"
                )
                continue
            sid = str(sid).strip()
            if sid == "primary":
                gaps.append(
                    f"{where}: 'primary' is reserved for the primary store - "
                    f"pick another id (the main store lives in primary_store)"
                )
            elif not _STORE_ID_RE.match(sid):
                gaps.append(
                    f"{where}: '{sid}' is not kebab-case (lowercase letters, "
                    f"digits, single hyphens; e.g. 'redis-cache')"
                )
            elif sid in declared:
                gaps.append(
                    f"{where}: '{sid}' is declared twice - store ids must be "
                    f"unique so a reference names exactly one store"
                )
            declared.add(sid)
    entities = _get_dotted(root, "entities")
    if isinstance(entities, dict):
        for ename, entity in entities.items():
            si = getattr(entity, "stored_in", None)
            if not isinstance(si, list):
                continue
            for v in si:
                v = str(v).strip()
                if v and v != "primary" and v not in declared:
                    warns.append(
                        f"entities.{ename}.stored_in: '{v}' names no declared "
                        f"secondary_stores[].store_id (and is not 'primary') - "
                        f"/sdlc:arch cannot bind this entity to a store. Add the "
                        f"store_id or drop the reference."
                    )
    return gaps, warns


def check_entity_lifecycles(root: object) -> List[str]:
    """Warn-level lifecycle wiring checks. The lifecycle block is what `test`
    seeds state-transition cases from and `task`/`code` copy into entity
    slices for guard logic — a lifecycle wired to a field or value set that
    does not exist produces tests and guards for states no row can hold."""
    warns: List[str] = []
    entities = _get_dotted(root, "entities")
    if not isinstance(entities, dict):
        return warns
    enums_block = _get_dotted(root, "enums_and_lookups")
    declared_enums: Dict[str, List[str]] = {}
    if enums_block is not None:
        raw_enums = getattr(enums_block, "enums", None)
        if isinstance(raw_enums, dict):
            for en, vals in raw_enums.items():
                if isinstance(vals, list):
                    declared_enums[str(en)] = [str(v) for v in vals]

    for ename, entity in entities.items():
        lc = getattr(entity, "lifecycle", None)
        if lc is None:
            continue
        fnames = _entity_field_names(root, ename)
        lfield = getattr(lc, "field", None)
        if lfield and fnames and lfield not in fnames:
            warns.append(
                f"entities.{ename}.lifecycle.field: '{lfield}' is not a field on "
                f"'{ename}' - tests and guard logic generated from this state "
                f"machine would read a column that does not exist. Name the "
                f"status-bearing field, or drop the lifecycle block."
            )
        transitions = getattr(lc, "transitions", None) or []
        terminal = [str(t) for t in (getattr(lc, "terminal", None) or [])]
        initial = getattr(lc, "initial", None)
        states: set = set()
        for t in transitions:
            frm = getattr(t, "from_", None)
            to = getattr(t, "to", None)
            if frm:
                states.add(str(frm))
            if to:
                states.add(str(to))
            if frm and str(frm) in terminal:
                warns.append(
                    f"entities.{ename}.lifecycle: terminal state '{frm}' has an "
                    f"outgoing transition - a terminal state has no exit. Remove "
                    f"it from `terminal` or drop the transition."
                )
        all_states = states | set(terminal) | ({str(initial)} if initial else set())
        if not all_states:
            continue
        # Value-set containment: the field's structured validation.enum wins;
        # otherwise, when the field is typed `enum`, any declared enum in
        # enums_and_lookups that covers the state set satisfies the check.
        candidates: List[set] = []
        fields = getattr(entity, "fields", None) or {}
        fspec = fields.get(lfield) if (lfield and isinstance(fields, dict)) else None
        val = getattr(fspec, "validation", None) if fspec is not None else None
        if isinstance(val, dict) and isinstance(val.get("enum"), list):
            candidates = [set(str(v) for v in val["enum"])]
        elif fspec is not None and getattr(fspec, "type", None) == FieldType.enum:
            candidates = [set(vs) for vs in declared_enums.values()]
        if candidates and not any(all_states <= c for c in candidates):
            warns.append(
                f"entities.{ename}.lifecycle: state(s) "
                f"{join_ids(sorted(all_states))} are not all listed in the value "
                f"set declared for field '{lfield}' - downstream tests would "
                f"assert states no declared enum allows. Align the lifecycle "
                f"states with the field's enum values."
            )
    return warns


def _index_hashes(docs_dir: Path) -> Dict[str, str]:
    """file -> sha256 from docs/INDEX.yaml generated_from, when present."""
    idx = docs_dir / "INDEX.yaml"
    if not idx.is_file():
        return {}
    try:
        raw = yaml.safe_load(idx.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    gf = (raw or {}).get("generated_from")
    out: Dict[str, str] = {}
    if isinstance(gf, dict):
        for fname, meta in gf.items():
            if isinstance(meta, dict) and meta.get("sha256"):
                out[str(fname)] = str(meta["sha256"])
    return out


def check_provenance(dm: "DataModel", docs_dir: Path) -> List[str]:
    """Warn-level provenance staleness (CLAUDE.md §7). Compare each recorded
    metadata.upstream_provenance sha256 to the upstream's current hash — from
    docs/INDEX.yaml generated_from when present, else the same normalized
    text hash `docs_index.py --hash` prints. Prefix-compare on 16 hex chars
    so recorded prefixes and full digests interoperate. Also warn when a
    `complete` artifact carries no provenance at all (gated to
    data_model_version >= 3.0 so legacy files stay quiet)."""
    warns: List[str] = []
    prov = dm.metadata.upstream_provenance
    if not prov:
        if (
            dm.metadata.status == "complete"
            and _version_tuple(dm.metadata.data_model_version) >= _PARADIGM_GATE_VERSION
        ):
            warns.append(
                "metadata.upstream_provenance is missing - nothing can tell "
                "whether the upstream PRD/UX changed since this file was "
                "written. The next /sdlc:data run records it."
            )
        return warns
    index_hashes = _index_hashes(docs_dir)
    for entry in prov:
        if not isinstance(entry, dict):
            continue
        f = entry.get("file")
        recorded = str(entry.get("sha256") or "").strip()
        if not f or not recorded:
            continue
        fname = Path(str(f)).name
        current = index_hashes.get(fname) or index_hashes.get(str(f))
        if current is None:
            for cand in (Path(str(f)), docs_dir / fname):
                if cand.is_file():
                    try:
                        text = cand.read_text(encoding="utf-8")
                    except (OSError, UnicodeDecodeError):
                        break
                    current = hashlib.sha256(text.encode("utf-8")).hexdigest()
                    break
        if current is None:
            continue  # upstream absent - a missing input is Phase 2's finding, not a hash mismatch
        if current[:16] != recorded[:16]:
            warns.append(
                f"built against an older docs/{fname} - run /sdlc:data to "
                f"review the delta"
            )
    return warns


def check_feature_coverage(
    prd_features: List[str],
    traced: List[str],
    deferred: Optional[set] = None,
) -> List[str]:
    """Return PRD FR-NNN IDs that no entity traces AND no warning defers."""
    covered = {f.upper() for f in traced}
    if deferred:
        covered |= deferred
    return [f for f in prd_features if f.upper() not in covered]


def check_volume_scale_gate(volume: Optional[str], root: object) -> Optional[str]:
    """If PRD volume ∈ {terabytes, petabytes}, scale_and_retention must be present
    and non-null. Returns an error string, or None."""
    if volume not in ("terabytes", "petabytes"):
        return None
    sar = _get_dotted(root, "scale_and_retention")
    if sar is None:
        return (
            f"scale_and_retention is required when PRD.data_volume_estimate "
            f"== '{volume}' but is absent"
        )
    # Must have at least one substantive field set.
    has_any = any(
        getattr(sar, name, None) is not None
        for name in (
            "partitioning_key",
            "partitioning_strategy",
            "sharding_key",
            "retention_policies",
        )
    )
    if not has_any:
        return (
            f"scale_and_retention is present but empty; PRD.data_volume_estimate "
            f"== '{volume}' requires at least one of partitioning_key, "
            f"partitioning_strategy, sharding_key, or retention_policies"
        )
    return None


# =============================================================================
# Driver
# =============================================================================


def _format_pydantic_errors(err: ValidationError) -> List[str]:
    formatted: List[str] = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e.get("loc", ()))
        msg = e.get("msg", "invalid")
        formatted.append(f"{loc}: {msg}")
    return formatted


def validate_file(path: Path) -> int:
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error in {path}:\n  {e}", file=sys.stderr)
        return 2

    if raw is None:
        print(f"ERROR: {path} is empty", file=sys.stderr)
        return 2

    if not isinstance(raw, dict):
        print(
            f"ERROR: {path} top level must be a mapping, got {type(raw).__name__}",
            file=sys.stderr,
        )
        return 2

    try:
        dm = DataModel.model_validate(raw)
    except ValidationError as e:
        print(f"[FAIL] {path} does not match the schema. No later "
              f"skill can read it until these fields are fixed:\n")
        print("Errors:")
        for line in _format_pydantic_errors(e):
            print(f"  - {line}")
        return 1

    # Per-product or single-product cross-checks.
    docs_dir = path.parent
    prd_path = docs_dir / "PRD.yaml"
    prd_exists = prd_path.exists()
    prd_features_by_scope = load_prd_features(prd_path)
    prd_volume = load_prd_data_volume(prd_path)

    relationship_errs: List[str] = []
    field_ref_errs: List[str] = []
    classification_errs: List[str] = []
    bounded_ctx_errs: List[str] = []
    trace_id_errs: List[str] = []
    paradigm_errs: List[str] = []
    uncovered_features: List[str] = []
    volume_errs: List[str] = []
    store_gaps: List[str] = []
    union_gaps: List[str] = []
    stored_in_warns: List[str] = []
    lifecycle_warns: List[str] = []
    paradigm_none_warns: List[str] = []
    coverage_skips: List[str] = []     # scopes whose paradigm is `none`
    checked_features = 0               # features actually gated (skips excluded)

    warning_id_errs = check_warning_ids(dm.data_warnings or [])

    # The DEFER half of trace-or-defer: structured `deferrals` first, a
    # data_warnings prose mention as a reported fallback (one more version).
    top_dfr = DataDeferralIndex(dm, "")
    scope_dfrs: List[DataDeferralIndex] = [top_dfr]

    def _per_scope(
        scope_label: str,
        root: object,
        scope_features: List[str],
        dfrs: List[DataDeferralIndex],
    ) -> None:
        nonlocal checked_features
        scope = scope_label if scope_label else ""
        for e_ in check_relationship_integrity(root):
            relationship_errs.append(f"{scope}{e_}")
        for e_ in check_field_references(root):
            field_ref_errs.append(f"{scope}{e_}")
        for e_ in check_classification_integrity(root):
            classification_errs.append(f"{scope}{e_}")
        for e_ in check_bounded_context_partition(root):
            bounded_ctx_errs.append(f"{scope}{e_}")
        for e_ in check_trace_id_formats(root):
            trace_id_errs.append(f"{scope}{e_}")
        # Paradigm-specific structural integrity. Each function no-ops when its
        # block is absent, so running them for every scope is safe.
        for e_ in check_edge_integrity(root):
            paradigm_errs.append(f"{scope}{e_}")
        for e_ in check_composition_integrity(root):
            paradigm_errs.append(f"{scope}{e_}")
        for e_ in check_cross_reference_integrity(root):
            paradigm_errs.append(f"{scope}{e_}")
        for e_ in check_vector_config(root):
            paradigm_errs.append(f"{scope}{e_}")
        for e_ in check_identity_conventions(root):
            paradigm_errs.append(f"{scope}{e_}")
        for e_ in check_key_value_design(root):
            paradigm_errs.append(f"{scope}{e_}")
        gaps, si_warns = check_store_ids(root)
        store_gaps.extend(f"{scope}{g}" for g in gaps)
        union_gaps.extend(f"{scope}{g}" for g in check_union_integrity(root))
        stored_in_warns.extend(f"{scope}{w}" for w in si_warns)
        lifecycle_warns.extend(f"{scope}{w}" for w in check_entity_lifecycles(root))
        # Volume-vs-scale only applies to paradigms with partitioning/sharding.
        if _paradigm_of(root) in (Paradigm.relational, Paradigm.document, Paradigm.key_value):
            volume_err = check_volume_scale_gate(prd_volume, root)
            if volume_err:
                volume_errs.append(f"{scope}{volume_err}")

        if _paradigm_of(root) == Paradigm.none:
            # Stateless scope: nothing stores data, so requirement coverage is
            # not gated here. The summary says so - never a vacuous claim.
            coverage_skips.append(scope_label.rstrip(".") if scope_label else "this project")
            n_declared = len(_entity_names(root))
            if n_declared:
                paradigm_none_warns.append(
                    f"{scope}persistence.paradigm is 'none' (no persisted state) "
                    f"but {n_declared} entit(y/ies) are defined - drop them, or "
                    f"pick a real storage paradigm."
                )
            return
        checked_features += len(scope_features)
        traced = collect_traced_features(root)
        deferred: set = set()
        for d in dfrs:
            deferred |= d.defer(scope_features, covered=traced)
        for f in check_feature_coverage(scope_features, traced, deferred):
            uncovered_features.append(f"{scope}{f}")

    if dm.metadata.monorepo and dm.products:
        for slug, product in dm.products.items():
            scope_features = prd_features_by_scope.get(slug, [])
            p_dfr = DataDeferralIndex(product, f"products.{slug}.")
            scope_dfrs.append(p_dfr)
            _per_scope(f"products.{slug}.", product, scope_features, [p_dfr, top_dfr])
    else:
        single_features = prd_features_by_scope.get(None, [])
        _per_scope("", dm, single_features, [top_dfr])

    missing = check_required(dm)
    status = dm.metadata.status

    # ⚠D: undeclared paradigm — blocking error at/after the gate version,
    # warning below it (version-gated per CLAUDE.md §10).
    paradigm_decl_gaps = check_paradigm_declared(dm)
    _paradigm_gated = _version_tuple(dm.metadata.data_model_version) >= _PARADIGM_GATE_VERSION
    paradigm_decl_errs = paradigm_decl_gaps if _paradigm_gated else []
    paradigm_decl_warns = [] if _paradigm_gated else paradigm_decl_gaps

    # Store ids share the 3.0 floor: error at/after it, warning below.
    store_gap_errs = store_gaps if _paradigm_gated else []
    store_gap_warns = [] if _paradigm_gated else store_gaps
    # Union integrity shares it too (a construct that never existed before
    # cannot have been stamped complete by an older version, but the floor
    # keeps the meta-corpus's private extension quiet until it is migrated).
    union_errs = union_gaps if _paradigm_gated else []
    union_warns = [] if _paradigm_gated else union_gaps

    # Deferral hygiene (warn-level): malformed structured entries + ids that
    # only the deprecated prose fallback deferred.
    deferral_warns: List[str] = []
    for d in scope_dfrs:
        deferral_warns.extend(d.shape_warnings)
    for d in scope_dfrs:
        dep = d.deprecation_warning()
        if dep:
            deferral_warns.append(dep)

    provenance_warns = check_provenance(dm, docs_dir)

    n_scopes = len(dm.products or {}) if (dm.metadata.monorepo and dm.products) else 1
    all_stateless = n_scopes > 0 and len(coverage_skips) == n_scopes

    prd_absent_warns: List[str] = []
    if not prd_exists and not all_stateless:
        prd_absent_warns.append(
            "docs/PRD.yaml was not found next to this file, so the "
            "requirement-coverage check could not run - 0 requirement(s) were "
            "checked, which is not the same as all-covered. Run /sdlc:prd "
            "first (or move this file beside its PRD), then re-run this check."
        )

    skip_notes: List[str] = []
    if coverage_skips and not all_stateless:
        skip_notes.append(
            f"paradigm 'none' - no persisted state in {join_ids(coverage_skips)}; "
            f"requirement coverage was skipped there (nothing stores data)."
        )

    # Hard errors (block status:complete): missing required, relationship integrity,
    # field references, classification integrity, bounded-context partition,
    # store-id integrity (>= 3.0), mode mismatch (caught by the pydantic
    # model_validator). Soft errors (force draft): feature coverage gaps,
    # volume-vs-scale gate.

    hard_problems = bool(
        missing
        or relationship_errs
        or field_ref_errs
        or classification_errs
        or bounded_ctx_errs
        or warning_id_errs
        or trace_id_errs
        or paradigm_errs
        or paradigm_decl_errs
        or store_gap_errs
        or union_errs
    )
    soft_problems = bool(uncovered_features or volume_errs)

    def _problems():
        out = []
        out += [f"a required field is empty: {m}" for m in missing]
        out += [f"wrong id format in data_warnings - {e_}" for e_ in warning_id_errs]
        out += [f"wrong id format in an entity trace - {e_}" for e_ in trace_id_errs]
        out += [f"a relationship points at something that does not exist - {e_}"
                for e_ in relationship_errs]
        out += [f"a field reference does not resolve - {e_}" for e_ in field_ref_errs]
        out += [f"an entity classification is inconsistent - {e_}"
                for e_ in classification_errs]
        out += [f"the bounded-context grouping does not partition cleanly - {e_}"
                for e_ in bounded_ctx_errs]
        out += [f"the storage structure is not valid for the chosen paradigm - {e_}"
                for e_ in paradigm_errs]
        out += [f"a secondary store id is missing or invalid - {e_}"
                for e_ in store_gap_errs]
        out += [f"a union entity cannot be resolved - {e_}" for e_ in union_errs]
        if paradigm_decl_errs:
            out.append(
                f"{len(paradigm_decl_errs)} store(s) do not say which kind of storage "
                f"they are (relational, document, key-value, graph, vector, files): "
                f"{join_ids(paradigm_decl_errs)}. Set persistence.paradigm explicitly "
                f"- leaving it blank silently assumes SQL.")
        if uncovered_features:
            ids = [str(f).split(":", 1)[0].strip() for f in uncovered_features]
            out.append(
                f"{len(uncovered_features)} requirement(s) from the PRD store no data "
                f"here and nothing says why: {join_ids(ids)}. Add an entity, or "
                f"defer each one in the top-level `deferrals` list as "
                f"{{id, reason}}.")
        out += [f"the expected data volume does not match the scale settings - {e_}"
                for e_ in volume_errs]
        return out

    def _soft():
        out: List[str] = []
        if paradigm_decl_warns:
            out.append(
                f"{len(paradigm_decl_warns)} store(s) do not say which kind of storage "
                f"they are, so SQL is assumed: {join_ids(paradigm_decl_warns)}. Set "
                f"persistence.paradigm explicitly."
            )
        out += [f"a secondary store id is missing or invalid - {e_} "
                f"(this blocks from data_model_version 3.0)"
                for e_ in store_gap_warns]
        out += [f"a union entity cannot be resolved - {e_} "
                f"(this blocks from data_model_version 3.0)"
                for e_ in union_warns]
        out += stored_in_warns
        out += lifecycle_warns
        out += paradigm_none_warns
        out += deferral_warns
        out += provenance_warns
        out += prd_absent_warns
        out += skip_notes
        return out

    n_entities = (
        sum(len(pr.entities or {}) for pr in (dm.products or {}).values())
        if (dm.metadata.monorepo and dm.products)
        else len(dm.entities or {})
    )

    if status == "complete":
        problems = _problems()
        soft = _soft()
        if problems:
            print(f"[FAIL] {path} says it is finished, but {len(problems)} thing(s) "
                  f"are wrong. /sdlc:api and everything after it will refuse it.")
            print_findings(problems, soft)
            print_next("fix the items above, then re-run this check.",
                       "Re-running /sdlc:data walks you through them.")
            return 1
        if all_stateless:
            print(f"[OK] {path} is finished - persistence.paradigm is 'none': "
                  f"nothing stores data, so the PRD requirement-coverage check "
                  f"was skipped. /sdlc:api can run it (or skip to /sdlc:arch "
                  f"if there is no API).")
        elif not prd_exists:
            print(f"[OK] {path} is finished - {n_entities} data entit(y/ies). "
                  f"The PRD requirement check could not run (docs/PRD.yaml not "
                  f"found - see WARNINGS). /sdlc:api can run it (or skip to "
                  f"/sdlc:arch if there is no API).")
        else:
            print(f"[OK] {path} is finished - {n_entities} data entit(y/ies), all "
                  f"{checked_features} PRD requirement(s) accounted for. /sdlc:api "
                  f"can run it (or skip to /sdlc:arch if there is no API).")
        print_findings([], soft)
        print_next("/sdlc:api  (or /sdlc:arch if the system has no API)",
                   show_glossary=bool(soft))
        return 0

    # status == "draft"
    todo = _problems()
    soft = _soft()
    print(f"[DRAFT] {path} is saved but not finished - {n_entities} entit(y/ies) so "
          f"far, {checked_features} PRD requirement(s) found upstream. Later skills "
          f"will refuse it until it says 'complete'.")
    print_findings(todo, soft, blocking_header="TO FINISH IT")
    print_next("re-run /sdlc:data to continue, or set metadata.status: complete.",
               show_glossary=bool(todo or soft))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DATA-MODEL.yaml against the sdlc-data schema."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs", "DATA-MODEL.yaml"),
        help="Path to DATA-MODEL.yaml (default: ./docs/DATA-MODEL.yaml).",
    )
    args = parser.parse_args(argv)
    return validate_file(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
