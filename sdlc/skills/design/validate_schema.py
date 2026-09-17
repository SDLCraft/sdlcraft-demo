"""Validate DESIGN.yaml + its conditional sub-files against the sdlc-design schema.

Run from the project root:

    python sdlc/skills/design/validate_schema.py
    python sdlc/skills/design/validate_schema.py --path docs/DESIGN.yaml

Validates:
    1. docs/DESIGN.yaml (or --path) — the global design-system contract.
    2. docs/DESIGN__tokens.yaml — iff token_based_ui ∈ functional_structure.
    3. docs/DESIGN__assets.yaml — iff asset_pipeline ∈ functional_structure OR
       aesthetic_direction.requires_custom_assets.
       (In monorepo mode: docs/DESIGN__<slug>__tokens.yaml / __assets.yaml.)
    4. ID-family prefix formats: AST-NNN on asset ids, WRN-NNN on design_warnings,
       FR-NNN/NFR-NNN in implements_requirements, SCR-NNN in traces_ux_surfaces,
       ENT-NNN in references_entities.
    5. Composition consistency: `headless` is exclusive; the tokens file exists
       iff token_based_ui is selected; the assets file exists iff asset_pipeline
       is selected or an aesthetic needs custom assets; aesthetic_direction is
       present unless the structure is purely headless.
    6. Asset-brief coverage (trace-or-defer): every asset with
       source == "to_be_generated" carries a non-null generation_brief OR is
       deferred via the structured `deferrals: [{id, reason}]` list of the
       scope that owns it (top level, or products.<slug> in monorepo mode;
       alias `deferred_requirements`). A "WRN-NNN: … AST-NNN …" entry in
       DESIGN.yaml.design_warnings still defers it for one more version
       (pooled across products — the reason the prose channel is deprecated),
       and every id that fell through to it is reported.
    7. Provenance-staleness WARNING (never blocks): each recorded
       metadata.upstream_provenance sha256 is compared to the upstream's
       current content hash (docs/INDEX.yaml generated_from, else computed
       as sha256 over the UTF-8 text - identical to docs_index.py --hash).

Exit codes:
    0 — schema valid; either status='complete' (all required fields filled,
        composition consistent, and to-be-generated coverage satisfied) or
        status='draft'.
    1 — schema invalid (pydantic error), OR status='complete' but required
        fields are missing, composition is inconsistent, ID-prefix format is
        violated, or a to-be-generated asset is uncovered.
    2 — could not read or parse one of the files (missing, bad YAML, etc.)
    3 — required dependency missing (pydantic v2 or pyyaml).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple


# =============================================================================
# User-facing output (CLAUDE.md 14). Three verdict tags, two finding sections,
# one NEXT block - identical across every SDLC script, because the person
# reading them knows only "there is a pipeline and I run it in order".
# Canonical guidance: sdlc/skills/prd/references/reporting-to-the-user.md
# =============================================================================

GLOSSARY_PATH = ".claude/rules/sdlc-output-glossary.md"
STALE_NOTE = ("an upstream moved after this file was written; review the delta "
              "before the next stage reads it")

def join_ids(ids, limit=12):
    """Render a grouped finding's id list. Capped, because a line nobody
    finishes reading has told the user nothing."""
    ids = [str(i) for i in ids]
    shown = ", ".join(ids[:limit])
    return shown if len(ids) <= limit else f"{shown} (+{len(ids) - limit} more)"



def _emit_finding(item, detail_cap=5):
    """One finding. A (headline, details) pair renders as a grouped finding:
    the class in one sentence, then a capped sample. A line nobody finishes
    reading has told the user nothing."""
    if isinstance(item, tuple):
        head, details = item
        print(f"  - {head}")
        for d in list(details)[:detail_cap]:
            print(f"      * {d}")
        if len(details) > detail_cap:
            print(f"      * (+{len(details) - detail_cap} more of the same)")
    else:
        print(f"  - {item}")


def print_findings(blocking, warnings, blocking_header="MUST FIX BEFORE 'complete'"):
    """The two canonical sections. A WARNING never blocks, and says so."""
    warnings = list(warnings or []) + drain_warning_shape_warnings()
    if blocking:
        print(f"\n{blocking_header} ({len(blocking)}):")
        for b in blocking:
            _emit_finding(b)
    if warnings:
        print(f"\nWARNINGS ({len(warnings)}) - none of these block the next skill:")
        for w in warnings:
            _emit_finding(w)


def print_next(*lines, show_glossary=True):
    """Close with what to type next. The glossary pointer only appears when
    there was something to decode."""
    print(f"\nNEXT: {lines[0]}")
    for extra in lines[1:]:
        print(f"      {extra}")
    if show_glossary:
        print(f"      What these labels mean: {GLOSSARY_PATH}")


try:
    import yaml
except ImportError:
    print(
        "ERROR: pyyaml is required.\nInstall with:  pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(3)

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
except ImportError:
    print(
        "ERROR: pydantic v2 is required.\nInstall with:  pip install 'pydantic>=2'",
        file=sys.stderr,
    )
    sys.exit(3)


# =============================================================================
# ID-family prefix regexes (kept in lockstep with DESIGN.schema.yaml header)
# =============================================================================

ID_PATTERN = r"-\d{3,}"  # three-digit minimum; longer allowed for big projects
AST_ID_RE = re.compile(rf"^AST{ID_PATTERN}$")
SCR_ID_RE = re.compile(rf"^SCR{ID_PATTERN}$")
ENT_ID_RE = re.compile(rf"^ENT{ID_PATTERN}$")
# implements_requirements traces BOTH functional (FR) and non-functional (NFR)
# requirements — a design can realize a feature and also honour a constraint.
FR_OR_NFR_ID_RE = re.compile(rf"^(?:FR|NFR){ID_PATTERN}$")
def _version_tuple(v: object) -> tuple:
    """Parse '2.0' / '1.1' into a comparable (major, minor). Unparseable -> (0, 0)."""
    m = re.match(r"^\s*(\d+)(?:\.(\d+))?", str(v or ""))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))

def _prose_deferrals_allowed(obj, _fields=('design_version',), _floor=2):
    """Is the DEPRECATED prose word-match still read on this artifact?

    Only below `<name>_version` 2.0. From there up, a deferral is
    declared structurally - the top-level `deferrals` list, or a typed warning
    with `kind: deferral` and `defers: [...]` - and a note that merely mentions
    an id no longer silences that id's gate. Version-gated because an artifact
    an older skill version stamped complete must not turn red on upgrade
    (CLAUDE.md section 10). When no version is reachable the answer is yes, so
    the gate can only ever get looser, never stricter, by accident.
    """
    md = getattr(obj, "metadata", None)
    for name in _fields:
        v = getattr(md, name, None)
        if v:
            return tuple(_version_tuple(v)[:2]) < (_floor, 0)
    return True


# =============================================================================
# Enums (kept in lockstep with the three schema yamls)
# =============================================================================


class Confidence(str, Enum):
    confirmed = "confirmed"
    inferred = "inferred"
    assumption = "assumption"


class FunctionalStructure(str, Enum):
    token_based_ui = "token_based_ui"
    asset_pipeline = "asset_pipeline"
    headless = "headless"


class MotionCharacter(str, Enum):
    none = "none"
    subtle = "subtle"
    expressive = "expressive"
    playful = "playful"


class TokenSource(str, Enum):
    dtcg_authored = "dtcg_authored"
    import_shadcn = "import_shadcn"
    import_tokens_studio = "import_tokens_studio"
    import_tailwind = "import_tailwind"
    import_other = "import_other"


class AssetSource(str, Enum):
    to_be_generated = "to_be_generated"
    user_supplied = "user_supplied"
    placeholder = "placeholder"


class AssetModality(str, Enum):
    image = "image"
    audio = "audio"
    model_3d = "model_3d"
    font = "font"
    shader = "shader"
    vfx = "vfx"
    animation = "animation"


# =============================================================================
# DESIGN.yaml models
# =============================================================================

# extra="allow" gives forward-compat for new question additions; enum values
# are still strictly validated.
_BASE_CONFIG = ConfigDict(extra="allow", str_strip_whitespace=True)


class _Block(BaseModel):
    model_config = _BASE_CONFIG


class AestheticDirection(_Block):
    style_family: Optional[str] = None  # OPEN vocabulary — free-form string
    style_family_confidence: Optional[Confidence] = None
    mood_keywords: Optional[List[str]] = None
    palette_intent: Optional[str] = None
    style_references: Optional[List[str]] = None
    typographic_voice: Optional[str] = None
    motion_character: Optional[MotionCharacter] = None
    texture_and_finish: Optional[str] = None
    requires_custom_assets: Optional[bool] = None


class SubArtifacts(_Block):
    tokens: Optional[str] = None
    assets: Optional[str] = None


class BrandIdentity(_Block):
    logo_usage: Optional[str] = None
    brand_palette: Optional[List[str]] = None
    brand_voice: Optional[str] = None
    imagery_style: Optional[str] = None


class SurfaceOverride(_Block):
    """Per-surface styling deviation on top of the global system. Keyed by
    SCR-NNN in surface_overrides. Presence of an entry = concrete per-surface
    design work `task` derives (in addition to the global theme/token task)."""

    density: Optional[Literal["compact", "comfortable", "spacious"]] = None
    token_overrides: Optional[Dict[str, Any]] = None
    component_variants: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class DesignMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    design_version: str
    last_updated: str
    generated_by: str = "sdlc-design"
    session_id: str
    monorepo: bool = False
    status: Literal["draft", "complete"] = "draft"
    # 0.8.0. Absent means "applicable" - every artifact written before this
    # field existed is applicable, so the default keeps legacy files valid
    # (CLAUDE.md section 10). "not_applicable" means this stage RAN and found
    # nothing to model: the artifact is deliberately empty and every coverage
    # gate over it is vacuous. Consumers treat it exactly like an absent
    # artifact, without asking the user anything.
    applicability: Literal["applicable", "not_applicable"] = "applicable"
    applicability_rationale: Optional[str] = None
    applicability_confidence: Optional[Confidence] = None
    changelog: Optional[List[str]] = None
    upstream_provenance: Optional[List[Dict[str, Any]]] = None


class DesignProduct(_Block):
    """One product's design contract in monorepo mode (also the shape of the
    single-product top level)."""

    # Structured deferrals (CLAUDE.md 6): [{id, reason}] entries read FIRST by
    # the asset-brief coverage gate for THIS product's AST ids; an entry with
    # no reason defers nothing.
    deferrals: Optional[List[Dict[str, Any]]] = None
    deferred_requirements: Optional[List[Dict[str, Any]]] = None  # accepted alias

    functional_structure: Optional[List[FunctionalStructure]] = None
    functional_structure_confidence: Optional[Confidence] = None
    functional_structure_rationale: Optional[str] = None
    aesthetic_direction: Optional[AestheticDirection] = None
    sub_artifacts: Optional[SubArtifacts] = None
    brand_identity: Optional[BrandIdentity] = None
    implements_requirements: Optional[List[str]] = None
    traces_ux_surfaces: Optional[List[str]] = None
    surface_overrides: Optional[Dict[str, SurfaceOverride]] = None


class Design(BaseModel):
    """Top-level DESIGN.yaml document."""

    model_config = ConfigDict(extra="allow")

    metadata: DesignMetadata
    design_warnings: List[Any] = Field(default_factory=list)  # str | typed WarningItem mapping

    # Structured deferrals (CLAUDE.md 6): the DEFER half of the asset-brief
    # coverage gate, single-product mode. In monorepo mode declare them under
    # products.<slug>.deferrals instead — AST id spaces are per product, so a
    # pooled top-level deferral cannot say which product's asset it means.
    deferrals: Optional[List[Dict[str, Any]]] = None
    deferred_requirements: Optional[List[Dict[str, Any]]] = None  # accepted alias

    # Single-product mode — axis blocks at top level
    functional_structure: Optional[List[FunctionalStructure]] = None
    functional_structure_confidence: Optional[Confidence] = None
    functional_structure_rationale: Optional[str] = None
    aesthetic_direction: Optional[AestheticDirection] = None
    sub_artifacts: Optional[SubArtifacts] = None
    brand_identity: Optional[BrandIdentity] = None
    implements_requirements: Optional[List[str]] = None
    traces_ux_surfaces: Optional[List[str]] = None
    surface_overrides: Optional[Dict[str, SurfaceOverride]] = None

    # Multi-product mode
    products: Optional[Dict[str, DesignProduct]] = None

    @model_validator(mode="after")
    def _check_mode(self) -> "Design":
        single = [
            self.functional_structure,
            self.aesthetic_direction,
            self.sub_artifacts,
            self.brand_identity,
            self.implements_requirements,
            self.traces_ux_surfaces,
            self.surface_overrides,
        ]
        any_single = any(t is not None for t in single)
        if self.metadata.monorepo:
            if not self.products:
                raise ValueError(
                    "metadata.monorepo is true but `products` is missing or empty"
                )
            if any_single:
                raise ValueError(
                    "monorepo mode set but top-level axis blocks are present; "
                    "in monorepo mode every block must live under `products.<slug>`"
                )
        else:
            if self.products:
                raise ValueError(
                    "`products` is set but metadata.monorepo is false; "
                    "either set monorepo: true or move blocks to top level"
                )
        return self


# =============================================================================
# DESIGN__tokens.yaml model
# =============================================================================


class TokensMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    design_tokens_version: str
    last_updated: str
    generated_by: str = "sdlc-design"
    session_id: str
    status: Literal["draft", "complete"] = "draft"
    changelog: Optional[List[str]] = None


class DesignTokens(BaseModel):
    """Top-level DESIGN__tokens.yaml document."""

    model_config = ConfigDict(extra="allow")

    metadata: TokensMetadata
    token_source: Optional[TokenSource] = None
    imported_from: Optional[str] = None
    component_library: Optional[str] = None
    theme_modes: Optional[List[str]] = None
    color: Optional[Dict[str, Any]] = None
    typography: Optional[Dict[str, Any]] = None
    spacing: Optional[Dict[str, Any]] = None
    radius: Optional[Dict[str, Any]] = None
    elevation: Optional[Dict[str, Any]] = None
    motion: Optional[Dict[str, Any]] = None
    contrast_notes: Optional[str] = None


# =============================================================================
# DESIGN__assets.yaml models
# =============================================================================


class AssetGenerationBrief(_Block):
    target_modality: Optional[AssetModality] = None
    recommended_tools: Optional[List[str]] = None
    prompt: Optional[str] = None
    negative_prompt: Optional[str] = None
    style_anchors: Optional[List[str]] = None
    technical_constraints: Optional[str] = None
    acceptance_criteria: Optional[List[str]] = None
    variation_notes: Optional[str] = None


class AssetSpec(_Block):
    id: Optional[str] = None  # AST-NNN
    asset_type: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    format_hint: Optional[str] = None
    source: Optional[AssetSource] = None
    traces_ux_surfaces: Optional[List[str]] = None
    references_entities: Optional[List[str]] = None
    generation_brief: Optional[AssetGenerationBrief] = None


class AssetsMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    design_assets_version: str
    last_updated: str
    generated_by: str = "sdlc-design"
    session_id: str
    status: Literal["draft", "complete"] = "draft"
    changelog: Optional[List[str]] = None


class DesignAssets(BaseModel):
    """Top-level DESIGN__assets.yaml document."""

    model_config = ConfigDict(extra="allow")

    metadata: AssetsMetadata
    asset_taxonomy: Optional[List[str]] = None
    render_pipeline: Optional[str] = None
    style_guide: Optional[str] = None
    assets: Optional[List[AssetSpec]] = None


# =============================================================================
# Helpers
# =============================================================================


def _get_dotted(obj: object, path: str) -> object:
    cur: object = obj
    for part in path.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


def _is_empty(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict, str)) and len(value) == 0:
        return True
    return False


def _is_pure_headless(fs: Optional[List[FunctionalStructure]]) -> bool:
    return bool(fs) and all(m == FunctionalStructure.headless for m in fs)


def _has(fs: Optional[List[FunctionalStructure]], member: FunctionalStructure) -> bool:
    return bool(fs) and member in fs


# A "scope" is the single top-level product, or one entry under products.<slug>.
# slug is None for single-product mode.
Scope = Tuple[str, object, Optional[str]]


def scopes_of(design: Design) -> List[Scope]:
    if design.metadata.monorepo and design.products:
        return [
            (f"products.{slug}.", product, slug)
            for slug, product in design.products.items()
        ]
    return [("", design, None)]


# =============================================================================
# Required-field checks
# =============================================================================

# DESIGN.yaml required paths for any non-pure-headless scope.
DESIGN_VISUAL_REQUIRED: List[str] = [
    "aesthetic_direction.style_family",
    "aesthetic_direction.mood_keywords",
]
TOKENS_REQUIRED: List[str] = ["token_source", "theme_modes", "color", "typography", "spacing"]
ASSETS_REQUIRED: List[str] = ["asset_taxonomy", "assets"]
BRIEF_REQUIRED: List[str] = [
    "target_modality",
    "recommended_tools",
    "prompt",
    "style_anchors",
    "acceptance_criteria",
]


def check_design_required(design: Design) -> List[str]:
    missing: List[str] = []
    for label, scope, _slug in scopes_of(design):
        fs = getattr(scope, "functional_structure", None)
        if _is_empty(fs):
            missing.append(f"{label}functional_structure")
            continue  # nothing else can be judged without the axes
        if not _is_pure_headless(fs):
            for path in DESIGN_VISUAL_REQUIRED:
                if _is_empty(_get_dotted(scope, path)):
                    missing.append(f"{label}{path}")
            # requires_custom_assets is a bool — None means unfilled (False is OK)
            ad = getattr(scope, "aesthetic_direction", None)
            if ad is None or getattr(ad, "requires_custom_assets", None) is None:
                missing.append(f"{label}aesthetic_direction.requires_custom_assets")
    return missing


def check_tokens_required(tokens: DesignTokens, label: str) -> List[str]:
    return [f"{label}: {p}" for p in TOKENS_REQUIRED if _is_empty(_get_dotted(tokens, p))]


def check_assets_required(assets: DesignAssets, label: str) -> List[str]:
    missing = [f"{label}: {p}" for p in ASSETS_REQUIRED if _is_empty(_get_dotted(assets, p))]
    for i, a in enumerate(assets.assets or []):
        where = f"{label}: assets[{i}]"
        if _is_empty(a.id):
            missing.append(f"{where}.id")
        if _is_empty(a.asset_type):
            missing.append(f"{where}.asset_type")
        if _is_empty(a.name):
            missing.append(f"{where}.name")
        if _is_empty(a.description):
            missing.append(f"{where}.description")
        if _is_empty(a.source):
            missing.append(f"{where}.source")
        # A to-be-generated asset that *has* a brief must have it fully filled.
        if a.source == AssetSource.to_be_generated and a.generation_brief is not None:
            for p in BRIEF_REQUIRED:
                if _is_empty(_get_dotted(a.generation_brief, p)):
                    missing.append(f"{where}.generation_brief.{p}")
    return missing


# =============================================================================
# ID-prefix format checks
# =============================================================================


def _check_list_prefix(
    values: Optional[List[str]], pattern: re.Pattern[str], expected: str, where: str
) -> List[str]:
    if not values:
        return []
    errors: List[str] = []
    for v in values:
        if not isinstance(v, str) or not pattern.match(v.strip()):
            errors.append(f"{where}: '{v}' does not match {expected}")
    return errors


# --- BEGIN canonical WRN block (CLAUDE.md section 2) — byte-identical everywhere
# A `*_warnings` entry is EITHER the legacy string "WRN-NNN: <text>" OR a
# mapping {id, text, kind, status, impact, refs?, defers?, resolution?,
# resolved_on?}. Legacy strings stay valid forever and read as an open,
# local-impact note. A malformed MAPPING never fails the file: it is reported
# and the entry is dropped or downgraded, exactly as a malformed `deferrals`
# entry is (it defers nothing). A malformed STRING stays the error it has
# always been.

WRN_KINDS = ("deferral", "limitation", "decision", "exception", "scope_change", "note")
WRN_STATUSES = ("open", "resolved")
WRN_IMPACTS = ("none", "local", "downstream", "risk")

_WRN_ENTRY_RE = re.compile(r"^WRN-\d{3,}:\s+.+", re.DOTALL)
_WRN_ID_RE = re.compile(r"^WRN-\d{3,}$")


class WarningItem:
    """One normalized `*_warnings` entry.

    `typed` records which form it was written in, so a writer can tell an
    untouched legacy corpus from one that has been migrated.
    """

    __slots__ = ("id", "text", "kind", "status", "impact", "refs", "defers",
                 "resolution", "resolved_on", "typed", "where")

    def __init__(self, wid, text, kind="note", status="open", impact="local",
                 refs=None, defers=None, resolution=None, resolved_on=None,
                 typed=False, where=""):
        self.id = wid
        self.text = text
        self.kind = kind
        self.status = status
        self.impact = impact
        self.refs = [str(r).strip() for r in (refs or []) if str(r).strip()]
        self.defers = [str(d).strip() for d in (defers or []) if str(d).strip()]
        self.resolution = resolution
        self.resolved_on = resolved_on
        self.typed = typed
        self.where = where

    def __str__(self):
        return "%s: %s" % (self.id, self.text)


def parse_warnings(raw, label):
    """Normalize one `*_warnings` list.

    Returns `(items, errors, shape_warnings)`:
      items          - WarningItem per usable entry, in file order.
      errors         - BLOCKING. A string entry that is not "WRN-NNN: <text>",
                       or an entry that is neither a string nor a mapping.
                       Unchanged from the pre-typed behaviour.
      shape_warnings - NON-BLOCKING. A mapping whose fields are wrong. Never
                       promoted to an error: an artifact stamped complete by an
                       older skill version must not start failing (section 10).
    """
    items: List["WarningItem"] = []
    errors: List[str] = []
    shape: List[str] = []
    for i, w in enumerate(raw or []):
        where = "%s[%d]" % (label, i)
        if isinstance(w, str):
            s = w.strip()
            if not _WRN_ENTRY_RE.match(s):
                errors.append(
                    "%s: '%s' must start with 'WRN-NNN: ' "
                    "(zero-padded 3-digit number)" % (where, w)
                )
                continue
            wid, _, text = s.partition(":")
            items.append(WarningItem(wid.strip(), text.strip(), where=where))
            continue
        if not isinstance(w, dict):
            errors.append(
                "%s: '%s' must start with 'WRN-NNN: ' "
                "(zero-padded 3-digit number)" % (where, w)
            )
            continue
        wid = str(w.get("id") or "").strip()
        text = str(w.get("text") or "").strip()
        if not _WRN_ID_RE.match(wid):
            shape.append(
                "%s declares id '%s' - a warning needs an id of the form "
                "'WRN-NNN' to be referenced; this entry is ignored"
                % (where, w.get("id"))
            )
            continue
        if not text:
            shape.append(
                "%s (%s) has no 'text' - a warning with no message says "
                "nothing; this entry is ignored" % (where, wid)
            )
            continue
        kind = str(w.get("kind") or "note").strip()
        status = str(w.get("status") or "open").strip()
        impact = str(w.get("impact") or "local").strip()
        if kind not in WRN_KINDS:
            shape.append(
                "%s (%s): kind '%s' is not one of %s - read as 'note'"
                % (where, wid, kind, ", ".join(WRN_KINDS))
            )
            kind = "note"
        if status not in WRN_STATUSES:
            shape.append(
                "%s (%s): status '%s' is not 'open' or 'resolved' - read as "
                "'open'" % (where, wid, status)
            )
            status = "open"
        if impact not in WRN_IMPACTS:
            shape.append(
                "%s (%s): impact '%s' is not one of %s - read as 'local'"
                % (where, wid, impact, ", ".join(WRN_IMPACTS))
            )
            impact = "local"
        resolution = w.get("resolution")
        if status == "resolved" and not str(resolution or "").strip():
            shape.append(
                "%s (%s) is marked resolved but records no resolution - a "
                "resolution nobody can read is not one; read as still open"
                % (where, wid)
            )
            status = "open"
        defers = [str(d).strip() for d in (w.get("defers") or []) if str(d).strip()]
        if defers and kind != "deferral":
            shape.append(
                "%s (%s) lists 'defers' but its kind is '%s' - only a "
                "'deferral' defers anything, so these ids are ignored"
                % (where, wid, kind)
            )
            defers = []
        items.append(WarningItem(
            wid, text, kind, status, impact, w.get("refs"), defers,
            resolution, w.get("resolved_on"), typed=True, where=where,
        ))
    return items, errors, shape


_WRN_SHAPE_SEEN = []


def check_warning_ids(warnings, label="warnings"):
    """The blocking half of `parse_warnings`.

    The non-blocking half is collected in `_WRN_SHAPE_SEEN` and drained once,
    where the report is printed, so a caller that only wants the errors cannot
    accidentally swallow a malformed mapping.
    """
    _items, errors, shape = parse_warnings(warnings, label)
    _WRN_SHAPE_SEEN.extend(shape)
    return errors


def drain_warning_shape_warnings():
    """Every malformed typed-warning report seen so far, each once."""
    out = list(dict.fromkeys(_WRN_SHAPE_SEEN))
    del _WRN_SHAPE_SEEN[:]
    return out


def warning_text(entry):
    """The message of one raw entry, whichever form it is written in."""
    if isinstance(entry, dict):
        return str(entry.get("text") or "")
    s = str(entry or "").strip()
    return s.partition(":")[2].strip() if ":" in s else s
# --- END canonical WRN block


def check_design_id_prefixes(design: Design) -> List[str]:
    errors: List[str] = []
    errors.extend(check_warning_ids(design.design_warnings, "design_warnings"))
    for label, scope, _slug in scopes_of(design):
        errors.extend(
            _check_list_prefix(
                getattr(scope, "implements_requirements", None),
                FR_OR_NFR_ID_RE,
                "'FR-NNN' or 'NFR-NNN'",
                f"{label}implements_requirements",
            )
        )
        errors.extend(
            _check_list_prefix(
                getattr(scope, "traces_ux_surfaces", None),
                SCR_ID_RE,
                "'SCR-NNN'",
                f"{label}traces_ux_surfaces",
            )
        )
        overrides = getattr(scope, "surface_overrides", None)
        if overrides:
            for key in overrides:
                if not isinstance(key, str) or not SCR_ID_RE.match(key.strip()):
                    errors.append(
                        f"{label}surface_overrides: key '{key}' must be an 'SCR-NNN' id"
                    )
    return errors


def check_assets_id_prefixes(assets: DesignAssets, label: str) -> List[str]:
    errors: List[str] = []
    for i, a in enumerate(assets.assets or []):
        where = f"{label}: assets[{i}]"
        if a.id is not None and not AST_ID_RE.match(a.id.strip()):
            errors.append(f"{where}.id: '{a.id}' must match 'AST-NNN'")
        errors.extend(
            _check_list_prefix(a.traces_ux_surfaces, SCR_ID_RE, "'SCR-NNN'", f"{where}.traces_ux_surfaces")
        )
        errors.extend(
            _check_list_prefix(a.references_entities, ENT_ID_RE, "'ENT-NNN'", f"{where}.references_entities")
        )
    return errors


def check_asset_type_taxonomy(assets: DesignAssets, label: str) -> List[str]:
    """Soft check: asset_type should be one of asset_taxonomy. Advisory only."""
    taxonomy = set(assets.asset_taxonomy or [])
    if not taxonomy:
        return []
    soft: List[str] = []
    for i, a in enumerate(assets.assets or []):
        if a.asset_type and a.asset_type not in taxonomy:
            soft.append(
                f"{label}: assets[{i}].asset_type '{a.asset_type}' is not in asset_taxonomy "
                f"{sorted(taxonomy)}"
            )
    return soft


# =============================================================================
# Sub-file discovery + composition + coverage
# =============================================================================


def discover_sub_files(design_path: Path) -> Dict[Tuple[str, Optional[str]], Path]:
    """Map (kind, slug) -> path for every DESIGN__*.yaml sibling.
    kind ∈ {"tokens","assets"}; slug is None (single-product) or the product slug."""
    out: Dict[Tuple[str, Optional[str]], Path] = {}
    for p in sorted(design_path.parent.glob("DESIGN__*.yaml")):
        middle = p.name[len("DESIGN__"):-len(".yaml")]
        for kind in ("tokens", "assets"):
            if middle == kind:
                out[(kind, None)] = p
            elif middle.endswith(f"__{kind}"):
                out[(kind, middle[: -len(f"__{kind}")])] = p
    return out


def check_composition(
    design: Design, sub_files: Dict[Tuple[str, Optional[str]], Path]
) -> List[str]:
    """Composition consistency, per scope. Returns error strings."""
    errors: List[str] = []
    for label, scope, slug in scopes_of(design):
        fs = getattr(scope, "functional_structure", None)
        if _is_empty(fs):
            continue
        # headless exclusivity
        if _has(fs, FunctionalStructure.headless) and len(fs) > 1:
            errors.append(
                f"{label}functional_structure: 'headless' is exclusive and cannot "
                f"co-occur with token_based_ui/asset_pipeline (got {[m.value for m in fs]})"
            )
        ad = getattr(scope, "aesthetic_direction", None)
        sub = getattr(scope, "sub_artifacts", None)

        # aesthetic_direction present unless purely headless
        if not _is_pure_headless(fs):
            if ad is None or _is_empty(getattr(ad, "style_family", None)):
                errors.append(
                    f"{label}aesthetic_direction is required when the structure is not "
                    f"purely headless"
                )

        needs_tokens = _has(fs, FunctionalStructure.token_based_ui)
        requires_assets = _has(fs, FunctionalStructure.asset_pipeline) or bool(
            ad is not None and getattr(ad, "requires_custom_assets", None)
        )

        tokens_path = (sub.tokens if sub else None)
        assets_path = (sub.assets if sub else None)
        tokens_on_disk = (("tokens", slug) in sub_files)
        assets_on_disk = (("assets", slug) in sub_files)

        # tokens
        if needs_tokens:
            if not tokens_path:
                errors.append(f"{label}sub_artifacts.tokens must be set (token_based_ui selected)")
            if not tokens_on_disk:
                errors.append(
                    f"{label}token_based_ui selected but no DESIGN__tokens.yaml found on disk"
                )
        else:
            if tokens_path:
                errors.append(
                    f"{label}sub_artifacts.tokens is set but token_based_ui is not in "
                    f"functional_structure (orphan tokens reference)"
                )
            if tokens_on_disk:
                errors.append(
                    f"{label}a DESIGN__tokens.yaml exists but token_based_ui is not selected "
                    f"(orphan tokens file)"
                )

        # assets
        if requires_assets:
            if not assets_path:
                errors.append(
                    f"{label}sub_artifacts.assets must be set (asset_pipeline selected or "
                    f"requires_custom_assets is true)"
                )
            if not assets_on_disk:
                errors.append(
                    f"{label}assets required (asset_pipeline / requires_custom_assets) but no "
                    f"DESIGN__assets.yaml found on disk"
                )
        else:
            if assets_path:
                errors.append(
                    f"{label}sub_artifacts.assets is set but neither asset_pipeline nor "
                    f"requires_custom_assets applies (orphan assets reference)"
                )
            if assets_on_disk:
                errors.append(
                    f"{label}a DESIGN__assets.yaml exists but neither asset_pipeline nor "
                    f"requires_custom_assets applies (orphan assets file)"
                )
    return errors


class DeferralIndex:
    """The DEFER half of the asset-brief coverage gate (CLAUDE.md 6), one
    index per product scope. Pattern replicated from the task validator's
    DeferralIndex (not imported — validators are standalone).

    Canonical channel: `deferrals: [{id, reason}]` (alias
    `deferred_requirements`) on the scope that owns the asset — top level in
    single-product mode, products.<slug> in monorepo mode. AST id spaces are
    per product, so only a per-product declaration can say WHICH product's
    AST-NNN is deferred. A malformed entry (no id, or no reason) defers
    nothing and is reported.

    DEPRECATED channel (honoured for one more version): the AST id appearing
    anywhere in the top-level design_warnings — pooled across every product,
    which is exactly why it is deprecated. Every id that fell through to the
    prose match lands in prose_only and is reported once per run.
    """

    def __init__(self, scope_label: str, scope: object,
                 warnings: List[str]) -> None:
        self.declared: Dict[str, str] = {}
        self.shape_warnings: List[str] = []
        self.prose_only: set = set()
        self.prose_ok = _prose_deferrals_allowed(scope)
        self.warnings = [warning_text(w) for w in (warnings or [])]
        if scope is None:
            return
        field = "deferrals"
        raw = getattr(scope, "deferrals", None)
        if raw is None:
            raw = getattr(scope, "deferred_requirements", None)
            field = "deferred_requirements"
        for i, entry in enumerate(raw or []):
            where = f"{scope_label}{field}[{i}]"
            if not isinstance(entry, dict):
                self.shape_warnings.append(
                    f"{where} is not a mapping - expected {{id, reason}}; "
                    f"it defers nothing"
                )
                continue
            eid = str(entry.get("id") or "").strip()
            reason = str(entry.get("reason") or "").strip()
            if not eid:
                self.shape_warnings.append(
                    f"{where} declares no id - it defers nothing"
                )
                continue
            if not reason:
                self.shape_warnings.append(
                    f"{where} defers '{eid}' with no reason - an unauditable "
                    f"deferral defers nothing; the coverage gate for '{eid}' "
                    f"stays armed"
                )
                continue
            self.declared[eid.upper()] = reason

        # A typed WRN entry with `kind: deferral` and `defers: [...]` declares
        # exactly what a `deferrals` entry declares, written where the author
        # already writes it. Reading it here is what lets the prose word-match
        # below be retired (CLAUDE.md sections 2 and 6).
        for _w in (warnings or []):
            if not isinstance(_w, dict):
                continue
            if str(_w.get("kind") or "").strip() != "deferral":
                continue
            _reason = str(_w.get("text") or "").strip()
            if not _reason:
                continue
            _ids = [str(_e).strip() for _e in (_w.get("defers") or []) if str(_e).strip()]
            for _eid in _ids:
                self.declared.setdefault(_eid.upper(), _reason)
            # Warn-first (CLAUDE.md 10, ledger IMP-109): the canonical WRN block
            # ignores a mapping whose id is not WRN-NNN, yet its deferral still
            # counts for one more version - say so instead of honouring it silently.
            _wid = str(_w.get("id") or "").strip()
            if _ids and not _WRN_ID_RE.match(_wid):
                self.shape_warnings.append(
                    f"{scope_label}design_warnings entry '{_wid}' still defers "
                    f"{', '.join(_ids)}, but that id is not of the form WRN-NNN, so the "
                    f"warning itself is ignored. The deferral counts for one more version "
                    f"only - give the warning a WRN-NNN id."
                )

    def defer(self, aid: str) -> bool:
        s = str(aid).strip()
        if not s:
            return False
        if s.upper() in self.declared:
            return True
        pat = re.compile(r"\b" + re.escape(s) + r"\b")
        if self.prose_ok and any(pat.search(w) for w in self.warnings):
            self.prose_only.add(s)
            return True
        return False


def build_deferral_indexes(design: Design) -> Dict[Optional[str], DeferralIndex]:
    """One DeferralIndex per product scope (slug None = single-product top
    level), all sharing the pooled top-level design_warnings as the
    deprecated prose fallback."""
    out: Dict[Optional[str], DeferralIndex] = {}
    for label, scope, slug in scopes_of(design):
        out[slug] = DeferralIndex(label, scope, design.design_warnings)
    return out


def check_asset_brief_coverage(
    design: Design,
    assets_by_slug: Dict[Optional[str], DesignAssets],
    dfr_by_slug: Dict[Optional[str], DeferralIndex],
) -> List[str]:
    """Trace-or-defer: every to_be_generated asset has a brief OR is deferred —
    via the owning scope's structured `deferrals` list first, via an AST
    mention in DESIGN.yaml.design_warnings only as the deprecated fallback
    (see DeferralIndex)."""
    uncovered: List[str] = []
    for slug, assets in assets_by_slug.items():
        label = (
            "DESIGN__assets.yaml" if slug is None else f"DESIGN__{slug}__assets.yaml"
        )
        # An assets file with no matching product scope still gets the pooled
        # prose fallback, so pre-DeferralIndex behaviour is preserved.
        idx = dfr_by_slug.setdefault(
            slug, DeferralIndex("", None, design.design_warnings)
        )
        for i, a in enumerate(assets.assets or []):
            if a.source == AssetSource.to_be_generated and a.generation_brief is None:
                aid = (a.id or "").strip()
                if aid and idx.defer(aid):
                    continue  # explicitly deferred — counts as covered
                uncovered.append(
                    f"{label}: assets[{i}] ({aid or 'no-id'}) is to_be_generated but has no "
                    f"generation_brief and no deferral"
                )
    return uncovered


# =============================================================================
# Provenance staleness (CLAUDE.md 7) — warn-level, never blocks
# =============================================================================


def _index_hashes(docs_dir: Path) -> Dict[str, str]:
    """basename -> 16-hex content hash from docs/INDEX.yaml generated_from.
    Empty when the index is absent or unreadable (project never ran setup)."""
    idx = docs_dir / "INDEX.yaml"
    if not idx.exists():
        return {}
    try:
        raw = yaml.safe_load(idx.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError, UnicodeDecodeError):
        return {}
    out: Dict[str, str] = {}
    gf = raw.get("generated_from") if isinstance(raw, dict) else None
    for k, v in (gf or {}).items():
        if isinstance(v, dict) and v.get("sha256"):
            out[Path(str(k)).name] = str(v["sha256"])[:16]
    return out


def _content_hash_16(path: Path) -> Optional[str]:
    """The 16-hex TEXT-level content hash `docs_index.py --hash` prints:
    sha256 over the decoded text re-encoded as UTF-8, so CRLF and LF checkouts
    of the same file hash alike. Never hash raw file bytes."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def check_provenance(
    meta: DesignMetadata, artifact_path: Path, no_prov_gate: bool
) -> List[str]:
    """WARNING (never blocks) — provenance staleness (CLAUDE.md 7).

    Compares each recorded metadata.upstream_provenance sha256 to the
    upstream's current content hash. A finished artifact recording no
    provenance at all is reported only at/above schema version 2.0
    (no_prov_gate) so older artifacts are not nagged.
    """
    warns: List[str] = []
    prov = [e for e in (getattr(meta, "upstream_provenance", None) or [])
            if isinstance(e, dict)]
    if not prov:
        if meta.status == "complete" and no_prov_gate:
            warns.append(
                "no metadata.upstream_provenance is recorded, so later runs "
                "cannot tell when an upstream moves under this artifact - "
                "re-running /sdlc:design records the snapshot"
            )
        return warns
    index_hashes = _index_hashes(artifact_path.parent)
    for entry in prov:
        f = str(entry.get("file") or "").strip()
        recorded = str(entry.get("sha256") or "").strip()[:16]
        if not f or not recorded:
            continue  # partial records are tolerated (CLAUDE.md 7)
        base = Path(f).name
        current = index_hashes.get(base)
        if current is None:
            up_path = artifact_path.parent / base
            if not up_path.exists():
                warns.append(
                    f"{f} is recorded as an upstream but was not found next to "
                    f"{artifact_path.name} - cannot tell whether it changed"
                )
                continue
            current = _content_hash_16(up_path)
        if current and current != recorded:
            warns.append(
                f"built against an older {f} - run /sdlc:design --reconcile to "
                f"review the delta"
            )
    return warns


