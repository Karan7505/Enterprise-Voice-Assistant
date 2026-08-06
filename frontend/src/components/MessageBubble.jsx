import { useState, useRef } from "react";

function MessageBubble({ sender, text, audioUrl, playAudio, type, voiceAudioUrl, voiceDuration }) {
  const isUser = sender === "You";
  const isSystem = sender === "System";
  const [copied, setCopied] = useState(false);
  const [vnPlaying, setVnPlaying] = useState(false);
  const [vnProgress, setVnProgress] = useState(0);
  const vnAudioRef = useRef(null);
  const vnIntervalRef = useRef(null);

  const isVoiceNote = type === "audio" && isUser;

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatDuration = (seconds) => {
    if (!seconds || seconds <= 0) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  };

  const toggleVoiceNote = () => {
    if (!voiceAudioUrl) return;

    if (vnPlaying) {
      if (vnAudioRef.current) {
        vnAudioRef.current.pause();
      }
      clearInterval(vnIntervalRef.current);
      setVnPlaying(false);
      return;
    }

    const audio = new Audio(voiceAudioUrl);
    vnAudioRef.current = audio;
    setVnProgress(0);

    audio.onplay = () => setVnPlaying(true);
    audio.ontimeupdate = () => {
      if (audio.duration) {
        setVnProgress((audio.currentTime / audio.duration) * 100);
      }
    };
    audio.onended = () => {
      setVnPlaying(false);
      setVnProgress(0);
      clearInterval(vnIntervalRef.current);
    };
    audio.onerror = () => {
      setVnPlaying(false);
      setVnProgress(0);
    };

    audio.play().catch(() => setVnPlaying(false));
  };

  return (
    <div className={`message-row ${isUser ? "user-row" : "ai-row"}`}>
      {!isUser && (
        <div className="avatar ai-avatar">
          🤖
        </div>
      )}

      {isVoiceNote ? (
        /* WhatsApp-style Voice Note Bubble */
        <div className="message-bubble user-message voice-note-bubble">
          <div className="voice-note-content">
            <button
              className="vn-play-btn"
              onClick={toggleVoiceNote}
              title={vnPlaying ? "Pause" : "Play"}
            >
              {vnPlaying ? (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                  <rect x="6" y="4" width="4" height="16" rx="1" />
                  <rect x="14" y="4" width="4" height="16" rx="1" />
                </svg>
              ) : (
                <svg width="20" height="20" viewBox="0 0 24 24" fill="white">
                  <polygon points="6 3 20 12 6 21 6 3" />
                </svg>
              )}
            </button>

            <div className="vn-waveform">
              <div className="vn-waveform-track">
                <div
                  className="vn-waveform-progress"
                  style={{ width: `${vnProgress}%` }}
                ></div>
                {/* Static waveform bars */}
                <div className="vn-bars">
                  {Array.from({ length: 28 }).map((_, i) => (
                    <span
                      key={i}
                      className="vn-bar"
                      style={{
                        height: `${Math.sin(i * 0.7) * 40 + 50}%`,
                      }}
                    ></span>
                  ))}
                </div>
              </div>
              <span className="vn-duration">
                {formatDuration(voiceDuration || 0)}
              </span>
            </div>

            <span className="vn-mic-icon">🎤</span>
          </div>
        </div>
      ) : (
        /* Standard Text Message Bubble */
        <div className={`message-bubble ${isUser ? "user-message" : isSystem ? "system-message" : "ai-message"}`}>
          <div className="message-header">
            <span className="sender-name">{sender}</span>
            <div className="message-actions">
              {!isUser && audioUrl && (
                <button
                  className="action-icon-btn"
                  onClick={() => playAudio(audioUrl)}
                  title="Replay Voice"
                >
                  🔊
                </button>
              )}
              <button
                className="action-icon-btn"
                onClick={handleCopy}
                title="Copy text"
              >
                {copied ? "✓" : "📋"}
              </button>
            </div>
          </div>

          <div className="message-text">{text}</div>
        </div>
      )}

      {isUser && (
        <div className="avatar user-avatar">
          👤
        </div>
      )}
    </div>
  );
}

export default MessageBubble;
