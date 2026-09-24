import React, { useCallback, useEffect, useState } from "react";
import {
  FiAlertTriangle,
  FiArrowDownRight,
  FiArrowRight,
  FiArrowUpRight,
  FiCheck,
  FiClock,
  FiCpu,
  FiHeart,
  FiInfo,
  FiMinus,
  FiRefreshCw,
} from "react-icons/fi";
import {
  LuActivity,
  LuBedDouble,
  LuBrainCircuit,
  LuFootprints,
  LuLightbulb,
  LuShieldCheck,
  LuSmile,
  LuSparkles,
  LuTarget,
  LuWind,
} from "react-icons/lu";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api";
import "./HealthTwin.css";

/* ------------------------------------------------------------------ constants */
const COMPONENT_META = {
  mood: { icon: <LuSmile />, color: "#f59e0b", module: "mood", hint: "Log your mood" },
  sleep: { icon: <LuBedDouble />, color: "#6f5bf6", module: "sleep", hint: "Log your sleep" },
  activity: { icon: <LuFootprints />, color: "#f97316", module: "fitness", hint: "Set up Physical Fitness" },
  mindfulness: { icon: <LuWind />, color: "#14b8a6", module: "meditation", hint: "Try a meditation" },
  consistency: { icon: <LuTarget />, color: "#3385fb", module: null, hint: "" },
};

const CATEGORY_META = {
  activity: { icon: <LuFootprints />, color: "#f97316" },
  sleep: { icon: <LuBedDouble />, color: "#6f5bf6" },
  mindfulness: { icon: <LuWind />, color: "#14b8a6" },
};

const KIND_ICON = {
  move: <LuFootprints />,
  mind: <LuBrainCircuit />,
  sleep: <LuBedDouble />,
  log: <LuActivity />,
};

const LANGUAGES = [
  { code: "en-US", label: "English" },
  { code: "hi-IN", label: "हिंदी" },
  { code: "mr-IN", label: "मराठी" },
];

const CONFIDENCE_TEXT = {
  strong: "Strong pattern",
  moderate: "Moderate pattern",
  emerging: "Emerging pattern",
};

const fmtDay = (iso) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/* ------------------------------------------------------------------ pieces */
export function ScoreRing({ score, color, size = 180, stroke = 14, label }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = score == null ? 0 : Math.max(0, Math.min(score, 100)) / 100;
  const gid = `twinRing${size}`;
  return (
    <svg width={size} height={size} className="twin-ring" role="img" aria-label={`Wellness score ${score ?? "unknown"}`}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#1d66f0" />
          <stop offset="55%" stopColor="#6f5bf6" />
          <stop offset="100%" stopColor="#22d3ee" />
        </linearGradient>
      </defs>
      <circle cx={size / 2} cy={size / 2} r={r} className="twin-ring-bg" strokeWidth={stroke} fill="none" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        stroke={score == null ? "var(--border-strong)" : `url(#${gid})`}
        strokeWidth={stroke}
        fill="none"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - pct)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className="twin-ring-fg"
      />
      <text x="50%" y={label ? "48%" : "54%"} textAnchor="middle" className="twin-ring-value" style={{ fontSize: size * 0.26 }}>
        {score ?? "–"}
      </text>
      {label && (
        <text x="50%" y="64%" textAnchor="middle" className="twin-ring-label" style={{ fill: color }}>
          {label}
        </text>
      )}
    </svg>
  );
}

function Delta({ value, suffix = "" }) {
  if (value == null || value === 0) {
    return (
      <span className="twin-delta flat">
        <FiMinus /> no change{suffix}
      </span>
    );
  }
  const up = value > 0;
  return (
    <span className={`twin-delta ${up ? "up" : "down"}`}>
      {up ? <FiArrowUpRight /> : <FiArrowDownRight />} {up ? "+" : ""}
      {value}
      {suffix}
    </span>
  );
}

