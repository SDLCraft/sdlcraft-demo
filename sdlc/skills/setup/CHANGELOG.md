# setup — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.13 (2026-09-12) — `docs_index.py --drift` recovers a sha-only stamp's old upstream from git: the newest committed revision whose text hash equals the recorded sha256 yields the exact item delta ("recovered from git"); only an uncommitted stamp falls back to the reference residue

Ledger IMP-083 (aicf LSN-065). Every recorded `sha256` is a text hash a git blob can
match, so a stamp written before items maps existed (every pre-0.9.8 project has
one per artifact) no longer prints a residue nobody can tell apart: `--drift` walks
the last 40 commits touching `docs/<upstream>`, hashes `git show <rev>:./<file>`
the way `--hash` does, materializes the first match into a scratch docs dir and
diffs item by item through the same renderer the items-map path uses. A miss says
"no committed revision ... carries the content this stamp recorded" and keeps the
residue. Git absent or no repository: silently the old behaviour. Regression:
`_smoke/index_selftest.py` section 12c (a committed stamp yields the exact +1/-0
delta; an uncommitted one still yields the residue; skipped when git is not on PATH).

## 1.12 (2026-09-11) — The marker records the installed edition (`edition: free|pro`, plus `pro_url` from the free build's `homepage`); the statusboard labels test/task/code `full edition only` and never routes to them in a demo (free) install

`wire_setup.py` decides the edition by whether test, task and code ship beside
setup. A marker without the key reads as the full plugin, so nothing changes
for existing projects; re-running `/sdlc:setup` after an upgrade flips the
board back. Regressions: `wire_selftest.py` (a tree without the Pro skills
installs as free; the full tree as pro) and `statusboard_selftest.py` case 7.

## 1.11 (2026-09-11) — `docs_index.py` capability 5: `--stale` lists every stale artifact in the order to reconcile it; `--stamp` records each upstream's version and `--drift` quotes its changelog since; an item whose id another file already defines is no longer missing from the item map

**Collisions.** `build_index` dropped the second definition of a symbol name
another file already defined, and `items_of` iterated only the named symbols —
so `--stamp` never recorded that item and `--drift` reported "no item added"
for exactly the item that was new (OPR ids are one counter across `API__`
shards). The shadowed definitions are kept (`DocIndex.shadowed`), `items_of`
includes them, and `--drift` warns on every collision touching the artifact or
one of its upstreams. Regression: `index_selftest.py` section 12b.

`--stale [--json]` compares every artifact's recorded upstream hashes at once
and lists the stale ones upstream first (pipeline order, system file before
shards), each with its owning skill's `--reconcile` command — what a reconcile
run computes its `Next:` from, so the chain after a repair walks itself.
`--drift`'s `NEXT:` names the reconcile form too. `--stamp` now records each
upstream's `metadata.<name>_version`, and `--drift` prints a `why` line per
moved upstream: its changelog entries newer than that version (a legacy stamp
falls back to entries dated on or after its `last_updated`; an upstream that
moved with no entry is flagged as a probable hand edit). The glossary gains
"reconcile", "STALE, IN THE ORDER TO RECONCILE THEM" and "handoff"; the
docs-access rule documents `--stale`. Regression: `index_selftest.py` section
13; `wire_selftest.py` pins capability 5.

## 1.10 (2026-09-10) — `docs_index.py` records per-item provenance (`--items` / `--stamp`, an exact `--drift`) and a prose mention is no longer a reference

Capability version 4. `--stamp <artifact> [--upstream <file>…]` rewrites an
artifact's `metadata.upstream_provenance` with, per upstream, the sha256 and
an `items:` map of every symbol that upstream defines to a body hash;
`--items <upstream>` prints that map; `--drift` then names exactly what was
added, removed and changed in body since the artifact was written - no git,
no guessing from the artifact's references (IMP-073, aicf LSN-051/053). A
work unit's hash ignores `touches_entities` and `status`, so a declaration
backfill is not a change (IMP-064, LSN-052). Without an `items` map `--drift`
falls back to the reference-set method, now subtracting the artifact's
structured deferrals and saying the residue mixes "new" with "never covered".
The dangling-reference scan counts only STRUCTURED references (a field value,
a list entry, a flow-list element); an id inside prose - a spec illustrating
its own id format, an example locator, example ids in help text - still feeds
`referenced_by` when it resolves but is never dangling (IMP-072, LSN-050).
Regression: `_smoke/index_selftest.py` sections 11-12 + the QUE case.

## 1.9 (2026-09-09) — `docs_index.py` writes LF on every platform; the installer normalizes a CRLF checkout's helpers to LF

`write_index` passes `newline="\n"` - the generated index no longer
inherits the host's line ending (IMP-043, aicf LSN-044; index_selftest).
`wire_setup._copy` normalizes text targets to LF, so a plugin checkout
rewritten by `core.autocrlf=true` still installs LF helpers, and the repo
pins `eol=lf` in `.gitattributes` (IMP-024, LSN-007; wire_selftest).

## 1.8 (2026-09-09) — The consent notice says what delivery provably keeps

The consent notice says what it now provably keeps. A delivered report
identifies a project by a random `project_uuid` minted on first delivery, not
by a hash of its absolute path (which is a hash of a guessable string, and
changed identity whenever the directory moved), so the question adds "your
project's name" to the list of what never travels and says the project appears
only as a random id. The marker's telemetry seed names the `project_uuid` slot;
`lessons.py` mints it, and only for a project that actually delivers.
Regressions: `_smoke/wire_selftest.py`, and `lesson/_smoke/lessons_selftest.py`
asserts the promise against the bytes - directory name, absolute path and
e-mail address are all absent from a built report.

