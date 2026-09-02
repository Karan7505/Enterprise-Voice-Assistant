<div align="center">

# VOICE ASSISTANT

**A production-ready AI voice assistant with persistent long-term memory, voice notes, and a premium voice-first interface.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.140-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev)
[![LLM](https://img.shields.io/badge/LLM-Multi--Provider-4285F4?style=for-the-badge)](#-tech-stack)
[![TTS](https://img.shields.io/badge/TTS-Multi--Provider-FF6B35?style=for-the-badge)](#-tech-stack)
[![SQLite](https://img.shields.io/badge/SQLite-Memory-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

<br/>

*Speak naturally. Be remembered. Get intelligent responses.*

[🚀 Quick Start](#-quick-start) · [✨ Features](#-features) · [🏗️ Architecture](#-architecture) · [📡 API Reference](#-api-reference) · [🧠 How Memory Works](#-how-memory-works)

</div>

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🎤 WhatsApp-Style Voice Notes
Press the microphone button to record your voice. Instead of showing raw transcription text, it renders a **beautiful voice note bubble** — just like WhatsApp — with a play/pause button, animated waveform, mic icon, and duration timer. The AI understands your speech while you stay in full control of what's displayed.

</td>
<td width="50%">

### 🧠 Persistent Long-Term Memory
The AI **automatically extracts facts** from every conversation and stores them in SQLite. Your name, role, company, location, preferences, projects — all remembered across sessions, page refreshes, and server restarts. Never re-introduce yourself again.

</td>
</tr>
<tr>
<td width="50%">

### 🔊 AI Voice Replies
Voice replies are synthesized through an ordered fallback chain: **ElevenLabs**, a **custom OpenAI-compatible TTS endpoint**, then **gTTS**. Typed messages are text-only and do not invoke TTS.

</td>
<td width="50%">

### 💬 Dual Input Modes
**Voice** or **text** — your choice. Typed messages receive text-only replies. Voice messages appear as audio notes with a subtle transcript and receive spoken replies. Both modes use the identical conversation and long-term-memory pipeline.

</td>
</tr>
<tr>
<td width="50%">

### 🧩 Memory Sidebar
A slide-out panel that shows **all stored memories in real time** as key-value cards. Search through them, watch new ones appear as you chat, and clear everything with one click if you want a fresh start.

</td>
<td width="50%">

### Premium Voice-First UI
A warm ivory interface with a centered JARVIS workspace, a floating composer, an on-demand memory drawer, and a clean orange orb with distinct idle, listening, thinking, and speaking states.

</td>
</tr>
</table>

---

## 🏗️ Architecture

```
Enterprise-Voice-Assistant/
│
├── 📂 app/                              # FastAPI Backend
│   ├── main.py                          # App entry point + CORS middleware
│   │
│   ├── 📂 api/
│   │   └── chat.py                      # REST endpoints: /chat /memories /history /clear /audio
│   │
│   ├── 📂 core/
│   │   ├── config.py                    # Loads API keys from .env
│   │   └── database.py                  # SQLite schema init (messages + memories tables)
│   │
│   ├── 📂 models/
│   │   └── chat_message.py              # Pydantic ChatMessage model
│   │
│   ├── 📂 prompts/
│   │   └── chat_prompt.py               # Memory-aware enterprise system prompt
│   │
│   └── 📂 services/
│       ├── llm_service.py               # OpenRouter, NVIDIA, and Gemini fallbacks
│       ├── tts_service.py               # Multi-provider TTS + generated .mp3 cleanup
│       ├── memory_service.py            # SQLite CRUD for long-term memories
│       ├── database_chat_history.py     # SQLite CRUD for conversation history
│       ├── context_builder.py           # Loads memory context at session start
│       └── session_service.py           # Orchestrates message flow + memory updates
│
├── 📂 frontend/                         # React + Vite Frontend
│   └── 📂 src/
│       ├── App.jsx                      # Root: state management, API calls, audio playback
│       ├── App.css                      # Component styles + voice note CSS
│       ├── index.css                    # CSS variables, fonts, global animations
│       │
│       └── 📂 components/
│           ├── ChatWindow.jsx           # Scrollable message list
│           ├── MessageBubble.jsx        # Text bubble OR voice note bubble (WhatsApp-style)
│           ├── ChatInput.jsx            # Textarea + MediaRecorder mic + SpeechRecognition
│           ├── AudioVisualizer.jsx      # Four-state animated assistant orb
│           ├── Icon.jsx                 # Shared thin-line SVG icon set
│           └── MemorySidebar.jsx        # On-demand memory drawer with search + reset
│
├── .env.example                         # API key template (copy → .env)
├── requirements.txt                     # Python dependencies
└── README.md
```

---

## 🔄 How It All Flows

```
USER SPEAKS
    │
    ▼
MediaRecorder (audio blob)  +  SpeechRecognition (transcript)
    │                                │
    │                                ▼
    │                      Voice Note Bubble shown in chat
    │                      (play/pause + waveform + duration)
    │
    ▼
Transcript sent to FastAPI /chat in voice-response mode
    │
    ▼
session_service.py
    ├── Loads stored memories from SQLite
    ├── Builds prompt: memories + history + message
    └── Calls the configured LLM providers in fallback order
            │
            ▼
        {
          "reply": "Your name is Karan!",
          "memories": { "name": "Karan" },
          "delete_memories": []
        }
            │
            ├── Save new memories → SQLite
            ├── Save message + reply → SQLite
            └── Voice mode only: generate speech through the TTS fallback chain → .mp3
                    │
                    ▼
              Frontend receives reply + optional audio_url + memories
                    │
                    ├── AI text bubble rendered in both modes
                    ├── Voice-mode audio plays automatically
                    └── Memory sidebar updates live
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 or higher |
| Node.js | 18 or higher |
| LLM API key | At least one of OpenRouter, NVIDIA NIM, or Google Gemini |
| TTS API key | Optional; gTTS is the no-key fallback |

---

### Step 1 — Clone the Repository

```bash
git clone https://github.com/Karan7505/Enterprise-Voice-Assistant.git
cd Enterprise-Voice-Assistant
```

### Step 2 — Configure API Keys

```bash
cp .env.example .env
```

Open `.env` and fill in at least one LLM key. TTS keys are optional:

```env
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=google/gemini-2.0-flash-001
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=myFdf83MJZVXe8yKeA6H
FRONTEND_URL=http://localhost:5173
CORS_ORIGINS=http://localhost:5173
```

In local development, the root `.env` file is authoritative: its values
override inherited terminal or VS Code environment variables each time the
backend starts. The normal workflow is simply **edit `.env` → save → restart
the backend**. Deployments without a root `.env` continue to use their platform
environment variables.

The default voice profile favors a warm, calm, confident male delivery at a
natural medium pace. ElevenLabs exposes precise controls through its voice ID
and stability/style settings. The custom OpenAI-compatible path defaults to
`gpt-4o-mini-tts` with the `ash` voice and uses the conversational JARVIS
delivery instructions from `TTS_INSTRUCTIONS`; it requires a valid
`TTS_API_KEY`. All values are configurable in `.env.example`.

### TTS provider selection rules

TTS runs only when `response_mode` is `"voice"`; text-mode replies never create
audio. For each voice reply, the backend tries the following providers in this
exact order and stops at the first successful synthesis:

1. **ElevenLabs** — attempted when `ELEVENLABS_API_KEY` is non-empty and not a
   `your_...` placeholder.
2. **Custom/OpenAI-compatible TTS** — attempted when `TTS_API_KEY` is valid.
   `TTS_BASE_URL` is optional (a blank value uses the OpenAI SDK default);
   `TTS_MODEL`, `TTS_VOICE`, and `TTS_SPEED` select the request settings.
   `TTS_INSTRUCTIONS` is sent only to `gpt-4o-mini-tts*` models.
3. **gTTS** — always attempted last and requires no API key.

If a provider fails, any partial `.mp3` is removed before the next provider is
tried. If gTTS also fails, the API preserves the text reply and returns an empty
`audio_url`.

> Voice character is provider- and voice-dependent. Audition an available male
> voice and set `ELEVENLABS_VOICE_ID` for the closest neutral-English match.
> gTTS is retained for availability but cannot control voice identity or style.

> ⚠️ **Never commit your `.env` file.** It is already in `.gitignore`.

### Step 3 — Set Up the Backend

```bash
# Create a virtual environment
python -m venv venv

# Activate it — Windows
.\venv\Scripts\activate

# Activate it — macOS / Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Step 4 — Run the Backend

```bash
# With the virtual environment activated
python -m uvicorn app.main:app --reload --port 8000

# Or on Windows, without activating it
.\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The API is now live at `http://localhost:8000`.  
Interactive docs are available at `http://localhost:8000/docs`.

### Step 5 — Set Up and Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **`http://localhost:5173`** in your browser (Chrome or Edge recommended for Web Speech API support).

Local development automatically uses `http://localhost:8000` from `frontend/.env.development`. For a separate deployment, set `VITE_API_BASE_URL` to the public backend URL in the hosting environment; leave it empty when a reverse proxy serves frontend and API from one origin.

---

## 📡 API Reference

### `POST /chat`

Send a message and receive an AI reply and updated memories. Set
`response_mode` to `"text"` for a text-only reply or `"voice"` for a spoken reply.

**Request:**
```json
{
  "message": "My name is Karan and I work at Google as a software architect.",
  "session_id": "default",
  "response_mode": "text"
}
```

**Response:**
```json
{
  "reply": "Great to meet you, Karan! As a software architect at Google, you must be working on some fascinating systems. How can I assist you today?",
  "audio_url": "",
  "memories": {
    "name": "Karan",
    "company": "Google",
    "job_title": "Software Architect"
  }
}
```

---

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/chat` | Send a text- or voice-mode message → get reply, optional audio URL, and updated memories |
| `GET` | `/memories` | Fetch all stored long-term memories for the session |
| `GET` | `/history` | Fetch full conversation history for the session |
| `POST` | `/clear-chat` | Clear conversation history while preserving long-term memories |
| `POST` | `/clear-memories` | Clear long-term memories while preserving chat history |
| `POST` | `/clear` | Wipe all history and memories (fresh start) |
| `GET` | `/status` | Health check — returns engine names and status |
| `GET` | `/audio/{filename}` | Stream a generated TTS audio file |

---

## 🧠 How Memory Works

The assistant uses structured model output plus validation to keep memory updates controlled:

### 1. Structured JSON with safe validation
Providers are asked for a JSON object containing `reply`, `memories`, and `delete_memories`. The backend validates the shape before changing history or memory. Malformed output is logged server-side and returned as a generic temporary-unavailable response instead of an uncontrolled 500.

### 2. Memory-Aware Prompt
Every request injects the **full memory store** into the system prompt so the AI can reference what it already knows:

```
=== YOUR STORED LONG-TERM MEMORIES ===
{
  "name": "Karan",
  "company": "Google",
  "job_title": "Software Architect",
  "location": "California"
}

=== LATEST USER MESSAGE ===
What's my name?

→ AI replies: "Your name is Karan!" (pulled from memory, not hallucinated)
```

### 3. Automatic Extraction
If the user says something new, the model extracts it:
```json
User: "I just moved to New York"

The active LLM returns:
{
  "reply": "New York is a fantastic city! How are you settling in?",
  "memories": { "location": "New York" },
  "delete_memories": []
}
```
The `location` memory is then **upserted** in SQLite — overwriting "California" with "New York".

### 4. Persistence
Memories survive:
- ✅ Page refreshes
- ✅ Server restarts
- ✅ New browser sessions

Because they live in **SQLite**, not in-memory state.

Only the most recent `MAX_HISTORY_MESSAGES` are sent back to the model for conversational context (default `10`; `0` means all), while the full chat history remains in SQLite. `/clear-chat` and `/clear-memories` deliberately reset those stores independently.

---

## 🎤 Voice Note Architecture

The voice note system runs **two browser APIs in parallel** when you press the microphone:

| API | Purpose | Output |
|---|---|---|
| `MediaRecorder` | Captures raw audio from microphone | `Blob` → local audio URL |
| `SpeechRecognition` | Transcribes speech to text in real-time | Transcript string |

When you press **Stop**:
1. The audio `Blob` is converted to a local URL and rendered as a **voice note bubble** with a play/pause button and waveform visualizer.
2. The transcript is sent to the AI and shown beneath the voice note in a subtle treatment.
3. The AI processes the transcript through the same memory-aware pipeline as typed text, then replies with voice and a subtle text transcript.

Voice-note object URLs are created only for playback and revoked on completion, failure, or component cleanup. Recorder tracks, speech recognition, timers, and playback objects are also stopped when their components unmount.

The transcript provides a lightweight confirmation of what was understood without turning the voice flow into a conventional text chat.

---

## 🎨 Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **LLM** | OpenRouter → NVIDIA NIM → Google Gemini | Natural language understanding + memory extraction with provider fallback |
| **TTS** | ElevenLabs → Custom/OpenAI-compatible TTS → gTTS | Voice-mode text-to-speech with graceful fallback |
| **Backend Framework** | FastAPI + Uvicorn | REST API server |
| **Database** | SQLite | Zero-config persistent storage for memories + history |
| **Frontend Framework** | React 18 + Vite | Component-based UI with fast HMR |
| **Styling** | Vanilla CSS | Responsive light-mode system, CSS variables, and stateful orb animations |
| **Voice Recording** | MediaRecorder API | Audio capture for voice notes |
| **Speech-to-Text** | Web Speech API | Real-time transcription in the browser |
| **HTTP Client** | Axios | Frontend → Backend API calls |

---

## 🌐 Browser Compatibility

| Browser | Voice Recording | Speech Recognition | Recommended |
|---|---|---|---|
| Chrome 90+ | ✅ | ✅ | ⭐ Best |
| Edge 90+ | ✅ | ✅ | ⭐ Best |
| Firefox | ✅ | ❌ (no Web Speech API) | ⚠️ Text only |
| Safari 15.4+ | ✅ | ✅ | ✅ Good |

> For the full voice note + transcription experience, use **Chrome** or **Edge**.

---

## 🔒 Security & Production Notes

- **API Keys**: Loaded exclusively from `.env` — never hardcoded. The `.env` file is in `.gitignore`.
- **CORS and OpenRouter attribution**: Set `FRONTEND_URL` to the exact deployed frontend origin. `CORS_ORIGINS` accepts a comma-separated allowlist and defaults to `FRONTEND_URL`; OpenRouter uses `FRONTEND_URL` as its referer.
- **Frontend API URL**: Set `VITE_API_BASE_URL` at frontend build time when the API is hosted on another origin.
- **Audio Files**: Generated files are stored in the gitignored `audio/` directory. Partial files are removed immediately after provider failures, and completed `.mp3` files older than `AUDIO_MAX_AGE_SECONDS` (default one hour) are cleaned at startup and before generation.
- **SQLite**: Suitable for single-user/small team deployments. For multi-user production, migrate to PostgreSQL.

---

## 🤝 Contributing

Contributions are welcome! Here's how to get started:

1. **Fork** the repository
2. **Create a branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** and ensure the app runs correctly
4. **Commit**: `git commit -m "feat: describe your change"`
5. **Push**: `git push origin feature/your-feature-name`
6. **Open a Pull Request**

---

## 📄 License

This project is licensed under the **MIT License** — free to use, modify, and distribute for personal or commercial projects.

---

<div align="center">

Built with ❤️ using **multi-provider LLM/TTS fallbacks** · **FastAPI** · **React** · **SQLite**

*If this project helped you, consider giving it a ⭐ on GitHub!*

</div>
