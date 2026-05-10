from fastapi import FastAPI, Request, Header, HTTPException
import requests
import os

from routes.kundli import router as kundli_router
from services.kundli_service import generate_kundli
from database import init_db, upsert_user, get_all_users_admin, get_all_users_for_push, send_broadcast_message
from daily_prediction import generate_daily_prediction

app = FastAPI()
app.include_router(kundli_router)

@app.on_event("startup")
def on_startup():
    init_db()

BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
ADMIN_SECRET = os.getenv("ADMIN_SECRET", "changeme123")

# ─────────────────────────────────────────────────────────────
# Session store  {chat_id: {step, data{}}}
# Steps: name → gender → dob → time → city → phone → processing
# ─────────────────────────────────────────────────────────────
user_sessions: dict = {}

STEP_PROMPTS = {
    "name": (
        "🌟 *Welcome to Hora — Your Vedic Astrology Guide* 🌟\n\n"
        "I'll cast your personalised Kundli in just a few steps.\n\n"
        "✨ *Step 1 of 6* — Please enter your *full name*:"
    ),
    "gender": (
        "✅ Got it!\n\n"
        "👤 *Step 2 of 6* — What is your *gender*?\n\n"
        "Reply with:\n  • `Male`\n  • `Female`\n  • `Other`"
    ),
    "dob": (
        "✅ Noted!\n\n"
        "📅 *Step 3 of 6* — Enter your *date of birth*\n"
        "Format: `DD-MM-YYYY`\n"
        "Example: `15-08-1995`"
    ),
    "time": (
        "✅ Date saved!\n\n"
        "⏰ *Step 4 of 6* — Enter your *time of birth* (IST)\n"
        "Format: `HH.MM`\n"
        "Example: `14.30` for 2:30 PM\n\n"
        "_If unknown, use `06.00` as an estimate._"
    ),
    "city": (
        "✅ Time recorded!\n\n"
        "🗺️ *Step 5 of 6* — Enter your *city and country of birth*\n"
        "Example: `Mumbai, India` or `London, UK`"
    ),
    "phone": (
        "✅ Location found!\n\n"
        "📱 *Step 6 of 6* — Enter your *WhatsApp / phone number*\n"
        "Include country code. Example: `+91 98765 43210`\n\n"
        "_This is optional. Type `skip` to continue without it._"
    ),
}


# ─────────────────────────────────────────────────────────────
# Telegram helpers
# ─────────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    max_len = 4000
    for chunk in [text[i:i+max_len] for i in range(0, len(text), max_len)]:
        requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": chunk, "parse_mode": parse_mode},
            timeout=10,
        )

def send_typing(chat_id: int):
    requests.post(
        f"{TELEGRAM_API}/sendChatAction",
        json={"chat_id": chat_id, "action": "typing"},
        timeout=5,
    )

