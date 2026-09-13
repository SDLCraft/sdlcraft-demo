"""Validate UX.yaml + every UX__*.yaml against the canonical sdlc-ux schema,
and run the PRD-flow coverage check.

Run from the project root:

    python sdlc/skills/ux/validate_schema.py
    python sdlc/skills/ux/validate_schema.py --path docs/UX.yaml

Validates:
    1. docs/UX.yaml (or --path) — global UX contract.
    2. Every docs/UX__*.yaml sibling — one per surface.
    3. ID-family prefix formats: SCR-NNN on surface ids, WRN-NNN on
       ux_warnings, WKF-NNN in traces_workflows, FR-NNN or NFR-NNN in
       implements_requirements, ENT-NNN in references_entities.
    4. Coverage: every WKF-NNN id in PRD use_cases.core_workflows must be
       referenced by at least one UX__*.yaml via `traces_workflows`.
       Coverage matches by WKF-NNN id (not verbatim text), so PRD text
       edits don't break UX traces.
    5. FR-coverage WARNING (trace-or-defer, never blocks): PRD FRs no surface
       implements are reported unless deferred via the structured top-level
       `deferrals: [{id, reason}]` list (alias `deferred_requirements`;
       per-product entries under products.<slug> in monorepo mode). A
       ux_warnings note naming the id still defers it for one more version,
       and every id that fell through to that prose fallback is reported.
    6. Provenance-staleness WARNING (never blocks): each recorded
       metadata.upstream_provenance sha256 is compared to the upstream's
       current content hash (docs/INDEX.yaml generated_from, else computed
       as sha256 over the UTF-8 text - identical to docs_index.py --hash).
    7. Deferred-FR-names-a-command WARNING (never blocks): a deferred FR
       whose PRD text names `<cli.root_command> <verb>` in backticks is
       reported, because a deferral covers the WHOLE requirement and the
       command clause is then specified nowhere (ledger IMP-076).

Exit codes:
    0 — schema valid; either status='complete' (with all required fields
        filled AND coverage check passing) or status='draft'.
    1 — schema invalid (pydantic error), OR status='complete' but required
        fields are missing, OR status='complete' but coverage is incomplete,
        OR status='complete' but ID-prefix format violations exist.
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
from typing import Any, Dict, List, Literal, Optional, Set, Tuple


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
        "ERROR: pyyaml is required.\n" "Install with:  pip install pyyaml",
        file=sys.stderr,
    )
    sys.exit(3)

try:
    from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
except ImportError:
    print(
        "ERROR: pydantic v2 is required.\n" "Install with:  pip install 'pydantic>=2'",
        file=sys.stderr,
    )
    sys.exit(3)


# =============================================================================
# ID-family prefix regexes (kept in lockstep with UX.schema.yaml header)
# =============================================================================

# Three-digit padding minimum; allow longer numbers for projects with many items.
ID_PATTERN = r"-\d{3,}"
SCR_ID_RE = re.compile(rf"^SCR{ID_PATTERN}$")
WKF_ID_RE = re.compile(rf"^WKF{ID_PATTERN}$")
FR_ID_RE = re.compile(rf"^FR{ID_PATTERN}$")
ENT_ID_RE = re.compile(rf"^ENT{ID_PATTERN}$")
# implements_requirements may trace BOTH functional (FR-NNN) and non-functional
# (NFR-NNN) requirements — a surface can deliver a feature and also be the place
# an NFR is realized (a per-call timeout cap, an input-containment boundary).
FR_OR_NFR_ID_RE = re.compile(rf"^(?:FR|NFR){ID_PATTERN}$")

# Extract the leading WKF-NNN id from a PRD core_workflows entry of the form
# "WKF-001: <verbatim description>". The PRD writes the verbatim form; UX
# references only the leading id.
WKF_PREFIX_EXTRACT_RE = re.compile(rf"^(WKF{ID_PATTERN})(?::|\s|$)")


def _version_tuple(v: object) -> tuple:
    """Parse '2.0' / '1.1' into a comparable (major, minor). Unparseable -> (0, 0)."""
    m = re.match(r"^\s*(\d+)(?:\.(\d+))?", str(v or ""))
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2) or 0))

def _prose_deferrals_allowed(obj, _fields=('ux_version',), _floor=2):
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
# Enums (kept in lockstep with UX.schema.yaml and UX__SURFACE.schema.yaml)
# =============================================================================


class Confidence(str, Enum):
    confirmed = "confirmed"
    inferred = "inferred"
    assumption = "assumption"


class SurfaceFamily(str, Enum):
    cli = "cli"
    web = "web"
    mobile = "mobile"
    desktop = "desktop"
    tui = "tui"          # full-screen terminal UI (curses/textual) — screen-like
    voice = "voice"      # voice / conversational, turn-based (no visual screens)
    service = "service"  # headless network service (no human UI surface)
    library = "library"  # headless code library / SDK (no human UI surface)
    mixed = "mixed"


# Headless families have no traditional visual screens: their "surfaces" are
# commands (cli), components/endpoints (service), or public API symbols
# (library). The interview emits a minimal spec for these — see
# references/surface-discovery.md.
HEADLESS_FAMILIES = {SurfaceFamily.cli, SurfaceFamily.service, SurfaceFamily.library}


class NavigationModelType(str, Enum):
    sitemap = "sitemap"
    command_tree = "command_tree"
    state_graph = "state_graph"
    hybrid = "hybrid"


class SurfaceStatus(str, Enum):
    defined = "defined"      # id + type known, no deep-dive yet
    draft = "draft"          # deep-dive started, not approved
    confirmed = "confirmed"  # deep-dive complete + user-approved
    proposed = "proposed"    # fully specced but deferred — targets a
                             # nice-to-have / post-MVP FR; kept in the inventory
                             # so the surface contract isn't lost


class SurfaceType(str, Enum):
    screen = "screen"
    modal = "modal"
    panel = "panel"
    drawer = "drawer"
    cli_command = "cli_command"
    flow_step = "flow_step"
    empty_state = "empty_state"
    toast = "toast"
    overlay = "overlay"
    tab = "tab"
    page = "page"
    dialog = "dialog"
    other = "other"


class ThemingApproach(str, Enum):
    design_tokens_dtcg = "design_tokens_dtcg"
    tailwind_utility = "tailwind_utility"
    css_variables = "css_variables"
    library_theme = "library_theme"
    none = "none"
    custom = "custom"


class WcagTarget(str, Enum):
    wcag_a = "wcag_a"
    wcag_aa = "wcag_aa"
    wcag_aaa = "wcag_aaa"
    none_yet = "none_yet"
    not_applicable_cli = "not_applicable_cli"


class CommandShape(str, Enum):
    verb_noun = "verb_noun"
    noun_verb = "noun_verb"
    flat = "flat"
    mixed = "mixed"


class ArgConventions(str, Enum):
    posix = "posix"
    gnu = "gnu"
    custom = "custom"


class HelpTextFormat(str, Enum):
    auto_generated = "auto_generated"
    authored = "authored"
    hybrid = "hybrid"


# =============================================================================
# UX.yaml — top-level theme models
# =============================================================================

# extra="allow" gives forward-compat for new question additions; enum values
# are still strictly validated.
_BASE_CONFIG = ConfigDict(extra="allow", str_strip_whitespace=True)


class _ThemeBase(BaseModel):
    model_config = _BASE_CONFIG


class DesignPrinciples(_ThemeBase):
    tenets: Optional[List[str]] = None
    anti_patterns: Optional[List[str]] = None
    inspiration_refs: Optional[List[str]] = None


class NavigationModel(_ThemeBase):
    type: Optional[NavigationModelType] = None
    type_confidence: Optional[Confidence] = None
    top_level_nodes: Optional[List[str]] = None
    deep_link_strategy: Optional[str] = None
    auth_required_routes: Optional[List[str]] = None
    sitemap: Optional[Any] = None
    command_tree: Optional[Any] = None
    state_graph: Optional[Any] = None


class SurfaceInventoryItem(_ThemeBase):
    id: Optional[str] = None  # SCR-NNN
    surface_id: Optional[str] = None
    surface_type: Optional[SurfaceType] = None
    status: Optional[SurfaceStatus] = None
    file_path: Optional[str] = None
    traces_workflows: Optional[List[str]] = None
    implements_requirements: Optional[List[str]] = None
    references_entities: Optional[List[str]] = None


class ThemingTokens(_ThemeBase):
    colors: Optional[Any] = None
    typography: Optional[Any] = None
    spacing: Optional[Any] = None
    radii: Optional[Any] = None
    shadows: Optional[Any] = None
    motion: Optional[Any] = None


class ComponentLibrary(_ThemeBase):
    name: Optional[str] = None
    name_rationale: Optional[str] = None
    name_confidence: Optional[Confidence] = None
    theming_approach: Optional[ThemingApproach] = None
    theming_approach_confidence: Optional[Confidence] = None
    theming_tokens: Optional[ThemingTokens] = None


class StatePatterns(_ThemeBase):
    default: Optional[str] = None
    loading: Optional[str] = None
    empty: Optional[str] = None
    error: Optional[str] = None
    error_confidence: Optional[Confidence] = None
    success: Optional[str] = None


class ContentRules(_ThemeBase):
    tone: Optional[str] = None
    tone_confidence: Optional[Confidence] = None
    error_message_style: Optional[str] = None
    terminology: Optional[List[Any]] = None
    copy_length_limits: Optional[Any] = None


class AccessibilityBaseline(_ThemeBase):
    wcag_target: Optional[WcagTarget] = None
    wcag_target_confidence: Optional[Confidence] = None
    keyboard_only: Optional[bool] = None
    screen_reader_notes: Optional[List[str]] = None
    color_contrast_minimum: Optional[str] = None
    motion_preferences: Optional[bool] = None


class Localisation(_ThemeBase):
    enabled: Optional[bool] = None
    default_locale: Optional[str] = None
    target_locales: Optional[List[str]] = None
    framework: Optional[str] = None
    rtl_support: Optional[bool] = None


class CliOutputFormats(_ThemeBase):
    supported: Optional[List[str]] = None
    default: Optional[str] = None


class CliConfigFile(_ThemeBase):
    location: Optional[str] = None
    precedence: Optional[str] = None
    env_prefix: Optional[str] = None


class Cli(_ThemeBase):
    root_command: Optional[str] = None
    root_command_confidence: Optional[Confidence] = None
    command_shape: Optional[CommandShape] = None
    arg_parsing_library: Optional[str] = None
    arg_parsing_library_rationale: Optional[str] = None
    arg_parsing_library_confidence: Optional[Confidence] = None
    arg_conventions: Optional[ArgConventions] = None
    help_text_format: Optional[HelpTextFormat] = None
    output_formats: Optional[CliOutputFormats] = None
    exit_code_convention: Optional[str] = None
    # exit_codes is a Dict[str, Any] so projects can use either the legacy
    # {code: "description"} string-only shape or the new
    # {code: {description, implements_requirements, ...}} mapping shape.
    # ID-prefix checks below walk the dict and validate FR-NNN refs when
    # present.
    exit_codes: Optional[Dict[str, Any]] = None
    interactive_mode: Optional[Any] = None
    config_file: Optional[CliConfigFile] = None


# -----------------------------------------------------------------------------
# Top-level UX models
# -----------------------------------------------------------------------------


class UXMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    ux_version: str
    last_updated: str
    generated_by: str = "sdlc-ux"
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
    # One entry per upstream artifact consumed, each a mapping
    # {file, session_id, last_updated, sha256}. Type-checked as a list of
    # mappings only — see CLAUDE.md §7 "Upstream-change re-invocation".
    upstream_provenance: Optional[List[Dict[str, Any]]] = None


class UXProduct(_ThemeBase):
    """One product's UX contract in monorepo mode."""

    # Structured deferrals (CLAUDE.md 6): [{id, reason}] entries read FIRST by
    # the FR-coverage warning; an entry with no reason defers nothing.
    deferrals: Optional[List[Dict[str, Any]]] = None
    deferred_requirements: Optional[List[Dict[str, Any]]] = None  # accepted alias

    surface_family: Optional[SurfaceFamily] = None
    surface_family_confidence: Optional[Confidence] = None
    surface_family_members: Optional[List[SurfaceFamily]] = None
    device_targets: Optional[List[str]] = None
    device_targets_confidence: Optional[Confidence] = None
    viewport_breakpoints: Optional[List[str]] = None

    design_principles: Optional[DesignPrinciples] = None
    navigation_model: Optional[NavigationModel] = None
    surface_inventory: Optional[List[SurfaceInventoryItem]] = None
    component_library: Optional[ComponentLibrary] = None
    state_patterns: Optional[StatePatterns] = None
    content_rules: Optional[ContentRules] = None
    accessibility: Optional[AccessibilityBaseline] = None
    localisation: Optional[Localisation] = None
    cli: Optional[Cli] = None


