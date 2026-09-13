"""Validate PRD.yaml against the canonical sdlc:prd schema.

Run from the project root:

    python sdlc/skills/prd/validate_schema.py
    python sdlc/skills/prd/validate_schema.py --path some/other/PRD.yaml

Exit codes:
    0 — schema valid; either status='complete' with all required fields filled,
        or status='draft' (with or without missing required fields).
    1 — schema invalid (pydantic error), OR status='complete' but required
        fields are missing.
    2 — could not read or parse the file (missing, bad YAML, etc.)
    3 — required dependency missing (pydantic v2 or pyyaml)
"""

from __future__ import annotations

import argparse
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, Union


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
# Enums (kept in lockstep with PRD.schema.yaml)
# =============================================================================


class Confidence(str, Enum):
    confirmed = "confirmed"
    inferred = "inferred"
    assumption = "assumption"


class ExpertiseLevel(str, Enum):
    novice = "novice"
    intermediate = "intermediate"
    expert = "expert"
    mixed = "mixed"


class Scalability(str, Enum):
    small = "small"
    medium = "medium"
    large = "large"
    hyperscale = "hyperscale"


class Reliability(str, Enum):
    best_effort = "best_effort"
    high = "high"
    mission_critical = "mission_critical"


class Accessibility(str, Enum):
    none_yet = "none_yet"
    wcag_aa = "wcag_aa"
    wcag_aaa = "wcag_aaa"
    not_applicable_cli = "not_applicable_cli"  # 1.1: headless surfaces (cli/service/library)


class PrimaryLanguage(str, Enum):
    python = "python"
    typescript = "typescript"
    javascript = "javascript"
    go = "go"
    rust = "rust"
    java = "java"
    csharp = "csharp"
    ruby = "ruby"
    other = "other"
    undecided = "undecided"


class RuntimePlatform(str, Enum):
    web = "web"
    mobile_ios = "mobile_ios"
    mobile_android = "mobile_android"
    desktop = "desktop"
    cli = "cli"
    tui = "tui"              # 1.1: terminal UI
    server = "server"
    service = "service"      # 1.1: headless network service, no UI of its own
    library = "library"      # 1.1: ships as a dependency, no runtime of its own
    embedded = "embedded"
    browser_extension = "browser_extension"
    voice = "voice"          # 1.1
    other = "other"
    undecided = "undecided"  # in the 1.1 list form: only ever stands alone


class DeploymentTarget(str, Enum):
    cloud_aws = "cloud_aws"
    cloud_gcp = "cloud_gcp"
    cloud_azure = "cloud_azure"
    self_hosted = "self_hosted"
    on_prem = "on_prem"
    edge = "edge"
    serverless = "serverless"
    hybrid = "hybrid"
    local = "local"                        # 1.1: runs on the user's own machine
    cloud_managed = "cloud_managed"        # 1.1: PaaS-style, vendor-agnostic
    mobile_app_store = "mobile_app_store"  # 1.1
    undecided = "undecided"


class DataOwnership(str, Enum):
    user_owned = "user_owned"
    org_owned = "org_owned"
    platform_owned = "platform_owned"
    third_party = "third_party"
    mixed = "mixed"


class DataVolume(str, Enum):
    kilobytes = "kilobytes"
    megabytes = "megabytes"
    gigabytes = "gigabytes"
    terabytes = "terabytes"
    petabytes = "petabytes"
    unknown = "unknown"


class AuthModel(str, Enum):
    none = "none"
    api_key = "api_key"
    oauth2 = "oauth2"
    oidc = "oidc"
    saml = "saml"
    jwt = "jwt"
    session_cookie = "session_cookie"
    passkeys = "passkeys"
    mtls = "mtls"            # 1.1: mutual TLS (service-to-service)
    custom = "custom"


class DataSensitivity(str, Enum):
    public = "public"
    internal = "internal"
    confidential = "confidential"
    restricted = "restricted"
    regulated = "regulated"
    phi = "phi"              # 1.1: protected health information (HIPAA)
    pci = "pci"              # 1.1: payment-card data (PCI-DSS)


class Monetization(str, Enum):
    free = "free"
    freemium = "freemium"
    paid = "paid"
    subscription = "subscription"
    usage_based = "usage_based"
    enterprise = "enterprise"
    open_source = "open_source"
    internal_tool = "internal_tool"
    undecided = "undecided"


class LicenseType(str, Enum):
    proprietary = "proprietary"
    mit = "mit"
    apache_2 = "apache_2"
    gpl_v3 = "gpl_v3"
    agpl_v3 = "agpl_v3"
    bsd_3_clause = "bsd_3_clause"
    mpl_2 = "mpl_2"
    cc_by = "cc_by"
    cc_by_sa = "cc_by_sa"
    bsl = "bsl"              # 1.1: Business Source License
    sspl = "sspl"            # 1.1: Server Side Public License
    dual = "dual"            # 1.1: dual-licensed (e.g. AGPL + commercial)
    other = "other"
    undecided = "undecided"


class RiskDisposition(str, Enum):
    mitigated = "mitigated"                # reified into / handled by mitigation_refs
    accepted_residual = "accepted_residual"  # deliberately accepted standing risk
    open = "open"                          # undecided; surface at HITL (often a QUE)


# =============================================================================
# Theme models — declared in the canonical interview order from
# prd-questions.yaml (required themes first, product_identity last among
# required, optional themes follow).
# =============================================================================

# Allow extra keys we haven't modeled yet (forward-compat for new question
# additions); reject unknown enum values strictly.
_BASE_CONFIG = ConfigDict(extra="allow", str_strip_whitespace=True)


class _ThemeBase(BaseModel):
    model_config = _BASE_CONFIG


class ProblemOpportunity(_ThemeBase):
    problem_statement: Optional[str] = None
    problem_statement_confidence: Optional[Confidence] = None
    who_has_pain: Optional[List[str]] = None
    who_has_pain_confidence: Optional[Confidence] = None
    current_workarounds: Optional[List[str]] = None
    current_workarounds_confidence: Optional[Confidence] = None
    why_now: Optional[str] = None


