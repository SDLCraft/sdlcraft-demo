# Committing the run: the auto-commit close step

Canonical for CLAUDE.md 20. Every skill's close phase runs the step below and
points here; nothing restates it.

## The setting

`/sdlc:setup` asks once whether every `/sdlc:*` run should commit its own files
when it finishes, and stores the answer in `.claude/sdlc/sdlc-plugin.json`
under `auto_commit` (`mode: on | off`, seeded `off`; `decided_on` is the date
the user answered). A re-run of `setup` carries the block forward verbatim. No
other skill ever asks the question: a skill reads the answer through the helper
and does what it says.

- `python .claude/sdlc/autocommit.py mode` prints the current mode and whether
  the project is a git repository; `mode --set on|off` changes it.
- `SDLC_AUTO_COMMIT=on|off` in the environment overrides the stored mode for
  one session or a CI job.
- Helper absent (the project never ran `/sdlc:setup`, or ran an older one):
  skip the step silently. There is nothing to read and nothing to commit.

## When

The commit is the **last action** of the close phase, on **every exit path**:
after the state file is set `complete` or `aborted`, after the findings drain
and `lessons.py record-run` (the last writes of the run), and **before the
close card** is printed — the helper's one printed line is the card's
`Commit:` row. An `EXIT` mid-interview commits too: the draft on disk is work,
and the summary says it is a draft.

`code` runs it once more at every **container boundary** a bare run continues
past — after that container's ring, doctor check and ledger write, before the
continue/stop gate — so a run that builds three containers leaves three
reviewable commits and a close that usually has nothing left to commit.

```bash
python .claude/sdlc/autocommit.py commit --skill <skill> \
  --invocation "<the command as typed>" \
  --summary "<one line: what changed, in the user's words>"
```

## The subject: `<invocation> → <summary>`

The separator is ` → ` (U+2192, one space each side). It is never `: ` — the
invocation carries its own colon (`/sdlc:data`) — and no human types an arrow
into a subject, so the arrow marks the commit as automatic and
`git log --grep='→'` lists exactly the pipeline's commits. The helper inserts
it; you pass the two halves.

**`--invocation`** is `/sdlc:<skill>` plus `$ARGUMENTS` exactly as the user
typed them, whitespace collapsed, flag spelling kept (`-d` stays `-d`):

- typed `/sdlc:test aicf-cli --reconcile` → `/sdlc:test aicf-cli --reconcile`
- typed `/sdlc:code` and the run auto-advanced into a container → `/sdlc:code`
  (the summary names the container; the dispatch inferred it, the user did
  not type it — the same rule keeps a remembered `--parallel` off the subject)
- invoked in natural language, no slash command → the canonical form the
  dispatch resolved to (`/sdlc:arch --system`)
- never include arguments the dispatch rejected.

**`--summary`** is one line, at most about 80 characters, in the vocabulary
CLAUDE.md 14 prescribes for the terminal: the artifact and its version, what
happened to it, and the container / finding / unit it concerns. Counts are
welcome when the reader can act on them. Examples, one per form:

| Run | Subject |
|---|---|
| `/sdlc:prd` | `/sdlc:prd → PRD 1.0 written - 14 features, 31 requirements (complete)` |
| `/sdlc:prd`, EXIT mid-interview | `/sdlc:prd → aborted at theme users_and_personas - draft saved` |
| `/sdlc:data --reconcile` | `/sdlc:data --reconcile → DATA-MODEL 2.3 reconciled against PRD 1.4 - ENT-014 added, ENT-003 updated` |
| `/sdlc:arch --system` | `/sdlc:arch --system → ARCH 1.0 written - 4 containers, build order set` |
| `/sdlc:arch -d` | `/sdlc:arch -d → ARCH 1.1 dependency edges derived - 12 edges, 0 cycles` |
| `/sdlc:test aicf-cli` | `/sdlc:test aicf-cli → TEST-STRATEGY__aicf-cli 1.0 written - 41 tests (complete)` |
| `/sdlc:task` (auto-advanced) | `/sdlc:task → TASKS__aicf-cli 1.0 written - 87 tasks, validator green` |
| `/sdlc:code` at a container boundary | `/sdlc:code → container aicf-cli built - 23 units green` |
| `/sdlc:code --step` | `/sdlc:code --step → aicf-cli/cli/parse_args implemented and green` |
| `/sdlc:code aicf-cli`, stopped at a gate | `/sdlc:code aicf-cli → stopped at component prompt-registry - 2 units blocked` |
| `/sdlc:repair FND-003` | `/sdlc:repair FND-003 → DATA-MODEL 2.4 - ENT-007 status enum fixed; FND-003 resolved` |
| `/sdlc:repair --check` | `/sdlc:repair --check → 2 findings recorded, nothing edited` |
| `/sdlc:lesson` | `/sdlc:lesson → LSN-NNN recorded - instruction_gap in sdlc-data` |
| `/sdlc:setup` | `/sdlc:setup → plugin 0.9.15 wired - helpers, rules, docs hook, INDEX.yaml` |

