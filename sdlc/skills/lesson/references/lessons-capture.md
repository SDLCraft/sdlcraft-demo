# Capturing lessons — when the SKILL is what is wrong

Canonical for CLAUDE.md §15. Every SDLC skill references this file rather than
restating it. It defines when the agent running an sdlc skill records a
**lesson** — an `LSN-NNN` entry in `.claude/skills-state/sdlc-lessons.yaml` —
what goes in one, and what must never become one. Schema with per-field
rationale: `sdlc/skills/lesson/LESSONS.schema.yaml`. The only writer is
`python .claude/sdlc/lessons.py` (installed by `/sdlc:setup`); if it is not
installed, skip lesson/run recording silently — never block a skill run on it.

## Who reads this

The agent running ANY sdlc skill — at the close phase (the self-review below);
mid-run, a raising condition produces a `lesson_notes` entry in the state file,
never an immediate recording (see "Mid-run: note now, record at close" below).
Also `/sdlc:lesson`, the capture skill (typed by the user, or self-invoked by
an agent in an AMBIENT session — never from inside a running skill), and any
agent in a consumer project pointed here by `.claude/rules/sdlc-lessons.md`.

## The routing question

One question decides the channel: **is the wrong thing in this project's
`docs/`, or in the plugin's files?**

| What is wrong | Channel | Why |
|---|---|---|
| An upstream artifact's content (a contract, a test spec, a path, an id) | `FND-NNN` finding (schema: `sdlc/skills/repair/FINDINGS.schema.yaml`) — `/sdlc:repair` fixes it | The defect lives in this project; repair localizes and edits `docs/` |
| Your own artifact legitimately omits an upstream item | `WRN-NNN` deferral in the owning artifact | Coverage stays honest inside the project |
| A test that is simply red | Neither — that is a `failed` task | A queue full of ordinary failures is a queue nobody reads |
| A SKILL's instruction, question, validator check, schema, script, or printed message | `LSN-NNN` lesson — the plugin maintainer fixes the SKILL | The defect lives in the plugin; nothing in this project can fix it, and a workaround here leaves it for the next project |

Two hard corollaries:

- **Never bend a validator to accept a consumer artifact**, and never patch any
  plugin file from inside a consumer project. The demo-corpus doctrine
  (`sdlc-demo-docs-findings.md`) states it for the maintainer's own dogfood
  project, and it holds everywhere: fix (or consciously waive) the artifact, or
  record a lesson — a validator hand-bent to one project is broken for all.
- A finding and a lesson can describe the same episode: when `/sdlc:repair`'s
  localization walk ends at "the skill never emits the field this needs", the
  finding closes `wontfix` and the lesson carries `related_findings: [FND-NNN]`.

## Mid-run: note now, record at close

**Capture never ends, aborts, or pauses an in-flight skill run.** No
observation — not a raising condition, not a harness bug, not a user aside —
is worth an interrupted interview: an aborted run records nothing at all,
which is strictly worse than a deferred note.

When a raising condition fires while an `/sdlc:*` skill run is in flight:

1. **Note it**: append one entry to the `lesson_notes:` list at the top level
   of the running skill's state file, in the same write-after-every-batch
   cadence (never a separate write — the note must survive compaction, resume,
   and death exactly like every other answer). Entry shape:
   `{noted_at: <iso8601>, about: <skill-slug or "harness">, kind_guess: <kind
   enum or "harness">, note: "<one line, sanitized, <= 200 chars>"}`. The note
   obeys the same sanitization contract as evidence (below).
