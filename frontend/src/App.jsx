import { useState } from "react";
import axios from "axios";
import "./App.css";

import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";

function App() {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);

  const sendMessage = async () => {
    if (!message.trim()) return;

    const userMessage = message.trim();

    setMessages((prev) => [
      ...prev,
      {
        sender: "You",
        text: userMessage,
      },
    ]);

    setMessage("");

    try {
      const response = await axios.post(
        "http://127.0.0.1:8000/chat",
        {
          message: userMessage,
        }
      );

      setMessages((prev) => [
        ...prev,
        {
          sender: "AI",
          text: response.data.reply,
        },
      ]);

      if (response.data.audio_url) {
        const audio = new Audio(
          `http://127.0.0.1:8000${response.data.audio_url}`
        );

        await audio.play();
      }
    } catch (error) {
      console.error(error);

      setMessages((prev) => [
        ...prev,
        {
          sender: "System",
          text: "Unable to contact the server.",
        },
      ]);
    }
  };

  return (
    <div className="container">
      <h1>Enterprise Voice Assistant</h1>

      <ChatWindow messages={messages} />

      <ChatInput
        message={message}
        setMessage={setMessage}
        sendMessage={sendMessage}
      />
    </div>
  );
}

export default App;