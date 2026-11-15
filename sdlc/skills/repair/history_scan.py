#!/usr/bin/env python3
"""Change history inside the text of docs/ artifacts - the one scanner.

A contract field states today's behaviour only. A version tag, an FND id or a
"Through vN" narrative inside it reaches every code worker verbatim (task embeds
copy the text), describes behaviour that no longer holds, and moves a built
task's fingerprint when it is edited. History has two homes: `metadata.changelog`
(bump_artifact.py) and a `<field>_rationale` sibling for a why-sentence.

This scanner walks every string of every artifact OUTSIDE those homes - one
generic leaf walk, no per-family field table, so a task embed that copies a
contract field is covered too - and names, per field, the owner and the matched
tokens. It never prints the field text: an output line that quoted prose could
be mistaken for a finding's evidence.

THE PINNED GRAMMAR. `HISTORY_PATTERN` below is the one definition. arch's
cross-check 33 carries the identical string (held equal by
_smoke/contract_history_selftest.py and _smoke/history_scan_selftest.py). It is
deliberately narrow: no bare `vN.NN` (it would flag "OpenAPI v3.1"), no
project-private forms. Change it only to remove a measured false positive or
negative, and change every copy in the same edit.

Used two ways:
  * imported by doctor.py, which hands it the documents it already loaded
    (`scan_document`) so `--provenance` adds no second parse of the corpus;
  * run directly: lists the stock, counts it, or gates on it.

Usage:
    python history_scan.py [--docs-dir docs]             # list every field, exit 0
    python history_scan.py [--docs-dir docs] --census    # counts per family, document, field
    python history_scan.py [--docs-dir docs] --check     # list, exit 1 while any remains

Exit codes:
    0 - scan ran (with --check: nothing carries change history).
    1 - --check only: at least one field carries change history.
    2 - the docs directory could not be read.
    3 - required dependency missing (pyyaml).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    print("[history_scan] missing dependency: pyyaml (pip install pyyaml)", file=sys.stderr)
    sys.exit(3)

# One pattern, the union of five forms (each `<ART>` is an artifact name with an
# optional `__slug`):
#   1. an FND id                                  FND-410
#   2. a parenthesised version tag                (v1.304,   (UX v3.4)
#   3. an artifact-qualified version              DATA-MODEL v2.39
#   4. a lead-in + version                        Through v1.75, As of v2.0,
#      and, without the `v`, three lead-ins       Through 1.242
#   5. a version + change verb                    v1.33 adds
# Written as ONE raw literal on ONE line: arch's validator and both selftests
# match it character for character.
HISTORY_PATTERN = r"\bFND-\d+\b|\((?:(?:ARCH|DATA-MODEL|TEST-STRATEGY|TASKS|PRD|UX|API|DESIGN)(?:__[a-z0-9-]+)?\s+)?v\d+\.\d+\s*[,)]|\b(?:ARCH|DATA-MODEL|TEST-STRATEGY|TASKS|PRD|UX|API|DESIGN)(?:__[a-z0-9-]+)?\s+v\d+\.\d+\b|\b(?:Through|Until|Since|From|After|As of)\s+v\d+\.\d+\b|\b(?:Through|Until|Since)\s+\d+\.\d{2,3}\b|\bv\d+\.\d+\s+(?:adds|added|removes|removed|retires|retired|renames|renamed|changes|changed|introduces|introduced)\b"
HISTORY_RE = re.compile(HISTORY_PATTERN)
_QUICK = re.compile(r"FND-|v\d|(?:Through|Until|Since)\s+\d")  # a superset of what HISTORY_PATTERN needs

# The sanctioned homes of history, at any depth: the metadata block (which holds
# the changelog and the provenance), a bare changelog, deferrals, every
# `*_warnings` list, open questions, retired ids and accepted warnings.
EXCLUDED_KEY = re.compile(
    r"^(metadata|changelog|deferrals|provenance|generated_by|retired_ids|open_questions"
    r"|accepted_warnings|.*_warnings)$"
)

# A docs/ file this scanner reads: a canonical artifact or one of its shards.
ARTIFACT_FILE = re.compile(
    r"^(ARCH|DATA-MODEL|TEST-STRATEGY|TASKS|PRD|UX|API|DESIGN)(__[a-z0-9-]+)?\.(yaml|json)$"
)

# Dict keys that name the item a leaf belongs to, most specific first.
OWNER_KEYS = ("tsk_id", "tst_id", "component_id", "surface_id", "id", "name")
# A mapping keyed by item name: the key itself names the item.
KEYED_COLLECTIONS = ("entities", "enums", "fields")

_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def family_of(name: str) -> Optional[str]:
    m = ARTIFACT_FILE.match(name)
    return m.group(1) if m else None


def tokens_in(text: str) -> List[str]:
    """The distinct matched tokens of one string, in order of appearance."""
    seen: List[str] = []
    for m in HISTORY_RE.finditer(text):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    return seen


def _leaves(node: Any, path: List[Any], out: List[Tuple[Tuple[Any, ...], List[str]]]) -> None:
    """Append (path, tokens) for every string leaf with a token outside the
    excluded homes. READ-ONLY: nothing here assigns into `node`; `path` is the
    one shared stack of keys and indexes, copied only when a leaf matches."""
    if isinstance(node, str):
        # Every form of the grammar contains "FND-", a "v<digit>" or a lead-in
        # followed by a digit; that one cheap test keeps the full union off
        # the long prose that has none of them.
        if _QUICK.search(node) and HISTORY_RE.search(node):
            out.append((tuple(path), tokens_in(node)))
    elif isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, (str, dict, list)):
                skey = key if isinstance(key, str) else str(key)
                if EXCLUDED_KEY.match(skey):
                    continue
                path.append(skey)
                _leaves(value, path, out)
                path.pop()
    elif isinstance(node, list):
        for i, value in enumerate(node):
            if isinstance(value, (str, dict, list)):
                path.append(i)
                _leaves(value, path, out)
                path.pop()


def owner_of(doc: Any, path: Tuple[Any, ...]) -> str:
    """A readable owner for a leaf: the ids of the items it sits under, outermost
    first ('tasks-service/create_task'); the first path key when none has one."""
    labels: List[str] = []
    node = doc
    for i, step in enumerate(path):
        node = node[step]
        if i >= 1 and path[i - 1] in KEYED_COLLECTIONS and isinstance(node, dict):
            labels.append(str(step))
        elif isinstance(node, dict) and i >= 1:
            for key in OWNER_KEYS:
                if isinstance(node.get(key), str) and node[key].strip():
                    labels.append(node[key].strip())
                    break
    if labels:
        return "/".join(labels)
    if isinstance(doc, dict):
        for key in ("id", "container_id"):
            if isinstance(doc.get(key), str):
                return doc[key]
    return str(path[0]) if path else "?"


def field_of(path: Tuple[Any, ...]) -> str:
    """The generalised field path: list indexes collapse to `[]`, the item names
    under entities / enums / fields to `*`."""
    parts: List[str] = []
    for i, step in enumerate(path):
        if isinstance(step, int):
            if parts:
                parts[-1] += "[]"
        elif i >= 1 and path[i - 1] in KEYED_COLLECTIONS:
            parts.append("*")
        else:
            parts.append(step)
    return ".".join(parts)


def scan_document(name: str, doc: Any) -> List[Dict[str, Any]]:
    """One record per field of `doc` carrying change history:
    {file, family, owner, field, tokens}. Never the field text."""
    fam = family_of(name)
    if fam is None or not isinstance(doc, (dict, list)):
        return []
    found: List[Tuple[Tuple[Any, ...], List[str]]] = []
    _leaves(doc, [], found)
    return [{"file": name, "family": fam, "owner": owner_of(doc, p), "field": field_of(p), "tokens": toks}
            for p, toks in found]


def parse_file(path: Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
        raw = json.loads(text) if path.suffix == ".json" else yaml.load(text, Loader=_YAML_LOADER)
    except (OSError, ValueError, yaml.YAMLError):
        return None
    return raw if isinstance(raw, (dict, list)) else None


def scan_docs(docs: Path, load: Callable[[Path], Any] = parse_file) -> List[Dict[str, Any]]:
    """Every record over a docs directory. `load(path)` returns the parsed
    document (or None); doctor passes its cached loader."""
    out: List[Dict[str, Any]] = []
    for path in sorted(docs.iterdir()):
        if path.is_file() and ARTIFACT_FILE.match(path.name):
            out += scan_document(path.name, load(path))
    return out


def describe(rec: Dict[str, Any], tokens_cap: int = 4) -> str:
    toks = rec["tokens"]
    more = f" | (+{len(toks) - tokens_cap} more)" if len(toks) > tokens_cap else ""
    return f"{rec['file']}: {rec['owner']} {rec['field']}: {' | '.join(toks[:tokens_cap])}{more}"


def summarise(records: List[Dict[str, Any]], sample: int = 20) -> Dict[str, Any]:
    """The machine-readable shape doctor reports under --provenance."""
    by_doc = Counter(r["file"] for r in records)
    return {
        "fields": len(records),
        "documents": dict(sorted(by_doc.items())),
        "sample": [describe(r) for r in records[:sample]],
    }


def census(records: List[Dict[str, Any]]) -> List[str]:
    lines: List[str] = []
    by_fam = Counter(r["family"] for r in records)
    lines.append(f"[history-scan] {len(records)} field(s) carry change history, by artifact family:")
    for fam, n in sorted(by_fam.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {n:6d}  {fam}")
    lines.append("by document:")
    for doc, n in sorted(Counter(r["file"] for r in records).items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {n:6d}  {doc}")
    lines.append("by field:")
    by_field = Counter(f"{r['family']}: {r['field']}" for r in records)
    for key, n in sorted(by_field.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {n:6d}  {key}")
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass
    ap = argparse.ArgumentParser(
        description="Name the fields of docs/ artifacts that carry change history (owner and token, never the text).")
    ap.add_argument("--docs-dir", default="docs", help="Directory holding the artifacts (default: docs).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--census", action="store_true", help="Counts per family, document and field instead of the list.")
    mode.add_argument("--check", action="store_true", help="List the fields and exit 1 while any remains.")
    args = ap.parse_args(argv)

    docs = Path(args.docs_dir)
    if not docs.is_dir():
        print(f"[history-scan] docs dir not found: {docs}", file=sys.stderr)
        return 2
    records = scan_docs(docs)
    if args.census:
        print("\n".join(census(records)))
        return 0
    for rec in records:
        print(describe(rec))
    if records:
        print(f"[history-scan] {len(records)} field(s) in {len({r['file'] for r in records})} "
              f"document(s) carry change history - a contract field states today's behaviour only; "
              f"clear the stock with one repair finding (references/forward-propagation.md, 'History sweep').")
    else:
        print("[history-scan] OK: no field carries change history.")
    return 1 if (args.check and records) else 0


if __name__ == "__main__":
    sys.exit(main())
