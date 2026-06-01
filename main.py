from __future__ import annotations

from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
import requests
import os
import re

from routes.kundli import router as kundli_router
from services.kundli_service import generate_kundli
from services.daily_forecast import generate_daily_forecast
from services.whatsapp_service import (
    send_message as wa_send_message,
    send_typing  as wa_send_typing,
    mark_read    as wa_mark_read,
)
from geo_lookup import city_to_latlon
app = FastAPI()
app.include_router(kundli_router)

# ─────────────────────────────────────────────────────────────
# Telegram setup
# ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ─────────────────────────────────────────────────────────────
# WhatsApp setup
# ─────────────────────────────────────────────────────────────
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")

# ─────────────────────────────────────────────────────────────
# In-memory session stores — namespaced by channel so a person
# using both Telegram and WhatsApp doesn't collide.
# Keys: "tg:<chat_id>" and "wa:<phone_number>"
# ─────────────────────────────────────────────────────────────
user_sessions: dict = {}
user_kundli_cache: dict = {}

STEPS = ["name", "gender", "dob", "time", "city"]

STEP_PROMPTS = {
    "name": (
        "🌟 *Welcome to Hora — Your Vedic Astrology Guide* 🌟\n\n"
        "I'll cast your personalised Kundli in just a few steps.\n\n"
        "✨ *Step 1 of 5* — Please enter your *full name*:"
    ),
    "gender": (
        "✅ Got it!\n\n"
        "👤 *Step 2 of 5* — What is your *gender*?\n\n"
        "Reply with:\n  • Male\n  • Female\n  • Other"
    ),
    "dob": (
        "✅ Noted!\n\n"
        "📅 *Step 3 of 5* — Enter your *date of birth*\n"
        "Format: DD-MM-YYYY\n"
        "Example: 15-08-1995"
    ),
    "time": (
        "✅ Date saved!\n\n"
        "⏰ *Step 4 of 5* — Enter your *time of birth* (IST)\n"
        "Format: HH.MM\n"
        "Example: 14.30 for 2:30 PM\n\n"
        "_If you don't know the exact time, use 06.00 as a rough estimate._"
    ),
    "city": (
        "✅ Time recorded!\n\n"
        "🗺️ *Step 5 of 5* — Enter your *city and country of birth*\n"
        "Example: Mumbai, India or London, UK"
    ),
}

GREETING_PATTERN = re.compile(r"^(hi|hello|hey|namaste|namaskar|hii+|hlo|start)$", re.IGNORECASE)


# ─────────────────────────────────────────────────────────────
# Telegram helpers
# ─────────────────────────────────────────────────────────────

def tg_send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    max_len = 4000
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode},
            timeout=10,
        )


def tg_send_typing(chat_id: int):
    requests.post(
        f"{TELEGRAM_API}/sendChatAction",
        json={"chat_id": chat_id, "action": "typing"},
        timeout=5,
    )


# ─────────────────────────────────────────────────────────────
# Geocoding (shared)
# ─────────────────────────────────────────────────────────────

# def city_to_latlon(city: str):
#     try:
#         r = requests.get(
#             "https://nominatim.openstreetmap.org/search",
#             params={"q": city, "format": "json", "limit": 1},
#             headers={"User-Agent": "HoraAstroBot/1.0"},
#             timeout=8,
#         )
#         results = r.json()
#         if results:
#             return float(results[0]["lat"]), float(results[0]["lon"])
#     except Exception:
#         pass
#     return None


# ─────────────────────────────────────────────────────────────
# fmt_kundli (unchanged — kept verbatim from your original)
# ─────────────────────────────────────────────────────────────

