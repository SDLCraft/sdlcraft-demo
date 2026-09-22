#!/usr/bin/env python3
"""statusboard.py - generate the two SDLC status files from the artifacts.

WHY THIS EXISTS
---------------
Everything a person or an agent needs to know about a project's pipeline state
already exists somewhere: open questions in `docs/PRD.yaml`, caveats in each
artifact's `*_warnings`, spec defects in the findings queue, blocked work in the
codegen ledger. It is just scattered across a dozen files, so in practice nobody
reads it - which is how a project's `CLAUDE.md` ends up with hand-written status
notes that go stale the day after they are written.

This script derives that state instead, into two files with different jobs:

  .claude/rules/sdlc-statusboard.md   Loaded into EVERY session, so it is
      capped hard. It carries verbatim only what is open and would mislead an
      agent that did not know it: the pipeline table, blocked work, open
      questions, open findings, and the caveats marked `impact: risk`. Caveats
      marked `downstream` get one line each; everything else is counted.

  .claude/sdlc/STATUS.md              Not auto-loaded. Every warning verbatim,
      grouped by artifact and located, plus the resolved ones, the deferrals,
      the parking lot and the full per-task ledger.

Both are GENERATED WHOLESALE on every run. Nothing is ever appended, so a stale
line cannot survive, and hand-edits are overwritten by design.

WHAT MAKES THE SPLIT WORK
-------------------------
A typed warning (CLAUDE.md section 2) carries `kind`, `status` and `impact`.
Those three are what let this script separate a live caveat from settled
bookkeeping. A legacy `"WRN-NNN: <text>"` string reads as
`{kind: note, status: open, impact: local}`, so an unmigrated project gets an
honest board with counts rather than a wrong one - run
`.claude/sdlc/migrate_warnings.py` to sharpen it.

The grammar itself is NOT re-implemented here: this script imports the canonical
block from `warning_item.py`, so an entry every validator reports as ignored is
ignored on this board too, and the ones no reader can use are counted in
STATUS.md instead of being presented as live caveats (ledger IMP-110).

Usage:
    python statusboard.py                 # rewrite both files
    python statusboard.py --check         # exit 1 if they are stale; write nothing
    python statusboard.py --dry-run       # print the ambient board, write nothing
    python statusboard.py --detail        # print the full board, write nothing

Exit codes:
    0 - written (or, with --check, up to date).
    1 - with --check: the files are stale and need regenerating.
    2 - could not read the project (no docs/ directory).
    3 - required dependency missing (pyyaml).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from hashlib import sha256
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "[FAIL] pyyaml is not installed - this script cannot read the artifacts.\n"
        "       Install it with 'pip install pyyaml' and run again.\n"
    )
    raise SystemExit(3)

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"
TIER1_REL = ".claude/rules/sdlc-statusboard.md"
TIER2_REL = ".claude/sdlc/STATUS.md"
STATE_REL = ".claude/skills-state"
MARKER_REL = ".claude/sdlc/sdlc-plugin.json"

# The public free edition ships setup through arch; these stages are Pro-only.
# setup records which edition it installed in the marker (`edition`).
PRO_STAGES = ("test", "task", "code")
FULL_ONLY = "full edition only"   # their status in a demo (free) install

# The ambient file is loaded into every session, so its size is a standing tax.
MAX_LINES = 150
MAX_BYTES = 10 * 1024
MAX_IDS_INLINE = 8

# stage -> canonical artifact. `None` means the stage produces no docs/ artifact.
STAGES = [
    ("prd", "PRD.yaml"),
    ("ux", "UX.yaml"),
    ("design", "DESIGN.yaml"),
    ("data", "DATA-MODEL.yaml"),
    ("api", "API.yaml"),
    ("arch", "ARCH.yaml"),
    ("test", "TEST-STRATEGY.yaml"),
    ("task", "TASKS.json"),
    ("code", "CODE-MANIFEST.json"),
]
SUCCESSOR = dict(zip([s for s, _ in STAGES], [s for s, _ in STAGES][1:] + [None]))

# A finding is "still open" in exactly the sense the queue's own writer uses.
OPEN_STATUSES = ("open", "triaged")


_FINDINGS_MOD = []


def findings_helper():
    """findings.py, if it is next to this script - else None.

    What a finding still owes (an open re-invoke resolution's
    downstream_rerun, an unverified propagation hop) is a rule with one owner,
    and doctor.py already reads it there. A second copy of that condition here
    is the defect IMP-110 records for the WRN parse in this same file, so the
    board imports the helper instead: `.claude/sdlc/findings.py` beside an
    installed board, `../repair/findings.py` beside the plugin's. Absent or
    unimportable - an older install, a project that never ran setup - the board
    degrades to what it said before: every open finding routes to /sdlc:repair.
    """
    if _FINDINGS_MOD:
        return _FINDINGS_MOD[0]
    import importlib.util
    here = Path(__file__).resolve().parent
    mod = None
    for cand in (here / "findings.py", here.parent / "repair" / "findings.py"):
        if not cand.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("sdlc_findings_for_board", cand)
            if spec is None or spec.loader is None:
                continue
            candidate = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(candidate)
            if hasattr(candidate, "awaiting_registry"):
                mod = candidate
                break
        except Exception:
            continue
    _FINDINGS_MOD.append(mod)
    return mod


_WARNING_MOD = []


def warning_parser():
    """warning_item.py, if it is next to this script - else None.

    The `*_warnings` grammar has ONE implementation (CLAUDE.md section 2): the
    canonical block in `warning_item.py`, embedded byte-identical in every
    validator and pinned there by `lint_claude_md.py`. A private copy here read
    as live caveats the entries all of those copies report as ignored, which is
    the defect ledger IMP-110 records - the same shape IMP-132 fixed one
    function above. So the board imports it: `.claude/sdlc/warning_item.py`
    beside an installed board, `../repair/warning_item.py` beside the plugin's.
    Absent or unimportable - an older install - the board degrades to reading
    each entry as written (`_as_written`), because the docs hook regenerates
    this file on every write and an import failure must never raise.
    """
    if _WARNING_MOD:
        return _WARNING_MOD[0]
    import importlib.util
    here = Path(__file__).resolve().parent
    mod = None
    for cand in (here / "warning_item.py", here.parent / "repair" / "warning_item.py"):
        if not cand.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location("sdlc_wrn_for_board", cand)
            if spec is None or spec.loader is None:
                continue
            candidate = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(candidate)
            if hasattr(candidate, "parse_warnings"):
                mod = candidate
                break
        except Exception:
            continue
    _WARNING_MOD.append(mod)
    return mod


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def load(path):
    """One artifact as a mapping, or None when it is absent or unreadable."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        doc = json.loads(raw) if path.suffix == ".json" else yaml.safe_load(raw)
    except (ValueError, yaml.YAMLError):
        return None
    return doc if isinstance(doc, dict) else None


