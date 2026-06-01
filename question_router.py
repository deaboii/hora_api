"""
question_router.py
-------------------
Free-form astrology Q&A for the Hora bot, powered by the FREE Google Gemini API
(Google AI Studio), grounded in the deterministically-computed kundli.

Architecture (the professional pattern):
    user question + computed kundli facts
        -> safety guardrails (death / self-harm / medical / legal / financial)
        -> compact chart context built from final_structure
        -> Gemini writes the answer, grounded ONLY in the supplied facts
        -> if Gemini is unavailable (no key / quota hit / error) -> template fallback

The LLM never computes positions — it only interprets the facts your engine
already calculated (planets, houses, dashas, yogas, doshas, marriage analysis).

Setup:
    1. Get a free key at https://aistudio.google.com  (no credit card).
    2. On Render, add env var:  GEMINI_API_KEY = <your key>
       (optional)             GEMINI_MODEL   = gemini-2.5-flash
    3. requirements.txt already has `requests` — no new dependency.

Usage:
    from question_router import answer_question
    reply = answer_question(user_text, kundli_dict, name="Deepak", gender="Male")
"""

from __future__ import annotations

import os
import re
import requests

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# ──────────────────────────────────────────────────────────────────────────────
# 1. SAFETY GUARDRAILS
# ──────────────────────────────────────────────────────────────────────────────
# Two layers:
#   HARD  -> never call the LLM; return a fixed, safe response.
#            (death-timing predictions, and any sign of self-harm/distress)
#   SOFT  -> still answer via the LLM, but inject extra instructions telling it
#            to add the right disclaimer and avoid definitive claims.
# ──────────────────────────────────────────────────────────────────────────────

# Self-harm / distress — handled with care, NOT with an astrology reading.
_SELF_HARM = re.compile(
    r"\b(suicid|kill myself|killing myself|end my life|ending my life|"
    r"want to die|wanna die|don'?t want to live|no reason to live|"
    r"harm myself|hurt myself|self[\s-]?harm|cut myself|"
    r"jeena nahi|marna chahta|marna chahti|aatmhatya|आत्महत्या|मरना चाहता|जीना नहीं)\b",
    re.IGNORECASE,
)

# Death / longevity timing — we decline to predict and reframe positively.
_DEATH_TIMING = re.compile(
    r"\b(when (will|do) i die|how long (will|do) i live|"
    r"time of my death|date of my death|my death|when is my death|"
    r"kab ma?runga|kab marungi|kab maut|meri maut|kitne saal jiunga|"
    r"मेरी मृत्यु|कब मरूंगा|कब मरूँगी)\b",
    re.IGNORECASE,
)

# Soft categories -> answer, but with disclaimers.
_MEDICAL = re.compile(
    r"\b(disease|cancer|tumou?r|diagnos|illness|surgery|operation|"
    r"will i (be )?(cure|heal|recover|sick)|medical condition|mental illness|"
    r"bimari|bimaari|ilaaj|बीमारी)\b",
    re.IGNORECASE,
)
_LEGAL = re.compile(
    r"\b(court case|lawsuit|litigation|legal case|win the case|jail|prison|"
    r"bail|fir|divorce case|property dispute|mukadma|मुकदमा|जेल)\b",
    re.IGNORECASE,
)
_FINANCIAL = re.compile(
    r"\b(should i invest|stock|stocks|shares|crypto|bitcoin|mutual fund|"
    r"trading|gamble|lottery|satta|which (share|stock) should|"
    r"paisa lagana|nivesh karu|शेयर|निवेश)\b",
    re.IGNORECASE,
)
_FERTILITY = re.compile(
    r"\b(conceive|conception|pregnan|fertilit|ivf|baby|child|children|"
    r"becoming a (mother|father|parent)|santaan|bachcha|गर्भ|संतान|बच्चा)\b",
    re.IGNORECASE,
)


def _classify(question: str) -> tuple[str, str]:
    """Return (level, kind). level in {'hard','soft','none'}."""
    q = question or ""
    if _SELF_HARM.search(q):
        return "hard", "self_harm"
    if _DEATH_TIMING.search(q):
        return "hard", "death"
    if _MEDICAL.search(q):
        return "soft", "medical"
    if _LEGAL.search(q):
        return "soft", "legal"
    if _FINANCIAL.search(q):
        return "soft", "financial"
    if _FERTILITY.search(q):
        return "soft", "fertility"
    return "none", ""


