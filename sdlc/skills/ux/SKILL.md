---
name: ux
description: >
  Explicitly invoked skill. Creates or updates docs/UX.yaml plus one
  docs/UX__<surface>.yaml per UI surface, consumed by downstream coding
  agents (api → arch → test → task → deploy). A maintenance form,
  /sdlc:ux --reconcile, reviews only what moved in docs/PRD.yaml since the
  file was written, without the interview. Trigger only on /sdlc:ux
  or a direct natural-language request to start the UX surface skill —
  never auto-trigger from generic UI/design chatter.
user-invocable: true
disable-model-invocation: true
model: opus
effort: xhigh
allowed-tools: Read Write(docs/UX.yaml) Write(docs/UX__*.yaml) Write(.claude/skills-state/sdlc-ux.state.yaml) Bash Bash(ls *) Glob Grep AskUserQuestion
---

# sdlc-ux

Guides the user through a structured interview that produces a validated
`docs/UX.yaml` (global UX contract) plus one `docs/UX__<surface>.yaml`
per UI surface, so downstream AI agents have an unambiguous machine-
readable description of every screen, modal, panel, CLI command, or
flow step they need to implement.

## What this skill does (at a glance)

1. **Resume check** → load existing state if any.
2. **Scan + idea capture** → read `docs/PRD.yaml`, verify
   `metadata.status == "complete"`, run PRD's validator, exit early if
   the PRD isn't there or isn't complete. Build a pre-fill map from
   **every relevant PRD family** (WKF, FR, ENT, JTB), not just workflows.
3. **Structural questions** → confirm surface family
   (cli | web | mobile | desktop | tui | voice | service | library | mixed)
   derived from `PRD.technical_constraints.runtime_platform` — a LIST as of
   PRD schema 1.1; two or more families in it mean `mixed`.
4. **Pre-fill confirmation** → theme by theme, each `⚠ inferred` confirmed individually.
5. **Theme interview** → required themes always run; optional themes are
   gated now/skip/todo. Theme 4 (`surface_inventory`) and theme 11
   (`per_surface_deepdive`) run as `critical` per-item drill-downs —
   every surface is examined, assigned a stable `SCR-NNN` id, and traced
   back to PRD via `traces_workflows` / `implements_requirements` /
   `references_entities`. Theme 4 closes with a **dynamic scope-
   completeness sweep** (analogous to PRD's `features` sweep)
   that catches surfaces implied by FR/ENT/JTB ids but not by any WKF.
6. **Write & validate** → merge into `docs/UX.yaml` and write all
   `docs/UX__<surface>.yaml`, prefixing every `ux_warnings` entry with a
   stable `WRN-NNN`, then run `validate_schema.py` (schema + ID-prefix
   format + PRD WKF-### coverage).
7. **Refresh & close** → refresh `docs/INDEX.yaml` and the
   statusboard, mark state `complete`. This skill does not touch
   `CLAUDE.md`.

State is persisted **after every confirmed batch and after every
per-surface deep-dive**, so the user can `EXIT` at any time without
losing progress.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — the workflow itself. |
| `ux-questions.yaml` | Full question inventory grouped by theme. |
| `UX.schema.yaml` | Human-readable canonical schema for `docs/UX.yaml`. |
| `UX__SURFACE.schema.yaml` | Human-readable canonical schema for `docs/UX__<surface>.yaml`. |
| `validate_schema.py` | Pydantic v2 validator (UX.yaml + every UX__*.yaml + PRD coverage check). |
| `references/interview-mechanics.md` | AskUserQuestion batch format, EXIT handling, conditional promotions. Read on entering Phase 6. |
| `references/surface-discovery.md` | How to enumerate surfaces from PRD workflows, generate `surface_id`s, run the per-surface state machine. Read whenever theme 4 or 11 is active. |
| `references/cli-ux.md` | CLI-specific guidance — subcommand modelling, arg parsing, output formats, exit codes. Loaded only when `surface_family == "cli"`. |
| `references/merge-validate.md` | Merge logic for `UX.yaml` and surface yamls, the flow-coverage check, and the rule that this skill never writes CLAUDE.md. Read on entering Phase 7. |
| `references/edge-cases.md` | Unusual situations and how to handle them. |

Runtime files (NOT inside this skill directory):

| File | Purpose |
|---|---|
| `docs/UX.yaml` (project root) | Global UX contract consumed by downstream agents. |
| `docs/UX__<surface>.yaml` (project root) | One file per UI surface. `<surface>` is kebab-case. |
| `.claude/skills-state/sdlc-ux.state.yaml` | Session state for resumability. |

## Reserved EXIT command

At any prompt, the user can type `EXIT` (case-insensitive) into the
free-text field of any `AskUserQuestion` call to abort. State is saved
after every confirmed batch and after every per-surface deep-dive, so
progress is never lost — `EXIT` simply marks the session
`status: aborted` and stops.

There is no `SAVE` command — saving is implicit.

## Invocation dispatch

Classify `$ARGUMENTS`:

1. **Empty** → the full flow below (Phases 1–8). On a re-run it still runs the
   upstream-change review in Phase 2 before the interview.
2. **`--reconcile`** → the **reconcile form**: the upstream-change review of
   `docs/UX.yaml` and nothing else — no theme interview, no structural
   questions. Follow `references/upstream-reconciliation.md` → "The
   `--reconcile` form" (steps 1–8, and this skill's row in its specifics
   table), then Phases 7–8 below. A surface the review adds is authored
   through the per-surface drill (theme 11) into its own `UX__<surface>.yaml`;
   the downstream-claim check stays in the full flow. It needs a `complete`
   `docs/UX.yaml` — without one, name plain `/sdlc:ux` and abort.
3. **Anything else** → print the two forms above and abort.

## The 8-phase flow

### Phase 1 — Resume check

Before doing anything else, check for
`.claude/skills-state/sdlc-ux.state.yaml`:

- If it exists with `status: in_progress`, ask:
  > "I found an unfinished UX session from `<last_updated>`. Would you
  > like to **resume**, **restart** (discard previous answers), or
  > **discard** (delete state and exit)?"
- If `status: complete` or `aborted` and `docs/UX.yaml` exists, scope the
  update — see `references/upstream-reconciliation.md`'s REFINE row (open
  only the named themes, the §7 delta items, and the non-confirmed set;
  confirm the rest in one summary) — then `references/merge-validate.md`.
