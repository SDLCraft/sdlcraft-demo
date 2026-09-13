#!/usr/bin/env python3
"""Navigation-index generator for the large SDLC artifacts under ``docs/``.

``docs/PRD.yaml``, ``docs/DATA-MODEL.yaml`` and ``docs/TASKS.json`` grow large
enough that a downstream agent loading them whole burns a big slice of its
context window. This script produces ``docs/INDEX.yaml`` — a pure *location map*
(file + line range + a short summary per addressable symbol) that lets an agent
``Read`` only the lines it needs, plus a ``shards:`` inventory naming every
``docs/*__*`` sub-artifact so agents can discover per-surface/container/resource
files without reading each parent's inventory block. The index duplicates no
field bodies, so it cannot drift in content; only line ranges move, and the
``Write|Edit|MultiEdit`` PostToolUse hook (installed by the ``sdlc:setup`` skill)
keeps those current. Beyond the location map it also emits a cross-reference
graph (``referenced_by`` + ``dangling``) so an agent can look up a symbol's edit
blast-radius and gate on id integrity (``--check``). The retrieval protocol
agents follow lives in ``.claude/rules/sdlc-docs-access.md``.

This file is dropped into a consumer project at ``.claude/sdlc/docs_index.py`` by
``sdlc:setup``. It is **stdlib-only by design**: a line-based scanner over the
regular 2-space-indented YAML — and pretty-printed JSON (``TASKS.json``,
``CODE-MANIFEST.json``) — the SDLC skills emit. No YAML parser is imported, so
the script has zero runtime dependencies and runs under any Python 3.8+ without an
environment to set up.

Usage
-----
    python docs_index.py                     # regenerate docs/INDEX.yaml
    python docs_index.py --docs-dir path     # ... for a non-default docs dir
    python docs_index.py --hook              # PostToolUse mode: regen iff the
                                             #   edited file (read from stdin JSON)
                                             #   is a canonical doc or a shard;
                                             #   else no-op
    python docs_index.py --show <symbol>     # print one symbol's [start,end] slice
                                             #   (entity / enum / convention name,
                                             #   any FR/NFR/WKF/SCR/USR/ENT/... id,
                                             #   TST-NNN, OPR-NNN, AST-NNN, a
                                             #   component id, a work unit
                                             #   <cid>/<component>/<unit> or its
                                             #   bare name when unique, a task
                                             #   TSK-NNN / <cid>/TSK-NNN)
    python docs_index.py --refs <symbol>     # print a symbol's edit blast-radius
    python docs_index.py --check             # exit non-zero on any dangling ref
    python docs_index.py --find kind=... ... # predicate search over symbols
    python docs_index.py --hash <file>       # the 16-hex content hash that
                                             #   generated_from and every
                                             #   upstream_provenance entry record
    python docs_index.py --drift <artifact>  # compare an artifact's recorded
                                             #   upstream_provenance with the
                                             #   upstreams' current hashes and
                                             #   diff what moved (exit 1 on drift)
    python docs_index.py --stale [--json]    # every artifact whose recorded
                                             #   upstreams moved, in the order to
                                             #   reconcile them, each with its
                                             #   owning skill's --reconcile command
                                             #   (exit 1 when any is stale)
    python docs_index.py --items <upstream>  # every item the upstream defines
                                             #   with its body hash (what --stamp
                                             #   records; --json for a mapping)
    python docs_index.py --stamp <artifact> [--upstream <file> ...]
                                             # rewrite the artifact's
                                             #   metadata.upstream_provenance:
                                             #   sha256 + per-item hashes of every
                                             #   upstream it consumes, so a later
                                             #   --drift diffs item by item. Writes
                                             #   ONLY that artifact, never the index

Project root is resolved from ``--project-root``, then ``$CLAUDE_PROJECT_DIR``,
then the current working directory. ``docs/`` is taken relative to that root
unless ``--docs-dir`` is given explicitly.

Exit codes
----------
    0 — done (index written | no dangling reference | no drift | symbol printed
        | artifact stamped).
    1 — the gate failed (--check: a dangling reference in a blocking family;
        --drift: an upstream changed; --stale: at least one artifact is stale;
        --show/--refs: unknown symbol; --stamp: an upstream the artifact
        records no longer exists, or it names none).
    2 — could not read a required file or directory.
    3 — never (stdlib only; kept for parity with the other SDLC scripts).

A reference is STRUCTURED or it is not a reference
--------------------------------------------------
An id counts as referenced only where it is the whole value of a field, a list
entry, or an element of a flow list/mapping (``covers: [FR-001]``,
``- FR-001``, ``"implements": ["FR-001"]``, ``{id: FR-031, reason: ...}``).
An id inside prose - a description that illustrates the id format
(``'Operation inventory (OPR-001...)'``), an example locator
(``operations[OPR-014]``), example ids in help text, a warning that mentions
one - is a mention: it still feeds ``referenced_by`` when it resolves (the
blast radius stays wide), but it is never dangling, so a spec that documents
its own conventions cannot fail the gate (ledger IMP-072, aicf LSN-050).

Per-item provenance (``--items`` / ``--stamp`` / exact ``--drift``)
--------------------------------------------------------------------
A file hash says THAT an upstream moved, never which items. ``--stamp`` records,
next to each upstream's ``sha256``, an ``items:`` map of every symbol that
upstream defines (work units, components, tests, entities, requirement items,
tasks, ...) to a short body hash; ``--drift`` then names exactly what was
added, removed and modified, without git and without guessing from what the
artifact happens to reference. A work unit's hash ignores its declaration-only
fields (``touches_entities``, ``status``), so an entity-trace backfill is not
"modified" - only behaviour-bearing fields are (ledger IMP-073/IMP-064, aicf
LSN-051/052/053). Without ``items`` (a stamp written by hand or by an older
version) ``--drift`` first looks through the upstream's recent git history for
a committed revision whose text hash equals the recorded ``sha256`` - every
recorded hash is a text hash a blob can match - and on a hit diffs against that
revision item by item, labelled "recovered from git" (ledger IMP-083, aicf
LSN-065: a 7-unit delta had printed as a 51-unit residue). Only a miss - an
uncommitted stamp matches no revision - falls back to the artifact's own
references as the old snapshot, subtracts its structured deferrals, and says
plainly that the residue mixes "new upstream" with "never covered".

``--stamp`` also records each upstream's ``metadata.<name>_version``, so
``--drift`` can print WHY an upstream moved: its changelog lines newer than the
recorded version (a stamp that recorded no version falls back to lines dated on
or after its ``last_updated``). A cold-started reconcile then reads the reason
for the change from disk - ``bump_artifact.py --summary`` and every skill's own
changelog line - instead of needing the session that made it.

The content hash (``--hash``, ``generated_from``, ``upstream_provenance``)
------------------------------------------------------------------------
``sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()[:16]``.
Text-level on purpose: ``read_text`` normalises line endings, so a CRLF checkout
and an LF checkout of the same file hash the same. Every skill that records a
provenance hash reads it from ``INDEX.yaml`` or calls ``--hash`` — never a raw
``sha256(bytes)`` of its own, which differs on CRLF.

Capability version: 5 (``--stale``: every stale artifact in the order to
reconcile it, with its owning skill's ``--reconcile`` command; ``--stamp``
records each upstream's version and ``--drift`` prints the changelog lines
since). Version 4 added per-item provenance (``--items``, ``--stamp``, an exact
``--drift``), made a prose mention not a reference, and typed QUE. Version 3
indexes every ``docs/*__*`` shard — ARCH__ components + work units,
TEST-STRATEGY tests, API__ operations, DESIGN__assets assets, TASKS__ tasks —
records shards in ``generated_from``, adds field-anchored named-symbol edges
(entities, work units, components, tasks), the TST/OPR/AST families
(warn-first), file-local WRN resolution, a durable retired-id channel
(``docs/INDEX.allow.yaml`` + PRD ``metadata.retired_ids``), a ``warnings:``
block, and the ``--hash`` / ``--drift`` subcommands. Version 2 added the
cross-reference graph and ``--refs`` / ``--check`` / ``--find``. Re-run
``/sdlc:setup`` to upgrade an installed copy.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from hashlib import sha256
from pathlib import Path
from typing import NamedTuple, Optional

CAPABILITY_VERSION = 5


# =============================================================================
# User-facing output (CLAUDE.md 14). Three verdict tags, two finding sections,
# one NEXT block - identical across every SDLC script, because the person
# reading them knows only "there is a pipeline and I run it in order".
# Canonical guidance: sdlc/skills/prd/references/reporting-to-the-user.md
# =============================================================================

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"


def join_ids(ids, limit=12):
    """Render a grouped finding's id list. Capped, because a line nobody
    finishes reading has told the user nothing."""
    ids = [str(i) for i in ids]
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown} (+{len(ids) - limit} more)"


def _emit_finding(item, detail_cap=5):
    """One blocking finding. A (headline, details) pair renders as a grouped
    finding: the class in one sentence, then a capped sample."""
    if isinstance(item, tuple):
        head, details = item
        print(f"  - {head}")
        for d in list(details)[:detail_cap]:
            print(f"      * {d}")
        if len(details) > detail_cap:
            print(f"      * (+{len(details) - detail_cap} more of the same)")
    else:
        print(f"  - {item}")


def _emit_warning(item, detail_cap=5):
    """One warning. Rendered with ``*`` bullets on purpose: the repair doctor
    files every ``- `` line of a failed check as a finding, and a warning is
    not a finding."""
    if isinstance(item, tuple):
        head, details = item
        print(f"  * {head}")
        for d in list(details)[:detail_cap]:
            print(f"      * {d}")
        if len(details) > detail_cap:
            print(f"      * (+{len(details) - detail_cap} more of the same)")
    else:
        print(f"  * {item}")


def print_findings(blocking, warnings, blocking_header="MUST FIX BEFORE 'complete'"):
    """The two canonical sections. A WARNING never blocks, and says so."""
    if blocking:
        print(f"\n{blocking_header} ({len(blocking)}):")
        for b in blocking:
            _emit_finding(b)
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}) - none of these block the next skill:")
        for w in warnings:
            _emit_warning(w)


def print_next(*lines, show_glossary=True):
    """Close with what to type next. The glossary pointer only appears when
    there was something to decode."""
    print(f"\nNEXT: {lines[0]}")
    for extra in lines[1:]:
        print(f"      {extra}")
    if show_glossary:
        print(f"      What these labels mean: {GLOSSARY_PATH}")


INDEX_FILENAME = "INDEX.yaml"
# Optional, hand-maintained: ``retired_ids: [{id, reason}]`` — ids a changelog
# still cites after their retirement. Never generated.
ALLOW_FILENAME = "INDEX.allow.yaml"

# Canonical SDLC docs the index covers, in priority order — this drives the
# deterministic ordering of the emitted index. Any *other* ``docs/*.yaml`` that
# is not a sub-artifact / snapshot (see ``_is_canonical``) is appended after
# these, alphabetically. Symbol extraction (see ``_EXTRACTORS``) only runs for
# the files that have an extractor; every covered file still gets ``sections``.
PRIORITY_FILES: tuple[str, ...] = (
    "PRD.yaml",
    "UX.yaml",
    "DESIGN.yaml",
    "DATA-MODEL.yaml",
    "API.yaml",
    "ARCH.yaml",
    "TEST-STRATEGY.yaml",
    "TASKS.json",
    "CODE-MANIFEST.json",
    "DEPLOY.yaml",  # planned — no producing skill yet
)

# Canonical docs that are JSON, not YAML. Their shards (``TASKS__<cid>.json``)
# are scanned like every other shard and listed in the ``shards:`` inventory.
_JSON_CANONICALS: frozenset = frozenset({"TASKS.json", "CODE-MANIFEST.json"})

_SUMMARY_LIMIT = 120

# The sha256 in ``generated_from`` is a change-detector, not a security digest,
# so a 16-hex (64-bit) prefix is plenty to spot a stale index and keeps the
# index lean.
_SHA_LEN = 16

# A mapping-key line: leading spaces, then an unquoted simple key, then a colon.
# List items (``- ...``) never match — ``-`` is not a valid first key character —
# so nested keys inside list items are correctly ignored.
_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][\w./-]*):(?:\s|$)")
# A ``- key: value`` list-item opener; the key sits at logical indent +2.
_ITEM_KEY_RE = re.compile(r"^(?P<indent>\s*)-\s+(?P<key>[A-Za-z_][\w./-]*):(?:\s|$)(?P<val>.*)$")

# A functional-requirement list item: ``- "FR-001: ...`` (quote optional). The
# opening quote is captured so a matching trailing quote can be trimmed off the
# summary of a short, single-sentence quoted FR.
_FR_ITEM_RE = re.compile(r'^\s*-\s*(?P<q>["\']?)(?P<id>FR-\d+):\s*(?P<rest>.*)')

# ---------------------------------------------------------------------------
# Cross-reference (edge) vocabulary — the id-integrity half of the index.
# ---------------------------------------------------------------------------
#
# ID families *defined* somewhere in the SDLC docs — the only prefixes the
# dangling-reference check resolves. Every other XX-### token (CMP/CFG/... or
# external standards like ISO-8601) is a forward/illustrative reference, NOT a
# corpus symbol: mentions of those are ignored and never flagged dangling.
_CORPUS_PREFIXES: "tuple[str, ...]" = (
    "FR", "NFR", "ENT", "INT", "AIF", "PER", "GOL", "PAN",
    "WKF", "JTB", "EDG", "OOS", "SCR", "ACR", "WRN",
    "USR",  # PRD 1.1 user stories — typed ``- id: USR-001`` items, like SCR
)
# Families added in capability version 3. Warn-first for one version: a
# dangling reference in one of these prints under WARNINGS and does not flip
# the --check exit code. TST ids may carry a container prefix (TST-CLI-001).
#
# QUE joined them in capability version 4 (ledger IMP-028): PRD open questions
# are typed ``- id: QUE-001`` items across BOTH ``undecided_decisions`` and
# ``parking_lot``, downstream stages gate on them, and the statusboard lists
# them - but a PRD written before the family was typed carries them as plain
# strings, so every mention elsewhere would suddenly be dangling. Warn-first
# keeps ``--check`` green on those projects while ``--show QUE-009`` starts
# resolving, which is what the installed rules already promise (CLAUDE.md 10).
_WARN_FIRST_PREFIXES: "tuple[str, ...]" = ("TST", "OPR", "AST", "QUE")
_ALL_PREFIXES = _CORPUS_PREFIXES + _WARN_FIRST_PREFIXES
_TST_ID = r"TST-(?:[A-Z][A-Z0-9]*-)?\d+"
_ID_PATTERN = (
    r"(?:(?:" + "|".join(p for p in _ALL_PREFIXES if p != "TST") + r")-\d+|" + _TST_ID + r")"
)

# A reference token: an uppercase corpus-prefix id (``FR-083``). Case-sensitive
# on purpose — ids are uppercase, so prose like "per-stage" or "integration"
# never matches "PER-"/"INT-".
_REF_RE = re.compile(r"\b" + _ID_PATTERN + r"\b")
_ID_ONLY_RE = re.compile(r"^" + _ID_PATTERN + r"$")


def _structured_ref(line: str, start: int, end: int) -> bool:
    """True when the id at ``line[start:end]`` sits in a STRUCTURED position -
    the whole value of a field, a list entry, or an element of a flow list /
    mapping - and False when it is a mention inside prose.

    Structured: what precedes the token (past one adjacent quote) is a field
    key's colon, a list dash, a list/mapping opener that itself follows a key
    or another element, or a comma; what follows is a comma, a closer, a
    comment or the end of the line; and the token is not inside a longer
    quoted string (an odd number of quotes before it). Prose fails one of the
    three - ``'Operation inventory (OPR-001...)'``, ``operations[OPR-014]``,
    ``"... 'TST-042', 'QUE-003' ..."`` inside a description - and a prose
    mention is never a reference (ledger IMP-072, aicf LSN-050).
    """
    before_raw = line[:start]
    after = line[end:]
    if after[:1] in ('"', "'"):
        after = after[1:]
    after = after.lstrip()
    if not (after == "" or after[0] in ",]}" or after.startswith("#")):
        return False
    before = before_raw
    if before[-1:] in ('"', "'"):
        before = before[:-1]
    if before.count('"') % 2 == 1 or before.count("'") % 2 == 1:
        return False  # inside a longer quoted string: prose
    before = before.rstrip()
    if before == "":
        return True  # a bare element line (a JSON array element, a flow-list continuation)
    last = before[-1]
    if last == ",":
        return True
    if last == ":":
        return True
    if last == "-":
        return len(before) == 1 or before[-2].isspace()  # a list dash, not a hyphenated word
    if last in "[{":
        opener_before = before[:-1].rstrip()
        # a flow list is structured only when the bracket itself follows a key,
        # a dash or another element - `operations[OPR-014]` in prose does not
        return opener_before == "" or opener_before[-1] in ":,-[{"
    return False

# Families whose ids are scoped to the file that defines them: ``WRN-001`` in
# PRD.yaml and ``WRN-001`` in ARCH__x.yaml are different warnings. A mention
# resolves only against the same file's definitions; a cross-file mention is
# neither an edge nor dangling.
_FILE_LOCAL_PREFIXES: frozenset = frozenset({"WRN"})

# Corpus ids intentionally referenced without a definition — a number RESERVED
# or RETIRED and kept in a changelog for an honest audit trail. The durable
# channel is ``docs/INDEX.allow.yaml`` (``retired_ids: [{id, reason}]``) or the
# PRD's ``metadata.retired_ids``; this code default stays empty.
_ALLOWLISTED_IDS: "frozenset[str]" = frozenset()

# Definition anchors (line-start), one per shape:
#  - PRD list families + every file's warnings: ``- "FR-001: ...``  /  ``- "WRN-006: ...``
#  - typed inventory items:                       ``- id: SCR-001`` (UX), ``- id: USR-001``
#                                                 (PRD), ``- id: OPR-001`` (API__),
#                                                 ``- id: AST-001`` (DESIGN__assets)
#  - test cases:                                  ``- tst_id: TST-001`` / ``TST-CLI-001``
_DEF_LISTITEM_RE = re.compile(
    r'^\s*-\s*"?(?P<id>(?:' + "|".join(_CORPUS_PREFIXES) + r")-\d+):"
)
_DEF_TYPED_RE = re.compile(r'^\s*-\s*id:\s*"?(?P<id>(?:SCR|USR|OPR|AST|QUE)-\d+)"?(?:\s|$)')
_DEF_TST_RE = re.compile(r'^\s*-\s*tst_id:\s*"?(?P<id>' + _TST_ID + r')"?(?:\s|$)')
_DEF_PATTERNS = (_DEF_LISTITEM_RE, _DEF_TYPED_RE, _DEF_TST_RE)
# A retired-id entry: ``- id: FR-058`` / ``- FR-058`` / ``- {id: FR-058, reason: ...}``.
# Anchored so a ``reason:`` that names another id never retires it too.
_RETIRED_ITEM_RE = re.compile(r'^\s*-\s*(?:\{\s*)?(?:id:\s*)?"?(?P<id>' + _ID_PATTERN + r')"?')

# The PRD's other single-namespace id list items (NFR/WKF/INT/AIF/OOS/PER/…),
# defined as ``- "NFR-004: …"`` — the same anchored shape ``_scan_definitions``
# resolves — surfaced as addressable symbols so ``--show NFR-010`` resolves an
# id the dangling-checker already understands. FR is handled by ``_extract_frs``.
# USR is excluded too: its items are typed mappings, not ``- "USR-001: …"`` strings.
_SYMBOL_ITEM_PREFIXES = tuple(p for p in _CORPUS_PREFIXES if p not in ("FR", "WRN", "USR"))
_SYMBOL_ITEM_RE = re.compile(
    r'^\s*-\s*"?(?P<id>(?:' + "|".join(_SYMBOL_ITEM_PREFIXES) + r")-\d+):\s*(?P<rest>.*)")
_SYMBOL_ITEM_KINDS = {
    "NFR": "non_functional_requirement", "ENT": "entity_ref", "INT": "integration",
    "AIF": "ai_feature", "PER": "persona", "GOL": "user_goal", "PAN": "user_frustration",
    "WKF": "workflow", "JTB": "job_to_be_done", "EDG": "edge_case", "OOS": "out_of_scope",
    "SCR": "surface", "ACR": "acceptance_criterion",
}
# Typed ``- id: <PREFIX>-NNN`` inventories: kind, and the child keys that make
# the one-line summary (first present wins).
_TYPED_KINDS = {
    "SCR": ("surface", ("name", "purpose")),
    "USR": ("user_story", ("story",)),
    "OPR": ("operation", ("summary", "operation_id")),
    "AST": ("asset", ("name", "description")),
    "QUE": ("open_question", ("question",)),
}

# ---------------------------------------------------------------------------
# Field-anchored named-symbol references (capability version 3).
# ---------------------------------------------------------------------------
#
# Entities, work units, components and tasks are addressed by NAME, not by an
# id family, so a bare-word scan would drown in prose. A named reference is
# therefore matched ONLY as the value of one of these keys, and resolved
# against the symbols the index itself defines. Kinds: entity (DATA-MODEL
# ``entities.<Name>`` or an enum), unit (ARCH__ ``work_units[].name``,
# qualified ``<cid>/<component>/<unit>``), component (ARCH__
# ``components[].component_id``), task (``TSK-NNN`` / ``<cid>/TSK-NNN``).
_NAMED_KEYS_YAML = {
    "traces_data_entities": "entity", "touches_entities": "entity", "via_entity": "entity",
    "primary_entity": "entity", "to_entity": "entity", "from_entity": "entity",
    "entity": "entity",
    "via_unit": "unit", "targets_work_units": "unit", "targets_work_unit": "unit",
    "component_ref": "component",
}
_NAMED_KEYS_JSON = {
    "touches_entities": "entity", "entity": "entity",
    "target_symbol": "unit", "component_ref": "component", "depends_on": "task",
}
_YAML_ANCHOR_RE = re.compile(
    r"(?:^\s*(?:-\s+)?|[{,]\s*)(?P<key>"
    + "|".join(sorted(_NAMED_KEYS_YAML, key=len, reverse=True))
    + r"):(?=\s|$)"
)
_JSON_ANCHOR_RE = re.compile(
    r'"(?P<key>' + "|".join(_NAMED_KEYS_JSON) + r')"\s*:\s*(?P<rest>.*)$'
)
_JSON_STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
# What a name may look like once unquoted; prose, paths with spaces, nulls and
# id tokens (handled by the id scan) are never named references.
_NAME_TOKEN_RE = re.compile(r"^[A-Za-z_][\w.\-/]*$")
_YAML_NULLS = frozenset({"", "~", "null", "none", "true", "false", "[]", "{}"})
_NAMED_KIND_LABEL = {
    "entity": "entity", "unit": "work unit", "component": "component", "task": "task",
}


class SymbolSlice(NamedTuple):
    """Location of a single addressable symbol within an SDLC doc."""

    file: str
    path: str
    start: int  # 1-based, inclusive
    end: int  # 1-based, inclusive
    kind: str
    context: Optional[str]
    summary: str
    name: Optional[str] = None  # explicit lookup key (else derived from ``path``)


class Reference(NamedTuple):
    """One mention of a corpus id or named symbol, attributed to its container."""

    id: str
    file: str
    line: int  # 1-based
    container: str
    blocking: bool = True  # False: warn-first family or a named reference
    key: str = ""  # the anchoring field for a named reference


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------


def _is_canonical(name: str) -> bool:
    """True for a top-level SDLC doc the index should section and symbol-index.

    Excludes the index itself and its allow-list, per-surface/container/resource
    sub-artifacts (``UX__login.yaml``, ``ARCH__backend.yaml``,
    ``TASKS__backend.json`` — they carry ``__`` and are scanned as shards),
    draft scratch files, and version-suffixed snapshots (``PRDv1.3.yaml``).
    JSON canonicals are whitelisted by exact name (``_JSON_CANONICALS``).
    """
    if name in (INDEX_FILENAME, ALLOW_FILENAME):
        return False
    if not (name.endswith(".yaml") or name in _JSON_CANONICALS):
        return False
    if "__" in name or "_draft" in name.lower():
        return False
    # A version-suffixed snapshot like ``PRDv1.3.yaml`` / ``PRD-v2.yaml``.
    if re.search(r"v\d", name) and name not in PRIORITY_FILES:
        return False
    return True


def _is_shard(name: str) -> bool:
    """True for a ``<PARENT>__<slug>`` sub-artifact (YAML or JSON).

    Shards are scanned for definitions and references (un-sectioned in the
    emitted index), listed in the ``shards:`` inventory, and an edit to one
    refreshes the index.
    """
    if "__" not in name or "_draft" in name.lower():
        return False
    return name.endswith(".yaml") or name.endswith(".json")


def _shard_parent(name: str) -> str:
    """The canonical file a shard belongs to (``UX__x.yaml`` → ``UX.yaml``)."""
    stem = name.split("__", 1)[0]
    return stem + (".json" if name.endswith(".json") else ".yaml")


def _shard_slug(name: str) -> str:
    """The slug of a shard (``ARCH__build-sandbox.yaml`` → ``build-sandbox``)."""
    return name.split("__", 1)[1].rsplit(".", 1)[0]


def _discover_files(docs_dir: Path) -> list[str]:
    """Return canonical doc filenames present in ``docs_dir``, in index order."""
    candidates = list(docs_dir.glob("*.yaml")) + list(docs_dir.glob("*.json"))
    present = {p.name for p in candidates if _is_canonical(p.name)}
    ordered = [f for f in PRIORITY_FILES if f in present]
    ordered += sorted(present - set(ordered))
    return ordered


def _discover_shards(docs_dir: Path) -> "dict[str, list[str]]":
    """Map each parent canonical filename to its sorted shard filenames."""
    shards: dict[str, list[str]] = {}
    candidates = list(docs_dir.glob("*__*.yaml")) + list(docs_dir.glob("*__*.json"))
    for p in candidates:
        if _is_shard(p.name):
            shards.setdefault(_shard_parent(p.name), []).append(p.name)
    return {parent: sorted(names) for parent, names in sorted(shards.items())}


def content_hash(path: Path) -> str:
    """The canonical 16-hex content hash (see the module docstring)."""
    return sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()[:_SHA_LEN]


# ---------------------------------------------------------------------------
# Low-level line scanning
# ---------------------------------------------------------------------------


def _indent(line: str) -> int:
    """Return the count of leading spaces on a line."""
    return len(line) - len(line.lstrip(" "))


def _is_boundary(line: str) -> bool:
    """A non-blank, non-comment line can close an enclosing block."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _block_end(lines: list[str], start_idx: int, indent: int, limit: int) -> int:
    """Return the 0-based index of the last content line of a block.

    The block opened at ``start_idx`` (a key or list-item line at ``indent``)
    extends through every following line more deeply indented than ``indent``,
    skipping blank and comment lines, and closes at the first content line whose
    indent is ``<= indent`` or at ``limit`` (exclusive). Trailing blank/comment
    lines are not included.
    """
    end = start_idx
    j = start_idx + 1
    while j < limit:
        line = lines[j]
        if not _is_boundary(line):
            j += 1
            continue
        if _indent(line) <= indent:
            break
        end = j
        j += 1
    return end


