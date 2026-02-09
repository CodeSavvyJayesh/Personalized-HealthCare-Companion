import React, { useState, useEffect, useRef } from "react";
import {
  FiSend,
  FiUser,
  FiMic,
  FiMicOff,
  FiGlobe,
  FiCheck,
  FiVolume2,
  FiVolumeX,
  FiRefreshCw,
} from "react-icons/fi";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import mediverseLogo from "../mediverseLogo.png";
import "./Chat.css";

function Chat() {
  const [messages, setMessages] = useState([
    {
      text: "Hello, I am **MindWell AI** 💙\n\nI'm here to listen and support you. How are you feeling right now?",
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
  const [isTTSActive, setIsTTSActive] = useState(true);

  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const langMenuRef = useRef(null);
  const recognitionRef = useRef(null);
  const voicesRef = useRef([]);

  const languages = [
    { code: "en-US", name: "English (US)" },
    { code: "hi-IN", name: "Hindi" },
    { code: "mr-IN", name: "Marathi" },
  ];

  // Auto scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isLoading]);

  // Load voices
  useEffect(() => {
    const loadVoices = () => {
      voicesRef.current = window.speechSynthesis.getVoices();
    };
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;

    // Cleanup
    return () => {
      window.speechSynthesis.cancel();
    };
  }, []);

  // Handle outside click for language menu
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (langMenuRef.current && !langMenuRef.current.contains(event.target)) {
        setShowLangMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Speech Recognition Logic
  const handleMicClick = () => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert(
        "Your browser does not support voice input. Please use Chrome or Edge.",
      );
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
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setIsListening(true);
    recognition.onend = () => setIsListening(false);
    recognition.onerror = (event) => {
      console.error("Speech recognition error", event.error);
      setIsListening(false);
    };

    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      setInput((prev) => prev + (prev && transcript ? " " : "") + transcript);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  // Text to Speech Logic
  const speakText = (text) => {
    if (!window.speechSynthesis || !isTTSActive) return;

    window.speechSynthesis.cancel();

    // Strip markdown characters for cleaner speech
    const cleanText = text.replace(/[*#_`]/g, "");

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = language;
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    // Attempt to select a voice matching the language
    const voices = voicesRef.current;
    const voice =
      voices.find((v) => v.lang === language) ||
      voices.find((v) => v.lang.startsWith(language.split("-")[0]));

    if (voice) {
      utterance.voice = voice;
    }

    window.speechSynthesis.speak(utterance);
  };

  const handleSendMessage = async () => {
    if (!input.trim()) return;

    const userMessage = {
      text: input,
      sender: "user",
      timestamp: new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      }),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await fetch("http://127.0.0.1:8000/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          text: userMessage.text,
          language: language,
        }),
      });

      const data = await response.json();

      // Artificial delay for "thinking" effect if response is too instant
      setTimeout(() => {
        const replyText =
          data.response || data.reply || "I am listening. Please go on.";
        const botMessage = {
          text: replyText,
          sender: "bot",
          timestamp: new Date().toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          }),
        };
        setMessages((prev) => [...prev, botMessage]);
        setIsLoading(false);
        speakText(replyText);
      }, 600);
    } catch (error) {
      console.error("Error sending message:", error);
      setTimeout(() => {
        const errorMsg =
          "I'm having trouble connecting to my thought process right now. Please check your connection or try again in a moment.";
        setMessages((prev) => [
          ...prev,
          {
            text: errorMsg,
            sender: "bot",
            timestamp: new Date().toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            }),
          },
        ]);
        setIsLoading(false);
      }, 1000);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const toggleTTS = () => {
    setIsTTSActive(!isTTSActive);
    if (isTTSActive) {
      window.speechSynthesis.cancel();
    }
  };

  return (
    <div className="chat-container">
      {/* Header */}
      <div className="chat-header-display">
        <div className="header-left">
          <div className="bot-status-indicator">
            <div className="status-dot"></div>
            <span className="status-text">MindWell AI • Online</span>
          </div>
        </div>

        <div className="header-right" ref={langMenuRef}>
          <button
            className="icon-btn"
            onClick={toggleTTS}
            title={isTTSActive ? "Mute Voice" : "Enable Voice"}
          >
            {isTTSActive ? <FiVolume2 size={18} /> : <FiVolumeX size={18} />}
          </button>

          <div className="lang-wrapper">
            <button
              className="lang-toggle-btn"
              onClick={() => setShowLangMenu(!showLangMenu)}
              title="Select Language"
            >
              <FiGlobe size={16} />
              <span className="lang-code">
                {language.split("-")[0].toUpperCase()}
              </span>
            </button>

            {showLangMenu && (
              <div className="lang-dropdown">
                {languages.map((lang) => (
                  <button
                    key={lang.code}
                    className={`lang-option ${language === lang.code ? "active" : ""}`}
                    onClick={() => {
                      setLanguage(lang.code);
                      setShowLangMenu(false);
                    }}
                  >
                    <span>{lang.name}</span>
                    {language === lang.code && <FiCheck size={14} />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="chat-safe-notice">
        <p>
          Your privacy is our priority. This is a secure, judgment-free zone.
        </p>
      </div>

      {/* Messages */}
      <div className="messages-area">
        {messages.map((msg, index) => (
          <div key={index} className={`message-wrapper ${msg.sender}`}>
            <div className="message-avatar">
              {msg.sender === "bot" ? (
                <div className="avatar-frame bot">
                  <img src={mediverseLogo} alt="AI" />
                </div>
              ) : (
                <div className="avatar-frame user">
                  <FiUser />
                </div>
              )}
            </div>
            <div className="message-bubble">
              {msg.sender === "bot" ? (
                <div className="markdown-content">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.text}
                  </ReactMarkdown>
                </div>
              ) : (
                <p>{msg.text}</p>
              )}
              <span className="timestamp">{msg.timestamp}</span>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="message-wrapper bot">
            <div className="message-avatar">
              <div className="avatar-frame bot">
                <img src={mediverseLogo} alt="AI" />
              </div>
            </div>
            <div className="message-bubble typing-bubble">
              <div className="typing-dots">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Area */}
      <div className="input-area">
        <div
          className={`input-container ${isListening ? "listening-active" : ""}`}
        >
          <button
            className={`mic-btn ${isListening ? "is-listening" : ""}`}
            onClick={handleMicClick}
            title={isListening ? "Stop Listening" : "Start Voice Input"}
          >
            {isListening ? <FiMicOff size={20} /> : <FiMic size={20} />}
            {isListening && <span className="mic-ripple"></span>}
          </button>

          <textarea
            ref={inputRef}
            placeholder={
              isListening ? "Listening..." : "Type your feelings here..."
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyPress}
            rows={1}
            className="chat-textarea"
          />

          <button
            onClick={handleSendMessage}
            className="send-btn"
            disabled={!input.trim()}
          >
            <FiSend size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default Chat;
