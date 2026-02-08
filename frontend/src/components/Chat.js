import React, { useState, useEffect, useRef } from "react";
import {
  FiSend,
  FiUser,
  FiMic,
  FiMicOff,
  FiGlobe,
  FiCheck,
} from "react-icons/fi";
import mediverseLogo from "../mediverseLogo.png";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import "./Chat.css";

function Chat() {
  const [messages, setMessages] = useState([
    {
      text: "Hello, I am **MindWell AI** 💙\n\nHow are you feeling today?",
      sender: "bot",
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    },
  ]);

  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [language, setLanguage] = useState("en-US");
  const [showLangMenu, setShowLangMenu] = useState(false);

  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);
  const langMenuRef = useRef(null);

  const languages = [
    { code: "en-US", name: "English" },
    { code: "hi-IN", name: "Hindi" },
    { code: "mr-IN", name: "Marathi" },
  ];

  /* Auto scroll */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  /* Close language menu */
  useEffect(() => {
    const handler = (e) => {
      if (langMenuRef.current && !langMenuRef.current.contains(e.target)) {
        setShowLangMenu(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  /* 🎤 SPEECH TO TEXT */
  const handleMicClick = () => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert("Speech recognition not supported");
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = language;
    recognition.interimResults = false;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);

    recognition.onresult = (e) => {
      setInput(e.results[0][0].transcript);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  /* 🔊 TEXT TO SPEECH */
  const speakText = (text) => {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language;
    utterance.rate = 0.95;
    window.speechSynthesis.speak(utterance);
  };

  /* 🚀 SEND MESSAGE */
  const handleSendMessage = async () => {
    if (!input.trim()) return;

    const userMsg = {
      text: input,
      sender: "user",
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsLoading(true);

    try {
      const res = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: userMsg.text, language }),
      });

      const data = await res.json();

      const botText = data.reply || "I’m here with you 💙";

      const botMsg = {
        text: botText,
        sender: "bot",
        timestamp: new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      };

      setMessages((prev) => [...prev, botMsg]);
      speakText(botText);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          text: "I’m having trouble, but I’m still here 💙",
          sender: "bot",
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="chat-container">
      {/* HEADER */}
      <div className="chat-header-display">
        <div className="bot-status-indicator">
          <div className="status-dot" />
          <span>MindWell AI • Online</span>
        </div>

        <div className="header-right" ref={langMenuRef}>
          <button
            className="lang-toggle-btn"
            onClick={() => setShowLangMenu(!showLangMenu)}
          >
            <FiGlobe />
            {language.split("-")[0].toUpperCase()}
          </button>

          {showLangMenu && (
            <div className="lang-dropdown">
              {languages.map((l) => (
                <button
                  key={l.code}
                  className={`lang-option ${
                    language === l.code ? "active" : ""
                  }`}
                  onClick={() => {
                    setLanguage(l.code);
                    setShowLangMenu(false);
                  }}
                >
                  {l.name}
                  {language === l.code && <FiCheck />}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* MESSAGES */}
      <div className="messages-area">
        {messages.map((m, i) => (
          <div key={i} className={`message-wrapper ${m.sender}`}>
            <div className="message-avatar">
              {m.sender === "bot" ? (
                <img src={mediverseLogo} alt="AI" className="bot-img-avatar" />
              ) : (
                <div className="user-icon-avatar">
                  <FiUser />
                </div>
              )}
            </div>

            <div className="message-bubble">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => (
                    <p className="md-p">{children}</p>
                  ),
                  li: ({ children }) => (
                    <li className="md-li">{children}</li>
                  ),
                  strong: ({ children }) => (
                    <strong className="md-strong">{children}</strong>
                  ),
                }}
              >
                {m.text}
              </ReactMarkdown>

              <span className="timestamp">{m.timestamp}</span>
            </div>
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* INPUT */}
      <div className="input-area">
        <div className={`input-wrapper ${isListening ? "listening-mode" : ""}`}>
          <button
            className={`mic-btn ${isListening ? "listening" : ""}`}
            onClick={handleMicClick}
          >
            {isListening ? <FiMicOff /> : <FiMic />}
            {isListening && <span className="mic-pulse" />}
          </button>

          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) =>
              e.key === "Enter" && !e.shiftKey && handleSendMessage()
            }
            placeholder="Type your feelings…"
          />

          <button
            className="send-btn"
            onClick={handleSendMessage}
            disabled={!input.trim()}
          >
            <FiSend />
          </button>
        </div>
      </div>
    </div>
  );
}

export default Chat;