def read_edition(root):
    """(edition, pro_url) from setup's marker. A missing or older marker is the
    full plugin, so nothing about the board changes for it."""
    marker = load(root / MARKER_REL) or {}
    edition = "free" if marker.get("edition") == "free" else "pro"
    return edition, (str(marker["pro_url"]) if marker.get("pro_url") else None)


def read_auto_commit(root):
    """True when the project opted in to every skill run committing its own
    files at close (setup's marker, `auto_commit.mode`). A missing or older
    marker is off, so nothing about the board changes for it."""
    marker = load(root / MARKER_REL) or {}
    block = marker.get("auto_commit")
    return isinstance(block, dict) and block.get("mode") == "on"


AUTO_COMMIT_LINE = ("Every `/sdlc:*` run commits its own files when it closes "
                    "(`python .claude/sdlc/autocommit.py mode` to change that).")


def _older(installed, running):
    """Dotted numbers compare part by part as integers (0.10.0 > 0.9.14);
    anything that does not parse counts as older when the two differ."""
    try:
        return (tuple(int(p) for p in str(installed).split("."))
                < tuple(int(p) for p in str(running).split(".")))
    except ValueError:
        return str(installed) != str(running)


def _plugin_root(explicit):
    """The running plugin's root: --plugin-root, else $CLAUDE_SKILL_DIR/../..
    Only a folder with a skills/ directory counts; None when neither names one."""
    candidates = [Path(explicit)] if explicit else []
    if os.environ.get("CLAUDE_SKILL_DIR"):
        candidates.append(Path(os.environ["CLAUDE_SKILL_DIR"]).parent.parent)
    for root in candidates:
        if (root / "skills").is_dir():
            return root
    return None


def collect_setup_lag(root, state, plugin_root=None):
    """The installed helpers' plugin version when they lag the plugin in use,
    else None (ledger IMP-108).

    Evidence, first that exists: the plugin in view (its version, and
    docs_index.py's CAPABILITY_VERSION against the marker's), else the newest
    run lessons.py recorded from a real plugin. The fallback is what keeps the
    board steady: the docs hook regenerates it with no plugin in view, and a
    line that came and went with the invoker would churn the file. The value
    names only the installed version, so both sources render the same line.
    """
    marker = load(root / MARKER_REL)
    if not marker:
        return None
    installed = marker.get("plugin_version")
    shown = str(installed) if installed else "an older plugin"
    plugin = _plugin_root(plugin_root)
    if plugin is not None:
        manifest = load(plugin / ".claude-plugin" / "plugin.json") or {}
        running = manifest.get("version")
        if installed and running and _older(installed, running):
            return shown
        cap = (marker.get("helpers") or {}).get("docs_index")
        try:
            text = (plugin / "skills" / "setup" / "docs_index.py").read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        m = re.search(r"^CAPABILITY_VERSION\s*=\s*[\"']?(\d+)", text, re.M)
        if cap is not None and m and _older(cap, m.group(1)):
            return shown
        return None
    queue = load(state / "sdlc-lessons.yaml") or {}
    runs = [r for r in (queue.get("runs") or []) if isinstance(r, dict)
            and r.get("plugin_version")
            and r.get("plugin_version_source") in ("manifest", "flag")]
    if not runs or not installed:
        return None
    newest = max(runs, key=lambda r: str(r.get("finished_at") or ""))
    return shown if _older(installed, newest["plugin_version"]) else None


