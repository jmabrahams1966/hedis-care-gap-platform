from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .measures import REGISTRY
from .measures.base import default_period
from .measures.exclusions import apply_exclusions_for_member
from .measures.pdc_service import recompute_pdc_for_member
from .measures.ppc_service import open_ppc_gaps_for_episode
from .models import (
    Dependent,
    Measure,
    Member,
    MedicationFill,
    MemberExclusion,
    PregnancyEpisode,
    StaffRole,
    StaffUser,
    Tenant,
    TenantMeasureConfig,
)
from .routers.members import _alias, _open_care_gaps_for_dependent, _open_care_gaps_for_member
from .security import hash_password

DEMO_MEMBERS = [
    # external_id, first, last, dob, sex, conditions, phone, email
    ("EXT-1001", "Alice", "Nguyen", "1988-03-14", "F", [], "+15550001001", "alice@example.com"),
    ("EXT-1002", "Ben", "Torres", "1975-07-02", "M", ["hypertension"], "+15550001002", "ben@example.com"),
    ("EXT-1003", "Carla", "Smith", "2006-11-30", "F", [], "+15550001003", "carla@example.com"),
    ("EXT-1004", "Deepak", "Rao", "1962-01-19", "M", ["hypertension", "diabetes"], "+15550001004", "deepak@example.com"),
    ("EXT-1005", "Elena", "Petrova", "1995-09-08", "F", [], "+15550001005", "elena@example.com"),
    # BCS/COL-eligible (female, 50-74)
    ("EXT-1006", "Fatima", "Hassan", "1970-05-12", "F", ["diabetes"], "+15550001006", "fatima@example.com"),
    ("EXT-1007", "Grace", "Kim", "1955-02-20", "F", ["hypertension"], "+15550001007", "grace@example.com"),
]

# guardian_external_id, external_dependent_id, first, last, age_years, sex
# age_years (not a fixed dob) so eligibility doesn't drift out of range as time passes
DEMO_DEPENDENTS = [
    ("EXT-1001", "DEP-1001", "Mia", "Nguyen", 2, "F"),  # CIS-eligible
    ("EXT-1005", "DEP-1002", "Leo", "Petrova", 8, "M"),  # WCV-eligible
]


async def ensure_measure_catalog(db: AsyncSession) -> None:
    for code, measure in REGISTRY.items():
        existing = await db.get(Measure, code)
        if existing is None:
            db.add(Measure(code=code, hedis_measure_name=measure.hedis_measure_name, description=measure.description))
    await db.commit()


async def _seed_demo_fills(db: AsyncSession, member: Member | None) -> None:
    """Give one demo member a realistic pharmacy-fill history so both a passing
    (adherent) and a failing (non-adherent) PDC gap show up in dev, then run the
    PDC recompute to open/score those gaps."""
    if member is None:
        return

    today = date.today()

    def _fill(drug_class: str, label: str, fill_date: date, days_supply: int, seq: int) -> MedicationFill:
        return MedicationFill(
            tenant_id=member.tenant_id,
            member_id=member.id,
            drug_class=drug_class,
            drug_label=label,
            fill_date=fill_date.isoformat(),
            days_supply=days_supply,
            external_claim_id=f"DEMO-RX-{member.external_member_id}-{drug_class}-{seq}",
            source="demo",
        )

    # Diabetes: refilled roughly monthly for the last ~6 months → adherent.
    for i in range(6):
        db.add(_fill("diabetes", "Metformin 500mg", today - timedelta(days=32 * (i + 1)), 32, i))
    # Hypertension (RAS antagonist): two early fills, then a long gap → non-adherent.
    db.add(_fill("rasa", "Lisinopril 10mg", today - timedelta(days=170), 30, 0))
    db.add(_fill("rasa", "Lisinopril 10mg", today - timedelta(days=140), 30, 1))

    await db.flush()
    await recompute_pdc_for_member(db, member)


async def _seed_demo_episode(db: AsyncSession, member: Member | None) -> None:
    """Give one demo member a recent delivery episode so the PPC gaps show up in
    dev with the postpartum visit in its actionable window."""
    if member is None:
        return
    delivery = date.today() - timedelta(days=30)
    episode = PregnancyEpisode(
        tenant_id=member.tenant_id,
        member_id=member.id,
        delivery_date=delivery.isoformat(),
        external_episode_id=f"DEMO-DELIVERY-{member.external_member_id}",
        source="demo",
    )
    db.add(episode)
    await db.flush()
    await open_ppc_gaps_for_episode(db, member, episode)


