import { useState, useEffect, useRef } from "react";

function ChatInput({ message, setMessage, sendMessage, sendVoiceMessage, isListening, setIsListening }) {
  const [isSending, setIsSending] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const transcriptRef = useRef("");
  const timerRef = useRef(null);
  const streamRef = useRef(null);

  // Initialize SpeechRecognition
  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onresult = (event) => {
        let finalTranscript = "";
        for (let i = 0; i < event.results.length; i++) {
          finalTranscript += event.results[i][0].transcript;
        }
        transcriptRef.current = finalTranscript;
      };

      recognition.onerror = (err) => {
        console.error("Speech recognition error:", err);
      };

      recognition.onend = () => {
        // Will be restarted if still recording
      };

      recognitionRef.current = recognition;
    }
  }, []);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      transcriptRef.current = "";

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        // Stop timer
        clearInterval(timerRef.current);
        timerRef.current = null;

        // Stop mic stream
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
        }

        // Stop speech recognition
        if (recognitionRef.current) {
          try { recognitionRef.current.stop(); } catch (e) { /* ignore */ }
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const audioBlobUrl = URL.createObjectURL(audioBlob);
        const transcript = transcriptRef.current.trim();
        const duration = recordingDuration;

        setIsListening(false);
        setRecordingDuration(0);

        if (transcript) {
          sendVoiceMessage(transcript, audioBlobUrl, duration);
        }
      };

      mediaRecorder.start(200);

      // Start speech recognition in parallel
      if (recognitionRef.current) {
        try { recognitionRef.current.start(); } catch (e) { /* ignore */ }
      }

      // Start duration timer
      setRecordingDuration(0);
      timerRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1);
      }, 1000);

      setIsListening(true);
    } catch (err) {
      console.error("Failed to start recording:", err);
      alert("Microphone access is required for voice recording. Please allow microphone permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  };

  const toggleRecording = () => {
    if (isListening) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  const formatDuration = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  };

  // Handle typed text send
  const handleSend = async () => {
    if (!message.trim() || isSending) return;

    setIsSending(true);
    try {
      await sendMessage();
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = async (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      await handleSend();
    }
  };

  return (
    <div className="input-container">
      {isListening && (
        <div className="recording-bar">
          <span className="rec-dot"></span>
          <span className="rec-label">Recording voice note...</span>
          <span className="rec-timer">{formatDuration(recordingDuration)}</span>
        </div>
      )}
      <div className="input-area">
        <button
          type="button"
          className={`mic-button ${isListening ? "listening" : ""}`}
          onClick={toggleRecording}
          title={isListening ? "Stop & Send Voice Note" : "Record Voice Note"}
        >
          {isListening ? (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="6" width="12" height="12" rx="2" />
            </svg>
          ) : (
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="22"/>
            </svg>
          )}
        </button>

        <textarea
          value={message}
          maxLength={1000}
          rows={1}
          autoComplete="off"
          spellCheck={false}
          autoFocus
          placeholder={isListening ? "Recording... click stop to send" : "Type a message..."}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isListening}
        />

        <button
          type="button"
          className="send-button"
          onClick={handleSend}
          disabled={isSending || !message.trim() || isListening}
        >
          {isSending ? (
            <span className="spinner"></span>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}

export default ChatInput;
