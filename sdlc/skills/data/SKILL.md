---
name: data
description: >
  Launch in empty context. Create or update DATA-MODEL.yaml for a software
  product across six storage paradigms (relational, document, key_value, graph,
  vector, file_native) plus a stateless `none` (nothing persisted; completes
  with empty entities). Reads docs/PRD.yaml (required) and any docs/UX*.yaml
  (optional but strongly recommended) as upstream
  inputs, scans pre-fill candidates, recommends a storage paradigm from PRD
  signals and asks the structural paradigm/monorepo/bounded-contexts questions,
  then routes a resume-aware thematic interview down the paradigm-appropriate
  path (with a per-entity drill-down for the critical `entities` theme),
  persists session state for resumability, and writes + validates
  docs/DATA-MODEL.yaml for downstream agent consumption (api, arch, test).
  A maintenance form, /sdlc:data --reconcile, reviews only what moved in
  PRD/UX since the file was written, without the interview.
  Trigger only on /sdlc:data or a direct natural-language request for the data
  model — do not auto-trigger from generic chat. ONLY stop when no open
  questions remain or the user types EXIT.
user-invocable: true
disable-model-invocation: true
model: opus
effort: xhigh
allowed-tools: Read Write(docs/DATA-MODEL.yaml) Write(.claude/skills-state/sdlc-data.state.yaml) Bash Bash(ls *) Glob Grep AskUserQuestion
---

# sdlc-data

Guides the user through a structured interview that produces a validated
`docs/DATA-MODEL.yaml` at the project root, so downstream AI agents (api,
arch, test, deploy) have a single unambiguous source of persistent-data
truth.

## What this skill does (at a glance)

1. **Resume check** → load existing state if any (otherwise scan from scratch).
2. **Scan inputs** → read `docs/PRD.yaml` (required) and every `docs/UX*.yaml`
   (optional but strongly recommended — warn before continuing without UX
   context, and confirm only when nothing on record says the absence was
   deliberate); on re-runs check upstream drift
   (`docs_index.py --drift`); run the input-adequacy gate (open findings +
   blocking PRD open_questions); build pre-fill map.
3. **Entity-candidate discovery** → propose a draft entity list early.
4. **Structural questions** → **storage paradigm** (agent recommends from PRD
   signals; user confirms) → monorepo (inherited from PRD)? → bounded contexts?
   → polyglot persistence? The paradigm decision drives everything downstream.
5. **Pre-fill confirmation** → theme by theme, each `⚠ inferred` confirmed
   individually (hallucination guard).
6. **Theme interview (paradigm-routed)** → run only the themes whose
   `applies_to_paradigms` includes the selected paradigm, PLUS the paradigm's
   own analogue themes from `references/paradigms/<paradigm>.md`. Required
   themes always run; optional themes are gated now/skip/todo. Importance tiers
   (`med | high | critical`) control batching. The `entities` theme is the lone
   `critical` (and lone `synthesis: true`) theme — full per-entity drill-down
   (with the paradigm-appropriate field shape) followed by a dynamic
   scope-completeness sweep across ALL upstream ID families (ENT, FR, WKF, JTB,
   UX surfaces).
7. **Write + validate** → merge into `docs/DATA-MODEL.yaml`, run
   `validate_schema.py` (Pydantic + **paradigm-gated** cross-checks: required
   fields, relationship/edge/composition/cross-reference integrity, field
   references, vector_config/identity_conventions/key_value_design substance,
   classification integrity, bounded-context partition, ID-prefix format
   (WRN/FR/SCR/WKF), feature coverage (trace-or-defer via the structured
   top-level `deferrals` list), store-id integrity, lifecycle wiring,
   provenance staleness, volume-vs-scale gate; mode-mismatch is enforced by
   the Pydantic model itself).
8. **Refresh & close** → refresh `docs/INDEX.yaml` and the
   statusboard, mark state `complete`. This skill does not touch
   `CLAUDE.md`.

State is persisted **after every confirmed batch and after every per-entity
drill-down step**, so the user can `EXIT` at any time without losing
progress, even mid-entity.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — the workflow itself. |
| `data-questions.yaml` | The full question inventory, grouped by theme. |
| `DATA-MODEL.schema.yaml` | Human-readable canonical schema for `docs/DATA-MODEL.yaml`. |
| `validate_schema.py` | Pydantic v2 validator + cross-checks, called after every write. |
| `references/paradigms/<paradigm>.md` | **One file per storage paradigm** (relational, file-native, document, key-value, graph, vector). Each holds: "When to recommend" heuristics (read in Phase 4 to form the recommendation), the paradigm's entity-field shape, and its analogue themes/questions (read on entering Phase 6 once the paradigm is locked). Read ONLY the file for the selected paradigm. |
| `references/interview-mechanics.md` | AskUserQuestion batch format, EXIT semantics, importance-tier flows. Read on entering Phase 6. |
| `references/entity-discovery.md` | Heuristics for deriving entity candidates from PRD features + UX surfaces. Read in Phase 3. |
| `references/submodel-and-context-sweep.md` | Exhaustive sub-model decomposition (recurse every entity's field types into first-class `sub_model` entries — the cure for shallow models) + the bounded-context partition reconciliation run before `status: complete`. Read on entering the `entities` theme (Phase 6) and again in Phase 7. |
| `references/pre-fill-sources.md` | Explicit PRD/UX-field → DATA-MODEL-field map. Read in Phase 3 + Phase 5. |
| `references/polyglot-persistence.md` | Guidance for multi-store designs (incl. cross-paradigm secondary stores). Read when the user opts into polyglot in Phase 4. |
| `references/merge-validate.md` | Merge logic for existing DATA-MODEL.yaml, validator recovery, and the rule that this skill never writes CLAUDE.md. Read on entering Phase 7. |
| `references/edge-cases.md` | Unusual situations (entity rename, mode switches, mass import, missing upstreams). Read whenever the happy path doesn't fit. |

Runtime files (NOT inside this skill directory):

| File | Purpose |
|---|---|
| `docs/DATA-MODEL.yaml` (project root) | Output artifact consumed by downstream agents. |
| `.claude/skills-state/sdlc-data.state.yaml` | Session state for resumability. |

## Reserved EXIT command

At any prompt, the user can type `EXIT` (case-insensitive) into the
free-text field of any `AskUserQuestion` call to abort the interview. State
is *always* saved automatically after each confirmed batch — `EXIT` simply
marks the session `status: aborted` and stops.

There is no `SAVE` command — saving is implicit.

## Invocation dispatch

Classify `$ARGUMENTS`:

1. **Empty** → the full flow below (Phases 1–8). On a re-run it still runs the
   upstream-change review in Phase 2 before the interview.
2. **`--reconcile`** → the **reconcile form**: the upstream-change review of
   `docs/DATA-MODEL.yaml` and nothing else — no entity interview, no
   structural questions. Follow
   `sdlc/skills/ux/references/upstream-reconciliation.md` → "The
   `--reconcile` form" (steps 1–8, and this skill's row in its specifics
   table), then Phases 7–8 below. A new entity gets the per-entity drill and
   its own sub-model sweep only; a change that would switch the storage
   paradigm or the bounded-context split is structural — stop and name plain
   `/sdlc:data`. It needs a `complete` `docs/DATA-MODEL.yaml` — without one,
   name plain `/sdlc:data` and abort.