def _top_level_sections(lines: list[str]) -> "dict[str, tuple[int, int]]":
    """Map every top-level (indent-0) key to its 1-based inclusive line range."""
    sections: dict[str, tuple[int, int]] = {}
    n = len(lines)
    for i, line in enumerate(lines):
        match = _KEY_RE.match(line)
        if match is None or match.group("indent"):
            continue
        end = _block_end(lines, i, 0, n)
        sections[match.group("key")] = (i + 1, end + 1)
    return sections


def _child_keys(
    lines: list[str], parent_range: "tuple[int, int]", child_indent: int
) -> "list[tuple[str, int, int]]":
    """Find keys at exactly ``child_indent`` inside a parent's line range.

    ``parent_range`` is 1-based inclusive. Returns ``(key, start, end)`` triples
    with 1-based inclusive ranges, in source order.
    """
    start_1b, end_1b = parent_range
    limit = end_1b  # exclusive 0-based == inclusive 1-based end
    results: list[tuple[str, int, int]] = []
    for i in range(start_1b, end_1b):  # skip the parent key line itself
        line = lines[i]
        match = _KEY_RE.match(line)
        if match is None or len(match.group("indent")) != child_indent:
            continue
        block_end = _block_end(lines, i, child_indent, limit)
        results.append((match.group("key"), i + 1, block_end + 1))
    return results


def _list_items(
    lines: list[str], block_range: "tuple[int, int]", key: str
) -> "list[tuple[str, int, int, int]]":
    """``- <key>: <value>`` items of the list under ``block_range``.

    The item indent is taken from the first such line (the SDLC skills emit
    2-space nesting, but nothing here depends on it). Returns
    ``(value, start, end, item_indent)`` with 1-based inclusive ranges.
    """
    start_1b, end_1b = block_range
    pattern = re.compile(rf"^(?P<ind>\s*)-\s+{re.escape(key)}:\s*(?P<val>.*)$")
    out: list[tuple[str, int, int, int]] = []
    indent: Optional[int] = None
    for i in range(start_1b, end_1b):
        match = pattern.match(lines[i])
        if match is None:
            continue
        ind = len(match.group("ind"))
        if indent is None:
            indent = ind
        if ind != indent:
            continue
        end = _block_end(lines, i, indent, end_1b)
        value = _unquote(re.sub(r"\s+#.*$", "", match.group("val")))
        out.append((value, i + 1, end + 1, indent))
    return out


def _find_child_value(
    lines: list[str], block_range: "tuple[int, int]", child_indent: int, key: str
) -> Optional[str]:
    """Return the inline scalar value of ``key`` at ``child_indent`` in a block."""
    start_1b, end_1b = block_range
    pattern = re.compile(rf"^\s{{{child_indent}}}{re.escape(key)}:\s*(?P<val>.*)$")
    for i in range(start_1b, end_1b):
        match = pattern.match(lines[i])
        if match is not None:
            return match.group("val").strip()
    return None


def _named_range(children: "list[tuple[str, int, int]]", key: str) -> "Optional[tuple[int, int]]":
    """Return the (start, end) range of the named child from ``_child_keys``."""
    for name, start, end in children:
        if name == key:
            return (start, end)
    return None


def _top_scalar(lines: list[str], sections: "dict[str, tuple[int, int]]", key: str) -> Optional[str]:
    """The inline value of a top-level scalar key (``container_id: backend``)."""
    rng = sections.get(key)
    if rng is None:
        return None
    line = lines[rng[0] - 1]
    value = line.split(":", 1)[1] if ":" in line else ""
    value = re.sub(r"\s+#.*$", "", value).strip()
    return _unquote(value) if value else None


def _in_ranges(lineno: int, ranges: "list[tuple[int, int]]") -> bool:
    return any(start <= lineno <= end for start, end in ranges)


# ---------------------------------------------------------------------------
# Value cleaning / summarising
# ---------------------------------------------------------------------------


def _unquote(value: str) -> str:
    """Strip one layer of surrounding single/double quotes if present."""
    value = value.strip()
    if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
        return value[1:-1]
    return value


def _summarize(text: str, limit: int = _SUMMARY_LIMIT) -> str:
    """First sentence of ``text``, collapsed to one line and capped at ``limit``."""
    text = " ".join(_unquote(text).split())
    dot = text.find(". ")
    if 0 < dot < limit:
        return text[:dot]
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
# Per-doc symbol extractors
# ---------------------------------------------------------------------------


def _bounded_context_map(
    lines: list[str], sections: "dict[str, tuple[int, int]]"
) -> "dict[str, str]":
    """Reverse map entity name -> owning bounded_context family (best-effort)."""
    result: dict[str, str] = {}
    bc_range = sections.get("bounded_contexts")
    if bc_range is None:
        return result
    for family, fam_start, fam_end in _child_keys(lines, bc_range, 2):
        ent_val = _find_child_value(lines, (fam_start, fam_end), 4, "entities")
        if ent_val is None:
            continue
        names: list[str] = []
        if ent_val.startswith("["):
            buf = ent_val
            k = fam_start
            while "]" not in buf and k < fam_end:
                buf += " " + lines[k].strip()
                k += 1
            inner = buf[buf.find("[") + 1 : buf.rfind("]")] if "]" in buf else buf[1:]
            names = [p.strip() for p in inner.split(",") if p.strip()]
        else:
            for i in range(fam_start, fam_end):
                item = lines[i].strip()
                if item.startswith("- "):
                    names.append(item[2:].strip())
        for name in names:
            result.setdefault(name, family)
    return result


def _extract_entities(
    lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
) -> "list[SymbolSlice]":
    """Index every entity under the top-level ``entities:`` block."""
    ent_range = sections.get("entities")
    if ent_range is None:
        return []
    context_of = _bounded_context_map(lines, sections)
    out: list[SymbolSlice] = []
    for name, start, end in _child_keys(lines, ent_range, 2):
        category = _find_child_value(lines, (start, end), 4, "category") or "entity"
        description = _find_child_value(lines, (start, end), 4, "description")
        summary = _summarize(description) if description else ""
        out.append(
            SymbolSlice(
                file=filename,
                path=f"entities.{name}",
                start=start,
                end=end,
                kind=category.strip(),
                context=context_of.get(name),
                summary=summary,
                name=name,
            )
        )
    return out


def _extract_enums(
    lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
) -> "list[SymbolSlice]":
    """Index every named enum under ``enums_and_lookups.enums``."""
    root = sections.get("enums_and_lookups")
    if root is None:
        return []
    enums_range = _named_range(_child_keys(lines, root, 2), "enums")
    if enums_range is None:
        return []
    out: list[SymbolSlice] = []
    for name, start, end in _child_keys(lines, enums_range, 4):
        value = re.sub(r"\s+#.*$", "", lines[start - 1].split(":", 1)[1]).strip()
        if not value:
            members = [
                lines[i].strip()[2:].strip()
                for i in range(start, end)
                if lines[i].strip().startswith("- ")
            ]
            value = f"[{', '.join(members)}]" if members else ""
        out.append(
            SymbolSlice(
                file=filename,
                path=f"enums_and_lookups.enums.{name}",
                start=start,
                end=end,
                kind="enum",
                context=None,
                summary=_summarize(value) if value else "",
                name=name,
            )
        )
    return out