# =============================================================================
# File loading / orchestration
# =============================================================================


def _load_yaml(path: Path) -> Tuple[Any, Optional[str]]:
    if not path.exists():
        return None, f"file not found: {path}"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return None, f"YAML parse error in {path}: {e}"
    if raw is None:
        return None, f"{path} is empty"
    if not isinstance(raw, dict):
        return None, f"{path} top level must be a mapping, got {type(raw).__name__}"
    return raw, None


def _format_pydantic_errors(err: ValidationError) -> List[str]:
    out: List[str] = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e.get("loc", ()))
        out.append(f"{loc}: {e.get('msg', 'invalid')}")
    return out


def validate_all(design_path: Path) -> int:
    # 1) DESIGN.yaml
    raw, err = _load_yaml(design_path)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2
    try:
        design = Design.model_validate(raw)
    except ValidationError as e:
        print(f"[FAIL] {design_path} does not match the schema. No later "
              f"skill can read it until these fields are fixed:\n")
        for line in _format_pydantic_errors(e):
            print(f"  - {line}")
        return 1

    # 2) sub-files
    sub_files = discover_sub_files(design_path)
    tokens_by_slug: Dict[Optional[str], DesignTokens] = {}
    assets_by_slug: Dict[Optional[str], DesignAssets] = {}
    for (kind, slug), p in sub_files.items():
        s_raw, s_err = _load_yaml(p)
        if s_err:
            print(f"ERROR: {s_err}", file=sys.stderr)
            return 2
        try:
            if kind == "tokens":
                tokens_by_slug[slug] = DesignTokens.model_validate(s_raw)
            else:
                assets_by_slug[slug] = DesignAssets.model_validate(s_raw)
        except ValidationError as e:
            print(f"[FAIL] {p.name} does not match the schema. No later "
              f"skill can read it until these fields are fixed:\n")
            for line in _format_pydantic_errors(e):
                print(f"  - {line}")
            return 1

    # 3) required-field checks
    missing = check_design_required(design)
    for slug, t in tokens_by_slug.items():
        lbl = "DESIGN__tokens.yaml" if slug is None else f"DESIGN__{slug}__tokens.yaml"
        missing.extend(check_tokens_required(t, lbl))
    for slug, a in assets_by_slug.items():
        lbl = "DESIGN__assets.yaml" if slug is None else f"DESIGN__{slug}__assets.yaml"
        missing.extend(check_assets_required(a, lbl))

    # 4) ID-prefix format checks
    id_errors = check_design_id_prefixes(design)
    soft_warnings: List[str] = []
    for slug, a in assets_by_slug.items():
        lbl = "DESIGN__assets.yaml" if slug is None else f"DESIGN__{slug}__assets.yaml"
        id_errors.extend(check_assets_id_prefixes(a, lbl))
        soft_warnings.extend(check_asset_type_taxonomy(a, lbl))

    # 5) composition consistency
    comp_errors = check_composition(design, sub_files)

    # 6) asset-brief coverage (structured deferrals first; prose fallback
    # deprecated — see DeferralIndex)
    dfr_by_slug = build_deferral_indexes(design)
    uncovered = check_asset_brief_coverage(design, assets_by_slug, dfr_by_slug)
    dfr_shape: List[str] = []
    for idx in dfr_by_slug.values():
        dfr_shape.extend(idx.shape_warnings)
    if design.metadata.monorepo and (design.deferrals or design.deferred_requirements):
        dfr_shape.append(
            "top-level deferrals defer nothing in monorepo mode - AST id spaces "
            "are per product, so declare each one under products.<slug>.deferrals"
        )
    prose_only = sorted({s for idx in dfr_by_slug.values() for s in idx.prose_only})

    # 7) provenance-staleness warning (never blocks, CLAUDE.md 7)
    prov_warnings = check_provenance(
        design.metadata, design_path,
        no_prov_gate=_version_tuple(design.metadata.design_version) >= (2, 0),
    )
    # Ledger IMP-127: NEXT names the reconcile form while an upstream is stale.
    stale_upstream = [w for w in prov_warnings if "built against an older" in str(w)]

    status = design.metadata.status
    n_tokens, n_assets = len(tokens_by_slug), len(assets_by_slug)
    blocking = bool(missing or id_errors or comp_errors or uncovered)

    # ---- "this project has no visual design" short-circuit ----------------
    # A not_applicable artifact is deliberately empty. The required-field and
    # composition checks above would all fire on it and all be wrong: there is
    # no aesthetic direction to name and no sub-file to require, because the
    # user said this project has no visual design at all. The reason is the one
    # thing still required.
    if design.metadata.applicability == "not_applicable":
        na_problems: List[str] = []
        if not (design.metadata.applicability_rationale or "").strip():
            na_problems.append(
                "metadata.applicability says this project has no visual design but "
                "gives no reason - set metadata.applicability_rationale to one "
                "sentence saying why (e.g. 'headless service; output conventions "
                "live in ARCH and code style')."
            )
        if n_tokens or n_assets:
            na_problems.append(
                f"metadata.applicability says this project has no visual design, "
                f"but {n_tokens} token file(s) and {n_assets} asset file(s) are "
                f"still present. Either drop them or set applicability back to "
                f"'applicable'."
            )
        if status == "complete" and na_problems:
            print(f"[FAIL] {design_path} says it is finished and not applicable, but "
                  f"{len(na_problems)} thing(s) are wrong.")
            print_findings(na_problems, [])
            print_next("fix the items above, then re-run this check.")
            return 1
        if status != "complete":
            print(f"[DRAFT] {design_path} records that this project has no visual "
                  f"design, but is still marked draft. Later skills will refuse it "
                  f"until it says 'complete'.")
            print_findings(na_problems, [], blocking_header="TO FINISH IT")
            print_next("set metadata.status: complete.")
            return 0
        print(f"[OK] {design_path} records that this project has no visual design, so "
              f"there is nothing to specify: "
              f"{design.metadata.applicability_rationale} /sdlc:data and everything "
              f"after it will skip design without asking.")
        print_findings([], [])
        print_next("/sdlc:data")
        return 0

    def _problems() -> List[str]:
        out: List[str] = []
        out += [f"a required field is empty: {m}" for m in missing]
        out += [f"the design files do not fit together - {m}" for m in comp_errors]
        out += [f"wrong id format - {m}" for m in id_errors]
        if uncovered:
            out.append(
                f"{len(uncovered)} asset(s) are marked to-be-generated but carry no "
                f"brief saying what to generate: {join_ids(uncovered)}. Write a "
                f"generation_brief for each, or defer it with a reason in the "
                f"owning scope's `deferrals` list."
            )
        return out

    def _soft() -> List[str]:
        out: List[str] = []
        if soft_warnings:
            out.append(
                f"{len(soft_warnings)} asset(s) use an asset_type outside the standard "
                f"list, so downstream tooling may not know how to build them: "
                f"{join_ids(soft_warnings)}"
            )
        out.extend(prov_warnings)
        out.extend(dfr_shape)
        if prose_only:
            out.append(
                f"{len(prose_only)} asset(s) count as deferred only because a "
                f"design_warnings note happens to mention them: "
                f"{', '.join(prose_only)}. That is fragile - ANY note naming an id "
                f"silences its coverage gate, pooled across every product. Declare "
                f"each one you meant in the owning scope's `deferrals` list as "
                f"{{id, reason}}. Notes still work for one more version. "
                f"[deferral hygiene]"
            )
        return out

    soft = _soft()

    if status == "complete":
        problems = _problems()
        if problems:
            print(f"[FAIL] {design_path} says it is finished, but {len(problems)} "
                  f"thing(s) are wrong. Later skills will refuse it.")
            print_findings(problems, soft)
            print_next("fix the items above, then re-run this check.",
                       "Re-running /sdlc:design walks you through them.")
            return 1
        print(f"[OK] {design_path} is finished - {n_tokens} token file(s), "
              f"{n_assets} asset file(s). /sdlc:data can run it.")
        print_findings([], soft)
        if stale_upstream:
            print_next(f"/sdlc:design --reconcile  ({STALE_NOTE})", "then /sdlc:data",
                       show_glossary=bool(soft))
        else:
            print_next("/sdlc:data", show_glossary=bool(soft))
        return 0

    # status == "draft"
    todo = _problems()
    print(f"[DRAFT] {design_path} is saved but not finished - {n_tokens} token "
          f"file(s), {n_assets} asset file(s). Later skills will refuse it until "
          f"it says 'complete'.")
    print_findings(todo, soft, blocking_header="TO FINISH IT")
    print_next("re-run /sdlc:design to continue, or set metadata.status: complete.",
               show_glossary=bool(todo or soft))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate DESIGN.yaml + its conditional sub-files against the sdlc-design schema."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs", "DESIGN.yaml"),
        help="Path to DESIGN.yaml (default: ./docs/DESIGN.yaml). DESIGN__*.yaml "
        "siblings in the same directory are validated automatically.",
    )
    args = parser.parse_args(argv)
    return validate_all(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
