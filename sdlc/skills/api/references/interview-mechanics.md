# Interview mechanics — sdlc-api

Rules for how the agent runs the question batches in Phase 6. Read this
when entering Phase 6.

The mechanics here are intentionally close to `sdlc:prd`'s
`interview-mechanics.md` and `sdlc:ux`'s `interview-mechanics.md` so
users see a consistent interface across the SDLC pipeline. Anything
specific to the API skill is called out below.

## AskUserQuestion call format

Each batch is **one `AskUserQuestion` call** covering 2–4 questions
(never fewer, never more — the tool's hard limit is 4 and
single-question interactions stall momentum).

Structure each question in the call:

```
header:   ≤ 12 chars  — abbreviated theme label (e.g. "Auth", "Pagination", "Rate-limit")
question: full question text ending with "?"
options:  2–4 options ranked by relevance
multiSelect: true for list-typed fields (auth.schemes, transport_styles, error_codes, …)
```

### Option layout — the universal pattern

| Position | Content |
|---|---|
| **1** | Recommended / `⚠ inferred` answer drawn from PRD/UX/DATA or pre-fill map |
| **2** | First viable alternative |
| **3** | Second viable alternative |
| **4** | Third viable alternative. If more options exist, list them in this option's `description`: `"Also: <option5>, <option6>, …. Use the text field to enter any of these or a custom answer."` |

The tool auto-adds an "Other" free-text entry below the explicit
options. The user can type any value there, including `EXIT`.
Position 4 is the last *explicit* option — its description surfaces
remaining menu items so the user knows what else is available.

### Free-text-only questions

For questions with no menu (`suggested_answers: []` in
`api-questions.yaml`), fill all 2–4 positions with `⚠ inferred`
suggestions drawn from PRD/UX/DATA, pre-fill map, or earlier answers.
Examples:

- `resource_inventory.resources` — propose 3–4 candidate resources
  drawn from `DATA-MODEL.entities` + cross-entity PRD features.
- `events.channels` — propose candidate channels from UX surfaces that
  mention real-time updates (subscriptions, notifications, live feeds).
- `error_codes` — propose 3–4 codes synthesized from PRD features (e.g.
  `PROJECT_NOT_FOUND` for project-related features).

### EXIT handling

The user aborts by typing `EXIT` (case-insensitive) in the "Other"
text field of any `AskUserQuestion` call. After every batch response,
check whether any field's answer equals `EXIT` before processing the
values. If detected, trigger the abort flow:

1. Write current state with `status: aborted`.
2. Flush partial answers into `state.partial_answers` and
   `state.partial_resources` so resume preserves everything.
3. Confirm to the user that state was saved.
4. Stop.

### Example batch (pagination theme, three `high` questions)

```
AskUserQuestion(questions=[
  {
    header: "Strategy",
    question: "Pagination strategy?",
    options: [
      { label: "⚠ cursor",  description: "⚠ Inferred from PRD scale targets. Safer at scale; stable across inserts." },
      { label: "offset",     description: "Simpler but skews when data changes mid-page." },
      { label: "none",       description: "No list endpoints, or all lists are small/bounded." }
    ],
    multiSelect: false
  },
  {
    header: "Page size",
    question: "Default page size?",
    options: [ ... ],
    multiSelect: false
  },
  {
    header: "Sort field",
    question: "Stable sort field for cursor pagination?",
    options: [ ... ],
    multiSelect: false
  }
])
```

## Parsing responses

After the `AskUserQuestion` call returns:

- **Picked option (non-inferred)**: use the option label/value directly.
  Set `<field>_confidence: confirmed`.
- **"Other" free text**: use the text verbatim (after checking for
  `EXIT`). Set `<field>_confidence: confirmed`.
- **`⚠ inferred` option accepted as-is**: set
  `<field>_confidence: inferred`.

For `multiSelect` questions: collect all selected labels plus any
"Other" text into a list.

If the response is ambiguous (e.g. free text that could map to multiple
fields), ask a single targeted clarifying `AskUserQuestion` before
writing.

## Capturing rationale

For questions marked `capture_rationale: true` in `api-questions.yaml`,
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

Fields with `capture_rationale: true` in this skill include
`api_kind`, `auth.schemes`, `errors.envelope`, and
`pagination.strategy` — choices with large downstream blast radius
benefit from a one-line "why" that downstream agents can read.

