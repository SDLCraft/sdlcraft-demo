#!/usr/bin/env python3
"""migrate_warnings.py - convert an artifact's legacy "WRN-NNN: <text>" warning
strings into the typed mapping form (CLAUDE.md section 2).

Legacy strings stay valid forever, so this migration is entirely optional. What
it buys is signal: only a typed warning carries `kind`, `status` and `impact`,
and only those three let the generated statusboard separate a live caveat from
settled bookkeeping. An unmigrated artifact reads as `{kind: note, status: open,
impact: local}` - correct, but the board can then only count it.

WHAT IT DECIDES, AND WHAT IT LEAVES TO YOU
    Pre-classified, because the corpus already says so in prose:
      * a leading "RESOLVED <YYYY-MM-DD>"  -> status: resolved + resolved_on
      * the word "deferred" / "deferral"   -> kind: deferral
    Left alone, deliberately:
      * `impact` is always written as `local`. Guessing that a warning matters
        downstream is exactly the judgement a person should make; a wrong guess
        would put noise on every session's statusboard.
      * `defers:` is never populated. Extracting ids from prose is the very
        word-match the typed channel exists to retire - adding them by hand is
        what arms the coverage gate.
    The message text is copied VERBATIM. Nothing is summarized or dropped.

The edit is textual for YAML: only the warnings block is rewritten, so every
comment and every other line in the file survives byte-identical. Comments
*inside* a warnings block are not preserved. JSON artifacts are loaded and
dumped with their existing indent.

Only TOP-LEVEL `*_warnings` blocks are migrated. A nested one (a container's
own list inside ARCH.yaml, say) is left untouched and reported.

Any skill may run this over its own artifact - it is not `repair`'s alone. Two
flags exist for that caller, and a caller that is not `repair` needs both:

    --by <skill>   who to credit in the changelog line (default: sdlc-repair)
    --no-bump      convert only, leaving the version for the caller's own write

Pass `--by` whenever another skill runs the conversion, or the artifact's
history will credit a skill that never ran; pass `--no-bump` as well when that
skill writes its own changelog line for the same run, or one run bumps the
version twice (ledger IMP-030).

Usage:
    python migrate_warnings.py --path docs/UX.yaml
    python migrate_warnings.py --all --dry-run       # every artifact under docs/
    python migrate_warnings.py --path docs/UX.yaml --no-bump
    python migrate_warnings.py --path docs/PRD.yaml --by sdlc-prd --no-bump

Exit codes:
    0 - migrated (or, with --dry-run, would migrate); nothing to do also exits 0.
    1 - at least one block could not be migrated and was left as it is.
    2 - could not read or parse a named file.
    3 - required dependency missing (pyyaml).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "[FAIL] pyyaml is not installed - this script cannot read the artifacts.\n"
        "       Install it with 'pip install pyyaml' and run again.\n"
    )
    raise SystemExit(3)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from warning_item import parse_warnings  # noqa: E402

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"
# Credited in the changelog line when no caller says otherwise. `repair`
# is the usual runner, not the only permitted one - see bump().
DEFAULT_BY = "sdlc-repair"

_FIELD_RE = re.compile(r"^([a-z_]+_warnings):\s*(.*)$")
_RESOLVED_RE = re.compile(r"^RESOLVED\s+(\d{4}-\d{2}-\d{2})\b")
_DEFER_RE = re.compile(r"\bdeferr(?:ed|al)\b", re.IGNORECASE)


def classify(text):
    """(kind, status, resolved_on) for one legacy message. Never guesses impact."""
    kind = "deferral" if _DEFER_RE.search(text) else "note"
    m = _RESOLVED_RE.match(text)
    if m:
        return kind, "resolved", m.group(1)
    return kind, "open", None


def to_item(w):
    """One typed mapping from one WarningItem, in a stable key order."""
    kind, status, resolved_on = classify(w.text)
    item = {"id": w.id, "text": w.text, "kind": kind,
            "status": status, "impact": "local"}
    if status == "resolved":
        item["resolution"] = "Stated in the message above."
        if resolved_on:
            item["resolved_on"] = resolved_on
    return item


def render_yaml_block(field, items):
    """The replacement lines for one YAML warnings block, indented two spaces."""
    body = yaml.safe_dump(items, default_flow_style=False, sort_keys=False,
                          allow_unicode=True, width=100)
    out = [field + ":"]
    for line in body.rstrip("\n").split("\n"):
        out.append("  " + line)
    return out


def migrate_yaml(path, dry_run):
    """Rewrite every top-level warnings block. Returns (n_converted, notes)."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    notes, converted, out, i = [], 0, [], 0
    while i < len(lines):
        m = _FIELD_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        field, inline = m.group(1), m.group(2).strip()
        if inline and inline != "[]" and not inline.startswith("#"):
            notes.append("%s is written inline - left as it is" % field)
            out.append(lines[i])
            i += 1
            continue
        j = i + 1
        while j < len(lines) and (lines[j].startswith("  ") or lines[j].strip() == ""):
            j += 1
        while j - 1 > i and lines[j - 1].strip() == "":
            j -= 1
        block = "\n".join([field + ":"] + lines[i + 1:j])
        try:
            parsed = yaml.safe_load(block) or {}
        except yaml.YAMLError as exc:
            notes.append("%s did not parse (%s) - left as it is" % (field, exc))
            out.extend(lines[i:j])
            i = j
            continue
        entries = parsed.get(field) or []
        if not entries or all(isinstance(e, dict) for e in entries):
            out.extend(lines[i:j])
            i = j
            continue
        items, errors, _shape = parse_warnings(entries, field)
        if errors:
            notes.append("%s has %d entr%s that is not 'WRN-NNN: <message>' - "
                         "left as it is; fix those first"
                         % (field, len(errors), "y" if len(errors) == 1 else "ies"))
            out.extend(lines[i:j])
            i = j
            continue
        out.extend(render_yaml_block(field, [to_item(w) for w in items]))
        converted += len(items)
        i = j
    if converted and not dry_run:
        path.write_bytes(newline.join(out).encode("utf-8"))
    return converted, notes


