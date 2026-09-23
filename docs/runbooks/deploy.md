# Runbook: Deploy, Verify, Rollback

Applies to the Terraform/ECS deployment (see `infra/README.md`). Local
development is unchanged (`uvicorn app.main:app`).

## Normal deploy (push to master)

1. Push to `master`. GitHub runs **CI** (84-test suite on PostgreSQL + Redis
   services, frontend build).
2. **Deploy** triggers automatically after CI passes:
   image built → pushed to ECR (tag = commit SHA) → new task definition
   revision → `ecs update-service --force-new-deployment` → wait for
   `services-stable`.
3. Verify (all should be true within ~2 minutes):
   - `https://<alb-dns>/auth/me` → **401** (app alive; the ALB health check
     uses exactly this)
   - ECS console / CLI:
     ```bash
     aws ecs describe-services --cluster $ECS_CLUSTER --services $ECS_SERVICE \
       --query 'services[0].{running:runningCount,desired:desiredCount,events:events[0:2]}'
     ```
     `runningCount == desiredCount`, no recent `SERVICE_DEPLOYMENT_FAILED`.
   - CloudWatch Logs `/ecs/<proj>-<env>-api`: startup shows
     `alembic upgrade head -> done`, `redis session store ready`, and
     `request` JSON lines with `status: 200/401`.
4. Smoke one real flow: register (or login) → chat (text) → voice reply if
   TTS keys are configured.

Every API log line carries `correlation_id` (also echoed in the
`X-Correlation-ID` response header) — capture it from any request you smoke
and use it to grep the logs.

## Manual deploy (workflow_dispatch)

Use when: CI was skipped, you are deploying a hotfix branch tip, or re-running
after a failed deploy. Select the branch in Actions → Deploy → Run workflow.
Note: manual runs deploy the **branch head**, not the last CI-green commit —
confirm the SHA in the run summary before starting.

## Rollback

**Prefer the automatic path**: the ECS circuit breaker (`rollback = true`)
reverts to the previous task definition automatically if the new revision
fails its health checks or can't reach `desiredCount`. Check
`events` in `describe-services` for `deployment ... rolled back`.

Manual rollback:

```bash
# 1. Find the last known-good revision (the image tag is the commit SHA)
aws ecs list-task-definitions --family <ECS_TASK_FAMILY> --sort DESC \
  --query 'taskDefinitionArns[0:5]'

# 2. Point the service at it
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE \
  --task-definition <good-revision-arn>

# 3. Watch it converge
aws ecs wait services-stable --cluster $ECS_CLUSTER --services $ECS_SERVICE
```

Old images are retained (ECR lifecycle keeps the 10 most recent), so any
revision from the last 10 deploys is restorable without a rebuild.

**Schema note**: migrations are additive/forward-only (Alembic at startup).
Rolling back the app to a commit *before* a new migration is safe as long as
the old code doesn't reference new columns — if it does, restore the DB from
the RDS automated snapshot (see `incidents.md`) instead.

## Scaling

```bash
aws ecs update-service --cluster $ECS_CLUSTER --service $ECS_SERVICE --desired-count 4
```

- Each Fargate task = 1 vCPU / 2 GB, holds a 20-connection PG pool
  (`PG_POOL_MAX`) and ~50 Redis connections.
- RDS `db.t4g.small` comfortably serves ~4–6 tasks; raise the instance class
  (`terraform apply -var rds_instance_class=...`) before scaling past that.
- Scale in freely: sessions/rate limits live in Redis, not in the task.

## What is NOT automated

- Terraform changes (network, RDS class, Redis class, secrets wiring): apply
  manually, review the plan, keep the state in your chosen remote backend.
- Provider key rotation: edit the Secrets Manager secret
  `<proj>/<env>/app` — ECS tasks pick it up on the **next task start**; run a
  manual `update-service --force-new-deployment` to roll immediately.
