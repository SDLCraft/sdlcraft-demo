# Forward-propagation — fixing at the source and carrying it downstream (sdlc-repair)

Read this on entering Phase 4. Back-propagation found *where* the defect lives;
this file covers *how* to fix it there and how far the fix has to travel.

---

## Blast radius is computed, never guessed

Before editing anything, ask the index who depends on the symbol you are about
to change:

```bash
python .claude/sdlc/docs_index.py --refs <symbol>
```

`setup` wires this graph precisely so an edit's inbound sites can be reconciled
in the same pass (CLAUDE.md, Phase 2 of the canonical flow). The `referenced_by`
set **is** the forward-propagation scope: every artifact in it either changes
with the source or is checked and found unaffected. Nothing outside it needs to
change.

**What `--refs` sees.** The index scans the canonical files AND every
`docs/*__*` shard, and treats *named* symbols as edges beside `PREFIX-NNN`
tokens: DATA-MODEL entities (`--refs User`), ARCH work_units
(`--refs <cid>/<component>/<unit>`, or the bare name when unique), tests
(`--refs TST-NNN`), API operations and design assets. Named references are
matched only inside anchored fields (`touches_entities`, `via_entity`,
`target_symbol`, `targets_work_units`, `via_unit`, `component_ref`,
`depends_on`, `entity_slice.entity`, …), never as bare prose words, so the
`--refs` set is authoritative for ids and named symbols alike. A name the
index cannot resolve lands in its `dangling_warnings` block — treat one of
those on the symbol you are editing as an inbound site the graph could not
place, and resolve it by hand before trusting the radius.

If the project never ran `/sdlc:setup` there is no index at all. Fall back to
`crosscheck_artifacts.py`'s own reference walk plus the same grep, and say in
the resolution record that the radius was derived without the index.

**The checklist.** Print the radius grouped by artifact, one line per inbound
site, and carry it through Phase 4 as a checklist. A site leaves the list in
exactly one of three ways — *edited*, *re-sliced* (a task embed moved by
`reslice_embeds.py`), or *unaffected* with one clause saying why. A site that
is none of the three at the end of Phase 4 is an incomplete propagation, and
the finding does not close — SKILL.md Phase 6 says which state it waits in, per
mode: a `re-invoke` stays `triaged` carrying its block, a `surgical` fix is
left `open` with its progress on one evidence line.

## Three modes

The choice turns on two questions: **does the fix change the SET of downstream
items, or only their CONTENT?** And when the set: **is the change purely
additive and fully determined by the walk just performed?**

| | `surgical` | `additive` | `re-invoke` |
|---|---|---|---|
| **When** | content of existing items changes: a field added to a contract, a threshold corrected, a statement disambiguated, a stale embed re-sliced, a null REQUIRED field filled | items are ADDED and nothing else, and every field the new items need follows from the walk: a TST for a branch the contract already states plus its test task, a work_unit the summary already names plus its impl task and test, an entity trace | the set changes in a way the walk cannot determine: a removed/renamed component, work_unit, entity, operation, surface, TST or task; a restructured boundary; a new item whose content needs an interview |
| **Who edits** | this skill, directly — scripted below | this skill, directly — the source per surgical, the new items by hand in their own artifacts, proven by the validators | the owning skill, re-invoked by the user (`--reconcile` first) |
| **Cost** | minutes, no interview | minutes, no interview | a scoped reconcile per downstream stage; a full interview only when the reconcile form is not enough |
| **Risk** | none if the radius was computed and every checklist site closed | none if the four-part criterion holds — the validators prove the result | none — the skills' own gates apply |

When in doubt between `surgical` and the set modes, prefer a set mode: a
surgical edit that *should* have changed the set leaves a downstream artifact
internally consistent but missing an item, and no validator will catch it —
coverage gates only check the items that exist. Between `additive` and
`re-invoke`, "in doubt" means one of the four criteria actually fails, not that
the change feels big (aicf LSN-019 / LSN-040: one fully-determined TST routed
to re-invoke cost two downstream interviews and discarded the walk). A finding
stamped `recurrence_of` (repaired before, came back) starts with `re-invoke`
in position 1 — never a refusal of the in-run modes, just a changed default.
When such a finding's fix also meets the four-part criterion, `additive` leads
anyway: the recurrence default changes which mode leads, never which modes are
offered (SKILL.md Phase 3).

