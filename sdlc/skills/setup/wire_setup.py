"""Wire the docs/INDEX.yaml toolchain and the shared SDLC helpers into a project.

`sdlc:setup` runs this once, before `sdlc:prd`, to make a project's large SDLC
specs cheap to navigate and to install the helpers every later skill calls. It
is fully deterministic and idempotent — re-running it never duplicates
anything; it only fills gaps and refreshes the index.

What it installs into the target project root (default: cwd):

  1. .claude/sdlc/docs_index.py        — the stdlib-only navigation-index generator
                                          (copied from this skill folder).
  2. .claude/rules/sdlc-docs-access.md — the slice-don't-slurp retrieval protocol
                                          (copied from this skill's assets/).
  2b. .claude/rules/sdlc-output-glossary.md — plain-language meanings for the
                                          words the skills print, for the user
                                          to look up (CLAUDE.md §14).
  2c. .claude/sdlc/lessons.py           — the lessons/run-record helper every
                                          skill's close phase calls (copied
                                          from the sibling `lesson` skill).
  2d. .claude/rules/sdlc-lessons.md     — when and how to record a skill-defect
                                          lesson (copied from this skill's assets/).
  2e. .claude/sdlc/findings.py          — the findings-queue writer (copied from
                                          the sibling `repair` skill) so an
                                          ambient session can record a spec
                                          defect it notices (CLAUDE.md §13),
                                          plus .claude/sdlc/validate_findings.py
                                          beside it (findings.py refuses to run
                                          without its validator models).
  2f. .claude/rules/sdlc-findings.md    — when and how to record a finding
                                          (copied from this skill's assets/).
  2g. .claude/sdlc/bump_artifact.py     — the version + changelog bumper the
                                          artifact skills and `repair` share
                                          (copied from the sibling `repair` skill).
  2h. .claude/sdlc/sdlc-plugin.json     — plugin-version marker naming the
                                          plugin and every helper version
                                          installed, so recorded runs, lessons
                                          and findings say what they ran against.
  3. .claude/settings.json             — a `Write|Edit|MultiEdit` PostToolUse hook
                                          that runs the generator on every docs/
                                          edit, anchored on $CLAUDE_PROJECT_DIR so
                                          it works from any cwd. Merged in;
                                          existing settings preserved.
  4. CLAUDE.md                         — a `## SDLC Documents` section with the
                                          slice-first access note + the INDEX.yaml
                                          pointer. Coexists with the per-artifact
                                          bullets the prd/ux/data/arch skills add.
  5. docs/INDEX.yaml                    — generated once now (no-op if docs/ empty).

A project that generates docs/INDEX.yaml with its OWN tool (detected from the
INDEX.yaml header and the hook commands) keeps that wiring: the generator copy,
the docs-access rule, the hook, the CLAUDE.md section and the index generation
are all skipped, and only the generator-agnostic pieces (glossary, lessons,
findings, bump helper, version marker) are installed — the run reports
`Status: partial`. Pass --force-stock to replace the project's own toolchain
with the stock one (the foreign hook entry is removed).

Run from the project root:

    python <skill>/wire_setup.py
    python <skill>/wire_setup.py --dry-run
    python <skill>/wire_setup.py --project-root /path/to/project --python "uv run python"

Exit codes:
    0 — success (installed | already-wired | partial | dry-run).
    1 — never (there is no gate here; kept for parity with the other scripts).
    2 — could not read/write a target file (permission error, bad JSON, missing
        plugin asset). Nothing is written past the point of failure.
    3 — never (stdlib only).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from hashlib import sha256
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent
GENERATOR_SRC = SKILL_DIR / "docs_index.py"
RULE_SRC = SKILL_DIR / "assets" / "sdlc-docs-access.md"
GLOSSARY_SRC = SKILL_DIR / "assets" / "sdlc-output-glossary.md"
LESSONS_SRC = SKILL_DIR.parent / "lesson" / "lessons.py"
LESSONS_RULE_SRC = SKILL_DIR / "assets" / "sdlc-lessons.md"
FINDINGS_SRC = SKILL_DIR.parent / "repair" / "findings.py"
FINDINGS_VALIDATOR_SRC = SKILL_DIR.parent / "repair" / "validate_findings.py"
FINDINGS_RULE_SRC = SKILL_DIR / "assets" / "sdlc-findings.md"
BUMP_SRC = SKILL_DIR.parent / "repair" / "bump_artifact.py"
REPO_SCAN_SRC = SKILL_DIR / "repo_scan.py"
STATUSBOARD_SRC = SKILL_DIR / "statusboard.py"
MIGRATE_WARNINGS_SRC = SKILL_DIR.parent / "repair" / "migrate_warnings.py"
WARNING_ITEM_SRC = SKILL_DIR.parent / "repair" / "warning_item.py"
PLUGIN_MANIFEST = SKILL_DIR.parent.parent / ".claude-plugin" / "plugin.json"
# Skills only the Pro edition ships. Their absence beside setup/ is how an
# install knows it is the free edition; the marker records it so the
# statusboard - a copy in the project, with no view of the plugin tree - can
# say so.
PRO_SKILLS = ("test", "task", "code")

GENERATOR_DEST_REL = ".claude/sdlc/docs_index.py"
RULE_DEST_REL = ".claude/rules/sdlc-docs-access.md"
GLOSSARY_DEST_REL = ".claude/rules/sdlc-output-glossary.md"
LESSONS_DEST_REL = ".claude/sdlc/lessons.py"
LESSONS_RULE_DEST_REL = ".claude/rules/sdlc-lessons.md"
FINDINGS_DEST_REL = ".claude/sdlc/findings.py"
FINDINGS_VALIDATOR_DEST_REL = ".claude/sdlc/validate_findings.py"
FINDINGS_RULE_DEST_REL = ".claude/rules/sdlc-findings.md"
BUMP_DEST_REL = ".claude/sdlc/bump_artifact.py"
REPO_SCAN_DEST_REL = ".claude/sdlc/repo_scan.py"
STATUSBOARD_DEST_REL = ".claude/sdlc/statusboard.py"
MIGRATE_WARNINGS_DEST_REL = ".claude/sdlc/migrate_warnings.py"
WARNING_ITEM_DEST_REL = ".claude/sdlc/warning_item.py"
MARKER_DEST_REL = ".claude/sdlc/sdlc-plugin.json"
HOOK_MATCHER = "Write|Edit|MultiEdit"
HOOK_TOKEN = "docs_index.py"  # idempotency marker inside the hook command
# Commands that regenerate a docs index some OTHER way (the project runs its
# own toolchain). A hook command containing one of these but not the stock
# generator path marks the index wiring as the project's own. The bare
# ``INDEX.yaml`` token is only a signal when the same command also carries a
# generator verb — a hook that merely validates or greps INDEX.yaml is not a
# generator.
FOREIGN_INDEX_TOKENS = ("docs_index", "docs-index")
FOREIGN_INDEX_FILE_TOKEN = "INDEX.yaml"
_GENERATOR_VERB_RE = re.compile(r"docs-index|\bindex\b|generate", re.IGNORECASE)
SECTION_HEADING = "## SDLC Documents"
INDEX_MARKER = "`docs/INDEX.yaml`"

# Helpers whose version the marker records. A helper declares
# ``__version__`` / ``VERSION`` / ``CAPABILITY_VERSION``; when it declares
# none, the marker stores the 16-hex content hash instead, so a re-run still
# notices an upgraded copy.
_VERSION_RE = re.compile(
    r'^(?:__version__|VERSION|CAPABILITY_VERSION|HELPER_VERSION)\s*=\s*["\']?([0-9][\w.\-]*)',
    re.MULTILINE,
)

# The whole `## SDLC Documents` section, written once and never rewritten.
#
# It used to be an intro paragraph plus one bullet per skill, each ending in
# "Last updated by `sdlc-<skill>` on <ISO timestamp>". That churned CLAUDE.md on
# every single run, restated `metadata.last_updated` which the artifact already
# carries, and - because CLAUDE.md is loaded into EVERY session - charged a
# standing context cost for information nothing ever read back. It is now a
# fixed eight lines: what exists, how to read it, and where the live state is.
# Byte-identical on every subsequent run, so `git diff CLAUDE.md` stays empty.
#
# The FIRST line is the idempotency sentinel (`SECTION_SENTINEL`).
SECTION_BODY = """This project's specs live in `docs/` - PRD, DATA-MODEL, ARCH, TEST-STRATEGY,
TASKS and their `__<slug>` shards (whichever the pipeline has produced).

