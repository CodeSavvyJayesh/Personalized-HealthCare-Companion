"use client";

import {
  FiMessageCircle,
  FiActivity,
  FiMoon,
  FiDroplet,
  FiBarChart2,
  FiHeart,
  FiCoffee,
  FiCalendar,
  FiSmile,
  FiTrendingUp
} from "react-icons/fi";

import "./Dashboard.css";

export default function Dashboard({ onOpenChat, onOpenDailyRoutine }) {
  const cards = [
    {
      title: "MindWell AI",
      desc: "Talk to your mental health companion",
      icon: <FiMessageCircle />,
      primary: true,
      action: onOpenChat
    },
    {
      title: "Workout Plan",
      desc: "AI-powered personalized workouts",
      icon: <FiActivity />
    },
    {
      title: "Sleep Tracker",
      desc: "Track rest & recovery",
      icon: <FiMoon />
    },
    {
      title: "Hydration",
      desc: "Monitor daily water intake",
      icon: <FiDroplet />
    },
    {
      title: "Nutrition Planner",
      desc: "AI-based diet & meal suggestions",
      icon: <FiCoffee />
    },
    {
      title: "Daily Routine",
      desc: "Plan your day for balance",
      icon: <FiCalendar />,
      action: onOpenDailyRoutine
    },
    {
      title: "Mood Tracker",
      desc: "Log mood & emotional trends",
      icon: <FiSmile />
    },
    {
      title: "Mindfulness",
      desc: "Relax with guided exercises",
      icon: <FiHeart />
    },
    {
      title: "Progress",
      desc: "Track your health journey",
      icon: <FiBarChart2 />
    },
    {
      title: "Health Insights",
      desc: "Weekly & monthly analysis",
      icon: <FiTrendingUp />
    }
  ];

  return (
    <div className="dashboard">
      <div className="dashboard-header">
        <h1>Your Health Dashboard</h1>
        <p>Personalized care for your mind and body</p>
      </div>

      <div className="dashboard-grid">
        {cards.map((card, index) => (
          <div
            key={index}
            className={`dashboard-card ${card.primary ? "primary" : ""}`}
            onClick={card.action}
          >
            <div className="card-icon">{card.icon}</div>
            <h3>{card.title}</h3>
            <p>{card.desc}</p>
            <button>Open</button>
          </div>
        ))}
      </div>
    </div>
  );
}
