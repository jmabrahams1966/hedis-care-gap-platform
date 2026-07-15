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
from ..measures.base import default_period
from ..measures.exclusions import (
    all_known_exclusion_codes,
    apply_exclusions_for_member,
    is_excluded,
    member_exclusion_codes,
)
from ..models import CareGap, Dependent, Member, MemberExclusion, StaffRole, StaffUser, TenantMeasureConfig
from ..schemas import (
    DependentCreate,
    DependentOut,
    MemberCreate,
    MemberExclusionCreate,
    MemberOut,
)

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
    exclusion_codes = await member_exclusion_codes(db, member.id)
    for config in configs:
        measure = REGISTRY.get(config.measure_code)
        if measure is None or measure.subject_type != "member" or measure.data_driven:
            # data_driven measures (PDC adherence) aren't opened from demographics —
            # they're opened from ingested pharmacy fills (see pdc_service).
            continue
        if not measure.is_eligible(member, date.today()):
            continue
        if is_excluded(exclusion_codes, measure):
            # A member with a qualifying HEDIS exclusion isn't in the denominator,
            # so don't open a gap to chase.
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


async def _create_dependent(db: AsyncSession, guardian: Member, item: DependentCreate) -> Dependent:
    dependent = Dependent(
        tenant_id=guardian.tenant_id,
        guardian_member_id=guardian.id,
        external_dependent_id=item.external_dependent_id,
        first_name=item.first_name,
        last_name=item.last_name,
        date_of_birth=item.date_of_birth,
        sex=item.sex,
    )
    dependent.alias = _alias(guardian.tenant_id, item.external_dependent_id, prefix="Dependent")
    db.add(dependent)
    await db.flush()
    await _open_care_gaps_for_dependent(db, dependent)
    return dependent


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
    """Roster ingestion from a CSV eligibility feed — one file can carry a whole
    family: subscriber rows and their dependents together, matching how a real
    payer eligibility feed is usually structured. Expected columns:

    external_member_id, external_dependent_id, guardian_external_member_id,
    first_name, last_name, date_of_birth (YYYY-MM-DD), sex (F/M/U),
    conditions (pipe-separated, e.g. "hypertension|diabetes"), phone, email,
    preferred_channel (sms/email), preferred_language, consent_sms, consent_email
    (consent columns accept 1/true/yes as truthy).

    A row is a **dependent** row if `guardian_external_member_id` is set — in
    that case `external_dependent_id`/`first_name`/`last_name`/`date_of_birth`/
    `sex` are used (conditions/phone/email/consent/etc. don't apply to
    dependents and are ignored) and the guardian is looked up by
    `guardian_external_member_id`, either from a member row earlier in this
    same file or from a member already on file from a previous upload.
    Otherwise it's a regular **member** row, same as before. Dependent rows
    are processed after all member rows, so ordering within the file doesn't
    matter — the guardian doesn't need to appear before their dependents.
    """
    raw = (await file.read()).decode("utf-8-sig")
    rows = [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(io.StringIO(raw))]

    member_rows = []
    dependent_rows = []
    for row_num, row in enumerate(rows, start=2):  # header is row 1
        (dependent_rows if row.get("guardian_external_member_id") else member_rows).append((row_num, row))

    created_members: list[Member] = []
    created_dependents: list[Dependent] = []
    errors: list[dict] = []
    members_by_external_id: dict[str, Member] = {}

    for row_num, row in member_rows:
        parsed = {k: v for k, v in row.items() if k not in ("guardian_external_member_id", "external_dependent_id")}
        for bool_field in ("consent_sms", "consent_email"):
            if bool_field in parsed:
                parsed[bool_field] = parsed[bool_field].lower() in CSV_BOOL_TRUE
        if "conditions" in parsed:
            parsed["conditions"] = [c.strip() for c in parsed["conditions"].split("|") if c.strip()]
        parsed = {k: v for k, v in parsed.items() if v != "" or k in ("consent_sms", "consent_email", "conditions")}
        try:
            item = MemberCreate(**parsed)
        except ValidationError as e:
            errors.append({"row": row_num, "type": "member", "external_id": row.get("external_member_id", ""), "error": str(e)})
            continue
        member = await _create_member(db, staff.tenant_id, item)
        created_members.append(member)
        members_by_external_id[item.external_member_id] = member

    for row_num, row in dependent_rows:
        guardian_external_id = row["guardian_external_member_id"]
        guardian = members_by_external_id.get(guardian_external_id)
        if guardian is None:
            guardian = (
                await db.execute(
                    select(Member).where(
                        Member.tenant_id == staff.tenant_id, Member.external_member_id == guardian_external_id
                    )
                )
            ).scalar_one_or_none()
        if guardian is None:
            errors.append(
                {
                    "row": row_num,
                    "type": "dependent",
                    "external_id": row.get("external_dependent_id", ""),
                    "error": f"Guardian '{guardian_external_id}' not found (add them in this file or an earlier upload)",
                }
            )
            continue

        parsed = {
            "external_dependent_id": row.get("external_dependent_id", ""),
            "first_name": row.get("first_name", ""),
            "last_name": row.get("last_name", ""),
            "date_of_birth": row.get("date_of_birth", ""),
            "sex": row.get("sex") or "U",
        }
        try:
            item = DependentCreate(**parsed)
        except ValidationError as e:
            errors.append({"row": row_num, "type": "dependent", "external_id": parsed["external_dependent_id"], "error": str(e)})
            continue
        created_dependents.append(await _create_dependent(db, guardian, item))

    await db.commit()
    for member in created_members:
        await db.refresh(member)
    for dependent in created_dependents:
        await db.refresh(dependent)

    return {
        "members_created": len(created_members),
        "dependents_created": len(created_dependents),
        "errors": errors,
        "members": [MemberOut.model_validate(m) for m in created_members],
        "dependents": [DependentOut.model_validate(d) for d in created_dependents],
    }