_SELF_HARM_RESPONSE = (
    "I'm really glad you reached out, and I want to gently set astrology aside for a "
    "moment — what you're feeling matters far more than any chart.\n\n"
    "You don't have to carry this alone. Please consider talking to someone you trust, "
    "or a mental-health professional, who can support you properly right now. If you're "
    "in immediate distress, reaching out to a local emergency number or a crisis "
    "helpline in your country can help.\n\n"
    "I'm here to talk whenever you'd like — and your wellbeing comes first. 🙏"
)

_DEATH_RESPONSE = (
    "🙏 I won't predict death or its timing — that's not something I'll put a date on, "
    "and no responsible Jyotish reading should.\n\n"
    "What I *can* look at is your *health, vitality, and longevity practices* — the "
    "houses and periods that support strength and wellbeing, and remedies traditionally "
    "used for vitality. If you'd like, ask me about your *health outlook* or *current "
    "dasha for wellbeing* and I'll happily go into that."
)

_SOFT_DISCLAIMERS = {
    "medical": (
        "IMPORTANT: This question touches on health. In your answer you MUST: avoid any "
        "diagnosis or medical claim, never state a disease will or won't happen, frame "
        "everything as traditional Jyotish guidance only, and clearly advise consulting "
        "a qualified doctor for anything medical."
    ),
    "legal": (
        "IMPORTANT: This is a legal matter. In your answer you MUST: not predict a "
        "definite legal outcome (win/lose/jail), frame timing only as supportive or "
        "challenging periods, and advise consulting a qualified lawyer."
    ),
    "financial": (
        "IMPORTANT: This involves money/investments. In your answer you MUST: give NO "
        "specific investment advice (no stock/crypto picks, no buy/sell calls), speak "
        "only in general Jyotish terms about favourable/unfavourable financial periods, "
        "and clearly say this is not financial advice."
    ),
    "fertility": (
        "IMPORTANT: This involves children/fertility, an emotionally sensitive area. Be "
        "gentle and hopeful but never definitive. Do not guarantee or rule out a child. "
        "Frame timing as traditionally supportive periods only, and suggest consulting a "
        "doctor for medical concerns."
    ),
}


# ──────────────────────────────────────────────────────────────────────────────
# 2. CHART CONTEXT BUILDER  (turns final_structure into compact text for the LLM)
# ──────────────────────────────────────────────────────────────────────────────

def _planet_house_map(d1: dict) -> dict[str, int]:
    """Invert the D1 house_mapper into {planet_name: house_number}."""
    out = {}
    for house_num, occupants in (d1 or {}).items():
        for p in occupants:
            try:
                out[p["name"]] = int(house_num)
            except (KeyError, ValueError):
                continue
    return out