## Type discipline when writing answers

`API.schema.yaml` and `API__RESOURCE.schema.yaml` specify the expected
type of every field. Many fields are *lists*
(`transport_styles`, `auth.schemes`, `auth.roles`, `auth.scopes`,
`rate_limiting.scopes`, `errors.error_codes`,
`external_dependencies`, `resource_inventory`, every resource's
`traces_prd_features`, `traces_ux_surfaces`, and `endpoints`).

When the user picks multiple options or types a multi-item free-text
answer (separated by `;`, `,`, "and", or one-per-line), split into a
proper YAML list. Single-item answers go in as a one-element list.

Never serialize a list-typed field as a single string — the validator
will reject it.

If the user answers "none" for a list-typed field, write an empty list
`[]`, not the string `"none"`.

## Importance tiers (`med | high | critical`)

`sdlc:api` uses the same tier mechanics as `sdlc:prd` and `sdlc:ux`.
The key references live in the PRD skill's `importance-flows.md`; only
the additional specifics for the API skill are summarised here.

### `med` flow (default)

Single AskUserQuestion entry, `⚠ inferred` candidate at position 1.
Batch 2–4 sibling `med` questions from the same theme.

### `high` flow

Used for the foundational fields with large downstream blast radius:
`auth.schemes`, `auth.roles`, `errors.envelope`, `errors.retry_semantics`,
`pagination.strategy`, `idempotency.idempotent_methods`,
`rate_limiting.scopes`, `events.channels`, and the per-resource fields
`schemas` and `primary_entity`.

For scalar `high` fields: agent drafts a 2–4-sentence answer, prints
it, asks for approval. On iterate, re-draft up to 3 times then accept
the current draft and add an `api_warnings` entry naming the field.

For list[string] `high` fields: run per-item — propose, optional single
clarifying round on free-text items, append. Soft cap 8 items, hard
cap 12.

### `critical` flow

Reserved for **theme 8 (`resource_inventory`)** and **theme 10
(`per_resource_deepdive`)** — the per-item state machines that drive
the entire API skill. Both themes are also marked `synthesis: true`:
after theme 8's per-item loop closes, the agent runs a dynamic
scope-completeness sweep against every upstream ID family (FR / WKF /
SCR / DATA entity names). See `references/resource-discovery.md` for
the full per-resource state machine and the sweep contract.

## Conditional promotions (`required_if`)

Several questions in `api-questions.yaml` carry `required_if:` rules.
Re-evaluate at the start of each new theme batch.

| Question / theme | Becomes required when |
|---|---|
| `api_kind_and_styles.rationale_for_none` | `api_kind == 'none'` |
| `api_kind_and_styles.transport_styles` | `api_kind != 'none'` |
| `events_async` (whole theme) | `transport_styles` includes `websocket`, `server_sent_events`, or `webhooks_out` |
| `pagination.default_page_size`, `pagination.max_page_size` | `pagination.strategy != 'none'` |
| `pagination.stable_sort_field` | `pagination.strategy == 'cursor'` |

When a question is promoted, surface this to the user transparently in
the next batch header or as a single `AskUserQuestion` before starting
that theme:

> "Because you set `transport_styles` to include `websocket`, the
> `events_async` theme is now required. I'll ask those questions next."

## Hallucination guard

`⚠ inferred` candidates surface as the **position-1 recommended
option** in their `AskUserQuestion` call. They cannot be silently
accepted — the user must explicitly pick or correct. This applies to:

- Phase 5 pre-fill confirmation.
- Phase 6 theme 8 (`resource_inventory`) candidate resources.
- Phase 6 theme 10 (`per_resource_deepdive`) every per-resource field.

Refuse and re-prompt if the user attempts to batch-accept inferred
items without explicit selection.

## State-write timing

State is written:

- After every confirmed batch (the standard cadence — same as
  `sdlc:prd` and `sdlc:ux`).
- After every per-resource deep-dive completion (theme 10). Each
  completed resource flips its `defined_resources[i].status` from
  `draft` → `confirmed` in state, and the partial resource yaml content
  moves from `state.partial_resources[<resource_id>]` to a confirmed
  slot.
- On EXIT — `status: aborted`, current `partial_answers` and
  `partial_resources` flushed, confirm to user, stop.