class UsersPersonas(_ThemeBase):
    primary_users: Optional[List[str]] = None
    primary_users_confidence: Optional[Confidence] = None
    secondary_users: Optional[List[str]] = None
    user_goals: Optional[List[str]] = None
    user_frustrations: Optional[List[str]] = None
    expertise_level: Optional[ExpertiseLevel] = None
    expertise_level_confidence: Optional[Confidence] = None


class UseCases(_ThemeBase):
    core_workflows: Optional[List[str]] = None
    primary_jobs_to_be_done: Optional[List[str]] = None
    secondary_jobs: Optional[List[str]] = None
    edge_cases: Optional[List[str]] = None


class FunctionalRequirements(_ThemeBase):
    # D2: one flat `features` list. must_have_features / nice_to_have_features
    # are retained as ACCEPTED legacy fields (parse-and-union — see
    # `flat_features()`) so old PRDs validate; new writes emit only `features`.
    features: Optional[List[str]] = None
    must_have_features: Optional[List[str]] = None
    nice_to_have_features: Optional[List[str]] = None
    out_of_scope: Optional[List[str]] = None
    integrations_required: Optional[List[str]] = None
    integrations_required_confidence: Optional[Confidence] = None
    ai_features: Optional[List[str]] = None
    ai_features_confidence: Optional[Confidence] = None

    def flat_features(self) -> List[str]:
        """The FR list, tolerant of both shapes: `features` if present, else the
        legacy must_have + nice_to_have union (must first, preserving FR order)."""
        if self.features:
            return list(self.features)
        return list(self.must_have_features or []) + list(self.nice_to_have_features or [])


class TechnicalConstraints(_ThemeBase):
    primary_language: Optional[PrimaryLanguage] = None
    primary_language_rationale: Optional[str] = None
    primary_language_confidence: Optional[Confidence] = None
    framework: Optional[List[str]] = None
    framework_confidence: Optional[Confidence] = None
    # 1.1: multi-valued — every platform the product ships on, e.g.
    # [mobile_ios, mobile_android]. New writes always emit a list; a bare
    # scalar is accepted as the legacy form (see runtime_platforms()).
    runtime_platform: Optional[Union[List[RuntimePlatform], RuntimePlatform]] = None
    runtime_platform_rationale: Optional[str] = None
    runtime_platform_confidence: Optional[Confidence] = None
    deployment_target: Optional[DeploymentTarget] = None
    deployment_target_rationale: Optional[str] = None
    deployment_target_confidence: Optional[Confidence] = None
    existing_systems: Optional[List[str]] = None
    existing_systems_confidence: Optional[Confidence] = None
    browser_support: Optional[List[str]] = None

    def runtime_platforms(self) -> List[RuntimePlatform]:
        """The runtime_platform list, tolerant of both shapes: the 1.1 list,
        or the legacy scalar wrapped in a one-element list."""
        rp = self.runtime_platform
        if rp is None:
            return []
        return list(rp) if isinstance(rp, list) else [rp]


class ProductIdentity(_ThemeBase):
    idea_text: Optional[str] = None
    name: Optional[str] = None
    name_confidence: Optional[Confidence] = None
    slug: Optional[str] = None
    slug_confidence: Optional[Confidence] = None
    one_liner: Optional[str] = None
    one_liner_confidence: Optional[Confidence] = None
    tagline: Optional[str] = None
    vision: Optional[str] = None
    mission: Optional[str] = None


class NonFunctionalRequirements(_ThemeBase):
    performance_targets: Optional[List[str]] = None
    scalability: Optional[Scalability] = None
    scalability_confidence: Optional[Confidence] = None
    reliability: Optional[Reliability] = None
    reliability_confidence: Optional[Confidence] = None
    availability_sla: Optional[str] = None
    accessibility: Optional[Accessibility] = None
    other: Optional[List[str]] = None  # catch-all for any NFRs not captured above


class DataModel(_ThemeBase):
    key_entities: Optional[List[str]] = None
    data_ownership: Optional[DataOwnership] = None
    data_ownership_confidence: Optional[Confidence] = None
    data_volume_estimate: Optional[DataVolume] = None
    data_volume_estimate_confidence: Optional[Confidence] = None
    storage_preferences: Optional[List[str]] = None
    storage_preferences_rationale: Optional[str] = None
    storage_preferences_confidence: Optional[Confidence] = None


class SecurityCompliance(_ThemeBase):
    auth_model: Optional[AuthModel] = None
    auth_model_rationale: Optional[str] = None
    auth_model_confidence: Optional[Confidence] = None
    data_sensitivity: Optional[DataSensitivity] = None
    data_sensitivity_confidence: Optional[Confidence] = None
    regulatory_requirements: Optional[List[str]] = None
    regulatory_requirements_confidence: Optional[Confidence] = None
    encryption_at_rest: Optional[bool] = None
    audit_logging: Optional[bool] = None


class BusinessModel(_ThemeBase):
    monetization: Optional[Monetization] = None
    monetization_rationale: Optional[str] = None
    monetization_confidence: Optional[Confidence] = None
    pricing_model: Optional[str] = None
    license_type: Optional[LicenseType] = None
    license_type_rationale: Optional[str] = None
    license_type_confidence: Optional[Confidence] = None
    target_market: Optional[str] = None


class Stakeholders(_ThemeBase):
    product_owner: Optional[str] = None
    primary_contributors: Optional[List[str]] = None
    decision_maker: Optional[str] = None
    external_dependencies: Optional[List[str]] = None


class Milestones(_ThemeBase):
    # D2: milestones are REMOVED from new PRDs (no MVP/phase split — every
    # consumer is built whole by /sdlc:code). This model is retained only so
    # legacy PRDs still carrying a typed `milestones` block validate cleanly
    # (parse-and-accept); the interview never emits it. See PRD.schema.yaml.
    mvp_scope: Optional[str] = None
    phases: Optional[List[str]] = None


class SuccessMetrics(_ThemeBase):
    primary_kpis: Optional[List[str]] = None
    acceptance_criteria: Optional[List[str]] = None
    definition_of_done: Optional[List[str]] = None
    user_satisfaction_target: Optional[str] = None


