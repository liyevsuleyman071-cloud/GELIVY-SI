import bcrypt
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core import (
    PASSWORD_COL,
    clear_login_cookie,
    get_current_user,
    is_htmx,
    normalize_phone,
    redirect,
    set_login_cookie,
    supabase,
    templates,
)

router = APIRouter(prefix="/auth", tags=["Auth"])

AFTER_LOGIN_URL = "/chat"


def render_error(request: Request, page: str, title: str, message: str, **context):
    """HTMX-də yalnız xəta qutusunu, adi sorğuda bütün səhifəni qaytarır."""
    if is_htmx(request):
        return templates.TemplateResponse(
            request=request, name="partials/alert.html", context={"error": message}
        )
    return templates.TemplateResponse(
        request=request,
        name=page,
        context={"title": title, "error": message, **context},
    )


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), (hashed or "").encode("utf-8"))
    except ValueError:  # bozuq hash
        return False


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(AFTER_LOGIN_URL, status_code=303)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"title": "Daxil ol · Gelivy AI"}
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, phone: str = Form(...), password: str = Form(...)):
    # Köhnə qeydlər fərqli formatda yazılmış ola bilər, ona görə hər iki variantı yoxlayırıq.
    candidates = {phone.strip()}
    normalized = normalize_phone(phone)
    if normalized:
        candidates.add(normalized)

    result = (
        supabase.table("users")
        .select("*")
        .in_("phone", list(candidates))
        .limit(1)
        .execute()
    )
    user = result.data[0] if result.data else None

    if not user or not verify_password(password, user.get(PASSWORD_COL, "")):
        # Eyni mesaj: nömrənin qeydiyyatda olub-olmadığı bilinməsin.
        return render_error(
            request,
            "login.html",
            "Daxil ol · Gelivy AI",
            "Nömrə və ya şifrə yanlışdır.",
            phone=phone,
        )

    response = redirect(request, AFTER_LOGIN_URL)
    set_login_cookie(response, user["id"])
    return response


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(AFTER_LOGIN_URL, status_code=303)
    return templates.TemplateResponse(
        request=request, name="signup.html", context={"title": "Qeydiyyat · Gelivy AI"}
    )


@router.post("/signup", response_class=HTMLResponse)
def signup_submit(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    password: str = Form(...),
):
    title = "Qeydiyyat · Gelivy AI"
    name = name.strip()
    phone_value = normalize_phone(phone)
    form_values = {"name": name, "phone": phone}

    if not 2 <= len(name) <= 50:
        return render_error(request, "signup.html", title, "Ad 2-50 simvol arasında olmalıdır.", **form_values)
    if not phone_value:
        return render_error(request, "signup.html", title, "Telefon nömrəsi düzgün deyil.", **form_values)
    if len(password) < 8:
        return render_error(request, "signup.html", title, "Şifrə ən azı 8 simvol olmalıdır.", **form_values)
    if len(password.encode("utf-8")) > 72:  # bcrypt limiti
        return render_error(request, "signup.html", title, "Şifrə çox uzundur (maksimum 72 bayt).", **form_values)

    existing = supabase.table("users").select("id").eq("phone", phone_value).limit(1).execute()
    if existing.data:
        return render_error(request, "signup.html", title, "Bu nömrə artıq qeydiyyatdan keçib.", **form_values)

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    try:
        created = (
            supabase.table("users")
            .insert({"phone": phone_value, "name": name, PASSWORD_COL: hashed})
            .execute()
        )
    except Exception:
        return render_error(request, "signup.html", title, "Qeydiyyat zamanı xəta baş verdi.", **form_values)

    if not created.data:
        return render_error(request, "signup.html", title, "Qeydiyyat zamanı xəta baş verdi.", **form_values)

    response = redirect(request, AFTER_LOGIN_URL)
    set_login_cookie(response, created.data[0]["id"])
    return response


@router.post("/logout")
def logout(request: Request):
    response = redirect(request, "/auth/login")
    clear_login_cookie(response)
    return response
