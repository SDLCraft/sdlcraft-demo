---
name: prd
description: >
  Launch in empty context. Create or update PRD.yaml for software product.
  Scans project files, captures user's idea in free text, asks structural
  monorepo question, interviews the user in thematic batches with multiple-choice
  answers (via AskUserQuestion), persists session state for resumability,
  then writes and validates PRD.yaml for downstream agent consumption.
  ONLY stop when no open questions remain or the user types EXIT.
user-invocable: true
disable-model-invocation: true
model: opus
effort: xhigh
allowed-tools: Read Write(docs/PRD.yaml) Write(.claude/skills-state/sdlc-prd.state.yaml) Bash Bash(ls *) Glob Grep AskUserQuestion
---

# sdlc-prd

Guides the user through a structured interview that produces a validated
`docs/PRD.yaml` at the project root, so downstream AI agents have a single
unambiguous source of product truth.

## What this skill does (at a glance)

1. **Resume check** → load existing state if any (otherwise scan from scratch).
2. **Scan + idea capture** → build pre-fill map and a free-text idea summary.
3. **Structural questions** → monorepo? products? (sets PRD shape.)
4. **Pre-fill confirmation** → theme by theme, each `⚠ inferred` confirmed individually.
5. **Theme interview** → required themes always run; optional themes are gated now/skip/todo. Per-question flow varies by `importance` tier (see `references/importance-flows.md`).
6. **Write + validate** → merge into `docs/PRD.yaml`, run `validate_schema.py`.
7. **Refresh & close** → refresh `docs/INDEX.yaml` and the
   statusboard, mark state `complete`. This skill does not touch
   `CLAUDE.md`.

State is persisted **after every confirmed batch**, so the user can `EXIT`
at any time without losing progress.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — the workflow itself. |
| `prd-questions.yaml` | The full question inventory, grouped by theme. |
| `PRD.schema.yaml` | Human-readable canonical schema for `docs/PRD.yaml`. |
| `validate_schema.py` | Pydantic v2 validator, called after every write. |
| `migrate_ids.py` | One-shot migration helper: renames legacy `F-NNN` to `FR-NNN` and applies the v1.1 ID-prefix convention (PER, WKF, JTB, etc.) to any unprefixed list items. Round-trips through `ruamel.yaml`, so comments, key order, and original quoting are preserved; new/renamed items are written as double-quoted scalars. Idempotent; not called by the skill itself — run manually when upgrading an existing PRD.yaml. |
| `references/interview-mechanics.md` | AskUserQuestion batch format, inferred-option pattern, conditional promotions. Read on entering Phase 6. |
| `references/importance-flows.md` | The `med` / `high` / `critical` / `nested_freeform` interview flows, including the per-item state machine for critical lists, the conventions synthesis pass, and the `product_identity` synthesis batch. Read alongside `interview-mechanics.md` on entering Phase 6 — required whenever a question with `importance: high`, `critical`, or `nested_freeform` is up next. |
| `references/conventions-catalog.md` | ~12 project-agnostic convention-bucket archetypes (artifact_ids, schema_versioning, nfr_propagation, code_style, testing_policy, severity rubrics, supply-chain policy, …) the agent reasons from during the `conventions` synthesis pass. Read on entering the `conventions` mini-section. |
| `references/merge-validate.md` | Merge logic for existing PRD.yaml, validator exit-code recovery, and the rule that this skill never writes CLAUDE.md. Read on entering Phase 7. |
| `references/edge-cases.md` | Unusual situations and their handling. Read whenever the happy path doesn't fit. |

Runtime files (NOT inside this skill directory):

| File | Purpose |
|---|---|
| `docs/PRD.yaml` (project root) | Output artifact consumed by downstream agents. |
| `.claude/skills-state/sdlc-prd.state.yaml` | Session state for resumability. |
| `CLAUDE.md` (project root) | Pointer block injected on completion. |

## Reserved EXIT command

At any prompt, the user can type `EXIT` (case-insensitive) into the free-text
field of any `AskUserQuestion` call to abort the interview. State is *always*
saved automatically after each confirmed batch, so progress is never lost —
`EXIT` simply marks the session `status: aborted` and stops.

There is no `SAVE` command — saving is implicit.

## The 8-phase flow

### Phase 1 — Resume check

Before doing anything else, check for `.claude/skills-state/sdlc-prd.state.yaml`:

- If it exists with `status: in_progress`, first compare its `skill_version`
  to this file's footer: older → **migrate it additively before asking**
  (`references/edge-cases.md` → "Resume with stale state": bump the version,
  add the missing baseline keys with empty defaults, record a `migrations`
  entry, touch no answer or theme list) — a version bump never costs the user
  a completed interview. Then ask:
  > "I found an unfinished session from `<last_updated>`. Would you like to
  > **resume**, **restart** (discard previous answers), or **discard** (delete
  > state and exit)?"
- If `status: complete` or `status: aborted` and `docs/PRD.yaml` exists, treat
  this as an update flow — see Phase 7's *merge* behavior.
- If no state file, continue to Phase 2.

### Phase 2 — Scan

On the **update/merge** flow (an existing `docs/PRD.yaml`), if `docs/INDEX.yaml`
is present (the project ran `/sdlc:setup`) and the PRD is large, read it by
slice rather than whole: look an `FR-###` or a top-level section up in
`INDEX.yaml` (or `python .claude/sdlc/docs_index.py --show <symbol>`) and `Read`
only its range. A fresh PRD is small, so this matters mainly on re-runs of a
mature spec. Protocol: `.claude/rules/sdlc-docs-access.md`.

Start with the shared sweep, which handles the traversal, the skip list and
the cost caps in one place:

```bash
python .claude/sdlc/repo_scan.py --domain prd --json
```

It returns `readme`, `manifests`, `idea_docs` and the monorepo `workspaces`
signal, each hit a `path`, `line` and one-line `excerpt`. Helper absent (this
project has not run `/sdlc:setup` — common, since `prd` is often the first
thing a user reaches for) → fall back to reading these yourself, in priority
order:

1. Project root: `README*`, `package.json`, `pyproject.toml`, `Cargo.toml`,
   `go.mod`, `Makefile`, `*.config.*`, any existing `docs/PRD.yaml`, any
   `BRD.yaml`, any `*idea*.md`, `*vision*.md`, `*pitch*.md`.
2. `docs/`, `doc/`, `project/` — read all readable text files.
3. Any additional config files at the root (`.env.example`, `tsconfig.json`,
   `next.config.*`, etc.).

Skip either way:

- Binary files, lockfiles (`package-lock.json`, `poetry.lock`,
  `Cargo.lock`), node_modules, venv directories, `.git/`.
- For *very large projects*, sample the priority list only and explain to the
  user that you skipped the rest. The helper reports this itself as
  `truncated: true`.

The sweep names the files worth reading; **read the interesting ones in full**
here. Unlike every later skill, `prd` needs the prose — a README's framing is
the raw material for Phase 3, not just a signal that a README exists.

Build a pre-fill map. For each candidate field, classify the source as:

- **`✓ found`** — the value is a direct quote/value from a file. Record file
  path. Example: `package.json: "name": "acme-app"` → product_identity.name.
- **`⚠ inferred`** — derived from signals, not explicit. Example:
  `package.json` exists with `"react"` in deps → runtime_platform = [web],
  primary_language = javascript. Record the reasoning in one sentence.

Anything you didn't pre-fill is unmarked and will be asked in the interview.

Also extract any **idea-like text** for Phase 3: README description, the
`description` field of `package.json`/`pyproject.toml`, the contents of
any `BRD.yaml`/`*idea*.md`/`*vision*.md`/`*pitch*.md`. Preserve verbatim
snippets and their source paths so Phase 3 can quote them back to the user.

### Phase 3 — Idea capture & summary

This phase exists because most invocations have very little to scan — often
just a typed slash-command and an idea in the user's head. Three branches:

**Branch A — `$ARGUMENTS` provided OR scan found idea-like content (or both):**

Concatenate everything available (args + extracted snippets) and produce a
2–10 sentence exhaustive summary of what's been said about the product.
Then prompt:

> "Here's what I understood about your idea so far:
>
> > _[2–10 sentence summary covering everything relevant the inputs imply
> > about the product]_
>
> Source(s): `$ARGUMENTS`, `README.md` line 3, `package.json: description`.
>
> Want to add or correct anything in free text before we start the structured
> interview? (Type your additions, or `ok` to proceed.)"

This block expects a TYPED reply, so the turn must END with it — never
combine it with a same-turn `AskUserQuestion` (channel rule:
`references/importance-flows.md`).

**Branch B — Nothing on disk, no `$ARGUMENTS`:**

