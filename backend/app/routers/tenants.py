from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..models import CareGap, GapStatus, Member, Measure, StaffRole, StaffUser, Tenant, TenantMeasureConfig
from ..schemas import MeasureToggle, TenantCreate, TenantOut
from ..security import hash_password

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


@router.get("/measures/catalog")
async def measures_catalog(
    staff: StaffUser = Depends(
        require_role(StaffRole.super_admin.value, StaffRole.payer_admin.value, StaffRole.care_manager.value)
    ),
    db: AsyncSession = Depends(get_db),
):
    """All measure modules available on the platform, and which are enabled for the
    caller's own tenant (super_admin sees the catalog with nothing pre-selected)."""
    measures = (await db.execute(select(Measure).where(Measure.active.is_(True)))).scalars().all()
    enabled_codes: set[str] = set()
    if staff.tenant_id:
        configs = (
            await db.execute(
                select(TenantMeasureConfig).where(
                    TenantMeasureConfig.tenant_id == staff.tenant_id,
                    TenantMeasureConfig.enabled.is_(True),
                )
            )
        ).scalars().all()
        enabled_codes = {c.measure_code for c in configs}

    return [
        {
            "code": m.code,
            "hedis_measure_name": m.hedis_measure_name,
            "description": m.description,
            "enabled": m.code in enabled_codes,
        }
        for m in measures
    ]


@router.get("", response_model=list[TenantOut])
async def list_tenants(
    staff: StaffUser = Depends(require_role(StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    tenants = (await db.execute(select(Tenant))).scalars().all()
    out = []
    for t in tenants:
        member_count = (
            await db.execute(select(func.count()).select_from(Member).where(Member.tenant_id == t.id))
        ).scalar_one()
        open_gaps = (
            await db.execute(
                select(func.count())
                .select_from(CareGap)
                .where(CareGap.tenant_id == t.id, CareGap.status != GapStatus.closed.value)
            )
        ).scalar_one()
        out.append(TenantOut.model_validate({**t.__dict__, "member_count": member_count, "open_gaps": open_gaps}))
    return out


@router.post("", response_model=TenantOut)
async def create_tenant(
    body: TenantCreate,
    staff: StaffUser = Depends(require_role(StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    existing = (await db.execute(select(Tenant).where(Tenant.slug == body.slug))).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Slug already in use")

    tenant = Tenant(
        slug=body.slug,
        name=body.name,
        primary_color=body.primary_color,
        support_phone=body.support_phone,
        support_email=body.support_email,
    )
    db.add(tenant)
    await db.flush()

    for code in body.enabled_measures:
        measure = await db.get(Measure, code)
        if measure is None:
            raise HTTPException(400, f"Unknown measure code: {code}")
        db.add(TenantMeasureConfig(tenant_id=tenant.id, measure_code=code, enabled=True))

    if body.first_admin_email and body.first_admin_password:
        db.add(
            StaffUser(
                tenant_id=tenant.id,
                email=body.first_admin_email,
                password_hash=hash_password(body.first_admin_password),
                role=StaffRole.payer_admin.value,
                name="Payer Admin",
            )
        )

    await db.commit()
    await db.refresh(tenant)
    return TenantOut.model_validate({**tenant.__dict__, "member_count": 0, "open_gaps": 0})


@router.put("/{tenant_id}/measures")
async def toggle_measure(
    tenant_id: str,
    body: MeasureToggle,
    staff: StaffUser = Depends(require_role(StaffRole.super_admin.value, StaffRole.payer_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    if staff.role == StaffRole.payer_admin.value and staff.tenant_id != tenant_id:
        raise HTTPException(403, "Cannot modify another tenant")

    res = await db.execute(
        select(TenantMeasureConfig).where(
            TenantMeasureConfig.tenant_id == tenant_id,
            TenantMeasureConfig.measure_code == body.measure_code,
        )
    )
    config = res.scalar_one_or_none()
    if config is None:
        config = TenantMeasureConfig(tenant_id=tenant_id, measure_code=body.measure_code)
        db.add(config)
    config.enabled = body.enabled
    config.config = body.config
    await db.commit()
    return {"measure_code": body.measure_code, "enabled": body.enabled}
