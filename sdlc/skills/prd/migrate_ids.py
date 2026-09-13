"""Migrate a PRD.yaml to the v1.1 ID-prefix convention.

What this script does
---------------------
- Renames legacy `F-NNN: ...` items in `features` (or the legacy
  `must_have_features` / `nice_to_have_features`) to `FR-NNN: ...`
  (preserving the original number).
- Adds `<PREFIX>-NNN: ` prefixes to every list[string] field that now
  carries IDs. Sibling lists (the flat `features` list plus the legacy
  must-have + nice-to-have it replaced, primary + secondary,
  performance_targets + other, primary_jobs + secondary_jobs) share one
  continuous counter per family per scope.
- Items already prefixed correctly are kept as-is; their numbers count
  toward the family's max so newly assigned IDs do not collide.
- Idempotent: running on an already-migrated file produces no changes.

Comments and quoting
--------------------
This script uses `ruamel.yaml` in round-trip mode, so YAML comments,
key ordering, and the original quoting style of unchanged strings are
preserved. New or renamed items are written with double-quoted scalars
to match the convention used throughout `PRD.yaml`.

Family map (prefix -> sibling list fields, in order)::

    FR  - functional_requirements.features
          (legacy: .must_have_features, .nice_to_have_features; also migrates F-NNN)
    OOS - functional_requirements.out_of_scope
    INT - functional_requirements.integrations_required
    AIF - functional_requirements.ai_features
    NFR - non_functional_requirements.performance_targets, .other
    WRN - prd_warnings (top level; same counter across single/monorepo)
    PER - users_personas.primary_users, .secondary_users
    GOL - users_personas.user_goals
    PAN - users_personas.user_frustrations
    WKF - use_cases.core_workflows
    JTB - use_cases.primary_jobs_to_be_done, .secondary_jobs
    EDG - use_cases.edge_cases
    ENT - data_model.key_entities
    ACR - success_metrics.acceptance_criteria
    QUE - open_questions.undecided_decisions, .parking_lot — migrated to
          TYPED mappings {id: QUE-NNN, question, status}, not prefixed
          strings; plain bullets get the next shared QUE id with
          status: open (undecided) / deferred (parking_lot).

In monorepo mode, each `products.<slug>` carries an independent ID space
per family (counters reset per product). `WRN` always lives at the root
regardless of mode.

Usage
-----
Run from the project root::

    python sdlc/skills/prd/migrate_ids.py
    python sdlc/skills/prd/migrate_ids.py --path other/PRD.yaml
    python sdlc/skills/prd/migrate_ids.py --dry-run

Exit codes::

    0 - migration written (or already up to date / dry-run completed)
    2 - could not read or parse the file
    3 - required dependency missing (ruamel.yaml)
"""

from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path
from typing import Any, List, Optional, Tuple

try:
    from ruamel.yaml import YAML
    from ruamel.yaml.comments import CommentedMap
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString
except ImportError:
    print(
        "ERROR: ruamel.yaml is required.\nInstall with:  pip install 'ruamel.yaml>=0.18'",
        file=sys.stderr,
    )
    sys.exit(3)


# (prefix, sibling-paths-in-canonical-order, scope)
# scope = "top"     -> field lives at PRD root in both modes (only WRN).
# scope = "product" -> field lives in product-scoped theme; in monorepo
#                      mode it sits under products.<slug>.<theme>.<field>.
FAMILIES: List[Tuple[str, List[str], str]] = [
    ("WRN", ["prd_warnings"], "top"),
    ("PER", ["users_personas.primary_users", "users_personas.secondary_users"], "product"),
    ("GOL", ["users_personas.user_goals"], "product"),
    ("PAN", ["users_personas.user_frustrations"], "product"),
    ("WKF", ["use_cases.core_workflows"], "product"),
    ("JTB", ["use_cases.primary_jobs_to_be_done", "use_cases.secondary_jobs"], "product"),
    ("EDG", ["use_cases.edge_cases"], "product"),
    (
        "FR",
        [
            # D2: flat list first; legacy split still migrated for old PRDs.
            "functional_requirements.features",
            "functional_requirements.must_have_features",
            "functional_requirements.nice_to_have_features",
        ],
        "product",
    ),
    ("OOS", ["functional_requirements.out_of_scope"], "product"),
    ("INT", ["functional_requirements.integrations_required"], "product"),
    ("AIF", ["functional_requirements.ai_features"], "product"),
    (
        "NFR",
        [
            "non_functional_requirements.performance_targets",
            "non_functional_requirements.other",
        ],
        "product",
    ),
    ("ENT", ["data_model.key_entities"], "product"),
    ("ACR", ["success_metrics.acceptance_criteria"], "product"),
]

