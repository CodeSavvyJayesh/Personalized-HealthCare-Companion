"use client";

import { useState, useContext } from "react";
import {
  FiSearch,
  FiLogOut,
  FiEdit,
  FiBook,
  FiActivity,
  FiBarChart2,
  FiFolder,
} from "react-icons/fi";

import Signup from "./components/Signup";
import Login from "./components/Login";
import Chat from "./components/Chat";
import UserMenu from "./components/UserMenu";
import Dashboard from "./components/Dashboard";
import DailyRoutine from "./components/DailyRoutine";

import "./App.css";
import doctorImage from "./doctor.png";
import mediverseLogo from "./mediverseLogo.png";

import { ThemeContext } from "./ThemeContext";

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [showSidebar, setShowSidebar] = useState(false);

  // 🔥 CORE NAVIGATION STATE
  const [activeModule, setActiveModule] = useState("dashboard");

  const [userEmail, setUserEmail] = useState("");
  const { darkMode } = useContext(ThemeContext);

  const handleLogout = () => {
    setIsLoggedIn(false);
    setActiveModule("dashboard");
    setShowSidebar(false);
    setUserEmail("");
  };

  const toggleSidebar = () => {
    setShowSidebar(!showSidebar);
  };

  const goToDashboard = () => {
    setActiveModule("dashboard");
    setShowSidebar(false);
  };

  /* =========================
     AUTH
  ========================= */
  if (!isLoggedIn) {
    return (
      <div className="main-container">
        <div className="auth-wrapper">
          <div className="auth-left">
            <img src={doctorImage} alt="Doctor" />
          </div>

          <div className="auth-right">
            {showSignup ? (
              <>
                <Signup onSignupSuccess={() => setShowSignup(false)} />
                <p>
                  Already have an account?{" "}
                  <button onClick={() => setShowSignup(false)}>Log in</button>
                </p>
              </>
            ) : (
              <>
                <Login
                  onLoginSuccess={(email) => {
                    setIsLoggedIn(true);
                    setUserEmail(email);
                  }}
                />
                <p>
                  Don&apos;t have an account?{" "}
                  <button onClick={() => setShowSignup(true)}>Sign up</button>
                </p>
              </>
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
    <div className={`main-container ${darkMode ? "dark" : ""}`}>
      {showSidebar && (
        <div
          className="sidebar-overlay"
          onClick={() => setShowSidebar(false)}
        />
      )}

      {/* SIDEBAR */}
      <div className={`sidebar ${showSidebar ? "sidebar-open" : ""}`}>
        <div className="sidebar-header">
          <img
            src={mediverseLogo}
            alt="MindWell Logo"
            className="logo-img clickable"
            onClick={toggleSidebar}
          />
          <span className="sidebar-title">MindWell</span>
        </div>

        <div className="sidebar-menu">
          <div className="sidebar-item">
            <FiEdit color="#8395eb" />
            <span>New therapy session</span>
          </div>

          <div className="sidebar-item">
            <FiSearch color="#8395eb" />
            <span>Search conversations</span>
          </div>

          <div className="sidebar-item">
            <FiBook color="#8395eb" />
            <span>Mental health library</span>
          </div>

          <div className="sidebar-item">
            <FiActivity color="#8395eb" />
            <span>Mindfulness exercises</span>
          </div>

          <div className="sidebar-item">
            <FiBarChart2 color="#8395eb" />
            <span>Progress tracking</span>
          </div>

          <div className="sidebar-item">
            <FiFolder color="#8395eb" />
            <span>My sessions</span>
            <span className="sidebar-badge">NEW</span>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-item sidebar-logout" onClick={handleLogout}>
            <FiLogOut />
            <span>Log out</span>
          </div>
        </div>
      </div>

      {/* TOP BAR */}
      <div className="top-bar">
        <div className="logo-container">
          <img
            src={mediverseLogo}
            alt="MindWell Logo"
            className="logo-img clickable"
            onClick={toggleSidebar}
          />
          <span className="logo-text" onClick={goToDashboard}>
            MindWell
          </span>
        </div>

        <UserMenu
          onLogout={handleLogout}
          userEmail={userEmail}
          onOpenChat={() => setActiveModule("chat")}
        />
      </div>

      {/* MAIN CONTENT */}
      <div className="content-area">
        {activeModule === "dashboard" && (
          <Dashboard
            onOpenChat={() => setActiveModule("chat")}
            onOpenDailyRoutine={() => setActiveModule("dailyRoutine")}
          />
        )}

        {activeModule === "chat" && <Chat />}

        {activeModule === "dailyRoutine" && (
          <DailyRoutine onBack={() => setActiveModule("dashboard")} />
        )}
      </div>
    </div>
  );
}

export default App;
