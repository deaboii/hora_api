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

Public API (unchanged): init_db, upsert_user, get_all_users_for_push,
get_all_users_admin, send_broadcast_message.
"""
from __future__ import annotations

import os
import json
import time
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor, Json

DATABASE_URL = os.getenv("DATABASE_URL")

# Retry the CONNECTION a few times to ride out a Neon cold start.
_CONNECT_RETRIES = 3
_CONNECT_BACKOFF = 2  # seconds; grows per attempt (2s, 4s, ...)


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
            # Common while Neon is waking from idle — wait and retry.
            last_err = e
            print(f"[db] connect attempt {attempt}/{_CONNECT_RETRIES} failed: {e}")
            if attempt < _CONNECT_RETRIES:
                time.sleep(_CONNECT_BACKOFF * attempt)
    # Out of retries — surface the last error to the caller's try/except.
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
    """Create the users table if it doesn't exist. Called once at startup."""
    sql = """
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
        daily_push        BOOLEAN DEFAULT TRUE,
        created_at        TIMESTAMP DEFAULT NOW(),
        updated_at        TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(sql)
            # Safe upgrades for tables created by older versions.
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_push BOOLEAN DEFAULT TRUE;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS kundli_json JSONB;")
        print("✅ Database initialized.")
    except Exception as e:
        print(f"❌ Database init error: {e}")


def upsert_user(chat_id: int, user_data: dict, kundli_result: dict = None):
    """
    Insert or update a user record.
    user_data keys: name, gender, dob, birth_time, city, lat, lon, phone_number
    The full kundli (if given) is stored as JSONB in kundli_json so it survives
    restarts and can be reloaded without recomputing.
    """
    lagna = moon_sign = mahadasha = None

    if kundli_result:
        for p in kundli_result.get("planets_data", []):
            if p["name"] == "Ascendant":
                lagna = p["zodiac"]
            if p["name"] == "Moon":
                moon_sign = p["zodiac"]
        mahadasha = kundli_result.get("dasha", {}).get("current", {}).get("mahadasha")

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
        phone_number      = EXCLUDED.phone_number,
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
                # psycopg2's Json adapter -> proper JSONB; None stays NULL.
                "kundli_json": Json(kundli_result) if kundli_result else None,
            })
        print(f"✅ User {chat_id} ({user_data.get('name')}) saved.")
    except Exception as e:
        print(f"❌ Save user error: {e}")


def get_user(chat_id: int) -> dict | None:
    """Fetch a single user by chat_id (returns None if not found)."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT * FROM users WHERE chat_id = %s;", (chat_id,))
            row = cur.fetchone()
        return dict(row) if row else None
    except Exception as e:
        print(f"❌ Get user error: {e}")
        return None


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
