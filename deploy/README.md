# Deployment templates

Templates that implement the **production hardening** items from the security
audit. They are starting points — adapt the domain, ports, and secret injection
to your real infrastructure before deploying. None of these files contain
secrets or talk to production.

| File | Purpose | Audit item |
|------|---------|-----------|
| `.env.production.example` (repo root) | Hardened env defaults: registration off, business actions fail-closed, pinned absolute DB/audio paths, same-site cookie | L-3, H-1, L-2, M-5 |
| `Caddyfile` | Reverse proxy: automatic TLS, strict `Content-Security-Policy` (`script-src 'self'`), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, HSTS | M-4, TLS |
| `Dockerfile` | Multi-stage build; slim non-root backend image; SPA built in-stage | #25 |
| `docker-compose.yml` | `api` (private) + `caddy` (public) orchestration with a shared SPA volume | #25 |

## Key decisions baked in

- **One origin for SPA + API.** Caddy serves the SPA and proxies the API under
  the same host, so the HttpOnly session cookie is *same-site* and
  `COOKIE_SAMESITE=lax` is sufficient. Build the frontend with an empty
  `VITE_API_BASE_URL` (same-origin calls).
- **TLS at the proxy.** Caddy auto-provisions certificates (ACME). The backend
  listens on plain HTTP internally and is never exposed publicly.
- **Secrets via env / secret store**, never in the image. `env_file: ../.env`.

## Notes / caveats

- If you serve the API on a **different registrable domain** than the SPA, set
  `COOKIE_SAMESITE=none` (requires HTTPS) and add the exact API origin to
  `CORS_ORIGINS`.
- Caddy serves the SPA from the host's `frontend/dist` (bind-mounted read-only).
  Run `(cd frontend && npm run build)` before starting the stack.
