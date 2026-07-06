from datetime import datetime

from pydantic import BaseModel, EmailStr


class TenantCreate(BaseModel):
    slug: str
    name: str
    primary_color: str = "#0d6efd"
    support_phone: str = ""
    support_email: str = ""
    enabled_measures: list[str] = ["mental_health"]
    first_admin_email: EmailStr | None = None
    first_admin_password: str | None = None


class TenantOut(BaseModel):
    id: str
    slug: str
    name: str
    primary_color: str
    member_count: int = 0
    open_gaps: int = 0

    class Config:
        from_attributes = True


class MeasureToggle(BaseModel):
    measure_code: str
    enabled: bool
    config: dict = {}


class StaffLogin(BaseModel):
    email: EmailStr
    password: str


class StaffOut(BaseModel):
    id: str
    email: str
    role: str
    name: str
    tenant_id: str | None

    class Config:
        from_attributes = True


class MemberCreate(BaseModel):
    external_member_id: str
    first_name: str
    last_name: str
    date_of_birth: str  # YYYY-MM-DD
    sex: str = "U"  # "F" | "M" | "U"
    conditions: list[str] = []  # e.g. ["hypertension", "diabetes"]
    phone: str = ""
    email: str = ""
    preferred_channel: str = "sms"
    preferred_language: str = "en"
    consent_sms: bool = False
    consent_email: bool = False


class MemberOut(BaseModel):
    id: str
    external_member_id: str
    first_name: str
    last_name: str
    sex: str
    conditions: list[str]
    alias: str
    preferred_channel: str
    consent_sms: bool
    consent_email: bool

    class Config:
        from_attributes = True


class DependentCreate(BaseModel):
    external_dependent_id: str
    first_name: str
    last_name: str
    date_of_birth: str  # YYYY-MM-DD
    sex: str = "U"


class DependentOut(BaseModel):
    id: str
    external_dependent_id: str
    first_name: str
    last_name: str
    sex: str
    alias: str
    guardian_member_id: str

    class Config:
        from_attributes = True


class MagicLinkRequest(BaseModel):
    external_member_id: str
    date_of_birth: str


class MagicLinkVerify(BaseModel):
    token: str


class ScreeningSubmit(BaseModel):
    """`responses` shape is measure-specific — each Measure module interprets its
    own payload (see app/measures/*.py). Mental health expects
    {"phq9": [...], "gad7": [...]}; breast cancer expects
    {"has_completed": bool, "completed_date": str | None, "wants_scheduling_help": bool}.
    """

    care_gap_id: str
    responses: dict


class CaseNoteCreate(BaseModel):
    note: str


class GapStatusUpdate(BaseModel):
    status: str
    reason: str = ""


class NumeratorConfirm(BaseModel):
    """Staff action recording a claims/encounter match for a self-reported
    numerator — the `reference` is what a HEDIS auditor will ask for (claim ID,
    encounter number, or whatever your claims system uses to look it up)."""

    reference: str


class CareGapOut(BaseModel):
    id: str
    measure_code: str
    period: str
    status: str
    safety_flag: bool
    numerator_met: bool
    follow_up_due_at: datetime | None
    member_alias: str

    class Config:
        from_attributes = True
