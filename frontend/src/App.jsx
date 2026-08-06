import { useState, useEffect, useRef } from "react";
import axios from "axios";
import "./App.css";

import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import MemorySidebar from "./components/MemorySidebar";
import AudioVisualizer from "./components/AudioVisualizer";

const API_BASE = "http://127.0.0.1:8000";

function App() {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [memories, setMemories] = useState({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const audioRef = useRef(null);

  // Load chat history & memories on mount
  useEffect(() => {
    fetchHistoryAndMemories();
  }, []);

  const fetchHistoryAndMemories = async () => {
    try {
      const [histRes, memRes] = await Promise.all([
        axios.get(`${API_BASE}/history`),
        axios.get(`${API_BASE}/memories`),
      ]);
      if (histRes.data && histRes.data.messages) {
        setMessages(histRes.data.messages);
      }
      if (memRes.data && memRes.data.memories) {
        setMemories(memRes.data.memories);
      }
    } catch (err) {
      console.error("Failed to load initial history or memories", err);
    }
  };

  const playAudio = async (url) => {
    if (!url) return;
    try {
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const fullUrl = url.startsWith("http") ? url : `${API_BASE}${url}`;
      const audio = new Audio(fullUrl);
      audioRef.current = audio;

      audio.onplay = () => setIsPlaying(true);
      audio.onended = () => setIsPlaying(false);
      audio.onerror = () => setIsPlaying(false);

      await audio.play();
    } catch (err) {
      console.error("Audio playback error:", err);
      setIsPlaying(false);
    }
  };

  const sendMessage = async (textToSend) => {
    const userMessage = (textToSend || message).trim();
    if (!userMessage) return;

    setMessages((prev) => [
      ...prev,
      {
        sender: "You",
        text: userMessage,
        type: "text",
      },
    ]);

    setMessage("");

    await sendToApi(userMessage);
  };

  const sendVoiceMessage = async (transcript, voiceBlobUrl, duration) => {
    if (!transcript) return;

    // Show as voice note bubble (no text shown to user)
    setMessages((prev) => [
      ...prev,
      {
        sender: "You",
        text: transcript,  // hidden, only sent to AI
        type: "audio",
        voiceAudioUrl: voiceBlobUrl,
        voiceDuration: duration,
      },
    ]);

    await sendToApi(transcript);
  };

  const sendToApi = async (userMessage) => {
    try {
      const response = await axios.post(`${API_BASE}/chat`, {
        message: userMessage,
      });

      const replyText = response.data.reply;
      const audioUrl = response.data.audio_url;
      const updatedMemories = response.data.memories;

      setMessages((prev) => [
        ...prev,
        {
          sender: "AI",
          text: replyText,
          audioUrl: audioUrl,
          type: "text",
        },
      ]);

      if (updatedMemories) {
        setMemories(updatedMemories);
      }

      if (audioUrl) {
        playAudio(audioUrl);
      }
    } catch (error) {
      console.error("API error:", error);
      const detail = error.response?.data?.detail || "Unable to contact the assistant server.";
      setMessages((prev) => [
        ...prev,
        {
          sender: "System",
          text: `Error: ${detail}`,
          type: "text",
        },
      ]);
    }
  };

  const handleClearSession = async () => {
    if (!window.confirm("Are you sure you want to reset all conversation history and extracted memories?")) {
      return;
    }
    try {
      await axios.post(`${API_BASE}/clear`);
      setMessages([]);
      setMemories({});
      if (audioRef.current) {
        audioRef.current.pause();
      }
      setIsPlaying(false);
    } catch (err) {
      console.error("Failed to clear session", err);
    }
  };

  return (
    <div className="app-layout">
      <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        <header className="app-header">
          <div className="brand-section">
            <div className="brand-logo">🎙️</div>
            <div className="brand-info">
              <h1>Enterprise Voice Assistant</h1>
              <div className="brand-subtitle">
                <span>Gemini 2.0 & ElevenLabs</span>
                <span className="engine-tag">Active</span>
              </div>
            </div>
          </div>

          <div className="header-actions">
            <button
              className="header-btn memory-toggle-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              🧠 Memories ({Object.keys(memories).length})
            </button>
          </div>
        </header>

        <main className="main-content">
          <AudioVisualizer isPlaying={isPlaying} isListening={isListening} />

          <ChatWindow
            messages={messages}
            playAudio={playAudio}
            onSelectSuggestion={(prompt) => {
              setMessage(prompt);
              sendMessage(prompt);
            }}
          />

          <ChatInput
            message={message}
            setMessage={setMessage}
            sendMessage={() => sendMessage()}
            sendVoiceMessage={sendVoiceMessage}
            isListening={isListening}
            setIsListening={setIsListening}
          />
        </main>
      </div>

      <MemorySidebar
        memories={memories}
        isOpen={sidebarOpen}
        toggleSidebar={() => setSidebarOpen(false)}
        onClearSession={handleClearSession}
      />
    </div>
  );
}

export default App;