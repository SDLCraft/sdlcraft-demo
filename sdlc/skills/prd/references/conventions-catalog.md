# Conventions catalogue — bucket archetypes to reason from

Read this when entering the `conventions` mini-section (the last thing the PRD
interview does). It is the menu the agent reasons *from* when proposing
convention buckets in the `nested_freeform` step-a — **not** a checklist to fill.

## Why conventions deserve a deliberate pass

`conventions` is a `Dict[str, Any]` of named buckets, each capturing a
cross-cutting rule that **every downstream stage must honour verbatim**: naming
and ID rules, schema-versioning policy, which PRD fields each later stage must
read, code-layering invariants, severity rubrics, supply-chain policy. These are
the rules that, if left implicit, every downstream agent silently reinvents
differently — the single biggest source of drift between PRD intent and what the
later artifacts actually encode.

The PRD interview runs `conventions` **last, on purpose**: by now you have read
the whole project — problem, users, workflows, every FR/NFR, the tech stack, the
data hints. This is a **synthesis pass**, not a fill-in-the-blanks question. Do
for conventions what the scope-completeness sweep does for the FR list: reflect
across *all* prior answers and the project type, then surface concrete buckets
the project actually needs.

In practice this block is where the most manual rework happens when it's done
thinly — agents propose two or three obvious buckets and miss the cross-stage
contracts that make the difference. Working from the archetypes below, and from
an honest reflection on this specific project, is how you avoid that.

## How to run the synthesis

Before proposing buckets (step a of the `nested_freeform` flow in
`importance-flows.md`), do a structured reflection over three lenses — the same
discipline as the FR scope sweep:

1. **The answers themselves.** Did an ID/naming scheme span multiple lists? Did
   the same term recur with a precise meaning? Did NFRs name downstream stages?
   Did a code-style or testing rule keep surfacing? Each recurrence is a bucket
   candidate.