class RiskItem(_ThemeBase):
    """One structured top risk — the richer (optional) form of a top_risks entry.

    A `top_risks` entry may be a plain string (legacy/simple form, no
    regression) OR this mapping. Only `statement` + `disposition` are
    required. `mitigation_refs` point at ids that EXIST at PRD-write time only
    (the PRD-minted families FR/NFR/QUE/INT/OOS/AIF) — NOT downstream ids like
    TST-/SIG- that no stage has minted yet (⚠C, D2). A mitigation realized by a
    later stage is simply the FR/NFR that demands it. They are references, not a
    new id family (no dangling check); `check_mitigation_refs()` emits an
    ADVISORY (never blocks) for any forward reference. By convention
    `mitigation_refs` is non-empty when disposition == mitigated, but that is a
    content-critic/judgment concern, not a deterministic gate.
    """

    statement: str                       # REQUIRED — the risk in prose
    disposition: RiskDisposition         # REQUIRED — mitigated | accepted_residual | open
    mitigation_refs: List[str] = Field(default_factory=list)  # OPTIONAL — PRD-write-time ids


# A top risk is EITHER a structured RiskItem OR a plain string. Mapping entries
# parse into RiskItem (typed disposition); plain strings stay strings.
RiskEntry = Union[RiskItem, str]


class RisksAssumptions(_ThemeBase):
    top_risks: Optional[List[RiskEntry]] = None
    key_assumptions: Optional[List[str]] = None
    blockers: Optional[List[str]] = None
    # DEPRECATED (1.1): accepted on read, never emitted by the interview. It
    # duplicated two better-owned fields — technical/service dependencies are
    # INT-NNN integrations (consumed by api/data); organizational ones live in
    # stakeholders.external_dependencies. Kept so legacy PRDs validate.
    dependencies: Optional[List[str]] = None


# =============================================================================
# 1.1 optional context blocks — adopted from the AICF meta-corpus PRD schema
# (DATA-MODEL.yaml `ProductRequirements` sub-models). Every field is optional
# and nullable: a PRD that omits all seven blocks is still complete. They stay
# typed mappings (no "<PREFIX>-NNN: " string form) because no downstream
# string-scan depends on them — see PRD.schema.yaml for the consumers.
# =============================================================================


class GlossaryTerm(_ThemeBase):
    term: Optional[str] = None
    definition: Optional[str] = None
    synonyms: Optional[List[str]] = None


class Glossary(_ThemeBase):
    terms: Optional[List[GlossaryTerm]] = None


class UserStoryItem(_ThemeBase):
    """One typed user story — the USR-NNN family (1.1).

    Like QUE, items are mappings, not prefixed strings: nothing downstream
    string-scans them, and the persona link (`owning_personas`) needs a slot
    of its own. Checked by check_user_stories(): id format + uniqueness and a
    non-empty story are violations (warning in draft, error in complete); a
    non-PER-NNN persona ref is only a warning.
    """

    id: Optional[str] = None                     # "USR-NNN"
    story: Optional[str] = None                  # "As a <persona>, I want <Y>, so that <Z>"
    owning_personas: Optional[List[str]] = None  # PER-NNN refs into users_personas


class UserStories(_ThemeBase):
    stories: Optional[List[UserStoryItem]] = None


class Internationalization(_ThemeBase):
    enabled: Optional[bool] = None
    default_locale: Optional[str] = None         # BCP-47, e.g. "en-US"
    target_locales: Optional[List[str]] = None
    rtl_support: Optional[bool] = None


class Competitor(_ThemeBase):
    name: Optional[str] = None
    url: Optional[str] = None
    strengths: Optional[List[str]] = None
    weaknesses: Optional[List[str]] = None
    pricing_notes: Optional[str] = None


class CompetitiveLandscape(_ThemeBase):
    competitors: Optional[List[Competitor]] = None
    differentiators: Optional[List[str]] = None
    market_positioning: Optional[str] = None


class LegalAndTerms(_ThemeBase):
    tos_required: Optional[bool] = None
    privacy_policy_required: Optional[bool] = None
    cookie_disclosure_required: Optional[bool] = None
    eula_required: Optional[bool] = None
    dpa_required: Optional[bool] = None          # Data Processing Agreement (GDPR Art. 28)


class ProductEvent(_ThemeBase):
    event_name: Optional[str] = None
    description: Optional[str] = None
    properties: Optional[List[str]] = None
    contains_pii: Optional[bool] = None


class AnalyticsAndTelemetry(_ThemeBase):
    product_events: Optional[List[ProductEvent]] = None
    consent_required: Optional[bool] = None
    pii_redaction_required: Optional[bool] = None


class SupportModel(_ThemeBase):
    channels: Optional[List[str]] = None
    sla_targets: Optional[Dict[str, str]] = None


class OpenQuestionItem(_ThemeBase):
    """One typed open question — the QUE-NNN family.

    Downstream stages gate on open questions (a QUE blocking an FR must be
    resolved before that FR is built), so items are typed mappings with a
    lifecycle status, not prose bullets. `undecided_decisions` and
    `parking_lot` share ONE continuous QUE counter (like FR across
    must/nice). Legacy plain-string entries still parse (Union below) but
    are flagged by check_open_questions — warnings in draft, errors in
    complete — mirroring the missing-prefix rule for every other family.
    """

    id: Optional[str] = None            # "QUE-NNN"
    question: Optional[str] = None      # the decision still open
    status: Optional[Literal["open", "resolved", "deferred"]] = "open"
    resolution: Optional[str] = None    # required once status == resolved
    blocks: Optional[List[str]] = None  # optional upstream ids gated by this
                                        # question (FR-NNN, NFR-NNN, WKF-NNN, …)


# Legacy plain-string entries accepted for parseability; flagged by
# check_open_questions. Mappings parse into OpenQuestionItem (typed status).
OpenQuestionEntry = Union[OpenQuestionItem, str]


class OpenQuestions(_ThemeBase):
    undecided_decisions: Optional[List[OpenQuestionEntry]] = None
    parking_lot: Optional[List[OpenQuestionEntry]] = None


