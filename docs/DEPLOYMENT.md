# Deployment Guide

How to actually stand this up on AWS once you've claimed a domain in Route 53.
Do sections in order — later steps depend on earlier ones.

## 0. Prerequisites

- AWS account with billing set up, and CLI credentials configured locally
  (`aws configure` or an SSO profile)
- Domain registered/claimed in Route 53 (Route 53 → Registered domains, or
  Route 53 → Hosted zones if you registered elsewhere and are delegating DNS)
- Terraform >= 1.7, Docker, Node 18+, Python 3.12

## 1. Verify SES sending identity

SES starts in sandbox mode (can only send to verified addresses). Before real
outreach:

1. SES console → Verified identities → verify your domain (adds a DNS TXT/CNAME
   record — Route 53 makes this a one-click "Create record in Route 53" button)
2. Request production access (SES console → Account dashboard → "Request
   production access") — this is a support ticket, can take up to 24h
3. Note the verified sending address for `ses_from_email` in `terraform.tfvars`

## 2. Request an SMS origination number

AWS End User Messaging (formerly Pinpoint SMS): toll-free or 10DLC number
registration requires identity/use-case verification and can take several
business days for 10DLC, ~2 weeks for toll-free. Start this early — it's the
long pole, not the infra.

1. AWS End User Messaging console → Phone numbers → request a toll-free number
2. Submit the toll-free verification request (use case: healthcare appointment/
   screening reminders; include the opt-in/opt-out language from
   `backend/app/notifications/templates.py`)
3. Once approved, set `sms_origination_phone` in `terraform.tfvars`

Email outreach works immediately after step 1; SMS outreach is gated on this
step. The platform degrades gracefully — members without SMS consent/number
fall back to email (see `backend/app/routers/outreach.py::_send_to_member`).

## 3. Build and push the backend image

```bash
aws ecr create-repository --repository-name hedis-care-gap --region us-east-1

cd backend
docker build -t hedis-care-gap:latest .
aws ecr get-login-password --region us-east-1 | docker login --username AWS \
  --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
docker tag hedis-care-gap:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/hedis-care-gap:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/hedis-care-gap:latest
```

Use that image URI as `container_image` in `terraform.tfvars`.

## 4. Apply the infrastructure

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # fill in domain_name, container_image, ses_from_email
terraform init
terraform plan     # review before applying — this creates billable resources
terraform apply
```

Expect 15-20 minutes on first apply (ACM DNS validation + Aurora cluster
creation are the slow parts). See `infra/README.md` for what gets created.

## 5. Seed the production database

The dev-mode auto-seed (`backend/app/seed.py`) only runs when `DEV_MODE=true`,
which production explicitly disables. Create your first real tenant instead:

```bash
# One-time: create a super_admin directly against the production DB
# (there's no API endpoint for this by design — it's a break-glass operation)
psql "$DATABASE_URL" -c "
  INSERT INTO staff_users (id, tenant_id, email, password_hash, role, name, created_at)
  VALUES (gen_random_uuid()::text, NULL, 'you@yourcompany.com', '<bcrypt-hash>', 'super_admin', 'Platform Admin', now());
"
```

Then use `POST /api/tenants` (as that super_admin) to create the first real
health plan tenant, and `POST /api/members/bulk` to load its member roster.

## 6. Deploy the frontend

```bash
cd frontend
echo "VITE_API_URL=https://api.<your-domain>" > .env.production
npm run build
aws s3 sync dist/ s3://hedis-care-gap-frontend --delete
aws cloudfront create-invalidation --distribution-id <from terraform output> --paths "/*"
```

## 7. Verify

- `https://api.<domain>/health` → `{"status": "ok"}`
- `https://app.<domain>/` loads the landing page
- Staff login works for the super_admin created in step 5
- Send a test outreach to a test member with real consent on file and confirm
  SMS/email actually arrives

## 8. Ongoing outreach cadence

`POST /api/outreach/run-batch` sends outreach for every gap due for (re)contact
for the calling admin's tenant. This needs to run on a schedule, not be
triggered manually — add an EventBridge Scheduler rule invoking an ECS
Scheduled Task (or a small Lambda that calls the endpoint with a service-role
JWT) on whatever cadence fits your outreach cadence (daily is a reasonable
start). Not yet in Terraform — add it once you've validated the manual flow.

## Rollback / redeploy

- **Backend**: push a new image tag, update `container_image` in
  `terraform.tfvars`, `terraform apply` — ECS does a rolling deployment
- **Frontend**: rebuild, re-sync to S3, re-invalidate CloudFront
- **Database migrations**: this scaffold uses `Base.metadata.create_all` on
  startup (see `backend/app/db.py::init_db`), which only adds new tables, never
  alters existing ones. Introduce Alembic (already in `requirements.txt`)
  before your first schema change against real data.