3. **Anything else** → print the two forms above and abort.

## The 8-phase flow

### Phase 1 — Resume check

Before doing anything else, check for `.claude/skills-state/sdlc-data.state.yaml`:

- If it exists with `status: in_progress`, ask:
  > "I found an unfinished `sdlc:data` session from `<last_updated>`. Would
  > you like to **resume**, **restart** (discard previous answers), or
  > **discard** (delete state and exit)?"
- If `status: complete` or `aborted` and `docs/DATA-MODEL.yaml` exists,
  scope the update — see
  `sdlc/skills/ux/references/upstream-reconciliation.md`'s REFINE row (open
  only the named themes, the §7 delta items, and the non-confirmed set;
  confirm the rest in one summary) — then Phase 7's *merge* behavior.
- If `status: complete` or `aborted` and `docs/DATA-MODEL.yaml` is ABSENT,
  only `partial_answers` survives: offer restart-from-partial_answers or
  discard — never resume.
- If no state file, continue to Phase 2.
- If the state file's `skill_version` is older than this file's footer: run
  the canonical recipe
  (`${CLAUDE_SKILL_DIR}/../prd/references/edge-cases.md` → "Resume with
  stale state" — migrate additively, reconcile the theme lists and
  `last_ids`, then offer resume at position 1).

### Phase 2 — Scan inputs

