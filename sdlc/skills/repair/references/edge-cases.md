# Edge cases (sdlc-repair)

The theme: **diagnosis degrades gracefully, edits never happen implicitly.**
This skill has write access to every artifact in the chain, which makes it the
one skill in the pipeline that can do real damage. Every unusual situation below
resolves toward "surface it and ask", not "make a reasonable guess".

## Inputs and preconditions

- **No findings queue and a clean sweep** → nothing to repair. Say so, print the
  sweep, and stop. This is a success, not an empty result: `/sdlc:repair --check`
  returning green is the whole point of having a doctor.
- **A findings queue that fails `validate_findings.py`** → refuse to edit
  anything. A corrupted queue means ids may be ambiguous, and appending or
  resolving against it can lose a finding. Show the validator's errors and offer
  to repair the queue file itself (that edit is in scope; artifact edits are not
  until it validates).
- **`docs/` absent or empty** → nothing to diagnose. Point at `/sdlc:prd`.
- **The project never ran `/sdlc:setup`** → no `docs/INDEX.yaml`, so no
  `--refs` blast radius, and no installed `findings.py` / `bump_artifact.py`
  / `docs_index.py` copies (use the plugin's own under
  `"${CLAUDE_SKILL_DIR}"` — the doctor already does for the dangling gate).
  Degrade to `crosscheck_artifacts.py` plus the per-symbol-class grep
  (SKILL.md Phase 2 table), say so at the confirmation gate, and record it in
  the resolution. Do not silently narrow the radius.
- **The located symbol is a NAME, not a corpus id** (an entity, a work_unit,
  an operation) → `--refs` returns nothing or only the canonical file, because
  the index does not yet follow names or scan shards. That is not "no inbound
  sites"; it is "the index cannot see them". Grep by symbol class, print the
  checklist from the grep, and say so in the resolution.
- **A validator or the crosscheck linter is missing from the skill tree**
  (partial install) → that check is *skipped*, never assumed green. A skipped
  check is reported as skipped in the sweep and never produces a finding.

## Localization

- **The walk terminates at `code`** → the finding was mis-raised: generated code
  is an output, never a source. Close it `wontfix` naming the reason, and treat
  the underlying red as a `failed` task for `/sdlc:code` to heal. The queue
  validator refuses `located_stage: code` outright on a version-2 queue.
- **`--flag` describes a defect an open finding already records** →
  `findings.py` reports the twin instead of minting a second id. Work the
  existing finding; tell the user which one.
- **The finding is a recurrence** (`recurrence_of` set) → read the earlier
  resolution before walking; the hop it never verified is usually the answer
  (`back-propagation.md` Step 5). Position 1 at the gate is `re-invoke`;
  `surgical` stays available.
- **The walk terminates nowhere** (every stage is internally consistent and the
  contradiction only exists between two of them) → the earliest stage that
  *should* have adjudicated is the source, which is usually `prd`. If PRD is
  genuinely silent, this is a product decision: ask, and record the answer as a
  new FR/NFR rather than as a downstream patch.
- **Two findings localize to the same symbol** → merge them: resolve one and
  mark the other `duplicate` with `duplicate_of`. Never fix the same symbol
  twice in one run; the second edit will be reasoning against a file the first
  already changed.
- **The finding's `suspected_stage` is right** → say so plainly and move on.
  Confirming the raiser's guess is a normal outcome; do not manufacture a
  more interesting localization to justify the walk.

## Editing

- **The source artifact has hand-edits nobody downstream has seen** → the
  Phase-2 `doctor.py --provenance` run already answered this: a `[stale]`
  line naming the source as the upstream of some downstream artifact means
  its content moved after that downstream was built (a hand-edit, or an
  earlier repair whose propagation never finished). The lines are in the
  state file's `provenance_drift`. Surface every such line for the artifact
  you are about to edit *before* editing; layering a repair on top of an
  unreviewed change produces a file neither party intended. Staleness itself
  is not a finding — the owning skill's delta-review is its channel — but it
  is a fact the confirmation gate must show.
- **The fix requires deleting an item** (an entity, a work_unit, a TST) → never
  delete implicitly. Deletion changes the *set* of downstream items, so it is a
  `re-invoke` case by definition, and it needs explicit approval naming what
  disappears and what currently references it.
