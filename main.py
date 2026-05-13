from fastapi import FastAPI, Request
import requests
import os

from routes.kundli import router as kundli_router
from services.kundli_service import generate_kundli
from services.daily_forecast import generate_daily_forecast

app = FastAPI()
app.include_router(kundli_router)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ─────────────────────────────────────────────────────────────
# In-memory session store  {chat_id: {step, data{}}}
# Steps: name → gender → dob → time → city → processing
# ─────────────────────────────────────────────────────────────
user_sessions: dict = {}
# Stores the last generated kundli per user for /today command
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
        "Reply with:\n  • `Male`\n  • `Female`\n  • `Other`"
    ),
    "dob": (
        "✅ Noted!\n\n"
        "📅 *Step 3 of 5* — Enter your *date of birth*\n"
        "Format: `DD-MM-YYYY`\n"
        "Example: `15-08-1995`"
    ),
    "time": (
        "✅ Date saved!\n\n"
        "⏰ *Step 4 of 5* — Enter your *time of birth* (IST)\n"
        "Format: `HH.MM`\n"
        "Example: `14.30` for 2:30 PM\n\n"
        "_If you don't know the exact time, use `06.00` as a rough estimate._"
    ),
    "city": (
        "✅ Time recorded!\n\n"
        "🗺️ *Step 5 of 5* — Enter your *city and country of birth*\n"
        "Example: `Mumbai, India` or `London, UK`"
    ),
}


