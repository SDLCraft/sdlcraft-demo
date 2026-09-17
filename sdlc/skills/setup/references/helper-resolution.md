# Which helper copy a skill runs: the installed one or the plugin's

`/sdlc:setup` copies the shared helpers into the project's `.claude/sdlc/` and
records what it copied in `.claude/sdlc/sdlc-plugin.json`. `claude plugin
update` moves the plugin; it does not touch those copies. So a project wired at
an older plugin keeps an older `docs_index.py`, and the skill prose that runs
`python .claude/sdlc/docs_index.py …` then meets a helper that rejects a flag
added since (`--stale` came with capability 5, `--hold-upstream` with 6) with
an argparse exit 2, which is not "nothing is stale", or reads an items-aware
stamp the old way, or prints a `--drift` list without the `[referenced here]`
/ `[cited in prose xN]` marks and the `re-stamp only` verdict the reconcile
forms read (capability 7). The prose used to fall back to the plugin's copy only when
the installed one was ABSENT, never when it was OLDER, and nothing asked for a
`/sdlc:setup` re-run (ledger IMP-108).

Every skill that runs an installed helper follows this file. A skill's own
"helper absent" fallbacks still apply; an installed copy older than the plugin's
counts as absent for them.

## The rule: resolve once per run, before the first call

Resolve before the first `docs_index.py` call of the run, and reuse the answer
for every later call in the same run.

1. **The plugin's capability.** Grep `^CAPABILITY_VERSION` in
   `"${CLAUDE_SKILL_DIR}/../setup/docs_index.py"`.
2. **What was installed.** Read `.claude/sdlc/sdlc-plugin.json` and take
   `helpers.docs_index`.
3. **Decide:**

| `.claude/sdlc/docs_index.py` | marker `helpers.docs_index` | Run |
|---|---|---|
| present | a number ≥ the plugin's `CAPABILITY_VERSION` | the installed copy: `python .claude/sdlc/docs_index.py <args>` |
| present | lower, missing, or no marker at all | the plugin's copy, and tell the user once (below) |
| absent | (any) | the plugin's copy, per the calling file's own "helper absent" rule |

The plugin's copy takes the same arguments plus `--docs-dir docs`:

```bash
python "${CLAUDE_SKILL_DIR}/../setup/docs_index.py" --docs-dir docs <args>
```

Numbers compare as integers, part by part (`0.10.0` is newer than `0.9.14`).
A value that is not a number, such as a `sha:` hash, counts as older.

**Three limits:**

- **A bare regenerate stays on the installed copy.** A plain `python
  .claude/sdlc/docs_index.py` with no flag rebuilds `docs/INDEX.yaml`. The
  docs hook rebuilds it with the installed copy after every `docs/` edit
  anyway, and a project that generates its index with its own tool must never
  receive the stock one. When there is no installed copy, skip the rebuild as
  the calling file says. Only calls that pass a flag switch copies.
- **No plugin in view, no switch.** In an ambient session (no
  `${CLAUDE_SKILL_DIR}`) there is nothing to compare, so run the installed
  copy as is. A file's by-hand fallback (comparing recorded hashes itself)
  applies only when neither copy can run.
- **Helpers without a `CAPABILITY_VERSION`** (`statusboard.py`, `findings.py`,
  `bump_artifact.py`, `lessons.py`) compare the marker's `plugin_version` with
  the running plugin's `version` in `"${CLAUDE_SKILL_DIR}/../../.claude-plugin/plugin.json"`.
  When the install is older, run the plugin's copy:

  | Installed | Plugin's copy |
  |---|---|
  | `.claude/sdlc/statusboard.py` | `"${CLAUDE_SKILL_DIR}/../setup/statusboard.py"` |
  | `.claude/sdlc/findings.py` | `"${CLAUDE_SKILL_DIR}/../repair/findings.py"` |
  | `.claude/sdlc/bump_artifact.py` | `"${CLAUDE_SKILL_DIR}/../repair/bump_artifact.py"` |
  | `.claude/sdlc/lessons.py` | `"${CLAUDE_SKILL_DIR}/../lesson/lessons.py"` |

  The close-phase `lessons.py record-run` and `statusboard.py` refreshes keep
  their old command forms, so an older install still runs them. They are
  also where the lag is reported (below).

## Telling the user

When the plugin's copy ran because the installed one is older, say so once per
run, on the close card's `Attention:` row, in plain words:

```
Attention: The helper scripts installed in .claude/sdlc/ are older than this
           plugin, so this run used the plugin's own copies. Run /sdlc:setup
           once to update them.
```

This is neither a finding (nothing in `docs/` is wrong) nor a lesson (no
skill misbehaved). Two places repeat it until `/sdlc:setup` runs again:
`lessons.py record-run` prints it as a `Check:` line at every skill close, and
the statusboard carries one line about it. The board line reaches projects
that record no runs, too.

## Capability history (what an older install lacks)

| Capability | Added |
|---|---|
| 4 | per-item provenance: the `items` map `--stamp` records, an exact `--drift` |
| 5 | `--stale`; `--stamp` records each upstream's version, `--drift` prints the changelog lines since |
| 6 | `--hold-upstream FILE` on `--stamp`, and a `re-stamped …` line for each re-hashed upstream whose items moved |

The authoritative list is the module docstring of `setup/docs_index.py`.
