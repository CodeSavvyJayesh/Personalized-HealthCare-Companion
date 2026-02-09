import React, { useState, useEffect } from "react";
import "./Journaling.css";

function Journaling() {
  const [entry, setEntry] = useState("");
  const [entries, setEntries] = useState([]);
  const [editingId, setEditingId] = useState(null);

  useEffect(() => {
    const saved = localStorage.getItem("journalEntries");
    if (saved) {
      setEntries(JSON.parse(saved));
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("journalEntries", JSON.stringify(entries));
  }, [entries]);

  const handleSave = () => {
    if (!entry.trim()) return;

    if (editingId) {
      setEntries(
        entries.map((e) =>
          e.id === editingId ? { ...e, text: entry } : e
        )
      );
      setEditingId(null);
    } else {
      setEntries([
        {
          id: Date.now(),
          text: entry,
          date: new Date().toLocaleString(),
        },
        ...entries,
      ]);
    }
    setEntry("");
  };

  const handleEdit = (id) => {
    const item = entries.find((e) => e.id === id);
    setEntry(item.text);
    setEditingId(id);
  };

  const handleDelete = (id) => {
    setEntries(entries.filter((e) => e.id !== id));
  };

  return (
    <div className="journaling-container">
      <textarea
        value={entry}
        onChange={(e) => setEntry(e.target.value)}
        rows={6}
      />

      <button onClick={handleSave}>
        {editingId ? "Update" : "Save"}
      </button>

      <div className="journal-list">
        {entries.map((item) => (
          <div key={item.id} className="journal-item">
            <p>{item.text}</p>
            <small>{item.date}</small>

            <div className="actions">
              <button onClick={() => handleEdit(item.id)}>Edit</button>
              <button onClick={() => handleDelete(item.id)}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default Journaling;

