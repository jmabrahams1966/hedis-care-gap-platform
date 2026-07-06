import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tenant: Mapped["Tenant | None"] = relationship(back_populates="users")


class Member(Base):
    """A patient/plan member, ingested from the payer's roster feed."""

    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("tenant_id", "external_member_id", name="uq_tenant_external_member"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    external_member_id: Mapped[str] = mapped_column(String(128), index=True)  # payer's member/subscriber ID

    first_name: Mapped[str] = mapped_column(String(128))
    last_name: Mapped[str] = mapped_column(String(128))
    date_of_birth: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    sex: Mapped[str] = mapped_column(String(1), default="U")  # "F" | "M" | "U" — used by sex-specific measure eligibility (e.g. BCS)
    conditions: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["hypertension", "diabetes"] — condition-gated measure eligibility
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    preferred_channel: Mapped[str] = mapped_column(String(16), default=Channel.sms.value)
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")

    consent_sms: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_email: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    alias: Mapped[str] = mapped_column(String(32), default="")  # de-identified label shown to counselors
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    tenant: Mapped["Tenant"] = relationship(back_populates="members")
    care_gaps: Mapped[list["CareGap"]] = relationship(back_populates="member", cascade="all, delete-orphan")


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
    """One row per member x measure x reporting period — the unit HEDIS reports on."""

    __tablename__ = "care_gaps"
    __table_args__ = (UniqueConstraint("member_id", "measure_code", "period", name="uq_member_measure_period"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    measure_code: Mapped[str] = mapped_column(ForeignKey("measures.code"), index=True)
    period: Mapped[str] = mapped_column(String(16))  # e.g. "2026"

    status: Mapped[str] = mapped_column(String(32), default=GapStatus.open.value)
    numerator_met: Mapped[bool] = mapped_column(Boolean, default=False)
    safety_flag: Mapped[bool] = mapped_column(Boolean, default=False)

    follow_up_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(ForeignKey("staff_users.id"), nullable=True)

    last_outreach_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_outreach_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closure_reason: Mapped[str] = mapped_column(String(255), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    member: Mapped["Member"] = relationship(back_populates="care_gaps")
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


class CaseNote(Base):
    __tablename__ = "case_notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    care_gap_id: Mapped[str] = mapped_column(ForeignKey("care_gaps.id"), index=True)
    author_id: Mapped[str] = mapped_column(ForeignKey("staff_users.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    care_gap: Mapped["CareGap"] = relationship(back_populates="notes")


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