def _extract_frs(
    lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
) -> "list[SymbolSlice]":
    """Index FR-### list items under ``functional_requirements``."""
    fr_range = sections.get("functional_requirements")
    if fr_range is None:
        return []
    out: list[SymbolSlice] = []
    for sublist, sub_start, sub_end in _child_keys(lines, fr_range, 2):
        for i in range(sub_start, sub_end):
            match = _FR_ITEM_RE.match(lines[i])
            if match is None:
                continue
            item_end = _block_end(lines, i, _indent(lines[i]), sub_end)
            rest = match.group("rest").rstrip()
            quote = match.group("q")
            if quote and rest.endswith(quote):  # trim the matching closing quote
                rest = rest[:-1]
            out.append(
                SymbolSlice(
                    file=filename,
                    path=f"functional_requirements.{sublist}[{match.group('id')}]",
                    start=i + 1,
                    end=item_end + 1,
                    kind="functional_requirement",
                    context=sublist,
                    summary=_summarize(rest),
                    name=match.group("id"),
                )
            )
    return out


def _extract_convention_blocks(
    lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
) -> "list[SymbolSlice]":
    """Index each indent-2 sub-block of ``conventions`` as an addressable symbol.

    ``conventions`` is a long sequence of self-contained sub-blocks
    (``nfr_propagation``, ``artifact_ids``, ``stage_tool_inventory``, …).
    Surfacing each as a ``convention`` symbol lets ``--show nfr_propagation``
    resolve like any other symbol. ``context`` carries the block's
    ``owning_fr``; ``summary`` its ``description``/``purpose`` first sentence.
    ``_``-prefixed keys (navigational manifests) are skipped.
    """
    conv = sections.get("conventions")
    if conv is None:
        return []
    out: list[SymbolSlice] = []
    for name, start, end in _child_keys(lines, conv, 2):
        if name.startswith("_"):
            continue
        owning = _find_child_value(lines, (start, end), 4, "owning_fr")
        descr = _find_child_value(lines, (start, end), 4, "description") or _find_child_value(
            lines, (start, end), 4, "purpose"
        )
        out.append(
            SymbolSlice(
                file=filename,
                path=f"conventions.{name}",
                start=start,
                end=end,
                kind="convention",
                context=_unquote(owning) if owning else None,
                summary=_summarize(descr) if descr else "",
                name=name,
            )
        )
    return out


def _extract_prd_id_items(
    lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
) -> "list[SymbolSlice]":
    """Index the PRD's other single-namespace id list items (NFR/WKF/INT/AIF/…).

    These families are *defined* as ``- "NFR-004: …"`` list items — the same
    anchored shape :func:`_scan_definitions` resolves for the edge graph — and
    become addressable symbols so ``--show NFR-010`` / ``--show WKF-001``
    resolve. ``context`` is the narrowest enclosing mapping key
    (``core_workflows``, ``other``, …). FR items are handled by
    :func:`_extract_frs`.
    """
    containers: list[tuple[int, int, str]] = []
    path_of: dict[str, str] = {}
    for name, (start, end) in sections.items():
        containers.append((start, end, name))
        path_of[name] = name
        for child, c_start, c_end in _child_keys(lines, (start, end), 2):
            containers.append((c_start, c_end, child))
            path_of[child] = f"{name}.{child}"
    out: list[SymbolSlice] = []
    for i, line in enumerate(lines):
        match = _SYMBOL_ITEM_RE.match(line)
        if match is None:
            continue
        item_end = _block_end(lines, i, _indent(line), len(lines))
        container = _locate_container(containers, i + 1)
        parent_path = path_of.get(container or "", container) if container else filename
        out.append(
            SymbolSlice(
                file=filename,
                path=f"{parent_path}[{match.group('id')}]",
                start=i + 1,
                end=item_end + 1,
                kind=_SYMBOL_ITEM_KINDS.get(match.group("id").split("-", 1)[0], "id_item"),
                context=container,
                summary=_summarize(match.group("rest")),
                name=match.group("id"),
            )
        )
    return out


def _typed_extractor(prefix: str):
    """An extractor for ``- id: <prefix>-NNN`` inventory items (SCR/USR/OPR/AST).

    The symbol path is ``<enclosing top-level section>[<id>]``; ``summary`` is
    the first present key from ``_TYPED_KINDS``. The typed-mapping shape is the
    one :func:`_scan_definitions` resolves via ``_DEF_TYPED_RE``, so every such
    symbol is also a definition the edge graph knows.
    """
    kind, summary_keys = _TYPED_KINDS[prefix]

    def extract(
        lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
    ) -> "list[SymbolSlice]":
        containers = [(start, end, name) for name, (start, end) in sections.items()]
        out: list[SymbolSlice] = []
        for i, line in enumerate(lines):
            match = _DEF_TYPED_RE.match(line)
            if match is None or not match.group("id").startswith(prefix + "-"):
                continue
            item_end = _block_end(lines, i, _indent(line), len(lines))
            child_indent = _indent(line) + 2
            summary = ""
            for key in summary_keys:
                val = _find_child_value(lines, (i + 1, item_end + 1), child_indent, key)
                if val:
                    summary = _summarize(_unquote(val))
                    break
            section = _locate_container(containers, i + 1) or kind + "s"
            out.append(
                SymbolSlice(
                    file=filename,
                    path=f"{section}[{match.group('id')}]",
                    start=i + 1,
                    end=item_end + 1,
                    kind=kind,
                    context=None,
                    summary=summary,
                    name=match.group("id"),
                )
            )
        return out

    return extract


def _extract_arch_components(
    lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
) -> "list[SymbolSlice]":
    """Index an ARCH__<cid> shard's ``components[].component_id`` and their
    ``work_units[].name``.

    A component is keyed by its bare ``component_id`` (kind ``component``,
    context = the container id); a work unit by its **qualified** name
    ``<cid>/<component>/<unit>`` (kind ``work_unit``, context = the component)
    — the address sdlc-task/sdlc-code use — and additionally by its bare name
    when that name is unique across the corpus (an alias, resolved by
    ``--show`` / ``--refs``, never rendered).
    """
    cid = _top_scalar(lines, sections, "container_id") or (
        _shard_slug(filename) if "__" in filename else filename
    )
    comp_range = sections.get("components")
    if comp_range is None:
        return []
    out: list[SymbolSlice] = []
    for comp_id, c_start, c_end, c_indent in _list_items(lines, comp_range, "component_id"):
        kid = c_indent + 2
        purpose = _find_child_value(lines, (c_start, c_end), kid, "purpose")
        out.append(
            SymbolSlice(
                file=filename,
                path=f"components[{comp_id}]",
                start=c_start,
                end=c_end,
                kind="component",
                context=cid,
                summary=_summarize(purpose) if purpose else "",
                name=comp_id,
            )
        )
        wu_range = _named_range(_child_keys(lines, (c_start, c_end), kid), "work_units")
        if wu_range is None:
            continue
        for unit, u_start, u_end, u_indent in _list_items(lines, wu_range, "name"):
            summary = _find_child_value(lines, (u_start, u_end), u_indent + 2, "summary")
            out.append(
                SymbolSlice(
                    file=filename,
                    path=f"components[{comp_id}].work_units[{unit}]",
                    start=u_start,
                    end=u_end,
                    kind="work_unit",
                    context=comp_id,
                    summary=_summarize(summary) if summary else "",
                    name=f"{cid}/{comp_id}/{unit}",
                )
            )
    return out


def _extract_tests(
    lines: list[str], sections: "dict[str, tuple[int, int]]", filename: str
) -> "list[SymbolSlice]":
    """Index ``tests[].tst_id`` items of a TEST-STRATEGY file or shard.

    Keyed by the test id (``TST-001`` or the container-prefixed
    ``TST-CLI-001``); ``context`` is the test's ``component_ref`` (else its
    tier); ``summary`` its name.
    """
    tests_range = sections.get("tests")
    if tests_range is None:
        return []
    out: list[SymbolSlice] = []
    for tst_id, s, e, ind in _list_items(lines, tests_range, "tst_id"):
        kid = ind + 2
        name = _find_child_value(lines, (s, e), kid, "name")
        comp = _find_child_value(lines, (s, e), kid, "component_ref")
        tier = _find_child_value(lines, (s, e), kid, "tier")
        context = _unquote(comp) if comp else (_unquote(tier) if tier else None)
        out.append(
            SymbolSlice(
                file=filename,
                path=f"tests[{tst_id}]",
                start=s,
                end=e,
                kind="test",
                context=context or None,
                summary=_summarize(name) if name else "",
                name=tst_id,
            )
        )
    return out


# Which extractors run for which file, keyed by the base (canonical) filename.
# Canonical files and shards can differ: ARCH.yaml (system) has no symbols of
# its own, while every ARCH__<cid>.yaml shard defines components + work units.
_EXTRACTORS = {
    "DATA-MODEL.yaml": (_extract_entities, _extract_enums),
    "PRD.yaml": (
        _extract_frs,
        _extract_prd_id_items,
        _typed_extractor("USR"),
        _typed_extractor("QUE"),
        _extract_convention_blocks,
    ),
    "UX.yaml": (_typed_extractor("SCR"),),
    "API.yaml": (_typed_extractor("OPR"),),
    "DESIGN.yaml": (_typed_extractor("AST"),),
    "TEST-STRATEGY.yaml": (_extract_tests,),
}
_SHARD_EXTRACTORS = {
    "ARCH.yaml": (_extract_arch_components,),
    "TEST-STRATEGY.yaml": (_extract_tests,),
    "API.yaml": (_typed_extractor("OPR"),),
    "DESIGN.yaml": (_typed_extractor("AST"),),
}


# ---------------------------------------------------------------------------
# JSON canonicals (TASKS.json, CODE-MANIFEST.json) and TASKS__ shards
# ---------------------------------------------------------------------------

# A task's stable id inside a pretty-printed task object. The SDLC task artifacts
# key this field ``tsk_id`` (TASKS.json + every TASKS__<cid>.json); it is the
# project-wide standard — do not look for a legacy ``task_id`` key.
_TSK_LINE_RE = re.compile(r'"tsk_id"\s*:\s*"(?P<id>[A-Z]+-\d+)"')
# A top-level JSON key line: ``  "key": ...`` (checked only at root depth).
_JSON_KEY_RE = re.compile(r'^\s*"(?P<key>[^"]+)"\s*:')
# A one-line title/name/summary member, used for the symbol summary.
_JSON_TITLE_RE = re.compile(r'"(?:title|name|summary)"\s*:\s*"(?P<val>[^"]*)"')


def _scan_json(lines: "list[str]") -> "tuple[dict[str, tuple[int, int]], list[SymbolSlice]]":
    """Line-range map for a pretty-printed JSON canonical (stdlib, no parse).

    Returns top-level-key sections plus one symbol per ``"tsk_id"`` object.
    Assumes the machine-written ``json.dump(indent=…)`` shape the skills emit:
    strings never span lines, and a task object's ``{`` opens on or before the
    line carrying its ``tsk_id`` member. Compact single-line objects are not
    symbol-indexed (their enclosing section still is). Best-effort by design —
    a malformed file yields empty results, never an exception.
    """
    sections: "dict[str, tuple[int, int]]" = {}
    symbols: "list[SymbolSlice]" = []
    stack: "list[dict]" = []  # frames: {"ch": "{"|"[", "line": int, "tid": str|None}
    current_key: "Optional[tuple[str, int]]" = None  # (key, start_line)

    def close_section(end_line: int) -> None:
        nonlocal current_key
        if current_key is not None:
            sections[current_key[0]] = (current_key[1], max(current_key[1], end_line))
            current_key = None

    for i, line in enumerate(lines, start=1):
        if len(stack) == 1 and stack[0]["ch"] == "{":
            key_match = _JSON_KEY_RE.match(line)
            if key_match is not None:
                close_section(i - 1)
                current_key = (key_match.group("key"), i)
        in_str = esc = False
        for ch in line:
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append({"ch": ch, "line": i, "tid": None})
            elif ch in "}]":
                if not stack:
                    return {}, []  # malformed — bail out empty
                frame = stack.pop()
                if frame["ch"] == "{" and frame["tid"]:
                    summary = ""
                    for j in range(frame["line"] - 1, i):
                        title = _JSON_TITLE_RE.search(lines[j])
                        if title is not None:
                            summary = _summarize(title.group("val"))
                            break
                    symbols.append(
                        SymbolSlice(
                            file="",  # filled by the caller
                            path=f"tasks[{frame['tid']}]",
                            start=frame["line"],
                            end=i,
                            kind="task",
                            context=None,
                            summary=summary,
                        )
                    )
                if not stack:
                    close_section(i - 1)
        tsk_match = _TSK_LINE_RE.search(line)
        if tsk_match is not None:
            for frame in reversed(stack):
                if frame["ch"] == "{":
                    if frame["tid"] is None:
                        frame["tid"] = tsk_match.group("id")
                    break
    close_section(len(lines))
    symbols.sort(key=lambda s: s.start)
    return sections, symbols


# ---------------------------------------------------------------------------
# Changelog + retired-id channels
# ---------------------------------------------------------------------------


def _changelog_ranges(
    lines: "list[str]", sections: "dict[str, tuple[int, int]]", is_json: bool
) -> "list[tuple[int, int]]":
    """The 1-based line range(s) of ``metadata.changelog`` — the ONE block the
    reference scan skips. A changelog legitimately cites ids that no longer
    exist (an honest audit trail of a retirement); ``*_warnings`` lists are
    never skipped, because a deferral note is a legitimate inbound site.
    """
    meta = sections.get("metadata")
    if meta is None:
        return []
    if not is_json:
        rng = _named_range(_child_keys(lines, meta, 2), "changelog")
        return [rng] if rng else []
    start, end = meta
    for i in range(start - 1, end):
        if re.match(r'^\s*"changelog"\s*:', lines[i]):
            if "[" in lines[i] and "]" not in lines[i]:
                j = i + 1
                while j < end and not lines[j].strip().startswith("]"):
                    j += 1
                return [(i + 1, j + 1)]
            return [(i + 1, i + 1)]
    return []


def _retired_in(lines: "list[str]", rng: "tuple[int, int]") -> "set[str]":
    """Ids listed under a ``retired_ids:`` block (flow or block form)."""
    start, end = rng
    found: set[str] = set()
    head = lines[start - 1].split(":", 1)[1] if ":" in lines[start - 1] else ""
    if head.strip().startswith("["):
        found.update(_REF_RE.findall(head))
    for i in range(start, end):
        match = _RETIRED_ITEM_RE.match(lines[i])
        if match is not None:
            found.add(match.group("id"))
    return found


def _load_retired_ids(
    docs_dir: Path,
    prd_lines: "Optional[list[str]]",
    prd_sections: "dict[str, tuple[int, int]]",
    warnings: "list[str]",
) -> "set[str]":
    """The durable retired-id channel: ``docs/INDEX.allow.yaml`` (``retired_ids:
    [{id, reason}]``) merged with the PRD's ``metadata.retired_ids`` and the
    (empty) code default. A retired id cited somewhere is neither an edge nor
    dangling."""
    retired: set[str] = set(_ALLOWLISTED_IDS)
    allow = docs_dir / ALLOW_FILENAME
    if allow.is_file():
        try:
            a_lines = allow.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            warnings.append(f"{ALLOW_FILENAME} could not be read ({e}) - its retired ids are not applied")
            a_lines = []
        rng = _top_level_sections(a_lines).get("retired_ids")
        if rng is not None:
            retired |= _retired_in(a_lines, rng)
    if prd_lines is not None:
        meta = prd_sections.get("metadata")
        if meta is not None:
            rng = _named_range(_child_keys(prd_lines, meta, 2), "retired_ids")
            if rng is not None:
                retired |= _retired_in(prd_lines, rng)
    return retired


# ---------------------------------------------------------------------------
# Cross-reference graph (definitions, references, dangling)
# ---------------------------------------------------------------------------


def _id_sort_key(symbol_id: str) -> "tuple[str, int, str]":
    """Natural sort: ``FR-83`` -> ('FR', 83, ''); names sort as plain strings."""
    match = re.match(r"^([A-Za-z]+)[-_](\d+)$", symbol_id)
    if match is not None:
        return (match.group(1), int(match.group(2)), "")
    return (symbol_id, 0, symbol_id)


def _scan_definitions(
    lines: "list[str]", skip: "list[tuple[int, int]]"
) -> "dict[str, int]":
    """Map every corpus id *defined* in this file to its 1-based line number.

    A definition is matched by an anchored line shape (list item ``- "FR-001:``,
    typed ``- id: SCR-001`` / ``USR`` / ``OPR`` / ``AST``, or ``- tst_id:
    TST-001``) — never an inline mention — so a body that merely cites an id is
    not mistaken for its source.
    """
    found: dict[str, int] = {}
    for i, line in enumerate(lines):
        if skip and _in_ranges(i + 1, skip):
            continue
        for pattern in _DEF_PATTERNS:
            match = pattern.match(line)
            if match is not None:
                found.setdefault(match.group("id"), i + 1)
                break
    return found