2. **Say at most one line in chat** ("Noted a skill defect for the close
   report.") — or nothing.
3. **Continue the interrupted step immediately** — re-issue the batch or
   action you were about to run.

Recording happens at the close-phase self-review (below), which drains
`lesson_notes` on EVERY exit path — completion, EXIT/abort (the
`record-run --outcome aborted` moment), and failure alike. The full
`/sdlc:lesson` flow — its confirmation question included — is reserved for
ambient sessions (no sdlc skill run in flight) and for explicit user
invocation. Mid-run, the state-file note IS the capture.

## Raising conditions — a closed set

Record a lesson when — and only when — one of these fires:

**About the instructions**
1. You had to **improvise outside the instructions**: SKILL.md and its
   references did not cover the situation you actually hit, and you did
   something no instruction describes.
2. **Two instructions contradicted each other**, or an instruction contradicted
   what a bundled script actually does.

**About validators and schemas**
3. A skill's validator **rejected an artifact the user confirmed legitimate**
   (you or the user had to waive or work around a check).
4. A downstream skill **rejected an upstream artifact its own validator had
   passed** as `complete` (raise it about the UPSTREAM skill).
5. A downstream skill **needed a field the upstream output schema does not
   have** (`schema_gap`, about the upstream skill).

**About scripts and the platform**
6. A bundled script **exited 2 or 3, or produced a wrong result**, or a
   command a SKILL.md documents **failed on this platform**.

**The user said so**
7. The user said an interview question was **irrelevant, redundant with
   upstream data, or asked for a deprecated field** (`question_quality`).
8. The user **explicitly complained about the skill's behaviour** — record
   their observation with `--raised-by user`, whatever its kind.

**The repeated-work signal**
9. You **wrote an ad-hoc helper script** to do something the skill describes
   only in prose. If every run has to write the same script, the skill should
   bundle it (`suggested_fix` says so).

**Recurrence and self-correction**
10. The **same friction recurred within this run** (twice or more) and traces
    to a plugin file: two artifacts tripped the same ambiguous check, two
    phases hit the same missing instruction, the user re-explained the same
    thing because the interview re-asked it. Across runs, recurrence is the
    maintainer's clustering job; within a run, it is your signal.

    You do not have to check whether this project already recorded it: `add`
    compares a new lesson against the queue and, when it is the same defect
    (same skill, same file, same thing named), bumps that lesson's
    `occurrences` and folds in any new evidence instead of writing a second
    entry. It says so when it does. That count is what ranks the defect for
    the maintainer, so a repeat worth recording is worth recording even
    though one already exists — it is not a duplicate, it is the second data
    point. If the match is wrong (a different defect that happens to live in
    the same file), re-run with `--allow-duplicate`.
11. You **confidently followed an instruction, produced something wrong, and
    had to redo it** — and the correction shows the instruction (not the
    project) misled you. Ordinary iteration on the user's content feedback is
    NOT this, and a `code` heal-loop attempt is NOT this — those are the work.
    Kind: `instruction_gap` or `instruction_conflict` — the defect IS the
    instruction; reserve `process` for flow/ordering problems in how the
    skill runs, not for a wrongly-documented step.

Nothing else. This list is closed on purpose: a lessons queue that fills with
every rough edge is a queue nobody reads. A red test is a `failed` task; a
wrong artifact is a finding; only a defective SKILL is a lesson.

## What is NOT a lesson

- Anything whose fix lives in this project's `docs/` — route per the table.
- A project quirk the skill handled correctly, even if awkwardly.
- A preference ("I'd have asked fewer questions") with no concrete episode —
  the run metrics already carry that signal.
- Anything you cannot pin to a plugin file: **if you cannot name the skill
  file in `where.file`, it is not a lesson yet.** Two sub-cases: (a) a broken
  platform/harness behaviour that a SKILL instruction **relies on** — the
  lesson is about that instruction (`where.file` = the skill file that relies
  on it; the harness detail goes in the evidence); (b) a pure harness/product
  bug no skill instruction relies on — NOT a lesson: give it one line in the
  close card's `Attention:` block (and use the platform's native feedback
  channel if one exists). Never a mid-run stop, never an ask-the-user detour.

## The entry

`lessons.py add` mints the id, stamps versions, and validates the shape. One
call per lesson:

```bash
python .claude/sdlc/lessons.py add --skill test --kind schema_gap \
  --summary "TEST-STRATEGY has no slot for naming shared fixtures" \
  --evidence "3 TSTs each restated the same fixture in prose" \
  --where-file TEST-STRATEGY.schema.yaml --where-anchor shared_infrastructure \
  --severity degraded --agent-action worked_around --generalizes yes
```

- `--skill` is the skill the lesson is ABOUT (a downstream skill often raises
  about an upstream one). `raised_by` is derived from `$CLAUDE_SKILL_DIR`;
  pass `--raised-by user` when relaying the user's own complaint, and the
  `code` manager passes `--raised-by sdlc-code-worker` when relaying a worker's
  `LESSON:` line.
- `--where-file` is a path INSIDE that skill's folder (`SKILL.md`,
  `references/x.md`, `validate_schema.py`, `<skill>-questions.yaml`);
  `--where-anchor` a phase name, check number, or question id.
- `--related FND-NNN` links the finding whose diagnosis surfaced it.
- `skill_version` is stamped from the named skill's own state file (what
  actually wrote what you observed), never overridden by the installed
  footer — except a ledger-shaped state (`code` today), which nothing
  re-stamps between runs: there the installed footer, when it disagrees, is
  recorded alongside as `footer_skill_version` rather than replacing the
  ledger's number.
- Severity: `blocker` = the run could not finish correctly; `degraded` =
  finished with rework or friction; `cosmetic` = polish. On a project that
  opted in to sharing, severity also decides **when** the lesson reaches the
  maintainer: a `blocker` is mailed at the next skill close, the other two ride
  a weekly batch. Do not reach for `blocker` to be heard sooner — the whole
  value of the queue is that the word still means what it says.

### A proper lesson

