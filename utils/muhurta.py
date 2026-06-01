"""
muhurta.py
----------
"Right now" Vedic time calculations that genuinely change through the day,
giving minute-to-minute granularity that the slow planetary transits cannot.

Provides:
  1. Hora (planetary hour)   — the ruling planet of the current ~1-hour window,
                               with activity guidance. Changes every hora.
  2. Live Lagna (Ascendant)  — the sign rising RIGHT NOW. The rising degree
                               advances every ~4 minutes; the sign every ~2 h.
  3. Choghadiya              — the current auspicious/inauspicious muhurta band.
  4. Live Moon position      — exact sign, degree, nakshatra, pada this minute.

All wall-clock reasoning is done in IST. Julian Day for ephemeris is true UTC.

Sunrise/sunset are computed at the user's stored birth coordinates (the best
available proxy for their location) for TODAY's date.

Usage:
    from utils.muhurta import live_snapshot
    snap = live_snapshot(lat, lon)   # dict with hora / lagna / choghadiya / moon
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
import swisseph as swe
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
swe.set_ephe_path(BASE_DIR)

from utils.config import signs, nakshatras

IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(IST)


# ──────────────────────────────────────────────────────────────────────────────
# Chaldean planetary order — the backbone of both Hora and day-Choghadiya
# ──────────────────────────────────────────────────────────────────────────────

CHALDEAN = ["Sun", "Venus", "Mercury", "Moon", "Saturn", "Jupiter", "Mars"]

WEEKDAY_LORD = {
    0: "Moon",    # Monday
    1: "Mars",    # Tuesday
    2: "Mercury", # Wednesday
    3: "Jupiter", # Thursday
    4: "Venus",   # Friday
    5: "Saturn",  # Saturday
    6: "Sun",     # Sunday
}

PLANET_ICONS = {
    "Sun": "☀️", "Moon": "🌙", "Mars": "🔴", "Mercury": "💚",
    "Jupiter": "🟡", "Venus": "⚪", "Saturn": "🪐", "Rahu": "🐉", "Ketu": "☄️",
}

# What each planetary Hora supports / discourages
HORA_GUIDE = {
    "Sun":     {"quality": "Authority",   "good": "Government & official work, dealing with bosses, leadership, medicine, applying for positions of power.",
                "avoid":  "Subordinate or humble requests; Sun's pride can backfire."},
    "Moon":    {"quality": "Emotion & Flow", "good": "Travel, meeting people, public dealings, matters involving women/mother, water, fresh starts in relationships.",
                "avoid":  "Rigid commitments — the mind is changeable in a Moon hora."},
    "Mars":    {"quality": "Force",       "good": "Sports, surgery, property & land work, debt recovery, bold confrontation, anything needing courage.",
                "avoid":  "Signing peace deals or romantic overtures; Mars heats arguments."},
    "Mercury": {"quality": "Intellect",   "good": "Study, exams, writing, communication, trade & business, accounting, contracts, short trips.",
                "avoid":  "Purely emotional or devotional matters — Mercury is heady, not heartfelt."},
    "Jupiter": {"quality": "Wisdom & Luck", "good": "THE most auspicious hora — education, finance, investments, religious acts, marriage talks, any important beginning.",
                "avoid":  "Very little; Jupiter blesses almost everything."},
    "Venus":   {"quality": "Harmony & Beauty", "good": "Romance, marriage, arts & music, buying clothes/jewellery/vehicles, beauty, luxury, socialising.",
                "avoid":  "Harsh or austere tasks; Venus dislikes conflict and hardship."},
    "Saturn":  {"quality": "Labour & Discipline", "good": "Hard manual work, dealing with elders/servants/labourers, iron, oil, long-term planning, decluttering.",
                "avoid":  "NOT for new beginnings, marriage, or celebrations — Saturn delays and restricts."},
}

# Choghadiya names mapped from the Chaldean planet that rules them
PLANET_TO_CHOGHADIYA = {
    "Sun": "Udveg", "Venus": "Char", "Mercury": "Labh", "Moon": "Amrit",
    "Saturn": "Kaal", "Jupiter": "Shubh", "Mars": "Rog",
}

CHOGHADIYA_QUALITY = {
    "Amrit": ("Most Auspicious", "✅", "Nectar period — excellent for ALL important work and new beginnings."),
    "Shubh": ("Auspicious",      "✅", "Good for marriage, ceremonies, and beneficial activities."),
    "Labh":  ("Profit",          "✅", "Favours business, trade, education, and money matters."),
    "Char":  ("Movable",         "🟢", "Good for travel, movement, and routine activities."),
    "Udveg": ("Inauspicious",    "⚠️", "Anxiety-prone; avoid new starts. Government work is an exception."),
    "Rog":   ("Inauspicious",    "⚠️", "Disease/conflict energy — avoid health risks and disputes."),
    "Kaal":  ("Most Inauspicious","🔴", "Avoid all important new work; routine maintenance only."),
}

# Standard night-Choghadiya sequences (sunset → next sunrise), 8 bands per weekday.
# Day sequence is derived from the Chaldean order; night uses the classical table.
NIGHT_CHOGHADIYA = {
    6: ["Shubh", "Amrit", "Char", "Rog", "Kaal", "Labh", "Udveg", "Shubh"],  # Sunday
    0: ["Char", "Rog", "Kaal", "Labh", "Udveg", "Shubh", "Amrit", "Char"],   # Monday
    1: ["Kaal", "Labh", "Udveg", "Shubh", "Amrit", "Char", "Rog", "Kaal"],   # Tuesday
    2: ["Udveg", "Shubh", "Amrit", "Char", "Rog", "Kaal", "Labh", "Udveg"],  # Wednesday
    3: ["Amrit", "Char", "Rog", "Kaal", "Labh", "Udveg", "Shubh", "Amrit"],  # Thursday
    4: ["Rog", "Kaal", "Labh", "Udveg", "Shubh", "Amrit", "Char", "Rog"],    # Friday
    5: ["Labh", "Udveg", "Shubh", "Amrit", "Char", "Rog", "Kaal", "Labh"],   # Saturday
}


# ──────────────────────────────────────────────────────────────────────────────
# Sunrise / sunset
# ──────────────────────────────────────────────────────────────────────────────

def _jd_utc(dt_ist: datetime) -> float:
    dt_utc = dt_ist.astimezone(timezone.utc)
    return swe.julday(dt_utc.year, dt_utc.month, dt_utc.day,
                      dt_utc.hour + dt_utc.minute / 60.0 + dt_utc.second / 3600.0)


def _event_to_ist(jd_event: float) -> datetime:
    """Convert a Julian Day (UT) returned by rise_trans into an IST datetime."""
    y, m, d, h = swe.revjul(jd_event)
    # h is fractional hours UT
    hh = int(h)
    mm = int((h - hh) * 60)
    ss = int((((h - hh) * 60) - mm) * 60)
    dt_utc = datetime(y, m, d, hh, mm, min(ss, 59), tzinfo=timezone.utc)
    return dt_utc.astimezone(IST)


def sun_event(date_ist: datetime, lat: float, lon: float, rise: bool) -> datetime:
    """Sunrise or sunset (IST datetime) for the given IST calendar date."""
    flag = swe.CALC_RISE if rise else swe.CALC_SET
    geopos = (lon, lat, 0.0)
    # Search from local midnight of the target date. rise_trans returns the
    # FIRST event at/after the start instant, so this yields the same-date
    # sunrise and sunset for any longitude (start = 00:00 IST is well before
    # both events everywhere).
    midnight_ist = date_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    jd_start = _jd_utc(midnight_ist)
    res, tret = swe.rise_trans(jd_start, swe.SUN, flag, geopos)
    return _event_to_ist(tret[0])


# ──────────────────────────────────────────────────────────────────────────────
# Hora
# ──────────────────────────────────────────────────────────────────────────────

def current_hora(now: datetime, lat: float, lon: float) -> dict:
    """
    Determine the planetary Hora active right now.

    Day horas: sunrise→sunset split into 12 equal parts.
    Night horas: sunset→next sunrise split into 12 equal parts.
    Hora 1 (from sunrise) is ruled by the weekday lord; the rest follow the
    Chaldean order cyclically.
    """
    today = now.date()
    today_dt = datetime(today.year, today.month, today.day, tzinfo=IST)

    sunrise = sun_event(today_dt, lat, lon, rise=True)
    sunset = sun_event(today_dt, lat, lon, rise=False)

    if now < sunrise:
        # We are in the night that began at YESTERDAY's sunset.
        prev_dt = today_dt - timedelta(days=1)
        sunset = sun_event(prev_dt, lat, lon, rise=False)
        astro_weekday = prev_dt.weekday()
        seg_len = (sunrise - sunset) / 12.0
        idx = int((now - sunset) / seg_len)
        idx = max(0, min(11, idx))
        hora_number = 12 + idx + 1  # horas 13..24
        seg_start = sunset + seg_len * idx
    elif now < sunset:
        # Daytime.
        astro_weekday = today_dt.weekday()
        seg_len = (sunset - sunrise) / 12.0
        idx = int((now - sunrise) / seg_len)
        idx = max(0, min(11, idx))
        hora_number = idx + 1  # horas 1..12
        seg_start = sunrise + seg_len * idx
    else:
        # Night that begins at TODAY's sunset.
        tomorrow_dt = today_dt + timedelta(days=1)
        next_sunrise = sun_event(tomorrow_dt, lat, lon, rise=True)
        astro_weekday = today_dt.weekday()
        seg_len = (next_sunrise - sunset) / 12.0
        idx = int((now - sunset) / seg_len)
        idx = max(0, min(11, idx))
        hora_number = 12 + idx + 1
        seg_start = sunset + seg_len * idx

    seg_end = seg_start + seg_len

    day_lord = WEEKDAY_LORD[astro_weekday]
    start_index = CHALDEAN.index(day_lord)
    ruler = CHALDEAN[(start_index + (hora_number - 1)) % 7]

    guide = HORA_GUIDE[ruler]
    return {
        "planet": ruler,
        "icon": PLANET_ICONS.get(ruler, "⭐"),
        "hora_number": hora_number,
        "start": seg_start.strftime("%H:%M"),
        "end": seg_end.strftime("%H:%M"),
        "quality": guide["quality"],
        "good_for": guide["good"],
        "avoid": guide["avoid"],
    }


def next_jupiter_venus_hora(now: datetime, lat: float, lon: float, max_hours: int = 24):
    """
    Find the next Jupiter or Venus hora (the two most auspicious) starting from
    now, scanning up to `max_hours` ahead. Useful for 'best time today' advice.
    """
    cursor = now
    for _ in range(max_hours + 2):
        h = current_hora(cursor, lat, lon)
        if h["planet"] in ("Jupiter", "Venus") and h["start"] >= now.strftime("%H:%M"):
            return h
        # jump to the end of this hora
        end_h, end_m = map(int, h["end"].split(":"))
        nxt = cursor.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
        if nxt <= cursor:
            nxt = cursor + timedelta(hours=1)
        cursor = nxt + timedelta(minutes=1)
        if cursor - now > timedelta(hours=max_hours):
            break
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Choghadiya
# ──────────────────────────────────────────────────────────────────────────────

def current_choghadiya(now: datetime, lat: float, lon: float) -> dict:
    """Determine the current Choghadiya band (8 by day, 8 by night)."""
    today = now.date()
    today_dt = datetime(today.year, today.month, today.day, tzinfo=IST)
    sunrise = sun_event(today_dt, lat, lon, rise=True)
    sunset = sun_event(today_dt, lat, lon, rise=False)

    def day_sequence(weekday: int) -> list[str]:
        lord = WEEKDAY_LORD[weekday]
        start = CHALDEAN.index(lord)
        seq = [PLANET_TO_CHOGHADIYA[CHALDEAN[(start + i) % 7]] for i in range(8)]
        return seq

    if now < sunrise:
        prev_dt = today_dt - timedelta(days=1)
        sunset_prev = sun_event(prev_dt, lat, lon, rise=False)
        seq = NIGHT_CHOGHADIYA[prev_dt.weekday()]
        seg_len = (sunrise - sunset_prev) / 8.0
        idx = max(0, min(7, int((now - sunset_prev) / seg_len)))
        seg_start = sunset_prev + seg_len * idx
        period = "Night"
    elif now < sunset:
        seq = day_sequence(today_dt.weekday())
        seg_len = (sunset - sunrise) / 8.0
        idx = max(0, min(7, int((now - sunrise) / seg_len)))
        seg_start = sunrise + seg_len * idx
        period = "Day"
    else:
        tomorrow_dt = today_dt + timedelta(days=1)
        next_sunrise = sun_event(tomorrow_dt, lat, lon, rise=True)
        seq = NIGHT_CHOGHADIYA[today_dt.weekday()]
        seg_len = (next_sunrise - sunset) / 8.0
        idx = max(0, min(7, int((now - sunset) / seg_len)))
        seg_start = sunset + seg_len * idx
        period = "Night"

    name = seq[idx]
    seg_end = seg_start + seg_len
    label, icon, desc = CHOGHADIYA_QUALITY[name]
    return {
        "name": name,
        "period": period,
        "label": label,
        "icon": icon,
        "description": desc,
        "start": seg_start.strftime("%H:%M"),
        "end": seg_end.strftime("%H:%M"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Live Lagna (rising sign right now) + live Moon
# ──────────────────────────────────────────────────────────────────────────────

def _interpret(lon_deg: float) -> dict:
    si = int(lon_deg // 30)
    deg = lon_deg % 30
    ni = int(lon_deg // 13.3333333) % 27
    deg_nak = lon_deg % 13.3333333
    pada = int(deg_nak // 3.3333333) + 1
    return {
        "sign": signs[si],
        "degree": round(deg, 2),
        "nakshatra": nakshatras[ni],
        "pada": pada,
    }


def current_lagna(now: datetime, lat: float, lon: float) -> dict:
    """The Ascendant (Lagna) rising right now. Degree changes every ~4 minutes."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    jd = _jd_utc(now)
    _, ascmc = swe.houses_ex(jd, lat, lon, b'A', swe.FLG_SIDEREAL)
    info = _interpret(ascmc[0])
    info["longitude"] = round(ascmc[0], 4)
    return info