**Slice large docs, don't slurp.** If `docs/INDEX.yaml` exists, the project was
bootstrapped by `/sdlc:setup`. Use it to read large upstream docs by slice:
`PRD.yaml` is routinely 1000+ lines, and on the merge flow your own
`DATA-MODEL.yaml` is the largest artifact in the tree. Look a symbol up in
`INDEX.yaml` (or run `python .claude/sdlc/docs_index.py --show <symbol>`) and
`Read` only its `[start, end]` range; resolve a whole top-level block via its
`sections.<file>.<key>` range. This keeps the scan within budget on big
projects — exactly the case this skill produces. Fall back to whole-file reads
when `INDEX.yaml` is absent. Protocol: `.claude/rules/sdlc-docs-access.md`.
Every `python .claude/sdlc/docs_index.py …` in this file runs the copy
`${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks once per
run: an installed copy older than the plugin's counts as absent, and every
fallback this file gives for a missing `docs_index.py` applies to it.

Required upstream artifacts:

1. **`docs/PRD.yaml`** — fail fast and inform the user if missing. Suggest
   running `/sdlc:prd` first.
2. **`docs/UX.yaml`** — strongly recommended (used for surface coverage and
   entity-field discovery), never required. Resolve applicability with the
   three-step rule in `sdlc/skills/prd/references/optional-stages.md`:
   present-and-applicable → read it; present with
   `metadata.applicability: not_applicable`, or absent with
   `PRD.pipeline_scope.ux.applicable: false` → continue without UX context,
   **ask nothing**, and note it once in `data_warnings` (WRN-NNN); absent with
   no scope entry → ask once (wording in optional-stages.md), record under
   `state.ux_present`, and add the "record it permanently with `/sdlc:prd`"
   line to the close card. Continuing without UX only means weaker
   entity-field discovery and weaker downstream surface coverage — it is never
   a reason to stop.
3. **`docs/UX__*.yaml`** — every sibling file is read for `validation_rules`,
   `components.content_slots`, and `interactions.effects`, which seed
   entity-field candidates.

Also scan:

- Existing `docs/DATA-MODEL.yaml` (for merge flow).
- Schema-like files in `db/`, `migrations/`, `prisma/`, `schema.prisma`,
  `*.sql`, `models/`, `entities/` — extract entity names verbatim where
  obvious (mark as `✓ found`).
- Lockfiles, binaries, and node_modules/venv directories — skip.

Build the pre-fill map (see `references/pre-fill-sources.md` for the full
mapping table). Tag each candidate:

- **`✓ found`** — value is a direct quote/value from a file (e.g.
  `PRD.security_compliance.encryption_at_rest: true` → `data_classification.encrypted_at_rest`
  must end up non-empty; the actual `Entity.field` entries are proposed per entity).
- **`⚠ inferred`** — derived from signals (e.g. `PRD.data_model.key_entities: [User]` →
  candidate entity name `User`, but no fields yet).

**Upstream-change detection (re-runs).** If `docs/DATA-MODEL.yaml` already
exists and carries `metadata.upstream_provenance`, this is a re-run: run
`python .claude/sdlc/docs_index.py --drift docs/DATA-MODEL.yaml` (exit 1 = at
least one upstream moved; exit 0 = fresh, so this is a refine — proceed to
the merge flow without a delta review). When the helper is absent (the
project never ran `/sdlc:setup`), fall back to comparing each recorded
`sha256` to the upstream's current hash (from
`docs/INDEX.yaml.generated_from[<file>]`, else
`sha256(read_text(encoding='utf-8').encode('utf-8'))[:16]` — the same hash
`docs_index.py --hash <file>` prints). For every changed upstream, classify
the delta (added / removed / modified ids) and run the **delta-review pass
before the entity interview** per
`sdlc/skills/ux/references/upstream-reconciliation.md` (CLAUDE.md §7); every
per-item prompt there carries the extra option "the upstream is wrong —
record a finding for /sdlc:repair" (see "Findings capture" below). Track
progress in `state.delta_review`. This supersedes the older
`session_id`-only stale-PRD check — a content hash also catches hand-edits
to an upstream yaml, which `session_id` does not. Fresh runs (no prior
`docs/DATA-MODEL.yaml`) skip this step. Phase 7 refreshes the provenance
snapshot, which is what the next run's `--drift` compares against.

**Input-adequacy gate (ask, never block).** After reading inputs, list what
is already known to be unsettled upstream:

1. Open findings: `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" list
   --open` (or read `.claude/skills-state/sdlc-findings.yaml` directly; when
   neither exists, skip silently).
2. PRD `open_questions` entries with `status: open` whose `blocks:` names an
   id this skill consumes (FR / ENT / WKF / NFR).

When the combined list is non-empty, ask ONE AskUserQuestion — continue
anyway, or stop and run `/sdlc:repair` (findings) / `/sdlc:prd` (open
questions) first — and record the decision in the state file under
`input_adequacy: {checked_at, open_ids, decision}` so a resume does not
re-ask.

**Findings owed to this run are not gate items.** A triaged re-invoke finding
that `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" list --owed-by
docs/DATA-MODEL.yaml` returns is waiting on this very run — its owed re-run is
what you are doing. Leave it out of the question and read it as the reason for
the change: its `fix` and `handoff` notes (canonical:
`sdlc/skills/ux/references/upstream-reconciliation.md` → "The `--reconcile`
form", step 3).

**Thin-upstream capture.** While building the pre-fill map, note every
schema-REQUIRED upstream field found null or empty in a `complete` upstream
(an empty `PRD.data_model` next to data-heavy FRs, a missing
`functional_requirements` block) to `state.finding_notes` as kind
`upstream_incomplete`. Phase 8 raises these automatically (see "Findings
capture"). Never stop the scan to record.

**Before dropping or renaming anything downstream references** (an entity
key, a WRN-NNN id), check its inbound sites first:
`python .claude/sdlc/docs_index.py --refs <Entity-or-id>` (skip when the
helper is absent). Every listed site must be reconciled in the same pass —
`references/merge-validate.md` walks the rename/removal mechanics.

### Phase 3 (first step) — Repo evidence

Before seeding anything, look at what the project already has. On a greenfield
project this finds nothing and costs one command; on a **brownfield** one it is
the best evidence available, and this skill used to ignore it entirely.

```bash
python .claude/sdlc/repo_scan.py --domain data --json
```

Helper absent (the project never ran `/sdlc:setup`) → skip silently and seed
from the upstream artifacts alone. Never block the run on it.

It returns migrations, `schema.prisma`, `CREATE TABLE` statements, ORM/pydantic models, TypeScript interfaces and database services declared in compose files — each hit a `path`, `line`
and one-line `excerpt`. Fold them into the pre-fill map below as **`⚠ inferred`
candidates**, never as answers: cite `<path>:<line>` in the `_rationale` sibling
of whatever field the evidence fed, confirm each one individually (the canonical
flow forbids batch-accepting inferred values), and pass on `truncated` /
`capped_signals` as "this is a sample of a large repo, not an inventory".

These are the strongest entity candidates there are — an existing table or model
names a real entity. It does **not** follow that its current shape is right:
seed the name, then run the normal per-entity drill-down. An existing store in
`docker-compose` is likewise a candidate for `persistence.primary_store`, to
confirm against the PRD's stated preference.

Full rules, including what to do when the repo contradicts an upstream
artifact: `sdlc/skills/setup/references/repo-evidence.md`.

### Phase 3 — Entity-candidate discovery

This is the most novel and most hallucination-prone phase. The skill
proposes a **draft entity list** before any deep interview begins, so the
user can correct course early. Sources of candidates, in priority order:

1. **`PRD.data_model.key_entities`** — direct names (PascalCase'd if not
   already). Tag `✓ found`.
2. **`PRD.functional_requirements.features`** — extract the
   nouns from each FR-NNN feature using lightweight heuristics (see
   `references/entity-discovery.md`). Tag `⚠ inferred`.
3. **`UX__<surface>.yaml.layout` + `validation_rules` + `components.content_slots`** —
   forms imply entities; list items imply entities; filters imply entities.
   Tag `⚠ inferred`.
4. **Schema files on disk** (Prisma, SQL, `models/`) — if present, those
   names are authoritative. Tag `✓ found`.

Present the draft to the user:

> "Based on PRD + UX, I see these entity candidates:
>
>   ✓ User           (from PRD.data_model.key_entities)
>   ✓ Project        (from PRD.data_model.key_entities)
>   ⚠ Task           (inferred from FR-001 'Add a task in under 3 seconds')
>   ⚠ Tag            (inferred from UX__dashboard form field 'tags')
>
> Add, remove, or rename anything before we go deep on each one?"

Persist the confirmed list to `state.defined_entities`. **Critical rule**:
each `⚠ inferred` candidate must be confirmed individually — no batch-accept
shortcuts.

### Phase 4 — Structural questions

These determine *the shape of DATA-MODEL.yaml*, not its content.

Two patterns coexist here and the convention matters:

- **Yaml-less structural questions** (monorepo, bounded_contexts,
  audit-columns preliminary) have no entry in `data-questions.yaml`
  because they are meta — they describe the document's shape rather
  than its content. Phase 4 hard-codes their prompts.
- **Yaml-backed structural questions** (polyglot) have an entry in
  `data-questions.yaml` under their natural theme (e.g. `persistence`)
  AND get asked in Phase 4. Phase 6 sees them already-answered and
  skips the duplicate.

Ask in order:

0. **Storage paradigm** — THE foundational decision; everything downstream
   routes off it. Six paradigms: `relational | document | key_value | graph |
   vector | file_native`.

   **The agent recommends first.** Before asking, derive a recommendation
   from PRD signals and present it at **position 1** with a one-line
   rationale (the position-1 recommendation pattern, not a silent default —
   the user still confirms or overrides). The signals (data volume,
   relationship density, embedding/semantic-search needs, query shape,
   deployment footprint, and any explicit `PRD.data_model.storage_preferences`)
   and their mapping to paradigms live in each paradigm reference's
   **"When to recommend"** section — **read
   `references/paradigms/<candidate>.md`** for the heuristics before forming
   the recommendation. Run this as a `critical`-style mini-decision:
   propose → one-line rationale → user picks. Persist
   `state.storage_paradigm`; write `persistence.paradigm`,
   `persistence.paradigm_confidence`, `persistence.paradigm_rationale`.
   Frozen for the project's lifetime once chosen (a later change is an
   explicit restart of the data model — see `references/edge-cases.md`).

   Once locked, **load `references/paradigms/<paradigm>.md`** — it defines the
   entity-field shape and the analogue themes you'll run in Phase 6.

   **`none` (stateless).** When the PRD shows no saved state anywhere (a pure
   filter/converter CLI, a stateless library), recommend `none`: nothing is
   persisted, entities stay empty, no store questions run, and Phase 6
   short-circuits (see its routing rule 0). The validator then skips the
   requirement-coverage check and says so explicitly. There is no
   `references/paradigms/none.md` — nothing structural to specify.

0b. **Storage topology** — the axis ORTHOGONAL to the paradigm (the family).
   Right after the paradigm is locked, recommend `persistence.topology` —
   *where/how* the store runs: `local_embedded | networked_server |
   cloud_managed | serverless | in_memory | other`. The same family runs
   across topologies, so this is a separate decision, not implied by the
   paradigm. Derive the recommendation from PRD signals: single-user / CLI /
   desktop + bounded volume + no concurrent writers ⇒ `local_embedded`;
   multi-tenant SaaS or a server runtime ⇒ `networked_server` /
   `cloud_managed`; spiky load + low-ops ⇒ `serverless`; cache/ephemeral-only
   ⇒ `in_memory`. Present at position 1 with a one-line rationale; the user
   confirms or overrides. Write `persistence.topology`,
   `persistence.topology_confidence`, `persistence.topology_rationale`. It's
   optional — if the user is genuinely undecided, leave it null and append a
   `WRN-NNN`. The concrete provider (RDS vs Cloud SQL vs self-managed) is
   finalized later at the deploy stage; topology only pins the deployment
   shape the data model assumes.

1. **Monorepo mode** — inherited from `PRD.metadata.monorepo`. Show as
   pre-filled and ask the user to confirm only if PRD signals conflict
   (rare). (In monorepo mode each product may pick its own paradigm —
   ask the paradigm question per product.)
2. **Bounded contexts** — opt-in. Ask:
   > "Do you want to group entities under DDD-style bounded contexts (e.g.
   > `auth: { entities: [...] }`, `billing: { entities: [...] }`)? Default:
   > no — keep `entities` as a flat dict."
   If the user opts in, ask for context names and assign each confirmed
   entity to exactly one context. Persist `state.bounded_contexts_enabled`
   and the assignment map.
3. **Polyglot persistence** — pre-fill from `PRD.data_model.storage_preferences`.
   If multiple stores are listed, default to `polyglot: true` and ask the
   user to confirm. See `references/polyglot-persistence.md` for the
   secondary-store interview script. (Yaml-backed: the `polyglot` entry
   under the `persistence` theme is consumed here, not in Phase 6.)
   **Mint a stable kebab-case `store_id` per secondary store** (unique;
   `primary` is reserved for the primary store) — ARCH data-store containers
   and `entities.<E>.stored_in` reference it, so it is an id, not a label.
4. **Audit-columns preliminary** — `audit_and_lifecycle` is theme 9 in
   `data-questions.yaml`, but its `audit_columns` answer (created_at /
   updated_at / created_by / updated_by / deleted_at) influences every
   per-entity drill-down in theme 3 (`entities`). Ask up-front, in Phase
   4, with a strong default:
   > "Add `created_at` and `updated_at` to every entity by default?
   > (Per-entity opt-out is possible. We'll revisit the full audit
   > picture — soft delete, archive — in theme `audit_and_lifecycle`.)"
   Persist the answer to `state.partial_answers.audit_and_lifecycle.
   audit_columns`. The full theme later refines it.

Persist all structural answers to state before proceeding.

### Phase 5 — Pre-fill confirmation

Present the pre-fill map **theme by theme** (skipping `entities` — that
gets its own treatment in Phase 6). For each theme:

1. **Display** the themed block as a summary (read-only preview) so the
   user can see all pre-fills together:

   ```
   ## Persistence (pre-filled)

     ✓ primary_store          : postgres                 [from PRD.data_model.storage_preferences]
     ⚠ polyglot               : true                     [inferred from secondary store: redis]
       secondary_stores       : (not pre-filled — will ask in Phase 6)
     ⚠ file_blob_store        : s3                       [inferred from regulatory_requirements: gdpr → audit log retention]
   ```

2. **Confirm via AskUserQuestion**, one structured call per `⚠ inferred`
   item — never bulk-accept. The candidate sits at position 1 with the
   `"(Recommended) "` prefix; the user must explicitly select it or pick
   another option. This is the position-1 hallucination guard from
   `references/interview-mechanics.md`.

3. **Batch-accept `✓ found` items** with a single AskUserQuestion
   multi-select call ("which of these found values should I keep
   verbatim?") — `✓ found` items come from direct quotes upstream, so
   bulk acceptance is appropriate here, with an "uncheck to edit"
   escape hatch.

The free-text shortcuts `confirm` / `ok` listed in the *Quick reference*
table below are accepted when the user types them into the "Other"
field of an AskUserQuestion call — they are not chat-mode commands.

**Critical rule** (hallucination guard): `⚠ inferred` items must NOT be
batch-accepted. Each one needs an explicit selection or correction in
its own AskUserQuestion call. Pre-filled inferences are where wrong
requirements sneak in unnoticed.

Write the confirmed values into the state file. Set
`<field>_confidence: confirmed` for explicitly confirmed items,
`<field>_confidence: inferred` for accepted-as-is inferences.

### Phase 6 — Theme interview (paradigm-routed)

Walk the themes in the order defined by `data-questions.yaml`. Use
`AskUserQuestion` as the canonical asking channel.

#### Paradigm routing (do this first)

The selected `state.storage_paradigm` decides which themes run:

0. **Paradigm `none` short-circuit** — nothing is persisted, so no theme
   applies (the `[all]` themes included): confirm once with the user that no
   feature stores state anywhere, write the minimal artifact (metadata +
   `persistence` block with `paradigm: "none"` and rationale), and jump to
   Phase 7. Do not run the entities drill or the sweep — there is nothing to
   sweep, and the validator says what it skipped.

1. **Universal + applicable `data-questions.yaml` themes** — run a theme only
   if its `applies_to_paradigms` list contains the selected paradigm (or is
   `[all]`). Themes whose list omits the paradigm are **skipped silently** —
   do NOT offer them as a now/skip/todo gate. (E.g. for `vector` you skip
   `relationships`, `indexes_and_queries`, `integrity_and_constraints`,
   `id_strategy`, `migrations_and_evolution`, `transactions_and_consistency`.)

2. **Paradigm analogue themes** — read `references/paradigms/<paradigm>.md` and
   run the analogue themes it defines. These replace the skipped relational
   themes with the paradigm's own structural questions:

   | paradigm     | analogue themes (from the reference file)                          |
   |--------------|--------------------------------------------------------------------|
   | relational   | (none — uses the data-questions.yaml relational themes directly)   |
   | document     | `composition`, `cross_references` (id links between documents)     |
   | key_value    | `key_value_design` (partition/sort keys, GSIs)                     |
   | graph        | `edges`, `graph_config` (traversal patterns)                       |
   | vector       | `vector_config` (embedding model, dims, distance, ANN index)       |
   | file_native  | `identity_conventions`, `composition`, `cross_references`, `serialization_conventions` |

   Wherever `cross_references` runs (document / file_native), close the theme
   with the **gate-clause sweep** (`references/paradigms/file-native.md` →
   "Gate-clause sweep"): every `Entity.field` that an upstream-named
   referential/coverage gate queries must have a cross_references row or an
   explicit `WRN-NNN` carve-out, and non-id-family relations (composite
   tuples, paths) get their resolution rule declared. An edge table that
   self-describes as exclusive but lacks rows for fields the gates read makes
   those gates mechanism-only.

3. **Entity field shape** — when drilling each entity in the `entities` theme,
   use the field-attribute shape the paradigm reference specifies (relational:
   `type/nullable/unique/primary_key/references/on_delete`; file_native:
   `pydantic_type` + `description`, no primary_key; graph: node properties;
   vector: `payload_fields` + one `embedding: true` field; key_value: fields +
   key design captured in `key_value_design`). Two paradigm-independent
   attributes to capture during the same drill-down:

   - **`validation`** (per field, optional) — structured app-level rules
     (`min`/`max`/`min_length`/`max_length`/`regex`/`format`/`enum`) whenever
     the user states a constraint. This is the machine home codegen renders
     Pydantic/zod validators from; a constraint expressed only as a SQL
     `check` string or prose is unreachable for non-relational paradigms.
   - **`lifecycle`** (per entity, optional) — when an entity has a
     status-like field, ask for the allowed transitions and record the state
     machine (`field`/`initial`/`transitions[]`/`terminal`). Enums hold the
     *values*; `lifecycle` holds the *legal moves* — what `test` needs for
     state-transition cases and `task`/`code` for guard logic. The validator
     warn-checks the wiring: `field` exists in `fields`, terminal states have
     no exit, and the state set appears in the field's declared value set.
   - **`invariants`** (per entity, optional) — plain-language always-true
     rules ("end_date >= start_date"). `task` copies invariants and
     lifecycle VERBATIM into each entity_slice embed (drift-checked); `code`
     renders model validators / DB CHECKs; `test` seeds invariant-violation
     cases. A rule that lives only in prose reaches none of them.
   - **`stored_in`** (per entity, optional; polyglot projects only) —
     'primary' or declared `secondary_stores[].store_id` values naming which
     store(s) hold the entity. Absent = primary only. The validator warns on
     ids no store declares.
   - **`one_of` + `discriminator`** (per entity, optional; any paradigm) —
     when an instance is exactly one of several concrete variants (a payload
     keyed on `kind`, an event that is one of N shapes), the entity is a
     **union parent**: `one_of: [VariantA, VariantB]` names the variants,
     `discriminator: <field>` the field every variant carries whose value
     selects it, and the parent may omit `fields`/`primary_key` (the variants
     carry them). Each variant is its own first-class entity. Not `composes`
     (mixins) and not `composition` (containment): a union is "is one of",
     not "has". The validator checks that every variant exists and carries
     the discriminator (blocking from `data_model_version` 3.0); `code`
     renders a tagged union, `test` seeds one case per variant. Before this
     slot existed a union could only be flattened, or smuggled in as a
     private extension that failed the required-`fields` check forever
     (ledger IMP-080).

   **Decompose, don't skim.** For every entity, recurse into its field types:
   any field whose type is a custom model (directly, in a `list[...]`/`dict[...]`,
   or `Optional[...]`) names a **sub-model that must exist as its own
   `entities.<Name>` entry** — define it and recurse into *its* fields, until
   every leaf is a scalar, an enum, or a reference to another first-class entity.
   This is the cure for shallow models (a `features: list[FeatureSpec]` whose
   `FeatureSpec` is never defined). After the entity scope-completeness sweep,
   run the dedicated **sub-model pass** described in
   `references/submodel-and-context-sweep.md` (Part A) so no referenced model is
   left undefined.

#### Required vs optional themes

- **Required themes** (`required: true`): run the theme's questions until
  every required question is answered.
- **Optional themes** (`required: false`): before asking any questions,
  offer a gate:
  > "Theme: **\<name\>** — N questions. \<one-line description\>.
  > Address now, skip, or mark as todo?"
  - **now** → run the theme's questions.
  - **skip** → record under `skipped_themes` in state, move on.
  - **todo** → mint the next writer-managed warning id and append
    `"WRN-NNN: theme <name> deferred (todo) — revisit before relying on this
    section"` to `data_warnings` (bump `state.last_ids.WRN`), move on. A bare
    `TODO:` entry would fail the validator's `WRN-NNN` format check.

