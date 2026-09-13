"""Validate API.yaml + every API__*.yaml against the canonical sdlc-api schema,
and run feature/surface coverage + DATA entity-link checks + ID-prefix format
checks.

Run from the project root:

    python sdlc/skills/api/validate_schema.py
    python sdlc/skills/api/validate_schema.py --path docs/API.yaml

Validates:
    1. docs/API.yaml (or --path) — global API contract.
    2. Every docs/API__*.yaml sibling — one per resource.
    3. ID-prefix format checks:
       - WRN-NNN on every api_warnings entry.
       - OPR-NNN on every endpoint's `id` field (when present).
       - FR-NNN on every traces_prd_features entry and every
         non_api_features entry.
       - SCR-NNN on every traces_ux_surfaces entry.
       - WKF-NNN on every traces_prd_workflows entry (when present).
       Hard error in status:complete.
    4. Coverage checks (all skipped when api_kind: none). Both gates are
       trace-OR-defer (CLAUDE.md §6): a top-level `deferrals: [{id, reason}]`
       list (alias `deferred_requirements`, also read under products.<slug>)
       is consulted FIRST; an entry without a reason defers nothing.
       - Feature coverage: every PRD FR-NNN (the flat `features` list, or the
         legacy must-have subset) appears in some resource's
         traces_prd_features, OR is deferred, OR (DEPRECATED, one more
         version — every id that falls through is reported) sits bare in
         API.yaml.non_api_features.
       - Surface coverage: every data-bearing UX surface (matched by the
         SCR-NNN id) appears in some resource's traces_ux_surfaces OR is
         deferred.
       - Entity-link: every resource's primary_entity (PascalCase entity
         name) exists in DATA-MODEL.yaml.entities.
       A resource file marked `internal: true` may keep empty trace lists at
       status complete (it serves no PRD feature / UX screen by design); each
       such waiver is reported as a warning.
       When an upstream input (PRD.yaml, UX__*.yaml shards, DATA-MODEL.yaml)
       is ABSENT, the corresponding check does not run and the summary says
       so — it never reports zeros as a pass.
    5. Provenance freshness (warn-level, never blocks): when
       metadata.upstream_provenance is present, each recorded sha256 is
       compared to the upstream's current hash (docs/INDEX.yaml
       generated_from[<file>].sha256 when present, else
       sha256(read_text(utf-8))[:16], identical to docs_index.py --hash).
       A mismatch warns that the contract was built against an older
       upstream. status: complete with NO provenance at all warns from
       api_version >= 2.0 (CLAUDE.md §10).

OpenAPI 3.1 deep-validation of embedded operations is OUT of scope for v1
(see references/openapi-embedding.md). The Pydantic models here enforce the
shape (required keys: method, path, responses) but do not call out to an
OpenAPI validator. Downstream codegen agents may re-validate.

Exit codes:
    0 — schema valid; either status='complete' (with all required fields
        filled AND all enabled checks passing) or status='draft'.
    1 — schema invalid (pydantic error), OR status='complete' but required
        fields are missing, OR status='complete' but any coverage check
        failed.
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
from typing import Any, Dict, List, Literal, Optional


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
# Enums — kept in lockstep with API.schema.yaml and API__RESOURCE.schema.yaml
# =============================================================================


class Confidence(str, Enum):
    confirmed = "confirmed"
    inferred = "inferred"
    assumption = "assumption"


class ApiKind(str, Enum):
    rest = "rest"
    graphql = "graphql"
    grpc = "grpc"
    mixed = "mixed"
    none = "none"


class TransportStyle(str, Enum):
    rest = "rest"
    graphql = "graphql"
    grpc = "grpc"
    websocket = "websocket"
    server_sent_events = "server_sent_events"
    webhooks_out = "webhooks_out"


class VersioningStrategy(str, Enum):
    path = "path"
    header = "header"
    content_type = "content_type"
    none = "none"


class AuthScheme(str, Enum):
    api_key = "api_key"
    bearer_jwt = "bearer_jwt"
    oauth2 = "oauth2"
    session_cookie = "session_cookie"
    mtls = "mtls"
    none = "none"


class DefaultVisibility(str, Enum):
    public = "public"
    authenticated = "authenticated"
    mixed = "mixed"


class ErrorEnvelope(str, Enum):
    rfc7807 = "rfc7807"
    custom = "custom"


class PaginationStrategy(str, Enum):
    offset = "offset"
    cursor = "cursor"
    none = "none"


class RateLimitScope(str, Enum):
    per_ip = "per_ip"
    per_user = "per_user"
    per_key = "per_key"
    glob = "global"  # python keyword clash; serialized value is "global"

    @classmethod
    def _missing_(cls, value: object):
        if value == "global":
            return cls.glob
        return None


class DeliveryGuarantee(str, Enum):
    at_most_once = "at_most_once"
    at_least_once = "at_least_once"
    exactly_once = "exactly_once"


class ResourceStatus(str, Enum):
    defined = "defined"
    draft = "draft"
    confirmed = "confirmed"


# Surface types treated as "data-bearing" for surface-coverage purposes.
# Mirrors the SurfaceType enum in sdlc-ux but excludes purely-visual states.
DATA_BEARING_SURFACE_TYPES = {
    "screen",
    "page",
    "tab",
    "modal",
    "dialog",
    "drawer",
    "panel",
    "cli_command",
    "flow_step",
    "other",
}


# =============================================================================
# API.yaml — top-level theme models
# =============================================================================

_BASE_CONFIG = ConfigDict(extra="allow", str_strip_whitespace=True)


class _ThemeBase(BaseModel):
    model_config = _BASE_CONFIG


class Versioning(_ThemeBase):
    strategy: Optional[VersioningStrategy] = None
    strategy_confidence: Optional[Confidence] = None
    current_version: Optional[str] = None
    deprecation_policy: Optional[str] = None


class Auth(_ThemeBase):
    schemes: Optional[List[AuthScheme]] = None
    schemes_confidence: Optional[Confidence] = None
    roles: Optional[List[str]] = None
    scopes: Optional[List[str]] = None
    default_visibility: Optional[DefaultVisibility] = None
    default_visibility_confidence: Optional[Confidence] = None


class ErrorCode(_ThemeBase):
    code: Optional[str] = None
    http_status: Optional[int] = None
    description: Optional[str] = None


class Errors(_ThemeBase):
    envelope: Optional[ErrorEnvelope] = None
    envelope_confidence: Optional[Confidence] = None
    localisation: Optional[bool] = None
    retry_semantics: Optional[str] = None
    error_codes: Optional[List[ErrorCode]] = None


class Pagination(_ThemeBase):
    strategy: Optional[PaginationStrategy] = None
    strategy_confidence: Optional[Confidence] = None
    default_page_size: Optional[int] = None
    max_page_size: Optional[int] = None
    stable_sort_field: Optional[str] = None


class Idempotency(_ThemeBase):
    idempotent_methods: Optional[List[str]] = None
    header: Optional[str] = None
    cache_window: Optional[str] = None


class RateLimiting(_ThemeBase):
    scopes: Optional[List[RateLimitScope]] = None
    burst: Optional[str] = None
    sustained: Optional[str] = None
    response: Optional[str] = None


class EventChannel(_ThemeBase):
    channel_id: Optional[str] = None
    transport: Optional[str] = None
    direction: Optional[str] = None
    payload_schema_ref: Optional[str] = None
    auth_ref: Optional[str] = None


class Events(_ThemeBase):
    channels: Optional[List[EventChannel]] = None
    payload_conventions: Optional[str] = None
    delivery_guarantees: Optional[DeliveryGuarantee] = None
    consumer_auth: Optional[str] = None


class ExternalDependency(_ThemeBase):
    name: Optional[str] = None
    auth: Optional[str] = None
    rate_limit: Optional[str] = None
    retry_policy: Optional[str] = None
    docs_url: Optional[str] = None


class SdkAndClients(_ThemeBase):
    generated_sdks: Optional[str] = None
    client_languages: Optional[List[str]] = None
    distribution: Optional[str] = None


class ResourceInventoryItem(_ThemeBase):
    resource_id: Optional[str] = None
    base_path: Optional[str] = None
    status: Optional[ResourceStatus] = None
    file_path: Optional[str] = None
    primary_entity: Optional[str] = None
    traces_prd_features: Optional[List[str]] = None
    traces_ux_surfaces: Optional[List[str]] = None
    traces_prd_workflows: Optional[List[str]] = None
    # True = internal-only resource that serves no PRD feature / UX screen by
    # design (health, metrics, ops). Mirrors the per-resource file's flag.
    internal: Optional[bool] = None


# -----------------------------------------------------------------------------
# Top-level API models
# -----------------------------------------------------------------------------


class APIMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_version: str
    last_updated: str
    generated_by: str = "sdlc-api"
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


class APIProduct(_ThemeBase):
    """One product's API contract in monorepo mode."""

    api_kind: Optional[ApiKind] = None
    api_kind_confidence: Optional[Confidence] = None
    rationale: Optional[str] = None

    transport_styles: Optional[List[TransportStyle]] = None
    transport_styles_confidence: Optional[Confidence] = None

    versioning: Optional[Versioning] = None
    auth: Optional[Auth] = None
    errors: Optional[Errors] = None
    pagination: Optional[Pagination] = None
    idempotency: Optional[Idempotency] = None
    rate_limiting: Optional[RateLimiting] = None
    events: Optional[Events] = None
    external_dependencies: Optional[List[ExternalDependency]] = None
    sdk_and_clients: Optional[SdkAndClients] = None
    shared_schemas: Optional[Dict[str, Any]] = None
    resource_inventory: Optional[List[ResourceInventoryItem]] = None
    non_api_features: Optional[List[str]] = None
    # Structural deferrals (CLAUDE.md §6): [{id, reason}] per product.
    deferrals: Optional[List[Any]] = None
    deferred_requirements: Optional[List[Any]] = None  # accepted alias


