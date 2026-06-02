"""
database.py
-----------
PostgreSQL storage for Hora Astrology Bot.

Works with any Postgres provider; tuned here for Neon (serverless Postgres):
  • Neon REQUIRES SSL — get_connection() forces sslmode=require.
  • Neon's free tier scales to zero when idle, so the first connection after a
    quiet spell may need a moment to wake; get_connection() retries briefly.
  • Use Neon's POOLED connection string (the host contains "-pooler") as your
    DATABASE_URL, since this app opens a short-lived connection per request.

Tables:
  • users        — one live row per user (primary key: chat_id)
  • user_archive — append-only history; one snapshot row per profile edit

Conversation memory lives on the users row:
  • qa_log       — JSONB list of {"q","a","ts"} (full record; never sent whole to Gemini)
  • chat_summary — TEXT rolling summary of older turns (sent to Gemini, token-bounded)
"""

import os
import time
from datetime import datetime, timezone
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor, Json

DATABASE_URL = os.getenv("DATABASE_URL")

# Retry the CONNECTION a few times to ride out a Neon cold start.
_CONNECT_RETRIES = 3
_CONNECT_BACKOFF = 2  # seconds; grows per attempt (2s, 4s, ...)

# Fields whose change invalidates the existing chart -> recompute + reset chat.
CHART_FIELDS = {"date_of_birth", "birth_time", "city", "latitude", "longitude"}


def get_connection():
    """
    Open a psycopg2 connection to Neon/Postgres.
    Forces SSL (Neon requires it) and retries briefly so a scale-to-zero
    wake-up doesn't fail the first query.
    """
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is not set. Add your Neon pooled connection string "
            "as the DATABASE_URL environment variable."
        )

    last_err = None
    for attempt in range(1, _CONNECT_RETRIES + 1):
        try:
            return psycopg2.connect(
                DATABASE_URL,
                cursor_factory=RealDictCursor,
                sslmode="require",       # Neon requires SSL
                connect_timeout=10,
            )
        except psycopg2.OperationalError as e:
            last_err = e
            print(f"[db] connect attempt {attempt}/{_CONNECT_RETRIES} failed: {e}")
            if attempt < _CONNECT_RETRIES:
                time.sleep(_CONNECT_BACKOFF * attempt)
    raise last_err