#### Conditional promotion

If `PRD.data_model.data_volume_estimate ∈ {terabytes, petabytes}` AND the
selected paradigm includes `scale_and_retention` in its
`applies_to_paradigms` (relational/document/key_value), the
`scale_and_retention` theme is promoted to required regardless of its
default. The agent re-evaluates promotion rules at every theme boundary.
(For graph/vector/file_native the volume gate does not apply — the validator
skips it for those paradigms.)

#### Tiered question flow (within a theme)

Each question in `data-questions.yaml` carries an `importance` field
(`med | high | critical`) that controls how the agent runs it:

- **`med`** (default): batch with up to 3 sibling `med` questions from the
  same theme into one `AskUserQuestion` call. `⚠ inferred` candidate at
  position 1.
- **`high`**: runs as its **own mini-section** — never batched. For
  scalars: agent drafts a full answer, shows it, user approves or iterates
  (max 3 rounds). For list[string] fields: per-item with one clarifying
  challenge round each.
- **`critical`** (only `entities`): full per-entity state machine — propose
  → challenge → fields → relationships → indexes → traces → final approval
  → next entity. Each entity is examined before being added. The
  per-entity questions use a `entity.<field>` prefix on `schema_path` that
  the agent rewrites per entity (e.g. `entity.fields` →
  `entities.User.fields` when drilling User). Because the `entities`
  theme is also `synthesis: true`, after the per-entity loop closes the
  agent runs a **dynamic scope-completeness sweep** that reflects on:
  (a) the draft entity list itself; (b) every upstream ID family that
  could imply an entity (PRD `ENT-NNN` key_entities, `FR-NNN` features,
  `WKF-NNN` workflows, `JTB-NNN` jobs, UX `SCR-NNN` surfaces with
  data I/O); (c) project-type heuristics. Surfaces concrete candidate
  entities — not categories — via one multi-select `AskUserQuestion`;
  cap of 2 sweep passes; anti-padding rule. See
  `references/entity-discovery.md` "Scope-completeness sweep" for the
  full procedure.

