import React, { useEffect, useState } from "react";
import { FiArrowRight, FiCheck } from "react-icons/fi";
import { LuBrainCircuit } from "react-icons/lu";
import { api } from "../api";
import { ScoreRing } from "./HealthTwin";
import "./HealthTwin.css";

/**
 * Compact Health Twin summary for the Dashboard. Renders nothing if the
 * twin can't load, so it can never break the dashboard.
 */
function HealthTwinCard({ userId, onNavigate }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    api
      .get(`/twin/overview/${encodeURIComponent(userId)}`)
      .then((res) => !cancelled && setData(res))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [userId]);

  if (!data) return null;
  const next = data.plan.find((a) => !a.done);

  return (
    <div className="twin-dash-card" onClick={() => onNavigate && onNavigate("twin")} role="button" tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onNavigate && onNavigate("twin")}>
      <ScoreRing score={data.score} color={data.color} size={96} stroke={9} />
      <div className="twin-dash-body">
        <span className="twin-eyebrow">
          <LuBrainCircuit /> Personal Health Twin
        </span>
        <h3>
          {data.score != null ? `${data.label} today` : "Meet your Health Twin"}
        </h3>
        <p>{data.summary}</p>
        {next ? (
          <span className="twin-dash-next">
            Next up: <strong>{next.title}</strong>
          </span>
        ) : (
          data.plan.length > 0 && (
            <span className="twin-dash-next">
              <FiCheck /> All of today's plan is done
            </span>
          )
        )}
      </div>
      <FiArrowRight className="twin-dash-arrow" />
    </div>
  );
}

export default HealthTwinCard;
