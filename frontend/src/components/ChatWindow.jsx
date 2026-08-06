import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";

function ChatWindow({ messages, playAudio, onSelectSuggestion }) {
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages]);

  const suggestions = [
    "Hi! My name is Alex, I'm a Senior Engineer at TechCorp in San Francisco.",
    "I prefer concise technical answers and Python solutions.",
    "What do you remember about me?",
    "Can you summarize my profile and long-term memories?",
  ];

  return (
    <div className="chat-box">
      {messages.length === 0 ? (
        <div className="empty-chat">
          <div className="empty-hero">
            <div className="sparkle-icon">⚡</div>
            <h3>Welcome to Enterprise Voice Assistant</h3>
            <p>Speak or type to converse with AI. Important facts are automatically extracted into long-term memory!</p>
          </div>
          <div className="suggestion-pills">
            {suggestions.map((prompt, idx) => (
              <button
                key={idx}
                className="suggestion-pill"
                onClick={() => onSelectSuggestion(prompt)}
              >
                "{prompt}"
              </button>
            ))}
          </div>
        </div>
      ) : (
        messages.map((msg, index) => (
          <MessageBubble
            key={index}
            sender={msg.sender}
            text={msg.text}
            audioUrl={msg.audioUrl}
            playAudio={playAudio}
            type={msg.type || "text"}
            voiceAudioUrl={msg.voiceAudioUrl}
            voiceDuration={msg.voiceDuration}
          />
        ))
      )}

      <div ref={chatEndRef} />
    </div>
  );
}

export default ChatWindow;