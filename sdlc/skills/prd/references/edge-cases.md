# Edge cases

Read this whenever the agent hits an unusual situation that doesn't fit
the happy path.

- **No project files found**: skip Phase 2; Phase 3 takes Branch B (cold
  idea capture). Phase 4 onward proceeds normally.
- **`docs/PRD.yaml` exists but no state file**: this is an update flow. Show
  `metadata.last_updated` and `metadata.status`, ask: "Run an update interview, or abort?"
- **Conflicting signals across scanned files** (e.g. README says
  "TypeScript" but `package.json` has no TS deps): surface the conflict
  during Phase 5 — do not silently pick one.
- **User skips a required field** during the interview: write `null` to
  the field, set `metadata.status = "draft"`, and add an informational
  entry to `prd_warnings`. The validator will surface the missing path on
  the next run.
- **Validation failure**: show field-level errors verbatim, list affected
  paths, offer via `AskUserQuestion`: "Fill in now, or accept draft status?"
  Re-run validation after re-entry.
- **User aborts mid-interview**: set `status: aborted`, write current
  `partial_answers`, confirm to user that state was saved before exiting.
  The PRD (if written) will have `metadata.status: draft`.
- **Very large projects (>500 readable files)**: limit scan to the
  priority list and tell the user what was skipped.
- **No write permission on `docs/PRD.yaml` or `CLAUDE.md`**: report the path
  and the OS error verbatim. Do not retry silently.
- **User wants to skip Phase 3 idea capture**: respected. They can type
  `ok` on Branch A or a one-word answer on Branch B. The interview
  proceeds normally; idea-extraction pre-fills will be sparse.
- **Resume with stale state** (canonical for every sdlc skill — the others
  point here): if the state file's `skill_version` is **older** than this
  skill's, **migrate it additively, in one state write, before the
  resume/restart/discard prompt** — never "warn and offer restart" as the
  default. A state file is progress bookkeeping; the output yaml holds the
  answers. Discarding a completed multi-theme interview for a version bump
  is the one outcome the recipe exists to prevent (seva-servant hand-migrated
  twice, ledger IMP-033). The recipe:
  1. Set `skill_version` to this file's footer value.
  2. Add every baseline key the current state contract defines that the
     file lacks, with its empty default: `metrics: {}`, `lesson_notes: []`,
     `finding_notes: []`, `input_adequacy: {}`, plus the optional slots this
     skill declares (`dropped_candidates: {}`, `delta_review`), and any
     skill-specific key the schema in SKILL.md lists. A key the file already
     has is never touched, whatever its shape.
  3. Touch nothing else: `partial_answers`, `completed_themes`,
     `skipped_themes`, `todo_themes`, `pending_themes`, `current_theme`,
     `last_ids*`, `session_id`, `started_at` stay byte-for-byte. Answers are
     not migrated here — the output yaml is authoritative for them, and a
     changed OUTPUT schema is Phase 7's merge to reconcile.
  4. Reconcile the theme lists against the current inventory: a
     `completed_themes` id the inventory no longer has moves to
     `retired_themes: []`; a required theme the inventory gained and the
     file lacks is appended to `pending_themes`.
  5. Append `migrations: [{from, to, at, added: [<keys>], retired_themes:
     [<ids>]}]` and bump `metrics.resumes`.
  6. Then offer the normal prompt with **resume at position 1**, saying in
     one line what the migration added.
  A key whose SHAPE changed between versions (not merely added) is the one
  case the recipe cannot do blind: the skill's CHANGELOG.md entry for that
  version says how; absent such an entry, treat the bump as additive. A state
  file NEWER than the skill (a downgrade) is the only case where "warn and
  offer a clean restart" remains the default.
- **Monorepo answer changes mid-flow**: if the user wants to switch from
  single → multi (or vice versa) after some themes have been answered,
  warn that this requires re-keying every answered field. Offer to
  restart or to keep answers and re-shape on write (Phase 7).
- **Hallucination guard violation attempt**: if the user tries to
  batch-accept `⚠ inferred` items without explicitly selecting or correcting,
  refuse and re-prompt. Each `⚠` item needs an explicit confirmation or
  correction. This applies to both Phase 5 pre-fill confirmation and the
  Phase 6 product_identity synthesis batch.
