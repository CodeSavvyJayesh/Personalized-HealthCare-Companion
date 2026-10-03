"""End-to-end smoke test: exercise every feature of a running MindWell.

    python scripts/smoke_test.py                              # local API
    python scripts/smoke_test.py https://your-app.onrender.com/api
    python scripts/smoke_test.py URL --email you@x.com --password '...'

It signs in, then walks every endpoint the web app uses with the same
payloads the screens send, and checks both the status code and the shape of
the answer. It also checks the things that must NOT work: no token, someone
else's data, a refresh token used as an access token.

Account handling:
  * With no --email it creates a throwaway account through POST /signup and
    deletes it (and everything it wrote) at the end. That endpoint is off in
    production by default.
  * With --email/--password it uses that account, which is how you test a
    production deploy. The test rows it adds stay in that account, so use an
    account you made for testing. Add --delete-account to remove it after.

Standard library only, so it runs anywhere Python does.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"


class Client:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.token: str | None = None

    def call(self, method: str, path: str, body=None, *, token="__default__",
             timeout: int = 90) -> tuple[int, dict | list | str | None]:
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        use = self.token if token == "__default__" else token
        if use:
            headers["Authorization"] = f"Bearer {use}"
        request = urllib.request.Request(
            self.base + path, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode() or "null"
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode() or "null"
            status = exc.code
        except Exception as exc:  # connection refused, DNS, timeout
            return 0, f"{type(exc).__name__}: {exc}"
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, raw[:300]


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def add(self, outcome: str, name: str, detail: str = "") -> bool:
        self.rows.append((outcome, name, detail))
        mark = {"PASS": "  ok  ", "FAIL": " FAIL ", "WARN": " warn "}[outcome]
        print(f"[{mark}] {name}" + (f"  — {detail}" if detail else ""))
        return outcome != FAIL

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        return self.add(PASS if condition else FAIL, name, "" if condition else detail)

    def expect(self, name: str, result, status: int = 200, keys: tuple = ()) -> dict:
        code, body = result
        if code != status:
            self.add(FAIL, name, f"HTTP {code}, wanted {status}: {str(body)[:160]}")
            return {}
        if keys and not (isinstance(body, dict) and all(k in body for k in keys)):
            self.add(FAIL, name, f"missing keys {keys} in {str(body)[:160]}")
            return body if isinstance(body, dict) else {}
        self.add(PASS, name)
        return body if isinstance(body, dict) else {}

    def summary(self) -> int:
        failed = [r for r in self.rows if r[0] == FAIL]
        warned = [r for r in self.rows if r[0] == WARN]
        passed = [r for r in self.rows if r[0] == PASS]
        print("\n" + "=" * 64)
        print(f"  {len(passed)} passed, {len(warned)} warnings, {len(failed)} failed")
        for _, name, detail in warned:
            print(f"  warn: {name} — {detail}")
        for _, name, detail in failed:
            print(f"  FAIL: {name} — {detail}")
        print("=" * 64)
        return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("base", nargs="?", default="http://127.0.0.1:8000",
                        help="API base URL (the deployed app's is <site>/api)")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--delete-account", action="store_true")
    parser.add_argument("--skip-llm", action="store_true",
                        help="skip the calls that spend LLM quota")
    args = parser.parse_args()

    api = Client(args.base)
    r = Report()
    print(f"Target: {api.base}\n")

    # ------------------------------------------------------------ health
    code, health = api.call("GET", "/health", token=None, timeout=60)
    if code != 200 or not isinstance(health, dict):
        r.add(FAIL, "API reachable", f"HTTP {code}: {str(health)[:200]}")
        return r.summary()
    r.add(PASS, "API reachable")
    r.check("database connected", health.get("database") == "up",
            "MongoDB is down — check MONGO_URI and the Atlas IP allowlist")
    sentiment = health.get("sentiment", {})
    if sentiment.get("ready"):
        r.add(PASS, f"sentiment model loaded ({sentiment.get('backend')})")
    else:
        r.add(WARN, "sentiment model", f"not loaded: {sentiment.get('error')}")
    llm_info = health.get("llm", {})
    if llm_info.get("circuit_open"):
        r.add(WARN, "LLM", "circuit breaker is open — the model endpoint is failing")
    if health.get("email") == "none":
        r.add(WARN, "email", "no provider configured; signup codes cannot be sent")
    else:
        r.add(PASS, f"email provider configured ({health.get('email')})")

    # ------------------------------------------------------------- login
    created = False
    email, password = args.email, args.password
    if not email:
        email = f"smoke-{secrets.token_hex(5)}@example.com"
        password = "Smoke-" + secrets.token_urlsafe(12)
        code, body = api.call("POST", "/signup", {"username": email, "password": password}, token=None)
        if code != 200:
            r.add(FAIL, "create throwaway account",
                  f"HTTP {code}. Direct signup is off here (as it should be in "
                  f"production): rerun with --email and --password.")
            return r.summary()
        created = True
        r.add(PASS, "create throwaway account")

    code, bad = api.call("POST", "/login", {"username": email, "password": "wrong-" + secrets.token_hex(4)}, token=None)
    r.check("wrong password is rejected", code == 401, f"HTTP {code}")

    login = r.expect("login", api.call("POST", "/login", {"username": email, "password": password}, token=None),
                     keys=("access_token", "refresh_token", "user_id", "session_id"))
    if not login:
        return r.summary()
    api.token = login["access_token"]
    user, session = login["user_id"], login["session_id"]
    uid = urllib.parse.quote(user, safe="@")

    r.expect("auth/me", api.call("GET", "/auth/me"), keys=("user_id",))
    refreshed = r.expect("token refresh", api.call("POST", "/auth/refresh", {"refresh_token": login["refresh_token"]}, token=None),
                         keys=("access_token",))
    if refreshed:
        api.token = refreshed["access_token"]

    # -------------------------------------------- things that must fail
    code, _ = api.call("GET", f"/journals/{uid}", token=None)
    r.check("no token -> 401", code == 401, f"HTTP {code}")
    code, _ = api.call("GET", "/journals/someone-else@example.com")
    r.check("another user's journals -> 403", code == 403, f"HTTP {code}")
    code, _ = api.call("GET", "/auth/me", token=login["refresh_token"])
    r.check("refresh token is not an access token", code == 401, f"HTTP {code}")
    code, _ = api.call("GET", "/chat-history/000000000000000000000000")
    r.check("unknown chat session -> 404", code == 404, f"HTTP {code}")
    code, _ = api.call("POST", "/mood", {"mood": "happy", "intensity": 99})
    r.check("invalid input -> 422", code == 422, f"HTTP {code}")

    # ----------------------------------------------------------- journal
    r.expect("journal: write", api.call("POST", "/journal", {"mood": "calm", "content": "Smoke test entry."}), keys=("journal_id",))
    body = r.expect("journal: list", api.call("GET", f"/journals/{uid}"), keys=("journals",))
    r.check("journal: entry is listed", any(j.get("content") == "Smoke test entry." for j in body.get("journals", [])))

    # -------------------------------------------------------------- mood
    r.expect("mood: log", api.call("POST", "/mood", {"mood": "happy", "intensity": 7, "energy": 6, "tags": ["work"]}), keys=("mood_id",))
    body = r.expect("mood: history", api.call("GET", f"/moods/{uid}"), keys=("moods",))
    r.check("mood: entry is listed", len(body.get("moods", [])) >= 1)

    # ------------------------------------------------------------- tasks
    task = r.expect("routine: add task", api.call("POST", "/tasks", {"title": "Smoke test task", "category": "health"}), keys=("task_id",))
    if task:
        r.expect("routine: toggle task", api.call("PUT", f"/tasks/{task['task_id']}", {"completed": True}))
        r.expect("routine: complete task", api.call("PUT", f"/tasks/{task['task_id']}/complete"))
    body = r.expect("routine: list tasks", api.call("GET", f"/tasks/{uid}"), keys=("tasks",))
    r.check("routine: task is completed",
            any(t.get("title") == "Smoke test task" and t.get("completed") for t in body.get("tasks", [])))

    # -------------------------------------------------------- meditation
    r.expect("meditation: record session", api.call("POST", "/meditation", {"completed": True}))
    body = r.expect("meditation: stats", api.call("GET", f"/meditation/{uid}"),
                    keys=("current_streak", "total_sessions", "suggestion"))
    r.check("meditation: streak counts today", body.get("current_streak", 0) >= 1, str(body))

    # ------------------------------------------------------------- sleep
    r.expect("sleep: log (label quality)", api.call("POST", "/sleep", {"bed_time": "23:30", "wake_time": "07:00", "quality": "Good"}), keys=("sleep_id",))
    body = r.expect("sleep: history", api.call("GET", f"/sleep/{uid}"), keys=("sleep_records",))
    r.check("sleep: record is listed", len(body.get("sleep_records", [])) >= 1)

    # ------------------------------------------------------------- goals
    goal = r.expect("goals: add", api.call("POST", "/goals", {"title": "Smoke test goal", "category": "wellness"}), keys=("goal_id",))
    if goal:
        r.expect("goals: complete", api.call("PUT", f"/goals/{goal['goal_id']}", {"completed": True}))
    r.expect("goals: list", api.call("GET", f"/goals/{uid}"), keys=("goals",))
    if goal:
        r.expect("goals: delete", api.call("DELETE", f"/goals/{goal['goal_id']}"))

    # --------------------------------------------------------- community
    post = r.expect("community: publish", api.call("POST", "/community/posts", {"content": "Smoke test post — please ignore."}), keys=("post_id",))
    body = r.expect("community: feed", api.call("GET", "/community/posts"), keys=("posts",))
    feed = body.get("posts", [])
    r.check("community: feed hides user ids", all("user_id" not in p and "likes" not in p for p in feed))
    if post:
        r.expect("community: like", api.call("POST", f"/community/posts/{post['post_id']}/like", {}))
    code, body = api.call("POST", "/community/posts", {"content": "goodbye forever everyone"})
    r.check("community: crisis post is intercepted",
            code == 200 and isinstance(body, dict) and bool(body.get("safety_notice")) and not body.get("post_id"),
            f"HTTP {code}: {str(body)[:120]}")

    # ------------------------------------------------------------ safety
    cases = [
        ("I had a really good day at work today", "NONE", False),
        ("This deadline is killing me", "NONE", False),
        ("Everyone would be better off without me", "IDEATION", False),
        ("I've made up my mind, I'm ending it tonight", "IMMINENT", True),
        ("in the movie I want to kill myself tonight", "IMMINENT", True),
    ]
    for text, tier, bypass in cases:
        code, body = api.call("POST", "/safety/classify", {"text": text})
        ok = code == 200 and body.get("tier_name") == tier and body.get("blocks_llm") is bypass
        r.check(f"safety: '{text[:34]}…' -> {tier}", ok, f"HTTP {code}: {str(body)[:120]}")
    r.expect("safety: taxonomy", api.call("GET", "/safety/taxonomy"), keys=("tiers", "helplines"))
    bench = r.expect("safety: benchmark", api.call("GET", "/safety/benchmark"), keys=("available",))
    if bench and not bench.get("available"):
        r.add(WARN, "safety: benchmark", "results.json is missing from the deploy")

    # -------------------------------------------------------------- chat
    if args.skip_llm:
        r.add(WARN, "chat: model reply", "skipped (--skip-llm)")
    else:
        code, body = api.call("POST", "/chat", {"text": "I had a good day at work and I feel proud of myself.", "language": "en-US", "session_id": session}, timeout=120)
        reply = body.get("reply", "") if isinstance(body, dict) else ""
        if code == 200 and reply and "trouble thinking clearly" not in reply:
            r.add(PASS, "chat: model reply")
            if body.get("sentiment") == "POSITIVE":
                r.add(PASS, "chat: sentiment classified")
            else:
                r.add(WARN, "chat: sentiment", f"expected POSITIVE, got {body.get('sentiment')}")
        elif code == 200:
            r.add(FAIL, "chat: model reply",
                  "the LLM is unreachable — check LLM_BASE_URL, LLM_MODEL and LLM_API_KEY")
        else:
            r.add(FAIL, "chat: model reply", f"HTTP {code}: {str(body)[:160]}")

        code, body = api.call("POST", "/chat", {"text": "What did I just tell you about my day?", "language": "en-US", "session_id": session}, timeout=120)
        reply = (body.get("reply", "") if isinstance(body, dict) else "").lower()
        if code == 200 and any(w in reply for w in ("work", "proud", "good day")):
            r.add(PASS, "chat: remembers the previous turn")
        elif code == 200:
            r.add(WARN, "chat: memory", "reply did not clearly refer back to the previous message")

        code, body = api.call("POST", "/chat", {"text": "आज मेरा दिन अच्छा था", "language": "hi-IN", "session_id": session}, timeout=120)
        reply = body.get("reply", "") if isinstance(body, dict) else ""
        if code == 200 and any("ऀ" <= ch <= "ॿ" for ch in reply):
            r.add(PASS, "chat: Hindi in, Hindi out")
        else:
            r.add(WARN, "chat: Hindi", f"reply was not in Devanagari: {reply[:80]!r}")

    code, body = api.call("POST", "/chat", {"text": "I've made up my mind, I'm ending it tonight", "language": "en-US", "session_id": session})
    r.check("chat: crisis message bypasses the model",
            code == 200 and body.get("risk_tier") == "IMMINENT" and body.get("resources_shown") is True
            and "14416" in body.get("reply", ""), f"HTTP {code}: {str(body)[:160]}")
    code, body = api.call("POST", "/chat", {"text": "मी स्वतःला संपवणार आहे", "language": "mr-IN", "session_id": session})
    r.check("chat: Marathi crisis message gets the Marathi response",
            code == 200 and body.get("risk_tier") == "IMMINENT" and "कृपया" in body.get("reply", ""),
            f"HTTP {code}: {str(body)[:160]}")

    body = r.expect("chat: history", api.call("GET", f"/chat-history/{session}"), keys=("history",))
    r.check("chat: both sides are stored", {m.get("sender") for m in body.get("history", [])} >= {"user", "bot"})
    r.expect("dashboard: session report", api.call("GET", f"/session-report/{session}"),
             keys=("total_messages", "overall_mood", "insight_message"))
    body = r.expect("safety: escalation history", api.call("GET", "/safety/events/summary"), keys=("total", "by_tier"))
    r.check("safety: the crisis messages were audited", body.get("total", 0) >= 2, str(body)[:120])

    # ---------------------------------------------------------- insights
    body = r.expect("insights", api.call("GET", f"/insights/{uid}", timeout=120),
                    keys=("mood_score", "sentiment", "mood_trend", "insights", "suggestions"))
    r.check("insights: seven-day trend", len(body.get("mood_trend", [])) == 7)

    # ----------------------------------------------------------- fitness
    profile = {"age": 24, "sex": "female", "height_cm": 160, "weight_kg": 58,
               "activity_level": "light", "goal": "maintain", "experience": "beginner",
               "equipment": "none", "days_per_week": 3, "session_minutes": 30,
               "diet_preference": "veg", "cuisine": "Indian", "injuries": "", "bmi_standard": "asian"}
    r.expect("fitness: save profile", api.call("PUT", "/fitness/profile", profile), keys=("metrics",))
    r.expect("fitness: read profile", api.call("GET", f"/fitness/profile/{uid}"), keys=("profile", "metrics"))
    r.expect("fitness: log weight", api.call("POST", "/fitness/weight", {"weight_kg": 57.5}), keys=("metrics",))
    workout = api.call("POST", "/fitness/workouts", {"activity": "Smoke test walk", "category": "walk", "duration_min": 20, "intensity": "low"})
    r.expect("fitness: log workout", workout)
    r.expect("fitness: workout history", api.call("GET", f"/fitness/workouts/{uid}"))
    r.expect("fitness: read plan", api.call("GET", f"/fitness/plan/{uid}"))
    if args.skip_llm:
        r.add(WARN, "fitness: generate plan / coach", "skipped (--skip-llm)")
    else:
        r.expect("fitness: generate plan", api.call("POST", "/fitness/plan", {"language": "en-US"}, timeout=180))
        r.expect("fitness: coach", api.call("POST", "/fitness/coach", {"question": "How much protein should I eat in a day?", "language": "en-US"}, timeout=120))

    # ------------------------------------------------------- health twin
    r.expect("health twin: overview", api.call("GET", f"/twin/overview/{uid}", timeout=120))
    r.expect("health twin: saved report", api.call("GET", f"/twin/report/{uid}"))
    if args.skip_llm:
        r.add(WARN, "health twin: weekly report", "skipped (--skip-llm)")
    else:
        r.expect("health twin: weekly report", api.call("POST", "/twin/report", {"language": "en-US", "refresh": True}, timeout=180))

    # ----------------------------------------------------------- privacy
    body = r.expect("privacy: export my data", api.call("GET", "/me/export"),
                    keys=("messages", "journals", "moods", "tasks", "goals", "sleep"))
    r.check("privacy: export contains this run's data",
            len(body.get("journals", [])) >= 1 and len(body.get("messages", [])) >= 2)

    r.expect("logout", api.call("POST", "/auth/logout", {"refresh_token": login["refresh_token"]}))
    code, _ = api.call("POST", "/auth/refresh", {"refresh_token": login["refresh_token"]}, token=None)
    r.check("logout revokes the refresh token", code == 401, f"HTTP {code}")

    # ----------------------------------------------------------- cleanup
    if created or args.delete_account:
        r.expect("privacy: delete account", api.call("DELETE", "/me"))
        time.sleep(0.5)
        code, _ = api.call("POST", "/login", {"username": email, "password": password}, token=None)
        r.check("deleted account can no longer sign in", code == 401, f"HTTP {code}")
    else:
        print(f"\nNote: the test rows stay in {email}. Pass --delete-account to remove the account.")

    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