def city_to_latlon(city: str):
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": "HoraAstroBot/1.0"},
            timeout=8,
        )
        results = r.json()
        if results:
            return float(results[0]["lat"]), float(results[0]["lon"])
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────
# Kundli formatter
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
        messages.append(
            "⏳ *CURRENT DASHA PERIOD*\n" + "─" * 28 + "\n\n"
            f"🔷 *Mahadasha:* {current.get('mahadasha', '—')}\n"
            f"🔹 *Antardasha:* {current.get('antardasha', '—')}\n"
            f"▫️ *Pratyantar:* {current.get('pratyantar', '—')}\n"
            f"📆 *Pratyantar Ends:* {current.get('pratyantar_end', '—')}"
        )

    doshas = result.get("doshas", {})
    if doshas:
        DOSHA_ICONS = {
            "mangal_dosha": "🔥", "kaal_sarp_dosha": "🐍",
            "pitra_dosha": "👴", "guru_chandal_dosha": "⚡",
            "grahan_dosha": "🌑", "shani_dosha": "⚖️"
        }
        DOSHA_NAMES = {
            "mangal_dosha": "Mangal Dosha", "kaal_sarp_dosha": "Kaal Sarp Dosha",
            "pitra_dosha": "Pitra Dosha", "guru_chandal_dosha": "Guru Chandal Dosha",
            "grahan_dosha": "Grahan Dosha", "shani_dosha": "Shani Dosha"
        }
        dosha_lines = ["⚠️ *DOSHA ANALYSIS*\n" + "─" * 28]
        for key, val in doshas.items():
            icon     = DOSHA_ICONS.get(key, "•")
            name_d   = DOSHA_NAMES.get(key, key)
            present  = str(val.get("present", "False")).lower() == "true"
            severity = val.get("severity", "")
            status   = "✅ Not Present" if not present else f"⚠️ Present — {severity}"
            dosha_lines.append(f"{icon} *{name_d}:* {status}")
        messages.append("\n".join(dosha_lines))

    yogas = result.get("yogas", {})
    if yogas:
        yoga_lines = ["✨ *YOGA ANALYSIS*\n" + "─" * 28]
        pmh = yogas.get("panch_mahapurusha_yogas", {})
        yoga_lines.append(
            f"🏆 *Panch Mahapurusha:* {'✅ Present (' + str(pmh.get('count',0)) + ')' if str(pmh.get('present','False')).lower()=='true' else '❌ Absent'}"
        )
        raj = yogas.get("raj_yoga", {})
        yoga_lines.append(
            f"👑 *Raj Yoga:* {'✅ ' + raj.get('strength','') + ' (' + str(raj.get('count',0)) + ')' if str(raj.get('present','False')).lower()=='true' else '❌ Absent'}"
        )
        dhana = yogas.get("dhana_yoga", {})
        yoga_lines.append(
            f"💰 *Dhana Yoga:* {'✅ Present (' + str(dhana.get('count',0)) + ')' if str(dhana.get('present','False')).lower()=='true' else '❌ Absent'}"
        )
        gk = yogas.get("gaja_kesari_yoga", {})
        yoga_lines.append(
            f"🐘 *Gaja Kesari:* {'✅ ' + gk.get('jupiter_strength','') if (gk.get('present') is True or str(gk.get('present','False')).lower()=='true') else '❌ Absent'}"
        )
        kem = yogas.get("kemdrum_yoga", {})
        yoga_lines.append(
            f"🌑 *Kemdrum:* {'⚠️ Present' if str(kem.get('present','False')).lower()=='true' else '✅ Not Present'}"
        )
        vip = yogas.get("viparita_raja_yoga", {})
        yoga_lines.append(
            f"🔄 *Viparita Raja:* {'✅ Present (' + str(vip.get('count',0)) + ')' if str(vip.get('present','False')).lower()=='true' else '❌ Absent'}"
        )
        messages.append("\n".join(yoga_lines))

    marriage = result.get("marriage", {})
    if marriage:
        quality  = marriage.get("overall_quality", {})
        timing   = marriage.get("marriage_timing_dasha", {})
        delay    = marriage.get("delay_denial", {})
        curr_win = timing.get("current_running_period", {})
        m_lines  = ["💍 *MARRIAGE ANALYSIS*\n" + "─" * 28]
        m_lines.append(f"📊 *Overall:* {quality.get('overall_verdict','—')}")
        if delay.get("severity", "None") != "None":
            m_lines.append(f"⏳ *Delay Indicator:* {delay.get('severity')}")
        if curr_win:
            m_lines.append(
                f"\n🗓️ *Current Period:* {curr_win.get('verdict','—')}\n"
                f"   Maha: {curr_win.get('mahadasha',{}).get('planet','—')} | "
                f"Antar: {curr_win.get('antardasha',{}).get('planet','—')}"
            )
        windows = timing.get("near_future_marriage_windows", [])
        if windows:
            m_lines.append("\n📅 *Best Upcoming Windows:*")
            for w in windows[:2]:
                m_lines.append(
                    f"   {w.get('strength','')} — {w.get('mahadasha_planet')} MD / {w.get('antardasha_planet')} AD\n"
                    f"   ({w.get('antardasha_start')} → {w.get('antardasha_end')})"
                )
        messages.append("\n".join(m_lines))

    transits = result.get("transits", {})
    if transits:
        sade    = transits.get("sade_sati_dhaiya", {}).get("sade_sati", {})
        dhaiya  = transits.get("sade_sati_dhaiya", {}).get("dhaiya", {})
        notable = transits.get("notable_transits", [])
        t_lines = [f"🌍 *CURRENT TRANSITS*  _{transits.get('transit_date','')}_\n" + "─" * 28]
        t_lines.append(
            f"🌙 *Natal Moon:* {transits.get('natal_moon_sign','—')}\n"
            f"⬆️ *Natal Lagna:* {transits.get('natal_lagna_sign','—')}"
        )
        if sade.get("active"):
            t_lines.append(f"\n🪐 *SADE SATI ACTIVE* — {sade.get('phase','')}")
        if dhaiya.get("active"):
            t_lines.append("🪐 *DHAIYA ACTIVE*")
        if notable:
            t_lines.append("\n🔔 *Notable Transits:*")
            for n in notable[:4]:
                t_lines.append(f"  • {n['planet']} in {n['sign']}: {n['effect']}")
        messages.append("\n".join(t_lines))

    remedies = result.get("remedies", {})
    if remedies:
        r_lines = ["💎 *REMEDIES & GEMSTONES*\n" + "─" * 28]
        for s in remedies.get("gemstones", [])[:3]:
            r_lines.append(
                f"  • *{s['primary_stone']}* (for {s['planet']}) — {s['reason'][:60]}...\n"
                f"    Wear on {s['wear_day']} on {s['finger']}"
            )
        for dr in remedies.get("dosha_remedies", [])[:2]:
            r_lines.append(f"\n🙏 *{dr['title']}*")
            for tip in dr["remedies"][:2]:
                r_lines.append(f"  ▫️ {tip}")
        r_lines.append("\n_⚠️ Consult a Jyotishi before wearing gemstones._")
        messages.append("\n".join(r_lines))

    messages.append(
        "─" * 28 + "\n"
        "🔱 *Report by Hora Astrology*\n"
        "Type /start to generate a new Kundli ✨\n"
        "_You will receive a personalised daily forecast every morning 🌅_"
    )
    return messages


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "Hora Astrology API is running"}


