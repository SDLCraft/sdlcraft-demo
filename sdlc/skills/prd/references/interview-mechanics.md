# Interview mechanics

Detailed rules for how the agent runs the question batches in Phase 6.
Read this when entering Phase 6 (the theme interview).

## AskUserQuestion call format

Each batch is **one `AskUserQuestion` call** covering 2–4 questions. Never
fewer than 2 (single-question interactions stall momentum) or more than 4
(the tool's hard limit).

Structure each question in the call as follows:

```
header:   ≤ 12 chars  — abbreviated theme label (e.g. "Problem", "Tech Stack")
question: full question text ending with "?"
options:  2–4 options ranked by relevance
multiSelect: true for list-typed fields (where the user may pick several)
```

### Option layout — the universal pattern

| Position | Content |
|---|---|
| **1** | Recommended / `⚠ inferred` answer — the top suggestion |
| **2** | First viable alternative |
| **3** | Second viable alternative |
| **4** | Third viable alternative. If more options exist beyond position 4, add to this option's `description`: `"Also: <option5>, <option6>, …. Use the text field to enter any of these or a custom answer."` |

The tool auto-adds an "Other" free-text entry below the explicit options.
The user can type any value there, including `EXIT`. Position 4 is the
last *explicit* option — its description surfaces the remaining menu items
so the user knows what's available without seeing them as selectable buttons.

### The channel rule

See AUTHORING §18 and `importance-flows.md` → "The channel rule" (this
skill's canonical worked examples) — cited here, not restated: content a
question depends on rides inside the `AskUserQuestion` call, never in
same-turn chat markdown.

### Free-text-only questions

For questions with no standard options (e.g. `problem_statement`,
`features`), all 2–4 positions carry `⚠ inferred` suggestions
drawn from the pre-fill map or Phase 3 idea text. The user picks one or
types their own via "Other".

### EXIT handling

The user aborts by typing `EXIT` (case-insensitive) in the "Other" text
field of any `AskUserQuestion` call. After every batch response, check
whether any field's answer equals `EXIT` before processing the values.
If detected, trigger the abort flow: write current state with
`status: aborted`, confirm to user, stop.

### Example batch (problem_opportunity, first 3 questions)

```
AskUserQuestion(questions=[
  {
    header: "Problem",
    question: "What user pain or unmet need does this product address?",
    options: [
      { label: "⚠ inferred: …", description: "Derived from README: '…'" },
      { label: "Manual process pain", description: "Users do this by hand today and it wastes time." },
      { label: "Missing data visibility", description: "Users can't see X without custom tooling." },
      { label: "Integration gap", description: "Two systems don't talk; manual syncing bridges them." }
    ],
    multiSelect: false
  },
  {
    header: "Problem",
    question: "Who specifically feels this pain?",
    options: [
      { label: "Software engineers", description: "Developers and DevOps practitioners." },
      { label: "Data analysts", description: "BI or data science teams." },
      { label: "Product / project managers", description: "Non-technical stakeholders." },
      { label: "Other", description: "Also: end consumers, small business operators, enterprise IT buyers. Use text field for anything else." }
    ],
    multiSelect: true
  },
  {
    header: "Problem",
    question: "How do affected people cope today?",
    options: [
      { label: "Manual / spreadsheets", description: "They track it in Excel or Notion." },
      { label: "Stitching tools", description: "Combining two or more existing tools with manual steps." },
      { label: "Competitor product", description: "Using a direct competitor." },
      { label: "Internal scripts", description: "Also: they simply don't (need goes unmet). Use text field for custom answer." }
    ],
    multiSelect: true
  }
])
```

## Parsing responses

After the `AskUserQuestion` call returns:

- **Picked option**: use the option label/value directly. Set
  `<field>_confidence: confirmed`.
- **"Other" free text**: use the text verbatim (after checking for `EXIT`).
  Set `<field>_confidence: confirmed` (explicit user input).
- **"Other" free text on a `free_text_allowed: false` question**: the field is
  an enum in the schema, so the text cannot be stored as the answer. Map it
  to the closest suggested value, read the mapping back in the next batch
  ("I recorded `org_owned` — the org is the controller and volunteers edit a
  narrow slice; right?"), and keep the text in `<field>_rationale` so the
  nuance is not lost — which the "Why?" follow-up below then skips, since the
  typed reply already IS the rationale. Count it under `free_text_by_question`
  all the same — the maintainer reads a high rate there as "the enum keeps not
  fitting", and that is worth knowing. Never widen the enum from inside a run
  (a schema change is the maintainer's; record a lesson if the values
  genuinely never fit, CLAUDE.md §15).
- **A `free_text_expected: true` question's `suggested_answers`** are
  templates, not complete answers a user can pick verbatim: each one that is a
  template carries a literal `<…>` placeholder (e.g. `"Throughput-driven: <N>
  req/s"`), never prose like "state your number" with nothing to fill in — a
  suggestion with no placeholder that a user CAN pick as-is defeats the flag's
  own contract.
- **`⚠ inferred` option picked without change**: set
  `<field>_confidence: inferred`.

For `multiSelect` questions: collect all selected labels + any "Other" text
into a list.

If the response is ambiguous (e.g. free text that could map to multiple
fields), ask a single targeted clarifying `AskUserQuestion` before writing.

## Capturing rationale

For questions marked `capture_rationale: true` in `prd-questions.yaml`,
immediately follow with a single-question `AskUserQuestion`:

```
header: "Why?"
question: "In one sentence — why this choice?"
options: [
  { label: "Skip", description: "No rationale needed." },
  { label: "Type reason", description: "Use the text field." }
]
```

Skippable. Stored at `<schema_path>_rationale`. Skipped entirely when the
Other-mapping rule above has already filled `<schema_path>_rationale` for
this question — the typed reply IS the rationale, so a second prompt would
just ask to repeat it.

## Type discipline when writing answers

`PRD.schema.yaml` specifies the expected type of every field. Many fields
are *lists* (e.g. `features`, `core_workflows`,
`key_entities`, `regulatory_requirements`).

When the user picks multiple options or types a multi-item free-text answer
(separated by `;`, `,`, "and", or one-per-line), split it into an actual
YAML list. Single-item answers go in as a one-element list.

Never serialize a list-typed field as a single string — the validator will
reject it.

If the user answers "none" for a list-typed field, write an empty list `[]`,
not the string `"none"`.

## product_identity — the synthesis batch

`product_identity` is asked LAST among required themes, so by the time
the agent gets there it has rich context to synthesize name, slug, and
one-liner candidates instead of asking cold. Every synthesized value
surfaces as the **position-1 `⚠ inferred` option** in its question.

The full call structure and hallucination-guard rules live in
`references/importance-flows.md` under "product_identity — the synthesis
batch" alongside the rest of the tier-flow guidance.

## `required_if` — the canonical definition (all SDLC skills)

A question inventory's `required_if:` rule (an expression evaluated against
already-answered fields) has exactly TWO readings, and an inventory's header
must say which one it means. This section is canonical — other skills'
`<skill>-questions.yaml` headers cite it rather than redefining the term:

- **Promotion** (the default, and prd's only reading): the question is always
  eligible to be ASKED; when the condition evaluates true, the field becomes
  REQUIRED — the artifact cannot reach `complete` while it is empty. While
  the condition is false, `required: false` stands and the answer is
  optional.
- **Activation**: the question is ASKED only when the condition holds; while
  the condition is false the question is skipped entirely and its field
  stays null with no warning. For inventories where the question is
  meaningless outside its condition (a platform-specific sub-question, a
  token-mode question on a no-theme design).

Whichever reading applies, re-evaluate every `required_if` at the start of
each new theme batch. Current promotion rules in prd:

| Question | Becomes required when |
|---|---|
| `security_compliance.auth_model` | `data_sensitivity in ['restricted', 'regulated', 'phi', 'pci']` |
| `security_compliance.regulatory_requirements` | `data_sensitivity in ['restricted', 'regulated', 'phi', 'pci']` |
| `business_model.pricing_model` | `monetization not in ['internal_tool', 'open_source', 'free']` |
| `technical_constraints.browser_support` | `'web' in runtime_platform` (a list as of schema 1.1) |
| `internationalization.default_locale` / `.target_locales` / `.rtl_support` | `internationalization.enabled == true` |
| `non_functional_requirements.performance_targets` | `scalability in ['large', 'hyperscale']` |

When a question is promoted, surface this to the user transparently in the
next batch header or as a single AskUserQuestion before starting that theme:

> "Because you set data_sensitivity to `regulated`, the security_compliance
> theme is now required. I'll ask those questions next."