# QUE is migrated separately (see _migrate_open_questions): its items become
# typed mappings {id, question, status}, not "QUE-NNN: <text>" strings. The
# two open_questions lists share one QUE counter per scope.
_QUE_PATHS: List[Tuple[str, str]] = [
    # (dotted path, retrofit status for legacy plain-string bullets)
    ("open_questions.undecided_decisions", "open"),
    ("open_questions.parking_lot", "deferred"),
]


def _make_yaml() -> YAML:
    """Build a round-trip YAML instance that preserves comments + quoting."""
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    # Match the conventional 2-space mapping indent and 4-space sequence
    # indent (with `-` at offset 2) used throughout PRD.yaml fixtures.
    yaml.indent(mapping=2, sequence=4, offset=2)
    # Avoid line-wrapping long feature strings.
    yaml.width = 4096
    yaml.allow_unicode = True
    return yaml


def _get_parent_and_key(d: Any, path: str) -> Tuple[Optional[Any], Optional[str]]:
    """Walk a dotted path to its leaf parent mapping + final key.

    Returns (parent, key) only if every intermediate node exists and is
    a mapping; otherwise (None, None). We don't create new theme blocks
    during migration — we only touch what's already there.
    """
    parts = path.split(".")
    cur: Any = d
    for part in parts[:-1]:
        if not hasattr(cur, "get"):
            return None, None
        cur = cur.get(part)
        if cur is None:
            return None, None
    if not hasattr(cur, "get"):
        return None, None
    return cur, parts[-1]


def _migrate_list(
    parent: Any,
    key: str,
    prefix: str,
    counter: int,
    changes: List[str],
    path_label: str,
) -> int:
    """Migrate a single list[str] in place.

    Returns the updated counter (max of original counter and any IDs
    encountered/assigned). Appends one human-readable line to `changes`
    for each item that was modified. New / renamed items are written as
    DoubleQuotedScalarString; unchanged items keep their original scalar
    type (and thus their original quote style).
    """
    items = parent.get(key)
    if items is None:
        return counter
    if not isinstance(items, list):
        return counter

    correct_rx = re.compile(rf"^{re.escape(prefix)}-(\d{{3,}}): (.+)", re.DOTALL)
    legacy_f_rx = re.compile(r"^F-(\d{3,}): (.+)", re.DOTALL) if prefix == "FR" else None

    for idx in range(len(items)):
        item = items[idx]
        if not isinstance(item, str):
            continue

        m = correct_rx.match(item)
        if m:
            # Already correctly prefixed — leave the scalar object alone so
            # ruamel preserves its quote style and any inline comment.
            counter = max(counter, int(m.group(1)))
            continue

        if legacy_f_rx is not None:
            m = legacy_f_rx.match(item)
            if m:
                n = int(m.group(1))
                counter = max(counter, n)
                items[idx] = DoubleQuotedScalarString(f"FR-{n:03d}: {m.group(2)}")
                changes.append(f"  {path_label}[{idx}]: rename  'F-{n:03d}'  ->  'FR-{n:03d}'")
                continue

        counter += 1
        new_value = f"{prefix}-{counter:03d}: {item}"
        items[idx] = DoubleQuotedScalarString(new_value)
        truncated = item if len(item) <= 60 else item[:57] + "..."
        changes.append(
            f"  {path_label}[{idx}]: prefix  '{prefix}-{counter:03d}: '  ({truncated!r})"
        )

    return counter


def _migrate_family(
    data: Any, prefix: str, paths: List[str], scope: str, changes: List[str]
) -> None:
    """Migrate one family across all its sibling paths and product scopes."""
    metadata = data.get("metadata") if hasattr(data, "get") else None
    is_monorepo = bool(metadata.get("monorepo", False)) if metadata is not None else False
    products = data.get("products") if is_monorepo else None

    if scope == "top":
        counter = 0
        for path in paths:
            parent, key = _get_parent_and_key(data, path)
            if parent is not None and key is not None:
                counter = _migrate_list(parent, key, prefix, counter, changes, path)
        return

    # scope == "product"
    if is_monorepo and products is not None and hasattr(products, "items"):
        for slug, product_data in products.items():
            if product_data is None or not hasattr(product_data, "get"):
                continue
            counter = 0
            for path in paths:
                parent, key = _get_parent_and_key(product_data, path)
                if parent is not None and key is not None:
                    counter = _migrate_list(
                        parent, key, prefix, counter, changes, f"products.{slug}.{path}"
                    )
    else:
        counter = 0
        for path in paths:
            parent, key = _get_parent_and_key(data, path)
            if parent is not None and key is not None:
                counter = _migrate_list(parent, key, prefix, counter, changes, path)