- If `status: complete` or `aborted` and `docs/UX.yaml` is ABSENT, only
  `partial_answers` survives: offer restart-from-partial_answers or
  discard — never resume.
- If no state file, continue to Phase 2.
- If the state file's `skill_version` is older than this file's footer: run
  the canonical recipe
  (`${CLAUDE_SKILL_DIR}/../prd/references/edge-cases.md` → "Resume with
  stale state" — migrate additively, reconcile the theme lists and
  `last_ids`, then offer resume at position 1).

### Phase 2 — Scan inputs

`sdlc:ux` does NOT re-interview anything that already lives in `docs/PRD.yaml`.

**Slice large docs, don't slurp.** If `docs/INDEX.yaml` exists (the project ran
`/sdlc:setup`), read `PRD.yaml` (often 1000+ lines) by slice: look an `FR-###`
or a top-level section up in `INDEX.yaml` (or `python .claude/sdlc/docs_index.py
--show <symbol>`) and `Read` only its `[start, end]` range, rather than loading
the whole PRD to pull a handful of workflows/features. Fall back to whole-file
reads when `INDEX.yaml` is absent. Protocol: `.claude/rules/sdlc-docs-access.md`.
Every `python .claude/sdlc/docs_index.py …` in this file runs the copy
`${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks once per
run: an installed copy older than the plugin's counts as absent, and every
fallback this file gives for a missing `docs_index.py` applies to it.

Read these files at startup:

1. **`docs/PRD.yaml`** — required. Run the PRD validator first:

   ```bash
   python "${CLAUDE_SKILL_DIR}/../prd/validate_schema.py" --path docs/PRD.yaml
   ```

   - If exit code ≠ 0 or `metadata.status != "complete"` → stop. Print
     a clear warning telling the user to complete the PRD first
     (`/sdlc:prd`). Do not proceed. One exception, for the exit code only:
     when `python "${CLAUDE_SKILL_DIR}/../repair/doctor.py" --docs-dir docs --artifact docs/PRD.yaml`
     reports the check `accepted (N, unchanged)`, the project accepted that
     deviance — proceed (never `--quick`; rule:
     `${CLAUDE_SKILL_DIR}/../repair/references/accepted-deviance.md`).
   - If valid and complete → extract the fields the UX skill needs:
     - `technical_constraints.runtime_platform` → preliminary `surface_family`
       (a LIST as of PRD 1.1, e.g. `[mobile_ios, mobile_android]`; a bare
       scalar is the legacy 1.0 form — treat it as a one-element list)
     - `technical_constraints.framework` → preliminary component-library hint
     - `non_functional_requirements.accessibility` → preliminary WCAG target
       (`not_applicable_cli` maps straight onto UX's own value)
     - `internationalization.{enabled, default_locale, target_locales,
       rtl_support}` (PRD 1.1) → the same-named `localisation.*` fields,
       tagged `✓ found`; `enabled: true` promotes the `localisation` theme
       gate to "now"
     - `glossary.terms` (PRD 1.1) → the vocabulary every label, copy string
       and command name must reuse verbatim (`✓ found`; the synonyms are the
       words to avoid)
     - `use_cases.core_workflows` (WKF-###) → primary seed for surface inventory
     - `functional_requirements.features` (FR-###) → seed for
       feature-driven surfaces (verbs/screens that implement a specific FR).
       One flat list post-D2 (legacy PRDs may still carry a must/nice split;
       the loader unions them)
     - `data_model.key_entities` (ENT-###) → seed for entity-driven
       surfaces (CRUD screens, list/detail/registry views, e.g. a
       `ProjectRegistry` entity implies a `list` command)
     - `use_cases.primary_jobs_to_be_done` and `secondary_jobs` (JTB-###)
       → orthogonal lens consulted during the scope-completeness sweep
     - `users_personas.expertise_level` → tone hint
     - `product_identity.name`, `product_identity.one_liner`,
       `product_identity.slug` → context + CLI root_command pre-fill
     - `conventions.artifact_ids` (if present) → the binding ID-family
       map. The UX skill respects every family listed and never invents
       IDs in an upstream family.
     - `metadata.monorepo` + `products: <slug>:` → if true, the UX skill
       runs the interview **per product** and writes one `UX.yaml` per
       product slug. (See `references/edge-cases.md` — monorepo mode.)

2. Existing `docs/UX.yaml` and `docs/UX__*.yaml` — if present, treat as
   the merge baseline (Phase 7).

3. Optional context files at project root: `README*`, design notes
   under `docs/design/`, `docs/wireframes/`, any `*ux*.md`, `*flow*.md`.
   Quote findings in pre-fill rationale.

Build the pre-fill map exactly as `sdlc:prd` does, classifying each
candidate as `✓ found` (direct PRD/file value) or `⚠ inferred` (derived).
While building it, note every schema-REQUIRED PRD field that is null or
empty although the PRD claims `complete`: append one
`{noted_at, kind_guess: upstream_incomplete, file: docs/PRD.yaml, summary,
evidence}` entry to `state.finding_notes` (summary MUST start
`docs/PRD.yaml <field.path>:`) and continue — capture never interrupts the
run; Phase 8 drains the list (CLAUDE.md §13).

**Input-adequacy gate (ask, never block).** After the scan, collect what is
known to be unsettled in the inputs:

1. Open findings: `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" list
   --open` (or read `.claude/skills-state/sdlc-findings.yaml` directly; skip
   silently when neither exists).
2. PRD `open_questions` entries (`undecided_decisions` + `parking_lot`) with
   `status: open` whose `blocks:` names an id this skill consumes
   (WKF/FR/NFR/ENT/JTB).

When the combined list is non-empty, ask ONE `AskUserQuestion`: continue
anyway, or stop and run `/sdlc:repair` (findings) / `/sdlc:prd` (open
questions) first. Record the decision in state under
`input_adequacy: {checked_at, open_ids, decision}` so a resume does not
re-ask.

**Findings owed to this run are not gate items.** A triaged re-invoke finding
that `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" list --owed-by
docs/UX.yaml` returns is waiting on this very run — its owed re-run is what you
are doing. Leave it out of the question and read it as the reason for the
change: its `fix` and `handoff` notes (canonical:
`references/upstream-reconciliation.md` → "The `--reconcile` form", step 3).

**Blast radius before dropping ids.** Before an update session drops or
renames an emitted `SCR-NNN`, check its inbound references:
`python .claude/sdlc/docs_index.py --refs <id>` (skip when the helper is
absent) — every site the report names must be reconciled in the same pass.

**Upstream-change detection (re-runs).** If `docs/UX.yaml` already exists and
carries `metadata.upstream_provenance`, this is a re-run: before deciding
refine-vs-reconcile, run

```bash
python .claude/sdlc/docs_index.py --drift docs/UX.yaml
```

Exit 1 means `docs/PRD.yaml` moved: run the **delta-review pass before the
theme interview** per `references/upstream-reconciliation.md` (CLAUDE.md §7) —
the report's per-family added/removed/changed lines are the classification
input. **Every added FR / ENT goes through `references/surface-discovery.md`
Step 1b/1c before its incorporate / ignore / defer prompt** — its text may
name a `<root_command> <verb>` or a screen, and that candidate is the prompt's
position-1 option; a `defer` for such an item needs a reason that names the
command, and an `incorporate` needs a surface that actually runs it — folding
the FR into a surface that runs some other command silences the command just
as a deferral does (the validator warns `[FR names a command]` for either).
Exit 0 means PRD is unchanged: an ordinary refine — proceed to the merge flow
without a delta-review. Helper absent (the project generates its index with
its own tool): run the plugin's copy,
`python "${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs --drift docs/UX.yaml`
(read-only; the same copy stamps at write time). Only when neither can run,
compare the recorded `sha256` to PRD's current hash
(`docs/INDEX.yaml.generated_from[PRD.yaml]`, or `docs_index.py --hash
docs/PRD.yaml`, else the text-level hash
`sha256(read_text(encoding='utf-8').encode()).hexdigest()[:16]` — never raw
bytes). Fresh runs (no prior `docs/UX.yaml`) skip this step. Track the
review's progress in the `delta_review` state slot (canonical shape:
`references/upstream-reconciliation.md`).