## What is staged

Only the files the running skill owns — never a blanket sweep of `docs/`, and
never `git add -A`. The helper carries the table; `--paths` adds a file a run
wrote outside it.

| Skill | Its own files, plus the common set |
|---|---|
| every artifact skill | its artifact and shards (`docs/API.yaml` + `docs/API__*.yaml`, …), `docs/INDEX.yaml`, `.claude/skills-state/sdlc-<skill>.state.yaml`, the findings and lessons queues, `.claude/rules/sdlc-statusboard.md`, `.claude/sdlc/STATUS.md`, the marker |
| `arch` | also `.claude/skills-state/sdlc-arch.derivation-report-*.yaml` |
| `code` | `docs/CODE-MANIFEST.json`, the ledger, `sdlc-code/inflight/` and `stuck/`, and every generated file the ledger's `files_written` and the manifest name — never `packets/` or `stack/` (regenerable caches) |
| `repair` | every artifact under `docs/` (it edits whichever holds the defect and re-slices task shards), its state file and doctor report — never `code`'s ledger |
| `lesson` | only the lessons queue and the marker — it is model-invocable in ambient sessions and must never sweep a hand edit |
| `setup` | `.claude/sdlc/`, `.claude/rules/sdlc-*.md`, `docs/INDEX.yaml`, the lessons queue, `CLAUDE.md`, `.claude/settings.json` |

A gitignored path is never added (the helper asks `git status`, which never
lists ignored files). A file the user had staged outside the set stays staged
and uncommitted. A hand edit to another artifact is left where it is and
counted on the printed line.

## Outcomes → the `Commit:` row

The helper prints exactly one line. Put it, in the user's words, on the card:

| The helper printed | The row |
|---|---|
| `[OK] committed a1b2c3d - /sdlc:api → API 1.0 written … (4 files)` | `Commit:    a1b2c3d  /sdlc:api → API 1.0 written - 12 resources` |
| `[OK] nothing to commit - …` | `Commit:    nothing to commit` |
| `[OK] auto-commit is off …` | no row (the project chose not to) |
| `[DRAFT] not committed - <reason>. Nothing is lost: …` | `Commit:    not committed - <reason>; N files staged, commit by hand` and one `Attention:` clause |
| helper absent | no row |
| ` · N other pipeline file(s) … left uncommitted` suffix | add it to the row: the user should know a hand edit is sitting there |

A `[DRAFT]` here is a fact about the environment (no identity configured, a
hook refused, not a repository) — never a lesson, never a finding, never a
reason to retry by hand inside the run.

## Boundaries

- **Never a gate.** Git state is an observation for the report, never a
  precondition of any phase — the `code`, `task` and `repair` rules that say a
  dirty tree is no reason to refuse stand unchanged. A failed commit is one
  line; the run's own verdict (`[OK]`/`[DRAFT]`/`[FAIL]`) never changes because
  of it.
- **Never push**, never amend or rebase, never `--no-verify`, never an empty
  commit. Hooks run and may refuse; the helper reports that and leaves the
  files staged.
- **The helper is the only git writer.** No skill runs `git add` or
  `git commit` itself, and no skill asks the auto-commit question — that is
  `setup`'s, once.
- **Attribution.** If the harness running the skill asks for an attribution
  line on commits it makes (a `Co-Authored-By:` trailer), pass it as
  `--trailer "Co-Authored-By: …"`; the helper appends it after the subject.
