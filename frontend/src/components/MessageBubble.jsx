import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./Icon";

function MessageBubble({
  sender,
  text,
  displayText = text,
  audioUrl,
  playAudio,
  type,
  responseMode = "text",
  voiceAudioBlob,
  voiceDuration,
  userInitial = "U",
}) {
  const isUser = sender === "You";
  const isSystem = sender === "System";
  const [copyStatus, setCopyStatus] = useState("idle");
  const [vnPlaying, setVnPlaying] = useState(false);
  const [vnProgress, setVnProgress] = useState(0);
  const vnAudioRef = useRef(null);
  const vnObjectUrlRef = useRef(null);
  const copyTimerRef = useRef(null);

  const isVoiceNote = type === "audio" && isUser;
  const displaySender = !isUser && !isSystem ? "JARVIS" : sender;

  const disposeVoiceAudio = useCallback(() => {
    const audio = vnAudioRef.current;
    if (audio) {
      audio.onplay = null;
      audio.onpause = null;
      audio.ontimeupdate = null;
      audio.onended = null;
      audio.onerror = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      vnAudioRef.current = null;
    }
    if (vnObjectUrlRef.current) {
      URL.revokeObjectURL(vnObjectUrlRef.current);
      vnObjectUrlRef.current = null;
    }
  }, []);

  useEffect(() => () => {
    clearTimeout(copyTimerRef.current);
    disposeVoiceAudio();
  }, [disposeVoiceAudio]);

  const handleCopy = async () => {
    clearTimeout(copyTimerRef.current);
    try {
      if (!navigator.clipboard) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(text);
      setCopyStatus("copied");
    } catch (error) {
      console.error("Clipboard copy failed:", error);
      setCopyStatus("error");
    }
    copyTimerRef.current = setTimeout(() => setCopyStatus("idle"), 2000);
  };

  const formatDuration = (seconds) => {
    if (!seconds || seconds <= 0) return "0:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${String(s).padStart(2, "0")}`;
  };

  const toggleVoiceNote = () => {
    if (!voiceAudioBlob) return;

    if (vnPlaying) {
      vnAudioRef.current?.pause();
      return;
    }

    if (vnAudioRef.current) {
      vnAudioRef.current.play().catch(() => setVnPlaying(false));
      return;
    }

    const objectUrl = URL.createObjectURL(voiceAudioBlob);
    const audio = new Audio(objectUrl);
    vnObjectUrlRef.current = objectUrl;
    vnAudioRef.current = audio;
    setVnProgress(0);

    audio.onplay = () => setVnPlaying(true);
    audio.onpause = () => setVnPlaying(false);
    audio.ontimeupdate = () => {
      if (audio.duration) {
        setVnProgress((audio.currentTime / audio.duration) * 100);
      }
    };
    audio.onended = () => {
      setVnPlaying(false);
      setVnProgress(0);
      disposeVoiceAudio();
    };
    audio.onerror = () => {
      setVnPlaying(false);
      setVnProgress(0);
      disposeVoiceAudio();
    };

    audio.play().catch(() => {
      setVnPlaying(false);
      disposeVoiceAudio();
    });
  };

  return (
    <div className={`message-row ${isUser ? "user-row" : "ai-row"}${isSystem ? " system-row" : ""}`}>
      {!isUser && (
        <div className={`avatar ${isSystem ? "system-avatar" : "ai-avatar"}`} aria-hidden="true">
          {isSystem ? (
            <Icon name="alert" size={18} />
          ) : (
            <span className="jarvis-message-orb" />
          )}
        </div>
      )}

      {isVoiceNote ? (
        <div className="message-bubble user-message voice-note-bubble">
          <div className="voice-note-content">
            <button
              type="button"
              className="vn-play-btn"
              onClick={toggleVoiceNote}
              title={vnPlaying ? "Pause" : "Play"}
              aria-label={vnPlaying ? "Pause voice note" : "Play voice note"}
              aria-pressed={vnPlaying}
            >
              <Icon name={vnPlaying ? "pause" : "play"} size={20} />
            </button>

            <div className="vn-waveform">
              <div
                className="vn-waveform-track"
                role="progressbar"
                aria-label="Voice note playback progress"
                aria-valuemin="0"
                aria-valuemax="100"
                aria-valuenow={Math.round(vnProgress)}
              >
                <div
                  className="vn-waveform-progress"
                  style={{ width: `${vnProgress}%` }}
                ></div>
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

            <span className="vn-mic-icon" aria-hidden="true">
              <Icon name="mic" size={17} />
            </span>
          </div>
        </div>
      ) : (
        <div className={`message-bubble ${isUser ? "user-message" : isSystem ? "system-message" : "ai-message"}${responseMode === "voice" && !isUser && !isSystem ? " voice-response" : ""}`}>
          <div className="message-header">
            <span className="sender-name">{displaySender}</span>
            <div className="message-actions">
              {!isUser && responseMode === "voice" && audioUrl && (
                <button
                  type="button"
                  className="action-icon-btn"
                  onClick={() => playAudio(audioUrl)}
                  title="Replay voice"
                  aria-label="Replay voice response"
                >
                  <Icon name="volume" size={16} />
                </button>
              )}
              <button
                type="button"
                className="action-icon-btn"
                onClick={handleCopy}
                title={copyStatus === "copied" ? "Copied" : copyStatus === "error" ? "Copy failed" : "Copy text"}
                aria-label={copyStatus === "copied" ? "Text copied" : copyStatus === "error" ? "Could not copy text" : "Copy text"}
              >
                <Icon
                  name={copyStatus === "copied" ? "check" : copyStatus === "error" ? "alert" : "copy"}
                  size={16}
                />
              </button>
            </div>
          </div>

          <div className="message-text">{displayText}</div>
        </div>
      )}

      {isUser && (
        <div className="avatar user-avatar" aria-hidden="true">
          <span>{userInitial}</span>
        </div>
      )}
    </div>
  );
}

export default MessageBubble;
