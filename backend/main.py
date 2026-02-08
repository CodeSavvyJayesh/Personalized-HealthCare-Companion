from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import requests
import threading
import time
import secrets

from passlib.context import CryptContext
from deep_translator import GoogleTranslator

from db import users_collection
from utils import send_otp_email

app = FastAPI()

# ================= SECURITY =================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
otp_store = {}

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= AI CONFIG =================
MODEL_NAME = "llama3:8b"
OLLAMA_URL = "http://127.0.0.1:11434/v1/chat/completions"

SYSTEM_PROMPT = """
You are an empathetic, calm, emotionally supportive mental health companion.

IMPORTANT RESPONSE FORMAT RULES:
- Always respond in VALID MARKDOWN
- Use bullet points or numbered lists when giving steps or tips
- Use **bold** for headings or key ideas
- Add a blank line between paragraphs
- Keep responses structured and easy to read

Behavior rules:
- Always acknowledge emotions first
- Never judge or shame
- No medical diagnosis or medication advice
- Ask at most ONE gentle follow-up question
- Keep replies 2–8 short sentences
- Warm, human, comforting tone
"""


# 🔥 IMPORTANT: MATCH FRONTEND LANGUAGES
LANG_CODE_MAP = {
    "en-US": "en",
    "hi-IN": "hi",
    "mr-IN": "mr",
}

# ================= MODEL WARMUP =================
def warm_up_model():
    try:
        requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "Hello"}
                ],
            },
            timeout=30
        )
        print("✅ LLaMA-3 warmed up")
    except Exception as e:
        print("⚠️ Warmup failed:", e)

threading.Thread(target=warm_up_model, daemon=True).start()

# ================= CHAT =================
@app.post("/chat")
async def chat_endpoint(request: Request):
    data = await request.json()

    user_text = data.get("text", "").strip()
    language_code = data.get("language", "en-US")
    source_lang = LANG_CODE_MAP.get(language_code, "en")

    if not user_text:
        return {"reply": "I’m here with you 💙 Take your time."}

    print("🌍 Language:", language_code)

    # 1️⃣ Translate → English
    user_text_en = user_text
    if source_lang != "en":
        user_text_en = GoogleTranslator(
            source=source_lang, target="en"
        ).translate(user_text)

    print("🧑 User (EN):", user_text_en)

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text_en},
        ],
        "temperature": 0.8,
        "top_p": 0.9,
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        response.raise_for_status()

        result = response.json()
        bot_reply_en = result["choices"][0]["message"]["content"]

        print("🤖 LLaMA (EN):", bot_reply_en)

        # 2️⃣ Translate back
        final_reply = bot_reply_en
        if source_lang != "en":
            final_reply = GoogleTranslator(
                source="en", target=source_lang
            ).translate(bot_reply_en)

        return {"reply": final_reply}

    except Exception as e:
        print("❌ Chat error:", e)
        return {
            "reply": "I’m having a little trouble right now, but I’m still here 💙"
        }

# ================= AUTH =================
@app.post("/signup")
async def signup(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return {"success": False, "message": "Missing fields"}

    if users_collection.find_one({"username": username}):
        return {"success": False, "message": "User exists"}

    users_collection.insert_one({
        "username": username,
        "password": pwd_context.hash(password),
    })

    return {"success": True}

@app.post("/login")
async def login(request: Request):
    data = await request.json()
    username = data.get("username")
    password = data.get("password")

    user = users_collection.find_one({"username": username})
    if not user or not pwd_context.verify(password, user["password"]):
        return {"success": False}

    return {"success": True}

# ================= OTP =================
@app.post("/send-otp")
async def send_otp(request: Request):
    data = await request.json()
    email = data.get("email")

    otp = str(secrets.randbelow(1000000)).zfill(6)
    otp_store[email] = {"otp": otp, "time": time.time()}

    await send_otp_email(email, otp)
    return {"success": True}

@app.post("/verify-otp")
async def verify_otp(request: Request):
    data = await request.json()
    email = data.get("email")
    otp = data.get("otp")
    password = data.get("password")

    record = otp_store.get(email)
    if not record or record["otp"] != otp:
        return {"success": False}

    if time.time() - record["time"] > 300:
        return {"success": False}

    users_collection.insert_one({
        "username": email,
        "password": pwd_context.hash(password),
    })

    del otp_store[email]
    return {"success": True}
