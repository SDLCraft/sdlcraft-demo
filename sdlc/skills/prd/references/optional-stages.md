# Optional stages — how a skill decides an upstream artifact isn't coming

Three of the pipeline's stages are optional: **`ux`** (a headless ETL, library
or service has no user-facing surface), **`design`** (nothing visual to style)
and **`api`** (no service contract). Every other stage always runs — every
project has a data story, an architecture, a test strategy and a task graph,
however small.

This file is the canonical mechanics. Skills reference it; they do not restate
it.

## Two records, two different facts

|  | Written by | When | Means |
|---|---|---|---|
| `PRD.pipeline_scope.<stage>` | `prd`, closing the `technical_constraints` theme | always | the stage **need not run at all** — its artifact will never exist |
| `<ARTIFACT>.metadata.applicability` | the stage itself | when it ran and found nothing to model | the stage **ran and concluded N/A** — an empty artifact exists |

Both are needed, and they are not interchangeable. `pipeline_scope` is what
lets a user skip `/sdlc:ux` entirely: nobody writes `docs/UX.yaml`, and the
absence is recorded as intentional in a file that always exists.
`metadata.applicability` is the generalization of `api_kind: none` — the stage
was invoked, the user confirmed there was nothing there, and the artifact is
deliberately empty so every coverage gate over it is vacuous.

## The rule every consumer implements

Given an upstream artifact this skill would read, resolve **is it applicable?**
in this order. First match wins.

1. **The artifact exists** → read `metadata.applicability`. A **missing field
   means `applicable`** — every artifact written before 0.8.0 lacks it, and
   defaulting the other way would silently disable gates on every legacy
   project. `not_applicable` is treated **exactly like an absent artifact**:
   skip its pre-fills, soften its coverage gates to vacuous, ask nothing.
2. **The artifact is absent and `PRD.pipeline_scope.<stage>.applicable` is
   `false`** → not applicable. **Ask nothing.** Note it once in this
   artifact's `*_warnings` as a `WRN-NNN` naming the stage and quoting the
   recorded rationale, so the skip is visible in the output rather than only
   in the PRD.
3. **The artifact is absent and there is no scope entry** (a legacy PRD, or a
   project that has not decided) → ask **one** `AskUserQuestion`, then record
   the answer in this skill's state under the existing `<x>_present` key so
   resume does not re-ask:

   > ⚠ No `<thing>` spec found (`docs/<FILE>` is missing). Is this a project
   > without `<a user-facing surface | a visual design | an API layer>`? If
   > not, stop and run `/sdlc:<stage>` first.

   Options: `"Yes, this project has no <thing> — continue"` /
   `"No — stop so I can run /sdlc:<stage> first"`. On stop, exit cleanly
   without writing anything.

   Then add one line to the close card:

   > `docs/UX.yaml` is absent and you confirmed this project has no UX.
   > Record it permanently with `/sdlc:prd` so later stages don't ask again.

**Consumers never write `PRD.yaml`.** Rule 3 is the legacy path, and it is
allowed to fire in more than one skill on an old project; the fix is one
`/sdlc:prd` re-run, not a write-back from a downstream skill.

**Do not map rule 3 into every consumer as an unconditional prompt.** Asking
six times for one fact is worse than not recording it at all. Rule 3 fires
only when rules 1 and 2 both came up empty.

## Writing the `not_applicable` stub (for the optional stage itself)

When the stage runs and the user confirms there is nothing to model:

- Write the artifact with `metadata.status: complete`,
  `metadata.applicability: not_applicable`, a one-sentence
  `applicability_rationale` (the validator **requires** it — a bare
  "not applicable" leaves the next reader a fact they cannot judge), and
  `applicability_confidence`.
- Leave every domain collection empty and write no sub-files. An artifact that
  claims not-applicable while still listing surfaces / tokens / resources is a
  contradiction, and each validator errors on it.
- Skip straight to Phase 7 (write & validate). No theme interview.
- The close card says the stage is recorded as not applicable and names the
  successor, which will skip it without asking.

`api` keeps `api_kind: none` as its domain form and stamps
`metadata.applicability: not_applicable` alongside it. Its validator errors on
the two disagreeing, and warns when a legacy `api_kind: none` file carries no
applicability marker.

## Deriving the proposal

Never ask cold. `PRD.technical_constraints.runtime_platform` (a LIST) is the
shape signal, corroborated by the repo scan:

| `runtime_platform` contains | ux | design | api |
|---|---|---|---|
| only `service` / `library` / `embedded` | no | no | ask |
| `cli` / `tui`, nothing visual | yes | no | no |
| any of `web`, `mobile_ios`, `mobile_android`, `desktop`, `browser_extension`, `voice` | yes | yes | yes |

`design` additionally proposes not-applicable whenever UX itself resolved to
not-applicable — there is nothing to style — and when every UX surface is
`cli` / `tui` (offer the light terminal aesthetic first; if declined, N/A).

A derived value is always `⚠ inferred` and always confirmed by the user before
it is written. The repo scan corroborates but does not decide: finding no UI
files is evidence, not proof.
