---
name: setup
description: >
  Run ONCE before /sdlc:prd to bootstrap a project for the SDLC document
  pipeline. Wires an automatic docs/INDEX.yaml navigation map: installs a
  stdlib-only generator (location map + cross-reference graph over every
  canonical doc AND every docs/*__* shard, with --show/--refs/--check/--find/
  --hash/--drift/--stale/--items/--stamp), a Write|Edit PostToolUse hook that refreshes the index on
  every docs/ edit, the slice-don't-slurp access rule, and the CLAUDE.md
  pointer — plus the shared helpers every later skill calls (lessons.py,
  findings.py, bump_artifact.py, repo_scan.py, autocommit.py) and their ambient rules. Trigger only on
  /sdlc:setup or a direct request to set up the sdlc docs toolchain / docs
  index. Idempotent — safe to re-run; a re-run also upgrades previously
  installed helpers.
user-invocable: true
disable-model-invocation: true
model: sonnet
effort: medium
allowed-tools: Read Write(CLAUDE.md) Write(.claude/**) Write(docs/INDEX.yaml) Edit(CLAUDE.md) Edit(.claude/**) Bash Bash(python *) Bash(uv *) Bash(ls *) Glob AskUserQuestion
---

# sdlc-setup

Bootstraps a consumer project so its SDLC specs stay cheap to navigate as they
grow. `docs/PRD.yaml` and `docs/DATA-MODEL.yaml` routinely reach thousands of
lines; an agent that loads one whole burns a large slice of its context window.
This skill wires a generated **`docs/INDEX.yaml`** location map (file + line
range + one-line summary per symbol) **plus a cross-reference graph**
(`referenced_by` blast-radius + `dangling` id-integrity) over the canonical
docs **and every `docs/*__*` shard**, plus the protocol and automation that keep
it current, so every downstream skill and agent reads by slice instead. It also
installs the **shared helpers** the rest of the pipeline calls — the lessons
recorder, the findings-queue writer and the version/changelog bumper — so a
project never has to reach into the plugin for them.

**Run this once, before `/sdlc:prd`.** It is fully idempotent — re-running only
fills gaps and refreshes the index, never duplicates. **Re-running also upgrades
a previously installed `docs_index.py`** and the helpers — an older copy without
the shard graph gains work-unit / entity / test symbols, `--hash`, `--drift`,
the per-item provenance subcommands `--items` / `--stamp` and the
reconcile-chain list `--stale` after a re-run.

## What it installs into the project

| Target | Purpose |
|---|---|
| `.claude/sdlc/docs_index.py` | Stdlib-only index generator (zero deps; copied from this skill; capability version 9). Sections the canonical docs, symbol-indexes DATA-MODEL entities + enums, every PRD id family (`FR/NFR/WKF/ENT/PER/USR/…`), UX surfaces, **and every shard**: ARCH__ components + work units (`<cid>/<component>/<unit>`), TEST-STRATEGY tests (`TST-NNN`, `TST-<PREFIX>-NNN`), API__ operations (`OPR`), DESIGN__assets assets (`AST`), TASKS__ tasks (`<cid>/TSK-NNN`). Builds the cross-reference graph over id families **and field-anchored named references** (`touches_entities`, `via_unit`, `target_symbol`, `component_ref`, `depends_on`, …). Power tools: `--show <symbol>`, `--refs <symbol>` (blast-radius), `--check` (dangling-reference gate; only a STRUCTURED reference counts, a prose mention is never dangling), `--find <filters>`, `--hash <file>` (the canonical 16-hex content hash), `--drift <artifact>` (recorded `upstream_provenance` vs the upstreams now — item by item when the stamp carries `items`, with each moved upstream's changelog lines since the stamp as the why), `--stale` (every artifact built against an upstream that has moved since, in the order to reconcile it, with its owning skill's `--reconcile` command), `--items <upstream>` (every item with its body hash), `--stamp <artifact> [--upstream <file>…]` (rewrite the artifact's provenance with sha256 + per-item hashes + each upstream's version; writes only that artifact). Capability version 5. |
| `.claude/settings.json` | A `Write\|Edit\|MultiEdit` **PostToolUse hook** — `<python> "$CLAUDE_PROJECT_DIR/.claude/sdlc/docs_index.py" --hook --project-root "$CLAUDE_PROJECT_DIR"` — that regenerates the index after any `docs/` edit (canonical, shard or `INDEX.allow.yaml`), from any working directory. Merged in — existing settings preserved; a shared entry keeps its own matcher. |
| `.claude/rules/sdlc-docs-access.md` | The slice-don't-slurp retrieval protocol agents follow. |
| `.claude/rules/sdlc-output-glossary.md` | Plain-language meanings for the words the skills print, for the USER to look up (CLAUDE.md §14). |
| `.claude/sdlc/lessons.py` | The lessons/run-record helper (copied from the sibling `lesson` skill). Every skill's close phase calls it to record its run; `/sdlc:lesson` and the rule below use it to record skill-defect lessons for the plugin maintainer. |
| `.claude/rules/sdlc-lessons.md` | When something an `/sdlc:*` skill itself did was wrong (the skill — not this project's `docs/`), record a lesson instead of silently working around it. |
| `.claude/sdlc/findings.py` | The findings-queue writer (copied from the sibling `repair` skill, CLAUDE.md §13). Skills call the plugin copy; this copy is for **ambient sessions** — an agent that notices a spec defect in `docs/` outside any skill run records it with `python .claude/sdlc/findings.py add …` so `/sdlc:repair` can localize it. |
| `.claude/sdlc/validate_findings.py` | The findings-queue validator models, installed beside `findings.py` (which refuses to run without them). |
| `.claude/rules/sdlc-findings.md` | When and how to record a finding (the ambient analog of the lessons rule). |
| `.claude/sdlc/bump_artifact.py` | The `metadata.<name>_version` + changelog bumper the artifact skills and `repair` share (copied from the sibling `repair` skill). |
| `.claude/sdlc/repo_scan.py` | Bounded evidence sweep over the project's OWN files, one domain per skill (`--domain prd\|ux\|design\|data\|api\|arch\|test\|task`, `--json`). Finds the migrations, route files, Dockerfiles, token files and test layout already on disk so a brownfield project's Phase-3 pre-fill starts from what exists rather than from the upstream specs alone. Costs are capped: the file list comes from `git ls-files` (so `.gitignore` is honoured for free), files and bytes per file are capped, and an excerpt is one trimmed line - it never emits a file body. Everything it returns is a CANDIDATE tagged `inferred`, confirmed item by item in the interview. |
| `.claude/sdlc/sdlc-plugin.json` | Plugin-version marker, also naming the version of every helper installed (`helpers: {docs_index, lessons, findings, bump_artifact, …, autocommit}`), so recorded runs, lessons and findings say what they ran against. Carries the `telemetry` block too — the answer to step 4's sharing question, seeded `off`, plus the batch thresholds and the project's opaque ids: a random `project_uuid` minted on the first delivery (stable across a move, and with no path to guess back out of it) beside the legacy path-hash `project_id`. A re-run preserves it verbatim. Likewise the `auto_commit` block — the answer to step 4's second question (`mode: on \| off`, seeded `off`, `decided_on`), preserved verbatim on re-run. Also records the installed `edition` — `free` when test, task and code do not ship beside setup, with the free build's `homepage` as `pro_url` — which the statusboard reads to label those stages instead of routing to them. |
| `.claude/sdlc/autocommit.py` | The close-step committer (CLAUDE.md 20; copied from this skill). When the project opted in, every skill's close runs `python .claude/sdlc/autocommit.py commit …` as its last action: it stages only that skill's own files and commits them as `<the command as typed> → <what changed>`. Never pushes, never `git add -A`, never a run failure. `autocommit.py mode [--set on\|off]` reads or changes the answer. Mechanics: `references/auto-commit.md`. |
| `CLAUDE.md` (`## SDLC Documents`) | Slice-first access note + the `docs/INDEX.yaml` pointer. Coexists with the per-artifact bullets `prd`/`ux`/`data`/`arch` add to the same section. |
| `docs/INDEX.yaml` | Generated once now (no-op if `docs/` is empty). |

**Why committed copies?** The scripts under `.claude/sdlc/` are repo-relative
and version-pinned on purpose: the hook, the `docs_index.py --check` CI gate,
and lessons/findings capture keep working for collaborators and CI that do not
have the sdlc plugin installed, and the toolchain upgrades only when
`/sdlc:setup` is deliberately re-run.

## Files in this skill

| File | Purpose |
|---|---|
| `SKILL.md` | This file — the workflow. |
| `docs_index.py` | The generator that gets copied into the target. Read it only if asked to extend index coverage. |
| `wire_setup.py` | Deterministic installer that performs all of the above. The skill calls it; you do not hand-edit the targets. |
| `autocommit.py` | The close-step committer copied into the target (CLAUDE.md 20); `references/auto-commit.md` is the rule every skill's close phase points at. |
| `assets/sdlc-docs-access.md` | The rule-file template copied into the target. |
| `assets/sdlc-output-glossary.md` | The user-facing glossary copied into the target. |
| `assets/sdlc-lessons.md` | The lessons rule-file template copied into the target. |
| `assets/sdlc-findings.md` | The findings rule-file template copied into the target. |
| `../lesson/lessons.py` | The lessons helper the installer copies into the target — owned by the `lesson` skill, listed here because `wire_setup.py` ships it. |
| `../repair/findings.py`, `../repair/validate_findings.py`, `../repair/bump_artifact.py` | The findings writer, its validator models and the version bumper the installer copies into the target — owned by the `repair` skill. |
| `_smoke/index_selftest.py`, `_smoke/wire_selftest.py` | Regression nets for the generator and the installer (run by `run_smoke.py --skill setup`). |

## Workflow

### 1 — Confirm this is the right moment
`sdlc:setup` is a project bootstrap step. Briefly confirm the project root is
the current working directory (where `docs/` will live). If a `docs/INDEX.yaml`
and the hook already exist, tell the user it's already wired and a re-run will
just refresh — proceed only if they want that.

### 2 — Pick the Python invocation for the hook
The hook command must call a Python that exists on this machine. Decide which:

- If the project uses **uv** (a `pyproject.toml` *and* `uv` is on PATH —
  `uv --version`), use `uv run python`. This matches how the project already
  runs Python and needs no global interpreter.
- Otherwise use a bare interpreter: `python` on Windows, `python3` on
  macOS/Linux (whichever `--version` succeeds).

The generator is **dependency-free stdlib**, so any Python 3.8+ works — the only
goal is naming an interpreter the hook shell can find. When unsure, ask the user
with `AskUserQuestion`, recommending the detected default.

### 3 — Preview, then wire
Run a dry-run first so the user sees exactly what changes:

```bash
python "${CLAUDE_SKILL_DIR}/wire_setup.py" --project-root . --python "<chosen>" --dry-run
```

On approval, apply it:

```bash
python "${CLAUDE_SKILL_DIR}/wire_setup.py" --project-root . --python "<chosen>"
```

`wire_setup.py` is deterministic and idempotent; it prints a per-target action
log, a `Status:` line and a `NEXT:` line, and exits non-zero only on a
read/write error (nothing is written past the point of failure). Do **not**
hand-edit `settings.json` / `CLAUDE.md` yourself — let the script own the merge.

**If the action log reports `[own-toolchain]`**, the project generates
`docs/INDEX.yaml` with its own tool (its INDEX header or an existing hook names
a non-stock generator command). The installer then leaves ALL index wiring
untouched — generator copy, docs-access rule, hook, CLAUDE.md section, index
generation — and installs only the generator-agnostic pieces (glossary,
lessons, findings and bump helpers + rules, version marker). The script's own
close text says **`Status: partial`**; carry that word into the card. That is
the correct outcome: report it to the user as such. Re-run with `--force-stock`
ONLY if the user explicitly says they want the stock toolchain to replace the
project's own — that form also removes the project's foreign index hook from
`settings.json`.

### 4 — Ask once: may lessons be shared, and should every run commit itself

The plugin learns from real runs. When a SKILL misbehaves, the agent records an
`LSN-NNN` lesson in `.claude/skills-state/sdlc-lessons.yaml` — about the plugin,
never about this project. Getting those to the maintainer used to need the user
to export and email them by hand, which nobody does; the helper can now send
them on its own. **That is off until someone says otherwise, and this is the one
place the question is asked.**

Ask it with a single `AskUserQuestion`, using the exact header, question and
option text below **verbatim** — do not paraphrase, shorten, or restate it in
your own words. This is a consent notice; drift between what is authored here
and what the user actually sees is a defect, not a style choice. The reader
has not necessarily read the README, so the wording is self-contained and
does not assume prior knowledge of this repo's own terms ("skills",
"lessons") beyond what it explains inline.

- **header:** `Bug reporting / telemetry consent`
- **question:**
  > This plugin can tell its maintainer when one of its own skills misbehaves,
  > so the skill gets fixed for everyone. A report never includes your code,
  > your `docs/`, your file paths, your project's name, or e-mail addresses —
  > your project appears only as a random id. You can change this choice
  > anytime by running `python .claude/sdlc/lessons.py consent`.
  > Share these reports?
- **options** (exactly these three — the tool adds a 4th "Other" slot on its
  own, so do not author a 4th):
  1. `Yes, send automatically (Recommended)` — "Sends on its own: a critical
     issue goes at the next skill close, everything else in a weekly batch."
  2. `Ask me each time` — "Nothing sends on its own — each report is offered
     to you individually before it goes out."
  3. `No` — "Nothing about this project ever leaves this machine."

Three answers, mapped to the three modes:

| Answer | Mode | What happens |
|---|---|---|
| Yes, send automatically | `auto` | a `blocker` goes at the next skill close; anything else waits for a weekly batch |
| Ask me each time | `ask` | nothing sends on its own; each `/sdlc:lesson` close offers |
| No | `off` | nothing ever leaves this machine |

Then record it:

```bash
python .claude/sdlc/lessons.py consent --set <auto|ask|off>
```

**Do not ask, and do not run the command, when:** the marker already carries a
`telemetry.consented_on` (the user answered on an earlier run — a re-run must
never re-litigate it), or the session is non-interactive. In both cases leave it
alone; the stored answer stands, and an unanswered project stays `off`. Say so
in the close card's `Attention:` row only when you skipped the question because
the session was non-interactive.

If the user asks later, `python .claude/sdlc/lessons.py consent` prints the
current setting and `consent --set off` stops it for good;
`SDLC_LESSONS_TELEMETRY=off` in the environment overrides everything.

**The second question: should every run commit itself** (CLAUDE.md 20). Ask
it in the SAME `AskUserQuestion` call as the sharing question when both are
pending (two questions, one call), alone when only this one is. The answer is
a standing permission — the helper's `git commit` runs from inside a script,
where no permission prompt will ever see it — so this too is a consent notice:
use the exact header, question and option text below **verbatim**.

- **header:** `Auto-commit`
- **question:**
  > Should every `/sdlc:*` run commit its own files when it finishes? When on,
  > each run ends with one `git commit` covering only the pipeline's own files —
  > the spec it wrote under `docs/`, `docs/INDEX.yaml`, its state file and the
  > shared queues under `.claude/skills-state/`, the generated statusboard, and
  > (for code generation) the source files it generated — with the message
  > `<the command you typed> → <what changed>`. It never pushes, never stages
  > anything else, never rewrites history, and skips the commit when nothing
  > changed; other changes in your working tree are left as they are. Change
  > this anytime with `python .claude/sdlc/autocommit.py mode --set off`.
  > Commit each run automatically?
- **options** (exactly these two — the tool adds "Other" on its own):
  1. `Yes, commit after every run (Recommended)` — "One commit per run, named
     by the command that produced it; drafts and aborted runs are committed
     too, marked as such."
  2. `No, I commit myself` — "Nothing is committed on its own; the close card
     names the files each run wrote."

Before asking, run `python .claude/sdlc/autocommit.py mode` (the helper was
installed in step 3) and read its `git:` line. Then record the answer:

```bash
python .claude/sdlc/autocommit.py mode --set <on|off>
```

**Do not ask, and do not run the command, when:** the marker already carries
an `auto_commit.decided_on` (answered on an earlier run — never re-litigate
it), the session is non-interactive, or the `git:` line says the project is
not a repository — in that last case say so in the close card's `Attention:`
row and name `python .claude/sdlc/autocommit.py mode --set on` for after
`git init`. `SDLC_AUTO_COMMIT=off` in the environment overrides everything.
Every skill's close then commits, or not, by reading this answer; none of
them asks again. Mechanics: `references/auto-commit.md`.

### 5 — Report + the one caveat that matters
Summarize what was installed and the action log. Then flag the timing caveat:

> **Claude Code loads hooks from `settings.json` at session start.** A hook added
> mid-session does not fire until the next session. `INDEX.yaml` was generated
> now, and every artifact skill (`sdlc:prd`/`ux`/`design`/`data`/`api`/`arch`/
> `test`/`task`) refreshes it after it writes (Phase 8 of the canonical flow),
> so the map stays current in this session regardless. The hook simply
> guarantees the refresh keeps happening on **manual** `docs/` edits too, from
> next session on.

Suggest the user restart the session (or `/hooks` to verify) if they want the
automatic hook active immediately.

**Self-review & record the run** (CLAUDE.md 15; doctrine:
`${CLAUDE_SKILL_DIR}/../lesson/references/lessons-capture.md`). `setup` has no state file
and no interview, so there are no `lesson_notes` to drain — answer the
self-review questions from that file for this run (did a bundled script fail on
this platform? did an instruction here mislead you? did the installer clobber
or skip something it should not have?). Each yes that matches a raising
condition becomes one `lessons.py add --skill setup …` (at most 2 per run
unless one is a `blocker`). Then record the run — best-effort: a non-zero exit
never blocks the close; note it in `Attention:` and move on. The outcome is
passed explicitly: `complete` normally, `failed` when `wire_setup.py` exited 2
(`partial` installs still record `complete` — the metric says what was kept).

```bash
python .claude/sdlc/lessons.py record-run --skill setup \
  --skill-version "<the skill_version at the end of this file>" \
  --outcome complete \
  --metric targets_written=<the 'targets written' count from the action log> \
  --metric own_toolchain=<1 if the log said [own-toolchain], else 0> \
  --metric wire_exit=<wire_setup.py exit code> \
  --plugin-root "${CLAUDE_SKILL_DIR}/../.."
```

`--skill-version` is this file's `skill_version` (the last line) — `setup` has no
state file to read it from, so pass it. Pass the real numbers from the action
log, never placeholders. On `wire_setup.py` exit 2 use `--outcome failed` and
still pass `wire_exit=2`. If the helper was not installed (the copy step itself
failed), skip this and say so in `Attention:`.

**Commit the run** (CLAUDE.md 20; `references/auto-commit.md`) — the last
action before the card, never a blocker. A re-run at the same version prints
`nothing to commit`, which is correct:

```bash
python .claude/sdlc/autocommit.py commit --skill setup --invocation "/sdlc:setup" \
  --summary "plugin <version> wired - helpers, rules, docs hook, INDEX.yaml"
```

Its one printed line is the card's `Commit:` row; off, or helper absent → no row.

**Close with the card** (CLAUDE.md 14; canonical shape:
`${CLAUDE_SKILL_DIR}/../prd/references/reporting-to-the-user.md`). The timing caveat above
is what belongs in `Attention:` — do not drop it.

```
-- /sdlc:setup - what you have now -------------------
Wrote:     .claude/sdlc/docs_index.py + lessons.py + findings.py + bump_artifact.py
           + autocommit.py, .claude/rules/*, docs/INDEX.yaml, the docs hook in
           .claude/settings.json, the static CLAUDE.md section, the plugin-version marker
Status:    complete - /sdlc:prd can run
Sharing:   lesson reports are {sent automatically | offered each time | not
           shared} - change it with: python .claude/sdlc/lessons.py consent
Commits:   every /sdlc:* run commits its own files: {on | off} - change it
           with: python .claude/sdlc/autocommit.py mode --set on|off
Commit:    {a1b2c3d  /sdlc:setup → <summary> | nothing to commit — only when auto-commit is on}
Attention: hooks load at session start, so the automatic index refresh begins
           next session; every skill also refreshes the index itself, so
           nothing is stale in the meantime
Next:      {the computed next invocation}   ← in a NEW session
Why new:   the artifacts and state files on disk are the handoff, not this
           transcript - and a fresh session is also what activates the hook.
```

In own-toolchain mode the `Status:` row reads
`partial - own index toolchain kept; shared helpers installed - /sdlc:prd can run`
and `Wrote:` lists only what the log says was copied.

**Compute the `Next:` row; never copy the example.** For `/sdlc:setup` it
resolves to:

- **`wire_setup.py` exited non-zero, or the user declined the plan** → `Next:` is
  `/sdlc:setup` again, and `Status:` says what is still unwired.
- **Installed cleanly (complete or partial)** → `/sdlc:prd`, the pipeline
  successor. `setup` is not sharded and has no other successor.

## Re-running / updating
Re-run any time the generator or a helper improves (this skill is the source of
truth for `docs_index.py`; `lesson` and `repair` for the helpers): the installer
overwrites a copied file only when it differs, refreshes the marker's helper
versions, and refreshes the index. Use `--dry-run` to preview.

## Edge cases
- **No `docs/` yet** — expected before `prd`. The index is skipped now and built
  on the first doc write (by the hook next session, or by `prd` on completion).
- **Project runs its own index generator** — detected from the `docs/INDEX.yaml`
  header and the hook commands; all index wiring is left untouched and only the
  generator-agnostic pieces are installed (the log says `[own-toolchain]`, the
  close text `Status: partial`). A hook that merely *reads* `docs/INDEX.yaml`
  (a grep, a validator) is not a generator — the bare filename counts only next
  to a generator verb. `--force-stock` replaces the project's toolchain with the
  stock one and removes the foreign hook entry — pass it only on the user's
  explicit say-so. Regression: `_smoke/wire_selftest.py`.
- **Existing unrelated hooks** — preserved; the SDLC hook is appended as its own
  PostToolUse entry. A pre-existing SDLC hook has its command refreshed in place
  and its entry's matcher left exactly as the project set it.
- **Malformed `settings.json`** — the installer aborts with exit 2 and a clear
  message before writing anything; fix the JSON and re-run.
- **Non-UTF-8 console (Windows cp1252)** — both scripts force UTF-8 stdio, so
  `--show` and the action log print cleanly. The content hash is text-level, so
  a CRLF checkout and an LF checkout hash the same.
- **A shard that is not valid JSON, or two artifacts defining one symbol name**
  — the index still generates; the problem lands in its `warnings:` block and
  under `WARNINGS` in `--check`, never as a crash or a dangling reference.

---

Version history: [`CHANGELOG.md`](CHANGELOG.md) - maintainer-facing,
not loaded into a run's context.

skill_version: "1.24"
