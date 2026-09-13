# SDLC lessons — when a skill (not your project) misbehaves

Something an `/sdlc:*` skill did was wrong — its instructions, a question, a
validator verdict the user confirmed was mistaken, a bundled script — and NOT
this project's `docs/`? That is a **lesson** for the plugin maintainer, and
recording it is the AGENT's job — the user cannot know this channel exists.
Never fix it silently or work around it unrecorded:

- The moment you notice it — the same skill-caused friction recurring and
  redoing work because an instruction misled you both count — capture it.
  How depends on whether an `/sdlc:*` skill run is in flight:
  - **No run in flight (ambient session):** invoke `/sdlc:lesson` or run
    `python .claude/sdlc/lessons.py add --skill <skill> ...` now.
  - **A run is in flight:** capture never ends, aborts, or pauses the run.
    Append one entry to the `lesson_notes:` list in the running skill's
    state file, say at most one line in chat, and continue the interrupted
    step; the run's close phase records it.
- A pure harness/product bug no skill instruction relies on is not a lesson —
  it gets one line in the close card's `Attention:` block.
- A defect in `docs/*` is a finding (`FND`, fixed by `/sdlc:repair`) or a
  `WRN` in the owning artifact — never a lesson.
- Never hand-edit `.claude/skills-state/sdlc-lessons.yaml`; `lessons.py` is
  its only writer. Never patch the plugin's own files from this project.

## Where they go

`lessons.py` may mail recorded lessons to the plugin maintainer, but only if
this project opted in when `/sdlc:setup` asked. Nothing about this project
travels: lessons name plugin files, and the helper strips absolute paths and
e-mail addresses and replaces the project's name with an opaque id on the way
out. A `blocker` goes at the next skill close; anything else waits for a batch.

You never run a send command — recording is the whole job, and `lessons.py`
decides the rest. Two things worth knowing:

- If a send fails you will see one `[DRAFT]` line. Nothing is lost and nothing
  is broken: the batch is kept and retried at the next close. Do not retry it
  by hand, and do not record a lesson about it.
- If the user asks where their lessons go, or wants it stopped:
  `python .claude/sdlc/lessons.py consent` prints the current setting,
  `consent --set off` stops it permanently, and `SDLC_LESSONS_TELEMETRY=off`
  overrides everything for one session. Never turn sharing ON for them.

Full doctrine: the sdlc plugin's `lesson/references/lessons-capture.md`.
