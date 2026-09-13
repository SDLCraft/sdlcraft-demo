# Architecture pattern selection — narrative guidance

This file contains the narrative guidance for selecting an
`architecture_pattern.pattern` value at the system level. The
machine-readable matrix lives in `pattern-selection.yaml`. Load both
together when running the `architecture_pattern` theme.

## When to recommend (and when not to)

Do not hard-bias toward any single pattern. A recommendation requires
evidence. The right inputs:

- **Team count and ownership boundaries** — fewer teams tolerates more
  shared state; many teams needs hard service boundaries.
- **Expected scale asymmetry** — if one capability dwarfs the rest in
  load, extracting it changes the calculus.
- **Independent deployment needs** — if teams want to deploy without
  coordinating, event-driven or microservices patterns become attractive.
- **Domain complexity** — rich domain logic with many invariants pushes
  toward hexagonal / DDD-shaped slices; simple CRUD does not need that
  overhead.
- **Number of external integrations** — many external systems favor an
  API gateway or adapter layer.
- **Async workflow needs** — long-running, retryable, or fan-out
  workflows naturally fit event-driven or choreography patterns.
- **Plugin / extensibility needs** — extensible platforms lean toward
  plugin architectures or clean hexagonal boundaries.
- **Ops maturity** — a single-pizza-team with no SRE function should
  not choose a pattern that requires distributed tracing to debug.
- **Observability tolerance** — distributed patterns produce many
  moving parts that require observability investment proportional to
  their complexity.

## AI-builder considerations

Because the system will be built primarily by AI agents, the
`ai_builder_notes` field in `pattern-selection.yaml` must be consulted
in every recommendation. Key axes:

- **Moving parts** — fewer containers = fewer surfaces where an AI
  agent can introduce a subtle integration bug. Prefer monolithic or
  modular-monolith patterns when the domain doesn't require
  independent scaling or deployment.
- **Interface explicitness** — AI-built code benefits from well-typed
  interfaces between components. Patterns that expose boundaries as
  explicit typed contracts (hexagonal, clean) are easier for agents
  to test and verify.
- **Failure locality** — AI-generated error handling has high
  variability. Patterns where a failure in one module cannot cascade
  (process-isolated services) reduce blast radius, but add
  operational overhead.
- **Tracing** — distributed patterns require tracing to diagnose
  subtle bugs. Weigh the observability investment.
- **Testability** — layered / hexagonal patterns with inversion of
  control produce components that are easy to unit-test with mocks.
  AI agents produce more reliable code when the test feedback loop is
  fast and local.
- **Contract stability** — event-driven patterns require stable event
  schemas. AI-generated schema migrations are risky; prefer versioned
  schemas or schema-registry patterns when going async.

## Recommendation process

1. Load `pattern-selection.yaml`. Identify the 2–3 top candidates
   from the inputs above.
2. For each candidate, summarize `best_when`, `tradeoffs`,
   `disqualifiers`, and `ai_builder_notes`.
3. Present the top 2 to the user with a clear recommendation and the
   main tradeoff. Do not recite the full matrix — synthesize.
4. Record the chosen pattern in `docs/ARCH.yaml.architecture_pattern.pattern`
   with `pattern_confidence` and a one-sentence `rationale`.
5. On subsequent system-mode invocations (EDIT flow), revisit the
   pattern only if the user raises it or if newly added containers
   make the current pattern obviously inappropriate (e.g. user added
   8 services to a `monolith`).