Order within a theme: run all `med` questions first (in 2–4-question
batches), then each `high`/`critical` question as its own mini-section in
the order they appear in `data-questions.yaml`.

**Read `references/interview-mechanics.md` before running any
`high`/`critical` question** for the exact AskUserQuestion prompts,
iteration caps, EXIT-mid-flow rules, and the per-entity state machine.

The two non-negotiable rules in this phase:

1. `⚠ inferred` candidates surface as the **position-1 recommended option**
   in their `AskUserQuestion` call. They cannot be silently accepted — the
   user must explicitly pick or correct. This is the hallucination guard.
2. State is written after **every confirmed batch, mini-section, or
   per-entity step** — not at theme boundaries.

### Phase 7 — Write & validate

**Before writing, when bounded contexts are enabled, run the bounded-context
reconciliation** (`references/submodel-and-context-sweep.md`, Part B): every
entity — including every `sub_model` promoted in Phase 6 — must appear in
exactly one `bounded_contexts.<family>.entities` list, and every name listed
there must be a real entity. Compute orphans / phantoms / duplicates, resolve
each with the user (orphans default to their `category`-implied context, usually
a one-click batch), and repeat until the partition is clean. This is the same
check `validate_schema.py` runs — doing it here means the validator never reports
"entity X is not assigned to any context" at write time (the failure mode that
piled up dozens of orphans in manual runs).

