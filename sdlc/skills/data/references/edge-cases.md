# Edge cases

Unusual situations and their handling. Read whenever the happy path
doesn't fit.

## Missing PRD.yaml

`docs/PRD.yaml` is the mandatory upstream input. If it's missing:

1. Inform the user clearly: *"This skill needs `docs/PRD.yaml` as input.
   Run `/sdlc:prd` first to produce it, then re-run `/sdlc:data`."*
2. Do not proceed. Do not write any state file. Do not create a stub
   `DATA-MODEL.yaml`.

If `docs/PRD.yaml` exists but has `metadata.status: draft`, warn:
*"PRD is still in draft. The data model derived from it may need rework
when the PRD finalizes. Continue?"* Offer three options: **continue
anyway**, **stop** (finish `/sdlc:prd` first), or **"the PRD itself is
wrong here — record a finding for /sdlc:repair"** (append the observation
to `state.finding_notes` per SKILL.md "Findings capture" and keep going —
never stop the run to record). Let the user choose.

## Missing UX.yaml / UX__*.yaml

UX context is *strongly recommended* but not strictly required. If it's
missing:

1. Resolve applicability first
   (`sdlc/skills/prd/references/optional-stages.md`). When
   `PRD.pipeline_scope.ux.applicable` is `false`, or a present `UX.yaml` says
   `metadata.applicability: not_applicable`, the absence is deliberate —
   **ask nothing** and skip straight to step 3. When there is no scope entry,
   ask the one question from optional-stages.md and record the answer under
   `state.ux_present`.
2. Warn: *"No UX artifacts found. Entity field discovery will rely on
   PRD features only — expect to add more fields manually."*
3. Proceed without UX context.
4. Append a `data_warnings` entry: *"Entity-field discovery ran without
   UX surface signals."* — naming the recorded rationale when there was one.

## Existing DATA-MODEL.yaml without state file

User ran `/sdlc:data` previously, completed it, then comes back. The
output file exists; the state file might be `status: complete` or
absent (user deleted it).

Handle as an **update flow**:

1. Load `docs/DATA-MODEL.yaml` as baseline.
2. Create a fresh state file with `session_id` = a new UUID4.
3. Pre-fill `state.partial_answers` from the on-disk YAML (so the
   interview reflects what's already there).
4. Run all phases. At each theme, the user sees the existing value
   as the position-1 option and can change or keep it.
5. On Phase 7 write, follow the merge rules in `merge-validate.md`.

## Conflicting scan signals

Examples:

- `PRD.data_model.storage_preferences: [postgres]` but the repo has
  `schema.prisma` with `provider = "mysql"` → pre-fill `mysql` (repo
  signal beats PRD), flag the discrepancy to the user, ask them to
  confirm.
- `PRD.data_model.key_entities: [User, Project]` but `models/` has
  `User`, `Project`, `Workspace` → pre-fill all three from the repo,
  tag `Workspace` as `⚠ inferred — not in PRD; appears in repo`.
- `PRD.functional_requirements.features` includes FR-007 about
  notifications but no UX surface references notifications → pre-fill a
  `Notification` entity as `⚠ inferred`, flag uncovered surface trace.

In all cases: **surface the conflict, let the user resolve**. Never
silently merge.

## Mid-interview abort (EXIT) — including mid-entity

When the user types `EXIT` during the per-entity drill-down in Phase 6:

1. If the current entity is mid-flow (between description and final
   approval), persist the partial entity to
   `state.partial_answers.entities.<Name>` with `status: draft` in
   `state.defined_entities`.
2. Set `state.current_entity = <Name>` so resume jumps back to it.
3. Standard EXIT actions: `state.status: aborted`, save, confirm to
   user, stop.

On resume, the agent sees `current_entity` and offers:
*"Resuming mid-entity on `User` (last step: fields). Continue, restart
this entity, or skip it?"*

## Hallucination-guard violation attempts

If the user tries to "ok all" through pre-fill confirmation in Phase 5,
the agent refuses:

> "I can batch-accept the ✓ found items, but each ⚠ inferred candidate
> needs your explicit confirmation. Here's the next one:
>   ⚠ persistence.file_blob_store: s3 (inferred from PRD compliance + GDPR)
> Type 'confirm' to accept, or correct it."

This rule applies in Phase 3 (entity-candidate list) and Phase 5
(pre-fill confirmation). It does NOT apply in Phase 6 — by Phase 6,
candidates are surfaced inside an AskUserQuestion option block, which
already requires explicit selection.

## Mode change mid-flow

If the user changes `monorepo: false` → `true` (or back) partway through:

1. Warn loudly: *"Switching to monorepo mode will move every theme block
   under `products.<slug>.`. This restructures the entire output. Are
   you sure?"*
2. If confirmed, ask for product slugs (matching what PRD declares — or
   fewer; data model can be scoped to a subset of PRD products).
3. Wrap existing partial_answers under the chosen slug.
4. Reset `pre_fill_confirmed: false` so Phase 5 re-runs per-product.

If the user changes `bounded_contexts_enabled: false` → `true` mid-flow:

1. Walk back the user through assigning each already-confirmed entity
   to a context.
2. If the user enables it before any entities are confirmed: ask for
   context names now, defer entity assignment to Phase 6's per-entity
   flow.

## Paradigm change

The storage paradigm (`persistence.paradigm`) is chosen in Phase 4 and is
meant to be **frozen for the project's lifetime** — it determines the entire
document shape and which themes ran. Two situations:

**Mid-flow change** (before completion). If the user wants to switch paradigm
partway (e.g. they picked `relational`, then realize the product is really a
RAG tool → `vector`):

1. Warn loudly: *"Switching paradigm from `relational` to `vector` discards
   the relational-only answers (id_strategy, relationships, indexes,
   constraints) and runs a different theme set. The entity list and their
   traces are preserved. Continue?"*
2. On confirm: keep `entities` (description + traces), drop the skipped
   paradigm's structural blocks from `partial_answers`, set
   `state.storage_paradigm` to the new value, load the new paradigm reference,
   re-enter Phase 6 routing. Reset `pre_fill_confirmed: false`.
3. Append a `data_warnings` entry recording the switch.

**Change after the model exists** (update flow). If `docs/DATA-MODEL.yaml`
already has `status: complete` with one paradigm and the user wants another,
treat it as a **near-restart of the data model**, not a merge: the two shapes
share only `entities` (names + descriptions + traces) and `data_classification`.
Confirm explicitly, carry those shared blocks forward, and re-run the structural
+ paradigm-analogue themes from scratch. Do not try to mechanically translate
relational relationships into graph edges or vector payloads — re-interview.

**Disputed recommendation.** If the user pushes back on the agent's Phase 4
recommendation, that's normal — present the trade-off (cite the relevant
paradigm reference's "When to recommend") and defer to the user's choice. Record
their pick with `persistence.paradigm_confidence: confirmed` and the rationale.

## Mass entity import from schema files

If the consumer project has an existing `schema.prisma`, `models.py`,
or similar with 20+ entities, the per-entity drill-down would be
exhausting. Offer a fast-path:

> "I found 23 entities in schema.prisma. Want me to import them all
> as-is and then walk only the ones with field/relationship questions?
> (Faster, but you'll skip the per-entity description + traces step.)"

On accept: import all entities with confirmed status, then iterate only
through:

1. Entities missing `traces_prd_features` (need user to assign FR-NNN).
2. Entities missing `description`.
3. Entities involved in N:M relationships (need join-table confirmation).

Append a `data_warnings` entry: *"23 entities imported from schema.prisma
without per-entity review. Drilling will resume on user request."*

## Validation failure with `status: complete`

If the user insists on `status: complete` but cross-checks fail:

1. Show the field-level errors verbatim.
2. Offer via AskUserQuestion: *"Fix now (recommended), accept status: draft,
   or cancel?"*
3. If "fix now": jump back to the failing theme's questions, re-run only
   the affected items.
4. If "accept draft": rewrite `metadata.status: draft`, re-run validator
   (should now exit 0 `[DRAFT]`), continue to Phase 8.
5. If "cancel": EXIT flow.

## Write-permission errors

If `docs/DATA-MODEL.yaml` can't be written (read-only filesystem, locked
file, etc.):

1. Surface the exact OS error.
2. Don't retry silently.
3. Don't lose the state file — it's still on disk and resumable.
4. Tell the user how to retry: *"Fix the permission issue and re-run
   `/sdlc:data` — your interview state is preserved."*

## Very large projects

For projects with hundreds of files in `models/` or `migrations/`:

- Sample up to ~50 model files for entity pre-fill.
- Glob `*.sql` to spot-check schema files but don't parse all of them.
- Tell the user: *"Scanned a sample of 50 model files from `models/`.
  If important entities were missed, add them manually during Phase 3."*

## When an upstream changes after DATA-MODEL exists (re-invocation, §7)

The user updates `docs/PRD.yaml` or `docs/UX.yaml` (re-run or hand-edit), then
re-runs `/sdlc:data`. The existing DATA-MODEL is now stale. Phase 2's
**upstream-change detection** drives the reconciliation per the cross-skill §7
contract (`sdlc/skills/ux/references/upstream-reconciliation.md`):

1. Run `python .claude/sdlc/docs_index.py --drift docs/DATA-MODEL.yaml`
   (exit 1 = at least one upstream moved; exit 0 = fresh). When the helper is
   absent, compare each recorded `sha256` (in `metadata.upstream_provenance`)
   to the upstream's current hash by hand. A content hash catches hand-edits
   that the old `session_id`-only check missed.
2. For every changed upstream, classify added / removed / modified ids and run
   the **consolidated delta-review before the entity interview**.
3. The familiar pieces are the branches of that review: the validator's
   feature-coverage check flags new FR-NNNs as uncovered (the "added" branch);
   pre-fill surfaces them as ⚠ inferred entity candidates; stale refs are the
   "removed" branch; and the Phase 7 merge preserves existing entities while
   adding confirmed new ones. Refresh `upstream_provenance` on write.
4. Every per-item prompt in the delta review carries the option **"the
   upstream is wrong — record a finding for /sdlc:repair"** beside
   incorporate / ignore+WRN / defer: append the observation to
   `state.finding_notes` (SKILL.md "Findings capture") and continue the
   review — never stop the run to record.

## Empty entities dict at status:complete

If somehow the user reaches Phase 7 with `entities: {}` and tries to mark
`status: complete`, the required-field check catches this (entities is
required-and-non-empty). The validator returns FAIL. Recovery: the user
must add at least one entity, or accept `status: draft`.

**Exception — `persistence.paradigm: none`** (stateless project): there
`entities: {}` or an absent `entities` block is the valid, expected shape.
The validator passes and its summary says the requirement-coverage check
was skipped because nothing stores data. Declaring entities *under*
paradigm `none` draws a warning (drop them, or pick a real paradigm).
