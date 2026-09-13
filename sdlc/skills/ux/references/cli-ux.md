# CLI-specific UX guidance

Read this when entering **theme 10 (`cli_specifics`)** — that is, when
`surface_family in ['cli', 'mixed']`. It also informs theme 11
deep-dives for any `cli_command` or `flow_step` surface.

This is not a generic CLI design guide — it's the set of conventions
downstream coding agents will assume by default unless the user
explicitly overrides them.

## Why these decisions matter

Downstream coding agents (api → arch → test → task) will generate
argument parsers, completion scripts, help text, and test cases
directly from the `cli:` block in `UX.yaml` and from each
`cli_command` surface's invocation pattern. Vague or ambiguous answers
here mean every later agent will re-litigate the same decisions or
silently invent inconsistent ones.

## The 12 fields that go in `UX.yaml.cli`

(Mirroring `ux-questions.yaml` theme 10; here are the recommended
patterns and the trade-offs.)

### 1. `root_command` — top-level binary name

Pre-fill from `PRD.product_identity.slug` (kebab-case product name).
Override only if the product has a strong existing brand
(`git`, `kubectl`-style).

### 2. `command_shape` — `verb_noun | noun_verb | flat | mixed`

- **`verb_noun`** (`git commit`, `apt install foo`) — the most common.
  Easy for newcomers; verbs are short and memorable. Default
  recommendation.
- **`noun_verb`** (`docker container ls`, `kubectl pods get`) — better
  for tools with many nouns and hierarchical concepts. Adds depth
  (more typing), but disambiguates verbs across nouns.
- **`flat`** — single-level commands only (`acme list`, `acme add`).
  Good for ≤ 10 commands; falls apart beyond that.
- **`mixed`** — some flat verbs, some hierarchical noun groups. Use
  sparingly; documentation overhead is high.

### 3. `arg_parsing_library`

| Language | Recommended library |
|---|---|
| Python | `typer` (modern, type-hint-driven) or `click` (mature, more flexible) — `argparse` only for stdlib-only constraints |
| Go | `cobra` (de facto standard) or `urfave/cli` |
| Rust | `clap` (de facto standard) |
| Node | `commander` (general), `oclif` (plugin-heavy CLIs), `yargs` (legacy projects) |

Pre-fill from `PRD.technical_constraints.primary_language` whenever it
implies a single obvious choice.

### 4. `arg_conventions` — `posix | gnu | custom`

- **POSIX** (`-x`, single-letter flags, no `=` for values): minimal,
  scriptable.
- **GNU** (`--long-flag`, `--flag=value` or `--flag value`,
  short+long combined): most common; pair short and long flags for
  most options. **Default recommendation.**
- **Custom**: only when the host ecosystem demands it
  (e.g. PowerShell-style `-Foo Bar`).

### 5. `help_text_format`

- **`auto_generated`** — let the parsing library produce `--help`.
  Cheapest; works for most CLIs.
- **`authored`** — hand-written, kept in `docs/cli/help/<command>.md`
  or similar. Only when the product has a documentation-first culture.
- **`hybrid`** — auto-generated base + authored *Examples* block per
  command. Best of both for popular CLIs.

### 6. `output_formats.supported` + `output_formats.default`

The minimum viable set: `table` (human default) + `json` (machine).
Recommend `plain` too if any command emits free-form text.

Add `--output / -o` flag of type choice. Document the default.

| Audience | Recommended default |
|---|---|
| Humans, primarily interactive | `table` |
| CI / scripts, primarily piped | `json` |
| Mixed — `isatty()` detection | `table` when stdout is a tty, `json` otherwise |

For machine-consumable formats, also note:

- `json` should be one-object-per-line for streaming (`jsonl`) or a
  single root array for batched output — be explicit about which.
- `yaml` output should match the structure of `json` output exactly.

### 7. `exit_code_convention`

Three viable conventions:

- **POSIX standard** — `0` success, `1` generic error, `2` misuse.
  Default recommendation.
