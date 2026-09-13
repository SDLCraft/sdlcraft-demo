# Paradigm: graph

Neo4j, ArangoDB, Neptune, JanusGraph. Nodes and **first-class edges**. Edges
carry their own properties and have no join table. The reason to pick a graph
is that your dominant queries are *traversals* — "friends of friends", "shortest
path", "everything reachable from X within N hops" — which are painful and slow
as recursive SQL joins.

## When to recommend

Recommend `graph` when the PRD shows:

- **Traversal-centric queries** — recommendations, social graphs,
  dependency/impact analysis, knowledge graphs, fraud rings, routing.
- **Relationships are first-class domain objects**, often with their own
  attributes (a FOLLOWS edge has a `since`; a TRANSFERRED_TO edge has an
  `amount`).
- **Variable-depth / recursive relationships** where the join depth isn't known
  in advance.
- The PRD's `key_entities` + workflows describe a densely interconnected web,
  not a few foreign keys.

Lean away when relationships are shallow and fixed (a couple of FKs → relational
is simpler), or when there are essentially no relationships (→ document/kv).

## Entity-field shape

Entities are **nodes**. Each carries:

- `node_label` (optional; defaults to the entity key) — the graph label.
- `fields` — node properties (reuse the relational `type`/`nullable` attrs).
- No `primary_key` requirement (node identity is the store's concern).

## Analogue themes to run (Phase 6)

1. **edges** (REQUIRED — may be empty for a nodes-only graph) — the
   relationships. For each:

   ```yaml
   edges:
     - type: FOLLOWS                # UPPER_SNAKE relationship type
       from_entity: User            # must resolve to an entity key/node_label
       to_entity: User
       cardinality: "N:M"           # "1:1"|"1:N"|"N:M"
       direction: directed          # directed|undirected
       properties: { since: timestamp }
   ```

   Edges are NOT relational relationships — never ask about join tables or
   `on_delete` cascade here.

2. **graph_config** — node-label inventory + named traversal patterns (the
   graph analogue of access_patterns):

   ```yaml
   graph_config:
     node_labels: [User, Post]
     traversal_patterns:
       - description: "Friends-of-friends up to 3 hops."
         start_label: User
         pattern: "(:User)-[:FOLLOWS*1..3]->(:User)"
   ```

Skip-instead: `relationships`, `id_strategy`, `indexes_and_queries`,
`integrity_and_constraints`, `scale_and_retention`,
`transactions_and_consistency`, `migrations_and_evolution`.

## Validator notes

Required (status: complete): `edges` (key present; empty list OK). Cross-check:
every edge's `from_entity`/`to_entity` resolves to an entity key or its
`node_label`. No volume/index/constraint checks.
