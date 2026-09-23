# Dependency Risk Acceptance

- **Date:** 2026-09-20
- **Method:** `pip-audit -r requirements.txt` (PyPA/OSV database) and `pip check`.
- **Status of the rest of the tree:** `pip check` → *No broken requirements found.* `pip-audit` → **exactly one** flagged package (below). JS side: `npm audit` → 0 vulnerabilities (lockfile present).

---

## DEP-1 — `click 8.1.8` (PYSEC-2026-2132)

| Field | Value |
|-------|-------|
| Package | `click` |
| Installed version | `8.1.8` |
| Advisory | `PYSEC-2026-2132` (as reported by `pip-audit`) |
| Fix version | `8.3.3` |
| Pulled in by | `gTTS==2.5.4` (declares `click<8.2,>=7.1`) |

### Why it cannot be upgraded in place

`gTTS` is the **free, keyless TTS fallback** (provider 3). `gTTS 2.5.4` is the
latest published release and its metadata pins `click<8.2,>=7.1`. The advisory's
fix (`click 8.3.3`) is `>= 8.2`, so it is **mutually exclusive** with the only
available gTTS version. Attempting `pip install click==8.3.3` yields a
`ResolutionImpossible` and would break clean installs. There is no gTTS release
that accepts the patched click.

### Why the vulnerable path is unreachable from this app

- The application uses gTTS **as a library only**: `from gtts import gTTS` in
  `app/services/tts_service.py`. It never invokes the gTTS command-line
  interface (`gtts-cli`), which is where `click` is used for argument parsing.
- **Verified** in this environment: importing the gTTS library does **not**
  import `click` (`click` is absent from `sys.modules` after
  `from gtts import gTTS`). The vulnerable module is therefore never loaded on
  any code path the server executes.
- The endpoint surface does not pass attacker-controlled data to any `click`
  parser; `click` is only reachable via the gTTS CLI entry point, which is not
  installed or invoked here.

### Decision

**Risk accepted, contained.** We keep `click 8.1.8` because the patched version
is unobtainable alongside gTTS 2.5.4, and because the vulnerable code path is
unreachable from the running application (library import does not load `click`;
the gTTS CLI is unused). No real external input reaches a `click` parser.

### Residual risk & monitoring

- If gTTS is ever used via its CLI, or a future dependency introduces a `click`
  parser on a request path, this acceptance is void and must be revisited.
- Re-run `pip-audit -r requirements.txt` on every dependency change and before
  each release. If a `gTTS` release that accepts `click>=8.3` (or a drop-in
  replacement TTS library) becomes available, upgrade and drop this acceptance.
- gTTS is the **last-resort** TTS fallback; primary voice output uses
  ElevenLabs / the custom OpenAI-compatible provider. Disabling gTTS entirely
  would remove the `click` dependency at the cost of the keyless fallback.