# Free-form, project-defined cross-cutting convention map. The validator only
# enforces that the value is a mapping; sub-keys, value types, and nesting are
# all up to the writing agent (which records them per project under
# `conventions.<bucket-name>`). Items here are not addressable by ID family.
ConventionsType = Optional[Dict[str, Any]]


# =============================================================================
# Top-level models
# =============================================================================


class Metadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    prd_version: str
    last_updated: str  # ISO-8601 string; not parsed to datetime to keep YAML simple
    generated_by: str = "sdlc-prd"
    session_id: str
    monorepo: bool = False
    status: Literal["draft", "complete"] = "draft"


class Product(_ThemeBase):
    """One product's themes in interview order, used inside `products: <slug>: ...`."""

    problem_opportunity: Optional[ProblemOpportunity] = None
    users_personas: Optional[UsersPersonas] = None
    use_cases: Optional[UseCases] = None
    functional_requirements: Optional[FunctionalRequirements] = None
    technical_constraints: Optional[TechnicalConstraints] = None
    product_identity: Optional[ProductIdentity] = None
    non_functional_requirements: Optional[NonFunctionalRequirements] = None
    data_model: Optional[DataModel] = None
    security_compliance: Optional[SecurityCompliance] = None
    business_model: Optional[BusinessModel] = None
    stakeholders: Optional[Stakeholders] = None
    milestones: Optional[Milestones] = None
    success_metrics: Optional[SuccessMetrics] = None
    risks_assumptions: Optional[RisksAssumptions] = None
    # 1.1 optional context blocks, in interview order
    glossary: Optional[Glossary] = None
    user_stories: Optional[UserStories] = None
    internationalization: Optional[Internationalization] = None
    competitive_landscape: Optional[CompetitiveLandscape] = None
    legal_and_terms: Optional[LegalAndTerms] = None
    analytics_and_telemetry: Optional[AnalyticsAndTelemetry] = None
    support_model: Optional[SupportModel] = None
    open_questions: Optional[OpenQuestions] = None
    conventions: ConventionsType = None


class PipelineScopeEntry(BaseModel):
    """One `pipeline_scope.<stage>` entry: does this project need that stage?

    `applicable: false` is the SKIP authority — the stage need not be run and
    its artifact will never exist, so a consumer that finds it missing reads
    an intention here instead of guessing from the absence. A false entry
    without a `rationale` explains nothing to the next reader, so it is an
    error at `status: complete` (a warning in draft).
    """

    model_config = ConfigDict(extra="allow")

    applicable: bool
    rationale: Optional[str] = None
    confidence: Optional[Confidence] = None


class PRD(BaseModel):
    """Top-level PRD document.

    Single-product mode: theme blocks live at the top level; `products` is None.
    Multi-product mode:  `products` is a non-empty map; theme blocks are None.
    """

    model_config = ConfigDict(extra="allow")

    metadata: Metadata
    prd_warnings: List[Any] = Field(default_factory=list)  # str | typed WarningItem mapping
    # Optional, top-level even in monorepo mode: the pipeline is one pipeline.
    # Absent (or an absent key) means UNKNOWN, never "false".
    pipeline_scope: Optional[Dict[str, PipelineScopeEntry]] = None

    # Single-product theme blocks in interview order (mirror Product)
    problem_opportunity: Optional[ProblemOpportunity] = None
    users_personas: Optional[UsersPersonas] = None
    use_cases: Optional[UseCases] = None
    functional_requirements: Optional[FunctionalRequirements] = None
    technical_constraints: Optional[TechnicalConstraints] = None
    product_identity: Optional[ProductIdentity] = None
    non_functional_requirements: Optional[NonFunctionalRequirements] = None
    data_model: Optional[DataModel] = None
    security_compliance: Optional[SecurityCompliance] = None
    business_model: Optional[BusinessModel] = None
    stakeholders: Optional[Stakeholders] = None
    milestones: Optional[Milestones] = None
    success_metrics: Optional[SuccessMetrics] = None
    risks_assumptions: Optional[RisksAssumptions] = None
    # 1.1 optional context blocks, in interview order
    glossary: Optional[Glossary] = None
    user_stories: Optional[UserStories] = None
    internationalization: Optional[Internationalization] = None
    competitive_landscape: Optional[CompetitiveLandscape] = None
    legal_and_terms: Optional[LegalAndTerms] = None
    analytics_and_telemetry: Optional[AnalyticsAndTelemetry] = None
    support_model: Optional[SupportModel] = None
    open_questions: Optional[OpenQuestions] = None
    conventions: ConventionsType = None

    # Multi-product mode
    products: Optional[Dict[str, Product]] = None

    @model_validator(mode="after")
    def _check_mode(self) -> "PRD":
        single_themes = [
            self.problem_opportunity,
            self.users_personas,
            self.use_cases,
            self.functional_requirements,
            self.technical_constraints,
            self.product_identity,
            self.non_functional_requirements,
            self.data_model,
            self.security_compliance,
            self.business_model,
            self.stakeholders,
            self.milestones,
            self.success_metrics,
            self.risks_assumptions,
            self.glossary,
            self.user_stories,
            self.internationalization,
            self.competitive_landscape,
            self.legal_and_terms,
            self.analytics_and_telemetry,
            self.support_model,
            self.open_questions,
            self.conventions,
        ]
        any_single = any(t is not None for t in single_themes)

        if self.metadata.monorepo:
            if not self.products:
                raise ValueError("metadata.monorepo is true but `products` is missing or empty")
            if any_single:
                raise ValueError(
                    "monorepo mode set but top-level theme blocks are present; "
                    "in monorepo mode all themes must live under `products.<slug>`"
                )
        else:
            if self.products:
                raise ValueError(
                    "`products` is set but metadata.monorepo is false; "
                    "either set monorepo: true or move themes to top level"
                )
        return self