The maintainer triages hundreds of these without the project in front of
them. Four things make an entry actionable, and the helper checks each one
mechanically — as a `Check:` line printed after `[OK]`, never as a rejection
(a rejected capture at a skill's close phase would simply be lost):

- **The file exists in that skill's folder.** The installed names invite the
  wrong `--skill`: `lessons.py` lives in `lesson/`, `findings.py` in
  `repair/`, `docs_index.py` in `setup/`. The check names the folder that has
  it. If you are sure the file existed in the version you ran (the helpers
  installed here can be older than the plugin), say so in the evidence.
- **The kind fits the file.** A `script_bug` names a `.py`; a `schema_gap`
  names a `*.schema.yaml`; a `question_quality` names
  `<skill>-questions.yaml` with the question id in the anchor; an
  `instruction_gap` names `SKILL.md` or a `references/*.md`.
- **The evidence is judgeable without the project.** Ids, counts, skill
  locations, the exact message — never "test", never the summary repeated.
- **`blocker` means the run stopped.** It also sends at the next close.

`add --dry-run` runs the same checks and writes nothing — the `/sdlc:lesson`
flow uses it on the draft, before its one confirmation. The close-phase
self-review calls `add` directly and reads the `Check:` line; an entry is
never re-recorded to fix a hint (that makes a duplicate) — the maintainer sees
the same checks in the digest and corrects the kind or file there.

## Sanitization

A lesson travels to the skillset maintainer — possibly by email, possibly from
someone else's project, possibly **on its own**, without anyone reading it
first. Evidence therefore carries **skill file locations, id families, and
counts** — never verbatim project content, never absolute paths, never secrets.
The helper enforces the mechanical half (relative `where.file`, no `docs/`,
evidence lines <= 200 chars); you own the judgment half: "the user picked Other
on 4 of 5 runs" travels, the user's actual answers do not.

`lessons.py` redacts a second time on the way out — absolute paths and e-mail
addresses become `<path>` / `<email>`, `container_id` is dropped, `metrics` is
cut to an allowlist, and the project appears only as an opaque `project_id`.
**Write as if that layer were not there.** It is a net for the mistake you did
not notice, not a licence to paste project content into evidence: it cannot
tell a leaked customer name from a legitimate one, and it never sees what you
chose not to write.

## Delivery

Nothing leaves a project unless someone said it may. `/sdlc:setup` asks once
and stores the answer in `.claude/sdlc/sdlc-plugin.json`; the default is
**off**, and `SDLC_LESSONS_TELEMETRY=off` overrides everything.

When sharing is on, `lessons.py` mails the unsent entries at a skill **close**
— `record-run`, `/sdlc:lesson`, or an explicit `export --send`. Three rules
matter to you as the agent recording a lesson:

- **A send never happens mid-run.** If you are inside a running skill, note the
  observation to that run's `lesson_notes` as always; delivery is a
  consequence of the close, never a reason to pause.
- **A failed send is never a failed run.** It prints one `[DRAFT]` line, keeps
  the batch, and retries at the next close. Do not treat it as an error worth
  a lesson of its own.
- **Delivery is not triage.** A sent lesson is still `status: open`; `sent_at`
  only records that this machine handed it over. The maintainer's verdict
  comes back on its own: the installed plugin ships `VERDICTS.yaml`, and
  `record-run` stamps it at every skill close (`triaged` / `resolved` with
  its `fixed_in` / `wontfix` / `dismissed`; `lessons.py list` shows each).
  A lesson you record again after its fix is reopened, not duplicated — the
  helper keeps the old verdict beside the new sighting so the maintainer
  sees the fix regressed. Never set a verdict by hand.

If the user asks where their lessons go, or asks to stop sending: `python
.claude/sdlc/lessons.py consent` prints the current setting, and
`consent --set off` stops it for good.

## End-of-run self-review (every skill, close phase)

Before the close card:

0. **Drain `lesson_notes`** from the state file first: an entry with a
   plugin-file `about` is a pre-answered yes (it already names its raising
   condition and file) and becomes a `lessons.py add`; an `about: harness`
   entry becomes one `Attention:` clause in the close card, never a lesson.
   After the `add` calls, clear the drained entries (or mark them
   `drained: true`) in the same state write that sets the final `status`.

Then answer six questions for anything not yet noted:

1. Did I improvise outside the instructions anywhere?
2. Did a bundled script or documented command fail?
3. Did the user push back on the skill itself — a question, a check, a message?
4. Did a validator fight an artifact the user confirmed was right?
5. Did the same problem bite twice this run?
6. Did I redo my own work because an instruction pointed the wrong way?

Each **yes** that matches a raising condition becomes one `lessons.py add`.
Cap: at most 2 lessons per run unless one is a `blocker` — pick the two with
the clearest evidence; the rest can wait for the run where they recur (and a
recurring lesson ranks higher for the maintainer anyway). Drained notes
count toward the same cap; a `blocker` still lifts it.

Then record the run itself (metrics come from the state file; nothing to
compose by hand):

```bash
python .claude/sdlc/lessons.py record-run --skill <skill> --plugin-root "${CLAUDE_SKILL_DIR}/../.."
```

## The close card

Add a `Lessons:` row ONLY when this run captured something — recorded
lessons and/or noted harness observations:

```
Lessons:   1 recorded (LSN-NNN) - about this skill, for its maintainer;
           noted 1 harness observation (see Attention:) - nothing for you
           to do
```

Nothing captured: no row. Never print "no lessons".

## Cost contract

The helper is best-effort infrastructure. A non-zero exit becomes one
`Attention:` clause in the close card and is never retried in a loop, never a
stop. If `.claude/sdlc/lessons.py` does not exist (the project never ran
`/sdlc:setup`), skip recording without comment. The whole loop — self-review,
zero-to-two `add` calls, one `record-run` — is a few hundred tokens against a
run of tens of thousands; if it ever costs more than that, that itself is a
`process` lesson about this file. The mid-run half is even cheaper: one
state-list append and at most one chat line; the run continues, and the
report prints when the run naturally ends.