- **The radius reaches an artifact that does not exist yet** (a repair to PRD
  while `api` has never run) → that is not a gap. Stages that have not run have
  nothing to reconcile; note them as "not yet authored" and exclude them from
  the radius.
- **A downstream artifact is `status: draft`** → repair it anyway, but say so:
  a draft artifact will be rewritten by its own skill, and the edit may not
  survive. Prefer `re-invoke` for draft stages.
- **Write-permission error mid-repair** → stop immediately, do not continue to
  the next finding. Report which artifacts were already edited and which were
  not: a half-propagated fix is the one state worse than an unfixed defect, and
  the user needs to know exactly where it stopped.

## Verification

- **A validator was already red before the repair** → record its before and
  after exit codes and state plainly that the pre-existing failure is unrelated.
  Never let an unrelated red be read as caused by the repair, and never claim a
  repair fixed something it did not touch.
- **The repair fixes the finding but breaks a coverage gate** (e.g. adding an FR
  leaves it traced by nothing) → that is an incomplete forward-propagation, not
  a validator problem. Either complete the propagation or declare the deferral
  **structurally** in the artifact that owes the coverage — its top-level
  `deferrals: [{id, reason}]` list where the skill has one (`task`), the
  `WRN-NNN` note only where no structured slot exists yet (CLAUDE.md §6 —
  trace or defer, never silent omission; a prose note is the human companion,
  not the machine channel).
- **`reslice_embeds.py --check` is still red after the re-slice** → an embed
  moved that the `--symbol` selector did not cover (a second task copies the
  same symbol under another selector, or an authored `fixture_briefs` /
  `config_keys` field the tool never rewrites). Re-slice by the selector it
  names; if the drift is in a field the tool refuses, that field's upstream is
  the source of a *second* finding, not a hand-patch.
- **`bump_artifact.py` refuses** (the on-disk version is above the newest
  changelog line) → somebody bumped without a line before you. Add the missing
  line by hand (newest first, canonical format), then re-run without
  `--force`. `--force` only when the changelog was repaired and the tool still
  cannot tell.
- **Verification cannot run** (missing pydantic, no python on PATH for a
  subprocess) → do not mark anything `resolved`. Leave the finding `open`, record
  what could not be verified in its `evidence` (the queue's bounded slot for
  partial progress), and say what the user should run. A surgical fix parked with
  a resolution block the queue validator refuses is exactly the defect this
  rule removed — only a re-invoke in progress may sit `triaged`.

## Session

- **EXIT mid-triage** → persist the state file with `status: aborted`, leave
  every unresolved finding as it was, and confirm which artifacts were already
  edited. Findings already resolved stay resolved — the queue is append-only and
  resolutions are audit records, not a transaction. Then drain `lesson_notes`
  (one `lessons.py add` per note that survives the self-review) and run
  `python .claude/sdlc/lessons.py record-run --skill repair --outcome aborted`
  (skip silently if the helper is absent) — an aborted run that records
  nothing is how a skill defect stays invisible.
- **A raising condition mid-run** (CLAUDE.md 15: an instruction gap you
  improvised past, a validator verdict the user says is wrong) → append it to
  the state file's `lesson_notes` in the next write and continue. Never stop
  the repair to record a lesson; Phase 6 drains the list.
- **Interrupted mid-repair** → on the next invocation, reconcile: for each
  finding left `open` whose `evidence` records partial progress, re-verify those
  artifacts against disk before continuing. Re-applying an edit that already
  landed is the common failure mode here.
- **A finding whose artifacts have changed since it was raised** → re-read
  before trusting the evidence. Evidence is a snapshot; the defect may already
  be gone, in which case close it `resolved` with `mode: none` and a note that
  it was fixed elsewhere.

## Boundaries

- This skill **never writes source code** and never touches the generated tree.
  Its output is artifacts under `docs/`, the findings queue, and its own state
  file.
- It **never runs another skill.** `re-invoke` mode prints a command sequence
  for the user; it does not execute one.
- It **never edits `.claude/skills-state/sdlc-code.state.yaml`.** That ledger
  belongs to `/sdlc:code`, and the `stale` handback works precisely because
  repair leaves it alone.
- `CLAUDE.md` is not touched: this skill owns no artifact and adds no pointer
  bullet.