class UX(BaseModel):
    """Top-level UX.yaml document."""

    model_config = ConfigDict(extra="allow")

    metadata: UXMetadata
    ux_warnings: List[Any] = Field(default_factory=list)  # str | typed WarningItem mapping

    # Structured deferrals (CLAUDE.md 6): the DEFER half of the FR-coverage
    # trace-or-defer. Read FIRST wherever a prose ux_warnings mention used to
    # count; an entry with no reason defers nothing.
    deferrals: Optional[List[Dict[str, Any]]] = None
    deferred_requirements: Optional[List[Dict[str, Any]]] = None  # accepted alias

    # Single-product mode — all theme blocks live at top level
    surface_family: Optional[SurfaceFamily] = None
    surface_family_confidence: Optional[Confidence] = None
    surface_family_members: Optional[List[SurfaceFamily]] = None
    device_targets: Optional[List[str]] = None
    device_targets_confidence: Optional[Confidence] = None
    viewport_breakpoints: Optional[List[str]] = None

    design_principles: Optional[DesignPrinciples] = None
    navigation_model: Optional[NavigationModel] = None
    surface_inventory: Optional[List[SurfaceInventoryItem]] = None
    component_library: Optional[ComponentLibrary] = None
    state_patterns: Optional[StatePatterns] = None
    content_rules: Optional[ContentRules] = None
    accessibility: Optional[AccessibilityBaseline] = None
    localisation: Optional[Localisation] = None
    cli: Optional[Cli] = None

    # Multi-product mode
    products: Optional[Dict[str, UXProduct]] = None

    @model_validator(mode="after")
    def _check_mode(self) -> "UX":
        single_themes = [
            self.surface_family,
            self.design_principles,
            self.navigation_model,
            self.surface_inventory,
            self.component_library,
            self.state_patterns,
            self.content_rules,
            self.accessibility,
            self.localisation,
            self.cli,
        ]
        any_single = any(t is not None for t in single_themes)

        if self.metadata.monorepo:
            if not self.products:
                raise ValueError(
                    "metadata.monorepo is true but `products` is missing or empty"
                )
            if any_single:
                raise ValueError(
                    "monorepo mode set but top-level theme blocks are present; "
                    "in monorepo mode every theme must live under `products.<slug>`"
                )
        else:
            if self.products:
                raise ValueError(
                    "`products` is set but metadata.monorepo is false; "
                    "either set monorepo: true or move themes to top level"
                )
        return self


