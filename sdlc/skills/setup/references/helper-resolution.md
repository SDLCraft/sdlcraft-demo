# Which helper copy a skill runs: the installed one or the plugin's

`/sdlc:setup` copies the shared helpers into the project's `.claude/sdlc/` and
records what it copied in `.claude/sdlc/sdlc-plugin.json`. `claude plugin
update` moves the plugin; it does not touch those copies. So a project wired at
an older plugin keeps older helpers, and the skill prose that runs
`python .claude/sdlc/<helper>.py …` then meets a copy that rejects a flag
added since (`--stale` came with capability 5, `--hold-upstream` with 6) with
an argparse exit 2, which is not "nothing is stale", or reads an items-aware
stamp the old way, or prints a `--drift` list without the `[referenced here]`
/ `[cited in prose xN]` marks and the `re-stamp only` verdict the reconcile
forms read (capability 7) — or, at the close, draws a statusboard without the
verdict buckets and records a run without stamping the maintainer's verdicts.
The prose used to fall back to the plugin's copy only when the installed one
was ABSENT, never when it was OLDER, and nothing asked for a `/sdlc:setup`
re-run.

Every skill that runs an installed helper follows this file, **for every
helper it runs** — `docs_index.py` and the close-phase `statusboard.py`,
`lessons.py`, `autocommit.py`, `findings.py`, `bump_artifact.py` alike. A
skill's own "helper absent" fallbacks still apply; an installed copy older than
the plugin's counts as absent for them.

## The rule: resolve once per run, before the first helper call

Resolve before the first helper call of the run — whichever helper that is —
and reuse the answer for every later `python .claude/sdlc/<helper>.py …` in
the same run. The SKILL.md prose keeps that spelling for every helper; this
rule decides which copy the spelling runs. One decision, made once: a run
that switched copies for `docs_index.py` and then ran the installed
`statusboard.py` and `lessons.py record-run` at its close got a board without
the verdict buckets and a run record with no verdicts stamped, because those
two helpers had changed too.

1. **The plugin's capability.** Grep `^CAPABILITY_VERSION` in
   `"${CLAUDE_SKILL_DIR}/../setup/docs_index.py"`.
2. **What was installed.** Read `.claude/sdlc/sdlc-plugin.json` and take
   `helpers.docs_index` — and `plugin_version`, which decides for every other
   helper (below).
3. **Decide:**

| `.claude/sdlc/docs_index.py` | marker `helpers.docs_index` | Run |
|---|---|---|
| present | a number ≥ the plugin's `CAPABILITY_VERSION` | the installed copy: `python .claude/sdlc/docs_index.py <args>` |
| present | lower, missing, or no marker at all | the plugin's copy, and tell the user once (below) |
| absent | (any) | a flagged call: the plugin's copy, per the calling file's own "helper absent" rule. A bare regenerate never falls back — see the two rows below |
| absent, bare regenerate only | `.claude/sdlc/sdlc-plugin.json` present, `helpers.docs_index` missing entirely (own-toolchain) | never the plugin's copy — run the project's own docs-hook command from `.claude/settings.json` (the `hooks.PostToolUse` entry naming the index) and say which command ran |
| absent, bare regenerate only | no `.claude/sdlc/sdlc-plugin.json` at all | nothing to run — the project never ran `/sdlc:setup` |

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
  receive the stock one. When there is no installed copy, the two absent
  bare-regenerate rows above decide: own-toolchain (the marker exists but
  names no `docs_index` helper) runs the project's own docs-hook command and
  says so; no marker at all is the only genuine no-op — the project never ran
  `/sdlc:setup`. Only calls that pass a flag switch copies.
- **No plugin in view, no switch.** In an ambient session (no
  `${CLAUDE_SKILL_DIR}`) there is nothing to compare, so run the installed
  copy as is. A file's by-hand fallback (comparing recorded hashes itself)
  applies only when neither copy can run. A hook or project script that needs
  the plugin anyway asks `plugin_root.py` (the last section).
