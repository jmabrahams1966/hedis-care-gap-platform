"""Best-effort mirror of each audit event to a write-once (S3 Object Lock)
bucket, so an application- or database-level compromise can't erase the trail —
see docs/SECURITY_HIPAA.md §4. The database `AuditLog` row is the primary
record; this is a tamper-evident second copy. Failures here never break the
request that produced the event.
"""

import asyncio
import json
import logging

import boto3

from .config import settings

log = logging.getLogger(__name__)

_client = None


def _s3():
    global _client
    if _client is None:
        _client = boto3.client("s3", region_name=settings.aws_region)
    return _client


def _put(event: dict) -> None:
    bucket = settings.audit_archive_bucket
    if not bucket:
        return  # disabled (dev/test, or before the bucket is provisioned)
    created = str(event.get("created_at") or "")
    # Key sorts chronologically and is unique per event; date prefix keeps
    # listings/lifecycle manageable.
    date_prefix = created[:10].replace("-", "/") or "undated"
    key = f"{event.get('tenant_id') or 'system'}/{date_prefix}/{created[11:]}-{event['id']}.json"
    _s3().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(event, default=str).encode(),
        ContentType="application/json",
    )


async def archive_event(event: dict) -> None:
    """Append the event to the WORM bucket off the event loop. Best-effort:
    swallows all errors (the DB copy already committed)."""
    if not settings.audit_archive_bucket:
        return
    try:
        await asyncio.to_thread(_put, event)
    except Exception:
        log.exception("audit archive to S3 failed; event %s remains in the DB only", event.get("id"))