# =============================================================================
# UX__<surface>.yaml — per-surface model
# =============================================================================


class SurfaceMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    ux_surface_version: str
    last_updated: str
    generated_by: str = "sdlc-ux"
    session_id: str
    # "proposed" = the surface is fully specced but its owning FR is
    # nice-to-have / post-MVP, so it is intentionally deferred (a terminal,
    # non-draft state). Downstream consumers that gate on `complete` will skip
    # a `proposed` surface — which is the intent. The top-level UX.yaml stays
    # draft|complete; only per-surface artifacts may be `proposed`.
    status: Literal["draft", "complete", "proposed"] = "draft"
    changelog: Optional[List[str]] = None


class SurfaceLayout(_ThemeBase):
    region_tree: Optional[Any] = None
    cli_args: Optional[List[Any]] = None


class SurfaceStateBlock(_ThemeBase):
    description: Optional[str] = None
    content_outline: Optional[Any] = None
    recovery_action: Optional[str] = None  # only used by `error`


class SurfaceStates(_ThemeBase):
    default: Optional[Any] = None  # "inherit" | SurfaceStateBlock | null
    loading: Optional[Any] = None
    empty: Optional[Any] = None
    error: Optional[Any] = None
    success: Optional[Any] = None


class SurfaceInteraction(_ThemeBase):
    """One event handler downstream — typed so every run emits the same shape."""

    id: Optional[str] = None                    # kebab-case, unique per surface
    actor: Optional[str] = None                 # user | system
    trigger: Optional[str] = None               # click | submit | keypress | ... | cli_invoke
    trigger_target: Optional[str] = None        # component_id | "surface"
    preconditions: Optional[List[str]] = None
    effects: Optional[List[str]] = None
    target_surface: Optional[str] = None        # SCR-NNN | surface_id | null
    error_paths: Optional[List[str]] = None


class SurfaceComponent(_ThemeBase):
    """One component to instantiate — typed so codegen sees a stable contract."""

    id: Optional[str] = None                    # kebab-case, unique per surface
    type: Optional[str] = None                  # button | input | table | ... | custom
    library_ref: Optional[str] = None
    variants: Optional[List[str]] = None
    content_slots: Optional[Dict[str, Any]] = None
    aria_role: Optional[str] = None
    keyboard_shortcuts: Optional[List[str]] = None
    binds: Optional[List[str]] = None           # "Entity.field" data bindings — which
                                                # DATA-MODEL field each input/display
                                                # component reads or writes


class SurfaceValidationRule(_ThemeBase):
    field: Optional[str] = None                 # component_id of the input
    rules: Optional[List[str]] = None           # ["required", "max_length=140", ...]
    error_message: Optional[str] = None


class UXSurface(BaseModel):
    """Top-level per-surface document."""

    model_config = ConfigDict(extra="allow")

    metadata: SurfaceMetadata

    id: Optional[str] = None  # SCR-NNN
    surface_id: Optional[str] = None
    surface_type: Optional[SurfaceType] = None
    parent_surface: Optional[str] = None
    route: Optional[str] = None
    cli_invocation: Optional[str] = None
    entry_conditions: Optional[List[str]] = None
    exit_conditions: Optional[List[str]] = None
    layout: Optional[SurfaceLayout] = None
    states: Optional[SurfaceStates] = None
    interactions: Optional[List[SurfaceInteraction]] = None
    components: Optional[List[SurfaceComponent]] = None
    validation_rules: Optional[List[SurfaceValidationRule]] = None
    accessibility_notes: Optional[Any] = None  # list[string] | "inherit" | null
    traces_workflows: Optional[List[str]] = None
    implements_requirements: Optional[List[str]] = None
    references_entities: Optional[List[str]] = None
    notes: Optional[str] = None


# =============================================================================
# Required-field checks. Validation behaviour depends on metadata.status:
# drafts are tolerated, but `status: complete` requires every required path
# to be non-empty.
# =============================================================================

