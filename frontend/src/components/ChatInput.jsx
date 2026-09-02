import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "./Icon";

function ChatInput({
  message,
  setMessage,
  sendMessage,
  sendVoiceMessage,
  isListening,
  setIsListening,
  isDisabled = false,
  isVoiceReactiveEnabled,
  onRecordingIntentChange,
  onVoiceLevelChange,
}) {
  const [isSending, setIsSending] = useState(false);
  const [recordingDuration, setRecordingDuration] = useState(0);
  const recognitionRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const transcriptRef = useRef("");
  const timerRef = useRef(null);
  const streamRef = useRef(null);
  const durationRef = useRef(0);
  const isMountedRef = useRef(false);
  const isUnmountingRef = useRef(false);
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const analyserSourceRef = useRef(null);
  const analyserFrameRef = useRef(null);
  const analyserSamplesRef = useRef(null);
  const smoothedVoiceLevelRef = useRef(0);
  const publishedVoiceLevelRef = useRef(0);
  const lastVoicePublishTimeRef = useRef(0);
  const onVoiceLevelChangeRef = useRef(onVoiceLevelChange);
  const onRecordingIntentChangeRef = useRef(onRecordingIntentChange);
  const isRecordingOperationRef = useRef(false);
  const isDisabledRef = useRef(isDisabled);

  useEffect(() => {
    onVoiceLevelChangeRef.current = onVoiceLevelChange;
  }, [onVoiceLevelChange]);

  useEffect(() => {
    onRecordingIntentChangeRef.current = onRecordingIntentChange;
  }, [onRecordingIntentChange]);

  useEffect(() => {
    isDisabledRef.current = isDisabled;
  }, [isDisabled]);

  const publishVoiceLevel = useCallback((level) => {
    publishedVoiceLevelRef.current = level;
    onVoiceLevelChangeRef.current?.(level);
  }, []);

  const stopVoiceAnalysis = useCallback((resetLevel = true) => {
    if (analyserFrameRef.current !== null) {
      window.cancelAnimationFrame(analyserFrameRef.current);
      analyserFrameRef.current = null;
    }

    try { analyserSourceRef.current?.disconnect(); } catch { /* already disconnected */ }
    try { analyserRef.current?.disconnect(); } catch { /* already disconnected */ }
    analyserSourceRef.current = null;
    analyserRef.current = null;
    analyserSamplesRef.current = null;

    const audioContext = audioContextRef.current;
    audioContextRef.current = null;
    if (audioContext && audioContext.state !== "closed") {
      audioContext.close().catch(() => {});
    }

    smoothedVoiceLevelRef.current = 0;
    lastVoicePublishTimeRef.current = 0;
    if (resetLevel && publishedVoiceLevelRef.current !== 0) {
      publishVoiceLevel(0);
    }
  }, [publishVoiceLevel]);

  const startVoiceAnalysis = useCallback((stream) => {
    stopVoiceAnalysis(false);

    if (
      !stream ||
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      publishVoiceLevel(0);
      return;
    }

    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) {
      publishVoiceLevel(0);
      return;
    }

    try {
      const audioContext = new AudioContext();
      const analyser = audioContext.createAnalyser();
      const source = audioContext.createMediaStreamSource(stream);
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.55;
      source.connect(analyser);

      audioContextRef.current = audioContext;
      analyserRef.current = analyser;
      analyserSourceRef.current = source;
      analyserSamplesRef.current = new Uint8Array(analyser.fftSize);
      smoothedVoiceLevelRef.current = 0;
      lastVoicePublishTimeRef.current = 0;
      publishVoiceLevel(0);

      if (audioContext.state === "suspended") {
        audioContext.resume().catch(() => {});
      }

      const measureVoiceLevel = (timestamp) => {
        if (
          analyserRef.current !== analyser ||
          !analyserSamplesRef.current
        ) {
          return;
        }

        const samples = analyserSamplesRef.current;
        analyser.getByteTimeDomainData(samples);

        let sumOfSquares = 0;
        for (let index = 0; index < samples.length; index += 1) {
          const sample = (samples[index] - 128) / 128;
          sumOfSquares += sample * sample;
        }

        const rms = Math.sqrt(sumOfSquares / samples.length);
        const normalizedLevel = Math.min(
          1,
          Math.max(0, (rms - 0.014) / 0.1),
        );
        const targetLevel = normalizedLevel === 0
          ? 0
          : Math.pow(normalizedLevel, 0.72);
        const currentLevel = smoothedVoiceLevelRef.current;
        const response = targetLevel > currentLevel ? 0.52 : 0.14;
        let nextLevel = currentLevel + (targetLevel - currentLevel) * response;
        if (nextLevel < 0.004) nextLevel = 0;
        smoothedVoiceLevelRef.current = nextLevel;

        const timeSincePublish = timestamp - lastVoicePublishTimeRef.current;
        const levelDifference = Math.abs(
          nextLevel - publishedVoiceLevelRef.current,
        );
        const shouldResetPublishedLevel =
          nextLevel === 0 && publishedVoiceLevelRef.current !== 0;
        if (
          timeSincePublish >= 33 &&
          (levelDifference >= 0.004 || shouldResetPublishedLevel)
        ) {
          lastVoicePublishTimeRef.current = timestamp;
          publishVoiceLevel(Number(nextLevel.toFixed(3)));
        }

        analyserFrameRef.current = window.requestAnimationFrame(
          measureVoiceLevel,
        );
      };

      analyserFrameRef.current = window.requestAnimationFrame(
        measureVoiceLevel,
      );
    } catch (error) {
      console.error("Microphone volume analysis unavailable:", error);
      stopVoiceAnalysis();
    }
  }, [publishVoiceLevel, stopVoiceAnalysis]);

  // Initialize SpeechRecognition
  useEffect(() => {
    isMountedRef.current = true;
    isUnmountingRef.current = false;
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

    return () => {
      isUnmountingRef.current = true;
      isMountedRef.current = false;
      isRecordingOperationRef.current = false;
      onRecordingIntentChangeRef.current?.(false);

      clearInterval(timerRef.current);
      timerRef.current = null;

      const recorder = mediaRecorderRef.current;
      if (recorder) {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        if (recorder.state !== "inactive") {
          try { recorder.stop(); } catch { /* already stopping */ }
        }
        mediaRecorderRef.current = null;
      }

      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }

      stopVoiceAnalysis();

      const recognition = recognitionRef.current;
      if (recognition) {
        recognition.onresult = null;
        recognition.onerror = null;
        recognition.onend = null;
        try { recognition.abort(); } catch { /* already stopped */ }
        recognitionRef.current = null;
      }
    };
  }, [stopVoiceAnalysis]);

  useEffect(() => {
    const recorder = mediaRecorderRef.current;
    const stream = streamRef.current;
    if (
      isListening &&
      isVoiceReactiveEnabled &&
      stream &&
      recorder?.state !== "inactive"
    ) {
      startVoiceAnalysis(stream);
    } else {
      stopVoiceAnalysis();
    }
  }, [
    isListening,
    isVoiceReactiveEnabled,
    startVoiceAnalysis,
    stopVoiceAnalysis,
  ]);

  const startRecording = async () => {
    if (isDisabled || isListening || isRecordingOperationRef.current) return;

    isRecordingOperationRef.current = true;
    onRecordingIntentChangeRef.current?.(true);
    let recordingStarted = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (
        !isMountedRef.current ||
        isUnmountingRef.current ||
        isDisabledRef.current
      ) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
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
        stopVoiceAnalysis();

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
          try { recognitionRef.current.stop(); } catch { /* already stopped */ }
        }

        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        const transcript = transcriptRef.current.trim();
        const duration = durationRef.current;
        durationRef.current = 0;

        mediaRecorderRef.current = null;
        isRecordingOperationRef.current = false;

        if (isUnmountingRef.current || !isMountedRef.current) {
          return;
        }

        setIsListening(false);
        setRecordingDuration(0);
        onRecordingIntentChangeRef.current?.(false);

        if (transcript && audioBlob.size > 0) {
          sendVoiceMessage(transcript, audioBlob, duration);
        }
      };

      mediaRecorder.start(200);
      recordingStarted = true;

      // Start speech recognition in parallel
      if (recognitionRef.current) {
        try { recognitionRef.current.start(); } catch { /* already started */ }
      }

      // Start duration timer
      setRecordingDuration(0);
      durationRef.current = 0;
      timerRef.current = setInterval(() => {
        durationRef.current += 1;
        if (isMountedRef.current) {
          setRecordingDuration(durationRef.current);
        }
      }, 1000);

      setIsListening(true);
    } catch (err) {
      stopVoiceAnalysis();
      clearInterval(timerRef.current);
      timerRef.current = null;
      durationRef.current = 0;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
      }
      const recorder = mediaRecorderRef.current;
      if (recorder) {
        recorder.ondataavailable = null;
        recorder.onstop = null;
        if (recorder.state !== "inactive") {
          try { recorder.stop(); } catch { /* already stopped */ }
        }
        mediaRecorderRef.current = null;
      }
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch { /* already stopped */ }
      }
      if (isMountedRef.current) {
        setIsListening(false);
        setRecordingDuration(0);
      }
      if (isUnmountingRef.current || !isMountedRef.current) return;
      console.error("Failed to start recording:", err);
      alert("Microphone access is required for voice recording. Please allow microphone permissions.");
    } finally {
      if (!recordingStarted) {
        isRecordingOperationRef.current = false;
        if (isMountedRef.current && !isUnmountingRef.current) {
          onRecordingIntentChangeRef.current?.(false);
        }
      }
    }
  };

  const stopRecording = () => {
    stopVoiceAnalysis();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      mediaRecorderRef.current.stop();
    }
  };

  const toggleRecording = () => {
    if (isDisabled) return;
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
    if (!message.trim() || isSending || isDisabled) return;

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
        <div className="recording-bar" role="status" aria-live="polite">
          <span className="rec-dot"></span>
          <span className="rec-label">Recording voice note...</span>
          <span className="rec-timer" aria-label={`${recordingDuration} seconds recorded`}>
            {formatDuration(recordingDuration)}
          </span>
        </div>
      )}
      <div className="input-area">
        <button
          type="button"
          className={`mic-button ${isListening ? "listening" : ""}`}
          onClick={toggleRecording}
          title={isListening ? "Stop and send voice note" : "Record voice note"}
          aria-label={isListening ? "Stop and send voice note" : "Record voice note"}
          aria-pressed={isListening}
          disabled={isDisabled}
        >
          <Icon name={isListening ? "stop" : "mic"} size={21} />
        </button>

        <textarea
          value={message}
          maxLength={1000}
          rows={1}
          autoComplete="off"
          spellCheck={false}
          autoFocus
          placeholder={isListening ? "Recording... click stop to send" : "Type a message..."}
          aria-label="Message"
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isListening || isDisabled}
        />

        <button
          type="button"
          className="send-button"
          onClick={handleSend}
          disabled={isSending || !message.trim() || isListening || isDisabled}
          aria-label={isSending ? "Sending message" : "Send message"}
        >
          {isSending ? (
            <span className="spinner" aria-hidden="true"></span>
          ) : (
            <Icon name="send" size={19} />
          )}
        </button>
      </div>
    </div>
  );
}

export default ChatInput;