class API(BaseModel):
    """Top-level API.yaml document."""

    model_config = ConfigDict(extra="allow")

    metadata: APIMetadata
    api_warnings: List[Any] = Field(default_factory=list)  # str | typed WarningItem mapping

    # Single-product mode — all theme blocks live at top level
    api_kind: Optional[ApiKind] = None
    api_kind_confidence: Optional[Confidence] = None
    rationale: Optional[str] = None

    transport_styles: Optional[List[TransportStyle]] = None
    transport_styles_confidence: Optional[Confidence] = None

    versioning: Optional[Versioning] = None
    auth: Optional[Auth] = None
    errors: Optional[Errors] = None
    pagination: Optional[Pagination] = None
    idempotency: Optional[Idempotency] = None
    rate_limiting: Optional[RateLimiting] = None
    events: Optional[Events] = None
    external_dependencies: Optional[List[ExternalDependency]] = None
    sdk_and_clients: Optional[SdkAndClients] = None
    shared_schemas: Optional[Dict[str, Any]] = None
    resource_inventory: Optional[List[ResourceInventoryItem]] = None
    non_api_features: Optional[List[str]] = None

    # Structural deferrals (CLAUDE.md §6): top-level [{id, reason}] read FIRST
    # by the feature and surface coverage gates. An entry with no reason
    # defers nothing.
    deferrals: Optional[List[Any]] = None
    deferred_requirements: Optional[List[Any]] = None  # accepted alias

    # Multi-product mode
    products: Optional[Dict[str, APIProduct]] = None

    @model_validator(mode="after")
    def _check_mode(self) -> "API":
        single_themes = [
            self.api_kind,
            self.transport_styles,
            self.versioning,
            self.auth,
            self.errors,
            self.pagination,
            self.idempotency,
            self.rate_limiting,
            self.events,
            self.external_dependencies,
            self.sdk_and_clients,
            self.shared_schemas,
            self.resource_inventory,
        ]
        any_single = any(t is not None for t in single_themes)

        if self.metadata.monorepo:
            if not self.products:
                raise ValueError("metadata.monorepo is true but `products` is missing or empty")
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
# API__<resource>.yaml — per-resource model
# =============================================================================


class ResourceMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    api_resource_version: str
    last_updated: str
    generated_by: str = "sdlc-api"
    session_id: str
    status: Literal["draft", "complete"] = "draft"
    changelog: Optional[List[str]] = None


class Endpoint(_ThemeBase):
    """One API endpoint = one (method, path) operation.

    The model is intentionally permissive on OpenAPI sub-shape. Deep OpenAPI
    3.1 conformance is out of scope for v1 — see references/openapi-embedding.md.
    """

    id: Optional[str] = None  # OPR-NNN stable id (SDLC sibling; stripped before OpenAPI round-trip)
    operation_id: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    parameters: Optional[List[Any]] = None
    requestBody: Optional[Any] = None
    responses: Optional[Dict[str, Any]] = None
    security: Optional[List[Any]] = None
    # SDLC siblings:
    idempotent: Optional[bool] = None
    rate_limit_override: Optional[str] = None
    auth_override: Optional[str] = None


class APIResource(BaseModel):
    """Top-level per-resource document."""

    model_config = ConfigDict(extra="allow")

    metadata: ResourceMetadata

    resource_id: Optional[str] = None
    base_path: Optional[str] = None
    primary_entity: Optional[str] = None
    traces_prd_features: Optional[List[str]] = None
    traces_ux_surfaces: Optional[List[str]] = None
    traces_prd_workflows: Optional[List[str]] = None
    endpoints: Optional[List[Endpoint]] = None
    schemas: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    # True = internal-only resource (health, metrics, ops). Empty
    # traces_prd_features / traces_ux_surfaces are then accepted at
    # status complete; the validator reports the waiver as a warning.
    internal: Optional[bool] = None


# =============================================================================
# Required-field checks
# =============================================================================

# Required when api_kind != none. (For api_kind == none, only api_kind and
# rationale are required.)
API_REQUIRED_PATHS: List[str] = [
    "api_kind",
    "transport_styles",
    "versioning.strategy",
    "versioning.current_version",
    "auth.schemes",
    "auth.default_visibility",
    "errors.envelope",
    "pagination.strategy",
    "idempotency.idempotent_methods",
    "rate_limiting.scopes",
    "resource_inventory",
]

# Always required:
API_REQUIRED_PATHS_ALWAYS: List[str] = ["api_kind"]

# Conditionally required (api_kind == none): rationale
API_NONE_REQUIRED_PATHS: List[str] = ["api_kind", "rationale"]

# Per-resource required fields:
RESOURCE_REQUIRED_PATHS: List[str] = [
    "resource_id",
    "base_path",
    "traces_prd_features",
    "traces_ux_surfaces",
    "endpoints",
]

# Per-endpoint required keys for status=complete:
ENDPOINT_REQUIRED_KEYS: List[str] = ["id", "operation_id", "method", "path", "summary", "responses"]


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


def check_api_required(api: API) -> List[str]:
    """Return list of missing required API.yaml field paths.

    Behaviour depends on api_kind:
      - api_kind == none: only api_kind + rationale required.
      - api_kind != none: full API_REQUIRED_PATHS list required.
    """
    missing: List[str] = []

    def _check(scope_label: str, root: object) -> None:
        kind = getattr(root, "api_kind", None)
        if kind == ApiKind.none:
            for path in API_NONE_REQUIRED_PATHS:
                if _is_empty(_get_dotted(root, path)):
                    missing.append(f"{scope_label}{path}")
            return
        for path in API_REQUIRED_PATHS:
            if _is_empty(_get_dotted(root, path)):
                missing.append(f"{scope_label}{path}")

    if api.metadata.monorepo and api.products:
        for slug, product in api.products.items():
            _check(f"products.{slug}.", product)
    else:
        _check("", api)
    return missing


def check_resource_required(resource: APIResource, file_label: str) -> List[str]:
    """Return list of missing required fields for one resource yaml.

    Also walks endpoints[] and flags any endpoint missing the canonical
    OpenAPI keys (operation_id, method, path, summary, responses).

    A resource marked `internal: true` (health, metrics, ops) serves no PRD
    feature / UX screen by design: its `traces_prd_features` and
    `traces_ux_surfaces` may stay empty. The caller reports each waiver as a
    warning so it is a visible choice, never a silent gap.
    """
    missing: List[str] = []
    waived = ("traces_prd_features", "traces_ux_surfaces") if resource.internal else ()
    for path in RESOURCE_REQUIRED_PATHS:
        if path in waived:
            continue
        if _is_empty(_get_dotted(resource, path)):
            missing.append(f"{file_label}: {path}")

    if resource.endpoints:
        for i, ep in enumerate(resource.endpoints):
            for key in ENDPOINT_REQUIRED_KEYS:
                if _is_empty(getattr(ep, key, None)):
                    missing.append(f"{file_label}: endpoints[{i}].{key}")
    return missing


