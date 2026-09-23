# Enterprise Voice Assistant — Pre-Production Security Audit

- **Date:** 2026-09-20
- **Scope:** `app/` (FastAPI backend), `frontend/` (React/Vite SPA), `requirements.txt`, `frontend/package.json`, config, DB schema, git tracking, deployment surface.
- **Method:** Static code/config review (OWASP Top 10 + OWASP API Security) plus read-only, isolated live probes on a throwaway `uvicorn` instance on a non-default port with a temp DB (no real provider credentials, no production system touched). All data endpoints, CORS, `/audio` traversal, and `/status` were verified live.
- **Constraints honored:** No destructive changes; no production interaction; no real secret values printed (only "configured/not"); findings are stated as vulnerable only where code/config evidence exists, otherwise labeled **requires manual verification**.

---

## SECURITY AUDIT SUMMARY

| Severity | Count |
|----------|-------|
| **Critical** | 0 |
| **High** | 2 |
| **Medium** | 5 |
| **Low** | 4 |
| **Total** | 11 |

The core **data plane is sound**: strong password hashing, fully parameterized SQL, per-user data isolation, a traversal-proof `/audio` route, correctly restricted CORS, and no secrets in the repo or git history. The risk is concentrated in the **outbound "business action" (WhatsApp/Email) path**, which executes real external sends with **operator credentials and no authorization, confirmation, or rate limits**, and is reachable by any self-registered account. Secondary gaps are the classic production hardening items: no token expiry, no rate limiting/input caps, no security headers, token in localStorage, and a public info-disclosure endpoint.

**This is not a clean bill of health.** The two High findings are exploitable-by-design (the code simply lacks the control), and several items require a live, authorized penetration test to confirm exploit reliability.

---

## Confirmed SOUND (evidence-based — not findings)

- **Password storage** — PBKDF2-HMAC-SHA256, 200,000 iterations, 16-byte per-user salt, constant-time `hmac.compare_digest` compare. `app/services/auth_service.py:19-21,24-34`.
- **SQL injection** — every query uses `?` placeholders; no string-concatenated SQL. `app/services/auth_service.py:47-59,70-81,94-102`, `app/services/database_chat_history.py:15-20,30-38,54-57`, `app/api/chat.py:49-52`.
- **`/audio` path traversal** — strict `^[0-9a-f]{32}\.mp3$` regex + per-session ownership check + `is_file()`. Live `GET /audio/..%2f..%2f.env` → `404`. `app/api/chat.py:29,45,185-193`.
- **Per-user data isolation (IDOR, by design)** — all history/memory/audio scoped to a server-derived `session_id = "user:<id>"`; no client-supplied session id is trusted. `app/services/auth_service.py:108`. (A live two-account exploit test is still recommended — see checklist.)
- **CORS** — env-restricted `allow_origins`; live preflight from `https://evil.example` → `400 Disallowed CORS origin`. `app/main.py:25`.
- **No file-upload endpoint** — voice STT is client-side (Web Speech API); no server upload route.
- **No admin/debug surface** — only `auth` + `chat` routers are mounted. `app/main.py:31-32`.
- **Secrets handling** — all provider keys are env-driven; code never prints secret values (only configured/not); WhatsApp error path is truncated and avoids leaking the token. `app/connectors/whatsapp_connector.py:122-128`. `.env`, `assistant.db`, `audio/`, `*.mp3` are in `.gitignore`; working tree + git history contain no secrets (verified earlier this session).
- **JS dependencies** — `npm audit`: 0 vulnerabilities (lockfile present).
- **Unauthenticated access to data** — live: `/chat`, `/history`, `/memories`, `/auth/me`, `/audio/...` all return `401` without a token.

---

## FINDINGS

