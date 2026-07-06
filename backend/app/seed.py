from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .measures import REGISTRY
from .measures.base import default_period
from .models import Dependent, Measure, Member, StaffRole, StaffUser, Tenant, TenantMeasureConfig
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
        "colorectal_cancer",
        "blood_pressure",
        "diabetes_a1c",
        "childhood_immunization",
        "well_child_visits",
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