def _container_ranges(
    lines: "list[str]",
    file_sections: "dict[str, tuple[int, int]]",
    file_symbols: "list[SymbolSlice]",
    qualify: Optional[str] = None,
) -> "list[tuple[int, int, str]]":
    """Candidate containers for reference attribution (coarse to fine).

    Combines top-level sections, the indent-2 children of the large
    ``conventions`` section (so a hit resolves to ``artifact_ids`` rather than
    the whole ``conventions`` blob), and every extracted symbol. Section
    containers of a shard are rendered ``<file>:<section>`` (``qualify``);
    symbol containers stay unqualified — a symbol name is already unique.
    """
    prefix = f"{qualify}:" if qualify else ""
    ranges: list[tuple[int, int, str]] = [
        (start, end, prefix + name) for name, (start, end) in file_sections.items()
    ]
    conv = file_sections.get("conventions")
    if conv is not None:
        ranges.extend((start, end, prefix + name) for name, start, end in _child_keys(lines, conv, 2))
    ranges.extend((sym.start, sym.end, _symbol_name(sym)) for sym in file_symbols)
    return ranges


def _locate_container(ranges: "list[tuple[int, int, str]]", line: int) -> Optional[str]:
    """Return the narrowest container range covering ``line`` (1-based)."""
    best: Optional[str] = None
    best_width: Optional[int] = None
    for start, end, name in ranges:
        if start <= line <= end:
            width = end - start
            if best_width is None or width < best_width:
                best, best_width = name, width
    return best


def _line_owners(ranges: "list[tuple[int, int, str]]", n_lines: int) -> "list[Optional[str]]":
    """Per-line narrowest container, precomputed once per file.

    Ranges nest, so painting them widest-first leaves the narrowest on top;
    the cost is the sum of range widths (a few times the file length), not
    references x ranges.
    """
    owners: "list[Optional[str]]" = [None] * (n_lines + 2)
    for start, end, name in sorted(ranges, key=lambda r: -(r[1] - r[0])):
        for ln in range(max(start, 1), min(end, n_lines) + 1):
            owners[ln] = name
    return owners


# --- anchored (named) reference scanning -----------------------------------


def _parse_inline_values(rest: str) -> "list[str]":
    """Values of an anchored key from the text after its colon: a flow list
    ``[A, B]``, or one scalar cut at the next ``,`` / ``}`` / comment. Empty
    when a block sequence follows on the next lines (or the value is a map)."""
    rest = rest.lstrip()
    if rest.startswith("["):
        close = rest.find("]")
        inner = rest[1:close] if close >= 0 else rest[1:]
        return [_unquote(p.strip()) for p in inner.split(",") if p.strip()]
    if rest.startswith("{"):
        return []
    match = re.match(r"""^("(?:[^"\\]|\\.)*"|'(?:[^']|'')*'|[^,}\]#]*)""", rest)
    value = match.group(1).strip() if match else ""
    return [_unquote(value)] if value else []


def _block_seq_values(lines: "list[str]", i: int, key_indent: int) -> "list[str]":
    """Scalar items of the block sequence that follows an empty-valued key."""
    values: list[str] = []
    j = i + 1
    while j < len(lines):
        line = lines[j]
        if not _is_boundary(line):
            j += 1
            continue
        ind = _indent(line)
        stripped = line.strip()
        if ind < key_indent or (ind == key_indent and not stripped.startswith("- ")):
            break
        if stripped.startswith("- "):
            item = re.sub(r"\s+#.*$", "", stripped[2:]).strip()
            if item and not item.startswith(("{", "[")) and not _KEY_RE.match(item):
                values.append(_unquote(item))
        j += 1
    return values


def _logical_key(line: str) -> "Optional[tuple[int, str, str]]":
    """``(logical_indent, key, value_text)`` for a mapping line; a ``- key: v``
    list-item opener counts as indent +2 (where its sibling keys sit)."""
    match = _KEY_RE.match(line)
    if match is not None:
        return len(match.group("indent")), match.group("key"), line[match.end():]
    match = _ITEM_KEY_RE.match(line)
    if match is not None:
        return len(match.group("indent")) + 2, match.group("key"), match.group("val")
    return None


def _item_scalars(lines: "list[str]", lineno: int, k: int) -> "dict[str, str]":
    """Sibling scalar keys of the mapping that owns the key at ``lineno``
    (logical indent ``k``) — e.g. an edge's ``to`` next to its ``via_unit``."""

    def logical(line: str) -> "tuple[int, Optional[str], str]":
        lk = _logical_key(line)
        return lk if lk is not None else (_indent(line), None, "")

    i = lineno - 1
    top = i
    j = i - 1
    while j >= 0:
        line = lines[j]
        if not _is_boundary(line):
            j -= 1
            continue
        ind, _key, _val = logical(line)
        if ind < k:
            break
        if ind == k:
            top = j
            if line.lstrip().startswith("- "):
                break
        j -= 1
    out: dict[str, str] = {}
    m = top
    while m < len(lines):
        line = lines[m]
        if not _is_boundary(line):
            m += 1
            continue
        ind, key, val = logical(line)
        if ind < k:
            break
        if m != top and ind == k and line.lstrip().startswith("- "):
            break
        if ind == k and key:
            vals = _parse_inline_values(val)
            if len(vals) == 1:
                out.setdefault(key, vals[0])
        m += 1
    return out


def _anchored_refs_yaml(lines: "list[str]") -> "list[tuple[int, str, str, str, dict]]":
    """Every anchored named reference in a YAML file:
    ``(lineno, key, kind, value, context)``; ``context`` carries the sibling
    scalars a work-unit reference needs to qualify itself (``to`` /
    ``component_ref``), fetched lazily only for unit-kind references."""
    out: list[tuple[int, str, str, str, dict]] = []
    for i, line in enumerate(lines):
        if not _is_boundary(line):
            continue
        for match in _YAML_ANCHOR_RE.finditer(line):
            key = match.group("key")
            kind = _NAMED_KEYS_YAML[key]
            rest = line[match.end():]
            values = _parse_inline_values(rest)
            flow = match.group(0).lstrip().startswith(("{", ","))
            if not values and not flow and not rest.strip():
                lk = _logical_key(line)
                values = _block_seq_values(lines, i, lk[0] if lk else _indent(line))
            context: dict = {}
            if kind == "unit" and values:
                if flow:
                    for pm in re.finditer(r"(?:[{,]\s*)(to|component_ref|from):\s*([^,}]+)", line):
                        context[pm.group(1)] = _unquote(pm.group(2).strip())
                else:
                    lk = _logical_key(line)
                    if lk is not None:
                        context = _item_scalars(lines, i + 1, lk[0])
            for value in values:
                out.append((i + 1, key, kind, value, context))
    return out


def _anchored_refs_json(lines: "list[str]") -> "list[tuple[int, str, str, str, dict]]":
    """Every anchored named reference in a pretty-printed JSON file."""
    out: list[tuple[int, str, str, str, dict]] = []
    for i, line in enumerate(lines):
        match = _JSON_ANCHOR_RE.search(line)
        if match is None:
            continue
        key = match.group("key")
        rest = match.group("rest").strip()
        values: list[str] = []
        if rest.startswith('"'):
            sm = _JSON_STR_RE.match(rest)
            if sm is not None:
                values = [sm.group(1)]
        elif rest.startswith("["):
            if "]" in rest:
                values = _JSON_STR_RE.findall(rest[: rest.find("]")])
            else:
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith("]"):
                    values += _JSON_STR_RE.findall(lines[j].strip())
                    j += 1
        for value in values:
            out.append((i + 1, key, _NAMED_KEYS_JSON[key], value, {}))
    return out


def _json_scalar_in(lines: "list[str]", rng: "tuple[int, int]", key: str) -> Optional[str]:
    pattern = re.compile(rf'"{re.escape(key)}"\s*:\s*"([^"]*)"')
    for i in range(rng[0] - 1, rng[1]):
        match = pattern.search(lines[i])
        if match is not None:
            return match.group(1)
    return None


class _NamedDefs:
    """The name-addressed definitions the edge graph resolves against."""

    def __init__(self) -> None:
        self.entities: dict[str, str] = {}  # entity/enum name -> symbol name
        self.components: dict[str, set[str]] = {}  # component_id -> {cid}
        self.units: set[str] = set()  # qualified <cid>/<component>/<unit>
        self.units_bare: dict[str, list[str]] = {}
        self.tasks: set[str] = set()  # TSK-NNN (canonical) / <cid>/TSK-NNN

    def resolve(
        self, kind: str, value: str, cid: Optional[str], context: dict
    ) -> "tuple[Optional[str], list[str]]":
        """``(target symbol name | None, ambiguous candidates)``."""
        if kind == "entity":
            return (value if value in self.entities else None), []
        if kind == "component":
            return (value if value in self.components else None), []
        if kind == "task":
            if value.startswith("TASKS/"):
                target = value.split("/", 1)[1]
            elif "/" in value or not cid:
                target = value
            else:
                target = f"{cid}/{value}"
            return (target if target in self.tasks else None), []
        # kind == "unit"
        if value in self.units:
            return value, []
        comp = context.get("to") or context.get("component_ref")
        if cid and comp and f"{cid}/{comp}/{value}" in self.units:
            return f"{cid}/{comp}/{value}", []
        bare = self.units_bare.get(value, [])
        if not bare and "." in value:
            bare = self.units_bare.get(value.rsplit(".", 1)[-1], [])
        if len(bare) == 1:
            return bare[0], []
        if len(bare) > 1:
            same = [q for q in bare if cid and q.startswith(cid + "/")]
            if len(same) == 1:
                return same[0], []
            return None, bare
        return None, []


class EdgeGraph(NamedTuple):
    definitions: "dict[str, tuple[str, int]]"
    referenced_by: "dict[str, list[str]]"
    local_referenced_by: "dict[str, dict[str, list[str]]]"  # file -> WRN id -> containers
    references_out: "dict[str, list[str]]"
    refs_by_file: "dict[str, set[tuple[str, str]]]"  # file -> {(family, id|name)}
    dangling: "list[Reference]"
    dangling_warnings: "list[Reference]"


def _build_edges(
    lines_by_file: "dict[str, list[str]]",
    sections_by_file: "dict[str, dict[str, tuple[int, int]]]",
    named_symbols: "dict[str, SymbolSlice]",
    skip_by_file: "dict[str, list[tuple[int, int]]]",
    shard_files: "set[str]",
    retired: "set[str]",
    warnings: "list[str]",
) -> EdgeGraph:
    """Build the corpus reference graph from the scanned docs.

    Id-family references are scanned everywhere except ``metadata.changelog``;
    named references only inside anchored fields. ``definitions`` maps a
    defined id or symbol name -> ``(file, line)``; ``referenced_by`` a defined
    id/name -> the sorted containers that mention it; ``references_out`` a
    container -> the sorted ids/names it mentions; ``dangling`` the references
    in a blocking family that resolve to no definition; ``dangling_warnings``
    the warn-first ones (TST/OPR/AST/QUE families and every named reference).
    """
    definitions: dict[str, tuple[str, int]] = {}
    local_defs: dict[str, dict[str, int]] = {}
    for filename, lines in lines_by_file.items():
        for sym_id, lineno in _scan_definitions(lines, skip_by_file.get(filename, [])).items():
            if sym_id.split("-", 1)[0] in _FILE_LOCAL_PREFIXES:
                local_defs.setdefault(filename, {})[sym_id] = lineno
            else:
                definitions.setdefault(sym_id, (filename, lineno))

    defs = _NamedDefs()
    for name, sym in named_symbols.items():
        if sym.kind in ("component", "work_unit", "task") or (
            sym.file.startswith("DATA-MODEL") and sym.path.startswith(("entities.", "enums_and_lookups."))
        ):
            definitions.setdefault(name, (sym.file, sym.start))
        if sym.file.startswith("DATA-MODEL") and sym.path.startswith(("entities.", "enums_and_lookups.")):
            defs.entities[name] = name
        elif sym.kind == "component":
            defs.components.setdefault(name, set()).add(sym.context or "")
        elif sym.kind == "work_unit":
            defs.units.add(name)
            defs.units_bare.setdefault(name.rsplit("/", 1)[-1], []).append(name)
        elif sym.kind == "task":
            defs.tasks.add(name)

    referenced_by: dict[str, set[str]] = {}
    local_referenced_by: dict[str, dict[str, set[str]]] = {}
    references_out: dict[str, set[str]] = {}
    refs_by_file: dict[str, set[tuple[str, str]]] = {}
    dangling: list[Reference] = []
    dangling_warnings: list[Reference] = []
    ambiguous: list[str] = []

    for filename, lines in lines_by_file.items():
        is_shard = filename in shard_files
        file_syms = [s for s in named_symbols.values() if s.file == filename]
        ranges = _container_ranges(
            lines, sections_by_file.get(filename, {}), file_syms,
            qualify=filename if is_shard else None,
        )
        owners = _line_owners(ranges, len(lines))
        skip = skip_by_file.get(filename, [])
        my_local = local_defs.get(filename, {})
        file_refs = refs_by_file.setdefault(filename, set())
        cid = _shard_slug(filename) if is_shard else None

        def add_edge(target: str, container: str) -> None:
            referenced_by.setdefault(target, set()).add(container)
            references_out.setdefault(container, set()).add(target)

        for i, line in enumerate(lines):
            lineno = i + 1
            if skip and _in_ranges(lineno, skip):
                continue
            for match in _REF_RE.finditer(line):
                ref_id = match.group(0)
                prefix = ref_id.split("-", 1)[0]
                container = owners[lineno] or filename
                if prefix in _FILE_LOCAL_PREFIXES:
                    if ref_id in my_local and my_local[ref_id] != lineno and container != ref_id:
                        local_referenced_by.setdefault(filename, {}).setdefault(ref_id, set()).add(container)
                    continue  # a cross-file WRN mention is neither an edge nor dangling
                if definitions.get(ref_id) == (filename, lineno):
                    continue  # the token sitting on its own definition line
                if container == ref_id:
                    continue  # a symbol referencing itself
                if ref_id not in definitions and not _structured_ref(line, match.start(), match.end()):
                    continue  # a prose mention is not a reference: never dangling
                file_refs.add((prefix, ref_id))
                if ref_id in definitions:
                    add_edge(ref_id, container)
                elif ref_id in retired:
                    continue
                elif prefix in _WARN_FIRST_PREFIXES:
                    dangling_warnings.append(Reference(ref_id, filename, lineno, container, False))
                else:
                    dangling.append(Reference(ref_id, filename, lineno, container))

        anchored = _anchored_refs_json(lines) if filename.endswith(".json") else _anchored_refs_yaml(lines)
        for lineno, key, kind, value, context in anchored:
            if skip and _in_ranges(lineno, skip):
                continue
            if value.lower() in _YAML_NULLS or _ID_ONLY_RE.match(value) or not _NAME_TOKEN_RE.match(value):
                continue
            container = owners[lineno] or filename
            if kind == "unit" and filename.endswith(".json") and not context:
                sym = named_symbols.get(container)
                if sym is not None:
                    comp = _json_scalar_in(lines, (sym.start, sym.end), "component_ref")
                    if comp:
                        context = {"component_ref": comp}
            family = {"entity": "entity", "unit": "work_unit", "component": "component", "task": "task"}[kind]
            target, candidates = defs.resolve(kind, value, cid, context)
            file_refs.add((family, target or value))
            if target is not None:
                if target != container:
                    add_edge(target, container)
            elif candidates:
                ambiguous.append(
                    f"'{value}' (in {key}) at {filename}:{lineno} names {len(candidates)} work units "
                    f"({join_ids(candidates, 4)}) - qualify it as <container>/<component>/<unit>"
                )
            else:
                dangling_warnings.append(Reference(value, filename, lineno, container, False, key))

    warnings.extend(ambiguous)
    return EdgeGraph(
        definitions=definitions,
        referenced_by={k: sorted(v, key=_id_sort_key) for k, v in referenced_by.items()},
        local_referenced_by={
            f: {k: sorted(v, key=_id_sort_key) for k, v in sorted(m.items(), key=lambda kv: _id_sort_key(kv[0]))}
            for f, m in local_referenced_by.items()
        },
        references_out={k: sorted(v, key=_id_sort_key) for k, v in references_out.items()},
        refs_by_file=refs_by_file,
        dangling=sorted(set(dangling), key=lambda r: (_id_sort_key(r.id), r.file, r.line)),
        dangling_warnings=sorted(set(dangling_warnings), key=lambda r: (_id_sort_key(r.id), r.file, r.line)),
    )


# ---------------------------------------------------------------------------
# Index assembly
# ---------------------------------------------------------------------------


