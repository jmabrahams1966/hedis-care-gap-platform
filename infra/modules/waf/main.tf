variable "project_name" {
  type = string
}

variable "alb_arn" {
  description = "ARN of the ALB to attach the web ACL to"
  type        = string
}

variable "rate_limit" {
  description = "Max requests per 5-minute window per client IP before blocking"
  type        = number
  default     = 2000
}

# Regional web ACL for the ALB (REGIONAL scope; CloudFront would need us-east-1
# CLOUDFRONT scope separately). Default action is allow — the rules below block
# bad traffic. See docs/SECURITY_HIPAA.md §5.
resource "aws_wafv2_web_acl" "this" {
  name        = "${var.project_name}-web-acl"
  description = "Rate limiting + AWS managed rule sets in front of the API ALB"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # 1. Per-IP rate limit — blunt DoS / credential-stuffing brake at the edge,
  #    complementing the per-account lockout in the app.
  rule {
    name     = "rate-limit"
    priority = 0
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = var.rate_limit
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-rate-limit"
      sampled_requests_enabled   = true
    }
  }

  # 2. AWS managed rule sets (OWASP-style common attacks, known-bad inputs,
  #    SQL injection, and IP reputation). Managed groups count in override_action.
  rule {
    name     = "common-rule-set"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "known-bad-inputs"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-bad-inputs"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "sqli"
    priority = 3
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesSQLiRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-sqli"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "ip-reputation"
    priority = 4
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-ip-reputation"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-web-acl"
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "alb" {
  resource_arn = var.alb_arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}

output "web_acl_arn" {
  value = aws_wafv2_web_acl.this.arn
}
