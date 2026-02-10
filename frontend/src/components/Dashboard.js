import React from "react";
import {
  FiMessageSquare,
  FiCalendar,
  FiActivity,
  FiMoon,
  FiSmile,
  FiBook,
  FiMusic,
  FiUsers,
  FiTrendingUp,
  FiTarget,
  FiBookOpen, // Added for Resources
} from "react-icons/fi";
import "./Dashboard.css";

function Dashboard({ onNavigate }) {
  const modules = [
    {
      id: "chat",
      title: "MindWell AI",
      desc: "Chat with your personal AI therapist available 24/7.",
      icon: <FiMessageSquare size={28} />,
      color: "var(--accent-color)",
      isPrimary: true,
    },
    {
      id: "meditation",
      title: "Meditation",
      desc: "Guided sessions to help you relax and focus.",
      icon: <FiMoon size={28} />,
      color: "#8b5cf6",
    },
    {
      id: "dailyRoutine",
      title: "Daily Routine",
      desc: "Track your habits and maintain a healthy lifestyle.",
      icon: <FiCalendar size={28} />,
      color: "#10b981",
    },
    {
      id: "mood",
      title: "Mood Tracker",
      desc: "Log your emotions and visualize your mental patterns.",
      icon: <FiSmile size={28} />,
      color: "#f59e0b",
    },
    {
      id: "journaling",
      title: "Journaling",
      desc: "Write down your thoughts securely.",
      icon: <FiBook size={28} />,
      color: "#ec4899",
    },
    {
      id: "calmSounds",
      title: "Calm Sounds",
      desc: "Curated playlists for relaxation.",
      icon: <FiMusic size={28} />,
      color: "#14b8a6",
    },
    {
      id: "resources",
      title: "Resources",
      desc: "Articles and guides for mental wellness.",
      icon: <FiBookOpen size={28} />,
      color: "#0ea5e9",
    },
    {
      id: "sleep",
      title: "Sleep Health",
      desc: "Analyze and improve your sleep quality.",
      icon: <FiActivity size={28} />,
      color: "#3b82f6",
    },
    {
      id: "community",
      title: "Community",
      desc: "Connect with others on similar journeys.",
      icon: <FiUsers size={28} />,
      color: "#f97316",
    },
    {
      id: "goals",
      title: "Goal Setting",
      desc: "Set achievable mental health goals.",
      icon: <FiTarget size={28} />,
      color: "#ef4444",
    },
    {
      id: "analytics",
      title: "Insights",
      desc: "Weekly reports on your progress.",
      icon: <FiTrendingUp size={28} />,
      color: "#6366f1",
    },
  ];

  // Helper to handle navigation only for implemented modules
  const handleModuleClick = (id) => {
    // List of modules that are fully implemented in App.js
    const implementedModules = [
      "chat",
      "meditation",
      "dailyRoutine",
      "mood",
      "journaling",
      "calmSounds",
      "resources",
    ];

    if (implementedModules.includes(id)) {
      onNavigate(id);
    } else {
      // Optional: You could show a toast here for "Coming Soon"
      // For now, we just don't navigate or navigate to dashboard (no-op)
      console.log(`Module ${id} is coming soon!`);
    }
  };

  return (
    <div className="dashboard-container">
      <div className="dashboard-header-section">
        <h1>Welcome Back!</h1>
        <p>How are you feeling today? Explore your wellness modules.</p>
      </div>

      <div className="modules-grid">
        {modules.map((module) => (
          <div
            key={module.id}
            className={`module-card ${module.isPrimary ? "primary-card" : ""}`}
            onClick={() => handleModuleClick(module.id)}
          >
            <div
              className="card-icon"
              style={{
                backgroundColor: `${module.color}20`,
                color: module.color,
              }}
            >
              {module.icon}
            </div>

            <div className="card-content">
              <h3>{module.title}</h3>
              <p>{module.desc}</p>
            </div>

            {module.isPrimary && (
              <button className="primary-btn">Start Session</button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default Dashboard;