def _build_chart_context(kundli: dict) -> str:
    details   = kundli.get("details", {})
    planets   = kundli.get("planets_data", [])
    hmap      = kundli.get("house_mapper", {})
    d1        = hmap.get("D1", {})
    dasha     = kundli.get("dasha", {})
    doshas    = kundli.get("doshas", {})
    yogas     = kundli.get("yogas", {})
    transits  = kundli.get("transits", {})
    marriage  = kundli.get("marriage", {})

    p_house = _planet_house_map(d1)
    pm = {p["name"]: p for p in planets}

    lines = ["=== BIRTH CHART FACTS (computed; use ONLY these, do not invent) ==="]

    # Birth details
    if details:
        lines.append(
            f"Birth: {details.get('date_of_birth','?')} at "
            f"{details.get('time_of_birth','?')} IST. "
            f"Tithi: {details.get('tithi',{}).get('tithi_name','?')} "
            f"({details.get('tithi',{}).get('paksha','?')} Paksha)."
        )

    # Big three
    asc  = pm.get("Ascendant", {})
    moon = pm.get("Moon", {})
    sun  = pm.get("Sun", {})
    lines.append(
        f"Lagna (Ascendant): {asc.get('zodiac','?')}. "
        f"Moon sign: {moon.get('zodiac','?')} ({moon.get('Nakshatra','?')} nakshatra). "
        f"Sun sign: {sun.get('zodiac','?')}."
    )

    # Planetary placements
    lines.append("\nPlanetary placements (planet — sign — house from Lagna — nakshatra):")
    for p in planets:
        if p["name"] == "Ascendant":
            continue
        h = p_house.get(p["name"], "?")
        lines.append(
            f"  • {p['name']}: {p.get('zodiac','?')} — house {h} — "
            f"{p.get('Nakshatra','?')} (pada {p.get('Pada','?')})"
        )

    # Dasha
    cur = dasha.get("current", {})
    if cur:
        lines.append(
            f"\nCurrent dasha: Mahadasha {cur.get('mahadasha','?')} > "
            f"Antardasha {cur.get('antardasha','?')} > "
            f"Pratyantar {cur.get('pratyantar','?')} "
            f"(pratyantar ends {cur.get('pratyantar_end','?')})."
        )
    # Next few mahadashas
    all_md = dasha.get("all_mahadashas", [])
    if all_md:
        from datetime import datetime
        today = datetime.today()
        upcoming = []
        for md in all_md:
            try:
                end = datetime.strptime(md["end"], "%d-%m-%Y")
            except Exception:
                continue
            if end >= today:
                upcoming.append(f"{md['planet']} (till {md['end']})")
            if len(upcoming) >= 4:
                break
        if upcoming:
            lines.append("Upcoming/active Mahadashas: " + ", ".join(upcoming) + ".")

    # Active doshas
    active_doshas = []
    for key, d in (doshas or {}).items():
        if str(d.get("present", "False")).lower() == "true":
            active_doshas.append(f"{key.replace('_',' ')} (severity: {d.get('severity','?')})")
    if active_doshas:
        lines.append("\nActive doshas: " + "; ".join(active_doshas) + ".")
    else:
        lines.append("\nActive doshas: none significant.")

    # Active yogas
    active_yogas = []
    for key, y in (yogas or {}).items():
        if isinstance(y, dict) and str(y.get("present", "False")).lower() == "true":
            active_yogas.append(key.replace("_", " "))
    if active_yogas:
        lines.append("Notable yogas present: " + ", ".join(active_yogas) + ".")

    # Sade Sati / transit summary
    ssd = transits.get("sade_sati_dhaiya", {})
    if ssd.get("sade_sati", {}).get("active"):
        lines.append(
            f"Sade Sati is ACTIVE ({ssd['sade_sati'].get('phase','')})."
        )
    elif ssd.get("dhaiya", {}).get("active"):
        lines.append("Dhaiya (Kantaka Shani) is currently active.")

    # Marriage timing (the most-asked question — include if computed)
    if marriage and "error" not in marriage:
        mt = marriage.get("marriage_timing_dasha", {})
        windows = mt.get("near_future_marriage_windows", [])
        verdict = marriage.get("overall_quality", {}).get("overall_verdict", "")
        if verdict:
            lines.append(f"\nMarriage — overall assessment: {verdict}")
        if windows:
            lines.append("Marriage-favourable dasha windows (next ~10 yrs):")
            for w in windows[:3]:
                lines.append(
                    f"  • {w.get('mahadasha_planet','?')}/{w.get('antardasha_planet','?')} "
                    f"({w.get('antardasha_start','?')} – {w.get('antardasha_end','?')}) "
                    f"strength: {w.get('strength','?')}"
                )
        delay = marriage.get("delay_denial", {})
        if delay.get("severity") and delay["severity"] != "None":
            lines.append(f"Marriage delay indicator: {delay['severity']}.")

    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# 3. SYSTEM PROMPT
# ──────────────────────────────────────────────────────────────────────────────

