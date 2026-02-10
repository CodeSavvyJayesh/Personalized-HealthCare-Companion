import React, { useState, useContext } from "react";
import { ThemeContext } from "./ThemeContext";

import Login from "./components/Login";
import Signup from "./components/Signup";
import Dashboard from "./components/Dashboard";
import Chat from "./components/Chat";
import UserMenu from "./components/UserMenu";
import DailyRoutine from "./components/DailyRoutine";
import MoodTracker from "./components/MoodTracker";
import Journaling from "./components/Journaling";
import CalmSounds from "./components/CalmSounds";
import Resources from "./components/Resources/Resources";
import Meditation from "./components/Meditation"; // Imported Meditation

import mediverseLogo from "./mediverseLogo.png";
import doctorImage from "./doctor.png";

import {
  FiHome,
  FiMessageSquare,
  FiCalendar,
  FiSmile,
  FiActivity,
  FiBookOpen,
  FiLogOut,
  FiMenu,
  FiX,
  FiMoon, // Imported for Meditation icon
} from "react-icons/fi";

import "./App.css";

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [activeModule, setActiveModule] = useState("dashboard");
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [userEmail, setUserEmail] = useState("");

  const { darkMode } = useContext(ThemeContext);

  const handleLoginSuccess = (email) => {
    setUserEmail(email);
    setIsLoggedIn(true);
  };

  const handleLogout = () => {
    setIsLoggedIn(false);
    setActiveModule("dashboard");
    setUserEmail("");
  };

  const toggleSidebar = () => setIsSidebarOpen((prev) => !prev);

  const navigateTo = (module) => {
    setActiveModule(module);
    if (window.innerWidth < 768) setIsSidebarOpen(false);
  };

  if (!isLoggedIn) {
    return (
      <div className="auth-layout">
        <div className="auth-wrapper">
          <div className="auth-left">
            <img src={doctorImage} alt="Doctor" className="doctor-img" />
            <div className="auth-welcome">
              <h1>Welcome to MindWell</h1>
              <p>Your personalized mental health companion</p>
            </div>
          </div>
          <div className="auth-right">
            {showSignup ? (
              <Signup onSignupSuccess={() => setShowSignup(false)} />
            ) : (
              <Login
                onLoginSuccess={handleLoginSuccess}
                onSwitch={() => setShowSignup(true)}
              />
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`app-container ${
        isSidebarOpen ? "sidebar-expanded" : "sidebar-collapsed"
      } ${darkMode ? "dark" : ""}`}
    >
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <img src={mediverseLogo} alt="MindWell" className="app-logo" />
          {isSidebarOpen && <span className="app-name">MindWell</span>}
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-item ${activeModule === "dashboard" ? "active" : ""}`}
            onClick={() => navigateTo("dashboard")}
          >
            <FiHome size={20} />
            {isSidebarOpen && <span>Dashboard</span>}
          </button>

          <button
            className={`nav-item ${activeModule === "chat" ? "active" : ""}`}
            onClick={() => navigateTo("chat")}
          >
            <FiMessageSquare size={20} />
            {isSidebarOpen && <span>Therapist AI</span>}
          </button>

          <button
            className={`nav-item ${activeModule === "dailyRoutine" ? "active" : ""}`}
            onClick={() => navigateTo("dailyRoutine")}
          >
            <FiCalendar size={20} />
            {isSidebarOpen && <span>Daily Routine</span>}
          </button>

          <button
            className={`nav-item ${activeModule === "meditation" ? "active" : ""}`}
            onClick={() => navigateTo("meditation")}
          >
            <FiMoon size={20} />
            {isSidebarOpen && <span>Meditation</span>}
          </button>

          <button
            className={`nav-item ${activeModule === "mood" ? "active" : ""}`}
            onClick={() => navigateTo("mood")}
          >
            <FiSmile size={20} />
            {isSidebarOpen && <span>Mood Tracker</span>}
          </button>

          <button
            className={`nav-item ${activeModule === "journaling" ? "active" : ""}`}
            onClick={() => navigateTo("journaling")}
          >
            <FiBookOpen size={20} />
            {isSidebarOpen && <span>Journaling</span>}
          </button>

          <button
            className={`nav-item ${activeModule === "calmSounds" ? "active" : ""}`}
            onClick={() => navigateTo("calmSounds")}
          >
            <FiActivity size={20} />
            {isSidebarOpen && <span>Calm Sounds</span>}
          </button>

          <button
            className={`nav-item ${activeModule === "resources" ? "active" : ""}`}
            onClick={() => navigateTo("resources")}
          >
            <FiBookOpen size={20} />
            {isSidebarOpen && <span>Resources</span>}
          </button>
        </nav>

        <div className="sidebar-footer">
          <button className="nav-item logout-btn" onClick={handleLogout}>
            <FiLogOut size={20} />
            {isSidebarOpen && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="main-content">
        <header className="navbar">
          <div className="navbar-left">
            <button className="menu-toggle" onClick={toggleSidebar}>
              {isSidebarOpen ? <FiX size={24} /> : <FiMenu size={24} />}
            </button>

            <h2 className="page-title">
              {activeModule === "dashboard" && "Dashboard"}
              {activeModule === "chat" && "MindWell Therapist"}
              {activeModule === "dailyRoutine" && "Daily Routine"}
              {activeModule === "meditation" && "Meditation & Focus"}
              {activeModule === "mood" && "Mood Tracker"}
              {activeModule === "journaling" && "Journaling"}
              {activeModule === "calmSounds" && "Calm Sounds"}
              {activeModule === "resources" && "Resources"}
            </h2>
          </div>

          <div className="navbar-right">
            <UserMenu
              userEmail={userEmail}
              onLogout={handleLogout}
              onEnableChat={() => navigateTo("chat")}
            />
          </div>
        </header>

        {/* content-scrollable with chat-mode conditional class for better scrolling */}
        <div
          className={`content-scrollable ${activeModule === "chat" ? "chat-mode" : ""}`}
        >
          {activeModule === "dashboard" && (
            <Dashboard onNavigate={navigateTo} />
          )}
          {activeModule === "chat" && <Chat />}
          {activeModule === "dailyRoutine" && <DailyRoutine />}
          {activeModule === "meditation" && <Meditation />}
          {activeModule === "mood" && <MoodTracker />}
          {activeModule === "journaling" && <Journaling />}
          {activeModule === "calmSounds" && <CalmSounds />}
          {activeModule === "resources" && <Resources />}
        </div>
      </main>
    </div>
  );
}

export default App;
