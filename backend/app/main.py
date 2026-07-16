from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import SessionLocal, init_db
from .routers import (
    auth,
    care_gaps,
    care_plan,
    conversations,
    dependents,
    enrollments,
    maternity,
    medications,
    members,
    outreach,
    reports,
    safety,
    screenings,
    sequences,
    tasks,
    tenants,
    webhooks,
)
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


@app.middleware("http")
async def security_headers(request, call_next):
    """Baseline security headers on every API response. The API returns PHI-bearing
    JSON, so responses are marked no-store; framing/sniffing/referrer are locked
    down. HSTS is safe because everything is served over HTTPS (ALB/CloudFront)."""
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store"
    return response

app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(members.router)
app.include_router(dependents.router)
app.include_router(medications.router)
app.include_router(maternity.router)
app.include_router(screenings.router)
app.include_router(care_gaps.router)
app.include_router(outreach.router)
app.include_router(reports.router)
app.include_router(tasks.router)
app.include_router(care_plan.router)
app.include_router(safety.router)
app.include_router(enrollments.router)
app.include_router(sequences.router)
app.include_router(conversations.router)
app.include_router(conversations.member_router)
app.include_router(webhooks.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