> "I don't know anything about your idea yet. Please describe it briefly in
> free text — even a paragraph is enough. After that we'll start a structured
> interview to fill in the details."

After the user replies (or accepts with `ok`), run a small **idea-extraction
pass**: probabilistically pre-fill candidate fields (`product_identity.one_liner`,
`problem_opportunity.problem_statement`, `users_personas.primary_users`,
possibly `functional_requirements.features`) and mark every one
of them as `⚠ inferred`. These join the Phase 2 pre-fill map and are
governed by the Phase 5 hallucination guard.

**Persist** the user's free-text idea verbatim into:
- `state.idea_text` — for the agent to re-read during later phases.
- `product_identity.idea_text` — written to `docs/PRD.yaml` so downstream agents
  see the original brief.

This prompt IS the inventory question `idea_text` (`prd-questions.yaml`,
theme `product_identity`): count the reply under `free_text_by_question`
with that id, never under an improvised one (`idea_check`, `idea_summary`).
The inventory offers it no suggested answers, so the maintainer's digest
knows free text is its designed answer; an improvised id lands in the
"asked by an agent, not from the inventory" bucket where nobody can act on
it (ledger IMP-067).

### Phase 4 — Structural questions

These determine *the shape of the PRD*, not its content. They must be asked
before any theme batch, because every later batch needs to know whether to
write to `product_identity.name` or `products.<slug>.product_identity.name`.

Ask in order:

1. **Monorepo / multi-product mode?** (single | multi)
   - Pre-fill default: scan signals (`workspaces` in `package.json`,
     top-level `packages/` or `apps/` with >1 package manifest, multiple
     `pyproject.toml`).
   - If signals present → pre-fill `multi`, mark `⚠ inferred`, ask the user
     to confirm with explanation:
     > "I see monorepo signals: `<signals>`. Should the PRD use multi-product
     > mode (one PRD.yaml at root, each product namespaced under
     > `products: <slug>:`)?"
   - If no signals → ask cold; pre-fill `single` as the typed default but
     require explicit confirmation:
     > "Are you working on a single product, or several distinct products
     > in one repo (monorepo)? (Default: single.)"
2. **(only if multi)** Which product slugs? (free text list — kebab-case)
3. **(only if multi)** Should each product get its own theme answers, or
   are some themes shared at the root? (Default: each product gets its own
   for product_identity, problem_opportunity, users_personas, use_cases,
   functional_requirements; technical_constraints and downstream themes
   may be shared.)

Persist these to state under `monorepo:` and `products:` (already in the
state schema) before proceeding.

**Not asked here: which downstream stages this project needs**
(`pipeline_scope`). It does not shape the PRD's structure, and it is derived
from `technical_constraints.runtime_platform`, which is not answered until
Phase 6 — so it runs as that theme's closing question instead (below).

### Phase 5 — Pre-fill confirmation

Present the pre-fill map **theme by theme**. For each theme that has any
pre-filled values, render a block like this:

```
## Product Identity (pre-filled)

  ✓ name        : "acme-app"            [from package.json]
  ⚠ slug        : "acme-app"            [inferred from package name]
  ✓ one_liner   : "Acme is a tool for…" [from README.md line 3]
    tagline     : (not pre-filled — will ask in interview)

For each ⚠ inferred item, type **confirm** to accept, or correct it.
For ✓ found items, you can batch-accept by typing **ok** to take all of them.
```

The pre-fill block expects TYPED replies (`confirm` / corrections / `ok`),
so the turn must END with it — never combine it with a same-turn
`AskUserQuestion` (channel rule: `references/importance-flows.md`).

**Critical rule**: `⚠ inferred` items must NOT be batch-accepted via
shortcuts like "ok" or "1a, 2b". Each one needs an explicit confirmation
or correction. This is the hallucination guard — pre-filled inferences are
where wrong requirements sneak in unnoticed.

Write the confirmed values into the state file. Set
`<field>_confidence: confirmed` for explicitly confirmed items,
`<field>_confidence: inferred` for accepted-as-is inferences.

### Phase 6 — Theme interview

Walk the themes in the order defined by `prd-questions.yaml`. Use
`AskUserQuestion` as the canonical asking channel. For each theme:

- **Required themes** (`required: true` in the YAML): run the theme's
  questions until every required question is answered. Write state after
  every confirmed batch or mini-section.
