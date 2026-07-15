SMS_OPT_OUT_FOOTER = "Reply STOP to opt out, HELP for help. Msg&data rates may apply."


def screening_invite_sms(tenant_name: str, link: str) -> str:
    return (
        f"{tenant_name}: You're due for a quick health check-in. "
        f"Complete it privately here: {link} {SMS_OPT_OUT_FOOTER}"
    )


def screening_invite_email_subject(tenant_name: str) -> str:
    return f"{tenant_name}: A quick health check-in for you"


def screening_invite_email_body(tenant_name: str, member_first_name: str, link: str) -> str:
    return (
        f"Hi {member_first_name},\n\n"
        f"{tenant_name} would like you to complete a brief, confidential health check-in. "
        f"It takes about 5 minutes and your responses are never shared with your employer.\n\n"
        f"Start here: {link}\n"
        f"This secure link is single-use and will expire after a while for your security.\n\n"
        f"If you didn't expect this message, you can safely ignore it or contact "
        f"{tenant_name} support.\n"
    )


def refill_reminder_sms(tenant_name: str, link: str) -> str:
    return (
        f"{tenant_name}: Our records show you may be due to refill a regular medication. "
        f"Taking it as prescribed keeps you covered — manage your refills here: {link}. "
        f"{SMS_OPT_OUT_FOOTER}"
    )


def refill_reminder_email_subject(tenant_name: str) -> str:
    return f"{tenant_name}: A reminder about your medication refills"


def refill_reminder_email_body(tenant_name: str, member_first_name: str, link: str) -> str:
    return (
        f"Hi {member_first_name},\n\n"
        f"{tenant_name}'s records suggest there may be a gap in refilling one of your regular "
        f"medications. Taking your medication as prescribed is one of the most important things "
        f"you can do for your health, and we'd like to help you stay on track.\n\n"
        f"Review your medications and refill options here: {link}\n"
        f"This secure link is single-use and will expire after a while for your security.\n\n"
        f"If you've already refilled, or your prescription has changed, please contact "
        f"{tenant_name} support so we can update our records.\n"
    )


def postpartum_reminder_sms(tenant_name: str, link: str) -> str:
    return (
        f"{tenant_name}: Congratulations! A postpartum checkup 1–12 weeks after delivery keeps you "
        f"healthy. Confirm your visit or get scheduling help here: {link}. {SMS_OPT_OUT_FOOTER}"
    )


def postpartum_reminder_email_subject(tenant_name: str) -> str:
    return f"{tenant_name}: Your postpartum checkup matters"


def postpartum_reminder_email_body(tenant_name: str, member_first_name: str, link: str) -> str:
    return (
        f"Hi {member_first_name},\n\n"
        f"Congratulations on your new arrival! A postpartum visit with your provider between 1 and "
        f"12 weeks after delivery is one of the best things you can do for your own health.\n\n"
        f"Let us know if you've had your visit, or ask for help scheduling one, here: {link}\n"
        f"This secure link is single-use and will expire after a while for your security.\n\n"
        f"If you have any concerns about your health, please contact your provider or "
        f"{tenant_name} support right away.\n"
    )


def prenatal_reminder_sms(tenant_name: str, link: str) -> str:
    return (
        f"{tenant_name}: Early prenatal care is important for you and your baby. "
        f"Confirm your prenatal visit here: {link}. {SMS_OPT_OUT_FOOTER}"
    )


def prenatal_reminder_email_subject(tenant_name: str) -> str:
    return f"{tenant_name}: A note about your prenatal care"


def prenatal_reminder_email_body(tenant_name: str, member_first_name: str, link: str) -> str:
    return (
        f"Hi {member_first_name},\n\n"
        f"{tenant_name} wants to help you get the most out of your prenatal care. Timely prenatal "
        f"visits — especially early in pregnancy — help keep you and your baby healthy.\n\n"
        f"Confirm your prenatal visit or ask for help here: {link}\n"
        f"This secure link is single-use and will expire after a while for your security.\n\n"
        f"If you have questions, contact your provider or {tenant_name} support.\n"
    )


#: Maps a measure's `outreach_template` key to its SMS + email builders, so the
#: outreach service can pick copy by measure without a chain of if/elses.
OUTREACH_TEMPLATES = {
    "screening_invite": {
        "sms": screening_invite_sms,
        "email_subject": screening_invite_email_subject,
        "email_body": screening_invite_email_body,
    },
    "refill_reminder": {
        "sms": refill_reminder_sms,
        "email_subject": refill_reminder_email_subject,
        "email_body": refill_reminder_email_body,
    },
    "postpartum_reminder": {
        "sms": postpartum_reminder_sms,
        "email_subject": postpartum_reminder_email_subject,
        "email_body": postpartum_reminder_email_body,
    },
    "prenatal_reminder": {
        "sms": prenatal_reminder_sms,
        "email_subject": prenatal_reminder_email_subject,
        "email_body": prenatal_reminder_email_body,
    },
}
