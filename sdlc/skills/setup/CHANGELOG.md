# setup — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.26 (2026-09-26) — `docs_index.py` capability 11: an item a stamp never itemized is recovered from git before `re-stamp only` is printed, and a referenced miss says a change cannot be ruled out

- `docs_index.py` `_item_delta_lines` (ledger IMP-229, aicf LSN-117: a stamp holding `items: 0` for ARCH.yaml drew "re-stamp only" while four NFRs this file covers had been added to its container): an index-new item - its family predates the stamp's capability, or the `items` map is empty - is first recovered from git at the recorded hash; unchanged stays `re-stamp only`, changed is a delta item, and a miss on an item this file references or cites prints "no earlier body recorded or recoverable - a change cannot be ruled out" instead. `--drift` and `--stale` both read it, so repair's drain no longer stamps such a row unreviewed. `CAPABILITY_VERSION` 10 -> 11, so an older installed copy counts as absent (`references/helper-resolution.md`). Plain added items are not reference-checked yet (ledger IMP-232). Pinned by `_smoke/index_selftest.py` (git-hit and no-git branches) and `_smoke/wire_selftest.py`.

## 1.25 (2026-09-24) — `docs_index.py` capability 10 itemizes the system ARCH.yaml (containers + edges) and prints a family the recovered revision lacked as one count line; `plugin_root.py` names the running plugin for hooks; the helper-resolution rule covers every helper, not `docs_index.py` alone

- `docs_index.py` (capability 10, ledger IMP-215): `_extract_arch_system` indexes the system `ARCH.yaml`'s `containers[].container_id` as kind `container` (keyed `container/<cid>`, the bare id an alias when nothing else claims it) and `edges[]` as kind `edge` (keyed `<from>-><to>`), so a container shard's `--drift` names the block or edge that moved - `[referenced here]` for its own container or an edge touching it, `re-stamp only` for another container's block - and `--stamp` records `ARCH.yaml (N item(s))` instead of 0. `_KIND_CAPABILITY` gates both kinds at 10, so a pre-10 stamp reads them as index-new, never as a phantom addition. Pinned by `_smoke/index_selftest.py` section 13.
- `docs_index.py --drift` (ledger IMP-216): against a git-recovered revision, a family the recovered side holds none of prints `<family>: N defined now, none in the recovered revision - a family added whole, or one written in a shape the index cannot itemize` instead of every current id as "added upstream" (a recovered PRD revision itemized 0 ACR and 0 QUE; the report listed all 121). An exact stamp's 0 is a real 0 and keeps the id list. Pinned by `index_selftest.py` 12c-ii and 13b.
- `plugin_root.py` (ledger IMP-220), installed as `.claude/sdlc/plugin_root.py` and recorded in the marker's `helpers`: the sanctioned way for a hook, project script or CI job with no `${CLAUDE_SKILL_DIR}` to find the running plugin - `SDLC_PLUGIN_ROOT`, then the skill dir, then the newest ENABLED `sdlc@<marketplace>` in Claude Code's `installed_plugins.json` (a `settings.json` `enabledPlugins: false` drops one; versions compare part by part; a candidate must carry the manifest and `skills/setup/docs_index.py`). `--path`, `--json`. Rule in `references/helper-resolution.md` → "Callers with no skill in view". Pinned by `_smoke/plugin_root_selftest.py`; `wire_selftest.py` pins the install.
- `references/helper-resolution.md` (ledger IMP-218): the rule resolves "before the first helper call", for every `.claude/sdlc/<helper>.py` a skill runs; the sentence that said the close-phase `record-run` and `statusboard.py` "keep their old command forms" (read as: run the installed copy) is gone; the plugin-copy table gains `plugin_root.py`; the capability history gains 10. `_smoke/helper_resolution_selftest.py` arm 4 pins the rule and every SKILL.md's helper-agnostic clause.

## 1.24 (2026-09-22) — statusboard.py's Lessons line reports the maintainer's verdicts, not just a count of everything ever recorded

- `statusboard.py`: `collect_lessons` reads the verdict fields `lessons.py reconcile` stamps and the line becomes `Lessons: N open (ids), M open again after a fix (ids), K triaged upstream, R resolved (fix installed), P resolved upstream, not installed - run /sdlc:setup, W wontfix`; STATUS.md splits open from open-again. Pinned by `_smoke/statusboard_selftest.py` (lessons arm).

## 1.23 (2026-09-22) — autocommit.py repairs a missing /sdlc:<skill> prefix and commits a project's declared auto_commit.also files; docs_index.py gains --items-at

