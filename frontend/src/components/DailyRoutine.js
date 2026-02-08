"use client";

import { useState, useEffect } from "react";
import {
  FiArrowLeft,
  FiPlus,
  FiTrash2,
  FiCheckCircle,
  FiEdit2,
  FiStar,
} from "react-icons/fi";
import "./DailyRoutine.css";

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
  const [priority, setPriority] = useState(false);

  /* 🔥 Persist tasks */
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
        done: false,
        priority,
        editing: false,
      },
    ]);

    setNewTask("");
    setNewTime("");
    setPriority(false);
    setShowModal(false);
  };

  const toggleTask = (id) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id ? { ...t, done: !t.done } : t
      )
    );
  };

  const deleteTask = (id) => {
    setTasks((prev) => prev.filter((t) => t.id !== id));
  };

  const toggleEdit = (id) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id ? { ...t, editing: !t.editing } : t
      )
    );
  };

  const updateTitle = (id, value) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id ? { ...t, title: value } : t
      )
    );
  };

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

        <div>
          <strong>{completedCount}</strong> / {tasks.length} completed
        </div>
      </div>

      {/* EMPTY STATE */}
      {tasks.length === 0 && (
        <div className="empty-state">
          <h3>Plan your perfect day ✨</h3>
          <p>Add tasks like workouts, study, meditation, or self-care</p>
        </div>
      )}

      {/* TASK LIST */}
      <div className="task-list">
        {tasks.map((task) => (
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
              <input type="checkbox" checked={task.done} readOnly />
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

      {/* ADD BUTTON */}
      <button
        className="add-task-btn"
        onClick={() => setShowModal(true)}
      >
        <FiPlus /> Add Task
      </button>

      {/* MODAL */}
      {showModal && (
        <div className="modal-overlay">
          <div className="task-modal">
            <h2>Add New Task</h2>

            <input
              type="text"
              placeholder="Task name"
              value={newTask}
              onChange={(e) => setNewTask(e.target.value)}
            />

            <input
              type="time"
              value={newTime}
              onChange={(e) => setNewTime(e.target.value)}
            />

            <label className="priority-toggle">
              <input
                type="checkbox"
                checked={priority}
                onChange={() => setPriority(!priority)}
              />
              Mark as priority
            </label>

            <div className="modal-actions">
              <button onClick={() => setShowModal(false)}>
                Cancel
              </button>
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