async def _seed_demo_exclusion(db: AsyncSession, member: Member | None, exclusion_code: str) -> None:
    """Put a HEDIS exclusion on file for a member and re-apply it so their
    relevant open gap is marked excluded (out of the denominator) in dev."""
    if member is None:
        return
    db.add(
        MemberExclusion(
            tenant_id=member.tenant_id,
            member_id=member.id,
            exclusion_code=exclusion_code,
            reference=f"DEMO-EXCL-{member.external_member_id}",
            source="demo",
        )
    )
    await db.flush()
    await apply_exclusions_for_member(db, member)


async def seed_demo_tenant(db: AsyncSession) -> None:
    if not settings.dev_mode:
        return

    existing = (
        await db.execute(select(Tenant).where(Tenant.slug == settings.default_tenant_slug))
    ).scalar_one_or_none()
    if existing is not None:
        return

    tenant = Tenant(slug=settings.default_tenant_slug, name="Demo Health Plan", primary_color="#0d6efd")
    db.add(tenant)
    await db.flush()

    for measure_code in (
        "mental_health",
        "breast_cancer",
        "cervical_cancer",
        "colorectal_cancer",
        "blood_pressure",
        "diabetes_a1c",
        "eye_exam",
        "kidney_health",
        "childhood_immunization",
        "well_child_visits",
        "pdc_diabetes",
        "pdc_hypertension",
        "pdc_statins",
        "ppc_prenatal",
        "ppc_postpartum",
    ):
        db.add(TenantMeasureConfig(tenant_id=tenant.id, measure_code=measure_code, enabled=True))

    db.add(
        StaffUser(
            tenant_id=None,
            email="superadmin@example.com",
            password_hash=hash_password("changeme123"),
            role=StaffRole.super_admin.value,
            name="Platform Super Admin",
        )
    )
    db.add(
        StaffUser(
            tenant_id=tenant.id,
            email="admin@demo-plan.example.com",
            password_hash=hash_password("changeme123"),
            role=StaffRole.payer_admin.value,
            name="Demo Payer Admin",
        )
    )
    db.add(
        StaffUser(
            tenant_id=tenant.id,
            email="care-manager@demo-plan.example.com",
            password_hash=hash_password("changeme123"),
            role=StaffRole.care_manager.value,
            name="Demo Care Manager",
        )
    )
    await db.flush()

    members_by_external_id: dict[str, Member] = {}
    for external_id, first, last, dob, sex, conditions, phone, email in DEMO_MEMBERS:
        member = Member(
            tenant_id=tenant.id,
            external_member_id=external_id,
            first_name=first,
            last_name=last,
            date_of_birth=dob,
            sex=sex,
            conditions=conditions,
            phone=phone,
            email=email,
            preferred_channel="sms",
            preferred_language="en",
            consent_sms=True,
            consent_email=True,
        )
        member.alias = _alias(tenant.id, external_id)
        db.add(member)
        await db.flush()
        await _open_care_gaps_for_member(db, member)
        members_by_external_id[external_id] = member

    # Demo pharmacy fills so the PDC adherence measures show real gaps in dev:
    # Deepak (EXT-1004, diabetes + hypertension) is adherent on his diabetes meds
    # (a monthly refill history → completed gap) but has fallen off his blood-
    # pressure meds (two early fills, then nothing → open gap for refill outreach).
    # Assumes a mid-year-or-later run so the dates land in the past.
    await _seed_demo_fills(db, members_by_external_id.get("EXT-1004"))

    # Elena (EXT-1005, F) delivered ~30 days ago → open PPC gaps, with the
    # postpartum visit currently in its actionable 7–84 day window.
    await _seed_demo_episode(db, members_by_external_id.get("EXT-1005"))

    # Fatima (EXT-1006, F, ~56) has a hysterectomy on file → her cervical
    # screening gap should drop out of the denominator as excluded.
    await _seed_demo_exclusion(db, members_by_external_id.get("EXT-1006"), "hysterectomy")

    today = date.today()
    for guardian_external_id, external_dependent_id, first, last, age_years, sex in DEMO_DEPENDENTS:
        dob = f"{today.year - age_years}-{today.month:02d}-{today.day:02d}"
        guardian = members_by_external_id[guardian_external_id]
        dependent = Dependent(
            tenant_id=tenant.id,
            guardian_member_id=guardian.id,
            external_dependent_id=external_dependent_id,
            first_name=first,
            last_name=last,
            date_of_birth=dob,
            sex=sex,
        )
        dependent.alias = _alias(tenant.id, external_dependent_id, prefix="Dependent")
        db.add(dependent)
        await db.flush()
        await _open_care_gaps_for_dependent(db, dependent)

    await db.commit()
