SMS_OPT_OUT_FOOTER = "Reply STOP to opt out, HELP for help. Msg&data rates may apply."


def screening_invite_sms(tenant_name: str, link: str) -> str:
    return (
        f"{tenant_name}: You're due for a quick health check-in. "
        f"Complete it privately here: {link} (expires in 30 min). {SMS_OPT_OUT_FOOTER}"
    )


def screening_invite_email_subject(tenant_name: str) -> str:
    return f"{tenant_name}: A quick health check-in for you"


def screening_invite_email_body(tenant_name: str, member_first_name: str, link: str) -> str:
    return (
        f"Hi {member_first_name},\n\n"
        f"{tenant_name} would like you to complete a brief, confidential health check-in. "
        f"It takes about 5 minutes and your responses are never shared with your employer.\n\n"
        f"Start here: {link}\n"
        f"This link expires in 30 minutes for your security.\n\n"
        f"If you didn't expect this message, you can safely ignore it or contact "
        f"{tenant_name} support.\n"
    )