## Surgical mode — scripted

Order matters: source first, then outward along the reference graph, then
verify. Editing a downstream copy before its source leaves a window where the
two disagree and a concurrent doctor run reports a defect that is mid-repair.
Nothing in this sequence is a hand edit to a task JSON.

1. **Edit the source artifact.** Make the smallest change that records the
   missing or corrected fact. Read and edit by `INDEX.yaml` line range.
2. **Bump its metadata in the same write** — one call:

   ```bash
   python "${CLAUDE_SKILL_DIR}/bump_artifact.py" --file docs/<SOURCE> --summary "<what changed and why>" --by sdlc-repair
   ```

   It bumps `metadata.<name>_version` (minor), prepends the canonical
   changelog line (`"<version> (<YYYY-MM-DD>): <summary>"`, newest first,
   append-only), refreshes `last_updated`, and keeps every comment. It
   **refuses** (exit 1) when the on-disk version is already above the newest
   changelog line — that is a bump somebody made without a line, or lines out
   of order (the ARCH 1.36 / changelog 1.25 shape). Fix the changelog by hand
   first; `--force` is for the case where you have already done so and the
   tool cannot tell. A repair that leaves no changelog trace is
   indistinguishable from a hand-edit later.
3. **Re-derive any prose the change invalidated** (CLAUDE.md §8): if the source
   carries a sentence restating a count you just changed, fix the sentence or
   delete it in the same write.
4. **Walk the rest of the checklist by hand — every inbound site that is not a
   task embed.** For each, apply the corresponding edit (a TST acceptance that
   quotes the old contract, an entity trace, a UX shard) with its own
   `bump_artifact.py` call, or record why it is unaffected. Task embeds are
   not edited here — step 6 moves them. **Retired-token sweep:** when the fix
   REMOVES or RENAMES a named token (an input parameter, a CLI flag, a field,
   an enum member, a literal), the reference graph cannot see the sites that
   still use the old name — nothing references a name that no longer exists —
   so sweep the corpus for it with a plain text search - `grep -rn <token>
   docs/` (Grep over `docs/`; the index's `--find` matches symbols, not
   prose, so it is not this sweep). Every hit joins the checklist and leaves it the
   same three ways, changelog lines excepted; the typical miss is a sibling
   test in the very file you just edited (aicf LSN-074: one run reconciled
   five artifacts and shipped a test that still passed the removed
   parameter). The close card names the token, the hit count and each hit's
   disposition.
