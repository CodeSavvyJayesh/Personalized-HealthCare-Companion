import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  FiActivity,
  FiAlertCircle,
  FiCheck,
  FiCheckCircle,
  FiClock,
  FiCpu,
  FiDroplet,
  FiHeart,
  FiInfo,
  FiMoon,
  FiRefreshCw,
  FiSend,
  FiTrash2,
  FiTrendingUp,
  FiZap,
} from "react-icons/fi";
import { LuDumbbell, LuFlame, LuSalad, LuScale, LuSparkles } from "react-icons/lu";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api";
import "./Fitness.css";

/* ------------------------------------------------------------------ constants */
const TABS = [
  { id: "overview", label: "Body Metrics", icon: <LuScale /> },
  { id: "plan", label: "My AI Plan", icon: <LuSparkles /> },
  { id: "activity", label: "Activity Log", icon: <FiActivity /> },
  { id: "coach", label: "AI Coach", icon: <FiCpu /> },
];

const ACTIVITY_OPTIONS = [
  { value: "sedentary", label: "Sedentary", hint: "Desk job, little exercise" },
  { value: "light", label: "Lightly active", hint: "Exercise 1–3 days/week" },
  { value: "moderate", label: "Moderately active", hint: "Exercise 3–5 days/week" },
  { value: "active", label: "Very active", hint: "Hard exercise 6–7 days/week" },
  { value: "very_active", label: "Extremely active", hint: "Physical job or 2x/day" },
];

const GOALS = [
  { value: "lose", label: "Lose fat", icon: <LuFlame /> },
  { value: "maintain", label: "Maintain", icon: <FiHeart /> },
  { value: "gain", label: "Build muscle", icon: <LuDumbbell /> },
  { value: "fitness", label: "Get fitter", icon: <FiZap /> },
];

const DIETS = [
  { value: "veg", label: "Vegetarian" },
  { value: "eggetarian", label: "Eggetarian" },
  { value: "non_veg", label: "Non-veg" },
  { value: "vegan", label: "Vegan" },
  { value: "jain", label: "Jain" },
];

const EQUIPMENT = [
  { value: "none", label: "No equipment" },
  { value: "home", label: "Dumbbells / bands" },
  { value: "gym", label: "Full gym" },
];

const LANGUAGES = [
  { code: "en-US", label: "English" },
  { code: "hi-IN", label: "हिंदी" },
  { code: "mr-IN", label: "मराठी" },
];

const CATEGORIES = [
  { value: "strength", label: "Strength" },
  { value: "cardio", label: "Cardio" },
  { value: "hiit", label: "HIIT" },
  { value: "yoga", label: "Yoga / Mobility" },
  { value: "walk", label: "Walk" },
  { value: "sports", label: "Sports" },
  { value: "other", label: "Other" },
];

const COACH_PROMPTS = [
  "What should I eat before and after a workout?",
  "How do I stay consistent when my motivation is low?",
  "Can you suggest a 15-minute workout for a busy day?",
  "How much protein do I need and where can I get it?",
  "How does exercise help with stress and anxiety?",
];

const BMI_SCALE = {
  asian: [
    { from: 15, to: 18.5, label: "Under", color: "#38bdf8" },
    { from: 18.5, to: 23, label: "Healthy", color: "#10b981" },
    { from: 23, to: 25, label: "Over", color: "#f59e0b" },
    { from: 25, to: 40, label: "Obese", color: "#ef4444" },
  ],
  who: [
    { from: 15, to: 18.5, label: "Under", color: "#38bdf8" },
    { from: 18.5, to: 25, label: "Healthy", color: "#10b981" },
    { from: 25, to: 30, label: "Over", color: "#f59e0b" },
    { from: 30, to: 40, label: "Obese", color: "#ef4444" },
  ],
};

const MACRO_COLORS = { protein: "#f43f5e", carbs: "#f59e0b", fat: "#3385fb" };

const EMPTY_PROFILE = {
  age: "",
  sex: "male",
  height_cm: "",
  weight_kg: "",
  activity_level: "light",
  goal: "maintain",
  experience: "beginner",
  equipment: "none",
  days_per_week: 3,
  session_minutes: 40,
  diet_preference: "veg",
  cuisine: "Indian",
  injuries: "",
  bmi_standard: "asian",
};

const KG_PER_LB = 0.45359237;
const CM_PER_IN = 2.54;

const todayName = () =>
  ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][
    new Date().getDay()
  ];

const fmtDate = (iso, opts = { day: "numeric", month: "short" }) =>
  iso ? new Date(iso).toLocaleDateString(undefined, opts) : "";

/* ------------------------------------------------------------------ helpers */
function BmiGauge({ bmi, standard, category, color }) {
  const scale = BMI_SCALE[standard] || BMI_SCALE.asian;
  const min = 15;
  const max = 40;
  const pos = Math.min(Math.max(((bmi - min) / (max - min)) * 100, 1), 99);
  return (
    <div className="fit-gauge">
      <div className="fit-gauge-value">
        <span className="fit-gauge-number" style={{ color }}>
          {bmi.toFixed(1)}
        </span>
        <span className="fit-gauge-category" style={{ background: `${color}22`, color }}>
          {category}
        </span>
      </div>
      <div className="fit-gauge-track">
        {scale.map((band) => (
          <div
            key={band.label}
            className="fit-gauge-band"
            style={{
              width: `${((band.to - band.from) / (max - min)) * 100}%`,
              background: band.color,
            }}
          />
        ))}
        <div className="fit-gauge-marker" style={{ left: `${pos}%` }}>
          <span />
        </div>
      </div>
      <div className="fit-gauge-labels">
        {scale.map((band) => (
          <span
            key={band.label}
            style={{ width: `${((band.to - band.from) / (max - min)) * 100}%` }}
          >
            {band.label}
            <small>{band.from}</small>
          </span>
        ))}
      </div>
    </div>
  );
}

function StatTile({ icon, label, value, unit, sub, accent }) {
  return (
    <div className="fit-stat" style={accent ? { "--tile-accent": accent } : undefined}>
      <div className="fit-stat-icon">{icon}</div>
      <div className="fit-stat-body">
        <span className="fit-stat-label">{label}</span>
        <span className="fit-stat-value">
          {value}
          {unit && <small> {unit}</small>}
        </span>
        {sub && <span className="fit-stat-sub">{sub}</span>}
      </div>
    </div>
  );
}