- **`sysexits.h`** — `64` usage, `65` data err, `66` no input, `67` no
  user, `68` no host, `69` unavailable, `70` software, `71` os err,
  `72` os file, `73` cant create, `74` io err, `75` temp fail,
  `76` protocol, `77` no perm, `78` config. Useful when monitoring
  systems consume the codes.
- **Custom** — only when the product has specific signalling needs
  (e.g. `2` for "no results", `3` for "stale cache").

Whatever the choice, record specific exit codes per command in
`UX.yaml.cli.exit_codes` (preferred — a project-wide map) OR in the
per-surface yaml's `notes` (when the code is surface-specific). The
project-wide map uses the structured shape:

```yaml
cli:
  exit_codes:
    "0":   { description: "success",      implements_requirements: [] }
    "2":   { description: "misuse",       implements_requirements: [] }
    "3":   { description: "gate failure", implements_requirements: ["FR-018", "FR-019"] }
    "130": { description: "SIGINT graceful shutdown", implements_requirements: [] }
```

The `implements_requirements` field per code lists the FR-NNN id(s)
that *mandate* this exit code's existence or define its semantics. The
validator enforces FR-NNN format on any value present. Codes without
a mandating FR (generic success, generic error, POSIX signals) use
`implements_requirements: []`.

### 8. `interactive_mode`

- **Never** — every required flag must be supplied; fail with non-zero
  exit if missing. Best for scripting; worst for newcomers.
- **Prompt for missing required args** — when stdin is a tty, prompt
  the user; in non-tty contexts, fail. Best general default.
- **Full interactive REPL** — separate `acme repl` or `acme shell`
  command. Reserve for power-user CLIs.
- **TUI mode** — full-screen interactive UI for some commands
  (`htop`-style). Treat the TUI surface as its own
  `UX__<command>-tui.yaml` with `surface_type: cli_command`.

### 9. `config_file.location`

Default to **XDG Base Directory Spec**:

- Linux/macOS: `$XDG_CONFIG_HOME/<app>/config.yaml`, falling back to
  `~/.config/<app>/config.yaml`.
- Windows: `%APPDATA%/<app>/config.yaml`.

Single-file alternatives:

- `~/.<app>rc` (single-file, classic Unix tools).
- `./<app>.config.yaml` (project-local, Node-style).

### 10. `config_file.precedence`

The universal CLI convention:

```
cli_flag > env_var > config_file > built-in default
```

Override only with documented reason. Each layer overrides the layer
below for any individual setting.

### 11. `config_file.env_prefix`

Prevents env-var collisions. E.g. `ACME_` so `ACME_API_KEY` ≠ system
`API_KEY`. Always use the same prefix everywhere; document it in
`--help` global section.

## Per-CLI-command (`cli_command`) surface contents

Each `cli_command` surface yaml fills in these surface fields with
CLI-specific shapes:

### `cli_invocation`

The canonical invocation pattern:

```
cli_invocation: "<root> task add <title> [--priority=<n>] [--due=<date>]"
```

Use angle brackets `<...>` for required values, square brackets `[...]`
for optional values, `...` for repeatable.

### `layout.cli_args`

The full arg/flag list as structured YAML. Each entry:

```yaml
- name: title
  kind: positional
  type: string
  required: true
  description: "Short title for the task."
- name: priority
  kind: option
  short: "-p"
  long: "--priority"
  type: choice
  choices: ["low","normal","high"]
  default: "normal"
  required: false
  description: "Priority bucket."
- name: due
  kind: option
  short: "-d"
  long: "--due"
  type: string
  required: false
  description: "Due date, ISO-8601 or natural language."
```

Downstream agents read this verbatim into their parsing library's
`add_argument` / `command.Flag` calls.

### `states` block adapted for CLI

Reinterpret the canonical 5 states for a CLI command:

- **default** — `cli_invocation` succeeded; output emitted.
- **loading** — long-running command; show progress to stderr (spinner
  / progress bar) so it doesn't pollute stdout pipes.
