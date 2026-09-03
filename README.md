<div align="center">

# Enterprise Voice Assistant

**A voice-first AI assistant with persistent long-term memory, a state-driven JARVIS orb, and a modular business-connector layer (CRM → WhatsApp / Email).**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.140-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev)
[![SQLite](https://img.shields.io/badge/SQLite-Storage-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)

*Speak naturally. Be remembered. Take action.*

</div>

---

## ✨ What it does

- **Voice notes, WhatsApp-style.** Press the mic to record. The user's voice renders as an audio-note bubble (play/pause, waveform, duration). The **user's transcript stays internal** — it is never shown in the UI. JARVIS replies are spoken and reveal a **live transcript as it speaks**.
- **Persistent long-term memory.** The LLM extracts durable facts into SQLite; they survive refreshes and restarts. `/clear-chat` and `/clear-memories` reset them independently.
- **State-driven orb.** One JARVIS orb with distinct **Idle / Listening / Thinking / Speaking** states, driven by real microphone and playback energy, with a contained liquid-wave interior.
- **Solar Lava theme.** A warm, molten-orange visual identity applied to the orb and the app accents (see below).
- **Business connectors.** Ask JARVIS in plain language to send a WhatsApp or email to a named contact. The LLM detects the intent; an **orchestrator** resolves the person via the **CRM connector** and sends via the **WhatsApp** or **Email connector**.

---

## 🏗️ Architecture

```
[BROWSER]
  MediaRecorder        → audio Blob (voice-note bubble only)
  SpeechRecognition    → transcript (Web Speech API; browser-only)
        │  { message, response_mode: "voice" | "text" }
        ▼
[BACKEND  POST /chat]
  session_service.process_message
    ├─ build_prompt(memories, history, message)  + business-action rules
    ├─ llm_service.generate            LLM: OpenRouter → NVIDIA → Gemini (fallback)
    │      returns { reply, action?, memories, delete_memories }
    ├─ if action → orchestrator.run_business_action        [BUSINESS ACTIONS]
    │       CRM.resolve(recipient)  ──►  WhatsApp.send_text   or  Email.send
    ├─ persist history (+ mode) and memories → SQLite
    └─ voice mode → tts_service.generate_speech  TTS: ElevenLabs → OpenAI-compat → gTTS
        │
        ▼
[BROWSER]  renders reply, plays audio, reveals JARVIS live transcript
```

### STT — Speech-to-Text
Transcription happens **entirely in the browser** via the **Web Speech API** (`SpeechRecognition`). The backend never decodes audio; it receives the already-transcribed text. The raw `MediaRecorder` audio blob is kept only to render the voice-note bubble and support local replay.

### LLM — Language model
`llm_service.generate()` tries providers in order and stops at the first success: **OpenRouter → NVIDIA NIM → Google Gemini**. Providers request strict JSON (`reply`, optional `action`, `memories`, `delete_memories`); malformed output is logged server-side and returned as a generic "temporarily unavailable" message.

### Orchestrator — business-action routing
When the LLM emits an `action`, `session_service` hands it to `app/connectors/orchestrator.py`, the **single bridge** between chat and providers. The orchestrator:
1. validates the action (`whatsapp_message` | `email`),
2. resolves the recipient (person or group) through the **CRM connector**,
3. dispatches to the **WhatsApp** or **Email connector**,
4. returns a clean, provider-neutral result the assistant speaks back.

Provider-specific code never lives in the prompt or the chat endpoint.

```
"Send Rahul a WhatsApp saying the meeting moved to 4"
   → LLM: { action: whatsapp_message, recipient: "Rahul", message: "The meeting has moved to 4 PM." }
   → CRM.resolve("Rahul") → phone +919812345678
   → WhatsApp.send_text(phone, message)
   → "I've sent the WhatsApp message."
```

### Connectors
| Connector | Module | Responsibility |
|---|---|---|
| **CRM** | `app/connectors/crm_connector.py` | Resolve a person/group by name; return phone, email, and identifiers. Reference in-memory `DirectoryCRM` is replaceable by implementing `BaseCRM`. |
| **WhatsApp** | `app/connectors/whatsapp_connector.py` | Send text via the **Meta WhatsApp Cloud API** (stdlib `urllib`). |
| **Email** | `app/connectors/email_connector.py` | Send email via **SMTP** (stdlib `smtplib`) — Gmail, Microsoft/Outlook, or any relay. |

All connectors return an `ActionResult` (`success` + a user-facing message) so failures are reported cleanly instead of leaking raw provider errors.

---

## 🎨 Solar Lava theme

The JARVIS orb and the surrounding UI share one molten identity:

| Role | Hex |
|---|---|
| Main molten body | `#FF8B2B` |
| Bright highlight | `#FFA73B` |
| Hot orange | `#FF6A1C` |
| Bright red accent | `#FC1304` |
| Deep red edge | `#D90206` |

- The **orb** builds depth from these together — molten body, luminous highlights, restrained red-hot edge — with a contained **liquid-wave** interior that reacts to mic/playback energy.
- The **app accents** (buttons, focus rings, active/hover states, borders, indicators, icons, shadows) derive from the same palette, defined as CSS variables in `frontend/src/index.css`.
- Surfaces stay neutral ivory and text stays high-contrast; state changes come from motion and intensity, not from unrelated color swaps.

---

## 📡 Environment variables

Copy `.env.example` → `.env`. In local development the root `.env` is authoritative (it overrides inherited shell values on each backend start); a deployment without a root `.env` uses its platform environment.

### Deployment / frontend origin
| Variable | Purpose | Default |
|---|---|---|
| `FRONTEND_URL` | Deployed frontend origin; also the OpenRouter referer | `http://localhost:5173` |
| `CORS_ORIGINS` | Comma-separated CORS allowlist | `FRONTEND_URL` |

### Runtime limits
| Variable | Purpose | Default |
|---|---|---|
| `MAX_HISTORY_MESSAGES` | How many recent messages go to the LLM (`0` = all) | `10` |
| `AUDIO_MAX_AGE_SECONDS` | Age before generated `.mp3` files are cleaned | `3600` |

### LLM (provide at least one)
| Variable | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | OpenRouter key (provider 1) | — |
| `OPENROUTER_MODEL` | OpenRouter model | `google/gemini-2.0-flash-001` |
| `NVIDIA_API_KEY` | NVIDIA NIM key (provider 2) | — |
| `NVIDIA_MODEL` | NVIDIA model | `meta/llama-3.3-70b-instruct` |
| `GEMINI_API_KEY` | Google Gemini key (provider 3) | — |

### TTS (voice replies)
| Variable | Purpose | Default |
|---|---|---|
| `ELEVENLABS_API_KEY` | ElevenLabs key (provider 1) | — |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice | `myFdf83MJZVXe8yKeA6H` |
| `ELEVENLABS_MODEL_ID` | ElevenLabs model | `eleven_multilingual_v2` |
| `ELEVENLABS_STABILITY` | 0.0–1.0 | `0.62` |
| `ELEVENLABS_SIMILARITY_BOOST` | 0.0–1.0 | `0.78` |
| `ELEVENLABS_STYLE` | 0.0–1.0 | `0.08` |
| `ELEVENLABS_USE_SPEAKER_BOOST` | `true`/`false` | `true` |
| `ELEVENLABS_SPEED` | 0.7–1.2 | `1.0` |
| `TTS_API_KEY` | Custom OpenAI-compatible TTS key (provider 2) | — |
| `TTS_BASE_URL` | Custom TTS endpoint (blank = OpenAI default) | `https://api.openai.com/v1` |
| `TTS_MODEL` | Custom TTS model | `gpt-4o-mini-tts` |
| `TTS_VOICE` | Custom TTS voice | `ash` |
| `TTS_SPEED` | 0.25–4.0 | `1.0` |
| `TTS_INSTRUCTIONS` | Voice instructions (sent only to `gpt-4o-mini-tts*`) | JARVIS delivery profile |
| *(no key)* | gTTS fallback (provider 3) — always tried last | — |

### Connectors (all optional)
| Variable | Purpose |
|---|---|
| `CRM_PROVIDER` | CRM provider name (`directory` = reference in-memory CRM) |
| `CRM_CONTACTS` | JSON array of contacts (see format below) |
| `WA_TOKEN` | WhatsApp Cloud API permanent token |
| `WA_PHONE_NUMBER_ID` | WhatsApp Business phone-number ID |
| `WA_GRAPH_VERSION` | Graph API version (default `v19.0`) |
| `EMAIL_HOST` | SMTP server (e.g. `smtp.gmail.com`, `smtp.office365.com`) |
| `EMAIL_PORT` | SMTP port (default `587`) |
| `EMAIL_USERNAME` | SMTP username / from address |
| `EMAIL_PASSWORD` | SMTP password / app password |
| `EMAIL_USE_TLS` | `true` = STARTTLS (default) |

#### `CRM_CONTACTS` format
A single-line JSON array. A **person** carries `phone` and/or `email`; a **group** carries `kind: "group"` and a `members` array (email addresses, or phone numbers for WhatsApp fan-out).

```json
[
  {"name":"Rahul","phone":"+919812345678","email":"rahul@acme.com","role":"engineer"},
  {"name":"Priya","email":"priya@acme.com","role":"designer"},
  {"name":"Sales Team","kind":"group","members":["rahul@acme.com","priya@acme.com"]}
]
```

---

## 🚀 Setup & run

### Prerequisites
| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| LLM API key | at least one of OpenRouter / NVIDIA / Gemini |
| TTS key | optional (gTTS is the no-key fallback) |
| Browser | Chrome or Edge for voice (Web Speech API) |

```bash
# 1. Clone
git clone https://github.com/Karan7505/Enterprise-Voice-Assistant.git
cd Enterprise-Voice-Assistant

# 2. Configure
cp .env.example .env     # Windows:  copy .env.example .env
#    → edit .env: set at least one LLM key (and optional TTS + connector keys)

# 3. Backend
python -m venv venv
.\venv\Scripts\activate   # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000

# 4. Frontend (new terminal)
cd frontend
npm install
npm run dev
```

- API: **http://localhost:8000** (docs at `/docs`)
- UI: **http://localhost:5173**

The frontend talks to `http://localhost:8000` automatically in development via `frontend/.env.development`. For a separate deployment, set `VITE_API_BASE_URL` at build time; leave it empty when a reverse proxy serves both from one origin.

---

## 🧪 Tests

```bash
# Backend (run from the repo root, with the venv)
python -m unittest discover -s tests

# Frontend (from frontend/)
npm run lint
npm run build
```

Backend suite (`tests/`): `test_config_loading.py`, `test_chat_response_modes.py`, `test_tts_service.py`, `test_connectors.py` (CRM → WhatsApp / Email routing and failure states, using mocks — no live calls).

---

## 📁 Project structure

```
Enterprise-Voice-Assistant/
├── app/
│   ├── main.py                          # FastAPI app, CORS, lifespan (DB + audio init)
│   ├── api/
│   │   └── chat.py                      # /chat /memories /history /clear* /status /audio
│   ├── core/
│   │   ├── config.py                    # env loading + settings (LLM, TTS, connectors)
│   │   └── database.py                  # SQLite schema init + migrations
│   ├── models/
│   │   └── chat_message.py              # ChatMessage (role, content, mode)
│   ├── prompts/
│   │   └── chat_prompt.py               # memory-aware prompt + business-action rules
│   ├── services/
│   │   ├── llm_service.py               # OpenRouter → NVIDIA → Gemini fallback
│   │   ├── tts_service.py               # ElevenLabs → OpenAI-compat → gTTS + cleanup
│   │   ├── session_service.py           # message flow, memory updates, action bridge
│   │   ├── memory_service.py            # long-term memory CRUD
│   │   ├── database_chat_history.py     # conversation history CRUD (+ mode)
│   │   └── context_builder.py           # loads memory context at session start
│   └── connectors/
│       ├── base.py                      # ActionResult / ActionCode
│       ├── crm_connector.py             # contact + group lookup (BaseCRM, DirectoryCRM)
│       ├── whatsapp_connector.py        # WhatsApp Cloud API sender
│       ├── email_connector.py           # SMTP sender
│       └── orchestrator.py              # CRM → connector routing (single entry point)
├── frontend/
│   └── src/
│       ├── App.jsx                      # state, API calls, audio playback, reset logic
│       ├── App.css / index.css          # Solar Lava theme, orb + layout styles
│       └── components/
│           ├── AudioVisualizer.jsx      # JARVIS orb (idle/listen/think/speak + waves)
│           ├── ChatWindow.jsx           # scrollable message list + orb layout
│           ├── ChatInput.jsx            # textarea + MediaRecorder + SpeechRecognition
│           ├── MessageBubble.jsx        # text bubble or voice-note bubble
│           ├── MemorySidebar.jsx        # memory drawer (search, clear, reset)
│           └── Icon.jsx                 # thin-line SVG icon set
├── tests/                               # backend unittest suite
├── .env.example                         # full env template (copy → .env)
└── requirements.txt                     # Python dependencies
```

---

## 📄 API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Send a message → reply, optional `audio_url`, updated `memories`. `response_mode`: `"text"` or `"voice"`. |
| `GET` | `/memories` | Stored long-term memories for the session. |
| `GET` | `/history` | Conversation history (each message includes its `mode`). |
| `POST` | `/clear-chat` | Clear history, keep memories. |
| `POST` | `/clear-memories` | Clear memories, keep history. |
| `POST` | `/clear` | Wipe history + memories. |
| `GET` | `/status` | Health + active LLM/TTS providers and configured connectors. |
| `GET` | `/audio/{filename}` | Stream a generated TTS file. |

---

## ⚠️ Known limitations

- **STT is browser-only.** Transcription uses the Web Speech API, so voice input works best in **Chrome/Edge**; **Firefox has no Web Speech API** (text only). The backend never transcribes audio.
- **Connectors are optional and not live until configured.** Without `WA_TOKEN`/`WA_PHONE_NUMBER_ID` or SMTP credentials (and a populated `CRM_CONTACTS`), business actions return a clean "not configured" result instead of failing. No live send has been performed without real credentials.
- **CRM is a reference in-memory directory.** `DirectoryCRM` reads `CRM_CONTACTS` from config. It is a placeholder for a real CRM; connect one by implementing `BaseCRM` (no core changes needed).
- **WhatsApp uses the Meta Cloud API.** The number in `WA_PHONE_NUMBER_ID` must be a WhatsApp Business/Cloud-API number; outbound text requires an approved template in some cases.
- **Email requires valid SMTP credentials.** Gmail/Microsoft with 2FA need an **app password**, not the account password.
- **Replayed voice notes are in-memory only.** After a reload, reloaded voice messages render as voice-note bubbles but the original recorded audio is not persisted (playback is a no-op); the transcript stays internal either way.
- **SQLite.** Fine for single-user/small team. Migrate to PostgreSQL for multi-user production.
- **Business actions are not stored as send logs** — only the chat exchange is persisted.

---

## 🔒 Security notes

- API keys and connector credentials load **only** from `.env` (in `.gitignore`) — never hardcoded, never sent to the frontend.
- Provider errors are logged server-side; the user receives generic, provider-neutral messages.
- Generated audio lives in the gitignored `audio/` directory; partial files are removed on provider failure and stale files are cleaned by `AUDIO_MAX_AGE_SECONDS`.

---

<div align="center">

Built with **multi-provider LLM/TTS fallbacks** · **FastAPI** · **React** · **SQLite** · **Solar Lava**

</div>