- `autocommit.py commit`: an `--invocation` without the `/sdlc:<skill>` prefix (the `$ARGUMENTS` half alone, a one-token `-d`, a bare `/<skill>`) is repaired from `--skill` and the one printed line says so; one naming a different skill is refused with a `[DRAFT]` line. argv is rewritten to `--invocation=`/`--summary=` before parsing so a value starting with `-` no longer exits 2. HELPER_VERSION 2 (ledger IMP-207, pinned by `_smoke/autocommit_selftest.py`).
- `autocommit.py`: a project may declare `auto_commit.also` in the marker (`mode --also P ...`, bare `--also` clears): literal repo-relative paths outside `docs/` and `.claude/skills-state/`, refused at write time and dropped with a count at read time, passed to git as `:(literal)`; honoured by every skill but `lesson` and `setup`. Every staged path is now passed as `:(literal)` so a `[` in a filename cannot glob in siblings (ledger IMP-209, pinned by `_smoke/autocommit_selftest.py` and `_smoke/wire_selftest.py`).
- `docs_index.py --items UPSTREAM --items-at <sha256>`: the item TEXT of the committed revision whose content hash matches, as `{status: hit|miss|unavailable, items}` JSON, from the same 40-revision git walk `--drift` uses - what task's reslice needs to follow a backfilled line (ledger IMP-203, pinned by `_smoke/index_selftest.py`).

## 1.22 (2026-09-20) — Asks once whether every run should commit itself, installs autocommit.py, and seeds the marker's auto_commit block (CLAUDE.md 20)

- Step 4 asks a second verbatim consent question (header `Auto-commit`, two options) in the same `AskUserQuestion` call as the sharing one when both are pending, skipped when `auto_commit.decided_on` is set, the session is non-interactive or the project is not a git repository; the answer is recorded with `python .claude/sdlc/autocommit.py mode --set on|off`. `wire_setup.py` installs `.claude/sdlc/autocommit.py` (the close-step committer every skill runs: stages only that skill's owned files, subject `<invocation as typed> → <summary>`, never pushes, never `git add -A`, never a run failure), records `helpers.autocommit`, seeds `auto_commit: {mode: off, decided_on: null}` beside `telemetry` and carries it forward on re-run; `statusboard.py` prints one line when it is on. Step 5 commits setup's own install set; the card gains `Commits:` and `Commit:` rows. New `references/auto-commit.md` (the rule every close phase points at), `_smoke/autocommit_selftest.py` (the helper against real git repositories) and `_smoke/autocommit_lockstep_selftest.py` (all twelve close phases); `wire_selftest.py` and `statusboard_selftest.py` extended.

## 1.21 (2026-09-19) — helper-resolution.md splits the absent-generator case into own-toolchain and never-ran-setup, pinned across all eight Phase 8 sites

- `references/helper-resolution.md`'s decision table splits the bare-regenerate-with-no-installed-copy case: own-toolchain (the marker `.claude/sdlc/sdlc-plugin.json` exists without a `docs_index` helper: run the project's own docs-hook command from `.claude/settings.json`) versus no marker at all (the only genuine no-op). No new marker key. New `_smoke/index_refresh_lockstep_selftest.py` pins the rule and every artifact skill's Phase 8 sentence (ledger IMP-200).

- `docs_index.py --stamp/--drift/--stale` no longer report a pre-1.20 stamp's unindexed failure_mode / security_concern items as a phantom "added upstream" (a stamp without a `capability` key predates every floor), and no longer absorb a real edit to an always-empty items map (an unindexed shard) as "nothing moved" — both fall back to the sha-only "cannot be told apart - review the diff" hedge, inside `_item_delta_lines` so the dict, git-recovered and `--stale` callers agree (ledger IMP-185).
- `--drift/--stale` never say "re-stamp only" when the upstream's own changelog-since-stamp names the target artifact, one of its shards or `/sdlc:<skill>`: every changed-in-body item is marked `[changelog names this file]` instead, matched on the raw changelog entries (ledger IMP-186).
- `_RESTAMP_ONLY` says its "no question" scopes the delta review only; the owning skill still runs every update-run step its own SKILL.md owes (ledger IMP-188).
- `mark()` reads the target's own structural deferrals: a changed-in-body item this file defers is marked `[deferred here]` instead of printing bare, and `_artifact_scan_ranges` skips the `deferrals` block so a deferral's own id is never mistaken for an active citation (ledger IMP-187).