# UX.yaml required paths (relative to a product in monorepo mode, or top level).
UX_REQUIRED_PATHS: List[str] = [
    "surface_family",
    "design_principles.tenets",
    "navigation_model.type",
    "navigation_model.top_level_nodes",
    "surface_inventory",
    "component_library.name",
    "state_patterns.error",
    "content_rules.tone",
    "accessibility.wcag_target",
]

# CLI-specific required paths (only enforced when surface_family is cli or mixed).
UX_CLI_REQUIRED_PATHS: List[str] = [
    "cli.root_command",
    "cli.arg_parsing_library",
    "cli.output_formats.supported",
    "cli.output_formats.default",
]

# UX__<surface>.yaml required paths.
SURFACE_REQUIRED_PATHS: List[str] = [
    "id",
    "surface_id",
    "surface_type",
    "layout",
    "traces_workflows",
]


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


def check_ux_required(ux: UX) -> List[str]:
    """Return list of missing required UX.yaml field paths."""
    missing: List[str] = []

    def _check(scope_label: str, root: object) -> None:
        for path in UX_REQUIRED_PATHS:
            if _is_empty(_get_dotted(root, path)):
                missing.append(f"{scope_label}{path}")
        # CLI-specific
        family = getattr(root, "surface_family", None)
        if family in (SurfaceFamily.cli, SurfaceFamily.mixed):
            for path in UX_CLI_REQUIRED_PATHS:
                if _is_empty(_get_dotted(root, path)):
                    missing.append(f"{scope_label}{path}")
        # Per-inventory-item required fields. Each surface in
        # surface_inventory must carry id/surface_id/surface_type/file_path
        # by the time the artifact claims complete; traces_workflows must
        # be non-None (empty list [] is allowed — see check_surface_required).
        inv: Optional[List[SurfaceInventoryItem]] = getattr(
            root, "surface_inventory", None
        )
        if inv:
            for i, item in enumerate(inv):
                where = f"{scope_label}surface_inventory[{i}]"
                if _is_empty(item.id):
                    missing.append(f"{where}.id")
                if _is_empty(item.surface_id):
                    missing.append(f"{where}.surface_id")
                if _is_empty(item.surface_type):
                    missing.append(f"{where}.surface_type")
                if _is_empty(item.file_path):
                    missing.append(f"{where}.file_path")
                if item.traces_workflows is None:
                    missing.append(f"{where}.traces_workflows")

    if ux.metadata.monorepo and ux.products:
        for slug, product in ux.products.items():
            _check(f"products.{slug}.", product)
    else:
        _check("", ux)

    return missing


def check_surface_required(surface: UXSurface, file_label: str) -> List[str]:
    """Return list of missing required fields for one surface yaml."""
    missing: List[str] = []
    for path in SURFACE_REQUIRED_PATHS:
        # traces_workflows: [] is allowed (non-flow surfaces) — only None/missing
        # counts as unfilled here; the coverage check handles flow obligations.
        if path == "traces_workflows":
            if _get_dotted(surface, path) is None:
                missing.append(f"{file_label}: {path}")
            continue
        if _is_empty(_get_dotted(surface, path)):
            missing.append(f"{file_label}: {path}")
    return missing


# =============================================================================
# ID-prefix format checks.
# All values are tested against the appropriate family's regex. Violations are
# returned as human-readable strings so the caller can print them.
# =============================================================================


def _check_list_prefix(
    values: Optional[List[str]],
    pattern: re.Pattern[str],
    expected: str,
    where: str,
) -> List[str]:
    """Return one error string per value that fails `pattern`."""
    if not values:
        return []
    errors: List[str] = []
    for v in values:
        if not isinstance(v, str) or not pattern.match(v.strip()):
            errors.append(
                f"{where}: '{v}' does not match {expected}"
            )
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


def check_ux_id_prefixes(ux: UX) -> List[str]:
    """Validate SCR/WRN/WKF/FR/ENT prefixes inside UX.yaml. Returns error
    strings; an empty list means all formats are valid.
    """
    errors: List[str] = []

    # ux_warnings — legacy "WRN-NNN: <message>" string, or a typed mapping
    errors.extend(check_warning_ids(ux.ux_warnings, "ux_warnings"))

    def _check_product(scope: str, product: object) -> None:
        inv: Optional[List[SurfaceInventoryItem]] = getattr(
            product, "surface_inventory", None
        )
        if inv:
            for i, item in enumerate(inv):
                where = f"{scope}surface_inventory[{i}]"
                if item.id is not None and not SCR_ID_RE.match(item.id.strip()):
                    errors.append(
                        f"{where}.id: '{item.id}' must match 'SCR-NNN'"
                    )
                errors.extend(
                    _check_list_prefix(
                        item.traces_workflows,
                        WKF_ID_RE,
                        "'WKF-NNN'",
                        f"{where}.traces_workflows",
                    )
                )
                errors.extend(
                    _check_list_prefix(
                        item.implements_requirements,
                        FR_OR_NFR_ID_RE,
                        "'FR-NNN' or 'NFR-NNN'",
                        f"{where}.implements_requirements",
                    )
                )
                errors.extend(
                    _check_list_prefix(
                        item.references_entities,
                        ENT_ID_RE,
                        "'ENT-NNN'",
                        f"{where}.references_entities",
                    )
                )
        cli: Optional[Cli] = getattr(product, "cli", None)
        if cli and cli.exit_codes:
            for code, spec in cli.exit_codes.items():
                if isinstance(spec, dict):
                    fr_refs = spec.get("implements_requirements")
                    errors.extend(
                        _check_list_prefix(
                            fr_refs if isinstance(fr_refs, list) else None,
                            FR_OR_NFR_ID_RE,
                            "'FR-NNN' or 'NFR-NNN'",
                            f"{scope}cli.exit_codes['{code}'].implements_requirements",
                        )
                    )

    if ux.metadata.monorepo and ux.products:
        for slug, product in ux.products.items():
            _check_product(f"products.{slug}.", product)
    else:
        _check_product("", ux)

    return errors


