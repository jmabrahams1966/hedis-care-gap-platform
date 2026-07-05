# Infrastructure (Terraform)

Provisions the full AWS stack: VPC (public/private subnets across 2 AZs, NAT), Aurora
Serverless v2 Postgres (encrypted, private), ECS Fargate service behind an ALB running the
FastAPI backend, an EventBridge Scheduler + dedicated ECS task running the outreach batch job
on a cadence, S3 + CloudFront for the static frontend, Route 53 records, ACM certificates,
KMS encryption key, and Secrets Manager entries for DB credentials / JWT secret.

**Not applied yet** — this is code only. Applying it creates real, billable AWS resources.

## Prerequisites

1. An AWS account with credentials configured (`aws configure` or an assumed role).
2. A domain claimed in Route 53 (Registered domains → the zone is created automatically).
3. Terraform >= 1.7: https://developer.hashicorp.com/terraform/install
4. A backend container image pushed to ECR (see `../docs/DEPLOYMENT.md` step 2) — the
   ECS task definition needs a real image URI before the first apply.
5. A verified SES sending identity for your domain (or subdomain) — see AWS SES console.

## Usage

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars: domain_name, container_image, ses_from_email, ...

terraform init
terraform plan
terraform apply
```

## Notes

- **CloudFront's ACM certificate must be in us-east-1** regardless of `aws_region` — the
  `dns` module handles this via a second aliased AWS provider (`aws.us_east_1`).
- **SMS origination** (AWS End User Messaging) requires a separate provisioning step outside
  Terraform — toll-free/10DLC number registration and verification takes AWS several business
  days. Leave `sms_origination_phone` empty until that's done; email outreach still works.
- **State**: this uses local state by default. Before a second person touches this, uncomment
  the `backend "s3"` block in `providers.tf` and create that bucket + DynamoDB lock table first.
- **First deploy order**: network → secrets → database → dns (cert validation can take several
  minutes) → ecs → frontend. Terraform resolves this automatically via module dependencies;
  just expect `apply` to take 15–20 minutes on a cold start (mostly ACM validation + Aurora).
- **Destroying**: the RDS cluster has `deletion_protection = true` — disable it explicitly
  before `terraform destroy` will succeed, so a stray destroy can't take the database with it.