@contextmanager
def db_cursor(commit: bool = False):
    """
    Yield a cursor and ALWAYS close the connection afterwards — even on error —
    so failed queries can't leak connections (which matters under Neon's
    free-tier connection limits). Pass commit=True for writes.
    """
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create the users + user_archive tables if they don't exist. Run at startup."""
    users_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id                SERIAL PRIMARY KEY,
        chat_id           BIGINT UNIQUE NOT NULL,
        name              TEXT,
        gender            TEXT,
        date_of_birth     TEXT,
        birth_time        TEXT,
        city              TEXT,
        latitude          FLOAT,
        longitude         FLOAT,
        phone_number      TEXT,
        lagna             TEXT,
        moon_sign         TEXT,
        current_mahadasha TEXT,
        kundli_json       JSONB,
        qa_log            JSONB DEFAULT '[]'::jsonb,
        chat_summary      TEXT,
        daily_push        BOOLEAN DEFAULT TRUE,
        created_at        TIMESTAMP DEFAULT NOW(),
        updated_at        TIMESTAMP DEFAULT NOW()
    );
    """
    archive_sql = """
    CREATE TABLE IF NOT EXISTS user_archive (
        id                SERIAL PRIMARY KEY,
        chat_id           BIGINT NOT NULL,
        name              TEXT,
        gender            TEXT,
        date_of_birth     TEXT,
        birth_time        TEXT,
        city              TEXT,
        latitude          FLOAT,
        longitude         FLOAT,
        phone_number      TEXT,
        lagna             TEXT,
        moon_sign         TEXT,
        current_mahadasha TEXT,
        kundli_json       JSONB,
        qa_log            JSONB,
        chat_summary      TEXT,
        changed_field     TEXT,
        archived_at       TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(users_sql)
            cur.execute(archive_sql)
            # Safe upgrades for tables created by older versions.
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_push BOOLEAN DEFAULT TRUE;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS kundli_json JSONB;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS qa_log JSONB DEFAULT '[]'::jsonb;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS chat_summary TEXT;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_archive_chat_id ON user_archive(chat_id);")
        print("✅ Database initialized.")
    except Exception as e:
        print(f"❌ Database init error: {e}")


def _extract_signs(kundli_result: dict):
    """Pull lagna / moon_sign / current mahadasha out of a kundli result dict."""
    lagna = moon_sign = mahadasha = None
    if kundli_result:
        for p in kundli_result.get("planets_data", []):
            if p.get("name") == "Ascendant":
                lagna = p.get("zodiac")
            if p.get("name") == "Moon":
                moon_sign = p.get("zodiac")
        mahadasha = kundli_result.get("dasha", {}).get("current", {}).get("mahadasha")
    return lagna, moon_sign, mahadasha


def upsert_user(chat_id: int, user_data: dict, kundli_result: dict = None):
    """
    Insert or update a user record.
    user_data keys: name, gender, dob, birth_time, city, lat, lon, phone_number
    The full kundli (if given) is stored as JSONB in kundli_json so it survives
    restarts and can be reloaded without recomputing.
    NOTE: does not touch qa_log / chat_summary (managed separately).
    """
    lagna, moon_sign, mahadasha = _extract_signs(kundli_result)

    sql = """
    INSERT INTO users (
        chat_id, name, gender, date_of_birth, birth_time,
        city, latitude, longitude, phone_number,
        lagna, moon_sign, current_mahadasha, kundli_json, updated_at
    )
    VALUES (
        %(chat_id)s, %(name)s, %(gender)s, %(dob)s, %(birth_time)s,
        %(city)s, %(lat)s, %(lon)s, %(phone)s,
        %(lagna)s, %(moon_sign)s, %(mahadasha)s, %(kundli_json)s, NOW()
    )
    ON CONFLICT (chat_id) DO UPDATE SET
        name              = EXCLUDED.name,
        gender            = EXCLUDED.gender,
        date_of_birth     = EXCLUDED.date_of_birth,
        birth_time        = EXCLUDED.birth_time,
        city              = EXCLUDED.city,
        latitude          = EXCLUDED.latitude,
        longitude         = EXCLUDED.longitude,
        phone_number      = COALESCE(EXCLUDED.phone_number, users.phone_number),
        lagna             = EXCLUDED.lagna,
        moon_sign         = EXCLUDED.moon_sign,
        current_mahadasha = EXCLUDED.current_mahadasha,
        kundli_json       = EXCLUDED.kundli_json,
        updated_at        = NOW();
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(sql, {
                "chat_id":     chat_id,
                "name":        user_data.get("name"),
                "gender":      user_data.get("gender"),
                "dob":         user_data.get("dob"),
                "birth_time":  user_data.get("birth_time"),
                "city":        user_data.get("city"),
                "lat":         user_data.get("lat"),
                "lon":         user_data.get("lon"),
                "phone":       user_data.get("phone_number"),
                "lagna":       lagna,
                "moon_sign":   moon_sign,
                "mahadasha":   mahadasha,
                "kundli_json": Json(kundli_result) if kundli_result else None,
            })
        print(f"✅ User {chat_id} ({user_data.get('name')}) saved.")
    except Exception as e:
        print(f"❌ Save user error: {e}")


def get_user(chat_id: int):
    """Fetch a single live user by chat_id (returns None if not found)."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE chat_id = %s;", (chat_id,))
            row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"❌ Get user error: {e}")
        return None


def set_phone_number(chat_id: int, phone: str) -> bool:
    """Store a (Telegram-verified) phone number for a user."""
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE users SET phone_number = %s, updated_at = NOW() WHERE chat_id = %s;",
                (phone, chat_id),
            )
        return True
    except Exception as e:
        print(f"❌ Set phone error: {e}")
        return False


def archive_user(chat_id: int, changed_field: str = None) -> bool:
    """
    Copy the CURRENT users row into user_archive (append-only history).
    Call this BEFORE applying an update so the old state is preserved.
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO user_archive (
                    chat_id, name, gender, date_of_birth, birth_time,
                    city, latitude, longitude, phone_number,
                    lagna, moon_sign, current_mahadasha, kundli_json,
                    qa_log, chat_summary, changed_field, archived_at
                )
                SELECT
                    chat_id, name, gender, date_of_birth, birth_time,
                    city, latitude, longitude, phone_number,
                    lagna, moon_sign, current_mahadasha, kundli_json,
                    qa_log, chat_summary, %s, NOW()
                FROM users WHERE chat_id = %s;
                """,
                (changed_field, chat_id),
            )
        print(f"🗄️  Archived snapshot for {chat_id} (changed: {changed_field}).")
        return True
    except Exception as e:
        print(f"❌ Archive error: {e}")
        return False


