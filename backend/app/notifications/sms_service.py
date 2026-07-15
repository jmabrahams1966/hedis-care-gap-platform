import logging

import boto3

from ..config import settings

logger = logging.getLogger("notifications.sms")


def send_sms(to_number: str, message: str) -> str:
    """Returns a provider message id. In dev mode, logs instead of calling AWS End
    User Messaging so local/CI runs never send a real text."""
    if settings.dev_mode:
        logger.info("DEV_MODE sms to=%s message=%r", to_number, message)
        return "dev-mode-not-sent"

    if not settings.sms_origination_number:
        # No toll-free/10DLC number provisioned yet (the long-pole item). Skip
        # rather than let boto3 raise a validation error on an empty origination
        # identity — callers treat an empty id as "not delivered".
        logger.warning("SMS origination number not configured; skipping SMS to %s", to_number)
        return ""

    client = boto3.client("pinpoint-sms-voice-v2", region_name=settings.aws_region)
    response = client.send_text_message(
        DestinationPhoneNumber=to_number,
        OriginationIdentity=settings.sms_origination_number,
        MessageBody=message,
        MessageType="TRANSACTIONAL",
        ConfigurationSetName=settings.sms_configuration_set,
    )
    return response["MessageId"]