**Downstream-claim reconciliation (re-runs).** Upstream isn't the only thing
that moves under a UX artifact — downstream does too, and surface `status` is
lifecycle metadata that must track it. On every re-run over an existing
`docs/UX.yaml`, peek at the downstream artifacts if present:

1. Collect the claimed surface set: every `surface_id` in any
   `docs/ARCH.yaml.containers[].owns_ux_surfaces` (and, where drilled, the
   matching `ARCH__*.yaml.ux_surface` lists).
2. For each claimed surface whose inventory `status` is not `confirmed`
   (still `proposed` / `defined` / `draft`), run one consolidated
   `AskUserQuestion` sweep: *"These surfaces are claimed by the architecture
   (and may already be tested) but UX still marks them `<status>`: …"* — per
   surface the user picks **confirm** (bump `status: confirmed`; if it was
   `proposed`, it has evidently been promoted into scope) / **keep — the
   downstream claim is premature or wrong**: append a
   `{noted_at, kind_guess: stale_downstream_claim, file: docs/ARCH.yaml,
   summary, evidence}` entry to `state.finding_notes` so `/sdlc:repair`
   fixes the ARCH claim (never a `WRN` about another artifact —
   CLAUDE.md §13) / **drop the claim note** (user will fix ARCH by hand).