def _system_prompt(name: str, gender: str, soft_kind: str) -> str:
    who = f"The querent's name is {name}. " if name else ""
    if gender:
        who += f"Gender: {gender}. "

    base = (
        "You are Hora, a warm, knowledgeable Vedic astrologer (Jyotish) speaking "
        "directly to a person about their own birth chart.\n\n"
        f"{who}\n"
        "RULES:\n"
        "1. Use ONLY the chart facts provided in the user message. NEVER invent or "
        "recalculate planetary positions, houses, or dasha dates. If a fact needed to "
        "answer isn't in the data, say so plainly.\n"
        "2. For 'when' questions, base timing on the dasha/antardasha periods given, and "
        "mention the relevant period and its dates. Be specific where the data allows.\n"
        "3. Explain your reasoning briefly in plain language (e.g. which house, lord, or "
        "dasha you're drawing on) so it feels like a real reading, not a fortune cookie.\n"
        "4. Be honest and grounded. Frame everything as traditional Jyotish interpretation "
        "and tendencies, NOT guaranteed events. Avoid absolute certainty. It's fine to say "
        "an outcome is 'likely', 'supported', or 'challenging' rather than certain.\n"
        "5. Reply in the SAME language the person used (English, Hindi, or Hinglish). Match "
        "their tone.\n"
        "6. Keep it focused: a few short paragraphs. End with one practical, encouraging "
        "note or a simple traditional remedy if relevant.\n"
        "7. FORMATTING (important): plain text with at most *single asterisks* for emphasis. "
        "Do NOT use **double asterisks**, markdown headers (#), bullet characters, or tables. "
        "Short paragraphs separated by blank lines only.\n"
    )
    if soft_kind and soft_kind in _SOFT_DISCLAIMERS:
        base += "\n" + _SOFT_DISCLAIMERS[soft_kind] + "\n"
    return base


# ──────────────────────────────────────────────────────────────────────────────
# 4. GEMINI CALL
# ──────────────────────────────────────────────────────────────────────────────


def _call_gemini(system_prompt: str, contents: list) -> str | None:
    """
    Call Gemini with the full conversation `contents`
    (a list of {"role": "user"|"model", "parts": [{"text": ...}]} turns).
    Returns the model's text, or None on any failure (-> template fallback).
    """
    if not GEMINI_API_KEY:
        print("[gemini] no GEMINI_API_KEY set — using template fallback.")
        return None

    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.75,
            "maxOutputTokens": 1200,
            "topP": 0.95,
        },
    }
    try:
        r = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json=payload,
            timeout=30,
        )
        if r.status_code == 429:
            print("[gemini] 429 rate/quota limit hit — using template fallback.")
            return None
        if not r.ok:
            print(f"[gemini] HTTP {r.status_code}: {r.text[:300]} — fallback.")
            return None

        data = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            print(f"[gemini] no candidates (feedback: {data.get('promptFeedback')}) — fallback.")
            return None

        cand = candidates[0]
        if cand.get("finishReason") == "SAFETY":
            print("[gemini] response blocked by safety — fallback.")
            return None

        parts = cand.get("content", {}).get("parts", [])
        text = "".join(p.get("text", "") for p in parts).strip()
        return text or None

    except Exception as e:
        print(f"[gemini] exception: {e} — fallback.")
        return None


def answer_question(
    question: str,
    kundli: dict,
    name: str = "",
    gender: str = "",
    history: list | None = None,
) -> str:
    """
    Answer a free-form astrology question grounded in the user's computed kundli.

    `history` is the running conversation for ONE session, a list of Gemini-format
    turns: [{"role": "user"|"model", "parts": [{"text": ...}]}, ...].
    Pass the SAME list object on every call for that session (store it in the
    user's cache). On a successful answer, this question and the reply are
    appended to `history` in place, so the next question has context.

    Always returns a string safe to send to Telegram/WhatsApp.
    """
    question = (question or "").strip()
    if not question:
        return "Please type your question — for example, *When will I get married?* 🙏"

    if history is None:
        history = []

    # ── Hard guardrails: never call the LLM (and don't record in history) ───
    level, kind = _classify(question)
    if level == "hard":
        if kind == "self_harm":
            return _SELF_HARM_RESPONSE
        if kind == "death":
            return _DEATH_RESPONSE

    # ── Chart facts go in the SYSTEM prompt so EVERY turn can see them ──────
    context = _build_chart_context(kundli)
    system  = (
        _system_prompt(name, gender, kind if level == "soft" else "")
        + "\n\n=== BIRTH CHART FACTS (use ONLY these; never recalculate) ===\n"
        + context
    )

    # ── Build the conversation: prior turns + this new question ────────────
    user_turn = {"role": "user", "parts": [{"text": question}]}
    contents  = history + [user_turn]          # new list; doesn't mutate history yet

    # ── Call Gemini; commit to history only on success ─────────────────────
    reply = _call_gemini(system, contents)
    if reply:
        history.append(user_turn)
        history.append({"role": "model", "parts": [{"text": reply}]})
        # Bound memory: keep the last 12 turns (6 Q&A pairs). Even count keeps
        # the trimmed history starting with a 'user' turn, as Gemini requires.
        if len(history) > 12:
            del history[:-12]
        return _sanitize_for_chat(reply)

    return _template_fallback(question, kundli, name)