def check_surface_id_prefixes(surface: UXSurface, file_label: str) -> List[str]:
    """Validate prefixes inside a UX__<surface>.yaml file."""
    errors: List[str] = []

    if surface.id is not None and not SCR_ID_RE.match(surface.id.strip()):
        errors.append(f"{file_label}: id: '{surface.id}' must match 'SCR-NNN'")
    errors.extend(
        _check_list_prefix(
            surface.traces_workflows,
            WKF_ID_RE,
            "'WKF-NNN'",
            f"{file_label}: traces_workflows",
        )
    )
    errors.extend(
        _check_list_prefix(
            surface.implements_requirements,
            FR_OR_NFR_ID_RE,
            "'FR-NNN' or 'NFR-NNN'",
            f"{file_label}: implements_requirements",
        )
    )
    errors.extend(
        _check_list_prefix(
            surface.references_entities,
            ENT_ID_RE,
            "'ENT-NNN'",
            f"{file_label}: references_entities",
        )
    )
    return errors


# =============================================================================
# PRD-flow coverage check.
# Coverage matches by WKF-NNN id (not verbatim text). PRD core_workflows
# entries are of the form "WKF-NNN: <description>"; the leading id is
# extracted and compared against UX surface traces_workflows (which carry
# WKF-NNN ids only).
# =============================================================================


def load_prd_core_workflow_ids(prd_path: Path) -> List[str]:
    """Return list of WKF-NNN ids parsed out of PRD.use_cases.core_workflows.
    Empty if file missing or flows section absent. In monorepo mode, returns
    the union across products. Entries that don't begin with a WKF-NNN id are
    skipped (they'd fail PRD validation anyway).
    """
    if not prd_path.exists():
        return []
    try:
        raw = yaml.safe_load(prd_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    if not isinstance(raw, dict):
        return []

    ids: List[str] = []
    metadata = raw.get("metadata") or {}
    monorepo = bool(metadata.get("monorepo"))

    def _collect(workflows: Any) -> None:
        if not isinstance(workflows, list):
            return
        for entry in workflows:
            if not isinstance(entry, str):
                continue
            m = WKF_PREFIX_EXTRACT_RE.match(entry.strip())
            if m:
                ids.append(m.group(1))

    if monorepo:
        products = raw.get("products") or {}
        if isinstance(products, dict):
            for _, prod in products.items():
                if not isinstance(prod, dict):
                    continue
                uc = prod.get("use_cases") or {}
                cw = uc.get("core_workflows") if isinstance(uc, dict) else None
                _collect(cw)
    else:
        uc = raw.get("use_cases") or {}
        cw = uc.get("core_workflows") if isinstance(uc, dict) else None
        _collect(cw)

    return ids


def collect_traced_workflow_ids(surfaces: Dict[str, UXSurface]) -> List[str]:
    traced: List[str] = []
    for _, surface in surfaces.items():
        if surface.traces_workflows:
            traced.extend(
                str(x).strip() for x in surface.traces_workflows if x
            )
    return traced


def check_coverage(prd_ids: List[str], traced_ids: List[str]) -> List[str]:
    """Return list of PRD WKF-NNN ids with no surface trace."""
    traced_set = set(traced_ids)
    return [w for w in prd_ids if w not in traced_set]


_FR_HEAD_EXTRACT_RE = re.compile(r"^(FR-\d+)(?::|\s|$)")


def load_prd_fr_texts(prd_path: Path) -> Dict[str, str]:
    """Gating FR-NNN ids -> requirement text, from PRD functional_requirements
    (union across products in monorepo mode). D2 gating subset (FR_GATE,
    CLAUDE.md §10): the flat `features` list when present, else the legacy
    `must_have_features` ONLY — a legacy PRD's nice_to_have backlog stays
    outside the coverage advisory, preserving pre-D2 behavior. Empty when PRD
    is absent. Insertion-ordered, so list(...) is the id list."""
    if not prd_path.exists():
        return {}
    try:
        raw = yaml.safe_load(prd_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    if not isinstance(raw, dict):
        return {}
    texts: Dict[str, str] = {}

    def _collect(scope: Any) -> None:
        if not isinstance(scope, dict):
            return
        fr = scope.get("functional_requirements") or {}
        if not isinstance(fr, dict):
            return
        entries = fr.get("features")
        if not entries:  # legacy: must_have only (nice_to_have stays ungated)
            entries = fr.get("must_have_features") or []
        for entry in entries or []:
            if isinstance(entry, str):
                line = entry.strip()
                m = _FR_HEAD_EXTRACT_RE.match(line)
                if m and m.group(1) not in texts:
                    texts[m.group(1)] = line[m.end():].lstrip(": ").strip()

    if (raw.get("metadata") or {}).get("monorepo"):
        for prod in (raw.get("products") or {}).values():
            _collect(prod)
    else:
        _collect(raw)
    return texts


def load_prd_fr_ids(prd_path: Path) -> List[str]:
    """The gating FR-NNN ids (see load_prd_fr_texts)."""
    return list(load_prd_fr_texts(prd_path))


class DeferralIndex:
    """The DEFER half of the FR-coverage trace-or-defer (CLAUDE.md 6).
    Pattern replicated from the task validator's DeferralIndex (not imported —
    validators are standalone).

    Canonical channel: `deferrals: [{id, reason}]` (alias
    `deferred_requirements`) — top-level, or under products.<slug> in monorepo
    mode. Explicit, auditable, impossible to trigger by accident. A malformed
    entry (no id, or no reason) defers nothing and is reported.

    DEPRECATED channel (honoured for one more version): the id appearing as a
    whole word in any ux_warnings note. ANY note that happens to mention an id
    silences that id's coverage warning, so every id that fell through to the
    prose match is collected and reported once by deprecation_warning().
    """

    def __init__(self, ux: "UX") -> None:
        self.declared: Dict[str, str] = {}
        self.shape_warnings: List[str] = []
        self.prose_only: set = set()
        self.prose_ok = _prose_deferrals_allowed(ux)
        self.warnings: List[str] = list(_iter_ux_warnings(ux))
        scopes = [("", ux)] + [
            (f"products.{slug}.", prod)
            for slug, prod in (getattr(ux, "products", None) or {}).items()
        ]
        for scope_label, scope in scopes:
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
                        f"deferral defers nothing; the coverage warning for "
                        f"'{eid}' stays armed"
                    )
                    continue
                self.declared[eid.upper()] = reason

        # A typed WRN entry with `kind: deferral` and `defers: [...]` declares
        # exactly what a `deferrals` entry declares, written where the author
        # already writes it. Reading it here is what lets the prose word-match
        # below be retired (CLAUDE.md sections 2 and 6).
        for _w in ([w for s in _iter_ux_scopes(ux) for w in (getattr(s, "ux_warnings", None) or [])] or []):
            if not isinstance(_w, dict):
                continue
            if str(_w.get("kind") or "").strip() != "deferral":
                continue
            _reason = str(_w.get("text") or "").strip()
            if not _reason:
                continue
            for _eid in (_w.get("defers") or []):
                _eid = str(_eid).strip()
                if _eid:
                    self.declared.setdefault(_eid.upper(), _reason)

    def defer(self, fid: str) -> bool:
        s = str(fid).strip()
        if not s:
            return False
        if s.upper() in self.declared:
            return True
        pat = re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE)
        if self.prose_ok and any(pat.search(w) for w in self.warnings):
            self.prose_only.add(s)
            return True
        return False

    def deprecation_warning(self) -> Optional[str]:
        if not self.prose_only:
            return None
        return (
            f"{len(self.prose_only)} requirement(s) count as intentionally out of "
            f"UX scope only because an ux_warnings note happens to mention them: "
            f"{', '.join(sorted(self.prose_only))}. That is fragile - ANY note "
            f"naming an id silences that id's coverage warning. Declare each one "
            f"you meant in the top-level `deferrals` list as {{id, reason}}. "
            f"Notes still work for one more version. [deferral hygiene]"
        )