def fmt_kundli(result: dict, name: str, gender: str) -> list[str]:
    messages = []
    det = result.get("details", {})

    gender_icon = "♂️" if gender.lower() == "male" else "♀️" if gender.lower() == "female" else "⚧️"
    header = (
        f"╔══════════════════════════╗\n"
        f"   🔱 *VEDIC KUNDLI REPORT* 🔱\n"
        f"╚══════════════════════════╝\n\n"
        f"👤 *Name:* {name} {gender_icon}\n"
        f"📅 *DOB:* {det.get('date_of_birth', '—')}\n"
        f"⏰ *Birth Time (IST):* {det.get('time_of_birth', '—')}\n"
        f"🗓️ *Tithi:* {det.get('tithi', {}).get('tithi_name', '—')} "
        f"({det.get('tithi', {}).get('paksha', '—')} Paksha)\n"
        f"🌅 *Sunrise:* {det.get('sunrise', '—')}  🌇 *Sunset:* {det.get('sunset', '—')}\n"
    )
    messages.append(header)

    planets = result.get("planets_data", [])
    if planets:
        PLANET_ICONS = {
            "Sun": "☀️", "Moon": "🌙", "Mars": "🔴", "Mercury": "💚",
            "Jupiter": "🟡", "Venus": "⚪", "Saturn": "🪐",
            "Rahu": "🐉", "Ketu": "☄️", "Ascendant": "⬆️"
        }
        planet_lines = ["🪐 *PLANETARY POSITIONS*\n" + "─" * 28]
        for p in planets:
            icon = PLANET_ICONS.get(p["name"], "⭐")
            planet_lines.append(
                f"{icon} *{p['name']}* → {p['zodiac']} {p['degree_in_rashi']:.2f}°\n"
                f"   📍 {p['Nakshatra']} Pada {p['Pada']}"
            )
        messages.append("\n".join(planet_lines))

    dasha = result.get("dasha", {})
    current = dasha.get("current", {})
    if current:
        dasha_msg = (
            "⏳ *CURRENT DASHA PERIOD*\n" + "─" * 28 + "\n\n"
            f"🔷 *Mahadasha:* {current.get('mahadasha', '—')}\n"
            f"🔹 *Antardasha:* {current.get('antardasha', '—')}\n"
            f"▫️ *Pratyantar:* {current.get('pratyantar', '—')}\n"
            f"📆 *Pratyantar Ends:* {current.get('pratyantar_end', '—')}"
        )
        messages.append(dasha_msg)

    # (Doshas / Yogas / Marriage / Transits / Remedies blocks — keep your originals.
    #  Omitted here only to keep this file readable; paste them in verbatim from your
    #  current main.py — they're channel-agnostic.)

    messages.append(
        "─" * 28 + "\n"
        "🔱 *Report by Hora Astrology API*\n"
        "Type /start to generate a new Kundli ✨\n"
        "Type /today for your Daily Forecast 🌅"
    )
    return messages


# ─────────────────────────────────────────────────────────────
# CHANNEL-AGNOSTIC CONVERSATION HANDLER
# Takes a `send` and `typing` function so it works for both
# Telegram and WhatsApp without duplicating logic.
# ─────────────────────────────────────────────────────────────

