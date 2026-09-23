# Infrastructure (Terraform)

Provisions the full runtime for the Enterprise Voice Assistant in one AWS
account/region:

| Layer | Resource | Notes |
|---|---|---|
| Network | VPC, 2 public + 2 private subnets (2 AZs), IGW, NAT | Private: RDS + Redis. Public: ALB + Fargate (tasks get public IPs for provider egress). |
| Data | RDS PostgreSQL 15 | Encrypted, 7-day backups, Multi-AZ (default on), private-only. Schema is migrated by the app at startup (Alembic) — no bootstrap SQL. |
| Cache | ElastiCache Redis 7.1 | Auth token, at-rest + in-transit encryption, private-only. |
| Object store | S3 `*-assistant-audio` | SSE, public access blocked, 90-day lifecycle expiration. |
| Secrets | Secrets Manager `<proj>/<env>/app` | TF generates `DATABASE_URL` / `REDIS_URL` (random passwords) and creates the provider-key slots (empty). The operator fills provider keys into this one secret. |
| Compute | ECS Fargate + ALB | 2 tasks (configurable), rolling deploys, circuit breaker with automatic rollback, CloudWatch logs 30 d. |

## Apply

```bash
cd infra
terraform init
terraform plan
terraform apply -auto-approve
```

Suggested for production: move state to your own S3 bucket + DynamoDB
lock table, and use `-var environment=production` / `=staging` with separate
state per environment.

## Wire up the deploy pipeline (one-time, per environment)

1. **GitHub OIDC trust**: in IAM, create a role trusted by
   `token.actions.githubusercontent.com` with a condition on
   `token.actions.githubusercontent.com:sub` =
   `repo:{owner}/{repo}:ref:refs/heads/master`
   (plus `aud: sts.amazonaws.com`). Policy: ECR push + `ecs:DescribeTaskDefinition`,
   `RegisterTaskDefinition`, `UpdateService`, `DescribeServices`,
   `DescribeTasks`, and CloudWatch Logs `CreateLogStream`/`PutLogEvents`/
   `DescribeLogStreams` for `/ecs/{project}-{env}*`.
2. **GitHub repository** → Settings:
   - Secrets: `AWS_ROLE_ARN`, `AWS_REGION`
   - Variables: `ECS_CLUSTER`, `ECS_TASK_FAMILY`, `ECS_SERVICE`,
     `ECR_REPOSITORY` — copy from `terraform output` after apply.
3. **Fill the app secret** (Secrets Manager → `<proj>/<env>/app`): add your
   real provider keys (`OPENROUTER_API_KEY`, `ELEVENLABS_API_KEY`, …) into
   the JSON. Empty values boot fine — the app degrades per provider (see
   runbooks).
4. Push to `master` — CI runs, then Deploy builds the image, tags it with
   the commit SHA, registers a new task definition revision, and rolls the
   service (circuit breaker auto-rolls back on failure).

## What the app receives at runtime

Every value below is injected into the container environment by the task
definition — **none of it is in the image, the repo, or the task definition
JSON** (only the secret ARN and key names are):

`DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT_URL` (empty → real AWS S3 via the
task role), `S3_ACCESS_KEY` / `S3_SECRET_KEY` (empty → task role), and the
provider keys. Non-secret config (`S3_BUCKET`, `LOG_FORMAT`, `CORS_ORIGINS`,
…) is plain task-definition environment set by Terraform.

## Cost notes

Defaults are sized small (db.t4g.small, cache.t4g.small, 2× Fargate
1vCPU/2GB, 1 NAT, ALB). For a staging environment set
`rds_multi_az=false`, `environment=staging`, a smaller RDS class, and expect
roughly $150–300/month at low usage. Multi-AZ RDS doubles the database cost.

## Teardown

`terraform destroy` removes everything except:
- the RDS final snapshot (production only) — delete manually if you want the data gone
- the ECR repository's images (delete with `aws ecr delete-repository --force`)
- Secrets Manager recovery copies (kept 7 days for recovery, then purged)
