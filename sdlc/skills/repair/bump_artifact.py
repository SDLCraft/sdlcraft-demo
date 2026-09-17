#!/usr/bin/env python3
"""bump_artifact.py — bump one docs/ artifact's metadata version and prepend
its changelog line, as ONE text-level edit that preserves comments, key order
and formatting.

Every sdlc artifact carries `metadata.<name>_version` and an append-only
`metadata.changelog` whose newest line comes first (CLAUDE.md section 1).
Every write that changes an artifact's content is supposed to bump the one
and prepend to the other in the same write — repair's surgical mode, the task
re-slicer, and the arch/test/task skills' Phase 7 all need it. Doing it by
hand is how the demo corpus ended up with ARCH at 1.36 while its newest
changelog line said 1.25: a version bumped without a line, and lines out of
order. This script refuses to layer a new line onto that state unless told to.

The edit is textual for YAML (a yaml round-trip would drop every comment and
re-flow every string); JSON artifacts (TASKS*.json, CODE-MANIFEST.json) are
loaded and dumped with indent 2, key order preserved. Line endings are kept
as found. `metadata.last_updated` is refreshed when the key exists.

Usage:
    python bump_artifact.py --file docs/ARCH__demo-api.yaml --summary "Added the page parameter to listItems"
    python bump_artifact.py --file docs/TASKS__demo-api.json --summary "..." --by sdlc-repair
    python bump_artifact.py --file docs/PRD.yaml --summary "..." --patch      # 1.3 -> 1.3.1 (default --minor: 1.3 -> 1.4)
    python bump_artifact.py --file docs/PRD.yaml --summary "..." --dry-run    # print, write nothing
    python bump_artifact.py --file docs/PRD.yaml --summary "..." --force      # accept an out-of-order changelog

Exit codes:
    0 — bumped (or, with --dry-run, would bump) and the changelog line is in place.
    1 — refused: the on-disk version is above EVERY version the changelog names,
        so a bump happened without a line. Fix the changelog by hand or pass
        --force. A changelog that merely lists its lines oldest-first is not
        refused: the new line is prepended and the order is reported (ledger
        IMP-140).
    2 — could not read or parse the file, or it carries no metadata.<name>_version.
    3 — required dependency missing (pyyaml).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    print("ERROR: pyyaml is required.\nInstall with:  pip install pyyaml", file=sys.stderr)
    sys.exit(3)

VERSION_KEY_RE = re.compile(r"^(\s+)([A-Za-z_][\w]*_version)\s*:\s*(.*?)\s*(#.*)?$")
CHANGELOG_KEY_RE = re.compile(r"^(\s+)changelog\s*:\s*(.*?)\s*(#.*)?$")
LAST_UPDATED_RE = re.compile(r"^(\s+)last_updated\s*:\s*(.*?)\s*(#.*)?$")
ENTRY_VERSION_RE = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*\(")
VERSION_RE = re.compile(r"^\d+(?:\.\d+)*$")


def _force_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_version(text: str) -> Optional[Tuple[int, ...]]:
    text = text.strip().strip("\"'")
    if not VERSION_RE.match(text):
        return None
    return tuple(int(p) for p in text.split("."))


def bump_version(parts: Tuple[int, ...], patch: bool) -> str:
    p = list(parts)
    if patch:
        while len(p) < 3:
            p.append(0)
        p[2] += 1
    else:
        while len(p) < 2:
            p.append(0)
        p[1] += 1
        p = p[:2]
    return ".".join(str(x) for x in p)


def changelog_line(version: str, summary: str, by: Optional[str]) -> str:
    text = summary.strip()
    if by:
        text = f"{text} [{by}]"
    return f"{version} ({_today()}): {text}"


def entry_versions(entries: List[str]) -> List[Optional[Tuple[int, ...]]]:
    """The version each changelog line names, in file order (None where a line
    carries none - an `initial.` entry is allowed and dates nothing)."""
    out: List[Optional[Tuple[int, ...]]] = []
    for raw in entries:
        m = ENTRY_VERSION_RE.match(str(raw))
        out.append(parse_version(m.group(1)) if m else None)
    return out


def refusal(current: Tuple[int, ...], versions: List[Optional[Tuple[int, ...]]], key: str,
            file: str) -> Optional[str]:
    """Refuse only when the artifact's version is above EVERY version its
    changelog names - a bump that never got its line. Reading only the FIRST
    line (what this did until ledger IMP-140) could not tell that apart from a
    list written oldest-first, which is a nuisance, not a missing line: the
    reported case had its current line present, at the end. That refusal made
    the first surgical /sdlc:repair on such a file fail while every validator
    called the file green."""
    known = [v for v in versions if v is not None]
    if not known or current <= max(known):
        return None
    return (f"[FAIL] {file}: metadata.{key} is {'.'.join(map(str, current))} but no "
            f"changelog line names it - the newest one says "
            f"{'.'.join(map(str, max(known)))}, so a version was bumped without a "
            f"line. Add the missing line (newest first) or re-run with --force to "
            f"layer the new line on top anyway.")


def order_note(versions: List[Optional[Tuple[int, ...]]], key: str) -> Optional[str]:
    """One line when the changelog is not newest-first. Never blocks: the new
    line still goes on top, and the list is then one entry closer to sorted."""
    known = [(i, v) for i, v in enumerate(versions) if v is not None]
    if len(known) < 2:
        return None
    top, newest = known[0], max(known, key=lambda iv: iv[1])
    if top[1] >= newest[1]:
        return None
    return (f"metadata.changelog is not newest-first: its first line says "
            f"{'.'.join(map(str, top[1]))} while entry {newest[0] + 1} says "
            f"{'.'.join(map(str, newest[1]))}. The new line went on top anyway; "
            f"put the rest in order (CLAUDE.md section 1) when you next edit "
            f"metadata.{key}.")


# --------------------------------------------------------------------------
# YAML (text-level)
# --------------------------------------------------------------------------

def _metadata_block(lines: List[str]) -> Optional[Tuple[int, int]]:
    """[start, end) line indexes of the top-level `metadata:` mapping body."""
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^metadata\s*:\s*(#.*)?$", ln):
            start = i + 1
            break
    if start is None:
        return None
    end = start
    while end < len(lines):
        ln = lines[end]
        if ln.strip() == "" or ln.startswith((" ", "\t")) or ln.lstrip().startswith("#"):
            end += 1
            continue
        break
    return start, end


def _quote(value: str, like: str) -> str:
    if like.startswith("'") and like.endswith("'") and len(like) >= 2:
        return f"'{value}'"
    return json.dumps(value)   # double-quoted, JSON escaping is valid YAML


def bump_yaml(text: str, summary: str, by: Optional[str], patch: bool, force: bool,
              file: str) -> Tuple[Optional[str], str, int]:
    """(new text | None, message, exit code)."""
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(nl)
    block = _metadata_block(lines)
    if block is None:
        return None, f"[FAIL] {file}: no top-level `metadata:` mapping - nothing to bump.", 2
    start, end = block

    ver_idx = key = None
    for i in range(start, end):
        m = VERSION_KEY_RE.match(lines[i])
        if m:
            ver_idx, key = i, m.group(2)
            break
    if ver_idx is None or key is None:
        return None, f"[FAIL] {file}: metadata carries no `<name>_version` key - nothing to bump.", 2
    m = VERSION_KEY_RE.match(lines[ver_idx])
    assert m is not None
    indent, raw_value, comment = m.group(1), m.group(3), m.group(4) or ""
    current = parse_version(raw_value)
    if current is None:
        return None, f"[FAIL] {file}: metadata.{key} is {raw_value!r}, not a dotted version - cannot bump.", 2
    new_version = bump_version(current, patch)

    # The changelog: find it, read its newest entry's version for the refusal rule.
    cl_idx = None
    for i in range(start, end):
        if CHANGELOG_KEY_RE.match(lines[i]):
            cl_idx = i
            break
    versions: List[Optional[Tuple[int, ...]]] = []
    items_start = None
    item_indent = indent + "  "
    inline_items: Optional[List[str]] = None
    if cl_idx is not None:
        cm = CHANGELOG_KEY_RE.match(lines[cl_idx])
        assert cm is not None
        inline = cm.group(2)
        if inline and inline != "[]":
            try:
                loaded = yaml.safe_load(inline)
            except yaml.YAMLError:
                loaded = None
            if not isinstance(loaded, list):
                return None, f"[FAIL] {file}: metadata.changelog is not a list - cannot prepend.", 2
            inline_items = [str(x) for x in loaded]
            versions = entry_versions(inline_items)
        elif not inline:
            j = cl_idx + 1
            while j < end and (lines[j].strip() == "" or lines[j].lstrip().startswith("#")):
                j += 1
            if j < end and re.match(r"^\s+-\s", lines[j]):
                items_start = j
                item_indent = re.match(r"^(\s+)-", lines[j]).group(1)  # type: ignore[union-attr]
                entries: List[str] = []
                k = j
                while k < end and re.match(r"^\s+-\s", lines[k]):
                    entries.append(lines[k].split("-", 1)[1].strip().strip("\"'"))
                    k += 1
                versions = entry_versions(entries)
    problem = refusal(current, versions, key, file)
    if problem and not force:
        return None, problem, 1
    note = order_note(versions, key)

    entry = changelog_line(new_version, summary, by)
    entry_line = f"{item_indent}- {json.dumps(entry)}"

    # Apply edits from the bottom up so indexes stay valid.
    lines[ver_idx] = f"{indent}{key}: {_quote(new_version, raw_value)}" + (f"  {comment}" if comment else "")
    if cl_idx is None:
        # Append after the last non-blank line of the block.
        last = end - 1
        while last > start and lines[last].strip() == "":
            last -= 1
        lines[last + 1:last + 1] = [f"{indent}changelog:", entry_line]
        end += 2
    elif inline_items is not None:
        body = [f"{indent}changelog:", entry_line] + [f"{item_indent}- {json.dumps(x)}" for x in inline_items]
        lines[cl_idx:cl_idx + 1] = body
        end += len(body) - 1
    elif items_start is not None:
        lines[items_start:items_start] = [entry_line]
        end += 1
    else:   # `changelog:` with nothing under it, or `changelog: []`
        lines[cl_idx] = f"{indent}changelog:"
        lines[cl_idx + 1:cl_idx + 1] = [entry_line]
        end += 1
    for i in range(start, end):
        lm = LAST_UPDATED_RE.match(lines[i])
        if lm:
            lines[i] = f"{lm.group(1)}last_updated: {_quote(_now(), lm.group(2))}" + (f"  {lm.group(3)}" if lm.group(3) else "")
            break

    new_text = nl.join(lines)
    try:
        loaded = yaml.safe_load(new_text)
    except yaml.YAMLError as e:
        return None, f"[FAIL] {file}: the edit would leave the YAML unreadable ({e}); nothing written.", 2
    meta = loaded.get("metadata") if isinstance(loaded, dict) else None
    if not isinstance(meta, dict) or str(meta.get(key)) != new_version or not meta.get("changelog"):
        return None, f"[FAIL] {file}: the edit did not land where expected; nothing written.", 2
    msg = f"{key} {'.'.join(map(str, current))} -> {new_version}; changelog line added: {entry}"
    if problem:
        msg += "  (forced over a changelog with no line for the current version)"
    if note:
        msg += f"\n       {note}"
    return new_text, msg, 0


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------

def bump_json(text: str, summary: str, by: Optional[str], patch: bool, force: bool,
              file: str) -> Tuple[Optional[str], str, int]:
    nl = "\r\n" if "\r\n" in text else "\n"
    try:
        doc = json.loads(text)
    except ValueError as e:
        return None, f"[FAIL] {file}: not valid JSON ({e}).", 2
    meta = doc.get("metadata") if isinstance(doc, dict) else None
    if not isinstance(meta, dict):
        return None, f"[FAIL] {file}: no `metadata` object - nothing to bump.", 2
    key = next((k for k in meta if str(k).endswith("_version")), None)
    if key is None:
        return None, f"[FAIL] {file}: metadata carries no `<name>_version` key - nothing to bump.", 2
    current = parse_version(str(meta[key]))
    if current is None:
        return None, f"[FAIL] {file}: metadata.{key} is {meta[key]!r}, not a dotted version - cannot bump.", 2
    new_version = bump_version(current, patch)
    changelog = meta.get("changelog")
    if changelog is None:
        changelog = []
    if not isinstance(changelog, list):
        return None, f"[FAIL] {file}: metadata.changelog is not a list - cannot prepend.", 2
    versions = entry_versions([str(x) for x in changelog])
    problem = refusal(current, versions, key, file)
    if problem and not force:
        return None, problem, 1
    note = order_note(versions, key)
    entry = changelog_line(new_version, summary, by)
    meta[key] = new_version
    meta["changelog"] = [entry] + [str(x) for x in changelog]
    if "last_updated" in meta:
        meta["last_updated"] = _now()
    out = json.dumps(doc, indent=2, ensure_ascii=False)
    if text.endswith(("\n", "\r\n")):
        out += "\n"
    out = out.replace("\n", nl) if nl != "\n" else out
    msg = f"{key} {'.'.join(map(str, current))} -> {new_version}; changelog line added: {entry}"
    if problem:
        msg += "  (forced over a changelog with no line for the current version)"
    if note:
        msg += f"\n       {note}"
    return out, msg, 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description="Bump an artifact's metadata version and prepend its changelog line.")
    ap.add_argument("--file", required=True, help="docs/<ARTIFACT>.yaml or .json")
    ap.add_argument("--summary", required=True, help="One line: what changed and why.")
    ap.add_argument("--by", default=None, help="Who made the change (e.g. sdlc-repair); appended to the line.")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument("--minor", action="store_true", help="1.3 -> 1.4 (default).")
    grp.add_argument("--patch", action="store_true", help="1.3 -> 1.3.1")
    ap.add_argument("--force", action="store_true",
                    help="Bump even when the on-disk version is above the newest changelog line.")
    ap.add_argument("--dry-run", action="store_true", help="Report what would change; write nothing.")
    args = ap.parse_args(argv)

    path = Path(args.file)
    if not path.is_file():
        print(f"[FAIL] cannot read {path}: file not found", file=sys.stderr)
        return 2
    if not args.summary.strip():
        print("[FAIL] --summary must not be empty - a changelog line with no summary records nothing.",
              file=sys.stderr)
        return 2
    try:
        # Bytes, not read_text(): universal newlines would hide a CRLF file,
        # and the edit must hand back exactly the line endings it found.
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[FAIL] cannot read {path}: {e}", file=sys.stderr)
        return 2

    label = path.as_posix()
    fn = bump_json if path.suffix.lower() == ".json" else bump_yaml
    new_text, msg, code = fn(text, args.summary, args.by, args.patch, args.force, label)
    if code != 0 or new_text is None:
        print(msg, file=sys.stderr)
        return code
    if args.dry_run:
        print(f"[DRY-RUN] {label}: {msg}")
        return 0
    try:
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
    except OSError as e:
        print(f"[FAIL] cannot write {path}: {e}", file=sys.stderr)
        return 2
    print(f"[OK] {label}: {msg}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
