# Interview mechanics — sdlc-ux

Rules for how the agent runs the question batches in Phase 6. Read this
when entering Phase 6.

The mechanics here are intentionally close to `sdlc:prd`'s
`interview-mechanics.md` so users see a consistent interface across the
SDLC pipeline. Anything that differs from the PRD flow is called out
explicitly below.

## AskUserQuestion call format

Each batch is **one `AskUserQuestion` call** covering 2–4 questions
(never fewer, never more — the tool's hard limit is 4 and single-question
interactions stall momentum).

Structure each question in the call:

```
header:   ≤ 12 chars  — abbreviated theme label (e.g. "Platform", "A11y", "Nav")
question: full question text ending with "?"
options:  2–4 options ranked by relevance
multiSelect: true for list-typed fields
```

### Option layout — the universal pattern

| Position | Content |
|---|---|
| **1** | Recommended / `⚠ inferred` answer drawn from PRD or pre-fill map |
| **2** | First viable alternative |
| **3** | Second viable alternative |
| **4** | Third viable alternative. If more options exist, list them in this option's `description`: `"Also: <option5>, <option6>, …. Use the text field to enter any of these or a custom answer."` |

The tool auto-adds an "Other" free-text entry below the explicit options.
The user can type any value there, including `EXIT`. Position 4 is the
last *explicit* option — its description surfaces remaining menu items
so the user knows what else is available.

### Free-text-only questions

For questions with no menu (`suggested_answers: []` in `ux-questions.yaml`),
fill all 2–4 positions with `⚠ inferred` suggestions drawn from the PRD,
pre-fill map, or earlier answers. Examples:

- `design_principles.tenets` — surface 3–4 candidate tenets distilled
  from the PRD's product_identity and users_personas.
- `navigation_model.top_level_nodes` — propose nodes synthesised from
  `PRD.use_cases.core_workflows`.

### EXIT handling

The user aborts by typing `EXIT` (case-insensitive) in the "Other" text
field of any `AskUserQuestion` call. After every batch response, check
whether any field's answer equals `EXIT` before processing the values.
If detected, trigger the abort flow:

1. Write current state with `status: aborted`.
2. Flush partial answers into `state.partial_answers` and
   `state.partial_surfaces` so resume preserves everything.
3. Confirm to the user that state was saved.
4. Stop.

### Example batch (state_patterns theme, three `med` questions)

```
AskUserQuestion(questions=[
  {
    header: "Loading",
    question: "Loading-state pattern across all surfaces?",
    options: [
      { label: "⚠ Skeleton placeholders", description: "⚠ Inferred from Shadcn library choice. Matches final layout." },
      { label: "Spinner centered",         description: "Standard library spinner, centered on surface." },
      { label: "Top progress bar",         description: "Linear progress bar at top of surface; content greyed." },
      { label: "Optimistic UI",            description: "Render assumed result, reconcile on response. Also: synchronous-only. Use text field for any other." }
    ],
    multiSelect: false
  },
  {
    header: "Empty",
    question: "Empty-state pattern?",
    options: [ ... ],
    multiSelect: false
  },
  {
    header: "Success",
    question: "Success / confirmation pattern?",
    options: [ ... ],
    multiSelect: false
  }
])
```

## Parsing responses

After the `AskUserQuestion` call returns:

- **Picked option (non-inferred)**: use the option label/value directly.
  Set `<field>_confidence: confirmed`.
- **"Other" free text**: use the text verbatim (after checking for `EXIT`).
  Set `<field>_confidence: confirmed`.
- **`⚠ inferred` option accepted as-is**: set
  `<field>_confidence: inferred`.

For `multiSelect` questions: collect all selected labels plus any "Other"
text into a list.

If the response is ambiguous (e.g. free text that could map to multiple
fields), ask a single targeted clarifying `AskUserQuestion` before
writing.

## Capturing rationale

For questions marked `capture_rationale: true` in `ux-questions.yaml`,
immediately follow with a single-question `AskUserQuestion`:

```
header: "Why?"
question: "In one sentence — why this choice?"
options: [
  { label: "Skip", description: "No rationale needed." },
  { label: "Type reason", description: "Use the text field." }
]
```

Skippable. Stored at `<schema_path>_rationale`.

## Type discipline when writing answers