3. Never bump silently — the mismatch may mean ARCH is wrong, not UX.

The ux validator surfaces the same mismatch as a standing non-blocking
warning ("claimed downstream but not 'confirmed'"), so a stale lifecycle
can't hide between re-runs. Skip the sweep when no downstream artifact
exists yet (the normal first-chain pass).

### Phase 3 (first step) — Repo evidence

```bash
python .claude/sdlc/repo_scan.py --domain ux --json
```

Finding **no** signal at all is itself evidence: it corroborates (never proves)
a not-applicable answer to Phase 4 question 0.

Full rules, including what to do when the repo contradicts an upstream
artifact: `${CLAUDE_SKILL_DIR}/../setup/references/repo-evidence.md`.

### Phase 3 — Idea capture (lightweight)

Unlike `sdlc:prd`, this skill does NOT need to capture a free-text idea
brief — the PRD's `product_identity.idea_text` already serves that role.
Quote it back briefly so the user knows the context you're working with:

> "Working from `docs/PRD.yaml`. Product: `<name>` — `<one_liner>`.
> Runtime platform(s): `<runtime_platform list>`. PRD lists `<N>` core workflows.
> Starting the UX interview. Type anything to add framing context, or
> `ok` to proceed."

If the user types extra context, store it verbatim in `state.idea_text`
(used as additional pre-fill signal — never overwrites PRD).

### Phase 4 — Structural questions

These determine the *shape* of the UX output:

0. **Does this project have a user-facing surface at all?** Ask this FIRST,
   before the surface family — a headless ETL, batch job, data pipeline or
   pure library has no surfaces to enumerate, and running the whole interview
   to discover that wastes the user's time.

   Propose an answer, never ask cold. Recommend **no** when
   `PRD.technical_constraints.runtime_platform` holds only
   `service` / `library` / `embedded`, when `PRD.pipeline_scope.ux.applicable`
   is already `false` (the user said so during `/sdlc:prd` — confirm rather
   than re-litigate), or when the Phase-2 repo scan found no arg parser, route
   file, template or component library. Recommend **yes** otherwise. Surface it
   as `⚠ inferred` at position 1.

   > "Does this project have any user-facing surface — screens, commands, or a
   > public API of its own that people interact with directly? A headless
   > pipeline or an internal library usually does not."

   On **yes** → continue to question 1 as normal.

   On **no** → capture a one-sentence rationale and take the **not-applicable
   path**: write `docs/UX.yaml` with `metadata.status: complete`,
   `metadata.applicability: not_applicable`, that rationale,
   `applicability_confidence: confirmed`, `surface_family: null` and an empty
   `surface_inventory`; write no `UX__*.yaml`; **skip straight to Phase 7**.
   The validator requires the rationale and rejects a not-applicable file that
   still lists surfaces. Mechanics:
   `${CLAUDE_SKILL_DIR}/../prd/references/optional-stages.md`.

   Do NOT confuse this with the headless surface families below. `service` and
   `library` mean "headless, but its commands / endpoints / public symbols are
   still worth specifying"; not-applicable means "do not model surfaces at
   all". When the platform list says `service` or `library`, offer both and let
   the user choose — the minimal headless spec is often the more useful answer.

1. **Surface family** — derived from
   `PRD.technical_constraints.runtime_platform`, which is a LIST of every
   platform the product ships on (PRD 1.1; a legacy scalar is a one-element
   list). Map each value, then reduce:
   - `cli` → `cli`; `tui` → `tui`; `web` → `web`; `desktop` → `desktop`
   - `mobile_ios | mobile_android` → `mobile` (both together are still ONE
     family)
   - `voice` → `voice`; `service` → `service`; `library` → `library`
     (the last two are headless — take them as-is, no screens)
   - `server | embedded | browser_extension | other | undecided` → ask the
     user which family that platform presents (a `server` is usually
     `service` plus whatever frontend it serves → `mixed`).
   - Reduce the mapped set: one distinct family → that family; two or more
     → `mixed` (e.g. `[web, cli]` → a web app + a CLI companion).
   - Always surface as `⚠ inferred` position-1 option; user must
     confirm or pick another.

2. **(only if `mixed`)** Which surface families? (multi-select from the
   nine families — pre-tick the ones the platform list mapped to)

