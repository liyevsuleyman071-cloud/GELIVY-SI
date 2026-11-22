"""Ümumi hissələr: ayarlar, Supabase, şablonlar, giriş (cookie) və köməkçi funksiyalar.

Bütün router-lar buradan import edir. Beləliklə `bot.py` yalnız süni intellekt
məntiqini saxlayır və dairəvi (circular) import problemi yaranmır.
"""

import hashlib
import hmac
import logging
import os
import re
import secrets
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from supabase import Client, create_client

load_dotenv()

logger = logging.getLogger("gelivyai")

# --------------------------------------------------------------------------- #
# Ayarlar (.env)
# --------------------------------------------------------------------------- #
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")  # webhook imzası üçün (ixtiyari)

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL və SUPABASE_KEY .env faylında olmalıdır.")

SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    # Təsadüfi açar: tətbiq hər yenidən başlayanda bütün istifadəçilər çıxış etmiş olur.
    SECRET_KEY = secrets.token_hex(32)
    logger.warning("SECRET_KEY təyin olunmayıb! .env faylına daimi bir dəyər yazın.")

COOKIE_NAME = "gelivyai_user"
COOKIE_MAX_AGE = 86400 * 90  # 90 gün
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"  # HTTPS-də 1 edin

# users cədvəlindəki şifrə sütunu (Supabase-dəki adla eyni olmalıdır).
PASSWORD_COL = "password-hash"

# --------------------------------------------------------------------------- #
# Supabase və şablonlar
# --------------------------------------------------------------------------- #
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# --------------------------------------------------------------------------- #
# HTMX köməkçiləri
# --------------------------------------------------------------------------- #
def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def redirect(request: Request, url: str) -> Response:
    """HTMX sorğusu üçün HX-Redirect, adi sorğu üçün 303 redirect qaytarır."""
    if is_htmx(request):
        return HTMLResponse("", headers={"HX-Redirect": url})
    return RedirectResponse(url, status_code=303)


# --------------------------------------------------------------------------- #
# İmzalı cookie (id cookie-də açıq yazılmır, saxtalaşdırmaq olmur)
# --------------------------------------------------------------------------- #
def _sign(value: str) -> str:
    return hmac.new(SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def make_cookie_value(user_id) -> str:
    value = str(user_id)
    return f"{value}.{_sign(value)}"


def read_cookie_value(raw: Optional[str]) -> Optional[str]:
    if not raw or "." not in raw:
        return None
    value, _, signature = raw.rpartition(".")
    if hmac.compare_digest(signature, _sign(value)):
        return value
    return None


def set_login_cookie(response: Response, user_id) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=make_cookie_value(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


def clear_login_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


# --------------------------------------------------------------------------- #
# İstifadəçi
# --------------------------------------------------------------------------- #
class LoginRequired(Exception):
    """Giriş tələb olunan səhifədə istifadəçi daxil olmayıb."""


def get_current_user(request: Request) -> Optional[dict]:
    user_id = read_cookie_value(request.cookies.get(COOKIE_NAME))
    if not user_id:
        return None
    res = (
        supabase.table("users")
        .select("id, name, phone")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def require_user(request: Request) -> dict:
    """FastAPI dependency: giriş yoxdursa LoginRequired atır (main.py-da tutulur)."""
    user = get_current_user(request)
    if not user:
        raise LoginRequired()
    return user


def normalize_phone(raw: str) -> Optional[str]:
    """Azərbaycan nömrələrini +994XXXXXXXXX formasına salır. Yanlışdırsa None."""
    raw = (raw or "").strip()
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("994") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 10:
        return "+994" + digits[1:]
    if len(digits) == 9:
        return "+994" + digits
    if raw.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    return None


# --------------------------------------------------------------------------- #
# Söhbətlər
# --------------------------------------------------------------------------- #
def parse_uuid(value: str) -> Optional[str]:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return None


def list_chats(user_id, limit: int = 50) -> list:
    res = (
        supabase.table("chats")
        .select("id, title")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_chat(user_id, chat_id: str) -> Optional[dict]:
    res = (
        supabase.table("chats")
        .select("id, title, messages")
        .eq("id", chat_id)
        .eq("user_id", str(user_id))
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    chat = res.data[0]
    chat["messages"] = chat.get("messages") or []
    return chat


def page_context(user: dict, **extra) -> dict:
    """Sidebar-ı olan səhifələr üçün ümumi context."""
    context = {
        "title": "Gelivy AI",
        "user": user,
        "chats": list_chats(user["id"]),
        "chat_id": None,
        "page": "",
    }
    context.update(extra)
    return context