`UX.schema.yaml` and `UX__SURFACE.schema.yaml` specify the expected type
of every field. Many fields are *lists* (e.g. `design_principles.tenets`,
`accessibility.screen_reader_notes`, `navigation_model.top_level_nodes`,
every surface's `interactions`, `components`, `traces_prd_flows`).

When the user picks multiple options or types a multi-item free-text
answer (separated by `;`, `,`, "and", or one-per-line), split into a
proper YAML list. Single-item answers go in as a one-element list.

Never serialize a list-typed field as a single string — the validator
will reject it.

If the user answers "none" for a list-typed field, write an empty list
`[]`, not the string `"none"`.

## Importance tiers (`med | high | critical`)

`sdlc:ux` uses the same tier mechanics as `sdlc:prd`. The key references
live in the PRD skill's `importance-flows.md`; only the additional
specifics for the UX skill are summarised here.

### `med` flow (default)

Single AskUserQuestion entry, `⚠ inferred` candidate at position 1.
Batch 2–4 sibling `med` questions from the same theme.

### `high` flow

Used for the foundational narrative fields and required list[string]
fields: `design_principles.tenets`, `navigation_model.top_level_nodes`,
`component_library.name` (with rationale), `state_patterns.error`,
`content_rules.tone`, `content_rules.terminology`, and the per-surface
fields `states`, `components`, `validation_rules`, `entry_conditions`,
`exit_conditions`.

For scalar `high` fields: agent drafts a 2–4-sentence answer, prints it,
asks for approval. On iterate, re-draft up to 3 times then accept the
current draft and add a `ux_warnings` entry naming the field.

For list[string] `high` fields: run per-item — propose, optional single
clarifying round on free-text items, append. Soft cap 8 items, hard cap 12.

### `critical` flow

Reserved for **theme 4 (`surface_inventory`)** and **theme 11
(`per_surface_deepdive`)** — the per-item state machines that drive the
entire UX skill. See `references/surface-discovery.md` for the full
per-surface state machine, the **scope-completeness sweep** (theme 4
step e — analogous to PRD's `features` sweep in
`importance-flows.md`), and the SCR-NNN assignment timing.

The sweep is mandatory in theme 4: after the per-item loop closes, the
agent runs up to two reflective passes over every upstream PRD family
(WKF, FR, ENT, JTB) plus project-type heuristics to catch surfaces the
initial seeding missed. Adding the sweep is the single most important
defence against gaps like "an entity literally named a CLI command in
its description but no workflow mentioned it, so the surface didn't
make it into the inventory." See `surface-discovery.md` for the exact
caps, anti-padding rule, and confidence-tagging behaviour.

## Conditional promotions (`required_if`)

Several questions in `ux-questions.yaml` carry `required_if:` rules.
Re-evaluate at the start of each new theme batch.

| Question / theme | Becomes required when |
|---|---|
| `platform_and_shell.surface_family_members` | `surface_family == 'mixed'` |
| `platform_and_shell.device_targets` | `surface_family in ['web','mobile','desktop','mixed']` |
| `platform_and_shell.viewport_breakpoints` | `surface_family in ['web','mixed']` |
| `navigation_model.deep_link_strategy` | `surface_family in ['web','mobile','mixed']` |
| `cli_specifics` (whole theme) | `surface_family in ['cli','mixed']` |
| `localisation.default_locale` | `localisation.enabled == true` |
| `localisation.target_locales` | `localisation.enabled == true` |
| `localisation.framework` | `localisation.enabled == true` |
| `localisation.rtl_support` | `localisation.enabled == true` |

When a question is promoted, surface this to the user transparently in
the next batch header or as a single AskUserQuestion before starting
that theme:

> "Because you set `surface_family` to `cli`, the `cli_specifics` theme
> is now required. I'll ask those questions next."

## Hallucination guard

`⚠ inferred` candidates surface as the **position-1 recommended option**
in their `AskUserQuestion` call. They cannot be silently accepted — the
user must explicitly pick or correct. This applies to:

- Phase 5 pre-fill confirmation.
- Phase 6 theme 4 (`surface_inventory`) candidate surfaces.
- Phase 6 theme 11 (`per_surface_deepdive`) every per-surface field.

Refuse and re-prompt if the user attempts to batch-accept inferred
items without explicit selection.

## State-write timing

State is written:

- After every confirmed batch (the standard cadence — same as
  `sdlc:prd`).
- After every per-surface deep-dive completion (theme 11). Each
  completed surface flips its `defined_surfaces[i].status` from `draft`
  → `confirmed` in state, and the partial surface yaml content moves
  from `state.partial_surfaces[<surface_id>]` to a confirmed slot.
- On EXIT — `status: aborted`, current `partial_answers` and
  `partial_surfaces` flushed, confirm to user, stop.