- **Optional themes** (`required: false`): before asking any questions, offer
  a gate via `AskUserQuestion`:

  > "Theme: **\<name\>** — N questions. \<one-line description\>.
  > Address now, skip, or mark as todo?"

  - **now** → run the theme's questions as above.
  - **skip** → record under `skipped_themes` in state, move on.
  - **todo** → append a **typed** entry to
    `open_questions.undecided_decisions` — `{id: QUE-NNN, question:
    "Address theme <name>", status: open}`, minting the id from
    `state.last_ids.QUE` — then move on. Never a bare "TODO: …" bullet;
    open questions are a typed family (see PRD.schema.yaml → QUE; user
    stories, USR, are the other typed family).

Required questions can never be `todo`'d. They must be answered, set to
`null` (writing a note to `prd_warnings`), or the user must `EXIT`.

After all themes are addressed (answered/skipped/todo'd), set
`suggestion_phase_done: true` in state.

#### Closing the `technical_constraints` theme: which stages does this project need?

Immediately after `runtime_platform` is answered — while it is on screen, and
before the next theme — ask ONE multi-select that records `pipeline_scope`
(PRD.schema.yaml). This is the **skip authority** for the three optional
stages: an entry marked not-applicable means the stage need not be run at all
and its artifact will never exist, so `design` / `api` / `arch` read a recorded
intention instead of stopping to ask the user why `docs/UX.yaml` is missing.

Derive the proposal from `runtime_platform` (a LIST), and offer it as a single
`⚠ inferred` pre-selection the user adjusts:

| `runtime_platform` contains | propose |
|---|---|
| only `service` / `library` / `embedded` | **ux no**, **design no**, api: ask |
| `cli` / `tui` (and nothing visual) | ux yes, **design no**, **api no** |
| any of `web`, `mobile_ios`, `mobile_android`, `desktop`, `browser_extension`, `voice` | ux yes, design yes, api yes |

Cross-check the proposal against the Phase-2 repo scan before showing it: a
repo with route files, templates or a component library has a UX whatever the
platform enum says, and finding none is corroboration, not proof.

> "Which of these stages does this project need? `ux` (user-facing surfaces),
> `design` (visual design system), `api` (a service contract). Unticking one
> means you never have to run it — later stages will know it was deliberate."

For every stage the user unticks, capture a one-sentence **rationale** (the
validator requires it — a stage scoped out with no reason leaves the next
reader a fact they cannot judge) and set `confidence: confirmed`. Write the
whole block only for stages the user actually decided; **omit a key rather
than guess it**, because an absent key means "unknown, ask me later" while
`applicable: false` means "never ask again".

Skip this question entirely when `runtime_platform` is `undecided` — there is
nothing to derive from, and an unknown scope is the correct state. Note it in
`prd_warnings` so the user knows a later stage may ask.

#### Within a theme: tiered question flow

Each question in `prd-questions.yaml` carries an `importance` field
(`med | high | critical | nested_freeform`) that controls how the agent
runs it:

- **`med`** (the default — most questions): batch with up to 3 sibling
  `med` questions from the same theme into one `AskUserQuestion` call.
  `⚠ inferred` candidate at position 1.
- **`high`** (~12 questions, mostly required list[string] fields and
  foundational narratives): runs as its **own mini-section** — never
  batched with other questions. For scalars: agent drafts a full answer,
  shows it, user approves or iterates (max 3 rounds). For list[string]:
  per-item with one clarifying challenge round each.
- **`critical`** (`features`,
  `non_functional_requirements.other`): full per-item state machine —
  propose → optionally challenge → detail (with structured slots:
  input / output / dependencies / edge cases / why for FRs;
  scope / threshold / measurement / downstream-impact / why for NFRs)
  → optionally clarify → final approval. After "Done", a **dynamic
  scope-completeness sweep** reflects on the draft list + all upstream
  answers and surfaces concrete candidate items the user (and the
  agent) may have forgotten — derived per project, not from a canned
  category list.
- **`nested_freeform`** (currently only `conventions`): per-bucket flow
  for a `Dict[str, Any]` field whose shape is project-defined. Runs LAST,
  as a deliberate **synthesis pass** over the whole project — the
  conventions analogue of the `critical` scope sweep, and the block where
  the most manual rework lands when done thinly. Agent reflects across all
  answers + every upstream ID family + the project type, proposes named
  buckets, and drafts a free-form nested YAML body per bucket the user
  approves or iterates on. Validator only type-checks the top-level
  mapping. **Read `references/conventions-catalog.md` before this pass** —
  it holds ~12 bucket archetypes to reason from.

Order within a theme: run all `med` questions first (in 2–4-question
batches), then each `high`/`critical`/`nested_freeform` question as
its own mini-section in the order they appear in `prd-questions.yaml`.

**Read `references/importance-flows.md` before running any
`high`/`critical`/`nested_freeform` question.** It contains the exact
`AskUserQuestion` prompts, slot tables, sweep heuristics, iteration
caps, EXIT-mid-flow rules, and the `product_identity` synthesis batch
example.

For batch format details (option layout, free-text-only questions,
`capture_rationale` follow-ups, `required_if` conditional-promotion
table) → see `references/interview-mechanics.md`.

The three non-negotiable rules in this phase:

1. `⚠ inferred` candidates surface as the **position-1 recommended option**
   in their `AskUserQuestion` call. They cannot be silently accepted — the
   user must explicitly pick or correct. This is the hallucination guard.
2. State is written after **every confirmed batch or mini-section**, not
   at theme boundaries.
3. **The channel rule** (`references/importance-flows.md`): content a
   question depends on rides INSIDE the `AskUserQuestion` call (question
   text, option description, or option preview); chat markdown printed in
   the same turn as a tool call may not render and is never load-bearing.

### Phase 7 — Write & validate

Write or merge `docs/PRD.yaml` at the project root, then run:

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/PRD.yaml
```

For full merge logic (conflict handling, key preservation, deletion
confirmation), type discipline when writing list-typed fields, and the
exit-code recovery flow → see `references/merge-validate.md`.

When writing the file: inline YAML comments on top-level keys, updated
`metadata.last_updated` and `metadata.session_id`.

Set `metadata.status`:
- `"complete"` — only when all required fields are filled and the validator
  passes with `[OK]`.
- `"draft"` — on early EXIT or when any required field is still null.

If the validator returns `[FAIL]` because required fields are missing despite
`status: complete`, ask the user via `AskUserQuestion` to either fill them
in now or accept `status: draft`.

**Acceptance-criteria backfill.** When the validator's warnings name features
that no acceptance criterion covers ("N feature(s) have no acceptance
criterion…"), offer to close the gap before leaving Phase 7 — ONE
`AskUserQuestion`: *"Add acceptance criteria for these N features now?"* with
options **Add now — I'll draft one per feature** (recommended) / **Skip —
keep the warning**. On "Add now": draft one `ACR-NNN: FR-NNN — <observable
done-condition>` per named feature, confirm the drafts in batches of ≤4 per
call (the drafts ride inside the call, channel rule), mint ids from
`state.last_ids.ACR`, append to `success_metrics.acceptance_criteria`, and
re-run the validator once. Never loop the offer.

### Phase 8 — Refresh & complete

**This skill does not write `CLAUDE.md`.** That file is owned by `/sdlc:setup`,
which writes one static `## SDLC Documents` block. A caveat belongs in this
artifact's own `WRN-NNN` list, a spec defect in the findings queue, a skill
defect in the lessons queue — never as a note, a bullet or a "resolved" section
in `CLAUDE.md`. See `references/merge-validate.md`.

**Refresh the navigation index.** If `.claude/sdlc/docs_index.py` exists (the
project ran `/sdlc:setup`), run `python .claude/sdlc/docs_index.py` after
writing `docs/PRD.yaml` so `docs/INDEX.yaml` reflects the new content right
away. The setup hook also regenerates it on every `docs/*.yaml` write, but a
hook added during the current session only activates next session — running it
here closes that gap. Harmless no-op if the generator isn't installed.

**Refresh the statusboard.** Run `python .claude/sdlc/statusboard.py` in the
same breath. It regenerates `.claude/rules/sdlc-statusboard.md` (loaded into
every session) and `.claude/sdlc/STATUS.md` from the artifacts, so this run's
new warnings, deferrals and open questions are visible to the next agent
without anyone writing them down by hand. Harmless no-op if it is not installed.

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
python .claude/sdlc/lessons.py record-run --skill prd --plugin-root "${CLAUDE_SKILL_DIR}/../.."
```

Best-effort: a non-zero exit becomes one `Attention:` clause in the card;
helper absent (project never ran `/sdlc:setup`) — skip silently.

**Drain `finding_notes`** (CLAUDE.md 13). `prd` consumes no upstream
artifact, so nothing auto-raises at close — but a user can describe a defect
in an existing `docs/` artifact mid-interview (the a-2 free-text fold,
`references/importance-flows.md`), and those observations wait in
`state.finding_notes`. For each entry, run:

```bash
python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add --raised-by sdlc-prd --kind <kind_guess> --summary "<summary>" --evidence "<evidence>"
```

Cap: 3 per run unless one is blocking. Helper absent (project never ran
`/sdlc:setup`) — skip silently and keep the notes in state. This drain runs
on **every** exit path, EXIT included. When any finding was recorded, the
close card gains a `Findings:` row.

**Close with the card** (CLAUDE.md 14; canonical shape:
`sdlc/skills/prd/references/reporting-to-the-user.md`). The user reading this
knows only "there is a pipeline and I run it in order", so answer their three
questions and nothing else: did it work, can I run the next skill, what do I
type next.

```
-- /sdlc:prd - what you have now ---------------------
Wrote:     docs/PRD.yaml ({the one count that matters})
Status:    complete - /sdlc:ux can run it
Attention: {what needs a decision, in the user's words}
Next:      {the computed next invocation}   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript.
```

**Compute the `Next:` row; never copy the example.** Procedure and successor
map: `sdlc/skills/prd/references/reporting-to-the-user.md`
(CLAUDE.md 14). For `/sdlc:prd` it resolves to:

- **`docs/` artifact is `draft`, the user typed `EXIT`, or the validator is not
  green** → `Next:` is `/sdlc:prd` again, and `Status:` says what finishing
  means. Never hand off an unfinished artifact.
- **This run recorded findings, or open findings name `docs/PRD.yaml`** →
  `Next:` is `/sdlc:repair` (name the ids) before any successor.
- **Complete and green** → `/sdlc:ux` is the pipeline successor and always the successor here — `prd` is not sharded.


Rules: omit any row with nothing to say (never write "no warnings"). Add a
`Lessons:` row only when this run recorded at least one — e.g. `Lessons: 1
recorded (LSN-004) - about this skill, for its maintainer; nothing for you to
do` — and never print "no lessons". Add a `Findings:` row only when the
Phase 8 drain recorded at least one — e.g. `Findings: 1 recorded (FND-007)
-> /sdlc:repair` — and never print "no findings".
**`Attention:` is translated, never pasted validator output** - turn each
finding into what happened, why it matters, and what to do. If the validator
printed nothing worth acting on, drop the row.

There is no literal `Next:` value to copy anywhere in this file — the row is
computed at every close by the procedure above, never echoed from an example.

## Session state file

Path: `.claude/skills-state/sdlc-prd.state.yaml`

Schema:

```yaml
session_id: <uuid4 string>
skill_version: <the skill_version at the end of this file>
started_at: <iso8601>
last_updated: <iso8601>
status: in_progress  # in_progress | complete | aborted
monorepo: false      # mirrors PRD metadata
products: []         # populated only when monorepo: true; list of product slugs
idea_text: null      # user's free-text idea description (Phase 3)
pre_fill_confirmed: false
suggestion_phase_done: false
completed_themes: []
skipped_themes: []
todo_themes: []      # themes the user marked `todo` in Phase 6
pending_themes: []
current_theme: null
migrations: []       # additive skill_version migrations applied on resume
                     # (references/edge-cases.md): [{from, to, at, added, retired_themes}]

# Per-family ID counters (single-product mode). Each entry is the last-assigned
# integer for that family — increment, format as <PREFIX>-{:03d}, then persist.
# See references/importance-flows.md → "ID conventions across families" for the
# family map (FR, OOS, INT, AIF, NFR, WRN, PER, GOL, PAN, WKF, JTB, EDG, ENT,
# ACR — success_metrics.acceptance_criteria, QUE — open_questions typed
# entries; both lists share the one QUE counter; USR — user_stories.stories
# typed entries, PRD 1.1).
last_ids: {}        # e.g. {FR: 5, PER: 2, WKF: 4, ACR: 2, QUE: 3, USR: 4, ...}

# Per-product ID counters (monorepo mode only). Same shape as last_ids, keyed
# by product slug. Each product carries an independent ID space per family.
last_ids_by_product: {}  # e.g. {auth: {FR: 3, PER: 2}, billing: {FR: 2}}

# Run telemetry (CLAUDE.md 15) — updated in the same write as everything
# else; consumed only by `lessons.py record-run` at close.
metrics: {}          # questions_asked, free_text_answers,
                     # free_text_by_question{<question-id>: n},
                     # validator_runs, validator_failures, resumes

lesson_notes: []     # mid-run lesson scratch (CLAUDE.md 15): observations
                     # noted while the run is in flight, drained by the
                     # Phase 8 self-review - the run is never interrupted
                     # to record. Entries: {noted_at, about, kind_guess, note}

finding_notes: []    # mid-run findings scratch (CLAUDE.md 13): defects the
                     # user described in an EXISTING docs/ artifact (the a-2
                     # free-text fold), drained by the Phase 8 findings drain
                     # on every exit path - the run is never interrupted to
                     # record. Entries: {noted_at, kind_guess, file, summary,
                     # evidence}

dropped_candidates: {}  # sweep candidates the user declined (CLAUDE.md state
                        # contract), keyed by schema_path. Entries:
                        # {candidate, seeded_from, reason, at}. Step e of
                        # references/importance-flows.md excludes recorded
                        # drops from re-surfacing; an update run reconsiders
                        # one only when its seeded_from answer changed.

partial_answers: {}  # mirrors PRD.yaml structure incrementally
```

Rules:

- Generate `session_id` as a UUID4 on first creation.
- Update `last_updated` on every write.
- Write the file **after every confirmed batch**, including pre-fill
  confirmations and the Phase 3 idea-text capture.
- The `metrics` counters (schema above) update in the same write: a batch
  bumps `questions_asked`; an Other/free-text answer bumps `free_text_answers`
  and `free_text_by_question[<question-id>]` — the id from
  `prd-questions.yaml`, verbatim (the Phase 3 idea prompt is `idea_text`);
  a resume bumps `resumes` (Phase 1); Phase 7 counts
  `validator_runs`/`validator_failures`.
- On user `EXIT`: set `status: aborted`, write current `partial_answers`,
  drain `lesson_notes` (lessons-capture.md → "Mid-run: note now, record at
  close") AND `finding_notes` (the Phase 8 findings drain runs on every
  exit path), run
  `python .claude/sdlc/lessons.py record-run --skill prd --outcome aborted`
  (skip silently if the helper is absent), confirm to user that state was
  saved, then stop.
- On Phase 8 completion: set `status: complete` but keep the file.
- The validator ignores this file — it validates only `docs/PRD.yaml`.

**Source of truth on resume:**

- `docs/PRD.yaml` (if present) is the on-disk source of truth for *answers*.
- The state file is the source of truth for *interview progress*.
- On resume: load `docs/PRD.yaml` first as the baseline, then layer the state's
  `partial_answers` on top.
- If they conflict on the same key, ask the user which to keep — never
  silently overwrite. (See Phase 7.)

## Edge cases

For unusual situations (no files found, existing PRD without state, conflicting
scan signals, skipped required fields, validation failures, mid-interview
abort, very large projects, write-permission errors, skipped Phase 3 idea
capture, monorepo-mode change mid-flow, hallucination-guard violation
attempts) → see `references/edge-cases.md`.

## Style of conversation

The interview is potentially long. Keep it humane:

- Use the user's terminology as soon as they introduce it.
- Keep AskUserQuestion batches to 2–4 questions; never more than 4.
- Acknowledge progress at each theme boundary ("That's problem & opportunity
  done — next: users & personas, 5 questions.").
- Always make multiple-choice the path of least resistance.
- For the product_identity batch (Phase 6 finale), explicitly call out that
  candidates were synthesized from prior answers — don't pretend they came
  from nowhere.
- After all themes are done, congratulate the user briefly and move to write/validate.
  Do not repeat the entire summary back at them.
  (This is about the INTERVIEW. The Phase-8 close report is separate and
  is NOT optional — see the card in Phase 8.)

## Quick reference: commands the user can type

| User input | Effect |
|---|---|
| `EXIT` | Abort: type into the free-text field of any AskUserQuestion call. |
| `confirm` | Accept a single inferred pre-fill (Phase 5). |
| `ok` | Batch-accept all `✓ found` pre-fills in the current theme, OR accept the Phase 3 summary as-is. |
| `now` | Run the proposed optional theme (gate question). |
| `skip` | Skip the proposed optional theme (gate question). |
| `todo` | Defer the proposed optional theme; logs it to `open_questions.undecided_decisions`. |

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.12"