@router.post("/exclusions/bulk")
async def bulk_ingest_exclusions(
    body: list[MemberExclusionCreate],
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Ingest HEDIS exclusion events from the payer's claims feed, then re-apply
    exclusions so any affected open care gaps drop out of the denominator.
    Unknown exclusion codes are reported as errors (an unrecognized code would
    silently exclude nothing)."""
    known = all_known_exclusion_codes()
    members_by_external_id: dict[str, Member | None] = {}
    affected: dict[str, Member] = {}
    created = 0
    errors: list[dict] = []

    for index, item in enumerate(body):
        if item.exclusion_code not in known:
            errors.append(
                {"index": index, "external_member_id": item.external_member_id,
                 "error": f"Unknown exclusion_code '{item.exclusion_code}' (known: {sorted(known)})"}
            )
            continue

        if item.external_member_id not in members_by_external_id:
            members_by_external_id[item.external_member_id] = (
                await db.execute(
                    select(Member).where(
                        Member.tenant_id == staff.tenant_id,
                        Member.external_member_id == item.external_member_id,
                    )
                )
            ).scalar_one_or_none()
        member = members_by_external_id[item.external_member_id]
        if member is None:
            errors.append(
                {"index": index, "external_member_id": item.external_member_id, "error": "Member not found for this tenant"}
            )
            continue

        # Idempotent: one row per (member, code).
        existing = (
            await db.execute(
                select(MemberExclusion).where(
                    MemberExclusion.member_id == member.id,
                    MemberExclusion.exclusion_code == item.exclusion_code,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                MemberExclusion(
                    tenant_id=staff.tenant_id,
                    member_id=member.id,
                    exclusion_code=item.exclusion_code,
                    reference=item.reference,
                    source=item.source,
                )
            )
            created += 1
        affected[member.id] = member

    await db.flush()

    gaps_excluded = 0
    for member in affected.values():
        gaps_excluded += await apply_exclusions_for_member(db, member)

    await db.commit()
    return {
        "exclusions_created": created,
        "members_affected": len(affected),
        "gaps_excluded": gaps_excluded,
        "errors": errors,
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
