import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";

function ChatWindow({ messages }) {
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages]);

  return (
    <div className="chat-box">
      {messages.length === 0 ? (
        <div className="empty-chat">
          Start a conversation with your AI assistant.
        </div>
      ) : (
        messages.map((msg, index) => (
          <MessageBubble
            key={index}
            sender={msg.sender}
            text={msg.text}
          />
        ))
      )}

      <div ref={chatEndRef} />
    </div>
  );
}

export default ChatWindow;