output "sms_inbound_topic_arn" {
  value = aws_sns_topic.sms_inbound.arn
}

output "configuration_set_name" {
  value = aws_pinpointsmsvoicev2_configuration_set.sms.name
}
