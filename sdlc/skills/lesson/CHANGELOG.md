# lesson — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

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