def update_profile(chat_id: int, field: str, value, kundli_result: dict = None,
                   reset_conversation: bool = False) -> bool:
    """
    Update ONE profile field on the live row. If the change is chart-affecting,
    pass the freshly recomputed kundli_result (and reset_conversation=True) so
    the stored chart + signs are refreshed and the conversation memory cleared.

    Allowed `field` values map to columns directly:
      name, gender, date_of_birth, birth_time, city, latitude, longitude, phone_number
    """
    allowed = {
        "name", "gender", "date_of_birth", "birth_time",
        "city", "latitude", "longitude", "phone_number",
    }
    if field not in allowed:
        print(f"❌ update_profile: unknown field '{field}'")
        return False

    sets = [f"{field} = %(value)s", "updated_at = NOW()"]
    params = {"value": value, "chat_id": chat_id}

    if kundli_result is not None:
        lagna, moon_sign, mahadasha = _extract_signs(kundli_result)
        sets += [
            "kundli_json = %(kundli_json)s",
            "lagna = %(lagna)s",
            "moon_sign = %(moon_sign)s",
            "current_mahadasha = %(mahadasha)s",
        ]
        params.update({
            "kundli_json": Json(kundli_result),
            "lagna": lagna, "moon_sign": moon_sign, "mahadasha": mahadasha,
        })

    if reset_conversation:
        sets += ["qa_log = '[]'::jsonb", "chat_summary = NULL"]

    sql = f"UPDATE users SET {', '.join(sets)} WHERE chat_id = %(chat_id)s;"
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(sql, params)
        print(f"✏️  Updated {field} for {chat_id}"
              + (" (chart recomputed, conversation reset)" if reset_conversation else ""))
        return True
    except Exception as e:
        print(f"❌ Update profile error: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Conversation memory (qa_log + chat_summary)
# ─────────────────────────────────────────────────────────────

def get_conversation(chat_id: int):
    """Return (chat_summary, qa_log_list) for a user. Empty defaults if none."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT chat_summary, qa_log FROM users WHERE chat_id = %s;", (chat_id,))
            row = cur.fetchone()
        if not row:
            return None, []
        return row.get("chat_summary"), (row.get("qa_log") or [])
    except Exception as e:
        print(f"❌ Get conversation error: {e}")
        return None, []


def append_qa(chat_id: int, question: str, answer: str) -> bool:
    """Append one {q,a,ts} entry to the user's qa_log (full record)."""
    entry = {
        "q": question,
        "a": answer,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE users SET qa_log = COALESCE(qa_log, '[]'::jsonb) || %s::jsonb "
                "WHERE chat_id = %s;",
                (Json([entry]), chat_id),
            )
        return True
    except Exception as e:
        print(f"❌ Append QA error: {e}")
        return False


def save_summary_and_trim(chat_id: int, summary: str, keep_last: int) -> bool:
    """
    Store an updated rolling summary and trim qa_log to the last `keep_last`
    entries (older turns are now captured by the summary). Keeps chronological
    order in the trimmed log.
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                UPDATE users
                SET chat_summary = %(summary)s,
                    qa_log = (
                        SELECT COALESCE(jsonb_agg(elem ORDER BY ord), '[]'::jsonb)
                        FROM (
                            SELECT elem, ord
                            FROM jsonb_array_elements(COALESCE(qa_log, '[]'::jsonb))
                                 WITH ORDINALITY AS t(elem, ord)
                            ORDER BY ord DESC
                            LIMIT %(keep_last)s
                        ) sub
                    )
                WHERE chat_id = %(chat_id)s;
                """,
                {"summary": summary, "keep_last": keep_last, "chat_id": chat_id},
            )
        return True
    except Exception as e:
        print(f"❌ Save summary error: {e}")
        return False


def reset_conversation(chat_id: int) -> bool:
    """Clear qa_log and chat_summary (used when the chart changes)."""
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "UPDATE users SET qa_log = '[]'::jsonb, chat_summary = NULL WHERE chat_id = %s;",
                (chat_id,),
            )
        return True
    except Exception as e:
        print(f"❌ Reset conversation error: {e}")
        return False


# ─────────────────────────────────────────────────────────────
# Admin / broadcast
# ─────────────────────────────────────────────────────────────

def get_all_users_for_push() -> list:
    """Fetch all users who have daily_push enabled."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE daily_push = TRUE ORDER BY created_at DESC;")
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ Fetch users error: {e}")
        return []


def get_all_users_admin() -> list:
    """Fetch ALL users for admin view."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM users ORDER BY created_at DESC;")
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ Fetch users error: {e}")
        return []


def send_broadcast_message(bot_token: str, message: str) -> dict:
    """Send a custom message to ALL users with daily_push enabled."""
    import requests
    users = get_all_users_for_push()
    success = failed = 0
    for user in users:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": user["chat_id"], "text": message, "parse_mode": "Markdown"},
                timeout=8,
            )
            ok = r.json().get("ok")
            success += 1 if ok else 0
            failed  += 0 if ok else 1
        except Exception:
            failed += 1
    return {"total": len(users), "success": success, "failed": failed}