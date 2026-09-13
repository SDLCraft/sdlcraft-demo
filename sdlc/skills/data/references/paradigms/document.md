# Paradigm: document

MongoDB, Firestore, Couchbase. Schemaless-ish collections of JSON-like
documents. Related data is often **embedded** inside a parent document rather
than split across normalized tables; cross-collection links travel as stored
ids. Has real indexes and a query language, so it sits close to relational —
but the modeling instinct is "design the document around your access patterns,
embed what you read together."

## When to recommend

Recommend `document` when the PRD shows:

- **Aggregate-oriented data** — an entity and its children are almost always
  read/written together (an Order with its line items as one document).
- **Flexible / evolving schema** — fields vary across records, or the shape is
  still in flux and per-document variation is acceptable.
- **Hierarchical / nested payloads** — content trees, form submissions, config
  blobs that are naturally one nested object.
- **Horizontal scale with mostly-aggregate access**, but still wanting indexes
  and ad-hoc queries (the thing key_value can't give you).

Lean away when: the data is highly relational with many-to-many joins (→
relational), traversal-centric (→ graph), or purely single-key (→ key_value).

## Entity-field shape

Same field block as relational (`type`, `nullable`, `unique`, `primary_key`,
optionally `references` for id links), with two adjustments:

- `primary_key` is required (the document `_id`, often `id`).
- Prefer **embedding** over foreign keys: a child entity that's always read
  with its parent is recorded as a `composition` entry with `kind: embeds`
  rather than a relationship. Use `cross_references` for the genuine
  cross-collection id links you keep normalized.

## Analogue themes to run (Phase 6)

Run the relational `id_strategy` and `indexes_and_queries` themes (they apply),
PLUS:

1. **composition** — for each parent/child that is embedded or contained:
   `{parent, child, kind: embeds|contains|references, comment}`. `embeds`
   means the child lives inside the parent document; `references` means it's a
   separate collection linked by id.

2. **cross_references** — normalized id links between collections:
   `{from_entity, field, to_entity, comment}`. These are the references you
   chose NOT to embed. Before closing the theme, run the **gate-clause
   sweep** (canonical spec: `references/paradigms/file-native.md` →
   "Gate-clause sweep"): every field an upstream-named referential/coverage
   gate queries gets a cross_references row or an explicit `WRN-NNN`
   carve-out — never silent omission.

Skip-instead: `relationships` (use composition + cross_references),
`integrity_and_constraints` (enforced in app code / Pydantic),
`transactions_and_consistency` (document stores have limited multi-doc tx —
note any needed boundaries in a `data_warnings` entry).

## Validator notes

Required (status: complete): `id_strategy.scheme`,
`indexes_and_queries.access_patterns` (present, empty OK). Cross-checks:
composition parent/child resolve; cross_references resolve; field references
resolve; volume-vs-scale gate applies (TB/PB → scale_and_retention required).
