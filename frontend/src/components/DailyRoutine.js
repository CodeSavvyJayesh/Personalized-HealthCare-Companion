"use client";

import { useState } from "react";
import {
  FiArrowLeft,
  FiPlus,
  FiTrash2,
  FiCheckCircle,
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

  const completedCount = tasks.filter((t) => t.done).length;

  const addTask = () => {
    if (!newTask.trim()) return;

    setTasks((prev) => [
      ...prev,
      {
        id: Date.now(),
        title: newTask,
        time: newTime || "Anytime",
        done: false,
      },
    ]);

    setNewTask("");
    setNewTime("");
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
        <FiCheckCircle />
        <span>
          {completedCount} / {tasks.length} tasks completed
        </span>
      </div>

      {/* EMPTY STATE */}
      {tasks.length === 0 && (
        <div className="empty-state">
          <p>No tasks yet 🌱</p>
          <span>Click + to plan your day</span>
        </div>
      )}

      {/* TASK LIST */}
      <div className="task-list">
        {tasks.map((task) => (
          <div
            key={task.id}
            className={`task-card ${task.done ? "done" : ""}`}
          >
            <div onClick={() => toggleTask(task.id)}>
              <h3>{task.title}</h3>
              <p>{task.time}</p>
            </div>

            <div className="task-actions">
              <input
                type="checkbox"
                checked={task.done}
                readOnly
              />
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
