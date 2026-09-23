import { useState, useEffect, useRef, useCallback } from "react";
import axios from "axios";
import "./App.css";

import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";
import MemorySidebar from "./components/MemorySidebar";
import AudioVisualizer from "./components/AudioVisualizer";
import Icon from "./components/Icon";

const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/+$/, "");
const CHAT_REQUEST_TIMEOUT_MS = 60_000;
const CLEAR_REQUEST_TIMEOUT_MS = 15_000;
// Mirrors the backend MAX_MESSAGE_LENGTH so over-length input gives clear,
// local feedback instead of a generic server error.
const MAX_MESSAGE_LENGTH = 4000;

// The session is an HttpOnly cookie set by the API on login; withCredentials makes
// axios send it on cross-origin calls (page JS can't read it, so XSS can't steal it).
axios.defaults.withCredentials = true;

// A 401 from any endpoint logs the user out so the app returns to the login
// screen instead of surfacing raw auth errors.
let unauthorizedHandler = null;
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && unauthorizedHandler) {
      unauthorizedHandler();
    }
    return Promise.reject(error);
  },
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
  const [isListening, setIsListening] = useState(false);
  const [voiceLevel, setVoiceLevel] = useState(0);
  const [playbackLevel, setPlaybackLevel] = useState(0);
  const [voiceOrbActivity, setVoiceOrbActivity] = useState("idle");
  const [chatScrollable, setChatScrollable] = useState(false);
  const [isClearingConversation, setIsClearingConversation] = useState(false);
  const [isAuthed, setIsAuthed] = useState(false);
  const [isFullResetting, setIsFullResetting] = useState(false);
  const [resetEpoch, setResetEpoch] = useState(0);
  const [accountName, setAccountName] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuShift, setMenuShift] = useState(0);
  const menuRef = useRef(null);
  const [voiceTranscriptReveal, setVoiceTranscriptReveal] = useState(null);
  const audioRef = useRef(null);
  const activeVoiceTranscriptRef = useRef(null);
  const playbackSequenceRef = useRef(0);
  const playbackAnalysisRef = useRef(null);
  const playbackObjectUrlRef = useRef(null);
  const sessionEpochRef = useRef(0);
  const activeChatRequestsRef = useRef(new Set());
  const clearedSectionsRef = useRef({ conversation: false, memory: false });
  const conversationClearInFlightRef = useRef(false);
  const fullResetInFlightRef = useRef(false);

  const revokePlaybackUrl = () => {
    if (playbackObjectUrlRef.current) {
      URL.revokeObjectURL(playbackObjectUrlRef.current);
      playbackObjectUrlRef.current = null;
    }
  };

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
    revokePlaybackUrl();
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
  const isResetControlDisabled =
    isClearingConversation || isFullResetting;
  // Identity comes from the authenticated account (primary), not memory. The
  // memory-derived name is only a fallback for pre-account sessions.
  const storedName = getStoredUserName(memories);
  const userName = (accountName || storedName || "")
    .trim()
    .replace(/\s+/g, " ")
    .slice(0, 80);

  // A 401 from any endpoint means the session is invalid: drop the token and
  // return to the login screen.
  useEffect(() => {
    unauthorizedHandler = () => {
      stopResponsePlayback();
      setIsAuthed(false);
      setAccountName("");
      setMessages([]);
      setMemories({});
    };
    return () => {
      unauthorizedHandler = null;
    };
  }, [stopResponsePlayback]);

  // On load/refresh, ask the server whether the (HttpOnly cookie) session is
  // still valid. Page JS can't read the cookie, so this one probe is how we
  // restore a logged-in state; a 401 leaves isAuthed false (login screen).
  useEffect(() => {
    let cancelled = false;
    axios
      .get(`${API_BASE}/auth/me`)
      .then((res) => {
        if (!cancelled && res.data?.user?.username) {
          setIsAuthed(true);
          setAccountName(res.data.user.username);
        }
      })
      .catch(() => {
        if (!cancelled) setIsAuthed(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Restore persisted server state once authenticated, so an existing
  // conversation is not briefly treated as a fresh, empty session. Re-runs when
  // the token changes (login) or after a full reset (sessionEpoch bump).
  useEffect(() => {
    if (!isAuthed) return undefined;
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
        setMemories(
          memRes.data?.memories && typeof memRes.data.memories === "object"
            ? memRes.data.memories
            : {},
        );
      } catch (err) {
         if (!cancelled && loadEpoch === sessionEpochRef.current) {
           console.error("Failed to load initial assistant data", err);
         }
       }
     };

    void fetchInitialData();
    return () => {
      cancelled = true;
    };
  }, [isAuthed, resetEpoch]);

  useEffect(() => () => {
    activeVoiceTranscriptRef.current = null;
    stopPlaybackAnalysis();
    releaseAudioElement(audioRef);
    revokePlaybackUrl();
  }, [stopPlaybackAnalysis]);

  // Recording starts while Jarvis is speaking: stop the reply so Listening can
  // take over cleanly.
  const handleRecordingIntentChange = useCallback((recordingIntent) => {
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
      // Stop response playback when the tab is hidden so Jarvis never keeps
      // speaking in the background.
      if (document.visibilityState !== "visible") {
        stopResponsePlayback();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [stopResponsePlayback]);

  useEffect(() => {
    if (messages.length === 0) {
      setChatScrollable(false);
    }
  }, [messages.length]);

  // When the memory sidebar slides in from the right, shift the round menu
  // button left (within the header) so it clears the panel, keeping the main
  // content centered. The amount is measured so it stays correct at any width.
  useEffect(() => {
    if (!sidebarOpen) {
      setMenuShift(0);
      return undefined;
    }
    const measure = () => {
      const panel = document.querySelector(".memory-sidebar");
      const panelWidth = panel ? panel.getBoundingClientRect().width : 370;
      const gutter = 16;
      setMenuShift(panelWidth + gutter);
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [sidebarOpen]);

  // Close the header menu on outside click or Escape.
  useEffect(() => {
    if (!menuOpen) return undefined;
    const onPointer = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setMenuOpen(false);
      }
    };
    const onKey = (event) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [menuOpen]);

  useEffect(() => {
    if (!isListening) {
      setVoiceLevel(0);
    }
  }, [isListening]);

  // Resolve a playable audio URL. Backend paths (/audio/...) are protected,
  // so fetch them through the authed axios client into a blob; external
  // http(s) URLs are played directly.
  const resolveAudioUrl = async (url) => {
    if (!url) return null;
    if (url.startsWith("http")) return url;
    const { data } = await axios.get(`${API_BASE}${url}`, {
      responseType: "blob",
    });
    return URL.createObjectURL(data);
  };

  const playAudio = useCallback(async (url, transcript = null) => {
    if (!url) return;
    let audio = null;
    let settled = false;
    let playbackToken = null;
    let objectUrl = null;

    const finishPlayback = () => {
      if (settled) return;
      settled = true;

      if (playbackToken !== null) {
        finalizeVoiceTranscript(playbackToken);
      }

      if (audio && audioRef.current === audio) {
        stopPlaybackAnalysis();
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
        setVoiceOrbActivity((currentActivity) => (
          currentActivity === "speaking" || currentActivity === "thinking"
            ? "idle"
            : currentActivity
        ));
      }

      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
        objectUrl = null;
      }
    };

    try {
      stopResponsePlayback();
      playbackToken = playbackSequenceRef.current + 1;
      playbackSequenceRef.current = playbackToken;

      // Fetch through the authed client (bearer token) so protected /audio
      // endpoints do not return 401. Blob URLs are same-origin, so the orb's
      // playback analyser can still read the JARVIS audio energy.
      const resolvedUrl = await resolveAudioUrl(url);
      if (!resolvedUrl) return;
      objectUrl = resolvedUrl;
      audio = new Audio();
      audio.src = resolvedUrl;
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
    if (userMessage.length > MAX_MESSAGE_LENGTH) {
      setMessages((prev) => [
        ...prev,
        {
          id: createMessageId(),
          sender: "System",
          text: "That message is too long to send.",
          type: "text",
        },
      ]);
      return;
    }

    clearedSectionsRef.current = { conversation: false, memory: false };
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
    if (voiceTranscript.length > MAX_MESSAGE_LENGTH) {
      setMessages((prev) => [
        ...prev,
        {
          id: createMessageId(),
          sender: "System",
          text: "That message is too long to send.",
          type: "text",
        },
      ]);
      return;
    }

    clearedSectionsRef.current = { conversation: false, memory: false };
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
    }
  };

  const performFullReset = async () => {
    if (fullResetInFlightRef.current) return;

    fullResetInFlightRef.current = true;
    sessionEpochRef.current += 1;
    stopResponsePlayback();
    setVoiceOrbActivity("idle");
    setIsFullResetting(true);
    setMessage("");
    setMessages([]);
    setVoiceTranscriptReveal(null);
    setMemories({});
    setSidebarOpen(false);
    setChatScrollable(false);
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
       setIsFullResetting(false);
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
    setChatScrollable(false);
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
    }

    if (didClearConversation) {
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

  const handleLogout = useCallback(async () => {
    try {
      await axios.post(`${API_BASE}/auth/logout`);
    } catch {
      // Best effort: revoke server-side, but always clear the local session.
    }
    stopResponsePlayback();
    setAccountName("");
    setMessages([]);
    setMemories({});
    setVoiceTranscriptReveal(null);
    setSidebarOpen(false);
    setIsAuthed(false);
  }, [stopResponsePlayback]);

  if (!isAuthed) {
    return (
      <AuthScreen
        onAuthenticated={(name) => {
          setAccountName(name || "");
          setIsAuthed(true);
        }}
      />
    );
  }

  return (
    <div className="app-layout">
      <div className="workspace-shell">
        <header className="workspace-header">
          <div className="workspace-title">
            <strong>JARVIS</strong>
            <span>Enterprise Voice Assistant</span>
          </div>
          <div className="workspace-actions">
            <div
              className={`workspace-menu${menuOpen ? " open" : ""}${sidebarOpen ? " workspace-menu-shifted" : ""}`}
              style={{ "--menu-shift-left": `-${menuShift}px` }}
              ref={menuRef}
            >
              <button
                type="button"
                className="workspace-menu-trigger"
                onClick={() => setMenuOpen((o) => !o)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                aria-label="Menu"
                title="Menu"
              >
                {/* Sparkles glyph (design source of truth): a 4-point star,
                    a small star, and a dot — rendered in the app's exact
                    --orange so the shade matches the rest of the system. */}
                <svg
                  className="workspace-menu-spark"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="M12 4 L13.6 10.4 L20 12 L13.6 13.6 L12 20 L10.4 13.6 L4 12 L10.4 10.4 Z" />
                  <path d="M18.5 2.8 L19.1 4.9 L21.2 5.5 L19.1 6.1 L18.5 8.2 L17.9 6.1 L15.8 5.5 L17.9 4.9 Z" />
                  <circle cx="6.2" cy="18.4" r="1.5" fill="currentColor" stroke="none" />
                </svg>
              </button>
              <div className="workspace-menu-panel" role="menu">
                <button
                  type="button"
                  role="menuitem"
                  className="workspace-menu-item"
                  onClick={() => {
                    setMenuOpen(false);
                    handleClearChat();
                  }}
                  disabled={isResetControlDisabled}
                >
                  <Icon name="trash" size={17} />
                  <span>Conversation</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="workspace-menu-item"
                  onClick={() => {
                    setMenuOpen(false);
                    setSidebarOpen(true);
                  }}
                >
                  <Icon name="memory" size={17} />
                  <span>Memory</span>
                </button>
                <button
                  type="button"
                  role="menuitem"
                  className="workspace-menu-item danger"
                  onClick={() => {
                    setMenuOpen(false);
                    if (window.confirm("Sign out of JARVIS?")) handleLogout();
                  }}
                >
                  <Icon name="logout" size={17} />
                  <span>Sign out</span>
                </button>
              </div>
            </div>
          </div>
        </header>

        <main
          className={`main-content${messages.length ? " has-messages" : ""}${isOrbHidden ? " orb-hidden" : ""}${isVoiceOrbActive ? " voice-orb-active" : ""}`}
        >
          <AudioVisualizer
            activity={voiceOrbActivity}
            isVisible={isOrbVisible}
            activityLevel={orbActivityLevel}
          />

          <ChatWindow
            messages={messages}
            playAudio={playAudio}
            voiceTranscriptReveal={voiceTranscriptReveal}
            userName={userName}
            isOrbCollapsed={isOrbHidden}
            isVoiceOrbActive={isVoiceOrbActive}
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

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const isRegister = mode === "register";

  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const route = isRegister ? "/auth/register" : "/auth/login";
      const { data } = await axios.post(`${API_BASE}${route}`, {
        username: username.trim(),
        password,
      });
      if (!data?.token) {
        throw new Error("Login failed.");
      }
      onAuthenticated(data.user?.username || username.trim());
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app-layout auth-layout">
      <div className="auth-card">
        <div className="auth-brand">
          <strong>JARVIS</strong>
          <span>Enterprise Voice Assistant</span>
        </div>
        <h1 className="auth-title">
          {isRegister ? "Create your account" : "Sign in to continue"}
        </h1>

        <form className="auth-form" onSubmit={submit}>
          <label className="auth-field">
            <span>Username</span>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter your name"
              required
              disabled={busy}
            />
          </label>
          <label className="auth-field">
            <span>Password</span>
            <input
              type="password"
              autoComplete={isRegister ? "new-password" : "current-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              required
              minLength={isRegister ? 8 : undefined}
              disabled={busy}
            />
          </label>

          {error ? <p className="auth-error" role="alert">{error}</p> : null}

          <button type="submit" className="auth-submit" disabled={busy}>
            {busy ? "Please wait…" : isRegister ? "Create account" : "Sign in"}
          </button>
        </form>

        <button
          type="button"
          className="auth-switch"
          onClick={() => {
            setMode(isRegister ? "login" : "register");
            setError("");
          }}
          disabled={busy}
        >
          {isRegister ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>
      </div>
    </div>
  );
}

export default App;