def _fr_covered_set(ux: "UX", surfaces: Dict[str, UXSurface]) -> Set[str]:
    """Every FR/NFR id some surface (file or inventory entry) or exit code
    traces - the TRACE half of trace-or-defer, shared by check_fr_coverage
    and check_deferred_fr_names_command."""
    covered = {
        str(x).strip().upper()
        for surface in surfaces.values()
        for x in (surface.implements_requirements or [])
    }
    for inv in _iter_inventory_items(ux):
        for x in getattr(inv, "implements_requirements", None) or []:
            covered.add(str(x).strip().upper())
    # cli.exit_codes[<code>].implements_requirements counts too - the schema
    # says so, and for a CLI an exit code is how a gate requirement reaches
    # the user; there is no screen to trace it to. Root and per-product
    # scopes alike (ledger IMP-046, aicf LSN-020).
    for scope in _iter_ux_scopes(ux):
        cli = getattr(scope, "cli", None)
        for spec in (getattr(cli, "exit_codes", None) or {}).values():
            if isinstance(spec, dict):
                for x in spec.get("implements_requirements") or []:
                    covered.add(str(x).strip().upper())
    return covered


def check_fr_coverage(
    prd_fr_ids: List[str], ux: "UX", surfaces: Dict[str, UXSurface],
    dfr: DeferralIndex,
) -> List[str]:
    """WARNING (never blocks) — FRs no surface implements.

    Trace-or-defer: an FR is covered when some surface (file or inventory
    entry) lists it in implements_requirements, or a cli.exit_codes entry
    does, OR it is deferred — via the
    structured `deferrals` list first, via a ux_warnings mention only as the
    deprecated fallback (see DeferralIndex). WKF coverage stays the blocking
    gate; this warning catches the FRs with no workflow AND no surface — the
    ones silently unrepresented at the UX layer.
    """
    covered = _fr_covered_set(ux, surfaces)
    return [
        f for f in prd_fr_ids
        if f.upper() not in covered and not dfr.defer(f)
    ]


def _root_commands(ux: "UX") -> List[str]:
    roots: List[str] = []
    for scope in _iter_ux_scopes(ux):
        cli = getattr(scope, "cli", None)
        root = str(getattr(cli, "root_command", None) or "").strip()
        if root and root not in roots:
            roots.append(root)
    return roots


def _commands_named_in(text: str, root: str) -> List[str]:
    """The `<root> <verb> [<verb>...]` commands a requirement text names in
    backticks, without the root: "`acme task add <title>`" -> "task add".
    Leading flags (`acme --json list`) are skipped; argument placeholders
    (<title>, [--flag]) end the command words."""
    pat = re.compile(
        r"`\s*" + re.escape(root)
        + r"(?:\s+-[\w-]+)*\s+(?P<cmd>[A-Za-z][\w-]*(?:\s+[A-Za-z][\w-]*)*)"
    )
    return [m.group("cmd").strip() for m in pat.finditer(text)]


def _surface_lookalike(
    cmd: str, root: str, ux: "UX", surfaces: Dict[str, UXSurface],
) -> Optional[str]:
    """A surface that already looks like the named command: an inventory
    surface_id equal to (or containing / contained in) the command's slug, or
    a UX__ file whose cli_invocation starts with `<root> <cmd>`."""
    slug = "-".join(cmd.lower().split())
    for inv in _iter_inventory_items(ux):
        sid = str(getattr(inv, "surface_id", None) or "").strip().lower()
        if sid and (sid == slug or slug in sid or sid in slug):
            return sid
    prefix = f"{root} {cmd}".lower()
    for surface in surfaces.values():
        inv_str = " ".join(str(surface.cli_invocation or "").lower().split())
        if inv_str.startswith(prefix) and (surface.surface_id or "").strip():
            return str(surface.surface_id).strip()
    return None


def check_deferred_fr_names_command(
    fr_texts: Dict[str, str], ux: "UX", surfaces: Dict[str, UXSurface],
    dfr: DeferralIndex,
) -> List[str]:
    """WARNING (never blocks) — a DEFERRED FR whose text names a command.

    Coverage is whole-FR: one deferral reason silences every clause of the
    requirement, including a clause that names `<root_command> <verb>` in
    backticks - which is a surface by definition. Such an FR needs a surface
    for the command (or a trace from the surface that already looks like it),
    or a deferral reason that says why the NAMED command needs none. Only
    FRs that are uncovered AND deferred are examined, so no new prose-only
    hit is recorded (the same defer() calls check_fr_coverage makes). Ledger
    IMP-076 (aicf LSN-056: FR-097 deferred as a 'global content rule' while
    its text named `aicf explain <term>`; nothing downstream ever built it).
    """
    roots = _root_commands(ux)
    if not roots:
        return []
    covered = _fr_covered_set(ux, surfaces)
    out: List[str] = []
    for fid, text in fr_texts.items():
        if fid.upper() in covered or not dfr.defer(fid):
            continue
        named: List[Tuple[str, str]] = []
        for root in roots:
            named.extend((root, cmd) for cmd in _commands_named_in(text, root))
        if not named:
            continue
        reason = dfr.declared.get(fid.upper()) or "by a ux_warnings note"
        shown = ", ".join(f"`{root} {cmd}`" for root, cmd in named)
        lookalike = next(
            (s for s in (_surface_lookalike(cmd, root, ux, surfaces) for root, cmd in named) if s),
            None,
        )
        if lookalike:
            remedy = (f"Add {fid} to the implements_requirements of surface "
                      f"'{lookalike}', whose invocation already looks like it")
        else:
            remedy = f"Add a cli_command surface that implements {fid}"
        out.append(
            f"{fid} is deferred ({reason[:90]!r}), but its text names a command: "
            f"{shown}. A deferral covers the whole requirement, so that command "
            f"is now specified nowhere and no task will build it. {remedy}, or "
            f"reword the deferral to say why {shown} needs no surface. "
            f"[FR names a command]"
        )
    return out