# =============================================================================
# ID-family check — every item in the registered list fields must start with
# "<PREFIX>-NNN: " (3+ zero-padded digits, colon, space). Violations are
# warnings for drafts; errors for status=complete.
#
# Sibling fields that should share one counter (e.g. the flat `features` list and
# the legacy must_have_features + nice_to_have_features it replaced, all sharing
# FR-NNN) appear as separate entries with the same prefix below. The validator
# only checks per-item format, not gapless numbering — the writing agent is
# responsible for sequential assignment.
#
# `scope` distinguishes two cases:
#   - "top"     — field lives at the PRD root in both single- and multi-product
#                 mode (currently only `prd_warnings`).
#   - "product" — field lives inside a product-scoped theme; in monorepo mode
#                 it sits under `products.<slug>.<theme>.<field>`.
# =============================================================================

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


# (prefix, dotted-path-from-scope-root, scope)
ID_FAMILIES: List[Tuple[str, str, str]] = [
    ("PER", "users_personas.primary_users", "product"),
    ("PER", "users_personas.secondary_users", "product"),
    ("GOL", "users_personas.user_goals", "product"),
    ("PAN", "users_personas.user_frustrations", "product"),
    ("WKF", "use_cases.core_workflows", "product"),
    ("JTB", "use_cases.primary_jobs_to_be_done", "product"),
    ("JTB", "use_cases.secondary_jobs", "product"),
    ("EDG", "use_cases.edge_cases", "product"),
    ("FR", "functional_requirements.features", "product"),
    ("FR", "functional_requirements.must_have_features", "product"),  # legacy (accepted)
    ("FR", "functional_requirements.nice_to_have_features", "product"),  # legacy (accepted)
    ("OOS", "functional_requirements.out_of_scope", "product"),
    ("INT", "functional_requirements.integrations_required", "product"),
    ("AIF", "functional_requirements.ai_features", "product"),
    ("NFR", "non_functional_requirements.performance_targets", "product"),
    ("NFR", "non_functional_requirements.other", "product"),
    ("ENT", "data_model.key_entities", "product"),
    # ACR — typed acceptance criteria. Emitting ACR-NNN here is what makes
    # downstream ACR→TST coverage gates instance-bearing instead of
    # mechanism-only (test's `covers` accepts ACR-NNN and resolves it by PRD
    # token scan).
    ("ACR", "success_metrics.acceptance_criteria", "product"),
]

# QUE — open_questions.undecided_decisions + .parking_lot share one QUE-NNN
# counter, but their items are typed MAPPINGS ({id, question, status, …}),
# not "QUE-NNN: <text>" strings — so they are checked by
# check_open_questions() below, not by the string-prefix machinery above.
# USR — user_stories.stories (1.1) is the other typed family ({id, story,
# owning_personas}); checked by check_user_stories() below.

# Legacy-shape floor (CLAUDE.md 10). The ACR-NNN prefix and the typed QUE
# mapping became blocking in July 2026 while prd_version was still 1.0, so a
# PRD stamped complete before then carries them as plain strings. prd_version
# is also an edit counter - repair's bump_artifact.py moves it on every
# surgical fix - so a floor a bump can reach would turn such a PRD red on its
# first repair. The floor therefore clears the corpus: below 2.0 a plain-string
# criterion or question warns; from 2.0 it blocks. A malformed TYPED entry
# blocks at every version - only an emitter that knew the typed form writes one.
LEGACY_SHAPE_FLOOR: Tuple[int, int] = (2, 0)
LEGACY_SHAPE_FAMILIES = ("ACR",)


def _legacy_shape_allowed(prd: "PRD") -> bool:
    m = re.match(r"^\s*(\d+)(?:\.(\d+))?", str(prd.metadata.prd_version or ""))
    version = (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)
    return version < LEGACY_SHAPE_FLOOR


_ID_PREFIX_RE_CACHE: Dict[str, re.Pattern] = {}


def _id_prefix_re(prefix: str) -> re.Pattern:
    rx = _ID_PREFIX_RE_CACHE.get(prefix)
    if rx is None:
        rx = re.compile(rf"^{re.escape(prefix)}-\d{{3,}}: .+")
        _ID_PREFIX_RE_CACHE[prefix] = rx
    return rx


def check_ids(prd: "PRD", legacy: Optional[List[str]] = None) -> List[str]:
    """Return violation messages for items missing their family's ID prefix.

    Below LEGACY_SHAPE_FLOOR a plain-string item in a LEGACY_SHAPE_FAMILIES
    list goes to ``legacy`` (a warning) instead, when the caller passes one."""
    violations: List[str] = []
    lenient = legacy is not None and _legacy_shape_allowed(prd)

    # prd_warnings is the one family whose items may be a typed mapping instead
    # of a "WRN-NNN: <text>" string, so it is checked by the canonical WRN
    # block rather than by the generic prefix table below.
    violations.extend(check_warning_ids(prd.prd_warnings, "prd_warnings"))

    def _check_list(items: object, path: str, prefix: str) -> None:
        if not isinstance(items, list):
            return
        rx = _id_prefix_re(prefix)
        for i, item in enumerate(items):
            if not isinstance(item, str) or not rx.match(item):
                msg = f"{path}[{i}]: expected '{prefix}-NNN: …' prefix, got {item!r}"
                if lenient and prefix in LEGACY_SHAPE_FAMILIES and isinstance(item, str):
                    legacy.append(msg)  # type: ignore[union-attr]
                else:
                    violations.append(msg)

    # top-level fields (currently just prd_warnings → WRN)
    for prefix, dotted_path, scope in ID_FAMILIES:
        if scope == "top":
            _check_list(_get_dotted(prd, dotted_path), dotted_path, prefix)

    # product-scoped fields
    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            for prefix, dotted_path, scope in ID_FAMILIES:
                if scope == "product":
                    _check_list(
                        _get_dotted(product, dotted_path),
                        f"products.{slug}.{dotted_path}",
                        prefix,
                    )
    else:
        for prefix, dotted_path, scope in ID_FAMILIES:
            if scope == "product":
                _check_list(_get_dotted(prd, dotted_path), dotted_path, prefix)

    return violations


_QUE_ID_RE = re.compile(r"^QUE-\d{3,}$")


