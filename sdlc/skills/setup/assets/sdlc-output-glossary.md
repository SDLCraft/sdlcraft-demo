# What the SDLC skills mean when they say that

Installed by `/sdlc:setup`. A reference for the words the pipeline's skills and
their validators print. You never need to read this front to back — look up the
word you just saw.

## Verdicts

| You see | It means |
|---|---|
| `[OK]` | The file is valid and finished. The next skill can consume it. |
| `[DRAFT]` | The file is valid but not finished. The next skill will refuse it until it says `complete`. Re-run the skill to continue. |
| `[FAIL]` | The file claims to be finished and is not. Nothing downstream will accept it. |
| `MUST FIX BEFORE 'complete'` | These stop the file from being finishable. |
| `WARNINGS` | These never block the next skill. They are things worth looking at, not gates. |
| `[check 20]`, `[cross-check 21]` | The internal rule that produced the line. Quote it if you report a problem; otherwise ignore it. |
| `exit 0 / 1 / 2 / 3` | 0 valid · 1 invalid or finished-with-errors · 2 file unreadable · 3 a Python package is missing. |

## The shape of the specs

| Word | Meaning |
|---|---|
| **artifact** | One file the pipeline produces: `docs/PRD.yaml`, `docs/ARCH.yaml`, and so on. |
| **container** | A separately deployable piece of the system — a backend service, a CLI, a web frontend. (C4 model, level 2.) |
| **component** | A module inside one container. |
| **work unit** | One function or class the architecture names inside a component. The smallest thing a task can build. |
| **surface** | One screen, page, or CLI command the user interacts with. |
| **shard** | A per-thing file next to a main one: `ARCH__backend.yaml` is the backend container's shard of `ARCH.yaml`. |
| **slice** | A part of a large file, read by line range instead of loading the whole file. |
| **task graph** | `docs/TASKS*.json` — every build step and what it depends on. |
| **build order** | The order containers get built in, computed from their dependencies. |

## Coverage and deferral

| Word | Meaning |
|---|---|
| **coverage** | Every upstream item (a requirement, an entity, a test) is accounted for downstream. |
| **trace** | Item A names item B, so B is accounted for. |
| **defer** | You decided an item is deliberately out of scope here, and said why. A deferred item counts as accounted-for. |
| `deferrals` | The top-level list where a deferral is declared: `{id, reason}`. This is the channel that counts. |
| `WRN-NNN` | A numbered note inside an artifact's own warnings list. Human-readable commentary — not a deferral. |
| **coverage gate** | The check that every upstream item is either traced or deferred. |

## Copies and staleness

| Word | Meaning |
|---|---|
| **embed** | A copy of an upstream detail, written into a task so the build stage does not have to look it up. |
| **drift** | An embedded copy no longer matches the thing it was copied from. Fix the original and re-run the skill — never edit the copy. |
| **stale** | A task whose definition changed after it was built — the schedule names why: `build` (the task itself changed), `context` (an upstream fact it consumed changed), `task` (built before fingerprints existed). `/sdlc:code` will offer to rebuild it. |
| **refreshed** | Built and unchanged in substance — only cosmetic fields moved. Re-fingerprinted silently; nothing to rebuild. |
| **ring_recheck** | Built and unchanged itself, but a task it depends on changed its contract afterwards. Its tests re-run: green is acknowledged, red means rebuild. |
| **fingerprint** | A hash of a task's definition; how staleness is detected. |
| **delta review** | When an upstream file changed since last time, the skill walks you through each change before re-interviewing — or, with `--reconcile`, instead of re-interviewing. |
| **reconcile** | `/sdlc:<skill> --reconcile`: bring a file up to date with upstream files that changed, reviewing only what moved — no full interview. On `arch`, `test` and `task` a bare `--reconcile` does every stale file of that skill; `<container> --reconcile` or `--system --reconcile` does one. Its close report names the next file to reconcile. |
| **blast radius** | Everything that references the thing you are about to edit. |

## Running the build

