"use client";

import { useState, useEffect } from "react";
import {
  FiArrowLeft,
  FiPlus,
  FiTrash2,
  FiEdit2,
  FiStar,
  FiSmile,
} from "react-icons/fi";
import "./DailyRoutine.css";

const CATEGORIES = [
  { id: "morning", label: "Morning ☀️" },
  { id: "work", label: "Work 💻" },
  { id: "health", label: "Health 🏃" },
  { id: "self", label: "Self-care 🧘" },
  { id: "night", label: "Night 🌙" },
];

const MOODS = ["😄", "😊", "😐", "😔", "😴"];

export default function DailyRoutine({ onBack }) {
  const today = new Date().toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });

  const [tasks, setTasks] = useState([]);
  const [showModal, setShowModal] = useState(false);

  const [newTask, setNewTask] = useState("");
  const [newTime, setNewTime] = useState("");
  const [category, setCategory] = useState("morning");
  const [priority, setPriority] = useState(false);

  /* 🔐 Persist */
  useEffect(() => {
    const saved = localStorage.getItem("dailyTasks");
    if (saved) setTasks(JSON.parse(saved));
  }, []);

  useEffect(() => {
    localStorage.setItem("dailyTasks", JSON.stringify(tasks));
  }, [tasks]);

  const completedCount = tasks.filter((t) => t.done).length;
  const progress =
    tasks.length === 0 ? 0 : Math.round((completedCount / tasks.length) * 100);

  const addTask = () => {
    if (!newTask.trim()) return;

    setTasks((prev) => [
      ...prev,
      {
        id: Date.now(),
        title: newTask,
        time: newTime || "Anytime",
        category,
        priority,
        mood: "",
        done: false,
        editing: false,
      },
    ]);

    setNewTask("");
    setNewTime("");
    setPriority(false);
    setCategory("morning");
    setShowModal(false);
  };

  const toggleTask = (id) =>
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id ? { ...t, done: !t.done } : t
      )
    );

  const deleteTask = (id) =>
    setTasks((prev) => prev.filter((t) => t.id !== id));

  const toggleEdit = (id) =>
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id ? { ...t, editing: !t.editing } : t
      )
    );

  const updateTitle = (id, value) =>
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id ? { ...t, title: value } : t
      )
    );

  const setMood = (id, mood) =>
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id ? { ...t, mood } : t
      )
    );

  return (
    <div className="daily-routine">
      {/* HEADER */}
      <div className="routine-header">
        <button className="back-btn" onClick={onBack}>
          <FiArrowLeft /> Back
        </button>
        <div>
          <h1>Daily Routine</h1>
          <p>{today}</p>
        </div>
      </div>

      {/* PROGRESS */}
      <div className="routine-progress">
        <div className="progress-ring">
          <svg>
            <circle cx="36" cy="36" r="32" />
            <circle
              cx="36"
              cy="36"
              r="32"
              style={{
                strokeDashoffset: 200 - (200 * progress) / 100,
              }}
            />
          </svg>
          <span>{progress}%</span>
        </div>

        <div className="progress-text">
          <strong>{completedCount}</strong> / {tasks.length} done
          <p className="motivation">
            {progress === 100
              ? "Perfect day 🌟"
              : progress >= 60
              ? "Almost there 💪"
              : "One task at a time 🌱"}
          </p>
        </div>
      </div>

      {/* TASKS BY CATEGORY */}
      {CATEGORIES.map((cat) => (
        <div key={cat.id}>
          <h2 className="category-title">{cat.label}</h2>

          <div className="task-list">
            {tasks
              .filter((t) => t.category === cat.id)
              .map((task) => (
                <div
                  key={task.id}
                  className={`task-card ${task.done ? "done" : ""} ${
                    task.priority ? "priority" : ""
                  }`}
                >
                  <div onClick={() => toggleTask(task.id)}>
                    {task.editing ? (
                      <input
                        value={task.title}
                        onChange={(e) =>
                          updateTitle(task.id, e.target.value)
                        }
                        onBlur={() => toggleEdit(task.id)}
                        autoFocus
                      />
                    ) : (
                      <h3>{task.title}</h3>
                    )}
                    <p>{task.time}</p>
                  </div>

                  <div className="task-actions">
                    {task.priority && <FiStar className="star" />}
                    {task.done && (
                      <div className="mood-picker">
                        {MOODS.map((m) => (
                          <span
                            key={m}
                            onClick={() => setMood(task.id, m)}
                            className={task.mood === m ? "active" : ""}
                          >
                            {m}
                          </span>
                        ))}
                      </div>
                    )}
                    <button onClick={() => toggleEdit(task.id)}>
                      <FiEdit2 />
                    </button>
                    <button onClick={() => deleteTask(task.id)}>
                      <FiTrash2 />
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>
      ))}

      {/* ADD */}
      <button className="add-task-btn" onClick={() => setShowModal(true)}>
        <FiPlus /> Add Task
      </button>

      {/* MODAL */}
      {showModal && (
        <div className="modal-overlay">
          <div className="task-modal">
            <h2>Add New Task</h2>

            <input
              placeholder="Task name"
              value={newTask}
              onChange={(e) => setNewTask(e.target.value)}
            />

            <input
              type="time"
              value={newTime}
              onChange={(e) => setNewTime(e.target.value)}
            />

            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            >
              {CATEGORIES.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>

            <label className="priority-toggle">
              <input
                type="checkbox"
                checked={priority}
                onChange={() => setPriority(!priority)}
              />
              Priority task
            </label>

            <div className="modal-actions">
              <button onClick={() => setShowModal(false)}>Cancel</button>
              <button className="primary" onClick={addTask}>
                Add
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}