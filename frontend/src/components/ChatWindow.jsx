import { useEffect, useLayoutEffect, useRef, useState } from "react";
import MessageBubble from "./MessageBubble";

const OVERFLOW_EPSILON = 2;
const ORB_RESTORE_BUFFER = 24;

const getGreetingPeriod = (hour) => {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 17) return "afternoon";
  return "evening";
};

function ChatWindow({
  messages,
  playAudio,
  voiceTranscriptReveal,
  userName,
  isOrbCollapsed,
  freezeOverflowMeasurements = false,
  onScrollableChange,
}) {
  const chatEndRef = useRef(null);
  const chatBoxRef = useRef(null);
  const chatThreadRef = useRef(null);
  const wasNearBottomRef = useRef(true);
  const previousOrbStateRef = useRef(isOrbCollapsed);
  const [localHour, setLocalHour] = useState(() => new Date().getHours());
  const revealedMessageId = voiceTranscriptReveal?.messageId ?? "";
  const revealedText = voiceTranscriptReveal?.text ?? "";

  useEffect(() => {
    const refreshLocalHour = () => setLocalHour(new Date().getHours());
    const timerId = window.setInterval(refreshLocalHour, 60_000);

    return () => window.clearInterval(timerId);
  }, []);

  useEffect(() => {
    const chatBox = chatBoxRef.current;
    if (!chatBox) return undefined;

    const updateNearBottom = () => {
      const distanceFromBottom =
        chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight;
      wasNearBottomRef.current = distanceFromBottom < 72;
    };

    updateNearBottom();
    chatBox.addEventListener("scroll", updateNearBottom, { passive: true });

    return () => chatBox.removeEventListener("scroll", updateNearBottom);
  }, []);

  // Measure the message thread itself rather than the scroll container. A
  // collapsed orb makes the container taller, so comparing only scrollHeight
  // and clientHeight would otherwise make the orb repeatedly hide and return.
  useLayoutEffect(() => {
    const chatBox = chatBoxRef.current;
    const chatThread = chatThreadRef.current;

    if (typeof onScrollableChange !== "function") return undefined;
    if (messages.length === 0 || !chatBox || !chatThread) {
      onScrollableChange(false);
      return undefined;
    }
    // Voice activity can temporarily place an orb over a collapsed long
    // conversation. That presentation must not rewrite the normal overflow
    // decision that will be restored once the voice lifecycle ends.
    if (freezeOverflowMeasurements) return undefined;

    let animationFrameId = null;

    const measureOverflow = () => {
      animationFrameId = null;

      const chatStyle = window.getComputedStyle(chatBox);
      const verticalPadding =
        (Number.parseFloat(chatStyle.paddingTop) || 0) +
        (Number.parseFloat(chatStyle.paddingBottom) || 0);
      const availableHeight = Math.max(0, chatBox.clientHeight - verticalPadding);
      const contentHeight = chatThread.scrollHeight;
      const mainContent = chatBox.closest(".main-content");
      const configuredOrbSpace = mainContent
        ? Number.parseFloat(
            window
              .getComputedStyle(mainContent)
              .getPropertyValue("--conversation-orb-space"),
          )
        : 0;
      const orbSpace = Number.isFinite(configuredOrbSpace)
        ? configuredOrbSpace
        : 0;

      if (isOrbCollapsed) {
        const availableWithOrb = Math.max(0, availableHeight - orbSpace);
        const shouldStayCollapsed =
          contentHeight > availableWithOrb - ORB_RESTORE_BUFFER;

        if (!shouldStayCollapsed) {
          onScrollableChange(false);
        }
        return;
      }

      if (contentHeight > availableHeight + OVERFLOW_EPSILON) {
        onScrollableChange(true);
      }
    };

    const scheduleMeasurement = () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }
      animationFrameId = window.requestAnimationFrame(measureOverflow);
    };

    let resizeObserver = null;
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(scheduleMeasurement);
      resizeObserver.observe(chatBox);
      resizeObserver.observe(chatThread);
    }

    scheduleMeasurement();
    window.addEventListener("resize", scheduleMeasurement);

    return () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }
      resizeObserver?.disconnect();
      window.removeEventListener("resize", scheduleMeasurement);
    };
  }, [freezeOverflowMeasurements, isOrbCollapsed, messages, onScrollableChange]);

  // If the reader was already at the newest message, keep that position while
  // the orb's smooth height transition changes the chat viewport.
  useLayoutEffect(() => {
    if (previousOrbStateRef.current === isOrbCollapsed) return undefined;
    previousOrbStateRef.current = isOrbCollapsed;

    const chatBox = chatBoxRef.current;
    if (!chatBox || !wasNearBottomRef.current) return undefined;

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const pinDuration = reducedMotion ? 34 : 300;
    const startedAt = performance.now();
    let animationFrameId = null;

    const keepNewestMessageVisible = (now) => {
      chatBox.scrollTop = chatBox.scrollHeight;
      if (now - startedAt < pinDuration) {
        animationFrameId = window.requestAnimationFrame(
          keepNewestMessageVisible,
        );
      }
    };

    animationFrameId = window.requestAnimationFrame(keepNewestMessageVisible);

    return () => {
      if (animationFrameId !== null) {
        window.cancelAnimationFrame(animationFrameId);
      }
    };
  }, [isOrbCollapsed]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }, [messages]);

  // While the visible assistant transcript grows with its speech, keep the
  // newest line in view only for readers who were already at the bottom.
  useLayoutEffect(() => {
    const chatBox = chatBoxRef.current;
    if (!revealedMessageId || !chatBox || !wasNearBottomRef.current) return;

    chatBox.scrollTop = chatBox.scrollHeight;
  }, [revealedMessageId, revealedText]);

  const greeting = `Good ${getGreetingPeriod(localHour)}${userName ? `, ${userName}` : ""}`;
  const userInitial = userName.match(/[\p{L}\p{N}]/u)?.[0]?.toLocaleUpperCase() || "U";

  return (
    <div className="chat-box" ref={chatBoxRef}>
      {messages.length === 0 ? (
        <div className="empty-chat">
          <div className="empty-hero">
            <h2 className="time-greeting">{greeting}</h2>
            <h3>How can I help?</h3>
            <p>Speak naturally or type a message to begin.</p>
          </div>
        </div>
      ) : (
        <div className="chat-thread" ref={chatThreadRef}>
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              sender={msg.sender}
              text={msg.text}
              displayText={
                revealedMessageId === msg.id ? revealedText : msg.text
              }
              audioUrl={msg.audioUrl}
              playAudio={playAudio}
              type={msg.type || "text"}
              responseMode={msg.responseMode || "text"}
              voiceAudioBlob={msg.voiceAudioBlob}
              voiceDuration={msg.voiceDuration}
              userInitial={userInitial}
            />
          ))}
          <div ref={chatEndRef} />
        </div>
      )}
    </div>
  );
}

export default ChatWindow;
