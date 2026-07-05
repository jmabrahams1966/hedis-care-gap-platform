"""Server-side clinical scoring. The client never computes or sees a trusted score.

Wording for PHQ-9 and GAD-7 below is the standard public-domain wording (Pfizer);
verify against the current official version before production use — see
docs/HEDIS_COMPLIANCE.md.
"""

PHQ9_ITEMS = [
    "Little interest or pleasure in doing things",
    "Feeling down, depressed, or hopeless",
    "Trouble falling or staying asleep, or sleeping too much",
    "Feeling tired or having little energy",
    "Poor appetite or overeating",
    "Feeling bad about yourself — or that you are a failure or have let yourself or your family down",
    "Trouble concentrating on things, such as reading or watching television",
    "Moving or speaking so slowly that other people could have noticed, or the opposite — being so "
    "fidgety or restless that you have been moving around a lot more than usual",
    "Thoughts that you would be better off dead, or of hurting yourself in some way",
]

GAD7_ITEMS = [
    "Feeling nervous, anxious, or on edge",
    "Not being able to stop or control worrying",
    "Worrying too much about different things",
    "Trouble relaxing",
    "Being so restless that it is hard to sit still",
    "Becoming easily annoyed or irritable",
    "Feeling afraid, as if something awful might happen",
]

_RESPONSE_SCALE = ["Not at all", "Several days", "More than half the days", "Nearly every day"]


def _severity(total: int, cutoffs: list[tuple[int, str]]) -> str:
    band = cutoffs[0][1]
    for threshold, label in cutoffs:
        if total >= threshold:
            band = label
    return band


def score_phq9(answers: list[int]) -> dict:
    if len(answers) != 9 or any(a not in (0, 1, 2, 3) for a in answers):
        raise ValueError("PHQ-9 requires exactly 9 answers, each 0-3")
    total = sum(answers)
    severity = _severity(
        total, [(0, "minimal"), (5, "mild"), (10, "moderate"), (15, "moderately_severe"), (20, "severe")]
    )
    safety_flag = answers[8] > 0  # item 9: thoughts of self-harm
    return {"total": total, "severity": severity, "safety_flag": safety_flag, "answers": answers}


def score_gad7(answers: list[int]) -> dict:
    if len(answers) != 7 or any(a not in (0, 1, 2, 3) for a in answers):
        raise ValueError("GAD-7 requires exactly 7 answers, each 0-3")
    total = sum(answers)
    severity = _severity(total, [(0, "minimal"), (5, "mild"), (10, "moderate"), (15, "severe")])
    return {"total": total, "severity": severity, "answers": answers}
