# Runbook: Production Incidents

First step for any incident: find one failing request's `correlation_id`
(from the client response header `X-Correlation-ID` or the CloudWatch access
line `"event": "request"`) and filter the logs by it. Every log line,
including DB-query timings (`"event": "db_query"`), carries it.

## 1. Redis (ElastiCache) unavailable

**Symptoms:** `/auth/*` and `/chat` return **503** (`session store
unavailable`); health check `/auth/me` still 401. Chat rate limiting and the
conversation-context cache **degrade silently** (fail-open by design):
rate limits fall back to per-process counters (weaker across instances),
context is rebuilt from PostgreSQL on every request (slower, not wrong).

**Expected behavior (do not "fix" this):**
- Auth is fail-closed: no session can be verified, so no authenticated
  request succeeds. This is correct and safe.
- New logins also 503 and roll back their durable row — no orphan sessions.

**Actions:**
1. ElastiCache console → replication group: `available?` `node_state?`
2. If a single-node outage: `aws elasticache reboot-cache-node --cache-node-id <id>`
   (brief disconnect, sessions survive in RAM; after a hard restart all
   sessions are lost — users re-login, no data loss since Redis is
   non-durable by design).
3. If the whole group is down, check security groups/subnets and VPC health.
4. Recovery is automatic (app retries on each request; no restart needed).
5. Announce impact: "logins and chats unavailable, data safe."

## 2. RDS (PostgreSQL) unavailable

**Symptoms:** authenticated requests 500/503, `"event": "db_query"` lines
stop, CloudWatch `DatabaseConnections`/`CPUUtilization` flat or spiking.
This is the source of truth — **the API should be taken out of rotation**.

**Actions:**
1. RDS console: instance status, `FreeStorageSpace`, `DatabaseConnections`
   (exhausted connections = pool exhaustion; the app pool is 20/task ×
   task count — compare against `max_connections`).
2. If connection exhaustion: scale in tasks first
   (`ecs update-service --desired-count 1`), then raise
   `PG_POOL_MAX` or instance class.
3. If storage: RDS storage auto-grows up to `max_allocated_storage`
   (4× base); if pinned at the max, grow the variable.
4. If the instance is crashed: `restart-db-instance` (Multi-AZ fails over
   automatically — if it didn't, that's the incident).
5. **If data is suspect** (not just unavailable): stop, restore from the
   latest automated snapshot (7-day retention) into a scratch instance,
   verify, then swap endpoints in the app secret + roll the service. Never
   restore over a still-serving instance.

## 3. S3 (audio store) unavailable

**Symptoms:** text chat works; voice replies 503
(`audio service temporarily unavailable`); `/audio/*` 503. Uploads fail
closed, so no audio is lost silently and no user can fetch another user's
key.

**Actions:** confirm bucket access from a task role context
(`aws sts assume-role` equivalent via a test task, or check IAM), then check
bucket policy/ACL drift (`terraform plan` — the config enforces encryption +
public-access block). Recovery is automatic; no app restart needed. Voice is
degraded, the product still functions in text mode.

## 4. Provider failures (LLM / TTS / CRM / WhatsApp / SMTP)

**Expected behavior:** each provider has a timebox (LLM 10 s, TTS 15 s,
CRM 5 s, WhatsApp 10 s, SMTP 10 s), retries (LLM 3×, TTS 2×), and a circuit
breaker (open after 5 consecutive failures, half-open after 60 s). LLM
fallbacks: OpenRouter → NVIDIA → Gemini. TTS fallbacks: ElevenLabs →
OpenAI-compatible → gTTS (needs internet egress).

**Symptoms:** `"circuit OPEN for '<provider>'"` warnings in logs; chat 503
after all LLM providers fail; voice replies silently drop to text (TTS
exhausted); business actions return user-facing "couldn't send" messages
(action is **never** sent half-way).

**Actions:**
1. Identify the provider from the circuit name in logs.
2. Check the provider's status page / your key quota (401/402/429 from
   providers are logged as warnings without leaking tokens).
3. If it's your key: fix quota/key in the app secret, then roll the service
   (`update-service --force-new-deployment`) so tasks pick it up.
4. Breakers reset themselves after 60 s (half-open probes). No restart
   needed for transient failures.
5. If a provider is down long: it's safe to leave — traffic that would have
   gone to it gets the fallback or a clean 503, never a hang.

## 5. Deploy failure / auto-rollback

**Symptoms:** Actions → Deploy fails at "Wait for service stability", or
ECS events show `deployment ... rolled back` (circuit breaker).

**Actions:**
1. Read ECS service events (first 5) — they name the failed task and reason
   (health, pull, register, OOM).
2. Task-level: `aws ecs describe-tasks` → the failed task's `lastStatus`
   and stop reason; CloudWatch logs for that task's stream prefix for the
   crash traceback.
3. Common causes:
   - **Migration failure at startup** → compare `alembic current` on a
     scratch connection vs the head in the image; usually a bad commit's
     migration. Roll back (see deploy.md) and fix forward.
   - **Secret missing/renamed** → a task-definition secret reference points
     at a key that doesn't exist in the secret (tasks fail at start).
   - **OOM** → raise `ecs_memory` (terraform) if sustained; check for a
     leak in the old-vs-new memory curves (CloudWatch ContainerInsights).
4. The previous good revision is still serving (circuit breaker) — users
   are unaffected. Fix forward, redeploy.

## 6. Users report 429 (rate limiting)

**Limits (shipped defaults):** login/register 5 per 60 s per IP, chat 12
per 60 s per user, business actions 20 per hour per user
(`BUSINESS_ACTION_MAX_PER_HOUR`).

- Per-IP login/register limits trip when many users share an egress IP
  (corporate NAT, CDN). If that's the real topology, raise
  `RATE_LIMIT_LOGIN` / `RATE_LIMIT_REGISTER` in the task environment (not
  the code) — the per-user chat cap is the one that matters for abuse.
- Counters are atomic in Redis (shared across all tasks) — the limit is
  global, not per-task. Verify with
  `aws elasticache` + a test task, or the app logs (429 responses are
  logged with the correlation id).

## 7. Data restore (worst case)

1. `aws rds describe-db-snapshots` → latest automated snapshot.
2. Restore to a **new** instance (`restore-db-instance-from-db-snapshot`),
   same engine version.
3. Verify: row counts for `users`, `auth_sessions`, `messages` against
   pre-incident expectations; run the repo's test suite against the scratch
   DB (point `DATABASE_URL` at it) — 84 tests exercise the full schema.
4. Update `DATABASE_URL` in the app secret, `update-service
   --force-new-deployment`, then delete the scratch instance.
5. Redis needs no restore (sessions: users re-login; context: rebuilt from
   the DB; rate limits: re-armed naturally).
6. S3 audio is regenerable + 90-day lifecycle — nothing to restore for v1.

## Escalation checklist (copy into the incident)

- [ ] Incident start (UTC) + first affected `correlation_id`
- [ ] Symptom → section above (1–7)
- [ ] Impact: which user actions are broken, which still work
- [ ] Provider-side status (ElastiCache / RDS / S3 / LLM vendor)
- [ ] Actions taken + timestamps
- [ ] Current task count + `describe-services` output
- [ ] Rollback decision (yes/no, target revision)