def norm_warnings(entries, label, source):
    """One artifact's `*_warnings` list as dicts, plus what could not be read.

    Returns `(items, refused)`. This is an ADAPTER over the canonical parser,
    not a second reading of the grammar: it adds the `source` and `line` a
    WarningItem does not carry, and nothing else. `refused` carries one row per
    entry the parser drops, `blocking` telling its two channels apart - a
    string that is not a warning at all is an error that fails the artifact,
    while a malformed mapping is only reported and ignored. Neither becomes a
    caveat, because no validator reads them either; STATUS.md counts them.
    """
    entries = entries or []
    parser = warning_parser()
    if parser is None:
        return [_as_written(e, source) for e in entries], []
    items, errors, _shape = parser.parse_warnings(entries, label)
    out = [{"id": it.id, "text": it.text, "kind": it.kind, "status": it.status,
            "impact": it.impact, "defers": list(it.defers),
            "resolution": it.resolution, "resolved_on": it.resolved_on,
            "source": source, "typed": it.typed} for it in items]
    kept = {it.where for it in items}
    refused = []
    for i in range(len(entries)):
        where = "%s[%d]" % (label, i)
        if where in kept:
            continue
        refused.append({
            "where": "docs/%s %s" % (source, where),
            # The error messages open with `<where>:`, the shape reports with
            # `<where> ` - so the prefix test cannot confuse [1] with [10].
            "blocking": any(m.startswith(where + ":") for m in errors),
        })
    return out, refused


def _as_written(entry, source):
    """One entry exactly as the artifact writes it - the degraded path only.

    Reached when `warning_item.py` is not installed beside this script. It
    judges nothing: no field is checked against the canonical vocabulary and no
    entry is dropped, so an older install gets a board built from what the
    artifact actually says rather than from a second, drifting copy of rules
    that live somewhere else.
    """
    if isinstance(entry, dict):
        return {"id": str(entry.get("id") or "").strip() or "WRN-???",
                "text": str(entry.get("text") or "").strip(),
                "kind": str(entry.get("kind") or "note").strip(),
                "status": str(entry.get("status") or "open").strip(),
                "impact": str(entry.get("impact") or "local").strip(),
                "defers": [str(d).strip() for d in (entry.get("defers") or [])
                           if str(d).strip()],
                "resolution": entry.get("resolution"),
                "resolved_on": entry.get("resolved_on"),
                "source": source, "typed": True}
    s = str(entry or "").strip()
    wid, _, text = s.partition(":")
    return {"id": wid.strip() or "WRN-???", "text": text.strip() or s,
            "kind": "note", "status": "open", "impact": "local", "defers": [],
            "resolution": None, "resolved_on": None, "source": source,
            "typed": False}


def line_of(path, needle):
    """1-based line where `needle` first appears, so a reader can slice to it."""
    try:
        for n, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            if needle in line:
                return n
    except (OSError, UnicodeDecodeError):
        pass
    return None


def artifact_files(docs):
    return sorted([p for p in docs.glob("*.yaml") if p.name != "INDEX.yaml"]
                  + list(docs.glob("*.json")))


def collect_warnings(docs):
    """Every warning in every artifact, normalized and located."""
    return collect_warnings_detail(docs)[0]


def collect_warnings_detail(docs):
    """`(warnings, refused)` across every artifact - see `norm_warnings`."""
    out, refused = [], []
    for path in artifact_files(docs):
        doc = load(path)
        if not doc:
            continue
        for key, value in doc.items():
            if not key.endswith("_warnings") or not isinstance(value, list):
                continue
            items, bad = norm_warnings(value, key, path.name)
            for w in items:
                w["line"] = line_of(path, w["id"])
            out.extend(items)
            refused.extend(bad)
    return out, refused


def collect_pipeline(docs, state, edition="pro"):
    """One row per stage: artifact, status, version, shard count.

    In the demo (free) edition a Pro-only stage with no artifact reads "full
    edition only", never "not started": nothing in this install can start it.
    """
    rows = []
    prd = load(docs / "PRD.yaml") or {}
    scope = (prd.get("pipeline_scope") or {}) if isinstance(prd, dict) else {}
    for stage, filename in STAGES:
        path = docs / filename
        doc = load(path) if path.exists() else None
        entry = scope.get(stage) if isinstance(scope, dict) else None
        declared_na = isinstance(entry, dict) and entry.get("applicable") is False
        if doc is None:
            rows.append({"stage": stage, "artifact": None, "shards": 0,
                         "status": "not applicable" if declared_na
                                   else FULL_ONLY if edition == "free" and stage in PRO_STAGES
                                   else "not started",
                         "version": None})
            continue
        md = doc.get("metadata") or {}
        version = next((str(v) for k, v in md.items()
                        if k.endswith("_version") and v), None)
        status = str(md.get("status") or "?")
        if str(md.get("applicability") or "") == "not_applicable" or declared_na:
            status = "not applicable"
        stem = filename.rsplit(".", 1)[0]
        shards = len([p for p in docs.glob(stem + "__*") if p.is_file()])
        rows.append({"stage": stage, "artifact": filename, "shards": shards,
                     "status": status, "version": version})
    rows.append(code_row(state))
    return [r for r in rows if r]


def code_row(state):
    """Codegen progress, from the execution ledger rather than an artifact."""
    ledger = load(state / "sdlc-code.state.yaml")
    if not ledger:
        return None
    tasks = ledger.get("tasks") or {}
    if not isinstance(tasks, dict):
        return None
    done = sum(1 for t in tasks.values()
               if isinstance(t, dict) and t.get("status") == "done")
    return {"stage": "code (ledger)", "artifact": "%d/%d tasks" % (done, len(tasks)),
            "shards": 0, "status": str(ledger.get("status") or "?"), "version": None}


