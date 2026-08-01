import { useState } from "react";

function ChatInput({ message, setMessage, sendMessage }) {
  const [isSending, setIsSending] = useState(false);

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
    <div className="input-area">
      <textarea
        value={message}
        maxLength={1000}
        rows={2}
        autoComplete="off"
        spellCheck={false}
        autoFocus
        placeholder="Ask anything..."
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
      />

      <button
        onClick={handleSend}
        disabled={isSending}
      >
        {isSending ? "Thinking..." : "Send"}
      </button>
    </div>
  );
}

export default ChatInput;