# ─────────────────────────────────────────────────────────────
# Telegram helpers
# ─────────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str, parse_mode: str = "Markdown"):
    """Send a single Telegram message, splitting if > 4000 chars."""
    max_len = 4000
    chunks = [text[i:i+max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
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


# ─────────────────────────────────────────────────────────────
# City → lat/lon  (Nominatim, free, no key needed)
# ─────────────────────────────────────────────────────────────

def city_to_latlon(city: str) -> tuple[float, float] | None:
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
# Kundli result → formatted Telegram text
# ─────────────────────────────────────────────────────────────

def fmt_kundli(result: dict, name: str, gender: str) -> list[str]:
    """
    Return a list of formatted message strings, one per section.
    """
    messages = []
    det = result.get("details", {})

    # ── Header ──────────────────────────────────────────────
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

    # ── Planets ─────────────────────────────────────────────
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

    # ── Dasha ────────────────────────────────────────────────
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

    # ── Doshas ───────────────────────────────────────────────
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
            icon = DOSHA_ICONS.get(key, "•")
            name = DOSHA_NAMES.get(key, key)
            present = str(val.get("present", "False")).lower() == "true"
            severity = val.get("severity", "")
            status = f"✅ Not Present" if not present else f"⚠️ Present — {severity}"
            dosha_lines.append(f"{icon} *{name}:* {status}")
        messages.append("\n".join(dosha_lines))

    # ── Yogas ────────────────────────────────────────────────
    yogas = result.get("yogas", {})
    if yogas:
        yoga_lines = ["✨ *YOGA ANALYSIS*\n" + "─" * 28]

        pmh = yogas.get("panch_mahapurusha_yogas", {})
        if str(pmh.get("present", "False")).lower() == "true":
            yoga_lines.append(f"🏆 *Panch Mahapurusha Yogas:* ✅ Present ({pmh.get('count', 0)} yoga(s))")
        else:
            yoga_lines.append("🏆 *Panch Mahapurusha Yogas:* ❌ Absent")

        raj = yogas.get("raj_yoga", {})
        if str(raj.get("present", "False")).lower() == "true":
            yoga_lines.append(f"👑 *Raj Yoga:* ✅ Present — {raj.get('strength', '')} ({raj.get('count', 0)} combo(s))")
        else:
            yoga_lines.append("👑 *Raj Yoga:* ❌ Absent")

        dhana = yogas.get("dhana_yoga", {})
        if str(dhana.get("present", "False")).lower() == "true":
            yoga_lines.append(f"💰 *Dhana Yoga:* ✅ Present ({dhana.get('count', 0)} combo(s))")
        else:
            yoga_lines.append("💰 *Dhana Yoga:* ❌ Absent")

        gk = yogas.get("gaja_kesari_yoga", {})
        if gk.get("present") is True or str(gk.get("present", "False")).lower() == "true":
            yoga_lines.append(f"🐘 *Gaja Kesari Yoga:* ✅ Present — {gk.get('jupiter_strength', '')}")
        else:
            yoga_lines.append("🐘 *Gaja Kesari Yoga:* ❌ Absent")

        kem = yogas.get("kemdrum_yoga", {})
        if str(kem.get("present", "False")).lower() == "true":
            yoga_lines.append("🌑 *Kemdrum Yoga:* ⚠️ Present — Moon is isolated")
        else:
            yoga_lines.append("🌑 *Kemdrum Yoga:* ✅ Not Present")

        vip = yogas.get("viparita_raja_yoga", {})
        if str(vip.get("present", "False")).lower() == "true":
            yoga_lines.append(f"🔄 *Viparita Raja Yoga:* ✅ Present ({vip.get('count', 0)} combo(s))")
        else:
            yoga_lines.append("🔄 *Viparita Raja Yoga:* ❌ Absent")

        messages.append("\n".join(yoga_lines))

    # ── Marriage ─────────────────────────────────────────────
    marriage = result.get("marriage", {})
    if marriage:
        quality = marriage.get("overall_quality", {})
        timing = marriage.get("marriage_timing_dasha", {})
        delay = marriage.get("delay_denial", {})
        current_window = timing.get("current_running_period", {})

        marriage_lines = ["💍 *MARRIAGE ANALYSIS*\n" + "─" * 28]
        marriage_lines.append(f"📊 *Overall:* {quality.get('overall_verdict', '—')}")

        delay_severity = delay.get("severity", "None")
        if delay_severity != "None":
            marriage_lines.append(f"⏳ *Delay Indicator:* {delay_severity}")

        if current_window:
            marriage_lines.append(
                f"\n🗓️ *Current Period for Marriage:*\n"
                f"   {current_window.get('verdict', '—')}\n"
                f"   Maha: {current_window.get('mahadasha', {}).get('planet', '—')} | "
                f"Antar: {current_window.get('antardasha', {}).get('planet', '—')}"
            )

        windows = timing.get("near_future_marriage_windows", [])
        if windows:
            marriage_lines.append("\n📅 *Best Upcoming Marriage Windows:*")
            for w in windows[:2]:
                marriage_lines.append(
                    f"   {w.get('strength', '')} — {w.get('mahadasha_planet')} MD / "
                    f"{w.get('antardasha_planet')} AD\n"
                    f"   ({w.get('antardasha_start')} → {w.get('antardasha_end')})"
                )

        messages.append("\n".join(marriage_lines))

    # ── Transits ─────────────────────────────────────────────
    transits = result.get("transits", {})
    if transits:
        saturn_sp = transits.get("sade_sati_dhaiya", {})
        sade = saturn_sp.get("sade_sati", {})
        dhaiya = saturn_sp.get("dhaiya", {})
        notable = transits.get("notable_transits", [])

        transit_lines = [
            f"🌍 *CURRENT TRANSITS*  _{transits.get('transit_date', '')}_\n" + "─" * 28
        ]
        transit_lines.append(
            f"🌙 *Natal Moon Sign:* {transits.get('natal_moon_sign', '—')}\n"
            f"⬆️ *Natal Lagna:* {transits.get('natal_lagna_sign', '—')}"
        )

        if sade.get("active"):
            transit_lines.append(f"\n🪐 *SADE SATI ACTIVE* — {sade.get('phase', '')}")
        if dhaiya.get("active"):
            transit_lines.append(f"🪐 *DHAIYA ACTIVE* — Saturn in {saturn_sp.get('dhaiya', {}).get('saturn_house_from_moon', '—')}th from Moon")

        if notable:
            transit_lines.append("\n🔔 *Notable Transits:*")
            for n in notable[:4]:
                transit_lines.append(f"  • {n['planet']} in {n['sign']}: {n['effect']}")

        messages.append("\n".join(transit_lines))

    # ── Remedies (top picks) ──────────────────────────────────
    remedies = result.get("remedies", {})
    if remedies:
        stones = remedies.get("gemstones", [])
        dosha_rem = remedies.get("dosha_remedies", [])

        remedy_lines = ["💎 *REMEDIES & GEMSTONES*\n" + "─" * 28]

        if stones:
            remedy_lines.append("🔮 *Recommended Gemstones:*")
            for s in stones[:3]:
                remedy_lines.append(
                    f"  • *{s['primary_stone']}* (for {s['planet']}) — {s['reason'][:60]}...\n"
                    f"    Wear on {s['wear_day']} on {s['finger']}"
                )

        if dosha_rem:
            remedy_lines.append("\n🙏 *Dosha Remedies (Top Tips):*")
            for dr in dosha_rem[:2]:
                remedy_lines.append(f"  🔸 *{dr['title']}*")
                for tip in dr["remedies"][:2]:
                    remedy_lines.append(f"    ▫️ {tip}")

        remedy_lines.append(
            "\n_⚠️ Consult a qualified Jyotishi before wearing gemstones._"
        )
        messages.append("\n".join(remedy_lines))

    # ── Footer ───────────────────────────────────────────────
    messages.append(
        "─" * 28 + "\n"
        "🔱 *Report by Hora Astrology API*\n"
        "Type /start to generate a new Kundli ✨\n"
        "Type /today for your Daily Forecast 🌅"
    )

    return messages


# ─────────────────────────────────────────────────────────────
# FastAPI routes
# ─────────────────────────────────────────────────────────────

@app.api_route("/", methods=["GET", "HEAD"])
def home():
    return {"message": "Astrology API is running"}


@app.post("/webhook/astro123")
async def telegram_webhook(req: Request):
    data = await req.json()

    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text    = message.get("text", "").strip()

    # ── /start resets session ────────────────────────────────
    if text == "/start":
        user_sessions[chat_id] = {"step": "name", "data": {}}
        send_message(chat_id, STEP_PROMPTS["name"])
        return {"ok": True}

    # ── /today → daily forecast using cached kundli ──────────
    if text == "/today":
        if chat_id not in user_kundli_cache:
            send_message(
                chat_id,
                "🌟 I don't have your birth chart yet!\n\n"
                "Please type /start first to generate your Kundli, "
                "then use /today for your daily forecast. 🙏"
            )
            return {"ok": True}

        send_typing(chat_id)
        cached = user_kundli_cache[chat_id]
        try:
            forecast_messages = generate_daily_forecast(
                cached["kundli"],
                name=cached.get("name", ""),
                gender=cached.get("gender", ""),
            )
            for msg in forecast_messages:
                send_message(chat_id, msg)
        except Exception as e:
            send_message(chat_id, f"❌ Error generating forecast: `{str(e)}`\n\nTry /start again.")
        return {"ok": True}

    # ── No active session → prompt /start ────────────────────
    if chat_id not in user_sessions:
        send_message(
            chat_id,
            "👋 *Welcome to Hora!*\n\n"
            "Type /start to generate your personalised Kundli 🔱\n"
            "Once done, type /today anytime for your Daily Forecast 🌅"
        )
        return {"ok": True}

    session = user_sessions[chat_id]
    step    = session["step"]

    # ── Collect inputs step by step ──────────────────────────

    if step == "name":
        if len(text) < 2:
            send_message(chat_id, "❗ Please enter a valid name.")
            return {"ok": True}
        session["data"]["name"] = text.title()
        session["step"] = "gender"
        send_message(chat_id, STEP_PROMPTS["gender"])

    elif step == "gender":
        g = text.lower()
        if g not in ("male", "female", "other"):
            send_message(chat_id, "❗ Please reply with `Male`, `Female`, or `Other`.")
            return {"ok": True}
        session["data"]["gender"] = text.title()
        session["step"] = "dob"
        send_message(chat_id, STEP_PROMPTS["dob"])

    elif step == "dob":
        import re
        if not re.match(r"^\d{2}-\d{2}-\d{4}$", text):
            send_message(chat_id, "❗ Invalid format. Please use `DD-MM-YYYY`.\nExample: `15-08-1995`")
            return {"ok": True}
        session["data"]["dob"] = text
        session["step"] = "time"
        send_message(chat_id, STEP_PROMPTS["time"])

    elif step == "time":
        import re
        if not re.match(r"^\d{1,2}\.\d{2}$", text):
            send_message(chat_id, "❗ Invalid format. Please use `HH.MM`.\nExample: `14.30`")
            return {"ok": True}
        session["data"]["birth_time"] = text
        session["step"] = "city"
        send_message(chat_id, STEP_PROMPTS["city"])

    elif step == "city":
        send_typing(chat_id)
        coords = city_to_latlon(text)
        if not coords:
            send_message(
                chat_id,
                "❗ Couldn't find that city. Please try again with more detail.\n"
                "Example: `Pune, India` or `New York, USA`"
            )
            return {"ok": True}

        lat, lon = coords
        session["data"]["city"]  = text.title()
        session["data"]["lat"]   = lat
        session["data"]["lon"]   = lon
        session["step"] = "processing"

        d = session["data"]
        send_message(
            chat_id,
            f"✅ *Details Confirmed:*\n\n"
            f"👤 Name: {d['name']}\n"
            f"👤 Gender: {d['gender']}\n"
            f"📅 DOB: {d['dob']}\n"
            f"⏰ Time: {d['birth_time']} IST\n"
            f"📍 City: {d['city']}\n"
            f"🌐 Coordinates: {round(lat, 4)}°N, {round(lon, 4)}°E\n\n"
            f"⏳ _Calculating your Kundli... please wait_"
        )
        send_typing(chat_id)

        # ── Call Kundli API ──────────────────────────────────
        try:
            result = generate_kundli(
                name       = d["name"],
                date_str   = d["dob"],
                birth_time = d["birth_time"],
                lat        = d["lat"],
                lon        = d["lon"],
            )

            # Cache the kundli for /today command
            user_kundli_cache[chat_id] = {
                "kundli": result,
                "name":   d["name"],
                "gender": d["gender"],
            }

            messages = fmt_kundli(result, d["name"], d["gender"])
            for msg in messages:
                send_message(chat_id, msg)

            # Prompt user about /today
            send_message(
                chat_id,
                "🌅 *Your Kundli is ready!*\n\n"
                "Type /today anytime to get your detailed daily forecast — "
                "family, love, health, career, finances, and more! 🔱"
            )

        except Exception as e:
            send_message(
                chat_id,
                f"❌ *Error generating Kundli:*\n`{str(e)}`\n\nPlease try /start again."
            )

        del user_sessions[chat_id]

    return {"ok": True}
