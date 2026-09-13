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

WRN_KINDS = ("deferral", "limitation", "decision", "exception", "scope_change", "note")
WRN_STATUSES = ("open", "resolved")
WRN_IMPACTS = ("none", "local", "downstream", "risk")


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


def norm_warning(entry, source):
    """One warning as a dict, whichever form it is written in.

    Mirrors `parse_warnings` in the validators, minus the reporting: this
    script reads, it never judges.
    """
    if isinstance(entry, dict):
        kind = str(entry.get("kind") or "note").strip()
        status = str(entry.get("status") or "open").strip()
        impact = str(entry.get("impact") or "local").strip()
        if status == "resolved" and not str(entry.get("resolution") or "").strip():
            status = "open"
        return {
            "id": str(entry.get("id") or "").strip() or "WRN-???",
            "text": str(entry.get("text") or "").strip(),
            "kind": kind if kind in WRN_KINDS else "note",
            "status": status if status in WRN_STATUSES else "open",
            "impact": impact if impact in WRN_IMPACTS else "local",
            "defers": [str(d) for d in (entry.get("defers") or [])],
            "resolution": entry.get("resolution"),
            "resolved_on": entry.get("resolved_on"),
            "source": source,
            "typed": True,
        }
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
    out = []
    for path in artifact_files(docs):
        doc = load(path)
        if not doc:
            continue
        for key, value in doc.items():
            if not key.endswith("_warnings") or not isinstance(value, list):
                continue
            for entry in value:
                w = norm_warning(entry, path.name)
                w["line"] = line_of(path, w["id"])
                out.append(w)
    return out


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
    out = []
    for f in doc.get("findings") or []:
        if not isinstance(f, dict) or str(f.get("status") or "") == "resolved":
            continue
        # The queue writes `fnd_id`, not `id` (FINDINGS.schema.yaml); accept
        # both so a hand-written entry still shows up with its real id.
        out.append({"id": str(f.get("fnd_id") or f.get("id") or "FND-???"),
                    "status": str(f.get("status") or "open"),
                    "kind": str(f.get("kind") or ""),
                    "summary": str(f.get("summary") or "").strip(),
                    "source": str(f.get("suspected_source") or ""),
                    "raised_by": str(f.get("raised_by") or ""),
                    "evidence": [str(e) for e in (f.get("evidence") or [])]})
    return out


def collect_lessons(state):
    doc = load(state / "sdlc-lessons.yaml") or {}
    # Same here: the lessons queue writes `lsn_id`.
    return [str(l.get("lsn_id") or l.get("id") or "LSN-???")
            for l in (doc.get("lessons") or [])
            if isinstance(l, dict) and str(l.get("status") or "") == "open"]


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


def next_step(pipeline, findings, blocked, questions, pro_url=None):
    """The single best next command, decided here rather than copied.

    Order matches CLAUDE.md section 14: an unfinished artifact first, then
    recorded defects, then the pipeline successor.
    """
    for row in pipeline:
        if row["status"] == "draft":
            return ("/sdlc:%s" % row["stage"].split()[0],
                    "%s is still a draft - no later stage will consume it."
                    % row["artifact"])
    if findings:
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
        L += ["## Open findings - %d  (`/sdlc:repair`)" % len(data["findings"]), ""]
        for f in data["findings"]:
            L += ["- **%s** *(%s%s)*%s" % (
                f["id"], f["status"], ", " + f["kind"] if f["kind"] else "",
                " - " + f["source"] if f["source"] else "")]
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
    if data["lessons"]:
        L += ["", "Lessons: %d open (%s) - about the SDLC plugin itself, not this "
                  "project." % (len(data["lessons"]), id_list(data["lessons"]))]
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
            for e in f["evidence"]:
                L.append("- %s" % e)
            if f["evidence"]:
                L.append("")

    L += ["## Caveats, verbatim, by artifact", ""]
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
    L.append("")
    if data["lessons"]:
        L += ["## Lessons about the plugin", "",
              "These describe the sdlc SKILLS, not this project; nothing in the",
              "pipeline reads them. Open: %s" % ", ".join(data["lessons"]), ""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------

def gather(root):
    docs, state = root / "docs", root / STATE_REL
    edition, pro_url = read_edition(root)
    warnings = collect_warnings(docs)
    pipeline = collect_pipeline(docs, state, edition)
    findings = collect_findings(state)
    blocked = collect_blocked(state)
    questions = collect_questions(docs)
    return {
        "warnings": warnings, "pipeline": pipeline, "findings": findings,
        "blocked": blocked, "questions": questions,
        "integrity": collect_integrity(docs), "lessons": collect_lessons(state),
        "next": next_step(pipeline, findings, blocked, questions, pro_url),
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
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not (root / "docs").is_dir():
        print("[FAIL] no docs/ directory under %s - this is not an SDLC project "
              "yet. Run /sdlc:setup first." % root)
        return 2

    data = gather(root)
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