- Every cross-skill reference pointer in SKILL.md and references/ now uses the consumer-safe `${CLAUDE_SKILL_DIR}/../<skill>/references/<file>.md` form instead of a bare `sdlc/skills/...` path that resolves only in the plugin repository; `lint_skill_paths.py` holds it (ledger IMP-206).

- No shipped runtime file (SKILL.md, references/, assets/) carries a ledger-id citation any more: bare `(IMP-NNN)` / `(LSN-NNN)` parentheticals are gone, history sentences keep their rule and their reason without the ticket, close-card examples show the `LSN-NNN` placeholder; `lint_context_budget.py` counts IMP- and LSN- ids with a ceiling of 0 per skill (ledger IMP-182).

## 1.20 (2026-09-17) — The index resolves every sanctioned item spelling it used to decline to block, indexes ARCH failure modes and security concerns, tells index-new from document-new on the first drift after an upgrade (capability 9), and the always-loaded docs-access rule carries only the read protocol

Ledger IMP-160: SCR/USR/OPR/AST/QUE items written with `id:` not first, single-quoted, or as a single-line flow mapping (the QUE form prd's own SKILL.md instructs) now resolve under `--show` and `--refs`, not only pass `--check` — one quote/bracket-aware tokenizer serves both the definition scan and the unaddressable fallback, which used to record an `id:`-looking token from inside quoted prose as the item's id (the red team's phantom `QUE-999`); that phantom is no longer swallowed and never resolves. Round two of IMP-028, whose remedy indexed only the block shape.

Ledger IMP-161: `failure_modes[].id` and `security_concerns[].id` (container- and component-level) are symbols, keyed qualified `<cid>/<id>` so a risk id never collides with a same-named component; `targets_failure_mode` / `targets_security_concern` resolve the bare id inside the citing shard's container and get the dangling check every family has; a mitigation-only edit is now "changed in body" under `--drift` instead of "re-stamp only", so `test --reconcile` asks. `--stamp` records the capability it was made with and `--drift` classifies items visible only since a later capability as index-new — one line, "re-stamp only", never a question — so the first drift after this upgrade does not walk N phantom additions. Consumers pick this up with one `/sdlc:setup` re-run. Regressions: new `_smoke/index_selftest.py` arms (33), `wire_selftest.py`'s pinned capability string.

Ledger IMP-141 (AUTHORING §19): `assets/sdlc-docs-access.md` — installed into every consumer session as `.claude/rules/sdlc-docs-access.md` — drops its write-time paragraphs (`--stamp`, `--items`, `--drift`, `--stale`, and the `${CLAUDE_SKILL_DIR}` "no installed copy" fallback, which restated `references/helper-resolution.md` and named a variable no ambient session defines); a skill run reads those steps from its own SKILL.md phase text. The asset keeps the read protocol (`--show`, `--refs`, `--check`, `--find`, `--hash`, the content hash) plus one sentence pointing a project with its own generator at `references/helper-resolution.md`. The four installed rule files now share one byte budget in the repo-root `lint_context_budget.py` (modelled on the statusboard's own cap), which also bans skill-run mechanics from the three protocol assets and the skill-dir variable from all four; the glossary keeps naming the flags because it defines the headings the terminal prints.

## 1.19 (2026-09-16) — The index reads a requirement item whatever its spelling, so a correct PRD stops failing the id check

Ledger IMP-159.

**This file disagreed with itself.** `_FR_ITEM_RE` accepted either quote while `_SYMBOL_ITEM_RE` and `_DEF_LISTITEM_RE` demanded a double one — so a single-quoted NFR, WKF, ACR or ENT was not a definition at all, every structured reference to one came back **dangling**, and `--check` exited 1 on documents that were correct. That is a blocking false reject, not a silent miss, and it is worth saying plainly: of the spellings this item covers, the single-quoted one was the loudest failure and the wrapped one the quietest. Both patterns now accept either quote.

The summary was wrong wherever it was produced: built from the item's first physical line alone, so a wrapped item lost its continuation and a comment-tailed one carried both the closing quote and the comment into the index. `_item_text()` now builds it from the item's full line range — which `_block_end` had already computed — for the FR arm and the other-families arm alike.

`CAPABILITY_VERSION` 7 → 8; consumers re-run `/sdlc:setup` to pick it up, and the board reports the new number. One consequence to expect rather than be surprised by: the first `--drift` after the upgrade may report items as *added* that were always there, because a previously unindexed single-quoted item becomes a real symbol with a body hash. That is a capability artifact, not a document edit.

Pinned by new `_smoke/index_selftest.py` arms over a re-spelled corpus: `--check` clean, `--show` resolving each single-quoted family, the wrapped summary carrying its continuation, and the comment-tailed one carrying neither quote nor comment.

## 1.18 (2026-09-16) — A re-run stops rewriting hand-written project instructions, stops clobbering a project's own toolchain, and the board reads warnings through the canonical parser instead of its own copy

Ledger IMP-117, IMP-118, IMP-116, IMP-110 and IMP-119, plus a second defect found while fixing them.

**The re-run was not idempotent and was destructive at the edges.** The section was rebuilt from non-blank lines, so a user's two-paragraph note or a fenced block lost its blank lines; the section ended at the next `##`, so a following `#` heading was swallowed; a `## SDLC Documents` line inside a code fence was treated as the section; and the retired 0.8.0 intro was matched as a substring, so a user line that merely contained the phrase was deleted. The scanner is now fence- and heading-aware, the retired line is matched exactly, one renderer serves the created, appended and updated paths, and the carried-over block is normalised to a FIXED POINT — naively keeping blank lines would have made the block grow by one per run, which the existing idempotence assertion would have caught. A reflowed retired line now has a case asserting it SURVIVES, so the safe failure is pinned rather than incidental.

**Own-toolchain detection could both clobber and abstain.** It demanded positive proof of a fork, so a project whose index header was hand-trimmed or written by an older generator got its index replaced; and it treated any hook merely mentioning the generator — including a read-only CI check — as a foreign generator, which disabled the whole install. A foreign HOOK, read from `settings.json` **and** `settings.local.json` and excluding read-only verbs, is what gates the install now, because a hook is positive evidence of another toolchain; a non-stock index header gates only index generation; an unrecognised header is treated as ours. Inverting the header test globally, which was the first design, would have silently un-wired stock projects across all three install steps.

**Found while fixing that:** the hook-merge token was the bare substring `docs_index.py`, so a project with its own `check_docs_index.py` hook had it OVERWRITTEN rather than preserved. It now targets the generator path. Two required assertions were unreachable until this was fixed.

**Line endings are an ownership question, not one rule.** Files this installer generates wholesale (the marker) are written LF; files the consumer authors (`settings.json`) have their endings detected from bytes and written back unchanged. A single "preserve on rewrite" rule would have frozen CRLF forever in the marker, since every Windows project that ever ran setup already holds it that way and nothing else rewrites it. The CRLF selftest's glob now covers `.json` and `.yaml`, and the assertions compare bytes before and after rather than looking for absent CRLF — an absence check passes on the pre-fix tree on POSIX and would pin nothing off Windows.

**The board no longer keeps its own copy of the warning rules.** `statusboard.py` imports the canonical parser through the loader pattern already in that file, so the always-loaded board stops printing as live caveats the entries every validator reports as ignored; `STATUS.md` gains one counted line naming BOTH refusal channels, since a line covering only the non-blocking one would have hidden a blocking entry from both files. The duplicate kind/status/impact tuples are gone.

**The index generator stops blocking on YAML it cannot address.** Ids carried by a definition shape the line scanner cannot parse are recorded as unaddressable at scan time; a reference to one is neither an edge nor dangling, and one non-blocking warning names the id, its site and the rewrite that would index it. An id nothing defines in any shape still blocks — that direction is pinned too, because a blanket never-block rule would have hidden the defect the gate exists to catch.

Regressions: `_smoke/wire_selftest.py` (12 and 13 assertions red across two of the items), `_smoke/statusboard_selftest.py` section 9, and `_smoke/index_selftest.py` section 16 — 7 of 283 red before the fix.

## 1.17 (2026-09-16) — The statusboard's Next names the command an owed finding is waiting on, and `--find` accumulates repeated filters

Ledger IMP-132, IMP-115. `next_step` sent every non-resolved finding to `/sdlc:repair`, so mid-reconcile the always-loaded board contradicted the doctor output from the same moment and the chain stalled. The board now imports `findings.py` (installed beside it) and reads `awaiting_registry`, so the owed-work rule keeps one owner; decided findings (wontfix, deferred, duplicate) no longer count as open; a Pro-only owed command is described rather than printed in the free edition. `docs_index.py --find` takes `action="extend"`. Regressions: `_smoke/statusboard_selftest.py`, `_smoke/index_selftest.py`.

## 1.16 (2026-09-15) — `docs_index.py` capability 7: `--drift` marks every removed or changed upstream item the artifact references or cites (`[referenced here]`, `[cited in prose xN]`, a unit's name in a directive included) and calls an upstream whose changed items carry no mark `re-stamp only` (`--stale` rows too); `--stamp` and `--drift` warn when the artifact references items of an earlier-stage file its stamp does not record

Ledger IMP-147 (aicf LSN-084) and IMP-148 (aicf LSN-085). The changed-in-body
list is the operand a reconcile's step 4 filters to "only items this file
traces or covers", and the helper left that filter to the reader - a prose
cite at four sites was invisible to a hand filter over structured traces. A
system test that drove a container unit's contract had never recorded the
unit's shard as an upstream, and nothing compared a stamp with what the file
references.

- `_item_delta_lines` marks each removed or changed item from `my_refs`
  (structured) plus a targeted prose scan of the artifact for the item's id
  or bare name outside its metadata block and changelogs (`_cite_counts`,
  `_artifact_scan_ranges`); each family counts its marked items; an upstream
  with none is labelled `re-stamp only` in `--drift` and in `--stale` rows
  (`restamp_only` in `--stale --json`). No new index field.
- `_provenance_gaps` / `_gap_warnings`: `--stamp` (also `provenance_gaps` in
  `--json`) and `--drift` warn when the artifact references items defined in
  an earlier-stage file that the stamp does not record - same-family shards
  and later-stage files excluded, only for owners with a `--reconcile` form.
- `CAPABILITY_VERSION` 6 -> 7 (consumers re-run `/sdlc:setup`);
  `assets/sdlc-docs-access.md` and `references/helper-resolution.md` say so.
- Pinned by `_smoke/index_selftest.py` sections 12d and 12e (red on the
  pre-fix helper: 7 assertions) and `_smoke/wire_selftest.py` (capability 7).

## 1.15 (2026-09-15) — `docs_index.py` capability 6: the hook refreshes only for files directly in the project's own docs dir, `--stamp` names every re-stamped upstream whose items moved and `--hold-upstream` keeps one untouched; installed helpers are used only when their capability matches the plugin, and the statusboard says when `/sdlc:setup` should be re-run

Ledger IMP-034 (reopened), IMP-106, IMP-108 - found by the 2026-09-15 retro (lessons/retro/2026-09-15/).
- `docs_index.py --hook` resolves the docs dir as `--docs-dir`, else `<--project-root>/docs`, else the `docs/` beside the nearest `.claude/`, and refreshes only for a file directly in it. It used to match any path with a `docs` component (state files, `src/config.yaml`) and wrote the index into the first `docs` ancestor. `_smoke/index_selftest.py` section 8b now feeds absolute paths under a docs-named ancestor and is red on the 0.6.0 generator.
- `--stamp` prints `re-stamped <file>: <ids> changed ... since the last stamp - reviewed by this run?` for each recorded upstream it refreshes whose items moved, and `--hold-upstream FILE` (repeatable) keeps that recorded entry byte-identical so `--drift` still owes its delta. `CAPABILITY_VERSION` 5 -> 6. Pinned in index_selftest section 15.
- New `references/helper-resolution.md`: a skill runs the installed `.claude/sdlc/docs_index.py` only when the marker records a capability at least the plugin copy's; otherwise the plugin copy, and the user is told once to re-run `/sdlc:setup`. `statusboard.py` adds one line to both boards when the install lags. Pinned by `_smoke/helper_resolution_selftest.py` and `_smoke/statusboard_selftest.py` (now swept by run_smoke).

## 1.14 (2026-09-15) — `docs_index.py --drift` prints its item lists and the fallback residue whole (they are the delta a reconcile takes verbatim), `--check` names every ambiguity candidate, and `--stale` warns about sha-only stamps (no items map), naming the re-stamp

Ledger IMP-097 (aicf LSN-078): the canonical reporting block's `join_ids(ids, 8)` capped
the added / removed / changed-in-body lists the reconcile form says to take verbatim, and two
hidden ids needed edits. The rule now lives in `reporting-to-the-user.md`: a capped sample is
for a verdict a person skims, an operand a later step consumes is printed whole; the five
operand sites pass `len(ids)`, the shared helper is untouched. Ledger IMP-102 (aicf LSN-083):
`--stale` lists every provenance entry that records a sha256 but no items map (`sha_only` in
`--stale --json`) - the hand-written stamps five consumer skills wrote until 0.9.13 - and names
the `--stamp` that records the map. Regression: `_smoke/index_selftest.py` sections 13 and 14.

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
