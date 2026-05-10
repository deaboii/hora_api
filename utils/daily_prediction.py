"""
daily_prediction.py
--------------------
Generates a personalised daily transit prediction message for a user.

Called by the morning cron job. Uses the user's natal Moon sign and Lagna
from the database, calculates today's transits, and returns a formatted
Telegram message string.
"""

from __future__ import annotations

from datetime import datetime, timezone
import swisseph as swe
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
swe.set_ephe_path(BASE_DIR)

from utils.config import signs, nakshatras

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

SIGN_INDEX = {sign: i for i, sign in enumerate(signs)}

PLANET_IDS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
    "Rahu": swe.TRUE_NODE,
}

PLANET_ICONS = {
    "Sun": "☀️", "Moon": "🌙", "Mercury": "💚", "Venus": "⚪",
    "Mars": "🔴", "Jupiter": "🟡", "Saturn": "🪐",
    "Rahu": "🐉", "Ketu": "☄️",
}

# Classical transit effects from natal Moon (house → description, is_good)
MOON_TRANSIT = {
    1: ("Your body and mind need rest. Health sensitive — avoid overexertion.", False),
    2: ("Watch finances carefully today. Family interactions may feel strained.", False),
    3: ("Great day for courage, short travel, communication and networking.", True),
    4: ("Emotional turbulence at home. Be patient with family members.", False),
    5: ("Avoid speculation and risky decisions. Children may need attention.", False),
    6: ("Excellent for defeating obstacles and competition. Health improves.", True),
    7: ("Relationships need attention. Possible travel or partnership matters.", False),
    8: ("Keep a low profile. Hidden challenges may surface. Stay cautious.", False),
    9: ("Fortune favours you today. Spiritual activities bring deep benefit.", True),
    10: ("Career matters highlighted. Recognition and success likely at work.", True),
    11: ("Gains and income opportunities. Wishes have a good chance of fulfilment.", True),
    12: ("Expenditure likely. Good for spiritual retreat and inner reflection.", False),
}

# Key planet-specific predictions based on house from Moon
PLANET_PREDICTIONS = {
    "Jupiter": {
        1: "Jupiter energises your personality — a day of wisdom and optimism.",
        2: "Financial gains through wise decisions. Speak with authority.",
        3: "Sibling relationships blessed. Good for writing and learning.",
        4: "Home life harmonious. Mother's health improves. Inner peace.",
        5: "Creativity and romance flourish. Children bring joy.",
        6: "Health and service sector favoured. Overcome enemies with grace.",
        7: "Partnerships and marriage highly blessed. Great for negotiations.",
        8: "Hidden knowledge surfaces. Research and occult studies rewarding.",
        9: "Spiritual expansion. Long-distance travel favoured. Guru's grace.",
        10: "Career peak. Promotions and recognition are on the horizon.",
        11: "Income and social network expand. Long-held desires fulfilled.",
        12: "Expenses for a good cause. Spiritual retreat or foreign travel.",
    },
    "Saturn": {
        1: "Discipline required. Slow down, focus on health and routine.",
        2: "Curb spending. Delays in financial matters. Be patient.",
        3: "Hard work in communication pays off slowly but surely.",
        4: "Domestic responsibilities heavy. Property matters need care.",
        5: "Creative blocks possible. Avoid gambling or speculation.",
        6: "Saturn here gives endurance to overcome long-standing obstacles.",
        7: "Relationship responsibilities increase. Patience with partner.",
        8: "Deep karmic lessons. Hidden matters come to light slowly.",
        9: "Dharmic duties call. Long journeys possible but with effort.",
        10: "Career demands discipline. Hard work now will pay off later.",
        11: "Slow but steady gains. Long-term goals need structured effort.",
        12: "Spiritual discipline recommended. Manage expenditures carefully.",
    },
    "Mars": {
        1: "High energy and drive. Channel it productively to avoid conflicts.",
        2: "Bold financial moves possible. Avoid impulsive spending.",
        3: "Courageous action in communication. Good for sports and travel.",
        4: "Tension at home. Avoid arguments with family members.",
        5: "Passionate but impulsive in romance. Think before acting.",
        6: "Excellent for defeating enemies and overcoming health issues.",
        7: "Conflict in relationships possible. Avoid confrontations.",
        8: "Investigate hidden matters. Transformation through boldness.",
        9: "Adventurous spiritual or physical journeys. Be bold.",
        10: "Career drive is high. Take initiative at work.",
        11: "Energetic pursuit of goals and income. Good for networking.",
        12: "Suppress aggression. Avoid hidden enemies and legal troubles.",
    },
    "Venus": {
        1: "Charm and beauty are enhanced. Social life sparkles.",
        2: "Financial gains through art, beauty, or luxury items.",
        3: "Creative writing and artistic pursuits rewarded.",
        4: "Home beautification. Harmony with mother and family.",
        5: "Romance and creativity peak. Wonderful for love life.",
        6: "Diplomatic resolution of conflicts. Health care through beauty.",
        7: "Marriage and partnerships highly blessed. Romance in the air.",
        8: "Deep intimacy and shared resources. Mystical experiences.",
        9: "Aesthetic travel and philosophical pursuits rewarded.",
        10: "Career in arts, beauty, or entertainment is favoured.",
        11: "Social gains and romantic fulfilment. Income through arts.",
        12: "Secret pleasures and private romance. Spiritual aesthetics.",
    },
}