5. **Stamp every artifact you reconciled by hand, upstream-first.** A hand
   edit moves an artifact's content but not its `upstream_provenance`, so the
   next `docs_index.py --stale` (and every validator's provenance warning)
   reads the change you just reviewed as unreviewed drift. Record the review:

   ```bash
   python .claude/sdlc/docs_index.py --stamp docs/<artifact> --upstream docs/<reviewed-upstream> --hold-upstream docs/<every-other-recorded-upstream>
   # one flag per file - each flag takes exactly one: --upstream for what this run reviewed,
   # --hold-upstream for every other entry in the artifact's metadata.upstream_provenance
   ```

   Run it through the copy
   `${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks:
   `--hold-upstream` needs `docs_index.py` capability 6, an older install
   rejects it with exit 2, and the plugin's form is
   `"${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs --stamp …`
   (ledger IMP-108). Order matters twice. A
   stamp rewrites the stamped file's metadata and therefore its own hash, so
   stamp in pipeline order (ARCH before TEST-STRATEGY before a task shard) and
   never before the last hand edit to that file. And stamp BEFORE step 6: the
   re-slice stamps the task shard against the upstream bytes it sees, so a
   stamp that lands after it moves those bytes and puts the shard behind
   again for a metadata-only write (aicf LSN-070 / LSN-073: stale rows 23 → 28
   on artifacts the run had just reconciled, then a delta review over
   nothing). A shard that consumed a hand-reconciled upstream the re-slice
   does not touch gets its own `--stamp` after step 6.

   **What a stamp claims.** `upstream_provenance` records "this artifact was
   reviewed against upstream@hash" — every delta between the recorded hash
   and the current one, not only the one this run made. A repair reviews one
   finding's change, so it may stamp a pair only when that change IS the
   whole delta: the pair was fresh before the run's first write. Phase 2's
   `doctor.py --provenance --json` (`.claude/skills-state/sdlc-repair.doctor.json`,
   key `provenance.stale`) is that pre-run snapshot. A pair it lists already
   owed an older, unreviewed delta to `/sdlc:<skill> … --reconcile`: stamping
   it now forges that review, and leaving it is not a missed stamp. Hold it
   (`--hold-upstream docs/Y`), name the pair on the close card (`Attention:
   pre-existing: docs/X vs docs/Y, owed to /sdlc:task <cid> --reconcile`) and
   route the reconcile in `Next:`. An artifact with no fresh reviewed pair is
   not stamped at all. The reconcile skills stamp freely because they review
   the whole `--drift` delta; that is the difference (ledger IMP-099, aicf
   LSN-080: a `ci_integration` fix landed in a TASKS.json that already owed a
   TEST-STRATEGY reconcile — following the step would have forged it,
   skipping it drew the "missed stamp" label).

   **Hold every recorded upstream this run did not review.** `--stamp`
   re-hashes EVERY upstream the artifact already records, not only the ones
   named: `--upstream` adds to that set, it never narrows it. A stamp for the
   one pair this run reviewed would otherwise mark every other recorded
   upstream reviewed too, a pre-existing pair's owed delta included, and
   `--drift`, `--stale` and the statusboard would stop showing it (ledger
   IMP-106). `--hold-upstream docs/<file>` keeps that entry byte-identical.
   So: `--upstream` for each pair this run reviewed that was fresh before its
   first write, `--hold-upstream` for every other entry in the artifact's
   `metadata.upstream_provenance`.

   **Read what the stamp printed.** For each upstream it re-hashed that had
   moved since the last stamp, `--stamp` prints `re-stamped <upstream>: <what
   moved> since the last stamp - reviewed by this run?`. For an upstream this
   run reviewed, that is expected. For any other, a hold is missing: restore
   the artifact's old record of that upstream from git (`git diff
   docs/<artifact>` shows the old lines), confirm `--drift docs/<artifact>`
   names that upstream again, and stamp again with the hold. The printout
   catches a missing hold after the fact; the holds are what prevent the
   forgery.

   The re-slice of step 6 refreshes
   a shard's stamp the same way, so for such a pair it takes `--hold-stamp
   docs/<upstream>`: the embed moves (a mechanical copy is not a review), the
   stamp stays, the owed reconcile still sees the whole delta.
6. **Re-slice every embed copied from the changed symbol — LAST.** One call,
   never a hand edit (demo edition, no `${CLAUDE_SKILL_DIR}/../task/SKILL.md`:
   skip this step and step 8 and say so — SKILL.md Phase 4). Last, because the
   re-slice stamps the shard against the upstream bytes as they are *now* —
   after every hand edit of step 4 and every stamp of step 5:

   ```bash
   python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --symbol <cid>/<component>/<work_unit>
   python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --tst TST-NNN
   python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --entity <Name>
   python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --operation <operation_id>
   ```

   It rewrites only the compared embed fields (`interface_contract`,
   `unit_kind`, `unit_summary`, `test_spec`, `family_contract`,
   `operation_contract`, `entity_slice`, `design_spec`, `cli_contract`,
   `fixture_briefs.fixture_strategy`) from the *current* upstream, preserves
   every other key, re-derives seeded prose (a description or acceptance line
   that was byte-equal to the *previous* upstream text follows it — the unit's
   `satisfies_acceptance` and the TST's `description` ride along from 1.7 for
   exactly this) and each impl task's test line from `targets_work_units`
   when a re-target made it wrong, bumps the
   shard's `tasks_container_version` with a changelog line, refreshes the
   shard's `upstream_provenance` hash for the changed upstream (so the next
   `/sdlc:task` does not re-run a delta review for a change repair already
   handled), and prints `qid  <fingerprint before> -> <fingerprint after>` per
   moved task. It never touches `config_keys` or authored `fixture_briefs`.
   This does **not** contradict CLAUDE.md §9 — that rule forbids patching an
   embed *instead of* its source. Fixing the source and re-slicing in the same
   pass is exactly what it asks for. Patching only the embed is what it forbids.
7. **Verify** — see below. `reslice_embeds.py --check` must be silent for the
   container(s) touched.
8. **Name the stale tasks.** The handback needs no new mechanism, but the
   resolution names what moved:

   ```bash
   python "${CLAUDE_SKILL_DIR}/../code/topo_order.py" --scope <cid> --state .claude/skills-state/sdlc-code.state.yaml
   python "${CLAUDE_SKILL_DIR}/../code/topo_order.py" --affected FR-012 FR-013     # after a PRD change
   ```

   `stale` (build-relevant content moved), `ring_recheck` (a provider's
   contract moved, consumers re-run their ring) and `--affected` (done tasks
   whose `implements` / `test_spec.covers` name the changed requirement) go
   into `resolution.stale_tasks`, each with the reason `topo_order` gives.
   `refreshed` tasks (only the whole-hash moved) are not stale and are not
   listed.

## Additive mode — author the determined item

The criterion, all four required (SKILL.md Phase 4 states the same list):
**purely additive** (nothing removed, renamed or re-scoped), **fully
determined** (every schema-required field of the new item follows from the
source slice, its siblings and the walk — no decision left), **validator-
provable** (Phase 5 green afterwards) and **the obligation chain closes in
this run** (a TST obliges its `kind: test` task; a work_unit obliges its impl
task and a test or a structured deferral; an entity obliges its traces).

The sequence, for the canonical case — a contract states a branch no test
exercises, so the strategy is missing one TST:

1. Steps 1–2 of surgical on the source (here `TEST-STRATEGY__<cid>.yaml`):
   add the TST — `tst_id` = next id in the shard's sequence, `tier`,
   `component_ref` and `targets_work_units` from the work_unit, `covers` from
   the impl task's `implements`, `directives` / `acceptance` restating the
   contract's `raises` line — then `bump_artifact.py`.
2. Author the realizing `kind: test` task in `TASKS__<cid>.json`: next `TSK`
   id, `implements_tests: [TST-NNN]`, `test_spec` copied from the TST
   (tier / targets_work_units / directives / acceptance / covers), `depends_on` the subject's impl
   task and the container's `test_infrastructure` task when one exists
   (checks 27/28), `target_files` under the container's test root, one
   acceptance line; then `bump_artifact.py --patch` the shard. A TASKS file
   always takes a patch bump: its minor version gates checks (check 18 from
   1.4), and a minor bump would switch them on for tasks this edit never
   touched — turning a consumable graph red.
3. **Stamp what you authored into, upstream-first**, under the surgical
   checklist's step 5 rules above — here `docs_index.py --stamp docs/TASKS__<cid>.json --upstream
   docs/TEST-STRATEGY__<cid>.yaml --hold-upstream docs/<every-other-recorded-upstream>`,
   the source stamped before the shard that copies it. This mode may claim the
   pair because it WROTE the whole delta between the recorded upstream and the
   current one, which is exactly what a stamp asserts; every other recorded
   upstream still takes `--hold-upstream`, a pair the Phase 2 snapshot already
   listed is still held and named on the close card, and the `re-stamped …`
   printout is read exactly as that step 5 says. Skip it and the shard you just
   authored into is left behind its own upstream, reported as `re-stamp only`
   and routed to the `/sdlc:task <cid> --reconcile` this mode exists to avoid.
4. Refresh the index; verify (below): `reslice_embeds.py --docs-dir docs
   --container <cid> --all --check`, both validators, `doctor.py --quick` —
   bare, exit codes captured. `topo_order.py --scope <cid>` now lists the
   new task as pending; the ledger is not touched.
5. Close `resolved`, `mode: additive`, `artifacts_touched` both files, a
   `source` hop for the strategy and a `downstream` hop for the task shard,
   `downstream_rerun: []`.

A new work_unit follows the same shape one stage earlier (ARCH shard → TST →
test task → impl task with its `interface_contract` copied from the unit),
and it is exactly the case where criterion 4 most often fails — then the mode
is `re-invoke`, and `/sdlc:test <cid>` runs before `/sdlc:task <cid>`.

## Re-invoke mode

This skill does not run other skills. It produces the **exact command sequence**
and stops, because those skills are interviews and the user owns them.

- Order the sequence by pipeline position (`prd → ux → design → data → api →
  arch → test → task`), including only the stages the radius actually touches.
- Print the **`--reconcile` forms first** — every consumer stage has one
  (`/sdlc:ux --reconcile`, `/sdlc:design --reconcile`, `/sdlc:data
  --reconcile`, `/sdlc:api --reconcile`, `/sdlc:arch <cid> --reconcile`,
  `/sdlc:test <cid> --reconcile`, `/sdlc:task <cid> --reconcile`: no
  interview, the exact item delta, one confirmation card per class of
  change). Name the container on arch/test/task: `downstream_rerun` is matched
  to files by its commands, and a bare sharded `--reconcile` maps to the
  system file only. When the owed file IS the system one, write
  `/sdlc:task --system --reconcile` rather than the bare form — that is the
  spelling the skill defines for a single named file, and the bare form means
  "walk every stale file" (ledger IMP-145). The full interview form comes
  second, as the fallback when a reconcile stops at a structural question.
- **Write `resolution.handoff`** — the walk's conclusion per downstream item,
  for a session that never saw the walk:

  ```yaml
  handoff:
    - artifact: docs/TEST-STRATEGY__demo-api.yaml   # a file an owed command rewrites
      key: demo-api/api/archive-task                # the item as --drift prints it; null = whole file
      note: "now raises NotFound for an unknown id; that branch needs a unit TST covering FR-014"
      basis: measured                               # REQUIRED per note: measured = read
                                                    #   off the artifacts it names;
                                                    #   inferred = the reconcile verifies
                                                    #   it there before it writes
  ```

  Each reconcile reads its notes with `findings.py list --owed-by docs/<file>`
  and offers them as the matching card's position-1 proposal — a candidate the
  user confirms, never a silent write. The `bump_artifact.py --summary` line
  is the other half of the handoff: every reconcile's `--drift` quotes the
  upstream's changelog since its stamp as the "why".
- **`/sdlc:test <cid>` before `/sdlc:task <cid>` whenever the fix minted a
  work_unit** (or any new subject): task wires a test task's `depends_on` to
  the impl task of the subject the *test* names (`targets_work_units`, CLAUDE.md
  §12). Run task first and the new unit gets an impl task with no test task,
  then test names it, then task has to run again — the double hop.
- Say what each stage will do: every downstream skill already carries the §7
  **upstream-change reconciliation** contract, so on re-invocation it detects
  the changed content hash, classifies the delta (added / removed / modified,
  by id family and by name), and runs a delta-review before its interview.
  That machinery is why repair does not need to drive those edits itself.
- Fix the source artifact first (steps 1–3 of surgical mode) so the
  re-invocations have something correct to reconcile against.
- **Always** record the sequence in the finding's
  `resolution.downstream_rerun` (the queue validator refuses a `re-invoke`
  without one from `findings_file_version: "2"`, and warns below it — so
  compute the sequence before the write and never park an empty one),
  together with the `artifacts_touched` so far, and leave the
  finding `triaged` — not `resolved` — until the user reports the
  re-invocations done or `doctor.py --provenance` prints its
  `can be marked resolved` hint for it. A finding marked resolved while its
  downstream stages are still stale is a lie the next doctor sweep will catch
  anyway.

**There is no `--propagate`.** A flag that walks the chain and re-runs
interviews on the user's behalf would be a chain walker, and it is rejected on
purpose: the interviews are the user's. The most `--propagate` could ever mean
is "reslice + refresh provenance + print the residual re-invoke list" — which
is what the sequence above already is. Nor does the user have to walk it by
hand: each reconcile's `Next:` is the next row of `docs_index.py --stale`, so
the printed sequence walks itself, and the last reconcile routes back to
`/sdlc:repair FND-NNN`, which verifies the hops and closes the finding.

## Verification (every mode, every time)

Run each command **bare** and record the captured numeric exit code — never read
an exit status after a pipe (CLAUDE.md §11). Pass the **system file** of every
touched family: the validators glob their own `__<slug>` siblings, and a shard
path (`--path docs/ARCH__demo-api.yaml`) is refused.

```bash
python "${CLAUDE_SKILL_DIR}/../arch/validate_schema.py" --path docs/ARCH.yaml
python "${CLAUDE_SKILL_DIR}/../test/validate_schema.py" --path docs/TEST-STRATEGY.yaml
python "${CLAUDE_SKILL_DIR}/../task/validate_schema.py" --path docs/TASKS.json
python "${CLAUDE_SKILL_DIR}/../task/reslice_embeds.py" --docs-dir docs --container <cid> --all --check
python "${CLAUDE_SKILL_DIR}/../task/crosscheck_artifacts.py" --docs-dir docs
python .claude/sdlc/docs_index.py                 # regenerate the index - the PROJECT's copy only;
                                                  # absent -> skip and say so, never the plugin's copy (SKILL.md Phase 5)
python .claude/sdlc/docs_index.py --check         # dangling-reference gate
python .claude/sdlc/docs_index.py --stale         # must list nothing this run reconciled - a row here is a missed stamp (step 5),
                                                  # the `re-stamp only` rows included (nothing the shard cites changed, so the
                                                  # review is cheap - but the stamp is still owed), unless the Phase 2 snapshot
                                                  # already held it: a pre-existing pair, owed to
                                                  # its own --reconcile - named on the close card, never stamped
```

The `test` and `task` lines run only where those skills ship (demo edition:
skip them, and say so).

Validate **every artifact touched**, not just the source. A surgical edit that
fixes the source and breaks a downstream coverage gate is a worse state than the
one you started in.

Compare against the Phase-2 `baseline_checks`: a validator that was already red
before this repair, and is still red for an unrelated reason, is reported with
its before/after exit codes and explicitly not claimed. Record both numbers.

## Propagation hops in the resolution

Every place the fix had to land is one `resolution.propagation` hop, verified
on disk before the finding closes:

| hop | what it is | how it is verified |
|---|---|---|
| `source` | the artifact whose content was wrong | its skill validator exit 0 |
| `embed` | a task embed copied from the changed symbol | `reslice_embeds.py --check` exit 0 for the container |
| `code` | generated source that `/sdlc:code` will regenerate | the task is listed as `stale` by `topo_order.py` (the regeneration itself is code's job; the hop is verified when the ledger shows it) |

`resolved` requires every listed hop to carry `verified_at` (queue version 2).
This is the rule the FND-016 → FND-023 → FND-034 sequence taught: a fix whose
propagation stopped one hop short came back twice under new ids.

## Handback to codegen

There is no bespoke handback mechanism, and there should not be. Editing a task
artifact changes each affected task's build-relevant content, which changes its
`build_fingerprint`, which `/sdlc:code` already classifies as **`stale`** and
gates at its plan approval (regenerate / keep); a moved provider contract marks
its consumers `ring_recheck`; a PRD or DATA change restales the tasks that
consumed the changed slice through their `context_fingerprint`. The chain closes
itself.

Then the close report's next step is a plain command:

```
Next:  /sdlc:code <cid>          ← in a NEW session
       2 tasks are now stale and will be offered for regeneration.
```

Fresh session for the same reason it always is: `/sdlc:code`'s handoff is its
ledger, not a transcript (`../../code/references/session-and-limits.md`).

## Batching — the recommended loop

Findings arrive in batches, and the cheapest loop treats them that way:

1. `/sdlc:repair --check --no-emit` — pre-flight; nothing recorded.
2. `/sdlc:code <cid>` to a **component boundary**. Findings batch there.
   Continue to the *container* boundary when the blocked cascade is confined
   to the component; stop when a finding blocks later components or two
   findings name one symbol.
3. ONE `/sdlc:repair` over the whole batch. Surgical findings are fixed and
   re-sliced in-session; set changes fix the source and print their
   `--reconcile` commands (test before task).
4. The `--reconcile` runs — only when printed: run the first, each names the
   next, and the last routes back to `/sdlc:repair FND-NNN` to close the
   finding.
5. `/sdlc:code <cid>` in a NEW session; at its plan gate: regenerate
   `stale` / `affected`, ring-check `ring_recheck`, silently keep `refreshed`.

Never repair mid-component: the ledger and the breadcrumbs assume the artifact
chain is still while a component is in flight.
