import logging

import boto3

from ..config import settings

logger = logging.getLogger("notifications.email")


def send_email(to_address: str, subject: str, body_text: str) -> str:
    """Returns a provider message id. In dev mode, logs instead of calling SES so
    local/CI runs never send real email."""
    if settings.dev_mode:
        logger.info("DEV_MODE email to=%s subject=%r body=%r", to_address, subject, body_text)
        return "dev-mode-not-sent"

    client = boto3.client("ses", region_name=settings.aws_region)
    response = client.send_email(
        Source=settings.ses_from_email,
        Destination={"ToAddresses": [to_address]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Text": {"Data": body_text}},
        },
        ConfigurationSetName=settings.ses_configuration_set,
    )
    return response["MessageId"]
