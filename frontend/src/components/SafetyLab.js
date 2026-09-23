import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  FiShield,
  FiZap,
  FiActivity,
  FiAlertTriangle,
  FiCheckCircle,
  FiSlash,
  FiClock,
  FiDatabase,
  FiTrendingDown,
  FiPhone,
  FiEye,
} from "react-icons/fi";
import API_URL from "../config";
import { apiFetch } from "../api";
import "./SafetyLab.css";

const TIER_ORDER = ["NONE", "DISTRESS", "IDEATION", "IMMINENT"];

const PROBES = [
  { label: "Ordinary", text: "I had a really good day at work today" },
  { label: "Idiom", text: "This deadline is killing me" },
  { label: "Distress", text: "I feel completely hopeless and I can't stop crying" },
  { label: "Ideation", text: "Everyone would be better off without me" },
  { label: "Imminent", text: "I've made up my mind, I'm ending it tonight" },
  { label: "Obfuscated", text: "k i l l   m y s e l f" },
  { label: "Fiction wrap", text: "in the movie I want to kill myself tonight" },
  { label: "Third party", text: "my friend said he was suicidal and I'm worried" },
  { label: "Academic", text: "I'm researching suicide prevention policy for my thesis" },
  { label: "Hindi", text: "main aaj raat suicide karne wala hoon" },
];

