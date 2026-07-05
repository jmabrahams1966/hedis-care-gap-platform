"""Entrypoint for the scheduled outreach batch job.

Run as: `python -m app.scripts.run_outreach_cron`

Invoked on a schedule by EventBridge Scheduler against a dedicated ECS task
definition (see infra/modules/ecs) — not by a human, and not by the always-on
API service. Iterates every tenant and sends outreach for any care gap due for
(re)contact, using the same logic and RETRY_CADENCE_DAYS as the manual
`POST /api/outreach/run-batch` endpoint.
"""

import asyncio
import logging
import sys

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Tenant
from ..outreach_service import run_batch_for_tenant

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("outreach_cron")


async def main() -> int:
    async with SessionLocal() as db:
        tenants = (await db.execute(select(Tenant))).scalars().all()
        total_sent = 0
        for tenant in tenants:
            result = await run_batch_for_tenant(db, tenant)
            logger.info("tenant=%s evaluated=%d sent=%d", tenant.slug, result["evaluated"], result["sent"])
            total_sent += result["sent"]
        logger.info("outreach cron complete: %d tenants, %d messages sent", len(tenants), total_sent)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