def collect_blocked(state):
    """Every unit the codegen run could not finish, with why."""
    out = []
    ledger = load(state / "sdlc-code.state.yaml") or {}
    tasks = ledger.get("tasks") if isinstance(ledger.get("tasks"), dict) else {}
    for qid, t in sorted((tasks or {}).items()):
        if not isinstance(t, dict):
            continue
        status = str(t.get("status") or "")
        if status not in ("failed", "blocked", "stuck"):
            continue
        why = str(t.get("reason") or t.get("stuck_reason")
                  or t.get("last_error") or "no reason recorded").strip()
        out.append({"id": qid, "status": status, "why": why,
                    "attempts": t.get("attempts")})
    stuck_dir = state / "sdlc-code" / "stuck"
    if stuck_dir.is_dir():
        known = {b["id"] for b in out}
        for report in sorted(stuck_dir.glob("*")):
            qid = report.stem.replace("-", "/", 1)
            if qid not in known:
                out.append({"id": qid, "status": "stuck",
                            "why": "see %s" % report.as_posix(), "attempts": None})
    return out


def collect_questions(docs):
    """PRD open questions that nobody has decided yet."""
    prd = load(docs / "PRD.yaml") or {}
    oq = prd.get("open_questions") or {}
    out = []
    if not isinstance(oq, dict):
        return out
    for bucket in ("undecided_decisions", "parking_lot"):
        for q in oq.get(bucket) or []:
            if not isinstance(q, dict) or str(q.get("status") or "") != "open":
                continue
            out.append({"id": str(q.get("id") or "QUE-???"),
                        "text": str(q.get("question") or q.get("text") or "").strip(),
                        "blocks": [str(b) for b in (q.get("blocks") or [])],
                        "bucket": bucket})
    return out


def collect_findings(state):
    doc = load(state / "sdlc-findings.yaml") or {}
    helper = findings_helper()
    owed = {}
    if helper is not None:
        try:
            for _artifact, (fnd_id, _label, cmds) in (helper.awaiting_registry(doc) or {}).items():
                owed.setdefault(str(fnd_id), [str(c) for c in (cmds or [])])
        except Exception:
            owed = {}
    out = []
    for f in doc.get("findings") or []:
        # wontfix, deferred and duplicate are decided, not open: counting them
        # inflated the board's tally and sent the reader to /sdlc:repair for
        # work nobody owes.
        if not isinstance(f, dict) or str(f.get("status") or "") not in OPEN_STATUSES:
            continue
        # The queue writes `fnd_id`, not `id` (FINDINGS.schema.yaml); accept
        # both so a hand-written entry still shows up with its real id.
        fid = str(f.get("fnd_id") or f.get("id") or "FND-???")
        out.append({"id": fid,
                    "status": str(f.get("status") or "open"),
                    "kind": str(f.get("kind") or ""),
                    "summary": str(f.get("summary") or "").strip(),
                    "source": str(f.get("suspected_source") or ""),
                    "raised_by": str(f.get("raised_by") or ""),
                    "evidence": [str(e) for e in (f.get("evidence") or [])],
                    "owed": owed.get(fid, [])})
    return out


def collect_lessons(state, root=None):
    """Open lessons by id, plus the counts of what the maintainer's verdicts
    made of the rest - a lesson stays `open` only until a verdict reaches the
    project (lessons.py reconcile, at every skill close), so the board says
    what came back rather than counting every lesson as live."""
    doc = load(state / "sdlc-lessons.yaml") or {}
    installed = (load(root / MARKER_REL) or {}).get("plugin_version") if root else None
    out = {"open": [], "reopened": [], "collected": 0, "triaged": 0,
           "resolved_installed": 0, "resolved_pending": 0, "wontfix": 0, "dismissed": 0}
    for l in (doc.get("lessons") or []):
        if not isinstance(l, dict):
            continue
        # Same here: the lessons queue writes `lsn_id`.
        lid = str(l.get("lsn_id") or l.get("id") or "LSN-???")
        status = str(l.get("status") or "")
        if status == "open":
            # An open lesson carrying a verdict date recurred AFTER its
            # verdict: the fix regressed, or the call was wrong.
            (out["reopened"] if l.get("verdict_at") else out["open"]).append(lid)
        elif status == "resolved":
            fixed_in = l.get("fixed_in")
            pending = bool(fixed_in and installed and _older(installed, fixed_in))
            out["resolved_pending" if pending else "resolved_installed"] += 1
        elif status in out:
            out[status] += 1
    return out


def lessons_line(lessons):
    """The one board line: open ids, then what came back from the maintainer."""
    bits = []
    if lessons["open"]:
        bits.append("%d open (%s)" % (len(lessons["open"]), id_list(lessons["open"])))
    if lessons["reopened"]:
        bits.append("%d open again after a fix (%s)"
                    % (len(lessons["reopened"]), id_list(lessons["reopened"])))
    if lessons["triaged"]:
        bits.append("%d triaged upstream" % lessons["triaged"])
    if lessons["resolved_installed"]:
        bits.append("%d resolved (fix installed)" % lessons["resolved_installed"])
    if lessons["resolved_pending"]:
        bits.append("%d resolved upstream, not installed - run /sdlc:setup"
                    % lessons["resolved_pending"])
    if lessons["wontfix"]:
        bits.append("%d wontfix" % lessons["wontfix"])
    return ", ".join(bits)


