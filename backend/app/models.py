import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .crypto import EncryptedString, EncryptedText
from .db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class StaffRole(str, enum.Enum):
    super_admin = "super_admin"
    payer_admin = "payer_admin"
    care_manager = "care_manager"


class Channel(str, enum.Enum):
    sms = "sms"
    email = "email"


class OutreachStatus(str, enum.Enum):
    queued = "queued"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    opted_out = "opted_out"


class NumeratorSource(str, enum.Enum):
    unconfirmed = "unconfirmed"
    self_report = "self_report"
    claims_confirmed = "claims_confirmed"


class DrugClass(str, enum.Enum):
    """Therapeutic classes tracked for PDC medication-adherence measures."""

    diabetes = "diabetes"  # non-insulin diabetes medications (PDC-DR)
    rasa = "rasa"  # RAS antagonists: ACEIs / ARBs / direct renin inhibitors (PDC-RASA)
    statins = "statins"  # statin cholesterol medications (PDC-STA)


class GapStatus(str, enum.Enum):
    open = "open"
    outreach_sent = "outreach_sent"
    completed = "completed"
    needs_follow_up = "needs_follow_up"
    closed = "closed"
    excluded = "excluded"


class Tenant(Base):
    """A health plan / payer customer. Top-level multi-tenancy boundary."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    primary_color: Mapped[str] = mapped_column(String(16), default="#0d6efd")
    support_phone: Mapped[str] = mapped_column(String(32), default="")
    support_email: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    measure_configs: Mapped[list["TenantMeasureConfig"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    members: Mapped[list["Member"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    users: Mapped[list["StaffUser"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class Measure(Base):
    """Catalog of pluggable measure modules available on the platform.

    A tenant elects which of these to enable via TenantMeasureConfig. New measure
    domains (breast cancer screening, colorectal screening, etc.) are added here and
    in app/measures/ without touching tenant or member schema.
    """

    __tablename__ = "measures"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)  # e.g. "mental_health"
    hedis_measure_name: Mapped[str] = mapped_column(String(255))  # e.g. "Depression Screening and Follow-Up"
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class TenantMeasureConfig(Base):
    __tablename__ = "tenant_measure_configs"
    __table_args__ = (UniqueConstraint("tenant_id", "measure_code", name="uq_tenant_measure"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    measure_code: Mapped[str] = mapped_column(ForeignKey("measures.code"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # per-tenant overrides (cadence, thresholds)
    sequence_id: Mapped[str | None] = mapped_column(
        ForeignKey("outreach_sequences.id"), nullable=True
    )  # outreach cadence assigned to this measure (Feature C1)

    tenant: Mapped["Tenant"] = relationship(back_populates="measure_configs")
    measure: Mapped["Measure"] = relationship()


class StaffUser(Base):
    """Platform/payer staff: super_admin (platform), payer_admin, care_manager."""

    __tablename__ = "staff_users"
    __table_args__ = (UniqueConstraint("email", name="uq_staff_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(255), default="")
    # Brute-force protection: consecutive failed logins, and a lock expiry after
    # too many. Reset on any successful login.
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # TOTP multi-factor auth. `mfa_secret` is the base32 shared secret (set at
    # enrollment); `mfa_enabled` flips true only once the user confirms a code,
    # so a half-finished enrollment never blocks login.
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tenant: Mapped["Tenant | None"] = relationship(back_populates="users")


class Member(Base):
    """A patient/plan member, ingested from the payer's roster feed."""

    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("tenant_id", "external_member_id", name="uq_tenant_external_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    external_member_id: Mapped[str] = mapped_column(String(128), index=True)  # payer's member/subscriber ID

    # PII encrypted at the field level (AES-256-SIV, see app/crypto.py). date_of_birth
    # is deterministically encrypted so the magic-link identity lookup still works.
    first_name: Mapped[str] = mapped_column(EncryptedString(512))
    last_name: Mapped[str] = mapped_column(EncryptedString(512))
    date_of_birth: Mapped[str] = mapped_column(EncryptedString(512))  # YYYY-MM-DD (encrypted)
    sex: Mapped[str] = mapped_column(String(1), default="U")  # "F" | "M" | "U" — used by sex-specific measure eligibility (e.g. BCS)
    conditions: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["hypertension", "diabetes"] — condition-gated measure eligibility
    phone: Mapped[str] = mapped_column(EncryptedString(512), default="")
    email: Mapped[str] = mapped_column(EncryptedString(512), default="")
    preferred_channel: Mapped[str] = mapped_column(String(16), default=Channel.sms.value)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")

    consent_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_email: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    alias: Mapped[str] = mapped_column(String(32), default="")  # de-identified label shown to counselors
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="members")
    care_gaps: Mapped[list["CareGap"]] = relationship(back_populates="member", cascade="all, delete-orphan")
    dependents: Mapped[list["Dependent"]] = relationship(back_populates="guardian", cascade="all, delete-orphan")
    medication_fills: Mapped[list["MedicationFill"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    pregnancy_episodes: Mapped[list["PregnancyEpisode"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    exclusions: Mapped[list["MemberExclusion"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )


class Dependent(Base):
    """A minor dependent of a Member — the guardian is the account holder who
    receives outreach (SMS/email) and authenticates via magic link; the
    dependent is who a pediatric measure (Childhood Immunization Status,
    Well-Child Visits) is actually about. Introduced because those measures
    don't fit the assumption every other measure makes: that the person
    answering the outreach is the person being screened.
    """

    __tablename__ = "dependents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "external_dependent_id", name="uq_tenant_external_dependent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    guardian_member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    external_dependent_id: Mapped[str] = mapped_column(String(128), index=True)

    # PII encrypted at the field level (see app/crypto.py).
    first_name: Mapped[str] = mapped_column(EncryptedString(512))
    last_name: Mapped[str] = mapped_column(EncryptedString(512))
    date_of_birth: Mapped[str] = mapped_column(EncryptedString(512))  # YYYY-MM-DD (encrypted)
    sex: Mapped[str] = mapped_column(String(1), default="U")

    alias: Mapped[str] = mapped_column(String(32), default="")  # de-identified label shown to care managers
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    guardian: Mapped["Member"] = relationship(back_populates="dependents")
    care_gaps: Mapped[list["CareGap"]] = relationship(back_populates="dependent", cascade="all, delete-orphan")


class MedicationFill(Base):
    """A pharmacy dispensing event for a member, used to compute Proportion of
    Days Covered (PDC) medication-adherence measures. Ingested from the payer's
    pharmacy-claims feed — there is no self-report path, since a fill is claims
    evidence by nature, which is why PDC numerators derived from these rows are
    recorded as `claims_confirmed`.
    """

    __tablename__ = "medication_fills"
    __table_args__ = (
        # Idempotent re-ingestion when the feed carries a claim id. Partial unique
        # index (not a plain UniqueConstraint) so rows without a claim id — a NULL,
        # not "" — don't collide with each other, the same reason CareGap uses
        # partial indexes for its nullable dependent_id.
        Index(
            "uq_medication_fill_claim",
            "tenant_id",
            "external_claim_id",
            unique=True,
            sqlite_where=text("external_claim_id IS NOT NULL"),
            postgresql_where=text("external_claim_id IS NOT NULL"),
        ),
        Index("ix_medication_fills_member_class", "member_id", "drug_class"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    drug_class: Mapped[str] = mapped_column(String(32))  # DrugClass value
    ndc: Mapped[str] = mapped_column(String(16), default="")  # National Drug Code, optional
    drug_label: Mapped[str] = mapped_column(String(128), default="")  # human-readable, optional
    fill_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD, dispensing date
    days_supply: Mapped[int] = mapped_column(Integer)
    external_claim_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="pharmacy_claim")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    member: Mapped["Member"] = relationship(back_populates="medication_fills")


class PregnancyEpisode(Base):
    """A delivery (live-birth) episode for a member, the anchor for the Prenatal
    and Postpartum Care (PPC) measures. PPC is scored relative to the delivery
    date, not the calendar year, so its care gaps hang off an episode rather than
    the usual (member × measure × period) grain. Ingested from the payer's
    claims feed; `estimated_due_date` lets prenatal outreach be prospective when
    the pregnancy is known before delivery.
    """

    __tablename__ = "pregnancy_episodes"
    __table_args__ = (
        Index(
            "uq_pregnancy_episode_external",
            "tenant_id",
            "external_episode_id",
            unique=True,
            sqlite_where=text("external_episode_id IS NOT NULL"),
            postgresql_where=text("external_episode_id IS NOT NULL"),
        ),
        Index("ix_pregnancy_episodes_member", "member_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    delivery_date: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    estimated_due_date: Mapped[str] = mapped_column(String(10), default="")  # YYYY-MM-DD, optional
    external_episode_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="claim")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    member: Mapped["Member"] = relationship(back_populates="pregnancy_episodes")


class MemberExclusion(Base):
    """A HEDIS exclusion event on file for a member — the clinical/enrollment
    fact (hysterectomy, hospice, deceased, …) plus a `reference` an auditor can
    check. Which measures each code removes from the denominator is policy that
    lives in code (app/measures/exclusions.py + each Measure.exclusion_codes),
    not here.
    """

    __tablename__ = "member_exclusions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "member_id", "exclusion_code", name="uq_member_exclusion"),
        Index("ix_member_exclusions_member", "member_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    exclusion_code: Mapped[str] = mapped_column(String(64))
    reference: Mapped[str] = mapped_column(String(255), default="")  # claim/encounter evidence
    source: Mapped[str] = mapped_column(String(32), default="claim")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    member: Mapped["Member"] = relationship(back_populates="exclusions")


class MagicToken(Base):
    """Single-use passwordless login token sent to a member via SMS/email."""

    __tablename__ = "magic_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    purpose: Mapped[str] = mapped_column(String(32), default="screening")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CareGap(Base):
    """One row per (member or dependent) x measure x reporting period — the
    unit HEDIS reports on. `member_id` is always the account holder who
    receives outreach; `dependent_id` is set when the gap's actual subject is
    their dependent (pediatric measures) rather than the member themselves;
    `pregnancy_episode_id` is set for episode-scoped measures (PPC), where the
    grain is the delivery, not the calendar period, so one member can hold two
    PPC gaps for two deliveries in the same measurement year.

    Three partial unique indexes (not plain UniqueConstraints) because a NULL
    doesn't collide with another NULL under standard SQL unique semantics — a
    plain constraint would silently allow duplicate gaps. Each index governs one
    grain, and the conditions are mutually exclusive so a gap falls under exactly
    one: plain member gaps (no dependent, no episode), dependent gaps, and
    episode gaps.
    """

    __tablename__ = "care_gaps"
    __table_args__ = (
        Index(
            "uq_member_measure_period_no_dependent",
            "member_id",
            "measure_code",
            "period",
            unique=True,
            sqlite_where=text("dependent_id IS NULL AND pregnancy_episode_id IS NULL"),
            postgresql_where=text("dependent_id IS NULL AND pregnancy_episode_id IS NULL"),
        ),
        Index(
            "uq_dependent_measure_period",
            "dependent_id",
            "measure_code",
            "period",
            unique=True,
            sqlite_where=text("dependent_id IS NOT NULL"),
            postgresql_where=text("dependent_id IS NOT NULL"),
        ),
        Index(
            "uq_episode_measure",
            "pregnancy_episode_id",
            "measure_code",
            unique=True,
            sqlite_where=text("pregnancy_episode_id IS NOT NULL"),
            postgresql_where=text("pregnancy_episode_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    dependent_id: Mapped[str | None] = mapped_column(ForeignKey("dependents.id"), nullable=True, index=True)
    # Set for episode-scoped measures (PPC) — the gap belongs to one delivery.
    # The uq_episode_measure partial index covers lookups by this column.
    pregnancy_episode_id: Mapped[str | None] = mapped_column(
        ForeignKey("pregnancy_episodes.id"), nullable=True
    )
    measure_code: Mapped[str] = mapped_column(ForeignKey("measures.code"), index=True)
    period: Mapped[str] = mapped_column(String(16))  # e.g. "2026"

    status: Mapped[str] = mapped_column(String(32), default=GapStatus.open.value)
    numerator_met: Mapped[bool] = mapped_column(Boolean, default=False)
    # "unconfirmed" | "self_report" | "claims_confirmed" — provenance of
    # numerator_met, not just whether it's true. Every measure's numerator is
    # self-report today (see docs/HEDIS_COMPLIANCE.md); claims_confirmed is
    # set only via the staff confirm-numerator action, which requires a
    # claim/encounter reference (numerator_source_reference).
    numerator_source: Mapped[str] = mapped_column(String(32), default=NumeratorSource.unconfirmed.value)
    numerator_source_reference: Mapped[str] = mapped_column(String(255), default="")
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    # Advisory AI triage signal from a screening submission (Feature E) —
    # additive to safety_flag (which stays the deterministic instrument-scored
    # flag). NULL when AI is off. Rationale may paraphrase responses → encrypted.
    ai_risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)  # low|medium|high
    ai_risk_rationale: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)

    follow_up_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)

    last_outreach_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_outreach_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closure_reason: Mapped[str] = mapped_column(String(255), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    member: Mapped["Member"] = relationship(back_populates="care_gaps")
    dependent: Mapped["Dependent | None"] = relationship(back_populates="care_gaps")
    outreach_attempts: Mapped[list["OutreachAttempt"]] = relationship(
        back_populates="care_gap", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["ScreeningSubmission"]] = relationship(
        back_populates="care_gap", cascade="all, delete-orphan"
    )
    notes: Mapped[list["CaseNote"]] = relationship(back_populates="care_gap", cascade="all, delete-orphan")


class OutreachAttempt(Base):
    __tablename__ = "outreach_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    care_gap_id: Mapped[str] = mapped_column(ForeignKey("care_gaps.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    template_code: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default=OutreachStatus.queued.value)
    provider_message_id: Mapped[str] = mapped_column(String(255), default="")
    error: Mapped[str] = mapped_column(String(500), default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Cadence provenance (Feature C1) — null for standard retry-batch attempts.
    sequence_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    step_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Response tracking (Feature C1) — set when the member engages after an attempt.
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    response_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    care_gap: Mapped["CareGap"] = relationship(back_populates="outreach_attempts")


class ScreeningSubmission(Base):
    """A completed instrument (e.g. PHQ-9 + GAD-7) submitted by a member for a care gap."""

    __tablename__ = "screening_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    care_gap_id: Mapped[str] = mapped_column(ForeignKey("care_gaps.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    measure_code: Mapped[str] = mapped_column(String(32))
    instrument_scores: Mapped[dict] = mapped_column(JSON, default=dict)  # {"phq9": {...}, "gad7": {...}}
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    care_gap: Mapped["CareGap"] = relationship(back_populates="submissions")


# Free-text clinical note categories — kept in sync with schemas + the notes UI.
NOTE_TYPES = {"contact", "assessment", "safety_check", "care_coordination", "other"}


class CaseNote(Base):
    __tablename__ = "case_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    care_gap_id: Mapped[str] = mapped_column(ForeignKey("care_gaps.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    note: Mapped[str] = mapped_column(EncryptedText)  # PHI — encrypted at rest (transition-tolerant)
    note_type: Mapped[str] = mapped_column(String(32), default="other")  # see NOTE_TYPES
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    care_gap: Mapped["CareGap"] = relationship(back_populates="notes")


class CareTask(Base):
    """A follow-up to-do on a member (optionally tied to a specific care gap),
    with an optional due date / SLA — powers the tasks panel and overdue rollup."""

    __tablename__ = "care_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    care_gap_id: Mapped[str | None] = mapped_column(ForeignKey("care_gaps.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(300))  # operational, non-PHI
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assignee_staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|done|cancelled
    created_by: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CarePlanGoal(Base):
    """A goal + interventions on a member's care plan. Free-text fields are PHI
    (encrypted at rest)."""

    __tablename__ = "care_plan_goals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    care_gap_id: Mapped[str | None] = mapped_column(ForeignKey("care_gaps.id"), nullable=True)
    goal_text: Mapped[str] = mapped_column(EncryptedText)  # PHI — encrypted
    interventions_text: Mapped[str] = mapped_column(EncryptedText, default="")  # PHI — encrypted
    target_date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # YYYY-MM-DD
    status: Mapped[str] = mapped_column(String(16), default="open")  # open|met|discontinued
    created_by: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SafetyPlan(Base):
    """A member's safety plan (one active per member). All sections are free-text
    PHI, encrypted at rest."""

    __tablename__ = "safety_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), unique=True, index=True)
    warning_signs: Mapped[str] = mapped_column(EncryptedText, default="")       # PHI — encrypted
    coping_strategies: Mapped[str] = mapped_column(EncryptedText, default="")   # PHI — encrypted
    support_contacts: Mapped[str] = mapped_column(EncryptedText, default="")    # PHI — encrypted
    means_restriction: Mapped[str] = mapped_column(EncryptedText, default="")   # PHI — encrypted
    notes: Mapped[str] = mapped_column(EncryptedText, default="")               # PHI — encrypted
    updated_by: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EscalationStep(Base):
    """One completed/uncompleted step of a care gap's crisis-escalation protocol.
    `step_key` is drawn from the fixed protocol list in routers/safety.py, which
    is a placeholder pending clinical sign-off (see docs/HEDIS_COMPLIANCE.md)."""

    __tablename__ = "escalation_steps"
    __table_args__ = (UniqueConstraint("care_gap_id", "step_key", name="uq_gap_step"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    care_gap_id: Mapped[str] = mapped_column(ForeignKey("care_gaps.id"), index=True)
    step_key: Mapped[str] = mapped_column(String(64))
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_by: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OutreachSequence(Base):
    """A reusable outreach cadence (ordered steps). tenant_id NULL = a platform
    template readable by every tenant (copy-on-edit)."""

    __tablename__ = "outreach_sequences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    steps: Mapped[list["SequenceStep"]] = relationship(
        back_populates="sequence", cascade="all, delete-orphan"
    )


class SequenceStep(Base):
    __tablename__ = "sequence_steps"
    __table_args__ = (UniqueConstraint("sequence_id", "step_order", name="uq_seq_step_order"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("outreach_sequences.id"), index=True)
    step_order: Mapped[int] = mapped_column(Integer)
    offset_days: Mapped[int] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(16))  # sms | email | member_preferred
    template_key: Mapped[str] = mapped_column(String(64))
    recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    repeat_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    sequence: Mapped["OutreachSequence"] = relationship(back_populates="steps")


class SequenceEnrollment(Base):
    __tablename__ = "sequence_enrollments"
    __table_args__ = (Index("ix_enroll_due", "status", "next_send_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    care_gap_id: Mapped[str | None] = mapped_column(ForeignKey("care_gaps.id"), nullable=True)
    sequence_id: Mapped[str] = mapped_column(ForeignKey("outreach_sequences.id"))
    status: Mapped[str] = mapped_column(String(16), default="active")  # active | paused | ended
    current_step_order: Mapped[int] = mapped_column(Integer, default=0)
    next_send_at: Mapped[datetime] = mapped_column(DateTime)
    ended_by: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Conversation(Base):
    """One secure-messaging thread per member (care team ↔ member). Message
    bodies are PHI and never leave over SMS/email — only a notification with a
    magic-link does (Feature D)."""

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), unique=True, index=True)
    assigned_staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | snoozed | closed
    crisis_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    staff_unread: Mapped[bool] = mapped_column(Boolean, default=False)
    member_unread: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    direction: Mapped[str] = mapped_column(String(16))  # inbound | outbound
    channel: Mapped[str] = mapped_column(String(16))  # web | sms | email
    sender_staff_id: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)
    body: Mapped[str] = mapped_column(EncryptedText)  # PHI — encrypted at rest
    delivery_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    crisis_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    # Advisory AI triage signal (Feature E) — additive to crisis_flag, never a
    # replacement. NULL when AI is off or triage was inconclusive. Rationale can
    # paraphrase member text, so it's PHI and encrypted at rest.
    ai_risk_level: Mapped[str | None] = mapped_column(String(16), nullable=True)  # low|medium|high
    ai_risk_rationale: Mapped[str | None] = mapped_column(EncryptedText, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


AI_SURFACES = {"composer", "summary", "triage", "outreach"}
AI_OUTCOMES = {"generated", "accepted", "edited", "discarded"}


class AiInteraction(Base):
    """One row per KaveraChat AI assist call (Feature E). Every AI draft is
    logged here — which surface asked, which staff member, the model, token
    counts, latency, and what the human did with the draft (outcome). This is
    the accountability record: AI output is never applied directly, so the
    outcome trail shows a human accepted/edited/discarded each suggestion.

    Prompt and completion text are deliberately NOT stored — a draft can echo
    member PHI, and the interaction only needs to be countable and auditable,
    not replayable. The generated draft lives in the operator's request/response
    and, if accepted, in the note/message it becomes (already encrypted there)."""

    __tablename__ = "ai_interactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    surface: Mapped[str] = mapped_column(String(16))  # composer | summary | triage | outreach
    actor_staff_id: Mapped[str | None] = mapped_column(
        ForeignKey("staff_users.id"), nullable=True, index=True
    )
    member_id: Mapped[str | None] = mapped_column(ForeignKey("members.id"), nullable=True)
    model: Mapped[str] = mapped_column(String(128))
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str] = mapped_column(String(16), default="generated")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Append-only access/action log — required for HIPAA audit controls."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(String(16))  # "staff" | "member" | "system"
    actor_id: Mapped[str] = mapped_column(String(36), default="")
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64), default="")
    resource_id: Mapped[str] = mapped_column(String(36), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
