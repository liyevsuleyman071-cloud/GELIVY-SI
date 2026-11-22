from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

from core import (
    LoginRequired,
    get_current_user,
    page_context,
    redirect,
    templates,
)
from routers import auth, chat, webhook

app = FastAPI(title="Gelivy AI")

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(webhook.router)


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    # HTMX sorğusunda HX-Redirect, adi sorğuda 303 redirect.
    return redirect(request, "/auth/login")


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    user = get_current_user(request)
    if not user:
        return redirect(request, "/auth/login")
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context=page_context(user, title="Gelivy AI", page="home"),
    )


@app.get("/healthz", response_class=PlainTextResponse)
def healthz():
    return "ok"
