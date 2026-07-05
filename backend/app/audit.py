from sqlalchemy.ext.asyncio import AsyncSession

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
    resources (member records, screenings, care gaps) per docs/SECURITY_HIPAA.md."""
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=ip_address,
            metadata_json=metadata or {},
        )
    )
    await db.commit()