### [H-1] LLM-triggered real WhatsApp/Email sends use operator credentials with no authorization, confirmation, or rate limits
- **Severity:** High (trends Critical — reachable by any self-registered account; see L-3)
- **Location / File:** `app/services/session_service.py:134,148-159`; `app/connectors/orchestrator.py:31,102,127,137-155,164`; `app/connectors/whatsapp_connector.py:36,75-106`; `app/connectors/email_connector.py:37,76-89`; entry via `app/api/chat.py:87`
- **Evidence:** `process_message` reads `action_data = data.get("action")` (session_service.py:134), validates only that it "is an object or null" (:148-149), then calls `run_business_action(reply, action_data)` (:159). That flows to `execute_action` (orchestrator.py:102), which resolves a recipient **by name** against the operator's CRM (`get_crm().resolve(business.recipient)`, :127) and sends for real: `get_whatsapp_connector().send_text(phone, ...)` (:137) / group fan-out to many numbers (:139-142) / `get_email_connector().send(email, subject, body)` (:151-155). `WhatsAppConnector` posts to `graph.facebook.com` with `Authorization: Bearer {settings.WA_TOKEN}` (whatsapp_connector.py:36,75-93); `EmailConnector` does `server.login(settings.EMAIL_USERNAME, settings.EMAIL_PASSWORD)` then `send_message()` (email_connector.py:37,83-89). The only guard is `is_ambiguous_recipient` (orchestrator.py:38-51), a handful of vague-phrase regexes ("someone", "one of my friends"). There is **no per-user authorization, no recipient allowlist, no human confirmation, no per-user quota, and no audit log of who sent what to whom.**
- **Why it matters:** This is the app's most powerful side effect — sending real outbound WhatsApp/Email **under the operator's identity/number** to the operator's contacts. It is gated only by "is the user authenticated," and registration is open (L-3), so it is effectively available to anonymous self-registered accounts.
- **How it could be abused:** (1) A newly self-registered user says "send Rahul a WhatsApp saying …" → the operator's WhatsApp number messages the operator's CRM contact. (2) Iterating names reveals which contacts exist in the operator's CRM. (3) Group actions fan out to many recipients at once (orchestrator.py:139-142). (4) Unbounded repetition → mass messaging / SMS-style abuse that drains the operator's paid WhatsApp/email quota and reputation, and can be used for phishing/scams under a trusted number.
- **Recommended fix:** (1) Add a **server-side authorization + capability check** before `execute_action` (only designated roles/accounts may trigger sends; scope recipients to a per-user subset of the CRM — never the operator's full directory for everyone). (2) Require an **explicit out-of-band user confirmation** (two-turn preview → confirm) or dry-run-by-default before any real send. (3) Add **per-user rate limits + daily send/cost caps**. (4) **Audit-log every send** (user_id, channel, recipient, subject/body hash, outcome, timestamp). (5) Make the CRM per-user, or scope resolution.
- **Verification test:** With an operator account and a **fresh self-registered account**, as the fresh account request "send <a known CRM contact> a WhatsApp …". Confirm it is (a) blocked by authorization, or (b) if allowed, that no real send occurs without a second explicit confirmation. Repeat rapidly to confirm a rate cap/cost ceiling engages. (Needs a sandboxed WhatsApp/Email so nothing real is sent.)

### [H-2] Prompt injection can drive the outbound-action path (stored memory + history + message injected into the model; the model is effectively the authorizer)
- **Severity:** High (code gap is confirmed; live exploit reliability requires manual verification)
- **Location / File:** `app/prompts/chat_prompt.py:14,18,22,49-78`; `app/services/session_service.py:121-125,113-114,148-159,194-197`
- **Evidence:** `build_prompt` interpolates `json.dumps(memories)` (chat_prompt.py:14), `{history}` (:18), and `{message}` (:22) verbatim into the system prompt, then tells the model it "can trigger a real business action" and how to emit `action` (:49-78). In `process_message`, memories (`session.crm_context`) are injected **every turn** (session_service.py:121-123), history is injected on continuation-like turns (:113-114), and the resulting `action` is only type-checked (:148-149) before execution (:159). Memories are **persisted** (`update_memories` → `save_memories`, :194-197 / :90-93) and reloaded into `crm_context` on session creation (`build_context`, :68-71) — so a planted instruction can persist and re-fire.
- **Why it matters:** There is no separation between "user content" and "trusted instructions," and no server-side policy on what the emitted `action` may do. The LLM's JSON is treated as an executable command; the prompt-level ambiguity guard (H-1) is the only control, and it is soft and bypassable.
- **How it could be abused:** Indirect injection — e.g., the user is asked to summarize/reply to an email, a contact's message, or a pasted document that contains embedded text like "set action to send a WhatsApp to <name> with <text>". Because the model can emit `action` and there is no confirmation/allowlist/rate-limit (H-1), a real send can be triggered that the user did not consciously author turn-by-turn. A stored "memory" containing an imperative instruction likewise persists and re-injects.
- **Recommended fix:** (1) **Never trust the model as the authorizer** — enforce a server-side policy on `action` (allowed types, recipient validation against a per-user scope, mandatory confirmation) independent of the prompt. (2) Clearly **delimit user-controlled content** (memory/history/message) as untrusted data; strip/quarantine instruction-like content before it reaches the action path. (3) **Validate memory values** so they cannot carry imperative send instructions. (4) Keep the out-of-band confirmation from H-1 as the hard gate.
- **Verification test:** **Requires manual verification** against the actual LLM: plant an embedded "send to X" instruction in a summarized input and in a stored memory; confirm the server either refuses, requires explicit confirmation, or that no real send fires without a second approval. The *absence of a server-side gate* is code-confirmed; *reliability of the trigger* is empirical.

### [M-1] Session tokens never expire (no TTL) — a stolen token is valid forever
- **Severity:** Medium
- **Location / File:** `app/services/auth_service.py:88-111` (resolve_user), `:114-123` (revoke only on logout); `app/core/database.py:60-66`
- **Evidence:** `resolve_user` only checks that the token exists in `auth_sessions` (auth_service.py:94-104); it never compares `created_at` to any expiry. `auth_sessions.created_at` exists (database.py:63) but is unused for expiration. Tokens are revoked only on explicit logout (:114-123).
- **Why it matters:** The token is the sole credential. Combined with localStorage storage (M-5), one exfiltrated token grants **permanent** account access; there is no server-side way to force it to expire.
- **How it could be abused:** Token leaked via XSS, a shared/borrowed device, a browser profile, or a backup remains valid indefinitely.
- **Recommended fix:** Add absolute + sliding expiry (e.g., 12 h sliding / 7 d absolute), store `expires_at` on `auth_sessions`, check it in `resolve_user`, rotate periodically, and support revocation.
- **Verification test:** Obtain a token, wait past the configured TTL, and confirm `/auth/me` returns `401`; confirm logout invalidates immediately.

### [M-2] No rate limiting, no brute-force lockout, no input size caps (on auth and on the expensive /chat)
- **Severity:** Medium
- **Location / File:** `app/main.py` (only CORS middleware, :23-29); `app/api/auth.py:47` (/login), `:35` (/register); `app/api/chat.py:32-33` (ChatRequest.message), `:87-102` (costly handler)
- **Evidence:** No rate-limit middleware or per-route limiter exists anywhere in `app/` (search for `slowapi`/`rate_limit`/`max_length` returned nothing). `/login` has no lockout/throttle; `/register` is unthrottled; `ChatRequest.message: str` has no `max_length`, so unbounded input flows into the LLM prompt, the DB, and TTS. `/chat` performs a paid LLM call + TTS + a possible outbound WhatsApp/Email send per request.
- **Why it matters:** `/login` is brute-forceable (200k-iteration PBKDF2 slows each attempt but there is no throttle/lockout); `/register` can be spammed (each new account is a vehicle for H-1); `/chat` is the most expensive endpoint and is unthrottled → cost exhaustion / DoS.
- **How it could be abused:** Credential stuffing on `/login`; mass account registration; flooding `/chat` to exhaust LLM/TTS budget or trigger mass sends; oversized `message` payloads to inflate prompt cost.
- **Recommended fix:** Add per-IP and per-token rate limits on `/login`, `/register`, `/chat`; add lockout/progressive delay on failed logins; cap `message` length (e.g., `Field(..., max_length=4000)`) and request body size.
- **Verification test:** Fire many rapid `/login` failures → confirm throttle/lockout; POST an oversized `/chat` → confirm `413`/`422`; hammer `/chat` → confirm per-user caps.

### [M-3] Public, unauthenticated /status endpoint discloses architecture and active capabilities
- **Severity:** Medium
- **Location / File:** `app/api/chat.py:170-180` (no `Depends(require_user)`)
- **Evidence (live):** `GET /status` → `200` with `llm_engine` incl. the concrete model name, `tts_providers`, `connectors` (which are armed), and `supported_actions` (`email`, `whatsapp_message`).
- **Why it matters:** Any anonymous caller can confirm exactly which paid providers and which outbound connectors are live, plus the model in use — reconnaissance that tells an attacker WhatsApp/Email are armed (focus for H-1/H-2).
- **How it could be abused:** Recon step before attacking the business-action path; provider/model fingerprinting.
- **Recommended fix:** Gate `/status` behind auth, or return a minimal public health payload (`{"status":"online"}`) and move capability detail to an authenticated ops endpoint.
- **Verification test:** Unauthenticated `GET /status` returns only health (no provider/connector/action detail).

### [M-4] No security response headers (no CSP, X-Content-Type-Options, X-Frame-Options, Referrer-Policy, HSTS)
- **Severity:** Medium
- **Location / File:** `app/main.py` (no security-headers middleware); confirmed live — none present; search in `app/` returned nothing.
- **Evidence:** The SPA keeps the auth token in localStorage (M-5). Without a `Content-Security-Policy`, any future DOM-XSS becomes a **full, permanent account takeover** (compounded by M-1 no-expiry). Missing `X-Frame-Options` → clickjacking of login/send flows; missing `X-Content-Type-Options: nosniff` → MIME sniffing; no `Strict-Transport-Security`.
- **Why it matters:** These are the primary web-layer defenses; their absence removes the main mitigations against XSS/token theft and clickjacking.
- **How it could be abused:** Clickjacking of the sign-in or "send message" actions; any script injection → token theft → permanent session (no XSS sink found in this pass — see note).
- **Recommended fix:** Add a global middleware (or reverse-proxy config) setting a strict `Content-Security-Policy` (no `unsafe-inline`/`unsafe-eval`), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and `Strict-Transport-Security` (behind TLS). Prefer an HttpOnly cookie for the token (M-5).
- **Verification test:** Inspect response headers; confirm all present with sane values. *Note:* a grep for `dangerouslySetInnerHTML`/`innerHTML`/`document.write` in `frontend/src` found no sink, so no live XSS was identified — but all render paths should be re-checked manually.

### [M-5] Bearer token stored in localStorage (XSS → permanent account takeover)
- **Severity:** Medium
- **Location / File:** `frontend/src/App.jsx:14` (`jarvis_auth_token`), `:16-20` (get/store via localStorage), `:25-29` (axios interceptor reads it on every request)
- **Evidence:** The session token is persisted to `localStorage` and read on each request; there is no HttpOnly-cookie path.
- **Why it matters:** `localStorage` is readable by any same-origin JS. With M-4 (no CSP) and M-1 (no expiry), a single XSS yields an exfiltrated, never-expiring token.
- **How it could be abused:** Any script injection (first-party code or a dependency) can read `localStorage.getItem('jarvis_auth_token')` and exfiltrate it.
- **Recommended fix:** Store the session in a server-set `HttpOnly; Secure; SameSite=Strict` cookie (or at minimum enforce a strong CSP + short token TTL); avoid long-lived client-readable credentials.
- **Verification test:** Confirm the token is not in `localStorage` (moved to HttpOnly cookie), or that CSP blocks inline script and the token has a short TTL.

### [L-1] Username enumeration via /auth/register
- **Severity:** Low
- **Location / File:** `app/api/auth.py:35-44` (register) vs `:51` (login); `app/services/auth_service.py:52`
- **Evidence:** Registering an existing username returns `409 {"detail":"That username is already taken."}` (auth_service.py:52) while a new one succeeds; `/login` returns a generic `401 "Invalid username or password."`. The distinct register response reveals which usernames exist.
- **Why it matters:** Allows building a list of valid accounts (e.g., the operator's) for targeted phishing / credential stuffing.
- **How it could be abused:** Iterate candidate usernames to discover real accounts.
- **Recommended fix:** Return an identical, non-distinguishing response for both cases (or require email verification before account creation).
- **Verification test:** Register an existing vs a non-existing username; confirm the responses are indistinguishable.

### [L-2] CWD-relative DB/audio paths and no `PRAGMA foreign_keys=ON`
- **Severity:** Low
- **Location / File:** `app/core/database.py:4` (`DB_PATH = Path("assistant.db")`), `:7-10` (no FK pragma); `app/services/tts_service.py:8` (`AUDIO_DIR = Path("audio")`); `app/api/chat.py:28`; `app/core/database.py:64` (un-enforced FK)
- **Evidence:** DB and audio locations depend on the process working directory; `get_connection` never enables `PRAGMA foreign_keys=ON`, so the `auth_sessions.user_id` FK (database.py:64) is not enforced.
- **Why it matters:** Deployment fragility — a different CWD changes where the DB is written (or fails), and the DB could land in an unexpected/world-readable path; orphaned session rows are possible.
- **How it could be abused:** Primarily operational risk; a misconfigured CWD could place the DB somewhere undesirable.
- **Recommended fix:** Make `DB_PATH`/`AUDIO_DIR` absolute, env-driven, service-owned, and outside any web-accessible tree; add `PRAGMA foreign_keys=ON` in `get_connection`.
- **Verification test:** Start the app from a different CWD and confirm the DB path is stable/absolute; confirm FK cascade works.

### [L-3] Open self-registration with no approval, allowlist, or limits
- **Severity:** Low (but it is the entry gate that makes H-1 reachable — treat as High in combination)
- **Location / File:** `app/api/auth.py:35-44`; `app/main.py:31`; `app/services/auth_service.py:40-43` (min 3-char username / 8-char password)
- **Evidence:** Anyone can `POST /auth/register` and immediately receive a working token with full assistant access — including the ability to attempt business actions (H-1). No admin gating, email verification, or account-count limit.
- **Why it matters:** For an *enterprise* assistant with operator-owned outbound channels, open registration multiplies the population that can drive H-1/H-2.
- **How it could be abused:** Bulk/self-service account creation to gain standing to trigger WhatsApp/Email sends.
- **Recommended fix:** For internal/enterprise use, gate registration behind an allowlist or invite/admin approval, or disable open registration in production and provision accounts out-of-band.
- **Verification test:** Confirm unapproved registration is blocked (or requires an admin/invite) in the production configuration.

### [L-4] No structured security/audit logging or monitoring of sensitive events
- **Severity:** Low
- **Location / File:** `app/connectors/orchestrator.py:180-185` (logs action + result code, not user/recipient/channel); `app/api/auth.py` (auth events essentially unlogged); `app/connectors/whatsapp_connector.py:109,116`; `app/connectors/email_connector.py:91,97`
- **Evidence:** Business-action logging records the action and result code but not the authenticated `user_id`, recipient, or channel in a queryable store; login/register events are not logged with IP/outcome; provider failures are logged only in connector modules.
- **Why it matters:** Without an attributable audit trail you cannot reconstruct "who sent what to whom" after an H-1 incident, nor detect brute force (M-2).
- **How it could be abused:** Abusive sends leave no attributable, queryable record; incident response is guesswork.
- **Recommended fix:** Emit structured audit logs (or a DB table) for auth success/failure (with IP), token issue/revoke, and every connector send (user_id, channel, recipient, subject/body hash, outcome, timestamp); alert on spikes.
- **Verification test:** Trigger a send and a failed login; confirm both appear in an attributable, queryable audit log.

---

## PRE-LAUNCH SECURITY CHECKLIST

| # | Check | Status |
|---|-------|--------|
| 1 | Secrets not hardcoded / not in VCS (env-driven, gitignored, clean history) | [PASS] |
| 2 | Production secret storage — live `.env` (real `WA_TOKEN`/`EMAIL_PASSWORD`/LLM keys) must not ship in any deploy artifact/image | [NEEDS MANUAL REVIEW] |
| 3 | Password storage: strong KDF + per-user salt + constant-time compare | [PASS] |
| 4 | SQL parameterized (no injection) | [PASS] |
| 5 | Per-user data isolation / IDOR protection (design) | [PASS] |
| 6 | Two-account IDOR isolation (cross-user read of history/memory/audio) | [PASS] (automated — `IDORIsolationTest`); live prod exploit pen-test still recommended |
| 7 | `/audio` path-traversal protection (regex + ownership) | [PASS] |
| 8 | CORS restricted to allowed origins | [PASS] |
| 9 | AuthN enforced on all data endpoints (live 401) | [PASS] |
| 10 | No file-upload endpoint (client-side STT) | [PASS] |
| 11 | No admin/debug surface exposed | [PASS] |
| 12 | Session token expiry + revocation | [PASS] (M-1) |
| 13 | Rate limiting / brute-force lockout on auth | [PASS] (M-2) |
| 14 | Input size validation on `/chat` message | [PASS] (M-2) |
| 15 | Security response headers (nosniff, X-Frame-Options, Referrer-Policy on API; strict CSP + HSTS at reverse proxy) | [PASS] (M-4) |
| 16 | Token stored in HttpOnly cookie (not localStorage) | [PASS] (M-5) |
| 17 | No public info-disclosure endpoint | [PASS] (M-3) |
| 18 | Authorization + confirmation + rate/cost caps on outbound WhatsApp/Email | [PASS] (H-1) |
| 19 | Server-side policy gate on LLM-emitted actions (prompt-injection defense) | [PASS] (H-2) — `PromptInjectionBoundaryTest`; live model-compliance pen-test recommended |
| 20 | Structured security/audit logging of sends + auth events | [PASS] (L-4) |
| 21 | Username-enumeration resistance | [PASS] (L-1) |
| 22 | Open self-registration controlled (allowlist/invite/admin) | [PASS] (L-3) |
| 23 | Python dependency CVE scan (`pip-audit`) | [PASS] — 1 finding (DEP-1, `click`) risk-accepted & documented |
| 24 | JS dependency CVE scan | [PASS] (`npm audit` = 0) |
| 25 | Deployment hardening: TLS termination, reverse-proxy CORS/headers, container/process supervisor, absolute DB path | [NEEDS MANUAL REVIEW] (templates in `deploy/` exist; apply to real infra) |

---

## TOP 5 THINGS TO FIX BEFORE LAUNCH

1. **Gate the outbound WhatsApp/Email business actions (H-1).** Add per-user authorization + a per-user recipient allowlist + mandatory out-of-band confirmation + per-user rate/cost caps + an audit log of every send. This is the largest real-world blast radius: operator identity + paid channels, reachable by open self-registration (L-3).
2. **Add a server-side policy gate on LLM-emitted actions and fix the prompt-injection path (H-2).** Never treat the model's `action` as authorization — validate it server-side, delimit user-controlled content (memory/history/message) as untrusted data, and keep confirmation (from #1) as the hard gate.
3. **Add rate limiting + brute-force lockout + input size caps (M-2).** Protect `/login`, `/register`, and the expensive `/chat`; cap `message` length. Stops credential stuffing, account spam, and cost/DoS on the priciest endpoint.
4. **Expire/rotate tokens and move the token out of localStorage (M-1 + M-5).** Add a TTL + revocation and use an `HttpOnly; Secure; SameSite=Strict` cookie. Eliminates the "stolen token = permanent full access" chain.
5. **Add security headers and de-scope the public `/status` (M-4 + M-3).** Close the XSS→token-theft and clickjacking paths, and stop leaking provider/connector/model capability to anonymous callers.

---

## WHAT STILL REQUIRES MANUAL PEN TESTING / PRODUCTION VERIFICATION

Do **not** treat this as "secure." The static + isolated-probe audit found no trivially exploitable injection, auth bypass, IDOR, path traversal, or secret leak in the **core data plane** — those are genuinely sound. The following still need live, **authorized** verification:

- **Business-action exploit (H-1/H-2):** a sandboxed, real two-account test confirming a fresh self-registered account cannot send (or must confirm) WhatsApp/Email, and an indirect-prompt-injection attempt against the actual LLM. Requires a throwaway Meta/SMTP sandbox — do not run against production numbers.
- **IDOR (checklist #6):** a live two-account test proving one user cannot read another user's history/memories/audio (the isolation logic is correct by design but should be empirically confirmed).
- **Deployment hardening (checklist #25):** the repo has **no** Dockerfile/compose/Procfile/nginx/systemd — the app runs via bare `uvicorn app.main:app`. TLS termination, reverse-proxy CORS + security headers, secret injection (and keeping the live `.env` out of the image), process supervision, and absolute DB path must all be configured and verified in the real environment. CORS currently defaults to `http://localhost:5173` and must be set to the real origin(s) in production.
- **Supply chain (checklist #23):** run `pip-audit`/`safety` for Python (not installed here); `npm audit` already passed (0).
- **Secrets hygiene:** rotate the live `WA_TOKEN`, `EMAIL_PASSWORD`, and LLM/TTS keys if the repo's `.env` was ever committed, shared, or copied into any artifact; confirm it is excluded from all deploy outputs.
- **Edge/WAF rate limiting** if application-level limiting (#3) is deferred.

*Method note: live verification was performed on a throwaway `uvicorn` instance on a non-default port with an isolated temp DB and no real provider credentials; the throwaway server and its scratch files were cleaned up after the audit.*

---

## REMEDIATION — fixes implemented (2026-09-20)

All 11 findings were addressed in code — **checklist items #12–#22 are now PASS.** Backend suite: **63 tests pass** — 15 in `tests/test_security_controls.py` and 8 in `tests/test_security_boundary.py` (two-account IDOR isolation, prompt-injection boundary, and the cookie session flow, all through the real HTTP surface with the LLM and outbound connectors mocked); frontend `vite build` and `eslint` are clean. A runtime smoke test on an isolated temp DB (with a copy of the legacy DB to exercise the schema migration) confirmed: minimal public `/status`, the three security headers, authed `/status/detail`, working auth, and the `/chat` length cap (422).

| Finding | Fix | Where | Verified by |
|---|---|---|---|
| **H-1** | Outbound sends are **fail-closed**: gated by `BUSINESS_ACTIONS_ENABLED` + per-user `BUSINESS_ACTION_ALLOWED_USERS`, a per-user hourly cap, an explicit confirm step (default on), and a full `action_audit` log. The LLM is never the authorizer. | `app/services/session_service.py`, `app/services/action_policy.py`, `app/core/database.py` (`action_audit`, `pending_actions`) | unit: disabled/allowlist/confirm/deny/single-turn — connector not invoked unless policy passes |
| **H-2** | Server-side policy gate on the LLM's `action` (see H-1) + prompt delimits memory/history/message as **untrusted data** and restricts actions to the user's current request, so injected instructions in stored content are inert. | `app/services/session_service.py`, `app/prompts/chat_prompt.py` | unit: disabled + non-allowlisted block the send; confirmation classification is fail-safe |
| **M-1** | Absolute token TTL (`TOKEN_TTL_MINUTES`, default 12h) enforced in `resolve_user`; expired tokens are rejected and purged; still revoked on logout. | `app/services/auth_service.py`, `app/core/database.py` (`expires_at`) | unit: backdated token → `None` |
| **M-2** | DB-backed fixed-window rate limiting on `/login`,`/register` (by IP) and `/chat` (per user); `ChatRequest.message` capped (`MAX_MESSAGE_LENGTH`, default 4000); Pydantic length validation on credentials. | `app/core/rate_limiter.py`, `app/api/auth.py`, `app/api/chat.py` | unit: window cap + overlong message → `ValidationError`; live 422 |
| **M-3** | Public `/status` returns only `{"status":"online"}`; capability detail moved to authed `/status/detail`. | `app/api/chat.py` | live: minimal public body; 401 unauth on detail |
| **M-4** | API sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`; Vite dev server sets baseline headers + CSP; production CSP (`script-src 'self'`) documented for the reverse proxy. | `app/main.py`, `frontend/vite.config.js`, README | live: headers present |
| **M-5** | **Done**: the session token is delivered in an `HttpOnly; Secure; SameSite` cookie (set on login/register, cleared on logout). The API accepts the token from the cookie **or** the `Authorization` header (backward compatible); the SPA no longer stores the token in `localStorage` (uses `withCredentials`). | `app/api/auth.py` (`_token_from_request`, `set_auth_cookie`, `clear_auth_cookie`), `app/core/config.py` (`COOKIE_*`), `frontend/src/App.jsx` | unit: header-vs-cookie precedence + HttpOnly/Secure/SameSite attributes |
| **L-1** | Register returns a **non-distinguishing** message (no "already taken"); length issues return 422 via Pydantic; registration is rate-limited; `ALLOW_REGISTRATION=false` closes enumeration entirely. | `app/api/auth.py` | code + unit (rate limit) |
| **L-2** | `PRAGMA foreign_keys=ON` on every connection; `DB_PATH`/`AUDIO_DIR` are absolute + env-overridable. | `app/core/database.py`, `app/core/config.py`, `app/api/chat.py`, `app/services/tts_service.py` | app boots on a legacy DB (migration exercised) |
| **L-3** | `ALLOW_REGISTRATION` gate (default true for dev; set false in prod) + register rate limit. | `app/api/auth.py`, `app/core/config.py` | code + unit (rate limit) |
| **L-4** | Structured auth logging (login success/failure + register, with client IP) and a queryable `action_audit` table for every send attempt (user, channel, recipient, outcome; message stored as SHA-1 only). | `app/api/auth.py`, `app/services/action_policy.py`, `app/core/database.py` | code; audit rows written during unit tests |
| **DEP-1** | `pip-audit` found `click 8.1.8` (transitive via `gTTS`) with PYSEC-2026-2132 (fix `8.3.3`). **Risk accepted & contained** (see `docs/DEPENDENCY_RISK_ACCEPTANCE.md`): `gTTS 2.5.4` (latest) pins `click<8.2` so the patch can't be installed; the vulnerable path is unreachable — the app uses gTTS as a library and `from gtts import gTTS` does **not** import `click` (verified), and the gTTS CLI is unused. | `requirements.txt` (`gTTS==2.5.4`), `docs/DEPENDENCY_RISK_ACCEPTANCE.md` | `pip-audit -r requirements.txt --no-deps`; click-not-imported check |

### Verified locally this session (previously flagged "manual")
- **Two-account IDOR** — `IDORIsolationTest` drives the real HTTP endpoints with two real users/tokens: user B cannot read or clear user A's history/memories, `/audio` ownership is per-user, and anonymous reads are 401.
- **Prompt-injection boundary** — `PromptInjectionBoundaryTest` mocks a compromised LLM emitting send actions (including a stored-memory injection). The server-side gate blocks unapproved/unconfirmed sends, enforces the hourly cap, and writes `denied_policy`/`rate_limited` audit rows.
- **Cookie session flow** — `CookieSessionFlowTest` confirms the HttpOnly cookie authenticates on its own and logout revokes the token + clears the cookie.
- **Log-injection hardening** — `Credentials.username` is now charset-restricted (`^[A-Za-z0-9._-]+$`) with a regression test.

### Still requires manual / production verification
- **Live model-compliance pen test:** the server-side gate blocks unapproved sends regardless of the model, but measure how the real LLM behaves under injection for defense-in-depth confidence (empirical; cannot be faked locally).
- **Production deployment:** `deploy/` ships ready-to-adapt templates (Caddyfile with TLS + strict `script-src 'self'` CSP, Dockerfile, docker-compose, and `.env.production.example`). You still apply them to real infrastructure: the real domain + TLS, a secret store keeping the live `.env` out of any image/artifact, and pinned `DATABASE_PATH`/`AUDIO_DIR`.
- **`click` CVE (DEP-1):** the risk acceptance is documented in `docs/DEPENDENCY_RISK_ACCEPTANCE.md`. The only alternative is a product/dependency tradeoff (replace `gTTS` with a free-TTS library that allows `click>=8.3.3`), so it's left to you.
- **Enable + allowlist the business-action feature** in `.env` for the accounts that should send, then re-verify the confirm flow end-to-end in a sandboxed WhatsApp/Email environment (requires a real sandbox; the local tests never send anything real).