_QUE_ID_RE = re.compile(r"^QUE-(\d{3,})$")


def _migrate_open_questions_scope(root: Any, scope_label: str, changes: List[str]) -> None:
    """Convert legacy plain-string open_questions bullets into typed
    {id, question, status} mappings, sharing one QUE counter across both
    lists in this scope. Existing typed entries keep their ids (and feed
    the counter). Idempotent."""
    # First pass: existing typed ids feed the counter.
    counter = 0
    lists: List[Tuple[Any, str, str, str]] = []  # (parent, key, path, retrofit_status)
    for path, retrofit_status in _QUE_PATHS:
        parent, key = _get_parent_and_key(root, path)
        if parent is None or key is None:
            continue
        items = parent.get(key)
        if not isinstance(items, list):
            continue
        lists.append((items, key, f"{scope_label}{path}", retrofit_status))
        for item in items:
            if hasattr(item, "get"):
                m = _QUE_ID_RE.match(str(item.get("id") or "").strip())
                if m:
                    counter = max(counter, int(m.group(1)))

    # Second pass: retrofit plain strings.
    for items, _key, path_label, retrofit_status in lists:
        for idx in range(len(items)):
            item = items[idx]
            if not isinstance(item, str):
                continue
            counter += 1
            entry = CommentedMap()
            entry["id"] = DoubleQuotedScalarString(f"QUE-{counter:03d}")
            entry["question"] = DoubleQuotedScalarString(item)
            entry["status"] = retrofit_status
            items[idx] = entry
            truncated = item if len(item) <= 60 else item[:57] + "..."
            changes.append(
                f"  {path_label}[{idx}]: typed  'QUE-{counter:03d}' "
                f"(status: {retrofit_status})  ({truncated!r})"
            )


def _migrate_open_questions(data: Any, changes: List[str]) -> None:
    metadata = data.get("metadata") if hasattr(data, "get") else None
    is_monorepo = bool(metadata.get("monorepo", False)) if metadata is not None else False
    if is_monorepo:
        products = data.get("products")
        if products is not None and hasattr(products, "items"):
            for slug, product_data in products.items():
                if product_data is not None and hasattr(product_data, "get"):
                    _migrate_open_questions_scope(product_data, f"products.{slug}.", changes)
    else:
        _migrate_open_questions_scope(data, "", changes)


def migrate(data: Any) -> Tuple[Any, List[str]]:
    """Run all family migrations on `data` in place. Returns (data, change-log)."""
    changes: List[str] = []
    for prefix, paths, scope in FAMILIES:
        _migrate_family(data, prefix, paths, scope, changes)
    _migrate_open_questions(data, changes)
    return data, changes


def _load_yaml(yaml: YAML, path: Path) -> Optional[Any]:
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.load(fh)
    except Exception as e:  # ruamel raises various exceptions on bad YAML
        print(f"ERROR: YAML parse error in {path}:\n  {e}", file=sys.stderr)
        return None
    if raw is None:
        print(f"ERROR: {path} is empty", file=sys.stderr)
        return None
    if not hasattr(raw, "get"):
        print(
            f"ERROR: {path} top level must be a mapping, got {type(raw).__name__}",
            file=sys.stderr,
        )
        return None
    return raw


def _dump_yaml(yaml: YAML, data: Any) -> str:
    buf = io.StringIO()
    yaml.dump(data, buf)
    return buf.getvalue()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migrate a PRD.yaml to the v1.1 ID-prefix convention."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs", "PRD.yaml"),
        help="Path to PRD.yaml (default: ./docs/PRD.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the change-log and proposed YAML without writing.",
    )
    args = parser.parse_args(argv)

    path: Path = args.path
    yaml = _make_yaml()
    data = _load_yaml(yaml, path)
    if data is None:
        return 2

    _, changes = migrate(data)

    if not changes:
        print(f"[OK] {path} already conforms to the v1.1 ID convention. No changes.")
        return 0

    print(f"[MIGRATE] {len(changes)} change(s) in {path}:")
    for line in changes:
        print(line)

    if args.dry_run:
        print("\n--- proposed YAML (dry-run; not written) ---")
        print(_dump_yaml(yaml, data))
        print("--- end ---")
        print("\nRe-run without --dry-run to apply.")
        return 0

    backup = path.with_suffix(path.suffix + ".pre-id-migration.bak")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(_dump_yaml(yaml, data), encoding="utf-8")
    print(f"\n[WROTE] {path}")
    print(f"[BACKUP] original saved to {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
