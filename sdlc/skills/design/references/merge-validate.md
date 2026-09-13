# Merge, validate, and closing out

Detailed rules for Phase 7 (write & validate) and Phase 8 (pointer + close).
Read on entering Phase 7.

## What Phase 7 writes

Always `docs/DESIGN.yaml`. Plus, conditionally:

- `docs/DESIGN__tokens.yaml` — iff `token_based_ui` ∈ `functional_structure`.
- `docs/DESIGN__assets.yaml` — iff `asset_pipeline` ∈ `functional_structure`
  OR `aesthetic_direction.requires_custom_assets`.

Set `DESIGN.yaml.sub_artifacts.tokens` / `.assets` to the file paths you wrote
(and only when the composition rule holds — a stray pointer is an orphan the
validator rejects). A pure-headless product writes only `DESIGN.yaml` with
`aesthetic_direction: null` and both sub_artifacts null.

If a sub-file's content is still a draft at write time (the user EXIT'd mid-token
or mid-asset), write what exists with that file's `metadata.status: draft`; the
parent `DESIGN.yaml.metadata.status` is forced to `draft` too.

## Merging into existing files

If `docs/DESIGN.yaml` (or a sub-file) already exists:

- Load as baseline. Overwrite a key **only if the user changed it this session**;
  otherwise keep the existing value. Add new keys.
- Keys the session would remove → ask the user to confirm before deleting
  (especially dropping an asset, which orphans its brief).
- User-edited-on-disk vs state conflict on the same key → surface it, never
  auto-resolve:
  > "Conflict on `DESIGN.yaml.<key>`: file has `<a>`, interview state has `<b>`
  > (set <timestamp>). Which should I keep?"
- Preserve unrelated keys you don't recognise (`extra="allow"` tolerates them).

If `functional_structure` changed such that a sub-file is no longer needed (e.g.
the user dropped `asset_pipeline` and `requires_custom_assets` is false), ask
before deleting `DESIGN__assets.yaml` — don't silently remove a file with work
in it.

## Writing the files

- Inline YAML comments on top-level keys (use the `*.schema.yaml` files as
  templates). Updated `metadata.last_updated` + `session_id` on every file.
- **IDs**: assign `AST-NNN` to every asset (persist `state.last_ids.AST`); prefix
  every `design_warnings` entry `"WRN-NNN: <message>"` (persist
  `state.last_ids.WRN`). Store all upstream refs as ID strings only.
- **changelog** (append-only): in update mode, prepend ONE
  `"<version> (<YYYY-MM-DD>): <one-line summary>"` to each file changed. Never
  rewrite/reorder. Fresh write may omit it or seed `"<version> (<date>): initial."`.
- **upstream_provenance** (replace-on-write, DESIGN.yaml only): a snapshot for
  each upstream consumed — `docs/PRD.yaml` and `docs/UX.yaml` — each
  `{file, session_id, last_updated, sha256}`. `sha256` from
  `docs/INDEX.yaml.generated_from[<file>]`, or
  `python .claude/sdlc/docs_index.py --hash docs/<file>`, else the text-level
  hash `sha256(read_text(encoding='utf-8').encode()).hexdigest()[:16]` —
  never raw bytes (a byte hash differs between CRLF and LF checkouts). See
  CLAUDE.md §7 and `sdlc/skills/ux/references/upstream-reconciliation.md`.
- **status**:
  - `complete` only when all required fields are filled, the validator passes
    `[OK]`, composition is consistent, and every `to_be_generated` asset is
    covered (brief or deferral).
  - `draft` on EXIT, any null required field, composition mismatch, or an
    uncovered asset.

## Running the validator

```bash
python "${CLAUDE_SKILL_DIR}/validate_schema.py" --path docs/DESIGN.yaml
```

One pass does six things: schema-validate `DESIGN.yaml`; discover + schema-
validate `DESIGN__*.yaml` siblings; required-field checks; ID-prefix formats
(AST/WRN/FR-or-NFR/SCR/ENT); **composition consistency**; **asset-brief
coverage** (trace-or-defer). It also prints advisory notes (e.g. an
`asset_type` not in `asset_taxonomy`) that never block `complete`.

| Code | Meaning | Agent action |
|---|---|---|
| 0 `[OK]` | complete, composition consistent, every asset covered | ✓ Proceed to Phase 8. |
| 0 `[DRAFT]` | draft — schema valid, maybe missing fields / coverage | Inform user; proceed to Phase 8 (pointer still injected). |
| 1 `[FAIL]` | schema invalid, OR `complete` with missing fields / composition error / id-prefix violation / uncovered asset | Show errors verbatim. Offer via `AskUserQuestion`: fix now, or accept `draft`. Re-validate after re-entry. |
| 2 | Cannot read/parse a file | Surface to user (missing file, bad YAML, permissions). Don't retry silently. |
| 3 | Missing dependency | Validator prints `pip install`. Ask user to install; don't auto-install. |

### Composition rules the validator enforces (per product scope)

- `headless` is exclusive — it can't co-occur with `token_based_ui`/`asset_pipeline`.
- `token_based_ui` selected ⟺ `sub_artifacts.tokens` set AND a tokens file on disk.
- `asset_pipeline` OR `requires_custom_assets` ⟺ `sub_artifacts.assets` set AND
  an assets file on disk.
- `aesthetic_direction` present unless `functional_structure == [headless]`.

### Coverage rule

Every asset with `source == to_be_generated` has a non-null `generation_brief`
OR is deferred via the owning scope's structured `deferrals: [{id, reason}]`
list (top level; `products.<slug>.deferrals` in monorepo mode — AST id spaces
are per product). A deferred asset counts as covered (CLAUDE.md §6
trace-or-defer). A `design_warnings` entry naming the AST id still defers it
for one more version, pooled across products, and is reported as deprecated.

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

## Refresh the index + close

If `.claude/sdlc/docs_index.py` exists, run `python .claude/sdlc/docs_index.py`
so `docs/INDEX.yaml` reflects the new DESIGN files immediately (the setup hook
also does this, but a mid-session hook only activates next session). Then set
state `status: complete`, keep the file, and tell the user:

> "Design spec written: `docs/DESIGN.yaml`" + the sub-files. "Index and
> statusboard refreshed. Downstream coding agents (and `sdlc:arch`/`sdlc:task`)
> can now style every surface and scaffold the asset pipeline from these."

## Downstream-agent contract

Downstream skills/agents MUST reject the design artifacts if
`DESIGN.yaml.metadata.status != "complete"` OR the validator exits non-zero.

> **Field-level errors are the one thing you show verbatim** — the field path
> *is* the fix, so paraphrasing it costs the user the answer. Everything else
> the validator prints gets translated, not pasted: coverage gaps, warnings and
> cross-check findings become one plain sentence each (what happened, why it
> matters, what to do). See CLAUDE.md section 14 and
> `sdlc/skills/prd/references/reporting-to-the-user.md`.
