from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .measures import REGISTRY
from .measures.base import default_period
from .models import Measure, Member, StaffRole, StaffUser, Tenant, TenantMeasureConfig
from .routers.members import _alias, _open_care_gaps_for_member
from .security import hash_password

DEMO_MEMBERS = [
    # external_id, first, last, dob, sex, phone, email
    ("EXT-1001", "Alice", "Nguyen", "1988-03-14", "F", "+15550001001", "alice@example.com"),
    ("EXT-1002", "Ben", "Torres", "1975-07-02", "M", "+15550001002", "ben@example.com"),
    ("EXT-1003", "Carla", "Smith", "2006-11-30", "F", "+15550001003", "carla@example.com"),
    ("EXT-1004", "Deepak", "Rao", "1962-01-19", "M", "+15550001004", "deepak@example.com"),
    ("EXT-1005", "Elena", "Petrova", "1995-09-08", "F", "+15550001005", "elena@example.com"),
    # BCS-eligible (female, 50-74)
    ("EXT-1006", "Fatima", "Hassan", "1970-05-12", "F", "+15550001006", "fatima@example.com"),
    ("EXT-1007", "Grace", "Kim", "1955-02-20", "F", "+15550001007", "grace@example.com"),
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

    db.add(TenantMeasureConfig(tenant_id=tenant.id, measure_code="mental_health", enabled=True))
    db.add(TenantMeasureConfig(tenant_id=tenant.id, measure_code="breast_cancer", enabled=True))

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

    for external_id, first, last, dob, sex, phone, email in DEMO_MEMBERS:
        member = Member(
            tenant_id=tenant.id,
            external_member_id=external_id,
            first_name=first,
            last_name=last,
            date_of_birth=dob,
            sex=sex,
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

    await db.commit()