# ──────────────────────────────────────────────────────────────────────────────
# 5. OUTPUT SANITISER  (keep Telegram/WhatsApp legacy-Markdown safe)
# ──────────────────────────────────────────────────────────────────────────────

def _sanitize_for_chat(text: str) -> str:
    if not text:
        return text
    # Double asterisks -> single (legacy Markdown bold is single *).
    text = text.replace("**", "*")
    # Strip markdown headers like "## Title" -> "Title".
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", text)
    # Convert [label](url) -> label (url).
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", text)
    # Unmatched emphasis markers crash Telegram's parser — if odd count, strip them.
    if text.count("*") % 2 != 0:
        text = text.replace("*", "")
    if text.count("_") % 2 != 0:
        text = text.replace("_", "")
    # Collapse 3+ blank lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ──────────────────────────────────────────────────────────────────────────────
# 6. TEMPLATE FALLBACK  (used when Gemini is unavailable)
# ──────────────────────────────────────────────────────────────────────────────

_FALLBACK_INTENTS = {
    "marriage": re.compile(r"\b(marr(y|ied|ying|iage)|spouse|partner|wedding|shaadi|shadi|vivah|life ?partner)\b", re.I),
    "career":   re.compile(r"\b(job|career|promotion|work|business|naukri|profession)\b", re.I),
    "wealth":   re.compile(r"\b(money|wealth|rich|finance|income|paisa|dhan|earning)\b", re.I),
}


def _template_fallback(question: str, kundli: dict, name: str) -> str:
    greeting = f"🙏 {name}, " if name else "🙏 "
    cur = kundli.get("dasha", {}).get("current", {})
    md = cur.get("mahadasha", "—")
    ad = cur.get("antardasha", "—")

    intent = None
    for key, pat in _FALLBACK_INTENTS.items():
        if pat.search(question or ""):
            intent = key
            break

    if intent == "marriage":
        mt = kundli.get("marriage", {}).get("marriage_timing_dasha", {})
        windows = mt.get("near_future_marriage_windows", [])
        verdict = kundli.get("marriage", {}).get("overall_quality", {}).get("overall_verdict", "")
        msg = greeting + "here is what your chart shows for marriage:\n\n"
        if verdict:
            msg += f"*Overall:* {verdict}\n\n"
        if windows:
            w = windows[0]
            msg += (
                f"*Most favourable upcoming window:* {w.get('mahadasha_planet','?')}/"
                f"{w.get('antardasha_planet','?')} dasha, around "
                f"{w.get('antardasha_start','?')} to {w.get('antardasha_end','?')} "
                f"({w.get('strength','')}). Marriage is traditionally more likely when "
                f"Jupiter or Venus transit your 7th house during such a period.\n\n"
            )
        else:
            msg += "I couldn't isolate a clear near-term window from the data.\n\n"
        msg += "_(Detailed AI reading is temporarily unavailable; this is a summary from your chart.)_"
        return _sanitize_for_chat(msg)

    # Generic fallback
    return _sanitize_for_chat(
        greeting + "I'm having trouble reaching the detailed reading service right now, "
        "so here's a quick note from your chart:\n\n"
        f"You're currently running the *{md}* Mahadasha and *{ad}* Antardasha, which "
        "sets the broad theme of this period. Please try your question again shortly for "
        "a full personalised answer.\n\n"
        "_(AI reading temporarily unavailable.)_"
    )



