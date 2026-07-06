# Inbound two-way SMS wiring: AWS End User Messaging (Pinpoint SMS Voice V2)
# delivers inbound replies (STOP/START/HELP) to this SNS topic, which pushes
# them as an HTTPS subscription to the backend's signature-verified webhook
# (backend/app/routers/webhooks.py + app/notifications/sns_verify.py).
#
# The origination phone number itself is NOT managed here. Toll-free/10DLC
# numbers go through AWS's manual verification process (see
# docs/DEPLOYMENT.md) and are provisioned by hand, not by `terraform apply` —
# managing a real, hard-to-replace leased number as a Terraform resource
# risks it being recreated/released on state drift. Once the number is
# approved, point its two-way channel at `aws_sns_topic.sms_inbound.arn`
# (console, or `aws pinpoint-sms-voice-v2 set-two-way-channel-for-phone-number`).

data "aws_caller_identity" "current" {}

resource "aws_sns_topic" "sms_inbound" {
  name = "${var.project_name}-sms-inbound"
}

data "aws_iam_policy_document" "sms_inbound_topic" {
  statement {
    sid     = "AllowEndUserMessagingPublish"
    effect  = "Allow"
    actions = ["SNS:Publish"]

    resources = [aws_sns_topic.sms_inbound.arn]

    principals {
      type        = "Service"
      identifiers = ["sms-voice.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "sms_inbound" {
  arn    = aws_sns_topic.sms_inbound.arn
  policy = data.aws_iam_policy_document.sms_inbound_topic.json
}

# SNS auto-confirms the HTTPS subscription against the webhook's
# SubscriptionConfirmation handling (webhooks.py -> confirm_subscription) the
# first time this is applied — nothing further to do by hand.
resource "aws_sns_topic_subscription" "sms_inbound_webhook" {
  topic_arn              = aws_sns_topic.sms_inbound.arn
  protocol               = "https"
  endpoint               = "https://${var.api_fqdn}/api/webhooks/sms-inbound"
  endpoint_auto_confirms = true
  raw_message_delivery   = false
}

resource "aws_pinpointsmsvoicev2_configuration_set" "sms" {
  name                 = "${var.project_name}-sms"
  default_message_type = "TRANSACTIONAL"
}