def collect_integrity(docs):
    """Drift, dangling references, and acceptance criteria with no test."""
    notes = {"drift": [], "dangling": [], "uncovered_acr": []}
    index = load(docs / "INDEX.yaml") or {}
    hashes = {}
    for name, meta in (index.get("generated_from") or {}).items():
        if isinstance(meta, dict) and meta.get("sha256"):
            hashes[str(name)] = str(meta["sha256"])
    for path in artifact_files(docs):
        doc = load(path)
        if not doc:
            continue
        stale = []
        for up in ((doc.get("metadata") or {}).get("upstream_provenance") or []):
            if not isinstance(up, dict):
                continue
            name = Path(str(up.get("file") or "")).name
            recorded, current = str(up.get("sha256") or ""), hashes.get(name)
            if recorded and current and recorded != current:
                stale.append(name)
        if stale:
            notes["drift"].append({"file": path.name, "behind": stale})
    for entry in (index.get("dangling") or []):
        notes["dangling"].append(str(entry))

    prd = load(docs / "PRD.yaml") or {}
    acrs = set()
    for item in ((prd.get("success_metrics") or {}).get("acceptance_criteria") or []):
        token = str(item).strip().partition(":")[0].strip()
        if token.startswith("ACR-"):
            acrs.add(token)
    covered = set()
    for path in docs.glob("TEST-STRATEGY*.yaml"):
        doc = load(path) or {}
        for key, value in doc.items():
            covered |= _covers(value)
    notes["uncovered_acr"] = sorted(a for a in acrs if a not in covered)
    return notes


def _covers(node):
    """Every ACR id named in any `covers` list anywhere in a test strategy."""
    out = set()
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "covers" and isinstance(value, list):
                out |= {str(v).strip() for v in value if str(v).startswith("ACR-")}
            else:
                out |= _covers(value)
    elif isinstance(node, list):
        for item in node:
            out |= _covers(item)
    return out


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def trim(text, width=140):
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[:width - 1].rstrip() + "…"


def id_list(ids):
    ids = list(ids)
    if len(ids) <= MAX_IDS_INLINE:
        return ", ".join(ids)
    return "%s, +%d more" % (", ".join(ids[:MAX_IDS_INLINE]),
                             len(ids) - MAX_IDS_INLINE)


