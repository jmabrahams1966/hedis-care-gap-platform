# Security & HIPAA Checklist

This platform handles real member PHI (health plan enrollees' screening
responses, contact info, clinical scores) once connected to a real payer roster
— unlike a "no PHI, mock data" prototype, it must be treated as in-scope for
HIPAA from the first real tenant onward. This is an engineering checklist, not
a compliance certification; a qualified compliance/legal review is still
required before handling real PHI.

## 1. Legal / organizational (do this first, before any real data)

- [ ] Execute a **Business Associate Agreement (BAA)** with AWS (available under
      AWS's HIPAA eligibility program) and with any other vendor touching PHI
- [ ] Confirm which AWS services in use are covered under the AWS BAA (SES, SNS,
      RDS/Aurora, ECS, S3, CloudFront, Secrets Manager, KMS, CloudWatch Logs are
      generally HIPAA-eligible — verify current list before relying on this)
- [ ] Define data retention / deletion policy for member PHI and screening
      responses, and a process for honoring a payer's or member's deletion request
- [ ] Incident response plan and breach notification procedure (HIPAA Breach
      Notification Rule timelines)

## 2. Encryption

- [x] **At rest** — Aurora cluster encrypted with a customer-managed KMS key
      (`infra/modules/database`, `infra/modules/secrets`); Secrets Manager entries
      and CloudWatch log group encrypted with the same key
- [ ] **In transit** — ALB terminates TLS 1.2+ only (`ssl_policy` in
      `infra/modules/ecs`); confirm CloudFront viewer + origin protocol policy is
      HTTPS-only end to end, and that RDS enforces `sslmode=require` for the
      asyncpg connection (add `?ssl=require` to `DATABASE_URL` in production)
- [ ] Rotate the KMS key and confirm `enable_key_rotation` stays on (already set)

## 3. Access control

- [x] Role-gated API (`super_admin` / `payer_admin` / `care_manager` /
      member) via `backend/app/deps.py::require_role`
- [x] Tenant isolation — every query scoped by `tenant_id`; verify this on every
      new router before merging (a missing `tenant_id` filter is a cross-tenant
      PHI leak)
- [ ] Principle of least privilege for staff roles — today `payer_admin` and
      `care_manager` see full member PII; confirm whether your payer contracts
      require a role that only sees de-identified data (the queue already shows
      aliases, not names — case detail currently does not surface raw name/DOB/
      phone, keep it that way unless a role explicitly needs it)
- [ ] MFA for staff logins — not yet implemented; `StaffUser` is password + JWT
      only today
- [ ] Session/token expiry review — `JWT_TTL_HOURS` (staff) and
      `MAGIC_TTL_MINUTES` (member) are configurable; confirm values against your
      security policy before production

## 4. Audit logging

- [x] Append-only `AuditLog` table (`backend/app/models.py`) — every login,
      magic-link request, screening submission, and care-gap status change is
      logged with actor, action, resource, tenant, and IP (`backend/app/audit.py`).
      SMS STOP/START replies are logged the same way (`action` = `sms_opt_out`/
      `sms_opt_in`, actor_type `member`) — this is the actual TCPA/HIPAA
      documentation trail for "member revoked consent on this date"; AWS's own
      carrier-level opt-out list stops delivery but doesn't produce this record
- [ ] Ship audit logs to a write-once store (e.g. S3 with Object Lock) in
      addition to the database, so an application-level compromise can't erase
      the trail
- [ ] Define retention period for audit logs (HIPAA doesn't mandate a specific
      number, but 6 years is a common baseline used for HIPAA documentation
      retention — confirm with counsel) — `infra/modules/ecs` currently sets
      CloudWatch log retention to 400 days as a starting point, not a final answer
- [ ] Alerting on anomalous access patterns (e.g. a care manager pulling an
      unusual volume of case detail records)

## 5. Network

- [x] Aurora in private subnets, security group scoped to ECS tasks only
      (`infra/modules/network`)
- [x] ECS tasks in private subnets, reachable only from the ALB
- [ ] WAF in front of the ALB/CloudFront (not yet in Terraform) — add
      `aws_wafv2_web_acl` before handling real traffic, at minimum rate-limiting
      and the AWS managed common rule set
- [ ] VPC Flow Logs enabled for network-level audit trail
- [x] Inbound SMS webhook (`POST /api/webhooks/sms-inbound`) verifies AWS SNS's
      message signature (RSA PKCS1v15, SHA1/SHA256 per SNS signature version)
      against a signing cert fetched only from an allow-listed `sns.*.amazonaws.com`
      host — a forged/unsigned POST cannot flip a member's consent (see
      `backend/app/notifications/sns_verify.py`). The cert-fetch and
      subscribe-confirmation URLs are both host-checked before any network
      call, closing off SSRF via a malicious `SigningCertURL`/`SubscribeURL`.
      Unit- and integration-tested against a synthetic cert, not yet exercised
      against a real AWS-signed message end-to-end.

## 6. Application-level PHI hygiene

- [x] De-identified counselor/care-manager queue (`Member.alias`, a stable
      pseudonym, not name/DOB) — mirrors the pattern from `cogai-campus`
- [x] Client never computes a trusted score — `backend/app/scoring.py` runs
      server-side only; the frontend's copy of PHQ-9/GAD-7 text is presentation-only
- [ ] PII field-level encryption (phone/email/DOB) beyond whole-disk encryption,
      if required by your specific payer contracts
- [ ] Data minimization review — confirm every field on `Member` is actually
      needed; don't ingest more of the payer's roster than the enabled measures
      require

## 7. Before the first real tenant

- [ ] All of section 1 (BAAs) signed
- [ ] Section 2–6 checkboxes reviewed by whoever owns security sign-off
- [ ] Penetration test or at minimum a focused security review of the auth flows
      (magic-link token handling, JWT, role checks)
- [ ] `DEV_MODE=false` confirmed in production config (dev mode returns magic-link
      tokens directly in API responses — catastrophic if left on in prod)
