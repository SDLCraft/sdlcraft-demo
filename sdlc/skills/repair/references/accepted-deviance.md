# Accepted deviance — the one exception to an upstream validator stop

Read this when an upstream artifact's validator exits non-zero during a skill's
input gate (Phase 2, or `code`'s Preconditions), or when a downstream-rejection
rule in a `merge-validate.md` would reject an artifact for that reason. This
file is the single statement of the rule; every skill's gate points here
instead of carrying its own copy.

## The rule

Every downstream consumer rejects an upstream artifact when

1. its `metadata.status != "complete"` — **no exception, ever**; or
2. its validator exits non-zero — **unless every failing check is accepted
   deviance**.

An **accepted deviance** is a finding in `.claude/skills-state/sdlc-findings.yaml`
that has all three of:

- `status: wontfix`;
- `expected_count: N` in its `summary` (or its `resolution.reason` /
  `resolution.summary`) — the number of problem lines the project decided to
  live with;
- `detected_by` naming **that check** (e.g. `data/validate_schema`), with
  `surfaced_at.file` (or `suspected_source`) naming the artifact.

The check then counts as passing while its count stays at `N`, and fails again
the moment the count moves, in either direction. Without this exception a
project with one permanently accepted validator error could never run the
stages below it again.

## The gate command

Run it bare, once per artifact whose validator exited non-zero:

```bash
python "${CLAUDE_SKILL_DIR}/../repair/doctor.py" --docs-dir docs --artifact docs/<the file whose validator exited non-zero>
```

`--artifact` re-runs that one artifact's validator with the accepted findings
applied. Each row reads either `accepted (N, unchanged) per FND-NNN` — proceed —
or `[FAIL]` — stop, name the offending file, and tell the user which upstream
skill to run (or `/sdlc:repair`). Exit 0 means every named artifact passed or
is accepted.

**Never `--quick`.** That depth runs only the cross-artifact linter; it says
nothing about any single artifact's validator, accepted or red, so a gate that
reads it proceeds on a broken upstream.

**A finding the doctor did not apply.** When a `wontfix` finding pins
`expected_count` for the artifact but its `detected_by` is empty or names a
skill instead of a check (`sdlc-arch`, say), the doctor keeps the check red and
prints a warning naming the finding and the `detected_by` value it needs. That
is still a stop: tell the user the finding needs its check named (a
`/sdlc:repair` edit), never compare the count yourself to get past it.

**Without the doctor** (the plugin's `repair` skill is absent): read the queue
for a finding matching all three conditions above, count the validator's
problem lines yourself, and proceed only when the count equals `N`.

## Where a deviance comes from

`/sdlc:repair` records one when the user picks *accept as-is* for a validator
finding. A finding minted by `doctor.py --emit-findings` already carries the
check as `detected_by`. One recorded by hand or by another skill must pass
`--detected-by <skill>/validate_schema` to `findings.py add`; `findings.py` and
`validate_findings.py` warn (never block) when `expected_count` appears without
it.
