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
from database import (
    init_db, upsert_user, get_user, set_phone_number,
    archive_user, update_profile,
)
app = FastAPI()


# ── Helpers shared across the handler ────────────────────────────
def _db_chat_id(session_key: str, user_id) -> int:
    """
    Map a session to the BIGINT primary key used in the DB.
    Telegram: the numeric chat_id. WhatsApp: a stable hash of the phone string.
    """
    if session_key.startswith("tg:"):
        return int(user_id)
    return abs(hash(str(user_id))) % (10 ** 15)


# Required fields for a profile to count as "complete" (skip onboarding).
_REQUIRED_FIELDS = ("name", "gender", "date_of_birth", "birth_time", "city")

def _profile_complete(row: dict) -> bool:
    return bool(row) and bool(row.get("kundli_json")) and all(
        row.get(f) for f in _REQUIRED_FIELDS
    )


# Map a user-facing "update X" keyword to (db_column, session_step, prompt).
UPDATE_FIELDS = {
    "name":   ("name",          "upd_name",   "✏️ Send your new *name*:"),
    "gender": ("gender",        "upd_gender", "✏️ Send your *gender* (Male / Female / Other):"),
    "dob":    ("date_of_birth", "upd_dob",    "✏️ Send your new *date of birth* (DD-MM-YYYY):"),
    "date":   ("date_of_birth", "upd_dob",    "✏️ Send your new *date of birth* (DD-MM-YYYY):"),
    "time":   ("birth_time",    "upd_time",   "✏️ Send your new *birth time* (HH.MM):"),
    "city":   ("city",          "upd_city",   "✏️ Send your new *city, country* of birth:"),
}


@app.on_event("startup")
def _startup_init_db():
    """Create the users table on boot (safe to run every start)."""
    init_db()
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


def tg_request_contact(chat_id: int):
    """Show a one-tap button to share the user's (verified) phone number."""
    keyboard = {
        "keyboard": [[{"text": "📱 Share my phone number", "request_contact": True}]],
        "one_time_keyboard": True,
        "resize_keyboard": True,
    }
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": ("📱 Want your reading saved to your number? Tap below to share it "
                     "(optional), or type */skip* to continue without it."),
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
        },
        timeout=10,
    )


