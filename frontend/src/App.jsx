import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import "./App.css";

import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import MemorySidebar from "./components/MemorySidebar";
import AudioVisualizer from "./components/AudioVisualizer";
import Icon from "./components/Icon";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
const DEFAULT_INITIAL_IDLE_DELAY_MS = 500;
const DEFAULT_JARVIS_IDLE_DELAY_MS = 15_000;
const CHAT_REQUEST_TIMEOUT_MS = 60_000;
const CLEAR_REQUEST_TIMEOUT_MS = 15_000;

const parseDelay = (rawValue, fallback, minimum) => {
  if (typeof rawValue !== "string" || !rawValue.trim()) return fallback;
  const parsedValue = Number(rawValue);
  return Number.isFinite(parsedValue) && parsedValue >= 0
    ? Math.max(minimum, Math.round(parsedValue))
    : fallback;
};

const INITIAL_IDLE_DELAY_MS = parseDelay(
  import.meta.env.VITE_JARVIS_INITIAL_IDLE_DELAY_MS,
  DEFAULT_INITIAL_IDLE_DELAY_MS,
  250,
);
const JARVIS_IDLE_DELAY_MS = parseDelay(
  import.meta.env.VITE_JARVIS_IDLE_DELAY_MS,
  DEFAULT_JARVIS_IDLE_DELAY_MS,
  1_000,
);

const releaseAudioElement = (audioRef) => {
  const audio = audioRef.current;
  if (!audio) return;

  audio.onplay = null;
  audio.onloadedmetadata = null;
  audio.ontimeupdate = null;
  audio.onended = null;
  audio.onerror = null;
  audio.onpause = null;
  audio.onabort = null;
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  audioRef.current = null;
};

const postClearRequest = (route) =>
  axios.post(`${API_BASE}${route}`, undefined, {
    timeout: CLEAR_REQUEST_TIMEOUT_MS,
  });

const createMessageId = () =>
  globalThis.crypto?.randomUUID?.() ||
  `message-${Date.now()}-${Math.random().toString(36).slice(2)}`;

const getVoiceTranscriptPreview = (fullText, progress) => {
  if (!fullText || progress >= 1) return fullText;
  if (!Number.isFinite(progress)) return fullText;

  const boundedProgress = Math.min(1, Math.max(0, progress));
  const targetLength = Math.max(1, Math.ceil(fullText.length * boundedProgress));
  const tokens = fullText.match(/\S+\s*/g);
  if (!tokens) return fullText.slice(0, targetLength);

  let preview = "";
  for (const token of tokens) {
    if (preview && preview.length + token.length > targetLength) break;
    preview += token;
  }

  return preview || tokens[0].slice(0, targetLength);
};

// The assistant stores the user's name under canonical keys; accept common
// variations so the greeting and monogram avatar use the real first initial.
const NAME_MEMORY_KEYS = [
  "name",
  "user_name",
  "full_name",
  "first_name",
  "display_name",
  "my_name",
];

