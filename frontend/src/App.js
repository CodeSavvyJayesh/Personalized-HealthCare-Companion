import React, { useState, useContext } from "react";
import { ThemeContext } from "./ThemeContext";

import Login from "./components/Login";
import Signup from "./components/Signup";
import Dashboard from "./components/Dashboard";
import Chat from "./components/Chat";
import UserMenu from "./components/UserMenu";
import DailyRoutine from "./components/DailyRoutine";
import MoodTracker from "./components/MoodTracker";

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
} from "react-icons/fi";

import "./App.css";

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showSignup, setShowSignup] = useState(false);

  // 🔥 CORE NAVIGATION
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

  const toggleSidebar = () => {
    setIsSidebarOpen((p) => !p);
  };

  const navigateTo = (module) => {
    setActiveModule(module);
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  };

  /* =========================
     AUTH SCREENS
  ========================= */
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

  /* =========================
     MAIN APP
  ========================= */
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
            className={`nav-item ${
              activeModule === "dashboard" ? "active" : ""
            }`}
            onClick={() => navigateTo("dashboard")}
          >
            <FiHome />
            {isSidebarOpen && <span>Dashboard</span>}
          </button>

          <button
            className={`nav-item ${
              activeModule === "chat" ? "active" : ""
            }`}
            onClick={() => navigateTo("chat")}
          >
            <FiMessageSquare />
            {isSidebarOpen && <span>Therapist AI</span>}
          </button>

          <button
            className={`nav-item ${
              activeModule === "dailyRoutine" ? "active" : ""
            }`}
            onClick={() => navigateTo("dailyRoutine")}
          >
            <FiCalendar />
            {isSidebarOpen && <span>Daily Routine</span>}
          </button>

          {/* 🔥 MOOD TRACKER CONNECTED */}
          <button
            className={`nav-item ${
              activeModule === "mood" ? "active" : ""
            }`}
            onClick={() => navigateTo("mood")}
          >
            <FiSmile />
            {isSidebarOpen && <span>Mood Tracker</span>}
          </button>

          <button className="nav-item">
            <FiActivity />
            {isSidebarOpen && <span>Insights</span>}
          </button>

          <button className="nav-item">
            <FiBookOpen />
            {isSidebarOpen && <span>Resources</span>}
          </button>
        </nav>

        <div className="sidebar-footer">
          <button className="nav-item logout-btn" onClick={handleLogout}>
            <FiLogOut />
            {isSidebarOpen && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="main-content">
        {/* TOP NAVBAR */}
        <header className="navbar">
          <div className="navbar-left">
            <button className="menu-toggle" onClick={toggleSidebar}>
              {isSidebarOpen ? <FiX /> : <FiMenu />}
            </button>

            <h2 className="page-title">
              {activeModule === "dashboard" && "Dashboard"}
              {activeModule === "chat" && "MindWell Therapist"}
              {activeModule === "dailyRoutine" && "Daily Routine"}
              {activeModule === "mood" && "Mood Tracker"}
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

        {/* MODULE RENDERING */}
        <div className="content-scrollable">
          {activeModule === "dashboard" && (
            <Dashboard onNavigate={navigateTo} />
          )}

          {activeModule === "chat" && <Chat />}

          {activeModule === "dailyRoutine" && <DailyRoutine />}

          {activeModule === "mood" && <MoodTracker />}
        </div>
      </main>
    </div>
  );
}

export default App;