def check_open_questions(prd: "PRD", legacy: Optional[List[str]] = None) -> List[str]:
    """Violations for the typed QUE family (open_questions).

    Items are typed mappings {id: QUE-NNN, question, status} — the two lists
    (undecided_decisions + parking_lot) share one continuous QUE counter per
    scope. A legacy plain-string bullet is a violation from prd_version 2.0
    (LEGACY_SHAPE_FLOOR) and goes to ``legacy`` - a warning - below it; the
    update flow retrofits them with the next QUE id and status: open. A
    malformed TYPED entry is a violation at every version.
    """
    violations: List[str] = []
    lenient = legacy is not None and _legacy_shape_allowed(prd)

    def _check_scope(root: object, scope_label: str) -> None:
        oq = getattr(root, "open_questions", None)
        if oq is None:
            return
        seen: Dict[str, str] = {}
        for field in ("undecided_decisions", "parking_lot"):
            items = getattr(oq, field, None)
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items):
                where = f"{scope_label}open_questions.{field}[{i}]"
                if isinstance(item, str):
                    (legacy if lenient else violations).append(  # type: ignore[union-attr]
                        f"{where}: expected typed mapping "
                        f"{{id: QUE-NNN, question, status}}, got plain string "
                        f"{item!r} — retrofit with the next QUE id and "
                        f"status: open"
                    )
                    continue
                qid = (item.id or "").strip()
                if not _QUE_ID_RE.match(qid):
                    violations.append(f"{where}.id: expected 'QUE-NNN', got {item.id!r}")
                elif qid in seen:
                    violations.append(
                        f"{where}.id '{qid}' duplicates {seen[qid]} — the two "
                        f"open_questions lists share one QUE counter"
                    )
                else:
                    seen[qid] = where
                if not (item.question or "").strip():
                    violations.append(f"{where}.question: missing")
                if item.status == "resolved" and not (item.resolution or "").strip():
                    violations.append(
                        f"{where}: status is 'resolved' but resolution is empty"
                    )

    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            _check_scope(product, f"products.{slug}.")
    else:
        _check_scope(prd, "")

    return violations


# QUE `blocks` resolution — WARNINGS only, never blocks. A QUE entry gates
# downstream work through the ids its `blocks` list names (task lists
# QUE-blocked units at code's plan gate); a malformed or dangling ref means
# the gate can never fire, so the question silently stops protecting anything.
_BLOCKS_REF_RE = re.compile(r"^(FR|NFR|WKF|ACR)-\d{3,}$")
_HEAD_ID_RE = re.compile(r"^\s*([A-Z]+-\d{3,})\s*:")


def check_que_blocks(prd: "PRD") -> List[str]:
    """WARNINGS (never block): open_questions[].blocks entries that are not
    FR-/NFR-/WKF-/ACR-NNN ids, or that name an id this PRD does not emit."""
    warns: List[str] = []

    def _emitted_ids(root: object) -> Set[str]:
        ids: Set[str] = set()
        fr_block = getattr(root, "functional_requirements", None)
        lists: List[object] = [fr_block.flat_features() if fr_block is not None else []]
        for path in (
            "non_functional_requirements.performance_targets",
            "non_functional_requirements.other",
            "use_cases.core_workflows",
            "success_metrics.acceptance_criteria",
        ):
            lists.append(_get_dotted(root, path) or [])
        for items in lists:
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, str):
                    m = _HEAD_ID_RE.match(item)
                    if m:
                        ids.add(m.group(1).upper())
        return ids

    def _scope(label: str, root: object) -> None:
        oq = getattr(root, "open_questions", None)
        if oq is None:
            return
        known = _emitted_ids(root)
        for field in ("undecided_decisions", "parking_lot"):
            items = getattr(oq, field, None)
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items):
                blocks = getattr(item, "blocks", None)
                if not isinstance(blocks, list):
                    continue
                qid = getattr(item, "id", None) or f"open_questions.{field}[{i}]"
                where = f"{label}{qid}"
                for ref in blocks:
                    norm = ref.strip().upper() if isinstance(ref, str) else ""
                    if not _BLOCKS_REF_RE.match(norm):
                        warns.append(
                            f"{where}.blocks names {ref!r}, which is not an "
                            f"FR-/NFR-/WKF-/ACR-NNN id, so no later skill can "
                            f"hold work back on it - point it at a requirement "
                            f"id this PRD emits, or drop it."
                        )
                    elif norm not in known:
                        warns.append(
                            f"{where}.blocks names {ref.strip()}, but this PRD "
                            f"defines no such id, so the question gates "
                            f"nothing - fix the id or drop it."
                        )

    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            _scope(f"products.{slug}.", product)
    else:
        _scope("", prd)
    return warns


_USR_ID_RE = re.compile(r"^USR-\d{3,}$")
_PER_REF_RE = re.compile(r"^PER-\d{3,}$")


def check_user_stories(prd: "PRD") -> Tuple[List[str], List[str]]:
    """(violations, warnings) for the typed USR family (user_stories.stories, 1.1).

    Items are typed mappings {id: USR-NNN, story, owning_personas}. A bad or
    duplicate id and an empty story are violations — warnings in draft,
    errors in complete, like every other family. An owning_personas entry
    that is not a PER-NNN id is only a warning: the story may name a persona
    the interview has not minted yet, and nothing downstream gates on the link.
    """
    violations: List[str] = []
    warnings: List[str] = []

    def _check_scope(root: object, scope_label: str) -> None:
        block = getattr(root, "user_stories", None)
        items = getattr(block, "stories", None) if block is not None else None
        if not isinstance(items, list):
            return
        seen: Dict[str, str] = {}
        for i, item in enumerate(items):
            where = f"{scope_label}user_stories.stories[{i}]"
            raw_id = getattr(item, "id", None)
            sid = (raw_id or "").strip()
            if not _USR_ID_RE.match(sid):
                violations.append(f"{where}.id: expected 'USR-NNN', got {raw_id!r}")
            elif sid in seen:
                violations.append(f"{where}.id '{sid}' duplicates {seen[sid]}")
            else:
                seen[sid] = where
            if not (getattr(item, "story", None) or "").strip():
                violations.append(f"{where}.story: missing")
            for ref in getattr(item, "owning_personas", None) or []:
                if not isinstance(ref, str) or not _PER_REF_RE.match(ref.strip()):
                    warnings.append(
                        f"{where}.owning_personas names {ref!r}, which is not a "
                        f"PER-NNN persona id - point it at an entry of "
                        f"users_personas.primary_users / secondary_users."
                    )

    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            _check_scope(product, f"products.{slug}.")
    else:
        _check_scope(prd, "")

    return violations, warnings


