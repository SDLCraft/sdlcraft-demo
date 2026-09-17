# lesson — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.14 (2026-09-17) — A where.file prefixed with another skill's folder is owned by that skill: the hint names it and the collector dates it there

Ledger IMP-143. `find_prefix_skill()` recognises a where.file whose leading segment is ANOTHER real skill folder — only when the remainder exists on disk under it, so a repo's own `test/` directory is never mistaken for the test skill — and `lesson_hints` names that owner instead of the alphabetically-first basename match. `lessons/collect_lessons.py`'s `version_delta` keys `path` / `exists_now` / `commits` / `changed` on the owner, and its changelog half prints the OWNER's entries dated after the commit that introduced the lesson's plugin version — never "since <the reporting skill's version>" against the owner's unrelated scale — with the two print lines labelled by the owner's name; byte-identical rendering when owner and skill coincide. Two new selftest arms (`lessons_selftest.py`, `collect_selftest.py`), red at 1.13. The clustering half (`same_subject` compares the filed skill before any prefix is stripped) is IMP-179, open.

## 1.13 (2026-09-17) — An ambient lesson about code's never-re-stamped ledger records the installed footer beside the state's version instead of trusting the state alone, and a run only claims an upgrade that happened inside it

Ledger IMP-144 (narrows IMP-095). `cmd_add`'s ambient path compares a LEDGER-shaped foreign state (code's, the one shape that never re-stamps itself between a plugin upgrade and the next run) to that skill's installed footer: `skill_version` stays the state's value — what wrote the artifacts the session observed, so `--delta` keeps showing a later fix instead of hiding it — and a new `footer_skill_version` plus a distinct Check line (`ambient_ledger_footer_note`) record the skew. A flat or sharded foreign state keeps trusting its own re-stamped number (the pinned prd case is untouched). `record-run`'s `skill_version_at_start` reads only a migration whose `at` falls inside this run and is omitted when none does. LESSONS.schema.yaml and lessons-capture.md carry the ledger-shape carve-out; a blanket footer-compare is the wrong simplification. Three new `_smoke/lessons_selftest.py` arms, red at 1.12.

## 1.12 (2026-09-16) — The two files this helper generates are written LF, so a consent answer no longer flips a repository's line endings

Ledger IMP-116, the lessons half.

Both files this helper writes are generated wholesale by the plugin rather than authored by the consumer, so they are pinned LF. Answering the telemetry consent question used to rewrite the marker with the host's native endings, which on Windows turned a repository that pins LF into a whole-file diff plus a warning from git — and because the marker is only rewritten when its content changes, nothing else would ever have healed it.

The rule this follows is an ownership split rather than a single idiom: the plugin's own generated files are LF, and a file the consumer authors keeps whatever endings it already has, detected from its bytes. The earlier design applied one uniform "preserve what is there" rule, which would have frozen the existing CRLF in exactly the file the plugin fully owns.

Regression: the line-ending case in `_smoke/lessons_selftest.py`, whose glob now covers the generated `.json` files and which compares bytes before and after rather than asserting CRLF is absent — the absent-CRLF form passes on the pre-fix tree on any POSIX host and would have pinned nothing.

## 1.11 (2026-09-15) — Collector-side: the digest ends with the ledger's open / verify / planned items, ranked as `/improve` step 3 ranks, each with a `needs:` line (no analysis, six-key analysis in a v2 ledger, a regression never proven red, notes saying superseded/deferred); `--check-ledger` holds every `planned` item to the current review whatever its id

Ledger IMP-155: `/improve` never offered the backlog. The digest printed only
what the collect brought in, so the 36 items the 2026-09-15 retro minted
(IMP-107, 110..146) and the pre-loop items it reopened were invisible to every
run with "No new lessons this collect"; and the id-based cutoffs let a
below-cutoff item move to `planned` without the current review.

Collector-side (repo `lessons/`, pinned in `_smoke/collect_selftest.py`):

- `collect_lessons.py`: `_report_backlog` (called last in `digest()`),
  `backlog_rank_key`, `backlog_needs`, `BACKLOG_STATUSES`, `BACKLOG_ROWS`; the
  `NEXT:` line names the backlog; `_cutoff_reached` counts every `planned`
  item once the ledger names a cutoff.
- `lessons/LEDGER.schema.yaml`: the planned rule beside the two cutoffs.
  `lessons/LEDGER.yaml`: IMP-017 planned -> duplicate of IMP-132 (the retro's
  verdict). `.claude/skills/improve/SKILL.md` steps 1, 3, 3½ and the close
  card; `references/triage.md` "The backlog is triage input too"; improve eval
  case 6 + `grade_F`.
- Red before the fix: `collect_selftest.py` 10 assertions (7 `check_backlog`,
  3 planned-below-cutoff).