## 1.7 (2026-09-04) — `docs_index.py` resolves the `QUE-NNN` family

`docs_index.py` resolves the `QUE-NNN` family: PRD open questions are typed
items across both `undecided_decisions` and `parking_lot`, so `--show QUE-009`
now works as `.claude/rules/sdlc-docs-access.md` already promised. The family
is warn-first, so a PRD that still carries open questions as plain strings
keeps a green `--check` (CLAUDE.md 10). `--drift` on the PRD no longer tells
the user to record `upstream_provenance` the root artifact is exempt from.
Ledger IMP-028/IMP-029/IMP-034/IMP-035/IMP-036; regression
`_smoke/index_selftest.py` + `_smoke/wire_selftest.py`.

## 1.6 (2026-09-03) — Asks once whether lessons may be shared with the plugin maintainer

Asks once whether lessons may be shared with the plugin maintainer (new step 4)
and records the answer with `lessons.py consent --set`. The marker gains a
`telemetry` block, seeded `off`, which a re-run carries forward verbatim — an
installer must never reset a consent answer. Regression:
`_smoke/wire_selftest.py`.

## 1.5 (2026-09-02) — `CLAUDE.md` becomes a static section

`CLAUDE.md` becomes a static section. The intro note plus the timestamped
`docs/INDEX.yaml` bullet are replaced by one eight-line block that is
byte-identical on every run, so `git diff CLAUDE.md` stays empty. Per-skill
bullets an older version wrote are left in place (they are inert) and reported.
New helpers installed: `statusboard.py`, `warning_item.py` and
`migrate_warnings.py`; `docs_index.py --hook` now refreshes the statusboard
whenever it refreshes the index.

## 1.4 (2026-09-01) — Shards join the index and the shared helpers join the install

Shards join the index and the shared helpers join the install (plan items
B1/B2/B4, D-setup-1, C1/A9 install steps). `docs_index.py` (capability 3):
every `docs/*__*` shard is scanned for definitions + references and recorded in
`generated_from`; ARCH__ components + work units (`<cid>/<component>/<unit>`,
bare alias when unique), TEST-STRATEGY tests, API__ operations and
DESIGN__assets assets are symbols; field-anchored named references (entities,
work units, components, tasks) form edges and, unresolved, `dangling_warnings`;
the TST/OPR/AST/QUE families are warn-first for one version; WRN resolves
file-locally; `metadata.changelog` is skipped (never `*_warnings`); retired ids
come from `docs/INDEX.allow.yaml` or PRD `metadata.retired_ids`; `stage_NN` and
the AICF dossier extractor are gone; `--show` resolves every family by bare id;
new `--hash` (the one canonical content hash) and `--drift <artifact>`;
`warnings:` block for unreadable/malformed files and symbol collisions,
rendered with `*` bullets so the repair doctor never files them.
`wire_setup.py`: installs `findings.py`, `bump_artifact.py` and
`sdlc-findings.md` (own-toolchain mode too); the hook is anchored on
`$CLAUDE_PROJECT_DIR`; a shared hook entry keeps its matcher; `--force-stock`
removes the foreign hook; the bare `INDEX.yaml` token needs a generator verb;
own-toolchain runs print `Status: partial`; the marker records helper versions.
This file: `wire_setup.py` invoked via `${CLAUDE_SKILL_DIR}`, close runs the
lessons self-review and passes `--skill-version`. Regressions:
`_smoke/index_selftest.py` (79 assertions), `_smoke/wire_selftest.py` (6
scenarios).

## 1.3 (2026-09-01) — `docs_index.py` indexes PRD 1.1 user stories

`docs_index.py` indexes PRD 1.1 user stories (USR-NNN, typed `- id:` items like
SCR): `--show USR-001`, blast radius and dangling PER refs inside
`owning_personas` all resolve. Regression: `_smoke/index_selftest.py` (two new
assertions).

## 1.2 (2026-09-01) — Run records carry facts (ledger IMP-004)

Run records carry facts (ledger IMP-004): record-run now passes --metric
targets_written / own_toolchain / wire_exit from the action log (lessons.py
gained the flag), and the installed assets/sdlc-lessons.md ambient rule gains
the never-interrupt carve-out (IMP-002): mid-run observations go to the running
skill's lesson_notes, never to an immediate /sdlc:lesson. Also documents why
the `.claude/sdlc/` copies are committed. Regressions:
lesson/_smoke/lessons_selftest.py (--metric), lesson/evals cases 9-11.

## 1.1 (2026-08-31) — Fork-aware install

fork-aware install (ledger IMP-001, lesson aicf/LSN-001): `wire_setup.py` now
detects a project that generates `docs/INDEX.yaml` with its own tool and leaves
every index piece untouched (generator copy, docs-access rule, hook, CLAUDE.md
pointer, index generation), still installing the generator-agnostic pieces
(glossary, lessons helper + rule, version marker). New `--force-stock` flag
restores the overwrite deliberately. Regression: `_smoke/wire_selftest.py`.

## 1.0 — Initial: deterministic installer for the docs/INDEX.yaml toolchain

Initial: deterministic installer for the docs/INDEX.yaml toolchain, docs hook,
rules, lessons wiring, CLAUDE.md pointer.
