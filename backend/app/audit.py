from sqlalchemy.ext.asyncio import AsyncSession

from .audit_archive import archive_event
from .models import AuditLog


async def log_action(
    db: AsyncSession,
    *,
    actor_type: str,
    actor_id: str = "",
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    tenant_id: str | None = None,
    ip_address: str = "",
    metadata: dict | None = None,
) -> None:
    """Append-only audit trail. Called on every access to or mutation of PHI-adjacent
    resources (member records, screenings, care gaps) per docs/SECURITY_HIPAA.md.
    After committing to the database, the event is mirrored (best-effort) to a
    write-once S3 archive so the trail survives an application-level compromise."""
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        metadata_json=metadata or {},
    )
    db.add(entry)
    await db.commit()

    await archive_event(
        {
            "id": entry.id,
            "tenant_id": entry.tenant_id,
            "actor_type": entry.actor_type,
            "actor_id": entry.actor_id,
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "ip_address": entry.ip_address,
            "metadata": entry.metadata_json,
            "created_at": entry.created_at,
        }
    )