def check_runtime_platform(prd: "PRD") -> List[str]:
    """Violations for the multi-valued technical_constraints.runtime_platform
    (1.1). The legacy scalar form has nothing to check; the list form must not
    repeat a value and must not mix `undecided` with concrete platforms.
    Warnings in draft, errors in complete — the same tier as the id checks.
    """
    violations: List[str] = []

    def _check_scope(root: object, scope_label: str) -> None:
        tc = getattr(root, "technical_constraints", None)
        rp = getattr(tc, "runtime_platform", None) if tc is not None else None
        if not isinstance(rp, list):
            return
        where = f"{scope_label}technical_constraints.runtime_platform"
        values = [v.value if isinstance(v, Enum) else str(v) for v in rp]
        repeated = sorted({v for v in values if values.count(v) > 1})
        if repeated:
            violations.append(
                f"{where}: {', '.join(repeated)} listed more than once - name "
                f"each platform once."
            )
        if "undecided" in values and len(values) > 1:
            violations.append(
                f"{where}: 'undecided' sits next to concrete platforms, so no "
                f"later skill can tell whether the platform is decided - drop "
                f"'undecided' or drop the others."
            )

    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            _check_scope(product, f"products.{slug}.")
    else:
        _check_scope(prd, "")

    return violations


# =============================================================================
# Required-field check — separate from schema validation so drafts can be
# saved without failing. Validation behavior depends on metadata.status.
# =============================================================================

# Path is dotted relative to a Product (or top level in single-product mode).
# NB: the FR list requirement is NOT in this table — it is D2-tolerant (satisfied
# by the flat `features` list OR the legacy must/nice union) and checked
# separately in check_required().
REQUIRED_PATHS: List[str] = [
    "problem_opportunity.problem_statement",
    "users_personas.primary_users",
    "use_cases.core_workflows",
    "technical_constraints.primary_language",
    "technical_constraints.runtime_platform",
    "product_identity.name",
    "product_identity.one_liner",
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


_FR_HEAD_RE = re.compile(r"^\s*(FR-\d+)\s*:")
_FR_TOKEN_RE = re.compile(r"\bFR-\d+\b", re.IGNORECASE)


def check_pipeline_scope(prd: "PRD") -> List[str]:
    """Violations for the optional top-level `pipeline_scope` block (1.2).

    Scoping a stage OUT is the one entry a later reader has to act on: it is
    why `docs/UX.yaml` is missing and why nothing will stop to ask about it.
    An entry that says `applicable: false` and gives no reason leaves that
    reader with a fact and no way to judge it, so the reason is required.
    Warnings in draft, errors in complete - the same tier as the id checks.
    """
    violations: List[str] = []
    scope = getattr(prd, "pipeline_scope", None)
    if not scope:
        return violations
    known = {"ux", "design", "api"}
    for stage, entry in scope.items():
        where = f"pipeline_scope.{stage}"
        if stage not in known:
            violations.append(
                f"{where}: '{stage}' is not an optional stage - only "
                f"{', '.join(sorted(known))} can be scoped out; every other "
                f"stage always runs."
            )
            continue
        if entry.applicable is False and not (entry.rationale or "").strip():
            violations.append(
                f"{where}: scoped out with no rationale - say in one sentence "
                f"why this project has no {stage}, so the skills that skip it "
                f"can tell the user why."
            )
    return violations


def check_acr_coverage(prd: PRD) -> List[str]:
    """ADVISORY (never blocks): FRs no acceptance criterion names.

    Downstream `test` gates ACR→TST coverage, so an FR that no ACR-NNN entry
    names (an `FR-NNN` token inside the criterion string) has no machine-linked
    done-condition — flag it so the interview can add one. D2: scopes to ALL
    FRs (the flat `features` list, or the legacy union), not just must-haves.
    """
    gaps: List[str] = []

    def _scope(label: str, root: object) -> None:
        fr_block = getattr(root, "functional_requirements", None)
        frs = fr_block.flat_features() if fr_block is not None else []
        acrs = _get_dotted(root, "success_metrics.acceptance_criteria") or []
        named = {m.upper() for a in acrs if isinstance(a, str) for m in _FR_TOKEN_RE.findall(a)}
        for entry in frs:
            if not isinstance(entry, str):
                continue
            head = _FR_HEAD_RE.match(entry)
            if head and head.group(1).upper() not in named:
                gaps.append(f"{label}{head.group(1)}: no acceptance_criteria entry names it")

    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            _scope(f"products.{slug}.", product)
    else:
        _scope("", prd)
    return gaps


# mitigation_refs may name only ids that EXIST at PRD-write time — the PRD-minted
# families. TST/SIG/... are minted by downstream stages and cannot be resolved
# forward (⚠C, D2). This is the realization of "restrict to same-stage/upstream
# ids": FR/NFR/QUE are the common mitigators; INT/OOS/AIF are also PRD-minted
# and therefore admissible (the corpus legitimately mitigates a risk with an
# INT-NNN integration id). Anything else is a forward reference → advisory.
_MITIGATION_ALLOWED_PREFIXES: Set[str] = {"FR", "NFR", "QUE", "INT", "OOS", "AIF"}
_REF_PREFIX_RE = re.compile(r"^([A-Z]+)-\d+$")


def check_mitigation_refs(prd: PRD) -> List[str]:
    """ADVISORY (never blocks): mitigation_refs that forward-reference an id no
    stage has minted at PRD-write time (a downstream family like TST-/SIG-)."""
    warns: List[str] = []

    def _scope(label: str, root: object) -> None:
        risks_block = getattr(root, "risks_assumptions", None)
        risks = getattr(risks_block, "top_risks", None) or []
        for risk in risks:
            refs = getattr(risk, "mitigation_refs", None) or []
            for ref in refs:
                if not isinstance(ref, str):
                    continue
                m = _REF_PREFIX_RE.match(ref.strip().upper())
                if m and m.group(1) not in _MITIGATION_ALLOWED_PREFIXES:
                    warns.append(
                        f"{label}mitigation_refs names '{ref}', which is an id from a "
                        f"document that does not exist yet when the PRD is written. "
                        f"Reference the FR or NFR the mitigation delivers instead."
                    )

    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            _scope(f"products.{slug}.", product)
    else:
        _scope("", prd)
    return warns


def check_required(prd: PRD) -> List[str]:
    """Return list of missing required field paths.

    In monorepo mode, paths are prefixed with `products.<slug>.`.
    """
    missing: List[str] = []

    def _check(scope_label: str, root: object) -> None:
        for path in REQUIRED_PATHS:
            if _is_empty(_get_dotted(root, path)):
                missing.append(f"{scope_label}{path}")
        # FR list is D2-tolerant: satisfied by flat `features` OR the legacy
        # must/nice union. Report against the canonical new path when absent.
        fr_block = getattr(root, "functional_requirements", None)
        frs = fr_block.flat_features() if fr_block is not None else []
        if _is_empty(frs):
            missing.append(f"{scope_label}functional_requirements.features")

    if prd.metadata.monorepo and prd.products:
        for slug, product in prd.products.items():
            _check(f"products.{slug}.", product)
    else:
        _check("", prd)

    return missing


# =============================================================================
# CLI
# =============================================================================


def _format_pydantic_errors(err: ValidationError) -> List[str]:
    formatted: List[str] = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e.get("loc", ()))
        msg = e.get("msg", "invalid")
        formatted.append(f"{loc}: {msg}")
    return formatted


