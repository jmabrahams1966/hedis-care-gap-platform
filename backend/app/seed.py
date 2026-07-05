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
    ("EXT-1001", "Alice", "Nguyen", "1988-03-14", "+15550001001", "alice@example.com"),
    ("EXT-1002", "Ben", "Torres", "1975-07-02", "+15550001002", "ben@example.com"),
    ("EXT-1003", "Carla", "Smith", "2006-11-30", "+15550001003", "carla@example.com"),
    ("EXT-1004", "Deepak", "Rao", "1962-01-19", "+15550001004", "deepak@example.com"),
    ("EXT-1005", "Elena", "Petrova", "1995-09-08", "+15550001005", "elena@example.com"),
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

    for external_id, first, last, dob, phone, email in DEMO_MEMBERS:
        member = Member(
            tenant_id=tenant.id,
            external_member_id=external_id,
            first_name=first,
            last_name=last,
            date_of_birth=dob,
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
