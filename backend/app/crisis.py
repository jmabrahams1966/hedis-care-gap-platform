"""Crisis detection + always-on safety response for secure messaging (Feature D).

The keyword/phrase list is a conservative PLACEHOLDER pending clinical sign-off
(shared concern with Feature B's escalation protocol — see
docs/HEDIS_COMPLIANCE.md). The 988 auto-reply is safe to send on any channel
(no PHI) and fires regardless of business hours.
"""

from datetime import datetime

# Deliberately high-recall (better a false alarm than a missed crisis). NOT clinically validated.
CRISIS_PHRASES = (
    "kill myself",
    "killing myself",
    "end it all",
    "end my life",
    "want to die",
    "wanna die",
    "suicide",
    "suicidal",
    "hurt myself",
    "harm myself",
    "self harm",
    "self-harm",
    "no reason to live",
    "better off dead",
    "can't go on",
    "cant go on",
)

CRISIS_AUTO_REPLY = (
    "If you're in crisis, call or text 988 (Suicide & Crisis Lifeline) now — it's free, "
    "confidential, and available 24/7. If you're in immediate danger, call 911."
)

AFTER_HOURS_ACK = (
    "Thanks for your message. Our care team is offline right now and will reply during "
    "business hours. If this is urgent, call or text 988, or call 911."
)


def crisis_scan(text: str) -> bool:
    t = (text or "").lower()
    return any(p in t for p in CRISIS_PHRASES)


def within_business_hours(now: datetime) -> bool:
    """Mon–Fri 08:00–18:00 (server time). Timezone-aware windowing is deferred
    (spec §10 open question)."""
    return now.weekday() < 5 and 8 <= now.hour < 18