def migrate_json(path, dry_run):
    """Same, for the JSON artifacts (TASKS*.json, CODE-MANIFEST.json)."""
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    try:
        doc = json.loads(raw)
    except ValueError as exc:
        return 0, ["did not parse (%s) - left as it is" % exc]
    indent = 2
    for line in raw.replace("\r\n", "\n").split("\n")[1:]:
        if line.strip():
            indent = (len(line) - len(line.lstrip(" "))) or 2
            break
    converted, notes = 0, []
    for field in [k for k in doc if k.endswith("_warnings")]:
        entries = doc.get(field) or []
        if not entries or all(isinstance(e, dict) for e in entries):
            continue
        items, errors, _shape = parse_warnings(entries, field)
        if errors:
            notes.append("%s has %d entry/entries that is not 'WRN-NNN: <message>' - "
                         "left as it is" % (field, len(errors)))
            continue
        doc[field] = [to_item(w) for w in items]
        converted += len(items)
    if converted and not dry_run:
        text = json.dumps(doc, indent=indent, ensure_ascii=False) + "\n"
        path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return converted, notes


def bump(path, converted, by=DEFAULT_BY):
    """Bump metadata.<name>_version and prepend the changelog line.

    `by` is the skill that actually ran this conversion. It is a parameter
    because the helper is shared: any skill may type its own artifact's
    warnings, and a changelog line crediting a skill that never ran misreports
    the artifact's history (ledger IMP-030). A caller that will write its own
    changelog line for the same run should pass --no-bump instead, so the run
    produces one version bump rather than two.
    """
    script = Path(__file__).resolve().parent / "bump_artifact.py"
    summary = ("Typed %d warning%s (kind/status/impact); message text unchanged"
               % (converted, "" if converted == 1 else "s"))
    try:
        return subprocess.call([sys.executable, str(script), "--file", str(path),
                                "--summary", summary, "--by", by])
    except OSError:
        return 1


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--path", help="one artifact to migrate")
    ap.add_argument("--all", action="store_true", help="every artifact under docs/")
    ap.add_argument("--docs-dir", default="docs")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    ap.add_argument("--no-bump", action="store_true",
                    help="skip the version + changelog bump - pass this when "
                         "the calling skill writes its own changelog line for "
                         "the same run, so the run bumps the version once")
    ap.add_argument("--by", default=DEFAULT_BY,
                    help="the skill running this conversion, credited in the "
                         "changelog line (default: %s)" % DEFAULT_BY)
    args = ap.parse_args()

    if not args.path and not args.all:
        ap.error("give --path <file> or --all")

    if args.path:
        targets = [Path(args.path)]
    else:
        d = Path(args.docs_dir)
        targets = sorted([p for p in d.glob("*.yaml") if p.name != "INDEX.yaml"]
                         + list(d.glob("*.json")))

    total, files_changed, left_alone = 0, [], 0
    print("SDLC warning migration%s"
          % (" - dry run, nothing is written" if args.dry_run else ""))
    print("")
    for path in targets:
        if not path.exists():
            print("[FAIL] %s does not exist." % path)
            return 2
        try:
            fn = migrate_json if path.suffix == ".json" else migrate_yaml
            converted, notes = fn(path, args.dry_run)
        except (OSError, UnicodeDecodeError) as exc:
            print("[FAIL] %s could not be read (%s)." % (path, exc))
            return 2
        for n in notes:
            left_alone += 1
            print("  %-34s %s" % (path.name, n))
        if converted:
            total += converted
            files_changed.append((path, converted))
            print("  %-34s %d warning(s) typed" % (path.name, converted))

    print("")
    if not total:
        print("[OK] nothing to migrate - every warning is already typed.")
        return 1 if left_alone else 0

    if not args.dry_run and not args.no_bump:
        for path, n in files_changed:
            bump(path, n, args.by)

    verb = "would be" if args.dry_run else "were"
    print("[OK] %d warning(s) in %d file(s) %s typed as {kind, status, impact}."
          % (total, len(files_changed), verb))
    print("")
    print("STILL YOURS TO DO - the migration deliberately does not guess:")
    print("  * impact is 'local' on every entry. Raise the ones a later stage must")
    print("    account for to 'downstream', and a known hazard in the built system")
    print("    to 'risk'. Only those two reach the statusboard.")
    print("  * a 'deferral' carries no 'defers:' ids yet. Add them to arm the")
    print("    structured coverage channel; until then that gate stays armed.")
    print("")
    print("NEXT:      python .claude/sdlc/statusboard.py    # see what the board now shows")
    print("           Label meanings: %s" % GLOSSARY_PATH)
    return 1 if left_alone else 0


if __name__ == "__main__":
    sys.exit(main())