3. **(only if `web` or `mixed-including-web`)** Device targets
   (desktop, tablet, mobile) and viewport breakpoints. Pre-fill from
   common defaults; user confirms.

4. **(only if `cli` or `mixed-including-cli`)** Promote theme
   `cli_specifics` to required for that surface family.

Persist these to state under `surface_family:`, `surface_family_members:`,
`device_targets:`, `viewport_breakpoints:` before proceeding.

### Phase 5 — Pre-fill confirmation

Present the pre-fill map **theme by theme**. Same rules as `sdlc:prd`:

- `✓ found` items can be batch-accepted with `ok`.
- `⚠ inferred` items must be confirmed or corrected one by one. No
  batch-acceptance. **This is the hallucination guard.**

Write confirmed values to state with the right `_confidence` value:
`confirmed` (explicit pick or typed answer) or `inferred` (`⚠` accepted
as-is).

### Phase 6 — Theme interview

Walk the themes in this order (canonical order from `ux-questions.yaml`):

1. `platform_and_shell` — required.
2. `design_principles` — required.
3. `navigation_model` — required.
4. **`surface_inventory`** — required, `synthesis: true`. CRITICAL tier.
   Per-item drill-down (see `references/surface-discovery.md`). Build the
   inventory of surfaces and trace each to PRD `use_cases.core_workflows`.
5. `component_library` — required.
6. `state_patterns` — required.
7. `content_rules` — required.
8. `accessibility` — required.
9. `localisation` — optional (now/skip/todo gate).
10. **`cli_specifics`** — `required_if: surface_family in ['cli', 'mixed']`.
11. **`per_surface_deepdive`** — required, `synthesis: true`. CRITICAL tier.
    For each surface defined in theme 4, run a per-surface mini-interview
    that fills out the surface yaml (layout, states, interactions,
    components, validation, accessibility, `traces_prd_flows`).

Required questions can never be `todo`'d. They must be answered, set to
`null` (writing a note to `ux_warnings`), or the user must `EXIT`.

After all themes are addressed, set `suggestion_phase_done: true` in state.

#### Within a theme: tiered question flow

Same tier mechanics as `sdlc:prd` — see
`references/interview-mechanics.md` for batch format and
`references/surface-discovery.md` for the `critical` per-surface state
machine.

Tier assignments (set in `ux-questions.yaml`):

- Theme 4 (`surface_inventory`) → `critical` per item — every surface
  is examined, named, typed, assigned the next `SCR-NNN` id, and traced
  to PRD via `traces_workflows`. **After the per-item loop closes, a
  dynamic scope-completeness sweep runs** over every upstream PRD family
  (WKF, FR, ENT, JTB) plus project-type heuristics to catch missed
  surfaces. See `references/surface-discovery.md`.