# ── Admin: view all users ─────────────────────────────────────
@app.get("/admin/users")
def admin_get_users(x_admin_secret: str = Header(None)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    users = get_all_users_admin()
    return {"total": len(users), "users": users}


# ── Admin: send custom broadcast ─────────────────────────────
@app.post("/admin/broadcast")
async def admin_broadcast(req: Request, x_admin_secret: str = Header(None)):
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    body = await req.json()
    msg  = body.get("message", "").strip()
    if not msg:
        raise HTTPException(status_code=400, detail="message field required")
    return send_broadcast_message(BOT_TOKEN, msg)


# ── Daily push — called by Render Cron Job every morning ─────
@app.post("/cron/daily-push")
async def daily_push(req: Request, x_admin_secret: str = Header(None)):
    """
    Trigger the daily personalised forecast for all users.
    Set up a Render Cron Job to POST to this URL every day at 06:00 IST (00:30 UTC).
    Schedule: 30 0 * * *
    """
    if x_admin_secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    users   = get_all_users_for_push()
    success = failed = 0

    for user in users:
        try:
            message = generate_daily_prediction(user)
            r = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id":    user["chat_id"],
                    "text":       message,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            if r.json().get("ok"):
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Push failed for {user.get('chat_id')}: {e}")
            failed += 1

    return {
        "status":  "done",
        "total":   len(users),
        "success": success,
        "failed":  failed,
    }


# ── Telegram webhook ──────────────────────────────────────────
@app.post("/webhook/astro123")
async def telegram_webhook(req: Request):
    data = await req.json()

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text    = message.get("text", "").strip()

    # /start resets session
    if text == "/start":
        user_sessions[chat_id] = {"step": "name", "data": {}}
        send_message(chat_id, STEP_PROMPTS["name"])
        return {"ok": True}

    if chat_id not in user_sessions:
        send_message(chat_id, "👋 Type /start to begin your Kundli reading!")
        return {"ok": True}

    session = user_sessions[chat_id]
    step    = session["step"]

    # ── Step 1: Name ──────────────────────────────────────────
    if step == "name":
        if len(text) < 2:
            send_message(chat_id, "❗ Please enter a valid name.")
            return {"ok": True}
        session["data"]["name"] = text.title()
        session["step"] = "gender"
        send_message(chat_id, STEP_PROMPTS["gender"])

    # ── Step 2: Gender ────────────────────────────────────────
    elif step == "gender":
        if text.lower() not in ("male", "female", "other"):
            send_message(chat_id, "❗ Reply with `Male`, `Female`, or `Other`.")
            return {"ok": True}
        session["data"]["gender"] = text.title()
        session["step"] = "dob"
        send_message(chat_id, STEP_PROMPTS["dob"])

    # ── Step 3: Date of birth ─────────────────────────────────
    elif step == "dob":
        import re
        if not re.match(r"^\d{2}-\d{2}-\d{4}$", text):
            send_message(chat_id, "❗ Use format `DD-MM-YYYY`. Example: `15-08-1995`")
            return {"ok": True}
        session["data"]["dob"] = text
        session["step"] = "time"
        send_message(chat_id, STEP_PROMPTS["time"])

    # ── Step 4: Birth time ────────────────────────────────────
    elif step == "time":
        import re
        if not re.match(r"^\d{1,2}\.\d{2}$", text):
            send_message(chat_id, "❗ Use format `HH.MM`. Example: `14.30`")
            return {"ok": True}
        session["data"]["birth_time"] = text
        session["step"] = "city"
        send_message(chat_id, STEP_PROMPTS["city"])

    # ── Step 5: City ──────────────────────────────────────────
    elif step == "city":
        send_typing(chat_id)
        coords = city_to_latlon(text)
        if not coords:
            send_message(chat_id, "❗ Couldn't find that city. Try `Mumbai, India`.")
            return {"ok": True}
        lat, lon = coords
        session["data"]["city"] = text.title()
        session["data"]["lat"]  = lat
        session["data"]["lon"]  = lon
        session["step"] = "phone"
        send_message(chat_id, STEP_PROMPTS["phone"])

    # ── Step 6: Phone number (NEW) ────────────────────────────
    elif step == "phone":
        import re
        if text.lower() == "skip":
            session["data"]["phone_number"] = None
        else:
            # Accept formats like +91 98765 43210 or +919876543210
            cleaned = re.sub(r"[\s\-()]", "", text)
            if not re.match(r"^\+?\d{7,15}$", cleaned):
                send_message(
                    chat_id,
                    "❗ Please enter a valid phone number with country code.\n"
                    "Example: `+91 98765 43210`\n"
                    "Or type `skip` to continue."
                )
                return {"ok": True}
            session["data"]["phone_number"] = cleaned

        session["step"] = "processing"
        d = session["data"]

        send_message(
            chat_id,
            f"✅ *All Details Confirmed!*\n\n"
            f"👤 Name: {d['name']}\n"
            f"👤 Gender: {d['gender']}\n"
            f"📅 DOB: {d['dob']}\n"
            f"⏰ Time: {d['birth_time']} IST\n"
            f"📍 City: {d['city']}\n"
            f"📱 Phone: {d.get('phone_number') or 'Not provided'}\n\n"
            f"⏳ _Calculating your Kundli... please wait_ 🔱"
        )
        send_typing(chat_id)

        # ── Call Kundli API ───────────────────────────────────
        try:
            result = generate_kundli(
                name       = d["name"],
                date_str   = d["dob"],
                birth_time = d["birth_time"],
                lat        = d["lat"],
                lon        = d["lon"],
            )

            # Save to database (with phone number)
            upsert_user(chat_id, d, result)

            for msg in fmt_kundli(result, d["name"], d["gender"]):
                send_message(chat_id, msg)

        except Exception as e:
            send_message(chat_id, f"❌ *Error:* `{str(e)}`\n\nTry /start again.")

        del user_sessions[chat_id]

    return {"ok": True}