def _iter_inventory_items(ux: "UX"):
    for scope in _iter_ux_scopes(ux):
        for item in getattr(scope, "surface_inventory", None) or []:
            yield item


def _iter_ux_warnings(ux: "UX"):
    for scope in _iter_ux_scopes(ux):
        for w in getattr(scope, "ux_warnings", None) or []:
            yield warning_text(w)


def _iter_ux_scopes(ux: "UX"):
    yield ux
    for prod in (getattr(ux, "products", None) or {}).values():
        yield prod


# =============================================================================
# File loading / validation orchestration
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
    meta: UXMetadata, artifact_path: Path, no_prov_gate: bool
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
                "re-running /sdlc:ux records the snapshot"
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
                f"built against an older {f} - run /sdlc:ux to review the delta"
            )
    return warns


def check_downstream_claims(ux: UX, docs_dir: Path) -> List[str]:
    """Advisory (never blocks) — surface-status maturity vs downstream claims.

    When a sibling docs/ARCH.yaml claims a surface (some container's
    owns_ux_surfaces lists it), the architecture treats that surface as real:
    it gets components, edges, and eventually tests. An inventory entry still
    marked `proposed` (specced but deferred) — or never advanced past
    `defined`/`draft` — is then stale lifecycle metadata that misleads every
    downstream reader about what is actually being built. The skill's
    re-invocation flow reconciles these (SKILL.md Phase 2 → downstream-claim
    reconciliation); this warning is the standing detector.
    """
    warns: List[str] = []
    arch_path = docs_dir / "ARCH.yaml"
    if not arch_path.exists():
        return warns
    try:
        arch_raw = yaml.safe_load(arch_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return warns
    if not isinstance(arch_raw, dict):
        return warns
    claimed: Dict[str, str] = {}  # surface_id -> claiming container_id
    for c in arch_raw.get("containers") or []:
        if isinstance(c, dict):
            for sid in c.get("owns_ux_surfaces") or []:
                claimed.setdefault(str(sid), str(c.get("container_id")))
    if not claimed:
        return warns

    def _sweep(items: Optional[List[SurfaceInventoryItem]], scope: str) -> None:
        for item in items or []:
            sid = (item.surface_id or "").strip()
            status = item.status.value if item.status else None
            if sid in claimed and status != "confirmed":
                warns.append(
                    f"{scope}surface '{sid}' ({item.id}) has status "
                    f"'{status}' but ARCH container '{claimed[sid]}' claims it "
                    f"(owns_ux_surfaces) — reconcile the lifecycle: re-run "
                    f"/sdlc:ux to confirm the surface or correct the ARCH claim"
                )

    _sweep(ux.surface_inventory, "")
    for slug, product in (ux.products or {}).items():
        _sweep(product.surface_inventory, f"products.{slug}.")
    return warns


def _load_yaml(path: Path) -> tuple[Any, Optional[str]]:
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
    formatted: List[str] = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e.get("loc", ()))
        msg = e.get("msg", "invalid")
        formatted.append(f"{loc}: {msg}")
    return formatted


def discover_surface_files(ux_path: Path) -> List[Path]:
    """Return sorted list of docs/UX__*.yaml siblings of ux_path."""
    parent = ux_path.parent
    return sorted(parent.glob("UX__*.yaml"))