def validate_file(path: Path) -> int:
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        print(f"ERROR: YAML parse error in {path}:\n  {e}", file=sys.stderr)
        return 2

    if raw is None:
        print(f"ERROR: {path} is empty", file=sys.stderr)
        return 2

    if not isinstance(raw, dict):
        print(
            f"ERROR: {path} top level must be a mapping, got {type(raw).__name__}",
            file=sys.stderr,
        )
        return 2

    try:
        prd = PRD.model_validate(raw)
    except ValidationError as e:
        print(f"[FAIL] {path} does not match the PRD schema. No later skill can "
              f"read it until these fields are fixed:\n")
        for line in _format_pydantic_errors(e):
            print(f"  - {line}")
        print_next("fix the fields above, or re-run /sdlc:prd to rewrite the file.")
        return 1

    missing = check_required(prd)
    usr_violations, usr_warns = check_user_stories(prd)
    legacy_shape: List[str] = []
    id_violations = (check_ids(prd, legacy_shape) + check_open_questions(prd, legacy_shape)
                     + usr_violations)
    value_violations = check_runtime_platform(prd) + check_pipeline_scope(prd)
    acr_gaps = check_acr_coverage(prd)
    mitigation_warns = check_mitigation_refs(prd)
    que_warns = check_que_blocks(prd)
    status = prd.metadata.status

    def _soft_warnings() -> List[object]:
        out: List[object] = []
        if acr_gaps:
            ids = [g.split(":", 1)[0].strip() for g in acr_gaps]
            out.append(
                f"{len(acr_gaps)} feature(s) have no acceptance criterion saying when "
                f"they are done, so nothing downstream can tell whether they work: "
                f"{join_ids(ids)}. Add ACR-NNN entries under "
                f"success_metrics.acceptance_criteria naming them."
            )
        if legacy_shape:
            out.append((
                f"{len(legacy_shape)} acceptance criteria / open question(s) still use the "
                f"plain-string form this PRD (prd_version {prd.metadata.prd_version}) was "
                f"written with, so a test cannot cite a criterion by its ACR id and an open "
                f"question cannot name what it blocks. Re-run /sdlc:prd - its update flow "
                f"gives each one the next id. Not blocking below prd_version 2.0:",
                legacy_shape,
            ))
        for w in mitigation_warns:
            out.append(w)
        for w in usr_warns:
            out.append(w)
        if len(que_warns) > 4:
            out.append((
                f"{len(que_warns)} open-question blocks references do not "
                f"resolve to an id this PRD emits:",
                que_warns,
            ))
        else:
            out.extend(que_warns)
        return out

    if status == "complete":
        problems = [f"a required field is empty: {m}" for m in missing]
        problems += [f"wrong id format - {v}" for v in id_violations]
        problems += [f"invalid value - {v}" for v in value_violations]
        if problems:
            print(f"[FAIL] {path} says it is finished, but {len(problems)} thing(s) "
                  f"are wrong. /sdlc:ux and everything after it will refuse it.")
            print_findings(problems, _soft_warnings())
            print_next("fill the fields above in, then re-run this check.",
                       "Re-running /sdlc:prd walks you through them.")
            return 1
        print(f"[OK] {path} is finished - /sdlc:ux can run it.")
        print_findings([], _soft_warnings())
        print_next("/sdlc:ux", show_glossary=bool(acr_gaps or mitigation_warns
                                                  or usr_warns or que_warns or legacy_shape))
        return 0

    # status == "draft"
    todo = [f"a required field is empty: {m}" for m in missing]
    todo += [f"wrong id format - {v}" for v in id_violations]
    todo += [f"invalid value - {v}" for v in value_violations]
    if missing:
        print(f"[DRAFT] {path} is saved but not finished - {len(missing)} required "
              f"field(s) still empty. Later skills will refuse it until it says "
              f"'complete'.")
    else:
        print(f"[DRAFT] {path} is saved with every required field filled. Set "
              f"metadata.status to 'complete' to release it to the next skill.")
    print_findings(todo, _soft_warnings(), blocking_header="TO FINISH IT")
    print_next("re-run /sdlc:prd to continue, or set metadata.status: complete.",
               show_glossary=bool(todo or acr_gaps or mitigation_warns
                                  or usr_warns or que_warns or legacy_shape))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate PRD.yaml against the sdlc-prd schema.")
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("docs", "PRD.yaml"),
        help="Path to PRD.yaml (default: ./docs/PRD.yaml)",
    )
    args = parser.parse_args(argv)
    return validate_file(args.path)


if __name__ == "__main__":
    raise SystemExit(main())
