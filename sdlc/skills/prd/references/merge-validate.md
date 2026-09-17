# Merging, validating, and closing out

Detailed rules for Phase 7 (write & validate) and Phase 8 (refresh & close). Read this when entering Phase 7.

## Merging into an existing PRD.yaml

If `docs/PRD.yaml` already exists at the project root:

- Load it as the baseline.
- Merge the session's confirmed answers on top:
  - **Keys present in both** — overwrite *only* if the user changed the
    value during this session. Otherwise keep the existing value.
  - **New keys** — add them.
  - **Keys the session would remove** (rare; only if the user explicitly
    cleared a value) — ask the user to confirm before deleting.

If the user manually edited `docs/PRD.yaml` between sessions and the state file
disagrees on a specific key, surface the conflict — do NOT silently pick
one:

> "Conflict on `<key>`:
>   PRD.yaml has: `<a>`
>   Interview state has: `<b>` (set at <timestamp>)
> Which should I keep?"

Always preserve **unrelated keys** in `PRD.yaml` even if you don't know
what they are. The validator's `extra="allow"` config means custom keys
are tolerated.

## Writing the file

Write `docs/PRD.yaml` with:

- Inline YAML comments on each top-level key (use `PRD.schema.yaml` as a
  template).
- Updated `metadata.last_updated` (ISO-8601 UTC) and `metadata.session_id`.
- `metadata.prd_version`: stamp `"2.0"` (or higher) on new writes — the
  version-gated blocking checks (the legacy-shape floor, the item-shape
  floor — CLAUDE.md section 10) arm only at/after 2.0; an older stamp
  silently degrades both to warnings instead of dead code nothing ever
  reaches. The update flow on an existing artifact bumps the minor number
  and never crosses a floor by itself.
- `metadata.status`:
  - Set to `"complete"` only when **all required fields are filled** and
    the validator passes with `[OK]`.
  - Set to `"draft"` on early EXIT or when any required field is still null.
- `prd_warnings`: informational notes (low-confidence answers, merge
  conflicts, etc.) — not used for required-field acknowledgement.

## Running the validator

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/PRD.yaml
```

Exit codes:

| Code | Meaning | What the agent does |
|---|---|---|
| 0 (`[OK]`) | Complete and valid | ✓ Proceed to Phase 8. |
| 0 (`[DRAFT]`) | Draft — structurally valid, possibly missing required fields | Inform user and proceed to Phase 8. |
| 1 (`[FAIL]`) | Schema invalid, OR `status: complete` but required fields missing | Fold the field-level errors into the `AskUserQuestion` call itself — the question text or each option's `description` (the channel rule, AUTHORING §18: content a question depends on rides inside the `AskUserQuestion` call) — and ask: fill them in now, or accept `status: draft`. The full report may also be printed, never instead. Re-run validation after re-entry. |
| 2 | Cannot read/parse the file | Surface to user (missing file, bad YAML, permission error). Do not retry silently. |
| 3 | Missing dependency | Validator prints `pip install` instructions. Do **not** auto-install — ask the user to install and re-run. |

**Downstream-agent contract**: downstream agents MUST reject the PRD if
`metadata.status != "complete"` OR if `validate_schema.py` exits non-zero.
The one exception is to the exit code, never to the status: a failure every
check of which `doctor.py --artifact docs/PRD.yaml` reports as accepted
deviance does not reject (`sdlc/skills/repair/references/accepted-deviance.md`).


## CLAUDE.md is not this skill's to write (Phase 8)

**This skill never writes `CLAUDE.md`.** The project-root `CLAUDE.md` is owned by
`/sdlc:setup`, which writes one static `## SDLC Documents` block — no per-skill
bullets, no timestamps, byte-identical on every run. Never add a section, a
bullet, a note, an id, a status, a caveat or a resolution there.

Those have homes that a machine reads and that nothing has to remember to
update:

| What you noticed | Where it goes |
|---|---|
| A caveat about this artifact | a typed `WRN-NNN` entry in the artifact itself |
| A defect in an upstream spec | `FND-NNN`, via `.claude/sdlc/findings.py` |
| A defect in an sdlc SKILL | `LSN-NNN`, via `/sdlc:lesson` |
| Something the user should see now | the close card's `Attention:` row |

All of them surface, generated and never stale, in
`.claude/rules/sdlc-statusboard.md` (loaded into every session) and
`.claude/sdlc/STATUS.md` (the full text). Refresh both at the end of Phase 8:

```bash
python .claude/sdlc/docs_index.py     # the navigation index
python .claude/sdlc/statusboard.py    # the statusboard
```

Both are harmless no-ops when the project has not run `/sdlc:setup`.

## Closing the session

Once Phase 8's refresh has run:

- Set `status: complete` in the state file.
- Keep the state file as an audit trail — do **not** delete it.
- Tell the user the workflow finished and where the artifacts live.

> **Field-level errors are the one thing you show verbatim** — the field path
> *is* the fix, so paraphrasing it costs the user the answer. Everything else
> the validator prints gets translated, not pasted: coverage gaps, warnings and
> cross-check findings become one plain sentence each (what happened, why it
> matters, what to do). See CLAUDE.md section 14 and
> `sdlc/skills/prd/references/reporting-to-the-user.md`.