function ProgressRing({ value, target, size = 128 }) {
  const stroke = 12;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.min(value / target, 1);
  return (
    <svg width={size} height={size} className="fit-ring" role="img" aria-label={`${value} of ${target} minutes`}>
      <defs>
        <linearGradient id="fitRingGrad" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#f97316" />
          <stop offset="100%" stopColor="#f43f5e" />
        </linearGradient>
      </defs>
      <circle cx={size / 2} cy={size / 2} r={r} className="fit-ring-bg" strokeWidth={stroke} fill="none" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        stroke="url(#fitRingGrad)"
        strokeWidth={stroke}
        fill="none"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - pct)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        className="fit-ring-fg"
      />
      <text x="50%" y="46%" textAnchor="middle" className="fit-ring-value">
        {value}
      </text>
      <text x="50%" y="62%" textAnchor="middle" className="fit-ring-label">
        of {target} min
      </text>
    </svg>
  );
}

/* ------------------------------------------------------------------ component */
function Fitness({ userId }) {
  const [tab, setTab] = useState("overview");
  const [toast, setToast] = useState(null);
  const [alert, setAlert] = useState(null);

  const [profile, setProfile] = useState(null);
  const [form, setForm] = useState(EMPTY_PROFILE);
  const [units, setUnits] = useState("metric");
  const [metrics, setMetrics] = useState(null);
  const [history, setHistory] = useState([]);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [saving, setSaving] = useState(false);
  const [weighIn, setWeighIn] = useState("");

  const [planDoc, setPlanDoc] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [planView, setPlanView] = useState("workout");
  const [selectedDay, setSelectedDay] = useState(todayName());
  const [planLanguage, setPlanLanguage] = useState("en-US");

  const [workouts, setWorkouts] = useState([]);
  const [stats, setStats] = useState(null);
  const [logForm, setLogForm] = useState({
    activity: "",
    category: "strength",
    duration_min: 30,
    intensity: "moderate",
    notes: "",
  });
  const [logging, setLogging] = useState(false);

  const [coachMessages, setCoachMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const coachEndRef = useRef(null);

  const uid = encodeURIComponent(userId || "");

  const showToast = useCallback((message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3200);
  }, []);

  const handleError = useCallback(
    (err, fallback) => {
      // 451 = the safety layer intercepted free text. Show the full,
      // reviewed response rather than a one-line toast.
      if (err?.status === 451) {
        setAlert(err.message);
        return;
      }
      showToast(err?.message || fallback, "error");
    },
    [showToast],
  );

  /* ------------------------------------------------------------- loading */
  const loadWorkouts = useCallback(async () => {
    try {
      const data = await api.get(`/fitness/workouts/${uid}`);
      setWorkouts(data.workouts || []);
      setStats(data.stats || null);
    } catch (err) {
      console.error("Failed to load workouts", err);
    }
  }, [uid]);

  useEffect(() => {
    if (!userId) return;
    let cancelled = false;
    (async () => {
      try {
        const [p, plan] = await Promise.all([
          api.get(`/fitness/profile/${uid}`),
          api.get(`/fitness/plan/${uid}`),
        ]);
        if (cancelled) return;
        if (p.profile) {
          setProfile(p.profile);
          setForm({ ...EMPTY_PROFILE, ...p.profile });
          setMetrics(p.metrics);
          setHistory(p.history || []);
        }
        if (plan.plan) setPlanDoc(plan);
      } catch (err) {
        console.error("Failed to load fitness data", err);
      } finally {
        if (!cancelled) setLoadingProfile(false);
      }
    })();
    loadWorkouts();
    return () => {
      cancelled = true;
    };
  }, [userId, uid, loadWorkouts]);

  useEffect(() => {
    coachEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [coachMessages, asking]);

  /* ------------------------------------------------------------- form */
  const setField = (field, value) => setForm((f) => ({ ...f, [field]: value }));

  const heightFtIn = useMemo(() => {
    const cm = parseFloat(form.height_cm);
    if (!cm) return { ft: "", inch: "" };
    const totalIn = cm / CM_PER_IN;
    let ft = Math.floor(totalIn / 12);
    let inch = Math.round(totalIn - ft * 12);
    if (inch === 12) {
      ft += 1;
      inch = 0;
    }
    return { ft, inch };
  }, [form.height_cm]);

  const setImperialHeight = (ft, inch) => {
    const f = parseFloat(ft) || 0;
    const i = parseFloat(inch) || 0;
    const cm = (f * 12 + i) * CM_PER_IN;
    setField("height_cm", cm ? cm.toFixed(1) : "");
  };

  const weightLb = form.weight_kg
    ? Math.round((parseFloat(form.weight_kg) / KG_PER_LB) * 10) / 10
    : "";

  const liveBmi = useMemo(() => {
    const h = parseFloat(form.height_cm) / 100;
    const w = parseFloat(form.weight_kg);
    if (!h || !w || h < 1 || w < 25) return null;
    return w / (h * h);
  }, [form.height_cm, form.weight_kg]);

  const validate = () => {
    const age = parseInt(form.age, 10);
    const h = parseFloat(form.height_cm);
    const w = parseFloat(form.weight_kg);
    if (!age || age < 13 || age > 100) return "Please enter an age between 13 and 100.";
    if (!h || h < 100 || h > 250) return "Please enter a height between 100 and 250 cm (3′3″–8′2″).";
    if (!w || w < 25 || w > 350) return "Please enter a weight between 25 and 350 kg.";
    return null;
  };

  const saveProfile = async (e) => {
    e?.preventDefault();
    const problem = validate();
    if (problem) {
      showToast(problem, "error");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        ...form,
        age: parseInt(form.age, 10),
        height_cm: parseFloat(form.height_cm),
        weight_kg: parseFloat(form.weight_kg),
        days_per_week: parseInt(form.days_per_week, 10),
        session_minutes: parseInt(form.session_minutes, 10),
      };
      delete payload.user_id;
      delete payload.updated_at;
      delete payload.created_at;
      const data = await api.put("/fitness/profile", payload);
      setProfile(data.profile);
      setMetrics(data.metrics);
      setHistory(data.history || []);
      showToast(profile ? "Profile updated" : "Profile saved – your metrics are ready");
    } catch (err) {
      handleError(err, "Could not save your profile");
    } finally {
      setSaving(false);
    }
  };

  const submitWeighIn = async (e) => {
    e.preventDefault();
    let kg = parseFloat(weighIn);
    if (!kg) return;
    if (units === "imperial") kg = kg * KG_PER_LB;
    if (kg < 25 || kg > 350) {
      showToast("That weight looks out of range", "error");
      return;
    }
    try {
      const data = await api.post("/fitness/weight", { weight_kg: Math.round(kg * 10) / 10 });
      setMetrics(data.metrics);
      setHistory(data.history || []);
      setForm((f) => ({ ...f, weight_kg: String(Math.round(kg * 10) / 10) }));
      setProfile((p) => (p ? { ...p, weight_kg: Math.round(kg * 10) / 10 } : p));
      setWeighIn("");
      showToast("Weigh-in logged");
    } catch (err) {
      handleError(err, "Could not log weight");
    }
  };

  /* ------------------------------------------------------------- plan */
  const generatePlan = async () => {
    if (!profile) {
      setTab("overview");
      showToast("Save your body metrics first", "error");
      return;
    }
    setGenerating(true);
    try {
      const data = await api.post("/fitness/plan", { language: planLanguage });
      setPlanDoc(data);
      setSelectedDay(todayName());
      setPlanView("workout");
      showToast(
        data.source === "ai"
          ? "Your AI plan is ready"
          : "AI is offline – here's your smart template plan",
        data.source === "ai" ? "success" : "info",
      );
    } catch (err) {
      handleError(err, "Could not generate a plan");
    } finally {
      setGenerating(false);
    }
  };

  const plan = planDoc?.plan;
  const schedule = plan?.workout?.schedule || [];
  const activeDay = schedule.find((d) => d.day === selectedDay) || schedule[0];

  const markDayDone = async (day) => {
    const category = day.type === "rest" ? "walk" : day.type === "cardio" ? "cardio" : "strength";
    try {
      const data = await api.post("/fitness/workouts", {
        activity: day.focus.slice(0, 80),
        category,
        duration_min: day.duration_min || 30,
        intensity: day.type === "rest" ? "low" : "moderate",
        notes: "",
        plan_day: day.day,
      });
      showToast(`Nice work! ~${data.calories} kcal logged`);
      loadWorkouts();
    } catch (err) {
      handleError(err, "Could not log workout");
    }
  };

  const doneToday = useMemo(() => {
    const today = new Date().toDateString();
    return new Set(
      workouts
        .filter((w) => w.plan_day && new Date(w.created_at).toDateString() === today)
        .map((w) => w.plan_day),
    );
  }, [workouts]);

  /* ------------------------------------------------------------- activity */
  const submitLog = async (e) => {
    e.preventDefault();
    if (!logForm.activity.trim()) {
      showToast("What did you do? Add an activity name", "error");
      return;
    }
    setLogging(true);
    try {
      const data = await api.post("/fitness/workouts", {
        ...logForm,
        activity: logForm.activity.trim(),
        duration_min: parseInt(logForm.duration_min, 10) || 1,
      });
      showToast(`Logged – about ${data.calories} kcal burned`);
      setLogForm((f) => ({ ...f, activity: "", notes: "" }));
      loadWorkouts();
    } catch (err) {
      handleError(err, "Could not log workout");
    } finally {
      setLogging(false);
    }
  };

  const deleteLog = async (id) => {
    try {
      await api.del(`/fitness/workouts/${id}`);
      setWorkouts((list) => list.filter((w) => w._id !== id));
      loadWorkouts();
    } catch (err) {
      handleError(err, "Could not delete entry");
    }
  };

  /* ------------------------------------------------------------- coach */
  const askCoach = async (text) => {
    const q = (text ?? question).trim();
    if (!q || asking) return;
    setCoachMessages((m) => [...m, { role: "user", text: q }]);
    setQuestion("");
    setAsking(true);
    try {
      const data = await api.post("/fitness/coach", { question: q, language: planLanguage });
      setCoachMessages((m) => [
        ...m,
        { role: "coach", text: data.answer, source: data.source },
      ]);
    } catch (err) {
      setCoachMessages((m) => [
        ...m,
        { role: "coach", text: err?.message || "Sorry, I couldn't answer that right now.", source: "error" },
      ]);
    } finally {
      setAsking(false);
    }
  };

  /* ------------------------------------------------------------- derived */
  const displayWeight = (kg) =>
    units === "imperial" ? `${Math.round((kg / KG_PER_LB) * 10) / 10}` : `${kg}`;
  const weightUnit = units === "imperial" ? "lb" : "kg";

  const historyChart = history.map((h) => ({
    date: fmtDate(h.date),
    weight: units === "imperial" ? Math.round((h.weight_kg / KG_PER_LB) * 10) / 10 : h.weight_kg,
    bmi: h.bmi,
  }));

  const macroData = metrics
    ? [
        { name: "Protein", key: "protein", grams: metrics.macros.protein_g, kcal: metrics.macros.protein_g * 4 },
        { name: "Carbs", key: "carbs", grams: metrics.macros.carbs_g, kcal: metrics.macros.carbs_g * 4 },
        { name: "Fat", key: "fat", grams: metrics.macros.fat_g, kcal: metrics.macros.fat_g * 9 },
      ]
    : [];
  const macroTotal = macroData.reduce((s, m) => s + m.kcal, 0) || 1;

  /* ================================================================ render */
  return (
    <div className="fit-container">
      {toast && (
        <div className={`fit-toast ${toast.type}`}>
          {toast.type === "error" ? <FiAlertCircle /> : toast.type === "info" ? <FiInfo /> : <FiCheck />}
          <span>{toast.message}</span>
        </div>
      )}

      {alert && (
        <div className="fit-modal-backdrop" onClick={() => setAlert(null)}>
          <div className="fit-modal" onClick={(e) => e.stopPropagation()}>
            <div className="fit-modal-icon">
              <FiHeart />
            </div>
            <div className="fit-markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{alert}</ReactMarkdown>
            </div>
            <button className="fit-btn fit-btn-primary" onClick={() => setAlert(null)}>
              Close
            </button>
          </div>
        </div>
      )}

      {/* HEADER */}
      <header className="fit-hero">
        <div className="fit-hero-text">
          <h1>
            <LuDumbbell /> Physical Fitness
          </h1>
          <p>
            Know your numbers, get an AI-built workout and meal plan, and see how moving your body
            lifts your mind.
          </p>
        </div>
        {metrics && (
          <div className="fit-hero-chips">
            <span className="fit-chip">
              BMI <strong>{metrics.bmi}</strong>
            </span>
            <span className="fit-chip">
              <LuFlame /> <strong>{metrics.target_calories}</strong> kcal/day
            </span>
            {stats && (
              <span className="fit-chip">
                <FiZap /> <strong>{stats.streak_days}</strong>-day streak
              </span>
            )}
          </div>
        )}
      </header>

      {/* TABS */}
      <nav className="fit-tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={`fit-tab ${tab === t.id ? "active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.icon}
            <span>{t.label}</span>
          </button>
        ))}
      </nav>

      {/* ============================================================ OVERVIEW */}
      {tab === "overview" && (
        <div className="fit-grid fit-grid-overview">
          <form className="fit-card fit-form" onSubmit={saveProfile}>
            <div className="fit-card-head">
              <h2>Your Body Profile</h2>
              <div className="fit-segment" role="group" aria-label="Units">
                {["metric", "imperial"].map((u) => (
                  <button
                    type="button"
                    key={u}
                    className={units === u ? "active" : ""}
                    onClick={() => setUnits(u)}
                  >
                    {u === "metric" ? "cm · kg" : "ft · lb"}
                  </button>
                ))}
              </div>
            </div>

            <div className="fit-row">
              <label className="fit-field">
                <span>Age</span>
                <input
                  type="number"
                  min="13"
                  max="100"
                  value={form.age}
                  onChange={(e) => setField("age", e.target.value)}
                  placeholder="e.g. 21"
                />
              </label>
              <div className="fit-field">
                <span>Sex</span>
                <div className="fit-segment fit-segment-full">
                  {[
                    ["male", "Male"],
                    ["female", "Female"],
                    ["other", "Other"],
                  ].map(([v, l]) => (
                    <button
                      type="button"
                      key={v}
                      className={form.sex === v ? "active" : ""}
                      onClick={() => setField("sex", v)}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="fit-row">
              {units === "metric" ? (
                <>
                  <label className="fit-field">
                    <span>Height (cm)</span>
                    <input
                      type="number"
                      step="0.1"
                      value={form.height_cm}
                      onChange={(e) => setField("height_cm", e.target.value)}
                      placeholder="e.g. 170"
                    />
                  </label>
                  <label className="fit-field">
                    <span>Weight (kg)</span>
                    <input
                      type="number"
                      step="0.1"
                      value={form.weight_kg}
                      onChange={(e) => setField("weight_kg", e.target.value)}
                      placeholder="e.g. 65"
                    />
                  </label>
                </>
              ) : (
                <>
                  <div className="fit-field">
                    <span>Height (ft / in)</span>
                    <div className="fit-inline">
                      <input
                        type="number"
                        value={heightFtIn.ft}
                        onChange={(e) => setImperialHeight(e.target.value, heightFtIn.inch)}
                        placeholder="ft"
                      />
                      <input
                        type="number"
                        value={heightFtIn.inch}
                        onChange={(e) => setImperialHeight(heightFtIn.ft, e.target.value)}
                        placeholder="in"
                      />
                    </div>
                  </div>
                  <label className="fit-field">
                    <span>Weight (lb)</span>
                    <input
                      type="number"
                      step="0.1"
                      value={weightLb}
                      onChange={(e) =>
                        setField(
                          "weight_kg",
                          e.target.value ? String(parseFloat(e.target.value) * KG_PER_LB) : "",
                        )
                      }
                      placeholder="e.g. 145"
                    />
                  </label>
                </>
              )}
            </div>

            {liveBmi && (
              <div className="fit-live-bmi">
                <FiActivity /> Live BMI: <strong>{liveBmi.toFixed(1)}</strong>
                <span>– save to see your full breakdown</span>
              </div>
            )}

            <div className="fit-field">
              <span>Goal</span>
              <div className="fit-goal-grid">
                {GOALS.map((g) => (
                  <button
                    type="button"
                    key={g.value}
                    className={`fit-goal ${form.goal === g.value ? "active" : ""}`}
                    onClick={() => setField("goal", g.value)}
                  >
                    {g.icon}
                    <span>{g.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <label className="fit-field">
              <span>Activity level</span>
              <select
                value={form.activity_level}
                onChange={(e) => setField("activity_level", e.target.value)}
              >
                {ACTIVITY_OPTIONS.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label} – {a.hint}
                  </option>
                ))}
              </select>
            </label>

            <div className="fit-row">
              <label className="fit-field">
                <span>Experience</span>
                <select value={form.experience} onChange={(e) => setField("experience", e.target.value)}>
                  <option value="beginner">Beginner</option>
                  <option value="intermediate">Intermediate</option>
                  <option value="advanced">Advanced</option>
                </select>
              </label>
              <label className="fit-field">
                <span>Equipment</span>
                <select value={form.equipment} onChange={(e) => setField("equipment", e.target.value)}>
                  {EQUIPMENT.map((q) => (
                    <option key={q.value} value={q.value}>
                      {q.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="fit-row">
              <label className="fit-field">
                <span>
                  Training days / week <strong>{form.days_per_week}</strong>
                </span>
                <input
                  type="range"
                  min="2"
                  max="6"
                  value={form.days_per_week}
                  onChange={(e) => setField("days_per_week", e.target.value)}
                />
              </label>
              <label className="fit-field">
                <span>
                  Minutes / session <strong>{form.session_minutes}</strong>
                </span>
                <input
                  type="range"
                  min="15"
                  max="120"
                  step="5"
                  value={form.session_minutes}
                  onChange={(e) => setField("session_minutes", e.target.value)}
                />
              </label>
            </div>

            <div className="fit-field">
              <span>Diet preference</span>
              <div className="fit-pills">
                {DIETS.map((d) => (
                  <button
                    type="button"
                    key={d.value}
                    className={`fit-pill ${form.diet_preference === d.value ? "active" : ""}`}
                    onClick={() => setField("diet_preference", d.value)}
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </div>

            <label className="fit-field">
              <span>Injuries or limitations (optional)</span>
              <input
                type="text"
                maxLength={300}
                value={form.injuries}
                onChange={(e) => setField("injuries", e.target.value)}
                placeholder="e.g. knee pain, lower back stiffness"
              />
            </label>

            <label className="fit-field">
              <span>BMI reference</span>
              <select value={form.bmi_standard} onChange={(e) => setField("bmi_standard", e.target.value)}>
                <option value="asian">Asian-Indian (healthy 18.5–22.9)</option>
                <option value="who">WHO international (healthy 18.5–24.9)</option>
              </select>
            </label>

            <button type="submit" className="fit-btn fit-btn-primary fit-btn-block" disabled={saving}>
              {saving ? "Calculating…" : profile ? "Update & recalculate" : "Calculate my metrics"}
            </button>
          </form>

          <div className="fit-stack">
            {loadingProfile ? (
              <div className="fit-card fit-skeleton" />
            ) : !metrics ? (
              <div className="fit-card fit-empty">
                <LuScale size={42} />
                <h3>Start with your numbers</h3>
                <p>
                  Fill in your profile to see your BMI, daily calorie needs, macros and a healthy
                  weight range – then let the AI build your plan.
                </p>
              </div>
            ) : (
              <>
                <div className="fit-card">
                  <div className="fit-card-head">
                    <h2>Body Mass Index</h2>
                    <span className="fit-muted">
                      {metrics.bmi_standard === "asian" ? "Asian-Indian cut-offs" : "WHO cut-offs"}
                    </span>
                  </div>
                  <BmiGauge
                    bmi={metrics.bmi}
                    standard={metrics.bmi_standard}
                    category={metrics.bmi_category}
                    color={metrics.bmi_color}
                  />
                  <p className="fit-note">
                    Healthy range for your height:{" "}
                    <strong>
                      {displayWeight(metrics.healthy_weight_min)}–{displayWeight(metrics.healthy_weight_max)} {weightUnit}
                    </strong>
                    {metrics.kg_to_healthy_range !== 0 && (
                      <>
                        {" "}
                        · {Math.abs(metrics.kg_to_healthy_range) > 0 && displayWeight(Math.abs(metrics.kg_to_healthy_range))}{" "}
                        {weightUnit} {metrics.kg_to_healthy_range > 0 ? "below" : "above"} it
                      </>
                    )}
                  </p>
                  <p className="fit-disclaimer">
                    BMI doesn't distinguish muscle from fat – athletes often read "high". It's a
                    screening tool, not a verdict.
                  </p>
                </div>

                {metrics.guardrails?.length > 0 && (
                  <div className="fit-guardrail">
                    <FiHeart />
                    <div>
                      {metrics.guardrails.map((g) => (
                        <p key={g}>{g}</p>
                      ))}
                    </div>
                  </div>
                )}

                <div className="fit-stats-grid">
                  <StatTile icon={<LuFlame />} label="Daily target" value={metrics.target_calories} unit="kcal"
                    sub={metrics.calorie_adjustment === 0 ? "Maintenance" : `${metrics.calorie_adjustment > 0 ? "+" : ""}${metrics.calorie_adjustment} vs maintenance`}
                    accent="#f97316" />
                  <StatTile icon={<FiZap />} label="Maintenance (TDEE)" value={metrics.tdee} unit="kcal" sub={metrics.activity_label} accent="#8b5cf6" />
                  <StatTile icon={<FiHeart />} label="BMR" value={metrics.bmr} unit="kcal" sub="Calories at complete rest" accent="#f43f5e" />
                  <StatTile icon={<FiDroplet />} label="Water" value={metrics.water_l} unit="L/day" sub="More on training days" accent="#22d3ee" />
                  <StatTile icon={<FiTrendingUp />} label="Expected pace" value={metrics.weekly_change_kg === 0 ? "Steady" : `${metrics.weekly_change_kg > 0 ? "+" : ""}${displayWeight(metrics.weekly_change_kg)}`}
                    unit={metrics.weekly_change_kg === 0 ? "" : `${weightUnit}/wk`} sub={metrics.goal_label} accent="#10b981" />
                  {metrics.body_fat_pct != null && (
                    <StatTile icon={<LuScale />} label="Body fat (est.)" value={metrics.body_fat_pct} unit="%" sub="BMI-based estimate" accent="#3385fb" />
                  )}
                </div>

                <div className="fit-card">
                  <div className="fit-card-head">
                    <h2>Daily Macros</h2>
                    <span className="fit-muted">Fibre ≥ {metrics.macros.fiber_g} g</span>
                  </div>
                  <div className="fit-macros">
                    {macroData.map((m) => (
                      <div key={m.key} className="fit-macro">
                        <div className="fit-macro-top">
                          <span>
                            <i style={{ background: MACRO_COLORS[m.key] }} /> {m.name}
                          </span>
                          <strong>{m.grams} g</strong>
                        </div>
                        <div className="fit-bar">
                          <div
                            style={{
                              width: `${Math.round((m.kcal / macroTotal) * 100)}%`,
                              background: MACRO_COLORS[m.key],
                            }}
                          />
                        </div>
                        <small>{Math.round((m.kcal / macroTotal) * 100)}% of calories</small>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="fit-card">
                  <div className="fit-card-head">
                    <h2>Weight Trend</h2>
                    <form className="fit-weighin" onSubmit={submitWeighIn}>
                      <input
                        type="number"
                        step="0.1"
                        value={weighIn}
                        onChange={(e) => setWeighIn(e.target.value)}
                        placeholder={`Today (${weightUnit})`}
                      />
                      <button type="submit" className="fit-btn fit-btn-soft">
                        Log
                      </button>
                    </form>
                  </div>
                  {historyChart.length > 1 ? (
                    <div className="fit-chart">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={historyChart} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                          <XAxis dataKey="date" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} />
                          <YAxis domain={["dataMin - 2", "dataMax + 2"]} tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} />
                          <Tooltip
                            contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderRadius: 12, color: "var(--text-primary)" }}
                            formatter={(v, n) => (n === "weight" ? [`${v} ${weightUnit}`, "Weight"] : [v, "BMI"])}
                          />
                          <Line type="monotone" dataKey="weight" stroke="#f97316" strokeWidth={3} dot={{ r: 4, fill: "#f97316" }} activeDot={{ r: 6 }} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  ) : (
                    <p className="fit-muted fit-center">
                      Log your weight once a week, same time of day, to see a trend here.
                    </p>
                  )}
                </div>

                <button className="fit-btn fit-btn-gradient fit-btn-block" onClick={() => setTab("plan")}>
                  <LuSparkles /> {plan ? "View my AI plan" : "Build my AI workout & diet plan"}
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {/* ============================================================ PLAN */}
      {tab === "plan" && (
        <div className="fit-plan">
          <div className="fit-card fit-plan-head">
            <div className="fit-plan-head-text">
              <h2>
                <LuSparkles /> Your Personalised Plan
              </h2>
              {plan ? (
                <>
                  <p>{plan.summary}</p>
                  <div className="fit-plan-meta">
                    <span className={`fit-badge ${planDoc.source === "ai" ? "ai" : "template"}`}>
                      {planDoc.source === "ai" ? (
                        <>
                          <FiCpu /> AI-personalised
                        </>
                      ) : (
                        <>
                          <FiCheckCircle /> Smart template
                        </>
                      )}
                    </span>
                    <span className="fit-muted">
                      <FiClock /> {fmtDate(planDoc.created_at, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
                    </span>
                    {planDoc.metrics && (
                      <span className="fit-muted">
                        <LuFlame /> {planDoc.metrics.target_calories} kcal · BMI {planDoc.metrics.bmi}
                      </span>
                    )}
                  </div>
                </>
              ) : (
                <p>
                  {profile
                    ? "Generate a weekly workout schedule and Indian-friendly meal plan built around your numbers, equipment, diet and any injuries."
                    : "Save your body profile first – the plan is built from it."}
                </p>
              )}
            </div>
            <div className="fit-plan-actions">
              <select value={planLanguage} onChange={(e) => setPlanLanguage(e.target.value)} aria-label="Plan language">
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.label}
                  </option>
                ))}
              </select>
              <button className="fit-btn fit-btn-gradient" onClick={generatePlan} disabled={generating}>
                {generating ? (
                  <>
                    <FiRefreshCw className="fit-spin" /> Building…
                  </>
                ) : plan ? (
                  <>
                    <FiRefreshCw /> Regenerate
                  </>
                ) : (
                  <>
                    <LuSparkles /> Generate plan
                  </>
                )}
              </button>
            </div>
          </div>

          {generating && (
            <div className="fit-card fit-generating">
              <div className="fit-pulse">
                <LuDumbbell />
              </div>
              <h3>Designing your week…</h3>
              <p className="fit-muted">
                The AI coach is matching exercises to your equipment and meals to your diet. This can
                take up to a minute.
              </p>
            </div>
          )}

          {plan && !generating && (
            <>
              {(plan.guardrails?.length > 0 || plan.context?.low_energy || plan.context?.short_sleep) && (
                <div className="fit-guardrail">
                  <FiHeart />
                  <div>
                    {plan.guardrails?.map((g) => (
                      <p key={g}>{g}</p>
                    ))}
                    {plan.context?.low_energy && (
                      <p>Your recent mood logs show low energy, so this plan is gentler. Listen to your body.</p>
                    )}
                    {plan.context?.short_sleep && (
                      <p>
                        <FiMoon /> Your last logged sleep was short – keep today's intensity moderate.
                      </p>
                    )}
                  </div>
                </div>
              )}

              <div className="fit-segment fit-segment-lg">
                <button className={planView === "workout" ? "active" : ""} onClick={() => setPlanView("workout")}>
                  <LuDumbbell /> Workout
                </button>
                <button className={planView === "diet" ? "active" : ""} onClick={() => setPlanView("diet")}>
                  <LuSalad /> Diet
                </button>
              </div>

              {planView === "workout" && (
                <>
                  <div className="fit-days">
                    {schedule.map((d) => (
                      <button
                        key={d.day}
                        className={`fit-day ${d.type} ${activeDay?.day === d.day ? "active" : ""} ${d.day === todayName() ? "today" : ""}`}
                        onClick={() => setSelectedDay(d.day)}
                      >
                        <span className="fit-day-name">{d.day.slice(0, 3)}</span>
                        <span className="fit-day-icon">
                          {d.type === "rest" ? <FiMoon /> : d.type === "cardio" ? <FiHeart /> : <LuDumbbell />}
                        </span>
                        {doneToday.has(d.day) && <FiCheckCircle className="fit-day-done" />}
                      </button>
                    ))}
                  </div>

                  {activeDay && (
                    <div className="fit-card fit-day-card">
                      <div className="fit-card-head">
                        <div>
                          <h2>
                            {activeDay.day} · {activeDay.focus}
                          </h2>
                          <span className="fit-muted">
                            <FiClock /> ~{activeDay.duration_min} min · {activeDay.exercises.length}{" "}
                            {activeDay.exercises.length === 1 ? "exercise" : "exercises"}
                          </span>
                        </div>
                        <button
                          className={`fit-btn ${doneToday.has(activeDay.day) ? "fit-btn-soft" : "fit-btn-primary"}`}
                          onClick={() => markDayDone(activeDay)}
                          disabled={doneToday.has(activeDay.day)}
                        >
                          {doneToday.has(activeDay.day) ? (
                            <>
                              <FiCheck /> Done today
                            </>
                          ) : (
                            <>
                              <FiCheckCircle /> Mark as done
                            </>
                          )}
                        </button>
                      </div>

                      <ol className="fit-exercises">
                        {activeDay.exercises.map((ex, i) => (
                          <li key={`${ex.name}-${i}`} className="fit-exercise">
                            <span className="fit-ex-num">{i + 1}</span>
                            <div className="fit-ex-body">
                              <strong>{ex.name}</strong>
                              {ex.notes && <span>{ex.notes}</span>}
                            </div>
                            <div className="fit-ex-dose">
                              <span className="fit-ex-sets">
                                {ex.sets > 1 ? `${ex.sets} × ` : ""}
                                {ex.reps}
                              </span>
                              {ex.rest_sec > 0 && <small>{ex.rest_sec}s rest</small>}
                            </div>
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  <div className="fit-grid fit-grid-2">
                    <div className="fit-card">
                      <h3 className="fit-h3">
                        <FiZap /> Warm-up
                      </h3>
                      <ul className="fit-list">
                        {plan.workout.warmup.map((w) => (
                          <li key={w}>{w}</li>
                        ))}
                      </ul>
                    </div>
                    <div className="fit-card">
                      <h3 className="fit-h3">
                        <FiMoon /> Cool-down
                      </h3>
                      <ul className="fit-list">
                        {plan.workout.cooldown.map((w) => (
                          <li key={w}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  </div>

                  <div className="fit-card fit-progression">
                    <h3 className="fit-h3">
                      <FiTrendingUp /> How to progress
                    </h3>
                    <p>{plan.workout.progression}</p>
                    {plan.workout.avoided_for_injury && (
                      <p className="fit-muted">
                        <FiInfo /> Movements that load your listed injury were swapped out. Stop any
                        exercise that causes sharp pain.
                      </p>
                    )}
                  </div>
                </>
              )}

              {planView === "diet" && (
                <>
                  <div className="fit-grid fit-grid-diet">
                    <div className="fit-card fit-diet-summary">
                      <h3 className="fit-h3">
                        <LuFlame /> Daily targets
                      </h3>
                      <div className="fit-donut">
                        <ResponsiveContainer width="100%" height="100%">
                          <PieChart>
                            <Pie
                              data={[
                                { name: "Protein", value: plan.diet.macros.protein_g * 4, key: "protein" },
                                { name: "Carbs", value: plan.diet.macros.carbs_g * 4, key: "carbs" },
                                { name: "Fat", value: plan.diet.macros.fat_g * 9, key: "fat" },
                              ]}
                              dataKey="value"
                              cx="50%"
                              cy="50%"
                              innerRadius="68%"
                              outerRadius="92%"
                              paddingAngle={3}
                              stroke="none"
                            >
                              {["protein", "carbs", "fat"].map((k) => (
                                <Cell key={k} fill={MACRO_COLORS[k]} />
                              ))}
                            </Pie>
                          </PieChart>
                        </ResponsiveContainer>
                        <div className="fit-donut-center">
                          <strong>{plan.diet.daily_calories}</strong>
                          <span>kcal / day</span>
                        </div>
                      </div>
                      <div className="fit-macro-legend">
                        <span>
                          <i style={{ background: MACRO_COLORS.protein }} /> Protein {plan.diet.macros.protein_g} g
                        </span>
                        <span>
                          <i style={{ background: MACRO_COLORS.carbs }} /> Carbs {plan.diet.macros.carbs_g} g
                        </span>
                        <span>
                          <i style={{ background: MACRO_COLORS.fat }} /> Fat {plan.diet.macros.fat_g} g
                        </span>
                      </div>
                      <div className="fit-water">
                        <FiDroplet /> Drink <strong>{plan.diet.hydration_l} L</strong> of water a day
                      </div>
                    </div>

                    <div className="fit-meals">
                      {plan.diet.meals.map((meal) => (
                        <div key={meal.name} className="fit-meal">
                          <div className="fit-meal-head">
                            <div>
                              <strong>{meal.name}</strong>
                              {meal.time && <span className="fit-muted"> · {meal.time}</span>}
                            </div>
                            {meal.calories > 0 && <span className="fit-meal-kcal">{meal.calories} kcal</span>}
                          </div>
                          <ul>
                            {meal.options.map((o, i) => (
                              <li key={o}>
                                {meal.options.length > 1 && <span className="fit-option">Option {i + 1}</span>}
                                {o}
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="fit-grid fit-grid-2">
                    <div className="fit-card">
                      <h3 className="fit-h3 fit-good">
                        <FiCheckCircle /> Eat more of
                      </h3>
                      <div className="fit-tags">
                        {plan.diet.foods_to_favor.map((f) => (
                          <span key={f} className="fit-tag good">
                            {f}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="fit-card">
                      <h3 className="fit-h3 fit-bad">
                        <FiAlertCircle /> Go easy on
                      </h3>
                      <div className="fit-tags">
                        {plan.diet.foods_to_limit.map((f) => (
                          <span key={f} className="fit-tag bad">
                            {f}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </>
              )}

              <div className="fit-grid fit-grid-2">
                <div className="fit-card">
                  <h3 className="fit-h3">
                    <FiZap /> Coach's tips
                  </h3>
                  <ul className="fit-list">
                    {plan.tips.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </div>
                <div className="fit-card fit-mindbody">
                  <h3 className="fit-h3">
                    <FiHeart /> Mind &amp; body
                  </h3>
                  <ul className="fit-list">
                    {plan.mind_body.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                </div>
              </div>

              <p className="fit-disclaimer fit-center">
                General wellness guidance, not medical advice. Check with a doctor before starting if
                you have a health condition, are pregnant, or feel pain, dizziness or chest discomfort.
              </p>
            </>
          )}
        </div>
      )}

      {/* ============================================================ ACTIVITY */}
      {tab === "activity" && (
        <div className="fit-grid fit-grid-activity">
          <div className="fit-stack">
            <div className="fit-card fit-week">
              <div className="fit-card-head">
                <h2>This Week</h2>
                <span className="fit-muted">WHO goal: 150 active min</span>
              </div>
              <div className="fit-week-body">
                <ProgressRing value={stats?.week_active_minutes || 0} target={stats?.who_target || 150} />
                <div className="fit-week-stats">
                  <div>
                    <strong>{stats?.week_sessions || 0}</strong>
                    <span>sessions</span>
                  </div>
                  <div>
                    <strong>{stats?.week_minutes || 0}</strong>
                    <span>minutes</span>
                  </div>
                  <div>
                    <strong>{stats?.week_calories || 0}</strong>
                    <span>kcal burned</span>
                  </div>
                  <div>
                    <strong>{stats?.streak_days || 0}</strong>
                    <span>day streak</span>
                  </div>
                </div>
              </div>
              <p className="fit-disclaimer">Vigorous minutes count double toward the WHO target.</p>
            </div>

            <form className="fit-card fit-form" onSubmit={submitLog}>
              <h2>Log a Workout</h2>
              <label className="fit-field">
                <span>Activity</span>
                <input
                  type="text"
                  maxLength={80}
                  value={logForm.activity}
                  onChange={(e) => setLogForm((f) => ({ ...f, activity: e.target.value }))}
                  placeholder="e.g. Evening run, Yoga, Upper body"
                />
              </label>
              <div className="fit-row">
                <label className="fit-field">
                  <span>Type</span>
                  <select value={logForm.category} onChange={(e) => setLogForm((f) => ({ ...f, category: e.target.value }))}>
                    {CATEGORIES.map((c) => (
                      <option key={c.value} value={c.value}>
                        {c.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="fit-field">
                  <span>Minutes</span>
                  <input
                    type="number"
                    min="1"
                    max="600"
                    value={logForm.duration_min}
                    onChange={(e) => setLogForm((f) => ({ ...f, duration_min: e.target.value }))}
                  />
                </label>
              </div>
              <div className="fit-field">
                <span>Intensity</span>
                <div className="fit-segment fit-segment-full">
                  {["low", "moderate", "high"].map((i) => (
                    <button
                      type="button"
                      key={i}
                      className={logForm.intensity === i ? "active" : ""}
                      onClick={() => setLogForm((f) => ({ ...f, intensity: i }))}
                    >
                      {i[0].toUpperCase() + i.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              <label className="fit-field">
                <span>How did it feel? (optional)</span>
                <input
                  type="text"
                  maxLength={500}
                  value={logForm.notes}
                  onChange={(e) => setLogForm((f) => ({ ...f, notes: e.target.value }))}
                  placeholder="e.g. Felt energised afterwards"
                />
              </label>
              <button type="submit" className="fit-btn fit-btn-primary fit-btn-block" disabled={logging}>
                {logging ? "Saving…" : "Save workout"}
              </button>
            </form>
          </div>

          <div className="fit-stack">
            <div className="fit-card">
              <div className="fit-card-head">
                <h2>Weekly Minutes</h2>
                <span className="fit-muted">Last 8 weeks</span>
              </div>
              <div className="fit-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stats?.weekly || []} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="fitBarGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#f97316" />
                        <stop offset="100%" stopColor="#f43f5e" />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--border-color)" vertical={false} />
                    <XAxis dataKey="week" tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <YAxis domain={[0, (max) => Math.max(max, 160)]} tick={{ fill: "var(--text-secondary)", fontSize: 12 }} axisLine={false} tickLine={false} />
                    <Tooltip
                      cursor={{ fill: "var(--accent-soft)" }}
                      contentStyle={{ background: "var(--bg-elevated)", border: "1px solid var(--border-color)", borderRadius: 12, color: "var(--text-primary)" }}
                      formatter={(v) => [`${v} min`, "Active"]}
                    />
                    <ReferenceLine y={150} stroke="#10b981" strokeDasharray="4 4" />
                    <Bar dataKey="minutes" fill="url(#fitBarGrad)" radius={[8, 8, 0, 0]} maxBarSize={36} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="fit-card">
              <h2>Recent Workouts</h2>
              {workouts.length === 0 ? (
                <div className="fit-empty fit-empty-sm">
                  <FiActivity size={32} />
                  <p>No workouts yet. Your first one can be a 10-minute walk – it all counts.</p>
                </div>
              ) : (
                <ul className="fit-history">
                  {workouts.map((w) => (
                    <li key={w._id} className="fit-history-item">
                      <div className={`fit-history-icon ${w.category}`}>
                        {w.category === "strength" ? <LuDumbbell /> : w.category === "yoga" ? <FiMoon /> : <FiActivity />}
                      </div>
                      <div className="fit-history-body">
                        <strong>{w.activity}</strong>
                        <span className="fit-muted">
                          {fmtDate(w.created_at, { weekday: "short", day: "numeric", month: "short" })} ·{" "}
                          {w.duration_min} min · {w.intensity}
                          {w.notes ? ` · “${w.notes}”` : ""}
                        </span>
                      </div>
                      <span className="fit-history-kcal">{w.calories} kcal</span>
                      <button className="fit-icon-btn" onClick={() => deleteLog(w._id)} aria-label="Delete workout">
                        <FiTrash2 />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ============================================================ COACH */}
      {tab === "coach" && (
        <div className="fit-card fit-coach">
          <div className="fit-card-head">
            <h2>
              <FiCpu /> AI Fitness Coach
            </h2>
            <select value={planLanguage} onChange={(e) => setPlanLanguage(e.target.value)} aria-label="Reply language">
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>

          <div className="fit-coach-feed">
            {coachMessages.length === 0 && (
              <div className="fit-coach-intro">
                <LuSparkles size={36} />
                <p>
                  Ask about workouts, food, recovery or staying motivated.
                  {profile ? " Answers use your profile." : " Save your body profile for personalised answers."}
                </p>
                <div className="fit-suggestions">
                  {COACH_PROMPTS.map((p) => (
                    <button key={p} className="fit-pill" onClick={() => askCoach(p)}>
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {coachMessages.map((m, i) => (
              <div key={i} className={`fit-msg ${m.role} ${m.source || ""}`}>
                {m.role === "coach" ? (
                  <div className="fit-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                  </div>
                ) : (
                  m.text
                )}
              </div>
            ))}
            {asking && (
              <div className="fit-msg coach fit-typing">
                <span />
                <span />
                <span />
              </div>
            )}
            <div ref={coachEndRef} />
          </div>

          <form
            className="fit-coach-input"
            onSubmit={(e) => {
              e.preventDefault();
              askCoach();
            }}
          >
            <input
              type="text"
              maxLength={1000}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask your coach anything…"
            />
            <button type="submit" className="fit-btn fit-btn-gradient" disabled={asking || !question.trim()} aria-label="Send">
              <FiSend />
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

export default Fitness;
