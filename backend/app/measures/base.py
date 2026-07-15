from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Any, Protocol


class Demographic(Protocol):
    """Whatever `is_eligible` needs from its subject — satisfied by both
    Member and Dependent, without either module importing the other."""

    date_of_birth: str
    sex: str


class Measure(ABC):
    """A pluggable HEDIS measure module.

    Adding a new measure domain (breast cancer screening, colorectal cancer
    screening, etc.) means implementing this interface and registering it in
    app/measures/__init__.py — no changes to tenant, member, or care-gap schema.
    """

    code: str
    hedis_measure_name: str
    description: str

    #: "member" (default) — the account holder is the one being screened, and
    #: `is_eligible`/CareGap.member_id are the same person. "dependent" — the
    #: measure is about the member's dependent (pediatric measures); the
    #: account holder still receives outreach and submits on the dependent's
    #: behalf, but `is_eligible` is evaluated against a Dependent, and the
    #: resulting CareGap has both member_id (guardian) and dependent_id set.
    subject_type: str = "member"

    #: How the gap is *opened*. False (default) — a gap is opened up-front for
    #: every demographically-eligible member by the gap-opening pass. True — the
    #: gap is opened only when ingested data arrives (pharmacy fills for PDC,
    #: delivery episodes for PPC), so `_open_care_gaps_for_member` skips it and a
    #: measure-specific service opens it instead.
    data_driven: bool = False

    #: Whether a member can answer this measure via `evaluate_submission`. True
    #: (default) — screening/self-report measures, incl. episode-opened ones like
    #: PPC where the member still reports "yes I had my visit". False — the
    #: numerator is *computed* from claims and there is no member-facing form
    #: (PDC): such measures are hidden from the member's screening list and
    #: reject submissions.
    accepts_self_report: bool = True

    #: Which outreach copy to send for this measure — a key into
    #: app/notifications/templates.OUTREACH_TEMPLATES. Screening measures use the
    #: generic check-in invite; PDC uses a refill reminder; PPC uses pre/postnatal
    #: reminders.
    outreach_template: str = "screening_invite"

    #: Measure-specific HEDIS exclusion codes — a member carrying any of these
    #: (as a MemberExclusion) is removed from THIS measure's denominator (e.g.
    #: a hysterectomy excludes cervical screening). Broad exclusions that remove
    #: a member from every measure (hospice, deceased) live centrally in
    #: app/measures/exclusions.py, not here.
    exclusion_codes: frozenset[str] = frozenset()

    @abstractmethod
    def is_eligible(self, subject: Demographic, as_of: date) -> bool:
        """Whether this subject (a Member, or a Dependent for subject_type ==
        "dependent" measures) falls in the measure's eligible population."""

    @abstractmethod
    def evaluate_submission(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Score a submitted response. Returns dict with at least
        `numerator_met` (bool) and `safety_flag` (bool), plus measure-specific detail
        to store on ScreeningSubmission.instrument_scores.
        """

    @abstractmethod
    def follow_up_window_days(self, evaluation: dict[str, Any]) -> int | None:
        """Days after a positive/at-risk result within which follow-up must be
        documented for HEDIS credit. None if this result doesn't require follow-up.
        """


def default_period(as_of: date | None = None) -> str:
    return str((as_of or datetime.utcnow().date()).year)


def age_in_years(date_of_birth: str, as_of: date) -> int | None:
    try:
        dob = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
    except ValueError:
        return None
    return as_of.year - dob.year - ((as_of.month, as_of.day) < (dob.month, dob.day))
