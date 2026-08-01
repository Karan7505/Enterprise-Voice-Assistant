function MessageBubble({ sender, text }) {
  const isUser = sender === "You";

  return (
    <div className={isUser ? "user-message" : "ai-message"}>
      <div className="sender">{sender}</div>

      <div className="message-text">
        {text}
      </div>
    </div>
  );
}

export default MessageBubble;