**Read them by slice via `docs/INDEX.yaml`** - a generated map of every file,
symbol and line range. Never load `PRD.yaml`, `DATA-MODEL.yaml` or `TASKS.json`
whole. Protocol: `.claude/rules/sdlc-docs-access.md`.

Pipeline state, open questions and caveats: `.claude/rules/sdlc-statusboard.md`
(loaded automatically) and `.claude/sdlc/STATUS.md` (full text). Both generated -
never hand-edit either, and never record status in this file."""

SECTION_SENTINEL = "Read them by slice via"

# A bullet an older plugin version left behind: "- `docs/X`: ... by `sdlc-y` on
# <ts>." They are inert now (nothing rewrites them), so they are reported and
# left alone rather than deleted - this script never removes a line a user might
# have edited.
LEGACY_BULLET_RE = re.compile(
    r"^- `docs/[^`]+`.*\bsdlc-[a-z-]+`? on \d{4}-\d{2}-\d{2}T[\d:]+Z\.\s*$"
)


def _iso_utc_now() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _index_bullet(timestamp: str) -> str:
    return (
        f"- {INDEX_MARKER}: GENERATED navigation map — entrypoint for the SDLC "
        f"docs. Refreshed by the `docs-index` PostToolUse hook; never hand-edit. "
        f"`python .claude/sdlc/docs_index.py --show <symbol>` prints one symbol's "
        f"slice. Wired by `sdlc-setup` on {timestamp}."
    )


# ---------------------------------------------------------------------------
# own-toolchain detection (pure functions)
# ---------------------------------------------------------------------------


def is_foreign_index_command(cmd: str) -> bool:
    """True when a hook command regenerates a docs index with a non-stock tool.

    ``docs_index`` / ``docs-index`` in the command is enough on its own. The
    bare ``INDEX.yaml`` token counts only together with a generator verb
    (``docs-index`` / ``index`` / ``generate``) elsewhere in the same command,
    so ``grep FR-001 docs/INDEX.yaml`` or a validator that reads the index is
    never mistaken for a generator.
    """
    if not cmd or GENERATOR_DEST_REL in cmd:
        return False
    if any(t in cmd for t in FOREIGN_INDEX_TOKENS):
        return True
    if FOREIGN_INDEX_FILE_TOKEN in cmd:
        rest = cmd.replace(FOREIGN_INDEX_FILE_TOKEN, " ")
        return bool(_GENERATOR_VERB_RE.search(rest))
    return False


def _post_tool_use(settings: dict) -> "list":
    hooks = settings.get("hooks", {}) if isinstance(settings, dict) else {}
    post = hooks.get("PostToolUse", []) if isinstance(hooks, dict) else []
    return post if isinstance(post, list) else []


def foreign_hook_commands(settings: dict) -> "list[str]":
    """The non-stock index-generating hook commands present in settings."""
    found: "list[str]" = []
    for entry in _post_tool_use(settings):
        for h in entry.get("hooks", []) if isinstance(entry, dict) else []:
            cmd = str(h.get("command", "")) if isinstance(h, dict) else ""
            if is_foreign_index_command(cmd):
                found.append(cmd)
    return found


def detect_foreign_wiring(index_text: "str | None", settings: dict) -> "list[str]":
    """Reasons this project runs its OWN index toolchain. Pure - no I/O.

    Two signals, both cheap and both conservative: the docs/INDEX.yaml header
    naming a generator that is not the stock one, and a PostToolUse hook whose
    command regenerates an index without being the stock command. A false
    positive only skips the index wiring (with a clear log line and a
    --force-stock override); a false negative can only happen when there is no
    index wiring present to clobber.
    """
    reasons: "list[str]" = []
    if index_text:
        first = next((ln.strip() for ln in index_text.splitlines() if ln.strip()), "")
        if "GENERATED" in first.upper() and GENERATOR_DEST_REL not in first:
            reasons.append(
                f"docs/INDEX.yaml says it is generated by another tool: {first.lstrip('#').strip()}"
            )
    for cmd in foreign_hook_commands(settings):
        reasons.append(
            f"an existing hook already regenerates the index with another tool: {cmd}"
        )
    return reasons


def strip_foreign_hooks(settings: dict) -> "tuple[dict, list[str]]":
    """Return (new_settings, removed_commands) with every foreign index hook
    dropped; an entry left without hooks is dropped too. Pure — no I/O."""
    settings = json.loads(json.dumps(settings))  # deep copy
    removed: "list[str]" = []
    post = _post_tool_use(settings)
    kept_entries = []
    for entry in post:
        if not isinstance(entry, dict):
            kept_entries.append(entry)
            continue
        kept_hooks = []
        for h in entry.get("hooks", []):
            cmd = str(h.get("command", "")) if isinstance(h, dict) else ""
            if is_foreign_index_command(cmd):
                removed.append(cmd)
            else:
                kept_hooks.append(h)
        if kept_hooks or not entry.get("hooks"):
            entry["hooks"] = kept_hooks
            kept_entries.append(entry)
    if removed:
        settings.setdefault("hooks", {})["PostToolUse"] = kept_entries
    return settings, removed


# ---------------------------------------------------------------------------
# settings.json hook merge (pure function + I/O wrapper)
# ---------------------------------------------------------------------------


def _hook_command(python_cmd: str) -> str:
    # Anchored on $CLAUDE_PROJECT_DIR (Claude Code exports it to every hook), so
    # the hook finds the generator and the docs dir from any working directory.
    # Still ONE command: `docs_index.py --hook` refreshes the statusboard itself
    # after it rewrites the index. A second chained command would have nothing
    # to read - the hook event arrives on stdin, and only one process can
    # consume it.
    return (
        f'{python_cmd} "$CLAUDE_PROJECT_DIR/{GENERATOR_DEST_REL}" --hook '
        f'--project-root "$CLAUDE_PROJECT_DIR"'
    )


def merge_hook(settings: dict, python_cmd: str) -> "tuple[dict, str]":
    """Return (new_settings, action). Pure — no I/O.

    Ensures a single PostToolUse entry whose command runs the generator. If one
    already references the generator, the command is refreshed (in case the
    python invocation changed) but no duplicate is added and the entry's
    matcher is left exactly as the project has it — the entry may be shared
    with other hooks. The matcher is set only when a new entry is appended.
    """
    settings = json.loads(json.dumps(settings))  # deep copy
    hooks = settings.setdefault("hooks", {})
    post = hooks.setdefault("PostToolUse", [])
    if not isinstance(post, list):
        raise ValueError("hooks.PostToolUse is not a list")

    command = _hook_command(python_cmd)
    for entry in post:
        for h in entry.get("hooks", []) if isinstance(entry, dict) else []:
            if isinstance(h, dict) and HOOK_TOKEN in str(h.get("command", "")):
                if h["command"] == command:
                    return settings, "no-op"
                h["command"] = command
                return settings, "updated_command"

    post.append(
        {
            "matcher": HOOK_MATCHER,
            "hooks": [{"type": "command", "command": command}],
        }
    )
    return settings, "added_hook"


# ---------------------------------------------------------------------------
# CLAUDE.md section upsert (pure function)
# ---------------------------------------------------------------------------


def _find_section(lines: "list[str]", heading: str) -> "tuple[int, int] | None":
    for i, line in enumerate(lines):
        if line.strip() == heading:
            j = i + 1
            while j < len(lines) and not lines[j].startswith("## "):
                j += 1
            return i, j
    return None


def upsert_claude_md(content: str, timestamp: str) -> "tuple[str, str, list]":
    """Insert or refresh the static `## SDLC Documents` section.

    Returns `(content, action, legacy_bullets)`. `legacy_bullets` are the
    per-skill pointer lines an older plugin version wrote; they are LEFT IN
    PLACE and reported, so the caller can tell the user they are now inert.
    Nothing outside the section is ever touched, and the file's own line
    endings are preserved by the caller.
    """
    section = SECTION_HEADING + "\n\n" + SECTION_BODY + "\n"
    if not content:
        return section, "created", []

    had_trailing_newline = content.endswith("\n")
    lines = content.split("\n")
    if had_trailing_newline:
        lines.pop()

    found = _find_section(lines, SECTION_HEADING)
    if found is None:
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines += [SECTION_HEADING, ""] + SECTION_BODY.split("\n")
        out = "\n".join(lines) + "\n"
        return out, "appended_section", []

    start, end = found
    body = lines[start + 1:end]
    keep = [ln for ln in body if ln.strip() and not _is_ours(ln)]
    # Only the bullets that SURVIVE are worth reporting: the retired access
    # note and INDEX bullet are ours and have just been replaced, so counting
    # those would report work this run already did.
    legacy = [ln for ln in keep if LEGACY_BULLET_RE.match(ln.strip())]
    # Anything in the section we did not write (the legacy bullets, or a note a
    # user added) is preserved BELOW the block rather than dropped.
    new_body = [""] + SECTION_BODY.split("\n")
    if keep:
        new_body += [""] + keep
    new_body += [""]  # one blank line before whatever heading follows
    if body == new_body:
        action = "no-op"
    else:
        action = "updated_section"
    lines[start + 1:end] = new_body
    out = "\n".join(lines)
    if had_trailing_newline:
        out += "\n"
    return out, action, legacy


def _is_ours(line: str) -> bool:
    """True for a line this script wrote in a previous run (any version)."""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped in {ln.strip() for ln in SECTION_BODY.split("\n")}:
        return True
    return (
        "Access the docs below via" in stripped        # the retired intro note
        or INDEX_MARKER in stripped and "Wired by" in stripped  # retired bullet
    )


# ---------------------------------------------------------------------------
# plugin-version marker (pure function + manifest reader)
# ---------------------------------------------------------------------------


def read_plugin_version() -> "str | None":
    try:
        data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    version = data.get("version")
    return str(version) if version else None


def plugin_edition() -> str:
    """'pro' when every Pro-only skill ships beside setup, else 'free'."""
    skills = SKILL_DIR.parent
    return "pro" if all((skills / s / "SKILL.md").is_file() for s in PRO_SKILLS) else "free"


def read_plugin_homepage() -> "str | None":
    """The free build's pointer to the Pro edition (plugin.json `homepage`)."""
    try:
        data = json.loads(PLUGIN_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    url = data.get("homepage") if isinstance(data, dict) else None
    return str(url) if url else None


def helper_version(path: Path) -> "str | None":
    """A helper's declared version, else ``sha:<16-hex>`` of its content."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = _VERSION_RE.search(text)
    if match is not None:
        return match.group(1)
    return "sha:" + sha256(text.encode("utf-8")).hexdigest()[:16]


# The telemetry block seeded on a fresh install. `mode: off` is the default on
# purpose: nothing leaves a project until someone answers the consent question.
# lessons.py owns the semantics and fills in any key missing here, so this stays
# a discoverable starting point rather than a second source of truth.
TELEMETRY_SEED = {
    "mode": "off",
    "consented_on": None,
    "project_id": None,
    # Minted by lessons.py on the first delivery, not here: a project that
    # never consents never gets one, and an id nobody will send is noise in
    # the marker. Named in the seed so the block is self-describing.
    "project_uuid": None,
    "batch_days": 7,
    "batch_max": 10,
    "runs_only_days": 30,
    "retry_after_hours": 6,
    "last_sent_at": None,
    "last_attempt_at": None,
    "last_sent_count": 0,
}


def telemetry_block(existing: "dict | None", project_id: "str | None") -> dict:
    """The marker's telemetry block: an existing one wins, seeded when absent.

    A re-run must never reset someone's answer, so every stored key survives and
    only the gaps are filled.
    """
    block = dict(TELEMETRY_SEED)
    stored = (existing or {}).get("telemetry")
    if isinstance(stored, dict):
        block.update(stored)
    if not block.get("project_id"):
        block["project_id"] = project_id
    return block


def plugin_marker(
    existing: "dict | None", version: str, timestamp: str,
    helpers: "dict[str, str] | None" = None, project_id: "str | None" = None,
    edition: str = "pro", pro_url: "str | None" = None,
) -> "tuple[dict, str]":
    """Return (marker, action). Pure — no I/O.

    `installed_at` is stamped only when the plugin version or a helper version
    actually changes, so a re-run at the same versions is a clean no-op, not a
    churned timestamp. The telemetry block is carried forward verbatim: it holds
    the user's consent answer, which this installer must never overwrite.
    """
    helpers = helpers or {}
    telemetry = telemetry_block(existing, project_id)
    if (
        isinstance(existing, dict)
        and existing.get("plugin_version") == version
        and existing.get("helpers", {}) == helpers
        and existing.get("telemetry") == telemetry
        and existing.get("edition", "pro") == edition
        and existing.get("pro_url") == pro_url
    ):
        return existing, "no-op"
    marker = {
        "plugin_version": version,
        "installed_at": timestamp,
        "wired_by": "sdlc-setup",
        "helpers": helpers,
        "edition": edition,
        "telemetry": telemetry,
    }
    if pro_url:
        marker["pro_url"] = pro_url
    if isinstance(existing, dict) and existing.get("installed_at") \
            and existing.get("plugin_version") == version \
            and existing.get("helpers", {}) == helpers:
        # Only the telemetry block moved (a first install of it onto an older
        # marker). Nothing about the install itself changed, so keep its date.
        marker["installed_at"] = existing["installed_at"]
    return marker, ("updated" if isinstance(existing, dict) else "written")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


_TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".txt"}


def _payload(src: Path) -> bytes:
    """What lands in the project: the plugin file's bytes, with a text file's
    CRLF normalized to LF. The plugin's sources are LF, but a consumer's
    checkout may not be (core.autocrlf=true rewrites them on the way in), and
    a verbatim copy would install that convention into every helper - the
    third CRLF-class defect (ledger IMP-024, aicf LSN-007). The repo pins
    eol=lf in .gitattributes too; this half covers a checkout the plugin does
    not control."""
    raw = src.read_bytes()
    if src.suffix.lower() in _TEXT_SUFFIXES and b"\r\n" in raw:
        raw = raw.replace(b"\r\n", b"\n")
    return raw


def _copy(src: Path, dest: Path, dry: bool, log: "list[str]") -> bool:
    """Copy when different. Returns True when something was (or would be) written."""
    payload = _payload(src)
    same = dest.exists() and dest.read_bytes() == payload
    verb = "no-op (identical)" if same else ("would copy" if dry else "copied")
    log.append(f"  [{verb}] {dest}")
    if dry or same:
        return not same
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return True


def run(
    project_root: Path, python_cmd: str, dry: bool, force_stock: bool = False
) -> "tuple[int, list[str], str]":
    """Perform the wiring. Returns ``(exit_code, action_log, status)`` with
    status ∈ {complete, partial, failed}: partial when the project keeps its
    own index toolchain and only the generator-agnostic pieces were installed."""
    log: list[str] = []
    sources = (
        GENERATOR_SRC, RULE_SRC, GLOSSARY_SRC, LESSONS_SRC, LESSONS_RULE_SRC,
        FINDINGS_SRC, FINDINGS_VALIDATOR_SRC, FINDINGS_RULE_SRC, BUMP_SRC,
        REPO_SCAN_SRC, STATUSBOARD_SRC, MIGRATE_WARNINGS_SRC, WARNING_ITEM_SRC,
    )
    if not all(src.is_file() for src in sources):
        missing = ", ".join(str(s) for s in sources if not s.is_file())
        return 2, [f"[ERR] plugin assets missing: {missing}"], "failed"

    # 0: read settings.json up front - the own-toolchain check needs it, and a
    # malformed file should abort before anything is written.
    settings_path = project_root / ".claude" / "settings.json"
    try:
        settings = (
            json.loads(settings_path.read_text(encoding="utf-8"))
            if settings_path.exists()
            else {}
        )
    except (OSError, ValueError) as e:
        return 2, [f"[ERR] cannot read {settings_path}: {e}"], "failed"

    index_path = project_root / "docs" / "INDEX.yaml"
    try:
        index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    except OSError:
        index_text = None

    foreign = [] if force_stock else detect_foreign_wiring(index_text, settings)
    removed_hooks: "list[str]" = []
    if foreign:
        log.append(
            "  [own-toolchain] this project generates docs/INDEX.yaml with its own "
            "tool; the stock index wiring is NOT installed, so it cannot overwrite yours:"
        )
        for reason in foreign:
            log.append(f"      - {reason}")
        log.append(
            "      re-run with --force-stock only if you want the stock index "
            "toolchain to REPLACE this project's own"
        )
    elif force_stock:
        settings, removed_hooks = strip_foreign_hooks(settings)
        for cmd in removed_hooks:
            log.append(f"  [{'would remove' if dry else 'removed'}] foreign index hook: {cmd}")

    def _left_alone(dest: "Path | str", what: str) -> None:
        log.append(f"  [left untouched] {dest} ({what})")

    # 1 + 2: copy generator + docs-access rule (stock index wiring - skipped for
    # a project running its own toolchain); the generator-agnostic helpers
    # (glossary, lessons, findings, bump) always.
    written = 0
    if foreign:
        _left_alone(project_root / GENERATOR_DEST_REL, "stock index generator")
        _left_alone(project_root / RULE_DEST_REL, "stock docs-access rule")
    else:
        written += _copy(GENERATOR_SRC, project_root / GENERATOR_DEST_REL, dry, log)
        written += _copy(RULE_SRC, project_root / RULE_DEST_REL, dry, log)
    for src, dest_rel in (
        (GLOSSARY_SRC, GLOSSARY_DEST_REL),
        (LESSONS_SRC, LESSONS_DEST_REL),
        (LESSONS_RULE_SRC, LESSONS_RULE_DEST_REL),
        (FINDINGS_SRC, FINDINGS_DEST_REL),
        (FINDINGS_VALIDATOR_SRC, FINDINGS_VALIDATOR_DEST_REL),
        (FINDINGS_RULE_SRC, FINDINGS_RULE_DEST_REL),
        (BUMP_SRC, BUMP_DEST_REL),
        (REPO_SCAN_SRC, REPO_SCAN_DEST_REL),
        (STATUSBOARD_SRC, STATUSBOARD_DEST_REL),
        (MIGRATE_WARNINGS_SRC, MIGRATE_WARNINGS_DEST_REL),
        (WARNING_ITEM_SRC, WARNING_ITEM_DEST_REL),
    ):
        written += _copy(src, project_root / dest_rel, dry, log)

    # 2h: plugin-version marker (recorded runs/lessons/findings name the versions they blame).
    marker_path = project_root / MARKER_DEST_REL
    version = read_plugin_version()
    if version is None:
        log.append(
            f"  [skipped] {marker_path} - plugin manifest not readable at {PLUGIN_MANIFEST}"
        )
    else:
        helpers = {
            name: ver
            for name, ver in (
                ("docs_index", helper_version(GENERATOR_SRC) if not foreign else None),
                ("lessons", helper_version(LESSONS_SRC)),
                ("findings", helper_version(FINDINGS_SRC)),
                ("bump_artifact", helper_version(BUMP_SRC)),
                ("repo_scan", helper_version(REPO_SCAN_SRC)),
                ("statusboard", helper_version(STATUSBOARD_SRC)),
                ("migrate_warnings", helper_version(MIGRATE_WARNINGS_SRC)),
            )
            if ver
        }
        try:
            existing = (
                json.loads(marker_path.read_text(encoding="utf-8"))
                if marker_path.exists()
                else None
            )
        except (OSError, ValueError):
            existing = None
        edition = plugin_edition()
        marker, marker_action = plugin_marker(
            existing, version, _iso_utc_now(), helpers,
            project_id=sha256(str(project_root.resolve()).encode("utf-8")).hexdigest()[:12],
            edition=edition,
            pro_url=read_plugin_homepage() if edition == "free" else None,
        )
        log.append(
            f"  [{'would ' + marker_action if dry else marker_action}] {marker_path} (plugin {version})"
        )
        if not dry and marker_action != "no-op":
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text(
                json.dumps(marker, indent=2) + "\n", encoding="utf-8"
            )
            written += 1

    # 3: merge settings.json hook (skipped for a project running its own toolchain).
    if foreign:
        _left_alone(settings_path, "PostToolUse hook")
    else:
        try:
            new_settings, hook_action = merge_hook(settings, python_cmd)
        except ValueError as e:
            return 2, log + [f"[ERR] {settings_path}: {e}"], "failed"
        if hook_action == "no-op" and removed_hooks:
            hook_action = "updated_hooks"
        log.append(f"  [{'would ' + hook_action if dry else hook_action}] {settings_path} (PostToolUse hook)")
        if not dry and hook_action != "no-op":
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            settings_path.write_text(
                json.dumps(new_settings, indent=2) + "\n", encoding="utf-8"
            )
            written += 1

    # 4: the static CLAUDE.md section (skipped for a project running its own
    # the bullet documents stock commands the project does not use).
    claude_md = project_root / "CLAUDE.md"
    if foreign:
        _left_alone(claude_md, "index pointer")
    else:
        try:
            # Read BYTES, not text: read_text() decodes with universal newlines,
            # so a CRLF file arrives as LF and the newline detection below can
            # never see what the file actually uses (ledger IMP-006).
            raw = claude_md.read_bytes() if claude_md.exists() else b""
        except OSError as e:
            return 2, log + [f"[ERR] cannot read {claude_md}: {e}"], "failed"
        newline = "\r\n" if b"\r\n" in raw else "\n"
        original = raw.decode("utf-8").replace("\r\n", "\n")
        new_md, md_action, legacy = upsert_claude_md(original, _iso_utc_now())
        log.append(f"  [{'would ' + md_action if dry else md_action}] {claude_md} (## SDLC Documents)")
        if legacy:
            log.append(
                f"  [note] {len(legacy)} per-skill pointer bullet(s) from an older "
                f"plugin version are still in that section. Nothing rewrites them "
                f"now, so they will never update again - delete them by hand when "
                f"you like; this script will not touch them."
            )
        if not dry and md_action != "no-op":
            # Keep the file's own line endings: rewriting a CRLF CLAUDE.md in LF
            # (or the reverse) turns a two-line edit into a whole-file diff.
            claude_md.write_bytes(
                new_md.replace("\r\n", "\n").replace("\n", newline).encode("utf-8"))
            written += 1

    # 5: initial index generation (skipped for a project running its own toolchain).
    docs_dir = project_root / "docs"
    if foreign:
        _left_alone(docs_dir / "INDEX.yaml", "generated by the project's own tool")
    elif dry:
        log.append(f"  [would generate] {docs_dir / 'INDEX.yaml'}")
    else:
        sys.path.insert(0, str(SKILL_DIR))
        import docs_index  # local import; SKILL_DIR is on sys.path

        if docs_dir.is_dir():
            target = docs_index.write_index(docs_dir)
            log.append(f"  [generated] {target}")
            written += 1
            # 5b: the statusboard, so the project has one from minute one.
            import subprocess

            board = project_root / STATUSBOARD_DEST_REL
            rc = subprocess.call([sys.executable, str(board), "--path", str(project_root)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) \
                if board.exists() else 1
            if rc == 0:
                log.append(f"  [generated] {project_root / '.claude/rules/sdlc-statusboard.md'}")
                written += 1
            else:
                log.append("  [skipped] statusboard (needs pyyaml; run "
                           "'python .claude/sdlc/statusboard.py' once it is installed)")
        else:
            log.append(f"  [skipped] {docs_dir} does not exist yet - index will be built on first doc write")
    log.append(f"  targets written: {written}")
    return 0, log, ("partial" if foreign else "complete")


def _force_utf8_stdio() -> None:
    """Best-effort: keep prints working on a non-UTF-8 console (e.g. Windows cp1252)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def main(argv: "list[str] | None" = None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description="Wire docs/INDEX.yaml and the SDLC helpers into a project.")
    ap.add_argument("--project-root", default=".", help="Target project root (default: cwd).")
    ap.add_argument("--python", default="python", help='Python invocation for the hook (e.g. "uv run python").')
    ap.add_argument("--dry-run", action="store_true", help="Print planned changes without writing.")
    ap.add_argument(
        "--force-stock",
        action="store_true",
        help="Replace a project's own index toolchain (docs/INDEX.yaml, the "
             "foreign hook, the generator) with the stock one.",
    )
    args = ap.parse_args(argv)

    root = Path(args.project_root).resolve()
    code, log, status = run(root, args.python, args.dry_run, args.force_stock)
    header = "[DRY-RUN] " if args.dry_run else ""
    print(f"{header}sdlc:setup wiring -> {root}")
    print("\n".join(log))
    print()
    if code != 0:
        print(f"[FAIL] sdlc:setup could not wire {root} - nothing was written past the "
              f"point of failure.")
        print("Status:    failed")
        print("\nNEXT: fix the file named above, then re-run /sdlc:setup")
        return code
    if status == "partial":
        print(f"{header}[OK] the shared helpers are installed; this project keeps its own "
              f"docs/INDEX.yaml toolchain, so the stock index wiring was not touched.")
        print(f"Status:    partial (own index toolchain kept; glossary, lessons, findings and "
              f"bump helpers installed)")
        print(f"\nNEXT: /sdlc:prd  (or re-run /sdlc:setup --force-stock to replace the "
              f"project's own index toolchain with the stock one)")
        return 0
    verb = "would be wired" if args.dry_run else "is wired"
    print(f"{header}[OK] {root} {verb} - /sdlc:prd can run.")
    print(f"Status:    {'dry-run (nothing written)' if args.dry_run else 'complete'}")
    print(f"\nNEXT: {'/sdlc:setup without --dry-run' if args.dry_run else '/sdlc:prd'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