| Word | Meaning |
|---|---|
| **worker** | A sub-agent `/sdlc:code` dispatches to build one unit of work. |
| **ledger** | The record of which tasks are already built. It is what makes re-running safe. |
| **breadcrumb** | A worker's progress note, so an interrupted unit resumes instead of restarting. |
| **ring** | A batch of tests run together at a boundary — component ring, container ring. |
| **drain** | Let everything in flight finish before continuing. |
| **heal** | An automatic retry after a test failed, up to 3 attempts. |
| **escalation** | Attempt 3, handed to a stronger model in a fresh sub-agent. |
| **checkpoint** | A stopping point where you get a summary and decide whether to continue. |
| **adopted** | A file kept at a gate (a hand-edit you chose to keep, or an orphaned write) without a fresh test run on that exact content. Sits below a test-verified file on the manifest's `verified` ladder. |
| **stuck report** | A per-unit note under `.claude/skills-state/sdlc-code/stuck/` written when healing ran out; the next `/sdlc:code` plan gate shows it as one decision row. |

## Problems and repairs

| Word | Meaning |
|---|---|
| `FND-NNN` | A finding: a problem in one of this project's `docs/` files, recorded by whichever stage noticed it (`/sdlc:code` while building, any interview skill while reading its inputs, the doctor sweep, or you via `/sdlc:repair --flag`). The noticer records it and moves on; `/sdlc:repair` works out which file is actually wrong and fixes it there. |
| `LSN-NNN` | A lesson: something a SKILL itself got wrong (an instruction, a question, a validator verdict, a bundled script). Recorded for the plugin maintainer to fix in the plugin — nothing in this project acts on it. |
| **doctor sweep** | Running every validator at once to see the health of the whole chain. |
| **dangling reference** | An id referenced somewhere that no longer exists anywhere. Only a structured reference counts (a field value, a list entry); an id merely mentioned inside prose is never one. |
| **dangling_warnings** | A reference the index cannot resolve, in a family that does not fail `--check` yet (tests, operations, assets, named symbols). Fix them anyway — a later version makes them blocking. |
| **item by item** | `docs_index.py --drift` compared the upstream against the per-item snapshot `--stamp` recorded, so the added / removed / changed lines are exact. A report that instead says the residue "cannot be told apart" means the file's stamp predates snapshots — re-stamping it fixes that for next time. |
| **retired id** | An id deliberately removed from the project. List it under `docs/INDEX.allow.yaml` `retired_ids:` (or PRD `metadata.retired_ids`) so leftover mentions stop being reported. |
| **UPSTREAMS THAT MOVED** | `docs_index.py --drift` found this file was written against an upstream that has changed since. Run the command its `NEXT:` names — the owning skill's `--reconcile` — to review only what moved. A `why` line quotes the upstream's own changelog since your file was written. |
| **STALE, IN THE ORDER TO RECONCILE THEM** | `docs_index.py --stale` lists every file built against an upstream that has since changed, upstream first. Run the first command; each reconcile's close report names the next one. |
| **handoff** | A note `/sdlc:repair` leaves on a finding for a file a re-run still owes: what changed there and what it proposes. The `--reconcile` run for that file shows it to you as a suggestion; `findings.py list --owed-by docs/<file>` prints it. |
| **[deferral hygiene]** | An id counts as deferred only because a warning note happens to mention it. Move it into the file's structured `deferrals:` list (`{id, reason}`) — the note-based escape stops working at the next version. |
| **localize** | Working backwards from where a problem showed up to the earliest file that is actually wrong. |
| **surgical vs re-invoke** | Two repair modes: edit the file directly, or re-run the skill that owns it (its `--reconcile` form) because the *set* of items changed. |

## If you are stuck

- `/sdlc:repair --check` — health report on the whole chain. Edits nothing under `docs/`, but records each failure as a finding so `/sdlc:repair` can pick it up; add `--no-emit` (the CI form) to record nothing, `--provenance` to also see which files were built against an upstream that has since changed.
- Every skill's close report names the exact next command.
- A `[FAIL]` names the file and the field. Re-run the skill that owns that file.
- A SKILL itself misbehaved (not your docs)? The agent records a lesson for
  the plugin maintainer as it happens; typing `/sdlc:lesson` also works.
