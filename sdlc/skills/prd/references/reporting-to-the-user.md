# Reporting to the user — the shared output contract (all SDLC skills)

Canonical for CLAUDE.md §14. Every SDLC skill references this file rather than
restating it. Its sibling `explaining-choices.md` (in the `test` skill) solves
the same problem for **questions**; this one covers **output**.

Read it when you are about to show the user a validator result, a checkpoint
summary, or a close report.

---

## Who is reading

Someone whose model of this system is: *"there is a pipeline of skills and I run
them in order."* They may be a strong developer. They are not a user of this
codebase's vocabulary. They do not know what a work unit, an embed, a shard, a
deferral, a ring, a stitch or a cross-check number is, and they have no reason
to.

Assume they want three answers and nothing else:

1. **Did it work?**
2. **Can I run the next skill?**
3. **What do I type next?**

Any line that does not help answer one of those is costing them attention.

## The one rule that fixes most of it

> **The agent translates; it never pastes.**

Raw validator stdout is *input* to your report. It is never the report. Reading
a wall of `TASKS__aicf-cli.json: [aicf-cli] work-unit coverage: …` to the user
and adding "so, some warnings" is not reporting — it is forwarding.

The exceptions are narrow and already documented where they apply: `code` quotes
`topo_order.py` at the plan gate (never hand-compute a build order), `repair`
quotes captured exit codes (never paraphrase a number), and field-level schema
errors are shown verbatim *because the field path is the fix*. Everything else
gets translated.

## Message anatomy

Three parts, in this order, in every finding you surface:

| Part | What it is | Failure mode it prevents |
|---|---|---|
| **What** | the fact, in plain terms, with the id and file kept verbatim | a user who cannot find the thing |
| **Why** | the consequence *for the pipeline*, one clause | a user who cannot judge whether to care |
| **What to do** | an imperative, naming the exact command or edit | a user who agrees and is still stuck |

Keep every id, path and line number exactly as printed — those are the user's
handles into the file. Translate the *sentence around them*, never the ids.

Do **not** state a rule's rationale-for-existing where its consequence belongs.
"…so the codegen agent needs no upstream lookup" explains why the schema has the
field. It tells the reader nothing they can act on. "…so the worker that writes
this file will have to guess the signature" does.

## The close report

Every skill ends with a card. Omit any row that has nothing to say — a card with
four honest rows is read, a card with eight is skimmed.

```
-- /sdlc:task - what you have now ------------------
Wrote:     docs/TASKS__aicf-cli.json (465 tasks)
Status:    complete - /sdlc:code can run it
Attention: 9 requirements are deferred by a note rather than
           declared; harmless now, worth tidying
Next:      /sdlc:task   (1 container left)   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript.
```

- **`Wrote:`** the artifact(s) and the one count that matters. No derived counts
  in prose elsewhere (CLAUDE.md §8) — this row is where a count belongs.
- **`Status:`** answers question 2 above, explicitly, in terms of the *next
  skill*. `complete - /sdlc:code can run it` / `draft - /sdlc:code will refuse
  it until it is complete`.
- **`Attention:`** translated, never pasted. If there is nothing, omit the row —
  do not write "no warnings".
- **`Findings:`** only when this run recorded `FND-NNN` findings or open findings
  name an artifact this skill consumed — the ids and one consequence clause:
  `Findings:  2 recorded (FND-011, FND-012) -> /sdlc:repair`. Omit otherwise.
- **`Lessons:`** only when the close self-review recorded `LSN-NNN` lessons —
  the count and the affected skill(s), one line. Omit otherwise.
- **`Next:`** exactly ONE invocation — the single best next step, **computed at
  run time** by the procedure below. The literal in a SKILL.md card is an
  example, never a value to copy through.
- **`Why new:`** one clause justifying the new-session annotation, printed once
  per card (not once per row). Omit it if no row carries the annotation.

### Computing the `Next:` row

First match wins:

| # | Condition | `Next:` |
|---|---|---|
| 1 | This run did not finish its own job — artifact is `draft`, the user typed `EXIT`, or the validator is not green | re-invoke **this** skill; `Status:` says what "finished" means. Never hand off from an unfinished artifact. |
| 2 | This run recorded findings, or open findings name an artifact this skill consumed — **except** a re-invoke finding still waiting on this run's output or on a file downstream of it (`findings.py list --owed-by`): that is a reconcile chain in progress, and rule 3 routes it | `/sdlc:repair` (name the ids) before any successor |
| 3 | This run was a `--reconcile`, or `python .claude/sdlc/docs_index.py --stale` lists a file downstream of what this run wrote | the first `--stale` row's command (upstream first) — the chain after a repair walks itself this way. Nothing stale any more and a finding was owed to this run → `/sdlc:repair FND-NNN`, which verifies the hops and closes it |
| 4 | A **sharded** skill (`arch`, `test`, `task`) with buildable, ready, un-specified containers left | plain `/sdlc:<this-skill>` — it auto-advances — naming how many are left |
| 5 | Otherwise | the pipeline successor |
| 6 | The successor is not implemented, or does not ship in this build — the **demo edition** (the free build) ships `setup` through `arch` plus `repair` and `lesson`; `test`, `task` and `code` ship only in the **full edition** | say so plainly, name what the user *can* do instead, and do **not** print it as a bare runnable command. Demo edition: the specification is complete, and test planning, the task graph and code generation are in the full edition — name the `homepage` from the plugin's `.claude-plugin/plugin.json` when it has one |