class DocIndex(NamedTuple):
    """The assembled navigation index, ready to render or query."""

    generated_from: "dict[str, dict[str, object]]"
    sections: "dict[str, dict[str, tuple[int, int]]]"  # canonical files only
    symbols: "dict[str, SymbolSlice]"
    aliases: "dict[str, str]"  # bare work-unit name -> qualified symbol (unique only)
    shards: "dict[str, list[str]]"
    definitions: "dict[str, tuple[str, int]]"
    referenced_by: "dict[str, list[str]]"
    local_referenced_by: "dict[str, dict[str, list[str]]]"
    references_out: "dict[str, list[str]]"
    refs_by_file: "dict[str, set[tuple[str, str]]]"
    dangling: "list[Reference]"
    dangling_warnings: "list[Reference]"
    warnings: "list[str]"
    retired_ids: "list[str]"
    # Definitions the index could not name because an earlier file already
    # defines the same symbol name - kept so a per-file item map (--stamp,
    # --drift, --items) still sees every item a file defines.
    shadowed: "tuple[SymbolSlice, ...]" = ()


def build_index(docs_dir: Path) -> DocIndex:
    """Scan the canonical docs and every shard and assemble the index.

    A file that cannot be read or parsed is recorded under ``warnings`` and
    skipped, so the generator never breaks an edit.
    """
    files = _discover_files(docs_dir)
    shard_map = _discover_shards(docs_dir)
    shard_names = sorted(n for names in shard_map.values() for n in names)
    warnings: list[str] = []
    generated_from: dict[str, dict[str, object]] = {}
    sections: dict[str, dict[str, tuple[int, int]]] = {}
    all_sections: dict[str, dict[str, tuple[int, int]]] = {}
    symbols: dict[str, SymbolSlice] = {}
    lines_by_file: dict[str, list[str]] = {}
    skip_by_file: dict[str, list[tuple[int, int]]] = {}

    for filename in files + shard_names:
        is_shard = filename in shard_names
        path = docs_dir / filename
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            warnings.append(f"{filename} could not be read ({e}) - it is not indexed")
            continue
        lines = text.splitlines()
        lines_by_file[filename] = lines
        generated_from[filename] = {
            "sha256": sha256(text.encode("utf-8")).hexdigest(),
            "lines": len(lines),
        }
        base = _shard_parent(filename) if is_shard else filename
        if filename.endswith(".json"):
            try:
                json.loads(text)
            except ValueError as e:
                warnings.append(
                    f"{filename} is not valid JSON ({str(e)[:80]}) - its tasks are not indexed "
                    f"and references inside it are not checked"
                )
                continue
            file_sections, json_symbols = _scan_json(lines)
            all_sections[filename] = file_sections
            if not is_shard:
                sections[filename] = file_sections
            skip_by_file[filename] = _changelog_ranges(lines, file_sections, True)
            for sym in json_symbols:
                sym = sym._replace(file=filename)
                symbols[sym.file + ":" + sym.path] = sym
            continue
        file_sections = _top_level_sections(lines)
        all_sections[filename] = file_sections
        if not is_shard:
            sections[filename] = file_sections
        skip_by_file[filename] = _changelog_ranges(lines, file_sections, False)
        extractors = (_SHARD_EXTRACTORS if is_shard else _EXTRACTORS).get(base, ())
        for extractor in extractors:
            for sym in extractor(lines, file_sections, filename):
                symbols[sym.file + ":" + sym.path] = sym  # temp key; re-keyed below

    def _file_rank(fname: str) -> int:
        try:
            return files.index(fname)  # canonical files keep their index order
        except ValueError:
            return len(files)  # shard files sort after every canonical

    ordered = sorted(
        symbols.values(),
        key=lambda s: (_file_rank(s.file), s.file, s.start),
    )
    named: dict[str, SymbolSlice] = {}
    shadowed: list[SymbolSlice] = []
    for sym in ordered:
        name = _symbol_name(sym)
        prior = named.get(name)
        if prior is not None and (prior.file, prior.start) != (sym.file, sym.start):
            warnings.append(
                f"symbol name '{name}' is defined twice ({prior.file}:{prior.start} and "
                f"{sym.file}:{sym.start}) - --show/--refs resolve the first; rename one to disambiguate"
            )
            shadowed.append(sym)
            continue
        named[name] = sym

    aliases: dict[str, str] = {}
    bare_units: dict[str, list[str]] = {}
    for name, sym in named.items():
        if sym.kind == "work_unit":
            bare_units.setdefault(name.rsplit("/", 1)[-1], []).append(name)
    for bare, qualified in bare_units.items():
        if len(qualified) == 1 and bare not in named:
            aliases[bare] = qualified[0]

    prd_lines = lines_by_file.get("PRD.yaml")
    retired = _load_retired_ids(docs_dir, prd_lines, all_sections.get("PRD.yaml", {}), warnings)

    graph = _build_edges(
        lines_by_file, all_sections, named, skip_by_file, set(shard_names), retired, warnings
    )
    return DocIndex(
        generated_from=generated_from,
        sections=sections,
        symbols=named,
        aliases=aliases,
        shards=shard_map,
        definitions=graph.definitions,
        referenced_by=graph.referenced_by,
        local_referenced_by=graph.local_referenced_by,
        references_out=graph.references_out,
        refs_by_file=graph.refs_by_file,
        dangling=graph.dangling,
        dangling_warnings=graph.dangling_warnings,
        warnings=warnings,
        retired_ids=sorted(retired, key=_id_sort_key),
        shadowed=tuple(shadowed),
    )


_BRACKET_ID_RE = re.compile(r"\[([A-Z]+-(?:[A-Z][A-Z0-9]*-)?\d+)\]$")


def _symbol_name(sym: SymbolSlice) -> str:
    """The lookup key an agent uses: an explicit ``name`` when the extractor set
    one (entities, enums, components, qualified work units, tests, typed ids),
    else the bracketed id at the end of the path, else the path's last segment.

    A task in a ``TASKS__<cid>.json`` shard is keyed by its **qualified** id
    ``<cid>/TSK-NNN`` — matching how sdlc-code (``topo_order.py``) addresses
    tasks and avoiding the cross-file ``TSK-001`` collision (every shard and the
    canonical file restart their numbering). A task in the canonical
    ``TASKS.json`` keeps its bare ``TSK-NNN``.
    """
    if sym.name:
        return sym.name
    bracketed = _BRACKET_ID_RE.search(sym.path)
    if bracketed is not None:
        sym_id = bracketed.group(1)
        if sym_id.startswith("TSK-") and "__" in sym.file:
            return f"{_shard_slug(sym.file)}/{sym_id}"
        return sym_id
    return sym.path.rsplit(".", 1)[-1]


def resolve_symbol(index: DocIndex, name: str) -> "tuple[Optional[SymbolSlice], list[str]]":
    """``(symbol | None, ambiguous candidates)`` for a symbol name, a bare
    work-unit alias, or a ``docs/``-prefixed shard task id."""
    sym = index.symbols.get(name)
    if sym is not None:
        return sym, []
    alias = index.aliases.get(name)
    if alias is not None:
        return index.symbols.get(alias), []
    candidates = [
        n for n, s in index.symbols.items() if s.kind == "work_unit" and n.rsplit("/", 1)[-1] == name
    ]
    return None, candidates


# ---------------------------------------------------------------------------
# YAML emission (controlled, schema-specific — not a general dumper)
# ---------------------------------------------------------------------------

_HEADER = (
    "# GENERATED by .claude/sdlc/docs_index.py — DO NOT HAND-EDIT.\n"
    "# Regenerated automatically by the Write|Edit|MultiEdit PostToolUse hook on\n"
    "# any canonical docs/*.yaml, docs/TASKS*.json or docs/*__* shard edit. A\n"
    "# location map (file + line range + one-line summary) PLUS a cross-reference\n"
    "# graph (referenced_by + dangling) over every SDLC artifact and shard; it\n"
    "# duplicates NO field bodies. `docs_index.py --check` gates on an empty\n"
    "# dangling list. Retrieval protocol: .claude/rules/sdlc-docs-access.md\n"
)

# Characters that force a scalar out of bare form inside a flow sequence.
_FLOW_UNSAFE = re.compile(r"""[\s,:\[\]{}#&*!|>'"%@`]""")


def _sq(value: object) -> str:
    """Render ``value`` as a single-quoted YAML scalar with minimal escaping."""
    text = " ".join(str(value).split())
    return "'" + text.replace("'", "''") + "'"


def _flow(value: str) -> str:
    """Bare scalar when safe in a flow sequence, else single-quoted."""
    return value if value and not _FLOW_UNSAFE.search(value) else _sq(value)


def _ref_line(ref: Reference) -> str:
    via = f", via {ref.key}" if ref.key else ""
    return f"{ref.id} @ {ref.file}:{ref.line} (in {ref.container}{via})"


def render_index_yaml(index: DocIndex) -> str:
    """Serialize the index to deterministic, token-lean YAML."""
    out: list[str] = [_HEADER, "# generated_from: every indexed file (canonicals, then shards) with the"]
    out.append("#   16-hex content hash `docs_index.py --hash <file>` prints and every")
    out.append("#   upstream_provenance entry records. Compare, never recompute inline.")
    out.append("generated_from:")
    for fname, meta in index.generated_from.items():
        sha = str(meta["sha256"])[:_SHA_LEN]
        out.append(f"  {fname}: {{sha256: {sha}, lines: {meta['lines']}}}")

    out.append("")
    out.append("# sections: canonical files only (shards load by symbol or whole).")
    out.append("sections:")
    for fname, secs in index.sections.items():
        out.append(f"  {fname}:")
        for key, (start, end) in secs.items():
            out.append(f"    {key}: [{start}, {end}]")

    if index.shards:
        out.append("")
        out.append("# shards: every docs/<PARENT>__<slug> sub-artifact present, keyed by")
        out.append("# its parent canonical. Shards are scanned: ARCH__ components + work units,")
        out.append("# TEST-STRATEGY__ tests, API__ operations, DESIGN__assets assets and")
        out.append("# TASKS__ tasks (<cid>/TSK-NNN) are symbols; references inside every shard")
        out.append("# count in referenced_by. Most non-TASKS shards still load cheaply whole.")
        out.append("shards:")
        for parent, names in index.shards.items():
            out.append(f"  {parent}: [{', '.join(_flow(n) for n in names)}]")

    out.append("")
    out.append("# symbols: grouped by file. Each row is positional —")
    out.append("#   name: [start, end, kind, context, summary]")
    out.append("# Read only the [start, end] line range; never the whole source file.")
    out.append("# Work units are keyed <cid>/<component>/<unit>; `--show <unit>` also")
    out.append("# accepts the bare name when it is unique. context is ~ (null) when none.")
    out.append("symbols:")
    by_file: dict[str, list[tuple[str, SymbolSlice]]] = {}
    for name, sym in index.symbols.items():
        by_file.setdefault(sym.file, []).append((name, sym))
    # Canonical files first (in sections order), then every shard that carries
    # symbols (by_file preserves the deterministic ordered() grouping).
    render_order = list(index.sections)
    render_order += [f for f in by_file if f not in index.sections]
    for fname in render_order:
        rows = by_file.get(fname)
        if not rows:
            continue
        out.append(f"  {fname}:")
        for name, sym in rows:
            context = _flow(sym.context) if sym.context else "~"
            out.append(
                f"    {_flow(name)}: [{sym.start}, {sym.end}, {_flow(sym.kind)}, "
                f"{context}, {_sq(sym.summary)}]"
            )

    _render_edges(out, index)
    return "\n".join(out) + "\n"


def _render_edges(out: "list[str]", index: DocIndex) -> None:
    """Append ``referenced_by`` (inbound blast-radius), ``dangling``,
    ``dangling_warnings``, ``warnings`` and ``retired_ids``.

    ``referenced_by`` rows are grouped by the file that DEFINES each id or
    name; only defined symbols with at least one inbound reference appear.
    File-local WRN rows sit under their own file. ``dangling`` lists blocking
    references that resolve to no definition — an empty list when the corpus
    is clean (the state the ``--check`` gate requires).
    """
    out.append("")
    out.append("# referenced_by: inbound edge map — the edit blast-radius. For each")
    out.append("#   defined id (FR/NFR/WKF/SCR/TST/...) or named symbol (entity, enum,")
    out.append("#   component, work unit, task), the symbols/sections/tasks that mention it,")
    out.append("#   grouped by the doc that DEFINES it. A shard's section container reads")
    out.append("#   <file>:<section>. WRN rows are file-local. Consult before editing.")
    out.append("referenced_by:")
    by_def_file: dict[str, list[str]] = {}
    for ref_id in index.referenced_by:
        def_entry = index.definitions.get(ref_id)
        if def_entry is None:
            continue
        by_def_file.setdefault(def_entry[0], []).append(ref_id)
    render_order = list(index.generated_from)
    render_order += [f for f in by_def_file if f not in index.generated_from]
    render_order += [f for f in index.local_referenced_by if f not in render_order]
    for fname in render_order:
        ids = by_def_file.get(fname, [])
        local = index.local_referenced_by.get(fname, {})
        if not ids and not local:
            continue
        out.append(f"  {fname}:")
        for ref_id in sorted(ids, key=_id_sort_key):
            containers = ", ".join(_flow(c) for c in index.referenced_by[ref_id])
            out.append(f"    {_flow(ref_id)}: [{containers}]")
        for ref_id, containers in local.items():
            out.append(f"    {ref_id}: [{', '.join(_flow(c) for c in containers)}]")

    out.append("")
    out.append("# dangling: references whose id is a blocking corpus family but resolves to")
    out.append("#   no definition (a typo or a deleted symbol). Empty when the corpus is clean;")
    out.append("#   `docs_index.py --check` exits non-zero when this list is non-empty.")
    out.append("#   Only STRUCTURED references count (a field value, a list entry, a flow-list")
    out.append("#   element); an id mentioned inside prose is never dangling.")
    if not index.dangling:
        out.append("dangling: []")
    else:
        out.append("dangling:")
        for ref in index.dangling:
            out.append(f"  - {_sq(_ref_line(ref))}")

    out.append("")
    out.append("# dangling_warnings: unresolved references that do NOT fail --check yet:")
    out.append("#   the TST/OPR/AST/QUE families (warn-first for one version) and named")
    out.append("#   references (entity, work unit, component, task) with no definition.")
    if not index.dangling_warnings:
        out.append("dangling_warnings: []")
    else:
        out.append("dangling_warnings:")
        for ref in index.dangling_warnings:
            out.append(f"  - {_sq(_ref_line(ref))}")

    out.append("")
    out.append("# warnings: files the generator could not index and symbol-name collisions.")
    if not index.warnings:
        out.append("warnings: []")
    else:
        out.append("warnings:")
        for w in index.warnings:
            out.append(f"  - {_sq(w)}")

    if index.retired_ids:
        out.append("")
        out.append("# retired_ids: cited without a definition on purpose (docs/INDEX.allow.yaml")
        out.append("#   or PRD metadata.retired_ids); never dangling.")
        out.append(f"retired_ids: [{', '.join(index.retired_ids)}]")


def write_index(docs_dir: Path) -> Path:
    """Build the index and write ``docs/INDEX.yaml``. Returns the written path."""
    index = build_index(docs_dir)
    target = docs_dir / INDEX_FILENAME
    # newline="\n": the index is a generated artifact other tools hash and diff;
    # the host's line-ending convention must not leak into it (ledger IMP-043).
    target.write_text(render_index_yaml(index), encoding="utf-8", newline="\n")
    return target


def find_symbol_slice(docs_dir: Path, name: str) -> "Optional[tuple[Path, int, int]]":
    """Resolve a symbol name to ``(file_path, start, end)`` via a fresh scan."""
    sym, _candidates = resolve_symbol(build_index(docs_dir), name)
    if sym is None:
        return None
    return docs_dir / sym.file, sym.start, sym.end


def find_symbol_refs(
    docs_dir: Path, name: str
) -> "Optional[tuple[str, list[str], list[str], list[Reference]]]":
    """Resolve a symbol/id's 1-hop reference neighbourhood (the ``--refs`` query).

    Returns ``(resolved_name, references_out, referenced_by, dangling_within)``:
    the defined ids/names ``name`` mentions, the containers that mention
    ``name``, and any dangling references located inside ``name``'s line
    range. A bare work-unit name resolves through its alias; a file-local WRN
    id reports the union of its per-file inbound sites. ``None`` when ``name``
    is wholly unknown (not a symbol, a container, or a defined id).
    """
    index = build_index(docs_dir)
    sym, _candidates = resolve_symbol(index, name)
    if sym is not None:
        name = _symbol_name(sym)
    local_in: list[str] = []
    if name.split("-", 1)[0] in _FILE_LOCAL_PREFIXES:
        for per_file in index.local_referenced_by.values():
            local_in += per_file.get(name, [])
    known = (
        sym is not None
        or name in index.definitions
        or bool(local_in)
        or name in index.references_out
        or any(name in cs for cs in index.referenced_by.values())
    )
    if not known:
        return None
    out_refs = index.references_out.get(name, [])
    in_refs = index.referenced_by.get(name, []) + sorted(set(local_in), key=_id_sort_key)
    within: list[Reference] = []
    if sym is not None:
        within = [
            r for r in index.dangling + index.dangling_warnings
            if r.file == sym.file and sym.start <= r.line <= sym.end
        ]
    return name, out_refs, in_refs, within


