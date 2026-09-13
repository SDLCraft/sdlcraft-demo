# SDLC findings — when a document in this project's `docs/` is wrong

Something in `docs/*.yaml` / `docs/TASKS*.json` is wrong — a contract that
does not determine the behaviour its consumers need, two documents that
contradict each other, a required section left null in a document stamped
`complete`, a task whose test was deferred, an acceptance nobody can satisfy —
and you noticed it while doing something else? That is a **finding** for
`/sdlc:repair`, and recording it is the AGENT's job: the user cannot know
this channel exists. Never fix it in place, never work around it unrecorded:

- **Capture, don't fix.** The document that *looks* wrong is usually a copy
  of the one that *is* wrong (a task embed, a test spec, a WRN in a
  downstream file); patching what you can reach re-diverges on the next
  regeneration while the real defect stays upstream. `/sdlc:repair` walks
  backwards to the source and fixes it there — that is its whole job.
- **How to record it** depends on whether an `/sdlc:*` skill run is in flight:
  - **No run in flight (ambient session):** run

    ```bash
    python .claude/sdlc/findings.py add --kind <kind> \
      --summary "<one line: what is wrong>" \
      --evidence "<the line that shows it>" [--evidence "..."] \
      [--file docs/<ARTIFACT>] [--symbol <work_unit|TST-NNN|Entity>] \
      [--field-path <dotted path>] [--suspected-stage <prd|ux|design|data|api|arch|test|task>]
    ```

    or, when you would rather describe it and let repair take it from there,
    `/sdlc:repair --flag "<reason>"`. `raised_by` is derived (`user` in an
    ambient session); the entry is validated before it lands, and a
    still-open twin is reported instead of duplicated.
  - **A run is in flight:** capture never ends, aborts, or pauses the run.
    Append one entry to the `finding_notes:` list in the running skill's state
    file (`.claude/skills-state/sdlc-<skill>.state.yaml`), say at most one
    line in chat, and continue the interrupted step; the run's close phase
    records it through the same helper.
- **Kinds** (`findings.py add --kind ...`): `contract_underdetermined`,
  `contract_contradiction`, `test_contradicts_contract`,
  `impossible_acceptance`, `unrealizable_item`, `missing_requirement`,
  `missing_operation`, `missing_entity`, `missing_dependency_edge`,
  `upstream_incomplete`, `drifted_embed`, `stale_downstream_claim`,
  `wrong_path`, `other`. A document merely *built against an older upstream*
  is not a finding — that is staleness, shown by `/sdlc:repair --check
  --provenance` and handled by re-running the owning skill.
- **Your guess at the owning stage is welcome and not binding** —
  `--suspected-stage` is a hint; `/sdlc:repair` localizes.
- A SKILL that misbehaved (its instructions, a question, a validator verdict
  the user says is wrong) is a **lesson**, not a finding — see
  `.claude/rules/sdlc-lessons.md`.
- Never hand-edit `.claude/skills-state/sdlc-findings.yaml`; `findings.py` is
  its only writer. Never edit a `docs/` artifact to make a finding go away.

Full doctrine: the sdlc plugin's `repair/FINDINGS.schema.yaml` (the entry
shape and every kind) and `repair/SKILL.md` (what repair does with it).