# =============================================================================
# Coverage checks
# =============================================================================


_FEATURE_ID_RE = re.compile(r"^FR-\d+", re.IGNORECASE)
_WRN_RE = re.compile(r"^WRN-\d{3,}:\s+.+")
_FR_PREFIX_RE = re.compile(r"^FR-\d{3,}$", re.IGNORECASE)
_SCR_PREFIX_RE = re.compile(r"^SCR-\d{3,}$", re.IGNORECASE)
_WKF_PREFIX_RE = re.compile(r"^WKF-\d{3,}$", re.IGNORECASE)
_OPR_PREFIX_RE = re.compile(r"^OPR-\d{3,}$", re.IGNORECASE)


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




def _check_id_prefix(values: object, regex: "re.Pattern[str]", path_label: str) -> List[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        return [f"{path_label}: expected a list, got {type(values).__name__}"]
    errs: List[str] = []
    for i, v in enumerate(values):
        if not isinstance(v, str) or not regex.match(v.strip()):
            errs.append(f"{path_label}[{i}]: '{v}' does not match expected ID format")
    return errs


def check_api_id_formats(api: API) -> List[str]:
    """Enforce <PREFIX>-NNN format on every trace list + non_api_features."""
    errs: List[str] = []

    def _check_root(scope: str, root: object) -> None:
        non_api = getattr(root, "non_api_features", None)
        errs.extend(_check_id_prefix(non_api, _FR_PREFIX_RE,
                                     f"{scope}non_api_features (expected FR-NNN)"))
        inv = getattr(root, "resource_inventory", None) or []
        for i, item in enumerate(inv):
            errs.extend(_check_id_prefix(
                getattr(item, "traces_prd_features", None), _FR_PREFIX_RE,
                f"{scope}resource_inventory[{i}].traces_prd_features (expected FR-NNN)"))
            errs.extend(_check_id_prefix(
                getattr(item, "traces_ux_surfaces", None), _SCR_PREFIX_RE,
                f"{scope}resource_inventory[{i}].traces_ux_surfaces (expected SCR-NNN)"))
            errs.extend(_check_id_prefix(
                getattr(item, "traces_prd_workflows", None), _WKF_PREFIX_RE,
                f"{scope}resource_inventory[{i}].traces_prd_workflows (expected WKF-NNN)"))

    if api.metadata.monorepo and api.products:
        for slug, product in api.products.items():
            _check_root(f"products.{slug}.", product)
    else:
        _check_root("", api)
    return errs


def check_resource_id_formats(resource: APIResource, label: str) -> List[str]:
    """Enforce ID prefix format on per-resource yaml lists and endpoint ids."""
    errs: List[str] = []
    errs.extend(_check_id_prefix(
        resource.traces_prd_features, _FR_PREFIX_RE,
        f"{label}: traces_prd_features (expected FR-NNN)"))
    errs.extend(_check_id_prefix(
        resource.traces_ux_surfaces, _SCR_PREFIX_RE,
        f"{label}: traces_ux_surfaces (expected SCR-NNN)"))
    errs.extend(_check_id_prefix(
        resource.traces_prd_workflows, _WKF_PREFIX_RE,
        f"{label}: traces_prd_workflows (expected WKF-NNN)"))
    # OPR ids on endpoints. `id` may be unset on draft endpoints; only check
    # values that are present.
    for i, ep in enumerate(resource.endpoints or []):
        ep_id = getattr(ep, "id", None)
        if ep_id is None:
            continue
        if not isinstance(ep_id, str) or not _OPR_PREFIX_RE.match(ep_id.strip()):
            errs.append(
                f"{label}: endpoints[{i}].id: '{ep_id}' must match OPR-NNN format"
            )
    return errs


def load_prd_features(prd_path: Path) -> List[str]:
    """Return the gating FR-NNN strings from PRD.functional_requirements.

    D2 gating subset (FR_GATE, CLAUDE.md §10): the flat `features` list when
    present, else the legacy `must_have_features` ONLY — a legacy PRD's
    nice_to_have backlog stays outside the coverage check, preserving pre-D2
    behavior. Each entry typically starts with "FR-NNN: <description>"; we
    extract just the FR-NNN prefix.
    """
    if not prd_path.exists():
        return []
    try:
        raw = yaml.safe_load(prd_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    if not isinstance(raw, dict):
        return []

    features: List[str] = []
    metadata = raw.get("metadata") or {}
    monorepo = bool(metadata.get("monorepo"))

    def _pull(node: dict) -> None:
        fr = node.get("functional_requirements") or {}
        if not isinstance(fr, dict):
            return
        feats = fr.get("features")
        if not feats:  # legacy: must_have only (nice_to_have stays ungated)
            feats = fr.get("must_have_features") or []
        if isinstance(feats, list):
            for item in feats:
                s = str(item).strip()
                m = _FEATURE_ID_RE.match(s)
                if m:
                    features.append(m.group(0).upper())

    if monorepo:
        products = raw.get("products") or {}
        if isinstance(products, dict):
            for prod in products.values():
                if isinstance(prod, dict):
                    _pull(prod)
    else:
        _pull(raw)
    return features


def load_ux_data_bearing_surfaces(docs_dir: Path) -> List[str]:
    """Return list of UX surface SCR-NNN ids whose surface_type is data-bearing.

    Reads every docs/UX__*.yaml file. Returns each surface's stable `id`
    field (SCR-NNN). Surfaces without a recognized type are treated as
    data-bearing (conservative — better a false positive in coverage than
    a silent miss).

    For backward compatibility, falls back to the per-surface
    `surface_id` slug ONLY when the file pre-dates the SCR-NNN convention
    (i.e. `id` is missing). When that fallback fires, the agent should
    propose migrating the surface file.
    """
    surfaces: List[str] = []
    for path in sorted(docs_dir.glob("UX__*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if not isinstance(raw, dict):
            continue
        # Prefer the SCR-NNN stable id; fall back to surface_id slug.
        scr_id = raw.get("id")
        slug = raw.get("surface_id")
        stype = raw.get("surface_type")
        chosen = scr_id if isinstance(scr_id, str) and scr_id.strip() else slug
        if not chosen:
            continue
        if stype is None or stype in DATA_BEARING_SURFACE_TYPES:
            surfaces.append(str(chosen))
    return surfaces


def load_data_model_entities(data_path: Path) -> Optional[List[str]]:
    """Return list of DATA-MODEL entity names, or None if the file is absent.

    The canonical shape (produced by sdlc-data) is a dict keyed by
    PascalCase entity name:

      entities:
        User: { ... }
        Order: { ... }

    A list-of-`{name: ...}` shape is also accepted for resilience against
    older or hand-written fixtures, but the dict shape is the source of
    truth.
    """
    if not data_path.exists():
        return None
    try:
        raw = yaml.safe_load(data_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    if not isinstance(raw, dict):
        return None

    entities = raw.get("entities")
    if isinstance(entities, dict):
        return [str(k) for k in entities.keys()]
    if isinstance(entities, list):
        names: List[str] = []
        for item in entities:
            if isinstance(item, dict) and "name" in item:
                names.append(str(item["name"]))
            elif isinstance(item, str):
                names.append(item)
        return names
    return []


def collect_resource_traces(
    api: API, resources: Dict[str, APIResource]
) -> tuple[List[str], List[str], List[Optional[str]]]:
    """Walk both the inventory and the per-resource files; aggregate traces.

    Returns (all_feature_traces, all_surface_traces, all_primary_entities).
    """
    feats: List[str] = []
    surfs: List[str] = []
    ents: List[Optional[str]] = []

    inventory: List[ResourceInventoryItem] = []
    if api.metadata.monorepo and api.products:
        for prod in api.products.values():
            inventory.extend(prod.resource_inventory or [])
    else:
        inventory.extend(api.resource_inventory or [])

    for item in inventory:
        if item.traces_prd_features:
            feats.extend(item.traces_prd_features)
        if item.traces_ux_surfaces:
            surfs.extend(item.traces_ux_surfaces)
        if item.primary_entity:
            ents.append(item.primary_entity)

    for res in resources.values():
        if res.traces_prd_features:
            feats.extend(res.traces_prd_features)
        if res.traces_ux_surfaces:
            surfs.extend(res.traces_ux_surfaces)
        if res.primary_entity:
            ents.append(res.primary_entity)

    return feats, surfs, ents


class ApiDeferralIndex:
    """The DEFER half of trace-or-defer (CLAUDE.md §6) for the API artifact.

    Canonical channel: the top-level `deferrals` list of {id, reason}
    (alias: `deferred_requirements`), also read under every
    `products.<slug>` in monorepo mode. Explicit, auditable, and impossible
    to trigger by accident. Feature deferrals name FR-NNN ids; surface
    deferrals name SCR-NNN ids.

    DEPRECATED channel (feature gate only): a bare FR-NNN in
    `non_api_features`. It carries no reason, so nobody can audit WHY the
    requirement needs no endpoint. Still honoured for one more version (no
    artifact flips red on upgrade); every id that falls through to it is
    collected here and reported once by `fallback_warning()`.

    Malformed structured entries never defer anything: an entry without an
    id, or with an id but no reason, is reported and the gate stays armed.
    A deferral you cannot audit is not a deferral.
    """

    def __init__(self, api: "API") -> None:
        self.declared: Dict[str, str] = {}
        self.shape_warnings: List[str] = []
        self.fallback_ids: set = set()

        roots: List[object] = [api]
        if api.products:
            roots.extend(api.products.values())
        for root in roots:
            field = "deferrals"
            raw = getattr(root, "deferrals", None)
            if raw is None:
                raw = getattr(root, "deferred_requirements", None)
                field = "deferred_requirements"
            for i, entry in enumerate(raw or []):
                where = f"{field}[{i}]"
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
        for _w in ([w for r in roots for w in (getattr(r, "api_warnings", None) or [])] or []):
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

    def is_deferred(self, id_str: str) -> bool:
        return str(id_str).strip().upper() in self.declared

    def note_fallback(self, id_str: str) -> None:
        self.fallback_ids.add(str(id_str).strip().upper())

    def fallback_warning(self) -> Optional[str]:
        if not self.fallback_ids:
            return None
        ids = sorted(self.fallback_ids)
        return (
            f"{len(ids)} requirement(s) pass the feature gate only because "
            f"they sit bare in `non_api_features`, which records no reason: "
            f"{join_ids(ids)}. Move each into the top-level `deferrals` list "
            f"as {{id, reason}} so the waiver is auditable. A bare "
            f"non_api_features entry still works for one more version. "
            f"[deferral hygiene]"
        )


def check_feature_coverage(
    prd_features: List[str],
    traced_features: List[str],
    non_api_features: Optional[List[str]],
    deferral: Optional[ApiDeferralIndex] = None,
) -> List[str]:
    """Return list of FR-NNN IDs that are neither traced, deferred, nor
    opted out. Structured deferrals are consulted BEFORE the deprecated
    `non_api_features` fallback; ids that only the fallback saves are
    recorded on the deferral index for the one-per-run hygiene warning."""
    traced_norm = {
        _FEATURE_ID_RE.match(str(f).strip()).group(0).upper()
        for f in traced_features
        if _FEATURE_ID_RE.match(str(f).strip())
    }
    opt_out: set = set()
    if non_api_features:
        for f in non_api_features:
            m = _FEATURE_ID_RE.match(str(f).strip())
            if m:
                opt_out.add(m.group(0).upper())
    uncovered: List[str] = []
    for f in prd_features:
        up = f.upper()
        if up in traced_norm:
            continue
        if deferral is not None and deferral.is_deferred(up):
            continue
        if up in opt_out:
            if deferral is not None:
                deferral.note_fallback(up)
            continue
        uncovered.append(f)
    return uncovered


def check_surface_coverage(
    ux_surfaces: List[str],
    traced_surfaces: List[str],
    deferral: Optional[ApiDeferralIndex] = None,
) -> List[str]:
    """Return list of SCR ids that are neither traced nor deferred."""
    traced_set = {s.strip() for s in traced_surfaces}
    uncovered: List[str] = []
    for s in ux_surfaces:
        if s.strip() in traced_set:
            continue
        if deferral is not None and deferral.is_deferred(s):
            continue
        uncovered.append(s)
    return uncovered


def check_entity_links(
    primary_entities: List[Optional[str]], data_entities: Optional[List[str]]
) -> List[str]:
    """Return list of primary_entity names that don't exist in DATA-MODEL.

    If data_entities is None (DATA-MODEL.yaml missing), this check is
    skipped — return [].
    """
    if data_entities is None:
        return []
    data_set = set(data_entities)
    missing: List[str] = []
    for ent in primary_entities:
        if ent and ent not in data_set:
            missing.append(ent)
    return missing


# =============================================================================
# Provenance freshness (warn-level, CLAUDE.md §7 / B5)
# =============================================================================


def _version_at_least(version: object, floor_major: int) -> bool:
    """True when the artifact's declared version has major >= floor_major.
    Unparseable versions count as below the floor (CLAUDE.md §10)."""
    m = re.match(r"^\s*(\d+)", str(version or ""))
    return bool(m) and int(m.group(1)) >= floor_major


def _artifact_hash(path: Path) -> Optional[str]:
    """The canonical 16-hex provenance hash — identical to
    `docs_index.py --hash`: sha256 over the utf-8 TEXT of the file."""
    try:
        return hashlib.sha256(
            path.read_text(encoding="utf-8").encode("utf-8")
        ).hexdigest()[:16]
    except (OSError, UnicodeDecodeError):
        return None


def _load_index_hashes(docs_dir: Path) -> Dict[str, str]:
    """Read docs/INDEX.yaml generated_from[<file>].sha256 into a lookup keyed
    by both the recorded path and its basename. Empty when INDEX is absent."""
    index_path = docs_dir / "INDEX.yaml"
    if not index_path.exists():
        return {}
    try:
        raw = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    out: Dict[str, str] = {}
    gf = (raw or {}).get("generated_from") if isinstance(raw, dict) else None
    if isinstance(gf, dict):
        for fname, meta in gf.items():
            if isinstance(meta, dict) and meta.get("sha256"):
                out[str(fname)] = str(meta["sha256"])
                out[Path(str(fname)).name] = str(meta["sha256"])
    return out


def check_provenance_freshness(api: "API", docs_dir: Path) -> List[str]:
    """Warn-level only — never blocks. Compares each recorded
    metadata.upstream_provenance sha256 to the upstream's current hash.
    An upstream file that no longer exists is skipped here (its absence is
    already reported by the coverage summary)."""
    warns: List[str] = []
    prov = api.metadata.upstream_provenance
    if not prov:
        if api.metadata.status == "complete" and _version_at_least(
            api.metadata.api_version, 2
        ):
            warns.append(
                "metadata.status is 'complete' but metadata.upstream_provenance "
                "is empty - nothing records which PRD/UX/DATA-MODEL this "
                "contract was built against, so a later upstream edit cannot "
                "be detected. Re-running /sdlc:api records it."
            )
        return warns
    index_hashes = _load_index_hashes(docs_dir)
    for entry in prov:
        if not isinstance(entry, dict):
            continue
        fname = str(entry.get("file") or "").strip()
        recorded = str(entry.get("sha256") or "").strip()
        if not fname or not recorded:
            continue
        current = index_hashes.get(fname) or index_hashes.get(Path(fname).name)
        if current is None:
            for cand in (Path(fname), docs_dir / Path(fname).name):
                if cand.exists():
                    current = _artifact_hash(cand)
                    break
        if current is None:
            continue
        if current != recorded:
            warns.append(
                f"built against an older {fname} - run /sdlc:api to review "
                f"the delta"
            )
    return warns


# =============================================================================
# File loading / validation orchestration
# =============================================================================


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


def discover_resource_files(api_path: Path) -> List[Path]:
    """Return sorted list of docs/API__*.yaml siblings of api_path."""
    parent = api_path.parent
    return sorted(parent.glob("API__*.yaml"))


def validate_all(api_path: Path) -> int:
    """Validate API.yaml, all API__*.yaml siblings, and run coverage checks."""

    # 1) API.yaml
    raw, err = _load_yaml(api_path)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    try:
        api = API.model_validate(raw)
    except ValidationError as e:
        print(f"[FAIL] {api_path} does not match the schema. No later "
              f"skill can read it until these fields are fixed:\n")
        print("Errors:")
        for line in _format_pydantic_errors(e):
            print(f"  - {line}")
        return 1

    # 2) Each API__<resource>.yaml
    resource_files = discover_resource_files(api_path)
    resources: Dict[str, APIResource] = {}
    for rp in resource_files:
        r_raw, r_err = _load_yaml(rp)
        if r_err:
            print(f"ERROR: {r_err}", file=sys.stderr)
            return 2
        try:
            resource = APIResource.model_validate(r_raw)
        except ValidationError as e:
            print(f"[FAIL] {rp.name} does not match the schema. No later "
              f"skill can read it until these fields are fixed:\n")
            for line in _format_pydantic_errors(e):
                print(f"  - {line}")
            return 1
        resources[rp.name] = resource

    # 3) Required-field checks
    missing_api = check_api_required(api)
    missing_resource: List[str] = []
    for name, resource in resources.items():
        missing_resource.extend(check_resource_required(resource, name))

    # 3b) ID-prefix format checks (WRN on warnings, FR/SCR/WKF on traces, OPR on endpoint ids)
    warning_id_errs = check_warning_ids(api.api_warnings or [], "api_warnings")
    id_format_errs = check_api_id_formats(api)
    for name, resource in resources.items():
        id_format_errs.extend(check_resource_id_formats(resource, name))

    # 4) Coverage + entity-link checks — skipped when api_kind: none
    docs_dir = api_path.parent
    prd_path = docs_dir / "PRD.yaml"
    data_path = docs_dir / "DATA-MODEL.yaml"
    prd_present = prd_path.exists()
    ux_present = any(docs_dir.glob("UX__*.yaml"))

    is_none_kind = api.api_kind == ApiKind.none or (
        api.metadata.monorepo
        and api.products
        and all((p.api_kind == ApiKind.none) for p in api.products.values())
    )

    deferral = ApiDeferralIndex(api)

    if is_none_kind:
        prd_features: List[str] = []
        ux_surfaces: List[str] = []
        data_entities: Optional[List[str]] = []
        uncovered_features: List[str] = []
        uncovered_surfaces: List[str] = []
        bad_entities: List[str] = []
    else:
        prd_features = load_prd_features(prd_path)
        ux_surfaces = load_ux_data_bearing_surfaces(docs_dir)
        data_entities = load_data_model_entities(data_path)

        traced_feats, traced_surfs, primary_ents = collect_resource_traces(api, resources)
        non_api = api.non_api_features
        if api.metadata.monorepo and api.products:
            non_api = []
            for prod in api.products.values():
                if prod.non_api_features:
                    non_api.extend(prod.non_api_features)
        uncovered_features = check_feature_coverage(
            prd_features, traced_feats, non_api, deferral)
        uncovered_surfaces = check_surface_coverage(
            ux_surfaces, traced_surfs, deferral)
        bad_entities = check_entity_links(primary_ents, data_entities)

    status = api.metadata.status
    n_resources = len(resources)

    # ---- api_kind:none and metadata.applicability must agree ---------------
    # `api_kind: none` is this artifact's own way of saying "no API here" and
    # predates the uniform marker; `metadata.applicability` is what every
    # consumer reads across artifacts. Keeping them in sync is what lets arch
    # skip the API without an `ls` and without asking. A legacy none-kind file
    # has no applicability field at all, so that direction only warns
    # (CLAUDE.md section 10); the contradiction direction is an error, because
    # anyone who wrote the new field wrote it deliberately.
    applicability = api.metadata.applicability
    applicability_errs: List[str] = []
    applicability_warns: List[str] = []
    if applicability == "not_applicable":
        if not (api.metadata.applicability_rationale or "").strip():
            applicability_errs.append(
                "metadata.applicability says this project has no API but gives no "
                "reason - set metadata.applicability_rationale to one sentence "
                "saying why (e.g. 'local CLI tool; no network surface')."
            )
        if not is_none_kind:
            applicability_errs.append(
                "metadata.applicability says this project has no API, but api_kind "
                "is not 'none'. Set api_kind: none, or set applicability back to "
                "'applicable' - arch and task read these two and cannot act on a "
                "contradiction."
            )
    elif is_none_kind:
        applicability_warns.append(
            "api_kind is 'none' but metadata.applicability still says 'applicable', "
            "so later skills fall back to guessing from whether docs/API.yaml "
            "exists - and this file does exist. Set metadata.applicability: "
            "not_applicable (with a rationale) so arch skips the API without asking."
        )

    # 4b) Warnings — none of these block (CLAUDE.md 14).
    warnings_found: List[Any] = []
    warnings_found.extend(applicability_warns)
    warnings_found.extend(deferral.shape_warnings)
    fb = deferral.fallback_warning()
    if fb:
        warnings_found.append(fb)
    internal_waived = [
        name for name, res in resources.items()
        if res.internal and (
            not res.traces_prd_features or not res.traces_ux_surfaces)
    ]
    if internal_waived:
        warnings_found.append((
            f"{len(internal_waived)} resource(s) are marked internal: true, so "
            f"their empty PRD/UX trace lists were accepted. Confirm each is "
            f"genuinely internal-only; otherwise add traces_prd_features / "
            f"traces_ux_surfaces:",
            internal_waived,
        ))
    if not is_none_kind and status == "complete":
        absent_upstreams = []
        if not prd_present:
            absent_upstreams.append(
                "docs/PRD.yaml - requirement coverage not checked")
        if not ux_present:
            absent_upstreams.append(
                "docs/UX__*.yaml - screen coverage not checked")
        if data_entities is None:
            absent_upstreams.append(
                "docs/DATA-MODEL.yaml - entity links not checked")
        if absent_upstreams:
            warnings_found.append((
                "coverage checks ran without their upstream inputs - the "
                "verdict above does not vouch for these:",
                absent_upstreams,
            ))
    warnings_found.extend(check_provenance_freshness(api, docs_dir))

    # 5) Reporting
    def _problems():
        out = []
        out += [f"a required API.yaml field is empty: {m}" for m in missing_api]
        out += [f"a required resource field is empty: {m}" for m in missing_resource]
        out += applicability_errs
        out += [f"wrong id format in api_warnings - {e_}" for e_ in warning_id_errs]
        out += [f"wrong id format - {e_}" for e_ in id_format_errs]
        if uncovered_features:
            ids = [str(f).split(":", 1)[0].strip() for f in uncovered_features]
            out.append(
                f"{len(uncovered_features)} requirement(s) from the PRD are served by "
                f"no endpoint here: {join_ids(ids)}. Add a resource that traces them, "
                f"or list them under non_api_features if they need no API.")
        if uncovered_surfaces:
            ids = [str(s).split(":", 1)[0].strip() for s in uncovered_surfaces]
            out.append(
                f"{len(uncovered_surfaces)} screen(s) need data but no endpoint "
                f"supplies it: {join_ids(ids)}. Each data-bearing surface needs an "
                f"endpoint that serves it.")
        if bad_entities:
            out.append(
                f"{len(bad_entities)} resource(s) name a primary_entity that "
                f"DATA-MODEL.yaml does not define: {join_ids(bad_entities)}. Fix the "
                f"name, or add the entity with /sdlc:data.")
        return out

    # Honest coverage notes: never report zeros as a pass when the upstream
    # input was absent — say what was not checked, and why. When deferrals
    # carried part of the gate, say "served or deferred", not "served".
    any_deferred = bool(deferral.declared) or bool(deferral.fallback_ids)
    feat_note = (
        f"all {len(prd_features)} PRD requirement(s) "
        f"{'served or deferred' if any_deferred else 'served'}"
        if prd_present
        else "docs/PRD.yaml is missing, so requirement coverage was not checked"
    )
    surf_note = (
        f"all {len(ux_surfaces)} data-bearing screen(s) "
        f"{'supplied or deferred' if any_deferred else 'supplied'}"
        if ux_present
        else "no docs/UX__*.yaml files, so screen coverage was not checked"
    )
    data_note = (
        f"{len(data_entities)} data entit(y/ies)"
        if data_entities is not None
        else "DATA-MODEL.yaml is missing, so entity links were not checked"
    )

    if status == "complete":
        problems = _problems()
        if problems:
            print(f"[FAIL] {api_path} says it is finished, but {len(problems)} "
                  f"thing(s) are wrong. /sdlc:arch and everything after it will "
                  f"refuse it.")
            print_findings(problems, warnings_found)
            print_next("fix the items above, then re-run this check.",
                       "Re-running /sdlc:api walks you through them.")
            return 1
        if is_none_kind:
            print(f"[OK] {api_path} is finished - this project declares no API, so "
                  f"the coverage checks were skipped. /sdlc:arch can run it.")
        else:
            print(f"[OK] {api_path} is finished - {n_resources} resource file(s); "
                  f"{feat_note}; {surf_note}; {data_note}. "
                  f"/sdlc:arch can run it.")
        print_findings([], warnings_found)
        print_next("/sdlc:arch", show_glossary=bool(warnings_found))
        return 0

    # status == "draft"
    todo = _problems()
    if is_none_kind:
        print(f"[DRAFT] {api_path} is saved but not finished (this project declares "
              f"no API, so coverage was not checked). Later skills will refuse it "
              f"until it says 'complete'.")
    else:
        prd_found = (f"{len(prd_features)} PRD requirement(s)" if prd_present
                     else "no PRD.yaml (requirement coverage not checked)")
        ux_found = (f"{len(ux_surfaces)} data-bearing screen(s)" if ux_present
                    else "no UX__*.yaml files (screen coverage not checked)")
        print(f"[DRAFT] {api_path} is saved but not finished - {n_resources} "
              f"resource file(s) so far; upstream: {prd_found}, {ux_found}; "
              f"{data_note}. Later skills will refuse it until it says 'complete'.")
    print_findings(todo, warnings_found, blocking_header="TO FINISH IT")
    print_next("re-run /sdlc:api to continue, or set metadata.status: complete.",
               show_glossary=bool(todo) or bool(warnings_found))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate API.yaml + every API__*.yaml against the sdlc-api schema."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs", "API.yaml"),
        help="Path to API.yaml (default: ./docs/API.yaml). Sibling API__*.yaml "
        "files in the same directory are validated automatically.",
    )
    args = parser.parse_args(argv)
    return validate_all(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