def find_symbols(
    docs_dir: Path,
    *,
    kind: "Optional[str]" = None,
    context: "Optional[str]" = None,
    file: "Optional[str]" = None,
    text: "Optional[str]" = None,
    references: "Optional[str]" = None,
    referenced_by: "Optional[str]" = None,
) -> "list[tuple[str, SymbolSlice]]":
    """Predicate search over the symbol table (the ``--find`` query).

    Every supplied filter must match (AND semantics): ``kind``/``context``/``file``
    are exact (case-insensitive); ``text`` is a case-insensitive substring of the
    summary; ``references`` keeps symbols whose container mentions that id;
    ``referenced_by`` keeps the single defined id whose inbound set contains the
    named container. Returns ``(name, SymbolSlice)`` pairs in index order.
    """
    index = build_index(docs_dir)
    refs_out = index.references_out
    out: list[tuple[str, SymbolSlice]] = []
    for name, sym in index.symbols.items():
        if kind is not None and sym.kind.lower() != kind.lower():
            continue
        if context is not None and (sym.context or "").lower() != context.lower():
            continue
        if file is not None and sym.file.lower() != file.lower():
            continue
        if text is not None and text.lower() not in sym.summary.lower():
            continue
        if references is not None and references not in refs_out.get(name, []):
            continue
        if referenced_by is not None and name not in index.referenced_by.get(referenced_by, []):
            continue
        out.append((name, sym))
    return out


# ---------------------------------------------------------------------------
# --drift: an artifact's recorded upstream_provenance vs the upstreams now
# ---------------------------------------------------------------------------

_PROV_KEYS = ("file", "sha256", "session_id", "last_updated", "version")
# Length of a per-item body hash recorded under upstream_provenance[].items.
_ITEM_HASH_LEN = 12
# Fields a change to which is a DECLARATION, not a behaviour change, per
# symbol kind: an entity-trace backfill or a status flip falsifies no test and
# changes no contract, so it does not make the item "modified" (ledger IMP-064,
# aicf LSN-052: 33 of 40 changed work-unit bodies differed only here).
_DECLARATION_ONLY_KEYS: "dict[str, tuple[str, ...]]" = {
    "work_unit": ("touches_entities", "status"),
    # A component's children are items of their own; the component's hash is
    # its own contract (purpose, responsibilities, code_location, traces).
    "component": ("work_units", "status"),
    "test": ("status",),
}
_STAGE_OF = {
    "PRD": "prd", "UX": "ux", "DESIGN": "design", "DATA-MODEL": "data", "API": "api",
    "ARCH": "arch", "TEST-STRATEGY": "test", "TASKS": "task", "CODE-MANIFEST": "code",
}
_CONTAINER_SKILLS = frozenset({"arch", "test", "task"})
# Artifacts that consume no upstream artifact, so they can never carry
# ``upstream_provenance`` and must never be told to record one. The PRD is the
# pipeline's root: it is built from the repo and the interview, and CLAUDE.md
# section 7 names it exempt from the provenance convention every later stage
# follows.
_ROOT_ARTIFACTS = frozenset({"PRD"})


def _parse_provenance(lines: "list[str]", is_json: bool) -> "list[dict]":
    """``metadata.upstream_provenance`` entries as ``{file, sha256, ...}`` dicts,
    plus ``items`` (``{key: hash}``) when the entry carries the per-item map
    ``--stamp`` writes. Flow entries (``- {file: ..., sha256: ...}``) and block
    entries are both read; ``items`` is read in block form only."""
    entries: list[dict] = []
    if not is_json:
        sections = _top_level_sections(lines)
        meta = sections.get("metadata")
        if meta is None:
            return []
        rng = _named_range(_child_keys(lines, meta, 2), "upstream_provenance")
        if rng is None:
            return []
        cur: Optional[dict] = None
        items_indent: Optional[int] = None
        for i in range(rng[0], rng[1]):
            raw = lines[i]
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            indent = _indent(raw)
            if items_indent is not None:
                if indent > items_indent and not stripped.startswith("- "):
                    key, _, value = stripped.partition(":")
                    if cur is not None and key:
                        cur.setdefault("items", {})[_unquote(key.strip())] = _unquote(value.strip())
                    continue
                items_indent = None
            if stripped.startswith("- "):
                if cur:
                    entries.append(cur)
                cur = {}
                body = stripped[2:]
                indent += 2
            else:
                body = stripped
            if re.match(r"^items:\s*(\{\s*\})?\s*$", body):
                if cur is not None:
                    cur.setdefault("items", {})
                items_indent = indent
                continue
            for m in re.finditer(r"(?:^|[{,]\s*)(" + "|".join(_PROV_KEYS) + r"):\s*([^,}]+)", body):
                if cur is not None:
                    cur[m.group(1)] = _unquote(m.group(2).strip())
        if cur:
            entries.append(cur)
        return entries
    try:
        data = json.loads("\n".join(lines))
    except ValueError:
        data = None
    if isinstance(data, dict):
        meta_obj = data.get("metadata")
        raw_entries = meta_obj.get("upstream_provenance") if isinstance(meta_obj, dict) else None
        for e in raw_entries or []:
            if not isinstance(e, dict):
                continue
            entry: dict = {k: str(e[k]) for k in _PROV_KEYS if e.get(k) is not None}
            if isinstance(e.get("items"), dict):
                entry["items"] = {str(k): str(v) for k, v in e["items"].items()}
            entries.append(entry)
        return entries
    sections, _syms = _scan_json(lines)
    meta = sections.get("metadata")
    if meta is None:
        return []
    inside = False
    cur = None
    for i in range(meta[0] - 1, meta[1]):
        line = lines[i]
        if not inside:
            if re.match(r'^\s*"upstream_provenance"\s*:', line):
                inside = True
                if "]" in line:
                    break
            continue
        stripped = line.strip()
        if stripped.startswith("]"):
            break
        if "{" in stripped:
            cur = {}
        for m in re.finditer(r'"(' + "|".join(_PROV_KEYS) + r')"\s*:\s*"([^"]*)"', line):
            if cur is not None:
                cur[m.group(1)] = m.group(2)
        if "}" in stripped and cur is not None:
            entries.append(cur)
            cur = None
    return entries


def item_hash(lines: "list[str]", sym: SymbolSlice) -> str:
    """The short body hash of one symbol: its line slice with blank and comment
    lines dropped and trailing whitespace stripped - and, for kinds listed in
    ``_DECLARATION_ONLY_KEYS``, with those child fields removed, so only a
    behaviour-bearing edit changes the hash."""
    body = lines[sym.start - 1: sym.end]
    excluded = _DECLARATION_ONLY_KEYS.get(sym.kind, ())
    kept: list[str] = []
    child_indent = (_indent(body[0]) + 2) if body else 0
    skipping = False
    for ln in body:
        if not _is_boundary(ln):
            continue
        ind = _indent(ln)
        if skipping and ind > child_indent:
            continue
        skipping = False
        if excluded and ind == child_indent:
            m = _KEY_RE.match(ln)
            if m is not None and m.group("key") in excluded:
                skipping = True
                continue
        kept.append(ln.rstrip())
    return sha256("\n".join(kept).encode("utf-8")).hexdigest()[:_ITEM_HASH_LEN]


def items_of(index: DocIndex, docs_dir: Path, upstream: str) -> "dict[str, str]":
    """Every symbol ``upstream`` (a file name inside docs/) defines, keyed the
    way the index addresses it, with its body hash. Empty when the file is not
    indexed or defines nothing addressable."""
    path = docs_dir / upstream
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for name, sym in index.symbols.items():
        if sym.file == upstream:
            out[name] = item_hash(lines, sym)
    # A symbol another file defines first is absent from index.symbols; it is
    # still one of THIS file's items, and leaving it out made --drift report
    # "no item added" for exactly the item that was new.
    for sym in index.shadowed:
        if sym.file == upstream:
            out.setdefault(_symbol_name(sym), item_hash(lines, sym))
    return out


def _item_family(key: str, index: DocIndex) -> str:
    """The family label of an item key, for ``--drift`` grouping - also for a
    key the current corpus no longer defines."""
    if key in index.symbols:
        return _family_of_definition(key, index)
    if _ID_ONLY_RE.match(key):
        return key.split("-", 1)[0]
    if re.search(r"/TSK-\d+$", key):
        return "task"
    if key.count("/") == 2:
        return "work_unit"
    return "item"


