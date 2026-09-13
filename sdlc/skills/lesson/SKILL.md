---
name: lesson
description: >
  Record a lesson about an sdlc SKILL that misbehaved — an instruction gap, a
  validator verdict the user says was wrong, a redundant or outdated interview
  question, a bundled script that failed. Trigger on /sdlc:lesson, on any
  user complaint about an sdlc skill's behaviour, and on your own observation
  of a raising condition in a project using the sdlc plugin — the same
  skill-caused friction recurring, or redoing work because a skill
  instruction misled you. The user cannot know when to invoke this; noticing
  is your job. Never self-invoke mid-run inside another /sdlc:* skill run —
  note the observation to that run's state-file lesson_notes instead
  (references/lessons-capture.md). Not for defects in this project's docs/ — those are findings
  (/sdlc:repair).
user-invocable: true
disable-model-invocation: false  # sanctioned exception (CLAUDE.md 15): in an
                                 # AMBIENT session the agent records a skill
                                 # defect the moment it sees one. Inside a
                                 # running /sdlc:* skill this flow is never
                                 # self-invoked - mid-run observations go to
                                 # the state file's lesson_notes (references/
                                 # lessons-capture.md)
model: sonnet
effort: medium
allowed-tools: Read Bash Bash(python *) Bash(ls *) Glob Grep AskUserQuestion
---

# sdlc-lesson

Captures the moment right after an sdlc skill annoyed the user — while the
evidence is still in this conversation. The output is one structured `LSN-NNN`
entry in `.claude/skills-state/sdlc-lessons.yaml`, written for the plugin
MAINTAINER, who collects these across projects and fixes the skill. Nothing in
this project changes and nothing downstream reads the entry — recording is the
whole job.

Like `setup`, this skill is **exempt from the interview contract** (no themes,
no questions file): one confirmation, one append. This exemption and the
queue's ownership are documented in CLAUDE.md 15.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — the flow. |
| `LESSONS.schema.yaml` | Canonical schema for `.claude/skills-state/sdlc-lessons.yaml`, with per-field rationale. |
| `lessons.py` | The queue's only writer (also what `/sdlc:setup` installs to `.claude/sdlc/lessons.py`). This skill calls its own copy, so it works in projects that never ran setup. |
| `references/lessons-capture.md` | The doctrine: routing table, closed raising conditions, sanitization. Canonical for every skill; load it in step 2. |

## Flow

**Guard — is an `/sdlc:*` run in flight?** If this session is mid-way through
another sdlc skill's run and the USER did not explicitly type `/sdlc:lesson`,
do not run this flow: append the observation to that run's `lesson_notes`
(`references/lessons-capture.md` → "Mid-run: note now, record at close") and
return to the interrupted step. An explicit user invocation is always
honoured — record, then hand straight back to the interrupted run.

### 1 — Find the episode

The lesson is almost always about what just happened. Gather, without asking
the user anything yet:

- this conversation's own record of what the user reacted to;
- the most recent skill run: newest `last_updated` across
  `.claude/skills-state/sdlc-*.state.yaml` (a sharded file's newest
  sub-session counts) — it names the skill, `session_id`, `skill_version`.

If the user's message names a different skill or an older episode, follow
that instead.

### 2 — Route and draft

Load `references/lessons-capture.md`. First the routing question: **is the
wrong thing in this project's `docs/`, or in the plugin's files?**

- `docs/` → decline politely: that is a finding — point at `/sdlc:repair`
  (or a `WRN` deferral in the owning artifact) and stop. Do not record.
- Nothing actually wrong (the user is asking a question, or venting about the
  project itself) → say so and stop. An empty queue is better than a noise
  entry.