## 1.10 (2026-09-15) — Collector-side: `--check-ledger` requires the v2 review keys (`interactions`, `introduces`) and a red `regression.pre_fix` from `analysis_v2_from` on, and warns on a selftest outside `run_smoke.py`'s sweep and on resolved notes that never name the regression file; `--show` and the digest print `written by` (git blame at the lesson's version, quote-first, per release and ledger item); `cluster_lessons.py` matches the lessons of open items against prior remedies too

Ledger IMP-149, IMP-150, IMP-151 and IMP-152 - the 2026-09-15 retro's Task
2 (`lessons/retro/2026-09-15/NEXT-SESSION.md`): of 78 fixes reviewed at
HEAD 16 were sound; the misses were interactions and introduced copies the
six-key review never asked about, regressions never run pre-fix, a remedy
guard that was token similarity only, and notes that drifted from the diff.

Collector-side (repo `lessons/`, pinned in this skill's
`_smoke/collect_selftest.py` and `_smoke/cluster_selftest.py`):

- `collect_lessons.py`: `ANALYSIS_KEYS_V2`, `analysis_v2_required` (cutoff
  keys `analysis_v2_from` / `analysis_v2_from_version`), a bare "none"
  refused in a v2 key; `pre_fix_problem` (`{result: fail, how, at}`, smoke
  exempt); `swept_by_run_smoke` (per skill folder); the notes-name-the-
  regression-file warning; `written_by` / `written_by_lines` /
  `written_by_digest_line` with `release_of_commit` (the bump commit that
  carries a commit; unreleased; uncommitted) and `anchor_section`; `--show`
  and the digest print the attribution.
- `cluster_lessons.py`: the lessons of open / verify / planned items are
  matched against resolved remedies under their own header, `held_by` in
  `--json`.
- `lessons/LEDGER.schema.yaml`: the cutoff pair, the two keys,
  `regression.pre_fix`, `redteam`. `.claude/skills/improve/SKILL.md` (step
  3½ keys 7-8, the fork on every working set, step 4.1 `pre_fix`, step 5
  notes), `references/triage.md`, `references/eval-loop.md` (the pre-fix
  run), new `references/redteam.md`; improve eval case 5 + `grade_E`.
- Red before the fix: `collect_selftest.py` 11 v2 assertions and an
  `AttributeError` on `written_by`; `cluster_selftest.py` 3 assertions.

## 1.9 (2026-09-15) — `lessons.py record-run` prints a `Check:` line naming `/sdlc:setup` when the installed helpers lag the running plugin