def tg_remove_keyboard(chat_id: int, text: str):
    """Send a message and dismiss the custom keyboard."""
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"remove_keyboard": True},
        },
        timeout=10,
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

    # ── 0. /skip → dismiss the phone-share keyboard, continue ────
    if text.lower() in ("/skip", "skip") and session_key.startswith("tg:"):
        tg_remove_keyboard(user_id, "👍 No problem — continuing without your phone number.")
        return

    # ── 0b. /update [field] → edit a stored detail ───────────────
    low_all = text.lower().strip()
    if low_all == "/update" or low_all.startswith("update ") or low_all.startswith("/update "):
        cid = _db_chat_id(session_key, user_id)
        if not get_user(cid):
            send(user_id, "I don't have your details yet. Send *Hi* to set up your Kundli first. 🙏")
            return
        # Which field? e.g. "update city" / "/update dob"
        parts = low_all.replace("/update", "update").split()
        field_key = parts[1] if len(parts) > 1 else None
        if field_key in UPDATE_FIELDS:
            col, step, prompt = UPDATE_FIELDS[field_key]
            user_sessions[session_key] = {"step": step, "data": {}}
            send(user_id, prompt)
        else:
            send(user_id,
                 "✏️ *What would you like to update?*\n\n"
                 "Send one of:\n"
                 "  • `update name`\n  • `update gender`\n  • `update dob`\n"
                 "  • `update time`\n  • `update city`")
        return

    # ── 1. /start or greeting: returning users skip onboarding ───
    if text == "/start" or GREETING_PATTERN.match(text):
        cid = _db_chat_id(session_key, user_id)
        existing = get_user(cid)
        if _profile_complete(existing):
            # Restore the chart into cache so questions work immediately.
            user_kundli_cache[session_key] = {
                "kundli": existing["kundli_json"],
                "name":   existing.get("name", ""),
                "gender": existing.get("gender", ""),
            }
            user_sessions.pop(session_key, None)
            send(user_id,
                 f"🙏 *Welcome back, {existing.get('name','')}!*\n\n"
                 "Ask me anything about your chart, send *today* for your daily "
                 "forecast, or type *update* to change your birth details.")
            # Telegram: offer the phone button if we don't have it yet.
            if session_key.startswith("tg:") and not existing.get("phone_number"):
                tg_request_contact(user_id)
            return
        # New / incomplete → start onboarding.
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

                # Persist to the database so user data survives restarts.
                # Telegram users key on the numeric chat_id; WhatsApp users
                # have a phone-string id, so store that in phone_number and
                # use a hash as the BIGINT chat_id key.
                try:
                    if session_key.startswith("tg:"):
                        db_chat_id = int(user_id)
                        db_data = dict(d)
                    else:  # "wa:" — phone number id
                        db_chat_id = abs(hash(str(user_id))) % (10 ** 15)
                        db_data = dict(d)
                        db_data["phone_number"] = str(user_id)
                    upsert_user(db_chat_id, db_data, result)
                except Exception as e:
                    import traceback
                    print(f"[db save error] {e}\n{traceback.format_exc()}")

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

        # ── /update handlers ───────────────────────────────────
        elif step in ("upd_name", "upd_gender", "upd_dob", "upd_time", "upd_city"):
            cid = _db_chat_id(session_key, user_id)
            row = get_user(cid)
            if not row:
                send(user_id, "Couldn't find your record. Send *Hi* to set up again. 🙏")
                user_sessions.pop(session_key, None)
                return

            new_val = text.strip()

            # Validate per field.
            if step == "upd_name":
                if len(new_val) < 2:
                    send(user_id, "❗ Please enter a valid name."); return
                col, value, chart_change = "name", new_val.title(), False

            elif step == "upd_gender":
                if new_val.lower() not in ("male", "female", "other"):
                    send(user_id, "❗ Please reply Male, Female, or Other."); return
                col, value, chart_change = "gender", new_val.title(), False

            elif step == "upd_dob":
                if not re.match(r"^\d{2}-\d{2}-\d{4}$", new_val):
                    send(user_id, "❗ Use DD-MM-YYYY.\nExample: 15-08-1995"); return
                col, value, chart_change = "date_of_birth", new_val, True

            elif step == "upd_time":
                if not re.match(r"^\d{1,2}\.\d{2}$", new_val):
                    send(user_id, "❗ Use HH.MM.\nExample: 14.30"); return
                col, value, chart_change = "birth_time", new_val, True

            elif step == "upd_city":
                typing(user_id)
                coords = city_to_latlon(new_val)
                if not coords:
                    send(user_id, "❗ Couldn't find that city. Try 'Pune, India'."); return
                new_lat, new_lon = coords
                col, value, chart_change = "city", new_val.title(), True

            # Archive the OLD snapshot before changing anything.
            archive_user(cid, changed_field=col)

            if chart_change:
                # Rebuild birth data from the stored row, applying the new value.
                typing(user_id)
                dob   = value if col == "date_of_birth" else row.get("date_of_birth")
                btime = value if col == "birth_time"    else row.get("birth_time")
                if col == "city":
                    lat, lon, city = new_lat, new_lon, value
                else:
                    lat, lon, city = row.get("latitude"), row.get("longitude"), row.get("city")
                try:
                    result = generate_kundli(
                        name=row.get("name"), date_str=dob, birth_time=btime,
                        lat=lat, lon=lon,
                    )
                except Exception as e:
                    import traceback
                    print(f"[update recompute error] {e}\n{traceback.format_exc()}")
                    send(user_id, "❌ Couldn't recompute your chart. Please try again.")
                    user_sessions.pop(session_key, None)
                    return

                # If city changed, also persist the new lat/lon (separate columns).
                if col == "city":
                    update_profile(cid, "latitude", new_lat)
                    update_profile(cid, "longitude", new_lon)
                # Update the changed field + refreshed chart, and reset chat memory.
                update_profile(cid, col, value, kundli_result=result, reset_conversation=True)

                # Refresh the in-memory cache so the new chart is used right away.
                user_kundli_cache[session_key] = {
                    "kundli": result,
                    "name":   row.get("name", ""),
                    "gender": row.get("gender", ""),
                }
                send(user_id,
                     "✅ Updated! Your birth details changed, so I recalculated your "
                     "Kundli and started a fresh conversation. Ask away, or send *today*. 🔱")
            else:
                # Cosmetic change (name/gender) — chart & conversation untouched.
                update_profile(cid, col, value)
                if session_key in user_kundli_cache and col in ("name", "gender"):
                    user_kundli_cache[session_key][col] = value
                send(user_id, f"✅ Your *{col.replace('_',' ')}* has been updated.")

            user_sessions.pop(session_key, None)

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
            _db_chat_id(session_key, user_id),   # DB-backed conversation memory
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

    # ── Shared contact (phone number via the request_contact button) ──
    if "contact" in message:
        contact = message["contact"]
        phone   = contact.get("phone_number")
        shared  = contact.get("user_id")
        try:
            # Verified only if the shared contact IS this user (Telegram vouches).
            if phone and shared == chat_id:
                set_phone_number(_db_chat_id(f"tg:{chat_id}", chat_id), phone)
                tg_remove_keyboard(chat_id, "✅ Thanks! Your phone number is saved.")
            else:
                tg_remove_keyboard(
                    chat_id,
                    "⚠️ Please use the button to share *your own* number. Or type */skip*.",
                )
        except Exception as e:
            import traceback
            print(f"[contact handler error] {e}\n{traceback.format_exc()}")
        return {"ok": True}

    text = message.get("text", "").strip()

    try:
        handle_user_message(
            session_key = f"tg:{chat_id}",
            user_id     = chat_id,
            text        = text,
            send        = tg_send_message,
            typing      = tg_send_typing,
        )
    except Exception as e:
        import traceback
        print(f"[telegram handler error] {e}\n{traceback.format_exc()}")
        try:
            tg_send_message(chat_id, "⚠️ Something went wrong on my side. Please send *Hi* to restart.")
        except Exception:
            pass

    return {"ok": True}   # ALWAYS 200 -> Telegram never retry-storms


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

                try:
                    handle_user_message(
                        session_key = f"wa:{from_number}",
                        user_id     = from_number,
                        text        = text,
                        send        = wa_send_message,
                        typing      = wa_send_typing,
                    )
                except Exception as e:
                    import traceback
                    print(f"[whatsapp handler error] {e}\n{traceback.format_exc()}")
                    try:
                        wa_send_message(from_number, "⚠️ Something went wrong on my side. Please send *Hi* to restart.")
                    except Exception:
                        pass

    return {"status": "ok"}