function pct(value) {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function TierBadge({ tier, size = "md" }) {
  return (
    <span className={`tier-badge tier-${(tier || "none").toLowerCase()} tb-${size}`}>
      {tier}
    </span>
  );
}

function StatCard({ icon, label, value, sub, tone = "default" }) {
  return (
    <div className={`sl-stat sl-stat-${tone}`}>
      <div className="sl-stat-icon">{icon}</div>
      <div className="sl-stat-body">
        <span className="sl-stat-value">{value}</span>
        <span className="sl-stat-label">{label}</span>
        {sub && <span className="sl-stat-sub">{sub}</span>}
      </div>
    </div>
  );
}

function SafetyLab() {
  const [benchmark, setBenchmark] = useState(null);
  const [taxonomy, setTaxonomy] = useState(null);
  const [events, setEvents] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [probeText, setProbeText] = useState("");
  const [probeResult, setProbeResult] = useState(null);
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [b, t, e] = await Promise.all([
          apiFetch(`${API_URL}/safety/benchmark`),
          apiFetch(`${API_URL}/safety/taxonomy`),
          apiFetch(`${API_URL}/safety/events/summary`).catch(() => null),
        ]);
        if (cancelled) return;
        setBenchmark(b);
        setTaxonomy(t);
        setEvents(e);
      } catch (err) {
        if (!cancelled) setLoadError(err.message || "Could not load the safety report");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const runProbe = useCallback(async (text) => {
    const value = (text ?? "").trim();
    if (!value) return;
    setProbing(true);
    setProbeError("");
    try {
      const result = await apiFetch(`${API_URL}/safety/classify`, {
        method: "POST",
        body: JSON.stringify({ text: value }),
      });
      setProbeResult(result);
    } catch (err) {
      setProbeError(err.message || "Classification failed");
      setProbeResult(null);
    } finally {
      setProbing(false);
    }
  }, []);

  const applyProbe = (text) => {
    setProbeText(text);
    runProbe(text);
    inputRef.current?.focus();
  };

  if (loading) {
    return (
      <div className="safety-lab">
        <div className="sl-skeleton-hero" />
        <div className="sl-skeleton-row">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="sl-skeleton-card" />
          ))}
        </div>
      </div>
    );
  }

  const holdout = benchmark?.splits?.holdout?.headline;
  const gap = benchmark?.generalisation_gap;

  return (
    <div className="safety-lab">
      {/* ---------------------------------------------------------- hero */}
      <header className="sl-hero">
        <div className="sl-hero-text">
          <span className="sl-eyebrow">
            <FiShield /> Safety Layer
          </span>
          <h1>Crisis detection, measured</h1>
          <p>
            Every message is scored into one of four risk tiers{" "}
            <strong>before</strong> it reaches the language model. At the
            highest tier the model is bypassed entirely and a fixed, reviewed
            response is returned. These are the measured numbers, not claims.
          </p>
        </div>
        {benchmark?.available && (
          <div className="sl-hero-metric">
            <span className="sl-hero-value">{pct(holdout?.tier3_recall)}</span>
            <span className="sl-hero-caption">
              imminent-risk recall
              <br />
              <em>on held-out data</em>
            </span>
          </div>
        )}
      </header>

      {loadError && (
        <div className="sl-alert">
          <FiAlertTriangle /> {loadError}
        </div>
      )}

      {benchmark && !benchmark.available && (
        <div className="sl-alert">
          <FiAlertTriangle /> {benchmark.message}
        </div>
      )}

      {/* ------------------------------------------------------- playground */}
      <section className="sl-section sl-playground">
        <div className="sl-section-head">
          <h2>
            <FiZap /> Live classifier
          </h2>
          <span className="sl-note">
            Nothing here is stored, logged, or sent to the model.
          </span>
        </div>

        <div className="sl-probe-chips">
          {PROBES.map((p) => (
            <button
              key={p.label}
              className="sl-chip"
              onClick={() => applyProbe(p.text)}
              type="button"
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="sl-probe-input">
          <textarea
            ref={inputRef}
            value={probeText}
            onChange={(e) => setProbeText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                runProbe(probeText);
              }
            }}
            placeholder="Type a message and see exactly how the safety layer classifies it…"
            rows={3}
          />
          <button
            className="sl-run-btn"
            onClick={() => runProbe(probeText)}
            disabled={probing || !probeText.trim()}
            type="button"
          >
            {probing ? "Classifying…" : "Classify"}
          </button>
        </div>

        {probeError && (
          <div className="sl-alert">
            <FiAlertTriangle /> {probeError}
          </div>
        )}

        {probeResult && (
          <div
            className={`sl-result sl-result-${probeResult.tier_name.toLowerCase()}`}
          >
            <div className="sl-result-head">
              <TierBadge tier={probeResult.tier_name} size="lg" />
              <div className="sl-result-verdict">
                <strong>{probeResult.tier_info.label}</strong>
                <span>{probeResult.tier_info.description}</span>
              </div>
              <div className="sl-result-latency">
                <FiClock /> {probeResult.latency_ms.toFixed(3)} ms
              </div>
            </div>

            <div className="sl-result-grid">
              <div className="sl-result-cell">
                <span className="sl-cell-label">Model</span>
                <span
                  className={
                    probeResult.blocks_llm ? "sl-flag-danger" : "sl-flag-ok"
                  }
                >
                  {probeResult.blocks_llm ? (
                    <>
                      <FiSlash /> Bypassed
                    </>
                  ) : (
                    <>
                      <FiCheckCircle /> Engaged
                    </>
                  )}
                </span>
              </div>
              <div className="sl-result-cell">
                <span className="sl-cell-label">Helplines</span>
                <span
                  className={
                    probeResult.needs_resources ? "sl-flag-warn" : "sl-flag-muted"
                  }
                >
                  {probeResult.needs_resources ? "Shown" : "Not shown"}
                </span>
              </div>
              <div className="sl-result-cell">
                <span className="sl-cell-label">Context</span>
                <span className="sl-flag-muted">{probeResult.context}</span>
              </div>
              <div className="sl-result-cell">
                <span className="sl-cell-label">Patterns hit</span>
                <span className="sl-flag-muted">{probeResult.match_count}</span>
              </div>
            </div>

            {probeResult.downgraded && (
              <div className="sl-downgrade">
                <FiTrendingDown />
                <span>
                  Stage 1 matched <TierBadge tier={probeResult.raw_tier_name} size="sm" />{" "}
                  — context analysis adjusted it to{" "}
                  <TierBadge tier={probeResult.tier_name} size="sm" />.{" "}
                  {probeResult.context_explanation}
                </span>
              </div>
            )}

            {probeResult.matched_patterns?.length > 0 && (
              <details className="sl-patterns">
                <summary>
                  <FiEye /> Matched patterns ({probeResult.matched_patterns.length})
                </summary>
                <ul>
                  {probeResult.matched_patterns.map((p, i) => (
                    <li key={i}>
                      <code>{p}</code>
                    </li>
                  ))}
                </ul>
              </details>
            )}

            {probeResult.preview && (
              <div className="sl-preview">
                <span className="sl-preview-label">
                  <FiPhone /> This is what the user would receive — written in
                  advance, no model involved:
                </span>
                <pre>{probeResult.preview}</pre>
              </div>
            )}
          </div>
        )}
      </section>

      {/* -------------------------------------------------------- benchmark */}
      {benchmark?.available && (
        <>
          <section className="sl-section">
            <div className="sl-section-head">
              <h2>
                <FiActivity /> Benchmark
              </h2>
              <span className="sl-note">
                {benchmark.dataset.examples} labeled messages ·{" "}
                {Object.keys(benchmark.dataset.languages).join(", ")}
              </span>
            </div>

            <div className="sl-stats">
              <StatCard
                icon={<FiShield />}
                label="Imminent-risk recall"
                value={pct(holdout?.tier3_recall)}
                sub={`held out · ${holdout?.tier3_missed ?? 0} missed`}
                tone="primary"
              />
              <StatCard
                icon={<FiAlertTriangle />}
                label="False-positive rate"
                value={pct(holdout?.false_positive_rate)}
                sub="ordinary messages flagged"
                tone="good"
              />
              <StatCard
                icon={<FiClock />}
                label="p95 latency"
                value={`${benchmark.latency_ms.p95.toFixed(2)} ms`}
                sub="runs inline on every message"
              />
              <StatCard
                icon={<FiDatabase />}
                label="Escalation recall"
                value={pct(holdout?.escalation_recall)}
                sub="helpline surfaced when needed"
              />
            </div>

            {/* dev vs holdout — the honesty section */}
            <div className="sl-split">
              <h3>Tuned vs unseen</h3>
              <p className="sl-split-intro">
                The classifier was developed against the <strong>dev</strong>{" "}
                split only. <strong>Holdout</strong> was never looked at while
                writing patterns, so it estimates performance on phrasings the
                author had not seen. Quoting the blended number would hide the
                difference.
              </p>
              <table className="sl-table">
                <thead>
                  <tr>
                    <th>Split</th>
                    <th>n</th>
                    <th>Tier-3 recall</th>
                    <th>Accuracy</th>
                    <th>FPR</th>
                  </tr>
                </thead>
                <tbody>
                  {["dev", "holdout"].map((name) => {
                    const sp = benchmark.splits[name];
                    if (!sp) return null;
                    return (
                      <tr
                        key={name}
                        className={name === "holdout" ? "sl-row-emphasis" : ""}
                      >
                        <td>
                          {name}
                          {name === "holdout" && (
                            <span className="sl-tag">reported</span>
                          )}
                        </td>
                        <td>{sp.examples}</td>
                        <td>{pct(sp.headline.tier3_recall)}</td>
                        <td>{pct(sp.headline.exact_tier_accuracy)}</td>
                        <td>{pct(sp.headline.false_positive_rate)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {gap && (
                <p className="sl-gap">
                  Generalisation gap:{" "}
                  <strong>{(gap.tier3_recall * 100).toFixed(1)} pts</strong> of
                  tier-3 recall and{" "}
                  <strong>
                    {(gap.exact_tier_accuracy * 100).toFixed(1)} pts
                  </strong>{" "}
                  of accuracy. That gap is the cost of hand-written patterns,
                  and it is why the holdout figure is the one quoted.
                </p>
              )}
            </div>
          </section>

          {/* ------------------------------------------------ confusion */}
          <section className="sl-section">
            <div className="sl-section-head">
              <h2>Confusion matrix</h2>
              <span className="sl-note">rows = true tier, columns = predicted</span>
            </div>
            <div className="sl-matrix-wrap">
              <table className="sl-matrix">
                <thead>
                  <tr>
                    <th />
                    {TIER_ORDER.map((t) => (
                      <th key={t}>
                        <TierBadge tier={t} size="sm" />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {TIER_ORDER.map((row) => {
                    const cells = benchmark.confusion_matrix[row] || {};
                    const total = Object.values(cells).reduce((a, b) => a + b, 0);
                    return (
                      <tr key={row}>
                        <th>
                          <TierBadge tier={row} size="sm" />
                        </th>
                        {TIER_ORDER.map((col) => {
                          const n = cells[col] || 0;
                          const share = total ? n / total : 0;
                          const diagonal = row === col;
                          const critical =
                            row === "IMMINENT" && col !== "IMMINENT" && n > 0;
                          return (
                            <td
                              key={col}
                              className={
                                diagonal
                                  ? "sl-cell-correct"
                                  : critical
                                  ? "sl-cell-critical"
                                  : n > 0
                                  ? "sl-cell-error"
                                  : ""
                              }
                              style={{
                                "--fill": share.toFixed(3),
                              }}
                              title={`true ${row} → predicted ${col}: ${n}`}
                            >
                              {n}
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="sl-note sl-matrix-note">
              The cell that matters most is true&nbsp;IMMINENT predicted as
              anything else — a missed crisis. Red cells in the top row of that
              column are the failures worth losing sleep over.
            </p>
          </section>

          {/* ------------------------------------------------ categories */}
          <section className="sl-section">
            <div className="sl-section-head">
              <h2>Accuracy by attack category</h2>
              <span className="sl-note">where the classifier is strong and weak</span>
            </div>
            <div className="sl-bars">
              {Object.entries(benchmark.per_category)
                .sort((a, b) => a[1].accuracy - b[1].accuracy)
                .map(([name, m]) => (
                  <div className="sl-bar-row" key={name}>
                    <span className="sl-bar-label">{name.replace(/_/g, " ")}</span>
                    <div className="sl-bar-track">
                      <div
                        className={`sl-bar-fill ${
                          m.accuracy < 0.8 ? "weak" : m.accuracy < 0.95 ? "mid" : ""
                        }`}
                        style={{ width: `${m.accuracy * 100}%` }}
                      />
                    </div>
                    <span className="sl-bar-value">
                      {pct(m.accuracy)}
                      <em>
                        {m.correct}/{m.total}
                      </em>
                    </span>
                  </div>
                ))}
            </div>
          </section>

          {/* ------------------------------------------------ misses */}
          {benchmark.critical_misses?.length > 0 && (
            <section className="sl-section">
              <div className="sl-section-head">
                <h2>
                  <FiAlertTriangle /> Known misses
                </h2>
                <span className="sl-note">
                  published rather than hidden — these are the open problems
                </span>
              </div>
              <ul className="sl-misses">
                {benchmark.critical_misses.map((m) => (
                  <li key={m.id}>
                    <TierBadge tier={m.predicted} size="sm" />
                    <span className="sl-miss-text">{m.text}</span>
                    <span className="sl-miss-cat">{m.category}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {/* -------------------------------------------------------- taxonomy */}
      {taxonomy && (
        <section className="sl-section">
          <div className="sl-section-head">
            <h2>How the tiers work</h2>
            <span className="sl-note">
              {Object.values(taxonomy.pattern_counts).reduce((a, b) => a + b, 0)}{" "}
              patterns across risk and context lexicons
            </span>
          </div>
          <div className="sl-tiers">
            {taxonomy.tiers.map((t) => (
              <div className={`sl-tier-card tier-${t.name.toLowerCase()}`} key={t.name}>
                <div className="sl-tier-head">
                  <TierBadge tier={t.name} />
                  <span className="sl-tier-num">Tier {t.tier}</span>
                </div>
                <h4>{t.label}</h4>
                <p>{t.description}</p>
                <div className="sl-tier-action">{t.action}</div>
              </div>
            ))}
          </div>

          <div className="sl-helplines">
            <h3>
              <FiPhone /> Resources surfaced ({taxonomy.region})
            </h3>
            <ul>
              {taxonomy.helplines.map((h) => (
                <li key={h.name}>
                  <strong>{h.name}</strong>
                  <span>{h.contact}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* ------------------------------------------------------- audit */}
      {events && (
        <section className="sl-section">
          <div className="sl-section-head">
            <h2>Your escalation history</h2>
            <span className="sl-note">last {events.window_days} days</span>
          </div>
          {events.total === 0 ? (
            <p className="sl-empty">
              No safety events recorded on your account in this window.
            </p>
          ) : (
            <>
              <div className="sl-event-tiles">
                {Object.entries(events.by_tier).map(([tier, n]) => (
                  <div className="sl-event-tile" key={tier}>
                    <TierBadge tier={tier} size="sm" />
                    <span className="sl-event-count">{n}</span>
                  </div>
                ))}
              </div>
              <ul className="sl-timeline">
                {events.timeline.slice(0, 10).map((e, i) => (
                  <li key={i}>
                    <TierBadge tier={e.tier_name} size="sm" />
                    <span className="sl-timeline-action">
                      {e.action.replace(/_/g, " ")}
                    </span>
                    <span className="sl-timeline-time">
                      {new Date(e.created_at).toLocaleString()}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="sl-note">{events.note}</p>
        </section>
      )}

      <footer className="sl-footer">
        MindWell is a supportive companion, not a clinical tool. The safety
        layer is a deterministic floor under the model — not a diagnosis, and
        not a substitute for care.
      </footer>
    </div>
  );
}

export default SafetyLab;