def handle_user_message(
        *,
        session_key: str,  # e.g. "tg:12345" or "wa:919XXXXXXXXX"
        user_id,  # int chat_id (telegram) or str phone (whatsapp)
        text: str,
        send,  # function(user_id, text)
        typing,  # function(user_id)
):
    text = (text or "").strip()

    # ── 1. /start or greeting always resets the session ──────
    if text == "/start" or GREETING_PATTERN.match(text):
        user_sessions[session_key] = {"step": "name", "data": {}}
        send(user_id, STEP_PROMPTS["name"])
        return

    # ── 2. /today → daily forecast (needs a cached Kundli) ───
    if text.lower() in ("/today", "today", "rashifal", "forecast"):
        if session_key not in user_kundli_cache:
            send(user_id,
                 "🌟 I don't have your birth chart yet!\n\n"
                 "Please type *Hi* (or /start) first to generate your Kundli, "
                 "then send *today* for your daily forecast. 🙏")
            return

        typing(user_id)
        cached = user_kundli_cache[session_key]
        try:
            forecast_messages = generate_daily_forecast(
                cached["kundli"],
                name=cached.get("name", ""),
                gender=cached.get("gender", ""),
            )
            for msg in forecast_messages:
                send(user_id, msg)
        except Exception as e:
            import traceback
            print(f"[forecast error] {e}\n{traceback.format_exc()}")
            send(user_id, "❌ Error generating forecast. Try sending *Hi* again.")
        return

    # ── 3. Mid-onboarding → run the step machine ─────────────
    if session_key in user_sessions:
        session = user_sessions[session_key]
        step = session["step"]

        if step == "name":
            if len(text) < 2:
                send(user_id, "❗ Please enter a valid name.")
                return
            session["data"]["name"] = text.title()
            session["step"] = "gender"
            send(user_id, STEP_PROMPTS["gender"])

        elif step == "gender":
            g = text.lower()
            if g not in ("male", "female", "other"):
                send(user_id, "❗ Please reply with Male, Female, or Other.")
                return
            session["data"]["gender"] = text.title()
            session["step"] = "dob"
            send(user_id, STEP_PROMPTS["dob"])

        elif step == "dob":
            if not re.match(r"^\d{2}-\d{2}-\d{4}$", text):
                send(user_id, "❗ Invalid format. Please use DD-MM-YYYY.\nExample: 15-08-1995")
                return
            session["data"]["dob"] = text
            session["step"] = "time"
            send(user_id, STEP_PROMPTS["time"])

        elif step == "time":
            if not re.match(r"^\d{1,2}\.\d{2}$", text):
                send(user_id, "❗ Invalid format. Please use HH.MM.\nExample: 14.30")
                return
            session["data"]["birth_time"] = text
            session["step"] = "city"
            send(user_id, STEP_PROMPTS["city"])

        elif step == "city":
            typing(user_id)
            coords = city_to_latlon(text)
            if not coords:
                send(user_id,
                     "❗ Couldn't find that city. Please try again with more detail.\n"
                     "Example: Pune, India or New York, USA")
                return

            lat, lon = coords
            session["data"]["city"] = text.title()
            session["data"]["lat"] = lat
            session["data"]["lon"] = lon
            session["step"] = "processing"

            d = session["data"]
            send(user_id,
                 f"✅ *Details Confirmed:*\n\n"
                 f"👤 Name: {d['name']}\n"
                 f"👤 Gender: {d['gender']}\n"
                 f"📅 DOB: {d['dob']}\n"
                 f"⏰ Time: {d['birth_time']} IST\n"
                 f"📍 City: {d['city']}\n"
                 f"🌐 Coordinates: {round(lat, 4)}°N, {round(lon, 4)}°E\n\n"
                 f"⏳ _Calculating your Kundli... please wait_")
            typing(user_id)

            try:
                result = generate_kundli(
                    name=d["name"],
                    date_str=d["dob"],
                    birth_time=d["birth_time"],
                    lat=d["lat"],
                    lon=d["lon"],
                )
                user_kundli_cache[session_key] = {
                    "kundli": result,
                    "name": d["name"],
                    "gender": d["gender"],
                }
                messages = fmt_kundli(result, d["name"], d["gender"])
                for msg in messages:
                    send(user_id, msg)

                send(user_id,
                     "🌅 *Your Kundli is ready!*\n\n"
                     "Send *today* anytime to get your detailed daily forecast — "
                     "family, love, health, career, finances, and more! 🔱\n\n"
                     "Or just *ask me anything* about your chart — career, marriage, "
                     "money, health... 💬")
            except Exception as e:
                import traceback
                print(f"[kundli error] {e}\n{traceback.format_exc()}")
                send(user_id, "❌ Error generating Kundli. Please send *Hi* to try again.")

            del user_sessions[session_key]

        return  # an onboarding step was handled

    # ── 4. Kundli already built → ANY message is a question ──
    if session_key in user_kundli_cache:
        typing(user_id)
        from question_router import answer_question
        cached = user_kundli_cache[session_key]

        # optional "ask " / "/ask " prefix, but no longer required
        low = text.lower()
        if low.startswith("/ask") or low.startswith("ask "):
            question = text[4:].strip()
        else:
            question = text

        if not question:
            send(user_id, "Please type your question — e.g. *When will I get married?* 🙏")
            return

        reply = answer_question(
            question,
            cached["kundli"],
            cached.get("name", ""),
            cached.get("gender", ""),
        )
        send(user_id, reply)
        return

    # ── 5. Brand-new user, nothing yet → prompt to start ─────
    send(user_id,
         "👋 *Welcome to Hora!*\n\n"
         "Send *Hi* (or /start) to generate your personalised Kundli 🔱\n"
         "Once done, send *today* anytime for your Daily Forecast 🌅")