Rule 3's `--stale` runs through the copy
`${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks. An
installed `docs_index.py` older than capability 5 rejects `--stale` with exit
2, and that is not an empty stale list.

The successor map:

```
setup → prd → ux → design → data → api (or arch) → arch → test → task → code
                                                        → [deploy: planned, NOT implemented]
```

`arch`, `test` and `task` are sharded: they run per container and only hand off
to the next skill once every buildable container is specified.

**Never route to a skill that does not exist.** Before printing a target as a
command, confirm `${CLAUDE_SKILL_DIR}/../<name>/SKILL.md` exists. `/sdlc:deploy`
has no skill folder today — mention it only as planned-and-unimplemented, never
as a command to run. The same check tells a skill it runs in the demo edition:
`../test/SKILL.md` absent → rule 6's pointer to the full edition replaces
`/sdlc:test`.

**Annotate with `← in a NEW session`** whenever that is the better advice —
decided at run time, but it is the typical case: the next skill's handoff is its
own artifacts and state files on disk, never this conversation's context, so a
fresh session starts from the same place with more room to work.

**When `Next:` is an in-run position rather than a pipeline successor** (`code`
names the next component; `repair` names the located stage), print **both**: the
in-run position while work remains, and the pipeline successor once the run is
complete.

`code` and `repair` already ship richer variants of this card (a resume card and
a "what changed" card). Match their shape; do not invent a third. Both carry
`Status:` like every other card, and `lint_output_style.py` fails a card
template without one, or one that prints the findings queue's state or field
names (ledger IMP-154).

## What not to say

| Never | Say instead |
|---|---|
| "advisory" / "advisories" | "warning", and state that it does not block |
| "cross-check 22 failed" | what the check found, then a trailing `[check 22]` |
| `Gap-1`, `SK-32`, `D2`, `post-D2`, `§6a` | the thing itself; internal tracker ids mean nothing outside this repo |
| "trace-or-defer" | "either something must cover it, or you must say why it doesn't" |
| "the embed drifted" | "this task's copy of X no longer matches X" |
| "WRN-NNN" as an instruction | name the field the user must edit |
| "N item(s) to resolve" under `[OK]` | `[DRAFT]`, and say what finishing means |

## Explaining a term you cannot avoid

Some concepts have no shorter name — a *container*, a *work unit*, a *task
graph*. Gloss on first use, in the same sentence, and move on:

> "…every **work unit** (one function or class the architecture names) …"

The full list lives in `.claude/rules/sdlc-output-glossary.md`, installed in the
user's project by `/sdlc:setup`. Point at it in the footer; do not recite it.

## Volume

Findings of the same class collapse into one line naming the class and listing
the ids. The threshold is four. A run that prints 234 individual lines has told
the user nothing — they will not read line 12, let alone 200.

When you must show many, show the grouped line and offer the detail:

> "37 work units have no test. Want the list, or should I open `/sdlc:test
> aicf-cli` and work through them?"

The cap is for a **verdict a person skims** — a grouped finding whose remedy
is a command that handles the whole class, or a re-run that shows the next
ones. It is never for an **operand**: a list whose members a later step must
act on one by one and cannot obtain any other way — the item delta
`docs_index.py --drift` prints for a reconcile, the residue the user picks the
new items from, the candidates an ambiguous symbol must be qualified against.
Those print whole, however long; the reconcile form says "verbatim" and means
it. Two ids hidden behind a `(+2 more)` once needed edits nobody made (ledger
IMP-097). The scripts' shared `join_ids(ids, limit)` helper takes
`len(ids)` at such a site.

## Bad and good, from the real corpus

**Before**

```
WARNINGS (10 component work_units advisorie(s) [waivers / Gap-1 / Gap-2 / traces derive]):
  - ARCH__aicf-cli.yaml: components[0]='config-foundation' is one file
    ('src/aicf/config.py') with 3 work_units but no `entrypoint` unit - add one
    to own arg/mode dispatch + step-sequencing + setup so downstream task/code
    build the composition root
```
…times ten, one per component.

**After**

```
WARNINGS (1) - none of these block the next skill:
  - ARCH__aicf-cli.yaml: 10 single-file components have no entry point:
    config-foundation, artifact-store, checkpoint-adapter, ... Without one,
    nothing owns startup for that file and the build stage has to invent it.
    Add an `entrypoint` work unit to each, or re-run /sdlc:arch aicf-cli.
    [cross-check 21]
```
