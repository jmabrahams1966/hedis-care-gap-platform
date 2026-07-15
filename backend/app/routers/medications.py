from sqlalchemy import select
from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..measures.medication_adherence import MEDICATION_ADHERENCE_MEASURES
from ..measures.pdc_service import pdc_snapshot_for_member, recompute_pdc_for_member
from ..models import DrugClass, Member, MedicationFill, StaffRole, StaffUser
from ..schemas import MedicationFillCreate

router = APIRouter(prefix="/api/medications", tags=["medications"])

_VALID_DRUG_CLASSES = {c.value for c in DrugClass}


@router.post("/fills/bulk")
async def bulk_ingest_fills(
    body: list[MedicationFillCreate],
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Ingest pharmacy fills from the payer's claims feed, then recompute PDC
    adherence gaps for every member the batch touched. A fill's `drug_class`
    must be one this platform tracks (diabetes / rasa / statins); rows for other
    classes are reported as errors rather than silently dropped."""
    members_by_external_id: dict[str, Member | None] = {}
    affected: dict[str, Member] = {}
    created = 0
    errors: list[dict] = []

    for index, item in enumerate(body):
        if item.drug_class not in _VALID_DRUG_CLASSES:
            errors.append(
                {
                    "index": index,
                    "external_member_id": item.external_member_id,
                    "error": f"Unknown drug_class '{item.drug_class}' (expected one of {sorted(_VALID_DRUG_CLASSES)})",
                }
            )
            continue
        if item.days_supply <= 0:
            errors.append(
                {"index": index, "external_member_id": item.external_member_id, "error": "days_supply must be positive"}
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
                {
                    "index": index,
                    "external_member_id": item.external_member_id,
                    "error": "Member not found for this tenant",
                }
            )
            continue

        db.add(
            MedicationFill(
                tenant_id=staff.tenant_id,
                member_id=member.id,
                drug_class=item.drug_class,
                ndc=item.ndc,
                drug_label=item.drug_label,
                fill_date=item.fill_date,
                days_supply=item.days_supply,
                external_claim_id=item.external_claim_id or None,
                source=item.source,
            )
        )
        created += 1
        affected[member.id] = member

    await db.flush()

    gaps: list[dict] = []
    for member in affected.values():
        gaps.extend(await recompute_pdc_for_member(db, member))

    await db.commit()
    return {
        "fills_created": created,
        "members_affected": len(affected),
        "gaps": gaps,
        "errors": errors,
    }


@router.get("/pdc/{external_member_id}")
async def member_pdc(
    external_member_id: str,
    staff: StaffUser = Depends(
        require_role(StaffRole.care_manager.value, StaffRole.payer_admin.value, StaffRole.super_admin.value)
    ),
    db: AsyncSession = Depends(get_db),
):
    """Current run-to-date PDC per tracked drug class for one member — what a
    care manager sees when deciding whether to intervene on adherence."""
    member = (
        await db.execute(
            select(Member).where(
                Member.tenant_id == staff.tenant_id,
                Member.external_member_id == external_member_id,
            )
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(404, "Member not found")

    snapshot = await pdc_snapshot_for_member(db, member)
    return {
        "external_member_id": external_member_id,
        "measures": {m.code: m.hedis_measure_name for m in MEDICATION_ADHERENCE_MEASURES},
        "pdc": [
            {
                "measure_code": code,
                "eligible": r.eligible,
                "pdc": r.pdc,
                "adherent": r.adherent,
                "covered_days": r.covered_days,
                "treatment_days": r.treatment_days,
                "fill_count": r.fill_count,
            }
            for code, r in snapshot
        ],
    }
