"""AWS SNS message signature verification, for the inbound SMS webhook.

SNS signs every notification/subscription-confirmation it POSTs to an HTTPS
endpoint. Verifying that signature is the only thing standing between this
webhook and anyone on the internet being able to flip a member's SMS consent
by POSTing a forged "STOP" — so this is real cryptographic verification, not
a stub, even though it can't be exercised against live AWS from this repo.
See https://docs.aws.amazon.com/sns/latest/dg/sns-verify-signature-of-message.html
"""

import base64
import re
import urllib.request
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import load_pem_x509_certificate

# Only ever fetch signing certs / confirm subscriptions against a real SNS
# endpoint — never follow an attacker-supplied URL (SSRF guard).
_TRUSTED_SNS_HOST = re.compile(r"^sns\.[a-z0-9-]+\.amazonaws\.com$")

NOTIFICATION_FIELDS = ["Message", "MessageId", "Subject", "Timestamp", "TopicArn", "Type"]
SUBSCRIPTION_FIELDS = ["Message", "MessageId", "SubscribeURL", "Timestamp", "Token", "TopicArn", "Type"]


def _is_trusted_sns_url(url: str) -> bool:
    match = re.match(r"^https://([^/]+)/", url)
    return bool(match and _TRUSTED_SNS_HOST.match(match.group(1)))


def _default_cert_fetcher(url: str) -> bytes:
    if not _is_trusted_sns_url(url):
        raise ValueError(f"Refusing to fetch signing cert from untrusted host: {url}")
    with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 — host allow-listed above
        return resp.read()


def _canonical_string(envelope: dict) -> str:
    is_subscription = envelope.get("Type") in ("SubscriptionConfirmation", "UnsubscribeConfirmation")
    fields = SUBSCRIPTION_FIELDS if is_subscription else NOTIFICATION_FIELDS

    parts = []
    for field in fields:
        if field not in envelope:
            continue
        parts.append(field)
        parts.append(str(envelope[field]))
    return "\n".join(parts) + "\n"


def verify_sns_signature(envelope: dict, *, cert_fetcher: Callable[[str], bytes] | None = None) -> bool:
    """Returns False on any malformed input or verification failure — never
    raises, so callers can treat this as a plain "is this real" check."""
    fetch = cert_fetcher or _default_cert_fetcher
    try:
        cert_url = envelope["SigningCertURL"]
        if not _is_trusted_sns_url(cert_url):
            return False
        signature = base64.b64decode(envelope["Signature"])
        cert = load_pem_x509_certificate(fetch(cert_url))
        public_key = cert.public_key()
        message = _canonical_string(envelope).encode("utf-8")
        chosen_hash = hashes.SHA256() if envelope.get("SignatureVersion") == "2" else hashes.SHA1()
        public_key.verify(signature, message, padding.PKCS1v15(), chosen_hash)
        return True
    except (InvalidSignature, KeyError, ValueError, TypeError):
        return False


def confirm_subscription(url: str, *, fetcher: Callable[[str], bytes] | None = None) -> None:
    """SNS requires the subscriber to GET the SubscribeURL once to confirm."""
    fetch = fetcher or _default_cert_fetcher
    if not _is_trusted_sns_url(url):
        raise ValueError(f"Refusing to confirm subscription from untrusted host: {url}")
    fetch(url)
