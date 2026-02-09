import React, { useState, useContext } from "react";
import { ThemeContext } from "./ThemeContext";
import Login from "./components/Login";
import Signup from "./components/Signup";
import Dashboard from "./components/Dashboard";
import Chat from "./components/Chat";
import UserMenu from "./components/UserMenu";
import DailyRoutine from "./components/DailyRoutine"; // Assuming this exists or kept as placeholder
import mediverseLogo from "./mediverseLogo.png";
import doctorImage from "./doctor.png";

// Icons
import {
  FiHome,
  FiMessageSquare,
  FiCalendar,
  FiSettings,
  FiMenu,
  FiX,
  FiActivity,
  FiBookOpen,
  FiLogOut,
} from "react-icons/fi";

import "./App.css";

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [activeModule, setActiveModule] = useState("dashboard"); // dashboard, chat, dailyRoutine
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [userEmail, setUserEmail] = useState("");

  // Theme context is used inside components, but App layout needs to structure the page
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
    setIsSidebarOpen(!isSidebarOpen);
  };

  const navigateTo = (moduleName) => {
    setActiveModule(moduleName);
    // On mobile, close sidebar after navigation
    if (window.innerWidth < 768) {
      setIsSidebarOpen(false);
    }
  };

  // Auth Screen
  if (!isLoggedIn) {
    return (
      <div className="auth-layout">
        <div className="auth-wrapper">
          <div className="auth-left">
            <div className="auth-decoration"></div>
            <img src={doctorImage} alt="Doctor" className="doctor-img" />
            <div className="auth-welcome">
              <h1>Welcome to MindWell</h1>
              <p>Your personalized mental health companion.</p>
            </div>
          </div>
          <div className="auth-right">
            {showSignup ? (
              <Signup
                onSignupSuccess={() => setShowSignup(false)}
                onSwitch={() => setShowSignup(false)}
              />
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
      className={`app-container ${isSidebarOpen ? "sidebar-expanded" : "sidebar-collapsed"}`}
    >
      {/* Sidebar */}
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

          <button className="nav-item">
            <FiActivity size={20} />
            {isSidebarOpen && <span>Progress</span>}
          </button>

          <button className="nav-item">
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

      {/* Main Content Area */}
      <main className="main-content">
        {/* Navbar */}
        <header className="navbar">
          <div className="navbar-left">
            <button className="menu-toggle" onClick={toggleSidebar}>
              {isSidebarOpen ? <FiX size={24} /> : <FiMenu size={24} />}
            </button>
            <h2 className="page-title">
              {activeModule === "dashboard" && "Dashboard"}
              {activeModule === "chat" && "MindWell Therapist"}
              {activeModule === "dailyRoutine" && "Daily Routine"}
            </h2>
          </div>

          <div className="navbar-right">
            {/* User Menu passes navigation handler to enable Chat from dropdown */}
            <UserMenu
              userEmail={userEmail}
              onLogout={handleLogout}
              onEnableChat={() => navigateTo("chat")}
            />
          </div>
        </header>

        {/* Dynamic Content */}
        {/* Added dynamic class to handle scrolling differently for chat vs dashboard */}
        <div
          className={`content-scrollable ${activeModule === "chat" ? "chat-mode" : ""}`}
        >
          {activeModule === "dashboard" && (
            <Dashboard onNavigate={navigateTo} />
          )}
          {activeModule === "chat" && <Chat />}
          {activeModule === "dailyRoutine" && <DailyRoutine />}
        </div>
      </main>
    </div>
  );
}

export default App;
