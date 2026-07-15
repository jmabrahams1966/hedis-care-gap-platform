from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..deps import require_role
from ..measures.ppc_service import open_ppc_gaps_for_episode
from ..models import Member, PregnancyEpisode, StaffRole, StaffUser
from ..schemas import PregnancyEpisodeCreate

router = APIRouter(prefix="/api/maternity", tags=["maternity"])


@router.post("/episodes/bulk")
async def bulk_ingest_episodes(
    body: list[PregnancyEpisodeCreate],
    staff: StaffUser = Depends(require_role(StaffRole.payer_admin.value, StaffRole.super_admin.value)),
    db: AsyncSession = Depends(get_db),
):
    """Ingest delivery episodes from the payer's claims feed and open the PPC
    (prenatal / postpartum) care gaps anchored to each delivery."""
    members_by_external_id: dict[str, Member | None] = {}
    created = 0
    gaps: list[dict] = []
    errors: list[dict] = []

    for index, item in enumerate(body):
        if not item.delivery_date:
            errors.append({"index": index, "external_member_id": item.external_member_id, "error": "delivery_date is required"})
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

        # Re-ingesting a claims feed shouldn't create duplicate episodes: if this
        # claim's episode id is already on file, reuse it (gap-opening below is
        # idempotent) rather than inserting a colliding row.
        episode = None
        if item.external_episode_id:
            episode = (
                await db.execute(
                    select(PregnancyEpisode).where(
                        PregnancyEpisode.tenant_id == staff.tenant_id,
                        PregnancyEpisode.external_episode_id == item.external_episode_id,
                    )
                )
            ).scalar_one_or_none()

        if episode is None:
            episode = PregnancyEpisode(
                tenant_id=staff.tenant_id,
                member_id=member.id,
                delivery_date=item.delivery_date,
                estimated_due_date=item.estimated_due_date,
                external_episode_id=item.external_episode_id or None,
                source=item.source,
            )
            db.add(episode)
            await db.flush()
            created += 1

        gaps.extend(await open_ppc_gaps_for_episode(db, member, episode))

    await db.commit()
    return {"episodes_created": created, "gaps": gaps, "errors": errors}