2. **Every upstream ID family.** FR/NFR/ENT/WKF/INT/AIF — a rule that governs how
   one family is referenced by later stages (e.g. "every FR-### must trace to a
   container") is a convention, not a feature.
3. **The project type.** A CLI tool, a SaaS app, a library/SDK, a data pipeline,
   an AI-orchestration framework, a regulated fintech app — each carries a
   different set of "rules everyone forgets to write down". Let the project's own
   profile drive which archetypes apply.

Then propose the buckets you actually see (step a). **Anti-padding holds**: a
small single-purpose utility may legitimately have *zero* conventions — don't
manufacture buckets to look thorough. The archetypes are prompts for recognition,
not quotas.

## The archetypes

Each entry: **propose when** you see the trigger; **captures** what goes in the
body; the skeleton is one *possible* shape — bodies are free-form and
project-defined, so adapt.

### `artifact_ids` — cross-stage ID & naming rules
- **Propose when:** stable IDs (FR-###, ENT-###, …) are referenced across lists,
  or the user named a file/entity/field naming scheme.
- **Captures:** which ID families exist, what each means, casing rules
  (PascalCase entities, kebab-case slugs), file-naming patterns, what is stable
  vs editable.
```yaml
artifact_ids:
  binding: true
  description: "Canonical cross-stage IDs; the prefix is the stable contract, the text is editable."
  id_types: { FR: "Functional Requirement", ENT: "Data entity", SCR: "UX surface" }
  naming: { entities: PascalCase, fields: snake_case, slugs: kebab-case }
```

### `schema_versioning` — artifact version & migration policy
- **Propose when:** the project versions its artifacts/schemas, or back-compat
  matters.
- **Captures:** version scheme (per-artifact semver?), where the version lives,
  migration policy for breaking changes.
```yaml
schema_versioning:
  policy: "Per-artifact semver on every artifact; evolves independently."
  migration: "Breaking changes ship a forward-migration script under tools/migrations/."
```

### `nfr_propagation` — which PRD/NFR fields each downstream stage must read
- **Propose when:** NFRs or security/compliance fields constrain later stages and
  you want to guarantee they aren't silently dropped. (LLM stage agents reliably
  miss NFRs without explicit routing.)
- **Captures:** a map from a PRD field path → the downstream stages/FRs that must
  consult it and what they do with it.
```yaml
nfr_propagation:
  description: "Stage prompts MUST read the listed PRD fields when generating their artifact."
  map:
    "security_compliance.data_sensitivity":
      - "Data Model: PII tagging, encryption-at-rest, retention"
      - "Deployment: region/residency constraints"
    "non_functional_requirements.performance_targets":
      - "Architecture: scaling pattern, caching, async topology"
```

### `code_style` — layering & coding invariants
- **Propose when:** the user named a dependency-direction rule, module layering,
  import discipline, or a formatter/linter that gates merges.
- **Captures:** allowed dependency direction between layers, import rules,
  formatter/linter, file-size or complexity limits.
```yaml
code_style:
  layering: "config -> core -> ui; never import sideways or upward."
  formatter: "ruff format; ruff + mypy --strict gate CI."
```

### `testing_policy` — coverage, tiers, what must be tested
- **Propose when:** coverage thresholds, test tiers, or required test categories
  came up.
- **Captures:** pyramid targets, coverage floors, which artifacts/FRs require
  tests, gate behaviour.
```yaml
testing_policy:
  pyramid: { unit: 0.7, integration: 0.25, e2e: 0.05 }
  coverage_floor: 0.8
  rule: "Every FR-### must trace to >=1 TST-###."
```

### `severity_rubric` — how findings/issues are graded
- **Propose when:** the project reviews security, compliance, or quality findings
  and needs a consistent severity scale.
- **Captures:** the severity levels, what each means, gate-blocking threshold.
  (Often split into `security_severity_rubric` / `compliance_severity_rubric`.)
```yaml
security_severity_rubric:
  levels: { critical: "blocks release", high: "fix before GA", medium: "backlog", low: "advisory" }
  gate_blocks_at: high
```

### `dependency_supply_chain_policy` — deps, pinning, licences
- **Propose when:** the project restricts dependencies, pins versions, or enforces
  a licence allowlist.
- **Captures:** allowed/banned deps, pinning rule, licence allowlist, vendoring,
  advisory-scan policy.
```yaml
dependency_supply_chain_policy:
  pinning: "All runtime deps pinned in the lockfile; no floating ranges."
  licences_allowed: [MIT, Apache-2.0, BSD-3-Clause]
  scan: "Fail CI on a known advisory at >= high severity."
```

### `directory_layout` — repo topology & where things live
- **Propose when:** the user described where code/docs/artifacts live, or it's a
  monorepo with a product layout convention.
- **Captures:** top-level layout, monorepo product paths, generated-artifact roots.
```yaml
directory_layout:
  source: "src/<pkg>/"
  generated_artifacts: "docs/"
  monorepo_products: "packages/<product-slug>/"
```

### `data_conventions` — modelling rules for the data stage
- **Propose when:** the user stated identity rules, an enum-vs-literal policy, or a
  serialization format that the Data Model stage must follow.
- **Captures:** identity/PK rules, enum promotion policy, serialization format,
  timestamp/timezone rules.
```yaml
data_conventions:
  identity: "No UUIDs; identity is path-derived for singleton artifacts."
  enum_policy: "Promote a Literal to a named enum when reused across >=2 entities."
  serialization: yaml
```

### `api_conventions` — cross-cutting API rules (when an API stage applies)
- **Propose when:** the product exposes an API and the user named versioning,
  pagination, or error-envelope rules.
- **Captures:** versioning scheme, pagination style, canonical error envelope,
  auth header convention.
```yaml
api_conventions:
  versioning: "URI prefix /v1; breaking change => /v2."
  errors: "RFC 9457 problem+json envelope for every 4xx/5xx."
```

### `observability` — required signals & telemetry conventions
- **Propose when:** logging/metrics/tracing requirements or an audit-log mandate
  surfaced.
- **Captures:** required signals, log format, trace/span conventions, retention.
```yaml
observability:
  log_format: "structured JSON; one event per line."
  required_signals: [request_latency, error_rate, audit_log]
```

### `domain_glossary` — canonical terms
- **Propose when:** the same domain term recurred with a precise meaning that
  downstream stages must use identically.
- **Captures:** term → definition, so UX/API/Data don't diverge on vocabulary.
```yaml
domain_glossary:
  Run: "One end-to-end execution of the pipeline for a single branch."
  Stage: "One pipeline step that consumes an upstream artifact and emits the next."
```

### `stage_contracts` — what each downstream artifact consumes/produces
- **Propose when:** the project is itself a multi-stage pipeline, or the user wants
  to pin cross-stage hand-off contracts beyond `nfr_propagation`.
- **Captures:** per-stage owning FR, the upstream fields it reads, the artifact it
  emits. (Generalises the demo's `stage_dossiers` / `stage_tool_inventory`.)
```yaml
stage_contracts:
  data_model: { owning_fr: "FR-007", reads: ["functional_requirements", "data_model"], emits: "DATA-MODEL.yaml" }
```

## Caps & cadence (defer to `importance-flows.md`)

The `nested_freeform` flow owns the per-bucket draft/approve loop, EXIT handling,
and state-write timing. Conventions-rich projects legitimately run to a dozen-plus
buckets — do not let a low bucket cap force you to drop real cross-cutting rules;
follow the caps as stated in `importance-flows.md`, deferring only genuine
overflow to `prd_warnings`.