const getStoredUserName = (memories) => {
  if (!memories || typeof memories !== "object") return "";
  for (const key of NAME_MEMORY_KEYS) {
    const value = memories[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return "";
};

function App() {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [memories, setMemories] = useState({});
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [playbackLevel, setPlaybackLevel] = useState(0);
  const [voiceOrbActivity, setVoiceOrbActivity] = useState("idle");
  const [pendingRequests, setPendingRequests] = useState(0);
  const [chatScrollable, setChatScrollable] = useState(false);
  const [conversationStarted, setConversationStarted] = useState(false);
  const [initialDataLoaded, setInitialDataLoaded] = useState(false);
  const [isAmbientIdle, setIsAmbientIdle] = useState(false);
  const [isPageVisible, setIsPageVisible] = useState(
    () => document.visibilityState === "visible",
  );
  const [isRecordingIntent, setIsRecordingIntent] = useState(false);
  const [isClearingConversation, setIsClearingConversation] = useState(false);
  const [isFullResetting, setIsFullResetting] = useState(false);
  const [resetEpoch, setResetEpoch] = useState(0);
  const [idleCycle, setIdleCycle] = useState(0);
  const [voiceTranscriptReveal, setVoiceTranscriptReveal] = useState(null);
  const audioRef = useRef(null);
  const activeVoiceTranscriptRef = useRef(null);
  const playbackSequenceRef = useRef(0);
  const playbackAnalysisRef = useRef(null);
  const sessionEpochRef = useRef(0);
  const activeChatRequestsRef = useRef(new Set());
  const clearedSectionsRef = useRef({ conversation: false, memory: false });
  const conversationClearInFlightRef = useRef(false);
  const fullResetInFlightRef = useRef(false);

  const finalizeVoiceTranscript = useCallback((playbackToken) => {
    const activeTranscript = activeVoiceTranscriptRef.current;
    if (
      !activeTranscript ||
      activeTranscript.playbackToken !== playbackToken
    ) {
      return;
    }

    activeVoiceTranscriptRef.current = null;
    setVoiceTranscriptReveal((currentReveal) => (
      currentReveal?.messageId === activeTranscript.messageId
        ? {
          messageId: activeTranscript.messageId,
          text: activeTranscript.fullText,
        }
        : currentReveal
    ));
  }, []);

  const updateVoiceTranscript = useCallback((playbackToken, progress) => {
    const activeTranscript = activeVoiceTranscriptRef.current;
    if (
      !activeTranscript ||
      activeTranscript.playbackToken !== playbackToken
    ) {
      return;
    }

    const preview = getVoiceTranscriptPreview(
      activeTranscript.fullText,
      progress,
    );
    setVoiceTranscriptReveal((currentReveal) => {
      if (
        currentReveal?.messageId === activeTranscript.messageId &&
        currentReveal.text === preview
      ) {
        return currentReveal;
      }
      return { messageId: activeTranscript.messageId, text: preview };
    });
  }, []);

  const stopPlaybackAnalysis = useCallback(() => {
    const analysis = playbackAnalysisRef.current;
    playbackAnalysisRef.current = null;

    if (analysis?.frameId !== null && analysis?.frameId !== undefined) {
      window.cancelAnimationFrame(analysis.frameId);
    }
    try { analysis?.source?.disconnect(); } catch { /* already disconnected */ }
    try { analysis?.analyser?.disconnect(); } catch { /* already disconnected */ }
    if (analysis?.context && analysis.context.state !== "closed") {
      analysis.context.close().catch(() => {});
    }
    setPlaybackLevel(0);
  }, []);

  const startPlaybackAnalysis = useCallback(async (audio, playbackToken) => {
    stopPlaybackAnalysis();

    if (
      !audio ||
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;

    const analysis = {
      audio,
      playbackToken,
      context: null,
      source: null,
      analyser: null,
      frameId: null,
      samples: null,
      smoothedLevel: 0,
      publishedLevel: 0,
      lastPublishTime: 0,
    };

    const disposeAnalysis = () => {
      if (analysis.frameId !== null) {
        window.cancelAnimationFrame(analysis.frameId);
        analysis.frameId = null;
      }
      try { analysis.source?.disconnect(); } catch { /* already disconnected */ }
      try { analysis.analyser?.disconnect(); } catch { /* already disconnected */ }
      if (analysis.context?.state !== "closed") {
        analysis.context?.close().catch(() => {});
      }
      if (playbackAnalysisRef.current === analysis) {
        playbackAnalysisRef.current = null;
        setPlaybackLevel(0);
      }
    };

    try {
      const context = new AudioContext();
      analysis.context = context;

      if (context.state !== "running") {
        await context.resume();
      }

      if (
        context.state !== "running" ||
        audioRef.current !== audio ||
        playbackSequenceRef.current !== playbackToken
      ) {
        disposeAnalysis();
        return;
      }

      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.58;
      const source = context.createMediaElementSource(audio);
      source.connect(analyser);
      analyser.connect(context.destination);

      analysis.analyser = analyser;
      analysis.source = source;
      analysis.samples = new Uint8Array(analyser.fftSize);
      playbackAnalysisRef.current = analysis;

      const samplePlaybackEnergy = (now) => {
        if (
          playbackAnalysisRef.current !== analysis ||
          audioRef.current !== audio ||
          playbackSequenceRef.current !== playbackToken
        ) {
          disposeAnalysis();
          return;
        }

        analyser.getByteTimeDomainData(analysis.samples);
        let sum = 0;
        for (let index = 0; index < analysis.samples.length; index += 1) {
          const centered = (analysis.samples[index] - 128) / 128;
          sum += centered * centered;
        }

        const rms = Math.sqrt(sum / analysis.samples.length);
        const normalized = Math.min(1, Math.max(0, (rms - 0.008) / 0.13));
        analysis.smoothedLevel += (normalized - analysis.smoothedLevel) * 0.42;

        if (now - analysis.lastPublishTime >= 33) {
          const nextLevel = Number(analysis.smoothedLevel.toFixed(3));
          if (Math.abs(nextLevel - analysis.publishedLevel) >= 0.012) {
            analysis.publishedLevel = nextLevel;
            setPlaybackLevel(nextLevel);
          }
          analysis.lastPublishTime = now;
        }

        analysis.frameId = window.requestAnimationFrame(samplePlaybackEnergy);
      };

      analysis.frameId = window.requestAnimationFrame(samplePlaybackEnergy);
    } catch {
      // Audio playback remains available through the native element if the
      // analyser cannot be attached (for example, due to a CORS policy).
      disposeAnalysis();
    }
  }, [stopPlaybackAnalysis]);

  const stopResponsePlayback = useCallback(() => {
    const activeTranscript = activeVoiceTranscriptRef.current;
    playbackSequenceRef.current += 1;
    if (activeTranscript) {
      finalizeVoiceTranscript(activeTranscript.playbackToken);
    }
    stopPlaybackAnalysis();
    releaseAudioElement(audioRef);
    setIsPlaying(false);
    setVoiceOrbActivity((currentActivity) => (
      ["speaking", "thinking"].includes(currentActivity)
        ? "idle"
        : currentActivity
    ));
  }, [finalizeVoiceTranscript, stopPlaybackAnalysis]);

  // Keep the normal conversation layout independent from active voice work.
  // A typed draft gets the empty-state orb out of the way, while a long chat
  // remains collapsed until an actual voice lifecycle temporarily overrides it.
  const hasTypedDraft = message.trim().length > 0;
  const isOrbHidden = hasTypedDraft || (messages.length > 0 && chatScrollable);
  const isVoiceOrbActive = voiceOrbActivity !== "idle";
  const isOrbVisible = !isOrbHidden || isVoiceOrbActive;
  const orbActivityLevel = voiceOrbActivity === "listening"
    ? voiceLevel
    : voiceOrbActivity === "speaking"
      ? playbackLevel
      : 0;
  const isJarvisBusy =
    hasTypedDraft ||
    isRecordingIntent ||
    isListening ||
    pendingRequests > 0 ||
    isPlaying ||
    isClearingConversation ||
    isFullResetting;
  const isResetControlDisabled =
    isClearingConversation || isFullResetting;
  const ambientEnabled =
    initialDataLoaded &&
    isAmbientIdle &&
    !isJarvisBusy &&
    !isOrbHidden &&
    isPageVisible;

  const storedName = getStoredUserName(memories);
  const userName = typeof storedName === "string"
    ? storedName.trim().replace(/\s+/g, " ").slice(0, 80)
    : "";

  // Restore persisted server state before allowing the idle sound. This avoids
  // briefly treating an existing conversation as a fresh, empty session.
  useEffect(() => {
    let cancelled = false;
    const loadEpoch = sessionEpochRef.current;

    const fetchInitialData = async () => {
      try {
        const [histRes, memRes] = await Promise.all([
          axios.get(`${API_BASE}/history`).catch(() => ({ data: { messages: [] } })),
          axios.get(`${API_BASE}/memories`).catch(() => ({ data: { memories: {} } })),
        ]);

        if (cancelled || loadEpoch !== sessionEpochRef.current) return;

        const history = Array.isArray(histRes.data?.messages)
          ? histRes.data.messages
          : [];
        setMessages(
          history.map((item) => ({
            ...item,
            id: item.id || createMessageId(),
            // A reloaded voice request is stored with the transcript as its text.
            // Re-tag it as an audio note so the transcript stays internal and
            // only the voice-note bubble renders (no transcript shown).
            type:
              item.sender === "You" && item.mode === "voice"
                ? "audio"
                : item.type || "text",
          })),
        );
        setConversationStarted(
          history.some((item) => item.sender === "You"),
        );
        setMemories(
          memRes.data?.memories && typeof memRes.data.memories === "object"
            ? memRes.data.memories
            : {},
        );
      } catch (err) {
        if (!cancelled && loadEpoch === sessionEpochRef.current) {
          console.error("Failed to load initial assistant data", err);
        }
      } finally {
        if (!cancelled && loadEpoch === sessionEpochRef.current) {
          setInitialDataLoaded(true);
        }
      }
    };

    void fetchInitialData();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => () => {
    activeVoiceTranscriptRef.current = null;
    stopPlaybackAnalysis();
    releaseAudioElement(audioRef);
  }, [stopPlaybackAnalysis]);

  // Recording becomes Listening only after MediaRecorder has actually
  // started. A denied permission request therefore returns straight to idle.
  const handleRecordingIntentChange = useCallback((recordingIntent) => {
    setIsRecordingIntent(recordingIntent);
    if (recordingIntent) {
      stopResponsePlayback();
    }
  }, [stopResponsePlayback]);

  useEffect(() => {
    if (isListening) {
      setVoiceOrbActivity("listening");
      return;
    }

    setVoiceOrbActivity((currentActivity) => (
      currentActivity === "listening" ? "idle" : currentActivity
    ));
  }, [isListening]);

  useEffect(() => {
    const handleVisibilityChange = () => {
      const pageIsVisible = document.visibilityState === "visible";
      setIsPageVisible(pageIsVisible);
      if (!pageIsVisible) {
        // Ambient audio has its own visibility gate. Stop response playback as
        // well so Jarvis never continues speaking in a background tab.
        stopResponsePlayback();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [stopResponsePlayback]);

  useEffect(() => {
    setIsAmbientIdle(false);

    if (
      !initialDataLoaded ||
      !isPageVisible ||
      isOrbHidden ||
      isJarvisBusy
    ) {
      return undefined;
    }

    const idleDelay = conversationStarted
      ? JARVIS_IDLE_DELAY_MS
      : INITIAL_IDLE_DELAY_MS;
    const idleTimer = window.setTimeout(() => {
      setIsAmbientIdle(true);
    }, idleDelay);

    return () => window.clearTimeout(idleTimer);
  }, [
    conversationStarted,
    idleCycle,
    initialDataLoaded,
    isJarvisBusy,
    isOrbHidden,
    isPageVisible,
  ]);

  useEffect(() => {
    if (messages.length === 0) {
      setChatScrollable(false);
    }
  }, [messages.length]);

  useEffect(() => {
    if (!isListening) {
      setVoiceLevel(0);
    }
  }, [isListening]);

  const playAudio = useCallback(async (url, transcript = null) => {
    if (!url) return;
    let audio = null;
    let settled = false;
    let playbackToken = null;

    const finishPlayback = () => {
      if (settled) return;
      settled = true;

      if (playbackToken !== null) {
        finalizeVoiceTranscript(playbackToken);
      }

      if (audio && audioRef.current === audio) {
        stopPlaybackAnalysis();
        setIsPlaying(false);
        setVoiceOrbActivity((currentActivity) => (
          currentActivity === "speaking" || currentActivity === "thinking"
            ? "idle"
            : currentActivity
        ));
        audio.onplay = null;
        audio.onloadedmetadata = null;
        audio.ontimeupdate = null;
        audio.onended = null;
        audio.onerror = null;
        audio.onpause = null;
        audio.onabort = null;
        audio.removeAttribute("src");
        audio.load();
        audioRef.current = null;
      } else if (!audioRef.current) {
        stopPlaybackAnalysis();
        setIsPlaying(false);
        setVoiceOrbActivity((currentActivity) => (
          currentActivity === "speaking" || currentActivity === "thinking"
            ? "idle"
            : currentActivity
        ));
      }
    };

    try {
      stopResponsePlayback();
      playbackToken = playbackSequenceRef.current + 1;
      playbackSequenceRef.current = playbackToken;

      const fullUrl = url.startsWith("http") ? url : `${API_BASE}${url}`;
      audio = new Audio();
      // Set this before src so same-origin and configured API-hosted audio can
      // be analysed without changing native playback when analysis is blocked.
      audio.crossOrigin = "anonymous";
      audio.src = fullUrl;
      audioRef.current = audio;

      if (transcript?.messageId && typeof transcript.fullText === "string") {
        activeVoiceTranscriptRef.current = {
          ...transcript,
          playbackToken,
        };
        setVoiceTranscriptReveal({ messageId: transcript.messageId, text: "" });
      }

      const updateTranscriptProgress = () => {
        if (audioRef.current !== audio || playbackToken === null) return;

        const duration = audio.duration;
        if (!Number.isFinite(duration) || duration <= 0) {
          if (audio.readyState >= HTMLMediaElement.HAVE_METADATA) {
            // An unusable duration means there is no safe timing signal. Show
            // the complete reply rather than leaving a partial transcript.
            finalizeVoiceTranscript(playbackToken);
          }
          return;
        }

        updateVoiceTranscript(playbackToken, audio.currentTime / duration);
      };

      audio.onplay = () => {
        if (audioRef.current !== audio) return;
        setIsPlaying(true);
        setVoiceOrbActivity("speaking");
        void startPlaybackAnalysis(audio, playbackToken);
        updateTranscriptProgress();
      };
      audio.ontimeupdate = updateTranscriptProgress;
      audio.onended = finishPlayback;
      audio.onerror = finishPlayback;
      audio.onpause = finishPlayback;
      audio.onabort = finishPlayback;

      await audio.play();
    } catch (err) {
      finishPlayback();
      console.error("Audio playback error:", err);
    }
  }, [
    finalizeVoiceTranscript,
    startPlaybackAnalysis,
    stopPlaybackAnalysis,
    stopResponsePlayback,
    updateVoiceTranscript,
  ]);

  const sendMessage = async (textToSend) => {
    const userMessage = (textToSend || message).trim();
    if (
      !userMessage ||
      conversationClearInFlightRef.current ||
      fullResetInFlightRef.current
    ) {
      return;
    }

    clearedSectionsRef.current = { conversation: false, memory: false };
    setConversationStarted(true);
    setIsAmbientIdle(false);
    stopResponsePlayback();

    setMessages((prev) => [
      ...prev,
      {
        id: createMessageId(),
        sender: "You",
        text: userMessage,
        type: "text",
      },
    ]);

    setMessage("");

    await sendToApi(userMessage, "text");
  };

  const sendVoiceMessage = async (transcript, voiceBlob, duration) => {
    const voiceTranscript = transcript?.trim();
    if (
      !voiceTranscript ||
      conversationClearInFlightRef.current ||
      fullResetInFlightRef.current
    ) {
      return;
    }

    clearedSectionsRef.current = { conversation: false, memory: false };
    setConversationStarted(true);
    setIsAmbientIdle(false);
    stopResponsePlayback();
    // A valid voice note has left the recorder and is now being processed.
    // This is deliberately separate from generic text request activity.
    setVoiceOrbActivity("thinking");

    // Keep the captured transcript internally for the existing voice request,
    // but render only the audio note in the user-facing conversation.
    setMessages((prev) => [
      ...prev,
      {
        id: createMessageId(),
        sender: "You",
        text: voiceTranscript,
        type: "audio",
        voiceAudioBlob: voiceBlob,
        voiceDuration: duration,
      },
    ]);

    await sendToApi(voiceTranscript, "voice");
  };

  const sendToApi = async (userMessage, responseMode) => {
    const requestEpoch = sessionEpochRef.current;
    const request = axios.post(
      `${API_BASE}/chat`,
      { message: userMessage, response_mode: responseMode },
      { timeout: CHAT_REQUEST_TIMEOUT_MS },
    );
    activeChatRequestsRef.current.add(request);
    setPendingRequests((count) => count + 1);

    try {
      const response = await request;
      if (requestEpoch !== sessionEpochRef.current) return;

      const replyText = response.data.reply;
      const audioUrl = response.data.audio_url;
      const updatedMemories = response.data.memories;
      const assistantMessageId = createMessageId();

      setMessages((prev) => [
        ...prev,
        {
          id: assistantMessageId,
          sender: "AI",
          text: replyText,
          audioUrl: audioUrl,
          type: "text",
          responseMode,
        },
      ]);

      if (updatedMemories) {
        setMemories(updatedMemories);
      }

      if (responseMode === "voice" && audioUrl) {
        void playAudio(audioUrl, {
          messageId: assistantMessageId,
          fullText: replyText,
        });
      } else if (responseMode === "voice") {
        // Text still appears if TTS is unavailable, but the temporary voice
        // presentation must not remain in Thinking after that failure.
        setVoiceOrbActivity("idle");
      }
    } catch (error) {
      if (requestEpoch !== sessionEpochRef.current) return;
      console.error("API error:", error);
      if (responseMode === "voice") {
        setVoiceOrbActivity("idle");
      }
      setMessages((prev) => [
        ...prev,
        {
          id: createMessageId(),
          sender: "System",
          text: "The assistant is temporarily unavailable. Please try again.",
          type: "text",
        },
      ]);
    } finally {
      activeChatRequestsRef.current.delete(request);
      setPendingRequests((count) => Math.max(0, count - 1));
    }
  };

  const performFullReset = async () => {
    if (fullResetInFlightRef.current) return;

    fullResetInFlightRef.current = true;
    sessionEpochRef.current += 1;
    stopResponsePlayback();
    setVoiceOrbActivity("idle");
    setIsFullResetting(true);
    setIsAmbientIdle(false);
    setInitialDataLoaded(false);
    setMessage("");
    setMessages([]);
    setVoiceTranscriptReveal(null);
    setMemories({});
    setSidebarOpen(false);
    setConversationStarted(false);
    setChatScrollable(false);
    setIsRecordingIntent(false);
    setIsClearingConversation(false);
    conversationClearInFlightRef.current = false;
    setIsListening(false);
    setVoiceLevel(0);
    setPlaybackLevel(0);
    setResetEpoch((epoch) => epoch + 1);
    let serverResetSucceeded = false;
    try {
      // Let already accepted chat work finish, then clear once more so a late
      // response cannot repopulate server-side history after the reset.
      const activeRequests = Array.from(activeChatRequestsRef.current);
      await Promise.allSettled(activeRequests);
      await postClearRequest("/clear");
      serverResetSucceeded = true;
    } catch (err) {
      console.error("Failed to finalize the full Jarvis reset", err);
    } finally {
      // The individual clear operations already succeeded before this
      // coordinator runs. Retaining these flags after a failed final session
      // clear means the next clear action retries the server-side eviction.
      clearedSectionsRef.current = serverResetSucceeded
        ? { conversation: false, memory: false }
        : { conversation: true, memory: true };
      setPendingRequests(0);
      setInitialDataLoaded(true);
      setIsFullResetting(false);
      setIdleCycle((cycle) => cycle + 1);
      fullResetInFlightRef.current = false;
    }
  };

  const noteClearedSection = async (section) => {
    const clearedSections = {
      ...clearedSectionsRef.current,
      [section]: true,
    };
    clearedSectionsRef.current = clearedSections;

    if (clearedSections.conversation && clearedSections.memory) {
      await performFullReset();
    }
  };

  // Task 1: Clear only conversation history (preserves long-term memories)
  const handleClearChat = async () => {
    if (
      isResetControlDisabled ||
      conversationClearInFlightRef.current ||
      fullResetInFlightRef.current
    ) {
      return;
    }
    if (!window.confirm("Clear conversation history? Your saved long-term memories will be preserved.")) {
      return;
    }

    conversationClearInFlightRef.current = true;
    sessionEpochRef.current += 1;
    stopResponsePlayback();
    setVoiceOrbActivity("idle");
    setIsClearingConversation(true);
    setMessages([]);
    setVoiceTranscriptReveal(null);
    setConversationStarted(false);
    setChatScrollable(false);
    setIsAmbientIdle(false);
    let didClearConversation = false;
    try {
      // Each chat request has a finite client timeout. Waiting for those
      // promises before issuing the clear prevents a completed request from
      // restoring the just-cleared server history.
      const activeRequests = Array.from(activeChatRequestsRef.current);
      await Promise.allSettled(activeRequests);
      await postClearRequest("/clear-chat");
      didClearConversation = true;
    } catch (err) {
      console.error("Failed to clear chat history", err);
    } finally {
      conversationClearInFlightRef.current = false;
      setIsClearingConversation(false);
      // A clear invalidates an in-flight history request, so its local empty
      // state becomes the new baseline for the idle controller.
      setInitialDataLoaded(true);
    }

    if (didClearConversation) {
      setIdleCycle((cycle) => cycle + 1);
      await noteClearedSection("conversation");
    }
  };

  // Task 1: Reset only long-term memories (preserves active chat messages)
  const handleClearMemories = async () => {
    if (
      isResetControlDisabled ||
      conversationClearInFlightRef.current ||
      fullResetInFlightRef.current
    ) {
      return;
    }
    if (!window.confirm("Are you sure you want to delete all long-term memories? Your chat history will be preserved.")) {
      return;
    }
    try {
      await postClearRequest("/clear-memories");
      setMemories({});
      await noteClearedSection("memory");
    } catch (err) {
      console.error("Failed to reset memories", err);
    }
  };

  return (
    <div className="app-layout">
      <div className="workspace-shell">
        <header className="workspace-header">
          <div className="workspace-title">
            <strong>JARVIS</strong>
            <span>Enterprise Voice Assistant</span>
          </div>
          <div className="workspace-actions">
            <button
              type="button"
              className="workspace-control clear-chat-trigger"
              onClick={handleClearChat}
              disabled={isResetControlDisabled}
              aria-label="Clear conversation"
              title="Clear conversation"
            >
              <Icon name="trash" />
              <span>Clear conversation</span>
            </button>
            <button
              type="button"
              className="workspace-control memory-trigger"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              disabled={isResetControlDisabled}
              aria-expanded={sidebarOpen}
              aria-label="Open memory"
              title="Open memory"
            >
              <Icon name="memory" />
              <span>Memory</span>
              <b>{Object.keys(memories).length}</b>
            </button>
          </div>
        </header>

        <main
          className={`main-content${messages.length ? " has-messages" : ""}${isOrbHidden ? " orb-hidden" : ""}${isVoiceOrbActive ? " voice-orb-active" : ""}`}
        >
          <AudioVisualizer
            activity={voiceOrbActivity}
            isVisible={isOrbVisible}
            isAmbientIdle={ambientEnabled}
            activityLevel={orbActivityLevel}
          />

          <ChatWindow
            messages={messages}
            playAudio={playAudio}
            voiceTranscriptReveal={voiceTranscriptReveal}
            userName={userName}
            isOrbCollapsed={isOrbHidden}
            freezeOverflowMeasurements={isVoiceOrbActive}
            onScrollableChange={setChatScrollable}
          />

          <ChatInput
            key={`chat-input-${resetEpoch}`}
            message={message}
            setMessage={setMessage}
            sendMessage={() => sendMessage()}
            sendVoiceMessage={sendVoiceMessage}
            isListening={isListening}
            setIsListening={setIsListening}
            isDisabled={
              isFullResetting || (isClearingConversation && !isListening)
            }
            isVoiceReactiveEnabled={true}
            onRecordingIntentChange={handleRecordingIntentChange}
            onVoiceLevelChange={setVoiceLevel}
          />
        </main>
      </div>

      <MemorySidebar
        key={`memory-sidebar-${resetEpoch}`}
        memories={memories}
        isOpen={sidebarOpen}
        toggleSidebar={() => setSidebarOpen(false)}
        onClearMemories={handleClearMemories}
        isClearDisabled={isResetControlDisabled}
      />
    </div>
  );
}

export default App;
