# SDLCraft Demo

Spec-driven development for [Claude Code](https://code.claude.com). Structured
interviews turn an idea into machine-readable specs — requirements, UX, design,
data model, API and architecture — that AI agents can build from. Every spec is
validated, every id is traceable from requirement to architecture, and each
stage tells you exactly what to run next.

This is the **demo edition** (MIT). It takes a project from idea to a complete,
validated architecture. The full edition, SDLCraft, continues from there to
tested code — see [Editions](#editions).

> Pre-1.0 (version 0.9.17): expect the skills to keep changing.

## Install

```
claude plugin marketplace add sdlcraft/sdlcraft-demo
claude plugin install sdlc@sdlcraft-demo
```

The skills' validators need Python 3.10+ with `pydantic>=2` and `pyyaml`:

```
pip install "pydantic>=2" pyyaml
```

## Pipeline Overview

```
setup → prd → [ux] → [design] → data → [api] → arch → test* → task* → code* → (deploy: planned)
         ▲───────────────────────────────────────────────────────────────┘
                                   repair
*: only in full version
[]: optional
```

One skill's output is the next skill's input — `setup` to initialize a new project, `prd` defines *what* to build, `ux`/`design`/`data`/`api` flesh out surfaces/look/storage/contract, `arch` turns that into containers. The full version contains `test` and `task` which turn each container into a test strategy and a dependency-ordered task graph, and `code` which executes that graph into actual source files. `repair` sits off to the side and can be invoked at any point to diagnose and fix a defect — it walks backward from wherever the defect surfaced to the *earliest* artifact whose content is actually wrong. `deploy` is the one stage not yet implemented.

Invoke each skill explicitly via `/sdlc:<skill>`. *DO NOT use plan-mode*.

### Skipping a stage

`ux`, `design` and `api` are the three optional stages — everything else always runs. `/sdlc:prd` asks once which of them your project needs and records the answer, so a headless project goes `prd → data → arch → test → task → code`. Change your mind later by re-running `/sdlc:prd`, or just run the skipped skill — the stages after it pick the artifact up on their next run.

## Feedback

`/sdlc:setup` asks once whether to share anonymous reports about defects in the skills themselves that help the maintainer to improve them; the default is off, and declining costs you nothing. Nothing about your project's content is sent — see [`PRIVACY.md`](PRIVACY.md) for what a report does and does not contain.

## Skills
All skills need to be explicitly invoked. Most of them provide an **interview mechanic** that lets you define your software project step by step.

In general, if an interview skill is invoked, three things are checked:
- Is it first time invocation? → generate initial output
- If previous run was interrupted → resume
- Consecutive invocation AND upstream documents have changed → a **delta review** surfaces every added / removed / modified upstream item before the interview, so you decide per item whether to incorporate, ignore or defer it

Typing `EXIT` into any question's free-text field stops the session; progress is saved and the next invocation offers to resume.

### Reading what a skill tells you

Every skill and every checker reports the same way, so you only learn it once:

| You see | It means |
|---|---|
| `[OK]` | Finished and valid. The next skill can use it. |
| `[DRAFT]` | Saved but not finished. The next skill will refuse it until it says `complete`. |
| `[FAIL]` | It claims to be finished and is not. Nothing downstream will accept it. |
| `MUST FIX BEFORE 'complete'` | These stop the file from being finishable. |
| `WARNINGS` | **Never block the next skill.** Things worth a look, not gates. |
| `[check 20]`, `[coverage: entity]` | Which internal rule produced the line — quote it if you report a problem, otherwise ignore it. |
| `NEXT:` | The command to type next. |

`/sdlc:setup` installs `.claude/rules/sdlc-output-glossary.md` in your project — a one-line explanation of every term the skills use (work unit, container, embed, defer, stale, ring, finding…). Look a word up there rather than reading it front to back. Template source: [`sdlc/skills/setup/assets/sdlc-output-glossary.md`](sdlc/skills/setup/assets/sdlc-output-glossary.md).

## Pipeline commands

Execute the following skills in order within your project repo. All skills put their output into **`docs/`** in the repo root (fixed folder name).

### `/sdlc:setup`

| Form | Action |
|---|---|
| `/sdlc:setup` | Bootstrap the project once, before `/sdlc:prd`. Idempotent — safe to re-run; also upgrades an installed copy. |

Installs a generated `docs/INDEX.yaml` — a line-range location map over the large specs plus a cross-reference graph — together with the generator (`.claude/sdlc/docs_index.py`), a `PostToolUse` hook that refreshes the index on every `docs/*.yaml` and `docs/TASKS*.json` edit, and the slice-don't-slurp access rule. This is what keeps later stages cheap: skills read big specs *by slice* instead of loading them whole.

### `/sdlc:prd`

| Form | Action |
|---|---|
| `/sdlc:prd` | Create or update product requirements → `PRD.yaml`. |

Scans everything already present in the repo, so having already a README or other project docs is beneficial at this stage.

### `/sdlc:ux` (optional)

| Form | Action |
|---|---|
| `/sdlc:ux` | Define UX surfaces → `UX.yaml` + `UX__<surface>.yaml`. |
| `/sdlc:ux --reconcile` | *Maintenance:* review only what changed in `PRD.yaml` since `UX.yaml` was written — no interview. |

Define frontend type (desktop, mobile, web, cli) and UX surfaces for it.

**Skip it** if the project has no user-facing surface — a data pipeline, an ETL job, a scheduled worker, a library. Say so when `/sdlc:prd` asks which stages you need, and every later skill knows the absence was deliberate and never asks about it.

### `/sdlc:design` (optional)

| Form | Action |
|---|---|
| `/sdlc:design` | Create the design system → `DESIGN.yaml` (+ `DESIGN__tokens.yaml`, `DESIGN__assets.yaml`). |
| `/sdlc:design --reconcile` | *Maintenance:* review only what changed in PRD/UX since `DESIGN.yaml` was written — no interview. |

Token-based UIs additionally get `DESIGN__tokens.yaml`; projects with an asset pipeline get `DESIGN__assets.yaml`.

**Skip it** if there is nothing visual to style — automatic whenever `ux` was skipped, and usually right for a pure CLI too.

### `/sdlc:data`

| Form | Action |
|---|---|
| `/sdlc:data` | Define the data model → `DATA-MODEL.yaml`. |
| `/sdlc:data --reconcile` | *Maintenance:* review only what changed in PRD/UX since `DATA-MODEL.yaml` was written — no interview. |

Define data storage (SQL, graph, document, key-value or vector database, or simple filesystem storage), then all data entities and their relations. Also pre-scans the repo and checks for existing info regarding the data model.

### `/sdlc:api` (optional)

| Form | Action |
|---|---|
| `/sdlc:api` | Define the API contract → `API.yaml` + `API__<resource>.yaml`. |
| `/sdlc:api --reconcile` | *Maintenance:* review only what changed in PRD/UX/DATA since `API.yaml` was written — no interview. |

If the app has an API, use this skill next; otherwise skip straight to `arch`.

### `/sdlc:arch`

| Form | Action |
|---|---|
| `/sdlc:arch` | **Auto-advance** — the usual form: resolves to system mode first, then to the next not-yet-drilled container. |
| `/sdlc:arch --system` | System architecture (pattern, container inventory, cross-container edges) → `ARCH.yaml`. |
| `/sdlc:arch <container>` | Per-container deep-dive (tech stack, deployment, components, internal edges) → `ARCH__<container>.yaml`. |
| `/sdlc:arch -d [<container>]` | *Maintenance:* re-derive the typed dependency-edge graph from `API.yaml` + `DATA-MODEL.yaml` + `UX.yaml` only, no interview. |
| `/sdlc:arch [--system \| <container>] --reconcile` | *Maintenance:* review only what changed upstream since the file was written — no interview. Bare `--reconcile` walks every stale ARCH file. |

Just run `/sdlc:arch` and repeat until it says every container is specified — you never have to track which mode is due. Name `--system` or a container only to re-open one deliberately; use `-d` after editing an upstream artifact that only changes *who talks to whom*, not the containers themselves (bare `-d` always means the system edges, it does not auto-advance).

### `/sdlc:deploy`

| Form | Action |
|---|---|
| `/sdlc:deploy` | *Not yet implemented.* Deployment strategy document → `DEPLOY.yaml`. |

## Side skills

Not steps in the linear chain — invoke these whenever they're needed, independent of where you are in the pipeline.

### `/sdlc:repair`

| Form | Action |
|---|---|
| `/sdlc:repair` | Full diagnose-and-fix flow → edits to whichever `docs/` artifact actually holds the defect. |
| `/sdlc:repair --check [--no-emit] [--provenance]` | Read-only doctor sweep (pre-flight / CI). `--no-emit` also suppresses recording new findings; `--provenance` adds the upstream-drift check. |
| `/sdlc:repair FND-003 FND-005` | Skip the sweep, work only the named findings. |
| `/sdlc:repair --flag "<reason>" [--stage <s>] [--path <p>]` | Hand-raise a defect you noticed yourself; records it as a finding, then localizes and fixes it like any other. |

The only skill that **walks backward**: it runs a doctor sweep (every validator, the cross-artifact linter, the dangling-reference gate), merges that with the `FND-NNN` findings raised during codegen, then localizes each defect to the *earliest* artifact whose content is actually wrong — not the stage that noticed it — fixes it there, and propagates the fix forward along the computed reference graph.

Two fix modes: **surgical** when only the content of existing items changes (edit the source, bump its version, re-slice every task embed copied from it), and **re-invoke** when the *set* of downstream items changes — then it fixes the source and hands you the exact downstream command sequence, because those stages are interviews you own.

**After an upstream change.** Every stage after `prd` has a `--reconcile` form that reviews only what moved in its upstream files since it last wrote — no interview. When `/sdlc:repair` changes the *set* of items a later file depends on, it prints the chain of `--reconcile` commands and leaves its reasoning on the finding, where each reconcile shows it to you as a suggestion. Run the first one (in a new session): each reconcile names the next stale file, and the last one sends you back to `/sdlc:repair FND-NNN` to close the finding. `python .claude/sdlc/docs_index.py --stale` prints the whole list at any time — which is also the way back in after you edit a spec by hand.

### `/sdlc:lesson`

| Form | Action |
|---|---|
| `/sdlc:lesson` | Record feedback about a skill's own behaviour (not your project) for the plugin maintainer. |

You rarely need to type this yourself — skills self-record at close, the moment something about their own behaviour misbehaves. See [Feeding back lessons](#feeding-back-lessons).

### Internal mechanics

Bookkeeping the skills perform on their own — never typed, listed here only so the pieces you see on disk make sense:

- **The `docs/INDEX.yaml` refresh.** A `PostToolUse` hook (installed by `/sdlc:setup`) regenerates the index automatically on every `docs/*.yaml` / `docs/TASKS*.json` write.
- **Breadcrumbs, ledgers, state files.** The execution ledger and each skill's `.state.yaml` are written automatically after every step, purely so a killed session can resume cheaply.
- **Bundled Python scripts.** `docs_index.py`, `validate_schema.py`, `doctor.py`, `findings.py`, `lessons.py`, `bump_artifact.py`, `reslice_embeds.py` are called by the skills as part of their own phases. You *can* run them by hand (see `lessons.py export` below) but the pipeline never expects you to.

## Where things are written

In the consumer project's repo root:

| Path | What |
|---|---|
| `docs/*.yaml`, `docs/TASKS*.json` | the spec chain — the artifacts each skill produces |
| `docs/INDEX.yaml` | generated navigation map + cross-reference graph (from `/sdlc:setup`) |
|---|---|
| `.claude/skills-state/sdlc-<skill>.state.yaml` | per-skill interview / execution state, kept as an audit trail |
| `.claude/skills-state/sdlc-findings.yaml` | the cross-skill `FND-NNN` queue — written by `code`, resolved by `repair` |
| `.claude/skills-state/sdlc-lessons.yaml` | run records + `LSN-NNN` lessons about the skills themselves — for the skill maintainer; nothing in the pipeline reads it |
| `.claude/sdlc/docs_index.py` | the index generator installed by `/sdlc:setup` |
| `.claude/sdlc/lessons.py` | the run/lesson recorder installed by `/sdlc:setup`; also the opt-in sender (`consent`, `export --send`) |
| `.claude/sdlc/findings.py` (+ `validate_findings.py`) | the findings-queue writer + its validator models, for recording a spec defect noticed outside a skill run |
| `.claude/sdlc/bump_artifact.py` | the `metadata.<name>_version` + changelog bumper artifact skills and `repair` share |
| `.claude/sdlc/autocommit.py` | the opt-in close-step committer: when you said yes at `/sdlc:setup`, every run commits its own files as `<the command you typed> → <what changed>` (see below) |
| `.claude/rules/sdlc-output-glossary.md` | plain-language meanings for the words the skills print (from `/sdlc:setup`) |
| `.claude/rules/sdlc-lessons.md` | when and how to record a lesson (from `/sdlc:setup`) |
| `.claude/rules/sdlc-findings.md` | when and how to record a finding — the ambient analog of the lessons rule (from `/sdlc:setup`) |
| `.claude/rules/sdlc-docs-access.md` | the slice-don't-slurp retrieval protocol agents follow (from `/sdlc:setup`) |
|---|---|
| `.claude/rules/sdlc-statusboard.md` | GENERATED statusboard, loaded into every session: pipeline state, blocked units, open questions, open findings, and the caveats that matter (from `/sdlc:setup`) |
| `.claude/sdlc/STATUS.md` | GENERATED full detail behind the board — every warning verbatim, located, resolved ones included |
| `.claude/sdlc/statusboard.py` (+ `warning_item.py`, `migrate_warnings.py`) | the board generator, the canonical typed-`WRN` parser, and the opt-in converter for legacy warning strings |
| `CLAUDE.md` → `## SDLC Documents` | one static section written once by `/sdlc:setup`: what lives in `docs/`, how to read it by slice, and where the statusboard is |

The scripts under `.claude/sdlc/` are committed, repo-relative copies on
purpose: the index hook, the `docs_index.py --check` CI gate, and lessons
capture keep working for collaborators and CI that do not have the plugin
installed, and they upgrade only when `/sdlc:setup` is deliberately re-run.

## Committing each run automatically

`/sdlc:setup` asks once whether every `/sdlc:*` run should commit its own
files when it finishes. **Off until you say yes.** Your answer lives in
`.claude/sdlc/sdlc-plugin.json` beside the sharing answer, and a re-run never
resets it.

When on, each run ends with one `git commit` covering only the pipeline's own
files — the spec it wrote under `docs/`, `docs/INDEX.yaml`, its state file and
the shared queues under `.claude/skills-state/`, the generated statusboard,
and the source files a code-generation run produced — with the subject

```
<the command you typed> → <what changed>
/sdlc:data --reconcile → DATA-MODEL 2.3 reconciled against PRD 1.4 - ENT-014 added
```

The arrow is the marker: the command carries its own colon, and nobody types
`→` into a subject by hand, so `git log --grep='→'` lists exactly the
pipeline's commits. It never pushes, never stages anything else, never
rewrites history, and skips the commit when nothing changed; other changes in
your working tree are left as they are. A run that ended early (you typed
`EXIT`) commits its draft too, marked as such, so nothing sits uncommitted.
Anything that stops a commit — no git identity, a hook that refused — is one
line on the close card, never a failed run.

```bash
python .claude/sdlc/autocommit.py mode            # what is it set to?
python .claude/sdlc/autocommit.py mode --set off  # stop it
SDLC_AUTO_COMMIT=off                              # override for one session
```

## Feeding back lessons

The skills improve from real runs. Every skill records a small run record at
close, and when a SKILL itself misbehaves — an instruction gap, a validator
verdict you had to overrule, a question that made no sense, a bundled script
that failed — the agent records a **lesson** in
`.claude/skills-state/sdlc-lessons.yaml` on its own, the moment it notices
(recurring friction and self-corrections included) — immediately in ambient
chat, and during a running skill by noting the observation and recording it at
that run's close, so a run is never interrupted to capture. You never need to
trigger this; typing `/sdlc:lesson` right after something annoyed you also
works.
Lessons describe the skill, never your project: locations are files inside the
plugin, evidence is ids and counts, and nothing in your project reads or acts
on the queue.

### Getting them to the maintainer

`/sdlc:setup` asks once whether the plugin may send these reports on its own,
and presents auto-send as the suggested choice. **The default is still no**
until you answer — nothing leaves your machine unless you say it may. Your
answer lives in `.claude/sdlc/sdlc-plugin.json` and a re-run never resets it.

```bash
python .claude/sdlc/lessons.py consent            # what is it set to?
python .claude/sdlc/lessons.py consent --set off  # stop it, permanently
SDLC_LESSONS_TELEMETRY=off                        # override for one session
```

If you say yes, reports go to `sdlc@agentmail.to` at a skill **close** — never
mid-run. A `blocker` goes at the next close; anything else waits for a batch (7
days, or 10 lessons, whichever comes first), so a busy project costs a handful
of mails a year. Each entry is stamped once sent and never sent twice, and a
failed send costs you one `[DRAFT]` line and is retried later.

**What travels**, and what does not:

| Sent | Never sent |
|---|---|
| which skill misbehaved, and which of *its own* files | your code, your `docs/`, your artifacts |
| the lesson's kind, severity, summary and evidence | your absolute paths and e-mail addresses — stripped to `<path>` / `<email>` |
| counts: questions asked, free-text ratios, validator failures, durations | your project's name — it appears only as an opaque id |
| the plugin and skill versions it was raised against | your container names, and any metric outside a fixed allowlist |

Redaction runs on the way out, on top of the rule that lessons describe the
plugin rather than your project. This is the only thing in the whole plugin
that touches the network.

Prefer to keep it manual? That still works, and is unchanged:

```bash
python .claude/sdlc/lessons.py export                       # print the report
python .claude/sdlc/lessons.py export --out lessons.md      # or save it
```

Review it like any outbound text, then email it to `sdlc@agentmail.to`.
Accepted lessons come back as skill fixes in a later plugin version, each
pinned by a regression test.


## Editions

| | Demo | SDLCraft |
|---|:---:|:---:|
| Requirements → architecture specs | ✓ | ✓ |
| Spec repair | ✓ | ✓ |
| Test strategy (`/sdlc:test`) | | ✓ |
| Dependency-ordered task graph (`/sdlc:task`) | | ✓ |
| Test-first code generation with a self-healing loop (`/sdlc:code`) | | ✓ |

SDLCraft keeps every command and every file you already have — upgrading is
uninstall, install, and one `/sdlc:setup` per project. It is a subscription,
one seat per developer, sold by Polar Software Inc. as merchant of record. The
subscription buys updates: cancel and you keep every version you received, you
just stop getting new ones. Everything the pipeline generates is yours either
way.

It is currently in an invite-only beta — open an issue in this repository to
ask for access.

## Legal

MIT — see [`LICENSE`](LICENSE). The MIT licence covers the code, not the name:
SDLCraft is a trade mark of Andreas Pfrengle. Fork it under a different name
and you're welcome to. Privacy: [`PRIVACY.md`](PRIVACY.md).

Andreas Pfrengle (Einzelunternehmer), Am Blasiwald 34, 79183 Waldkirch, Germany · sdlc@agentmail.to