Write or merge `docs/DATA-MODEL.yaml` at the project root, then run:

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/DATA-MODEL.yaml
```

For full merge logic (conflict handling, entity renames, field removal,
deletion confirmation), type discipline when writing nested entity blocks,
and the exit-code recovery flow → see `references/merge-validate.md`.

When writing the file: inline YAML comments on top-level keys, updated
`metadata.last_updated` and `metadata.session_id`. Then stamp
`metadata.upstream_provenance` with the helper — one `--upstream` per file
read this run, `UX__<surface>.yaml` shards included:

```bash
python .claude/sdlc/docs_index.py --stamp docs/DATA-MODEL.yaml \
    --upstream docs/PRD.yaml --upstream docs/UX.yaml --upstream docs/UX__<surface>.yaml …
```

It writes `{file, session_id, last_updated, sha256, items}` per upstream; the
`items` map is what lets the next `--drift` name the delta item by item. A
hand-written `{file, sha256}` entry is a sha-only stamp: `--drift` can only
recover its old side from git or fall back to the residue, and `--stale` warns
about it. Provenance is file-granular, so a shard read but not recorded is
invisible to every drift check (ledger IMP-102). Helper absent → the plugin's
copy, `python "${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs
--stamp …` (it writes only the artifact it is given). Replace-on-write. See
CLAUDE.md §7.

Set `metadata.status`:

- `"complete"` — only when all required fields are filled and the validator
  passes with `[OK]`.
- `"draft"` — on early EXIT or when any required field is still null, or
  when a cross-check (feature coverage, relationship integrity,
  classification integrity) reports problems.

If the validator returns `[FAIL]` because required fields are missing
despite `status: complete`, ask the user via `AskUserQuestion` to either
fill them in now or accept `status: draft`.

### Phase 8 — Refresh & close

**This skill does not write `CLAUDE.md`.** That file is owned by `/sdlc:setup`,
which writes one static `## SDLC Documents` block. A caveat belongs in this
artifact's own `WRN-NNN` list, a spec defect in the findings queue, a skill
defect in the lessons queue — never as a note, a bullet or a "resolved" section
in `CLAUDE.md`. See `references/merge-validate.md`.

