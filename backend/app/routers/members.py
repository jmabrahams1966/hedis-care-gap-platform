import csv
import hashlib
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..measures import REGISTRY
from ..models import CareGap, Dependent, Member, StaffRole, StaffUser, TenantMeasureConfig
from ..measures.base import default_period
from ..schemas import MemberCreate, MemberOut

router = APIRouter(prefix="/api/members", tags=["members"])


def _alias(tenant_id: str, external_id: str, *, prefix: str = "Member") -> str:
    digest = hashlib.sha256(f"{tenant_id}:{external_id}".encode()).hexdigest()[:6].upper()
    return f"{prefix}-{digest}"


async def _enabled_measure_configs(db: AsyncSession, tenant_id: str) -> list[TenantMeasureConfig]:
    return (
        await db.execute(
            select(TenantMeasureConfig).where(
                TenantMeasureConfig.tenant_id == tenant_id,
                TenantMeasureConfig.enabled.is_(True),
            )
        )
    ).scalars().all()


async def _open_care_gaps_for_member(db: AsyncSession, member: Member) -> None:
    """Evaluate every member-scoped measure enabled for the member's tenant and
    open a CareGap row for the current period if the member is eligible and
    doesn't have one yet. Dependent-scoped measures (pediatric) are handled by
    _open_care_gaps_for_dependent instead — a member is never their own
    dependent-measure subject."""
    configs = await _enabled_measure_configs(db, member.tenant_id)
    period = default_period()
    for config in configs:
        measure = REGISTRY.get(config.measure_code)
        if measure is None or measure.subject_type != "member":
            continue
        if not measure.is_eligible(member, date.today()):
            continue
        existing = (
            await db.execute(
                select(CareGap).where(
                    CareGap.member_id == member.id,
                    CareGap.dependent_id.is_(None),
                    CareGap.measure_code == config.measure_code,
                    CareGap.period == period,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                CareGap(
                    tenant_id=member.tenant_id,
                    member_id=member.id,
                    measure_code=config.measure_code,
                    period=period,
                )
            )


async def _open_care_gaps_for_dependent(db: AsyncSession, dependent: Dependent) -> None:
    """Same as _open_care_gaps_for_member, but for dependent-scoped (pediatric)
    measures. The resulting CareGap keeps member_id = the guardian (who
    receives outreach and submits on the dependent's behalf) alongside
    dependent_id = the actual subject of the measure."""
    configs = await _enabled_measure_configs(db, dependent.tenant_id)
    period = default_period()
    for config in configs:
        measure = REGISTRY.get(config.measure_code)
        if measure is None or measure.subject_type != "dependent":
            continue
        if not measure.is_eligible(dependent, date.today()):
            continue
        existing = (
            await db.execute(
                select(CareGap).where(
                    CareGap.dependent_id == dependent.id,
                    CareGap.measure_code == config.measure_code,
                    CareGap.period == period,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                CareGap(
                    tenant_id=dependent.tenant_id,
                    member_id=dependent.guardian_member_id,
                    dependent_id=dependent.id,
                    measure_code=config.measure_code,
                    period=period,
                )
            )


async def _create_member(db: AsyncSession, tenant_id: str, item: MemberCreate) -> Member:
    member = Member(
        tenant_id=tenant_id,
        external_member_id=item.external_member_id,
        first_name=item.first_name,
        last_name=item.last_name,
        date_of_birth=item.date_of_birth,
        sex=item.sex,
        conditions=item.conditions,
        phone=item.phone,
        email=item.email,
        preferred_channel=item.preferred_channel,
        preferred_language=item.preferred_language,
        consent_sms=item.consent_sms,
        consent_email=item.consent_email,
    )
    member.alias = _alias(tenant_id, item.external_member_id)
    db.add(member)
    await db.flush()
    await _open_care_gaps_for_member(db, member)
    return member


@router.post("", response_model=MemberOut)
async def create_member(
    body: MemberCreate,
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    if staff.role != StaffRole.super_admin.value and staff.tenant_id is None:
        raise HTTPException(403, "Staff user has no tenant")

    member = await _create_member(db, staff.tenant_id, body)
    await db.commit()
    await db.refresh(member)
    return member


@router.post("/bulk", response_model=list[MemberOut])
async def bulk_create_members(
    body: list[MemberCreate],
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Roster ingestion endpoint — accepts a batch from the payer's eligibility feed."""
    created = [await _create_member(db, staff.tenant_id, item) for item in body]
    await db.commit()
    for member in created:
        await db.refresh(member)
    return created


CSV_BOOL_TRUE = {"1", "true", "yes", "y"}


@router.post("/bulk-csv")
async def bulk_create_members_csv(
    file: UploadFile,
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Roster ingestion from a CSV eligibility feed. Expected columns:
    external_member_id, first_name, last_name, date_of_birth (YYYY-MM-DD), sex (F/M/U),
    conditions (pipe-separated, e.g. "hypertension|diabetes"), phone, email,
    preferred_channel (sms/email), preferred_language, consent_sms, consent_email
    (consent columns accept 1/true/yes as truthy). Unknown/missing optional columns fall back
    to MemberCreate's defaults.
    """
    raw = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(raw))

    created: list[Member] = []
    errors: list[dict] = []
    for row_num, row in enumerate(reader, start=2):  # header is row 1
        row = {k: (v or "").strip() for k, v in row.items()}
        for bool_field in ("consent_sms", "consent_email"):
            if bool_field in row:
                row[bool_field] = row[bool_field].lower() in CSV_BOOL_TRUE
        if "conditions" in row:
            row["conditions"] = [c.strip() for c in row["conditions"].split("|") if c.strip()]
        row = {
            k: v
            for k, v in row.items()
            if v != "" or k in ("consent_sms", "consent_email", "conditions")
        }
        try:
            item = MemberCreate(**row)
        except ValidationError as e:
            errors.append({"row": row_num, "external_member_id": row.get("external_member_id", ""), "error": str(e)})
            continue
        created.append(await _create_member(db, staff.tenant_id, item))

    await db.commit()
    for member in created:
        await db.refresh(member)

    return {
        "created": len(created),
        "errors": errors,
        "members": [MemberOut.model_validate(m) for m in created],
    }


@router.get("", response_model=list[MemberOut])
async def list_members(
    staff: StaffUser = Depends(
        require_role(StaffRole.payer_admin.value, StaffRole.care_manager.value, StaffRole.super_admin.value)
    ),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(select(Member).where(Member.tenant_id == staff.tenant_id))
    return res.scalars().all()