Ledger IMP-108 (2026-09-15 retro). The run record already stored `installed_version`; nothing told the user. `_smoke/lessons_selftest.py` pins the line.
Collector-side (repo `lessons/`, pinned in this skill's `_smoke/collect_selftest.py`): a re-sent lesson updates its inbox copy's count, severity and evidence instead of being dropped, and a reused `lsn_id` for a different lesson is quarantined (IMP-040, reopened); the digest's free-text rate is `m of n` runs of the skill, flagged at >=3 runs and >=50% (IMP-105).

## 1.8 (2026-09-12) — `lessons.py` dates a run record, and a lesson about the running skill, from the SKILL.md footer when the state file lags it (the state's number kept as `state_skill_version`); a migrated run records `skill_version_at_start`

Ledger IMP-095. `add` and `record-run` read `skill_version` from the named skill's
state file as "what ran", but the code ledger records the version that CREATED it
and nothing re-stamps it: every code lesson and run the consumer sent carried 0.3
while the skill was at 0.14, so `collect_lessons.py --delta` could date none of
them. An interview state IS re-stamped (the resume migration sets it), but a run
that spans an upgrade then has two truthful numbers and nothing recorded which:
one 35-hour test run closed at 1.12/0.9.10 while the lesson raised inside it says
1.9/0.9.7, and its `resumes: 0` hides that anything moved. Inside a running
skill the footer is what executes NOW: `record-run` (always at a skill's close,
inside it) and an `add` whose `--skill` is `$CLAUDE_SKILL_DIR`'s skill date from
the footer, keep the state's number as `state_skill_version`, and print one
`Check:` line; an `add` about another skill still trusts that skill's state file
(the version whose behaviour it observed). `record-run` also records
`skill_version_at_start` from `state.migrations[0].from`. `LESSONS.schema.yaml`
documents both fields. Regression: `_smoke/lessons_selftest.py` (version-skew
section). The code half - Phase 1 re-stamps the ledger - ships as code 0.15.

## 1.7 (2026-09-09) — A `where.file` prefixed with its own skill folder is normalized everywhere, never read as gone

`lessons.py add` strips a leading `<skill>/` (or `sdlc/skills/<skill>/`) from
`--where-file` and says so in its `Check:` line; `lesson_hints` on a stored
prefixed path names the prefix instead of sending the author to another
skill; `same_subject` (clustering) and the collector's `version_delta`
(dating) see through it. Seven of one collect's 34 lessons had been dated
"gone at HEAD" and split from their twins. Ledger IMP-041; regression
`_smoke/lessons_selftest.py`, `_smoke/collect_selftest.py`,
`_smoke/cluster_selftest.py`.

## 1.6 (2026-09-09) — One defect, one lesson, and a report that stands

One defect, one lesson, and a report that stands on its own. `lessons.py add`
now folds a repeat of a defect already in the queue into that lesson
(`occurrences`, `first_seen_at`, `last_seen_at`, `sent_at` cleared so the new
count travels) instead of writing a second entry; `--allow-duplicate`
overrides. Matching is on skill + `where.file` + what the anchor, evidence and
summary name, and deliberately NOT on `kind`, which two reports of one defect
routinely disagree on. The delivered report — the maintainer's only copy once
the plugin is published — gains a stable `project_uuid` (minted once, survives
a repo move, no guessable preimage; the legacy path-hash `project_id` still
travels so earlier reports reconcile — the id is MORE opaque than before, never
less, which is why /sdlc:setup's consent notice can now promise the project's
name never travels), the `environment` that raised it, and a truncation rule
that gives up runs no travelling lesson references before ones it does.
`metrics` filtering moves from a fixed allowlist, which silently dropped every
key added after it was written, to a shape rule: numbers and flags travel,
strings and structures never do. Regressions: `_smoke/cluster_selftest.py` (the
real collected corpus, including two pairs the maintainer had grouped by hand),
`_smoke/06_recurrence.yaml`, `_smoke/lessons_selftest.py` ("the delivered
report" section).

## 1.5 (2026-09-04) — Proper lessons, checked not refused

Proper lessons, checked not refused. `lessons.py add` prints a `Check:` line
after `[OK]` when the entry looks improper (file not in the skill folder —
naming the folder that has it —, kind/file mismatch, placeholder text, a
blocker that stopped nothing) and gains `--dry-run`, which this skill's step 2
runs on the draft. Hints never reject: a capture refused at a skill's close
phase is simply lost, the installed helpers can be older than the plugin the
check runs against, and an ambient call has no plugin to check against at all.
`skill_version` falls back to the installed plugin's SKILL.md footer (setup
keeps no state, so 8 of the first 23 collected lessons carried none), and
`installed_version` records the marker when it lags the plugin, so the
maintainer dates a lesson from the older number. Regression
`_smoke/lessons_selftest.py` ("proper lessons" section); collector side in
`_smoke/collect_selftest.py`.

## 1.4 (2026-09-04) — `lessons.py add` stops hiding its enums

`lessons.py add` stops hiding its enums: `--kind`, `--severity`,
`--agent-action` and `--generalizes` list their values in `--help`, and one
call now reports every bad value it was given instead of one per round-trip.
The repo-side collector splits the free-text telemetry by what a high rate
actually means — a question that forbids free text, a real signal, one the
agent invented, or one with no suggested answers at all — so the maintainer
stops triaging false signals. Ledger IMP-026/IMP-038; regression
`_smoke/lessons_selftest.py` + `_smoke/collect_selftest.py`.

## 1.3 (2026-09-03) — Opt-in automatic delivery

opt-in automatic delivery. `lessons.py` gains `consent`, `export --out/--send`,
redaction on the way out (absolute paths, e-mail addresses, `container_id`, an
allowlist over `metrics`, and an opaque `project_id` instead of the directory
name) and a batching policy: a `blocker` mails at the next skill close,
everything else waits 7 days or 10 lessons, stamped `sent_at` so nothing is
sent twice. The close card gains a `Sharing:` row. Regressions:
`_smoke/lessons_selftest.py` (redaction, the `send_due` truth table, the
delivery round-trip against a stand-in relay).

## 1.2 (2026-09-02) — This skill never writes `CLAUDE.md`

This skill never writes `CLAUDE.md`. That file belongs to `/sdlc:setup`; a
caveat is a typed `WRN-NNN`, a spec defect an `FND-NNN`, a skill defect an
`LSN-NNN`, and all of them surface in the generated
`.claude/rules/sdlc-statusboard.md`.

## 1.1 (2026-09-01) — Never-interrupt capture (ledger IMP-002)

never-interrupt capture (ledger IMP-002): mid-run observations defer to the
running skill's `lesson_notes` and its close self-review; self-invocation is
ambient-only (in-flight guard above); harness bugs with no skill reliance route
to the close card's `Attention:` block, never a mid-run stop. `lessons.py
record-run` gains repeatable `--metric key=value` and explicit resumes
semantics (IMP-004). Regressions: `evals/evals.json` cases 9-11,
`_smoke/lessons_selftest.py`.

## 1.0 — Initial: one-confirmation LSN capture + `lessons.py` queue writer

Initial: one-confirmation LSN capture + `lessons.py` queue writer.