**Refresh the navigation index.** `DATA-MODEL.yaml` is the largest artifact in
the tree, so a current `docs/INDEX.yaml` matters most here. If
`.claude/sdlc/docs_index.py` exists (the project ran `/sdlc:setup`), run
`python .claude/sdlc/docs_index.py` after writing the file so downstream
`api`/`arch` can slice it immediately. The setup hook also does this, but a hook
added mid-session only activates next session. Harmless no-op if not installed.
Optionally confirm the write introduced no dangling references before closing:
`python .claude/sdlc/docs_index.py --check` (same guard).

**Refresh the statusboard.** Run `python .claude/sdlc/statusboard.py` in the
same breath. It regenerates `.claude/rules/sdlc-statusboard.md` (loaded into
every session) and `.claude/sdlc/STATUS.md` from the artifacts, so this run's
new warnings, deferrals and open questions are visible to the next agent
without anyone writing them down by hand. Harmless no-op if it is not installed.

**Drain `state.finding_notes`** (CLAUDE.md 13; mechanics in "Findings
capture" below): raise each noted upstream defect through
`python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add --raised-by sdlc-data
...` — cap 3 per run unless one is blocking; skip silently when the script is
absent. Additionally auto-raise one `upstream_incomplete` finding per
schema-REQUIRED upstream field the Phase 2/3 scan found null/empty in a
`complete` upstream, its summary prefixed `<upstream file> <field path>: `
(the dedupe key, so a thin upstream is recorded once across runs).

Then: set `status: complete` in the state
file (do not delete it — it's an audit trail), tell the user where the
artifacts live, and point at what comes next:

**Self-review & record the run** (CLAUDE.md 15; doctrine:
`sdlc/skills/lesson/references/lessons-capture.md`). First drain `state.lesson_notes` (mid-run observations — that file →
"Mid-run: note now, record at close"), then answer the self-review questions
from that file for this run. Each yes that matches a raising condition
becomes one `lessons.py add` (at most 2 per run unless one is a `blocker`;
drained notes count toward the cap). Then record the run:

```bash
python .claude/sdlc/lessons.py record-run --skill data --plugin-root "${CLAUDE_SKILL_DIR}/../.."
```

Best-effort: a non-zero exit becomes one `Attention:` clause in the card;
helper absent (project never ran `/sdlc:setup`) — skip silently.

**Close with the card** (CLAUDE.md 14; canonical shape:
`sdlc/skills/prd/references/reporting-to-the-user.md`). The user reading this
knows only "there is a pipeline and I run it in order", so answer their three
questions and nothing else: did it work, can I run the next skill, what do I
type next.

```
-- /sdlc:data - what you have now ---------------------
Wrote:     docs/DATA-MODEL.yaml ({the one count that matters})
Status:    complete - /sdlc:api can run it
Attention: {what needs a decision, in the user's words}
Next:      {the computed next invocation}   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript.
```

**Compute the `Next:` row; never copy the example** — the literal above is a
shape, and printing it unchanged means you guessed, not reported. Procedure
and successor map: `sdlc/skills/prd/references/reporting-to-the-user.md`
(CLAUDE.md 14). For `/sdlc:data` it resolves to:

- **`docs/` artifact is `draft`, the user typed `EXIT`, or the validator is not
  green** → `Next:` is `/sdlc:data` again, and `Status:` says what finishing
  means. Never hand off an unfinished artifact.
- **This run recorded findings, or open findings name an artifact this skill
  consumed** → `/sdlc:repair` (name the ids) before any successor.
- **Complete and green** → `/sdlc:api` when the project has a service contract to specify, otherwise
  `/sdlc:arch` directly — pick ONE and print only that one. `data` is not sharded.


Rules: omit any row with nothing to say (never write "no warnings"). Add a
`Lessons:` row only when this run recorded at least one — e.g. `Lessons: 1
recorded (LSN-004) - about this skill, for its maintainer; nothing for you to
do` — and never print "no lessons". Add a `Findings:` row only when this run
recorded findings or open ones name an input — the ids plus one consequence
clause, e.g. `Findings: 2 recorded (FND-011, FND-012) -> /sdlc:repair` — and
never print "no findings".
**`Attention:` is translated, never pasted validator output** - turn each
finding into what happened, why it matters, and what to do. If the validator
printed nothing worth acting on, drop the row.

> Data model complete. Next: `/sdlc:api` (optional — a REST/GraphQL contract
> projecting these entities), or skip straight to `/sdlc:arch` if the system
> has no formal API surface.

## Findings capture (CLAUDE.md 13)

A defect in an UPSTREAM artifact (PRD/UX) discovered here is never fixed here
and never becomes a `data_warnings` note about the other file — it goes to
the findings queue for `/sdlc:repair`. The raising set for this skill is
closed:

1. **A user pick** at these prompts, each of which carries the option "the
   upstream is wrong — record a finding for /sdlc:repair": the draft-PRD
   continue prompt and the stale-ref/conflicting-signals prompts
   (`references/edge-cases.md`), and every per-item step of the §7 delta
   review.
2. **Two upstream artifacts contradict each other** (e.g. the PRD names an
   entity the UX flow renders incompatibly) — offer the same option at the
   conflicting-signals prompt.
3. **`upstream_incomplete`** — a schema-REQUIRED field is null or empty in a
   `complete` upstream, noted automatically during Phase 2/3 pre-fill and
   raised automatically at close.

Mid-run the agent NEVER stops to record: append
`{noted_at, kind_guess, file, summary, evidence}` to `state.finding_notes`
in the next state write (same cadence as answers) and continue the
interrupted step. Phase 8 drains the list — at most 3 findings per run
unless one is blocking — through:

```bash
python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add \
  --raised-by sdlc-data --detected-by sdlc-data \
  --kind <kind> --suspected-stage <stage> \
  --file "docs/<upstream>.yaml" --summary "<one line>"
```

Skip silently when the script is absent (the project never ran
`/sdlc:setup` and has no plugin install). For auto-raised
`upstream_incomplete` entries the summary MUST start
`<upstream file> <field path>: ` — findings.py dedupes on
(detected_by, summary), so a thin upstream is recorded once, not once per
run. The close card gains a `Findings:` row whenever any were recorded, and
`Next:` routes to `/sdlc:repair` before any successor while findings are
open.

## Session state file

Path: `.claude/skills-state/sdlc-data.state.yaml`

Schema:

```yaml
session_id: <uuid4 string>
skill_version: <the skill_version at the end of this file>
started_at: <iso8601>
last_updated: <iso8601>
status: in_progress  # in_progress | complete | aborted
storage_paradigm: null  # relational | document | key_value | graph | vector |
                        # file_native. Chosen in Phase 4; frozen for the
                        # project. In monorepo mode use storage_paradigm_by_product.
storage_paradigm_by_product: {}  # slug → paradigm (monorepo mode only)
monorepo: false      # mirrors DATA-MODEL metadata; inherited from PRD
products: []         # populated only when monorepo: true; list of product slugs
bounded_contexts_enabled: false
bounded_contexts_map: {}     # entity_name → context_name (when enabled)
polyglot_persistence: false
pre_fill_confirmed: false
completed_themes: []
skipped_themes: []
todo_themes: []
pending_themes: []
current_theme: null
current_entity: null         # which entity is mid-deepdive in theme 3
defined_entities: []         # list of {name, status: proposed|draft|confirmed|dropped, source}
dropped_entity_candidates: []  # so we don't re-propose ones the user rejected

# Per-family ID counters (single-product mode). Each entry is the last-assigned
# integer for that family — increment, format as <PREFIX>-{:03d}, then persist.
# This skill emits only the WRN family; the data model does not introduce a
# new entity-level ID family (entity names are dict keys, and PRD's ENT-NNN
# is consumed verbatim, not regenerated).
last_ids: {}        # e.g. {WRN: 3}

# Per-product ID counters (monorepo mode only). Same shape as last_ids, keyed
# by product slug. Each product carries an independent WRN id space.
last_ids_by_product: {}  # e.g. {billing: {WRN: 1}, notifications: {WRN: 2}}

# Run telemetry (CLAUDE.md 15) — updated in the same write as everything
# else; consumed only by `lessons.py record-run` at close.
metrics: {}                  # questions_asked, free_text_answers,
                             # free_text_by_question{<question-id>: n},
                             # validator_runs, validator_failures, resumes

# Mid-run scratch lists (CLAUDE.md 15 + 13) — appended in the same write as
# everything else; the run is never interrupted to record. Both are drained
# by the Phase 8 close on EVERY exit path, EXIT included.
lesson_notes: []             # {noted_at, about, kind_guess, note}
finding_notes: []            # {noted_at, kind_guess, file, summary, evidence}

# §7 delta-review progress (re-runs with changed upstreams only).
delta_review: {}             # {upstreams: [], decisions: [], unresolved: []}

# Phase 2 input-adequacy decision, so a resume does not re-ask.
input_adequacy: {}           # {checked_at, open_ids, decision}

# Sweep candidates the user dropped, keyed by schema_path (cross-skill state
# contract; dropped_entity_candidates above stays as the legacy per-entity
# alias). The §7 delta re-surfaces one only when its seeded_from id changed.
dropped_candidates: {}       # {<schema_path>: [{candidate, seeded_from, reason, at}]}

partial_answers: {}          # mirrors DATA-MODEL.yaml structure incrementally
```

Rules:

- Generate `session_id` as a UUID4 on first creation.
- Update `last_updated` on every write.
- Write the file **after every confirmed batch, mini-section, and per-entity
  step**, including pre-fill confirmations and Phase 3 entity-list
  confirmation.
- The `metrics` counters (schema above) update in the same write: a batch
  bumps `questions_asked`; an Other/free-text answer bumps `free_text_answers`
  and `free_text_by_question[<question-id>]`; a resume bumps `resumes`
  (Phase 1); Phase 7 counts `validator_runs`/`validator_failures`.
- On user `EXIT`: set `status: aborted`, write current `partial_answers`,
  drain `lesson_notes` AND `finding_notes` (the close self-review and the
  findings drain run on every exit path), run
  `python .claude/sdlc/lessons.py record-run --skill data --outcome aborted`
  (skip silently if the helper is absent), confirm to user that state was
  saved, then stop.
- On Phase 8 completion: set `status: complete` but keep the file.
- The validator ignores this file — it validates only `docs/DATA-MODEL.yaml`.

**Source of truth on resume:**

- `docs/DATA-MODEL.yaml` (if present) is the on-disk source of truth for
  *answers*.
- The state file is the source of truth for *interview progress*.
- On resume: load `docs/DATA-MODEL.yaml` first as the baseline, then layer
  the state's `partial_answers` on top.
- If they conflict on the same key, ask the user which to keep — never
  silently overwrite.

## Edge cases

For unusual situations (missing PRD, missing UX, existing DATA-MODEL.yaml
without state file, conflicting scan signals, entity rename mid-flow,
relationship integrity failures, mass entity import from schema files,
mid-interview abort, very large projects, write-permission errors,
hallucination-guard violation attempts) → see `references/edge-cases.md`.

## Style of conversation

The interview is potentially long, especially the per-entity drill-down.
Keep it humane:

- Use the user's terminology as soon as they introduce it.
- Keep AskUserQuestion batches to 2–4 questions; never more than 4.
- Acknowledge progress at each theme boundary and at each entity boundary
  ("That's User done — 5 fields, 2 relationships, 3 indexes. Next: Task,
  which I've drafted as 4 fields. Review and add?").
- Always make multiple-choice the path of least resistance.
- After all themes are done, congratulate the user briefly and move to
  write/validate. Do not repeat the entire summary back at them.
  (This is about the INTERVIEW. The Phase-8 close report is separate and
  is NOT optional — see the card in Phase 8.)

## Quick reference: commands the user can type

| User input | Effect |
|---|---|
| `EXIT` | Abort: type into the free-text field of any AskUserQuestion call. |
| `confirm` | Accept a single inferred pre-fill (Phase 5). |
| `ok` | Batch-accept all `✓ found` pre-fills in the current theme, OR accept the Phase 3 entity list as-is. |
| `now` | Run the proposed optional theme (gate question). |
| `skip` | Skip the proposed optional theme (gate question). |
| `todo` | Defer the proposed optional theme; logs it to `data_warnings`. |

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.18"