def validate_all(ux_path: Path) -> int:
    """Validate UX.yaml, all UX__*.yaml siblings, and run coverage check."""

    # 1) UX.yaml
    raw, err = _load_yaml(ux_path)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    try:
        ux = UX.model_validate(raw)
    except ValidationError as e:
        print(f"[FAIL] {ux_path} does not match the UX schema. No later skill can "
              f"read it until these fields are fixed:\n")
        print("Errors:")
        for line in _format_pydantic_errors(e):
            print(f"  - {line}")
        return 1

    # 2) Each UX__<surface>.yaml
    surface_files = discover_surface_files(ux_path)
    surfaces: Dict[str, UXSurface] = {}
    for sp in surface_files:
        s_raw, s_err = _load_yaml(sp)
        if s_err:
            print(f"ERROR: {s_err}", file=sys.stderr)
            return 2
        try:
            surface = UXSurface.model_validate(s_raw)
        except ValidationError as e:
            print(f"[FAIL] {sp.name} does not match the UX surface schema. No later "
                  f"skill can read it until these fields are fixed:\n")
            for line in _format_pydantic_errors(e):
                print(f"  - {line}")
            return 1
        surfaces[sp.name] = surface

    # 3) Required-field checks
    missing_ux = check_ux_required(ux)
    missing_surface: List[str] = []
    for name, surface in surfaces.items():
        missing_surface.extend(check_surface_required(surface, name))

    # 4) ID-prefix format checks
    id_errors = check_ux_id_prefixes(ux)
    for name, surface in surfaces.items():
        id_errors.extend(check_surface_id_prefixes(surface, name))

    # 5) Coverage check (WKF-NNN id-based)
    # PRD.yaml is a sibling of UX.yaml in the same docs/ directory; resolve it
    # relative to the artifact, not the CWD, so the validator works regardless
    # of where it is invoked from (fixtures, staged eval test-projects, etc.).
    prd_path = ux_path.parent / "PRD.yaml"
    prd_state = "ok"
    if not prd_path.exists():
        prd_state = "missing"
    else:
        try:
            yaml.safe_load(prd_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            prd_state = "unreadable"
    prd_ids = load_prd_core_workflow_ids(prd_path)
    traced_ids = collect_traced_workflow_ids(surfaces)
    uncovered = check_coverage(prd_ids, traced_ids) if prd_ids else []

    # 6) Downstream-claim maturity check (warning, never blocks)
    downstream_warnings = check_downstream_claims(ux, ux_path.parent)

    # 7) FR-coverage warning (never blocks): FRs with no surface
    # implements_requirements trace and no deferral (structured `deferrals`
    # first; ux_warnings prose mention as the deprecated fallback).
    dfr = DeferralIndex(ux)
    fr_texts = load_prd_fr_texts(prd_path)
    fr_gaps = check_fr_coverage(list(fr_texts), ux, surfaces, dfr)
    # A deferred FR whose text names `<root_command> <verb>` (IMP-076).
    cmd_warnings = check_deferred_fr_names_command(fr_texts, ux, surfaces, dfr)

    # 8) Provenance-staleness warning (never blocks, CLAUDE.md 7).
    prov_warnings = check_provenance(
        ux.metadata, ux_path,
        no_prov_gate=_version_tuple(ux.metadata.ux_version) >= (2, 0),
    )

    def _soft() -> List[str]:
        out: List[str] = []
        for w in downstream_warnings:
            out.append(w)
        if fr_gaps:
            ids = [str(f).split(":", 1)[0].strip() for f in fr_gaps]
            out.append(
                f"{len(fr_gaps)} requirement(s) from the PRD are served by no screen "
                f"or command here, and nothing says why: {join_ids(ids)}. Add a "
                f"surface that implements them, or defer each with a reason in the "
                f"top-level `deferrals` list."
            )
        out.extend(cmd_warnings)
        out.extend(prov_warnings)
        out.extend(dfr.shape_warnings)
        dep = dfr.deprecation_warning()
        if dep:
            out.append(dep)
        return out

    def _problems() -> List[str]:
        out: List[str] = []
        out += [f"a required UX.yaml field is empty: {m}" for m in missing_ux]
        out += [f"a required surface field is empty: {m}" for m in missing_surface]
        out += [f"wrong id format - {m}" for m in id_errors]
        if uncovered:
            ids = [str(u).split(":", 1)[0].strip() for u in uncovered]
            out.append(
                f"{len(uncovered)} user workflow(s) from the PRD have no screen or "
                f"command carrying them out: {join_ids(ids)}. Every workflow needs at "
                f"least one surface that traces it."
            )
        return out

    status = ux.metadata.status
    n_surfaces = len(surfaces)

    # ---- "this project has no UX" short-circuit ---------------------------
    # A not_applicable artifact is deliberately empty. Every required-field and
    # coverage check above would fire on it, and every one of them would be
    # wrong: there is no surface_family to name and no workflow to cover
    # because the user said there is no user-facing surface at all. The only
    # thing still required is the reason - a bare "not applicable" leaves the
    # next reader a fact they cannot judge.
    if ux.metadata.applicability == "not_applicable":
        na_problems: List[str] = []
        if not (ux.metadata.applicability_rationale or "").strip():
            na_problems.append(
                "metadata.applicability says this project has no UX but gives no "
                "reason - set metadata.applicability_rationale to one sentence "
                "saying why (e.g. 'headless ETL; no human-facing surface')."
            )
        n_listed = len(ux.surface_inventory or []) + sum(
            len(p.surface_inventory or []) for p in (ux.products or {}).values()
        )
        if n_surfaces or n_listed:
            na_problems.append(
                f"metadata.applicability says this project has no UX, but the file "
                f"still lists {max(n_surfaces, n_listed)} surface(s). Either drop "
                f"them or set applicability back to 'applicable'."
            )
        if status == "complete" and na_problems:
            print(f"[FAIL] {ux_path} says it is finished and not applicable, but "
                  f"{len(na_problems)} thing(s) are wrong.")
            print_findings(na_problems, [])
            print_next("fix the items above, then re-run this check.")
            return 1
        if status != "complete":
            print(f"[DRAFT] {ux_path} records that this project has no UX, but is "
                  f"still marked draft. Later skills will refuse it until it says "
                  f"'complete'.")
            print_findings(na_problems, [], blocking_header="TO FINISH IT")
            print_next("set metadata.status: complete.")
            return 0
        print(f"[OK] {ux_path} records that this project has no user-facing surface, "
              f"so there is nothing to specify: {ux.metadata.applicability_rationale} "
              f"/sdlc:design and everything after it will skip UX without asking.")
        print_findings([], [])
        print_next("/sdlc:design")
        return 0

    soft = _soft()

    if status == "complete":
        problems = _problems()
        if problems:
            print(f"[FAIL] {ux_path} says it is finished, but {len(problems)} thing(s) "
                  f"are wrong. /sdlc:design and everything after it will refuse it.")
            print_findings(problems, soft)
            print_next("fix the items above, then re-run this check.",
                       "Re-running /sdlc:ux walks you through them.")
            return 1
        if prd_state == "ok":
            print(f"[OK] {ux_path} is finished - {n_surfaces} screen/command file(s), "
                  f"all {len(prd_ids)} PRD workflow(s) covered. /sdlc:design can run it.")
        else:
            reason = "not found" if prd_state == "missing" else "unreadable"
            print(f"[OK] {ux_path} is finished - {n_surfaces} screen/command file(s). "
                  f"docs/PRD.yaml was {reason}, so PRD workflow coverage was NOT "
                  f"checked. /sdlc:design can run it.")
        print_findings([], soft)
        print_next("/sdlc:design", show_glossary=bool(soft))
        return 0

    # status == "draft"
    todo = _problems()
    if prd_state == "ok":
        print(f"[DRAFT] {ux_path} is saved but not finished - {n_surfaces} screen/command "
              f"file(s) so far, {len(prd_ids)} PRD workflow(s) found. Later skills will "
              f"refuse it until it says 'complete'.")
    else:
        reason = "not found" if prd_state == "missing" else "unreadable"
        print(f"[DRAFT] {ux_path} is saved but not finished - {n_surfaces} screen/command "
              f"file(s) so far. docs/PRD.yaml was {reason}, so PRD workflow coverage "
              f"was NOT checked. Later skills will refuse it until it says 'complete'.")
    print_findings(todo, soft, blocking_header="TO FINISH IT")
    print_next("re-run /sdlc:ux to continue, or set metadata.status: complete.",
               show_glossary=bool(todo or soft))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate UX.yaml + every UX__*.yaml against the sdlc-ux schema."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs", "UX.yaml"),
        help="Path to UX.yaml (default: ./docs/UX.yaml). Sibling UX__*.yaml "
        "files in the same directory are validated automatically.",
    )
    args = parser.parse_args(argv)
    return validate_all(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