- The plugin → draft the entry: `kind` (the closed enum), `severity`,
  `where.file` (a file inside the skill's folder — if you cannot name one,
  ask for the one missing fact in step 3), `where.anchor` (phase / check
  number / question id), a one-line `summary`, 1–5 evidence lines
  (sanitized: skill locations, ids, counts — never verbatim project content),
  `agent_action` if the episode shows one, `suggested_fix` if the user
  offered one. Then run the step-4 command with `--dry-run` appended: it
  writes nothing and prints a `Check:` line when the entry looks improper —
  the file is not in that skill's folder (it names the folder that has it),
  the kind does not fit the file, the text reads like a placeholder, a
  `blocker` that stopped nothing. Fix the draft before asking; the
  confirmation should show the corrected entry
  (`references/lessons-capture.md` → "A proper lesson").

### 3 — Confirm (at most one question)

One `AskUserQuestion`: present the drafted kind + where + summary as the
recommended option, with alternatives when the classification is genuinely
ambiguous — or ask for the single missing fact. Free-text `EXIT` aborts
without writing (there is no state to save).

When you invoked this skill yourself (no explicit user complaint), this
confirmation is mandatory — it is the noise gate on self-triggering.

### 4 — Write

```bash
python "${CLAUDE_SKILL_DIR}/lessons.py" add --raised-by user --skill <skill> \
  --kind <kind> --severity <severity> --summary "<one line>" \
  --evidence "<line>" [--evidence "<line>" ...] \
  --where-file <file> [--where-anchor <anchor>] \
  [--agent-action <action>] [--suggested-fix "<one line>"] \
  [--related FND-NNN] --plugin-root "${CLAUDE_SKILL_DIR}/../.."
```

The helper mints the id, stamps versions (the skill's state file, else the
installed plugin's SKILL.md footer; the marker's version too when the
installed helpers lag the plugin), validates the shape, and rejects
unsanitized input — relay a rejection's message, fix the flag, retry once. A
`Check:` line after `[OK]` is a hint the dry run should already have
addressed; never re-record to answer one — that makes a duplicate.

### 5 — Close

```
-- /sdlc:lesson - recorded ---------------------------
Wrote:     LSN-007 about /sdlc:test (question_quality, degraded)
Status:    for the plugin maintainer - nothing in this project changes
Sharing:   held for the next batch (this project shares lessons automatically)
Next:      nothing to run - the maintainer collects this file
```

Compute the rows from what actually happened (CLAUDE.md 14); when the routing
declined, say what the right channel is instead of a `Wrote:` row. When a
skill run is in flight (user-invoked capture mid-run), `Next:` instead names
the interrupted run's resumption — the recording is a detour, the run is the
job.

The `Sharing:` row reports what `lessons.py add` already did — it sends
nothing itself, and you never run a second command to make it send. Read the
line the helper printed and say it in the user's terms:

| What happened | The row says |
|---|---|
| sharing is off (the default) | `not shared - to send it: python .claude/sdlc/lessons.py export` |
| sharing is on, batch not due | `held for the next batch (7 days, or sooner if more arrive)` |
| sharing is on, a blocker or a due batch went | `sent to the plugin maintainer just now` |
| sharing is on, the send failed | `not sent (<reason>) - kept, and retried at the next close` |

Sharing is **opt-in**, chosen once at `/sdlc:setup` and stored in
`.claude/sdlc/sdlc-plugin.json`. If the user asks about it — where their
lessons go, or how to stop — point them at `python .claude/sdlc/lessons.py
consent` (prints the setting) and `consent --set off` (stops it). Never turn
it on for them: this skill records, it does not decide what leaves their
machine.

**This skill never writes `CLAUDE.md`.** That file belongs to `/sdlc:setup`, which
writes one static `## SDLC Documents` block. Never add a section, a bullet, a
note, an id, a status, a caveat or a resolution there — a caveat is a typed
`WRN-NNN` in the artifact it is about, a spec defect is an `FND-NNN`, a skill
defect is an `LSN-NNN`, and all of them surface, generated, in
`.claude/rules/sdlc-statusboard.md`.

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.8"
