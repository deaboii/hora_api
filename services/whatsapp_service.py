"""
whatsapp_service.py
-------------------
Sends messages via the WhatsApp Cloud API (Meta).

Mirrors the Telegram send_message / send_typing helpers used in main.py
so we can re-use the existing kundli + forecast pipeline with minimal changes.
"""

from __future__ import annotations

import os
import requests

WHATSAPP_TOKEN           = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

GRAPH_API_VERSION = "v21.0"
WHATSAPP_API_URL  = (
    f"https://graph.facebook.com/{GRAPH_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Telegram → WhatsApp Markdown conversion
#
# Telegram uses *bold*, _italic_, `code`.
# WhatsApp uses *bold*, _italic_, ```monospace block```.
# Single backticks must be removed (WhatsApp shows them literally).
# ─────────────────────────────────────────────────────────────────────────────

def _telegram_to_whatsapp_markdown(text: str) -> str:
    # WhatsApp doesn't support inline `code`. Strip single backticks.
    text = text.replace("`", "")
    return text


def send_message(to: str, text: str) -> dict:
    """
    Send a plain text message to a WhatsApp user.

    `to` must be the user's phone number in international format,
    *without* the leading '+', as received in the webhook (e.g. "919XXXXXXXXX").

    WhatsApp's hard cap is 4096 chars per body. We chunk just like Telegram.
    """
    text = _telegram_to_whatsapp_markdown(text)
    max_len = 4000
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]

    last_response = {}
    for chunk in chunks:
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type":    "individual",
            "to":                to,
            "type":              "text",
            "text":              {"body": chunk, "preview_url": False},
        }
        try:
            r = requests.post(WHATSAPP_API_URL, headers=_headers(),
                              json=payload, timeout=10)
            last_response = r.json()
            if not r.ok:
                print(f"[WhatsApp] send_message failed → {r.status_code}: {last_response}")
        except Exception as e:
            print(f"[WhatsApp] send_message exception: {e}")
    return last_response


def send_typing(to: str) -> None:
    """
    WhatsApp Cloud API has no public 'typing' indicator yet.
    Kept as a no-op so the same main.py flow works without branching.
    """
    return None


def mark_read(message_id: str) -> None:
    """
    Optional: mark the user's last incoming message as 'read' (blue ticks).
    Helps make the bot feel responsive.
    """
    payload = {
        "messaging_product": "whatsapp",
        "status":            "read",
        "message_id":        message_id,
    }
    try:
        requests.post(WHATSAPP_API_URL, headers=_headers(),
                      json=payload, timeout=5)
    except Exception as e:
        print(f"[WhatsApp] mark_read exception: {e}")
