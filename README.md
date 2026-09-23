# MindWell – Personalized HealthCare Companion

A mental and physical wellbeing companion built around one idea: **the AI
is useful, but it is never the last line of defence.**

MindWell pairs an empathetic LLM companion with a deterministic,
benchmarked crisis-safety layer, conversational memory, strict per-user
data isolation, and a full **Physical Fitness** module – BMI and body
metrics, AI-generated workout and diet plans, activity tracking and an AI
coach. Available in English, Hindi and Marathi.

> MindWell is a supportive companion, not a clinical tool. It does not
> diagnose or treat. The safety layer is a floor under the model, not a
> substitute for care.

---

## Contents

- [Features](#features)
- [Crisis-safety layer](#crisis-safety-layer)
- [The benchmark](#the-benchmark)
- [Physical Fitness module](#physical-fitness-module)
- [Architecture](#architecture)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [API overview](#api-overview)
- [Testing](#testing)
- [Privacy](#privacy)
- [Roadmap](#roadmap)

---

## Features

| Module | What it does |
|---|---|
| **Therapist AI** | Empathetic chat with memory, voice input/output, English / Hindi / Marathi |
| **Safety Lab** | Live, inspectable view of the crisis classifier and its benchmark |
| **Physical Fitness** | BMI, BMR/TDEE, macros, AI workout + diet plans, activity log, AI coach |
| **Mood Tracker** | Log mood, intensity, energy and tags; see patterns over time |
| **Journaling** | Private journal entries with mood tagging |
| **Sleep Health** | Bed/wake logging, duration and quality history |
| **Meditation** | Guided sessions with streak tracking |
| **Daily Routine** | Habit and task tracking |
| **Goal Setting** | Set, complete and track wellbeing goals |
| **Calm Sounds** | Curated ambient playlists (rain, lo-fi, nature, focus, …) |
| **Community** | Anonymous support wall, routed through the same safety classifier |
| **Insights** | Sentiment and mood analytics over your own history |
| **Resources** | Articles and guides for mental wellness |

Light and dark themes, responsive down to phone width.

---

## Crisis-safety layer

Most chatbot projects hand every message to a model and hope. For a mental
health app that is not acceptable, so MindWell puts a deterministic layer
**in front of** the model. Every incoming message is scored into one of
four risk tiers before anything else happens:

| Tier | Signal | What the system does |
|------|--------|----------------------|
| 0 – `NONE` | ordinary conversation | normal LLM path |
| 1 – `DISTRESS` | strong negative affect | normal path, logged |
| 2 – `IDEATION` | passive ideation, self-harm language | LLM runs under a restricted safety prompt, helplines appended |
| 3 – `IMMINENT` | plan, means, timeframe, goodbye framing | **the LLM is never called** – a fixed, reviewed response with helplines is returned |

Design decisions:

- **Tier 3 bypasses the model entirely.** A generative model cannot be
  trusted to improvise at the one moment where getting it wrong matters most.
- **False negatives cost more than false positives.** The classifier is
  deliberately eager; over-triggering means someone sees a helpline they
  did not need.
- **Context can downgrade, but never clears Tier 3.** "My friend said he
  was suicidal" is de-escalated; "in the movie I want to kill myself
  tonight" is not, because a fiction frame is also the easiest jailbreak.
- **Obfuscation is normalised away** – `k i l l   m y s e l f` and
  `k.i.l.l myself` both resolve before matching.
- **Escalations are audited, not archived.** `safety_events` stores the
  tier, matched patterns and message length – deliberately *not* the
  message body.
- **Every free-text surface is covered** – chat, the community wall, and
  the fitness module's notes, injuries field and AI coach.
- Region-aware helplines (India by default: Tele-MANAS 14416, KIRAN
  1800-599-0019, AASRA, 112).

Behaviour is pinned by a red-team suite in
[`backend/tests/test_safety.py`](backend/tests/test_safety.py) –
obfuscation, casing, idioms (`"the exam was killing me"`), third-party
framing and the fiction-frame bypass.

### Safety Lab

An in-app screen that makes the classifier inspectable: type any message
and see its tier, the context rule applied, matched patterns, latency and
the exact response a user would receive (nothing typed there is stored or
sent to the model). It also shows the benchmark, the dev/holdout gap, an
interactive confusion matrix, per-category accuracy, the helplines surfaced
and the signed-in user's own escalation history.

---

## The benchmark

The safety layer is measured, not asserted. `backend/evals/` holds a
labeled benchmark, a scorer and a CI gate.

Measured 2026-09-15 on 323 labeled messages (English + romanised
Hindi/Marathi):

| Metric | Holdout | Overall |
|---|---|---|
| **Imminent-risk (Tier-3) recall** | **88.9%** | 96.0% |
| Escalation recall (helpline surfaced) | 86.5% | 94.9% |
| False-positive rate on ordinary messages | **0.0%** | 0.0% |
| Ordinary messages escalated to crisis | 0 | 0 |
| Exact tier accuracy | 90.7% | 96.6% |
| p95 latency | – | 0.23 ms |

- **Why two columns:** patterns were written against the **dev** split
  only. The **holdout** split was never inspected, so it estimates
  performance on unseen phrasings. The 11.1-point generalisation gap is
  published rather than hidden, and the holdout number is the one quoted.
- **Before the benchmark existed** the same classifier scored 53.3%
  Tier-3 recall. It looked fine; only measurement surfaced that.
- **Coverage:** 13 adversarial categories – plain phrasing, obfuscation,
  casing, implicit finality with no keyword (`I've set a date`), fiction
  framing, third-party concern, resolved past tense, academic discussion,
  idioms (`this deadline is killing me`), near-misses (`my phone died`),
  code-switched Hindi/Marathi and greetings.
- **Provenance:** every example is hand-written, not collected from real
  people – publishable and privacy-safe, but it measures coverage of
  *anticipated* phrasings rather than real-world prevalence.
- **CI gate:** `tests/test_crisis_eval.py` fails the build if holdout
  Tier-3 recall drops below 0.85, the false-positive rate exceeds 0.10, or
  any ordinary message triggers the crisis response. Thresholds in
  `evals/thresholds.json` are a ratchet – raised when the classifier
  improves, never lowered to turn a build green.
- **Known misses** (three imminent-risk phrasings) are listed in the app
  rather than buried.

```bash
cd backend
python evals/scorer.py     # full report
```

---

## Physical Fitness module

BMI calculation, AI-built workout and diet plans, activity tracking and an
AI coach – designed with the same philosophy as the safety layer:
**the numbers that could hurt someone are deterministic; the AI only
writes around them.**

### Body metrics

| Metric | Method |
|---|---|
| BMI + category | Asian-Indian cut-offs (healthy 18.5–22.9) or WHO (18.5–24.9), user's choice |
| Healthy weight range | Derived from the chosen BMI band and height |
| BMR | Mifflin-St Jeor |
| Maintenance calories (TDEE) | BMR × activity factor (1.2–1.9) |
| Daily calorie target | Goal-based adjustment with hard safety floors |
| Macros | Protein by bodyweight, fat 27% of calories, carbs the remainder, fibre target |
| Water | ~35 ml/kg, adjusted for activity |
| Body fat (estimate) | Deurenberg formula, adults only, clearly labelled as an estimate |

Metric and imperial units, live BMI preview, weigh-in logging and a weight
trend chart.

### AI workout and diet plans

- **7-day workout schedule** matched to goal, experience, equipment (none /
  dumbbells & bands / full gym), days per week and session length, with
  sets, reps, rest, coaching cues, warm-up, cool-down and a 4-week
  progression. Movements that load a listed injury (knee, back, shoulder,
  wrist, ankle) are swapped out.
- **Indian-friendly meal plan** – five meals with options and per-meal
  calories, for vegetarian, eggetarian, non-veg, vegan and Jain diets.
- Plans can be generated in **English, Hindi or Marathi**.
- One-tap **"Mark as done"** logs the day's session.

### Guardrails

- The LLM **never picks the calorie target or macros** – they are computed
  and then forced onto whatever the model returns.
- Every AI plan is **validated and normalised**: malformed sections are
  replaced from a rule-based plan, meal calories are rescaled to the
  target, and **meal options that break the diet preference are removed**
  (e.g. chicken in a vegetarian plan, onion/garlic in a Jain plan, dairy in
  a vegan plan).
- **No fat-loss plan for an underweight BMI or for under-18s** – the goal
  is redirected with a gentle explanation.
- **Calorie floors** (1200 / 1500 kcal, never below BMR) and a deficit cap
  of 20% of maintenance.
- Requests for **severe restriction** ("500 calories a day", "stop eating",
  purging) get a fixed, supportive response with helplines and never reach
  the model.
- **Wellbeing-aware:** if recent mood logs show low energy or the last
  logged sleep was short, the plan is made gentler.
- **Works without the AI:** if the LLM is down, a complete rule-based
  "smart template" plan is served and labelled as such.

### Activity log and AI coach

- Log workouts by type, duration and intensity; calories estimated with MET
  values from the Compendium of Physical Activities.
- Weekly progress ring toward the **WHO target of 150 active minutes**
  (vigorous minutes count double), streaks and an 8-week chart.
- **AI Coach** answers fitness, nutrition, sleep and motivation questions
  using the user's profile, in English, Hindi or Marathi.

---

## Architecture

```
React 19 SPA  ──JWT──▶  FastAPI  ──▶  MongoDB Atlas
                           │
                           ├─▶ Safety classifier   (deterministic, pre-LLM)
                           ├─▶ DistilBERT          (3-class sentiment)
                           ├─▶ Memory              (window + rolling summary)
                           ├─▶ Fitness engine      (deterministic metrics + plan validator)
                           └─▶ LLM                 (any OpenAI-compatible endpoint)
```

| Concern | Approach |
|---|---|
| Auth | JWT access + revocable refresh tokens, bcrypt, silent refresh on the client |
| Authorization | Ownership enforced server-side on every route (`require_owner`) |
| Memory | Last N turns verbatim + LLM-generated rolling summary of older turns |
| Sentiment | DistilBERT SST-2 with a confidence band mapped to a real `NEUTRAL` class |
| LLM | Provider-agnostic, circuit breaker, rule-based fallbacks everywhere |
| Privacy | Self-service data export and hard account deletion |
| Ops | Rate limiting, `/health`, structured logs, non-root Docker, CI |

**Conversation memory** – the chat replays the last `CHAT_WINDOW_TURNS`
turns verbatim and, past `SUMMARISE_AFTER_TURNS`, compresses older turns
into a rolling summary stored on the session: continuity without unbounded
token cost.

**Three-class sentiment** – the bundled SST-2 model only knows two labels,
so predictions below `SENTIMENT_NEUTRAL_THRESHOLD` are mapped to `NEUTRAL`,
and analytics weight each message by model confidence. Insights count only
the user's own messages, not the bot's replies.

### Tech stack

- **Frontend:** React 19, Recharts, React Markdown, React Icons, date-fns
- **Backend:** FastAPI, Pydantic v2, PyMongo, python-jose, passlib/bcrypt
- **ML:** Hugging Face Transformers (DistilBERT), PyTorch
- **LLM:** Ollama, Groq, OpenAI or any OpenAI-compatible API
- **Database:** MongoDB Atlas
- **Deployment:** Docker, Docker Compose, nginx

---

## Project structure

```
ai-mental-health-chatbot/
├── backend/
│   ├── main.py              # FastAPI app, auth, chat, trackers, privacy routes
│   ├── safety.py            # deterministic crisis classifier
│   ├── safety_api.py        # Safety Lab endpoints
│   ├── fitness.py           # fitness API routes
│   ├── fitness_calc.py      # BMI, BMR, TDEE, macros, guardrails (pure functions)
│   ├── fitness_library.py   # exercise/meal library, AI prompt, plan validator
│   ├── analytic.py          # insights and analytics
│   ├── memory.py            # conversation window + rolling summary
│   ├── sentiment.py         # DistilBERT sentiment
│   ├── llm.py               # provider-agnostic LLM client + circuit breaker
│   ├── auth.py  db.py  config.py  schemas.py  ratelimit.py  utils.py
│   ├── evals/               # crisis benchmark, scorer, thresholds
│   ├── models/              # sentiment model weights
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── App.js  api.js  config.js  ThemeContext.js
│   │   └── components/      # Chat, Fitness, SafetyLab, MoodTracker, …
│   ├── public/sounds/       # Calm Sounds audio
│   ├── Dockerfile  nginx.conf
└── docker-compose.yml
```

---

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 18+
- A MongoDB Atlas cluster (or local MongoDB)
- An LLM endpoint – e.g. [Ollama](https://ollama.com) running `llama3:8b`
  locally, or a Groq / OpenAI API key

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env            # then fill it in
python -c "import secrets; print(secrets.token_urlsafe(64))"   # → JWT_SECRET

uvicorn main:app --reload
```

API docs at `http://127.0.0.1:8000/docs`, health check at `/health`.

### Frontend

```bash
cd frontend
npm install
cp .env.example .env            # REACT_APP_API_URL=http://127.0.0.1:8000
npm start
```

The app opens at `http://localhost:3000`.

### Docker

```bash
docker compose up --build
```

Frontend on port 3000, API on port 8000. The API reads `backend/.env`.

---

## Configuration

All configuration is environment-driven, and the app **refuses to start if
a required secret is missing** rather than falling back to an insecure
default. See [`backend/.env.example`](backend/.env.example).

| Variable | Purpose |
|---|---|
| `MONGO_URI`, `MONGO_DB` | Database connection (required) |
| `JWT_SECRET` | Token signing key (required) |
| `CORS_ORIGINS` | Allowed frontend origins |
| `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_TIMEOUT` | LLM endpoint |
| `SENTIMENT_MODEL_PATH`, `SENTIMENT_NEUTRAL_THRESHOLD` | Sentiment model |
| `CHAT_WINDOW_TURNS`, `SUMMARISE_AFTER_TURNS` | Conversation memory |
| `EMAIL_FROM`, `EMAIL_PASSWORD`, `SMTP_HOST`, `SMTP_PORT` | OTP emails |
| `RATE_LIMIT_*` | Request limits |
| `CRISIS_REGION` | Helpline region (default `IN`) |

Switching LLM providers is two lines of `.env`, not a code change:

```env
LLM_BASE_URL=http://127.0.0.1:11434/v1        # Ollama
LLM_MODEL=llama3:8b

# LLM_BASE_URL=https://api.groq.com/openai/v1  # Groq
# LLM_MODEL=llama-3.3-70b-versatile
```

> Never commit `.env`. If a credential was ever committed, rotate it.

---

## API overview

All data routes require a Bearer token and are scoped to the caller.
Full interactive docs are at `/docs`.

| Area | Endpoints |
|---|---|
| Auth | `POST /signup` `/login` `/auth/refresh` `/auth/logout` `/send-otp` `/verify-otp` `/reset-password` |
| Chat | `POST /chat`, `GET /chat-history/{session_id}`, `GET /session-report/{session_id}` |
| Trackers | `/mood`, `/journal`, `/sleep`, `/tasks`, `/goals`, `/meditation` |
| Community | `GET/POST /community/posts`, `POST /community/posts/{id}/like` |
| Safety | `GET /safety/benchmark`, `GET /safety/taxonomy`, `POST /safety/classify`, `GET /safety/events/summary` |
| Fitness | `GET /fitness/profile/{user_id}`, `PUT /fitness/profile`, `POST /fitness/weight`, `POST /fitness/plan`, `GET /fitness/plan/{user_id}`, `POST/GET /fitness/workouts`, `DELETE /fitness/workouts/{id}`, `POST /fitness/coach` |
| Privacy | `GET /me/export`, `DELETE /me` |
| Ops | `GET /health` |

---

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest tests -q
```

The suite covers auth, memory, sentiment, the safety red-team set, the
crisis benchmark CI gate, and the fitness module (calculations, guardrails,
diet-preference filtering, AI plan validation and the API flow against an
in-memory MongoDB).

---

## Privacy

- Every route enforces ownership server-side – a user ID in the URL must
  match the token.
- Safety audit logs store patterns and message length, never the message.
- **Data export** (`GET /me/export`) returns everything stored about the
  user, including fitness data.
- **Account deletion** (`DELETE /me`) hard-deletes all of it.

---

## Roadmap

- RAG over vetted CBT / psychoeducation content with citations
- Token streaming over SSE
- LLM eval harness in CI (empathy / safety / groundedness, LLM-as-judge)
- Fine-tuned multi-label emotion model to replace the binary head
- Field-level encryption for journals and messages
- Wearable / step-count integration for the fitness module
- Mood ↔ activity correlation in Insights

---

## Disclaimer

MindWell provides general wellbeing support and fitness guidance only. It
is not a medical device and does not replace professional diagnosis or
treatment. If you are in crisis, contact local emergency services or a
helpline – in India, **Tele-MANAS 14416** or **KIRAN 1800-599-0019**.
