"""
database.py
-----------
Handles PostgreSQL connection and user data storage for Hora Astrology Bot.

Setup on Render:
1. Go to Render Dashboard → New → PostgreSQL (free tier)
2. Copy the "Internal Database URL"
3. Add it as an environment variable: DATABASE_URL=<your-url>
"""
from __future__ import annotations

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    """Get a PostgreSQL connection."""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    """
    Create the users table if it doesn't exist.
    Call this once at app startup.
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id               SERIAL PRIMARY KEY,
        chat_id          BIGINT UNIQUE NOT NULL,
        name             TEXT,
        gender           TEXT,
        date_of_birth    TEXT,
        birth_time       TEXT,
        city             TEXT,
        latitude         FLOAT,
        longitude        FLOAT,
        lagna            TEXT,
        moon_sign        TEXT,
        current_mahadasha TEXT,
        created_at       TIMESTAMP DEFAULT NOW(),
        updated_at       TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(create_table_sql)
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"❌ Database init error: {e}")


def upsert_user(chat_id: int, user_data: dict, kundli_result: dict = None):
    """
    Insert or update a user record.

    user_data keys: name, gender, dob, birth_time, city, lat, lon
    kundli_result: the full dict returned by generate_kundli()
    """

    # Extract useful fields from kundli result
    lagna = None
    moon_sign = None
    mahadasha = None

    if kundli_result:
        planets = kundli_result.get("planets_data", [])
        for p in planets:
            if p["name"] == "Ascendant":
                lagna = p["zodiac"]
            if p["name"] == "Moon":
                moon_sign = p["zodiac"]
        mahadasha = kundli_result.get("dasha", {}).get("current", {}).get("mahadasha")

    sql = """
    INSERT INTO users (
        chat_id, name, gender, date_of_birth, birth_time,
        city, latitude, longitude, lagna, moon_sign,
        current_mahadasha, updated_at
    )
    VALUES (
        %(chat_id)s, %(name)s, %(gender)s, %(dob)s, %(birth_time)s,
        %(city)s, %(lat)s, %(lon)s, %(lagna)s, %(moon_sign)s,
        %(mahadasha)s, NOW()
    )
    ON CONFLICT (chat_id) DO UPDATE SET
        name              = EXCLUDED.name,
        gender            = EXCLUDED.gender,
        date_of_birth     = EXCLUDED.date_of_birth,
        birth_time        = EXCLUDED.birth_time,
        city              = EXCLUDED.city,
        latitude          = EXCLUDED.latitude,
        longitude         = EXCLUDED.longitude,
        lagna             = EXCLUDED.lagna,
        moon_sign         = EXCLUDED.moon_sign,
        current_mahadasha = EXCLUDED.current_mahadasha,
        updated_at        = NOW();
    """

    params = {
        "chat_id": chat_id,
        "name": user_data.get("name"),
        "gender": user_data.get("gender"),
        "dob": user_data.get("dob"),
        "birth_time": user_data.get("birth_time"),
        "city": user_data.get("city"),
        "lat": user_data.get("lat"),
        "lon": user_data.get("lon"),
        "lagna": lagna,
        "moon_sign": moon_sign,
        "mahadasha": mahadasha,
    }

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ User {chat_id} ({user_data.get('name')}) saved to database.")
    except Exception as e:
        print(f"❌ Failed to save user {chat_id}: {e}")


def get_all_users() -> list:
    """Fetch all stored users (for admin/broadcast use)."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users ORDER BY created_at DESC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ Failed to fetch users: {e}")
        return []


def get_user_by_chat_id(chat_id: int) -> dict | None:
    """Fetch a single user by Telegram chat_id."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE chat_id = %s;", (chat_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"❌ Failed to fetch user {chat_id}: {e}")
        return None


def send_broadcast_message(bot_token: str, message: str) -> dict:
    """
    Send a message to ALL stored users.
    Returns a summary of successes and failures.

    Usage:
        from database import send_broadcast_message
        result = send_broadcast_message(BOT_TOKEN, "🌟 New feature released!")
    """
    import requests

    users = get_all_users()
    success, failed = 0, 0

    for user in users:
        chat_id = user["chat_id"]
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                },
                timeout=8,
            )
            if r.json().get("ok"):
                success += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return {"total": len(users), "success": success, "failed": failed}