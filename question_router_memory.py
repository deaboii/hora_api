# ══════════════════════════════════════════════════════════════════════════════
# DROP-IN REPLACEMENTS for question_router.py
#
# Replace your existing `_call_gemini` and `answer_question` with the two
# functions below. Everything else in question_router.py stays exactly the same
# (_classify, _build_chart_context, _system_prompt, _sanitize_for_chat,
#  _template_fallback, the regexes, the canned responses, etc.).
#
# WHAT CHANGED & WHY:
#   • Your old code sent Gemini ONE user turn, so it had no memory. A follow-up
#     like "from where will she be?" had no idea who "she" was, so it rephrased
#     the previous marriage answer.
#   • Now each session keeps a running conversation (a list of turns). The chart
#     facts move into the SYSTEM instruction so they're available on every turn,
#     and the back-and-forth goes into `contents`. Follow-ups now resolve
#     pronouns and build on earlier answers.
#   • On an LLM failure we DON'T record the exchange, so a transient error never
#     poisons the history.
# ══════════════════════════════════════════════════════════════════════════════


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