def current_moon(now: datetime) -> dict:
    """The Moon's exact position right now."""
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    jd = _jd_utc(now)
    lon = swe.calc_ut(jd, swe.MOON, swe.FLG_SIDEREAL)[0][0]
    info = _interpret(lon)
    info["longitude"] = round(lon, 4)
    return info


# ──────────────────────────────────────────────────────────────────────────────
# One-call snapshot
# ──────────────────────────────────────────────────────────────────────────────

def live_snapshot(lat: float | None, lon: float | None) -> dict:
    """
    Return a complete 'this moment' reading. Falls back to a default
    sunrise/sunset assumption if coordinates are missing.
    """
    now = _now_ist()

    # Fallback coordinates (central India) if none stored — keeps Hora working.
    if lat is None or lon is None:
        lat, lon = 21.0, 78.0

    try:
        hora = current_hora(now, lat, lon)
    except Exception as e:
        hora = {"error": str(e)}
    try:
        chogh = current_choghadiya(now, lat, lon)
    except Exception as e:
        chogh = {"error": str(e)}
    try:
        lagna = current_lagna(now, lat, lon)
    except Exception as e:
        lagna = {"error": str(e)}
    try:
        moon = current_moon(now)
    except Exception as e:
        moon = {"error": str(e)}

    return {
        "timestamp_ist": now.strftime("%d %b %Y, %H:%M IST"),
        "hora": hora,
        "choghadiya": chogh,
        "lagna": lagna,
        "moon": moon,
    }
