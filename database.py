"""
database.py
-----------
Handles PostgreSQL connection and user data storage for Hora Astrology Bot.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


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
        daily_push        BOOLEAN DEFAULT TRUE,
        created_at        TIMESTAMP DEFAULT NOW(),
        updated_at        TIMESTAMP DEFAULT NOW()
    );
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        # Safe upgrades for existing tables
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number TEXT;")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_push BOOLEAN DEFAULT TRUE;")
        conn.commit()
        cur.close()
        conn.close()
        print("✅ Database initialized.")
    except Exception as e:
        print(f"❌ Database init error: {e}")


def upsert_user(chat_id: int, user_data: dict, kundli_result: dict = None):
    """
    Insert or update a user record.
    user_data keys: name, gender, dob, birth_time, city, lat, lon, phone_number
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
        lagna, moon_sign, current_mahadasha, updated_at
    )
    VALUES (
        %(chat_id)s, %(name)s, %(gender)s, %(dob)s, %(birth_time)s,
        %(city)s, %(lat)s, %(lon)s, %(phone)s,
        %(lagna)s, %(moon_sign)s, %(mahadasha)s, NOW()
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
        updated_at        = NOW();
    """
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql, {
            "chat_id":    chat_id,
            "name":       user_data.get("name"),
            "gender":     user_data.get("gender"),
            "dob":        user_data.get("dob"),
            "birth_time": user_data.get("birth_time"),
            "city":       user_data.get("city"),
            "lat":        user_data.get("lat"),
            "lon":        user_data.get("lon"),
            "phone":      user_data.get("phone_number"),
            "lagna":      lagna,
            "moon_sign":  moon_sign,
            "mahadasha":  mahadasha,
        })
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ User {chat_id} ({user_data.get('name')}) saved.")
    except Exception as e:
        print(f"❌ Save user error: {e}")


def get_all_users_for_push() -> list:
    """Fetch all users who have daily_push enabled."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE daily_push = TRUE ORDER BY created_at DESC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"❌ Fetch users error: {e}")
        return []


def get_all_users_admin() -> list:
    """Fetch ALL users for admin view."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users ORDER BY created_at DESC;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
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
            success += 1 if r.json().get("ok") else 0
            failed  += 0 if r.json().get("ok") else 1
        except Exception:
            failed += 1
    return {"total": len(users), "success": success, "failed": failed}