/* ================================================================ component */
function HealthTwin({ userId, onNavigate }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [report, setReport] = useState(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [language, setLanguage] = useState("en-US");
  const [toast, setToast] = useState(null);

  const uid = encodeURIComponent(userId || "");

  const showToast = useCallback((message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  const load = useCallback(async () => {
    try {
      const [overview, latest] = await Promise.all([
        api.get(`/twin/overview/${uid}`),
        api.get(`/twin/report/${uid}`).catch(() => ({ report: null })),
      ]);
      setData(overview);
      if (latest?.report) setReport(latest.report);
      setError("");
    } catch (err) {
      setError(err?.message || "Could not load your Health Twin");
    } finally {
      setLoading(false);
    }
  }, [uid]);

  useEffect(() => {
    if (userId) load();
  }, [userId, load]);

  const toggleAction = async (action) => {
    // Optimistic: the tick should feel instant.
    setData((d) => ({
      ...d,
      plan: d.plan.map((a) => (a.id === action.id ? { ...a, done: !a.done } : a)),
    }));
    try {
      const res = await api.post(`/twin/actions/${encodeURIComponent(action.id)}/toggle`);
      if (res.done) showToast("Nice – one step done today");
    } catch (err) {
      setData((d) => ({
        ...d,
        plan: d.plan.map((a) => (a.id === action.id ? { ...a, done: action.done } : a)),
      }));
      showToast(err?.message || "Could not update", "error");
    }
  };

  const generateReport = async (refresh = false) => {
    setReportLoading(true);
    try {
      const res = await api.post("/twin/report", { language, refresh });
      setReport(res);
    } catch (err) {
      showToast(err?.message || "Could not create the report", "error");
    } finally {
      setReportLoading(false);
    }
  };

  const go = (module) => module && onNavigate && onNavigate(module);

  /* ------------------------------------------------------------- states */
  if (loading) {
    return (
      <div className="twin-container">
        <div className="twin-skeleton twin-skeleton-hero" />
        <div className="twin-grid twin-grid-2">
          <div className="twin-skeleton" />
          <div className="twin-skeleton" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="twin-container">
        <div className="twin-card twin-empty">
          <FiAlertTriangle size={36} />
          <h3>Your twin couldn't load</h3>
          <p>{error}</p>
          <button className="twin-btn twin-btn-primary" onClick={() => { setLoading(true); load(); }}>
            <FiRefreshCw /> Try again
          </button>
        </div>
      </div>
    );
  }

  const doneCount = data.plan.filter((a) => a.done).length;
  const trend = data.trend.map((t) => ({ ...t, label: fmtDay(t.date) }));
  const hasTrend = trend.filter((t) => t.score != null).length >= 2;
  const snap = data.snapshot;
  const progress = data.insight_progress;

  return (
    <div className="twin-container">
      {toast && (
        <div className={`twin-toast ${toast.type}`}>
          {toast.type === "error" ? <FiAlertTriangle /> : <FiCheck />}
          <span>{toast.message}</span>
        </div>
      )}

      {/* HERO */}
      <header className="twin-hero">
        <div className="twin-hero-text">
          <span className="twin-eyebrow">
            <LuBrainCircuit /> Personal Health Twin
          </span>
          <h1>Your health, understood.</h1>
          <p>
            Your twin learns from everything you log – mood, sleep, movement, meditation and journaling – to show
            what really affects you and what to do today.
          </p>
        </div>
        <div className="twin-hero-side">
          <span className="twin-hero-date">
            {data.weekday}, {fmtDay(data.date)}
          </span>
          <button className="twin-btn twin-btn-glass" onClick={() => { setLoading(true); load(); }}>
            <FiRefreshCw /> Refresh
          </button>
        </div>
      </header>

      {/* SUPPORT (from the safety layer) */}
      {data.support && (
        <div className="twin-support">
          <FiHeart />
          <div className="twin-markdown">
            <p>{data.support.message}</p>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.support.resources}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* SCORE + COMPONENTS */}
      <div className="twin-grid twin-grid-score">
        <section className="twin-card twin-score-card">
          <ScoreRing score={data.score} color={data.color} label={data.score != null ? data.label : null} />
          <div className="twin-score-text">
            <h2>Wellness Score</h2>
            {data.score != null && <Delta value={data.delta} suffix=" vs last week" />}
            <p className="twin-summary">{data.summary}</p>
            {snap.streak > 0 && (
              <span className="twin-chip">
                <LuSparkles /> {snap.streak}-day logging streak
              </span>
            )}
          </div>
        </section>

        <section className="twin-card">
          <div className="twin-card-head">
            <h2>What makes up your score</h2>
            <span className="twin-muted">Weighted by impact</span>
          </div>
          <ul className="twin-components">
            {data.components.map((c) => {
              const meta = COMPONENT_META[c.key];
              return (
                <li key={c.key} className="twin-component">
                  <span className="twin-component-icon" style={{ color: meta.color, background: `${meta.color}1f` }}>
                    {meta.icon}
                  </span>
                  <div className="twin-component-body">
                    <div className="twin-component-top">
                      <span>
                        {c.label} <small>{c.weight}%</small>
                      </span>
                      {c.tracked ? (
                        <strong>{Math.round(c.value)}</strong>
                      ) : (
                        <button className="twin-link" onClick={() => go(meta.module)}>
                          {meta.hint} <FiArrowRight />
                        </button>
                      )}
                    </div>
                    <div className="twin-bar">
                      <div
                        style={{
                          width: c.tracked ? `${Math.max(c.value, 2)}%` : "0%",
                          background: meta.color,
                        }}
                      />
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      </div>

      {/* EARLY WARNING */}
      {data.warning.level !== "clear" ? (
        <section className={`twin-warning ${data.warning.level}`}>
          <div className="twin-warning-icon">
            <FiAlertTriangle />
          </div>
          <div>
            <h3>{data.warning.level === "alert" ? "Early warning: things are sliding" : "Worth keeping an eye on"}</h3>
            <p>{data.warning.message}</p>
            <div className="twin-signals">
              {data.warning.signals.map((s) => (
                <span key={s.area} className="twin-signal">
                  {s.text}
                </span>
              ))}
            </div>
          </div>
        </section>
      ) : (
        data.score != null && (
          <section className="twin-warning clear">
            <div className="twin-warning-icon">
              <LuShieldCheck />
            </div>
            <div>
              <h3>No warning signs</h3>
              <p>{data.warning.message}</p>
            </div>
          </section>
        )
      )}

      {/* TODAY'S PLAN */}
      <section className="twin-card">
        <div className="twin-card-head">
          <h2>
            <LuTarget /> Today's plan
          </h2>
          <span className="twin-progress-pill">
            {doneCount}/{data.plan.length} done
          </span>
        </div>
        <div className="twin-plan">
          {data.plan.map((a) => (
            <article key={a.id} className={`twin-action ${a.done ? "done" : ""} kind-${a.kind}`}>
              <button
                className="twin-check"
                onClick={() => toggleAction(a)}
                aria-label={a.done ? "Mark as not done" : "Mark as done"}
              >
                {a.done ? <FiCheck /> : KIND_ICON[a.kind] || <LuActivity />}
              </button>
              <div className="twin-action-body">
                <h3>{a.title}</h3>
                <p>{a.detail}</p>
                <div className="twin-action-foot">
                  <span className="twin-muted">
                    <FiClock /> {a.minutes} min
                  </span>
                  {a.module && (
                    <button className="twin-link" onClick={() => go(a.module)}>
                      Open <FiArrowRight />
                    </button>
                  )}
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>

      {/* TREND + SNAPSHOT */}
      <div className="twin-grid twin-grid-trend">
        <section className="twin-card">
          <div className="twin-card-head">
            <h2>Score trend</h2>
            <span className="twin-muted">Last 30 days</span>
          </div>
          {hasTrend ? (
            <div className="twin-chart">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trend} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="twinArea" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6f5bf6" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#6f5bf6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} interval="preserveStartEnd" minTickGap={24} />
                  <YAxis domain={[0, 100]} tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} />
                  <Tooltip
                    contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderRadius: 12, color: "var(--text-primary)" }}
                    formatter={(v) => [v ?? "–", "Score"]}
                  />
                  <ReferenceLine y={65} stroke="#10b981" strokeDasharray="4 4" />
                  <Area type="monotone" dataKey="score" stroke="#6f5bf6" strokeWidth={3} fill="url(#twinArea)" connectNulls dot={false} activeDot={{ r: 5 }} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="twin-muted twin-center">Your trend appears after a couple of days of check-ins.</p>
          )}
        </section>

        <section className="twin-card">
          <div className="twin-card-head">
            <h2>This week</h2>
            <span className="twin-muted">Last 7 days</span>
          </div>
          <div className="twin-snapshot">
            <div>
              <span className="twin-snap-icon" style={{ color: "#f59e0b" }}><LuSmile /></span>
              <strong>{snap.avg_mood ?? "–"}</strong>
              <small>avg mood /100</small>
            </div>
            <div>
              <span className="twin-snap-icon" style={{ color: "#6f5bf6" }}><LuBedDouble /></span>
              <strong>{snap.avg_sleep_h ?? "–"}{snap.avg_sleep_h != null && <em>h</em>}</strong>
              <small>avg sleep</small>
            </div>
            <div>
              <span className="twin-snap-icon" style={{ color: "#f97316" }}><LuFootprints /></span>
              <strong>{snap.active_minutes}<em>min</em></strong>
              <small>active</small>
            </div>
            <div>
              <span className="twin-snap-icon" style={{ color: "#14b8a6" }}><LuWind /></span>
              <strong>{snap.mindful_days}<em>/7</em></strong>
              <small>mindful days</small>
            </div>
            <div>
              <span className="twin-snap-icon" style={{ color: "#3385fb" }}><LuActivity /></span>
              <strong>{snap.logged_days}<em>/7</em></strong>
              <small>days logged</small>
            </div>
            <div>
              <span className="twin-snap-icon" style={{ color: "#f43f5e" }}><LuSparkles /></span>
              <strong>{snap.workouts}</strong>
              <small>workouts</small>
            </div>
          </div>
        </section>
      </div>

      {/* INSIGHTS */}
      <section className="twin-card">
        <div className="twin-card-head">
          <h2>
            <LuLightbulb /> What affects you
          </h2>
          <span className="twin-muted">Learned from your own data</span>
        </div>
        {data.insights.length > 0 ? (
          <>
            <div className="twin-insights">
              {data.insights.map((i) => {
                const meta = CATEGORY_META[i.category] || CATEGORY_META.activity;
                return (
                  <article key={i.id} className={`twin-insight ${i.direction}`}>
                    <div className="twin-insight-head">
                      <span className="twin-insight-icon" style={{ color: meta.color, background: `${meta.color}1f` }}>
                        {meta.icon}
                      </span>
                      <span className={`twin-effect ${i.direction}`}>
                        {i.direction === "helps" ? <FiArrowUpRight /> : <FiArrowDownRight />}
                        {i.direction === "helps" ? "Helps you" : "Holds you back"}
                      </span>
                    </div>
                    <p>{i.statement}</p>
                    <div className="twin-insight-foot">
                      <span className={`twin-confidence ${i.confidence}`}>{CONFIDENCE_TEXT[i.confidence]}</span>
                      <span className="twin-muted">
                        {i.n_with} vs {i.n_without} days
                      </span>
                    </div>
                    {i.module && (
                      <button className="twin-link" onClick={() => go(i.module)}>
                        Act on this <FiArrowRight />
                      </button>
                    )}
                  </article>
                );
              })}
            </div>
            <p className="twin-disclaimer">
              <FiInfo /> These are patterns in your data, not proof of cause – but they're personal to you, which makes
              them worth testing.
            </p>
          </>
        ) : (
          <div className="twin-unlock">
            <LuLightbulb size={34} />
            <div>
              <h3>{progress.unlocked ? "No clear patterns yet" : "Insights unlock as you log"}</h3>
              <p>
                {progress.unlocked
                  ? "Your data doesn't show a strong pattern yet. Keep logging mood alongside sleep and workouts – differences show up within a couple of weeks."
                  : "Log your mood on a few more days (along with sleep or workouts) and your twin will start finding what lifts you and what drains you."}
              </p>
              <div className="twin-bar twin-bar-lg">
                <div style={{ width: `${Math.min((progress.mood_days / progress.needed) * 100, 100)}%` }} />
              </div>
              <small className="twin-muted">
                {progress.mood_days}/{progress.needed} days with a mood check-in
              </small>
            </div>
          </div>
        )}
      </section>

      {/* WEEKLY REPORT */}
      <section className="twin-card twin-report">
        <div className="twin-card-head">
          <h2>
            <FiCpu /> Weekly AI report
          </h2>
          <div className="twin-report-actions">
            <select value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Report language">
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
            <button className="twin-btn twin-btn-primary" onClick={() => generateReport(Boolean(report))} disabled={reportLoading}>
              {reportLoading ? (
                <>
                  <FiRefreshCw className="twin-spin" /> Writing…
                </>
              ) : report ? (
                <>
                  <FiRefreshCw /> Regenerate
                </>
              ) : (
                <>
                  <LuSparkles /> Generate report
                </>
              )}
            </button>
          </div>
        </div>

        {!report ? (
          <p className="twin-muted">
            Get a short, personal write-up of your week: what improved, what slipped, and one focus for next week.
            It's written from your numbers only – never from your journal or chat text.
          </p>
        ) : (
          <div className="twin-report-body">
            <div className="twin-report-text">
              <div className="twin-report-meta">
                <span className={`twin-badge ${report.source === "ai" ? "ai" : "template"}`}>
                  {report.source === "ai" ? <><FiCpu /> AI-written</> : <><FiCheck /> Summary</>}
                </span>
                <span className="twin-muted">Week of {fmtDay(report.week_start)}</span>
              </div>
              <p className="twin-narrative">{report.narrative}</p>
              <div className="twin-focus">
                <LuTarget />
                <div>
                  <small>Focus for next week</small>
                  <p>{report.focus}</p>
                </div>
              </div>
            </div>
            <table className="twin-compare">
              <thead>
                <tr>
                  <th />
                  <th>This week</th>
                  <th>Last week</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {report.compare.map((r) => (
                  <tr key={r.key}>
                    <td>{r.label}</td>
                    <td>
                      <strong>{r.this_week ?? "–"}</strong>
                      {r.this_week != null && <small> {r.unit}</small>}
                    </td>
                    <td className="twin-muted">{r.last_week ?? "–"}</td>
                    <td>
                      {r.trend === "up" && <span className="twin-trend up"><FiArrowUpRight /></span>}
                      {r.trend === "down" && <span className="twin-trend down"><FiArrowDownRight /></span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <p className="twin-disclaimer twin-center">
        Your Health Twin supports self-awareness. It isn't a medical assessment – if you're worried about your health,
        please talk to a doctor.
      </p>
    </div>
  );
}

export default HealthTwin;