def _upstream_meta(path: Path) -> "dict[str, str]":
    """``session_id`` / ``last_updated`` of an upstream artifact's metadata."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError:
            return out
        meta = data.get("metadata") if isinstance(data, dict) else None
        for key in ("session_id", "last_updated"):
            if isinstance(meta, dict) and meta.get(key) is not None:
                out[key] = str(meta[key])
        if isinstance(meta, dict):
            vkey = next((k for k in meta if str(k).endswith("_version")), None)
            if vkey is not None and meta.get(vkey) is not None:
                out["version"] = str(meta[vkey])
        return out
    lines = text.splitlines()
    meta_rng = _top_level_sections(lines).get("metadata")
    if meta_rng is None:
        return out
    # The artifact's own `<name>_version` - the key bump_artifact.py bumps, so
    # --drift can list the changelog lines written since this stamp.
    vkey = next((name for name, _s, _e in _child_keys(lines, meta_rng, 2)
                 if name.endswith("_version")), None)
    for key in ("session_id", "last_updated") + ((vkey,) if vkey else ()):
        val = _find_child_value(lines, meta_rng, 2, key)
        if val:
            val = _unquote(re.sub(r"\s+#.*$", "", val))
            if val.lower() not in _YAML_NULLS:
                out["version" if key == vkey else key] = val
    return out


def _parse_deferrals(lines: "list[str]", is_json: bool) -> "set[str]":
    """Ids and item keys the artifact defers STRUCTURALLY (CLAUDE.md 6): a
    top-level ``deferrals`` / ``deferred_requirements`` entry that carries both
    an id and a reason, or a typed warning's ``defers: [...]`` list. Prose that
    merely mentions an id defers nothing."""
    out: set[str] = set()
    if is_json:
        try:
            data = json.loads("\n".join(lines))
        except ValueError:
            return out
        if not isinstance(data, dict):
            return out
        for key in ("deferrals", "deferred_requirements"):
            for d in data.get(key) or []:
                if isinstance(d, dict) and d.get("id") and d.get("reason"):
                    out.add(str(d["id"]).strip())
        for key, val in data.items():
            if str(key).endswith("_warnings") and isinstance(val, list):
                for w in val:
                    if isinstance(w, dict) and isinstance(w.get("defers"), list):
                        out.update(str(x).strip() for x in w["defers"] if x)
        return out
    sections = _top_level_sections(lines)
    for key in ("deferrals", "deferred_requirements"):
        rng = sections.get(key)
        if rng is None:
            continue
        pending: Optional[str] = None
        has_reason = False
        for i in range(rng[0], rng[1]):
            stripped = lines[i].strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith("- "):
                if pending and has_reason:
                    out.add(pending)
                pending, has_reason = None, False
                body = stripped[2:].strip()
                m = re.search(r"(?:^|[{,]\s*)id:\s*([^,}]+)", body)
                if m:
                    pending = _unquote(m.group(1).strip())
                if re.search(r"(?:^|[{,]\s*)reason:\s*\S", body):
                    has_reason = True
                continue
            m = re.match(r"^id:\s*(.+)$", stripped)
            if m:
                pending = _unquote(re.sub(r"\s+#.*$", "", m.group(1)).strip())
            elif re.match(r"^reason:\s*\S", stripped):
                has_reason = True
        if pending and has_reason:
            out.add(pending)
    for i, line in enumerate(lines):
        m = re.match(r"^(\s*)(?:-\s+)?defers:\s*(.*)$", line)
        if m is None:
            continue
        values = _parse_inline_values(m.group(2))
        if not values and not m.group(2).strip():
            values = _block_seq_values(lines, i, len(m.group(1)))
        out.update(v for v in values if v)
    return out


def _deferred_match(key: str, deferred: "set[str]") -> bool:
    """A deferral names an item by its full key, its bare name, or its id."""
    if key in deferred:
        return True
    bare = key.rsplit("/", 1)[-1]
    return bare in deferred or bare.upper() in {d.upper() for d in deferred}


def _render_provenance_yaml(entries: "list[dict]", indent: int) -> "list[str]":
    """The block form of ``upstream_provenance`` at ``indent`` (the metadata
    children's indent): one block entry per upstream, ``items`` as a nested
    mapping, keys quoted only when YAML needs it."""
    pad = " " * indent
    out = [f"{pad}upstream_provenance:"]
    for e in entries:
        out.append(f"{pad}  - file: {_flow(str(e.get('file', '')))}")
        for key in ("session_id", "last_updated", "version", "sha256"):
            if e.get(key) is not None:
                out.append(f"{pad}    {key}: {_sq(e[key])}")
        items = e.get("items")
        if isinstance(items, dict):
            if not items:
                out.append(f"{pad}    items: {{}}")
            else:
                out.append(f"{pad}    items:")
                for k in sorted(items, key=_id_sort_key):
                    out.append(f"{pad}      {_flow(str(k))}: {items[k]}")
    return out


def stamp_artifact(docs_dir: Path, artifact: str, extra_upstreams: "list[str]",
                   as_json: bool = False) -> int:
    """``--stamp``: rewrite one artifact's ``metadata.upstream_provenance`` -
    ``{file, session_id, last_updated, sha256, items}`` per upstream, where
    the upstream set is what the artifact already records plus every
    ``--upstream``. Writes ONLY that artifact (never the index, never an
    upstream), so it is safe on a project that runs its own index generator.
    Returns the exit code."""
    path = _locate(artifact, docs_dir)
    if not path.is_file():
        print(f"[docs-stamp] cannot read {artifact}: no such file (looked in {docs_dir})", file=sys.stderr)
        return 2
    name = path.name
    is_json = name.endswith(".json")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        print(f"[docs-stamp] cannot read {path}: {e}", file=sys.stderr)
        return 2
    lines = text.splitlines()
    label = f"docs/{name}"
    existing = _parse_provenance(lines, is_json)
    wanted: list[str] = []
    for f in [e.get("file", "") for e in existing] + list(extra_upstreams):
        base = Path(str(f)).name if f else ""
        if base and base != name and base not in wanted:
            wanted.append(base)
    if not wanted:
        if name.split("__", 1)[0].rsplit(".", 1)[0] in _ROOT_ARTIFACTS:
            print(f"[OK] {label} consumes no upstream artifact, so there is nothing to stamp.")
            return 0
        print(f"[FAIL] {label} records no upstream and none was given - name what it was built "
              f"from with --upstream docs/<file> (one flag per upstream).")
        return 1
    index = build_index(docs_dir)
    missing = [u for u in wanted if not (docs_dir / u).is_file()]
    entries: list[dict] = []
    for up in wanted:
        if up in missing:
            old = next((e for e in existing if Path(str(e.get("file", ""))).name == up), None)
            if old is not None:
                entries.append(old)  # keep the stale record rather than lose it
            continue
        meta = _upstream_meta(docs_dir / up)
        entry: dict = {"file": f"docs/{up}"}
        entry.update(meta)
        entry["sha256"] = content_hash(docs_dir / up)
        entry["items"] = items_of(index, docs_dir, up)
        entries.append(entry)
    newline = "\r\n" if "\r\n" in text else "\n"
    if is_json:
        try:
            data = json.loads(text)
        except ValueError as e:
            print(f"[docs-stamp] {label} is not valid JSON ({e}) - nothing written", file=sys.stderr)
            return 2
        if not isinstance(data, dict):
            print(f"[docs-stamp] {label} is not a JSON object - nothing written", file=sys.stderr)
            return 2
        meta_obj = data.setdefault("metadata", {})
        if not isinstance(meta_obj, dict):
            print(f"[docs-stamp] {label} has no metadata mapping - nothing written", file=sys.stderr)
            return 2
        meta_obj["upstream_provenance"] = entries
        second = lines[1] if len(lines) > 1 else "  "
        indent = len(second) - len(second.lstrip(" ")) or 2
        rendered = json.dumps(data, indent=indent, ensure_ascii=False) + "\n"
    else:
        sections = _top_level_sections(lines)
        meta_rng = sections.get("metadata")
        if meta_rng is None:
            print(f"[docs-stamp] {label} has no top-level metadata block - nothing written", file=sys.stderr)
            return 2
        children = _child_keys(lines, meta_rng, 2)
        child_indent = 2
        if children:
            child_indent = _indent(lines[children[0][1] - 1])
        block = _render_provenance_yaml(entries, child_indent)
        prov_rng = _named_range(children, "upstream_provenance")
        if prov_rng is not None:
            new_lines = lines[: prov_rng[0] - 1] + block + lines[prov_rng[1]:]
        else:
            new_lines = lines[: meta_rng[1]] + block + lines[meta_rng[1]:]
        rendered = "\n".join(new_lines) + "\n"
    with open(path, "w", encoding="utf-8", newline=newline) as fh:
        fh.write(rendered)
    stamped = [e for e in entries if isinstance(e.get("items"), dict) and Path(str(e.get("file", ""))).name not in missing]
    if as_json:
        print(json.dumps({
            "artifact": label,
            "stamped": [{"file": e["file"], "sha256": e.get("sha256"), "items": len(e["items"])} for e in stamped],
            "missing": missing,
        }, indent=2))
    else:
        summary = ", ".join(f"{Path(e['file']).name} ({len(e['items'])} item(s))" for e in stamped)
        print(f"[OK] {label} now records {len(stamped)} upstream(s) item by item: {summary}.")
        if missing:
            print_findings([], [
                f"{u} is recorded as an upstream but no longer exists in {docs_dir} - its old "
                f"record was kept unchanged; re-run the skill that owns {label} to reconcile"
                for u in missing])
        else:
            print_findings([], [])
        print_next("nothing required - a later --drift on this file diffs item by item.",
                   show_glossary=False)
    return 1 if missing else 0


def _family_of_definition(name: str, index: DocIndex) -> str:
    """The family label a defined id/name belongs to (its prefix, or the
    symbol kind for name-addressed definitions)."""
    if _ID_ONLY_RE.match(name):
        return name.split("-", 1)[0]
    sym = index.symbols.get(name)
    if sym is None:
        return "name"
    if sym.file.startswith("DATA-MODEL"):
        return "entity"
    return sym.kind


def _owner_skill(artifact: str) -> str:
    stem = artifact.split("__", 1)[0].rsplit(".", 1)[0]
    skill = _STAGE_OF.get(stem)
    if skill is None:
        return "the skill that owns it"
    if "__" in artifact and skill in _CONTAINER_SKILLS:
        return f"/sdlc:{skill} {_shard_slug(artifact)}"
    return f"/sdlc:{skill}"


# Consumer skills that have a scoped `--reconcile` form (CLAUDE.md 7). The
# pipeline root consumes no upstream; `code` gates staleness at its own plan.
_RECONCILE_SKILLS = frozenset({"ux", "design", "data", "api", "arch", "test", "task"})
_PIPELINE = ("prd", "ux", "design", "data", "api", "arch", "test", "task", "code")


def _reconcile_command(artifact: str) -> str:
    """The invocation that reconciles ``artifact`` against its moved upstreams:
    ``/sdlc:data --reconcile``; ``/sdlc:arch --system --reconcile`` for a
    sharded skill's system file; ``/sdlc:test <cid> --reconcile`` for a shard."""
    stem = artifact.split("__", 1)[0].rsplit(".", 1)[0]
    skill = _STAGE_OF.get(stem)
    if skill is None:
        return "the skill that owns it"
    if skill not in _RECONCILE_SKILLS:
        return f"/sdlc:{skill}"
    if skill in _CONTAINER_SKILLS:
        if "__" in artifact:
            return f"/sdlc:{skill} {_shard_slug(artifact)} --reconcile"
        return f"/sdlc:{skill} --system --reconcile"
    return f"/sdlc:{skill} --reconcile"


_CHANGELOG_RE = re.compile(
    r"^(?P<ver>\d+(?:\.\d+)*)\s*\((?P<date>\d{4}-\d{2}-\d{2})\)\s*:?\s*(?P<text>.*)$")
_WHY_CAP = 5


def _version_tuple(value: str) -> "Optional[tuple[int, ...]]":
    m = re.match(r"^\s*(\d+(?:\.\d+)*)", str(value or ""))
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def _clip(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _changelog_entries(path: Path) -> "list[str]":
    """The ``metadata.changelog`` lines of an artifact, in file order (newest
    first by convention). Block form only on the YAML side."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if path.suffix == ".json":
        try:
            data = json.loads(text)
        except ValueError:
            return []
        meta = data.get("metadata") if isinstance(data, dict) else None
        log = meta.get("changelog") if isinstance(meta, dict) else None
        return [str(x) for x in log] if isinstance(log, list) else []
    lines = text.splitlines()
    meta_rng = _top_level_sections(lines).get("metadata")
    if meta_rng is None:
        return []
    rng = _named_range(_child_keys(lines, meta_rng, 2), "changelog")
    if rng is None:
        return []
    out: list[str] = []
    for i in range(rng[0], rng[1]):
        stripped = lines[i].strip()
        if not stripped.startswith("- "):
            continue
        val = stripped[2:].strip()
        if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        else:
            val = val.lstrip("\"'")   # a quoted scalar folded over several lines
        out.append(val)
    return out


def _why_lines(docs_dir: Path, up_name: str, entry: dict) -> "list[str]":
    """WHY an upstream moved, from its own changelog: the lines newer than the
    version the stamp recorded - or, on a stamp that recorded no version, the
    lines dated on or after its ``last_updated``. Empty when the stamp carries
    neither, so nothing can be compared."""
    path = docs_dir / up_name
    if not path.is_file():
        return []
    recorded_v = _version_tuple(entry.get("version") or "")
    recorded_d = str(entry.get("last_updated") or "")[:10]
    by_date = recorded_v is None
    if by_date and not re.match(r"^\d{4}-\d{2}-\d{2}$", recorded_d):
        return []
    newer: list[str] = []
    for raw in _changelog_entries(path):
        m = _CHANGELOG_RE.match(raw.strip())
        if m is None:
            continue
        if by_date:
            if m.group("date") >= recorded_d:
                newer.append(raw.strip())
        else:
            v = _version_tuple(m.group("ver"))
            if v is not None and v > recorded_v:
                newer.append(raw.strip())
    if not newer:
        return ["why: its changelog has no entry since this file was stamped - the edit "
                "carried no changelog line (a hand edit?)"]
    head = ("why, per its changelog since the stamp" if not by_date else
            f"why, per its changelog since {recorded_d} (this stamp recorded no version, so "
            f"an entry from that day may predate it)")
    out = [f'{head}: "{_clip(line)}"' for line in newer[:_WHY_CAP]]
    if len(newer) > _WHY_CAP:
        out.append(f"why: +{len(newer) - _WHY_CAP} older changelog entr(ies) since the stamp")
    return out


def _stale_rows(docs_dir: Path) -> "tuple[list[dict], list[str]]":
    """(stale rows in the order to reconcile them, artifacts that record no
    provenance). Upstream first: pipeline order, a system file before its
    shards - a reconcile can move the files after it."""
    index = build_index(docs_dir)
    rows: list[dict] = []
    unstamped: list[str] = []
    for path in sorted(list(docs_dir.glob("*.yaml")) + list(docs_dir.glob("*.json"))):
        name = path.name
        if not (_is_canonical(name) or _is_shard(name)):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        stem = name.split("__", 1)[0].rsplit(".", 1)[0]
        skill = _STAGE_OF.get(stem)
        entries = _parse_provenance(lines, name.endswith(".json"))
        if not entries:
            # Only files that are supposed to carry their own stamp: a consumer
            # skill's system file, or a per-container shard.
            if skill in _RECONCILE_SKILLS and ("__" not in name or skill in _CONTAINER_SKILLS):
                unstamped.append(name)
            continue
        moved: list[str] = []
        missing: list[str] = []
        for e in entries:
            up = Path(str(e.get("file") or "")).name
            recorded = (e.get("sha256") or "")[:_SHA_LEN]
            if not up or not recorded:
                continue
            meta = index.generated_from.get(up)
            if meta is not None:
                current = str(meta["sha256"])[:_SHA_LEN]
            elif (docs_dir / up).is_file():
                current = content_hash(docs_dir / up)
            else:
                missing.append(up)
                continue
            if current != recorded:
                moved.append(up)
        if moved or missing:
            order = (_PIPELINE.index(skill) if skill in _PIPELINE else len(_PIPELINE),
                     1 if "__" in name else 0, name)
            rows.append({
                "artifact": f"docs/{name}",
                "upstreams_moved": [f"docs/{u}" for u in moved],
                "upstreams_missing": [f"docs/{u}" for u in missing],
                "command": _reconcile_command(name),
                "_order": order,
            })
    rows.sort(key=lambda r: r["_order"])
    for r in rows:
        r.pop("_order")
    return rows, unstamped


def stale_report(docs_dir: Path, as_json: bool = False) -> int:
    """``--stale``: every artifact whose recorded upstreams moved, in the order
    to reconcile them. What a `--reconcile` run prints its ``Next:`` from, so
    the chain after a repair routes itself. Returns the exit code."""
    rows, unstamped = _stale_rows(docs_dir)
    if as_json:
        print(json.dumps({
            "stale": rows,
            "unstamped": [f"docs/{n}" for n in unstamped],
            "next": rows[0]["command"] if rows else None,
        }, indent=2))
        return 1 if rows else 0
    warnings: list = []
    if unstamped:
        warnings.append((
            f"{len(unstamped)} artifact(s) record no upstream_provenance, so whether they are "
            f"stale cannot be told - the next run of the skill that owns each records one",
            [f"docs/{n}" for n in unstamped],
        ))
    if not rows:
        print("[OK] every artifact that records its upstreams is built against their current state.")
        print_findings([], warnings)
        print_next("nothing required - no reconcile is owed.", show_glossary=bool(warnings))
        return 0
    print(f"[FAIL] {len(rows)} artifact(s) were built against upstreams that have changed "
          f"since, so what they say about them may be stale.")
    print(f"\nSTALE, IN THE ORDER TO RECONCILE THEM ({len(rows)}):")
    for r in rows:
        why = []
        if r["upstreams_moved"]:
            why.append(f"{', '.join(r['upstreams_moved'])} moved")
        if r["upstreams_missing"]:
            why.append(f"{', '.join(r['upstreams_missing'])} no longer exist(s)")
        print(f"  - {r['artifact']} ({'; '.join(why)})  ->  {r['command']}")
    print_findings([], warnings)
    print_next(
        f"{rows[0]['command']}  (upstream first - a reconcile can move the files after it, "
        f"so run --stale again when it closes)",
    )
    return 1


def _locate(given: str, docs_dir: Path) -> Path:
    """Resolve a ``--hash`` / ``--drift`` argument. ``docs/X.yaml`` and bare
    ``X.yaml`` mean the file inside the docs dir being indexed (so
    ``--docs-dir`` wins over a same-named file under the cwd); any other
    relative path is taken from the cwd; absolute paths as given."""
    p = Path(given)
    if p.is_absolute():
        return p
    in_docs = docs_dir / p.name
    if p.parent.name in ("", "docs") and in_docs.is_file():
        return in_docs
    return p if p.is_file() else in_docs


_GIT_REVISIONS = 40   # how far back --drift looks for a revision matching a sha-only stamp


def _recover_items_from_git(docs_dir: Path, up_name: str, recorded: str):
    """The old upstream a sha-only stamp did not snapshot, recovered from git.

    Returns ``("hit", revision, items)`` for the newest of the last
    ``_GIT_REVISIONS`` commits touching ``docs/<up_name>`` whose text hash equals
    ``recorded`` (the hash ``--hash`` prints: text-level, so a CRLF checkout and
    an LF blob agree); ``("miss", None, None)`` when history holds no such
    revision (an uncommitted stamp); ``("unavailable", None, None)`` when git is
    absent or ``docs_dir`` is in no repository. Never raises."""
    if not recorded:
        return "unavailable", None, None
    import subprocess
    import tempfile
    try:
        log = subprocess.run(
            ["git", "-C", str(docs_dir), "log", f"-n{_GIT_REVISIONS}", "--format=%H", "--", up_name],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
    except OSError:
        return "unavailable", None, None
    if log.returncode != 0:
        return "unavailable", None, None
    for rev in log.stdout.split():
        try:
            show = subprocess.run(
                ["git", "-C", str(docs_dir), "show", f"{rev}:./{up_name}"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
        except OSError:
            return "unavailable", None, None
        if show.returncode != 0:
            continue
        old_text = show.stdout
        if sha256(old_text.encode("utf-8")).hexdigest()[:_SHA_LEN] != recorded:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            old_docs = Path(tmp) / "docs"
            old_docs.mkdir()
            (old_docs / up_name).write_text(old_text, encoding="utf-8", newline="\n")
            old_index = build_index(old_docs)
            return "hit", rev, items_of(old_index, old_docs, up_name)
    return "miss", None, None


def _item_delta_lines(index: DocIndex, docs_dir: Path, up_name: str,
                      old_items: "dict[str, str]", my_refs: "set[tuple[str, str]]",
                      basis: str) -> "list[str]":
    """The per-family added / removed / changed-in-body lines of one upstream,
    diffed item by item against ``old_items`` (a stamp's items map, or the
    items of a revision recovered from git); ``basis`` names the old side."""
    out: list[str] = []
    current_items = items_of(index, docs_dir, up_name)
    added_keys = [k for k in current_items if k not in old_items]
    removed_keys = [k for k in old_items if k not in current_items]
    modified_keys = [k for k in old_items
                     if k in current_items and current_items[k] != old_items[k]]
    referenced = {r for _fam, r in my_refs}
    by_fam: dict[str, dict[str, list[str]]] = {}
    for bucket, keys in (("added", added_keys), ("removed", removed_keys), ("modified", modified_keys)):
        for k in sorted(keys, key=_id_sort_key):
            by_fam.setdefault(_item_family(k, index), {}).setdefault(bucket, []).append(k)
    for family in sorted(by_fam):
        bits = []
        buckets = by_fam[family]
        if buckets.get("added"):
            ks = buckets["added"]
            bits.append(f"{len(ks)} added upstream since this file was written ({join_ids(ks, 8)})")
        if buckets.get("removed"):
            ks = buckets["removed"]
            stale = [k for k in ks if k in referenced or k.rsplit('/', 1)[-1] in referenced]
            note = f", {len(stale)} of them referenced here" if stale else ""
            bits.append(f"{len(ks)} removed upstream ({join_ids(ks, 8)}){note}")
        if buckets.get("modified"):
            ks = buckets["modified"]
            bits.append(f"{len(ks)} changed in body ({join_ids(ks, 8)})")
        out.append(f"{family}: " + "; ".join(bits))
    if not (added_keys or removed_keys or modified_keys):
        out.append(
            "no item was added, removed or changed - the edit touched only text outside "
            "the indexed items, or declaration-only fields (touches_entities, status)"
        )
    else:
        out.append(f"compared item by item against {basis}")
    return out


def drift_report(docs_dir: Path, artifact: str) -> int:
    """Print the ``--drift`` report for one artifact. Returns the exit code."""
    path = _locate(artifact, docs_dir)
    if not path.is_file():
        print(f"[docs-drift] cannot read {artifact}: no such file (looked in {docs_dir})", file=sys.stderr)
        return 2
    name = path.name
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        print(f"[docs-drift] cannot read {path}: {e}", file=sys.stderr)
        return 2
    entries = _parse_provenance(lines, name.endswith(".json"))
    index = build_index(docs_dir)
    label = f"docs/{name}"
    if not entries:
        if name.split("__", 1)[0].rsplit(".", 1)[0] in _ROOT_ARTIFACTS:
            print(f"[OK] {label} consumes no upstream artifact, so there is "
                  f"nothing to compare.")
            print_findings([], [])
            print_next("nothing required.", show_glossary=False)
            return 0
        print(f"[OK] {label} records no upstream_provenance, so there is nothing to compare.")
        print_findings([], [
            f"{label} carries no metadata.upstream_provenance - re-running {_owner_skill(name)} "
            f"records one, and later runs can then tell when an upstream moved"
        ])
        print_next("nothing required.", show_glossary=False)
        return 0

    my_refs = index.refs_by_file.get(name, set())
    deferred = _parse_deferrals(lines, name.endswith(".json"))
    changed: list[tuple[str, list[str]]] = []
    unchanged: list[str] = []
    warnings: list[str] = []
    # A symbol two files define is indexed under the first; items_of still
    # compares each file's own copy, but --show/--refs resolve only the first.
    # Say so for every collision touching this artifact or an upstream of it.
    involved = {name} | {Path(str(e.get("file") or "")).name for e in entries}
    for sym in index.shadowed:
        first = index.symbols.get(_symbol_name(sym))
        if first is not None and (sym.file in involved or first.file in involved):
            warnings.append(
                f"{_symbol_name(sym)} is defined twice (docs/{first.file}:{first.start} and "
                f"docs/{sym.file}:{sym.start}) - this comparison counts each file's own copy, but "
                f"--show and --refs resolve only the first, so a reference meant for the second "
                f"lands on the wrong item. Give one of them a new id."
            )
    for entry in entries:
        up_file = entry.get("file", "")
        up_name = Path(up_file).name if up_file else ""
        recorded = (entry.get("sha256") or "")[:_SHA_LEN]
        if not up_name:
            warnings.append(f"a provenance entry names no file ({entry}) - skipped")
            continue
        meta = index.generated_from.get(up_name)
        if meta is not None:
            current = str(meta["sha256"])[:_SHA_LEN]
        else:
            candidate = docs_dir.parent / up_file if not Path(up_file).is_absolute() else Path(up_file)
            if not candidate.is_file():
                candidate = docs_dir / up_name
            try:
                current = content_hash(candidate)
            except (OSError, UnicodeDecodeError):
                changed.append((up_name, [
                    f"{up_file} is recorded as an upstream but no longer exists - every reference "
                    f"into it is stranded"
                ]))
                continue
        if not recorded:
            warnings.append(f"{up_file}: no sha256 recorded - cannot tell whether it changed")
            continue
        if current == recorded:
            unchanged.append(up_name)
            continue
        details = [f"recorded {recorded}, now {current}"]
        details.extend(_why_lines(docs_dir, up_name, entry))
        recorded_items = entry.get("items")
        if isinstance(recorded_items, dict):
            # Exact: the stamp recorded every item with its body hash, so the
            # delta is item by item - no git, no guessing from references.
            details.extend(_item_delta_lines(index, docs_dir, up_name, recorded_items, my_refs,
                                             "the snapshot recorded at the last write"))
            changed.append((up_name, details))
            continue
        # No item snapshot in the stamp. Every recorded sha256 is a text hash a
        # committed revision of the upstream can match, so history is tried
        # first: a hit gives the same exact delta (ledger IMP-083, aicf LSN-065).
        found, rev, old_items = _recover_items_from_git(docs_dir, up_name, recorded)
        if found == "hit" and old_items is not None:
            details.extend(_item_delta_lines(
                index, docs_dir, up_name, old_items, my_refs,
                f"revision {str(rev)[:8]} of docs/{up_name}, recovered from git (its content "
                f"matches the hash this stamp recorded)"))
            details.append("re-stamping this file (docs_index.py --stamp) records the items map, "
                           "so the next reconcile needs no git")
            changed.append((up_name, details))
            continue
        if found == "miss":
            details.append(
                f"git: no committed revision of docs/{up_name} carries the content this stamp "
                f"recorded (an uncommitted stamp, or history that never held it) - nothing "
                f"exact could be recovered"
            )
        # Fallback: no item snapshot. The artifact's own references stand in for
        # the old upstream set, which is exact only where the artifact covers the
        # family completely (a blocking trace-or-defer gate); elsewhere the
        # residue mixes "new upstream" with "never covered" and says so.
        by_family: dict[str, set[str]] = {}
        for def_name, (def_file, _line) in index.definitions.items():
            if def_file == up_name:
                by_family.setdefault(_family_of_definition(def_name, index), set()).add(def_name)
        touched = False
        for family in sorted(by_family):
            defs = by_family[family]
            refs = {r for fam, r in my_refs if fam == family}
            if not refs:
                continue
            shared = refs & defs
            # "removed" means gone from the corpus, not merely absent from THIS
            # upstream: a TST defined in a container shard is not missing just
            # because the system TEST-STRATEGY.yaml does not carry it.
            removed = sorted(
                (r for r in refs if r not in index.definitions and r not in index.retired_ids),
                key=_id_sort_key,
            )
            added = sorted(defs - refs, key=_id_sort_key) if shared else []
            deferred_here = [a for a in added if _deferred_match(a, deferred)]
            added = [a for a in added if a not in deferred_here]
            if added or removed or deferred_here:
                touched = touched or bool(added or removed)
                bits = []
                if added and len(shared) * 2 >= len(defs):
                    # This artifact covers most of the family: the rest is new or dropped.
                    bits.append(
                        f"{len(added)} defined upstream that this file neither references nor defers "
                        f"({join_ids(added, 8)}) - new since it was written, or never covered: "
                        f"no item snapshot was recorded, so the two cannot be told apart"
                    )
                elif added:
                    # A subset by design (a shard, a narrow consumer): counts only.
                    bits.append(
                        f"references {len(shared)} of {len(defs)} defined upstream "
                        f"(a subset by design - the {len(added)} others are not listed)"
                    )
                if removed:
                    bits.append(f"{len(removed)} referenced here but no longer defined ({join_ids(removed, 8)})")
                if deferred_here:
                    bits.append(f"{len(deferred_here)} deferred here, not counted")
                details.append(f"{family}: " + "; ".join(bits))
        details.append(
            "bodies edited as well as the sets above" if touched
            else "only bodies changed - every id/name this artifact references still exists; "
                 "its content may no longer match"
        )
        details.append(
            "which items changed cannot be named: this file's stamp records no per-item "
            "hashes - re-stamping it (docs_index.py --stamp) records them for next time"
        )
        changed.append((up_name, details))

    if not changed:
        print(f"[OK] {label} is built against the current upstreams ({len(unchanged)} unchanged).")
        print_findings([], warnings)
        print_next("nothing required.", show_glossary=not warnings)
        return 0
    print(
        f"[FAIL] {label} was built against older upstreams - {len(changed)} of "
        f"{len(changed) + len(unchanged)} changed since it was written, so what it "
        f"says about them may be stale."
    )
    print("\nUPSTREAMS THAT MOVED:")
    for up_name, details in changed:
        print(f"  * docs/{up_name}:")
        for d in details:
            print(f"      * {d}")
    if unchanged:
        print(f"  * unchanged: {', '.join(sorted(unchanged))}")
    print_findings([], warnings)
    print_next(
        f"{_reconcile_command(name)}  (reviews only what moved - no full interview - then "
        f"re-stamps the provenance)",
    )
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_docs_dir(args: argparse.Namespace) -> Path:
    if args.docs_dir:
        return Path(args.docs_dir)
    root = args.project_root or os.environ.get("CLAUDE_PROJECT_DIR") or "."
    return Path(root) / "docs"


def _edited_path_from_stdin() -> Optional[str]:
    """Read the PostToolUse JSON event from stdin and pull out the file path.

    Tolerant of schema variation: tries ``tool_input.file_path`` /
    ``tool_input.path`` and the top-level fallbacks. Returns None on empty or
    unparseable input (manual ``--hook`` invocation), which the caller treats
    as "nothing relevant changed".
    """
    raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    if not raw.strip():
        return None
    try:
        event = json.loads(raw)
    except (ValueError, TypeError):
        return None
    ti = event.get("tool_input") or {}
    for key in ("file_path", "path", "filePath"):
        val = ti.get(key) or event.get(key)
        if val:
            return str(val)
    return None


def _path_is_relevant(file_path: str) -> bool:
    """True if ``file_path``'s edit should trigger a regen.

    Canonical docs move line ranges; shard writes (``UX__x.yaml``,
    ``TASKS__cid.json``) move symbols and edges; the allow-list changes the
    retired set. All refresh.
    """
    p = Path(file_path)
    return "docs" in p.parts and (
        _is_canonical(p.name) or _is_shard(p.name) or p.name == ALLOW_FILENAME
    )


def _force_utf8_stdio() -> None:
    """Best-effort: keep prints working on a non-UTF-8 console (e.g. Windows cp1252).

    ``--show`` streams raw doc text (em-dashes, arrows), which would otherwise
    crash on a cp1252 console.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


def _check_warnings(index: DocIndex) -> "list":
    """The WARNINGS section of ``--check``: warn-first dangling references
    (grouped by class when more than four share it) plus index warnings."""
    items: list = []
    warn_family = [r for r in index.dangling_warnings if not r.key]
    warn_named = [r for r in index.dangling_warnings if r.key]
    if warn_family:
        by_prefix: dict[str, list[Reference]] = {}
        for r in warn_family:
            by_prefix.setdefault(r.id.split("-", 1)[0], []).append(r)
        for prefix, refs in by_prefix.items():
            if len(refs) > 4:
                items.append((
                    f"{len(refs)} {prefix} id(s) are referenced but no document defines them "
                    f"(a family that does not fail --check yet)",
                    [_ref_line(r) for r in refs],
                ))
            else:
                for r in refs:
                    items.append(
                        f"{r.id} is referenced at {r.file}:{r.line} (in {r.container}) but no "
                        f"document defines it (a family that does not fail --check yet)"
                    )
    if warn_named:
        if len(warn_named) > 4:
            items.append((
                f"{len(warn_named)} named reference(s) (entity / work unit / component / task) "
                f"resolve to no definition - the field names something no artifact defines",
                [_ref_line(r) for r in warn_named],
            ))
        else:
            for r in warn_named:
                items.append(
                    f"'{r.id}' named in {r.key} at {r.file}:{r.line} (in {r.container}) is defined "
                    f"by no artifact - rename it or add the definition"
                )
    items.extend(index.warnings)
    return items


def main(argv: "Optional[list[str]]" = None) -> int:
    _force_utf8_stdio()
    ap = argparse.ArgumentParser(description="SDLC docs/INDEX.yaml generator.")
    ap.add_argument("--docs-dir", help="Path to the docs directory (default: <root>/docs).")
    ap.add_argument("--project-root", help="Project root (default: $CLAUDE_PROJECT_DIR or cwd).")
    ap.add_argument(
        "--hook",
        action="store_true",
        help="PostToolUse mode: read the event from stdin and regenerate only when a doc or shard changed.",
    )
    ap.add_argument(
        "--show", metavar="SYMBOL", help="Print one symbol's [start,end] line slice and exit."
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="Integrity gate: rebuild the index and exit non-zero if any reference is dangling.",
    )
    ap.add_argument(
        "--refs",
        metavar="SYMBOL",
        help="Print a symbol/id's blast-radius: outbound refs, inbound referenced_by, dangling within.",
    )
    ap.add_argument(
        "--find",
        nargs="+",
        metavar="FILTER",
        help="Predicate search over symbols. Filters: kind=, context=, file=, text=, references=, referenced_by=.",
    )
    ap.add_argument(
        "--hash", metavar="FILE",
        help="Print the 16-hex content hash generated_from / upstream_provenance record for FILE.",
    )
    ap.add_argument(
        "--drift", metavar="ARTIFACT",
        help="Compare ARTIFACT's recorded upstream_provenance with the upstreams' current hashes "
             "(item by item from the stamp's items map, else from the committed revision whose "
             "hash the stamp recorded, else from the artifact's own references).",
    )
    ap.add_argument(
        "--stale", action="store_true",
        help="List every artifact whose recorded upstreams moved, in the order to reconcile "
             "them, each with its owning skill's --reconcile command (exit 1 when any).",
    )
    ap.add_argument(
        "--items", metavar="UPSTREAM",
        help="Print every item UPSTREAM defines with its body hash (what --stamp records).",
    )
    ap.add_argument(
        "--stamp", metavar="ARTIFACT",
        help="Rewrite ARTIFACT's metadata.upstream_provenance with sha256 + per-item hashes "
             "of every upstream it records (plus each --upstream). Writes only ARTIFACT.",
    )
    ap.add_argument(
        "--upstream", action="append", default=[], metavar="FILE",
        help="With --stamp: an upstream to record (docs/<file>); repeatable.",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="With --items / --stamp / --stale: machine-readable output.",
    )
    args = ap.parse_args(argv)

    docs_dir = _resolve_docs_dir(args)

    if args.stale:
        if not docs_dir.is_dir():
            print(f"[docs-stale] no docs dir: {docs_dir}", file=sys.stderr)
            return 2
        return stale_report(docs_dir, as_json=args.json)

    if args.items:
        if not docs_dir.is_dir():
            print(f"[docs-items] no docs dir: {docs_dir}", file=sys.stderr)
            return 2
        target = _locate(args.items, docs_dir)
        if not target.is_file():
            print(f"[docs-items] cannot read {args.items}: no such file (looked in {docs_dir})", file=sys.stderr)
            return 2
        index = build_index(docs_dir)
        items = items_of(index, docs_dir, target.name)
        if args.json:
            print(json.dumps({"file": f"docs/{target.name}", "sha256": content_hash(target),
                              "items": items}, indent=2, sort_keys=True))
        else:
            print(f"# {len(items)} item(s) defined in docs/{target.name} (sha256 {content_hash(target)})")
            for k in sorted(items, key=_id_sort_key):
                print(f"{_flow(k)}: {items[k]}")
        return 0

    if args.stamp:
        if not docs_dir.is_dir():
            print(f"[docs-stamp] no docs dir: {docs_dir}", file=sys.stderr)
            return 2
        return stamp_artifact(docs_dir, args.stamp, args.upstream, as_json=args.json)

    if args.hash:
        path = _locate(args.hash, docs_dir)
        try:
            print(content_hash(path))
        except (OSError, UnicodeDecodeError) as e:
            print(f"[docs-hash] cannot read {args.hash}: {e}", file=sys.stderr)
            return 2
        return 0

    if args.drift:
        if not docs_dir.is_dir():
            print(f"[docs-drift] no docs dir: {docs_dir}", file=sys.stderr)
            return 2
        return drift_report(docs_dir, args.drift)

    if args.check:
        if not docs_dir.is_dir():
            print(f"[docs-check] no docs dir: {docs_dir}", file=sys.stderr)
            return 2
        index = build_index(docs_dir)
        warnings = _check_warnings(index)
        if index.dangling:
            print(f"[FAIL] {len(index.dangling)} id(s) are referenced in the "
                  f"documents but defined nowhere. Anything following those "
                  f"references will not find what it is looking for.")
            print_findings(
                [f"{ref.id} is referenced at {ref.file}:{ref.line} "
                 f"(in {ref.container}) but no document defines it"
                 for ref in index.dangling],
                warnings,
                blocking_header="BROKEN REFERENCES",
            )
            print_next("/sdlc:repair  (works out which document is actually wrong)")
            return 1
        print("[OK] every id referenced in the documents is defined somewhere.")
        print_findings([], warnings)
        print_next("nothing required.", show_glossary=bool(warnings))
        return 0

    if args.refs:
        hit = find_symbol_refs(docs_dir, args.refs)
        if hit is None:
            print(f"[docs-refs] unknown symbol/id: {args.refs}", file=sys.stderr)
            return 1
        resolved, out_refs, in_refs, within = hit
        print(f"# refs for {resolved}" + (f" (asked as {args.refs})" if resolved != args.refs else ""))
        print(f"references_out: [{', '.join(out_refs)}]")
        print(f"referenced_by: [{', '.join(in_refs)}]")
        if within:
            print("dangling_within:")
            for ref in within:
                print(f"  - {_ref_line(ref)}")
        return 0

    if args.find:
        filters: dict[str, str] = {}
        for tok in args.find:
            if "=" not in tok:
                print(f"[docs-find] bad filter (expected key=value): {tok}", file=sys.stderr)
                return 2
            key, val = tok.split("=", 1)
            key = key.strip()
            if key not in ("kind", "context", "file", "text", "references", "referenced_by"):
                print(f"[docs-find] unknown filter key: {key}", file=sys.stderr)
                return 2
            filters[key] = val.strip()
        matches = find_symbols(docs_dir, **filters)  # type: ignore[arg-type]
        for name, sym in matches:
            print(f"{name}\t{sym.file}:{sym.start}-{sym.end}\t{sym.kind}\t{sym.summary}")
        print(f"# {len(matches)} match(es)", file=sys.stderr)
        return 0

    if args.show:
        if not docs_dir.is_dir():
            print(f"[docs-show] no docs dir: {docs_dir}", file=sys.stderr)
            return 2
        index = build_index(docs_dir)
        sym, candidates = resolve_symbol(index, args.show)
        if sym is None:
            if candidates:
                print(f"[docs-show] '{args.show}' names {len(candidates)} work units - ask for one "
                      f"of: {', '.join(candidates)}", file=sys.stderr)
            else:
                print(f"[docs-show] symbol not found: {args.show}", file=sys.stderr)
            return 1
        path = docs_dir / sym.file
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            print(f"[docs-show] cannot read {path}: {e}", file=sys.stderr)
            return 2
        print(f"# {path}:{sym.start}-{sym.end}")
        sys.stdout.write("\n".join(lines[sym.start - 1 : sym.end]) + "\n")
        return 0

    if args.hook:
        edited = _edited_path_from_stdin()
        if edited is None or not _path_is_relevant(edited):
            return 0  # unrelated edit (or no event) — silent no-op
        # Resolve docs dir from the edited path itself when not pinned, so the
        # hook works regardless of cwd.
        if not args.docs_dir and not args.project_root:
            parts = Path(edited).parts
            docs_dir = Path(*parts[: parts.index("docs") + 1])

    if not docs_dir.is_dir():
        # Nothing to index yet (docs/ not created) — not an error.
        return 0
    target = write_index(docs_dir)
    _refresh_statusboard(docs_dir.parent, quiet=args.hook)
    if not args.hook:
        print(f"[docs-index] wrote {target}")
    return 0


def _refresh_statusboard(project_root: Path, quiet: bool) -> None:
    """Regenerate the statusboard whenever the index is regenerated.

    The two are refreshed by the same event, and the hook can only have ONE
    reader of the event on stdin - so the index generator invokes the board
    rather than the settings file chaining a second command that would find no
    event to read. Entirely best-effort: the board needs pyyaml and this script
    deliberately does not, so a project without it keeps a working index and
    simply has no board.
    """
    script = project_root / ".claude" / "sdlc" / "statusboard.py"
    if not script.is_file():
        return
    try:
        import subprocess

        subprocess.call(
            [sys.executable, str(script), "--path", str(project_root)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass  # never let a missing interpreter break the index hook


if __name__ == "__main__":
    sys.exit(main())
