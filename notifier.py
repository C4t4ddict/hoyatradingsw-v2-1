import json
import os
import urllib.parse
import urllib.request
from typing import Optional
from security import resolve_secret


def _telegram_config(channel: str = "default"):
    if channel == "paper":
        token = resolve_secret("PAPER_ALERT_TELEGRAM_BOT_TOKEN").strip() or resolve_secret("ALERT_TELEGRAM_BOT_TOKEN").strip()
        chat_id = resolve_secret("PAPER_ALERT_TELEGRAM_CHAT_ID").strip() or resolve_secret("ALERT_TELEGRAM_CHAT_ID").strip()
    else:
        token = resolve_secret("ALERT_TELEGRAM_BOT_TOKEN").strip()
        chat_id = resolve_secret("ALERT_TELEGRAM_CHAT_ID").strip()
    return token, chat_id


def send_telegram(text: str, channel: str = "default") -> bool:
    token, chat_id = _telegram_config(channel=channel)
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            parsed = json.loads(body)
            return bool(parsed.get("ok"))
    except Exception:
        return False


def maybe_alert(title: str, detail: Optional[str] = None):
    msg = f"🚨 {title}"
    if detail:
        msg += f"\n{detail}"
    send_telegram(msg)