- **Helpers without a `CAPABILITY_VERSION`** (`statusboard.py`, `findings.py`,
  `bump_artifact.py`, `lessons.py`, `autocommit.py`, `plugin_root.py`) compare
  the marker's `plugin_version` with the running plugin's `version` in
  `"${CLAUDE_SKILL_DIR}/../../.claude-plugin/plugin.json"`. When the install
  is older, every one of them runs as the plugin's copy — the close phase
  included, where the lag is also reported (below):

  | Installed | Plugin's copy |
  |---|---|
  | `.claude/sdlc/statusboard.py` | `"${CLAUDE_SKILL_DIR}/../setup/statusboard.py"` |
  | `.claude/sdlc/findings.py` | `"${CLAUDE_SKILL_DIR}/../repair/findings.py"` |
  | `.claude/sdlc/bump_artifact.py` | `"${CLAUDE_SKILL_DIR}/../repair/bump_artifact.py"` |
  | `.claude/sdlc/lessons.py` | `"${CLAUDE_SKILL_DIR}/../lesson/lessons.py"` |
  | `.claude/sdlc/autocommit.py` | `"${CLAUDE_SKILL_DIR}/../setup/autocommit.py"` |
  | `.claude/sdlc/plugin_root.py` | `"${CLAUDE_SKILL_DIR}/../setup/plugin_root.py"` |

  The commands keep their arguments; only the path changes. `lessons.py`
  refuses on its own to write a queue a newer plugin stamped (one line, exit
  4), so an older copy that does slip through a close records nothing rather
  than dropping fields — but the close is still where the verdicts arrive,
  and only the plugin's copy delivers them.

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

## Callers with no skill in view: hooks, project scripts, CI

`${CLAUDE_SKILL_DIR}` exists only inside a skill run. A `SessionStart` hook,
a project's own script or a CI job has neither it nor a `CLAUDE_PLUGIN_ROOT`;
the only trace in a hook's environment is a `PATH` entry under the plugin
cache, undocumented and rewritten by `uv run`. One project therefore
hard-coded a marketplace path and measured with plugin 0.9.10 for ten days
after 0.9.17 had been installed under another marketplace.

The sanctioned answer is the installed `plugin_root.py` (source:
`"${CLAUDE_SKILL_DIR}/../setup/plugin_root.py"`), which reads the registry
Claude Code keeps and prints the newest ENABLED sdlc plugin:

```bash
python .claude/sdlc/plugin_root.py           # 0.9.17 @ sdlcraft
python .claude/sdlc/plugin_root.py --path    # the root folder alone
python .claude/sdlc/plugin_root.py --json    # root, version, marketplace, source, candidates
```

Its rule, in order: `SDLC_PLUGIN_ROOT` (an explicit override, for bisecting;
printed with `[override]`), then `${CLAUDE_SKILL_DIR}/../..` when set, then
the registry — `<home>/plugins/installed_plugins.json` → `plugins`, every key
`sdlc@<marketplace>` (never one literal marketplace); `<home>/settings.json` →
`enabledPlugins` drops a key set to `false` (an unreadable file keeps them
all); the highest version wins, compared part by part as integers, a
non-numeric version sorting oldest; a candidate must carry
`.claude-plugin/plugin.json` and `skills/setup/docs_index.py`, and its version
is read from that manifest with the registry's as the fallback. `<home>` is
`$CLAUDE_CONFIG_DIR`, else `~/.claude`. Exit 1 means no enabled sdlc plugin
is registered; exit 2 means the registry could not be read.

Two uses it was written for: a hook that wants the running plugin's
`topo_order.py` or `doctor.py` (`ROOT="$(python .claude/sdlc/plugin_root.py
--path)"`), and the ambient verdict stamp — `python .claude/sdlc/lessons.py
reconcile --plugin-root "$(python .claude/sdlc/plugin_root.py --path)"` — for
a project that wants the maintainer's verdicts before its next skill close.

## Capability history (what an older install lacks)

| Capability | Added |
|---|---|
| 4 | per-item provenance: the `items` map `--stamp` records, an exact `--drift` |
| 5 | `--stale`; `--stamp` records each upstream's version, `--drift` prints the changelog lines since |
| 6 | `--hold-upstream FILE` on `--stamp`, and a `re-stamped …` line for each re-hashed upstream whose items moved |
| 7 | `--drift` marks `[referenced here]` / `[cited in prose xN]` and calls an unreferenced move `re-stamp only` |
| 9 | ARCH `failure_modes[].id` / `security_concerns[].id` indexed; `--stamp` records its capability |
| 10 | the system `ARCH.yaml` is itemized (`container` by `container_id`, `edge` by `<from>-><to>`), so a shard's `--drift` names the container block or edge that moved instead of "no item to itemize"; a family the stamp held none of prints one count line, never every id as "added upstream" |
| 11 | an item the stamp never itemized (a pre-capability family, an empty `items` map) is recovered from git before `re-stamp only` is printed; a referenced miss says a change cannot be ruled out |

The authoritative list is the module docstring of `setup/docs_index.py`.