- Theme 11 (`per_surface_deepdive`) → `critical` per surface — for each
  surface, run the full per-surface mini-interview (layout / states /
  interactions / components / validation / accessibility /
  traces_workflows). `implements_requirements` (FR-###) and
  `references_entities` (ENT-###) are inferred by the agent from the
  surface's purpose and presented in the final-approval draft for the
  user to correct.
- Themes 2, 3, 5, 7 → mostly `high` (agent drafts; user iterates).
- Remainder → `med` (batched 2–4 per `AskUserQuestion` call).

**Read `references/surface-discovery.md` before running theme 4 or 11.**
**Read `references/cli-ux.md` before running theme 10.**

The two non-negotiable rules in this phase:

1. `⚠ inferred` candidates surface as the **position-1 recommended option**
   in their `AskUserQuestion` call. They cannot be silently accepted —
   the user must explicitly pick or correct.
2. State is written after **every confirmed batch, every mini-section,
   and every per-surface deep-dive completion**.

#### Conditional promotions (`required_if`)

Some questions in `ux-questions.yaml` are conditionally required:

| Question / theme | Becomes required when |
|---|---|
| `cli_specifics` (entire theme) | `surface_family in ['cli', 'mixed']` |
| `device_targets`, `viewport_breakpoints` | `surface_family in ['web', 'mobile', 'desktop', 'mixed']` |
| `localisation.framework` | `localisation.enabled == true` |

Re-evaluate at the start of each new theme batch.

### Phase 7 — Write & validate

Write or merge `docs/UX.yaml` and write every `docs/UX__<surface>.yaml`
in one consistent batch (so that the surface inventory and the per-
surface files always agree).

Writer responsibilities for the new ID conventions:

- Every entry appended to `ux_warnings` is prefixed `"WRN-NNN: <message>"`,
  using and persisting `state.last_ids.WRN`.
- A PRD FR that deliberately gets no surface is deferred **structurally**: a
  top-level `deferrals: [{id, reason}]` entry (per product in monorepo mode).
  An entry with no reason defers nothing. A prose `ux_warnings` mention still
  counts for one more version but is reported as deprecated; keep the WRN as
  the human-readable companion, not the machine channel (CLAUDE.md §6).
- Every surface in `surface_inventory` carries its stable `id: SCR-NNN`
  (assigned in theme 4; persisted in `state.last_ids.SCR`).
- The corresponding `docs/UX__<surface_id>.yaml` mirrors the same
  `id: SCR-NNN`.
- All PRD references — in `traces_workflows`, `implements_requirements`,
  `references_entities`, and `cli.exit_codes[code].implements_requirements`
  — are stored as **ID strings only** (e.g. `"WKF-001"`), never as
  verbatim text. The validator's coverage check matches by id.
- `metadata.changelog`: when running in update mode (existing UX.yaml on
  disk), prepend one entry describing the material change, format
  `"<version> (<YYYY-MM-DD>): <one-line summary>"`. Append-only — never
  rewrite existing entries.
- `metadata.upstream_provenance`: stamped by the helper after the write —
  `python .claude/sdlc/docs_index.py --stamp docs/UX.yaml --upstream
  docs/PRD.yaml` (the plugin's copy, `"${CLAUDE_SKILL_DIR}/../setup/docs_index.py"
  --docs-dir docs`, when the project has none; `--reconcile` step 7 already
  does this). It writes `{file, session_id, last_updated, sha256, items}`; the
  `items` map is what lets the next `--drift` name the delta item by item, and
  a hand-written `{file, sha256}` entry is a sha-only stamp `--stale` warns
  about. Replace-on-write, so it always reflects the latest
  write. See CLAUDE.md §7.

Then run:

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/UX.yaml
```

The validator walks `docs/UX__*.yaml` siblings, enforces ID-prefix
formats (SCR/WRN/WKF/FR/ENT), and runs the **PRD WKF-NNN coverage check**:
every WKF-NNN parsed out of `PRD.use_cases.core_workflows` must be
referenced by at least one `UX__<surface>.yaml` via `traces_workflows`.
Any uncovered id is appended to `UX.yaml`'s `ux_warnings` (as a fresh
`WRN-NNN: coverage: WKF-XYZ has no surface trace` entry) and forces
`status: draft`.

For full merge logic and the exit-code recovery flow, see
`references/merge-validate.md`.

When writing files: inline YAML comments on top-level keys, updated
`metadata.last_updated` and `metadata.session_id`.

Set `metadata.status`:
- `"complete"` — only when all required fields are filled, the validator
  passes with `[OK]`, AND the coverage check passes.
- `"draft"` — on early EXIT, when any required field is null, or when
  coverage is incomplete.

### Phase 8 — Refresh & complete

**This skill does not write `CLAUDE.md`.** That file is owned by `/sdlc:setup`,
which writes one static `## SDLC Documents` block. A caveat belongs in this
artifact's own `WRN-NNN` list, a spec defect in the findings queue, a skill
defect in the lessons queue — never as a note, a bullet or a "resolved" section
in `CLAUDE.md`. See `references/merge-validate.md`.

**Refresh the navigation index.** Resolve the copy per `helper-resolution.md`:
the installed `.claude/sdlc/docs_index.py` if present, run it after writing
`docs/UX.yaml` and its per-surface files; own-toolchain (marker present, no
`docs_index` helper) → run the project's own docs-hook command from
`.claude/settings.json` and name it; no marker → nothing to run. Optionally
run `python .claude/sdlc/docs_index.py --check` to confirm the write
introduced no dangling id references (skip when the helper is absent).
Phase 7's write already refreshed `metadata.upstream_provenance`, so the next
run's drift check starts from this write.

**Refresh the statusboard.** Run `python .claude/sdlc/statusboard.py` in the
same breath. It regenerates `.claude/rules/sdlc-statusboard.md` (loaded into
every session) and `.claude/sdlc/STATUS.md` from the artifacts, so this run's
new warnings, deferrals and open questions are visible to the next agent
without anyone writing them down by hand. Harmless no-op if it is not installed.

Then: set `status: complete` in the state
file (keep the file — audit trail), tell the user where the artifacts live,
and point at what comes next:

**Self-review & record the run** (CLAUDE.md 15; doctrine and the self-review
questions: `${CLAUDE_SKILL_DIR}/../lesson/references/lessons-capture.md` → "Mid-run:
note now, record at close"). Drain `state.lesson_notes`, answer the self-review for
this run (at most 2 `lessons.py add` per run unless one is a `blocker`; drained
notes count toward the cap), then `python .claude/sdlc/lessons.py record-run --skill ux --plugin-root "${CLAUDE_SKILL_DIR}/../.."`
— best-effort: a non-zero exit is one `Attention:` clause; helper absent, skip silently.

**Drain the findings notes** (CLAUDE.md 13). For each `state.finding_notes`
entry (user picks at the stale-ref / downstream-claim / delta-review prompts,
plus the Phase-2 `upstream_incomplete` notes), record one finding:

```bash
python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add --raised-by sdlc-ux \
  --kind <kind_guess> --summary "<summary>" --evidence "<evidence>" \
  --file <file> --detected-by sdlc-ux
```

Cap 3 per run unless one is blocking; skip silently when the script is absent
(keep the notes in state for a later run). `upstream_incomplete` summaries
start `docs/PRD.yaml <field.path>:` so the (detected_by, summary) dedupe
lands each defect once across runs. Mid-run the agent NEVER stops to record —
notes ride the normal state writes; this drain (also run on EXIT) is the only
place they become findings.

**Commit the run** (CLAUDE.md 20; the message rules and what is staged:
`${CLAUDE_SKILL_DIR}/../setup/references/auto-commit.md`) — the last action before the card, on every exit path, never a blocker:
`python .claude/sdlc/autocommit.py commit --skill ux --invocation "<the form the dispatch resolved, as typed>" --summary "<one line: what changed, in the user's words>"`
Its one printed line is the card's `Commit:` row; off, or helper absent → no row.

**Close with the card** (CLAUDE.md 14; canonical shape:
`${CLAUDE_SKILL_DIR}/../prd/references/reporting-to-the-user.md`). The user reading this
knows only "there is a pipeline and I run it in order", so answer their three
questions and nothing else: did it work, can I run the next skill, what do I
type next.

```
-- /sdlc:ux - what you have now ---------------------
Wrote:     docs/UX.yaml + docs/UX__*.yaml ({the one count that matters})
Status:    complete - /sdlc:design can run it
Attention: {what needs a decision, in the user's words}
Findings:  {N recorded (FND-011, ...) -> /sdlc:repair — only when any exist}
Commit:    {a1b2c3d  /sdlc:ux → <summary> | nothing to commit | not committed - <reason> — only when auto-commit is on}
Next:      {the computed next invocation}   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript.
```

**Compute the `Next:` row; never copy the example.** Procedure and successor
map: `${CLAUDE_SKILL_DIR}/../prd/references/reporting-to-the-user.md`
(CLAUDE.md 14). For `/sdlc:ux` it resolves to:

- **`docs/` artifact is `draft`, the user typed `EXIT`, or the validator is not
  green** → `Next:` is `/sdlc:ux` again, and `Status:` says what finishing
  means. Never hand off an unfinished artifact.
- **This run recorded findings, or open findings name `docs/PRD.yaml` or this
  artifact** → `/sdlc:repair` (name the ids) before the successor.
- **Complete, green, no open findings** → `/sdlc:design` is the pipeline
  successor and always the successor here — `ux` is not sharded.


Rules: omit any row with nothing to say (never write "no warnings"). Add a
`Lessons:` row only when this run recorded at least one — e.g. `Lessons: 1
recorded (LSN-NNN) - about this skill, for its maintainer; nothing for you to
do` — and never print "no lessons". Add the `Findings:` row only when this
run recorded findings (the drain above) or open findings name an artifact
this skill consumed — ids plus one consequence clause; never print "no
findings".
**`Attention:` is translated, never pasted validator output** - turn each
finding into what happened, why it matters, and what to do. If the validator
printed nothing worth acting on, drop the row.

The card above is a *shape* and its `Next:` literal an example — the row is
computed by the procedure every run, never copied through.

## Session state file

Path: `.claude/skills-state/sdlc-ux.state.yaml`

Schema (extends the baseline state schema from CLAUDE.md):

```yaml
session_id: <uuid4 string>
skill_version: <the skill_version at the end of this file>
started_at: <iso8601>
last_updated: <iso8601>
status: in_progress  # in_progress | complete | aborted

# Phase 4 — structural answers (mirror UX.yaml top-level)
surface_family: null        # cli | web | mobile | desktop | tui | voice | service | library | mixed
surface_family_members: []  # populated only when surface_family == "mixed"
device_targets: []
viewport_breakpoints: []

idea_text: null             # optional extra context user typed in Phase 3
pre_fill_confirmed: false
suggestion_phase_done: false
completed_themes: []
skipped_themes: []
todo_themes: []
pending_themes: []
current_theme: null
current_surface: null       # which SCR-NNN is mid-deepdive (theme 11)

# Phase 2 gates (CLAUDE.md 7/13) — written once, so resume does not re-ask
input_adequacy: null        # {checked_at, open_ids: [], decision: continue|stop}
delta_review:               # section-7 review progress; canonical shape:
  upstreams: []             #   references/upstream-reconciliation.md
  decisions: []             #   ("The delta-review state slot")
  unresolved: []

# Mid-run capture scratch lists (CLAUDE.md 15/13) — appended in the normal
# state write, NEVER by interrupting the run; both drained at Phase 8 and on
# EXIT before aborting.
lesson_notes: []            # {noted_at, about, kind_guess, note}
finding_notes: []           # {noted_at, kind_guess, file, summary, evidence}

# Per-family ID counters (single-product mode). Each entry is the last-
# assigned integer for that family — increment, format as <PREFIX>-{:03d},
# then persist. Families this skill emits:
#   SCR — surface inventory ids (writer-managed; assigned when a surface
#         candidate is accepted in theme 4 step a, or accepted from the
#         scope-completeness sweep in theme 4 step e).
#   WRN — ux_warnings entries (writer-managed; assigned at write time).
last_ids: {}                # e.g. {SCR: 9, WRN: 11}

# Per-product ID counters (monorepo mode only). Same shape as last_ids,
# keyed by product slug. Each product carries an independent SCR/WRN space.
last_ids_by_product: {}     # e.g. {auth: {SCR: 3, WRN: 1}, billing: {SCR: 5}}

# Surface registry — one entry per defined surface
defined_surfaces:           # extension over the baseline state schema
  - id: <SCR-NNN>            # stable id assigned in theme 4
    surface_id: <kebab>      # slug; may be renamed by the user — id stays
    surface_type: <enum>     # screen | modal | panel | cli_command | flow_step | …
    status: defined          # defined | draft | confirmed
    file_path: docs/UX__<slug>.yaml
    traces_workflows: []     # WKF-NNN ids; filled during theme 4/11
    implements_requirements: []  # FR-NNN ids (optional; inferred during deepdive)
    references_entities: []      # ENT-NNN ids (optional; inferred during deepdive)

# Sweep state — tracks scope-completeness sweep passes for theme 4
sweep_passes_done: 0        # 0 | 1 | 2; capped at 2 per importance-flows.md
dropped_candidates: {}      # {<schema_path>: [{candidate, seeded_from, reason, at}]}
                            # — candidates the user explicitly dropped; not
                            # re-proposed on resume. Supersedes the flat
                            # dropped_surface_candidates list (still read on
                            # resume for one version).

# Run telemetry (CLAUDE.md 15) — updated in the same write as everything
# else; consumed only by `lessons.py record-run` at close.
metrics: {}                 # questions_asked, free_text_answers,
                            # free_text_by_question{<question-id>: n},
                            # validator_runs, validator_failures, resumes

partial_answers: {}         # mirrors UX.yaml structure incrementally
partial_surfaces: {}        # mirrors per-surface yamls incrementally,
                            # keyed by SCR-NNN (stable across renames)
```

Rules:

- Generate `session_id` as a UUID4 on first creation.
- Update `last_updated` on every write.
- Write the file **after every confirmed batch** and **after every
  per-surface deep-dive completion**.
- The `metrics` counters (schema above) update in the same write: a batch
  bumps `questions_asked`; an Other/free-text answer bumps `free_text_answers`
  and `free_text_by_question[<question-id>]`; a resume bumps `resumes`
  (Phase 1); Phase 7 counts `validator_runs`/`validator_failures`.
- On user `EXIT`: set `status: aborted`, write current `partial_answers`
  and `partial_surfaces`, drain `lesson_notes` (CLAUDE.md 15) and
  `finding_notes` (the Phase 8 drain, CLAUDE.md 13), run
  `python .claude/sdlc/lessons.py record-run --skill ux --outcome aborted`
  (skip silently if the helper is absent), confirm to user, stop.
- On Phase 8 completion: set `status: complete`, keep the file.
- The validator ignores this file — it validates only `docs/UX.yaml`
  and the surface yamls.

**Source of truth on resume:**

- `docs/UX.yaml` + the existing `docs/UX__*.yaml` files (if present)
  are the on-disk source of truth for *answers*.
- The state file is the source of truth for *interview progress*.
- On resume: load the on-disk yamls first as the baseline, then layer
  `partial_answers` and `partial_surfaces` on top.
- If they conflict on the same key, ask the user which to keep —
  never silently overwrite.

## Edge cases

For unusual situations (PRD missing or in draft state, surfaceless PRD
workflow, conflicting design decisions across surfaces, mid-interview
platform change, deleted PRD workflows mid-session, validation
failures, write-permission errors, monorepo mode) →
`references/edge-cases.md`.

## Style of conversation

The interview can be long, especially for products with many surfaces.
Keep it humane:

- Use the user's terminology as soon as they introduce it.
- Keep `AskUserQuestion` batches to 2–4 questions; never more than 4.
- Acknowledge progress at each theme boundary
  (*"Navigation done — next: surface inventory, ~6 surfaces drawn from
  the PRD workflows."*).
- For theme 11 (per-surface deep-dive), announce each surface before
  diving in (*"Now: `surface-id` (cli_command). 4 questions."*).
- Always make multiple-choice the path of least resistance.
- For the `surface_inventory` and `per_surface_deepdive` themes,
  explicitly call out that candidates were synthesized from the PRD —
  don't pretend they came from nowhere.
- After all themes are done, congratulate the user briefly and move to
  write/validate. Do not repeat everything back at them.
  (This is about the INTERVIEW. The Phase-8 close report is separate and
  is NOT optional — see the card in Phase 8.)

## Quick reference: commands the user can type

| User input | Effect |
|---|---|
| `EXIT` | Abort: type into the free-text field of any AskUserQuestion call. |
| `confirm` | Accept a single inferred pre-fill (Phase 5). |
| `ok` | Batch-accept all `✓ found` pre-fills in the current theme, OR accept the Phase 3 framing summary. |
| `now` | Run the proposed optional theme (gate question). |
| `skip` | Skip the proposed optional theme (gate question). |
| `todo` | Defer the proposed optional theme; logs it to `ux_warnings`. |

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.23"