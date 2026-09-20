# Surface discovery — how to enumerate, name, and deep-dive surfaces

Read this when entering **theme 4 (`surface_inventory`)** or **theme 11
(`per_surface_deepdive`)**. Both are `critical` per-item flows; this
file is the source of truth for how the agent drives them.

The core idea: **a surface is the smallest unit of UI the user
interacts with**. For graphical products that's typically a screen,
modal, panel, drawer, page, tab, dialog, overlay, or toast. For CLI
products that's typically one `cli_command` per verb+noun, plus one
`flow_step` per interactive prompt. A surface always has an `id`
(`SCR-NNN`), a `surface_id` (kebab-case slug), a `surface_type`, entry/
exit conditions, layout, states, and a `traces_workflows` list (may be
empty for chrome/diagnostic surfaces).

## Headless surface families (service, library — and cli)

Three families are **headless** — they expose no visual screens:

- **`cli`** — surfaces are `cli_command` / `flow_step` entries (the common
  case, covered throughout this file and `cli-ux.md`).
- **`service`** — a network service with no human UI. Its "surfaces" are the
  endpoints/operations it serves (owned by the API stage, not UX). Emit a
  **minimal** UX spec: enumerate at most a thin operational surface inventory
  (or none), set `accessibility.wcag_target: not_applicable_cli`, and leave
  `component_library`/theming null. Most of the interview's visual themes are
  gated `skip`.
- **`library`** — a code library / SDK with no UI at all. Its "surfaces" are its
  public API symbols (owned by the API stage). Emit the minimum: typically an
  empty or near-empty `surface_inventory`, `accessibility.wcag_target:
  not_applicable_cli`, null `component_library`. Record a `ux_warnings` note that
  the surface contract lives in the API spec.

For all three, do **not** manufacture screen surfaces. When `surface_family`
is `mixed` and includes a headless member, run the visual sub-interview for the
visual members and the minimal path for the headless ones. `tui` (full-screen
terminal UI) and `voice` (turn-based) are **not** headless — `tui` enumerates
screen-like surfaces; `voice` enumerates `flow_step` turns.

## ID conventions for surfaces

- **`id: SCR-NNN`** is the stable cross-stage handle. Once assigned (in
  step a of theme 4), it never changes — not when the user renames
  `surface_id`, not when the surface moves between products in monorepo
  mode (though monorepo SCR-NNN counters reset per product).
- **`surface_id`** is the kebab-case slug (`cmd-list`, `dashboard`,
  `quick-add`). It's used as the filename suffix
  (`docs/UX__<surface_id>.yaml`) and may be renamed during the
  interview. Renames update the slug + file path; the SCR-NNN id stays.
- **`state.last_ids.SCR`** is the writer-managed counter; persist after
  every accepted candidate (theme 4 step a AND step e sweep).

## Step 1 — Generate the candidate list from upstream PRD ids

