# Deploying MindWell

One container serves everything: the React build and the API, from one URL.
There is no separate frontend host and no CORS to configure.

```
https://<your-app-url>/         the web app
https://<your-app-url>/api/...  the API
https://<your-app-url>/health   status
```

You need four free accounts. Nothing here needs a credit card.

| What | Why | Where |
|---|---|---|
| MongoDB Atlas | database (you already have this) | cloud.mongodb.com |
| Groq | the language model — your laptop's Ollama is not reachable from a server | console.groq.com |
| Brevo | sends the signup codes — Railway (below Pro) and Render's free tier both block SMTP, so Gmail cannot work there | app.brevo.com |
| Railway or Render | runs the container | railway.com / render.com |

---

## 1. Before you push

```bash
cd backend
pip install -r requirements.txt
pip install -r requirements-dev.txt
pytest tests -q
```

Then make sure nothing secret is tracked:

```bash
git status            # .env, venv/, node_modules/ must NOT be listed
git add .
git commit -m "feat: production deployment — single container, ONNX sentiment, hosted LLM"
git push
```

## 2. MongoDB Atlas

1. **Database Access** → your user → *Edit* → set a new password if the old
   one was ever committed to git.
2. **Network Access** → *Add IP Address* → *Allow access from anywhere*
   (`0.0.0.0/0`). Neither Railway (below Pro) nor Render's free tier has a
   fixed outbound IP, so the
   database has to accept connections from any address; the username and
   password are what protect it.
3. **Connect → Drivers** → copy the connection string. That is `MONGO_URI`.

## 3. Groq (the language model)

1. Sign in at console.groq.com → **API Keys** → *Create API Key*.
2. Copy it. That is `LLM_API_KEY`.

The blueprint already sets the endpoint and the models
(`llama-3.3-70b-versatile`, falling back to `llama-3.1-8b-instant` when the
first is rate limited).

## 4. Brevo (verification emails)

1. Sign up at brevo.com.
2. **Senders, Domains & Dedicated IPs → Senders** → add the address you want
   codes to come from and click the confirmation link Brevo emails to it.
   That address is `EMAIL_FROM`.
3. **SMTP & API → API Keys** → *Generate a new API key*. That is
   `BREVO_API_KEY`.

A new Brevo account may need its sending approved before mail goes out; if
codes do not arrive, check **Transactional → Logs** there first.

## 5. Host it — Railway or Render

Pick one. Both build the `Dockerfile` at the repo root.

### Option A — Railway

`railway.json` tells Railway to build the Dockerfile, health-check `/health`
and run one instance.

1. railway.com → **New Project → Deploy from GitHub repo** → pick the
   repository. The first deploy will fail or exit: the variables are not set
   yet. That is expected.
2. Open the service → **Variables → Raw Editor** and paste this, with your
   own values in the four marked lines:

   ```
   MONGO_URI=<from step 2>
   JWT_SECRET=<see below>
   LLM_API_KEY=<from step 3>
   BREVO_API_KEY=<from step 4>
   EMAIL_FROM=<the verified sender from step 4>
   EMAIL_FROM_NAME=MindWell
   LLM_BASE_URL=https://api.groq.com/openai/v1
   LLM_MODEL=llama-3.3-70b-versatile
   LLM_FALLBACK_MODEL=llama-3.1-8b-instant
   LLM_TIMEOUT=30
   PORT=8000
   ```

   Generate `JWT_SECRET` on your machine and paste the output:

   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

3. **Deploy** the staged changes. The build takes several minutes: it builds
   the React app, installs Python packages, downloads the 68 MB sentiment
   model and checks that it classifies correctly.
4. **Settings → Networking → Generate Domain**, target port `8000`. That is
   your public URL.

Railway is not free forever: a new account gets a one-time trial credit,
and after that the free plan's monthly credit is small. Watch **Usage**; when
the credit runs out Railway stops the service until you add a plan.

### Option B — Render

1. render.com → **New + → Blueprint** → connect the GitHub repository.
   Render reads `render.yaml`.
2. It asks for the four secrets:

   | Key | Value |
   |---|---|
   | `MONGO_URI` | from step 2 |
   | `LLM_API_KEY` | from step 3 |
   | `BREVO_API_KEY` | from step 4 |
   | `EMAIL_FROM` | the verified sender from step 4 |

   `JWT_SECRET` is generated for you.
3. **Apply**. The first build takes several minutes, for the same reasons.

## 6. Verify the deploy

Open `https://<your-app-url>/health`. You want:

```json
{ "status": "ok", "database": "up",
  "sentiment": { "backend": "onnx", "ready": true },
  "email": "brevo" }
```

Then sign up through the site with a real mailbox, and run the end-to-end
test against it with that account:

```bash
cd backend
python scripts/smoke_test.py https://<your-app-url>/api \
    --email you+test@gmail.com --password 'the password you chose' --delete-account
```

It walks every feature — auth, chat, memory, Hindi, the crisis path in
English and Marathi, journal, mood, routine, meditation, sleep, goals,
community, insights, fitness, Health Twin, export, account deletion — and
prints what passed and what did not.

---

## What to expect from the free tier

- **Railway credit.** Usage is billed against your credit; at zero the
  service is stopped, not slowed.
- **Cold starts (Render).** Render stops a free service after 15 minutes without
  traffic; the next visit takes about a minute to wake it. Open the site a
  minute before a demo.
- **750 instance hours a month**, shared by the free services in your
  workspace.
- **Groq rate limits.** The free tier is metered per model. When the main
  model is rate limited the API falls back to the smaller one; if both are,
  chat replies with a "give me a moment" message rather than an error.
- **One instance.** The rate limiter and the LLM circuit breaker keep their
  state in the process, which is correct for a single instance and is why
  the container runs one worker.

## If something is wrong

| Symptom | Cause |
|---|---|
| Build fails at "verify_sentiment" | The model download failed or changed. Set the `SENTIMENT_ONNX_URL` build arg to a working ONNX export. |
| Service exits immediately with `FATAL:` | A required setting is missing or still points at localhost. The message names it. |
| `/health` says `"database": "down"` | `MONGO_URI` is wrong, or Atlas Network Access does not include `0.0.0.0/0`. |
| Chat always answers "having trouble thinking clearly" | `LLM_API_KEY` is missing or wrong. `/health` shows `api_key_set` and `circuit_open`. |
| Signup says it couldn't send the email | `/health` → `"email"`. `none` means `BREVO_API_KEY` or `EMAIL_FROM` is not set; otherwise check Brevo's logs and that the sender is verified. |
| Hindi/Marathi replies come back in English | Google's translation endpoint refused the server and the LLM fallback also failed; check the logs for `translation`. |

## Running the production image locally

```bash
python backend/scripts/fetch_sentiment_model.py     # optional: ONNX locally too
docker compose up --build                           # http://localhost:8000
```

`backend/.env` must point `LLM_BASE_URL` at something reachable from inside
the container: a hosted endpoint, or `http://host.docker.internal:11434/v1`
for an Ollama on your machine.

## Other hosts

Nothing here is specific to Railway or Render. Any host that runs a
Dockerfile and injects `PORT` works (Fly.io, Koyeb, a VPS). Give it the same
environment variables as above.
