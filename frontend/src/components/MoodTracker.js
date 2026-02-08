"use client";

import { useState, useEffect } from "react";
import {
  FiArrowLeft,
  FiTrendingUp,
  FiCalendar,
  FiEdit3,
  FiStar,
} from "react-icons/fi";
import "./MoodTracker.css";

const MOODS = [
  { id: "happy", label: "Happy", emoji: "😄", score: 5 },
  { id: "calm", label: "Calm", emoji: "😌", score: 4 },
  { id: "neutral", label: "Neutral", emoji: "😐", score: 3 },
  { id: "sad", label: "Sad", emoji: "😞", score: 2 },
  { id: "anxious", label: "Anxious", emoji: "😟", score: 1 },
];

const TAGS = [
  "Work",
  "Family",
  "Health",
  "Friends",
  "Sleep",
  "Stress",
  "Self-care",
  "Social",
];

export default function MoodTracker({ onBack }) {
  const today = new Date().toDateString();

  const [mood, setMood] = useState(null);
  const [intensity, setIntensity] = useState(5);
  const [energy, setEnergy] = useState(5);
  const [note, setNote] = useState("");
  const [tags, setTags] = useState([]);
  const [history, setHistory] = useState([]);

  /* LOAD */
  useEffect(() => {
    const stored = JSON.parse(localStorage.getItem("moodHistory")) || [];
    setHistory(stored);

    const todayEntry = stored.find((e) => e.date === today);
    if (todayEntry) {
      setMood(todayEntry.mood);
      setIntensity(todayEntry.intensity);
      setEnergy(todayEntry.energy);
      setNote(todayEntry.note);
      setTags(todayEntry.tags);
    }
  }, []);

  /* SAVE */
  const saveMood = () => {
    if (!mood) return;

    const entry = {
      date: today,
      mood,
      intensity,
      energy,
      note,
      tags,
      score: mood.score,
    };

    const updated = [
      entry,
      ...history.filter((e) => e.date !== today),
    ];

    setHistory(updated);
    localStorage.setItem("moodHistory", JSON.stringify(updated));
  };

  /* ANALYTICS */
  const avgMood =
    history.length === 0
      ? 0
      : (
          history.reduce((a, b) => a + b.score, 0) /
          history.length
        ).toFixed(1);

  const streak = (() => {
    let s = 0;
    let d = new Date();
    for (let i = 0; i < history.length; i++) {
      if (history.find((e) => e.date === d.toDateString())) {
        s++;
        d.setDate(d.getDate() - 1);
      } else break;
    }
    return s;
  })();

  return (
    <div className="mood-root">
      {/* HEADER */}
      <div className="mood-header">
        <button className="back-btn" onClick={onBack}>
          <FiArrowLeft /> Back
        </button>

        <div>
          <h1>Mood Tracker</h1>
          <p>Understand your emotions deeply 🌱</p>
        </div>
      </div>

      {/* MOOD PICK */}
      <div className="glass mood-section">
        <h2>How do you feel today?</h2>
        <div className="mood-grid">
          {MOODS.map((m) => (
            <button
              key={m.id}
              className={`mood-card ${
                mood?.id === m.id ? "active" : ""
              }`}
              onClick={() => setMood(m)}
            >
              <span className="emoji">{m.emoji}</span>
              <span>{m.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* SLIDERS */}
      {mood && (
        <div className="glass mood-section">
          <div className="slider-block">
            <label>Intensity: {intensity}/10</label>
            <input
              type="range"
              min="1"
              max="10"
              value={intensity}
              onChange={(e) => setIntensity(e.target.value)}
            />
          </div>

          <div className="slider-block">
            <label>Energy Level: {energy}/10</label>
            <input
              type="range"
              min="1"
              max="10"
              value={energy}
              onChange={(e) => setEnergy(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* TAGS */}
      {mood && (
        <div className="glass mood-section">
          <h2>What influenced your mood?</h2>
          <div className="tag-grid">
            {TAGS.map((t) => (
              <button
                key={t}
                className={`tag ${
                  tags.includes(t) ? "active" : ""
                }`}
                onClick={() =>
                  setTags((prev) =>
                    prev.includes(t)
                      ? prev.filter((x) => x !== t)
                      : [...prev, t]
                  )
                }
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* JOURNAL */}
      {mood && (
        <div className="glass mood-section">
          <h2>Reflection</h2>
          <textarea
            placeholder="Write what’s on your mind…"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </div>
      )}

      {/* SAVE */}
      {mood && (
        <div className="save-area">
          <button className="save-btn" onClick={saveMood}>
            Save Today’s Mood
          </button>
        </div>
      )}

      {/* ANALYTICS */}
      {history.length > 0 && (
        <div className="glass mood-section analytics">
          <h2>
            <FiTrendingUp /> Insights
          </h2>

          <div className="stats">
            <div className="stat">
              <strong>{avgMood}</strong>
              <span>Avg Mood</span>
            </div>
            <div className="stat">
              <strong>{streak}</strong>
              <span>Day Streak</span>
            </div>
            <div className="stat">
              <strong>{history.length}</strong>
              <span>Total Logs</span>
            </div>
          </div>
        </div>
      )}

      {/* HISTORY */}
      {history.length > 0 && (
        <div className="glass mood-section">
          <h2>
            <FiCalendar /> Mood History
          </h2>

          <div className="history">
            {history.map((h, i) => (
              <div key={i} className="history-item">
                <span>{h.mood.emoji}</span>
                <div>
                  <strong>{h.mood.label}</strong>
                  <p>{h.date}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}