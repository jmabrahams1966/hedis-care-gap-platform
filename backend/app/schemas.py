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


class MfaCode(BaseModel):
    """A 6-digit TOTP code, used to confirm enrollment or disable MFA."""

    code: str


class MfaVerify(BaseModel):
    """Completes a login for an MFA-enabled staff user: the short-lived
    `mfa_token` from the password step plus the current authenticator code."""

    mfa_token: str
    code: str


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


class MagicLinkByPhone(BaseModel):
    """Alternative identity check for members who don't have their member ID
    handy — phone number + DOB. Phone is normalized to E.164 before lookup."""

    phone: str
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


class MedicationFillCreate(BaseModel):
    """One pharmacy dispensing row from the payer's claims feed. `drug_class` is
    the therapeutic class this platform tracks for PDC adherence — one of
    "diabetes", "rasa" (RAS-antagonist antihypertensives), or "statins"."""

    external_member_id: str
    drug_class: str
    fill_date: str  # YYYY-MM-DD
    days_supply: int
    ndc: str = ""
    drug_label: str = ""
    external_claim_id: str | None = None
    source: str = "pharmacy_claim"


class PregnancyEpisodeCreate(BaseModel):
    """A delivery episode from the payer's claims feed — the anchor for PPC.
    `delivery_date` is required; `estimated_due_date` is optional and enables
    prospective prenatal outreach when the pregnancy is known before delivery."""

    external_member_id: str
    delivery_date: str  # YYYY-MM-DD
    estimated_due_date: str = ""
    external_episode_id: str | None = None
    source: str = "claim"


class MemberExclusionCreate(BaseModel):
    """A HEDIS exclusion event from the payer's claims feed. `exclusion_code` is
    one the platform understands — a broad code (hospice, deceased,
    palliative_care) or a measure-specific one (hysterectomy, bilateral_mastectomy,
    total_colectomy, colorectal_cancer_history). `reference` is the claim/encounter
    id an auditor will ask for."""

    external_member_id: str
    exclusion_code: str
    reference: str = ""
    source: str = "claim"


class CaseNoteCreate(BaseModel):
    note: str
    note_type: str = "other"


class CareTaskCreate(BaseModel):
    title: str
    care_gap_id: str | None = None
    due_at: datetime | None = None
    sla_hours: int | None = None
    assignee_staff_id: str | None = None


class CareTaskUpdate(BaseModel):
    status: str  # done | cancelled | open


class CarePlanGoalCreate(BaseModel):
    goal_text: str
    interventions_text: str = ""
    target_date: str | None = None  # YYYY-MM-DD
    care_gap_id: str | None = None


class CarePlanGoalUpdate(BaseModel):
    status: str | None = None  # open | met | discontinued
    goal_text: str | None = None
    interventions_text: str | None = None
    target_date: str | None = None


class SafetyPlanUpsert(BaseModel):
    warning_signs: str = ""
    coping_strategies: str = ""
    support_contacts: str = ""
    means_restriction: str = ""
    notes: str = ""


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
