# api — skill changelog

Maintainer-facing history for `SKILL.md`. Never loaded into an agent's
context. `/improve` reads it through `python lessons/collect_lessons.py
--delta <slug>/LSN-NNN` to judge whether a collected lesson predates its
fix, so each entry's one-line summary is the answer to "did a later
version address this?". Newest first; the top version must equal the
`skill_version` at the end of `SKILL.md` (`lint_skill_versions.py`).

## 1.10 (2026-09-15) — Phase 7 stamps provenance through `docs_index.py --stamp` over every file read, `UX__<surface>.yaml` shards included, instead of a hand-written sha-only entry for the three canonicals

Ledger IMP-102 (aicf LSN-083, the arch lesson's sibling sweep): the write paragraph told the
agent to hand-write `{file, session_id, last_updated, sha256}` for PRD, UX and DATA-MODEL - a
sha-only stamp with no items map, so every `--drift` on API.yaml fell back to git or the
residue, and the UX__ shards this skill reads were never recorded. Same fix as arch 1.17; each
`API__<resource>.yaml` written this run is stamped the same way.

## 1.9 (2026-09-11) — `/sdlc:api --reconcile`: the upstream-change review alone, no interview; the `--drift` code fence no longer swallows the statusboard paragraph

New `Invocation dispatch` section (the skill took no arguments before).
`--reconcile` follows the canonical form in
`ux/references/upstream-reconciliation.md`: a new resource gets its
`API__<resource>.yaml` through the per-resource drill; another `api_kind` or
transport style is structural. The input-adequacy gate leaves out re-invoke
findings owed to `docs/API.yaml`, and the restated `Next:` procedure gains the
reconcile-chain rule. The "Refresh the statusboard" paragraph had been pasted
inside Phase 2's `--drift` bash fence, where it read as a command; it moves to
Phase 8.

## 1.8 (2026-09-04) — The typed-`WRN` note names `resolution` as REQUIRED once resolved

The typed-`WRN` note now lists `resolution` and says it is REQUIRED once
`status: resolved`. Without it `warning_item.py` forces the warning back to
`open`, so a warning the user believes they closed silently never leaves the
statusboard while the artifact still validates. Ledger IMP-027; regression
`lint_claude_md.py`.

## 1.7 (2026-09-02) — This skill no longer writes `CLAUDE.md`

This skill no longer writes `CLAUDE.md`. `set_claude_md_pointer.py` is deleted
and the `Write(CLAUDE.md)` grant is gone: `/sdlc:setup` owns that file and
writes one static `## SDLC Documents` block, so the per-skill bullet and its
`Last updated by … on <timestamp>` tail — rewritten on every run, read back by
nothing — are retired. Phase 8 now refreshes `docs/INDEX.yaml` **and**
`.claude/rules/sdlc-statusboard.md` instead. Warnings may be written in the
typed `WRN` form (`{id, text, kind, status, impact, refs?, defers?,
resolution?, resolved_on?}`, CLAUDE.md 2). `resolution` is REQUIRED once
`status: resolved` - without it `warning_item.py` forces the warning back to
`open`, so it silently never leaves the statusboard while the artifact still
validates. Legacy `"WRN-NNN: <text>"` strings stay valid forever and read as
`{kind: note, status: open, impact: local}`.

## 1.6 (2026-09-01) — Structural `deferrals` drive both coverage gates

pipeline-review pass: structural `deferrals: [{id, reason}]` drive both
coverage gates (a bare id in `non_api_features` still passes for one more
version and is reported); `internal: true` resources may keep empty trace lists
(waiver warned); validator gains the provenance-staleness WARNING and
absent-upstream honesty (never zeros as a pass); Phase 2 gains the
`docs_index.py --drift` upstream-drift check, the input-adequacy gate (open
findings + blocking PRD open questions) and the `--refs`-before-rename rule;
findings capture wired per CLAUDE.md 13 (`finding_notes` drain + auto-raised
`upstream_incomplete` at close, cap 3/run); state declares `lesson_notes` /
`finding_notes` / `delta_review` / `dropped_candidates` / `input_adequacy`;
sibling validator calls use `"${CLAUDE_SKILL_DIR}/../<skill>/"`; close card
computes a `Findings:` row and the open-findings Next rule. Regression:
`_smoke/10_deferral_coverage`, `_smoke/11_provenance_warning`,
`_smoke/output_honesty_selftest.py`.

## 1.5 (2026-09-01) — PRD 1.1 propagation: list-aware `api_kind` derivation

PRD 1.1 propagation: list-aware `api_kind` derivation; `errors.localisation`
pre-filled from PRD.internationalization; `auth_model: mtls` → `auth.schemes`;
glossary drives resource/operation naming; `localized_fields` DTO rule. Also:
`set_claude_md_pointer.py` keeps the consumer CLAUDE.md's own line endings (LF
or CRLF) on every write — it used to rewrite the whole file in the host's
newline on a timestamp-only update (ledger IMP-006, aicf/LSN-002; regression
sdlc/skills/task/_smoke/pointer_selftest.py runs every skill's copy).

## 1.4 (2026-09-01) — Self-review pointer de-drifted

self-review pointer de-drifted (the canonical questions live in
lessons-capture.md, no longer counted here) + `lesson_notes` drain wired at
close (CLAUDE.md 15, ledger IMP-002); per-resource approval drafts and the
announce recap ride inside the AskUserQuestion call (channel rule, ledger
IMP-005; regression: evals/evals.json case 3).

## 1.3 (2026-08-31) — Lessons capture wired (CLAUDE.md 15)

Lessons capture wired (CLAUDE.md 15): the `metrics` telemetry block rides along
in every state write, Phase 8 runs the close self-review from
`sdlc/skills/lesson/references/lessons-capture.md` and records the run via
`.claude/sdlc/lessons.py` (best-effort — an absent helper or non-zero exit
never blocks), and EXIT records `--outcome aborted`.

## 1.2 (2026-08-27) — Terminal output rewritten for the person running the pipeline

Terminal output rewritten for the person running the pipeline (CLAUDE.md 14):
three verdict tags (`[OK]` / `[DRAFT]` / `[FAIL]`, never `[OK]` above blocking
errors), one `WARNINGS` section that states it does not block, same-class
findings grouped into one line, internal ids and check codes moved out of the
message subject, and a closing `NEXT:` block naming the exact command. Phase 8
now ends with a close card the agent fills in — translated, never pasted
validator output.
