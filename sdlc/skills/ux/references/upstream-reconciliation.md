# Upstream-change re-invocation — canonical mechanics

**This is the shared, canonical specification for what happens when an SDLC
artifact skill is invoked a second (or third…) time for the same output and
one or more of its *upstream* artifacts has changed in between.** It is the
detailed companion to CLAUDE.md cross-skill convention §7. Every consumer
skill (`ux`, `design`, `data`, `api`, `arch`, `test`, `task` — all implemented
consumers today; `deploy` remains planned) references this file; `prd` does
not (it consumes no upstream artifact).

Downstream skills point here with the repo-relative path
`${CLAUDE_SKILL_DIR}/../ux/references/upstream-reconciliation.md`.

## Contents

- [Three meanings of re-invocation](#three-meanings-of-re-invocation)
- [The provenance record](#the-provenance-record)
- [Step 1 — record provenance at write time (Phase 7/8)](#step-1)
- [Step 2 — detect change on re-run (Phase 2)](#step-2)
- [Step 3 — classify the delta](#step-3)
- [Name-addressed items — diff by natural key](#name-addressed)
- [Step 4 — the delta-review pass (one AskUserQuestion sweep)](#step-4)
- [Step 5 — reconcile, then continue the normal flow](#step-5)
- [The `--reconcile` form](#reconcile-form) (+ per-skill specifics)
- [The delta-review state slot](#delta-review-state)
- [Edge cases](#edge-cases)

## Three meanings of re-invocation

When a skill is invoked and its output yaml already exists, the user means
one of three things. Disambiguate before doing anything — they are handled
by different machinery:

| Meaning | Trigger | Handled by |
|---|---|---|
| **Resume** an interrupted session | state file `status: in_progress` | the state-file resume prompt (Phase 1) |
| **Refine / extend** deliberately | state `complete`/`aborted`, upstream *unchanged* | [the refine-scoping step](#refine-scoping) below, then the merge/update flow (`references/merge-validate.md`) |
| **Reconcile** because upstream changed | state `complete`/`aborted`, upstream *changed* | **this document** — in the plain invocation before its interview, or alone as `--reconcile` |

The first two are well-defined and uniform across skills. This document
governs the third — the case the user most often re-invokes for ("the
PRD/UX/DATA/API moved under me") — and the refine row's scoping step below.
The three are not mutually exclusive in one run (a resume can also discover
upstream drift); run resume first, then the delta-review below before the
theme interview.

### Refine scoping (before Phase 7 merge) {#refine-scoping}

A `complete`/`aborted` re-invocation with upstream unchanged still needs a
scope before Phase 7's merge — otherwise the agent either re-walks every
theme or invents its own scoping question each run. Open only:

1. **The themes the user names** — or, for a sharded skill, the shard the
   user names (a surface, a resource, a container).
2. **The §7 delta items**, if a delta-review just ran.
3. **The non-confirmed set** — an open `QUE` entry that blocks a theme, an
   inventory field the current schema defines that the artifact still
   holds as `null`, any bucket a `finding` names, and a legacy plain-string
   ACR/QUE id, routed through the skill's id-migration helper (prd's
   `migrate_ids.py`) rather than a buried inventory hint.

Confirm everything else in one summary; do not re-walk it question by
question. `prd` is exempt from `--reconcile` (it consumes no upstream) but
not from this scoping step — its own Phase 1 points here too.

## The provenance record

The output artifact carries `metadata.upstream_provenance`: a snapshot,
written at every save, of exactly which upstream artifacts this output was
built against. One entry per upstream artifact consumed:

```yaml
metadata:
  upstream_provenance:
    - file: docs/PRD.yaml
      session_id: <uuid4>
      last_updated: <iso8601>
      sha256: <16-hex>
      items:                      # every item the upstream defines -> body hash
        FR-001: <12-hex>          #   (written by `docs_index.py --stamp`)
        FR-002: <12-hex>
    - {file: docs/DATA-MODEL.yaml, session_id: <uuid4>, last_updated: <iso8601>, sha256: <16-hex>}
```

The flow form (second entry) is the legacy hand-written record and stays
valid; the block form with `items` is what `--stamp` writes and what makes
the delta exact (below).

Field sources:

- `file` — the upstream artifact path.
- `session_id` — the upstream's `metadata.session_id` at read time.
- `last_updated` — the upstream's `metadata.last_updated` at read time.
- `sha256` — the **16-hex content-hash prefix** of the upstream file. This is
  the *same* primitive `setup`'s `docs_index.py` computes and prints: read it
  from `docs/INDEX.yaml.generated_from[<file>].sha256` (shards — every
  `docs/*__*` sub-artifact — are recorded there too), or run
  `python .claude/sdlc/docs_index.py --hash docs/<file>`. Only when neither
  is available (the project never ran `/sdlc:setup`), compute it inline as
  the **text-level** hash:
  `sha256(path.read_text(encoding='utf-8').encode()).hexdigest()[:16]`.
  Never hash raw file bytes — a byte hash differs between CRLF and LF
  checkouts of the same content; the text-level hash does not.
- `items` — a map of every symbol the upstream defines (work units as
  `<cid>/<component>/<unit>`, components, `TST-NNN`, entities, `FR-NNN` and
  the other PRD item families, tasks) to a 12-hex **body hash**. Recorded by
  `docs_index.py --stamp`; never written by hand. A file hash says THAT an
  upstream moved — the items map says WHICH items were added, removed or
  changed, without git and without guessing from what this artifact happens
  to reference. A work unit's hash ignores its declaration-only fields
  (`touches_entities`, `status`), so an entity-trace backfill is not a
  change; only behaviour-bearing fields are.

Unlike `changelog` (append-only history), `upstream_provenance` is a
**replace-on-write snapshot** — it always reflects the upstream state of the
*latest* write. The validator type-checks it as a list of mappings only; it
enforces no field shape (manual edits and partial records are tolerated).

Why a content hash and not just `session_id`? `session_id` only changes when
the upstream skill *writes*. It does **not** change when the user hand-edits
`PRD.yaml` directly — the single most common way upstream drifts. The hash
catches hand-edits; `session_id`/`last_updated` are kept as human-legible
context and a fallback when no hash is available.

## Step 1 — record provenance at write time (Phase 7/8) {#step-1}

Whenever the skill writes its output, (re)write `metadata.upstream_provenance`
with the current snapshot of every upstream artifact it consumed this run.
Do this for both fresh writes and merges. For skills with per-item
sub-artifacts that are authored in separate invocations (`arch` containers),
each sub-artifact records the provenance of what *it* consumed at *its* write
time — so a container drilled weeks after the system interview carries its
own, possibly newer, baseline.

**Write it with the helper, after the artifact is on disk:**

```bash
python .claude/sdlc/docs_index.py --stamp docs/<THIS-ARTIFACT-or-shard> \
    --upstream docs/<upstream-1> --upstream docs/<upstream-2> ...
```

One `--upstream` per artifact consumed this run (entries already recorded are
kept and refreshed). It writes only the artifact named, so run it before the
validator and before `docs_index.py` regenerates the index. When the project
has no installed copy (it generates `docs/INDEX.yaml` with its own tool), run
the plugin's copy instead — `python
"${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs --stamp …` — it
still writes nothing but the artifact. Only when neither can run, hand-write
the four scalar fields per entry as above (no `items`); the next
re-invocation then diffs by the fallback method and says so. An installed copy
older than the plugin's counts as having none: every `python
.claude/sdlc/docs_index.py …` in this file runs the copy
`${CLAUDE_SKILL_DIR}/../setup/references/helper-resolution.md` picks once per
run.

## Step 2 — detect change on re-run (Phase 2) {#step-2}

After the input scan, if the output already exists and carries
`upstream_provenance`, detection is one command:

```bash
python .claude/sdlc/docs_index.py --drift docs/<THIS-ARTIFACT-or-shard>
```

- **exit 0** — every recorded upstream hash matches: no drift.
- **exit 1** — an upstream moved: run the delta review (Step 4). The report
  IS Step 3's classification: when the stamp carries an `items` map it names,
  per family, exactly which items were **added upstream**, **removed
  upstream** (and which of those this artifact references) and **changed in
  body** — take those lists as the delta, verbatim. Without an `items` map
  (a stamp written by hand or by an older version) the report falls back to
  this artifact's own references as the old set, subtracts its structured
  `deferrals`, and says the residue "cannot be told apart" — read the
  "Name-addressed items" section below for what that residue means before
  treating it as a delta. Shards are recorded in `generated_from` too, so a
  container-mode artifact (`ARCH__<cid>`, `TEST-STRATEGY__<cid>`, …) gets
  the same treatment.
- **helper absent** — the project has no installed copy (own index
  generator): run the plugin's copy, `python
  "${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs --drift
  docs/<file>`; it reads everything in memory and writes nothing. A stamp
  with no `items` map is diffed against the committed revision whose text
  hash equals the recorded `sha256` when history holds one ("recovered from
  git" — the helper searches history itself); only an
  uncommitted stamp, which matches no revision, leaves the residue below.
  Never dig through git by hand.
- **exit 2, or neither copy can run** — fall back to a manual compare: for
  each provenance entry, read the upstream's current hash from
  `docs/INDEX.yaml.generated_from[<file>].sha256`, or run
  `docs_index.py --hash docs/<file>`, else compute the text-level hash
  inline (see "The provenance record" above), and classify:
  - **unchanged** — recorded `sha256` equals current. Skip it.
  - **changed** — `sha256` differs (or, if no hash is recorded, `session_id`
    differs). Mark for delta classification (Step 3).
  - **no-baseline** — the output predates this convention (no
    `upstream_provenance` at all, or no entry for this file). We can't diff;
    recommend a coverage-driven review (Step 4 falls back to "review all
    traces against current upstream") and write a fresh provenance snapshot
    going forward.

If every upstream is **unchanged**, there is no drift: this is a *refine*,
not a *reconcile* — fall through to the normal merge flow and do not run the
delta-review.

## Step 3 — classify the delta {#step-3}

For each **changed** upstream, diff its ID families (the families named in its
`conventions.artifact_ids`) against the ids this output references. Three
buckets:

- **Added** — ids now in the upstream that this output does not yet consume.
  These already surface via the coverage cross-checks; the delta-review names
  them up front so they aren't only discovered at validation time.
- **Removed** — ids this output references that no longer exist upstream.
  This is the existing stale-ref case (CLAUDE.md §4) — never silently delete;
  ask per ref.
- **Modified** — ids present in *both* the recorded and current upstream
  whose **body changed while the id stayed stable** (a requirement reworded,
  an entity gaining fields, a DTO reshaped). With an `items` map in the
  stamp, `--drift` names them exactly ("changed in body (FR-002, WKF-003)")
  — walk only those, re-reading their *current* slices (via `INDEX.yaml`),
  so the user confirms or adjusts. A work unit changed only in
  `touches_entities` or `status` is not on that list on purpose: nothing a
  downstream artifact asserts depends on those fields. Without an `items`
  map, file-level hashing tells you the upstream moved but cannot pinpoint
  *which* item; so:
  - If a changed upstream has a non-empty add/remove set, surface those
    precisely (above).
  - If a changed upstream's id *set* is identical to the recorded one, the
    change is purely in item bodies. Surface it honestly: "PRD changed but its
    FR/WKF id set is unchanged — descriptions or fields were edited." Offer to
    walk the upstream items this output traces, re-reading their *current*
    slices (via `INDEX.yaml`), so the user confirms or adjusts — and re-stamp
    at write time so the next run is exact.

## Name-addressed items — diff by natural key {#name-addressed}

Not every upstream item carries a `PREFIX-NNN` id. Work units, components,
entities and tasks are addressed by NAME, and a delta that only diffs id
families files every one of them under "bodies may have changed — walk
everything". They diff just as precisely — by their **natural keys**:

| item (upstream)     | natural key |
|---------------------|---|
| ARCH work_units     | `(component_id, name)` — qualified `<cid>/<component>/<unit>` |
| ARCH components     | `component_id` |
| TEST-STRATEGY tests | `tst_id` (`TST-NNN`, prefixed forms included) |
| DATA-MODEL entities | the `entities.<Name>` mapping key |
| TASKS tasks         | `target_symbol` (impl) \| `implements_tests` (test tasks) |

**The stamp's `items` map is the old snapshot.** It records every key the
upstream defined when this artifact was last written, so `--drift` diffs the
key set exactly: **added** (defined upstream now, absent from the snapshot),
**removed** (in the snapshot, no longer defined anywhere — and which of those
this artifact references), **modified** (key stable, body hash changed).
`docs_index.py --drift` prints the name-addressed families (entities, work
units, TSTs, tasks) beside the id families.

**The artifact's own references are NOT a snapshot** — they were used as one
before the items map existed, and the shortcut is exact only where this
artifact covers the family completely, i.e. where a BLOCKING trace-or-defer
gate holds (a task graph builds or defers every work unit). Where coverage of
the family is advisory — a test strategy targets the work units it chose to
test and leaves the rest to other tiers — "defined upstream but not referenced
here" is the sum of *new since the last write* and *never covered*, and the
two cannot be told apart without the snapshot. On one project that meant a
45-item "delta" for a reconcile whose true set change was one unit. So, when
`--drift` reports by the fallback method (no `items` map,
and no committed revision matched the recorded hash — the helper tries git
first), print the residue as a **backlog line** — "N upstream items are targeted by
nothing and deferred by nothing; the last write recorded no snapshot, so
which of them are new is unknown" — never as the delta, and let the user
pick the items to treat as new. Re-stamping at this run's write makes the
next reconcile exact.

Every consumer skill exposes exactly this delta as its `--reconcile` form — see
"The `--reconcile` form" below.

## Step 4 — the delta-review pass (one AskUserQuestion sweep) {#step-4}

Present a **single consolidated summary** across all changed upstreams before
the theme interview begins — don't drip-feed one upstream at a time. The
channel rule applies here too (`../../prd/references/importance-flows.md`,
AUTHORING §18): the summary either rides inside the first resolve
question's text below (fold it in, then batch as normal), or it is printed
alone and the turn ENDS there — no `AskUserQuestion` call in the same
turn — taking the user's typed reply before the resolve batch opens next
turn. Printing the summary and calling `AskUserQuestion` in the same turn
is the defect this rule forbids: the markdown may not render. Lead with
what moved:

> Since this `<OUTPUT>` was last written:
> - `docs/PRD.yaml` changed (added FR-014, FR-015; removed FR-009; bodies of
>   FR-002, WKF-003 may have changed).
> - `docs/DATA-MODEL.yaml` unchanged.

**An added item is a candidate before it is a decision.** The first interview
never showed the user a bare "FR-097 — incorporate / ignore / defer?" prompt:
it met FR-097 through the skill's own candidate-generation step (`ux`:
`surface-discovery.md` Step 1b/1c — an FR or entity whose text names a
`<root_command> <verb>` in backticks, or a screen, is a surface candidate;
`data`: an FR naming a persisted thing is an entity candidate; `arch`: a
component / work-unit candidate). A re-run owes every **added** item that same
pass: run the discovery step over the added item's *text* first, and when it
yields a candidate, position 1 is **incorporate — add `<candidate>`**, with the
candidate named, never a bare "incorporate". Read the whole item: one FR often
carries several clauses — a content rule *and* the command that exposes it —
and the coverage gates are whole-item (an FR is traced or deferred as one), so
a `defer` written for one clause silences the clause that names the command —
and so does an `incorporate` that folds the item into a surface running some
other command, because a trace is whole-item too. A `defer` for an item whose
text names a command therefore needs a reason that says why the *named
command* needs no surface, and an `incorporate` needs a surface that actually
runs it — or the command clause is incorporated and only the rest deferred
(`ux`'s validator warns `[FR names a command]` whenever an FR's text names a
command that no surface tracing it runs). (FR-097 once deferred as "global
content rule" while its text named `aicf explain <term>`; ARCH then claimed
it realized in a surface with no function behind it, and the codegen task
stuck.)

Then resolve each item. Batch with `AskUserQuestion` (multi-select where the
items are independent). For every added / removed / modified item the user
chooses one of:

- **incorporate** — fold it into this session (for an add: the candidate the
  discovery step named — a new surface/entity/endpoint/container; a re-trace
  or removal for a remove; a re-review for a modify).
- **ignore + warn** — leave the output as-is and record a `WRN-NNN` so the
  gap is reviewable rather than silent.
- **defer (todo)** — same as ignore but flagged as intended future work
  (`WRN-NNN` worded as a deferral).
- **the upstream is wrong — record a finding for `/sdlc:repair`** — the delta
  reveals a defect in the upstream itself (an id removed by mistake, a body
  edit that contradicts another artifact). Append
  `{noted_at, kind_guess, file, summary, evidence}` to the state file's
  `finding_notes:` list and continue the review — the run NEVER stops to
  record; Phase 8 drains the list through
  `python "${CLAUDE_SKILL_DIR}/../repair/findings.py" add` (CLAUDE.md §13;
  skip silently when the helper is absent). Offer this option only where the
  prompt has ≤3 options; where a prompt is already at `AskUserQuestion`'s
  4-option limit, fold it into the free-text guidance instead.

**A delegation is not an assignment.** An upstream item can hand a decision
to THIS artifact instead of contradicting or assigning it — "the exact flow
is left to UX", "reserved until DATA-MODEL describes it", "the API decides
the shape". Such an item does not say the element should exist; it says this
artifact decides whether it should. Route it exactly like an *added* item:
the skill's discovery step first (the "Per-skill specifics" table below —
consumers via `docs_index.py --refs` or a grep over `docs/`, the predecessor
version of this file, what job the element would do). A candidate counts only
when something consumes it — an FR, a WKF, an entity or another item of this
artifact refers to it — or this artifact can state the job it would do; a
name alone ("a flow", "a discriminator") is not a candidate. Position 1 is the
candidate discovery names, or, when it names none, **the delegation is void
— record a finding** (`finding_notes`, drained in Phase 8) so repair retires
the delegating sentence, and author nothing. `defer` stays. "The upstream is
wrong" is not offered for a delegation: the upstream is not wrong, it
deferred, and that option beside define/remove is incoherent. (A PRD sentence
once reserved `EdgeDef.discriminator` "until DATA-MODEL describes
it"; the card offered define / leave / upstream-wrong, the necessity check
found a symmetry copy with no consumer, and the right outcome was to remove
it, not to describe it.) Record the choice as
`delegation_void` in the state slot.

Persist each decision to the state file so an EXIT-then-resume does not
re-prompt already-resolved items. Honour the standard caps and the
anti-padding rule — surface only real deltas, never manufacture them.

## Step 5 — reconcile, then continue the normal flow {#step-5}

After the delta-review:

1. Carry the **incorporate** decisions into the theme interview / merge as
   pre-seeded work (treat them like `⚠ inferred` candidates needing
   confirmation, not silent writes).
2. Append a `WRN-NNN` for every **ignore**/**defer** decision.
3. At write time (Step 1), refresh `metadata.upstream_provenance` to the new
   snapshot — the reconciled output is now built against the *current*
   upstream.
4. Add a `changelog` line, e.g.
   `"<version> (<date>): Re-derived against changed docs/PRD.yaml (added FR-014/015, removed FR-009)."`

This is what makes re-invocation *mean* something precise: instead of
re-walking the whole interview and hoping the merge plus coverage checks
catch the drift, the user sees exactly what moved upstream and decides, per
item, what this artifact should do about it.

## The `--reconcile` form {#reconcile-form}

Every consumer skill — `ux`, `design`, `data`, `api`, `arch`, `test`, `task` —
accepts `--reconcile`: the review above, **and nothing else**. No theme
interview, no structural questions, no sweep over the whole artifact. It is
what `/sdlc:repair` prints for a re-invoke fix, what `docs_index.py --drift`
and `--stale` name as the next command, and what a user runs after editing an
upstream by hand. The plain invocation runs the same review in Phase 2 and
then continues into its interview; `--reconcile` stops after the review.

| Skill | Forms | Reconciles |
|---|---|---|
| `ux`, `design`, `data`, `api` | `/sdlc:<skill> --reconcile` | the system file; a shard the review adds (a surface, a resource, the token or asset file) is authored by the scoped drill in step 5 |
| `arch`, `test`, `task` | `/sdlc:<skill> --reconcile` — every stale file of that skill, the system file first, then containers in spec/drill order · `--system --reconcile` · `<container> --reconcile` | one file per form; the bare form walks the stale ones |

The steps, in order:

1. **Preconditions.** The target file exists and is `metadata.status:
   complete`. Absent → reconciling nothing is authoring: name the plain form
   and abort. Draft → the plain form finishes it: name it and abort. Phase 1
   (resume) runs as usual; Phase 2 reads the inputs by slice and runs the
   input-adequacy gate, minus the owed findings (step 3).
2. **Capture the delta before any write.** `python .claude/sdlc/docs_index.py
   --drift docs/<file>` (the plugin's copy when the project has none — Step 2
   above). Any write this run makes — a re-slice, a stamp — refreshes the
   stamps the drift check reads, so capture first.
   **Exit 0** → print `[OK] nothing moved since docs/<file> was written`,
   write nothing, compute `Next:` (step 8) and stop. **Exit 1** → the report's
   item lists ARE the delta, verbatim, and its `why` lines are each upstream's
   own changelog since the stamp — quote them once at the top of the delta
   summary, so the user sees why before what. No `items` map in the stamp →
   the backlog rule in "Name-addressed items" above.
3. **Read what repair handed off.** `python
   "${CLAUDE_SKILL_DIR}/../repair/findings.py" list --owed-by docs/<file>`
   (helper or queue absent → nothing is owed; skip silently). Each row is a
   triaged re-invoke finding that is **waiting on this run** — this run IS the
   re-invocation it owes. That makes it context, never a gate: it is left out
   of the input-adequacy question, and it never routes this run back to
   `/sdlc:repair`. Quote each row's `summary` and `fix` once at the top of the
   delta summary. A `handoff` note whose `key` matches a delta item becomes
   that item's **position-1 proposal**, shown with the note — still `⚠
   inferred`, confirmed like any candidate, never written unasked. Its
   `basis` says how far to trust it: `measured` was read off the artifacts
   the note names, so offer it as read for what it names — but its window is
   the finding's own change, narrower than this step's full `--drift` delta,
   so the delta always comes from step 2 and the handoff is a proposal
   within it, never its extent (an `expect re-stamp only` note is a
   prediction to check against the stamp, not a summary of it); `inferred`
   (or a note with no basis) is an analogy the walk never checked there -
   read the artifact it cites before offering it, and say on the card what
   you verified. A note with
   `key: null` frames the whole file. This is how the reasoning of the repair
   session reaches a fresh one: on disk, not in a transcript.
   **A finding the delta cites is a decision, not a question.** Besides the
   owed rows, collect every `FND-NNN` that the `--drift` report's `why` lines
   (the upstream's changelog since the stamp — a stamp with neither a version
   nor a date quotes none: read the upstream's `metadata.changelog` top
   entries yourself) and the changed items' text cite, and read them: `python
   "${CLAUDE_SKILL_DIR}/../repair/findings.py" list --id FND-NNN`
   (repeatable; the queue file when the helper is absent).
   A **resolved** finding's `resolution` is the decision that moved the item,
   so its card leads with it — "decided in FND-104 (resolved <date>,
   surgical): <fix>" — as the position-1 recommendation with basis
   `measured` (a recorded resolution is a fact, not an analogy), and never
   re-offers "record a finding" for that item. An open or triaged finding is
   context for the card, not a gate: it was not owed to this file. (A
   DATA-MODEL 3.1 change whose changelog cited FND-104 was once carded
   as an open incorporate / ignore / finding menu one session after the
   repair that decided it.)
   **A handoff carrying `retired` is a sweep, not a citation.** When a note's
   entry carries `retired: [<token>, ...]`, its own prose enumeration of which
   items use the token is unverified — repair could not confirm it either
   (`FND-104` named five tests without the retired token and
   missed five that had it, two of them live assertions). Sweep THIS run's own
   artifact family — the system file plus its shards, the text this reconcile
   is about to read or write — for each token: `grep -rn <token> docs/<family
   system-file-stem>*.yaml` (the same "Token sweep" convention repair's own
   surgical Phase 4 uses; repair's own corpus-wide sweep stays where it is —
   this is narrower, one family, not `docs/`). On a TASKS family a prose grep
   cannot see an embedded copy — run the reslicer's `--check` instead
   (`reslice_embeds.py --docs-dir docs --container <cid|TASKS> --all --check`,
   `TASKS` for the system file); it
   re-derives every embed from its source, which is the only sweep that means
   anything there. Every hit becomes its own card (Step 4), never accepted
   from the note alone. A `key: null` handoff (the whole file) with `retired`
   reports file-level hits — "N lines still carry `<token>`" — and the run
   cards that count as ONE item, not one per line.
4. **One confirmation card per class of change**, never one per item (Step 4
   above holds the options: incorporate / ignore + warn / defer / the upstream
   is wrong):
   - *added* → the skill's discovery step first (table below); position 1
     names the candidate it yields, or the handoff proposal when one exists.
   - *removed* → the §4 stale-ref case: re-trace, remove with approval, or
     defer; never a silent delete.
   - *changed in body* → only the items the report marks `[referenced here]`
     (a structured trace), `[cited in prose xN]` (a mention in a
     description or directive — re-read those N sites), `[changelog names
     this file]` (the upstream's own changelog since the stamp already names
     this file — read the entry and check each changed item against what
     this file says about it), or `[deferred here]` (this file defers the
     item — does the deferral's reason still hold now that the contract
     changed? keep it, or author the test/task). The report computes
     this filter; never re-derive it by hand, and an unmarked list means an
     older installed helper (re-run `/sdlc:setup`; a prose cite at four
     sites was once invisible to a hand filter over structured traces).
     Per item, two
     questions, batched across items: *does the change contradict what this
     file says?* (→ correct it here) and *does it assign something this file
     does not cover yet?* (→ an authoring card — unless it *delegates* the
     decision here: then the discovery step first, Step 4 above, and a
     delegation it cannot substantiate is void and becomes a finding, never
     an element). An item a cited finding already decided leads with that
     resolution (step 3). Neither → refresh the text
     that quotes the upstream in place, with no question. `--drift` already
     leaves declaration-only edits (`touches_entities`, `status`) off the list.

     **An item on the changed-in-body list carrying none of these marks is
     its own class, never the backlog's.** "Not this run's business" applies
     only at the WHOLE-UPSTREAM level — an upstream the report calls
     `re-stamp only` (every changed item in that family unmarked) is step
     6's case, no question at all. Inside a family the report DOES cover, a
     changed-in-body item carrying no mark is *changed and uncovered*: one
     lighter question, batched across items — author a test (or, in `task`,
     a task), record a typed `deferrals` entry, or say it is not this file's
     family — never re-stamped as reviewed by silence. On a validator-green
     artifact every item is targeted, cited, or structurally deferred
     (AUTHORING §6), so this class should be rare; where an item is
     genuinely named in none of those buckets, the file predates the
     `deferrals` mechanism — a pre-2.x artifact still on the prose-only
     deferral channel — and is walked with the same lighter question.
5. **Incorporate means a scoped drill, not the interview.** Each accepted
   item is authored at its own list's importance tier — `critical` items get
   the per-item drill (`../../prd/references/importance-flows.md`), and a
   scope-completeness sweep, where the list has one, is seeded from the delta
   and the handoff notes only. A note or arm that quantifies over an upstream
   enumeration ("per class the contract enumerates", "every verb") is seeded
   by reading that enumeration from the artifact it names — whatever the
   note's `basis` — and the close card prints seeded-vs-enumerated with the
   difference. When an accepted item needs a decision this run
   cannot scope — a Phase 4 structural question (a new container, another
   storage paradigm, a new surface family) — save the decisions so far, stop,
   and name the plain form as `Next:`; its Phase 2 resumes this review from
   the `delta_review` slot instead of asking again.
6. **Hash moved, no item delta** (a comment or formatting edit), or the report
   says `re-stamp only` (items moved, none this file references or cites) →
   re-stamp and add one changelog line, with no question. That "no question"
   scopes the delta review only — whatever the skill's own SKILL.md owes
   every update run (pre-flight WRNs, ask-once gates, Phase 7/8) still runs
   regardless. **The report says it cannot itemize the upstream** (both the
   recorded snapshot and the current index hold no items for it) → read the
   upstream's `git diff` since the stamp, or its changelog lines, and card
   what changed; the re-stamp-with-no-question path above is only for "no
   item delta" on an upstream the report DID itemize.
7. **Phase 7 and Phase 8 as usual** — merge (never drop an item the user did
   not approve dropping), `--stamp` against every upstream consumed, validate
   bare, refresh the index and the statusboard, drain `finding_notes` and
   `lesson_notes`, record the run. The changelog line names the delta and any
   finding it served:
   `"<ver> (<date>): Reconciled against docs/ARCH__x.yaml (added a, b; FND-012)."`
8. **`Next:` routes the chain** (`../../prd/references/reporting-to-the-user.md`,
   rule 3): after the write run `python .claude/sdlc/docs_index.py --stale`.
   Its first row is the next reconcile — upstream first, so a chain started by
   `/sdlc:repair` walks itself. Nothing stale and a finding was owed to this
   run → `/sdlc:repair FND-NNN`: every file it owed is fresh now, so repair
   can verify the hops and close it.

**The bare form on `arch` / `test` / `task`.** Walk the `--stale` rows that
belong to this skill, in their order, one file at a time — each through steps
1–7 with its own `delta_review` slot. Keep the files not yet done in the state
file's `reconcile_queue`, so `EXIT` and resume continue at the next file. A
file that stops at step 5 stops the walk.

### Per-skill specifics

| Skill | Upstreams | An added item is seeded by | Structural, so the plain form |
|---|---|---|---|
| `ux` | PRD | `surface-discovery.md` Step 1b/1c — an FR or ENT naming a command or a screen is a surface candidate; a defer names the command and an incorporate points at a surface that runs it (`[FR names a command]`); a new surface gets its `UX__<surface>.yaml` through the per-surface drill | another surface family; ux's downstream-claim check stays in the plain form |
| `design` | PRD, UX | the asset manifest's candidate rules (`asset-pipeline.md`) and the token groups a new surface needs (`design-tokens.md`) | a change to `functional_structure` or `aesthetic_direction` |
| `data` | PRD, UX | `entity-discovery.md` — an FR or surface naming a persisted thing is an entity candidate; the sub-model sweep runs for each new entity only | another storage paradigm, bounded-context split |
| `api` | PRD, UX, DATA | `resource-discovery.md` — a new entity or surface is a resource or operation candidate; a new resource gets its `API__<resource>.yaml` | another `api_kind` or transport style |
| `arch` | PRD, DATA, UX, API | system file: `container-discovery.md`; container file: `component-discovery.md` (a new operation or entity is a work-unit candidate) | a new container (`/sdlc:arch --system`) |
| `test` | PRD, DATA, ARCH (+ shard), API, UX | `test-discovery.md`; its SKILL.md holds the TST-specific cards for the container form | — |
| `task` | ARCH + TEST shards, PRD, DATA, API, UX, DESIGN | `task-discovery.md`; content-only embed drift moves through `reslice_embeds.py` AFTER step 2 | — |

## The delta-review state slot {#delta-review-state}

Every skill that runs this review declares ONE named slot in its state file.
This is the canonical definition — skills mirror it, they do not redefine it:

```yaml
delta_review:
  upstreams: []    # [{file, recorded_sha256, current_sha256}] — Step 2's verdicts
  decisions: []    # [{key, choice: incorporate|ignore_warn|defer|upstream_wrong|delegation_void, at}]
                   #   key = the id (FR-014) or natural key (aicf-cli/emit/render)
  unresolved: []   # the queue still to review — what an EXIT-then-resume continues from
reconcile_queue: []  # sharded skills only (arch keeps it per sub-session): the
                     # files a bare `--reconcile` has still to walk, in order
```

Written in the same state write as everything else. EXIT mid-review persists
`decisions` + `unresolved` (see the edge case below); the EXIT path also
drains `lesson_notes` and `finding_notes` per CLAUDE.md §15/§13 before
aborting.

## Edge cases {#edge-cases}

- **Output exists, no provenance at all (pre-convention artifact).** Cannot
  diff. Tell the user the artifact predates drift-tracking; offer a
  coverage-driven review (walk current upstream id families against the
  output's traces) and write a provenance snapshot from this run forward.
- **`INDEX.yaml` absent.** Compute hashes inline as the text-level hash
  (`sha256(read_text(encoding='utf-8').encode()).hexdigest()[:16]` — never
  raw bytes). Everything else is unchanged.
- **Upstream artifact missing entirely.** That is the existing "required
  input missing" abort (each skill's Phase 2 / `edge-cases.md`), not a
  delta — handle it there, before this document applies.
- **Hash differs but the diff is empty** (whitespace/comment-only edit, or a
  re-save with no semantic change). Report "changed, but no id-level delta
  found" and let the user proceed without action; still refresh the snapshot.
- **Provenance present and every hash matches.** No drift — skip the
  delta-review and treat as a plain refine/extend.
- **EXIT mid-delta-review.** Persist resolved decisions and the unresolved
  queue to the `delta_review` state slot (above); on resume, continue the
  review where it stopped.
