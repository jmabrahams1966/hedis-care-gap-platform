import datetime
import uuid
from datetime import date

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditLog, Member, StaffRole, StaffUser
from app.notifications import sns_verify
from app.notifications.sns_verify import _canonical_string
from app.security import hash_password


async def _make_super_admin() -> tuple[str, str]:
    email = f"super-{uuid.uuid4().hex[:8]}@example.com"
    password = "test-password-123"
    async with SessionLocal() as db:
        db.add(
            StaffUser(
                tenant_id=None,
                email=email,
                password_hash=hash_password(password),
                role=StaffRole.super_admin.value,
                name="Test Super Admin",
            )
        )
        await db.commit()
    return email, password


async def _login(client: AsyncClient, email: str, password: str) -> str:
    res = await client.post("/api/auth/staff/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["token"]


def _auth(token: str) -> dict:
    return {"authorization": f"Bearer {token}"}


@pytest.fixture
def signing_keypair(monkeypatch):
    """Self-signed keypair standing in for AWS's real SNS signing cert, wired
    up so the webhook's default cert fetcher returns it instead of hitting
    the network — the trusted-host check still runs against the real regex."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "sns.amazonaws.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    monkeypatch.setattr(sns_verify, "_default_cert_fetcher", lambda url: cert_pem)
    return private_key


def _sign(private_key, envelope: dict) -> dict:
    message = _canonical_string(envelope).encode("utf-8")
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())
    envelope = dict(envelope)
    envelope["Signature"] = base64_encode(signature)
    return envelope


def base64_encode(raw: bytes) -> str:
    import base64

    return base64.b64encode(raw).decode("ascii")


async def _create_tenant_and_member(client: AsyncClient, phone: str) -> str:
    sa_email, sa_password = await _make_super_admin()
    sa_token = await _login(client, sa_email, sa_password)

    slug = f"webhook-{uuid.uuid4().hex[:8]}"
    admin_email = f"admin-{uuid.uuid4().hex[:8]}@example.com"
    res = await client.post(
        "/api/tenants",
        json={
            "slug": slug,
            "name": "Webhook Test Plan",
            "enabled_measures": ["mental_health"],
            "first_admin_email": admin_email,
            "first_admin_password": "admin-password-123",
        },
        headers=_auth(sa_token),
    )
    assert res.status_code == 200, res.text

    pa_token = await _login(client, admin_email, "admin-password-123")

    this_year = date.today().year
    res = await client.post(
        "/api/members",
        json={
            "external_member_id": f"EXT-{uuid.uuid4().hex[:8]}",
            "first_name": "Webhook",
            "last_name": "Test",
            "date_of_birth": f"{this_year - 40}-01-01",
            "sex": "F",
            "phone": phone,
            "consent_sms": True,
        },
        headers=_auth(pa_token),
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


@pytest.mark.asyncio
async def test_stop_keyword_revokes_sms_consent(client: AsyncClient, signing_keypair):
    phone = "+15559990001"
    member_id = await _create_tenant_and_member(client, phone)

    envelope = {
        "Type": "Notification",
        "MessageId": "msg-stop-1",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "Message": f'{{"originationNumber": "{phone}", "messageBody": "STOP"}}',
        "Timestamp": "2026-01-01T00:00:00.000Z",
        "SignatureVersion": "1",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/fake-cert.pem",
    }
    signed = _sign(signing_keypair, envelope)

    res = await client.post("/api/webhooks/sms-inbound", json=signed)
    assert res.status_code == 200, res.text
    assert res.json() == {"status": "opted_out"}

    async with SessionLocal() as db:
        member = await db.get(Member, member_id)
        assert member.consent_sms is False
        assert member.consent_recorded_at is not None

        audit = (
            await db.execute(select(AuditLog).where(AuditLog.action == "sms_opt_out", AuditLog.resource_id == member_id))
        ).scalar_one_or_none()
        assert audit is not None
        assert audit.metadata_json == {"keyword": "STOP"}


@pytest.mark.asyncio
async def test_start_keyword_restores_sms_consent(client: AsyncClient, signing_keypair):
    phone = "+15559990002"
    member_id = await _create_tenant_and_member(client, phone)

    async def _send(keyword: str):
        envelope = {
            "Type": "Notification",
            "MessageId": f"msg-{keyword}",
            "TopicArn": "arn:aws:sns:us-east-1:123456789012:test-topic",
            "Message": f'{{"originationNumber": "{phone}", "messageBody": "{keyword}"}}',
            "Timestamp": "2026-01-01T00:00:00.000Z",
            "SignatureVersion": "1",
            "SigningCertURL": "https://sns.us-east-1.amazonaws.com/fake-cert.pem",
        }
        signed = _sign(signing_keypair, envelope)
        return await client.post("/api/webhooks/sms-inbound", json=signed)

    res = await _send("STOP")
    assert res.json() == {"status": "opted_out"}

    res = await _send("START")
    assert res.json() == {"status": "opted_in"}

    async with SessionLocal() as db:
        member = await db.get(Member, member_id)
        assert member.consent_sms is True

        audit = (
            await db.execute(select(AuditLog).where(AuditLog.action == "sms_opt_in", AuditLog.resource_id == member_id))
        ).scalar_one_or_none()
        assert audit is not None


@pytest.mark.asyncio
async def test_unsigned_notification_is_rejected(client: AsyncClient, signing_keypair):
    envelope = {
        "Type": "Notification",
        "MessageId": "msg-forged",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "Message": '{"originationNumber": "+15559990003", "messageBody": "STOP"}',
        "Timestamp": "2026-01-01T00:00:00.000Z",
        "SignatureVersion": "1",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/fake-cert.pem",
        "Signature": base64_encode(b"not-a-real-signature-but-plausible-length-000000"),
    }
    res = await client.post("/api/webhooks/sms-inbound", json=envelope)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_subscription_confirmation_is_confirmed(client: AsyncClient, signing_keypair):
    seen = []
    import app.routers.webhooks as webhooks_module

    envelope = {
        "Type": "SubscriptionConfirmation",
        "MessageId": "msg-sub-1",
        "Token": "test-token",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "Message": "You have chosen to subscribe...",
        "SubscribeURL": "https://sns.us-east-1.amazonaws.com/confirm",
        "Timestamp": "2026-01-01T00:00:00.000Z",
        "SignatureVersion": "1",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/fake-cert.pem",
    }
    signed = _sign(signing_keypair, envelope)

    orig_confirm = webhooks_module.confirm_subscription
    webhooks_module.confirm_subscription = lambda url: seen.append(url)
    try:
        res = await client.post("/api/webhooks/sms-inbound", json=signed)
    finally:
        webhooks_module.confirm_subscription = orig_confirm

    assert res.status_code == 200, res.text
    assert res.json() == {"status": "subscribed"}
    assert seen == ["https://sns.us-east-1.amazonaws.com/confirm"]