NATURAL_BENEFICS = {"Jupiter", "Venus", "Mercury", "Moon"}
NATURAL_MALEFICS = {"Sun", "Mars", "Saturn", "Rahu", "Ketu"}

# Sade Sati / Dhaiya check
SADE_SATI_HOUSES = {12, 1, 2}
DHAIYA_HOUSES = {4, 8}


# ──────────────────────────────────────────────────────────────────────────────
# Core helpers
# ──────────────────────────────────────────────────────────────────────────────

def _today_jd() -> float:
    now = datetime.now(timezone.utc)
    return swe.julday(now.year, now.month, now.day, now.hour + now.minute / 60.0)


def _get_transit_positions() -> dict[str, dict]:
    """Return today's sidereal positions for all planets."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    jd = _today_jd()
    positions = {}

    for name, pid in PLANET_IDS.items():
        lon = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
        sign_idx = int(lon // 30)
        nak_idx = int(lon // 13.3333333) % 27
        degree_in_nak = lon % 13.3333333
        pada = int(degree_in_nak // 3.3333333) + 1
        positions[name] = {
            "longitude": round(lon, 4),
            "sign": signs[sign_idx],
            "degree": round(lon % 30, 2),
            "nakshatra": nakshatras[nak_idx],
            "pada": pada,
        }

    # Add Ketu as 180° from Rahu
    rahu_lon = positions["Rahu"]["longitude"]
    ketu_lon = (rahu_lon + 180.0) % 360.0
    sign_idx = int(ketu_lon // 30)
    nak_idx = int(ketu_lon // 13.3333333) % 27
    deg_nak = ketu_lon % 13.3333333
    positions["Ketu"] = {
        "longitude": round(ketu_lon, 4),
        "sign": signs[sign_idx],
        "degree": round(ketu_lon % 30, 2),
        "nakshatra": nakshatras[nak_idx],
        "pada": int(deg_nak // 3.3333333) + 1,
    }
    return positions


def _house_from(ref_sign: str, transit_sign: str) -> int:
    return ((SIGN_INDEX[transit_sign] - SIGN_INDEX[ref_sign]) % 12) + 1


def _overall_day_score(positions: dict, moon_sign: str, lagna: str) -> tuple[int, str]:
    """
    Score the day from -5 to +5 based on key planet transits from Moon.
    Returns (score, label).
    """
    score = 0

    # Jupiter and Venus from Moon — strong benefic weight
    jup_house = _house_from(moon_sign, positions["Jupiter"]["sign"])
    ven_house = _house_from(moon_sign, positions["Venus"]["sign"])
    if jup_house in {1, 4, 7, 10}:  # Kendra from Moon
        score += 2
    if jup_house in {3, 6, 10, 11}:
        score += 1
    if ven_house in {1, 5, 9, 11}:
        score += 1

    # Moon's own transit house
    moon_house = _house_from(moon_sign, positions["Moon"]["sign"])
    effect, is_good = MOON_TRANSIT.get(moon_house, ("", True))
    score += 2 if is_good else -1

    # Saturn and Mars malefic check
    sat_house = _house_from(moon_sign, positions["Saturn"]["sign"])
    mars_house = _house_from(moon_sign, positions["Mars"]["sign"])
    if sat_house in {1, 4, 8, 12}:
        score -= 1
    if mars_house in {1, 4, 8, 12}:
        score -= 1

    # Sade Sati
    if sat_house in SADE_SATI_HOUSES:
        score -= 2

    score = max(-5, min(5, score))

    if score >= 3:
        label = "🌟 Excellent Day"
    elif score >= 1:
        label = "✅ Good Day"
    elif score == 0:
        label = "⚖️ Mixed Day"
    elif score >= -2:
        label = "⚠️ Challenging Day"
    else:
        label = "🔴 Difficult Day — Stay Cautious"

    return score, label


# ──────────────────────────────────────────────────────────────────────────────
# Main prediction builder
# ──────────────────────────────────────────────────────────────────────────────

def generate_daily_prediction(user: dict) -> str:
    """
    Build the full daily prediction message for one user.

    user dict (from DB): name, moon_sign, lagna, current_mahadasha, gender
    Returns a Telegram-formatted string.
    """
    name = user.get("name", "Friend")
    moon_sign = user.get("moon_sign")
    lagna = user.get("lagna")
    mahadasha = user.get("current_mahadasha", "—")
    gender = user.get("gender", "")

    if not moon_sign or not lagna:
        return (
            f"🌅 Good morning, *{name}*!\n\n"
            "⚠️ We don't have your complete birth details yet. "
            "Please type /start to complete your Kundli profile and get personalised daily predictions."
        )

    positions = _get_transit_positions()
    today_str = datetime.now().strftime("%A, %d %B %Y")
    score, day_label = _overall_day_score(positions, moon_sign, lagna)

    gender_icon = "♂️" if gender.lower() == "male" else "♀️" if gender.lower() == "female" else "✨"

    lines = []

    # ── Header ──────────────────────────────────────────────────────────────
    lines.append(
        f"🌅 *Good Morning, {name}* {gender_icon}\n"
        f"📅 _{today_str}_\n\n"
        f"🔱 *Your Daily Cosmic Forecast*\n"
        f"{'─' * 28}\n"
        f"🌙 *Moon Sign (Rashi):* {moon_sign}\n"
        f"⬆️ *Lagna:* {lagna}\n"
        f"⏳ *Running Mahadasha:* {mahadasha}\n"
    )

    # ── Day rating ───────────────────────────────────────────────────────────
    lines.append(f"\n*Today's Energy: {day_label}*")

    # ── Moon transit (most important for daily) ──────────────────────────────
    moon_house = _house_from(moon_sign, positions["Moon"]["sign"])
    moon_effect, moon_good = MOON_TRANSIT.get(moon_house, ("Neutral day.", True))
    moon_icon = "✅" if moon_good else "⚠️"
    lines.append(
        f"\n🌙 *Transiting Moon* — {positions['Moon']['sign']} "
        f"({positions['Moon']['degree']}° {positions['Moon']['nakshatra']} Pada {positions['Moon']['pada']})\n"
        f"   House {moon_house} from your Moon Sign\n"
        f"   {moon_icon} {moon_effect}"
    )

    # ── Key planet predictions ───────────────────────────────────────────────
    KEY_PLANETS = ["Jupiter", "Saturn", "Mars", "Venus"]
    lines.append(f"\n{'─' * 28}\n🪐 *Key Planet Influences Today*\n")

    for planet in KEY_PLANETS:
        pos = positions[planet]
        house = _house_from(moon_sign, pos["sign"])
        icon = PLANET_ICONS.get(planet, "•")
        pred = PLANET_PREDICTIONS.get(planet, {}).get(house, "Neutral influence today.")
        qualifier = "✅" if planet in NATURAL_BENEFICS else "⚠️"
        lines.append(
            f"{icon} *{planet}* in {pos['sign']} (House {house} from Moon)\n"
            f"   {qualifier} {pred}\n"
        )

    # ── Sade Sati / Dhaiya alert ─────────────────────────────────────────────
    sat_house = _house_from(moon_sign, positions["Saturn"]["sign"])
    if sat_house in SADE_SATI_HOUSES:
        phase_map = {12: "Rising Phase", 1: "Peak Phase", 2: "Setting Phase"}
        lines.append(
            f"🚨 *Sade Sati Alert — {phase_map[sat_house]}*\n"
            "Saturn is transiting close to your natal Moon. "
            "This is a karmic period of transformation. Stay grounded, be patient, and do Saturn remedies.\n"
        )
    elif sat_house in DHAIYA_HOUSES:
        lines.append(
            f"⚠️ *Dhaiya (Kantaka Shani) Active*\n"
            f"Saturn in house {sat_house} from your Moon. "
            "Obstacles in career or sudden disruptions possible. Stay disciplined.\n"
        )

    # ── Today's planet positions snapshot ───────────────────────────────────
    lines.append(f"{'─' * 28}\n🌍 *Today's Planet Positions*\n")
    for pname in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"]:
        pos = positions.get(pname, {})
        icon = PLANET_ICONS.get(pname, "•")
        h = _house_from(moon_sign, pos["sign"]) if pos else "—"
        lines.append(f"  {icon} *{pname}*: {pos.get('sign', '—')} {pos.get('degree', '—')}° | House {h}")

    # ── Auspicious timings (Choghadiya — simplified) ─────────────────────────
    lines.append(
        f"\n{'─' * 28}\n"
        f"⏰ *Auspicious Timings Today (IST)*\n"
        f"  🟢 Morning: 06:00 – 07:30 (Brahma Muhurta)\n"
        f"  🟢 Forenoon: 10:30 – 12:00\n"
        f"  🟡 Avoid: 12:00 – 01:30 (Kuthu Muhurta)\n"
        f"  🟢 Evening: 04:30 – 06:00\n"
    )

    # ── Today's tip ──────────────────────────────────────────────────────────
    DAILY_TIPS = [
        "🙏 Chant your Mahadasha lord's mantra 108 times today.",
        "💧 Offer water to the Sun at sunrise for vitality.",
        "🪔 Light a ghee lamp in the evening for prosperity.",
        "🌿 Donate green items today if Mercury is your lagna lord.",
        "📿 Carry a Rudraksha mala for protection during the day.",
        "🌸 Offer flowers to your Ishta Devata for inner peace.",
        "🍚 Feed crows or birds in the morning for ancestral blessings.",
    ]
    import hashlib
    tip_index = int(hashlib.md5(today_str.encode()).hexdigest(), 16) % len(DAILY_TIPS)
    lines.append(f"💡 *Today's Vedic Tip*\n{DAILY_TIPS[tip_index]}\n")

    # ── Footer ───────────────────────────────────────────────────────────────
    lines.append(
        f"{'─' * 28}\n"
        f"_🔱 Hora Astrology · Daily Forecast_\n"
        f"_Type /start to refresh your Kundli_"
    )

    return "\n".join(lines)