`PRD.use_cases.core_workflows` (WKF-###) is the **primary** seed, but
not the only one. The PRD-to-UX gap that bites most often is "the
inventory only got drawn from workflows, but the product has commands
implied by entities or features that no workflow mentioned." (The
canonical example: an `ENT-032 ProjectRegistry` entity whose
description literally names an `aicf list` command but where no
WKF-### entry mentions cross-project enumeration.)

Seed candidates from **all** of these PRD families, in this order:

### 1a — `PRD.use_cases.core_workflows` (WKF-###) — primary

For each WKF-### entry, propose 1–3 candidate surfaces likely to
participate in it. Examples:

| WKF entry (verbatim) | Likely surface(s) |
|---|---|
| "WKF-001: Add a task in under 3 seconds" (web) | `dashboard` (screen), `quick-add` (modal) |
| "WKF-002: Mark tasks done from the keyboard" (web) | `dashboard` (screen) |
| "WKF-003: Authenticate via SSO" (web) | `login` (screen), `sso-callback` (page) |
| "WKF-001: List my open tasks" (cli) | `task-list` (cli_command) |
| "WKF-002: Add a task" (cli) | `task-add` (cli_command), `task-add-prompt` (flow_step, if interactive) |

### 1b — `PRD.functional_requirements.features` (FR-###) — feature-driven surfaces

Many FRs name a verb or screen directly in their description ("the CLI
exposes a `doctor` command", "users can view the artifact via `aicf
show`"). For each FR-### whose description mentions a verb/screen that
isn't already covered by a WKF-### candidate, add a candidate. Mark its
`implements_requirements` with the FR-### id.

**Read the whole FR, not its first clause.** One FR often carries a content
rule *and* the command that exposes it ("every error ends with a hint;
`myapp explain <code>` prints the long form"). The backticked
`<root_command> <verb>` is a candidate even when the rest of the FR is not
UX work: the FR-coverage gate is whole-FR (trace OR defer, as one), and
**either half silences the command** — a deferral whose reason is about the
other clause, or a trace to something that does not run the named command (a
surface for a different verb, or a `cli.exit_codes` entry, which has no
invocation at all). The validator reports both as `[FR names a command]`.
Either the command gets a surface that runs it *and* the FR is traced from
that surface, or the deferral reason says why the *named command* needs none.

**This step is not first-interview-only.** On a re-run, every FR (and ENT,
via 1c) the delta review reports as **added** goes through 1b/1c *before*
its incorporate / ignore / defer prompt, and the candidate it yields is that
prompt's position-1 option (`upstream-reconciliation.md` Step 4). An added
FR that skips this step arrives as a bare three-way decision, which is how
a command clause gets deferred unseen.

### 1c — `PRD.data_model.key_entities` (ENT-###) — entity-driven surfaces

Entities often imply CRUD/list/detail/registry surfaces — especially
when the entity description literally names a verb or surface (e.g.
`ENT-032 ProjectRegistry: CLI-side index of all known projects + branches
+ checkpoint DB paths (for aicf list / aicf resume)`). For each ENT-###:

- If the description names a CLI verb or screen → add as a candidate.
- If the entity is "displayed by the user" semantically → propose a
  list view + a detail view.
- If the entity is internal (e.g. `CheckpointRecord`, `GateResult`) →
  do NOT add a candidate; these are downstream-only.

Surfaces seeded from entities get the entity id(s) in
`references_entities`.

### 1d — `PRD.use_cases.primary_jobs_to_be_done` and `secondary_jobs` (JTB-###) — orthogonal lens

JTBs cut across workflows ("when I want to share a generated app, I want
a marketing brief and README produced automatically"). They rarely
imply new surfaces on their own once 1a–1c are done, but they're
consulted in the scope-completeness sweep (step e) as a check.

### 1e — Project-type heuristics

The same project profile (CLI tool, SaaS app, mobile-first, library,
internal data pipeline, etc.) tends to imply the same "obvious-once-
mentioned" surfaces. A CLI tool almost always has:

- A `doctor` / diagnostic command (config validation, dependency
  health, env-var inspection).
- A `list` / cross-resource enumeration view.
- A `log` / history / audit view (when audit_logging is true in PRD).
- A `version` flag (already conventional — don't add as a surface
  unless the product explicitly wants `aicf version` as a verb).

A web SaaS app almost always has:

- A `settings` screen, an `account` / profile screen, a `404` /
  `error` page, a sign-out flow.

Don't try to be exhaustive — the user will add, remove, or rename
during the per-item drill-down, and the sweep in step e catches what
this step misses. Aim for a starter inventory that covers every WKF-###
with at least one candidate.

## Step 2 — Generate `surface_id` slugs

`surface_id` is kebab-case, unique within the project (per-product in
monorepo mode), and short (≤ 32 chars). Rules:

- Derive from the dominant noun/verb of the surface, not the PRD
  workflow text.
- For CLI surfaces, mirror the invocation: `task add` → `task-add`,
  `aicf list` → `cmd-list` (use a consistent prefix like `cmd-` when
  the verbs themselves are common English words that might collide
  with other slugs).
- For graphical surfaces, use the destination concept: `dashboard`,
  `project-detail`, `quick-add`.
- For modal/dialog/drawer surfaces, prefix with the host surface and
  the action: `task-bulk-update-confirm`, `project-archive-confirm`.
- Renames during the interview are fine — update the
  `state.defined_surfaces` entry and the (unwritten) deep-dive partial
  in one move. **The SCR-NNN id stays.** If the surface yaml has
  already been written under the old slug, ask the user before
  deleting/renaming it on disk.

## Step 3 — Per-surface state machine (theme 4)

For each candidate surface, run one mini-section that confirms the
identity (id, slug, type, traces) but does NOT yet do the layout/states/
etc. deep-dive — that's theme 11.

### State machine

Each surface progresses through three states tracked in
`state.defined_surfaces[i].status`:

| state | meaning |
|---|---|
| `defined`   | id + slug + type known, no deep-dive started |
| `draft`     | deep-dive in progress (theme 11) |
| `confirmed` | deep-dive complete + user approved |

Theme 4 produces a list of `defined` surfaces. Theme 11 walks that list
and transitions each from `defined` → `draft` → `confirmed`.

### When is the `SCR-NNN` assigned?

Inside step a, **at the moment of acceptance**:

1. The user picks the position-1 inferred candidate, picks an
   alternative, types a free-text override, or "drops" it.
2. If accepted (any non-drop outcome): increment
   `state.last_ids.SCR` (or
   `state.last_ids_by_product[<slug>].SCR` in monorepo mode), format
   the new id as `SCR-{:03d}`, and write the surface_inventory entry
   with that id. Persist state in the same write.
3. If dropped: do not consume an id. Record the dropped candidate in
   `state.dropped_surface_candidates` so resume doesn't re-propose it.

This matches the PRD `critical` flow's "ID assigned at step c
(Finalize)" pattern. The downstream stability guarantee is the same:
once assigned, a `SCR-NNN` never moves.

### Per-item flow for theme 4

For each candidate surface from step 1:

#### a) Propose

```
header: "Surface N"
question: "Surface #N — confirm or revise?"
options:
  - { label: "⚠ <inferred slug> (<type>)",  description: "⚠ <one-sentence purpose>. Seeded from <WKF-NNN | FR-NNN | ENT-NNN | project-type heuristic>. Confirm or correct in text field." }
  - { label: "Rename slug",                  description: "Type a different surface_id (kebab-case) in the text field." }
  - { label: "Change type",                  description: "screen | modal | panel | drawer | cli_command | flow_step | empty_state | toast | overlay | tab | page | dialog | other." }
  - { label: "Drop this candidate",          description: "Remove it from the inventory — no surface will be created. No SCR-NNN consumed." }
```

On accept → assign next `SCR-NNN`, record:

```yaml
{ id: SCR-NNN,
  surface_id: <kebab>,
  surface_type: <enum>,
  status: defined,
  file_path: docs/UX__<surface_id>.yaml,
  traces_workflows: [],          # filled in step b
  implements_requirements: [],   # if seeded from an FR, prefill that id
  references_entities: [] }      # if seeded from an ENT, prefill that id
```

Persist state.

On rename → update the slug and `file_path`; keep the SCR-NNN id.

On drop → record `{ candidate_slug, reason, at: <timestamp> }` in
`state.dropped_surface_candidates`. Don't write the file. No id
consumed.

#### b) Confirm PRD references

If the seed was a WKF-### that the user might want to extend, ask one
clarifying `AskUserQuestion`:

```
header: "Workflows?"
question: "Which WKF-### workflows does '<surface_id>' participate in?"
options:
  - { label: "<WKF-NNN: short summary>",   description: "<verbatim WKF entry from PRD>." }
  - { label: "<WKF-NNN: short summary>",   description: "<verbatim WKF entry from PRD>." }
  - { label: "Other (type WKF-NNN)",       description: "Type one or more WKF-NNN ids (comma-separated) in the text field." }
  - { label: "None — non-flow surface",    description: "This surface doesn't trace to any WKF. (Will record a ux_warnings entry.)" }
multiSelect: true
```

Store **WKF-NNN ids only** in `traces_workflows`, never the verbatim
description text. The coverage check matches by id.

If the seed was an FR-### or ENT-### (steps 1b/1c), pre-fill
`implements_requirements` / `references_entities` accordingly. These
are not asked separately in theme 4 — they're refined in theme 11's
final-approval draft.

#### c) Next or end

When the candidate list is exhausted, ask:

```
header: "More?"
question: "Add another surface, or move to the scope sweep?"
options:
  - { label: "Add another (I'll suggest)", description: "I'll propose a candidate next." }
  - { label: "Add my own",                  description: "Type a surface_id + type in the text field." }
  - { label: "Done — run the sweep",        description: "Run a scope-completeness sweep over the inventory + every upstream PRD family before closing." }
```

**Caps**: soft 12 surfaces, hard 20. The sweep in step e can take the
list past the soft cap when the user picks candidates; that's
intentional. Above the hard cap, refuse politely and suggest splitting
the product or pushing some surfaces to a later phase.

When the user picks "Done", do **not** close the inventory yet — run
step e first.

### d) WKF coverage hint at end of step c

Before running the sweep, check whether every WKF-NNN id in
`PRD.use_cases.core_workflows` is referenced by at least one
`defined_surfaces[i].traces_workflows`. If any are uncovered, tell the
user which ones and ask:

```
header: "Coverage?"
question: "These WKF-### aren't covered by any surface: <id list>. Add surfaces for them now, leave the gap, or update existing surfaces' traces?"
options:
  - { label: "Add surface(s) now",        description: "I'll propose one per uncovered WKF-###." }
  - { label: "Leave gap — record warning", description: "Each uncovered WKF gets a WRN-NNN entry; UX.yaml saves as draft." }
  - { label: "Edit existing traces",       description: "Re-open an existing surface to add the missing WKF-### to its traces_workflows." }
```

This is the soft coverage check. The hard check happens in
`validate_schema.py` (Phase 7).

### e) Dynamic scope-completeness sweep

This is the gate that catches surfaces the user (and the agent so far)
forgot. It is **dynamic and project-specific**: don't use any canned
checklist. Instead, take a reflective pass over:

1. **The draft inventory itself** — what kinds of surfaces dominate?
   What kinds are conspicuously absent given the project profile?
2. **All upstream PRD families** — not just WKF-###. Look at:
   - **FR-###** descriptions for verbs/screens that didn't end up as a
     surface candidate (steps 1b vs the final draft).
   - **ENT-###** descriptions for entities whose description names a
     CLI verb or implies a CRUD/list/detail view that isn't on the
     list (the `ProjectRegistry → cmd-list` pattern).
   - **JTB-###** descriptions for jobs that don't have a clear surface
     path through the current inventory.
   - **NFR-###** entries that imply diagnostic/audit surfaces (e.g.
     `audit_logging: true` → a `log` / `history` view; auditability
     SLA → an `audit-trail` screen).
3. **Project-type heuristics** — a CLI tool typically has a doctor /
   list / log; a SaaS app typically has settings / 404 / account; a
   data pipeline typically has a status / lineage / lag view. Cite the
   profile when surfacing candidates.

The sweep produces **concrete candidate surfaces**, not category
labels. "You might be missing a list command" beats "have you
considered cross-project views"; "cmd-doctor for config diagnostics
(implied by FR-029 + FR-030)" beats "have you considered setup
helpers". The user is going to read these and decide in one click
each, so name the thing.

Format the sweep as **one** `AskUserQuestion` call surfacing the
agent's top 2–4 candidate surfaces. Add 1–2 sentences of preamble in
the question text explaining what you noticed (cite the PRD ids).

```
header: "Sweep"
question: "Looking at your N surfaces alongside PRD's FR/ENT/JTB ids — a
  few candidates look notable that aren't on the list yet. Add any of
  these, or wrap up?"
options:
  - { label: "⚠ cmd-list (cli_command)",   description: "⚠ Implied by ENT-032 ProjectRegistry ('aicf list / aicf resume'). Cross-project enumeration counterpart to cmd-status. Pick to draft." }
  - { label: "⚠ cmd-doctor (cli_command)", description: "⚠ Implied by FR-029 + FR-030; typical config/dependency diagnostic for any CLI tool. Pick to draft." }
  - { label: "⚠ cmd-log (cli_command)",    description: "⚠ Implied by FR-026 (run-level audit log); read-only history view. Pick to draft." }
  - { label: "Wrap up — list is complete", description: "Skip these. The inventory closes as-is." }
multiSelect: true
```

For each picked candidate: re-enter the per-item flow at step a (the
candidate is treated as the position-1 inferred candidate; agent may
skip risk-checking when self-evidently clean). Assign the next SCR-NNN
on acceptance. Then return to step e for a second pass.

**Caps for the sweep:**

- At most **2 sweep passes** per inventory (per product in monorepo
  mode). After two passes, even if you still see candidates, defer
  them to a `ux_warnings` entry:
  `"WRN-NNN: sweep suggested but not added — <candidate>, <candidate>"`
  and close the inventory. The user can re-run the skill in update
  mode if they want more.
- **No sweep at all** if the user added 0 surfaces in steps a-c (an
  empty inventory is its own signal — don't push). Surface a single
  `ux_warnings` note: `"WRN-NNN: surface_inventory empty — no surfaces
  collected"`.
- For very short inventories (1–2 surfaces), still run one sweep
  pass — short lists are exactly when forgotten surfaces are most
  likely.

**Anti-padding rule:** if you don't see *concrete* candidates after
honest reflection across all upstream families, surface 0 — close the
inventory without a sweep question. Don't manufacture candidates to
look thorough.

### Confidence after step e

Surfaces added during the sweep get
`surface_inventory[i].surface_family_confidence: inferred` if the
candidate was the position-1 (agent-proposed) option; `confirmed` if
the user edited via free text. Same rule as PRD's `critical` sweep.

### State-write timing

Write state after:

- each step a/b acceptance (single-surface granularity),
- each step e completed pass (so partial sweeps survive EXIT),
- each step c "Done — run the sweep" transition.

This keeps `EXIT` cheap.

## Step 4 — Per-surface deep-dive (theme 11)

For each surface in `state.defined_surfaces` (in id order), run the
deep-dive. The deep-dive is the `critical` per-item flow that writes
the per-surface yaml.

### State transition

When the deep-dive starts for a surface, set its status to `draft` and
seed `state.partial_surfaces[<SCR-NNN>]` (keyed by id, not slug, so
mid-deep-dive renames don't strand the partial) with the known identity
(`id`, `surface_id`, `surface_type`, `traces_workflows`,
`implements_requirements`, `references_entities` if pre-seeded) plus
empty values for the rest.

When the deep-dive completes (after step e final approval), flip status
to `confirmed`, write the surface yaml to disk
(`docs/UX__<surface_id>.yaml`), and move the contents from
`state.partial_surfaces` into a permanent slot.

### Per-surface mini-interview (5 steps)

For each surface:

#### a) Announce + identity recap

Open the surface with a one-line recap — "Now: `<SCR-NNN>` / `<surface_id>`
(`<surface_type>`); traces `<WKF-NNN list>`, implements `<FR-NNN list>`,
references `<ENT-NNN list>`." Because chat markdown sharing a turn with a
tool call may not render (the channel rule:
`../../prd/references/importance-flows.md`), either END the turn with the
recap or fold it into the first step-b question's text — never rely on a
banner printed in the same turn as an `AskUserQuestion` call.

#### b) Layout

Run the `surface.layout` question. For graphical surfaces, propose a
region tree (e.g. `header` + `content` + `footer`); for CLI surfaces,
propose an arg/flag structure. Use `AskUserQuestion` with 2–3 candidate
layouts and an "Other / type" option. Multi-turn iteration allowed (cap
3).

#### c) States

Run the `surface.states` question. By default, every state inherits
from the global `state_patterns` in UX.yaml — only ask the user to
override states that need to differ for this surface. The user can pick
"All five with global defaults" to short-circuit.

If the user picks an override, follow up with a single-question
`AskUserQuestion` for that state's `description` and
`content_outline`.

#### d) Interactions, components, validation_rules

Run these as three back-to-back `high` list[string] flows (per
`interview-mechanics.md`). For each:

- Propose 1–3 items inferred from PRD/feature context + the surface's
  identity recap.
- Per-item: confirm/revise/drop, one optional clarifying round.
- Soft cap 8, hard cap 12.

`validation_rules` is skippable if the surface has no input fields —
ask the gate question first:

```
header: "Validation?"
question: "Does '<surface_id>' have input fields needing validation rules?"
options:
  - { label: "Yes — list them",        description: "I'll walk through field validations." }
  - { label: "No — skip",              description: "Leave validation_rules empty." }
  - { label: "Inherit from a sibling", description: "Copy validations from another surface (pick which by SCR-NNN)." }
```

#### e) Final approval — with FR/ENT ref inference

Before presenting the final draft, **infer `implements_requirements`
and `references_entities`** by scanning the drafted answers for FR-###
/ ENT-### mentions:

- If the user's interactions/effects mention an FR-### → add to
  `implements_requirements` (de-duplicated, ordered).
- If the user's interactions/components/layout mention an ENT-### → add
  to `references_entities` (de-duplicated, ordered).

Present the drafted per-surface yaml (or a compact summary if long) and
ask:

```
header: "Approve?"
question: "Approve <SCR-NNN> as drafted? Inferred FR refs: <list>; ENT refs: <list>."
options:
  - { label: "Approve — write to disk",       description: "Save docs/UX__<surface_id>.yaml and continue." }
  - { label: "Edit refs",                      description: "Use the text field to add/remove FR-NNN or ENT-NNN ids." }
  - { label: "Iterate — type changes",         description: "Use the text field to describe what to change. The agent will re-draft." }
  - { label: "Skip for now — keep as draft",   description: "Move on to the next surface; this one stays status: draft and the file is NOT written." }
```

On approve: write the surface yaml, flip status to `confirmed`,
persist state.

On edit refs: take the user's revised id lists, re-validate format
(must match WKF/FR/ENT regex), then re-present step e.

On iterate: re-enter step b/c/d with the user's revision context. After
3 iterations on a single surface, write the current draft and add a
`ux_warnings` entry naming the surface
(`"WRN-NNN: <SCR-NNN>/<surface_id> deep-dive iteration cap reached"`).

On skip: leave status `draft`, do NOT write the file (the validator
won't see it, but the entry remains in `state.defined_surfaces` and
`state.partial_surfaces` so the user can resume later).

### State-write timing

Persist state after each per-surface step (b/c/d/e), not just at the
end. This keeps EXIT cheap mid-deep-dive — the partial surface stays in
`state.partial_surfaces[<SCR-NNN>]` and resumes cleanly.

## When the user EXITs mid-flow

- Mid-theme 4 (step a/b): write all approved inventory entries to
  `state.defined_surfaces`, drop the current unconfirmed candidate (it
  wasn't approved; no SCR-NNN was consumed). Set `status: aborted`.
- Mid-theme 4 (step e sweep): persist whatever sweep candidates were
  approved so far; do not finalize the sweep pass. Set
  `status: aborted`. On resume, agent asks: *"Sweep pass was in
  progress. Resume mid-sweep, or skip to theme 5?"*.
- Mid-theme 11 deep-dive on surface N: write the partial yaml content
  to `state.partial_surfaces[<SCR-NNN>]`. Do NOT write the surface
  file to disk (it's incomplete). Set `status: aborted`. The
  `state.defined_surfaces[N].status` stays `draft`.

On resume, the agent picks up at the partial surface — it explicitly
asks the user *"Resume mid-deep-dive of `<SCR-NNN>` (slug:
`<surface_id>`)?"* before re-entering theme 11.

## Naming and renaming surfaces mid-flow

If the user renames a surface's slug during theme 4 or 11:

1. **`id: SCR-NNN` does NOT change** — the slug is a label, the id is
   the handle.
2. If no file has been written yet → update the slug and `file_path`
   everywhere (`state.defined_surfaces`, `state.partial_surfaces` if
   keyed by slug — but the current schema keys by SCR-NNN, so only the
   `surface_id` field needs updating).
3. If the file already exists → ask the user:
   *"Rename `docs/UX__<old>.yaml` → `docs/UX__<new>.yaml`? The
   SCR-NNN id (`<SCR-NNN>`) stays the same. This will delete the old
   file."* Wait for explicit confirmation before deleting.

## Soft-deletion of dropped candidates

When the user drops a candidate in theme 4 step a:

- Record `{ candidate_slug, seeded_from: <WKF-NNN | FR-NNN | ENT-NNN | heuristic>, reason: "dropped by user", at: <timestamp> }` in
  `state.dropped_surface_candidates`.
- Don't propose the same slug again on resume.
- No `SCR-NNN` is consumed.
- The dropped surface is NOT written to `UX.yaml.surface_inventory`.

If the user later wants the dropped candidate back, they re-add it
manually via "Add my own" in step c; it gets the next available
SCR-NNN at that point.