# ─────────────────────────────────────────────────────────────
# FastAPI routes
# ─────────────────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "Astrology API is running"}


# ─────────────────────────────────────────────────────────────
# TELEGRAM WEBHOOK (unchanged behaviour)
# ─────────────────────────────────────────────────────────────

@app.post("/webhook/astro123")
async def telegram_webhook(req: Request):
    data = await req.json()
    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text    = message.get("text", "").strip()

    handle_user_message(
        session_key = f"tg:{chat_id}",
        user_id     = chat_id,
        text        = text,
        send        = tg_send_message,
        typing      = tg_send_typing,
    )
    return {"ok": True}


# ─────────────────────────────────────────────────────────────
# WHATSAPP WEBHOOK
# Meta requires:
#   • GET  /webhook/whatsapp → respond with hub.challenge if verify token matches
#   • POST /webhook/whatsapp → receive message events
# ─────────────────────────────────────────────────────────────

@app.get("/webhook/whatsapp")
async def whatsapp_verify(
    hub_mode:         str | None = Query(None, alias="hub.mode"),
    hub_challenge:    str | None = Query(None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
):
    """
    Webhook verification handshake. Meta hits this URL once when you save
    the webhook in the Developer Dashboard. We must echo `hub.challenge` back
    as plain text if the verify token matches.
    """
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge or "", status_code=200)
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(req: Request):
    """
    Receive incoming WhatsApp messages.

    Payload shape (simplified):
    {
      "object": "whatsapp_business_account",
      "entry": [{
        "changes": [{
          "value": {
            "messages": [{
              "from":      "919XXXXXXXXX",
              "id":        "wamid.xxx",
              "type":      "text",
              "text":      {"body": "Hi"}
            }],
            "contacts": [{"profile": {"name": "User"}, "wa_id": "919XXXXXXXXX"}]
          }
        }]
      }]
    }
    """
    try:
        data = await req.json()
    except Exception:
        return {"status": "ignored"}

    # Always 200-OK quickly so Meta doesn't retry-storm us.
    if data.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])
            if not messages:
                # Could be a status update (delivered / read) — ignore for now
                continue

            for msg in messages:
                from_number = msg.get("from")          # e.g. "919XXXXXXXXX"
                msg_id      = msg.get("id")
                msg_type    = msg.get("type")

                # Mark read for nicer UX
                if msg_id:
                    wa_mark_read(msg_id)

                # Only handle plain text for now
                if msg_type != "text":
                    wa_send_message(
                        from_number,
                        "Please send a text message. Send *Hi* to start your Kundli."
                    )
                    continue

                text = msg.get("text", {}).get("body", "").strip()

                handle_user_message(
                    session_key = f"wa:{from_number}",
                    user_id     = from_number,
                    text        = text,
                    send        = wa_send_message,
                    typing      = wa_send_typing,
                )

    return {"status": "ok"}