- **empty** — query returned zero results. For machine-consumable
  formats emit `[]` / `{}`; for human formats emit a one-line message
  to stderr and exit 0.
- **error** — non-zero exit. Error messages to stderr, never stdout.
- **success** — for commands that produce no normal output (e.g.
  `acme task done`), emit a single-line confirmation to stderr (or
  silent if `--quiet`).

### `interactions` for CLI

CLI surfaces have fewer interactions than graphical ones. The common ones:

- `cli_invoke` — the user runs the command. Effects: read flags, read
  config, execute, emit output, set exit code.
- `cli_signal` — SIGINT/SIGTERM handling. Effects: graceful shutdown,
  flush stdout, set exit code 130 (SIGINT) or 143 (SIGTERM).

If the command has interactive prompts, model each prompt as its own
`flow_step` surface (`surface_type: flow_step`), with its own
`UX__<command>-prompt-<n>.yaml`. The prompt's `interactions` list one
or more `keypress` triggers (e.g. typed input + Enter).

## Validation rules for CLI inputs

For arg validation, use these patterns in
`UX__<command>.yaml.validation_rules`:

```yaml
- field: priority
  rules: ["choice: ['low','normal','high']"]
  error_message: "priority must be one of: low, normal, high"
- field: due
  rules: ["regex: ^\\d{4}-\\d{2}-\\d{2}$", "or", "regex: ^(today|tomorrow|next [a-z]+)$"]
  error_message: "due must be ISO date (YYYY-MM-DD) or natural ('today', 'tomorrow', 'next monday')"
```

## Accessibility for CLI

CLI products do not have a WCAG target in the conventional sense.
Recommend:

- `wcag_target: not_applicable_cli` (recommended) — or `wcag_aa` if
  the CLI emits HTML reports / has a TUI mode.
- Color support: detect `NO_COLOR` env var and disable color
  accordingly; detect `TERM=dumb` and fall back to plain text.
- Keyboard-only is implicit (CLI is keyboard by nature) — set
  `accessibility.keyboard_only: true`.
- Screen-reader notes: don't apply unless a TUI surface is present;
  for TUIs document the readback strategy.

## Pre-fill heuristics

When entering theme 10, pre-fill:

- `root_command` ← `PRD.product_identity.slug` (always).
- `arg_parsing_library` ← from `PRD.technical_constraints.primary_language`
  (Python → typer; Go → cobra; Rust → clap; Node → commander).
- `arg_conventions` ← `gnu` (universal best default).
- `help_text_format` ← `auto_generated` (lowest-cost default).
- `output_formats.supported` ← `[table, json]` (minimum scriptable set).
- `output_formats.default` ← `table` (humans first; revisit if PRD
  primary_users skews "engineers running CI").
- `exit_code_convention` ← "POSIX standard (0=ok, 1=error, 2=misuse)".
- `interactive_mode` ← "Prompt for missing required args" (best UX
  default that still scripts cleanly when piped).
- `config_file.location` ← XDG default for the OS.
- `config_file.precedence` ← `cli_flag > env > config_file > default`.
- `config_file.env_prefix` ← `<ROOT_COMMAND_UPPER>_`.

Surface all as `⚠ inferred` position-1 options. The user must confirm
or correct each.

## Downstream: `cli_args` is the `cli_contract` source

The per-surface `cli_args` block (each `CLIArg`: name/kind/type/required/
description/…) is the single source of truth for a CLI handler's argument
parser. Downstream `sdlc-task` copies the whole block **verbatim** into the CLI
handler task's `cli_contract` field, and `sdlc-code`'s worker generates the
parser straight from that embedded slice — it never reads the UX shard. So a
`cli_args` entry must be complete enough to code a parser from on its own:
don't leave a required flag's `type` or `description` blank on the assumption a
later stage will fill it. (Seam: SK-34 — the task-side `cli_contract` field.)
