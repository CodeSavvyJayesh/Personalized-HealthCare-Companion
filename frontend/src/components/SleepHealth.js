import React, { useState, useEffect } from "react";
import {
  FiMoon,
  FiSun,
  FiActivity,
  FiClock,
  FiCheck,
} from "react-icons/fi";
import API_URL from "../config";
import { apiFetch } from "../api";
import "./SleepHealth.css";

function SleepHealth({ userId }) {
  const [sleepData, setSleepData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [bedTime, setBedTime] = useState("");
  const [wakeTime, setWakeTime] = useState("");
  const [quality, setQuality] = useState("Good");
  const [toast, setToast] = useState(null);

  useEffect(() => {
    const fetchSleepData = async () => {
      if (!userId) return;

      try {
        const res = await apiFetch(
          `${API_URL}/sleep/${userId}`
        );

        const data = res;

        if (data.success) {
          setSleepData(data.sleep_records);
        }
      } catch (err) {
        console.error(
          "Failed to fetch sleep data",
          err
        );
      } finally {
        setLoading(false);
      }
    };

    fetchSleepData();
  }, [userId]);

  const showToast = (
    message,
    type = "success"
  ) => {
    setToast({ message, type });

    setTimeout(
      () => setToast(null),
      3000
    );
  };

  const handleSaveSleep = async () => {
    if (!bedTime || !wakeTime) {
      showToast(
        "Please enter both bed time and wake time",
        "error"
      );
      return;
    }

    try {
      const res = await apiFetch(
        `${API_URL}/sleep`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            bed_time: bedTime,
            wake_time: wakeTime,
            quality: quality,
          }),
        }
      );

      const data = res;

      if (data.success) {
        showToast(
          "Sleep record saved!"
        );

        setBedTime("");
        setWakeTime("");
        setQuality("Good");

        // Refetch to update list
        const updatedRes = await apiFetch(
          `${API_URL}/sleep/${userId}`
        );

        const updatedData =
          updatedRes;

        if (updatedData.success) {
          setSleepData(
            updatedData.sleep_records
          );
        }
      } else {
        showToast(
          "Failed to save sleep record",
          "error"
        );
      }
    } catch (err) {
      console.error(
        "Error saving sleep record",
        err
      );

      showToast(
        "An error occurred",
        "error"
      );
    }
  };

  const calculateDuration = (
    bed,
    wake
  ) => {
    const bedDate = new Date(
      `2000-01-01T${bed}`
    );

    let wakeDate = new Date(
      `2000-01-01T${wake}`
    );

    if (wakeDate < bedDate) {
      wakeDate = new Date(
        `2000-01-02T${wake}`
      );
    }

    const diffMs =
      wakeDate - bedDate;

    const diffHrs =
      diffMs /
      (1000 * 60 * 60);

    return diffHrs.toFixed(1);
  };

  return (
    <div className="sleep-container">
      {/* TOAST */}
      {toast && (
        <div
          className={`toast-notification ${toast.type}`}
        >
          {toast.type === "success" ? (
            <FiCheck />
          ) : (
            <FiActivity />
          )}

          <span>{toast.message}</span>
        </div>
      )}

      {/* HEADER */}
      <div className="sleep-header">
        <h1>
          <FiMoon /> Sleep Health
        </h1>

        <p>
          Track your sleep patterns to
          improve your rest and recovery.
        </p>
      </div>

      <div className="sleep-content">
        {/* INPUT CARD */}
        <div className="sleep-input-card">
          <h2>
            Log Last Night's Sleep
          </h2>

          {/* BED TIME */}
          <div className="input-group">
            <label>
              <FiMoon /> Bed Time
            </label>

            <input
              type="time"
              value={bedTime}
              onChange={(e) =>
                setBedTime(
                  e.target.value
                )
              }
            />
          </div>

          {/* WAKE TIME */}
          <div className="input-group">
            <label>
              <FiSun /> Wake Time
            </label>

            <input
              type="time"
              value={wakeTime}
              onChange={(e) =>
                setWakeTime(
                  e.target.value
                )
              }
            />
          </div>

          {/* SLEEP QUALITY */}
          <div className="input-group">
            <label>
              <FiActivity /> Sleep Quality
            </label>

            <select
              value={quality}
              onChange={(e) =>
                setQuality(
                  e.target.value
                )
              }
            >
              <option value="Excellent">
                Excellent
              </option>

              <option value="Good">
                Good
              </option>

              <option value="Fair">
                Fair
              </option>

              <option value="Poor">
                Poor
              </option>
            </select>
          </div>

          <button
            className="save-btn"
            onClick={handleSaveSleep}
          >
            Save Sleep Record
          </button>
        </div>

        {/* HISTORY CARD */}
        <div className="sleep-history-card">
          <h2>
            Recent Sleep Records
          </h2>

          {loading ? (
            <div className="loading-state">
              Loading sleep data...
            </div>
          ) : sleepData.length > 0 ? (
            <div className="sleep-list">
              {sleepData.map(
                (record, index) => (
                  <div
                    key={index}
                    className="sleep-item"
                  >
                    <div className="sleep-date">
                      {new Date(
                        record.created_at
                      ).toLocaleDateString(
                        undefined,
                        {
                          weekday: "short",
                          month: "short",
                          day: "numeric",
                        }
                      )}
                    </div>

                    <div className="sleep-details">
                      <div className="sleep-times">
                        <span>
                          <FiMoon />{" "}
                          {record.bed_time}
                        </span>

                        <span> - </span>

                        <span>
                          <FiSun />{" "}
                          {record.wake_time}
                        </span>
                      </div>

                      <div className="sleep-duration">
                        <FiClock />{" "}
                        {calculateDuration(
                          record.bed_time,
                          record.wake_time
                        )}{" "}
                        hrs
                      </div>

                      <div
                        className={`sleep-quality badge-${record.quality.toLowerCase()}`}
                      >
                        {record.quality}
                      </div>
                    </div>
                  </div>
                )
              )}
            </div>
          ) : (
            <div className="empty-state">
              <p>
                No sleep records found.
                Start tracking your sleep
                tonight!
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default SleepHealth;