<div align="center">

# 🎙️ Enterprise Voice Assistant

**A production-ready AI voice assistant with persistent long-term memory, WhatsApp-style voice notes, and a stunning glassmorphic UI.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.140-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-6-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev)
[![Google Gemini](https://img.shields.io/badge/Gemini-Flash-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![ElevenLabs](https://img.shields.io/badge/ElevenLabs-TTS-FF6B35?style=for-the-badge)](https://elevenlabs.io)
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
Every AI response is **synthesized to natural speech** using ElevenLabs' multilingual model. Responses play automatically so you can have a fully hands-free conversation with your enterprise assistant.

</td>
<td width="50%">

### 💬 Dual Input Modes
**Voice** or **text** — your choice. Typed messages appear as clean text bubbles. Voice messages appear as audio note bubbles. Both are sent to the AI for understanding, but the display is completely different — smart and intentional.

</td>
</tr>
<tr>
<td width="50%">

### 🧩 Memory Sidebar
A slide-out panel that shows **all stored memories in real time** as key-value cards. Search through them, watch new ones appear as you chat, and clear everything with one click if you want a fresh start.

</td>
<td width="50%">

### 🌑 Premium Glassmorphic UI
A stunning dark-mode interface with **backdrop blur, gradient meshes, micro-animations, and a pulsing audio visualizer**. Built with vanilla CSS — no frameworks, just pure precision.

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
│       ├── llm_service.py               # Gemini API wrapper (JSON mode + model fallback)
│       ├── tts_service.py               # ElevenLabs TTS → .mp3 file
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
│           ├── AudioVisualizer.jsx      # Animated orb (listening / playing states)
│           └── MemorySidebar.jsx        # Slide-out memory panel with search + clear
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
Transcript sent silently to FastAPI /chat
    │
    ▼
session_service.py
    ├── Loads stored memories from SQLite
    ├── Builds prompt: memories + history + message
    └── Calls Gemini (JSON mode enforced)
            │
            ▼
        {
          "reply": "Your name is Karan!",
          "memories": { "name": "Karan" }
        }
            │
            ├── Save new memories → SQLite
            ├── Save message + reply → SQLite
            └── Generate speech → ElevenLabs → .mp3
                    │
                    ▼
              Frontend receives reply + audio_url + memories
                    │
                    ├── AI text bubble rendered
                    ├── Audio plays automatically
                    └── Memory sidebar updates live
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 or higher |
| Node.js | 18 or higher |
| [Google Gemini API Key](https://aistudio.google.com/apikey) | Free tier available |
| [ElevenLabs API Key](https://elevenlabs.io) | Free tier available |

---

### Step 1 — Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/Enterprise-Voice-Assistant.git
cd Enterprise-Voice-Assistant
```

### Step 2 — Configure API Keys

```bash
cp .env.example .env
```

Open `.env` and fill in your keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
```

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
uvicorn app.main:app --reload --port 8000
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

---

## 📡 API Reference

### `POST /chat`

Send a message and receive an AI reply with audio and updated memories.

**Request:**
```json
{
  "message": "My name is Karan and I work at Google as a software architect.",
  "session_id": "default"
}
```

**Response:**
```json
{
  "reply": "Great to meet you, Karan! As a software architect at Google, you must be working on some fascinating systems. How can I assist you today?",
  "audio_url": "/audio/a3f92b1c.mp3",
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
| `POST` | `/chat` | Send a message → get reply + audio URL + updated memories |
| `GET` | `/memories` | Fetch all stored long-term memories for the session |
| `GET` | `/history` | Fetch full conversation history for the session |
| `POST` | `/clear` | Wipe all history and memories (fresh start) |
| `GET` | `/status` | Health check — returns engine names and status |
| `GET` | `/audio/{filename}` | Stream a generated TTS audio file |

---

## 🧠 How Memory Works

The assistant uses a **two-phase JSON extraction pipeline** to make memory reliable:

### 1. Strict JSON Mode
Gemini is called with `response_mime_type="application/json"` enforced at the API level — the model *cannot* return plain text. This eliminates all JSON parsing failures.

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

Gemini returns:
{
  "reply": "New York is a fantastic city! How are you settling in?",
  "memories": { "location": "New York" }
}
```
The `location` memory is then **upserted** in SQLite — overwriting "California" with "New York".

### 4. Persistence
Memories survive:
- ✅ Page refreshes
- ✅ Server restarts
- ✅ New browser sessions

Because they live in **SQLite**, not in-memory state.

---

## 🎤 Voice Note Architecture

The voice note system runs **two browser APIs in parallel** when you press the microphone:

| API | Purpose | Output |
|---|---|---|
| `MediaRecorder` | Captures raw audio from microphone | `Blob` → local audio URL |
| `SpeechRecognition` | Transcribes speech to text in real-time | Transcript string |

When you press **Stop**:
1. The audio `Blob` is converted to a local URL and rendered as a **voice note bubble** with a play/pause button and waveform visualizer.
2. The transcript is **silently sent to the AI** — it never appears as text in the chat.
3. The AI processes the transcript as a normal message and replies.

This mirrors exactly how WhatsApp works: you see the audio file, not the transcription.

---

## 🎨 Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **LLM** | Google Gemini Flash | Natural language understanding + memory extraction |
| **TTS** | ElevenLabs (George voice) | Text-to-speech for AI replies |
| **Backend Framework** | FastAPI + Uvicorn | REST API server |
| **Database** | SQLite | Zero-config persistent storage for memories + history |
| **Frontend Framework** | React 18 + Vite | Component-based UI with fast HMR |
| **Styling** | Vanilla CSS | Glassmorphism, CSS variables, custom animations |
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
- **CORS**: Restricted to `localhost:5173` by default. Update `allow_origins` in `app/main.py` for your production domain.
- **Audio Files**: Stored in the `audio/` directory (gitignored). Consider adding a cleanup cron job for old files in production.
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

Built with ❤️ using **Google Gemini** · **ElevenLabs** · **FastAPI** · **React**

*If this project helped you, consider giving it a ⭐ on GitHub!*

</div>
