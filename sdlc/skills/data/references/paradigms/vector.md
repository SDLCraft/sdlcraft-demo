# Paradigm: vector

Pinecone, Qdrant, Weaviate, Milvus, Chroma, pgvector, LanceDB. Stores
high-dimensional embedding vectors and serves **approximate nearest-neighbor
(ANN)** similarity search. Each record is an embedding plus a payload of
filterable metadata. The reason to pick it is semantic search / RAG /
recommendation-by-similarity — "find the items closest in meaning to this
query", which keyword and SQL stores cannot do.

## When to recommend

Recommend `vector` when the PRD shows:

- **Semantic search / RAG** — "search documents by meaning", "answer questions
  over a corpus", retrieval-augmented generation.
- **Similarity / recommendation by embedding** — "items like this one",
  near-duplicate detection, clustering.
- Language in features about embeddings, vectors, similarity, relevance,
  nearest-neighbor, or an LLM that needs retrieval.

**Often a SECONDARY store, not the primary.** Most products keep their source
of truth in relational/document/file and add a vector store as a derived index.
If so, pick the primary paradigm for the source of truth and record the vector
store under `persistence.secondary_stores` (see `polyglot-persistence.md`).
Choose `vector` as the *primary* paradigm only when similarity search is the
product's core and there's little other relational state.

## Entity-field shape

Entities are **collections** of vectors. Each carries:

- `payload_fields` — the metadata stored alongside the vector and used for
  filtering (e.g. `[source_id, title, chunk_index]`).
- `fields` — declare the payload fields (reuse relational `type`), and mark the
  field the embedding is computed from with `embedding: true`.
- No `primary_key` requirement (point id is the store's concern).

```yaml
entities:
  DocumentChunk:
    description: "A chunk of source text plus its embedding + retrieval payload."
    payload_fields: [source_id, chunk_index, title]
    fields:
      text:   { type: text, embedding: true }   # vector computed from this
      source_id: { type: string }
      title:  { type: string }
    traces_prd_features: [FR-001]
```

## Analogue themes to run (Phase 6)

1. **vector_config** (REQUIRED) — the embedding + index configuration:

   ```yaml
   vector_config:
     embedding_model: "text-embedding-3-large"   # REQUIRED
     dimensions: 3072                             # REQUIRED — must match the model
     distance_metric: cosine                      # REQUIRED — cosine|euclidean|dot_product|manhattan
     ann_index: hnsw                              # hnsw|ivf|ivf_flat|ivf_pq|flat|diskann|other
     index_params: { m: 16, ef_construct: 200 }
   ```

   Pin the embedding model and its dimension count together — a mismatch is the
   most common vector bug. Pick the distance metric the model was trained for
   (cosine for most text-embedding models).

Skip-instead: `id_strategy`, `relationships`, `indexes_and_queries`,
`integrity_and_constraints`, `scale_and_retention`,
`transactions_and_consistency`, `migrations_and_evolution`.

## Validator notes

Required (status: complete): `vector_config` present, with `embedding_model`,
`dimensions`, and `distance_metric` all set. No relationship/index/constraint/
volume checks. (`pgvector` as `primary_store` is the one case where you might
ALSO want relational blocks — model that as relational primary + a vector
secondary instead, unless similarity search truly dominates.)