def wrap(text, width=74, indent="  "):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(indent + cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(indent + cur)
    return lines


def next_step(pipeline, findings, blocked, questions, pro_url=None, edition="pro"):
    """The single best next command, decided here rather than copied.

    Order matches CLAUDE.md section 14: an unfinished artifact first, then
    recorded defects, then the pipeline successor - including rule 2's
    exception, which this file used to miss (ledger IMP-132). A finding
    /sdlc:repair has already localized and handed off is not waiting on
    repair; it is waiting on the --reconcile it owes, which is what doctor.py
    names on the same queue. Sending the reader back into repair mid-chain
    stalls the chain.
    """
    for row in pipeline:
        if row["status"] == "draft":
            return ("/sdlc:%s" % row["stage"].split()[0],
                    "%s is still a draft - no later stage will consume it."
                    % row["artifact"])
    if findings:
        owed = [c for f in findings for c in f.get("owed") or []]
        if owed and all(f.get("owed") for f in findings):
            cmd = owed[0]
            skill = cmd.split("/sdlc:", 1)[-1].split()[0] if "/sdlc:" in cmd else ""
            if edition == "free" and skill in PRO_STAGES:
                return (None, "%d finding(s) wait on %s, which ships in the full "
                        "edition%s." % (len(findings), cmd,
                                        " (%s)" % pro_url if pro_url else ""))
            return (cmd, "%d finding(s) are waiting on this re-invocation; running "
                    "it in a new session is what clears them." % len(findings))
        return ("/sdlc:repair",
                "%d finding(s) are open against this project's specs."
                % len(findings))
    if blocked:
        return ("/sdlc:code",
                "%d unit(s) did not finish; the run resumes where it stopped."
                % len(blocked))
    done = [r for r in pipeline if r["status"] in ("complete", "not applicable")]
    for row in pipeline:
        if row["status"] in ("not started",):
            return ("/sdlc:%s" % row["stage"], "it is the next stage that has no artifact.")
    pro_rows = [r for r in pipeline if r["status"] == FULL_ONLY]
    if questions:
        return ("/sdlc:prd",
                "every stage%s has an artifact, but %d question(s) are still open."
                % (" in this edition" if pro_rows else "", len(questions)))
    if pro_rows:
        return (None, "the specification is complete - test planning, the task "
                "graph and code generation are in the full edition%s."
                % (" (%s)" % pro_url if pro_url else ""))
    if len(done) >= len(pipeline):
        return (None, "every stage has an artifact and nothing is open.")
    return (None, "nothing is blocking.")


def render_tier1(data, stamp):
    """The ambient board. Capped; whatever does not fit spills to STATUS.md."""
    w = data["warnings"]
    risks = [x for x in w if x["status"] == "open" and x["impact"] == "risk"]
    down = [x for x in w if x["status"] == "open" and x["impact"] == "downstream"]
    other = [x for x in w if x["status"] == "open"
             and x["impact"] in ("local", "none")]

    L = ["# SDLC statusboard", ""]
    L += ["<!-- GENERATED by %s - do not hand-edit; every run rewrites it whole." % TIER2_REL.replace("STATUS.md", "statusboard.py"),
          "     %s -->" % stamp, ""]
    L += ["Where the pipeline stands and what is still unresolved. Every caveat in",
          "full, including the resolved ones: `%s`." % TIER2_REL, ""]
    if data.get("setup_lag"):
        L += ["**Setup is behind the plugin.** The helper scripts in `.claude/sdlc/` "
              "were installed by plugin %s and the plugin in use is newer, so skills "
              "run its own copies. Run `/sdlc:setup` once to update them."
              % data["setup_lag"], ""]
    if data.get("auto_commit"):
        L += [AUTO_COMMIT_LINE, ""]

    L += ["## Pipeline", "",
          "| Stage | Artifact | Status | v | Open caveats |",
          "|---|---|---|---|---|"]
    per_file = {}
    for x in w:
        if x["status"] == "open":
            per_file[x["source"]] = per_file.get(x["source"], 0) + 1
    for row in data["pipeline"]:
        art = row["artifact"] or "-"
        if row["shards"]:
            art += " (+%d shards)" % row["shards"]
        n = per_file.get(row["artifact"], 0)
        L.append("| %s | %s | %s | %s | %s |"
                 % (row["stage"], art, row["status"], row["version"] or "-",
                    n or "-"))
    L.append("")

    if data["blocked"]:
        L += ["## Blocked work - %d unit(s)" % len(data["blocked"]), ""]
        for b in data["blocked"]:
            head = "- **%s** *(%s%s)* -" % (
                b["id"], b["status"],
                ", attempt %s" % b["attempts"] if b.get("attempts") else "")
            L += [head] + wrap(trim(b["why"], 220))
        L.append("")

    if data["questions"]:
        L += ["## Open questions - %d (docs/PRD.yaml)" % len(data["questions"]), "",
              "Nobody has decided these. Do not assume an answer; ask, or record a",
              "finding with `.claude/sdlc/findings.py`.", ""]
        for q in data["questions"]:
            L += ["- **%s**" % q["id"]] + wrap(trim(q["text"], 400))
            if q["blocks"]:
                L.append("  *Blocks: %s.*" % id_list(q["blocks"]))
        L.append("")

    if data["findings"]:
        all_owed = all(f.get("owed") for f in data["findings"])
        L += ["## Open findings - %d%s" % (len(data["findings"]),
                                           "" if all_owed else "  (`/sdlc:repair`)"), ""]
        for f in data["findings"]:
            L += ["- **%s** *(%s%s)*%s%s" % (
                f["id"], f["status"], ", " + f["kind"] if f["kind"] else "",
                " - " + f["source"] if f["source"] else "",
                " - waiting on `%s`" % f["owed"][0] if f.get("owed") else "")]
            L += wrap(trim(f["summary"], 300))
        L.append("")

    if risks:
        L += ["## Risks - %d caveat(s), verbatim" % len(risks), ""]
        for x in risks:
            L += ["- **%s** *(%s, %s)*" % (x["id"], x["kind"], x["source"])]
            L += wrap(x["text"])
        L.append("")

    if down:
        L += ["## Downstream caveats - %d, one line each" % len(down), ""]
        for x in down:
            L.append("- **%s** *(%s, %s)* - %s"
                     % (x["id"], x["kind"], x["source"], trim(x["text"], 110)))
        L.append("")

    integ = data["integrity"]
    if integ["drift"] or integ["dangling"] or integ["uncovered_acr"]:
        L += ["## Integrity", ""]
        for d in integ["drift"]:
            L.append("- **%s** is behind %s: %s."
                     % (d["file"], "its upstream" if len(d["behind"]) == 1
                        else "%d upstreams" % len(d["behind"]),
                        id_list(d["behind"])))
        if integ["drift"]:
            L.append("  Re-run each stage above so its delta review can reconcile "
                     "the change.")
        if integ["dangling"]:
            L.append("- Dangling references: %d (%s)."
                     % (len(integ["dangling"]), id_list(integ["dangling"][:MAX_IDS_INLINE])))
        if integ["uncovered_acr"]:
            L.append("- Acceptance criteria with no covering test: %d (%s)."
                     % (len(integ["uncovered_acr"]), id_list(integ["uncovered_acr"])))
        L.append("")

    if other:
        counts = {}
        for x in other:
            counts[x["source"]] = counts.get(x["source"], 0) + 1
        typed_any = any(x["typed"] for x in w)
        L += ["## Other caveats - %d  (%s; full text in STATUS.md)"
              % (len(other), "local or bookkeeping" if typed_any
                 else "not yet triaged"), ""]
        if not typed_any:
            # Saying "bookkeeping" here would be a claim nobody made: on a corpus
            # of legacy strings every warning reads `local` by DEFAULT, not by a
            # decision. Say what is actually true.
            L += ["None of these carry a `kind`/`impact` yet, so they all read as",
                  "`local` by default rather than by anyone's judgement. Run",
                  "`python .claude/sdlc/migrate_warnings.py --all --dry-run` to see",
                  "what typing them would move onto this board.", ""]
        L.append(" | ".join("%s %d" % (k, v) for k, v in sorted(counts.items())))
        L.append("")

    cmd, why = data["next"]
    L += ["## Next", ""]
    L.append("`%s` - %s" % (cmd, why) if cmd else "Nothing is queued - %s" % why)
    if lessons_line(data["lessons"]):
        L += ["", "Lessons: %s - about the SDLC plugin itself, not this project."
              % lessons_line(data["lessons"])]
    L.append("")
    return cap(L, len(down), len(risks))


def cap(lines, n_down, n_risk):
    """Keep the ambient file inside its budget, saying what it dropped."""
    def over(ls):
        return len(ls) > MAX_LINES or len("\n".join(ls).encode("utf-8")) > MAX_BYTES

    if not over(lines):
        return "\n".join(lines) + "\n"

    # Trim the one-line downstream list first: it is the longest low-value run.
    start = next((i for i, l in enumerate(lines)
                  if l.startswith("## Downstream caveats")), None)
    if start is not None:
        end = next((i for i in range(start + 1, len(lines))
                    if lines[i].startswith("## ")), len(lines))
        body = [i for i in range(start + 2, end) if lines[i].startswith("- ")]
        while over(lines) and len(body) > 3:
            drop = body.pop()
            del lines[drop]
        lines.insert(min(body[-1] + 1 if body else start + 2, len(lines)),
                     "- ... and the rest, verbatim, in `%s`." % TIER2_REL)

    while over(lines) and len(lines) > 40:
        lines.pop(len(lines) - 2)
    return "\n".join(lines) + "\n"


def render_tier2(data, stamp):
    """The complete board. Not loaded into a session, so nothing is trimmed."""
    L = ["# SDLC status - full detail", "",
         "<!-- GENERATED by .claude/sdlc/statusboard.py - do not hand-edit. %s -->" % stamp,
         "",
         "The ambient summary is `%s`; this file is everything behind it."
         % TIER1_REL, ""]
    if data.get("auto_commit"):
        L += [AUTO_COMMIT_LINE, ""]

    L += ["## Pipeline", "",
          "| Stage | Artifact | Status | Version | Shards |", "|---|---|---|---|---|"]
    for row in data["pipeline"]:
        L.append("| %s | %s | %s | %s | %s |"
                 % (row["stage"], row["artifact"] or "-", row["status"],
                    row["version"] or "-", row["shards"] or "-"))
    L.append("")

    if data["blocked"]:
        L += ["## Blocked work", ""]
        for b in data["blocked"]:
            L += ["### %s - %s" % (b["id"], b["status"]), "", b["why"], ""]

    if data["questions"]:
        L += ["## Open questions", ""]
        for q in data["questions"]:
            L += ["### %s  (%s)" % (q["id"], q["bucket"]), "", q["text"], ""]
            if q["blocks"]:
                L += ["Blocks: %s" % ", ".join(q["blocks"]), ""]

    if data["findings"]:
        L += ["## Open findings", ""]
        for f in data["findings"]:
            L += ["### %s - %s (%s)" % (f["id"], f["status"], f["kind"] or "no kind"),
                  "", f["summary"], ""]
            if f["source"]:
                L += ["Suspected source: `%s`" % f["source"], ""]
            if f.get("owed"):
                L += ["Waiting on: %s" % ", ".join("`%s`" % c for c in f["owed"]), ""]
            for e in f["evidence"]:
                L.append("- %s" % e)
            if f["evidence"]:
                L.append("")

    L += ["## Caveats, verbatim, by artifact", ""]
    # One line for BOTH channels the canonical parser separates. A line that
    # covered only the ignored mappings would let a blocking entry disappear
    # from the ambient board and from here - a stricter silence than the one
    # this file's import exists to remove.
    refused = data.get("refused_warnings") or []
    if refused:
        ignored = [r["where"] for r in refused if not r["blocking"]]
        broken = [r["where"] for r in refused if r["blocking"]]
        bits = []
        if ignored:
            bits.append("%d malformed, which every validator reads and ignores "
                        "(%s)" % (len(ignored), id_list(ignored)))
        if broken:
            bits.append("%d that a validator refuses outright, failing the "
                        "artifact (%s)" % (len(broken), id_list(broken)))
        L += ["- Entries no reader can use: %d - %s. They are in no list above, "
              "because nothing else reads them either. Fix them in the artifact "
              "and they appear here." % (len(refused), " and ".join(bits)), ""]
    by_file = {}
    for x in data["warnings"]:
        by_file.setdefault(x["source"], []).append(x)
    if not by_file:
        L += ["No artifact records a warning.", ""]
    for source in sorted(by_file):
        items = by_file[source]
        n_open = sum(1 for x in items if x["status"] == "open")
        L += ["### docs/%s - %d warning(s), %d open" % (source, len(items), n_open), ""]
        for x in sorted(items, key=lambda i: (i["status"] != "open", i["id"])):
            where = "docs/%s%s" % (source, ":%d" % x["line"] if x.get("line") else "")
            bits = [x["kind"], x["status"], "impact: " + x["impact"]]
            if not x["typed"]:
                bits.append("legacy string")
            L += ["- **%s** *(%s)* - `%s`" % (x["id"], ", ".join(bits), where)]
            L += wrap(x["text"], indent="  ")
            if x["defers"]:
                L.append("  Defers: %s" % ", ".join(x["defers"]))
            if x["resolution"]:
                L.append("  Resolution: %s%s"
                         % (x["resolution"],
                            " (%s)" % x["resolved_on"] if x["resolved_on"] else ""))
        L.append("")

    integ = data["integrity"]
    L += ["## Integrity", ""]
    if integ["drift"]:
        L.append("- Upstream drift:")
        for d in integ["drift"]:
            L.append("  - `docs/%s` was built against an older %s"
                     % (d["file"], ", ".join(d["behind"])))
    else:
        L.append("- Upstream drift: none")
    L += ["- Dangling references: %s"
          % (", ".join(integ["dangling"]) if integ["dangling"] else "none")]
    L += ["- Acceptance criteria with no covering test: %s"
          % (", ".join(integ["uncovered_acr"]) if integ["uncovered_acr"] else "none")]
    if data.get("setup_lag"):
        L.append("- Installed helpers: from plugin %s, older than the plugin in use - "
                 "run `/sdlc:setup` once." % data["setup_lag"])
    L.append("")
    lessons = data["lessons"]
    if lessons_line(lessons):
        L += ["## Lessons about the plugin", "",
              "These describe the sdlc SKILLS, not this project; nothing in the",
              "pipeline reads them. The maintainer's verdicts arrive at every skill",
              "close (`python .claude/sdlc/lessons.py list` shows each one)."]
        if lessons["open"]:
            L.append("- Open: %s" % ", ".join(lessons["open"]))
        if lessons["reopened"]:
            L.append("- Open again after a fix (recurred - the maintainer sees it as a "
                     "reopen): %s" % ", ".join(lessons["reopened"]))
        L.append("- Verdicts: %s" % lessons_line(lessons))
        L.append("")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def gather(root, plugin_root=None):
    docs, state = root / "docs", root / STATE_REL
    edition, pro_url = read_edition(root)
    setup_lag = collect_setup_lag(root, state, plugin_root)
    warnings, refused = collect_warnings_detail(docs)
    pipeline = collect_pipeline(docs, state, edition)
    findings = collect_findings(state)
    blocked = collect_blocked(state)
    questions = collect_questions(docs)
    return {
        "warnings": warnings, "refused_warnings": refused,
        "pipeline": pipeline, "findings": findings,
        "blocked": blocked, "questions": questions,
        "integrity": collect_integrity(docs), "lessons": collect_lessons(state, root),
        "next": next_step(pipeline, findings, blocked, questions, pro_url, edition),
        "setup_lag": setup_lag,
        "auto_commit": read_auto_commit(root),
    }


def body_of(text):
    """The file minus its generation stamp, so --check ignores the timestamp."""
    return "\n".join(l for l in text.split("\n") if "GENERATED by" not in l
                     and not l.strip().startswith("Z -->")
                     and not l.strip().endswith("-->"))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--path", default=".", help="project root (default: .)")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the files are stale; write nothing")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the ambient board; write nothing")
    ap.add_argument("--detail", action="store_true",
                    help="print the full board; write nothing")
    ap.add_argument("--plugin-root", default=None,
                    help="the running plugin's root (default: the plugin of the skill "
                         "that runs this); used only to notice that /sdlc:setup's "
                         "install is older")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not (root / "docs").is_dir():
        print("[FAIL] no docs/ directory under %s - this is not an SDLC project "
              "yet. Run /sdlc:setup first." % root)
        return 2

    data = gather(root, args.plugin_root)
    # The stamp is a fingerprint of the SOURCES, not a wall clock. A wall clock
    # would rewrite both files on every run and dirty the diff even when
    # nothing about the project changed - the same churn this whole change set
    # exists to remove from CLAUDE.md.
    stamp = "sources %s" % sha256(
        json.dumps(data, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:12]
    tier1, tier2 = render_tier1(data, stamp), render_tier2(data, stamp)

    if args.detail:
        sys.stdout.write(tier2)
        return 0
    if args.dry_run:
        sys.stdout.write(tier1)
        return 0

    t1, t2 = root / TIER1_REL, root / TIER2_REL
    if args.check:
        for path, fresh in ((t1, tier1), (t2, tier2)):
            old = path.read_text(encoding="utf-8") if path.exists() else ""
            if body_of(old) != body_of(fresh):
                print("[FAIL] %s is out of date - an artifact changed after it was "
                      "written." % path.relative_to(root).as_posix())
                print("")
                print("NEXT:      python .claude/sdlc/statusboard.py")
                return 1
        print("[OK] the statusboard matches the artifacts.")
        return 0

    for path, text in ((t1, tier1), (t2, tier2)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")

    n_open = sum(1 for x in data["warnings"] if x["status"] == "open")
    lines = len(tier1.split("\n"))
    print("[OK] statusboard rewritten - %d line(s) ambient, %d caveat(s) in full."
          % (lines, n_open))
    print("     %s   loaded into every session" % TIER1_REL)
    print("     %s          read on demand" % TIER2_REL)
    if not any(x["typed"] for x in data["warnings"]) and data["warnings"]:
        print("")
        print("     Every warning is still a legacy string, so all of them count as")
        print("     'local' and the board can only tally them. Run")
        print("     'python .claude/sdlc/migrate_warnings.py --all --dry-run' to see")
        print("     what typing them would surface.")
    cmd, why = data["next"]
    print("")
    print("NEXT:      %s" % (cmd if cmd else "nothing queued"))
    print("           %s" % why)
    print("           Label meanings: %s" % GLOSSARY_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
