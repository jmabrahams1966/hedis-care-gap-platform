import base64
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from app.notifications.sns_verify import _canonical_string, confirm_subscription, verify_sns_signature


@pytest.fixture(scope="module")
def keypair():
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
    return private_key, cert_pem


def _signed_envelope(keypair, **overrides) -> dict:
    private_key, _ = keypair
    envelope = {
        "Type": "Notification",
        "MessageId": "test-message-id",
        "TopicArn": "arn:aws:sns:us-east-1:123456789012:test-topic",
        "Message": '{"originationNumber": "+15550001001", "messageBody": "STOP"}',
        "Timestamp": "2026-01-01T00:00:00.000Z",
        "SignatureVersion": "1",
        "SigningCertURL": "https://sns.us-east-1.amazonaws.com/fake-cert.pem",
    }
    envelope.update(overrides)

    message = _canonical_string(envelope).encode("utf-8")
    signature = private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())
    envelope["Signature"] = base64.b64encode(signature).decode("ascii")
    return envelope


def test_valid_signature_is_accepted(keypair):
    _, cert_pem = keypair
    envelope = _signed_envelope(keypair)
    assert verify_sns_signature(envelope, cert_fetcher=lambda url: cert_pem) is True


def test_tampered_message_is_rejected(keypair):
    _, cert_pem = keypair
    envelope = _signed_envelope(keypair)
    envelope["Message"] = '{"originationNumber": "+15550001001", "messageBody": "START"}'
    assert verify_sns_signature(envelope, cert_fetcher=lambda url: cert_pem) is False


def test_tampered_signature_is_rejected(keypair):
    _, cert_pem = keypair
    envelope = _signed_envelope(keypair)
    envelope["Signature"] = base64.b64encode(b"not-a-real-signature-but-right-length-ish-00000").decode("ascii")
    assert verify_sns_signature(envelope, cert_fetcher=lambda url: cert_pem) is False


def test_wrong_signing_key_is_rejected(keypair):
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_cert_pem = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "attacker")]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "attacker")]))
        .public_key(other_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
        .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
        .sign(other_private_key, hashes.SHA256())
        .public_bytes(serialization.Encoding.PEM)
    )
    envelope = _signed_envelope(keypair)  # signed by the "real" key
    # verifier fetches the attacker's cert instead of the real signer's — must fail
    assert verify_sns_signature(envelope, cert_fetcher=lambda url: other_cert_pem) is False


def test_untrusted_cert_host_rejected_without_fetching(keypair):
    envelope = _signed_envelope(keypair, SigningCertURL="https://evil.example.com/fake-cert.pem")

    def _boom(url):
        raise AssertionError("must not fetch from an untrusted host")

    assert verify_sns_signature(envelope, cert_fetcher=_boom) is False


def test_confirm_subscription_rejects_untrusted_host():
    with pytest.raises(ValueError):
        confirm_subscription("https://evil.example.com/subscribe", fetcher=lambda url: b"")


def test_confirm_subscription_fetches_trusted_url():
    seen = []
    confirm_subscription("https://sns.us-east-1.amazonaws.com/confirm", fetcher=lambda url: seen.append(url) or b"")
    assert seen == ["https://sns.us-east-1.amazonaws.com/confirm"]
