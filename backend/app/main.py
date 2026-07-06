from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, init_db
from .routers import auth, care_gaps, dependents, members, outreach, reports, screenings, tenants, webhooks
from .seed import ensure_measure_catalog, seed_demo_tenant


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as db:
        await ensure_measure_catalog(db)
        await seed_demo_tenant(db)
    yield


app = FastAPI(title="HEDIS Care Gap Platform", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(members.router)
app.include_router(dependents.router)
app.include_router(screenings.router)
app.include_router(care_gaps.router)
app.include_router(outreach.router)
app.include_router(reports.router)
app.include_router(webhooks.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
